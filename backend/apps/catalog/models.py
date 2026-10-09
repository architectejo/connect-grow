"""Référentiels configurables du back-office (règle 11 : jamais codés en dur).

Villes, communes, catégories et liste des produits interdits. Les autres
domaines référencent ces entités par UUID (`city_id`, `commune_id`,
`category_id`) et passent par `apps.catalog.services`.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from apps.common.models import BaseModel


def normalize_key(value: str) -> str:
    """Clé de comparaison : espaces superflus retirés et casse neutralisée (casefold).
    Traitée en Python, pas par la base : SQLite et MySQL ne comparent pas la casse
    de la même façon (et SQLite ignore la casse hors ASCII)."""
    return ' '.join((value or '').split()).casefold()


class NormalizedKeyMixin(models.Model):
    """Unicité insensible à la casse, explicite et portable SQLite/MySQL.

    Pour chaque champ listé dans `KEY_FIELDS` ({'name': 'name_key'}), `save()` calcule
    la clé normalisée stockée dans une colonne dédiée (unique, éventuellement dans la
    portée `KEY_SCOPE`), et `clean()` renvoie une erreur de formulaire lisible avant
    que la base ne la refuse (le champ clé est non éditable, donc ignoré par les
    formulaires)."""

    KEY_FIELDS: dict = {}
    KEY_SCOPE: tuple = ()

    class Meta:
        abstract = True

    def _compute_keys(self):
        for source, key in self.KEY_FIELDS.items():
            cleaned = ' '.join((getattr(self, source) or '').split())
            setattr(self, source, cleaned)
            setattr(self, key, normalize_key(cleaned))

    def clean(self):
        super().clean()
        self._compute_keys()
        for source, key in self.KEY_FIELDS.items():
            duplicates = type(self).objects.filter(**{key: getattr(self, key)})
            for scope_field in self.KEY_SCOPE:
                duplicates = duplicates.filter(**{scope_field: getattr(self, scope_field)})
            if duplicates.exclude(pk=self.pk).exists():
                raise ValidationError({source: "Une entrée portant ce nom existe déjà (la casse n'est pas prise en compte)."})

    def save(self, *args, **kwargs):
        self._compute_keys()
        super().save(*args, **kwargs)


class SlugMixin(models.Model):
    """Génère le slug à partir du nom s'il est vide. Le slug (ASCII, minuscules) sert
    d'identifiant lisible stable ; il n'est PAS la garantie d'unicité insensible à la
    casse (c'est le rôle de NormalizedKeyMixin). S'il est déjà pris, ou si le nom ne
    donne rien de lisible (« ??? », idéogrammes), un suffixe tiré de l'UUID le rend
    unique plutôt que de provoquer une erreur d'intégrité."""

    class Meta:
        abstract = True

    def _build_slug(self):
        base = slugify(self.name)[:90] or 'sans-nom'
        taken = type(self).objects.filter(slug=base).exclude(pk=self.pk).exists()
        return f"{base}-{self.id.hex[:8]}" if taken or base == 'sans-nom' else base

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._build_slug()
        super().save(*args, **kwargs)


class City(NormalizedKeyMixin, SlugMixin, BaseModel):
    KEY_FIELDS = {'name': 'name_key'}

    name = models.CharField(max_length=100, unique=True)
    name_key = models.CharField(max_length=100, unique=True, editable=False)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        verbose_name = "Ville"
        verbose_name_plural = "Villes"
        ordering = ['name']

    def __str__(self):
        return self.name


class Commune(NormalizedKeyMixin, BaseModel):
    KEY_FIELDS = {'name': 'name_key'}
    KEY_SCOPE = ('city_id',)

    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='communes')
    name = models.CharField(max_length=100)
    name_key = models.CharField(max_length=100, editable=False)

    class Meta:
        unique_together = ('city', 'name_key')
        verbose_name = "Commune"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.city.name})"


class Category(NormalizedKeyMixin, SlugMixin, BaseModel):
    KEY_FIELDS = {'name': 'name_key'}

    name = models.CharField(max_length=100, unique=True)
    name_key = models.CharField(max_length=100, unique=True, editable=False)
    icon = models.CharField(max_length=50, help_text="Nom de l'icône Lucide (ex: shopping-bag)", blank=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        verbose_name = "Catégorie"
        ordering = ['name']

    def __str__(self):
        return self.name


class ForbiddenItem(NormalizedKeyMixin, BaseModel):
    """CDC 2.1 / 3.11 : liste des produits et services interdits, référentiel
    consulté par la modération (médicaments, armes, contrefaçons...)."""

    KEY_FIELDS = {'keyword': 'keyword_key'}

    keyword = models.CharField(max_length=100, unique=True)
    keyword_key = models.CharField(max_length=100, unique=True, editable=False)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='forbidden_items',
    )
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['keyword']

    def __str__(self):
        return self.keyword
