"""Limitation de débit des points d'entrée sensibles (OTP, connexion).

Les compteurs vivent dans le cache Django ; les taux sont lus dans
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] (réglables sans toucher au code).
"""
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class PerValueThrottle(SimpleRateThrottle):
    """Limite par valeur d'un champ du corps de la requête (numéro, identifiant...),
    en plus de la limite par adresse IP. Sans valeur exploitable : pas de limite
    ici (la vue renverra sa propre erreur de validation)."""

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


class OtpRequestIpThrottle(AnonRateThrottle):
    """Demandes de code OTP : par adresse IP."""

    scope = 'otp'


class OtpRequestPhoneThrottle(PerValueThrottle):
    """Demandes de code OTP : par numéro de téléphone (coût SMS, harcèlement)."""

    scope = 'otp_phone'
    field = 'phone'


class OtpConfirmIpThrottle(AnonRateThrottle):
    """Confirmation de réinitialisation du mot de passe : par adresse IP."""

    scope = 'otp_confirm'


class OtpConfirmPhoneThrottle(PerValueThrottle):
    """Confirmation de réinitialisation du mot de passe : par numéro."""

    scope = 'otp_confirm_phone'
    field = 'phone'


class LoginIpThrottle(AnonRateThrottle):
    scope = 'login'


class LoginIdentifierThrottle(PerValueThrottle):
    """Connexion : par identifiant (e-mail), contre le bourrage d'identifiants."""

    scope = 'login_identifier'
    field = 'email'


class LoginPhoneThrottle(PerValueThrottle):
    scope = 'login_phone'
    field = 'phone'
