import os
import re
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import Resolver404, URLResolver, get_resolver, resolve
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

# Routes (méthode, gabarit d'URL) volontairement publiques : tout le reste doit refuser un
# anonyme. Une vue qui devient publique par erreur (AllowAny ajouté) OU privée par erreur
# (AllowAny oublié avec le refus par défaut) fait échouer test_every_route_..., qui parcourt
# TOUTES les routes via get_resolver().
EXPECTED_PUBLIC = {
    ('get', 'api/marketplace/cities/'),
    ('get', 'api/marketplace/cities/<pk>/'),
    ('get', 'api/marketplace/communes/'),
    ('get', 'api/marketplace/communes/<pk>/'),
    ('get', 'api/marketplace/categories/'),
    ('get', 'api/marketplace/categories/<pk>/'),
    ('get', 'api/marketplace/posts/'),
    ('get', 'api/marketplace/posts/<pk>/'),
    ('get', 'api/moderation/forbidden-items/'),
    ('get', 'api/moderation/forbidden-items/<pk>/'),
    ('get', 'api/interactions/reviews/'),
    ('get', 'api/interactions/reviews/<pk>/'),
    ('get', 'api/accounts/businesses/'),
    ('post', 'api/accounts/register/'),
    ('post', 'api/accounts/login/'),
    ('post', 'api/accounts/token/refresh/'),
    ('post', 'api/accounts/otp/request/'),
    ('post', 'api/accounts/password-reset/confirm/'),
}

# Routes qui doivent figurer dans le parcours (garde contre un parcours qui raterait des vues).
MUST_BE_WALKED = {
    'api/accounts/kyc/documents/<pk>/',
    'api/accounts/kyc/documents/<pk>/decision/',
    'api/accounts/kyc/documents/<pk>/download/',
    'api/marketplace/posts/<pk>/pause/',
    'api/marketplace/posts/<pk>/soft_delete/',
    'api/marketplace/posts/<pk>/favorite/',
    'api/marketplace/posts/recalculate_all_scores/',
    'api/marketplace/posts/trash/',
    'api/moderation/reports/<pk>/claim/',
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
    if actions:  # ViewSet : méthode HTTP -> action
        return {method: action for method, action in actions.items()}
    view_class = callback.cls
    return {m: None for m in view_class.http_method_names if m != 'options' and hasattr(view_class, m)}


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
