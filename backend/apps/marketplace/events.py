"""Abonnés de `marketplace` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
from apps.common.utils import parse_uuid
from apps.platform_core.registry import PermanentEventError, subscribe

from . import services


def _sync(event):
    offer_id = parse_uuid(event.payload.get('offer_id'))
    if offer_id is None:
        raise PermanentEventError("charge utile invalide")
    services.sync_offer_engagement(offer_id)


@subscribe('visibility.offer_viewed', name='marketplace.sync_offer_views')
def sync_offer_views(event):
    _sync(event)


@subscribe('visibility.offer_shared', name='marketplace.sync_offer_shares')
def sync_offer_shares(event):
    _sync(event)


@subscribe('identity.seller_context_status_changed', name='marketplace.sync_seller_visibility')
def sync_seller_visibility(event):
    """Un vendeur devient public ou cesse de l'être (compte, profil prestataire, organisation) : recalcul
    idempotent de `Offer.seller_is_public` depuis `identity` (ADR 0006, A7). Rejouable sans risque."""
    services.apply_seller_status_event(event.payload)


@subscribe('visibility.ranking_settings_changed', name='marketplace.refresh_scores_after_ranking_change')
def refresh_scores_after_ranking_change(event):
    """Réglages du classement modifiés : recalcul idempotent des scores depuis les compteurs."""
    services.refresh_all_scores()


@subscribe('messaging.contact_message_delivered', name='marketplace.mark_contact_delivered')
def mark_contact_delivered(event):
    """Le message de contact est dans la conversation du vendeur : preuve de remise (ADR 0005, C10)."""
    contact_event_id = parse_uuid(event.payload.get('contact_event_id'))
    if contact_event_id is None:
        raise PermanentEventError("charge utile invalide")
    services.mark_contact_delivered(contact_event_id)
