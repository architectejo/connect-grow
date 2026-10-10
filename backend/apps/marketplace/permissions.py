from rest_framework.permissions import BasePermission


class IsOfferOwner(BasePermission):
    """Seul le vendeur d'une offre la modifie, la supprime ou gère son cycle de vie."""

    message = "Action non autorisée"

    def has_object_permission(self, request, view, obj):
        return obj.seller_id == request.user.id
