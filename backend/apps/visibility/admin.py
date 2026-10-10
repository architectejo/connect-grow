from django.contrib import admin

from apps.common.admin_mixins import SingletonSettingsAdminMixin
from apps.platform_core.services import publish_event

from .models import RankingSettings, VisibilitySettings


@admin.register(RankingSettings)
class RankingSettingsAdmin(SingletonSettingsAdminMixin, admin.ModelAdmin):
    list_display = (
        'weight_views', 'weight_favorites', 'weight_contacts', 'weight_shares',
        'recency_half_life_hours', 'proximity_same_commune', 'proximity_same_city', 'proximity_default',
    )

    def on_settings_changed(self, request, obj, changed):
        # Publié dans la transaction de l'admin : les scores sont recalculés à la diffusion.
        publish_event(
            'visibility.ranking_settings_changed', aggregate_type='rankingsettings', aggregate_id=obj.pk,
            payload={'changed': changed},
        )


@admin.register(VisibilitySettings)
class VisibilitySettingsAdmin(SingletonSettingsAdminMixin, admin.ModelAdmin):
    list_display = ('unique_view_retention_days',)
