"""Back-office de l'outbox : lecture seule, avec relance journalisée (règle 12).

La charge utile n'est volontairement pas affichée : elle peut contenir des données
personnelles (texte d'un message de contact).
"""
from django.contrib import admin, messages

from .models import OutboxDelivery, OutboxEvent
from .operations import requeue_and_audit


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_requeue_permission(self, request):
        return request.user.has_perm('platform_core.change_outboxdelivery')


@admin.register(OutboxEvent)
class OutboxEventAdmin(ReadOnlyAdmin):
    list_display = ('event_type', 'version', 'status', 'aggregate_type', 'created_at', 'completed_at')
    list_filter = ('status', 'event_type')
    exclude = ('payload',)
    actions = ['requeue_dead']

    @admin.action(description="Relancer les livraisons en échec des événements sélectionnés",
                  permissions=['requeue'])
    def requeue_dead(self, request, queryset):
        deliveries = OutboxDelivery.objects.filter(event__in=queryset, status=OutboxDelivery.DEAD)
        count = requeue_and_audit(request.user, deliveries)
        self.message_user(request, f"{count} livraison(s) relancée(s).", messages.SUCCESS)


@admin.register(OutboxDelivery)
class OutboxDeliveryAdmin(ReadOnlyAdmin):
    list_display = ('handler', 'status', 'attempts', 'next_attempt_at', 'processed_at', 'created_at')
    list_filter = ('status', 'handler')
    raw_id_fields = ('event',)
    actions = ['requeue_selected']

    @admin.action(description="Relancer les livraisons sélectionnées", permissions=['requeue'])
    def requeue_selected(self, request, queryset):
        count = requeue_and_audit(request.user, queryset.select_related('event'))
        self.message_user(request, f"{count} livraison(s) relancée(s).", messages.SUCCESS)
