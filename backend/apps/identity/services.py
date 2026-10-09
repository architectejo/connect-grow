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
