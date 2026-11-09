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
    list_display = (
        'title', 'offer_type', 'status', 'price', 'currency', 'seller_context_type', 'seller_context_id',
        'seller_is_public', 'is_deleted', 'expires_at',
    )
    list_filter = ('offer_type', 'status', 'currency', 'is_deleted', 'seller_context_type', 'seller_is_public')
    search_fields = ('title', 'description')
    # Le propriétaire d'une offre ne se change pas depuis l'administration (ADR 0006) ; la visibilité du vendeur
    # est recalculée depuis `identity`.
    readonly_fields = ('seller_context_type', 'seller_context_id', 'created_by', 'seller_is_public')
    inlines = [OfferImageInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        record_audit(request.user, 'OFFER_ADMIN_UPDATED' if change else 'OFFER_ADMIN_CREATED', target=obj,
                     details=f"Champs : {', '.join(form.changed_data)}")

    def delete_model(self, request, obj):
        record_audit(
            request.user, 'OFFER_DELETED', target=obj, details='offer deleted',
            context=(obj.seller_context_type, obj.seller_context_id) if obj.seller_context_type else None,
        )
        services.delete_offers(Offer.objects.filter(pk=obj.pk))

    def delete_queryset(self, request, queryset):
        for offer in queryset:
            record_audit(
                request.user, 'OFFER_DELETED', target=offer, details='offer deleted',
                context=(offer.seller_context_type, offer.seller_context_id) if offer.seller_context_type else None,
            )
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
        'reveal_abuse_threshold', 'reveal_abuse_window_days', 'exchange_enabled',
    )
