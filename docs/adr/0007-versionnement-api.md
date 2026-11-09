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
- La documentation OpenAPI n'existe pas encore (aucune dépendance de génération installée) ; elle sera servie sous `/api/v1/` quand la dépendance sera validée.
