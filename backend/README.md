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

### Déconnexion, CORS et filtres (L0-19)

- `POST /api/accounts/logout/` est public (sans jeton d'accès) : le refresh du corps est mis sur liste noire. Réponse 200 identique pour un jeton forgé, expiré ou déjà révoqué ; 400 si `refresh` est absent ; limite `logout` de 60/h par IP. `logout-all/` reste authentifié.
- `Retry-After` est exposé aux appels inter-origines (`CORS_EXPOSE_HEADERS`) pour que le front lise les 429.
- `GET /api/marketplace/posts/<uuid>/` renvoie au vendeur authentifié toutes ses offres (pause, vendue, expirée, masquée par la modération, corbeille) ; le public et les tiers ne voient que les offres actives. Les vues du vendeur sur sa propre offre ne sont pas comptées. Une offre masquée porte `is_hidden_by_moderation: true`.
- Limite `logout` par IP : derrière un NAT partagé (opérateur mobile, bureau), plusieurs utilisateurs comptent pour une seule IP et peuvent recevoir un 429. Sans conséquence : le front vide sa session locale de toute façon, seule la mise sur liste noire du refresh est différée (il expire seul au bout de 7 jours).
- `GET /api/marketplace/posts/<uuid>/` renvoie `Cache-Control: private` à un utilisateur authentifié et `Vary: Authorization` dans tous les cas (réponse propre à l'utilisateur : favori, masquage). `is_hidden_by_moderation` n'est présent que dans la réponse au vendeur de l'offre.
- En-têtes de cache : `ApiCacheHeadersMiddleware` pose `Vary: Authorization` sur toute réponse de `/api/` et `Cache-Control: private` si la requête porte un jeton ou si la réponse pose un cookie (`anon_id`).
- Vie privée (L0-10a-a) : aucune réponse d'API n'expose le téléphone ni l'e-mail d'un autre utilisateur (`seller.phone` a disparu de l'offre). Le numéro ne sortira que par l'action de contact (L0-10a-c). `apps/common/tests_privacy.py` parcourt toutes les routes GET (anonyme, tiers, contrepartie, vendeur, modérateur) et échoue à la moindre clé ou valeur `phone`/`email` hors `/api/accounts/me/`.
- Inscription et changement de numéro (`POST register/`, `PATCH me/`) : l'erreur `phone` « déjà utilisé » n'existe plus ; un numéro pris donne la même réponse qu'un code faux (`otp_code : Code invalide ou expiré.`). L'e-mail garde l'erreur d'unicité (dette, ADR 0002) ; limites `register` 20/h par IP et `profile_write` 30/h par utilisateur (60/h par IP).
- `GET /api/accounts/businesses/?is_verified=true|false` filtre les entreprises ; toute autre valeur donne un 400 (`{"is_verified": [...]}`).

## Envois de fichiers et tâches planifiées

- **Taille des envois** : Django borne le corps hors fichiers (`DATA_UPLOAD_MAX_MEMORY_SIZE`, 1 Mo par défaut, réglable par `DATA_UPLOAD_MAX_MEMORY_KB`), le nombre de fichiers par requête (`DATA_UPLOAD_MAX_NUMBER_FILES = 10`) et chaque image (`PROFILE_IMAGE_MAX_MB`, `PROFILE_IMAGE_MAX_PIXELS`, 16 Mpx, mêmes plafonds pour les photos d'offres). Nginx doit aussi borner le corps total avant Django : `client_max_body_size 12m;` (8 photos de 5 Mo ne passent pas d'un seul envoi : le plafond protège le serveur, les photos s'envoient en plusieurs requêtes).
- **Vues uniques** : la commande `purge_offer_views` (quotidienne, voir `cron/crontab`) supprime les vues uniques plus anciennes que la durée réglée dans le back-office (Paramètres de visibilité, 2 jours par défaut ; durée définitive à fixer avec LEG-PRV).
- **Fuseau** : `TIME_ZONE = 'Africa/Kinshasa'`, `USE_TZ = True`. Les dates JSON portent le décalage (`+01:00`).

## Structure des modules (ADR 0002)

Un domaine par app dans `apps/` ; clés UUID (`common.models.BaseModel`) ; aucune clé étrangère entre domaines (sauf vers l'utilisateur) ; un domaine lit un autre uniquement par son `services.py`.

| Module | Contenu |
|---|---|
| `common` | classe abstraite UUID, pagination, utilitaires, contrôle des frontières (pas de modèle concret) |
| `identity` | utilisateur, OTP, fiche entreprise (transitoire), pièces KYC, sessions |
| `catalog` | villes, communes, catégories, produits interdits (référentiels configurables) |
| `marketplace` | offres, photos, favoris, contacts, propositions d'échange |
| `visibility` | compteurs journaliers, vues uniques, réglages du classement |
| `reviews` | avis ; `Deal` et Trust Score transitoires (retrait : L0-07) |
| `messaging` | conversations et messages |
| `notifications` | notifications |
| `moderation` | signalements, sanctions, journal d'audit (`record_audit`) ; cibles par `target_type` + `target_id` |
| `payments` | gelé (L0-13), refonte en L1-12 |
| `platform_core` | outbox des événements de domaine (`OutboxEvent`, `OutboxDelivery`), registre d'abonnés, diffusion et purge ; ne dépend que de `common` |

**Contrôle des frontières.** `common.tests.DomainBoundariesTests` (analyse `ast`, `common/boundaries.py`) tourne dans `manage.py test apps` et dans la CI : aucun import de modèle d'un autre domaine (imports directs, relatifs, `get_model`, `import_string`), aucune clé étrangère ou many-to-many hors utilisateur, aucune clé générique, aucune dépendance de migration entre domaines hors `identity`. Tout nouveau domaine doit être ajouté à `ALL_DOMAINS` dans ce fichier de tests (un test le rappelle). `import-linter` n'est pas utilisé : il ne voit pas les chargements dynamiques et n'apporte rien de plus.

**Cibles de modération.** `moderation` résout `target_type` (`offer`, `user`, `review`, `message`) via `get_report_labels(ids)` du `services.py` de chaque domaine (registre `TARGET_RESOLVERS`). Un nouveau type signalable ajoute une entrée à ce registre et cette fonction à son domaine.

## Événements de domaine (outbox, ADR 0003)

Un domaine ne modifie pas un autre domaine : il écrit son changement **et** un événement (`platform_core.services.publish_event`, refusé hors `transaction.atomic()`) dans la même transaction. Les abonnés (`apps/<domaine>/events.py`, enregistrés par `AppConfig.ready()`) sont appelés ensuite par `dispatch_outbox`, avec reprise (attente 30 s x 2^n, plafonnée à 1 h, 8 tentatives puis `dead`), exactement une fois par abonné. La diffusion est aussi tentée tout de suite après validation de la transaction (`OUTBOX_INLINE_DISPATCH`, vrai par défaut, faux en test) ; le cron est le filet de sécurité.

| Type d'événement | Émetteur | Abonnés | Contenu de la charge utile |
|---|---|---|---|
| `marketplace.contact_recorded` | marketplace | `messaging.open_contact_conversation`, `notifications.notify_contact` | identifiants (contact, offre, vendeur, expéditeur) et titre public de l'offre ; ni message ni nom |
| `marketplace.exchange_proposed` | marketplace | `messaging.open_exchange_conversation`, `notifications.notify_exchange` | idem (`proposal_id`) |
| `marketplace.offer_expiring_soon` | marketplace | `notifications.notify_offer_expiration` | offre, titre, vendeur, échéance |
| `visibility.offer_viewed` | visibility | `marketplace.sync_offer_views` | offre, date |
| `visibility.offer_shared` | visibility | `marketplace.sync_offer_shares` | offre, date |
| `reviews.review_posted` | reviews | `notifications.notify_review_posted` | identifiants et titre public de l'offre ; nom de l'auteur et extrait relus à la diffusion |
| `reviews.review_replied` | reviews | `notifications.notify_review_reply` | identifiants et titre public de l'offre ; nom du répondant relu à la diffusion |
| `reviews.crossed_reviews_detected` | reviews | `moderation.file_crossed_reviews_report` | avis, deux comptes, nombre d'affaires, fenêtre |

Ajouter un événement : déclarer le type dans `platform_core/catalog.py`, publier avec `publish_event('<domaine>.<fait>', ...)` (type littéral), écrire l'abonné idempotent dans `events.py` du domaine récepteur (il n'appelle que des `services.py`). Un contrôle Django (`platform_core.E001`/`E002`) et des tests de frontières vérifient le catalogue, les émetteurs et les abonnés. Le `name` d'un abonné est stocké en base : ne jamais le renommer sans migration.

Exploitation : `python manage.py dispatch_outbox --stats` (décomptes ; code de sortie 1 s'il existe une livraison `dead`), `--requeue <id|dead>` (relance journalisée dans l'AuditLog, comme l'action « Relancer » de l'admin Django, qui n'affiche pas les charges utiles). `purge_outbox` supprime les événements traités après 7 jours (`OUTBOX_RETENTION_DAYS`) et en échec définitif après 30 jours (`OUTBOX_DEAD_RETENTION_DAYS`). En test, utiliser `apps.platform_core.testing.dispatch_outbox_now()` pour diffuser de façon synchrone.

**Vérification manuelle de la concurrence** (hors `manage.py test`, la base de test en mémoire n'accepte pas les accès parallèles) : `SECRET_KEY=... NUM_PROXIES=1 python scripts/check_outbox_concurrency.py --events 60 --workers 3`. Elle sème une base SQLite temporaire, lance plusieurs `dispatch_outbox` en parallèle et vérifie l'absence de doublon, de perte et de « database is locked ». À refaire après toute modification de `platform_core/services.py` et avant le passage à MySQL.

Les totaux `views_count` et `shares_count` d'une offre sont recalculés à la source : **les compteurs journaliers de `visibility` sont la seule source** (pas de `max()` avec la valeur stockée ; une valeur divergente est écrasée au prochain événement) : la valeur `shares_count` renvoyée par l'endpoint de partage est « au mieux » (à jour dans le cas normal, sinon le total précédent).

## Tâches planifiées (cron)

Déclarées dans `cron/crontab` (conteneur `cron`) ; chacune est une commande de gestion testée. Hors Docker, les lancer à la main ou par le cron de la machine.

| Commande | Module | Fréquence | Rôle |
|---|---|---|---|
| `purge_offer_trash` | marketplace | quotidienne, 02:00 | supprime définitivement les offres en corbeille depuis plus de N jours |
| `expire_offers` | marketplace | quotidienne, 02:05 | expire les offres échues, notifie les échéances proches |
| `lift_expired_sanctions` | moderation | quotidienne, 02:10 | lève les suspensions arrivées à échéance (journalisé) |
| `purge_offer_views` | visibility | quotidienne, 02:20 | purge les vues uniques anciennes |
| `purge_otp_codes` | identity | horaire | supprime les OTP expirés |
| `refresh_daily_contacts` | marketplace | horaire (:05) | recalcule les contacts du jour pour les graphiques |
| `dispatch_outbox` | platform_core | chaque minute | diffuse les événements de domaine aux abonnés |
| `purge_outbox` | platform_core | quotidienne, 02:30 | supprime les anciens événements (7 j traités, 30 j en échec) |

Anciens noms (reset R3) : `purge_trash`, `expire_posts`, `cleanup_otp_codes`, `refresh_dashboard_aggregates`.

## Rôles

`setup_roles` (idempotent, lancé au démarrage du conteneur) recale les groupes `Modérateur` et `Administrateur` exactement sur les tables de `moderation/management/commands/setup_roles.py` (moindre privilège : pas d'accès aux messages, notifications, OTP ni à `payments`). Il échoue si une permission listée n'existe pas.

### Droits de modération et données personnelles

- L'API `/api/moderation/` exige les droits Django portés par les groupes (`moderation.view_report`, `change_report`, `view_sanction`, `add_sanction`) : un compte `is_staff` sans groupe n'a aucun accès. Suspension, bannissement et leur levée : administrateur seulement. Un signalement est ouvert à tout utilisateur connecté (10 par heure) mais sa réponse reste minimale pour lui.
- **Consigne** : ne jamais écrire de donnée personnelle (e-mail, téléphone, adresse, pièce d'identité) dans les notes de décision, les motifs de sanction (`reason`), les descriptions de signalement ni les `details` du journal d'audit. Ces textes sont libres, conservés et lus par le personnel.
- Le groupe Modérateur a `identity.user view` : l'admin Django lui montre l'e-mail et le téléphone des comptes. Finalité : instruction des vérifications KYC et des signalements. **À valider avec LEG-PRV** (et durée de conservation du journal et des signalements, question ouverte).
- Le Modérateur a `reviews.review change` uniquement pour masquer ou réafficher un avis : `ReviewAdmin` rend tous les autres champs en lecture seule pour lui (seul un super-administrateur réécrit un avis).
