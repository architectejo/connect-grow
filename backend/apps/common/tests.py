import os
import re
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import Resolver404, URLResolver, get_resolver, resolve
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from apps.common import boundaries

# Routes (méthode, gabarit d'URL) volontairement publiques : tout le reste doit refuser un
# anonyme. Une vue qui devient publique par erreur (AllowAny ajouté) OU privée par erreur
# (AllowAny oublié avec le refus par défaut) fait échouer test_every_route_..., qui parcourt
# TOUTES les routes via get_resolver().
EXPECTED_PUBLIC = {
    ('get', 'api/v1/schema/'),  # schéma OpenAPI : structure seule, aucune donnée (ADR 0007)
    ('get', 'api/v1/marketplace/cities/'),
    ('get', 'api/v1/marketplace/cities/<pk>/'),
    ('get', 'api/v1/marketplace/communes/'),
    ('get', 'api/v1/marketplace/communes/<pk>/'),
    ('get', 'api/v1/marketplace/categories/'),
    ('get', 'api/v1/marketplace/categories/<pk>/'),
    ('get', 'api/v1/marketplace/posts/'),
    ('get', 'api/v1/marketplace/posts/<pk>/'),
    ('get', 'api/v1/marketplace/sellers/<context_type>/<context_id>/'),  # profil public d'un vendeur (ADR 0006, 9.7)
    ('get', 'api/v1/moderation/forbidden-items/'),
    ('get', 'api/v1/moderation/forbidden-items/<pk>/'),
    ('get', 'api/v1/interactions/reviews/'),
    ('get', 'api/v1/interactions/reviews/<pk>/'),
    ('get', 'api/v1/accounts/organizations/'),  # liste publique minimale des organisations (L0-09g)
    ('post', 'api/v1/accounts/register/'),
    ('post', 'api/v1/accounts/login/'),
    ('post', 'api/v1/accounts/token/refresh/'),
    ('get', 'api/v1/config/features/'),  # fonctionnalités activables, sans donnée personnelle (L0-14)
    ('post', 'api/v1/accounts/logout/'),  # public : le refresh du corps prouve la session (L0-19)
    ('post', 'api/v1/accounts/otp/request/'),
    ('post', 'api/v1/accounts/password-reset/confirm/'),
}

# Routes qui doivent figurer dans le parcours (garde contre un parcours qui raterait des vues).
MUST_BE_WALKED = {
    'api/v1/accounts/kyc/documents/<pk>/decision/',
    'api/v1/accounts/kyc/documents/<pk>/download/',
    'api/v1/accounts/organizations/',
    'api/v1/accounts/organizations/limits/',
    'api/v1/accounts/organizations/<pk>/',
    'api/v1/accounts/organizations/<pk>/internal/',
    'api/v1/accounts/organizations/<pk>/archive/',
    'api/v1/accounts/organizations/<pk>/leave/',
    'api/v1/marketplace/posts/<pk>/pause/',
    'api/v1/marketplace/posts/<pk>/soft_delete/',
    'api/v1/marketplace/posts/<pk>/favorite/',
    'api/v1/marketplace/posts/recalculate_all_scores/',
    'api/v1/marketplace/posts/trash/',
    'api/v1/moderation/reports/<pk>/claim/',
    'api/v1/marketplace/posts/<pk>/images/',
    'api/v1/marketplace/posts/<pk>/hard_delete/',
    'api/v1/marketplace/favorites/',
    'api/v1/marketplace/stats/dashboard/',
    'api/v1/marketplace/stats/post/<pk>/',
    'api/v1/interactions/reviews/<pk>/reply/',
    'api/v1/interactions/reviews/eligibility/',
    'api/v1/interactions/contacts/',
    'api/v1/interactions/exchanges/',
    'api/v1/interactions/conversations/',
    'api/v1/interactions/messages/',
    'api/v1/interactions/notifications/',
    'api/v1/interactions/notifications/mark_all_as_read/',
}

SAMPLE_VALUES = ('1', '8f0f5a52-3c6e-4a49-9d44-0d8a3d5f1c11')


def walk_routes(patterns=None, prefix=''):
    """(gabarit, callback) de toutes les routes, sans l'admin ni les suffixes de format."""
    patterns = get_resolver().url_patterns if patterns is None else patterns
    for entry in patterns:
        text = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from walk_routes(entry.url_patterns, text)
            continue
        template = text.replace('^', '').replace('$', '').replace('\\Z', '')
        template = re.sub(r'\(\?P<(\w+)>[^)]*\)', r'<\1>', template)
        template = re.sub(r'<\w+:(\w+)>', r'<\1>', template)
        if 'format' in template or template.startswith(('admin/', 'static/')):
            continue
        yield template, entry.callback


def concrete_url(template, callback):
    """URL réelle : paramètres remplacés par la valeur d'exemple qui résout vers cette vue."""
    for sample in SAMPLE_VALUES:
        url = '/' + re.sub(r'<\w+>', sample, template)
        try:
            if resolve(url).func is callback:
                return url
        except Resolver404:
            continue
    raise AssertionError(f"Aucune URL d'exemple ne résout {template}")


def allowed_methods(callback):
    actions = getattr(callback, 'actions', None)
    if actions:  # ViewSet : méthode HTTP -> action (HEAD est ajouté par DRF à la première requête : ignoré)
        return {method: action for method, action in actions.items() if method != 'head'}
    view_class = callback.cls
    return {m: None for m in view_class.http_method_names if m not in ('options', 'head') and hasattr(view_class, m)}


def declares_allow_any(callback, action):
    view = callback.cls(**getattr(callback, 'initkwargs', {}))
    view.action = action
    view.request = None
    return any(isinstance(permission, AllowAny) for permission in view.get_permissions())


class PermissionDefaultsTests(TestCase):
    def test_default_permission_is_authenticated(self):
        self.assertEqual(
            settings.REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'], ['rest_framework.permissions.IsAuthenticated'],
        )

    def test_every_route_refuses_anonymous_unless_explicitly_public(self):
        client = APIClient(raise_request_exception=False)
        walked, public_seen = set(), set()
        for template, callback in walk_routes():
            walked.add(template)
            url = concrete_url(template, callback)
            for method, action in allowed_methods(callback).items():
                response = getattr(client, method)(url, {}, format='json')
                label = f"{method.upper()} {template}"
                if declares_allow_any(callback, action):
                    public_seen.add((method, template))
                    self.assertIn((method, template), EXPECTED_PUBLIC, f"{label} est public sans être attendu")
                    self.assertNotIn(response.status_code, (401, 403), f"{label} est devenu privé")
                else:
                    self.assertIn(response.status_code, (401, 403), f"{label} accepte un anonyme ({response.status_code})")
        self.assertEqual(EXPECTED_PUBLIC - public_seen, set(), "Routes publiques attendues introuvables")
        self.assertEqual(MUST_BE_WALKED - walked, set(), "Routes absentes du parcours")
        self.assertGreater(len(walked), 60)


# Tous les domaines (ADR 0002, R3) : aucun n'échappe au contrôle de découplage. Un nouveau module
# doit être ajouté ici ; `test_every_installed_domain_is_covered` le rappelle.
ALL_DOMAINS = {'catalog', 'identity', 'marketplace', 'visibility', 'reviews', 'messaging', 'notifications',
               'moderation', 'payments', 'platform_core'}
DECOUPLED_APPS = tuple(sorted(ALL_DOMAINS))
APPS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DomainBoundariesTests(SimpleTestCase):
    def test_every_installed_domain_is_covered(self):
        from django.apps import apps as django_apps

        installed = {c.label for c in django_apps.get_app_configs() if c.name.startswith('apps.')} - {'common'}
        self.assertEqual(installed, ALL_DOMAINS)

    def test_no_foreign_key_leaves_its_domain_except_towards_the_user(self):
        from django.apps import apps as django_apps
        from django.contrib.contenttypes.fields import GenericForeignKey

        for label in DECOUPLED_APPS:
            for model in django_apps.get_app_config(label).get_models():
                for field in model._meta.get_fields():
                    self.assertNotIn(
                        type(field), (GenericForeignKey,), f'{label}.{model.__name__}.{field.name} : clé générique',
                    )
                    if (field.is_relation and (field.concrete or field.many_to_many) and not field.auto_created
                            and field.related_model is not None):
                        target = field.related_model._meta.app_label
                        if target == label or target == 'auth':
                            continue
                        is_user = target == 'identity' and field.related_model._meta.model_name == 'user'
                        self.assertTrue(is_user, f'{label}.{model.__name__}.{field.name} -> {target}')

    def test_no_migration_depends_on_another_domain_except_identity(self):
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(None, ignore_no_migrations=True)
        offenders = []
        for (label, name), migration in loader.disk_migrations.items():
            if label not in ALL_DOMAINS:
                continue
            for dep_label, dep_name in migration.dependencies:
                if dep_label in ALL_DOMAINS and dep_label != label and dep_label != 'identity':
                    # Exception A11 (ADR 0006, section 20) : la conversion `identity 0011` lit `moderation.Sanction`
                    # (lecture seule, via `apps.get_model`) pour suspendre les organisations de propriétaires sanctionnés.
                    if (label, name, dep_label) == ('identity', '0011_convert_business_profiles', 'moderation'):
                        continue
                    # Contraction T9-2 : `identity 0013` (suppression des profils) attend les gardes de `marketplace`
                    # et `visibility`, qui lisent les profils/organisations tant qu'ils existent.
                    if (label, name) == ('identity', '0013_remove_business_profile') and dep_label in ('marketplace', 'visibility'):
                        continue
                    offenders.append(f'{label}.{name} -> {dep_label}.{dep_name}')
        self.assertEqual(offenders, [])

    def test_no_domain_imports_the_models_of_another_one(self):
        offenders = []
        for label in DECOUPLED_APPS:
            offenders += boundaries.scan_domain(APPS_DIR, label, ALL_DOMAINS)
        self.assertEqual(offenders, [])

    def violations(self, source, label='marketplace', module='views'):
        return boundaries.find_violations(source, label, ['apps', label, module], ALL_DOMAINS)

    def test_analyzer_catches_every_form_of_model_access(self):
        faulty = [
            'from apps.reviews.models import Review',
            'from apps.reviews.models import Review, ReviewSettings as S',
            'from apps.reviews import models',
            'from apps.reviews import services, models as m',
            'import apps.reviews.models',
            'import apps.reviews.models as m',
            'from ..reviews.models import Review',
            'from .. import reviews',
            'from apps import reviews',
            'apps.get_model("reviews.Review")',
            'apps.get_model("reviews", "Review")',
            'import_string("apps.reviews.models.Review")',
            'importlib.import_module("apps.reviews.models")',
        ]
        for source in faulty:
            self.assertTrue(self.violations(source), source)

    def test_analyzer_allows_services_own_models_user_and_shared_code(self):
        fine = [
            'from apps.reviews import services as reviews_services',
            'from apps.reviews.services import notify',
            'from apps.common.models import BaseModel',
            'from apps.marketplace.models import Offer',
            'from .models import Offer',
            'from . import models',
            'from .services import x',
            'from apps.reviews.serializers import ReviewSerializer',
            'apps.get_model("identity.User")',
            'get_user_model()',
        ]
        for source in fine:
            self.assertEqual(self.violations(source), [], source)

    def test_relative_import_that_leaves_the_domain_is_resolved_from_the_file_location(self):
        source = 'from ..reviews.models import Review'
        self.assertTrue(boundaries.find_violations(source, 'marketplace', ['apps', 'marketplace', 'views'], ALL_DOMAINS))
        # Dans un sous-paquet, `..` reste dans le domaine.
        self.assertEqual(
            boundaries.find_violations('from ..models import Offer', 'marketplace',
                                       ['apps', 'marketplace', 'management', 'x'], ALL_DOMAINS), [],
        )

    def test_scanner_reports_a_faulty_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            apps_root = os.path.join(tmp, 'apps')
            os.makedirs(os.path.join(apps_root, 'marketplace', 'sub'))
            with open(os.path.join(apps_root, 'marketplace', 'sub', 'bad.py'), 'w', encoding='utf-8') as handle:
                handle.write('from ...reviews.models import Review' + chr(10))
            with open(os.path.join(apps_root, 'marketplace', 'good.py'), 'w', encoding='utf-8') as handle:
                handle.write('from apps.reviews import services' + chr(10))
            with open(os.path.join(apps_root, 'marketplace', 'tests_x.py'), 'w', encoding='utf-8') as handle:
                handle.write('from apps.reviews.models import Review' + chr(10))
            offenders = boundaries.scan_domain(apps_root, 'marketplace', ALL_DOMAINS)
        self.assertEqual(len(offenders), 1)
        self.assertIn('sub/bad.py', offenders[0])

    def test_domain_models_use_uuid_primary_keys(self):
        from django.apps import apps as django_apps

        for label in DECOUPLED_APPS:
            for model in django_apps.get_app_config(label).get_models():
                self.assertEqual(model._meta.pk.get_internal_type(), 'UUIDField', f'{label}.{model.__name__}')


class SecretKeySettingsTests(SimpleTestCase):
    """SECRET_KEY : aucune valeur de repli hors DEBUG."""

    def import_settings(self, **env):
        base = {k: v for k, v in os.environ.items() if k not in ('SECRET_KEY', 'DEBUG')}
        base.update({'DJANGO_SETTINGS_MODULE': 'backend.settings'}, **env)
        return subprocess.run(
            [sys.executable, '-c', 'import backend.settings as s; print("KEY=" + s.SECRET_KEY)'],
            cwd=str(settings.BASE_DIR), env=base, capture_output=True, text=True, timeout=60,
        )

    def test_missing_secret_key_outside_debug_stops_startup(self):
        for key in ('', 'change-me'):
            result = self.import_settings(SECRET_KEY=key, DEBUG='False')
            self.assertNotEqual(result.returncode, 0, key)
            self.assertIn('ImproperlyConfigured', result.stderr)

    def test_debug_allows_a_development_key(self):
        result = self.import_settings(SECRET_KEY='', DEBUG='True')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('KEY=django-insecure', result.stdout)

    def test_explicit_secret_key_is_used(self):
        result = self.import_settings(SECRET_KEY='une-vraie-cle-secrete-unique', DEBUG='False')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('KEY=une-vraie-cle-secrete-unique', result.stdout)

    def test_proxy_ssl_header_only_when_declared_behind_proxy(self):
        code = 'import backend.settings as s; print(getattr(s, "SECURE_PROXY_SSL_HEADER", None))'
        for flag, expected in (('False', 'None'), ('True', "('HTTP_X_FORWARDED_PROTO', 'https')")):
            env = {k: v for k, v in os.environ.items() if k != 'BEHIND_PROXY'}
            env.update(SECRET_KEY='cle-de-test-unique', DEBUG='False', BEHIND_PROXY=flag,
                       DJANGO_SETTINGS_MODULE='backend.settings')
            result = subprocess.run(
                [sys.executable, '-c', code], cwd=str(settings.BASE_DIR), env=env,
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.stdout.strip(), expected, result.stderr)


class TestSettingsGuardTests(SimpleTestCase):
    def test_settings_test_refuses_to_load_outside_manage_py_test(self):
        env = {k: v for k, v in os.environ.items() if k != 'DJANGO_SETTINGS_MODULE'}
        result = subprocess.run(
            [sys.executable, '-c', 'import backend.settings_test'],
            cwd=str(settings.BASE_DIR), env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ImproperlyConfigured', result.stderr)


class NumProxiesCheckTests(SimpleTestCase):
    def run_check(self, *, debug, testing, num_proxies):
        from django.test import override_settings

        from apps.common.checks import check_num_proxies

        rest = {**settings.REST_FRAMEWORK, 'NUM_PROXIES': num_proxies}
        with override_settings(DEBUG=debug, TESTING=testing, REST_FRAMEWORK=rest):
            return check_num_proxies(None)

    def test_error_when_production_without_proxy_count(self):
        errors = self.run_check(debug=False, testing=False, num_proxies=0)
        self.assertEqual([e.id for e in errors], ['common.E001'])
        self.assertIn('NUM_PROXIES=1', errors[0].hint)

    def test_no_error_in_debug_in_tests_or_with_a_proxy_count(self):
        self.assertEqual(self.run_check(debug=True, testing=False, num_proxies=0), [])
        self.assertEqual(self.run_check(debug=False, testing=True, num_proxies=0), [])
        self.assertEqual(self.run_check(debug=False, testing=False, num_proxies=1), [])

    def test_check_is_registered_and_fails_the_real_check_command_in_production_settings(self):
        env = {k: v for k, v in os.environ.items() if k not in ('DEBUG', 'NUM_PROXIES')}
        env.update(SECRET_KEY='cle-de-test-unique', DEBUG='False', NUM_PROXIES='0', DJANGO_SETTINGS_MODULE='backend.settings')
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check'], cwd=str(settings.BASE_DIR), env=env,
            capture_output=True, text=True, timeout=120,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('common.E001', result.stderr)
        env['NUM_PROXIES'] = '1'
        ok = subprocess.run(
            [sys.executable, 'manage.py', 'check'], cwd=str(settings.BASE_DIR), env=env,
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(ok.returncode, 0, ok.stderr)


class TestStorageCleanupTests(SimpleTestCase):
    def test_media_and_kyc_roots_are_temporary_and_registered_for_removal(self):
        import atexit  # noqa: F401
        import tempfile

        tmp = tempfile.gettempdir()
        self.assertTrue(str(settings.MEDIA_ROOT).startswith(tmp))
        self.assertTrue(str(settings.KYC_PRIVATE_ROOT).startswith(tmp))
        self.assertIn('connecteplus-tests-', str(settings.MEDIA_ROOT))


# Tâches planifiées de la V1 (CDC 5.6) : une ligne de backend/cron/crontab chacune.
SCHEDULED_COMMANDS = {
    'purge_offer_trash', 'expire_offers', 'lift_expired_sanctions',
    'purge_otp_codes', 'refresh_daily_contacts', 'refresh_visibility_scores', 'purge_offer_views', 'dispatch_outbox', 'purge_outbox',
    'sync_seller_visibility', 'expire_invitations',
}


class CrontabTests(SimpleTestCase):
    def scheduled(self):
        path = os.path.join(os.path.dirname(APPS_DIR), 'cron', 'crontab')
        with open(path, encoding='utf-8') as handle:
            return re.findall(r'manage\.py (\w+)', handle.read())

    def test_crontab_schedules_exactly_the_expected_commands_once(self):
        scheduled = self.scheduled()
        self.assertEqual(sorted(scheduled), sorted(SCHEDULED_COMMANDS))

    def test_every_scheduled_command_exists(self):
        from django.core.management import get_commands

        self.assertEqual(set(self.scheduled()) - set(get_commands()), set())
