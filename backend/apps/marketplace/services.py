"""Interface publique du domaine `marketplace`.

Les autres domaines (reviews, messaging, moderation, payments...) ne lisent jamais les
modèles de `marketplace` : ils passent par ces fonctions, qui renvoient des structures
immuables et proposent des variantes par lot (`*_by_ids`). La logique métier du cycle de
vie d'une offre (publication, pause, vente, renouvellement, corbeille, score) est ici.
"""
import math
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from django.contrib.auth import get_user_model
from django.db import OperationalError, transaction
from django.db.models import Case, Count, ExpressionWrapper, F, FloatField, Value, When
from django.utils import timezone

from apps.catalog import services as catalog_services
from apps.common.contexts import CONTEXT_USER
from apps.common.utils import day_bounds, parse_uuid
from apps.identity import services as identity_services
from apps.moderation import services as moderation_services
from apps.moderation.services import record_audit
from apps.platform_core.services import publish_event
from apps.visibility import services as visibility_services

from .models import ContactEvent, ExchangeProposal, Favorite, MarketplaceSettings, Offer


class MarketplaceError(Exception):
    """Refus métier (message en français destiné à l'utilisateur). `code` renseigné : refus codé
    (`{detail, code}` au statut `status_code`) plutôt qu'une erreur de champ."""

    def __init__(self, message, code=None, status_code=400, wait=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.wait = wait  # secondes avant de pouvoir réessayer (en-tête Retry-After des 429)


class OfferHiddenError(MarketplaceError):
    """L'offre est masquée par la modération : le vendeur ne peut pas la remettre en ligne."""



@dataclass(frozen=True)
class OfferInfo:
    id: uuid.UUID
    seller_id: uuid.UUID
    title: str
    main_image_url: Optional[str]
    is_active: bool
    is_deleted: bool
    is_hidden_by_moderation: bool = False

    @property
    def seller_context_type(self) -> str:
        # Couture L0-09 : le contexte vendeur deviendra l'organisation sans changer les appelants.
        return CONTEXT_USER

    @property
    def seller_context_id(self) -> uuid.UUID:
        return self.seller_id

    @property
    def is_available(self) -> bool:
        """Visible sur la marketplace : active (ni masquée, ni en pause, vendue ou expirée) et hors corbeille."""
        return self.is_active and not self.is_deleted


def _info(offer: Offer) -> OfferInfo:
    return OfferInfo(
        id=offer.id, seller_id=offer.seller_id, title=offer.title,
        main_image_url=offer.main_image.url if offer.main_image else None,
        is_active=offer.is_active, is_deleted=offer.is_deleted,
        is_hidden_by_moderation=offer.is_hidden_by_moderation,
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


@dataclass(frozen=True)
class ReviewContact:
    """Preuve de contact qui ouvre le droit d'avis (CDC 3.4) : le plus ancien contact de l'auteur
    sur l'offre, tous canaux confondus (message, appel, WhatsApp)."""

    contact_event_id: uuid.UUID
    channel: str
    recorded_at: object


def get_review_contact(offer_id, user_id) -> Optional[ReviewContact]:
    """Plus ancien contact de `user_id` sur l'offre, ou None s'il n'a jamais contacté le vendeur.
    Valent preuve les contacts comptés (`is_counted`) ET remis (`delivered_at` non nul : numéro
    révélé, ou message déposé chez le vendeur ; ADR 0005, C10). La réponse du vendeur n'est pas exigée."""
    row = (
        ContactEvent.objects.filter(
            offer_id=offer_id, sender_id=user_id, is_counted=True, delivered_at__isnull=False,
        )
        .order_by('created_at', 'id').values_list('id', 'channel', 'created_at').first()
    )
    return None if row is None else ReviewContact(contact_event_id=row[0], channel=row[1], recorded_at=row[2])


def hide_by_moderation(offer_id) -> None:
    """Masque une offre (sanction « masquage d'annonce ») : état explicite + retrait de la marketplace."""
    Offer.objects.filter(pk=offer_id).update(is_hidden_by_moderation=True, is_active=False)


def lift_moderation_hiding(offer_id) -> None:
    """Lève le masquage. N'active l'offre que si elle est encore en statut ACTIVE : une offre
    vendue, expirée ou mise en pause reste hors ligne."""
    Offer.objects.filter(pk=offer_id).update(is_hidden_by_moderation=False)
    Offer.objects.filter(pk=offer_id, status=Offer.STATUS_ACTIVE, is_deleted=False).update(is_active=True)


def count_contacts_by_offer(day: date) -> list:
    """(offer_id, seller_id, total) des contacts comptés un jour donné (agrégat du tableau de bord).
    Même définition du « contact » que l'engagement E du classement : `is_counted` (ADR 0004)."""
    start, end = day_bounds(day)
    rows = (
        ContactEvent.objects.filter(created_at__gte=start, created_at__lt=end, is_counted=True)
        .values('offer_id', 'offer__seller_id')
        .annotate(total=Count('id'))
    )
    return [(row['offer_id'], row['offer__seller_id'], row['total']) for row in rows]


# --- Score de visibilité -----------------------------------------------------

def _score_of(offer: Offer, settings_row, now=None) -> float:
    return visibility_services.compute_score(
        views=offer.views_count, favorites=offer.likes_count, contacts=offer.contacts_count,
        shares=offer.shares_count, created_at=offer.created_at, settings_row=settings_row, now=now,
    )


def refresh_visibility_score(offer: Offer, settings_row=None) -> None:
    """Recalcule et enregistre le score de visibilité d'une offre (E x R, CDC 3.5), depuis les
    compteurs : jamais d'incrément, donc rejouable. Aucune note ni avis n'entre dans le score
    (règle 4) et la promotion est séparée (règle 5)."""
    now = timezone.now()
    offer.visibility_score = _score_of(offer, settings_row, now)
    offer.last_score_update = now
    Offer.objects.filter(pk=offer.pk).update(visibility_score=offer.visibility_score, last_score_update=now)


def recount_contacts(offer_id) -> int:
    """Recompte `contacts_count` à la source (nombre de contacts comptés) ; renvoie le total."""
    total = ContactEvent.objects.filter(offer_id=offer_id, is_counted=True).count()
    Offer.objects.filter(pk=offer_id).update(contacts_count=total)
    return total


REFRESH_BATCH_SIZE = 500


def refresh_all_scores() -> int:
    """Recalcule le score de toutes les offres actives (réglages modifiés, cron horaire de récence,
    action d'administration). Idempotent : les compteurs sources sont recomptés (favoris, contacts)
    ou relus (vues, partages) avant le calcul ; renvoie le nombre d'offres mises à jour.

    Traitement par lots de `REFRESH_BATCH_SIZE` identifiants (pas de `IN (...)` géant, portable
    MySQL), chaque lot dans sa transaction. Ce recomptage horaire corrige aussi toute dérive des
    compteurs incrémentaux (`likes_count`, `contacts_count`) : l'auto-correction est au plus d'une heure."""
    ids = list(Offer.objects.filter(is_active=True, is_deleted=False).order_by('id').values_list('id', flat=True))
    settings_row = visibility_services.get_ranking_settings()
    now = timezone.now()
    for start in range(0, len(ids), REFRESH_BATCH_SIZE):
        batch = ids[start:start + REFRESH_BATCH_SIZE]
        with transaction.atomic():
            offers = list(Offer.objects.filter(id__in=batch, is_active=True, is_deleted=False))
            batch_ids = [o.id for o in offers]
            favorites = dict(
                Favorite.objects.filter(offer_id__in=batch_ids).values('offer_id')
                .annotate(n=Count('id')).values_list('offer_id', 'n')
            )
            contacts = dict(
                ContactEvent.objects.filter(offer_id__in=batch_ids, is_counted=True)
                .values('offer_id').annotate(n=Count('id')).values_list('offer_id', 'n')
            )
            for offer in offers:
                offer.likes_count = favorites.get(offer.id, 0)
                offer.contacts_count = contacts.get(offer.id, 0)
                offer.visibility_score = _score_of(offer, settings_row, now)
                offer.last_score_update = now
            Offer.objects.bulk_update(
                offers, ['likes_count', 'contacts_count', 'visibility_score', 'last_score_update'], batch_size=200,
            )
    return len(ids)


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
    puis les compteurs de visibilité. Les avis et conversations liés sont conservés
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
    """Expire les offres actives échues et publie `marketplace.offer_expiring_soon` pour les
    échéances proches (CDC 3.2, 3.6) ; la notification est créée à la diffusion de l'événement.
    Renvoie (nombre d'offres expirées, nombre d'échéances signalées)."""
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
        with transaction.atomic():
            # Marque conditionnelle : deux exécutions simultanées ne signalent pas deux fois la même offre.
            marked = Offer.objects.filter(pk=offer.pk, expiring_soon_notified=False).update(
                expiring_soon_notified=True,
            )
            if not marked:
                continue
            publish_event(
                'marketplace.offer_expiring_soon', aggregate_type='offer', aggregate_id=offer.id,
                payload={
                    'offer_id': str(offer.id), 'offer_title': offer.title, 'seller_id': str(offer.seller_id),
                    'expires_at': offer.expires_at.isoformat(),
                },
            )
        notified += 1
    return expired_count, notified


# --- Engagement ---------------------------------------------------------------

def sync_offer_engagement(offer_id) -> bool:
    """Recalcule `views_count` et `shares_count` d'une offre à partir des compteurs journaliers
    de `visibility` (source de vérité), puis son score. Idempotent : rejouable sans risque
    (abonné aux événements de vue et de partage). Renvoie False si l'offre n'existe plus."""
    offer = Offer.objects.filter(pk=offer_id).first()
    if offer is None:
        return False
    offer.views_count = visibility_services.total_views(offer_id)
    offer.shares_count = visibility_services.total_shares(offer_id)
    Offer.objects.filter(pk=offer_id).update(views_count=offer.views_count, shares_count=offer.shares_count)
    refresh_visibility_score(offer)
    return True


def register_view(offer: Offer, viewer_key: str) -> bool:
    """CDC 3.8 : une vue unique par jour et par visiteur. `visibility` compte la vue et publie
    l'événement ; le total et le score de l'offre suivent à la diffusion (immédiate après la
    validation, sinon reprise par le cron). Renvoie True si la vue est nouvelle ; l'instance
    reçoit alors les compteurs lus en base, « au mieux »."""
    if not visibility_services.record_view(offer_id=offer.id, seller_id=offer.seller_id, viewer_key=viewer_key):
        return False
    offer.refresh_from_db(fields=['views_count'])
    return True


def register_share(offer: Offer, user) -> int:
    """CDC 3.4 : partage externe, compteur qui alimente l'engagement. Un utilisateur ne compte
    qu'une fois par offre et par jour. Renvoie `shares_count` « au mieux » : valeur lue après la
    diffusion immédiate de l'événement ; si elle n'a pas encore eu lieu, le total précédent
    (la source de vérité reste le compteur de `visibility`, recalculé ensuite)."""
    visibility_services.record_share(offer_id=offer.id, seller_id=offer.seller_id, actor_key=f"user:{user.pk}")
    offer.refresh_from_db(fields=['shares_count'])
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
    offer.refresh_from_db(fields=['views_count', 'likes_count', 'shares_count', 'contacts_count'])
    refresh_visibility_score(offer)


def toggle_favorite(user, offer: Offer) -> bool:
    """Ajoute ou retire l'offre des favoris ; renvoie True si elle est désormais favorite."""
    favorite, created = add_favorite(user, offer)
    if not created:
        remove_favorite(favorite)
    return created


# --- Contacts et échanges (CDC 3.5) ---------------------------------------------

def ensure_available(offer: Offer) -> None:
    """Une offre masquée, en pause, vendue, expirée ou supprimée n'accepte ni contact, ni
    échange, ni favori."""
    if not offer.is_active or offer.is_deleted or not offer.seller.is_active:
        raise MarketplaceError("Cette annonce n'est plus disponible.")


def _check_can_contact(offer: Offer, sender) -> None:
    if offer.seller_id == sender.pk:
        raise MarketplaceError("Vous ne pouvez pas contacter votre propre annonce.")
    ensure_available(offer)


EXCHANGE_MESSAGE_PREFIX = "[PROPOSITION D'ÉCHANGE] "


def get_contact_message(contact_event_id) -> Optional[str]:
    """Texte à poser dans la conversation pour un contact, ou None si le contact n'existe plus
    (annonce supprimée entre-temps). Lu à la diffusion : le message ne transite pas par l'outbox."""
    return ContactEvent.objects.filter(pk=contact_event_id).values_list('message', flat=True).first()


def mark_contact_delivered(contact_event_id) -> None:
    """Pose `delivered_at` d'un contact par message une fois remis au vendeur. Idempotent : une
    seconde diffusion ne modifie pas l'horodatage ; un contact disparu est ignoré."""
    ContactEvent.objects.filter(pk=contact_event_id, delivered_at__isnull=True).update(delivered_at=timezone.now())


def get_exchange_message(proposal_id) -> Optional[str]:
    """Idem pour une proposition d'échange (préfixée)."""
    text = ExchangeProposal.objects.filter(pk=proposal_id).values_list('message', flat=True).first()
    return None if text is None else f"{EXCHANGE_MESSAGE_PREFIX}{text}"


def _interaction_payload(offer: Offer, sender, **ids) -> dict:
    """Charge utile d'un contact ou d'un échange : identifiants et titre public de l'annonce
    seulement. Ni le texte du message ni le nom de l'expéditeur (données personnelles) ne
    sont copiés dans l'outbox : les abonnés les relisent par `services.py`."""
    return {
        **{key: str(value) for key, value in ids.items()},
        'offer_id': str(offer.id), 'offer_title': offer.title,
        'seller_id': str(offer.seller_id), 'sender_id': str(sender.pk),
    }


def is_countable_contact(offer: Offer, sender, window_hours: int) -> bool:
    """Un contact entre dans l'engagement une seule fois par expéditeur et par offre dans la
    fenêtre réglée (même fenêtre que l'anti-doublon), tous canaux confondus."""
    return not ContactEvent.objects.filter(
        offer=offer, sender=sender, is_counted=True,
        created_at__gte=timezone.now() - timedelta(hours=window_hours),
    ).exists()


def create_contact_event(*, offer: Offer, sender, message: str, channel: str = ContactEvent.CHANNEL_MESSAGE) -> ContactEvent:
    """Enregistre un contact et publie `marketplace.contact_recorded` dans la même transaction :
    la conversation et la notification du vendeur sont créées par leurs domaines à la diffusion
    de l'événement (outbox), avec reprise en cas d'échec.

    Limite connue : le contrôle de doublon puis le marquage `is_counted` ne sont pas atomiques
    entre deux requêtes simultanées du même expéditeur (SQLite sérialise les écritures ; sous
    MySQL, deux contacts pourraient être comptés). L'effet est borné : `contacts_count` est
    recompté à la source et corrigé à chaque rafraîchissement horaire (`refresh_all_scores`)."""
    _check_can_contact(offer, sender)
    if channel == ContactEvent.CHANNEL_MESSAGE and ContactEvent.CHANNEL_MESSAGE not in (
        identity_services.get_allowed_channels([offer.seller_id]).get(offer.seller_id, [])
    ):
        raise MarketplaceError("Ce vendeur n'accepte pas ce moyen de contact.", 'channel_not_allowed', 403)
    window_hours = MarketplaceSettings.get_solo().duplicate_contact_window_hours
    # Le doublon se juge par canal : obtenir un numéro n'empêche pas d'écrire au vendeur, et
    # inversement (l'engagement, lui, ne compte qu'un contact par fenêtre : `is_countable_contact`).
    recent = ContactEvent.objects.filter(
        offer=offer, sender=sender, channel=channel, created_at__gte=timezone.now() - timedelta(hours=window_hours),
    )
    if recent.exists():
        raise MarketplaceError(
            f"Vous avez déjà contacté le vendeur pour cette annonce ces dernières {window_hours} heures.",
            'contact_duplicate', 400,
        )
    with transaction.atomic():
        # Engagement : un contact compte une fois par expéditeur et par offre dans la fenêtre,
        # tous canaux confondus ; `contacts_count` est recompté à la source, puis le score,
        # dans la même transaction.
        event = ContactEvent.objects.create(
            offer=offer, sender=sender, message=message, channel=channel,
            is_counted=is_countable_contact(offer, sender, window_hours),
        )
        recount_contacts(offer.id)
        offer.refresh_from_db(fields=['views_count', 'likes_count', 'shares_count', 'contacts_count'])
        refresh_visibility_score(offer)
        publish_event(
            'marketplace.contact_recorded', aggregate_type='offer', aggregate_id=offer.id,
            payload={**_interaction_payload(offer, sender, contact_event_id=event.pk), 'channel': event.channel},
        )
    return event


# --- Révélation du numéro de contact (ADR 0005) ---------------------------------------

REVEAL_CHANNELS = (ContactEvent.CHANNEL_CALL, ContactEvent.CHANNEL_WHATSAPP)
REVEAL_QUOTA_WINDOW = timedelta(hours=24)  # fenêtre glissante des plafonds « par jour » (ADR 0005, C9)
REVEAL_FALLBACK = "Vous pouvez écrire au vendeur par message en attendant."
_QUOTA_MESSAGES = {
    'reveal_quota_account': "Vous avez atteint le nombre maximal de numéros obtenus sur 24 heures. ",
    'reveal_quota_new_account': "Votre compte est récent : le nombre de numéros obtenus sur 24 heures est limité. ",
}


class RevealError(MarketplaceError):
    """Refus d'une révélation de numéro : message français, code machine, statut HTTP."""

    def __init__(self, message, code, status_code=403, wait=None):
        super().__init__(message, code, status_code, wait)


class _QuotaExceeded(Exception):
    def __init__(self, code, wait):
        super().__init__(code)
        self.code = code
        self.wait = wait


@dataclass(frozen=True)
class RevealResult:
    """Numéro remis au visiteur. `phone` n'est jamais journalisé ni publié (règle 10)."""

    contact_event_id: uuid.UUID
    channel: str
    created: bool
    offer_title: str
    phone: str = field(repr=False)


def _revealable_offer(offer_id) -> Offer:
    """Offre visible, ou refus uniforme 404 : inconnue, mal formée, en corbeille, masquée ou
    expirée ne se distinguent pas (anti-énumération)."""
    parsed = parse_uuid(offer_id)
    offer = None
    if parsed is not None:
        offer = Offer.objects.select_related('seller').filter(
            pk=parsed, is_active=True, is_deleted=False, seller__is_active=True,
        ).first()
    if offer is None:
        raise RevealError("Cette annonce n'est pas disponible.", 'offer_not_found', 404)
    return offer


def _is_new_account(user, new_account_hours, now) -> bool:
    """Compte neuf : inscrit depuis moins de `new_account_hours` OU numéro non vérifié (il n'existe
    pas de vérification d'e-mail : décision du chef de projet)."""
    return (not user.phone_verified) or user.date_joined > now - timedelta(hours=new_account_hours)


def _quota_of(sender, row, now) -> tuple:
    if _is_new_account(sender, row.new_account_hours, now):
        return row.reveal_daily_limit_new_account, 'reveal_quota_new_account'
    return row.reveal_daily_limit_account, 'reveal_quota_account'


def _reveal_times(sender, now, exclude_id=None) -> list:
    """Dates des numéros obtenus par ce compte sur la fenêtre glissante, de la plus ancienne à la
    plus récente (`exclude_id` : un contact en cours de validation, à ne pas compter)."""
    queryset = ContactEvent.objects.filter(
        sender=sender, channel__in=REVEAL_CHANNELS, created_at__gt=now - REVEAL_QUOTA_WINDOW,
    )
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    return list(queryset.order_by('created_at').values_list('created_at', flat=True))


def _quota_wait(times, limit, now) -> int:
    """Secondes avant que assez de révélations sortent de la fenêtre pour repasser sous le plafond."""
    index = max(0, len(times) - limit)
    return max(1, math.ceil((times[index] + REVEAL_QUOTA_WINDOW - now).total_seconds()))


def _enforce_reveal_quota(sender, row, now) -> None:
    limit, code = _quota_of(sender, row, now)
    times = _reveal_times(sender, now)
    if len(times) >= limit:
        raise _QuotaExceeded(code, _quota_wait(times, limit, now))


def _refuse_quota(sender, offer, row, exceeded, now):
    """Trace le dépassement (une seule entrée par refus, hors transaction métier : la trace survit
    au refus), signale à la modération un abus répété, puis lève le refus 429 avec `Retry-After`.
    Le seuil compte des JOURS distincts avec dépassement : un double-clic ou une rafale le même
    jour ne fait pas un abus."""
    record_audit(
        sender, 'contact.reveal_quota_exceeded', target=sender, details=f"{exceeded.code} ; annonce {offer.id}",
    )
    since = now - timedelta(days=row.reveal_abuse_window_days)
    if moderation_services.count_audit_days(
        sender.pk, 'contact.reveal_quota_exceeded', since,
    ) >= row.reveal_abuse_threshold:
        moderation_services.file_automatic_report(
            'user', sender.pk, moderation_services.REASON_SPAM,
            "Plafond de révélation de numéros dépassé à répétition (collecte possible de numéros).",
            only_open=True,
        )
    raise RevealError(_QUOTA_MESSAGES[exceeded.code] + REVEAL_FALLBACK, exceeded.code, 429, wait=exceeded.wait)


def _lock_visitor(user) -> None:
    """Sérialise les révélations d'un même visiteur : verrou de ligne sur son compte (`SELECT ...
    FOR UPDATE` sous MySQL ; sans effet sous SQLite, qui sérialise déjà les écritures). Doit
    précéder la relecture du doublon et du plafond. Ne lit aucun champ du compte."""
    get_user_model().objects.select_for_update().filter(pk=user.pk).values_list('pk', flat=True).first()


def _find_recent_reveal(offer, sender, channel, window_hours, now):
    return ContactEvent.objects.filter(
        offer=offer, sender=sender, channel=channel, created_at__gte=now - timedelta(hours=window_hours),
    ).order_by('-created_at').first()


def reveal_contact(*, offer_id, sender, channel: str) -> RevealResult:
    """Remet au visiteur le numéro de contact du vendeur pour un canal consenti (ADR 0005).

    Ordre des contrôles : canal, offre (404 uniforme), propre annonce, sanction, plafonds,
    consentement. Le plafond précède le consentement pour qu'un refus ne révèle pas quel vendeur
    a consenti. Une demande répétée dans la fenêtre anti-doublon renvoie le même contact sans
    nouveau contact ni plafond consommé (mais avec une entrée d'audit : le numéro sort).

    Le numéro n'est lu chez `identity` qu'avant la transaction et n'est renvoyé qu'après son
    commit (contact + événement + audit). Il n'entre ni dans l'événement, ni dans l'audit."""
    if channel not in REVEAL_CHANNELS:
        raise RevealError("Moyen de contact invalide.", 'channel_invalid', 400)
    offer = _revealable_offer(offer_id)
    if offer.seller_id == sender.pk:
        raise RevealError("Vous ne pouvez pas contacter votre propre annonce.", 'own_offer', 403)
    if moderation_services.is_user_restricted(sender.pk):
        raise RevealError("Votre compte ne peut pas contacter de vendeur pour le moment.", 'contact_restricted', 403)

    row = MarketplaceSettings.get_solo()
    window_hours = row.duplicate_contact_window_hours
    now = timezone.now()
    try:
        if _find_recent_reveal(offer, sender, channel, window_hours, now) is None:
            _enforce_reveal_quota(sender, row, now)
    except _QuotaExceeded as exceeded:
        _refuse_quota(sender, offer, row, exceeded, now)

    try:
        endpoint = identity_services.get_contact_endpoint(offer.seller_id, channel)
    except identity_services.ChannelNotConsented:
        # Une trace par visiteur, offre et jour : un visiteur qui insiste ne remplit pas le journal.
        if not moderation_services.has_audit_since(
            sender.pk, 'contact.reveal_refused', offer.id, day_bounds(timezone.localdate())[0],
        ):
            record_audit(
                sender, 'contact.reveal_refused', target=offer, details=f"Moyen {channel} refusé : channel_not_allowed",
            )
        raise RevealError("Ce vendeur n'accepte pas ce moyen de contact.", 'channel_not_allowed', 403)

    try:
        with transaction.atomic():
            # Verrou par visiteur PUIS relecture du doublon : deux demandes simultanées du même
            # compte ne créent qu'un contact et ne dépassent pas le plafond.
            _lock_visitor(sender)
            event = _find_recent_reveal(offer, sender, channel, window_hours, now)
            created = event is None
            if created:
                event = ContactEvent.objects.create(
                    offer=offer, sender=sender, channel=channel,
                    is_counted=is_countable_contact(offer, sender, window_hours),
                )
                ContactEvent.objects.filter(pk=event.pk).update(delivered_at=event.created_at)
                # Filet si le verrou ne sérialise pas (autre moteur) : un doublon apparu entre-temps
                # est annulé (on garde le plus ancien), puis recomptage du plafond APRÈS insertion.
                earlier = ContactEvent.objects.filter(
                    offer=offer, sender=sender, channel=channel,
                    created_at__gte=now - timedelta(hours=window_hours),
                ).exclude(pk=event.pk).order_by('created_at').first()
                if earlier is not None:
                    event.delete()
                    event, created = earlier, False
                else:
                    limit, code = _quota_of(sender, row, now)
                    later = timezone.now()
                    # Hors le contact à valider : un `Retry-After` juste, sans surestimation.
                    times = _reveal_times(sender, later, exclude_id=event.pk)
                    if len(times) >= limit:
                        raise _QuotaExceeded(code, _quota_wait(times, limit, later))
                    recount_contacts(offer.id)
                    offer.refresh_from_db(fields=['views_count', 'likes_count', 'shares_count', 'contacts_count'])
                    refresh_visibility_score(offer)
                    publish_event(
                        'marketplace.contact_revealed', aggregate_type='offer', aggregate_id=offer.id,
                        payload={**_interaction_payload(offer, sender, contact_event_id=event.pk), 'channel': channel},
                    )
            record_audit(
                sender, 'contact.number_revealed', target=offer,
                details=f"Moyen {channel} ; vendeur {offer.seller_id} ; {'nouveau' if created else 'renvoi'}",
            )
    except _QuotaExceeded as exceeded:
        _refuse_quota(sender, offer, row, exceeded, now)
    except OperationalError as exc:
        # SQLite : écriture concurrente du même compte (double-clic) -> « database is locked ».
        if 'locked' not in str(exc).lower():
            raise
        event = _find_recent_reveal(offer, sender, channel, window_hours, timezone.now())
        if event is None:
            raise RevealError(
                "Une demande est déjà en cours. Réessayez dans un instant.", 'reveal_in_progress', 409, wait=1,
            )
        created = False
        record_audit(
            sender, 'contact.number_revealed', target=offer,
            details=f"Moyen {channel} ; vendeur {offer.seller_id} ; renvoi",
        )
    return RevealResult(
        contact_event_id=event.pk, channel=channel, created=created, offer_title=offer.title,
        phone=endpoint.phone_e164,
    )


@dataclass(frozen=True)
class ReceivedReveal:
    """Ligne de la liste « qui a demandé mon numéro » : ni numéro, ni identifiant du visiteur."""

    id: uuid.UUID
    channel: str
    created_at: object
    requester_display_name: str
    offer_id: uuid.UUID
    offer_title: str


def list_reveals_for_seller(seller, channel=None):
    """Révélations de numéro sur les offres du vendeur, les plus récentes d'abord (queryset paginable) ;
    `to_received_reveals` convertit une page."""
    queryset = ContactEvent.objects.filter(offer__seller=seller, channel__in=REVEAL_CHANNELS)
    if channel:
        queryset = queryset.filter(channel=channel)
    return queryset.select_related('offer').order_by('-created_at', '-id')


def to_received_reveals(events) -> list:
    """Convertit une page de contacts : noms résolus en une requête (« Marie K. »)."""
    names = identity_services.get_full_names([event.sender_id for event in events])
    return [
        ReceivedReveal(
            id=event.id, channel=event.channel, created_at=event.created_at,
            requester_display_name=identity_services.public_display_name(names.get(event.sender_id)),
            offer_id=event.offer_id, offer_title=event.offer.title,
        )
        for event in events
    ]


def create_exchange_proposal(*, offer: Offer, sender, message: str) -> ExchangeProposal:
    _check_can_contact(offer, sender)
    with transaction.atomic():
        proposal = ExchangeProposal.objects.create(offer=offer, sender=sender, message=message)
        publish_event(
            'marketplace.exchange_proposed', aggregate_type='offer', aggregate_id=offer.id,
            payload=_interaction_payload(offer, sender, proposal_id=proposal.pk),
        )
    return proposal


def get_report_labels(ids: Iterable) -> dict:
    """Libellés d'offres signalables, indexés par UUID (une requête) : sert à la modération.
    Une offre absente n'apparaît pas dans le résultat."""
    return {offer_id: f"[{offer_type}] {title}" for offer_id, offer_type, title in
            Offer.objects.filter(id__in=_parsed(ids)).values_list('id', 'offer_type', 'title')}


def _parsed(ids: Iterable) -> set:
    return {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}


def get_report_authors(ids: Iterable) -> dict:
    """Vendeur de chaque offre, `{offre: vendeur}` (une requête) : refuse l'auto-signalement."""
    return dict(Offer.objects.filter(id__in=_parsed(ids)).values_list('id', 'seller_id'))


def seller_owns_offer(offer_id, user_id) -> bool:
    """Vrai si l'offre existe et appartient à cet utilisateur (rattachement d'une sanction)."""
    parsed = parse_uuid(offer_id)
    return parsed is not None and Offer.objects.filter(id=parsed, seller_id=user_id).exists()


# --- Proximité D à la lecture (CDC 3.5, ADR 0004 6.2) -------------------------

def proximity_expression(near_commune_id):
    """Coefficient D en expression SQL (Case/When) : même commune, même ville, défaut. Lu en base
    (RankingSettings). Renvoie None quand aucune commune de référence n'est connue : pas de
    proximité, l'ordre reste celui du score stocké. Le coefficient n'est jamais exposé."""
    commune = parse_uuid(near_commune_id)
    if commune is None:
        return None
    same_commune, same_city, default = visibility_services.get_proximity_weights()
    info = catalog_services.get_communes_by_ids([commune]).get(commune)
    whens = [When(commune_id=commune, then=Value(float(same_commune)))]
    if info is not None:
        city_communes = catalog_services.get_commune_ids_for_city(info.city_id)
        if city_communes:
            whens.append(When(commune_id__in=city_communes, then=Value(float(same_city))))
    return Case(*whens, default=Value(float(default)), output_field=FloatField())


def order_by_relevance(queryset, near_commune_id=None, descending=True):
    """Tri par pertinence : score stocké (E x R) multiplié par D à la lecture, entièrement en SQL
    (pagination exacte). Départage stable : date de création puis identifiant."""
    proximity = proximity_expression(near_commune_id)
    if proximity is None:
        score = F('visibility_score')
    else:
        score = ExpressionWrapper(F('visibility_score') * proximity, output_field=FloatField())
    if descending:
        return queryset.order_by(score.desc(), '-created_at', 'id')
    return queryset.order_by(score.asc(), 'created_at', 'id')
