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
