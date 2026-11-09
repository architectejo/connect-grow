"""Abonnés de `reviews` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
from apps.platform_core.registry import subscribe

from . import services


@subscribe('identity.seller_context_removed', name='reviews.purge_seller_context')
def purge_seller_context(event):
    """Compte ou profil prestataire supprimé (T9-3) : efface les avis reçus par le contexte. Idempotent."""
    services.purge_seller_context(event.payload.get('context_type'), event.payload.get('context_id'))
