"""Contrôles de configuration (system checks Django, tag security)."""
from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def check_num_proxies(app_configs, **kwargs):
    """Hors développement, NUM_PROXIES=0 est une erreur de configuration : derrière Nginx,
    tous les clients partageraient l'IP du proxy (throttles par IP inopérants ou injustes).
    Ignoré en développement (DEBUG) et pendant les tests (TESTING)."""
    if settings.DEBUG or getattr(settings, 'TESTING', False):
        return []
    if settings.REST_FRAMEWORK.get('NUM_PROXIES', 0) == 0:
        return [Error(
            "NUM_PROXIES vaut 0 alors que DEBUG est désactivé.",
            hint=(
                "Derrière Nginx, définir NUM_PROXIES=1 (et BEHIND_PROXY=True) dans l'environnement, avec "
                "`proxy_set_header X-Forwarded-For $remote_addr;`. Sans proxy devant l'application, "
                "utiliser DEBUG=True uniquement en développement."
            ),
            id='common.E001',
        )]
    return []
