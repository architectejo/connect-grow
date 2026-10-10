from rest_framework.permissions import BasePermission

REVIEW_KYC_PERMISSION = 'identity.review_kycdocument'


class CanReviewKyc(BasePermission):
    """Accès aux pièces KYC réservé aux comptes qui détiennent la permission dédiée
    `identity.review_kycdocument` (groupes Modérateur et Administrateur, ou
    super-administrateur) : être `is_staff` ne suffit pas (données d'identité)."""

    message = "Vous n'avez pas le droit d'examiner les pièces de vérification."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.has_perm(REVIEW_KYC_PERMISSION))
