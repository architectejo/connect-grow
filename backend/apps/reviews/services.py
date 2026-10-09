"""Interface publique du domaine `reviews` et logique métier des avis après contact (CDC 3.4, ADR 0004).

Dépendances sortantes, toutes par `services.py` : marketplace (offres, preuve de contact),
identity (contexte vendeur), moderation (journal d'audit). Les notifications et le signalement
automatique passent par des événements de domaine (outbox, ADR 0003). Aucune n'importe un modèle
d'un autre domaine.

Aucune note agrégée n'est stockée : les moyennes sont calculées à la lecture (règle 4).
"""
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.common.contexts import CONTEXT_USER
from apps.common.utils import parse_uuid
from apps.identity import services as identity_services
from apps.marketplace import services as marketplace_services
from apps.moderation import services as moderation_services
from apps.platform_core.services import publish_event

from .models import Review, ReviewDailyCount, ReviewSettings

# Statuts HTTP portés par les refus métier (la couche vue les traduit sans les connaître).
HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_CONFLICT, HTTP_TOO_MANY = 403, 404, 409, 429


class ReviewError(Exception):
    """Refus métier : message en français, code machine stable et statut HTTP suggéré."""

    def __init__(self, message, code, status_code=HTTP_FORBIDDEN):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def get_settings() -> ReviewSettings:
    return ReviewSettings.get_solo()


# --- Moyennes affichées (calculées à la lecture) ---------------------------------------

@dataclass(frozen=True)
class RatingSummary:
    """Moyenne (1 décimale, demi supérieur) et nombre d'avis. `average` est None sous le seuil
    d'affichage ; `count` est toujours exact (avis masqués exclus)."""

    average: Optional[float]
    count: int


def _rounded_average(total, count) -> Optional[float]:
    if not count:
        return None
    return float((Decimal(total) / Decimal(count)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def _summaries(rows, keys, minimum) -> dict:
    """`rows` : valeurs (clé, total, nombre) ; renvoie `{clé: RatingSummary}` pour toutes les clés."""
    found = {key: (total or 0, count) for key, total, count in rows}
    result = {}
    for key in keys:
        total, count = found.get(key, (0, 0))
        result[key] = RatingSummary(_rounded_average(total, count) if count >= minimum else None, count)
    return result


def get_offer_ratings(offer_ids: Iterable) -> dict:
    """Note d'offre de chaque offre, `{offer_id: RatingSummary}` (une requête). Les avis masqués
    sont exclus ; la moyenne est None sous `ReviewSettings.min_reviews_to_display`."""
    wanted = {parsed for parsed in (parse_uuid(i) for i in offer_ids) if parsed is not None}
    if not wanted:
        return {}
    rows = (
        Review.objects.filter(offer_id__in=wanted, is_hidden=False).order_by().values('offer_id')
        .annotate(total=Sum('offer_rating'), n=Count('id')).values_list('offer_id', 'total', 'n')
    )
    return _summaries(rows, wanted, get_settings().min_reviews_to_display)


def get_seller_ratings(context_type: str, context_ids: Iterable) -> dict:
    """Note vendeur de chaque contexte vendeur, `{context_id: RatingSummary}` (une requête). Seule
    la dernière note de chaque auteur compte (`counts_for_seller`) ; avis masqués exclus ; moyenne
    None sous le seuil d'affichage."""
    wanted = {parsed for parsed in (parse_uuid(i) for i in context_ids) if parsed is not None}
    if not wanted:
        return {}
    rows = (
        Review.objects.filter(
            seller_context_type=context_type, seller_context_id__in=wanted, is_hidden=False, counts_for_seller=True,
        ).order_by().values('seller_context_id').annotate(total=Sum('seller_rating'), n=Count('id'))
        .values_list('seller_context_id', 'total', 'n')
    )
    return _summaries(rows, wanted, get_settings().min_reviews_to_display)


@dataclass(frozen=True)
class SellerDashboardRating:
    average: Optional[float]
    review_count: int


def get_seller_dashboard_rating(seller_id) -> SellerDashboardRating:
    """Pour le tableau de bord du vendeur lui-même : moyenne de ses notes vendeur visibles, sans
    seuil d'affichage (None s'il n'a aucun avis), et nombre d'avis visibles reçus."""
    visible = Review.objects.filter(
        seller_context_type=CONTEXT_USER, seller_context_id=seller_id, is_hidden=False,
    )
    counted = visible.filter(counts_for_seller=True).aggregate(total=Sum('seller_rating'), n=Count('id'))
    return SellerDashboardRating(
        average=_rounded_average(counted['total'] or 0, counted['n']), review_count=visible.count(),
    )


# --- Drapeau « dernière note vendeur » -------------------------------------------------

def reconcile_seller_flag(user_id, context_type, context_id) -> None:
    """Une seule note vendeur par auteur et par vendeur (D2) : `counts_for_seller` est vrai pour la
    plus récente non masquée du couple (auteur, contexte vendeur), faux pour les autres. Idempotent ;
    à appeler dans la transaction de toute création, suppression, masquage ou réaffichage d'avis."""
    rows = Review.objects.filter(
        user_id=user_id, seller_context_type=context_type, seller_context_id=context_id,
    )
    latest = rows.filter(is_hidden=False).order_by('-created_at', '-id').values_list('id', flat=True).first()
    rows.exclude(pk=latest).filter(counts_for_seller=True).update(counts_for_seller=False)
    if latest is not None:
        rows.filter(pk=latest, counts_for_seller=False).update(counts_for_seller=True)


# --- Avis croisés ----------------------------------------------------------------------

def check_crossed_reviews(review: Review) -> None:
    """CDC 3.4 (anti-abus) : détecte les avis croisés répétés entre les deux mêmes comptes et les
    envoie en modération plutôt que de les bloquer (un faux positif ne doit pas empêcher un vrai
    avis d'exister). Chaque couple (auteur, offre) compte une fois. Entre comptes personnels
    seulement (organisations : L0-09). À appeler dans la transaction de création."""
    if review.seller_context_type != CONTEXT_USER:
        return
    user_a, user_b = review.user_id, review.seller_context_id
    if user_a == user_b:
        return

    row = get_settings()
    since = timezone.now() - timedelta(days=row.crossed_reviews_window_days)
    pairs = set(
        Review.objects.filter(
            Q(user_id=user_a, seller_context_id=user_b) | Q(user_id=user_b, seller_context_id=user_a),
            seller_context_type=CONTEXT_USER, created_at__gte=since,
        ).values_list('user_id', 'offer_id')
    )
    if len(pairs) >= row.crossed_reviews_threshold:
        publish_event(
            'reviews.crossed_reviews_detected', aggregate_type='review', aggregate_id=review.pk,
            payload={
                'review_id': str(review.pk), 'user_a': str(user_a), 'user_b': str(user_b),
                'reviews_count': len(pairs), 'window_days': row.crossed_reviews_window_days,
            },
        )


# --- Création d'un avis ----------------------------------------------------------------

def ensure_can_review(user, offer_id):
    """Contrôle les conditions d'un nouvel avis et renvoie `(offre, preuve de contact)`.

    Ordre d'évaluation (ADR 0004, 7.2) : offre introuvable, propre offre, aucun contact, avis déjà
    donné, offre indisponible. Point d'extension (L0-10 a) : le délai entre contact et avis se
    contrôle ici, juste après « aucun contact », avec `ReviewSettings.delay_after_contact_hours`."""
    offer = marketplace_services.get_offer(offer_id)
    if offer is None:
        raise ReviewError("Annonce introuvable.", 'offer_not_found', HTTP_NOT_FOUND)
    if identity_services.acts_for_context(user.pk, offer.seller_context_type, offer.seller_context_id):
        raise ReviewError("Vous ne pouvez pas noter votre propre annonce.", 'own_offer')
    contact = marketplace_services.get_review_contact(offer.id, user.pk)
    if contact is None:
        raise ReviewError("Vous pourrez donner votre avis après avoir contacté le vendeur.", 'not_eligible')
    if Review.objects.filter(user=user, offer_id=offer.id).exists():
        raise ReviewError("Vous avez déjà donné votre avis pour cette annonce.", 'already_reviewed', HTTP_CONFLICT)
    if offer.is_deleted or offer.is_hidden_by_moderation:
        raise ReviewError("Cette annonce n'est plus disponible.", 'offer_unavailable', HTTP_CONFLICT)
    return offer, contact


def reserve_daily_slot(user) -> None:
    """Réserve atomiquement une place dans la limite quotidienne (à appeler dans la transaction
    de création). Les avis supprimés ensuite restent comptés."""
    limit = get_settings().daily_review_limit
    today = timezone.localdate()
    ReviewDailyCount.objects.get_or_create(user=user, date=today)
    reserved = ReviewDailyCount.objects.filter(user=user, date=today, count__lt=limit).update(count=F('count') + 1)
    if not reserved:
        raise ReviewError(f"Vous avez atteint la limite de {limit} avis par jour.", 'daily_limit', HTTP_TOO_MANY)


def create_review(user, *, offer_id, offer_rating, seller_rating, content) -> Review:
    """Crée l'avis d'un visiteur ayant contacté le vendeur : une note d'offre, une note vendeur et
    un commentaire (déjà validés par la couche API). Atomique : limite quotidienne, drapeau de la
    dernière note vendeur, événements `review_posted` et, le cas échéant, `crossed_reviews_detected`."""
    offer, contact = ensure_can_review(user, offer_id)
    try:
        with transaction.atomic():
            reserve_daily_slot(user)
            review = Review.objects.create(
                user=user, offer_id=offer.id,
                seller_context_type=offer.seller_context_type, seller_context_id=offer.seller_context_id,
                contact_event_id=contact.contact_event_id, contact_channel=contact.channel,
                contact_recorded_at=contact.recorded_at,
                offer_rating=offer_rating, seller_rating=seller_rating, content=content.strip(),
            )
            reconcile_seller_flag(user.pk, review.seller_context_type, review.seller_context_id)
            publish_review_posted(review, user, offer)
            check_crossed_reviews(review)
    except IntegrityError:
        # Deux requêtes simultanées pour le même couple (auteur, offre) : l'unicité en base tranche.
        raise ReviewError(
            "Vous avez déjà donné votre avis pour cette annonce.", 'already_reviewed', HTTP_CONFLICT,
        )
    review.refresh_from_db()
    return review


def update_review(review: Review, changes: dict) -> Review:
    """Modifie la note d'offre, la note vendeur ou le texte (fenêtre `edit_window_hours`) ; renseigne
    `edited_at`. Modifier un avis qui n'est pas le plus récent du couple ne change pas la moyenne vendeur."""
    ensure_author_can_modify(review)
    if not review.can_still_be_edited(get_settings().edit_window_hours):
        raise ReviewError(
            "Cet avis n'est plus modifiable : le délai de modification est dépassé.", 'edit_window_closed',
        )
    for name in ('offer_rating', 'seller_rating', 'content'):
        if name in changes:
            setattr(review, name, changes[name].strip() if name == 'content' else changes[name])
    review.edited_at = timezone.now()
    review.save(update_fields=['offer_rating', 'seller_rating', 'content', 'edited_at', 'updated_at'])
    return review


def delete_review(review: Review) -> None:
    """Suppression par l'auteur ; la place de la limite quotidienne n'est pas libérée."""
    ensure_author_can_modify(review)
    with transaction.atomic():
        review.delete()
        reconcile_seller_flag(review.user_id, review.seller_context_type, review.seller_context_id)


def ensure_author_can_modify(review: Review) -> None:
    """Un avis masqué ou signalé échappe à son auteur : il ne peut ni le modifier ni le supprimer
    (sinon il effacerait la preuve avant la décision de la modération)."""
    if review.is_hidden:
        raise ReviewError(
            "Cet avis a été masqué par la modération : vous ne pouvez plus le modifier ni le supprimer.",
            'review_locked',
        )
    if moderation_services.has_open_report(review):
        raise ReviewError(
            "Cet avis fait l'objet d'un signalement en cours : vous ne pouvez plus le modifier ni le supprimer.",
            'review_locked',
        )


def set_review_hidden(review: Review, hidden: bool, actor) -> None:
    """Masque ou réaffiche un avis (CDC 3.4) ; journalisé (règle 12). Les notes d'un avis masqué
    sortent des moyennes ; le drapeau « dernière note vendeur » est recalculé dans la même transaction."""
    if review.is_hidden == hidden:
        return
    with transaction.atomic():
        review.is_hidden = hidden
        review.save(update_fields=['is_hidden', 'updated_at'])
        reconcile_seller_flag(review.user_id, review.seller_context_type, review.seller_context_id)
        moderation_services.record_audit(actor, 'REVIEW_HIDDEN' if hidden else 'REVIEW_UNHIDDEN', target=review)
    review.refresh_from_db(fields=['counts_for_seller'])


def publish_review_posted(review: Review, author, offer=None) -> None:
    """Publie `reviews.review_posted` (v2), à appeler dans la transaction de création : le vendeur est
    notifié à la diffusion. Seuls des identifiants et le titre public de l'annonce sont copiés : le
    nom de l'auteur et l'extrait sont relus à la diffusion. `recipient_id` est l'utilisateur à
    notifier (L0-09 résoudra les membres d'une organisation)."""
    if offer is None:
        offer = marketplace_services.get_offer(review.offer_id)
    publish_event(
        'reviews.review_posted', aggregate_type='review', aggregate_id=review.pk,
        payload={
            'review_id': str(review.pk), 'recipient_id': str(review.seller_context_id),
            'author_id': str(author.pk), 'offer_id': str(review.offer_id) if offer else None,
            'offer_title': _offer_title(offer),
            'seller_context_type': review.seller_context_type, 'seller_context_id': str(review.seller_context_id),
        },
    )


def _offer_title(offer):
    return offer.title if offer else "une annonce supprimée"


def can_reply(review: Review, user) -> bool:
    """Le vendeur concerné (et lui seul) répond à l'avis, via `identity.acts_for_context`."""
    return identity_services.acts_for_context(user.pk, review.seller_context_type, review.seller_context_id)


def reply_to_review(review: Review, replier, content: str) -> Review:
    """Réponse publique du vendeur concerné ; l'auteur de l'avis en est prévenu (événement
    `reviews.review_replied`, publié dans la même transaction que la réponse)."""
    if not can_reply(review, replier):
        raise ReviewError("Seul le vendeur concerné peut répondre à cet avis.", 'not_seller')
    offer = marketplace_services.get_offer(review.offer_id)
    with transaction.atomic():
        # Mise à jour conditionnelle : la réponse ne s'écrit qu'une fois, même en cas de requêtes simultanées.
        written = Review.objects.filter(pk=review.pk).filter(
            Q(reply_content__isnull=True) | Q(reply_content=''),
        ).update(reply_content=content, reply_at=timezone.now(), updated_at=timezone.now())
        if not written:
            raise ReviewError("Vous avez déjà répondu à cet avis.", 'already_replied', HTTP_CONFLICT)
        publish_event(
            'reviews.review_replied', aggregate_type='review', aggregate_id=review.pk,
            payload={
                'review_id': str(review.pk), 'review_author_id': str(review.user_id),
                'replier_id': str(replier.pk), 'offer_id': str(review.offer_id) if offer else None,
                'offer_title': _offer_title(offer),
            },
        )
    review.refresh_from_db()
    return review


EXCERPT_LENGTH = 50


def get_review_excerpt(review_id):
    """Début du texte d'un avis (notification), ou None si l'avis n'existe plus."""
    content = Review.objects.filter(pk=review_id).values_list('content', flat=True).first()
    return None if content is None else content[:EXCERPT_LENGTH]


def get_report_labels(ids) -> dict:
    """Libellés d'avis signalables, indexés par UUID (une requête) : sert à la modération.
    Un avis absent n'apparaît pas dans le résultat."""
    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return {review.id: str(review) for review in Review.objects.filter(id__in=wanted)}


def get_report_authors(ids) -> dict:
    """Auteur de chaque avis, `{avis: auteur}` (une requête)."""
    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return dict(Review.objects.filter(id__in=wanted).values_list('id', 'user_id'))
