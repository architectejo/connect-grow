"""Aides de test : diffusion synchrone de l'outbox (les tests désactivent la diffusion immédiate)."""
from . import services


def dispatch_outbox_now(limit=1000) -> dict:
    """Diffuse toutes les livraisons échues, immédiatement."""
    return services.dispatch_due(limit=limit)
