from django.contrib import admin

from .models import Deal, Review, TrustScoreSettings


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    # CDC 3.7 : un avis retiré par la modération (is_hidden) sort du calcul du Trust Score —
    # cocher/décocher ici déclenche le recalcul (apps.reviews.signals).
    list_display = ('offer_id', 'user', 'reviewed_user', 'rating', 'is_hidden', 'created_at')
    list_filter = ('is_hidden', 'rating')
    search_fields = ('user__email', 'user__phone', 'content')
    raw_id_fields = ('user', 'reviewed_user', 'deal')


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
