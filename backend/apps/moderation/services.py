"""Interface publique du domaine `moderation` pour les autres domaines."""
from .models import AuditLog, Report


def record_audit(actor, action, target=None, details=''):
    """Journalise une action sensible (règle 12) dans l'AuditLog."""
    return AuditLog.record(actor, action, target=target, details=details)


# Motif des signalements automatiques d'avis croisés (CDC 3.7), exposé sans importer le modèle.
REASON_CROSSED_REVIEWS = Report.REASON_AVIS_CROISES


def file_automatic_report(target, reason, description=''):
    """Dépose dans la file de modération un signalement émis par le système (sans auteur).
    Un seul signalement par cible et par motif : renvoie None s'il existe déjà."""
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(target)
    object_id = str(target.pk)
    if Report.objects.filter(content_type=content_type, object_id=object_id, reason=reason).exists():
        return None
    return Report.objects.create(
        content_type=content_type, object_id=object_id, reporter=None, reason=reason, description=description,
    )


def has_open_report(target) -> bool:
    """Vrai si la cible fait l'objet d'un signalement non clos (en attente ou pris en charge)."""
    from django.contrib.contenttypes.models import ContentType

    return Report.objects.filter(
        content_type=ContentType.objects.get_for_model(target), object_id=str(target.pk),
        status__in=(Report.STATUS_EN_ATTENTE, Report.STATUS_EN_COURS),
    ).exists()
