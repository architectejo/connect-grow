"""Abonnés de `notifications` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
from apps.common.utils import parse_uuid
from apps.identity import services as identity_services
from apps.platform_core.registry import PermanentEventError, subscribe

from . import services

UNKNOWN_USER = "Un utilisateur"


def _sender_name(payload):
    sender_id = parse_uuid(payload.get('sender_id'))
    if sender_id is None:
        raise PermanentEventError("charge utile invalide")
    return identity_services.get_full_names([sender_id]).get(sender_id) or UNKNOWN_USER


@subscribe('marketplace.contact_recorded', name='notifications.notify_contact')
def notify_contact(event):
    payload = event.payload
    services.notify(
        user_id=payload['seller_id'], notification_type=services.CONTACT,
        title="Nouvelle demande de contact",
        content=f"{_sender_name(payload)} vous a contacté pour {payload['offer_title']}",
        link='/messages',
    )


@subscribe('marketplace.exchange_proposed', name='notifications.notify_exchange')
def notify_exchange(event):
    payload = event.payload
    services.notify(
        user_id=payload['seller_id'], notification_type=services.EXCHANGE,
        title="Nouvelle proposition d'échange",
        content=f"{_sender_name(payload)} propose un échange pour {payload['offer_title']}",
        link='/messages',
    )


def _post_link(payload):
    return f"/post/{payload['offer_id']}" if payload.get('offer_id') else ''


@subscribe('reviews.review_posted', name='notifications.notify_review_posted')
def notify_review_posted(event):
    payload = event.payload
    services.notify(
        user_id=payload['reviewed_user_id'], notification_type=services.COMMENT,
        title=f"Nouvel avis sur {payload['offer_title']}",
        content=f"{payload['author_name']} a laissé un avis : {payload['excerpt']}...",
        link=_post_link(payload),
    )


@subscribe('reviews.review_replied', name='notifications.notify_review_reply')
def notify_review_reply(event):
    payload = event.payload
    services.notify(
        user_id=payload['review_author_id'], notification_type=services.SYSTEM,
        title="Réponse à votre avis",
        content=f"{payload['replier_name']} a répondu à votre avis sur {payload['offer_title']}",
        link=_post_link(payload),
    )
