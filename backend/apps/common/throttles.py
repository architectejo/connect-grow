"""Limites de débit des écritures (taux dans REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']).

`ScopedRateThrottle` compte par utilisateur connecté, ou par IP pour un anonyme. Les vues
déclarent `throttle_scopes = {action: scope}` via `ActionScopedThrottleMixin`. Les dépassements
renvoient 429 avec l'en-tête `Retry-After`."""
from rest_framework.throttling import ScopedRateThrottle


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


class AnonymousScopedThrottle(ScopedRateThrottle):
    """Comme ScopedRateThrottle, mais ne limite que les requêtes anonymes (par IP)."""

    def allow_request(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        return super().allow_request(request, view)
