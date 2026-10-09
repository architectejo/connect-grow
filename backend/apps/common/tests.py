import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

# Endpoints qui DOIVENT rester publics (anonyme : ni 401 ni 403). Si l'un devient privé
# par erreur (p. ex. oubli de AllowAny avec le refus par défaut), ce test échoue.
PUBLIC_ENDPOINTS = [
    ('get', '/api/marketplace/cities/'),
    ('get', '/api/marketplace/communes/'),
    ('get', '/api/marketplace/categories/'),
    ('get', '/api/marketplace/posts/'),
    ('get', '/api/moderation/forbidden-items/'),
    ('get', '/api/interactions/reviews/'),
    ('get', '/api/accounts/businesses/'),
    ('post', '/api/accounts/register/'),
    ('post', '/api/accounts/login/'),
    ('post', '/api/accounts/token/refresh/'),
    ('post', '/api/accounts/otp/request/'),
    ('post', '/api/accounts/password-reset/confirm/'),
]

# Endpoints qui DOIVENT refuser un anonyme (401).
PRIVATE_ENDPOINTS = [
    ('get', '/api/accounts/me/'),
    ('post', '/api/accounts/change-password/'),
    ('post', '/api/accounts/logout/'),
    ('post', '/api/accounts/logout-all/'),
    ('get', '/api/accounts/kyc/documents/'),
    ('get', '/api/accounts/kyc/review-queue/'),
    ('get', '/api/marketplace/favorites/'),
    ('get', '/api/marketplace/posts/trash/'),
    ('get', '/api/marketplace/stats/dashboard/'),
    ('post', '/api/marketplace/posts/'),
    ('get', '/api/interactions/notifications/'),
    ('get', '/api/interactions/conversations/'),
    ('get', '/api/interactions/messages/'),
    ('post', '/api/interactions/contacts/'),
    ('post', '/api/interactions/reviews/'),
    ('get', '/api/reputation/deals/'),
    ('get', '/api/moderation/reports/'),
    ('get', '/api/moderation/sanctions/'),
    ('get', '/api/moderation/dashboard/'),
    ('post', '/api/moderation/forbidden-items/'),
    ('get', '/api/payments/'),
]


class PermissionDefaultsTests(TestCase):
    def test_default_permission_is_authenticated(self):
        self.assertEqual(
            settings.REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'], ['rest_framework.permissions.IsAuthenticated'],
        )

    def test_expected_public_endpoints_stay_public(self):
        client = APIClient()
        for method, url in PUBLIC_ENDPOINTS:
            response = getattr(client, method)(url, {}, format='json') if method == 'post' else client.get(url)
            self.assertNotIn(response.status_code, (401, 403), f"{method.upper()} {url} est devenu privé")

    def test_expected_private_endpoints_refuse_anonymous(self):
        client = APIClient()
        for method, url in PRIVATE_ENDPOINTS:
            response = getattr(client, method)(url, {}, format='json') if method == 'post' else client.get(url)
            self.assertIn(response.status_code, (401, 403, 404), f"{method.upper()} {url}")
            self.assertNotEqual(response.status_code, 200, f"{method.upper()} {url} est public")
        # Les routes existantes (hors /api/payments/, vide) répondent bien 401 et non 404.
        for method, url in PRIVATE_ENDPOINTS:
            if url == '/api/payments/':
                continue
            response = getattr(client, method)(url, {}, format='json') if method == 'post' else client.get(url)
            self.assertEqual(response.status_code, 401, f"{method.upper()} {url}")


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
