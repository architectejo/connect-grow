"""Réglages de test : indépendants de .env et de DEBUG.

Utilisés automatiquement par `python manage.py test` (voir manage.py). Ils ne
servent qu'aux tests : jamais en développement ni en production.
"""
import os
import tempfile

# Avant l'import des réglages principaux : aucune clé réelle n'est nécessaire.
os.environ.setdefault('SECRET_KEY', 'test-only-secret-key-not-for-production')
os.environ['DB_ENGINE'] = 'sqlite'

from .settings import *  # noqa: E402,F401,F403

DEBUG = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

# Hachage rapide, UNIQUEMENT en test (PBKDF2 rend la suite 50 fois plus lente).
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Les pièces KYC et médias de test ne polluent pas le dépôt ni le stockage de dev.
_TEST_STORAGE = tempfile.mkdtemp(prefix='connecteplus-tests-')
KYC_PRIVATE_ROOT = type(KYC_PRIVATE_ROOT)(_TEST_STORAGE) / 'kyc'  # noqa: F405
MEDIA_ROOT = os.path.join(_TEST_STORAGE, 'media')

# Cache factice : aucune limitation de débit (throttle) ne s'accumule d'un test à l'autre.
# Les tests de throttling activent un cache mémoire avec @override_settings(CACHES=...).
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}
