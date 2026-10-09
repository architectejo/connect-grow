import json
from unittest import mock
import tempfile
import uuid
from io import StringIO
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.identity.models import User

from . import services
from .models import Category, City, Commune, ForbiddenItem


class CatalogModelTests(TestCase):
    def test_primary_keys_are_uuid_with_timestamps(self):
        city = City.objects.create(name='Kinshasa')
        self.assertIsInstance(city.id, uuid.UUID)
        self.assertIsNotNone(city.created_at)
        self.assertIsNotNone(city.updated_at)

    def test_slug_generated_from_name(self):
        self.assertEqual(Category.objects.create(name='Électronique').slug, 'electronique')
        self.assertEqual(City.objects.create(name='Lubumbashi').slug, 'lubumbashi')


class CatalogServicesTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name='Kinshasa')
        self.gombe = Commune.objects.create(city=self.city, name='Gombe')
        self.limete = Commune.objects.create(city=self.city, name='Limete')
        self.category = Category.objects.create(name='Électronique', slug='electronique')

    def test_get_categories_by_ids_uses_one_query(self):
        other = Category.objects.create(name='Mode', slug='mode')
        with self.assertNumQueries(1):
            result = services.get_categories_by_ids([self.category.id, str(other.id), 'pas-un-uuid'])
        self.assertEqual({self.category.id, other.id}, set(result))
        self.assertEqual(result[self.category.id].name, 'Électronique')

    def test_get_communes_by_ids_returns_city_name_in_one_query(self):
        with self.assertNumQueries(1):
            result = services.get_communes_by_ids([self.gombe.id, self.limete.id])
        self.assertEqual(result[self.gombe.id].city_name, 'Kinshasa')

    def test_commune_ids_for_city_and_search(self):
        self.assertEqual(set(services.get_commune_ids_for_city(self.city.id)), {self.gombe.id, self.limete.id})
        self.assertEqual(services.get_commune_ids_for_city('invalide'), [])
        self.assertEqual(services.search_commune_ids('gomb'), [self.gombe.id])
        self.assertEqual(len(services.search_commune_ids('kinsha')), 2)

    def test_exists_helpers_reject_invalid_ids(self):
        self.assertTrue(services.category_exists(self.category.id))
        self.assertFalse(services.category_exists(uuid.uuid4()))
        self.assertFalse(services.category_exists('abc'))
        self.assertFalse(services.commune_exists(None))
        self.assertTrue(services.city_exists(str(self.city.id)))
        self.assertEqual(services.existing_category_ids([self.category.id, uuid.uuid4()]), {self.category.id})

    def test_slug_lookup(self):
        self.assertEqual(services.get_category_id_by_slug('electronique'), self.category.id)
        self.assertIsNone(services.get_category_id_by_slug('inconnu'))
        self.assertEqual(services.get_city_id_by_slug('kinshasa'), self.city.id)

    def test_forbidden_keywords_are_case_insensitive(self):
        ForbiddenItem.objects.create(keyword='Arme à Feu')
        self.assertEqual(services.find_forbidden_keywords("Vends ARME À FEU neuve"), ['arme à feu'])
        self.assertEqual(services.find_forbidden_keywords("Vends téléphone"), [])


class CatalogApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=self.city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')

    def test_public_referentials_keep_url_and_json_keys(self):
        response = self.client.get('/api/marketplace/cities/')
        self.assertEqual(response.status_code, 200)
        city = response.data[0] if isinstance(response.data, list) else response.data['results'][0]
        self.assertEqual(set(city), {'id', 'name', 'communes'})
        self.assertEqual(city['id'], str(self.city.id))
        self.assertEqual(set(city['communes'][0]), {'id', 'name', 'city'})

        response = self.client.get('/api/marketplace/categories/')
        self.assertEqual(set(response.data[0]), {'id', 'name', 'icon', 'slug'})
        self.assertEqual(self.client.get('/api/marketplace/communes/').status_code, 200)

    def test_forbidden_items_read_public_write_admin_only(self):
        ForbiddenItem.objects.create(keyword='médicament')
        self.assertEqual(self.client.get('/api/moderation/forbidden-items/').status_code, 200)

        user = User.objects.create_user(email='u@example.com', password='x', full_name='U')
        self.client.force_authenticate(user)
        denied = self.client.post('/api/moderation/forbidden-items/', {'keyword': 'poison'})
        self.assertEqual(denied.status_code, 403)

        admin = User.objects.create_user(email='a@example.com', password='x', full_name='A', is_staff=True)
        self.client.force_authenticate(admin)
        created = self.client.post('/api/moderation/forbidden-items/', {'keyword': 'poison'})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(ForbiddenItem.objects.get(keyword='poison').added_by_id, admin.id)

    def test_forbidden_item_invalid_data(self):
        admin = User.objects.create_user(email='a@example.com', password='x', full_name='A', is_staff=True)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.post('/api/moderation/forbidden-items/', {}).status_code, 400)


class SeedCatalogTests(TestCase):
    def run_seed(self, *args):
        call_command('seed_catalog', *args, stdout=StringIO())

    def test_seed_is_idempotent_and_loads_default_file(self):
        self.run_seed()
        counts = (City.objects.count(), Commune.objects.count(), Category.objects.count(), ForbiddenItem.objects.count())
        self.assertGreaterEqual(counts[0], 1)
        self.assertGreaterEqual(counts[1], 24)
        self.assertGreaterEqual(counts[2], 1)
        self.run_seed()
        self.assertEqual(
            counts,
            (City.objects.count(), Commune.objects.count(), Category.objects.count(), ForbiddenItem.objects.count()),
        )

    def test_seed_reads_values_from_given_file_and_keeps_existing_data(self):
        Category.objects.create(name='Mode (modifiée)', slug='mode')
        data = {
            'cities': [{'name': 'Goma', 'communes': ['Karisimbi']}],
            'categories': [{'name': 'Mode', 'slug': 'mode', 'icon': 'shirt'}, {'name': 'Santé', 'icon': 'heart'}],
            'forbidden_items': [{'keyword': 'Poison'}, {'keyword': 'poison'}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'seed.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            self.run_seed('--file', str(path))
        self.assertTrue(Commune.objects.filter(city__name='Goma', name='Karisimbi').exists())
        self.assertEqual(Category.objects.get(slug='mode').name, 'Mode (modifiée)')
        self.assertTrue(Category.objects.filter(slug='sante').exists())
        self.assertEqual(ForbiddenItem.objects.count(), 1)

    def test_seed_unreadable_file(self):
        with self.assertRaises(CommandError):
            self.run_seed('--file', 'introuvable.json')


class DomainIsolationTests(TestCase):
    """ADR 0002 / CDC §5.4 : aucune clé étrangère entre domaines, sauf vers l'utilisateur."""

    def test_identity_and_catalog_only_reference_themselves_or_the_user(self):
        user_label = settings.AUTH_USER_MODEL.lower()
        for app_label in ('identity', 'catalog'):
            for model in django_apps.get_app_config(app_label).get_models():
                for field in model._meta.get_fields():
                    if not (field.is_relation and field.concrete):
                        continue
                    target = field.related_model._meta
                    allowed = target.app_label in (app_label, 'auth') or target.label_lower == user_label
                    self.assertTrue(allowed, f"{model._meta.label}.{field.name} -> {target.label}")

    def test_all_domain_models_use_uuid_primary_keys(self):
        for app_label in ('identity', 'catalog'):
            for model in django_apps.get_app_config(app_label).get_models():
                self.assertEqual(model._meta.pk.get_internal_type(), 'UUIDField', model)


class CaseInsensitiveUniquenessTests(TestCase):
    def test_city_commune_category_and_keyword_reject_case_variants(self):
        from django.core.exceptions import ValidationError

        city = City.objects.create(name='Kinshasa')
        with self.assertRaises(ValidationError) as ctx:
            City(name='  KINSHASA ').full_clean()
        self.assertIn('name', ctx.exception.message_dict)

        Commune.objects.create(city=city, name='Gombe')
        with self.assertRaises(ValidationError):
            Commune(city=city, name='gombe').full_clean()
        # Même nom dans une autre ville : autorisé.
        other = City.objects.create(name='Matadi')
        Commune(city=other, name='GOMBE').full_clean()

        Category.objects.create(name='Électronique')
        with self.assertRaises(ValidationError):
            Category(name='ÉLECTRONIQUE').full_clean()

        ForbiddenItem.objects.create(keyword='Arme à feu')
        with self.assertRaises(ValidationError):
            ForbiddenItem(keyword='ARME À  FEU').full_clean()

    def test_database_enforces_the_normalized_key_too(self):
        from django.db import IntegrityError, transaction

        City.objects.create(name='Goma')
        with self.assertRaises(IntegrityError), transaction.atomic():
            City.objects.create(name='GOMA')

    def test_name_is_stored_trimmed(self):
        self.assertEqual(City.objects.create(name='  Bukavu  ').name, 'Bukavu')

    def test_forbidden_item_api_rejects_case_duplicate_with_400(self):
        ForbiddenItem.objects.create(keyword='Poison')
        admin = User.objects.create_user(email='a@example.com', password='x', full_name='A', is_staff=True)
        client = APIClient()
        client.force_authenticate(admin)
        response = client.post('/api/moderation/forbidden-items/', {'keyword': 'POISON'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('keyword', response.data)

    def test_seed_does_not_duplicate_case_variants(self):
        City.objects.create(name='KINSHASA')
        Category.objects.create(name='ÉLECTRONIQUE', slug='electronique-2')
        ForbiddenItem.objects.create(keyword='MÉDICAMENT')
        call_command('seed_catalog', stdout=StringIO())
        self.assertEqual(City.objects.filter(name_key='kinshasa').count(), 1)
        self.assertEqual(Category.objects.filter(name_key='électronique').count(), 1)
        self.assertEqual(ForbiddenItem.objects.filter(keyword_key='médicament').count(), 1)


class SlugFallbackTests(TestCase):
    def test_empty_slugify_result_gets_a_unique_fallback(self):
        first = City.objects.create(name='???')
        second = City.objects.create(name='!!!')
        self.assertTrue(first.slug.startswith('sans-nom-'))
        self.assertNotEqual(first.slug, second.slug)

    def test_slug_collision_gets_a_suffix_instead_of_failing(self):
        first = Category.objects.create(name='Électronique')
        second = Category.objects.create(name='Electronique')
        self.assertEqual(first.slug, 'electronique')
        self.assertTrue(second.slug.startswith('electronique-'))
        self.assertNotEqual(first.slug, second.slug)


class CommuneIdCapTests(TestCase):
    def test_commune_id_lists_are_capped(self):
        city = City.objects.create(name='Grande ville')
        for i in range(5):
            Commune.objects.create(city=city, name=f'Commune {i}')
        with mock.patch.object(services, 'MAX_COMMUNE_IDS', 3):
            self.assertEqual(len(services.get_commune_ids_for_city(city.id)), 3)
            self.assertEqual(len(services.search_commune_ids('Commune')), 3)


class ForbiddenItemAuditTests(TestCase):
    def setUp(self):
        from apps.moderation.models import AuditLog

        self.AuditLog = AuditLog
        self.admin = User.objects.create_user(email='a@example.com', password='x', full_name='A', is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_create_update_delete_are_audited(self):
        created = self.client.post('/api/moderation/forbidden-items/', {'keyword': 'poison'})
        self.assertEqual(created.status_code, 201)
        item_id = created.data['id']
        updated = self.client.patch(f'/api/moderation/forbidden-items/{item_id}/', {'keyword': 'poison fort'})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.client.delete(f'/api/moderation/forbidden-items/{item_id}/').status_code, 204)
        actions = list(self.AuditLog.objects.filter(actor=self.admin).order_by('created_at').values_list('action', flat=True))
        self.assertEqual(actions, ['FORBIDDEN_ITEM_CREATED', 'FORBIDDEN_ITEM_UPDATED', 'FORBIDDEN_ITEM_DELETED'])

    def test_admin_site_changes_are_audited(self):
        from django.contrib import admin as django_admin
        from django.test import RequestFactory

        from .admin import ForbiddenItemAdmin

        model_admin = ForbiddenItemAdmin(ForbiddenItem, django_admin.site)
        request = RequestFactory().post('/')
        request.user = self.admin
        item = ForbiddenItem(keyword='explosif')
        model_admin.save_model(request, item, form=None, change=False)
        model_admin.delete_model(request, item)
        actions = list(self.AuditLog.objects.filter(actor=self.admin).order_by('created_at').values_list('action', flat=True))
        self.assertEqual(actions, ['FORBIDDEN_ITEM_CREATED', 'FORBIDDEN_ITEM_DELETED'])
        self.assertEqual(item.added_by, self.admin)
