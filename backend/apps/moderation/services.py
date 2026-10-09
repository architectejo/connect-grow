"""Interface publique du domaine `moderation` pour les autres domaines.

Un signalement ou une entrée du journal désigne sa cible par (`target_type`, `target_id`) : la
modération ne lit jamais les modèles des autres domaines, elle interroge leur `services.py`
(`get_report_labels`, par lot) selon le registre `TARGET_RESOLVERS`.
"""
from importlib import import_module

from apps.common.utils import parse_uuid

from .models import AuditLog, Report

# Type de cible -> module de services du domaine propriétaire.
TARGET_RESOLVERS = {
    'offer': 'apps.marketplace.services',
    'user': 'apps.identity.services',
    'review': 'apps.reviews.services',
    'message': 'apps.messaging.services',
}


class ReportRefused(Exception):
    """Signalement refusé (message en français) ; `duplicate` distingue le doublon (409)."""

    def __init__(self, message, duplicate=False):
        super().__init__(message)
        self.duplicate = duplicate


def resolve_target_author(target_type, target_id):
    """UUID de l'auteur de la cible (vendeur, rédacteur, expéditeur, compte lui-même), ou None."""
    module = TARGET_RESOLVERS.get(target_type)
    return import_module(module).get_report_authors([target_id]).get(target_id) if module else None


def ensure_can_report(reporter, target_type, target_id):
    """Règles d'un nouveau signalement : pas de signalement de sa propre cible, un seul signalement
    ouvert par (auteur, cible). Garantie en couche service, sans contrainte conditionnelle."""
    if resolve_target_author(target_type, target_id) == reporter.pk:
        raise ReportRefused("Vous ne pouvez pas signaler votre propre contenu ou votre propre compte.")
    if Report.objects.filter(
        reporter=reporter, target_type=target_type, target_id=target_id, status__in=Report.OPEN_STATUSES,
    ).exists():
        raise ReportRefused("Vous avez déjà signalé cet élément ; le signalement est en cours de traitement.", True)


# Types de cible produits par les signalements automatiques (avis croisés, CDC 3.7) ; chacun
# doit avoir un résolveur dans TARGET_RESOLVERS (test), sinon le signalement serait illisible.
AUTOMATIC_TARGET_TYPES = frozenset({'review'})


def record_audit(actor, action, target=None, details=''):
    """Journalise une action sensible (règle 12) dans l'AuditLog. Synchrone, sans outbox :
    une action sensible ne doit jamais exister sans sa trace (ADR 0002, notes R1)."""
    return AuditLog.record(actor, action, target=target, details=details)


# Motif des signalements automatiques d'avis croisés (CDC 3.7), exposé sans importer le modèle.
REASON_CROSSED_REVIEWS = Report.REASON_AVIS_CROISES


def resolve_target_labels(target_type, target_ids) -> dict:
    """Libellés des cibles d'un même type, indexés par UUID ; une cible introuvable est absente.
    Un type inconnu renvoie un dictionnaire vide."""
    module = TARGET_RESOLVERS.get(target_type)
    if module is None:
        return {}
    return import_module(module).get_report_labels(target_ids)


def resolve_target(target_type, target_id):
    """(UUID canonique, libellé) de la cible, ou None si le type est inconnu, l'identifiant mal
    formé ou la cible inexistante. La forme canonique regroupe les écritures d'un même UUID."""
    parsed = parse_uuid(target_id)
    if parsed is None:
        return None
    label = resolve_target_labels(target_type, [parsed]).get(parsed)
    return None if label is None else (parsed, label)


def resolve_labels_for_reports(reports) -> dict:
    """Libellés de la cible de chaque signalement, `{(target_type, target_id): libellé}`,
    en une requête par type de cible."""
    ids_by_type = {}
    for report in reports:
        ids_by_type.setdefault(report.target_type, set()).add(report.target_id)
    labels = {}
    for target_type, ids in ids_by_type.items():
        for target_id, label in resolve_target_labels(target_type, ids).items():
            labels[(target_type, target_id)] = label
    return labels


def file_automatic_report(target, reason, description=''):
    """Dépose dans la file de modération un signalement émis par le système (sans auteur).
    Un seul signalement par cible et par motif : renvoie None s'il existe déjà."""
    target_type = target._meta.model_name
    if target_type not in AUTOMATIC_TARGET_TYPES:
        raise ValueError(f"Type de cible non pris en charge pour un signalement automatique : {target_type}")
    if Report.objects.filter(target_type=target_type, target_id=target.pk, reason=reason).exists():
        return None
    return Report.objects.create(
        target_type=target_type, target_id=target.pk, reporter=None, reason=reason, description=description,
    )


def has_open_report(target) -> bool:
    """Vrai si la cible fait l'objet d'un signalement non clos (en attente ou pris en charge)."""
    return Report.objects.filter(
        target_type=target._meta.model_name, target_id=target.pk,
        status__in=(Report.STATUS_EN_ATTENTE, Report.STATUS_EN_COURS),
    ).exists()
