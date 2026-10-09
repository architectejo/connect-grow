"""Interface publique du domaine `moderation` pour les autres domaines."""
from .models import AuditLog


def record_audit(actor, action, target=None, details=''):
    """Journalise une action sensible (règle 12) dans l'AuditLog."""
    return AuditLog.record(actor, action, target=target, details=details)
