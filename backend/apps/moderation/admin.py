from django.contrib import admin
from django.db import transaction

from . import services
from .models import AuditLog, Report, Sanction


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('id', 'target_type', 'target_id', 'reason', 'status', 'assigned_to', 'created_at')
    list_filter = ('status', 'reason', 'target_type')
    search_fields = ('description', 'decision_notes')

    def save_model(self, request, obj, form, change):
        """Un signalement passé à « Traité » depuis l'admin a les mêmes conséquences que par l'API
        (un contact fictif retenu masque l'avis) et reste journalisé (règle 12)."""
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if change and 'status' in form.changed_data:
                services.record_audit(request.user, 'REPORT_STATUS_CHANGED', target=obj, details=obj.status)
                if obj.status == Report.STATUS_TRAITE:
                    services.apply_resolution(obj, request.user)


@admin.register(Sanction)
class SanctionAdmin(admin.ModelAdmin):
    list_display = ('user', 'sanction_type', 'is_active', 'issued_by', 'starts_at', 'ends_at')
    list_filter = ('sanction_type', 'is_active')
    search_fields = ('user__email', 'user__phone', 'reason')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'target_type', 'target_id')
    list_filter = ('action', 'target_type')
    search_fields = ('actor__email', 'details')
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
