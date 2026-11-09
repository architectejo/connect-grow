from django.apps import AppConfig


class IdentityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.identity'
    label = 'identity'

    def ready(self):
        from . import signals  # noqa: F401  (purge des contextes à la suppression d'un compte, T9-3)
