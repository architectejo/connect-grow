# ADR 0002 — Réinitialisation des migrations, clés UUID et modules cibles

- **Statut :** accepté
- **Date :** 09/10/2026
- **Décideurs :** Anicet, Jonathan (IMARA TECH Group) ; rédaction : architecte-technique
- **Tâche :** L0-05 (exécution : voir « Plan d'exécution »)

## Contexte

- Le code existant (7 apps : `accounts`, `marketplace`, `interactions`, `reputation`, `ranking`, `moderation`, `payments`) a été écrit pour le CDC v1.0. Il compte 30 migrations, toutes à clé entière.
- Le CDC v1.2 impose : identifiants UUID (§11.1), un module Django par domaine (§5.3), aucune clé étrangère entre domaines sauf vers l'utilisateur, références par UUID (§5.4), événements via outbox (§5.4, `platform`).
- Écarts constatés dans l'existant :
  - `accounts.User.ville/commune` → `marketplace.City/Commune` ; `accounts.BusinessProfile.categories` → `marketplace.Category` ;
  - `marketplace.Post.category/commune`, `payments.Transaction.post`, `interactions.*.post`, `reputation.Deal.post`, `moderation.Sanction.related_post` → clés étrangères inter-domaines ;
  - `moderation.Report` et `AuditLog` utilisent `GenericForeignKey` (couplage à tous les modèles, `object_id` entier) ;
  - `moderation.ForbiddenItem` référence `marketplace.Category` ; `interactions` mélange avis, contacts, troc, messagerie, notifications, statistiques ;
  - `is_delete` (nullable, mal nommé) ; `Post` au lieu de `Offer`.
- Passer des clés entières à UUID par migration de données impose de réécrire toutes les clés étrangères, les index et les données. Aucune donnée de production n'existe : la base `db.sqlite3` et `media/` ne contiennent que des données de développement.
- Contrainte ADR 0001 : SQLite seul, code portable MySQL. Contrainte CLAUDE.md §9 : une migration déjà partagée ne se modifie pas sans accord ; une réinitialisation peut être décidée par ADR tant que le projet n'est pas en production. Le présent ADR en est l'accord.

## Options étudiées

1. **Migrer en place (int → UUID, déplacement de modèles entre apps).** Conserve l'historique, mais : changement de type de clé primaire sur User (clé référencée partout, y compris JWT, `auth`, `admin`) non supporté proprement par SQLite, déplacement de modèles entre apps (`SeparateDatabaseAndState`) fragile, 30 migrations à réécrire, valeur nulle puisque aucune donnée à préserver. Écartée.
2. **Réinitialiser en gardant la structure actuelle des apps** (UUID seulement). Réglerait les clés mais laisserait les clés étrangères inter-domaines et obligerait à une seconde réinitialisation pour le découpage en modules. Écartée.
3. **Réinitialiser une seule fois : UUID + modules cibles + découplage (retenue).** Un seul `0001_initial` par app, structure alignée sur le CDC §5.3 et §11.1.
4. **Reporter la réinitialisation à la mise en production.** Chaque nouveau module du lot 1 construit sur la mauvaise base ; coût croissant. Écartée.

## Décision

On réinitialise toutes les migrations en une seule opération, en passant à la structure cible :

1. **Clés primaires UUID** (`UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`) sur tous les modèles de domaine, y compris `User`. Classe abstraite commune dans `apps/common/models.py` : `id`, `created_at` (`auto_now_add`), `updated_at` (`auto_now`). Les tables techniques Django (`auth`, `contenttypes`, `sessions`, `admin`) restent inchangées.
2. **Modules cibles** (mapping ci-dessous), un `0001_initial` par app, générés par `makemigrations` après suppression des anciens fichiers de migration.
3. **Aucune clé étrangère entre domaines**, sauf vers `settings.AUTH_USER_MODEL`. Les autres références sont des `UUIDField(db_index=True)` nommés `<entité>_id` (ex. `category_id`, `commune_id`, `offer_id`). Pas d'accès ORM à un autre domaine : lecture via `services.py` du domaine propriétaire (méthodes par lot pour éviter les requêtes N+1).
4. **`is_delete` → `is_deleted`** (`BooleanField(default=False)`, non nul) ; **`Post` → `Offer`**, `PostImage` → `OfferImage`, `PostViewStat`/`PostUniqueView`/`ContactStat` → compteurs du module `visibility`.
5. **Génériques supprimés** : `moderation.Report` et `AuditLog` remplacent `content_type`/`object_id`/`GenericForeignKey` par `target_type` (`CharField(max_length=50)`, valeurs `offer`, `user`, `review`, `message`…) + `target_id` (`UUIDField`), index `(target_type, target_id)`. La résolution de la cible passe par un registre de services par type.
6. **Fidélité du portage.** L'opération déplace et renomme sans changer le comportement métier. Le retrait du Trust Score (L0-07), le compte à contextes (L0-09), le classement (L0-08) et l'avis après contact (L0-10) viennent ensuite, en migrations ordinaires `0002`.
7. **Le contrat HTTP ne change pas pendant la réinitialisation**, sauf les identifiants (chaînes UUID au lieu d'entiers). Les URL (`/api/posts/…`) et les clés JSON (`is_delete`, `post`…) sont conservées via `source=` dans les serializers jusqu'à L0-11, qui fait en une seule fois le passage à `/api/v1/`, `offers` et `is_deleted`. Le front ne casse ainsi qu'à deux endroits maîtrisés.

### Mapping apps actuelles → modules cibles

| Actuel | Cible | Remarques |
| --- | --- | --- |
| `accounts.User`, `OtpCode`, `KycDocument` | `identity` | `AUTH_USER_MODEL = 'identity.User'`. `ville`/`commune` deviennent `city_id`/`commune_id` (UUID). `KycDocument.business_profile` : FK interne à `identity`, conservée jusqu'à L0-09 (remplacée par `VerificationRequest`). Stockage privé KYC inchangé. |
| `accounts.BusinessProfile` | `identity` (transitoire) | `categories` M2M → table de liaison interne `category_id` (UUID) ; supprimé par L0-09 au profit d'`Organization`. `user_type` conservé jusqu'à L0-09. |
| `marketplace.City`, `Commune`, `Category` | `catalog` | Référentiels configurables (règle 11). `slug` unique explicite, `max_length` explicites. |
| `moderation.ForbiddenItem` | `catalog` | `category_id` interne à `catalog` ; `added_by` → utilisateur (FK autorisée). |
| `marketplace.Post`, `PostImage`, `Favorite`, `MarketplaceSettings` | `marketplace` | `Offer`, `OfferImage`, `Favorite`, `MarketplaceSettings`. `category_id`, `commune_id` en UUID. `Offer.seller` reste FK vers l'utilisateur (devient `organization_id` en L0-09). |
| `interactions.ContactRequest`, `ExchangeProposal` | `marketplace` | `ContactRequest` → `ContactEvent` (CDC §11.1). `ExchangeProposal` reste derrière l'interrupteur de L0-14. |
| `marketplace.PostViewStat`, `PostUniqueView`, `interactions.ContactStat` | `visibility` | `DailyVisibilityCounter` (offer_id, date, vues, contacts). `seller` : FK utilisateur conservée. |
| `ranking.RankingSettings` | `visibility` | Facteur de confiance retiré en L0-07/L0-08, pas pendant le portage. |
| `interactions.Review` | `reviews` | `offer_id` UUID ; `deal_id` UUID (voir ci-dessous). |
| `reputation.Deal`, `TrustScoreSettings` | `reviews` (transitoire) | Portés tels quels pour garder les tests verts, marqués « supprimés par L0-07 ». Le module `reputation` disparaît. |
| `interactions.Conversation`, `Message` | `messaging` | `offer_id` UUID ; participants : M2M vers l'utilisateur (autorisé). Réalise la préparation demandée par L0-15. |
| `interactions.Notification` | `notifications` | Inchangé hors UUID. |
| `moderation.Report`, `Sanction`, `AuditLog` | `moderation` | `target_type/target_id` ; `Sanction.related_offer_id`. `Appeal` viendra avec L1. |
| `payments.Transaction` | `payments` (gelée) | `offer_id` UUID ; refonte en L1-12. |
| — (nouveau) | `platform` | `OutboxEvent`, `FeatureFlag` (L0-16 ; les interrupteurs de L0-13 et L0-14 s'y appuient). Chemin `apps.platform`, label `platform` ; vérifier l'absence de collision avec le module standard `platform` (pas d'`apps/` dans `sys.path`). **Note (ADR 0003) : renommée `apps.platform_core`, label `platform_core`, pour supprimer tout risque de collision.** |
| — (nouveau) | `common` | Classe abstraite UUID + horodatages, utilitaires ; ce n'est pas un domaine, ne porte aucun modèle concret. |

Modules `profiles`, `social`, `promotion`, `events`, `subscriptions`, `campaigns`, `jobs`, `tenders` : non créés ici, ajoutés par leurs stories (une app vide n'apporte rien).

## Conséquences

**Code**
- Réécriture des imports : plus aucun `from apps.<autre>.models import …` ; usage de `services.py`. Les signaux inter-domaines (`reputation/signals.py`) deviennent des appels de service ou des événements outbox.
- Les filtres ORM à jointure (`category__slug`, `commune__city`, `seller__business_profile`) disparaissent : le `services.py` de `catalog` résout slugs/villes en UUID, et fournit des libellés par lot (`get_categories_by_ids`).
- `AUTH_USER_MODEL`, `INSTALLED_APPS`, `setup_roles`, admin, commandes cron (`purge_trash`, `expire_posts`, `cleanup_otp_codes`, `lift_expired_sanctions`, `refresh_dashboard_aggregates`) à adapter aux nouveaux noms d'apps.
- Contrôle de découplage : ~~ajout de `import-linter` (contrats : un domaine n'importe pas `models` d'un autre), à brancher en CI par `devops`. (caduc : remplacé par le test `ast` `DomainBoundariesTests`, voir notes R3)~~
- JWT : le claim `user_id` devient une chaîne UUID ; tous les jetons existants sont invalidés (sans importance en développement).

**Base et migrations**
- Une seule `0001_initial` par app, générée sur base vierge. Ordre de dépendance trivial : `identity` d'abord, puis tous les autres modules qui ne dépendent que de l'utilisateur. Aucune dépendance de migration entre domaines.
- Pas de migration inverse pour le reset. Retour arrière : tag Git `pre-reset-migrations` posé avant l'opération + copie de `db.sqlite3` hors dépôt.
- La base de développement est recréée (`migrate`, `setup_roles`, commande de données de départ `seed_catalog` dans `catalog` pour villes, communes, catégories, produits interdits ; données configurables, règle 11). Les médias de développement liés à d'anciennes lignes deviennent orphelins : à vider (`media/` non versionné).
- Portabilité MySQL : `UUIDField` est stocké en `CHAR(32)`, supporté sans réécriture. Les UUID v4 aléatoires fragmentent les index InnoDB ; acceptable aux volumes du projet, à réévaluer à F-01 (UUID v7 possible sans changement de schéma).

**Tests**
- Les 98 tests existants doivent être adaptés (entiers codés en dur, `pk=1`, `post_id`, `Post.objects`, imports inter-apps, fixtures). Le nombre de tests ne doit pas baisser ; les tests qui ne portent que sur `Deal`/Trust Score restent verts jusqu'à L0-07.
- Nouveaux tests : contrat de découplage (test `ast` `DomainBoundariesTests` ; ~~import-linter~~ non retenu), `target_type/target_id`, résolution catalog par lot.

**Front**
- Les identifiants deviennent des chaînes : types `number` → `string` pour les ids, routes, clés React Query, `Number(id)`/`parseInt`. Contrat JSON par ailleurs inchangé jusqu'à L0-11.

**Risques acceptés**
- Perte des données de développement (assumée).
- Les jointures supprimées coûtent des requêtes supplémentaires ; compensé par les méthodes de service par lot et un cache court sur le catalogue.
- Intégrité référentielle inter-domaines non garantie par la base : vérifiée en couche service (cohérent avec ADR 0001).

## Plan d'exécution

Règle : **une seule branche et un seul agent touchent les modèles pendant la réinitialisation** ; les autres tâches s'insèrent avant ou après. Raison : chaque tâche L0 touche `models.py` et les migrations des mêmes apps ; deux tâches en parallèle sur ces fichiers génèrent des `0001` incompatibles.

| Étape | Tâche | Agent | Dépend de | Parallélisable avec |
| --- | --- | --- | --- | --- |
| 0 | Pose du tag `pre-reset-migrations`, sauvegarde `db.sqlite3` hors dépôt | chef de projet / dev-backend | — | — |
| 1 | **L0-04** Suppression du code mort restant (`backend/scratch/`, résidus des apps non installées, références mortes ; `connecte-plus-hub/` relève de L0-03, `docker-compose.mysql.yml`/`mysql-init` de L0-02) | dev-backend | 0 | L0-17, front |
| 2 | **Reset R1** : `apps/common`, `identity`, `catalog` (+ `seed_catalog`), `AUTH_USER_MODEL`, UUID. Inclut **L0-06**. | dev-backend | 1 | L0-16 (voir 3) |
| 3 | **L0-16** App `platform` (devenue `platform_core`, ADR 0003) : `OutboxEvent` (UUID, `event_type`, `aggregate_id`, `payload` JSON, `status`, `created_at`, `published_at`, `attempts`), `FeatureFlag`, `services.publish_event()`, commande `dispatch_outbox`, tests. Ne dépend que de `common` (livré au début de R1) ; ne touche que `apps/platform` et une ligne de `INSTALLED_APPS`. | dev-backend (2e instance) | `common` de R1 | R1 puis R2 |
| 4 | **Reset R2** : `marketplace` (Offer, **L0-12** : `is_deleted`, `Post`→`Offer`), `visibility`, `reviews` (avec `Deal` transitoire), `notifications`, `messaging`. Suppression de `reputation`, `ranking`, `interactions`, `accounts`, `marketplace` d'origine. Découplage par services. | dev-backend | R1 | L0-16, F1 |
| 5 | **Reset R3** : `moderation` (`target_type/id`), `payments` (gelée), commandes cron, `setup_roles`, ~~import-linter~~ (non retenu, voir notes R3), régénération finale des `0001`, `makemigrations --check`, suite de tests complète sur base vierge. | dev-backend | R2 | L0-16, F1 |
| F1 | Front : ids en chaînes UUID, aucune autre modification de contrat. | dev-frontend | contrat R1 figé (début) | R1 à R3 |
| 6 | Relecture (`relecteur-code`) puis `qa-testeur` sur base vierge ; `auditeur-securite` sur `identity` (KYC, JWT) | agents | R3, L0-16, F1 | — |
| 7 | **L0-07** Retrait Trust Score (migrations `0002` : drop `User.trust_score`, `Deal`, `TrustScoreSettings`, `Review.deal_id`) puis **L0-10** (gating par contact) ; analyse fonctionnelle possible dès l'étape 1 | analyste, dev-backend, dev-frontend | 6 | L0-13, L0-14 |
| 8 | **L0-13**, **L0-14** (interrupteurs `FeatureFlag`) | dev-paiements, dev-backend | L0-16 mergé | L0-07 si fichiers disjoints |
| 9 | **L0-09** Organisations et contextes (`identity` + `marketplace.Offer.organization_id`) ; plan détaillé par l'architecte avant, car change `Offer.seller` | analyste, architecte, dev-backend, dev-frontend | L0-07 (même app `identity`, migrations 0002 sérialisées) | L0-08 |
| 10 | **L0-08** Score organique P×E×R×D (module `visibility`) | dev-backend | L0-07 | L0-09 |
| 11 | **L0-11** `/api/v1/`, `offers`, `is_deleted` côté JSON ; front en même temps | dev-backend, dev-frontend | L0-09 (urls stabilisées) | — |
| 12 | **L0-18** passe i18n | dev-frontend | L0-07, L0-09, L0-14 | — |

Tâches listées par l'utilisateur, en résumé : **L0-04** (étape 1) → **L0-06 + L0-12 dans la réinitialisation** (R1 à R2) ; **L0-16** en parallèle de R1-R3 ; **L0-07** puis **L0-09** (ne pas les paralléliser : même app `identity`, même `User`) après la réinitialisation. L0-15 est absorbé par R2 (création de `messaging`) ; à clore au backlog avec L0-05.

Étapes internes de R1-R3 : un commit par module, tests verts à chaque module avec des migrations provisoires ; les `0001` définitifs sont régénérés à la fin de R3 (suppression de tous les fichiers de migration, `makemigrations`, `migrate` sur base vierge).

## Risques

1. **Volume des adaptations de tests** (123 occurrences de `is_delete`/imports inter-apps/`trust_score` dans 33 fichiers) : mitigé par l'ordre module par module et l'interdiction de baisser le nombre de tests.
2. **Découplage plus lourd que prévu** : `moderation`, `interactions` et `reputation` lisent directement `Post` et `User.trust_score`. Prévoir 2 à 3 allers-retours de relecture.
3. **Régression API non visible** : les serializers conservent les anciennes clés ; test de contrat (clés JSON de chaque endpoint listées) à écrire avant R2 pour détecter une dérive.
4. **Front** : tout `Number(id)` ou typage `number` silencieusement faux ; `lint` + `build` TypeScript + test de parcours (connexion, annonce, favoris, messages).
5. **Données de développement** à recréer (comptes de test, annonces, villes) : documenter `seed_catalog` et une commande `seed_dev` facultative ; jamais d'export de `db.sqlite3` dans le dépôt.
6. **Jetons JWT et `setup_roles`** : groupes à recréer après reset ; les permissions Django dépendent des nouveaux `app_label`.
7. **Collision de nom** `platform` avec le module standard : à vérifier dès R1 (test d'import).
8. **Perf des jointures supprimées** : surveiller les listes marketplace (annonces + catégories + communes) ; méthodes par lot obligatoires.
9. **Conflit avec des branches ouvertes** : toute branche backend ouverte avant le reset devient inutilisable ; geler les branches backend pendant R1-R3 (hors L0-16 et front).


## Notes d'exécution R1 (ajoutées après relecture)

- **Exception assumée à « pas de transaction entre domaines ».** `identity.services.decide_kyc_document` écrit l'`AuditLog` (via `moderation.services.record_audit`) dans la même `transaction.atomic()` que la décision KYC et le recalcul de `is_verified`. Raison : une décision de vérification sans trace (règle 12) ne doit pas exister. C'est la seule transaction à cheval sur deux domaines ; elle passe par le `services.py` du domaine voisin, jamais par ses modèles. En R3, `record_audit` devra rester synchrone (pas d'outbox) pour garder cette garantie.
- **Cache et limitation de débit.** Les throttles et le compteur d'échecs de connexion (`identity/throttles.py`) s'appuient sur le cache Django. `LocMemCache` est propre à chaque processus : en production à plusieurs processus Daphne, les compteurs ne sont pas partagés (limites effectives multipliées). Avant la mise en production, prévoir un cache partagé (SQLite via `DatabaseCache` en V1, conforme à « pas de Redis »). Les tests utilisent un cache factice, avec LocMem dans les tests de throttling.
- **Réglages de test.** `backend/settings_test.py`, chargé seulement par `manage.py test`.
- **Limitation de débit par échecs (lot 3).** Connexion et confirmation de reset : délai croissant par couple (identifiant normalisé, IP) : 5 échecs, puis 15 min, doublé à chaque palier de 5 échecs supplémentaires (plafond 24 h), remise à zéro au succès. Pas de plafond par identifiant seul : il permettait à un tiers de bloquer le titulaire. **Risque résiduel assumé** : un bourrage réparti sur de très nombreuses adresses n'est freiné que par le throttle par IP (60 connexions/h par IP) ; une alerte sur le volume d'échecs par identifiant (journal) est à prévoir. OTP : 3 demandes/h par couple (numéro, IP) et 10/jour par numéro seul (coût SMS) ; **un tiers peut épuiser ces 10 demandes quotidiennes pour une victime** (déni de service ciblé du reset), accepté contre le risque de facture SMS.
- **Compteurs atomiques et cache partagé.** `FailureLimiter` incrémente via `cache.add` puis `cache.incr` (atomique sur LocMem et, à défaut d'atomicité du backend, au pire sous-compte). Avec plusieurs processus Daphne, un cache LocMem donne autant de compteurs que de processus : en production, utiliser un cache partagé (`DatabaseCache` sur SQLite en V1, sans Redis) avant l'ouverture au public.
- **NUM_PROXIES.** Le contrôle `common.E001` (tag security) échoue hors DEBUG si `NUM_PROXIES=0`.

## Notes d'exécution R2

- **Modules créés** : `visibility` (réglages du classement, compteurs journaliers, vues uniques), `notifications`, `messaging`, `reviews` (avis ; `Deal` et `TrustScoreSettings` transitoires, supprimés par L0-07) et `marketplace` réécrit (`Offer`, `OfferImage`, `Favorite`, `ContactEvent`, `ExchangeProposal`). `interactions`, `reputation` et `ranking` sont supprimés.
- **Dépendances de services (sens autorisé)** : `marketplace` -> `visibility`, `messaging`, `notifications`, `reviews` (seuil d'affichage), `identity` (fiche vendeur par lot) ; `reviews` -> `marketplace`, `identity`, `notifications`, `moderation` ; `messaging` -> `notifications`, `marketplace` (titre et image de l'offre, au niveau des sérialiseurs) ; `moderation` -> `marketplace`, `notifications`. Cycles `marketplace` <-> `reviews` et `marketplace` <-> `messaging` : au niveau des sérialiseurs seulement, jamais entre `services.py` ni entre modèles ; un test (`common.tests.DomainBoundariesTests`) interdit tout import de modèle d'un autre domaine et toute clé étrangère hors utilisateur.
- **Écritures sur plusieurs domaines sans transaction commune** : le contact (`ContactEvent` + message + notification), la nouvelle vue (compteurs `visibility` + total `Offer`) et le recalcul du Trust Score (`identity` + score des offres) sont des candidats naturels aux événements de l'outbox (L0-16).
- **`moderation` et `payments`** : adaptés au strict nécessaire (`Sanction.related_offer_id`, `Transaction.offer_id`, tables de cibles, services) ; leurs `0001` ont été régénérés seuls. Le reste (`target_type` / `target_id`) relève de R3.
- **Durcissements découverts au portage** (hors périmètre initial, avec tests) : propriété de l'offre vérifiée sur modification, suppression et actions de cycle de vie (tout utilisateur connecté pouvait modifier ou supprimer l'offre d'un autre) ; conversations privées par acheteur (un seul fil par offre était partagé entre tous les acheteurs) ; seuls les participants écrivent dans une conversation ; messages non modifiables ; contacts visibles de leur seul expéditeur ; contact de sa propre offre refusé ; réponse à un avis non modifiable par son auteur ; avis masqué non consultable publiquement.
- **Fuseau horaire** : `TIME_ZONE = 'Africa/Kinshasa'` et `USE_TZ = True` (corrigé après relecture R2). Les « jours » (compteurs, limites quotidiennes) suivent `timezone.localdate()` avec des bornes `created_at__gte/lt` explicites ; les dates JSON portent le décalage `+01:00`.
- **Références orphelines possibles** : `Transaction.offer_id` (payments) et `Sanction.related_offer_id` (moderation) désignent une offre par UUID sans clé étrangère. Une purge définitive de l'offre laisse la référence pendante (voulu pour les avis, affaires, conversations ; à traiter explicitement pour les transactions en L1-12 et les sanctions en R3). Les lectures passent par `marketplace.services` et tolèrent l'absence.
- **Fenêtre d'incohérence du contact** : `create_contact_event` écrit le contact, puis le message de la conversation, puis la notification, sans transaction commune (règle « pas de transaction sur deux domaines »). Un échec entre deux écritures laisse un contact sans message ou sans notification. Résolu par l'outbox (L0-16) : le contact publie un événement, `messaging` et `notifications` le consomment de façon idempotente.
- **Masquage de modération** : état explicite `Offer.is_hidden_by_moderation`, posé par la sanction MASQUAGE_ANNONCE ; la reprise et le renouvellement par le vendeur sont refusés ; la levée n'active l'offre que si son statut est ACTIVE.
- **Quota d'avis** : compteur `ReviewDailyCount` (une suppression ne libère pas de place). `likes_count` suit le nombre de favoris.

## Notes d'exécution R3 (état final)

- **`moderation`** : `Report` et `AuditLog` portent `target_type` (nom de modèle en minuscules : `offer`, `user`, `review`, `message`) et `target_id` (UUID), index nommés `report_target` et `audit_target`. Plus de `GenericForeignKey` ni de `ContentType`. `AuditLog.record(actor, action, target=None, details='')` et `record_audit` gardent leur signature (`target` = instance, son nom de modèle devient le type) ; l'écriture reste synchrone. La cible d'un signalement est vérifiée et libellée par `get_report_labels(ids)` du `services.py` de `marketplace`, `identity`, `reviews` et `messaging` (registre `moderation.services.TARGET_RESOLVERS`, méthode par lot : une requête par type pour toute une page). Le tableau de bord passe par `identity.services` (`count_users`, `count_pending_kyc_documents`). Listes `reports` et `sanctions` paginées à la demande (`?page=` ou `?page_size=`).
- **Écarts de contrat HTTP** : aucun changement de clé JSON. `object_id` (signalement) est l'UUID de la cible ; `target_display` vaut `null` si la cible a été purgée ; `id` de signalement, de sanction et d'entrée de journal sont des UUID. Un identifiant de cible mal formé ou d'un autre type donne 400 `object_id: Cible introuvable.`.
- **Sanctions orphelines** : `Sanction.related_offer_id` reste une référence sans clé ; la purge de l'offre laisse la sanction (historique conservé), `apply`/`lift` tolèrent l'offre absente.
- **`payments`** : alignement structurel seulement (UUID par `BaseModel`, `offer_id` en UUID, clés étrangères vers l'utilisateur uniquement, aucune route, aucune fonction ajoutée). Gel par interrupteur : L0-13 ; refonte : L1-12.
- **Commandes cron renommées** : `purge_trash` -> `purge_offer_trash`, `expire_posts` -> `expire_offers`, `cleanup_otp_codes` -> `purge_otp_codes`, `refresh_dashboard_aggregates` -> `refresh_daily_contacts` ; `lift_expired_sanctions` et `purge_offer_views` inchangées. `refresh_daily_contacts` utilise désormais le jour local (`localdate`). Un test vérifie que `cron/crontab` planifie exactement ces six commandes et qu'elles existent.
- **`setup_roles`** : tables alignées sur les modèles finaux ; ajouts administrateur : réglages de visibilité et de marketplace (règle 11), lecture seule du journal d'audit. Aucun accès aux messages, notifications, OTP, comptes (modification) ni à `payments`. Une permission inconnue fait échouer la commande (au lieu d'être ignorée).
- **Frontières** : `DomainBoundariesTests` couvre les neuf domaines (liste `ALL_DOMAINS`, avec un test qui échoue si un nouveau domaine installé n'y figure pas), vérifie aussi les many-to-many, l'absence de clé générique et l'absence de dépendance de migration entre domaines hors `identity`. **Décision import-linter : non ajouté.** Le test `ast` couvre déjà ses contrats (imports directs, relatifs, imports dans les fonctions) et davantage (`get_model`, `import_string`, `import_module`) ; import-linter ne verrait pas les chargements dynamiques et ajouterait une dépendance et une étape de CI sans gain. La mention « import-linter » de la section Conséquences est donc caduque.
- **Migrations** : tous les `0001_initial` supprimés puis régénérés (`makemigrations identity` d'abord, puis le reste : sinon Django scinde `catalog` en deux migrations à cause de la dépendance à l'utilisateur). Une seule migration par domaine, aucune dépendance entre domaines hors utilisateur. `migrate`, `setup_roles` et `seed_catalog` vérifiés sur base vierge.

- **Corrections après relecture et audit (aller-retour 1).** Signalements : réponse de création minimale (`id`, `status`, `created_at`) pour qui n'est pas du personnel de modération, libellé de compte sans e-mail ni téléphone, throttle `report` (10/h), doublon ouvert refusé (409), auto-signalement refusé (400), description et notes bornées à 1000 caractères, machine d'états (409 depuis un état clos). Accès à l'API de modération par droits Django (`view_report`, `change_report`, `view_sanction`, `add_sanction`) et non plus par `is_staff` ; suspension, bannissement et leur levée réservés à l'administrateur ; on ne sanctionne ni le personnel ni soi-même, et l'offre masquée doit appartenir au sanctionné. Le modérateur garde `reviews.review change` (seul droit permettant de masquer un avis, via l'admin) mais `ReviewAdmin` ne lui laisse modifier que `is_hidden`.
- **Question ouverte LEG-PRV : durées de conservation.** Le journal d'audit (`AuditLog`, détails libres) et les signalements (description, notes de décision) n'ont aucune durée de conservation ni purge : à fixer avec LEG-PRV avant la production, puis commande de purge planifiée. Les `details`, `reason` et notes ne doivent contenir aucune donnée personnelle (consigne dans le README).

- **Oracle d'existence à l'inscription (L0-10a-a, aller-retour 1).** Le téléphone n'a plus d'`UniqueValidator` : l'unicité est contrôlée dans `validate()` après la preuve de possession du numéro par OTP, avec la réponse neutre « Code invalide ou expiré. » (inscription et changement de numéro sur `me/`). **Dette résiduelle : l'e-mail** garde l'erreur « existe déjà » (aucune vérification d'e-mail n'existe) ; atténuée par les limites `register` (20/h par IP) et `profile_write` (30/h par utilisateur, 60/h par IP). À lever avec une vérification d'e-mail (lien ou code) avant la production.
