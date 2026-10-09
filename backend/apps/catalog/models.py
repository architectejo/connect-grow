"""Référentiels configurables du back-office (règle 11 : jamais codés en dur).

Villes, communes, catégories et liste des produits interdits. Les autres
domaines référencent ces entités par UUID (`city_id`, `commune_id`,
`category_id`) et passent par `apps.catalog.services`.
"""
from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.common.models import BaseModel


class SlugMixin(models.Model):
    """Génère le slug à partir du nom s'il est vide. L'unicité du slug (en
    minuscules, donc insensible à la casse) évite les doublons « Kinshasa » /
    « kinshasa » quelle que soit la base (SQLite sensible à la casse, MySQL non)."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:100]
        super().save(*args, **kwargs)


class City(SlugMixin, BaseModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        verbose_name = "Ville"
        verbose_name_plural = "Villes"
        ordering = ['name']

    def __str__(self):
        return self.name


class Commune(BaseModel):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='communes')
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ('city', 'name')
        verbose_name = "Commune"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.city.name})"


class Category(SlugMixin, BaseModel):
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, help_text="Nom de l'icône Lucide (ex: shopping-bag)", blank=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        verbose_name = "Catégorie"
        ordering = ['name']

    def __str__(self):
        return self.name


class ForbiddenItem(BaseModel):
    """CDC 2.1 / 3.11 : liste des produits et services interdits, référentiel
    consulté par la modération (médicaments, armes, contrefaçons...)."""

    keyword = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='forbidden_items',
    )
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['keyword']

    def __str__(self):
        return self.keyword
