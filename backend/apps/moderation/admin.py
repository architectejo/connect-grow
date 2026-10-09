from django import forms
from django.contrib import admin
from django.db import transaction

from apps.common.admin_mixins import SingletonSettingsAdminMixin

from . import services
from .models import AuditLog, ModerationSettings, Report, ReportClosedError, Sanction

# Transitions permises depuis l'admin (comme par l'API : un signalement clos ne se rouvre pas).
ALLOWED_TRANSITIONS = {
    Report.STATUS_EN_ATTENTE: {Report.STATUS_EN_COURS, Report.STATUS_TRAITE, Report.STATUS_REJETE},
    Report.STATUS_EN_COURS: {Report.STATUS_TRAITE, Report.STATUS_REJETE},
    Report.STATUS_TRAITE: set(),
    Report.STATUS_REJETE: set(),
}


class ReportAdminForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['status', 'assigned_to', 'decision_notes']

    def clean_status(self):
        new = self.cleaned_data['status']
        old = Report.objects.filter(pk=self.instance.pk).values_list('status', flat=True).first()
        if old is not None and new != old and new not in ALLOWED_TRANSITIONS[old]:
            raise forms.ValidationError("Ce changement de statut n'est pas permis : un signalement clos ne se rouvre pas.")
        return new


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    form = ReportAdminForm
    list_display = ('id', 'target_type', 'target_id', 'reason', 'status', 'assigned_to', 'created_at')
    list_filter = ('status', 'reason', 'target_type')
    search_fields = ('description', 'decision_notes')
    # Le signalement lui-même est une pièce : seuls statut, affectation et notes de décision se modifient.
    readonly_fields = (
        'reason', 'target_type', 'target_id', 'reporter', 'description', 'resolved_at',
        'author_response', 'author_responded_at',
    )

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        """Un changement de statut suit les mêmes transitions et les mêmes conséquences que par l'API
        (un contact fictif retenu masque l'avis, l'auteur est informé) et reste journalisé (règle 12)."""
        if not change or 'status' not in form.changed_data:
            super().save_model(request, obj, form, change)
            return
        new_status, notes = obj.status, obj.decision_notes
        original = Report.objects.get(pk=obj.pk)
        with transaction.atomic():
            obj.status, obj.resolved_at = original.status, original.resolved_at
            super().save_model(request, obj, form, change)  # affectation et notes
            try:
                if new_status == Report.STATUS_TRAITE:
                    obj.resolve(notes=notes)
                elif new_status == Report.STATUS_REJETE:
                    obj.reject(notes=notes)
                else:
                    obj.claim(obj.assigned_to or request.user)
            except ReportClosedError:
                transaction.set_rollback(True)  # ni notes ni affectation n'écrasent la décision déjà prise
                self.message_user(request, "Ce signalement a été clos entre-temps : statut inchangé.", level='error')
                return
            services.record_audit(request.user, 'REPORT_STATUS_CHANGED', target=obj, details=obj.status)
            services.apply_decision(obj, request.user)


@admin.register(ModerationSettings)
class ModerationSettingsAdmin(SingletonSettingsAdminMixin, admin.ModelAdmin):
    list_display = ('report_processing_target_hours', 'fictitious_contact_daily_limit')


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
