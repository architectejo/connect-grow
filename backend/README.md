# Backend Connecte+ : notes Docker

Base SQLite seule (ADR 0001). Voir `CLAUDE.md` section 7 pour les commandes hors Docker.

## Données persistantes sous Docker

| Volume | Contenu |
|---|---|
| `backend_data` | base SQLite (`/app/data/db.sqlite3`), partagée par `backend` et `cron` |
| `backend_media` | médias publics |
| `backend_private` | pièces KYC (`/app/private_media`), service `backend` uniquement |

Attention :
- `docker compose down -v` supprime ces volumes : la base SQLite et les pièces KYC sont détruites de façon irréversible. Utiliser `docker compose down` sans `-v` pour un simple arrêt.
- Le `db.sqlite3` présent dans le dossier `backend/` de l'hôte n'est pas utilisé dans Docker (le compose impose `DB_NAME=data/db.sqlite3` sur le volume). La base Docker est donc distincte de celle du développement local.

## Données de départ

Après `migrate` sur une base vierge :

```bash
python manage.py setup_roles     # groupes Modérateur et Administrateur
python manage.py seed_catalog    # villes, communes, catégories, produits interdits
```

`seed_catalog` lit `apps/catalog/seed/initial_catalog.json` (ou un autre fichier via `--file`). Il est idempotent : il crée ce qui manque et ne modifie jamais l'existant. Les valeurs se gèrent ensuite dans le back-office ; ne pas l'ajouter au démarrage du conteneur, il recréerait les entrées supprimées par l'administration.

## Tests

```bash
python manage.py test apps
```

`manage.py test` charge automatiquement `backend/settings_test.py` : pas de `.env` ni de `DEBUG=True` nécessaires, redirection HTTPS désactivée, hachage MD5 (tests uniquement), stockages dans un dossier temporaire. Comptez quelques dizaines de secondes. Ces réglages ne se chargent que par `manage.py test` (ils lèvent `ImproperlyConfigured` ailleurs) et fixent eux-mêmes les variables d'environnement lues par `settings.py`, pour qu'un `.env` local ne change pas le résultat.

## Limitation de débit derrière Nginx

Définir `NUM_PROXIES=1` (et `BEHIND_PROXY=True`) en production derrière Nginx, avec `proxy_set_header X-Forwarded-For $remote_addr;` et `proxy_set_header X-Forwarded-Proto $scheme;` : sans cela, tous les clients partagent l'IP du proxy ou l'en-tête devient falsifiable. Le cache de production devra être partagé entre processus (LocMem est local à chaque processus).

### NUM_PROXIES (obligatoire hors développement)

Derrière Nginx : `NUM_PROXIES=1` et `BEHIND_PROXY=True` dans l'environnement, avec dans Nginx :

```nginx
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
```

`$remote_addr` (et non `$proxy_add_x_forwarded_for`) écrase tout en-tête envoyé par le client : l'IP lue par les limites de débit n'est alors pas falsifiable. Un contrôle Django (`common.E001`, exécuté par `check`, `migrate`, `runserver`...) échoue si `DEBUG=False` et `NUM_PROXIES=0`.


## Envois de fichiers et tâches planifiées

- **Taille des envois** : Django borne le corps hors fichiers (`DATA_UPLOAD_MAX_MEMORY_SIZE`, 1 Mo par défaut, réglable par `DATA_UPLOAD_MAX_MEMORY_KB`), le nombre de fichiers par requête (`DATA_UPLOAD_MAX_NUMBER_FILES = 10`) et chaque image (`PROFILE_IMAGE_MAX_MB`, `PROFILE_IMAGE_MAX_PIXELS`, 16 Mpx, mêmes plafonds pour les photos d'offres). Nginx doit aussi borner le corps total avant Django : `client_max_body_size 12m;` (8 photos de 5 Mo ne passent pas d'un seul envoi : le plafond protège le serveur, les photos s'envoient en plusieurs requêtes).
- **Vues uniques** : la commande `purge_offer_views` (quotidienne, voir `cron/crontab`) supprime les vues uniques plus anciennes que la durée réglée dans le back-office (Paramètres de visibilité, 2 jours par défaut ; durée définitive à fixer avec LEG-PRV).
- **Fuseau** : `TIME_ZONE = 'Africa/Kinshasa'`, `USE_TZ = True`. Les dates JSON portent le décalage (`+01:00`).
