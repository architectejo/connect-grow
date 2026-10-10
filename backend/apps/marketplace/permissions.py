from rest_framework.permissions import BasePermission

from . import services

# Capacité requise sur le contexte PROPRIÉTAIRE de l'offre, par action de la vue (ADR 0006, 5 et 6.4).
OBJECT_CAPABILITIES = {
    'update': services.CAP_EDIT, 'partial_update': services.CAP_EDIT,
    'pause': services.CAP_EDIT, 'unpause': services.CAP_EDIT, 'mark_sold': services.CAP_EDIT,
    'renew': services.CAP_EDIT, 'images': services.CAP_EDIT, 'delete_image': services.CAP_EDIT,
    'destroy': services.CAP_DELETE, 'soft_delete': services.CAP_DELETE, 'restore': services.CAP_DELETE,
    'hard_delete': services.CAP_DELETE,
}


class HasOfferCapability(BasePermission):
    """Autorise une action sur une offre existante d'après le contexte propriétaire de l'offre et le rôle réel
    de l'utilisateur ; l'en-tête `X-Context` est ignoré (ADR 0006, 6.4). Refus : 403 `DENY_*`."""

    message = "Action non autorisée"

    def has_object_permission(self, request, view, obj):
        view.authorize_object(obj.seller_context_type, obj.seller_context_id, OBJECT_CAPABILITIES[view.action])
        return True
