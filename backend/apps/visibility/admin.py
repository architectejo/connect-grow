from django.contrib import admin

from .models import RankingSettings, VisibilitySettings


@admin.register(RankingSettings)
class RankingSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'weight_views', 'weight_likes', 'weight_comments', 'weight_shares',
        'trust_factor_min', 'trust_factor_max', 'recency_half_life_hours',
    )

    def has_add_permission(self, request):
        # Ligne unique de paramètres.
        return not RankingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VisibilitySettings)
class VisibilitySettingsAdmin(admin.ModelAdmin):
    list_display = ('unique_view_retention_days',)

    def has_add_permission(self, request):
        return not VisibilitySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
