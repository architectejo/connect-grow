"""Interface publique du domaine `identity` (sessions et jetons)."""
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


def revoke_all_sessions(user) -> int:
    """Révoque tous les refresh tokens en cours de `user` (déconnexion de tous les
    appareils, changement ou réinitialisation de mot de passe). Renvoie le nombre
    de jetons révoqués. Les jetons d'accès déjà émis expirent d'eux-mêmes (15 min)."""
    revoked = 0
    for token in OutstandingToken.objects.filter(user=user).exclude(blacklistedtoken__isnull=False):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        revoked += created
    return revoked


def validate_new_password(password, user=None) -> None:
    """Applique les validateurs de mot de passe de Django (AUTH_PASSWORD_VALIDATORS).
    Lève rest_framework.serializers.ValidationError (liste de messages en français).
    Refuse aussi un mot de passe absent ou vide."""
    from django.contrib.auth import password_validation
    from django.core.exceptions import ValidationError as DjangoValidationError
    from rest_framework import serializers

    if not isinstance(password, str) or not password.strip():
        raise serializers.ValidationError(["Le mot de passe est requis."])
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
