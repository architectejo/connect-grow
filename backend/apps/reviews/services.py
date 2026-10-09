"""Interface publique du domaine `reviews` et logique métier des avis (CDC 3.7).

Dépendances sortantes, toutes par `services.py` : marketplace (offres), identity (cache du
Trust Score), notifications, moderation (signalement automatique). Aucune n'importe un
modèle d'un autre domaine.
"""
from datetime import timedelta

from django.utils import timezone

from apps.identity import services as identity_services
from apps.marketplace import services as marketplace_services
from apps.moderation import services as moderation_services
from apps.notifications import services as notification_services

from .models import Deal, Review, TrustScoreSettings

# CDC 3.7 (anti-abus) : 5 avis par jour et par utilisateur ; avis croisés : 3 affaires
# distinctes entre les deux mêmes comptes en 30 jours. Valeurs du CDC, reprises telles
# quelles au portage ; leur paramétrage relève de L0-10 (nouvelle règle d'avis).
DAILY_REVIEW_LIMIT = 5
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
    from django.db.models import Q

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
        moderation_services.file_automatic_report(
            review, moderation_services.REASON_CROSSED_REVIEWS,
            description=(
                f"Avis croisés répétés détectés entre les utilisateurs {user_a} et {user_b} "
                f"({len(deal_ids)} affaires distinctes sur {CROSSED_REVIEWS_WINDOW_DAYS} jours)."
            ),
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
    today_count = Review.objects.filter(user=user, created_at__date=timezone.now().date()).count()
    if today_count >= DAILY_REVIEW_LIMIT:
        raise ReviewError(f"Vous avez atteint la limite de {DAILY_REVIEW_LIMIT} avis par jour.")
    return reviewed_user


def _offer_title(offer):
    return offer.title if offer else "une annonce supprimée"


def notify_review_created(review: Review, author) -> None:
    offer = marketplace_services.get_offer(review.offer_id) if review.offer_id else None
    notification_services.notify(
        user_id=review.reviewed_user_id,
        notification_type=notification_services.COMMENT,
        title=f"Nouvel avis sur {_offer_title(offer)}",
        content=f"{author.full_name} a laissé un avis : {review.content[:50]}...",
        link=f"/post/{review.offer_id}" if offer else '',
    )


def reply_to_review(review: Review, replier, content: str) -> Review:
    """Réponse publique de la personne évaluée ; l'auteur de l'avis en est prévenu."""
    review.reply_content = content
    review.reply_at = timezone.now()
    review.save(update_fields=['reply_content', 'reply_at', 'updated_at'])
    offer = marketplace_services.get_offer(review.offer_id) if review.offer_id else None
    notification_services.notify(
        user_id=review.user_id,
        notification_type=notification_services.SYSTEM,
        title="Réponse à votre avis",
        content=f"{replier.full_name} a répondu à votre avis sur {_offer_title(offer)}",
        link=f"/post/{review.offer_id}" if offer else '',
    )
    return review
