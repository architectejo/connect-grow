from django.contrib import admin

from apps.common.admin_mixins import SingletonSettingsAdminMixin
from apps.moderation.services import record_audit

from . import services
from .models import ContactEvent, ExchangeProposal, Favorite, MarketplaceSettings, Offer, OfferImage


class OfferImageInline(admin.TabularInline):
    model = OfferImage
    extra = 0


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('title', 'offer_type', 'status', 'price', 'currency', 'seller', 'is_deleted', 'expires_at')
    list_filter = ('offer_type', 'status', 'currency', 'is_deleted')
    search_fields = ('title', 'description')
    raw_id_fields = ('seller',)
    inlines = [OfferImageInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        record_audit(request.user, 'OFFER_ADMIN_UPDATED' if change else 'OFFER_ADMIN_CREATED', target=obj,
                     details=f"Champs : {', '.join(form.changed_data)}")

    def delete_model(self, request, obj):
        record_audit(request.user, 'OFFER_DELETED', target=obj, details=obj.title)
        services.delete_offers(Offer.objects.filter(pk=obj.pk))

    def delete_queryset(self, request, queryset):
        for offer in queryset:
            record_audit(request.user, 'OFFER_DELETED', target=offer, details=offer.title)
        services.delete_offers(queryset)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'offer', 'created_at')
    search_fields = ('user__email', 'user__phone', 'offer__title')
    raw_id_fields = ('user', 'offer')


@admin.register(MarketplaceSettings)
class MarketplaceSettingsAdmin(SingletonSettingsAdminMixin, admin.ModelAdmin):
    list_display = (
        'expiration_days', 'trash_retention_days', 'expiring_soon_warning_days', 'duplicate_contact_window_hours',
        'reveal_daily_limit_account', 'reveal_daily_limit_new_account', 'new_account_hours',
    )
