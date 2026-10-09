"""Réglages de test, réservés à `python manage.py test` (manage.py les sélectionne seul).

Le module refuse de se charger autrement : ses allègements (hachage MD5, SSL désactivé,
cache factice) seraient dangereux en développement ou en production.

Reproductibilité : `backend.settings` appelle load_dotenv(), donc un `.env` local serait lu.
Pour qu'il ne puisse pas changer le résultat des tests, toutes les variables d'environnement
que les réglages consultent sont fixées ici AVANT l'import (load_dotenv n'écrase jamais une
variable déjà présente).
"""
import atexit
import os
import shutil
import sys
import tempfile

from django.core.exceptions import ImproperlyConfigured

if len(sys.argv) < 2 or sys.argv[1] != 'test':
    raise ImproperlyConfigured(
        "backend.settings_test ne se charge que par `python manage.py test` ; "
        "n'utilisez jamais ces réglages ailleurs."
    )

_FORCED_ENV = {
    'SECRET_KEY': 'test-only-secret-key-not-for-production',
    'DEBUG': 'False',
    'DB_ENGINE': 'sqlite',
    'BEHIND_PROXY': 'False',
    'NUM_PROXIES': '0',
    'KYC_MAX_FILE_MB': '5',
    'KYC_MAX_DOCUMENTS_PER_PROFILE': '6',
    'PROFILE_IMAGE_MAX_SIDE': '1024',
    'PROFILE_IMAGE_QUALITY': '85',
    'PROFILE_IMAGE_MAX_MB': '5',
    'PROFILE_IMAGE_MAX_PIXELS': '16000000',
    # Outbox : diffusion explicite dans les tests (apps.platform_core.testing.dispatch_outbox_now).
    'OUTBOX_INLINE_DISPATCH': 'False',
    'OUTBOX_MAX_ATTEMPTS': '8',
    'OUTBOX_LOCK_TIMEOUT_SECONDS': '300',
    'OUTBOX_BACKOFF_BASE_SECONDS': '30',
    'OUTBOX_BACKOFF_MAX_SECONDS': '3600',
    'OUTBOX_RETENTION_DAYS': '7',
    'OUTBOX_DEAD_RETENTION_DAYS': '30',
}
os.environ.update(_FORCED_ENV)

from .settings import *  # noqa: E402,F401,F403

TESTING = True
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

# Hachage rapide, UNIQUEMENT en test (PBKDF2 rend la suite 50 fois plus lente).
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Les pièces KYC et médias de test ne polluent pas le dépôt ni le stockage de dev.
_TEST_STORAGE = tempfile.mkdtemp(prefix='connecteplus-tests-')
atexit.register(shutil.rmtree, _TEST_STORAGE, ignore_errors=True)  # supprimé en fin de run
KYC_PRIVATE_ROOT = type(KYC_PRIVATE_ROOT)(_TEST_STORAGE) / 'kyc'  # noqa: F405
MEDIA_ROOT = os.path.join(_TEST_STORAGE, 'media')

# Cache factice : aucune limitation de débit (throttle) ne s'accumule d'un test à l'autre.
# Les tests de throttling activent un cache mémoire avec @override_settings(CACHES=...).
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}

# Les échecs d'abonnés provoqués exprès par les tests ne polluent pas la sortie (assertLogs reste possible).
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'loggers': {'apps.platform_core': {'handlers': ['null'], 'propagate': False}},
}
