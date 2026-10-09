from django.contrib import admin

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
    list_display = ('keyword', 'category', 'added_by', 'created_at')
    search_fields = ('keyword',)
