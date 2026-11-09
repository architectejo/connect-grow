# ADR 0007 — Versionnement de l'API sous `/api/v1/` et plafond de pagination (L0-11)

- **Statut :** accepté
- **Date :** 09/11/2026
- **Tâche :** L0-11 (CLAUDE.md §5, CDC v1.2 §5.9)

## Décision

1. Toutes les routes REST sont servies sous le préfixe unique `/api/v1/` (`/api/v1/accounts/`, `/api/v1/marketplace/`, `/api/v1/interactions/`, `/api/v1/moderation/`, `/api/v1/config/`, `/api/v1/payments/`). Une future version incompatible sera montée sous `/api/v2/` à côté de la v1.
2. **Pas de double montage ni de redirection** de l'ancien préfixe `/api/` : aucune production n'existe, l'ancien préfixe répond 404.
3. Les chemins WebSocket `/ws/…` et les routes du front (`/organizations/<id>` dans les liens de notification) sont inchangés.
4. Pagination commune (`apps.common.pagination.StandardPagination`) : taille par défaut `API_PAGE_SIZE` (20) et plafond `API_MAX_PAGE_SIZE` (100), réglables par variable d'environnement. Un `page_size` client supérieur au plafond est ramené au plafond ; nul, négatif ou non numérique, il est ramené au défaut, sans erreur.

## Conséquences

- Le front utilise `VITE_API_URL=http://localhost:8000/api/v1/`.
- Le middleware de cache d'API, les tests, le script `scripts/recette_contrat_http.py` et le README suivent le nouveau préfixe.
- Le Service Worker (PWA) met en cache l'ancien préfixe : au déploiement, forcer la mise à jour du Service Worker (`registerType: 'prompt'`) et l'inscrire dans le runbook de déploiement.
- La pagination est validée au démarrage : `API_PAGE_SIZE` et `API_MAX_PAGE_SIZE` doivent être des entiers >= 1 avec taille <= plafond, sinon `ImproperlyConfigured` (`backend/api_limits.py`).

## Documentation OpenAPI (L0-11b)

- Outil : `drf-spectacular` 0.30.0 (épinglé dans `requirements.txt`), schéma OpenAPI 3 généré depuis les vues DRF.
- `GET /api/v1/schema/` : schéma (JSON ou YAML selon `Accept`), public car il ne contient que de la structure, aucune donnée. Hors `/api/v1/` (admin, schéma, docs), rien n'est documenté.
- `GET /api/v1/docs/` (Swagger UI) : routé **seulement si `DEBUG=True`** (l'interface charge ses assets depuis un CDN) ; absent en production.
- Schéma de sécurité `jwtAuth` (Bearer JWT, fourni par simplejwt) et en-tête optionnel `X-Context` (`TYPE:uuid`) ajouté à chaque opération (`apps/common/openapi.py`).
- Les `APIView` sans serializer sont documentées comme « objet libre » (`PayloadLibre`) : dette, à décrire avec `extend_schema` au fil des stories.
- Commande : `python manage.py spectacular --file schema.yml --validate` (base migrée requise).
