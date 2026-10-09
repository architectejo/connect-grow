from django.contrib import admin

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


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'offer', 'created_at')
    search_fields = ('user__email', 'user__phone', 'offer__title')
    raw_id_fields = ('user', 'offer')


@admin.register(MarketplaceSettings)
class MarketplaceSettingsAdmin(admin.ModelAdmin):
    list_display = ('expiration_days', 'trash_retention_days', 'expiring_soon_warning_days')

    def has_add_permission(self, request):
        return not MarketplaceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
