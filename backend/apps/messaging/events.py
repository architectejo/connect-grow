"""Abonnés de `messaging` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
import uuid

from apps.marketplace import services as marketplace_services
from apps.platform_core.registry import PermanentEventError, subscribe

from . import services


def _open(event, text):
    payload = event.payload
    try:
        offer_id, sender_id, seller_id = (uuid.UUID(payload[key]) for key in ('offer_id', 'sender_id', 'seller_id'))
    except (KeyError, ValueError, TypeError) as exc:
        raise PermanentEventError("charge utile invalide") from exc
    if text is None:  # contact supprimé avec son annonce avant la diffusion : rien à ouvrir
        return
    services.open_conversation_with_message(
        offer_id=offer_id, sender_id=sender_id, recipient_id=seller_id, content=text,
    )


@subscribe('marketplace.contact_recorded', name='messaging.open_contact_conversation')
def open_contact_conversation(event):
    _open(event, marketplace_services.get_contact_message(event.payload.get('contact_event_id')))


@subscribe('marketplace.exchange_proposed', name='messaging.open_exchange_conversation')
def open_exchange_conversation(event):
    _open(event, marketplace_services.get_exchange_message(event.payload.get('proposal_id')))
