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
import math
import time

from django.core.cache import cache
from rest_framework.exceptions import Throttled
from rest_framework.throttling import SimpleRateThrottle

from .identifiers import normalize_phone


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
    """Demandes de code OTP : 3/h par couple (numéro, IP). Toutes les demandes comptent, car
    chacune coûte un SMS. Par couple, pour qu'un tiers ne puisse pas épuiser le quota horaire
    de la victime depuis d'autres adresses."""

    scope = 'otp_phone'
    field = 'phone'

    def get_value(self, request):
        value = super().get_value(request)
        return normalize_phone(value) if value else None

    def get_cache_key(self, request, view):
        value = self.get_value(request)
        if value is None:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': f"{value}|{self.get_ident(request)}"}


class OtpRequestPhoneDailyThrottle(OtpRequestPhoneThrottle):
    """Demandes de code OTP : plafond journalier par numéro seul, toutes adresses confondues
    (borne le coût SMS total d'un numéro). Risque assumé : un tiers peut épuiser ce plafond
    pour une victime (voir ADR 0002)."""

    scope = 'otp_phone_day'

    def get_cache_key(self, request, view):
        value = self.get_value(request)
        if value is None:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': value}


class RegisterIpThrottle(IpThrottle):
    """Inscription : par adresse IP (freine l'énumération des e-mails, voir l'ADR 0002)."""

    scope = 'register'


class ProfileWriteThrottle(UserWriteThrottle):
    """Écritures du profil (PATCH /me/) : par utilisateur et par IP."""

    scope = 'profile_write'


class ProfileWriteIpThrottle(IpThrottle):
    """Écritures du profil : par IP, pour qu'un lot de comptes jetables ne contourne pas la limite."""

    scope = 'profile_write_ip'

    def allow_request(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return super().allow_request(request, view)


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


class LogoutIpThrottle(IpThrottle):
    """Déconnexion (publique) : scope distinct, par adresse IP."""

    scope = 'logout'


class ChangePasswordThrottle(UserWriteThrottle):
    """Changement de mot de passe : par utilisateur."""

    scope = 'change_password'


class KycWriteThrottle(UserWriteThrottle):
    """Dépôt et suppression de pièces KYC : par utilisateur."""

    scope = 'kyc_write'


class ContactSettingsThrottle(UserWriteThrottle):
    """Écritures des réglages de contact vendeur (numéro, code, canaux) : par utilisateur."""

    scope = 'contact_settings'


class ProviderWriteThrottle(UserWriteThrottle):
    """Activation, modification et archivage du profil prestataire : par utilisateur."""

    scope = 'provider_write'


class OrganizationCreateThrottle(UserWriteThrottle):
    """Création d'organisation : 5/jour par compte (anti-abus, ADR 0006, 9.2)."""

    scope = 'org_create'


class OrganizationListThrottle(IpThrottle):
    """Liste publique des organisations (recherche, filtres) : par adresse IP, anonymes compris."""

    scope = 'org_list'


class OrganizationWriteThrottle(UserWriteThrottle):
    """Modification, archivage et sortie d'une organisation : 30/h par compte (ADR 0006, 9.2)."""

    scope = 'org_write'


class ContextsListThrottle(SimpleRateThrottle):
    """Lecture de la liste des contextes (appelée à chaque chargement du front) : par utilisateur."""

    scope = 'contexts'

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {'scope': self.scope, 'ident': request.user.pk}


class FailureLimiter:
    """Compteur d'ÉCHECS par clé (couple identifiant+IP), avec délai croissant.

    Au-delà de `threshold` échecs, les tentatives sont refusées (429) pendant un délai qui
    double à chaque palier de `threshold` échecs supplémentaires (base_delay, 2x, 4x...,
    plafonné à max_delay), mesuré depuis le dernier échec. Un succès efface le compteur ;
    les compteurs expirent seuls après `window` secondes.

    Seul le couple (identifiant, IP) est limité : un tiers qui martèle un compte depuis
    d'autres adresses ne bloque pas son titulaire. Contrepartie : un bourrage réparti sur de
    très nombreuses IP n'est freiné que par le throttle par IP (voir l'ADR 0002).

    Le compteur s'incrémente de façon atomique (cache.add puis cache.incr). Le cache de
    production doit être partagé entre processus.
    """

    def __init__(self, name, threshold=5, base_delay=15 * 60, max_delay=24 * 3600, window=24 * 3600):
        self.name = name
        self.threshold = threshold
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.window = window

    def _keys(self, key):
        base = f"fail:{self.name}:{key}"
        return base, f"{base}:last"

    def delay_for(self, count):
        steps = max(0, (count - self.threshold) // self.threshold)
        return min(self.base_delay * (2 ** steps), self.max_delay)

    def check(self, key):
        """Lève Throttled (429, Retry-After) si le délai en cours n'est pas écoulé."""
        count_key, last_key = self._keys(key)
        count = cache.get(count_key, 0)
        if count < self.threshold:
            return
        last = cache.get(last_key)
        if last is None:
            return
        remaining = last + self.delay_for(count) - time.time()
        if remaining > 0:
            raise Throttled(wait=max(1, math.ceil(remaining)))

    def failure(self, key):
        count_key, last_key = self._keys(key)
        if not cache.add(count_key, 1, self.window):
            try:
                cache.incr(count_key)
            except ValueError:  # expiré entre add et incr
                cache.add(count_key, 1, self.window)
        cache.set(last_key, time.time(), self.window)

    def success(self, key):
        cache.delete_many(self._keys(key))
