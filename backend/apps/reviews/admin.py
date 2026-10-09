from django.contrib import admin
from django.db import transaction

from apps.common.admin_mixins import SingletonSettingsAdminMixin
from apps.moderation.services import record_audit

from . import services
from .models import Review, ReviewSettings


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    # Un avis masqué par la modération (is_hidden) sort de toutes les moyennes ; le drapeau
    # « dernière note vendeur » est recalculé à l'enregistrement (services.reconcile_seller_flag).
    list_display = (
        'offer_id', 'user', 'offer_rating', 'seller_rating', 'contact_channel', 'is_hidden', 'created_at',
    )
    list_filter = ('is_hidden', 'contact_channel', 'offer_rating', 'seller_rating')
    search_fields = ('user__email', 'user__phone', 'content')
    # Preuve de contact et drapeau calculé : jamais modifiables à la main (la modération les consulte).
    ALWAYS_READONLY = (
        'user', 'offer_id', 'seller_context_type', 'seller_context_id',
        'contact_event_id', 'contact_channel', 'contact_recorded_at', 'counts_for_seller', 'edited_at',
    )

    def has_add_permission(self, request):
        # Un avis naît d'une prise de contact (API) : pas de création à la main.
        return False

    def get_readonly_fields(self, request, obj=None):
        # Le modérateur (droit `change_review`) masque ou réaffiche un avis ; seul le
        # super-administrateur peut en réécrire le contenu ou les notes.
        if request.user.is_superuser:
            return self.ALWAYS_READONLY
        return tuple(f.name for f in Review._meta.fields if f.name != 'is_hidden')

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            hidden_changed = change and 'is_hidden' in form.changed_data
            super().save_model(request, obj, form, change)
            services.reconcile_seller_flag(obj.user_id, obj.seller_context_type, obj.seller_context_id)
            changes = '; '.join(
                f"{name} : {form.initial.get(name)!r} -> {getattr(obj, name, None)!r}" for name in form.changed_data
            )
            record_audit(request.user, 'REVIEW_ADMIN_UPDATED', target=obj, details=changes)
            if hidden_changed:
                record_audit(request.user, 'REVIEW_HIDDEN' if obj.is_hidden else 'REVIEW_UNHIDDEN', target=obj)

    def delete_model(self, request, obj):
        with transaction.atomic():
            record_audit(request.user, 'REVIEW_ADMIN_DELETED', target=obj)
            super().delete_model(request, obj)
            services.reconcile_seller_flag(obj.user_id, obj.seller_context_type, obj.seller_context_id)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            reviews = list(queryset)
            for review in reviews:
                record_audit(request.user, 'REVIEW_ADMIN_DELETED', target=review)
            super().delete_queryset(request, queryset)
            for pair in {(r.user_id, r.seller_context_type, r.seller_context_id) for r in reviews}:
                services.reconcile_seller_flag(*pair)


@admin.register(ReviewSettings)
class ReviewSettingsAdmin(SingletonSettingsAdminMixin, admin.ModelAdmin):
    list_display = (
        'min_reviews_to_display', 'daily_review_limit', 'edit_window_hours', 'delay_after_contact_hours',
        'crossed_reviews_window_days', 'crossed_reviews_threshold',
    )
