from django.apps import AppConfig


class ModerationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.moderation'
    label = 'moderation'

    def ready(self):
        from . import events  # noqa: F401  (enregistre les abonnés aux événements)
