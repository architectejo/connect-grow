"""Permissions de la modération : droits Django portés par les groupes Modérateur et Administrateur
(`setup_roles`), jamais le seul indicateur `is_staff`. Refus par défaut."""
from rest_framework import permissions

VIEW_REPORT = 'moderation.view_report'
CHANGE_REPORT = 'moderation.change_report'
VIEW_SANCTION = 'moderation.view_sanction'
ADD_SANCTION = 'moderation.add_sanction'


def is_administrator(user):
    return bool(user and user.is_authenticated and (
        user.is_superuser or user.groups.filter(name='Administrateur').exists()
    ))


def can_moderate(user):
    """Vrai pour le personnel de modération (droit de consulter la file de signalements)."""
    return bool(user and user.is_authenticated and user.is_active and user.has_perm(VIEW_REPORT))


class HasModerationPermission(permissions.BasePermission):
    """La vue déclare `required_permissions = {action: 'app.codename'}` ; une action absente
    de la table est refusée."""

    message = "Vous n'avez pas le droit d'effectuer cette action de modération."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        required = getattr(view, 'required_permissions', {}).get(getattr(view, 'action', None))
        return bool(required) and user.has_perm(required)
