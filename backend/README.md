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
