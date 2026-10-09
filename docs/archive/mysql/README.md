# Archive MySQL (réservée à la tâche F-01)

Le projet tourne sur SQLite seul jusqu'à la fin du projet (ADR 0001). Ces fichiers
sont conservés pour la bascule vers MySQL (tâche F-01) et ne sont pas utilisés :

- `docker-compose.mysql.yml` : variante de parité MySQL (service `db`, `DB_ENGINE=mysql`).
  Elle référençait encore Redis, à retirer lors de la remise en service.
- `mysql-init/` : script d'initialisation (droits sur la base de test).
- Pilote : `backend/requirements-mysql.txt` (mysqlclient) ; il nécessite en plus
  `build-essential`, `default-libmysqlclient-dev` et `pkg-config` dans le Dockerfile.
