"""Interface publique du domaine `reviews` et logique métier des avis (CDC 3.7).

Dépendances sortantes, toutes par `services.py` : marketplace (offres), identity (cache du
Trust Score, transitoire), moderation (journal d'audit). Les notifications et le signalement
automatique passent par des événements de domaine (outbox, ADR 0003). Aucune n'importe un
modèle d'un autre domaine.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.identity import services as identity_services
from apps.marketplace import services as marketplace_services
from apps.moderation import services as moderation_services
from apps.platform_core.services import publish_event

from .models import Deal, Review, ReviewDailyCount, TrustScoreSettings

# CDC 3.7 (anti-abus) : 5 avis par jour et par utilisateur ; avis croisés : 3 affaires
# distinctes entre les deux mêmes comptes en 30 jours. Valeurs du CDC, reprises telles
# quelles au portage ; leur paramétrage relève de L0-10 (nouvelle règle d'avis).
DAILY_REVIEW_LIMIT = 5
LIMIT_MESSAGE = f"Vous avez atteint la limite de {DAILY_REVIEW_LIMIT} avis par jour."
CROSSED_REVIEWS_THRESHOLD = 3
CROSSED_REVIEWS_WINDOW_DAYS = 30


class ReviewError(Exception):
    """Refus métier (message en français) ; `field` désigne le champ fautif, le cas échéant."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def get_min_reviews_to_display() -> int:
    """CDC 3.7 : nombre d'avis à partir duquel la note d'un vendeur est affichée."""
    return TrustScoreSettings.get_solo().min_reviews_to_display


# --- Trust Score (transitoire, retiré par L0-07) ----------------------------------

def recompute_trust_score(user_id) -> None:
    """Moyenne bayésienne des avis reçus (hors avis masqués), mise en cache sur l'utilisateur,
    puis répercutée sur le score de visibilité de ses offres actives (facteur T)."""
    row = TrustScoreSettings.get_solo()
    ratings = list(Review.objects.filter(reviewed_user_id=user_id, is_hidden=False).values_list('rating', flat=True))
    n = len(ratings)
    score = (row.neutral_weight * row.neutral_rating + sum(ratings)) / (row.neutral_weight + n)
    identity_services.set_reputation(user_id, round(score, 2), n)
    marketplace_services.refresh_seller_offer_scores(user_id)


def check_crossed_reviews(review: Review) -> None:
    """CDC 3.7 (anti-abus) : détecte les avis croisés répétés entre les deux mêmes comptes et
    les envoie en modération plutôt que de les bloquer — un faux positif ne doit pas
    empêcher un vrai avis d'exister."""
    user_a, user_b = review.user_id, review.reviewed_user_id
    if not user_a or not user_b:
        return

    since = timezone.now() - timedelta(days=CROSSED_REVIEWS_WINDOW_DAYS)
    deal_ids = set(
        Review.objects.filter(
            Q(user_id=user_a, reviewed_user_id=user_b) | Q(user_id=user_b, reviewed_user_id=user_a),
            created_at__gte=since,
        ).values_list('deal_id', flat=True)
    )
    if len(deal_ids) >= CROSSED_REVIEWS_THRESHOLD:
        with transaction.atomic():
            publish_event(
                'reviews.crossed_reviews_detected', aggregate_type='review', aggregate_id=review.pk,
                payload={
                    'review_id': str(review.pk), 'user_a': str(user_a), 'user_b': str(user_b),
                    'deals_count': len(deal_ids), 'window_days': CROSSED_REVIEWS_WINDOW_DAYS,
                },
            )


# --- Création d'un avis ---------------------------------------------------------------

def validate_new_review(user, deal):
    """Contrôle les conditions d'un nouvel avis et renvoie la personne évaluée.
    Lève ReviewError (CDC 3.7 : affaire confirmée, partie prenante, un avis par partie, limite quotidienne)."""
    if deal is None:
        raise ReviewError("Un avis n'est possible qu'après une affaire conclue.", 'deal')
    if deal.status != Deal.STATUS_CONFIRMED:
        raise ReviewError("Cette affaire n'a pas encore été confirmée par les deux parties.", 'deal')
    reviewed_user = deal.other_party(user)
    if reviewed_user is None:
        raise ReviewError("Vous ne faites pas partie de cette affaire.", 'deal')
    if Review.objects.filter(deal=deal, user=user).exists():
        raise ReviewError("Vous avez déjà laissé un avis pour cette affaire.")
    today_count = ReviewDailyCount.objects.filter(user=user, date=timezone.localdate()).values_list('count', flat=True).first()
    if (today_count or 0) >= DAILY_REVIEW_LIMIT:
        raise ReviewError(LIMIT_MESSAGE)
    return reviewed_user


def reserve_daily_slot(user) -> None:
    """Réserve atomiquement une place dans la limite quotidienne (à appeler dans la transaction
    de création). Les avis supprimés ensuite restent comptés."""
    today = timezone.localdate()
    ReviewDailyCount.objects.get_or_create(user=user, date=today)
    reserved = ReviewDailyCount.objects.filter(user=user, date=today, count__lt=DAILY_REVIEW_LIMIT).update(
        count=F('count') + 1,
    )
    if not reserved:
        raise ReviewError(LIMIT_MESSAGE)


def ensure_author_can_modify(review: Review) -> None:
    """Un avis masqué ou signalé échappe à son auteur : il ne peut ni le modifier ni le supprimer
    (sinon il effacerait la preuve avant la décision de la modération)."""
    if review.is_hidden:
        raise ReviewError("Cet avis a été masqué par la modération : vous ne pouvez plus le modifier ni le supprimer.")
    if moderation_services.has_open_report(review):
        raise ReviewError("Cet avis fait l'objet d'un signalement en cours : vous ne pouvez plus le modifier ni le supprimer.")


def set_review_hidden(review: Review, hidden: bool, actor) -> None:
    """Masque ou réaffiche un avis (CDC 3.7) ; journalisé (règle 12). Le Trust Score est recalculé
    par le signal d'enregistrement."""
    if review.is_hidden == hidden:
        return
    review.is_hidden = hidden
    review.save(update_fields=['is_hidden', 'updated_at'])
    moderation_services.record_audit(actor, 'REVIEW_HIDDEN' if hidden else 'REVIEW_UNHIDDEN', target=review)


def _offer_title(offer):
    return offer.title if offer else "une annonce supprimée"


def publish_review_posted(review: Review, author) -> None:
    """Publie `reviews.review_posted` (à appeler dans la transaction de création de l'avis) : la
    personne évaluée est notifiée à la diffusion. Le nom de l'auteur, le titre de l'annonce et
    l'extrait sont des données déjà publiques avec l'avis."""
    if not review.reviewed_user_id:
        return
    offer = marketplace_services.get_offer(review.offer_id) if review.offer_id else None
    publish_event(
        'reviews.review_posted', aggregate_type='review', aggregate_id=review.pk,
        payload={
            'review_id': str(review.pk), 'reviewed_user_id': str(review.reviewed_user_id),
            'author_id': str(author.pk), 'author_name': author.full_name,
            'offer_id': str(review.offer_id) if offer else None,
            'offer_title': _offer_title(offer), 'excerpt': review.content[:50],
        },
    )


def reply_to_review(review: Review, replier, content: str) -> Review:
    """Réponse publique de la personne évaluée ; l'auteur de l'avis en est prévenu (événement
    `reviews.review_replied`, publié dans la même transaction que la réponse)."""
    offer = marketplace_services.get_offer(review.offer_id) if review.offer_id else None
    with transaction.atomic():
        # Mise à jour conditionnelle : la réponse ne s'écrit qu'une fois, même en cas de requêtes simultanées.
        written = Review.objects.filter(pk=review.pk).filter(
            Q(reply_content__isnull=True) | Q(reply_content=''),
        ).update(reply_content=content, reply_at=timezone.now(), updated_at=timezone.now())
        if not written:
            raise ReviewError("Vous avez déjà répondu à cet avis.")
        publish_event(
            'reviews.review_replied', aggregate_type='review', aggregate_id=review.pk,
            payload={
                'review_id': str(review.pk), 'review_author_id': str(review.user_id),
                'replier_name': replier.full_name, 'offer_id': str(review.offer_id) if offer else None,
                'offer_title': _offer_title(offer),
            },
        )
    review.refresh_from_db()
    return review


def get_report_labels(ids) -> dict:
    """Libellés d'avis signalables, indexés par UUID (une requête) : sert à la modération.
    Un avis absent n'apparaît pas dans le résultat."""
    from apps.common.utils import parse_uuid

    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return {review.id: str(review) for review in Review.objects.filter(id__in=wanted)}


def get_report_authors(ids) -> dict:
    """Auteur de chaque avis, `{avis: auteur}` (une requête)."""
    from apps.common.utils import parse_uuid

    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return dict(Review.objects.filter(id__in=wanted).values_list('id', 'user_id'))
