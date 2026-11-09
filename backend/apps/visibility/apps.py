from django.apps import AppConfig


class VisibilityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.visibility'
    label = 'visibility'

    def ready(self):
        from . import events  # noqa: F401  (enregistre les abonnés aux événements)
