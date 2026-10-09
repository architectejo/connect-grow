# ADR 0004 — Avis après contact, classement organique, retrait du Trust Score (L0-07, L0-08, L0-10)

- **Statut :** accepté (chef de projet, 09/10/2026) (à valider par l'utilisateur, voir section 11)
- **Date :** 09/10/2026
- **Rédaction :** architecte-technique
- **Références :** CLAUDE.md §4 (règles 4, 5, 10, 11, 12) et §5 ; CDC v1.2 §3.4, §3.5, §3.15 ; ADR 0001, 0002, 0003 ; `docs/specs/avis-classement-contact.md` (décisions D1 à D16 du chef de projet, section 6).

## 1. Contexte

L'existant (code lu dans `cp-wt-backend/backend/apps`) porte trois écarts avec les règles verrouillées :

- Un **Trust Score** (règle 4) : `identity.User.trust_score` et `reviews_count` ; `reviews.TrustScoreSettings`, `Deal`, `recompute_trust_score`, `reviews/signals.py` (recalcul synchrone, écrit dans `identity` et `marketplace`) ; facteur T de `visibility.compute_score` ; `RankingSettings.trust_factor_*` ; badge « Vendeur fiable » (`is_trusted_seller`) ; `avg_rating = trust_score` dans le tableau de bord.
- Un **droit d'avis fondé sur `Deal`** (« affaire conclue ») au lieu de la prise de contact (CDC §3.4), une note unique, des avis dans les deux sens, des seuils codés en dur (règle 11).
- Un **score de visibilité** qui n'est pas P x E x R x D (§3.5) : `comments_count` (jamais alimenté) à la place des contacts, T au lieu de D, pondérations en base mais mal nommées.

Aucune donnée de production n'existe (ADR 0002 ; spec section 5). La messagerie des événements (outbox, ADR 0003) est en place : `reviews/services.py` publie déjà `review_posted`, `review_replied`, `crossed_reviews_detected` ; il n'existe plus d'événement `reputation_changed` dans le catalogue (le recalcul du Trust Score est resté synchrone par signaux).

## 2. Décision en bref

1. Suppression nette du Trust Score, de `Deal` et du badge « Vendeur fiable ». Aucune compatibilité ascendante.
2. `Review` est réécrit : une ligne = un visiteur qui note **une offre** (note d'offre) et **son vendeur** (note vendeur), preuve = référence à une prise de contact (`contact_event_id`, UUID, sans clé étrangère).
3. Les moyennes ne sont **jamais stockées** : calculées à la lecture par requêtes d'agrégat (pas de score agrégé sur `User` ni sur `Offer`).
4. Le score organique stocké sur l'offre (`Offer.visibility_score`) vaut **E x R** ; **P = 1** (filtre strict en V1) et **D** est appliqué à la lecture dans le tri SQL (`ExpressionWrapper` + `Case/When`, portable).
5. Réglages en base : `visibility.RankingSettings` (classement), `reviews.ReviewSettings` (avis), `marketplace.MarketplaceSettings` (fenêtre de doublon de contact). Toute modification est journalisée (`AuditLog`).
6. Migrations : réécriture des `0001` des cinq apps touchées, en une seule opération (section 8).

## 3. Modèle de données final

Convention : `BaseModel` (UUID, `created_at`, `updated_at`). Longueurs explicites. Aucune unicité conditionnelle.

### 3.1 `reviews.Review` (remplace l'existant)

| Champ | Type | Remarque |
|---|---|---|
| `user` | FK utilisateur, CASCADE | Auteur (le visiteur). Nom conservé. |
| `offer_id` | UUIDField, `db_index`, **non nul** | Référence sans FK ; l'avis survit à la purge de l'offre. |
| `seller_context_type` | CharField(20), défaut `USER` | Valeurs : `USER` maintenant ; `ORGANIZATION` / contexte prestataire après L0-09. Constantes dans `apps/common/contexts.py` (aucun modèle). |
| `seller_context_id` | UUIDField | Contexte vendeur noté (un `User.id` tant que L0-09 n'est pas faite). Jamais fusionné avec un autre rôle (CDC §3.4). |
| `contact_event_id` | UUIDField | Prise de contact qui ouvre le droit (la plus ancienne de l'auteur pour cette offre). Pas de FK (autre domaine). |
| `contact_channel` | CharField(10) | Instantané : `MESSAGE`, `CALL`, `WHATSAPP`. Pour la modération (D5e). |
| `contact_recorded_at` | DateTimeField | Instantané de la date du contact. |
| `offer_rating` | PositiveSmallIntegerField 1..5 | Note de l'offre. |
| `seller_rating` | PositiveSmallIntegerField 1..5 | Note du vendeur. |
| `content` | TextField, 10..500 après `strip` | Validateurs modèle + serializer. |
| `reply_content` / `reply_at` | TextField(<=500) null / DateTimeField null | Inchangés. |
| `is_hidden` | BooleanField, défaut False | Masqué par la modération : exclu de toutes les moyennes et listes publiques. |
| `counts_for_seller` | BooleanField, défaut True | Vrai pour **la dernière** note vendeur non masquée de ce couple (auteur, contexte vendeur) ; voir 3.2. |
| `edited_at` | DateTimeField null | Mention « modifié ». |

Contraintes et index :
- `UniqueConstraint(user, offer_id)` nom `uniq_review_author_offer` : un avis par couple auteur-offre (D2, inconditionnelle).
- Index `(seller_context_type, seller_context_id, is_hidden, counts_for_seller)` : moyenne vendeur.
- Index `(offer_id, is_hidden)` : moyenne et liste d'offre.
- Index `(user, seller_context_id, created_at)` : calcul du drapeau et avis croisés.
- Supprimés : `deal`, `reviewed_user`, `rating`, `uniq_review_deal_user`.
- Conservé tel quel : `ReviewDailyCount` (limite quotidienne qui ne se libère pas à la suppression).

### 3.2 Une note vendeur par auteur et par vendeur (D2)

L'unicité « auteur x vendeur » ne peut pas être une contrainte (un auteur écrit un avis par offre, donc plusieurs lignes pour un même vendeur) et on exclut la contrainte conditionnelle. Règle en couche service : `reviews.services.reconcile_seller_flag(user_id, ctx_type, ctx_id)`, idempotente, dans la même transaction que toute création, suppression, masquage ou réaffichage d'avis : met `counts_for_seller=False` sur toutes les lignes du couple, puis `True` sur la plus récente non masquée (`created_at`, puis `id`). La moyenne vendeur = `Avg(seller_rating)` des lignes `is_hidden=False, counts_for_seller=True` du contexte. La moyenne d'offre = `Avg(offer_rating)` des lignes `is_hidden=False` de l'offre. Modifier (48 h) un avis qui n'est pas le plus récent ne change pas la moyenne vendeur (documenté).

### 3.3 `reviews.ReviewSettings` (SingletonSettingsModel, « Avis et contact », règle 11)

| Champ | Défaut | Contrôle |
|---|---|---|
| `min_reviews_to_display` | 3 | >= 1 |
| `daily_review_limit` | 5 | >= 1 |
| `edit_window_hours` | 48 | >= 1 |
| `delay_after_contact_hours` | 24 | >= 0 |
| `crossed_reviews_window_days` | 30 | >= 1 |
| `crossed_reviews_threshold` | 3 | >= 2 |

Remplace `TrustScoreSettings.min_reviews_to_display` et les constantes `DAILY_REVIEW_LIMIT`, `CROSSED_REVIEWS_*`, `REVIEW_EDIT_WINDOW_HOURS`. Les limites de révélation de numéro (D13) arrivent avec L0-10a dans `MarketplaceSettings` (domaine du contact). **Écart avec D8** (« une seule table ») : deux tables par domaine, car `reviews` ne peut pas lire un modèle de `marketplace` ; l'admin les présente côte à côte (regroupement visuel).

### 3.4 `marketplace` (T1 pose le schéma ; T2 porte la logique)

- `ContactEvent` : ajout `channel` CharField(10) (`MESSAGE` défaut, `CALL`, `WHATSAPP`) ; `is_counted` BooleanField (défaut True) = ce contact entre dans l'engagement (une fois par expéditeur, offre et fenêtre, tous canaux confondus).
- `Offer` : ajout `contacts_count` PositiveIntegerField (nombre de `ContactEvent.is_counted`, recalculé depuis la source) ; **suppression de `comments_count`**. `likes_count` (nombre de favoris) est conservé tel quel ; son renommage est renvoyé à L0-11. `visibility_score` est conservé (sens : E x R) ; index `offer_public_ranking` conservé.
- `MarketplaceSettings` : ajout `duplicate_contact_window_hours` (défaut 24, >= 1) à la place de `DUPLICATE_CONTACT_WINDOW`.
- `OfferInfo` (dataclass de service) : ajout `is_hidden_by_moderation`, `seller_context_type`, `seller_context_id` (propriétés : `USER` et `seller_id` pour l'instant ; L0-09 les remplace par l'organisation sans changer les appelants).
- Nouvelle fonction de lecture `get_review_contact(offer_id, user_id) -> ReviewContact | None` (`contact_event_id`, `channel`, `recorded_at` du plus ancien contact de l'auteur sur l'offre ; tous canaux, D14).

### 3.5 `visibility.RankingSettings` (ligne unique)

Champs finals : `weight_views` 1, `weight_favorites` 3, `weight_contacts` 5, `weight_shares` 8, `recency_half_life_hours` 72, `proximity_same_commune` 1,2, `proximity_same_city` 1,1, `proximity_default` 1,0.
Supprimés : `weight_likes`, `weight_comments`, `trust_factor_min`, `trust_factor_max`.
`clean()` (pris en compte par l'admin) : poids >= 0 ; demi-vie > 0 ; chaque proximité >= 1 ; `same_commune >= same_city >= default`. Messages en français.

### 3.6 `identity`

Suppression de `User.trust_score`, `User.reviews_count`. Dans `services.py` : suppression de `set_reputation` ; `SellerSummary` perd `trust_score`, `reviews_count`. Nouvelle fonction-couture `acts_for_context(user_id, context_type, context_id) -> bool` (aujourd'hui : `context_type == 'USER' and user_id == context_id` ; L0-09 l'étend aux organisations) et `public_display_name(full_name)` (prénom + initiale du nom, D11 proposé). `admin.py` : retirer les deux colonnes de `list_display`.

### 3.7 `moderation`

`Report` : ajout du motif `CONTACT_FICTIF` (« Contact fictif ») dans `REASON_CHOICES` (CharField(20), valeur de 14 caractères). Réservé aux signalements de cible `review` faits par le vendeur concerné : contrôle dans `moderation.services.ensure_can_report` via `reviews.services.is_review_seller(review_id, user)` (appel de service, pas de modèle). `setup_roles` : remplacer `reviews.trustscoresettings` par `reviews.reviewsettings`.

## 4. Ce qui disparaît (liste exhaustive à vérifier par `grep`)

| Zone | Éléments supprimés |
|---|---|
| `identity` | `User.trust_score`, `User.reviews_count`, `set_reputation`, champs de `SellerSummary`, colonnes d'admin |
| `reviews` | `TrustScoreSettings` (+ admin), `Deal` (+ admin, `DealSerializer`, `DealViewSet`, `urls_deals.py`), `recompute_trust_score`, `get_min_reviews_to_display` (remplacé par `ReviewSettings`), `signals.py` et `AppConfig.ready`, `Review.deal/reviewed_user/rating`, constantes de seuils |
| `visibility` | paramètre `trust_score` et facteur T de `compute_score`, `trust_factor_*`, `weight_likes`, `weight_comments` |
| `marketplace` | `refresh_seller_offer_scores`, `get_contact_sender_ids` (si plus utilisé), `TRUSTED_SELLER_MIN_*`, `SellerSerializer.{trust_score, reviews_count, is_new_seller, is_trusted_seller}`, `Offer.comments_count`, `avg_rating = trust_score` |
| Racine | route `api/reputation/` dans `backend/urls.py`, portée de limitation `deal` dans `settings.py` |
| Clés d'API | voir 7.4 |
| Front | `TrustScore.tsx`, `lib/trust.ts` (ses fonctions utiles `sellerDisplayName` et `getPostBadges` sont déplacées), `StatusBadge kind="reliable"`, type de badge `reliable`, clés i18n `trust.*` liées au score, textes « Trust Score », « Vendeur fiable », « Trust & Engage », « affaire conclue » |

Vérification : `grep -rniE "trust_?score|trust_factor|is_trusted|Deal\b|set_reputation|reputation|comments_count|recompute_trust" backend/apps connect-grow/src` ne renvoie rien (hors commentaires d'historique des ADR).

## 5. Événements (outbox, ADR 0003)

| Événement | Changement |
|---|---|
| `reviews.review_posted` | **Version 2.** Payload : `review_id, recipient_id, author_id, offer_id, offer_title, seller_context_type, seller_context_id`. `recipient_id` remplace `reviewed_user_id` (utilisateur à notifier ; L0-09 résoudra les membres d'une organisation). Abonné `notifications.notify_review_posted` mis à jour ; il refuse la version 1 (`PermanentEventError`). |
| `reviews.review_replied` | Inchangé (v1). |
| `reviews.crossed_reviews_detected` | **Version 2.** `deals_count` devient `reviews_count`. Abonné `moderation.file_crossed_reviews_report` mis à jour. |
| `marketplace.contact_recorded` | v1, clé `channel` ajoutée au payload (compatible). |
| `visibility.ranking_settings_changed` | **Nouveau** (v1), publié par l'admin dans la transaction de sauvegarde des réglages. Payload : `changed` (liste de noms de champs). Abonné `marketplace.refresh_all_scores` (idempotent : recalcul depuis la source). |
| `reviews.reputation_changed` | N'existe pas dans le catalogue : rien à retirer. Le recalcul synchrone par signaux disparaît. |

Les versions 2 sont déclarées dans `platform_core/catalog.py` (`EventType(name, version=2)`). Pas de migration d'événements en attente : en développement, vider l'outbox (`purge_outbox` ou base recréée).

Le marquage `is_counted`, `contacts_count` et le recalcul du score se font **dans le domaine `marketplace`, dans la transaction du contact** : pas d'événement nécessaire.

## 6. Classement organique

### 6.1 Formule et où chaque terme vit

| Terme | Valeur | Où |
|---|---|---|
| P | 1. Recherche et catégorie = **filtre strict** (D9, déjà en place dans `apply_filters`) | lecture |
| E | `1 + ln(1 + w_v*vues + w_f*favoris + w_c*contacts + w_s*partages)` | stocké (avec R) |
| R | `0,5 ** (âge_heures / demi_vie)` (équivaut à `exp(-ln2/demi_vie * âge)`) | stocké (avec E), rafraîchi par cron |
| D | `proximity_same_commune` / `proximity_same_city` / `proximity_default` | lecture, dans le tri SQL |

`Offer.visibility_score = E x R`. Aucun terme de note, aucun badge de note. Pas de terme de promotion (règle 5 : le Sponsorisé est séparé, L1).

Signature cible : `visibility.services.compute_score(*, views, favorites, contacts, shares, created_at, settings_row=None, now=None) -> float` (E x R seulement). Nouvelle `visibility.services.get_proximity_weights() -> (same_commune, same_city, default)`. Aucune pondération codée en dur dans le calcul. Compteurs sources : vues et partages = `visibility.total_views/total_shares` ; favoris = `Offer.likes_count` ; contacts = `Offer.contacts_count`.

### 6.2 Proximité à la lecture (D10)

- Paramètre de requête **`near=<uuid commune>`** (nouveau, ne réutilise pas `commune` qui est un filtre). À défaut, `request.user.commune_id` si connecté, sinon aucune proximité.
- Pour le tri par défaut `-visibility_score` uniquement : `order_by(-(visibility_score * D), -created_at, id)` où D est un `Case(When(commune_id=near, then=w1), When(commune_id__in=<communes de la même ville via catalog.services>, then=w2), default=w3)` enveloppé dans `ExpressionWrapper(FloatField())`. La liste des communes d'une ville vient de `catalog_services.get_commune_ids_for_city` (plafonnée). Les autres ordres (`-created_at`, `price`...) ne changent pas. Le tri est entièrement en SQL : la pagination reste exacte. `id` ajouté en dernier départage les égalités (pages stables).
- La réponse n'expose pas D. `visibility_score` reste E x R.

### 6.3 Recalcul : qui le déclenche, idempotence

Un seul point d'entrée par offre : `marketplace.services.refresh_visibility_score(offer)` (recalcul depuis les compteurs, jamais d'incrément) et un point en lot `refresh_all_scores()` (renvoie le nombre d'offres). Déclencheurs :

1. Vue ou partage nouveau : abonné `marketplace.sync_offer_views/shares` -> `sync_offer_engagement` (existant ; recalcule vues et partages depuis `visibility`, **puis** score).
2. Favori ajouté ou retiré : existant (`_refresh_after_like_change`).
3. Contact enregistré : dans `create_contact_event`, même transaction : calcul de `is_counted`, recalcul `contacts_count = COUNT(ContactEvent is_counted)` de l'offre, puis score.
4. Récence : nouvelle commande **`python manage.py refresh_visibility_scores`** (cron toutes les heures, `15 * * * *`) -> `refresh_all_scores()`, affiche « N offres mises à jour ». Ligne ajoutée à `backend/cron/crontab` et au test de crontab (`common/tests.py`).
5. Réglages modifiés : événement `visibility.ranking_settings_changed` (voir 5).
6. Action d'administration existante `POST .../posts/recalculate_all_scores/` conservée.

Rejouer n'importe lequel de ces déclencheurs donne le même résultat à `now` près. Les compteurs `visibility.DailyVisibilityCounter.contacts` (graphiques du tableau de bord, cron `refresh_daily_contacts`) utilisent désormais le même filtre `is_counted` dans `count_contacts_by_offer` : une seule définition du « contact ».

## 7. Contrat d'API figé

Chemins historiques conservés jusqu'à L0-11 (préfixe `/api/`). Authentification JWT (`Authorization: Bearer`). Listes : tableau simple, ou enveloppe `{count,next,previous,results}` si `?page=` ou `?page_size=` (`OptionalPagination`, existant). `L0-11` basculera tout sous `/api/v1/`.

**Format d'erreur** (T1 ajoute `common.exception_handler`, additif) : toute erreur non liée à un champ a pour corps `{"detail": "<message en français>", "code": "<code_machine>"}`. Erreurs de validation de champs : `{"<champ>": ["<message>"]}` (DRF standard). Les anciens corps `{"error": "..."}` des avis disparaissent. Les messages sont ceux du tableau ; le front se fonde sur `code`.

### 7.1 Notes affichées (dans les offres)

`GET /api/marketplace/posts/` et `GET /api/marketplace/posts/{id}/` : chaque offre porte

```json
"offer_rating":  {"average": 4.2, "count": 5},
"seller_rating": {"average": null, "count": 2}
```

- `average` : moyenne arithmétique arrondie à 1 décimale, demi supérieur ; `null` si `count < ReviewSettings.min_reviews_to_display` ; `count` toujours exact (avis masqués exclus). Aucun champ ne fusionne les deux notes.
- `seller_rating` désigne le contexte vendeur de l'offre. La page profil vendeur lit `seller_rating` et `seller.date_joined` (ancienneté, source unique : « Sur Connecte+ depuis <mois année> » formaté par le front).
- Objet `seller` : `id, full_name, user_type, date_joined, photo, business_profile`. **Disparaissent** : `trust_score, reviews_count, is_new_seller, is_trusted_seller`. Offre : `comments_count` disparaît. `is_sponsored` reste.
- Tri : `ordering` et ses valeurs inchangés (`-visibility_score` par défaut). Nouveau paramètre optionnel `near=<uuid commune>` (voir 6.2). Un identifiant invalide est ignoré (pas d'erreur).

### 7.2 Avis

Base : `/api/interactions/reviews/`.

**Objet `Review` (réponse)** :
```json
{"id":"uuid","post":"uuid|null","user_id":"uuid","user_name":"Marie K.",
 "offer_rating":4,"seller_rating":5,"content":"...",
 "source":"CONTACT","reply_content":null,"reply_at":null,
 "created_at":"iso","edited_at":null,
 "is_post_owner":false,"can_edit":true}
```
`source` vaut toujours `"CONTACT"` (libellé front « Avis après contact »). `user_name` = nom public (prénom + initiale, D11 à confirmer). `rating`, `deal`, `reviewed_user_id` disparaissent. Le canal du contact n'est pas exposé publiquement.

| Méthode et URL | Permission | Corps | Succès |
|---|---|---|---|
| `GET /reviews/?post=<uuid>` ou `?seller=<uuid>` | public | - | 200 liste (avis masqués exclus, plus récents d'abord ; `seller` = identifiant du contexte vendeur) |
| `GET /reviews/{id}/` | public (un avis masqué n'est visible que de son auteur et du staff) | - | 200 |
| `GET /reviews/eligibility/?post=<uuid>` | public | - | 200 `{"can_review":bool,"reason":null\|"login_required"\|"own_offer"\|"no_contact"\|"too_early"\|"already_reviewed"\|"offer_unavailable","available_at":"iso\|null","review_id":"uuid\|null"}` |
| `POST /reviews/` | connecté | `{"post":uuid,"offer_rating":1-5,"seller_rating":1-5,"content":"10-500 car."}` | 201 `Review` |
| `PATCH /reviews/{id}/` | auteur | sous-ensemble de `offer_rating, seller_rating, content` (`post` ignoré) | 200 `Review`, `edited_at` renseigné |
| `DELETE /reviews/{id}/` | auteur | - | 204 |
| `POST /reviews/{id}/reply/` | vendeur concerné (`acts_for_context`) | `{"reply_content":"1-500 car."}` | 200 `Review` |

**Codes d'erreur de `POST /reviews/`** (ordre d'évaluation) :

| HTTP | `code` | Cas / message |
|---|---|---|
| 400 | (champs) | note absente ou hors 1..5 ou non entière ; commentaire < 10 ou > 500 caractères après `strip` ; `post` absent ou mal formé ; clé inconnue `deal` ignorée |
| 401 | `not_authenticated` | pas de jeton |
| 404 | `offer_not_found` | offre inconnue ou purgée ; « Annonce introuvable. » |
| 403 | `own_offer` | « Vous ne pouvez pas noter votre propre annonce. » |
| 403 | `not_eligible` | « Vous pourrez donner votre avis après avoir contacté le vendeur. » |
| 403 | `review_too_early` | contact depuis moins de `delay_after_contact_hours` ; message « Vous pourrez donner votre avis dans <durée>. » ; l'en-tête `Retry-After` n'est pas utilisé, `available_at` est dans `eligibility` |
| 409 | `already_reviewed` | « Vous avez déjà donné votre avis pour cette annonce. » (aussi sur `IntegrityError` concurrent) |
| 409 | `offer_unavailable` | offre en corbeille ou masquée par la modération ; une offre expirée, vendue ou en pause **reste notable** |
| 429 | `daily_limit` | « Vous avez atteint la limite de N avis par jour. » ; la suppression d'un avis ne libère pas de place ; le throttle DRF `review` (10/h) répond aussi 429 `throttled` |

Compte suspendu : `User.is_active=False`, il ne peut pas s'authentifier (401) ; aucune règle supplémentaire.

`PATCH`/`DELETE` : 403 `edit_window_closed` (au-delà de `edit_window_hours`, PATCH seulement), 403 `review_locked` (avis masqué ou signalement ouvert), 403 `not_author`. `reply` : 403 `not_seller`, 400 (champ `reply_content`), 409 `already_replied`. Le vendeur ne note pas l'acheteur : aucun endpoint.

Signalement « contact fictif » : endpoint existant `POST /api/moderation/reports/` avec `{"target_type":"review","target_id":"uuid","reason":"CONTACT_FICTIF","description":"..."}` ; 403 `not_seller` si l'appelant n'est pas le vendeur de l'avis. Le modérateur voit `contact_channel` et `contact_recorded_at` dans l'admin de `Review`.

### 7.3 Tableau de bord vendeur

`GET /api/marketplace/dashboard/stats/` (URL existante) : `summary.avg_rating` devient **moyenne des `seller_rating` visibles du vendeur** (1 décimale, demi supérieur, `null` s'il n'a aucun avis, sans seuil d'affichage) et `summary.review_count` le nombre d'avis visibles. Les autres champs sont inchangés.

### 7.4 Résumé de ce qui disparaît côté front

Clés : `trust_score`, `reviews_count`, `is_new_seller`, `is_trusted_seller`, `comments_count` (offre, utilisateur, vendeur), `rating` et `deal` (avis), `reviewed_user_id`. Endpoints : tout `/api/reputation/deals/` (404). Type `PostBadge` : `"reliable"` retiré.
Nouveautés : `offer_rating`, `seller_rating`, `offer_rating.average == null` (« Pas encore d'avis »), `offer_rating.count`, `source`, `edited_at`, `offer_rating`/`seller_rating` dans `Review`, endpoint `eligibility`, paramètre `near`.

### 7.5 Ce qui ne bouge pas

`POST /api/interactions/contacts/` (message) : même contrat. Son effet nouveau est interne (`channel='MESSAGE'`, `is_counted`, `contacts_count`). La révélation du téléphone et les canaux `CALL`/`WHATSAPP` relèvent de L0-10a (hors de cet ADR).

## 8. Migrations

Aucune donnée de production, aucune migration de données : décision de **réécrire les `0001`** des cinq apps dont le schéma change (accord donné dans la demande de cadrage ; CLAUDE.md §9 : à confirmer en section 11) : `identity`, `marketplace`, `visibility`, `reviews`, `moderation`. Les autres apps (`catalog`, `messaging`, `notifications`, `payments`, `platform_core`) gardent leur `0001`, qui ne dépend que de `identity.0001_initial` (nom conservé).

Procédure (T1, une seule fois, par un seul agent) :
1. Poser le tag Git `pre-L0-07-migrations`.
2. Supprimer `migrations/0001_initial.py` des cinq apps (garder `__init__.py`).
3. `python manage.py makemigrations identity marketplace visibility reviews moderation` (une passe, pour que les dépendances soient cohérentes).
4. Vérifier `python manage.py makemigrations --check --dry-run`.
5. Supprimer la base de développement locale (`db.sqlite3` hors dépôt), puis `migrate`, `setup_roles`, `seed_catalog`.
6. `python manage.py test apps` sur base vierge.
Retour arrière : `git revert` ou retour au tag ; il n'y a pas de données à restaurer. **Après T1, T2 et T3 ne génèrent aucune migration** : tout le schéma (y compris `ContactEvent.channel`, `Offer.contacts_count`, `RankingSettings` final, `ReviewSettings`) est posé par T1. Si T2 ou T3 découvre un champ manquant, il le signale au chef de projet (pas de seconde réécriture sans accord).

Portabilité : `Avg`, `Count`, `Case/When`, `ExpressionWrapper`, aucun `__date`, aucune contrainte conditionnelle, longueurs explicites, `CharField(10/20)` pour les énumérations.

## 9. Plan de tâches

Ordre : **T1 puis (T2 en parallèle de T3 et de T4)**. T4 démarre dès la validation de cet ADR avec des mocks.

### T1 — dev-backend : schéma final, retrait du Trust Score, avis simples (L0-07 a/b/c, L0-10 b)
Branche `feat/L0-07-retrait-trust-score`. Zones : `identity/{models,services,admin}.py`, `reviews/*` (sauf `tests_*` hors de la tâche, à adapter), `visibility/{models,services,admin}.py`, `marketplace/{models,services,serializers,stats_views}.py` (retrait et couture de lecture uniquement), `moderation/{models,services,events}.py`, `notifications/events.py`, `platform_core/catalog.py`, `common/{contexts,exception_handler}.py`, `backend/{urls,settings}.py`, `setup_roles`, les cinq `0001`.
Contenu : section 3 en entier (modèles et migrations), section 4 (suppressions), 7.1 / 7.3 (lecture des moyennes), `POST/PATCH/DELETE/reply/GET` des avis avec condition « contact existant » (sans délai ni réglages dynamiques : lecture directe de `ReviewSettings` pour le seuil et la limite, valeurs par défaut), `reconcile_seller_flag`, avis croisés recomptés par couples (auteur, offre) et événements v2, `compute_score` réduit à E x R avec les nouveaux champs (contacts lus de `Offer.contacts_count`, encore 0), format d'erreur, `moderation` motif `CONTACT_FICTIF` (modèle seulement).
Critères : AC de L0-07-a, b, c de la spec ; `grep` de la section 4 vide côté backend ; `makemigrations --check` propre ; `migrate` sur SQLite vierge ; tests sur : moyennes (seuil, masqués, arrondi demi supérieur), drapeau « dernière note vendeur », unicité auteur-offre, suppression de `/api/reputation/deals/` (404), absence des clés disparues, `acts_for_context`, événements v2 de bout en bout (`dispatch_outbox`), `python manage.py test apps` vert.

### T2 — dev-backend : classement organique (L0-08 a/b)
Branche `feat/L0-08-classement-organique`, **après T1**. Zones : `visibility/{services,admin,tests}.py`, `marketplace/{services,views,management/commands/refresh_visibility_scores.py,tests*}.py`, `backend/cron/crontab`, `common/tests.py` (test de crontab), `platform_core/catalog.py` (une ligne), `marketplace/events.py`. Aucune migration.
Contenu : section 6 : `is_counted` + `contacts_count` dans `create_contact_event` et `count_contacts_by_offer`, `duplicate_contact_window_hours` lu en base, tri avec D et paramètre `near`, commande et cron horaire, `clean()` de `RankingSettings` (si T1 ne l'a pas fait), admin avec `AuditLog` (ancienne et nouvelle valeur) et événement `ranking_settings_changed` + abonné.
Critères : AC de L0-08-a et L0-08-b ; deux offres identiques dont les vendeurs ont des notes différentes ont le même score ; E = 1 sans interaction ; R = 0,5 à 72 h (et 0,125 à 24 h de demi-vie) ; D 1,2/1,1/1,0 testé via l'API (`near=`) sur l'ordre des résultats et la pagination ; modification d'un réglage -> `AuditLog` + recalcul après `dispatch_outbox` ; la commande affiche le nombre d'offres ; aucun test ne référence `trust_*`.

### T3 — dev-backend : avis après contact et garde-fous (L0-10 a/c)
Branche `feat/L0-10-avis-apres-contact`, **après T1, en parallèle de T2**. Zones : `reviews/{services,views,serializers,admin}.py` et leurs tests, `moderation/{services,serializers}.py` (restriction `CONTACT_FICTIF`), `marketplace/services.py` **uniquement** la fonction `get_review_contact` si T1 ne l'a pas finie (convenir qu'elle est dans T1). Aucune migration.
Contenu : lecture de tous les seuils dans `ReviewSettings` (délai contact -> avis, limite quotidienne, fenêtre de modification, avis croisés), `GET eligibility`, codes d'erreur de 7.2 (429 `daily_limit`, 403 `review_too_early`, 409), `edited_at`, snapshot `contact_*` à la création, signalement `CONTACT_FICTIF`, admin `ReviewSettings` / `Review` avec `AuditLog` sur changement de réglage et sur masquage (via `services.set_review_hidden`, qui reconcile le drapeau vendeur), avis croisés 3 en 30 jours -> signalement automatique sans blocage.
Critères : AC de L0-10-a, b, c ; test de chaque ligne du tableau d'erreurs de 7.2 ; le délai est réglable (0 puis 24 h) ; un contact `CALL` ou `WHATSAPP` (créé directement via le service) ouvre le droit ; masquer un avis fait sortir ses notes des moyennes et reconcile le drapeau.

### T4 — dev-frontend : retrait et nouveaux blocs de notes (L0-07 front, L0-10 front), parallèle
Branche `feat/L0-07-front-notes`. Zone : `connect-grow/src/**` uniquement (`api/types.ts`, `components/common/{TrustScore,StatusBadge,SellerCard,PostCard,index}`, `lib/trust.ts`, `components/post/ReviewsSection.tsx`, `hooks/use-reviews.ts`, `pages/{Dashboard,SellerProfile,PostDetail,Index,DesignSystem,Settings}.tsx`, `components/landing/*`, `i18n/locales/fr.ts`).
Contenu : section 7 ; deux blocs « Note de l'offre » / « Note du vendeur » avec « Pas encore d'avis », nombre d'avis et « Sur Connecte+ depuis <mois année> » ; libellé accessible « Note de l'offre : 4,2 sur 5, 5 avis » ; carte d'offre = note d'offre seulement ; formulaire à deux notes et commentaire 10-500 ; bouton « Donner mon avis » piloté par `eligibility` (jamais déduit côté client) ; affichage des codes d'erreur 7.2 ; mention « modifié » et libellé « Avis après contact » ; tableau de bord (`avg_rating` nullable) ; suppression de tout ce qui figure au tableau de la section 4 ; textes d'accueil réécrits sans « Trust Score » ni « affaire conclue ». Mocks MSW ou fixtures jusqu'à ce que T1 soit fusionnée, puis intégration réelle.
Critères : `npm run lint && npm run test && npm run build` verts ; `grep` de la section 4 vide côté front ; tests des composants (seuil, `null`, accessibilité).

Ensuite : `relecteur-code` après chaque tâche ; `auditeur-securite` sur T3 (anti-abus, données affichées, nom public de l'auteur) ; `qa-testeur` après T1+T2+T3+T4 (recette L0-07, L0-08, L0-10) ; le chef de projet met à jour `BACKLOG.md` (ajout du badge « Vendeur fiable » à L0-07, de la suppression de `Deal` à L0-10) et `JOURNAL.md`.

Zones disjointes : T2 ne touche pas `reviews/` ; T3 ne touche ni `visibility/` ni la logique de score ni les migrations ; seul `platform_core/catalog.py` est touché par T1 (versions 2 + `ranking_settings_changed` déclaré d'avance) pour que T2 et T3 ne s'y rencontrent pas.

## 10. Dettes et risques

- **`Review.user` en CASCADE** : la fermeture d'un compte supprimerait ses avis, contre CDC §3.16 (avis conservés). À traiter avec l'anonymisation de compte (hors cet ADR).
- **`Offer.seller` FK utilisateur** et `seller_context_*` en `USER` : à remplacer par `organization_id` en L0-09 ; les couplages sont isolés dans `OfferInfo.seller_context_*`, `identity.acts_for_context` et `recipient_id`.
- **Avis croisés** : calculés entre `USER` seulement ; à revoir pour les organisations (L0-09).
- **`visibility_rank`** (« Elite/Standard/Faible », seuils 10 et 50 codés en dur dans `OfferSerializer`) : contraire à la règle 11 et sans lien avec le nouveau score ; à rendre configurable ou supprimer (proposition : supprimer en L0-11).
- **`likes_count` incrémental** (favoris) : peut dériver ; le score est recalculé depuis lui. Recompter depuis `Favorite` dans `refresh_all_scores` est recommandé (T2).
- **Tri avec proximité** sans index utile : acceptable aux volumes visés, à mesurer au passage MySQL.
- **Version 2 des événements** : un `dispatch_outbox` avec des livraisons v1 en attente les met `dead` (normal en développement).
- **D3 et D11** attendent le client : l'API renvoie `count` exact, `average: null` sous le seuil ; `user_name` est formaté par une fonction unique (`identity.public_display_name`).
- Le texte « modifié » et le délai de 24 h modifient la fluidité d'usage : à valider en recette.

## 11. Points à faire valider par l'utilisateur

1. Réécriture des `0001` de cinq apps plutôt que des migrations `0002` (CLAUDE.md §9 : accord requis).
2. Deux tables de réglages (`reviews.ReviewSettings`, `marketplace.MarketplaceSettings`) au lieu d'une seule « Avis et contact » (frontière entre domaines).
3. Règle « la dernière note vendeur compte » par un drapeau recalculé en service ; moyennes calculées à la lecture, jamais stockées.
4. Score stocké E x R ; D appliqué à la lecture avec le paramètre `near` (repli : commune du profil) ; recalcul horaire par cron.
5. Passage de la limite quotidienne d'avis de 400 à **429** et unification du format d'erreur `{detail, code}` (changement visible du front).
6. Événements `review_posted` et `crossed_reviews_detected` en version 2.
7. Prénom + initiale comme nom public d'auteur par défaut, en attendant le client (D11).
8. Un contact `CALL` ou `WHATSAPP` ouvre le droit d'avis dès aujourd'hui côté modèle (D14), même si ces canaux n'existent qu'avec L0-10a.


## Décisions du chef de projet (09/10/2026)

- **Migrations :** pas de réécriture des `0001` (CLAUDE.md §9 : accord de l'utilisateur pour toute migration déjà partagée). T1 génère des migrations `0002` (suppressions et ajouts) par app concernée. La procédure « tag `pre-L0-07-migrations` + base de dev recréée » reste valable pour la base locale. Un regroupement pré-production pourra être décidé plus tard avec l'utilisateur.
- **Validés :** deux tables de réglages (`reviews`, `marketplace`) ; limite quotidienne d'avis en 429 et format d'erreur `{detail, code}` ; événements `review_posted` et `crossed_reviews_detected` en version 2 ; délai de 24 h contact→avis ; la dernière note vendeur compte ; nom d'auteur « prénom + initiale » par défaut (D11, en attente du client).
- **Dettes :** `Review.user` en CASCADE (CDC §3.16), seuils de `visibility_rank` en dur, dérive de `likes_count`.


## État d'exécution

### T1 (branche `feat/L0-07-retrait-trust-score`, 09/10/2026) : fait

- **Migrations (écart avec la section 8, décision du chef de projet)** : aucun `0001` réécrit ; une migration `0002` par app touchée (`identity`, `marketplace`, `visibility`, `moderation`, `reviews`). Celle de `reviews` (`0002_avis_apres_contact`) supprime puis recrée `Review` et supprime `Deal` et `TrustScoreSettings` : les anciens avis (sans preuve de contact ni note vendeur) ne sont pas conservés, ce qui suppose une base sans donnée à garder. Vérifié : `migrate` sur base vierge et depuis l'état `0001` (base migrée avant T1, sans donnée) ; `makemigrations --check` propre.
- **Livré** : section 3 (modèles, `ReviewSettings`, `MarketplaceSettings.duplicate_contact_window_hours`, `RankingSettings` final avec `clean()`, `ContactEvent.channel/is_counted`, `Offer.contacts_count`), section 4 (retraits vérifiés par `grep` : seules des assertions négatives de tests et une phrase du README citent encore les anciens noms), section 5 (événements `review_posted` et `crossed_reviews_detected` en version 2, `channel` dans `contact_recorded`), 7.1 et 7.3 (notes calculées à la lecture, `avg_rating` du tableau de bord), 7.2 hors `eligibility` et hors garde-fous de T3, format d'erreur `{detail, code}`.
- **Anticipé sur T2** : `visibility.ranking_settings_changed` (publié par l'admin dans la transaction, abonné `marketplace.refresh_scores_after_ranking_change`), journalisation des changements de réglages (`SETTINGS_CHANGED`, ancienne et nouvelle valeur) pour `RankingSettings`, `ReviewSettings`, `MarketplaceSettings` et `VisibilitySettings` via `common.admin_mixins.SingletonSettingsAdminMixin`, `visibility.services.get_proximity_weights`.
- **Reste pour T2** : marquage `is_counted` et recalcul de `contacts_count` dans `create_contact_event` (point d'extension commenté), filtre `is_counted` dans `count_contacts_by_offer`, tri avec D et paramètre `near`, commande `refresh_visibility_scores` et cron, recompte de `likes_count`.
- **Reste pour T3** : `GET eligibility`, délai `delay_after_contact_hours` (point d'extension dans `reviews.services.ensure_can_review`, `review_too_early`), restriction du motif `CONTACT_FICTIF` au vendeur concerné (`ensure_can_report`), `is_review_seller`.
- **Précisions de comportement** : l'unicité `(auteur, offre)` répond 409 `already_reviewed` (vérification préalable puis `IntegrityError`) ; `PUT` n'est plus routé sur `/reviews/` ; un avis modifié qui n'est pas le plus récent du couple ne change pas la note vendeur ; `summary.review_count` du tableau de bord compte les avis visibles reçus, `avg_rating` la moyenne des dernières notes vendeur visibles (sans seuil).

### T1, corrections après relecture et audit (aller-retour 1)

- **Bornes des réglages** (migrations `0003_bornes_reglages` de `reviews`, `marketplace`, `visibility`) : validateurs de champ et `clean()` ; plafonds : fenêtre de modification 8760 h, délai après contact 168 h, fenêtre d'avis croisés 365 j, seuil d'avis croisés 50, seuil d'affichage et limite quotidienne 100, fenêtre de doublon de contact 8760 h, poids 1000, demi-vie 8760 h, proximité 5.
- **Verrouillage** : `update_review` et `delete_review` relisent l'avis sous `select_for_update()` dans une transaction et contrôlent l'état (masqué, signalé, répondu) sur cette ligne ; `reconcile_seller_flag` verrouille les avis du couple ; `ReviewAdmin` écrit dans `transaction.atomic()`. (SQLite ignore le verrou de ligne ; il prendra effet avec MySQL.)
- **Suppression** : journalisée (`REVIEW_DELETED`) ; refusée si le vendeur a répondu (`review_locked_after_reply`, choix : refus plutôt que journalisation seule) ; ré-écriture d'un avis pour la même offre interdite pendant `edit_window_hours` (`review_recently_deleted`, 409) via `DeletedReviewMark` (une ligne par auteur et offre, unicité inconditionnelle). La modification est aussi refusée après la réponse.
- **Énumération** : offre inconnue, purgée, en corbeille ou masquée donne la même réponse que l'absence de contact (403 `not_eligible`) ; `offer_not_found` et `offer_unavailable` ne sont plus renvoyés par `POST /reviews/`.
- **Auteur** : `user_id` retiré de la réponse publique ; `is_mine` le remplace ; `can_edit` est faux après une réponse du vendeur.
- **Limites connues jusqu'à T3** : le motif `CONTACT_FICTIF` est provisoirement accepté pour toute cible et tout utilisateur (la restriction au vendeur concerné arrive avec T3) ; le délai contact vers avis (`delay_after_contact_hours`) n'est pas encore appliqué.
- **Dette** : les avis croisés ne sont détectés qu'en réciprocité A vers B ; une alerte sur les pics d'avis 5 étoiles et sur les comptes récents reste à concevoir.


### T2 (branche `feat/L0-08-classement-organique`, 09/10/2026) : fait

- Aucune migration. `is_counted`/`contacts_count` dans `create_contact_event` (même transaction), filtre `is_counted` dans `count_contacts_by_offer`, score E x R recalculé depuis les sources (`refresh_all_scores` recompte `likes_count` et `contacts_count`), commande `refresh_visibility_scores` (cron :15), tri `visibility_score x D` en SQL avec `near` (repli : commune du profil), tie-break `-created_at` puis `id`.
- Écart de test T1 : `test_ratings_do_not_change_the_organic_score` crée maintenant les mêmes contacts sur l'offre jumelle (le recomptage à la source rend les contacts réels).

### T3 (branche `feat/L0-10-avis-apres-contact`, 09/10/2026) : fait

- **Livré** : `GET /reviews/eligibility/` (`reviews.services.assess_eligibility`, partagé avec `POST`), délai `delay_after_contact_hours` (borne `available_at` incluse, calculé depuis le plus ancien contact, tous canaux), code `review_too_early` avec durée en français, signalement `CONTACT_FICTIF` réservé au vendeur concerné (`is_review_seller`, 403 `not_seller`, 400 `invalid_reason`, 409 doublon ouvert), journalisation `CONTACT_FICTIF_REPORTED`, suites d'un signalement validé (`moderation.apply_resolution` -> `reviews.reject_fictitious_contact` : avis masqué, `contact_rejected`), même effet depuis l'admin des signalements. Aucune migration.
- **Écarts avec la section 7.2** (instruction du chef de projet) : `eligibility` exige l'authentification (401 sinon, donc pas de motif `login_required`) et est limité par la portée `review_eligibility` (120/h) ; une offre inconnue ou non publique que l'appelant n'a pas contactée répond 404 `offer_not_found` (corps identique) ; nouveau motif et code `contact_rejected` (403) ; l'évaluation place `already_reviewed` et `offer_unavailable` avant `too_early`, et `offer_not_found` (404) l'emporte sur `not_eligible` pour une offre non publique sans contact.
- **Notification du modérateur** : par les chemins existants, soit la file des signalements (liste filtrable par statut, compteur `pending_reports_count`) ; aucune notification individuelle n'existe pour les modérateurs.

### Intégration T1 corrigé + T2 + T3 (branche `integ/L0-07-08-10`) : état final

- **Énumération (arbitrage final)** : offre inconnue, ou non publique (corbeille, masquée, hors ligne) sans contact de l'appelant et dont il n'est pas le vendeur : 404 `offer_not_found`, corps identique, dans `POST /reviews/` comme dans `GET /reviews/eligibility/`. Aucun contact sur une offre publique : 403 `not_eligible` (motif `no_contact`). Cela remplace la ligne « Énumération » des corrections T1 (qui renvoyait 403 `not_eligible` pour tout) ; celui qui a contacté une offre devenue indisponible reçoit 409 `offer_unavailable`.
- **Ordre final** : offre inconnue (404), `own_offer`, aucun contact, `contact_rejected`, `already_reviewed`, `recently_deleted` (code `review_recently_deleted`, 409, `DeletedReviewMark` de T1), `offer_unavailable`, `too_early`.
- **Contrat public** : `user_id` absent des avis, `is_mine` à la place ; `can_edit` faux après réponse du vendeur ; `review_locked_after_reply` ; l'éligibilité est authentifiée et renvoie `can_review` (pas de motif `login_required`). Les « limites connues jusqu'à T3 » de T1 sont levées.
- **Adaptations de tests** : `ReviewsTestBase` fixe `delay_after_contact_hours` à 0 h (le défaut de 24 h bloquerait tous les tests de création) et `tests_privacy` aussi pour son cas d'écriture ; les tests d'énumération de T1 attendent 404 pour l'offre non publique sans contact.

### Corrections d'intégration après relecture et audit (aller-retour 1)

- **Recours de l'auteur d'un avis signalé « contact fictif »** : l'auteur est notifié (notifications `SYSTEM`) au dépôt, puis à la décision (retenu : avis masqué ; rejeté : avis maintenu), avec un texte fixe en français qui ne nomme que « le vendeur ». Il peut déposer **une** réponse de 1000 caractères au plus : `POST /api/moderation/reports/{id}/author-response/` `{"author_response": "..."}` (champs `Report.author_response` et `author_responded_at`, visibles du modérateur dans la file ; `AuditLog` `REPORT_AUTHOR_RESPONDED`). 404 pour toute autre personne ou tout autre motif, 400 si le texte est vide ou trop long, 409 `already_responded` ou `report_closed`.
- **Verrou limité** : tant qu'un signalement de motif grave (`Report.GRAVE_REASONS` : arnaque, contenu interdit, harcèlement, avis croisés, contact fictif) est ouvert, l'auteur ne peut pas **supprimer** son avis (`review_locked`) mais peut le **modifier**. Spam et « autre » ne verrouillent rien. Un avis masqué reste verrouillé.
- **Délai de traitement** : `moderation.ModerationSettings.report_processing_target_hours` (72 h, 1 à 720) ; le tableau de bord de modération expose `overdue_contact_fictif_count` (signalements « contact fictif » ouverts au-delà du délai). `fictitious_contact_daily_limit` (20, 1 à 200) plafonne les signalements de ce motif par vendeur et par jour (429 `report_daily_limit`).
- **`contact_rejected` dérive de l'état réel** : avis masqué ET signalement « contact fictif » traité. Choix : le réaffichage d'un avis par la modération est permis et **défait** `contact_rejected` (l'éligibilité redevient `already_reviewed`) ; la décision « Traité » reste dans l'historique.
- **Séries de signalements** : un avis dont un signalement « contact fictif » a été rejeté ne peut plus être signalé pour ce motif (409 `report_already_rejected`) ; le rejet est journalisé (`CONTACT_FICTIF_REJECTED`, cible = l'avis).
- **Admin des signalements** : motif, cible, signaleur et description en lecture seule ; ajout interdit ; seules les transitions de l'API sont permises (un signalement clos ne se rouvre pas, erreur de formulaire) ; la sauvegarde passe par `resolve`/`reject`/`claim`, journalise `REPORT_STATUS_CHANGED` et applique `moderation.services.apply_decision` (masquage, notification). Un signalement clos entre-temps annule l'écriture et affiche un message.
- **Preuve de contact** : `ReviewSettings.min_account_age_hours` (24, 0 à 720) : un compte plus jeune reçoit 403 `account_too_new` (aussi motif d'éligibilité, avec `available_at` = la plus tardive des échéances compte et délai de contact) ; `delay_after_contact_hours` est borné à 1 h minimum (migration `reviews.0004`). `get_review_contact` ignore les contacts non comptés (`is_counted=False`). Limite connue : « un message effectivement échangé » (réponse du vendeur) comme preuve viendra avec L0-10a ; les tests fixent 0 h par `update()` (qui contourne le validateur), jamais en production.
- **Recalcul** : `refresh_all_scores` traite les offres par lots de 500 identifiants, chacun dans sa transaction ; le recomptage horaire corrige les dérives de `likes_count` et `contacts_count`. Limite connue de `create_contact_event` : le contrôle de doublon et le marquage `is_counted` ne sont pas atomiques entre deux requêtes simultanées (SQLite sérialise ; sous MySQL un doublon compté est possible), borné par ce recomptage horaire.
- **Liste des annonces** : `GET /api/marketplace/posts/` est limitée par la portée `offer_list` (600/h, par IP pour un anonyme, par utilisateur sinon). Le tri par pertinence (`visibility_score x D`) n'est pas indexé : à mesurer au passage MySQL, avec plafonnement au top N si besoin.
- **Migrations** : `moderation.0003_recours_auteur_reglages_moderation`, `reviews.0004_anciennete_compte_delai_minimal` ; aucune migration existante modifiée.
- **Adaptations de tests** : les tests fixent `delay_after_contact_hours=0` et `min_account_age_hours=0` par `update()` ; les tests de verrou attendent « suppression refusée, modification permise » pour un motif grave et « rien de verrouillé » pour spam/autre.
