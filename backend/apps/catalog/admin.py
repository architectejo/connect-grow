from django.contrib import admin

from apps.moderation.services import record_audit

from .models import Category, City, Commune, ForbiddenItem


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ('name', 'city')
    list_filter = ('city',)
    search_fields = ('name',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon')
    prepopulated_fields = {'slug': ('name',)}  # Génère le slug automatiquement


@admin.register(ForbiddenItem)
class ForbiddenItemAdmin(admin.ModelAdmin):
    """Le référentiel des produits interdits est sensible : toute modification est journalisée."""

    list_display = ('keyword', 'category', 'added_by', 'created_at')
    search_fields = ('keyword',)
    readonly_fields = ('added_by',)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.added_by = request.user
        super().save_model(request, obj, form, change)
        record_audit(
            request.user, 'FORBIDDEN_ITEM_UPDATED' if change else 'FORBIDDEN_ITEM_CREATED',
            target=obj, details=obj.keyword,
        )

    def delete_model(self, request, obj):
        record_audit(request.user, 'FORBIDDEN_ITEM_DELETED', target=obj, details=obj.keyword)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            record_audit(request.user, 'FORBIDDEN_ITEM_DELETED', target=obj, details=obj.keyword)
        super().delete_queryset(request, queryset)
