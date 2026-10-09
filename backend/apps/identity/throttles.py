"""Limitation de débit des points d'entrée sensibles (OTP, connexion, jetons).

Deux mécanismes, tous deux adossés au cache Django (taux réglables dans
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], plafonds d'échecs dans les vues) :

- les throttles DRF « tout compter » (`IpThrottle`, `PerValueThrottle`, ...) ;
- le compteur d'ÉCHECS (`FailureLimiter`) pour la connexion et la confirmation de
  reset : seuls les échecs comptent, un succès remet à zéro, et un tiers ne peut
  pas verrouiller durablement le compte d'une victime depuis d'autres adresses.

Le cache de production devra être partagé entre processus (LocMem est par
processus : voir l'ADR 0002).
"""
import time

from django.core.cache import cache
from rest_framework.exceptions import Throttled
from rest_framework.throttling import SimpleRateThrottle


class IpThrottle(SimpleRateThrottle):
    """Limite par adresse IP, que la requête soit authentifiée ou non (contrairement à
    AnonRateThrottle, qui ignore les requêtes authentifiées : un compte jetable
    contournerait la limite). L'IP vient de `get_ident`, donc de NUM_PROXIES."""

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class PerValueThrottle(SimpleRateThrottle):
    """Limite par valeur d'un champ du corps de la requête (numéro, identifiant...).
    Sans valeur exploitable : pas de limite ici (la vue renverra sa propre erreur)."""

    field = None

    def get_value(self, request):
        value = request.data.get(self.field) if hasattr(request.data, 'get') else None
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
        return None

    def get_cache_key(self, request, view):
        value = self.get_value(request)
        if value is None:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': value}


class UserWriteThrottle(SimpleRateThrottle):
    """Limite par utilisateur connecté, sur les seules méthodes qui modifient."""

    def allow_request(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {'scope': self.scope, 'ident': request.user.pk}


class OtpRequestIpThrottle(IpThrottle):
    """Demandes de code OTP : par adresse IP."""

    scope = 'otp'


class OtpRequestPhoneThrottle(PerValueThrottle):
    """Demandes de code OTP : par numéro de téléphone (coût SMS, harcèlement). Toutes les
    demandes comptent, puisque chacune coûte un SMS."""

    scope = 'otp_phone'
    field = 'phone'


class OtpConfirmIpThrottle(IpThrottle):
    """Confirmation de réinitialisation du mot de passe : par adresse IP."""

    scope = 'otp_confirm'


class LoginIpThrottle(IpThrottle):
    """Connexion : par adresse IP (toutes requêtes). Les échecs par identifiant sont
    comptés à part par FailureLimiter."""

    scope = 'login'


class RefreshIpThrottle(IpThrottle):
    """Renouvellement de jeton : scope distinct, par adresse IP."""

    scope = 'refresh'


class ChangePasswordThrottle(UserWriteThrottle):
    """Changement de mot de passe : par utilisateur."""

    scope = 'change_password'


class KycWriteThrottle(UserWriteThrottle):
    """Dépôt et suppression de pièces KYC : par utilisateur."""

    scope = 'kyc_write'


class FailureLimiter:
    """Compteur d'échecs à fenêtre fixe, par clé. Deux niveaux typiques :

    - plafond serré par couple (identifiant, IP) : freine le bourrage depuis une adresse ;
    - plafond large par identifiant seul (journalier) : freine la distribution sur de
      nombreuses adresses sans permettre de verrouiller la victime avec quelques requêtes.

    Un succès efface les compteurs. Le blocage expire avec la fenêtre (jamais définitif).
    """

    def __init__(self, name, limits):
        # limits : liste de (clé de `parts`, échecs maximaux, durée de la fenêtre en secondes)
        self.name = name
        self.limits = limits

    def _keys(self, parts):
        return [f"fail:{self.name}:{part}:{parts[part]}" for part, _, _ in self.limits]

    def check(self, parts):
        """Lève Throttled (429) si un des plafonds est atteint."""
        now = time.time()
        for (_, maximum, _), key in zip(self.limits, self._keys(parts)):
            state = cache.get(key)
            if state and state['count'] >= maximum and state['expires'] > now:
                raise Throttled(wait=max(1, int(state['expires'] - now)))

    def failure(self, parts):
        now = time.time()
        for (_, _, window), key in zip(self.limits, self._keys(parts)):
            state = cache.get(key)
            if not state or state['expires'] <= now:
                state = {'count': 0, 'expires': now + window}
            state['count'] += 1
            cache.set(key, state, max(1, int(state['expires'] - now)))

    def success(self, parts):
        cache.delete_many(self._keys(parts))
