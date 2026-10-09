from django.contrib import admin

from apps.moderation.services import record_audit

from .models import Deal, Review, TrustScoreSettings


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    # CDC 3.7 : un avis retiré par la modération (is_hidden) sort du calcul du Trust Score —
    # cocher/décocher ici déclenche le recalcul (apps.reviews.signals).
    list_display = ('offer_id', 'user', 'reviewed_user', 'rating', 'is_hidden', 'created_at')
    list_filter = ('is_hidden', 'rating')
    search_fields = ('user__email', 'user__phone', 'content')
    raw_id_fields = ('user', 'reviewed_user', 'deal')

    def save_model(self, request, obj, form, change):
        hidden_changed = change and 'is_hidden' in form.changed_data
        super().save_model(request, obj, form, change)
        record_audit(request.user, 'REVIEW_ADMIN_UPDATED' if change else 'REVIEW_ADMIN_CREATED', target=obj,
                     details=f"Champs : {', '.join(form.changed_data)}")
        if hidden_changed:
            record_audit(request.user, 'REVIEW_HIDDEN' if obj.is_hidden else 'REVIEW_UNHIDDEN', target=obj)

    def delete_model(self, request, obj):
        record_audit(request.user, 'REVIEW_ADMIN_DELETED', target=obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for review in queryset:
            record_audit(request.user, 'REVIEW_ADMIN_DELETED', target=review)
        super().delete_queryset(request, queryset)


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ('offer_id', 'initiator', 'counterparty', 'status', 'created_at', 'confirmed_at')
    list_filter = ('status',)
    raw_id_fields = ('initiator', 'counterparty')


@admin.register(TrustScoreSettings)
class TrustScoreSettingsAdmin(admin.ModelAdmin):
    list_display = ('neutral_rating', 'neutral_weight', 'min_reviews_to_display')

    def has_add_permission(self, request):
        return not TrustScoreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
