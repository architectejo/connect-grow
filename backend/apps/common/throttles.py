"""Limites de débit des écritures (taux dans REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']).

`ScopedRateThrottle` compte par utilisateur connecté, ou par IP pour un anonyme. Les vues
déclarent `throttle_scopes = {action: scope}` via `ActionScopedThrottleMixin`. Les dépassements
renvoient 429 avec l'en-tête `Retry-After`."""
import ipaddress

from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class ActionScopedThrottleMixin:
    """Ajoute le throttle de portée associé à l'action courante (en plus des throttles par défaut)."""

    throttle_scopes: dict = {}

    def get_throttles(self):
        throttles = super().get_throttles()
        entry = self.throttle_scopes.get(getattr(self, 'action', None))
        if entry:
            scope, throttle_class = entry if isinstance(entry, tuple) else (entry, ScopedRateThrottle)
            self.throttle_scope = scope
            throttles.append(throttle_class())
        return throttles


class AnonymousOrUserScopedThrottle(ScopedRateThrottle):
    """Comme ScopedRateThrottle (clé : utilisateur connecté, sinon adresse IP), nommé pour les
    lectures publiques coûteuses : la limite s'applique à tous, par IP pour les anonymes."""


class AnonymousScopedThrottle(ScopedRateThrottle):
    """Comme ScopedRateThrottle, mais ne limite que les requêtes anonymes (par IP)."""

    def allow_request(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        return super().allow_request(request, view)


def normalize_ip(ident):
    """Clé de limitation d'une adresse : IPv4 telle quelle ; IPv6 réduite à son préfixe /64 (un
    abonné reçoit au moins un /64 : sans cela, il change d'adresse à volonté pour contourner la limite)."""
    try:
        address = ipaddress.ip_address(ident)
    except ValueError:
        return ident
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


class _RevealThrottle(SimpleRateThrottle):
    """Révélation de numéro : ne compte que les POST ; chaque tentative compte (refusée ou non).
    Les compteurs vivent dans le cache et expirent seuls : aucune adresse IP n'est persistée
    (ADR 0005, C9)."""

    code = 'throttled'

    def allow_request(self, request, view):
        if request.method != 'POST':
            return True
        return super().allow_request(request, view)


class RevealIpThrottle(_RevealThrottle):
    """30/h par adresse IP (lue selon NUM_PROXIES), connectée ou non."""

    scope = 'contact_reveal_ip'
    code = 'reveal_quota_ip'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': normalize_ip(self.get_ident(request))}


class RevealUserThrottle(_RevealThrottle):
    """Filet technique contre les rafales, par utilisateur (les vrais plafonds métier sont en base)."""

    scope = 'contact_reveal_user'

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {'scope': self.scope, 'ident': request.user.pk}
