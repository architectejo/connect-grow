"""Opérations d'exploitation de l'outbox, partagées par l'admin et la ligne de commande.

Seul module de `platform_core` (avec admin.py) à appeler un autre domaine, et uniquement par
son `services.py` : la relance d'une livraison est un acte sensible journalisé (règle 12).
"""
from apps.moderation.services import record_audit

from . import services

REQUEUE_ACTION = 'OUTBOX_REQUEUED'


def requeue_and_audit(actor, deliveries, via='back-office') -> int:
    """Relance les livraisons et journalise chacune dans l'AuditLog (sans la charge utile)."""
    requeued = services.requeue(list(deliveries))
    for delivery in requeued:
        record_audit(actor, REQUEUE_ACTION, target=delivery, details=f"{delivery.handler} ({via})")
    return len(requeued)
