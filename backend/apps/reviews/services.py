"""Interface publique du domaine `reviews` et logique métier des avis après contact (CDC 3.4, ADR 0004).

Dépendances sortantes, toutes par `services.py` : marketplace (offres, preuve de contact),
identity (contexte vendeur), moderation (journal d'audit). Les notifications et le signalement
automatique passent par des événements de domaine (outbox, ADR 0003). Aucune n'importe un modèle
d'un autre domaine.

Aucune note agrégée n'est stockée : les moyennes sont calculées à la lecture (règle 4).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.common.contexts import CONTEXT_USER, DENY_RELATION, ContextDenied
from apps.common.utils import parse_uuid, seconds_until_next_day
from apps.identity import services as identity_services
from apps.marketplace import services as marketplace_services
from apps.moderation import services as moderation_services
from apps.platform_core.services import publish_event

from .models import DeletedReviewMark, Review, ReviewDailyCount, ReviewSettings

# Statuts HTTP portés par les refus métier (la couche vue les traduit sans les connaître).
HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_CONFLICT, HTTP_TOO_MANY = 403, 404, 409, 429


class ReviewError(Exception):
    """Refus métier : message en français, code machine stable et statut HTTP suggéré."""

    def __init__(self, message, code, status_code=HTTP_FORBIDDEN, wait=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.wait = wait  # secondes avant de pouvoir réessayer (en-tête Retry-After des 429)


NOT_ELIGIBLE_MESSAGE = "Vous pourrez donner votre avis après avoir contacté le vendeur."


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


def get_seller_dashboard_rating(context_type, seller_id) -> SellerDashboardRating:
    """Pour le tableau de bord d'un contexte vendeur : moyenne de ses notes vendeur visibles, sans
    seuil d'affichage (None s'il n'a aucun avis), et nombre d'avis visibles reçus. `seller_id` est l'identifiant
    du contexte (compte, profil prestataire ou organisation) de type `context_type`."""
    visible = Review.objects.filter(
        seller_context_type=context_type, seller_context_id=seller_id, is_hidden=False,
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
    with transaction.atomic():
        rows = Review.objects.filter(
            user_id=user_id, seller_context_type=context_type, seller_context_id=context_id,
        )
        # Verrou sur les avis du couple : deux recalculs simultanés se suivent au lieu de se croiser.
        list(rows.select_for_update().values_list('id', flat=True))
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

# Refus d'avis : motif d'éligibilité -> (code d'erreur de POST, statut HTTP, message). Le motif est
# celui de `GET /reviews/eligibility/` ; le code est celui de `POST /reviews/` (ADR 0004, 7.2).
REFUSALS = {
    'own_offer': ('own_offer', HTTP_FORBIDDEN, "Vous ne pouvez pas noter votre propre annonce."),
    'no_contact': ('not_eligible', HTTP_FORBIDDEN, NOT_ELIGIBLE_MESSAGE),
    'recently_deleted': (
        'review_recently_deleted', HTTP_CONFLICT,
        "Vous avez supprimé votre avis pour cette annonce : vous pourrez en écrire un autre plus tard.",
    ),
    'contact_rejected': (
        'contact_rejected', HTTP_FORBIDDEN,
        "Votre contact avec ce vendeur n'a pas été retenu par la modération : vous ne pouvez pas donner votre avis pour cette annonce.",
    ),
    'already_reviewed': (
        'already_reviewed', HTTP_CONFLICT, "Vous avez déjà donné votre avis pour cette annonce.",
    ),
    'offer_unavailable': ('offer_unavailable', HTTP_CONFLICT, "Cette annonce n'est plus disponible."),
    'too_early': ('review_too_early', HTTP_FORBIDDEN, "Vous pourrez donner votre avis dans {delay}."),
    'account_too_new': (
        'account_too_new', HTTP_FORBIDDEN,
        "Votre compte est trop récent pour publier un avis : vous pourrez le faire dans {delay}.",
    ),
}


@dataclass(frozen=True)
class Eligibility:
    """Droit d'un utilisateur de noter une offre. `reason` est None si `can_review` ; `available_at`
    n'est renseigné que pour `too_early` ; `review_id` pour `already_reviewed`."""

    can_review: bool
    reason: Optional[str] = None
    available_at: Optional[datetime] = None
    review_id: Optional[object] = None


def _format_delay(delta: timedelta) -> str:
    """Durée restante en français, arrondie à la minute supérieure : « 2 heures et 5 minutes »."""
    minutes = max(1, -(-int(delta.total_seconds()) // 60))
    days, rest = divmod(minutes, 1440)
    hours, minutes = divmod(rest, 60)
    parts = [
        f"{value} {label}{'s' if value > 1 else ''}"
        for value, label in ((days, 'jour'), (hours, 'heure'), (minutes, 'minute')) if value
    ]
    return ' et '.join(parts[:2])


def assess_eligibility(user, offer_id):
    """Évalue le droit de `user` de noter l'offre ; renvoie `(Eligibility, offre, preuve de contact)`.

    Ordre (ADR 0004, 7.2) : offre inconnue (404), propre offre, aucun contact (404 si l'offre n'est pas
    publique), contact écarté par la modération, avis déjà donné, avis supprimé récemment, offre
    indisponible, délai après contact. Une offre non
    publique (corbeille, masquée, hors ligne) n'est connue que de son vendeur et de ceux qui l'ont
    contactée : pour les autres, elle est introuvable (404 uniforme, aucune fuite d'existence)."""
    offer = marketplace_services.get_offer(offer_id)
    if offer is None:
        raise ReviewError("Annonce introuvable.", 'offer_not_found', HTTP_NOT_FOUND)
    if identity_services.acts_for_context(user.pk, offer.seller_context_type, offer.seller_context_id):
        return Eligibility(False, 'own_offer'), offer, None
    contact = marketplace_services.get_review_contact(offer.id, user.pk)
    if contact is None:
        if not offer.is_available:
            raise ReviewError("Annonce introuvable.", 'offer_not_found', HTTP_NOT_FOUND)
        return Eligibility(False, 'no_contact'), offer, None
    existing = Review.objects.filter(user=user, offer_id=offer.id).values_list('id', 'is_hidden').first()
    existing_id = None if existing is None else existing[0]
    # `contact_rejected` dérive de l'état réel : avis masqué ET signalement « contact fictif » traité.
    # Réafficher l'avis (modération) le défait ; aucun indicateur n'est stocké à part.
    if existing is not None and existing[1] and moderation_services.has_resolved_report(
        'review', existing_id, moderation_services.REASON_CONTACT_FICTIF,
    ):
        return Eligibility(False, 'contact_rejected', review_id=existing_id), offer, contact
    if existing_id is not None:
        return Eligibility(False, 'already_reviewed', review_id=existing_id), offer, contact
    mark = DeletedReviewMark.objects.filter(user=user, offer_id=offer.id).first()
    if mark is not None and timezone.now() < mark.deleted_at + timedelta(hours=get_settings().edit_window_hours):
        return Eligibility(False, 'recently_deleted'), offer, contact
    if offer.is_deleted or offer.is_hidden_by_moderation:
        return Eligibility(False, 'offer_unavailable'), offer, contact
    row = get_settings()
    contact_ready = contact.recorded_at + timedelta(hours=row.delay_after_contact_hours)
    account_ready = user.date_joined + timedelta(hours=row.min_account_age_hours)
    # Un seul `available_at` : la plus tardive des deux échéances, avec le motif qui la porte.
    if timezone.now() < max(contact_ready, account_ready):
        if account_ready > contact_ready:
            return Eligibility(False, 'account_too_new', available_at=account_ready), offer, contact
        return Eligibility(False, 'too_early', available_at=contact_ready), offer, contact
    return Eligibility(True), offer, contact


def get_eligibility(user, offer_id) -> Eligibility:
    """Éligibilité exposée par `GET /reviews/eligibility/` (lève `ReviewError` 404 si introuvable)."""
    return assess_eligibility(user, offer_id)[0]


def ensure_can_review(user, offer_id):
    """Contrôle les conditions d'un nouvel avis et renvoie `(offre, preuve de contact)` ; lève
    `ReviewError` avec le code de `POST /reviews/` sinon (même évaluation que l'éligibilité)."""
    eligibility, offer, contact = assess_eligibility(user, offer_id)
    if not eligibility.can_review:
        code, status_code, message = REFUSALS[eligibility.reason]
        if eligibility.reason in ('too_early', 'account_too_new'):
            message = message.format(delay=_format_delay(eligibility.available_at - timezone.now()))
        raise ReviewError(message, code, status_code)
    return offer, contact


def reject_fictitious_contact(review_id, actor) -> None:
    """Décision de la modération sur un signalement « contact fictif » validé : l'avis est masqué
    (ses notes sortent des moyennes) et son auteur ne peut ni le supprimer ni en écrire un autre pour
    cette offre. Sans effet si l'avis n'existe plus."""
    review = Review.objects.filter(pk=review_id).first()
    if review is not None:
        set_review_hidden(review, True, actor)


def is_review_seller(review_id, user) -> bool:
    """Vrai si `user` peut agir pour le vendeur noté par l'avis (ADR 0006, 11.3) : capacité `review.reply` du contexte
    vendeur de l'avis (membre éligible de l'organisation, titulaire du prestataire ou du compte ; pas l'analyste,
    pas un ancien membre). Sert au signalement « contact fictif »."""
    row = Review.objects.filter(pk=review_id).values_list('seller_context_type', 'seller_context_id').first()
    return row is not None and identity_services.can(user.pk, row[0], row[1], CAP_REPLY)


def reserve_daily_slot(user) -> None:
    """Réserve atomiquement une place dans la limite quotidienne (à appeler dans la transaction
    de création). Les avis supprimés ensuite restent comptés."""
    limit = get_settings().daily_review_limit
    today = timezone.localdate()
    ReviewDailyCount.objects.get_or_create(user=user, date=today)
    reserved = ReviewDailyCount.objects.filter(user=user, date=today, count__lt=limit).update(count=F('count') + 1)
    if not reserved:
        raise ReviewError(f"Vous avez atteint la limite de {limit} avis par jour.", 'daily_limit', HTTP_TOO_MANY,
                          wait=seconds_until_next_day())


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


def _lock_review(review: Review) -> Review:
    """Relit l'avis sous verrou (à appeler dans une transaction) : les contrôles d'état qui suivent
    portent sur la ligne à jour, pas sur une copie périmée (masquage, signalement ou réponse
    survenus entre la lecture et l'écriture)."""
    locked = Review.objects.select_for_update().filter(pk=review.pk).first()
    if locked is None:
        raise ReviewError("Avis introuvable.", 'not_found', HTTP_NOT_FOUND)
    return locked


def update_review(review: Review, changes: dict) -> Review:
    """Modifie la note d'offre, la note vendeur ou le texte (fenêtre `edit_window_hours`) ; renseigne
    `edited_at`. Refusé après la réponse du vendeur. Modifier un avis qui n'est pas le plus récent
    du couple ne change pas la moyenne vendeur. Atomique, contrôles sur la ligne verrouillée."""
    with transaction.atomic():
        review = _lock_review(review)
        ensure_author_can_modify(review, deleting=False)
        if review.reply_content:
            raise ReviewError(
                "Le vendeur a répondu à cet avis : vous ne pouvez plus le modifier.", 'review_locked_after_reply',
            )
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


def delete_review(review: Review, actor) -> None:
    """Suppression par l'auteur, journalisée (règle 12). Refusée si le vendeur a répondu (la réponse
    publique ne doit pas disparaître avec l'avis) ou si l'avis est masqué ou signalé. La place de la
    limite quotidienne n'est pas libérée, et le même auteur ne peut pas réécrire un avis pour cette
    offre pendant `edit_window_hours` (`DeletedReviewMark`)."""
    with transaction.atomic():
        review = _lock_review(review)
        ensure_author_can_modify(review, deleting=True)
        if review.reply_content:
            raise ReviewError(
                "Le vendeur a répondu à cet avis : vous ne pouvez plus le supprimer.", 'review_locked_after_reply',
            )
        moderation_services.record_audit(
            actor, 'REVIEW_DELETED', target=review,
            details=f"Avis sur l'offre {review.offer_id}, notes {review.offer_rating}/{review.seller_rating}",
        )
        DeletedReviewMark.objects.update_or_create(
            user_id=review.user_id, offer_id=review.offer_id, defaults={'deleted_at': timezone.now()},
        )
        review.delete()
        reconcile_seller_flag(review.user_id, review.seller_context_type, review.seller_context_id)


def ensure_author_can_modify(review: Review, deleting: bool) -> None:
    """Un avis masqué échappe à son auteur (modification et suppression). Tant qu'un signalement
    grave est ouvert (contact fictif et motifs de fond), l'auteur ne peut pas SUPPRIMER son avis (la
    preuve ne s'efface pas avant la décision) mais peut encore le MODIFIER et se défendre ; un
    signalement de motif mineur (spam, autre) ne verrouille rien."""
    if review.is_hidden:
        raise ReviewError(
            "Cet avis a été masqué par la modération : vous ne pouvez plus le modifier ni le supprimer.",
            'review_locked',
        )
    if deleting and moderation_services.has_open_report(review, grave_only=True):
        raise ReviewError(
            "Cet avis fait l'objet d'un signalement en cours : vous ne pouvez pas le supprimer avant la décision.",
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
    """Publie `reviews.review_posted` (v3), à appeler dans la transaction de création. La charge utile désigne le
    CONTEXTE vendeur de l'avis, pas des comptes : l'abonné résout les destinataires à la livraison (compte,
    titulaire du profil prestataire, membres éligibles de l'organisation selon `review.reply`, ADR 0006, section 8).
    Seuls des identifiants et le titre public de l'annonce sont copiés : le nom de l'auteur et l'extrait sont
    relus à la diffusion."""
    if offer is None:
        offer = marketplace_services.get_offer(review.offer_id)
    publish_event(
        'reviews.review_posted', aggregate_type='review', aggregate_id=review.pk,
        payload={
            'review_id': str(review.pk), 'author_id': str(author.pk),
            'offer_id': str(review.offer_id) if offer else None, 'offer_title': _offer_title(offer),
            'seller_context_type': review.seller_context_type, 'seller_context_id': str(review.seller_context_id),
        },
    )


def _offer_title(offer):
    return offer.title if offer else "une annonce supprimée"


CAP_REPLY = 'review.reply'
NOT_SELLER_MESSAGE = "Seul le vendeur concerné peut répondre à cet avis."


def can_reply(review: Review, user) -> bool:
    """Le vendeur concerné répond à l'avis. Contexte personnel ou prestataire : le titulaire ; organisation : la
    capacité `review.reply` (propriétaire, administrateur, éditeur ; jamais l'analyste), relue en base. Compte
    désactivé ou sanctionné, ancien membre, organisation suspendue ou archivée : non. Pour une LISTE d'avis, utiliser
    `get_reply_contexts` (une seule fois pour toute la page)."""
    return identity_services.can(user.pk, review.seller_context_type, review.seller_context_id, CAP_REPLY)


def get_reply_contexts(user) -> set:
    """Contextes vendeur `(type, id)` pour lesquels `user` peut répondre aux avis (capacité `review.reply`),
    calculés PAR LOT : 4 requêtes au plus, quel que soit le nombre d'avis affichés (plus de N+1). Mêmes règles que
    `can_reply`. Un utilisateur anonyme n'a aucun contexte."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return set()
    return identity_services.get_capable_contexts(user.pk, CAP_REPLY)


def ensure_can_reply(review: Review, user) -> None:
    """Contrôle d'autorisation de la réponse, par OBJET (contexte propriétaire de l'avis, jamais l'en-tête
    `X-Context`). Un étranger au contexte, l'auteur de l'avis ou un ancien membre : 403 `not_seller` (contrat de
    l'ADR 0004). Un membre sans la capacité (analyste) : 403 `DENY_PERMISSION` ; compte sanctionné ou organisation
    suspendue : `DENY_SECURITY` ; organisation archivée : `DENY_OBJECT_STATE`."""
    try:
        identity_services.authorize_on(user, review.seller_context_type, review.seller_context_id, CAP_REPLY)
    except ContextDenied as exc:
        if exc.detail.code == DENY_RELATION:
            raise ReviewError(NOT_SELLER_MESSAGE, 'not_seller')
        raise


def reply_to_review(review: Review, replier, content: str) -> Review:
    """Réponse publique du vendeur concerné ; l'auteur de l'avis en est prévenu (événement
    `reviews.review_replied`, publié dans la même transaction que la réponse). Écriture sensible : l'autorisation
    est refaite sous la transaction (une révocation survenue entre-temps est prise en compte) et la réponse est
    journalisée avec le contexte vendeur (règle 12) ; elle s'affiche au nom du vendeur, jamais du membre."""
    offer = marketplace_services.get_offer(review.offer_id)
    with transaction.atomic():
        ensure_can_reply(review, replier)
        # Mise à jour conditionnelle : la réponse ne s'écrit qu'une fois, même en cas de requêtes simultanées.
        written = Review.objects.filter(pk=review.pk).filter(
            Q(reply_content__isnull=True) | Q(reply_content=''),
        ).update(reply_content=content, reply_at=timezone.now(), updated_at=timezone.now())
        if not written:
            raise ReviewError("Vous avez déjà répondu à cet avis.", 'already_replied', HTTP_CONFLICT)
        moderation_services.record_audit(
            replier, 'REVIEW_REPLIED', target=review, details=f"offer={review.offer_id}",
            context=(review.seller_context_type, review.seller_context_id),
        )
        publish_event(
            'reviews.review_replied', aggregate_type='review', aggregate_id=review.pk,
            payload={
                'review_id': str(review.pk), 'review_author_id': str(review.user_id),
                'seller_context_type': review.seller_context_type, 'seller_context_id': str(review.seller_context_id),
                'offer_id': str(review.offer_id) if offer else None,
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


def get_report_links(ids) -> dict:
    """Lien front de l'annonce de chaque avis, `{avis: '/post/<annonce>'}` (une requête) : sert aux
    notifications de la modération à l'auteur."""
    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return {
        review_id: f'/post/{offer_id}'
        for review_id, offer_id in Review.objects.filter(id__in=wanted).values_list('id', 'offer_id') if offer_id
    }
