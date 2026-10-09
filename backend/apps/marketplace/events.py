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
