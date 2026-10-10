"""Briques d'administration communes aux domaines."""


class SingletonSettingsAdminMixin:
    """Réglages à ligne unique : ni ajout en double, ni suppression ; chaque modification est
    journalisée dans l'`AuditLog` avec l'ancienne et la nouvelle valeur (règles 11 et 12).

    `on_settings_changed(request, obj, changed)` est appelé après l'enregistrement, dans la
    transaction de l'admin : un domaine y publie un événement de domaine si nécessaire."""

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        changed = list(form.changed_data)
        if not changed:
            return
        from apps.moderation.services import record_settings_change

        old = {name: form.initial.get(name) for name in changed}
        new = {name: getattr(obj, name, None) for name in changed}
        record_settings_change(request.user, obj, old, new)
        self.on_settings_changed(request, obj, changed)

    def on_settings_changed(self, request, obj, changed):
        """Point d'extension : rien par défaut."""
