"""Données de départ du catalogue : villes, communes, catégories, produits interdits.

Les valeurs sont lues dans un fichier JSON (par défaut
`apps/catalog/seed/initial_catalog.json`, ou `--file` pour un autre), jamais
codées dans la logique : ce sont des valeurs de départ, ensuite modifiables dans
le back-office (règle 11). La commande est idempotente : elle crée ce qui
manque et ne modifie ni ne supprime rien d'existant.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from apps.catalog.models import Category, City, Commune, ForbiddenItem, normalize_key

DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'seed' / 'initial_catalog.json'


class Command(BaseCommand):
    help = "Crée les villes, communes, catégories et produits interdits de départ (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DEFAULT_FILE), help="Fichier JSON des données de départ.")

    def handle(self, *args, **options):
        path = Path(options['file'])
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise CommandError(f"Impossible de lire {path} : {exc}")

        created = {'cities': 0, 'communes': 0, 'categories': 0, 'forbidden_items': 0}

        for city_data in data.get('cities', []):
            city = City.objects.filter(name_key=normalize_key(city_data['name'])).first()
            if city is None:
                city = City.objects.create(name=city_data['name'])
                created['cities'] += 1
            for commune_name in city_data.get('communes', []):
                if not Commune.objects.filter(city=city, name_key=normalize_key(commune_name)).exists():
                    Commune.objects.create(city=city, name=commune_name)
                    created['communes'] += 1

        for category_data in data.get('categories', []):
            slug = category_data.get('slug') or slugify(category_data['name'])
            already = Category.objects.filter(slug=slug) | Category.objects.filter(
                name_key=normalize_key(category_data['name'])
            )
            if not already.exists():
                Category.objects.create(
                    name=category_data['name'], slug=slug, icon=category_data.get('icon', ''),
                )
                created['categories'] += 1

        existing_keywords = set(ForbiddenItem.objects.values_list('keyword_key', flat=True))
        for item_data in data.get('forbidden_items', []):
            keyword = item_data['keyword']
            if normalize_key(keyword) in existing_keywords:
                continue
            category = None
            if item_data.get('category_slug'):
                category = Category.objects.filter(slug=item_data['category_slug']).first()
            ForbiddenItem.objects.create(keyword=keyword, category=category)
            existing_keywords.add(normalize_key(keyword))
            created['forbidden_items'] += 1

        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(
                "Catalogue de départ : {cities} ville(s), {communes} commune(s), "
                "{categories} catégorie(s), {forbidden_items} produit(s) interdit(s) créé(s).".format(**created)
            ))
