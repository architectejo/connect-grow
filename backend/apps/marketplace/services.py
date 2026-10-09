"""Interface publique du domaine `marketplace`.

Les autres domaines (reviews, messaging, moderation, payments...) ne lisent jamais les
modèles de `marketplace` : ils passent par ces fonctions, qui renvoient des structures
immuables et proposent des variantes par lot (`*_by_ids`). La logique métier du cycle de
vie d'une offre (publication, pause, vente, renouvellement, corbeille, score) est ici.
"""
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional

from django.db import transaction
from django.db.models import Count, F
from django.utils import timezone

from apps.common.utils import day_bounds, parse_uuid
from apps.messaging import services as messaging_services
from apps.notifications import services as notification_services
from apps.visibility import services as visibility_services

from .models import ContactEvent, ExchangeProposal, Favorite, MarketplaceSettings, Offer


class MarketplaceError(Exception):
    """Refus métier (message en français destiné à l'utilisateur)."""


class OfferHiddenError(MarketplaceError):
    """L'offre est masquée par la modération : le vendeur ne peut pas la remettre en ligne."""


DUPLICATE_CONTACT_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class OfferInfo:
    id: uuid.UUID
    seller_id: uuid.UUID
    title: str
    main_image_url: Optional[str]
    is_active: bool
    is_deleted: bool

    @property
    def is_available(self) -> bool:
        """Visible sur la marketplace : active (ni masquée, ni en pause, vendue ou expirée) et hors corbeille."""
        return self.is_active and not self.is_deleted


def _info(offer: Offer) -> OfferInfo:
    return OfferInfo(
        id=offer.id, seller_id=offer.seller_id, title=offer.title,
        main_image_url=offer.main_image.url if offer.main_image else None,
        is_active=offer.is_active, is_deleted=offer.is_deleted,
    )


# --- Lecture pour les autres domaines ---------------------------------------

def get_offers_by_ids(ids: Iterable) -> dict:
    """Offres indexées par UUID, en une requête (y compris celles en corbeille)."""
    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    if not wanted:
        return {}
    return {o.id: _info(o) for o in Offer.objects.filter(id__in=wanted)}


def get_offer(offer_id) -> Optional[OfferInfo]:
    parsed = parse_uuid(offer_id)
    if parsed is None:
        return None
    return get_offers_by_ids([parsed]).get(parsed)


def offer_exists(offer_id) -> bool:
    parsed = parse_uuid(offer_id)
    return parsed is not None and Offer.objects.filter(id=parsed).exists()


def count_active_offers(seller_id=None) -> int:
    """Offres visibles sur la marketplace (actives, hors corbeille), d'un vendeur ou de tous."""
    queryset = Offer.objects.filter(is_active=True, is_deleted=False)
    if seller_id is not None:
        queryset = queryset.filter(seller_id=seller_id)
    return queryset.count()


def get_contact_sender_ids(offer_id) -> set:
    """Identifiants des utilisateurs ayant contacté l'offre (historique des contacts)."""
    return set(ContactEvent.objects.filter(offer_id=offer_id).values_list('sender_id', flat=True))


def hide_by_moderation(offer_id) -> None:
    """Masque une offre (sanction « masquage d'annonce ») : état explicite + retrait de la marketplace."""
    Offer.objects.filter(pk=offer_id).update(is_hidden_by_moderation=True, is_active=False)


def lift_moderation_hiding(offer_id) -> None:
    """Lève le masquage. N'active l'offre que si elle est encore en statut ACTIVE : une offre
    vendue, expirée ou mise en pause reste hors ligne."""
    Offer.objects.filter(pk=offer_id).update(is_hidden_by_moderation=False)
    Offer.objects.filter(pk=offer_id, status=Offer.STATUS_ACTIVE, is_deleted=False).update(is_active=True)


def count_contacts_by_offer(day: date) -> list:
    """(offer_id, seller_id, total) des contacts reçus un jour donné (agrégat du tableau de bord)."""
    start, end = day_bounds(day)
    rows = (
        ContactEvent.objects.filter(created_at__gte=start, created_at__lt=end)
        .values('offer_id', 'offer__seller_id')
        .annotate(total=Count('id'))
    )
    return [(row['offer_id'], row['offer__seller_id'], row['total']) for row in rows]


# --- Score de visibilité -----------------------------------------------------

def refresh_visibility_score(offer: Offer, settings_row=None) -> None:
    """Recalcule et enregistre le score de visibilité d'une offre (CDC 3.8)."""
    offer.visibility_score = visibility_services.compute_score(
        views=offer.views_count, likes=offer.likes_count, comments=offer.comments_count,
        shares=offer.shares_count, created_at=offer.created_at,
        trust_score=offer.seller.trust_score, settings_row=settings_row,
    )
    offer.last_score_update = timezone.now()
    offer.save(update_fields=['visibility_score', 'last_score_update'])


def _refresh_scores(queryset) -> int:
    offers = list(queryset.select_related('seller'))
    settings_row = visibility_services.get_ranking_settings()
    now = timezone.now()
    for offer in offers:
        offer.visibility_score = visibility_services.compute_score(
            views=offer.views_count, likes=offer.likes_count, comments=offer.comments_count,
            shares=offer.shares_count, created_at=offer.created_at,
            trust_score=offer.seller.trust_score, settings_row=settings_row, now=now,
        )
        offer.last_score_update = now
    Offer.objects.bulk_update(offers, ['visibility_score', 'last_score_update'], batch_size=200)
    return len(offers)


def refresh_seller_offer_scores(seller_id) -> int:
    """Recalcule le score de toutes les offres actives d'un vendeur (son Trust Score a changé)."""
    return _refresh_scores(Offer.objects.filter(seller_id=seller_id, is_active=True, is_deleted=False))


def refresh_all_scores() -> int:
    """Recalcule le score de toutes les offres actives (action d'administration)."""
    return _refresh_scores(Offer.objects.filter(is_active=True, is_deleted=False))


# --- Cycle de vie (CDC 3.2, 3.9, 3.10) ----------------------------------------

def _expiration_days() -> int:
    return MarketplaceSettings.get_solo().expiration_days


def _refuse_if_hidden(offer: Offer) -> None:
    if offer.is_hidden_by_moderation:
        raise OfferHiddenError("Cette annonce a été masquée par la modération : vous ne pouvez pas la remettre en ligne.")


def renew_offer(offer: Offer) -> None:
    _refuse_if_hidden(offer)
    offer.status = Offer.STATUS_ACTIVE
    offer.is_active = True
    offer.expires_at = timezone.now() + timedelta(days=_expiration_days())
    offer.expiring_soon_notified = False
    offer.save(update_fields=['status', 'is_active', 'expires_at', 'expiring_soon_notified', 'updated_at'])


def mark_offer_sold(offer: Offer) -> None:
    offer.status = Offer.STATUS_SOLD
    offer.is_active = False
    offer.save(update_fields=['status', 'is_active', 'updated_at'])


def pause_offer(offer: Offer) -> None:
    offer.status = Offer.STATUS_PAUSED
    offer.is_active = False
    offer.save(update_fields=['status', 'is_active', 'updated_at'])


def unpause_offer(offer: Offer) -> bool:
    """Remet l'offre en ligne ; renvoie False (et la marque expirée) si son échéance est passée.
    Refusé (OfferHiddenError) tant que la modération la masque."""
    _refuse_if_hidden(offer)
    if offer.expires_at and offer.expires_at < timezone.now():
        offer.status = Offer.STATUS_EXPIRED
        offer.save(update_fields=['status', 'updated_at'])
        return False
    offer.status = Offer.STATUS_ACTIVE
    offer.is_active = True
    offer.save(update_fields=['status', 'is_active', 'updated_at'])
    return True


def move_to_trash(offer: Offer) -> None:
    offer.is_deleted = True
    offer.deleted_at = timezone.now()
    offer.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])


def restore_from_trash(offer: Offer) -> None:
    offer.is_deleted = False
    offer.deleted_at = None
    offer.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])


def delete_offers(queryset) -> int:
    """Suppression définitive : l'offre, sa galerie, ses favoris et contacts (cascade interne),
    puis les compteurs de visibilité. Les avis, affaires et conversations liés sont conservés
    (CDC 3.10) : ils gardent l'UUID de l'offre, qui n'existe plus."""
    ids = list(queryset.values_list('id', flat=True))
    if not ids:
        return 0
    with transaction.atomic():
        Offer.objects.filter(id__in=ids).delete()
    visibility_services.delete_offer_data(ids)
    return len(ids)


def purge_expired_trash(retention_days: Optional[int] = None) -> int:
    retention_days = MarketplaceSettings.get_solo().trash_retention_days if retention_days is None else retention_days
    cutoff = timezone.now() - timedelta(days=retention_days)
    return delete_offers(Offer.objects.filter(is_deleted=True, deleted_at__lt=cutoff))


def expire_offers() -> tuple:
    """Expire les offres actives échues et notifie les échéances proches (CDC 3.2, 3.6).
    Renvoie (nombre d'offres expirées, nombre de notifications envoyées)."""
    now = timezone.now()
    row = MarketplaceSettings.get_solo()

    expired_count = Offer.objects.filter(
        status=Offer.STATUS_ACTIVE, is_deleted=False, expires_at__lt=now,
    ).update(status=Offer.STATUS_EXPIRED, is_active=False)

    warning_cutoff = now + timedelta(days=row.expiring_soon_warning_days)
    soon = Offer.objects.filter(
        status=Offer.STATUS_ACTIVE, is_deleted=False, expires_at__gte=now,
        expires_at__lte=warning_cutoff, expiring_soon_notified=False,
    )
    notified = 0
    for offer in soon:
        notification_services.notify(
            user_id=offer.seller_id,
            notification_type=notification_services.EXPIRATION,
            title="Votre annonce expire bientôt",
            content=f"« {offer.title} » expire le {offer.expires_at:%d/%m/%Y}. Renouvelez-la pour rester visible.",
            link=f"/post/{offer.id}",
        )
        Offer.objects.filter(pk=offer.pk).update(expiring_soon_notified=True)
        notified += 1
    return expired_count, notified


# --- Engagement ---------------------------------------------------------------

def register_view(offer: Offer, viewer_key: str) -> bool:
    """CDC 3.8 : une vue unique par jour et par visiteur. Met à jour le total, les compteurs
    journaliers (visibility) et le score. Renvoie True si la vue est nouvelle."""
    if not visibility_services.record_view(offer_id=offer.id, seller_id=offer.seller_id, viewer_key=viewer_key):
        return False
    Offer.objects.filter(pk=offer.pk).update(views_count=F('views_count') + 1)
    offer.refresh_from_db(fields=['views_count'])
    refresh_visibility_score(offer)
    return True


def register_share(offer: Offer, user) -> int:
    """CDC 3.4 : partage externe, compteur qui alimente l'engagement. Un utilisateur ne compte
    qu'une fois par offre et par jour."""
    if not visibility_services.record_share(offer_id=offer.id, actor_key=f"user:{user.pk}"):
        return offer.shares_count
    Offer.objects.filter(pk=offer.pk).update(shares_count=F('shares_count') + 1)
    offer.refresh_from_db(fields=['shares_count'])
    refresh_visibility_score(offer)
    return offer.shares_count


def add_favorite(user, offer: Offer) -> tuple:
    """Ajoute l'offre aux favoris ; renvoie (favori, créé). `likes_count` suit le nombre de favoris."""
    existing = Favorite.objects.filter(user=user, offer=offer).first()
    if existing is not None:
        return existing, False
    ensure_available(offer)
    favorite, created = Favorite.objects.get_or_create(user=user, offer=offer)
    if created:
        Offer.objects.filter(pk=offer.pk).update(likes_count=F('likes_count') + 1)
        _refresh_after_like_change(offer)
    return favorite, created


def remove_favorite(favorite: Favorite) -> None:
    offer = favorite.offer
    favorite.delete()
    Offer.objects.filter(pk=offer.pk, likes_count__gt=0).update(likes_count=F('likes_count') - 1)
    _refresh_after_like_change(offer)


def _refresh_after_like_change(offer: Offer) -> None:
    offer.refresh_from_db(fields=['likes_count'])
    refresh_visibility_score(offer)


def toggle_favorite(user, offer: Offer) -> bool:
    """Ajoute ou retire l'offre des favoris ; renvoie True si elle est désormais favorite."""
    favorite, created = add_favorite(user, offer)
    if not created:
        remove_favorite(favorite)
    return created


# --- Contacts et échanges (CDC 3.5) ---------------------------------------------

def _start_conversation(offer: Offer, sender, message: str):
    conversation = messaging_services.get_or_create_offer_conversation(
        offer_id=offer.id, user_ids=[sender.pk, offer.seller_id],
    )
    messaging_services.send_message(conversation=conversation, sender=sender, content=message, notify=False)
    return conversation


def ensure_available(offer: Offer) -> None:
    """Une offre masquée, en pause, vendue, expirée ou supprimée n'accepte ni contact, ni
    échange, ni favori, ni affaire."""
    if not offer.is_active or offer.is_deleted:
        raise MarketplaceError("Cette annonce n'est plus disponible.")


def _check_can_contact(offer: Offer, sender) -> None:
    if offer.seller_id == sender.pk:
        raise MarketplaceError("Vous ne pouvez pas contacter votre propre annonce.")
    ensure_available(offer)


def create_contact_event(*, offer: Offer, sender, message: str) -> ContactEvent:
    """Enregistre un contact, ouvre (ou alimente) la conversation avec le vendeur et le
    prévient. Les trois écritures sont indépendantes (pas de transaction entre domaines) :
    elles deviendront des événements de l'outbox (L0-16)."""
    _check_can_contact(offer, sender)
    recent = ContactEvent.objects.filter(
        offer=offer, sender=sender, created_at__gte=timezone.now() - DUPLICATE_CONTACT_WINDOW,
    )
    if recent.exists():
        raise MarketplaceError("Vous avez déjà contacté le vendeur pour cette annonce ces dernières 24 heures.")
    event = ContactEvent.objects.create(offer=offer, sender=sender, message=message)
    _start_conversation(offer, sender, message)
    notification_services.notify(
        user_id=offer.seller_id,
        notification_type=notification_services.CONTACT,
        title="Nouvelle demande de contact",
        content=f"{sender.full_name} vous a contacté pour {offer.title}",
        link='/messages',
    )
    return event


def create_exchange_proposal(*, offer: Offer, sender, message: str) -> ExchangeProposal:
    _check_can_contact(offer, sender)
    proposal = ExchangeProposal.objects.create(offer=offer, sender=sender, message=message)
    _start_conversation(offer, sender, f"[PROPOSITION D'ÉCHANGE] {message}")
    notification_services.notify(
        user_id=offer.seller_id,
        notification_type=notification_services.EXCHANGE,
        title="Nouvelle proposition d'échange",
        content=f"{sender.full_name} propose un échange pour {offer.title}",
        link='/messages',
    )
    return proposal
