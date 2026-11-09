"""
Django settings for backend project.
Version sécurisée pour la production et le développement.
"""

from pathlib import Path
import os
from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
from backend.api_limits import parse_page_limits
from corsheaders.defaults import default_headers

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- SÉCURITÉ CRITIQUE ---
# DEBUG doit être à False en production pour ne pas exposer la structure de la DB en cas d'erreur
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Vrai seulement sous backend.settings_test (lancé par `manage.py test`).
TESTING = False

# Ne jamais stocker la clé secrète dans le code. Valeur de repli réservée au développement
# (DEBUG=True) : hors DEBUG, une clé absente ou factice interrompt le démarrage.
_DEV_SECRET_KEY = 'django-insecure-dev-only-key'
SECRET_KEY = os.getenv('SECRET_KEY', '')
if not SECRET_KEY or SECRET_KEY == 'change-me':
    if not DEBUG:
        raise ImproperlyConfigured(
            "SECRET_KEY est absente ou factice : définissez une clé secrète unique dans l'environnement "
            "(.env), ou activez DEBUG=True en développement uniquement."
        )
    SECRET_KEY = _DEV_SECRET_KEY

# Restreindre les hôtes autorisés pour éviter les attaques par empoisonnement d'hôte HTTP
# ALLOWED_HOSTS='localhost,127.0.0.1,api.connecteplus.cd' dans .env pour la recette/prod
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]


# --- DÉFINITION DES APPLICATIONS ---
INSTALLED_APPS = [
    'daphne', # Toujours en haut pour ASGI
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Bibliothèques tierces
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',  # schéma OpenAPI de l'API (ADR 0007)
    'rest_framework_simplejwt.token_blacklist',  # déconnexion et révocation des refresh tokens
    'corsheaders',
    
    # Applications locales. `identity` précède `catalog` (ForbiddenItem.added_by -> utilisateur) :
    # l'ordre garde un seul 0001_initial par app à la génération des migrations.
    'apps.common',
    'apps.platform_core',
    'apps.identity',
    'apps.catalog',
    'apps.visibility',
    'apps.notifications',
    'apps.messaging',
    'apps.marketplace',
    'apps.reviews',
    'apps.payments',
    'apps.moderation',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware', # Doit être avant CommonMiddleware
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware', # Protection contre les attaques CSRF
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware', # Protection contre le Clickjacking
    'apps.common.middleware.ApiCacheHeadersMiddleware',  # Vary/Cache-Control de l'API (vie privée)
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# --- Pagination de l'API (classe commune apps.common.pagination) ---
# Valeurs invalides (non numérique, < 1, taille > plafond) : arrêt explicite au démarrage.
API_PAGE_SIZE, API_MAX_PAGE_SIZE = parse_page_limits(os.getenv('API_PAGE_SIZE', '20'), os.getenv('API_MAX_PAGE_SIZE', '100'))

# --- CONFIGURATION REST FRAMEWORK & JWT ---
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'apps.common.openapi.ConnecteAutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # Erreurs hors champ : {"detail", "code"} (ADR 0004, section 7).
    'EXCEPTION_HANDLER': 'apps.common.exception_handler.exception_handler',
    # Refus par défaut : toute vue publique déclare explicitement AllowAny.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Protection contre le brute-force : limitation du nombre de requêtes
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    # Nombre de proxies de confiance devant l'application (0 = adresse de connexion directe ;
    # 1 derrière Nginx). Détermine l'IP lue par tous les throttles (voir .env.example).
    'NUM_PROXIES': int(os.getenv('NUM_PROXIES', '0')),
    'DEFAULT_THROTTLE_RATES': {
        # Navigation générale (larges : plusieurs utilisateurs derrière une même IP mobile).
        'anon': '5000/day',
        'user': '10000/day',
        # CDC 4.2 : OTP (coût SMS, anti-brute-force).
        'otp': '5/hour',            # demandes de code, par IP
        'otp_phone': '3/hour',      # demandes de code, par couple numéro+IP
        'otp_phone_day': '10/day',  # demandes de code, par numéro seul (coût SMS)
        'otp_confirm': '20/hour',   # confirmations de reset, par IP
        # Connexion : toutes requêtes par IP ; les échecs par identifiant sont comptés à part
        # (voir apps/identity/throttles.py : FailureLimiter).
        'login': '60/hour',
        'refresh': '60/hour',       # renouvellement de jeton, par IP
        'register': '20/hour',      # inscription, par IP (anti-énumération des e-mails)
        'profile_write': '30/hour',     # écritures du profil, par utilisateur
        'profile_write_ip': '60/hour',  # écritures du profil, par IP
        'logout': '60/hour',        # déconnexion (publique), par IP
        'change_password': '10/hour',  # par utilisateur
        'kyc_write': '20/hour',     # dépôt/suppression de pièces KYC, par utilisateur
        'provider_write': '20/hour',  # profil prestataire (activation, modification, archivage), par utilisateur
        'org_create': '5/day',      # création d'organisation, par utilisateur (ADR 0006, 9.2)
        'org_list': '600/hour',     # liste publique des organisations, par IP
        'seller_profile': '600/hour',  # profil public d'un vendeur (marketplace), par IP
        'org_write': '30/hour',     # modification, archivage et sortie d'une organisation, par utilisateur
        'org_sensitive': '10/hour',  # transfert de propriété, promotion ou rétrogradation d'un propriétaire, par utilisateur
        'invitation_create': '20/hour',        # création d'invitation d'équipe, par utilisateur (ADR 0008, 8.3)
        'invitation_create_org': '50/day',     # création d'invitation d'équipe, par organisation
        'invitation_redeem': '60/hour',        # aperçu, acceptation, refus d'invitation, par IP
        'invitation_redeem_user': '30/hour',   # aperçu, acceptation, refus d'invitation, par utilisateur
        'contexts': '600/hour',    # liste des contextes disponibles, par utilisateur
        'account_blockers': '120/hour',  # blocages de suppression de compte, par utilisateur (ADR 0008, 8.3)
        'contact_settings': '20/hour',  # réglages de contact vendeur (numéro, code, canaux), par utilisateur
        # Écritures du marketplace et des interactions (par utilisateur ; par IP pour la vue anonyme).
        'contact': '20/hour',
        'contact_reveal_ip': '30/hour',    # révélation de numéro, par IP (aucune IP persistée)
        'contact_reveal_user': '60/hour',  # révélation de numéro, filet technique par utilisateur
        'contact_reveals_list': '120/hour',  # liste « qui a demandé mon numéro », par utilisateur
        'exchange': '10/hour',
        'features': '120/hour',  # configuration publique des fonctionnalités, par IP (anonymes)
        'share': '30/hour',
        'message': '120/hour',
        'review': '10/hour',
        'offer_list': '600/hour',  # liste des annonces (tri par pertinence non indexé), par IP ou par utilisateur
        'review_eligibility': '120/hour',  # lecture du droit d'avis, par utilisateur
        'report': '10/hour',        # signalements, par utilisateur
        'report_response': '30/hour',  # recours de l'auteur d'un avis signalé, par utilisateur
        'offer_upload': '30/hour',  # création / modification d'offre et envoi de photos
        'favorite': '60/hour',
        'offer_view_anon': '300/hour',  # consultation anonyme d'une offre, par IP
    }
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),  # CLAUDE.md §5
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True, # Sécurité accrue : change le refresh token à chaque usage
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# --- CONFIGURATION CORS ---
# En production, remplacez CORS_ALLOW_ALL_ORIGINS par une liste précise
CORS_ALLOW_ALL_ORIGINS = DEBUG 

# 1. Autoriser explicitement l'URL du frontend React
# CORS_ALLOWED_ORIGINS='https://connecteplus.cd,https://www.connecteplus.cd' dans .env en recette/prod
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        'CORS_ALLOWED_ORIGINS', 'http://localhost:8080,http://127.0.0.1:8080'
    ).split(',') if o.strip()
]

# 2. Obligatoire pour withCredentials: true (cookies)
CORS_ALLOW_CREDENTIALS = True

# Le front doit pouvoir lire Retry-After sur les réponses 429 (appels inter-origines).
CORS_EXPOSE_HEADERS = ['Retry-After']

# En-tête du contexte actif (ADR 0006, 6.1) : en plus des en-têtes par défaut de django-cors-headers,
# sinon la requête préalable du navigateur le refuse.
CORS_ALLOW_HEADERS = (*default_headers, 'x-context')

# 3. Assure-toi que ces méthodes sont autorisées
CORS_ALLOW_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]

# --- BASE DE DONNÉES & SÉCURITÉ ---
# L'utilisation de l'ORM Django protège déjà nativement contre les Injections SQL
#
# CDC 2.5 et ADR 0001 : SQLite seul dans tous les environnements jusqu'à la fin du
# projet. Le moteur est choisi par DB_ENGINE dans .env ('sqlite' par défaut).
# La branche 'mysql' ci-dessous est réservée à la tâche F-01 (requirements-mysql.txt) :
# code non testé, ne pas l'activer avant F-01.
if os.getenv('DB_ENGINE', 'sqlite') == 'mysql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'connecteplus'),
            'USER': os.getenv('DB_USER', 'connecteplus'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {
                'charset': 'utf8mb4',
                # Mode SQL strict explicite (2.5) : pas de troncature silencieuse des données.
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.getenv('DB_NAME', 'db.sqlite3'),
            # Le serveur et le cron écrivent dans le même fichier : on attend jusqu'à
            # 20 s un verrou d'écriture avant « database is locked » (défaut : 5 s).
            'OPTIONS': {'timeout': 20},
        }
    }

# Derrière Nginx (TLS terminé par le proxy) : faire confiance à X-Forwarded-Proto pour que
# Django sache que la requête est en HTTPS (sinon SECURE_SSL_REDIRECT boucle). À n'activer
# (BEHIND_PROXY=True) que si le proxy écrase cet en-tête et que Daphne n'est pas joignable
# directement : sinon un client pourrait le falsifier. Nginx doit envoyer
# `proxy_set_header X-Forwarded-Proto $scheme;`.
if os.getenv('BEHIND_PROXY', 'False') == 'True':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Paramètres de sécurité avancés (pour HTTPS en production)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000 # 1 an
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True

# --- AUTRES CONFIGURATIONS ---
AUTH_USER_MODEL = 'identity.User'
ASGI_APPLICATION = 'backend.asgi.application'

# CDC 5.5 : une seule instance Daphne avec channel layer en mémoire suffit tant qu'il n'y a
# qu'un serveur ; RabbitMQ interviendra seulement au passage à plusieurs instances Daphne
# (channels_rabbitmq, à valider avant adoption). Pas de Redis.
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# CDC 4.2 / 5.8 : pièces KYC dans un espace privé, jamais sous MEDIA_ROOT (qui est
# servi publiquement par Nginx/le helper static() en dev). Accès uniquement via une
# vue authentifiée réservée aux administrateurs (apps.identity).
KYC_PRIVATE_ROOT = BASE_DIR / 'private_media' / 'kyc'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Mots de passe et langue ---
LANGUAGE_CODE = 'fr'  # messages de validation Django en français
# Les dates sont stockées en UTC et exposées avec leur décalage (Kinshasa : UTC+1). Les « jours »
# des compteurs et des limites quotidiennes suivent ce fuseau (timezone.localdate()).
TIME_ZONE = 'Africa/Kinshasa'
USE_TZ = True

# --- Contact vendeur (ADR 0005) ---
# Ancienneté minimale (heures) d'un compte sans identifiant vérifié pour recevoir un SMS de
# vérification vers un numéro saisi (anti-SMS arbitraire).
CONTACT_SMS_MIN_ACCOUNT_AGE_HOURS = int(os.getenv('CONTACT_SMS_MIN_ACCOUNT_AGE_HOURS', '24'))

# --- Journalisation ---
# En développement (DEBUG=True), le code OTP « envoyé » est affiché en console (apps/identity/sms.py,
# aucun fournisseur SMS branché). Hors DEBUG, le niveau reste à WARNING pour ce logger et le code
# n'est de toute façon jamais journalisé : la passerelle lève une erreur sans l'écrire.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'simple': {'format': '%(levelname)s %(name)s : %(message)s'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'}},
    'loggers': {
        'apps.identity.sms': {
            'handlers': ['console'],
            'level': 'INFO' if DEBUG else 'WARNING',
            'propagate': False,
        },
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# --- Pièces KYC (règle 10 : données d'identité) ---
# Valeurs de départ, ajustables par variable d'environnement.
KYC_MAX_FILE_BYTES = int(os.getenv('KYC_MAX_FILE_MB', '5')) * 1024 * 1024
KYC_MAX_DOCUMENTS_PER_PROFILE = int(os.getenv('KYC_MAX_DOCUMENTS_PER_PROFILE', '6'))


# --- Photos de profil et logos (ré-encodés sans métadonnées : apps/common/images.py) ---
PROFILE_IMAGE_MAX_SIDE = int(os.getenv('PROFILE_IMAGE_MAX_SIDE', '1024'))      # pixels, côté le plus long
PROFILE_IMAGE_QUALITY = int(os.getenv('PROFILE_IMAGE_QUALITY', '85'))
PROFILE_IMAGE_MAX_BYTES = int(os.getenv('PROFILE_IMAGE_MAX_MB', '5')) * 1024 * 1024
PROFILE_IMAGE_MAX_PIXELS = int(os.getenv('PROFILE_IMAGE_MAX_PIXELS', str(16_000_000)))  # anti « bombe » d'image

# Plafonds de requête : corps hors fichiers (JSON, champs de formulaire) et nombre de fichiers par
# requête. La taille des fichiers est contrôlée par PROFILE_IMAGE_MAX_BYTES ; la taille totale du
# corps doit aussi être bornée par Nginx (client_max_body_size, voir README).
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('DATA_UPLOAD_MAX_MEMORY_KB', '1024')) * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 10
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200

# Cookie signé qui identifie un visiteur anonyme pour le comptage des vues (apps.marketplace).
ANON_VIEW_COOKIE_MAX_AGE = 365 * 86400

# --- Outbox des événements de domaine (ADR 0003) ---
# Diffusion immédiate après validation de la transaction émettrice ; le cron `dispatch_outbox`
# (chaque minute) reste le filet de sécurité. Désactivée sous settings_test.
OUTBOX_INLINE_DISPATCH = os.getenv('OUTBOX_INLINE_DISPATCH', 'True') == 'True'
OUTBOX_MAX_ATTEMPTS = int(os.getenv('OUTBOX_MAX_ATTEMPTS', '8'))
OUTBOX_LOCK_TIMEOUT_SECONDS = int(os.getenv('OUTBOX_LOCK_TIMEOUT_SECONDS', '300'))
OUTBOX_BACKOFF_BASE_SECONDS = int(os.getenv('OUTBOX_BACKOFF_BASE_SECONDS', '30'))
OUTBOX_BACKOFF_MAX_SECONDS = int(os.getenv('OUTBOX_BACKOFF_MAX_SECONDS', '3600'))
OUTBOX_MAX_PAYLOAD_BYTES = 16 * 1024
# Rétention courte : certaines charges utiles contiennent des données personnelles (message de contact).
OUTBOX_RETENTION_DAYS = int(os.getenv('OUTBOX_RETENTION_DAYS', '7'))
OUTBOX_DEAD_RETENTION_DAYS = int(os.getenv('OUTBOX_DEAD_RETENTION_DAYS', '30'))


# --- Documentation OpenAPI (drf-spectacular, ADR 0007) ---
SPECTACULAR_SETTINGS = {
    'TITLE': 'Connecte+ API',
    'VERSION': '1.0.0',
    'DESCRIPTION': (
        "API REST de Connecte+ (plateforme de visibilité de Kinshasa), versionnée sous `/api/v1/`.\n\n"
        "Authentification : jeton JWT dans `Authorization: Bearer <jeton>`. Le contexte actif "
        "(personnel, prestataire, organisation) se choisit avec l'en-tête optionnel `X-Context: TYPE:uuid`. "
        "Les erreurs hors champ ont la forme `{\"detail\", \"code\"}`."
    ),
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '/api/v1',
    'SCHEMA_PATH_PREFIX_TRIM': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'PREPROCESSING_HOOKS': ['apps.common.openapi.only_v1_endpoints'],
    'POSTPROCESSING_HOOKS': ['apps.common.openapi.add_context_header'],
}
