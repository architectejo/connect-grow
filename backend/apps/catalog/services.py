"""Interface publique du domaine `catalog`.

Les autres domaines ne lisent jamais les modèles de `catalog` : ils passent par
ces fonctions, qui renvoient des structures immuables et offrent des variantes
par lot (`*_by_ids`) pour éviter les requêtes N+1 là où une jointure ORM
existait avant le découplage (ADR 0002).
"""
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

from django.db.models import Q

from apps.common.utils import parse_uuid

from .models import Category, City, Commune, ForbiddenItem


@dataclass(frozen=True)
class CityInfo:
    id: uuid.UUID
    name: str
    slug: str


@dataclass(frozen=True)
class CommuneInfo:
    id: uuid.UUID
    name: str
    city_id: uuid.UUID
    city_name: str


@dataclass(frozen=True)
class CategoryInfo:
    id: uuid.UUID
    name: str
    slug: str
    icon: str


def _valid_ids(ids: Iterable) -> set:
    return {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}


def _city_info(city: City) -> CityInfo:
    return CityInfo(id=city.id, name=city.name, slug=city.slug)


def _commune_info(commune: Commune) -> CommuneInfo:
    return CommuneInfo(id=commune.id, name=commune.name, city_id=commune.city_id, city_name=commune.city.name)


def _category_info(category: Category) -> CategoryInfo:
    return CategoryInfo(id=category.id, name=category.name, slug=category.slug, icon=category.icon)


# --- Villes ---------------------------------------------------------------

def get_cities_by_ids(ids: Iterable) -> dict:
    """Villes indexées par UUID, en une requête."""
    wanted = _valid_ids(ids)
    if not wanted:
        return {}
    return {c.id: _city_info(c) for c in City.objects.filter(id__in=wanted)}


def city_exists(city_id) -> bool:
    parsed = parse_uuid(city_id)
    return parsed is not None and City.objects.filter(id=parsed).exists()


def get_city_id_by_slug(slug: str) -> Optional[uuid.UUID]:
    return City.objects.filter(slug=slug).values_list('id', flat=True).first()


# --- Communes -------------------------------------------------------------

def get_communes_by_ids(ids: Iterable) -> dict:
    """Communes (avec nom de la ville) indexées par UUID, en une requête."""
    wanted = _valid_ids(ids)
    if not wanted:
        return {}
    return {c.id: _commune_info(c) for c in Commune.objects.select_related('city').filter(id__in=wanted)}


def commune_exists(commune_id) -> bool:
    parsed = parse_uuid(commune_id)
    return parsed is not None and Commune.objects.filter(id=parsed).exists()


def get_commune_ids_for_city(city_id) -> list:
    """UUID des communes d'une ville (remplace le filtre `commune__city`)."""
    parsed = parse_uuid(city_id)
    if parsed is None:
        return []
    return list(Commune.objects.filter(city_id=parsed).values_list('id', flat=True))


def search_commune_ids(text: str) -> list:
    """UUID des communes dont le nom, ou celui de la ville, contient `text`
    (remplace les filtres `commune__name__icontains` et `commune__city__name__icontains`)."""
    return list(
        Commune.objects.filter(Q(name__icontains=text) | Q(city__name__icontains=text))
        .values_list('id', flat=True)
    )


# --- Catégories -----------------------------------------------------------

def get_categories_by_ids(ids: Iterable) -> dict:
    """Catégories indexées par UUID, en une requête."""
    wanted = _valid_ids(ids)
    if not wanted:
        return {}
    return {c.id: _category_info(c) for c in Category.objects.filter(id__in=wanted)}


def category_exists(category_id) -> bool:
    parsed = parse_uuid(category_id)
    return parsed is not None and Category.objects.filter(id=parsed).exists()


def existing_category_ids(ids: Iterable) -> set:
    """Sous-ensemble des UUID qui désignent bien une catégorie."""
    wanted = _valid_ids(ids)
    if not wanted:
        return set()
    return set(Category.objects.filter(id__in=wanted).values_list('id', flat=True))


def get_category_id_by_slug(slug: str) -> Optional[uuid.UUID]:
    return Category.objects.filter(slug=slug).values_list('id', flat=True).first()


# --- Produits interdits ---------------------------------------------------

def get_forbidden_keywords() -> list:
    """Mots-clés interdits en minuscules (la casse est traitée ici, pas par la
    base : SQLite et MySQL ne se comportent pas pareil)."""
    return [k.lower() for k in ForbiddenItem.objects.values_list('keyword', flat=True)]


def find_forbidden_keywords(text: str) -> list:
    """Mots-clés interdits présents dans `text`, sans tenir compte de la casse."""
    haystack = (text or '').lower()
    return [k for k in get_forbidden_keywords() if k in haystack]
