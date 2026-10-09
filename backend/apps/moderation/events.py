"""Abonnés de `moderation` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
import uuid

from apps.platform_core.registry import PermanentEventError, subscribe

from . import services


@subscribe('reviews.crossed_reviews_detected', name='moderation.file_crossed_reviews_report')
def file_crossed_reviews_report(event):
    """CDC 3.7 (anti-abus) : dépose un signalement automatique sur l'avis ; idempotent (un seul
    signalement par avis et par motif)."""
    payload = event.payload
    try:
        review_id = uuid.UUID(payload['review_id'])
        description = (
            f"Avis croisés répétés détectés entre les utilisateurs {payload['user_a']} et {payload['user_b']} "
            f"({int(payload['deals_count'])} affaires distinctes sur {int(payload['window_days'])} jours)."
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise PermanentEventError("charge utile invalide") from exc
    services.file_automatic_report('review', review_id, services.REASON_CROSSED_REVIEWS, description=description)
