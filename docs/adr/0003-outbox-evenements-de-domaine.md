# ADR 0003 — Outbox des événements de domaine (L0-16)

Statut : accepté (09/10/2026, décisions du chef de projet du même jour intégrées) · Date : 09/10/2026
Références : CLAUDE.md §5, CDC v1.2 §5.4, ADR 0001, ADR 0002 (notes R1 à R3).

## 1. Contexte

Aujourd'hui des services écrivent dans plusieurs domaines à la suite, sans transaction commune ni reprise :
- `marketplace.create_contact_event` / `create_exchange_proposal` : `ContactEvent` (marketplace), puis conversation et message (messaging), puis notification (notifications) ;
- `marketplace.register_view` / `register_share` : `visibility.record_view`, puis `Offer.views_count`, puis recalcul du score ;
- `reviews/signals.py` : `recompute_trust_score` écrit dans `identity` et recalcule les scores de `marketplace` ; `check_crossed_reviews` passe une instance `Review` à `moderation` ; `notify_review_created` et `reply_to_review` appellent `notifications` ;
- `marketplace.expire_offers` appelle `notifications`.

Si la 2e ou la 3e écriture échoue, le contact existe sans message ni notification, sans aucun moyen de rattrapage. CLAUDE.md §5 impose : événements écrits dans une outbox dans la même transaction que le changement émetteur, diffusés par une commande planifiée, sans Redis ni Celery.

## 2. Décisions

### 2.1 Nom de l'app : `platform_core` (et non `platform`)

L'ADR 0002 prévoyait `apps.platform`. Le chemin `apps.platform` ne collisionne pas tant que `apps/` n'est pas dans `sys.path`, mais ce n'est pas garanti : `python apps/x.py`, un IDE, `unittest` lancé dans `apps/`, un `pytest rootdir` mal réglé. Dans ce cas `import platform` (utilisé par Django, DRF, Daphne et `sys`-level tooling) charge notre dossier et l'application ne démarre plus, avec une erreur très difficile à lire. Coût du changement : nul aujourd'hui (l'app n'existe pas).

Décision : **`apps/platform_core/`, label `platform_core`**, tables `platform_core_*`. Elle porte `OutboxEvent`, `OutboxDelivery` et, plus tard, `FeatureFlag` (L0-13/L0-14). Mettre à jour la ligne correspondante de l'ADR 0002 (note de renvoi, pas de réécriture). Ajouter `platform_core` à `ALL_DOMAINS` dans `common/tests.py` (le test `test_every_installed_domain_is_covered` l'exige). Test d'import ajouté : `importlib.import_module('platform').__file__` ne pointe pas dans le dépôt.

`platform_core` ne dépend de rien sauf `common`. Tous les domaines peuvent importer `platform_core.services` et `platform_core.registry` (jamais ses modèles, règle habituelle). Aucune migration d'un autre domaine ne dépend de la sienne.

### 2.2 Modèles (portables SQLite/MySQL)

`OutboxEvent(BaseModel)` (PK UUID, `created_at`, `updated_at` hérités)
| Champ | Type | Remarque |
|---|---|---|
| `event_type` | CharField(100) | `<domaine>.<fait_au_passé>`, ex. `marketplace.contact_recorded` |
| `version` | PositiveSmallIntegerField, défaut 1 | version du schéma du payload ; un abonné refuse (dead) une version qu'il ne connaît pas |
| `aggregate_type` | CharField(50) | ex. `offer` |
| `aggregate_id` | UUIDField, null | pour le diagnostic et l'ordre par agrégat |
| `payload` | JSONField | uniquement UUID (en chaîne) et valeurs simples, déjà dénormalisées (titre de l'offre, nom de l'expéditeur) : un abonné ne relit pas le domaine émetteur |
| `status` | CharField(10) | `pending`, `done`, `dead` (statut global, déduit des livraisons) |
| `completed_at` | DateTimeField, null | pour la purge |

Index : `(status, created_at)`, `(completed_at)`, `(event_type)`.

`OutboxDelivery(BaseModel)` : une ligne par (événement, abonné), créée **à la publication**, dans la même transaction. Nécessaire pour que la reprise d'un abonné en échec ne rejoue pas les abonnés déjà réussis.
| Champ | Type |
|---|---|
| `event` | ForeignKey(OutboxEvent, CASCADE) (même domaine : permis) |
| `handler` | CharField(150) : nom stable de l'abonné, `<domaine>.<fonction>` |
| `status` | CharField(10) : `pending`, `processing`, `done`, `dead` |
| `attempts` | PositiveSmallIntegerField, défaut 0 |
| `next_attempt_at` | DateTimeField (défaut = création) |
| `locked_at` | DateTimeField, null |
| `locked_by` | CharField(64), blank (jeton aléatoire de l'exécution) |
| `last_error` | TextField, blank (tronqué à 2 000 caractères, sans payload ni donnée personnelle) |
| `processed_at` | DateTimeField, null |

Contrainte : unicité `(event, handler)` (inconditionnelle, portable). Index : `(status, next_attempt_at)`. Un seul `0001_initial`, retour arrière = `migrate platform_core zero`. Pas de migration de données (nouvelle table). Pas de clé étrangère hors du domaine, pas de FK vers l'utilisateur.

### 2.3 Publication

`platform_core.services.publish_event(event_type, *, aggregate_type, aggregate_id, payload, version=1)` :
- doit être appelée **dans** un `transaction.atomic()` de l'émetteur ; sinon elle lève `OutboxError` (vérification `connection.in_atomic_block`). Dans les `TestCase`, le bloc atomic existe déjà : le contrôle utilise donc l'argument `require_atomic=True` désactivable seulement dans les tests unitaires de `platform_core`.
- valide que le payload est sérialisable JSON et inférieur à 16 Ko ;
- crée l'`OutboxEvent` puis une `OutboxDelivery` par abonné enregistré pour ce type ; aucun abonné = événement créé directement `done` (trace) ;
- n'appelle aucun abonné.

Exception assumée à « pas de transaction couvrant deux domaines » : la table outbox est une table technique partagée par construction (patron transactionnel outbox) ; l'écriture métier et l'écriture de l'événement partagent la transaction, jamais deux écritures métier de domaines différents.

L'émetteur englobe désormais dans un seul `atomic` : sa propre écriture + `publish_event`. Les validations (`MarketplaceError`) restent avant l'écriture.

### 2.4 Registre des abonnés

`platform_core/registry.py` :
```python
@subscribe('marketplace.contact_recorded', name='messaging.open_contact_conversation')
def open_contact_conversation(event): ...   # dans apps/messaging/events.py
```
- Chaque domaine déclare ses abonnés dans `apps/<domaine>/events.py`, importé par `AppConfig.ready()` du domaine. Le décorateur enregistre `(event_type, name, fonction)` ; un doublon de `name` lève une erreur au démarrage.
- L'abonné reçoit un `EventData` immuable (`id`, `event_type`, `version`, `payload`, `created_at`), jamais le modèle. Il appelle les `services.py` de son propre domaine et, au besoin, ceux d'autres domaines (pas de modèles étrangers).
- Le `name` est persisté dans `OutboxDelivery.handler` : ne jamais le renommer sans migration de données. Une livraison dont l'abonné n'existe plus passe `dead` avec l'erreur `handler inconnu`.
- Un type d'événement sans émetteur ou un abonné sur un type inconnu : contrôle Django (`checks`) via un catalogue `EVENT_TYPES` déclaré dans `platform_core/catalog.py` (type, version courante, domaine émetteur). Le catalogue est la documentation exécutable.
- Domaine émetteur d'un type : vérifié par `publish_event` (`event_type` commence par le label du module appelant, contrôle de convention testé, pas de magie sur la pile d'appel).

### 2.5 Diffusion : `python manage.py dispatch_outbox`

Options : `--limit 200` (livraisons par exécution), `--max-seconds 50`, `--stats` (compte par statut et plus ancien en attente, code de sortie 1 si une livraison est `dead`), `--requeue <delivery_id|dead>`.

Algorithme, par livraison due (`status=pending`, `next_attempt_at <= now`, ou `processing` avec `locked_at < now - 5 min`, ordre `created_at`) :
1. **Prise en charge par UPDATE conditionnel** (portable, sans `SELECT FOR UPDATE SKIP LOCKED`, inconnu de SQLite) : `OutboxDelivery.objects.filter(pk=…, status=<vu>, locked_by=<vu>).update(status='processing', locked_at=now, locked_by=token, attempts=F('attempts')+1)` ; 0 ligne modifiée = un autre processus a gagné, on passe.
2. **Exécution + marquage dans un même `atomic`** : l'abonné écrit dans son domaine, puis un UPDATE conditionnel `filter(pk, locked_by=token).update(status='done', processed_at=now)`. Si 0 ligne (verrou repris par un autre), `OutboxError` provoque l'annulation des écritures de l'abonné. Dans le monolithe, effet de l'abonné et marque « fait » sont donc validés ensemble : traitement exactement une fois, y compris après plantage. Les transactions restent courtes (SQLite n'a qu'un écrivain ; `timeout` de 20 s déjà réglé).
3. **Échec** : l'`atomic` est annulé, puis une écriture séparée enregistre `last_error`, `status='pending'`, `next_attempt_at = now + min(30 s × 2^(tentatives-1), 1 h)`. À la 8e tentative : `status='dead'`, journal `logger.error`. Une exception `PermanentEventError` (version inconnue, payload invalide) passe directement `dead`.
4. Recalcul du statut de l'événement : `done` quand toutes les livraisons sont `done` (renseigne `completed_at`) ; `dead` si au moins une est `dead` et aucune `pending`.
5. Un plantage entre 1 et 2 laisse `processing` : repris après 5 minutes (les écritures de l'abonné n'ont pas été validées, donc rien à défaire).

Règles imposées aux abonnés (sans elles la garantie « exactement une fois » ne tient plus le jour où un abonné devient un service) : idempotents par construction (préférer « recalculer à partir de la source » à « incrémenter », ou clé naturelle), uniquement des écritures en base (pas d'e-mail ni de SMS dans l'`atomic` : un abonné d'envoi externe doit être idempotent par clé d'événement et placé dans sa propre livraison), tolérants à l'ordre (aucune garantie d'ordre entre événements au-delà du tri par `created_at` à la première tentative).

Concurrence : plusieurs `dispatch_outbox` simultanés sont sûrs (étape 1). Cron : **toutes les minutes** (`* * * * *`). Pour la latence perçue, `publish_event` enregistre un `transaction.on_commit` qui tente une diffusion immédiate des livraisons de cet événement (`dispatch_for_event(id)`, exceptions avalées et journalisées ; le cron reste le filet de sécurité), pilotée par `OUTBOX_INLINE_DISPATCH` (vrai en dev et prod, faux dans les tests sauf cas dédiés via `captureOnCommitCallbacks(execute=True)`). Ligne à ajouter à `backend/cron/crontab` et au test de crontab.

Purge : commande `purge_outbox` (cron quotidien 02:30) : événements `done` après 7 jours (réglable `OUTBOX_RETENTION_DAYS`, la charge utile contient des messages de contact, donc données personnelles : rétention courte), `dead` après 90 jours. Suppression en lots de 500 (CASCADE sur les livraisons).

Observabilité : `dispatch_outbox --stats` ; `OutboxEvent` et `OutboxDelivery` en lecture seule dans l'admin Django avec action « relancer » (remet `pending`, `attempts=0`) ; la relance est un acte sensible : journalisée via `moderation.record_audit` (`OUTBOX_REQUEUED`). Un événement `dead` ne bloque ni les autres événements ni l'émetteur.

### 2.6 Ce qui reste synchrone

- **`AuditLog` (`moderation.record_audit`)** : preuve d'une action sensible (règle 12) ; elle doit être validée ou annulée avec l'action elle-même. Elle est écrite dans la transaction de l'acte, jamais différée.
- Écritures du même domaine (favori + `likes_count`, `ContactEvent` + validations) ; lectures par `services.py` ; validations et contrôles de droits.
- Effets de modération qui doivent être immédiats (masquage d'offre par sanction) : appel direct à `marketplace.hide_by_moderation`.
- Envoi de message de messagerie → notification du destinataire : appel direct tant que la messagerie n'est pas passée en temps réel ; à reprendre avec `dev-temps-reel` (candidat `messaging.message_sent`).

## 3. Événements initiaux

Tous `version=1`. Les payloads ne contiennent que des UUID (en chaîne) et valeurs simples.

| Type | Émetteur (et fonction) | Abonnés | Payload |
|---|---|---|---|
| `marketplace.contact_recorded` | marketplace `create_contact_event` (dans le `atomic` de la création de `ContactEvent`) | `messaging.open_contact_conversation` (conversation + message, `send_message(sender_id, notify=False)`) ; `notifications.notify_contact` (type CONTACT au vendeur) | `contact_event_id, offer_id, offer_title, seller_id, sender_id, sender_name, message` |
| `marketplace.exchange_proposed` | marketplace `create_exchange_proposal` | `messaging.open_exchange_conversation` (préfixe `[PROPOSITION D'ÉCHANGE]`) ; `notifications.notify_exchange` | idem avec `proposal_id` |
| `visibility.offer_viewed` | visibility `record_view` (quand la vue est nouvelle, dans son `atomic`) | `marketplace.sync_offer_views` : `views_count = visibility_services.total_views(offer_id)` (idempotent, recalcul à la source) puis `refresh_visibility_score` | `offer_id, seller_id, date` |
| `visibility.offer_shared` | visibility `record_share` (si nouveau) | `marketplace.sync_offer_shares` : recalcul de `shares_count` à la source puis score | `offer_id, actor_key, date` |
| `reviews.review_posted` | reviews, création d'un avis (remplace `notify_review_created`) | `notifications.notify_review_posted` | `review_id, reviewed_user_id, author_id, author_name, offer_id, offer_title, excerpt` |
| `reviews.review_replied` | reviews `reply_to_review` | `notifications.notify_review_reply` | `review_id, review_author_id, replier_name, offer_id, offer_title` |
| `reviews.crossed_reviews_detected` | reviews `check_crossed_reviews` (remplace le passage d'une instance `Review` à moderation) | `moderation.file_crossed_reviews_report` : `file_automatic_report` reçoit désormais `target_type, target_id` au lieu d'une instance | `review_id, user_a, user_b, deals_count, window_days` |
| `reviews.reputation_changed` | reviews `recompute_trust_score` (calcul interne) | `identity.cache_reputation` (`set_reputation`) ; `marketplace.refresh_seller_scores` (transitoire) | `user_id, trust_score, reviews_count` |
| `marketplace.offer_expiring_soon` / `marketplace.offer_expired` | marketplace `expire_offers` | `notifications.notify_offer_expiration` | `offer_id, offer_title, seller_id, expires_at` |

Remarques :
- **`reviews.reputation_changed` est transitoire** : le Trust Score disparaît avec L0-07 (règle 4, aucun score de confiance universel, aucune note dans le classement organique). Ses deux abonnés et l'événement sont supprimés par L0-07/L0-08. Ne pas investir au-delà du strict nécessaire : la chaîne actuelle (signaux) est simplement ré-exprimée en événement pour supprimer les écritures croisées d'ici là. Si l'utilisateur préfère, ne pas migrer cet événement et laisser L0-07 retirer directement le code.
- Les signaux de `reviews` restent (même domaine) mais ne font plus que `publish_event` dans la transaction de sauvegarde. `post_delete` : même principe.
- `register_view`/`register_share` de marketplace n'appellent plus que `visibility.record_*` ; les vues HTTP renvoient `shares_count` sans attendre l'abonné (valeur lue après `on_commit` inline dans la grande majorité des cas ; à vérifier côté test de contrat et à signaler au front : la valeur est « au mieux », la source de vérité reste le recalcul).
- Il faut ajouter à `visibility.services` : `total_views(offer_id)` et `total_shares(offer_id)` (somme de `DailyVisibilityCounter` ; pour les partages, un compteur dédié ou comptage des `OfferUniqueView` préfixées `share:` non purgées, **à trancher par dev-backend avec l'architecte : la purge des vues uniques empêche de recompter les partages ; si c'est le cas, ajouter `shares` à `DailyVisibilityCounter` en migration 0001 régénérée avant mise en production, sinon abonné incrémental exact-une-fois**).
- Données personnelles : `message` et `sender_name` dans le payload, d'où la rétention de 7 jours. Aucune adresse exacte, pièce d'identité ni position (règle 10). À soumettre à `auditeur-securite`.
- Hors de cette tâche (candidats suivants) : `moderation` → effets sur marketplace (masquage), `messaging.message_sent`, futurs événements des lots 1 et 2 (paiement confirmé, billet émis).

## 4. Frontières et tests de frontières

- `DomainBoundariesTests` : ajouter `platform_core` à `ALL_DOMAINS`. Aucun changement du parseur (`boundaries.py`) : les imports `apps.platform_core.services`/`registry` sont autorisés ; seuls les `models` sont interdits, et `platform_core` n'importe aucun modèle des autres domaines (il ne les connaît pas).
- Tests à ajouter : (a) aucun domaine n'importe `platform_core.models` ; (b) `platform_core` n'importe aucun autre domaine ; (c) chaque `events.py` n'importe que des `services` ; (d) chaque type de `catalog.py` a au moins un émetteur et un abonné (ou est déclaré « sans abonné ») ; (e) test de non-collision `platform`. Le test sur les clés étrangères hors domaine reste vert (FK interne à `platform_core` uniquement).
- Le test de crontab (`common/tests.py` ~l.360) est mis à jour : `dispatch_outbox` (chaque minute) et `purge_outbox` (quotidien).

## 5. Tests de `platform_core` et des émetteurs

- Publication : atomicité (rollback de l'émetteur = aucun événement ni livraison), refus hors transaction, payload non sérialisable, une livraison par abonné.
- Diffusion : succès, échec puis reprise avec backoff (temps simulé), dépassement des tentatives = `dead`, `PermanentEventError`, livraison `processing` périmée reprise, deux prises en charge concurrentes (la 2e est refusée par l'UPDATE conditionnel), perte du verrou annule les écritures de l'abonné, un abonné en échec n'empêche pas l'autre de réussir et n'est pas rejoué quand l'autre se rejoue, ordre `created_at`.
- Idempotence : rejouer deux fois la même livraison ne crée qu'une notification/un message.
- Chaque émetteur migré : test « écriture + événement dans la même transaction » (un abonné qui plante n'annule pas le contact), puis test bout en bout `dispatch_outbox` produisant message, notification, compteurs.
- Les tests existants qui attendent un effet immédiat (notification après contact) appellent `dispatch_outbox` ou utilisent `captureOnCommitCallbacks(execute=True)` ; `OUTBOX_INLINE_DISPATCH=False` par défaut en test.
- `python manage.py makemigrations --check --dry-run`, migrations sur base vierge, `migrate platform_core zero`.

## 6. Plan de tâches (dev-backend, une tâche, commits successifs)

Prérequis : ADR 0002 R1 à R3 terminés (services de domaines en place). Branche `feat/L0-16-outbox`.

1. `feat(platform_core)` : app, modèles, migration, `publish_event`, registre, catalogue, `dispatch_outbox`, `purge_outbox`, admin lecture seule + relance, tests, crontab et son test, ajout dans `ALL_DOMAINS`, test de non-collision. Critères : sections 5 (publication, diffusion, idempotence) vertes ; deux `dispatch_outbox` parallèles sur SQLite sans doublon ni `database is locked` non géré.
2. `refactor(marketplace,messaging,notifications)` : contact et échange en événements. Critères : un abonné en échec laisse le contact enregistré puis le message/la notification apparaissent après reprise ; plus aucun appel direct marketplace → messaging/notifications dans ces deux fonctions.
3. `refactor(visibility,marketplace)` : vues et partages. Critères : compteur exact après N vues concurrentes et rejouées ; `total_views`/`total_shares` ajoutés ; contrat JSON des endpoints inchangé.
4. `refactor(reviews,notifications,moderation)` : avis, réponse, avis croisés (`file_automatic_report(target_type, target_id)`), et si validé `reputation_changed`. Critères : plus de signal ni de service d'avis qui écrit hors de `reviews`.
5. `refactor(marketplace,notifications)` : expiration. Critères : `expire_offers` ne dépend plus de `notifications`.
6. Mise à jour de `README`/doc (catalogue d'événements), `BACKLOG.md` et `JOURNAL.md` par le chef de projet.

Ordre strict 1 puis 2 à 5 (2 à 5 parallélisables entre développeurs seulement si les fichiers sont disjoints ; 4 touche `moderation.services`, 2 et 5 touchent `marketplace.services` : à faire séquentiellement). Revue : `relecteur-code` après chaque commit majeur, `auditeur-securite` sur le payload des contacts, puis `qa-testeur`.

## 7. Conséquences

Positif : plus d'écriture partielle sans rattrapage ; domaines indépendants ; reprise et diagnostic ; chemin direct vers des services séparés. Négatif : cohérence à terme (latence de quelques secondes, jusqu'à 1 minute si l'inline échoue), tables supplémentaires, discipline d'idempotence pour les abonnés ; une livraison `dead` demande une action humaine. Dette signalée : `visibility` ne conserve pas de compteur de partages durable ; `reputation_changed` à supprimer avec L0-07.

## 8. Écarts constatés à l'implémentation (L0-16, 09/10/2026)

Les décisions du chef de projet du 09/10/2026 priment sur les sections 2 à 6 en cas d'écart. Résultat :

- **Charges utiles minimisées pour les contacts et échanges** : identifiants (contact ou proposition, offre, vendeur, expéditeur) et titre public de l'offre. Ni le texte du message ni le nom de l'expéditeur ne sont copiés : `messaging` relit le texte par `marketplace.services.get_contact_message` / `get_exchange_message` (None si l'annonce a été supprimée entre-temps : rien à ouvrir), `notifications` relit le nom par `identity.services.get_full_names`. La rétention courte (7 jours) est conservée par prudence. Les charges des avis (nom de l'auteur, titre de l'offre, extrait de 50 caractères) ne contiennent que des données déjà publiques avec l'avis.
- **`reviews.reputation_changed` n'est pas migré** (le Trust Score disparaît avec L0-07) : `recompute_trust_score` reste synchrone dans les signaux de `reviews`, seule exception restante à « aucune écriture hors de son domaine » côté avis. Aucun abonné `identity.cache_reputation` ni `marketplace.refresh_seller_scores`.
- **`marketplace.offer_expired` n'est pas émis** : l'existant ne notifie que l'échéance proche ; aucun comportement ajouté.
- **Partages** : colonne `shares` ajoutée à `DailyVisibilityCounter` (migration 0001 de `visibility` régénérée) ; `shares_count` de l'offre est recalculé à la source par l'abonné `marketplace.sync_offer_shares` (idempotent), comme `views_count` (`sync_offer_views`). Les deux abonnés appellent `marketplace.services.sync_offer_engagement`. `record_share` prend désormais `seller_id`. La valeur `shares_count` renvoyée par l'endpoint de partage est « au mieux » (testée : à jour avec la diffusion immédiate, total précédent sinon). Dette : les partages antérieurs à ce changement n'ont pas de compteur journalier (base non encore en production).
- **`moderation.file_automatic_report(target_type, target_id, reason, description)`** remplace la version à instance ; l'abonné `moderation.file_crossed_reviews_report` construit la description.
- **Relance** : l'AuditLog est écrit par `platform_core/operations.py` (`requeue_and_audit`, partagé par l'admin et `dispatch_outbox --requeue`) via `moderation.services.record_audit` : seule dépendance de `platform_core` vers un autre domaine, par `services.py`. Le test de frontières l'autorise explicitement pour ce seul module.
- **Verrou SQLite** : le traitement d'une livraison commence par une écriture (renouvellement de `locked_at`) pour que SQLite attende son délai au lieu d'échouer en promouvant une lecture en écriture (« database is locked ») ; vérifié avec trois `dispatch_outbox` simultanés sur un fichier SQLite (60 contacts : 60 messages et 60 notifications exactement, aucun échec).
- **`last_error`** ne contient que la classe de l'exception et son point d'origine (fichier:ligne) pour les erreurs inattendues, jamais son message ; le détail va au journal serveur (`logger.exception`).
- **L'admin Django n'affiche pas la charge utile** (`exclude = ('payload',)`).
- Réglages techniques : `OUTBOX_INLINE_DISPATCH`, `OUTBOX_RETENTION_DAYS`, `OUTBOX_DEAD_RETENTION_DAYS`, `OUTBOX_MAX_ATTEMPTS`, `OUTBOX_LOCK_TIMEOUT_SECONDS`, `OUTBOX_BACKOFF_*` dans `settings.py` (variables d'environnement), pas de modèle de réglages : ce ne sont pas des règles métier.

### Corrections après relecture et audit sécurité (aller-retour 1)

- **Journaux** : plus aucun `logger.exception`. Un échec d'abonné ou de diffusion immédiate écrit seulement la classe de l'exception et son origine (`_describe`), jamais son message ni sa trace (ils peuvent citer des données personnelles).
- **Source unique des totaux** : les compteurs journaliers de `visibility` sont la seule source de `views_count` et `shares_count` ; `sync_offer_engagement` écrase toute valeur divergente (pas de `max(valeur, total)`). Testé.
- **Charges utiles des avis** : `review_posted` et `review_replied` ne portent plus que des identifiants et le titre public de l'offre (`replier_id` ajouté) ; le nom et l'extrait sont relus à la diffusion (`identity.get_full_names`, `reviews.get_review_excerpt`). Un avis supprimé avant la diffusion n'est pas notifié.
- **Rétention** : événements traités 7 jours, **dead 30 jours** (`OUTBOX_DEAD_RETENTION_DAYS`). Question ouverte pour LEG-PRV : faut-il effacer ou anonymiser les événements encore présents (identifiants d'un compte) à la suppression de ce compte ? Les charges ne contiennent aucun texte libre de l'utilisateur, mais des identifiants.
- **Relance** : l'action admin « Relancer les livraisons sélectionnées » ne touche que les livraisons `dead`. Un futur rôle d'exploitation aura besoin de `view_outboxdelivery` **et** `change_outboxdelivery` (la permission « change » commande la relance, le modèle restant en lecture seule). La relance en ligne de commande est journalisée dans l'AuditLog avec `actor=None` (« ligne de commande » dans le détail). Relance et AuditLog sont écrits dans une même transaction.
- **Statut d'événement** : `_refresh_event_status` est composé d'UPDATE conditionnels (sous-requêtes EXISTS) évalués par la base à l'écriture, sans lecture préalable périmée.
- **Charge invalide** : tous les abonnés de `notifications` lèvent `PermanentEventError` (clé absente, UUID ou date mal formé) ; la livraison passe `dead` sans nouvelle tentative.
- **Préfixe du type** : `publish_event` ne vérifie pas à l'exécution que le préfixe du type est le domaine appelant ; c'est garanti par le test de frontières (types littéraux publiés par le seul domaine propriétaire, présents au catalogue).
- **Concurrence réelle** : `backend/scripts/check_outbox_concurrency.py` (manuel, voir README), à refaire avant MySQL.
