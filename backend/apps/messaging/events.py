"""Abonnés de `messaging` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
import uuid

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER
from apps.identity import services as identity_services
from apps.marketplace import services as marketplace_services
from apps.platform_core.registry import PermanentEventError, subscribe

from . import services


def _open(event, text, contact_event_id=None):
    """Ouvre la conversation du contact ou de l'échange (événements de version 2, ADR 0006, section 8).

    Le vendeur est un CONTEXTE : le destinataire est résolu ICI, à la livraison. Compte ou prestataire : le titulaire
    est participant ; organisation : seul l'acheteur est participant et l'équipe habilitée (`message.reply`) accède
    par capacité, donc aucun membre n'est copié dans la conversation."""
    payload = event.payload
    try:
        offer_id, sender_id = (uuid.UUID(payload[key]) for key in ('offer_id', 'sender_id'))
        if event.version == 1:  # encore en file : le vendeur était un compte, lu comme son contexte USER
            context_type, context_id = CONTEXT_USER, uuid.UUID(payload['seller_id'])
        else:
            context_type = payload['seller_context_type']
            context_id = uuid.UUID(payload['seller_context_id'])
    except (KeyError, ValueError, TypeError) as exc:
        raise PermanentEventError("charge utile invalide") from exc
    if context_type not in (CONTEXT_USER, CONTEXT_PROVIDER, CONTEXT_ORGANIZATION):
        raise PermanentEventError("charge utile invalide")
    if text is None:  # contact supprimé avec son annonce avant la diffusion : rien à ouvrir
        return
    recipient_id = None
    if context_type != CONTEXT_ORGANIZATION:
        key = (context_type, context_id)
        recipient_id = identity_services.get_contact_accounts([key]).get(key)
        if recipient_id is None:  # prestataire archivé entre-temps : pas de destinataire, pas de remise
            return
    services.open_conversation_with_message(
        offer_id=offer_id, sender_id=sender_id, recipient_id=recipient_id, content=text,
        contact_event_id=contact_event_id, seller_context=(context_type, context_id),
    )


@subscribe('marketplace.contact_recorded', name='messaging.open_contact_conversation', versions=(1, 2))
def open_contact_conversation(event):
    contact_event_id = event.payload.get('contact_event_id')
    _open(event, marketplace_services.get_contact_message(contact_event_id), contact_event_id=contact_event_id)


@subscribe('marketplace.exchange_proposed', name='messaging.open_exchange_conversation', versions=(1, 2))
def open_exchange_conversation(event):
    _open(event, marketplace_services.get_exchange_message(event.payload.get('proposal_id')))
