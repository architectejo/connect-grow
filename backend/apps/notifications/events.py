"""Abonnés de `notifications` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
from datetime import datetime

from apps.common.utils import parse_uuid
from apps.identity import services as identity_services
from apps.platform_core.registry import PermanentEventError, subscribe
from apps.reviews import services as reviews_services

from . import services

UNKNOWN_USER = "Un utilisateur"


def _require(payload, *keys):
    """Valeurs obligatoires de la charge utile ; une clé absente ou un UUID mal formé est une
    erreur définitive (rejouer ne changera rien)."""
    try:
        return [payload[key] for key in keys]
    except (KeyError, TypeError) as exc:
        raise PermanentEventError("charge utile invalide") from exc


def _user_id(value):
    parsed = parse_uuid(value)
    if parsed is None:
        raise PermanentEventError("charge utile invalide")
    return parsed


def _name(user_id_value):
    user_id = _user_id(user_id_value)
    return identity_services.get_full_names([user_id]).get(user_id) or UNKNOWN_USER


@subscribe('marketplace.contact_recorded', name='notifications.notify_contact')
def notify_contact(event):
    seller_id, sender_id, title = _require(event.payload, 'seller_id', 'sender_id', 'offer_title')
    services.notify(
        user_id=_user_id(seller_id), notification_type=services.CONTACT,
        title="Nouvelle demande de contact",
        content=f"{_name(sender_id)} vous a contacté pour {title}",
        link='/messages',
    )


@subscribe('marketplace.exchange_proposed', name='notifications.notify_exchange')
def notify_exchange(event):
    seller_id, sender_id, title = _require(event.payload, 'seller_id', 'sender_id', 'offer_title')
    services.notify(
        user_id=_user_id(seller_id), notification_type=services.EXCHANGE,
        title="Nouvelle proposition d'échange",
        content=f"{_name(sender_id)} propose un échange pour {title}",
        link='/messages',
    )


def _post_link(payload):
    return f"/post/{payload['offer_id']}" if payload.get('offer_id') else ''


@subscribe('reviews.review_posted', name='notifications.notify_review_posted')
def notify_review_posted(event):
    payload = event.payload
    review_id, reviewed_id, author_id, title = _require(
        payload, 'review_id', 'reviewed_user_id', 'author_id', 'offer_title',
    )
    excerpt = reviews_services.get_review_excerpt(_user_id(review_id))
    if excerpt is None:  # avis supprimé avant la diffusion : plus rien à annoncer
        return
    services.notify(
        user_id=_user_id(reviewed_id), notification_type=services.COMMENT,
        title=f"Nouvel avis sur {title}",
        content=f"{_name(author_id)} a laissé un avis : {excerpt}...",
        link=_post_link(payload),
    )


@subscribe('reviews.review_replied', name='notifications.notify_review_reply')
def notify_review_reply(event):
    payload = event.payload
    author_id, replier_id, title = _require(payload, 'review_author_id', 'replier_id', 'offer_title')
    services.notify(
        user_id=_user_id(author_id), notification_type=services.SYSTEM,
        title="Réponse à votre avis",
        content=f"{_name(replier_id)} a répondu à votre avis sur {title}",
        link=_post_link(payload),
    )


@subscribe('marketplace.offer_expiring_soon', name='notifications.notify_offer_expiration')
def notify_offer_expiration(event):
    payload = event.payload
    seller_id, title, offer_id, raw_date = _require(payload, 'seller_id', 'offer_title', 'offer_id', 'expires_at')
    try:
        expires_at = datetime.fromisoformat(raw_date)
    except (ValueError, TypeError) as exc:
        raise PermanentEventError("charge utile invalide") from exc
    services.notify(
        user_id=_user_id(seller_id), notification_type=services.EXPIRATION,
        title="Votre annonce expire bientôt",
        content=f"« {title} » expire le {expires_at:%d/%m/%Y}. Renouvelez-la pour rester visible.",
        link=f"/post/{offer_id}",
    )
