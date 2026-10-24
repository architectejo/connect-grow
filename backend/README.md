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
- Organisations (L0-09g, ADR 0006 §9.2) : `GET /api/accounts/organizations/` remplace `businesses/` (supprimé, 404). Liste publique paginée, filtres `search` (100 caractères au plus), `org_type`, `claim` (ex. `RCCM_VERIFIED`) et `fully_verified=true|false` ; toute valeur invalide donne un 400. Aucune donnée personnelle ni NIF. `POST organizations/` (téléphone de connexion vérifié exigé, 5 créations par jour), `GET organizations/<uuid>/internal/`, `PATCH organizations/<uuid>/`, `POST .../archive/`, `POST .../leave/` et `GET organizations/limits/`. L'en-tête `X-Context` est ignoré sur ces routes.
- `register/` et `me/` n'ont plus de `user_type` ni de `business_profile` (un ancien client qui les envoie encore n'a aucun effet) ; `phone_verified` est exposé en lecture seule.

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
| `visibility` | compteurs journaliers, vues uniques, réglages du classement (`RankingSettings`) |
| `reviews` | avis après contact (deux notes, preuve de contact), réglages `ReviewSettings` ; ni Trust Score ni `Deal` (retirés par L0-07) |
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
| `marketplace.contact_recorded` | marketplace | `messaging.open_contact_conversation`, `notifications.notify_contact` | identifiants (contact, offre, vendeur, expéditeur), `channel` (`MESSAGE`, `CALL`, `WHATSAPP`) et titre public de l'offre ; ni message ni nom |
| `marketplace.exchange_proposed` | marketplace | `messaging.open_exchange_conversation`, `notifications.notify_exchange` | idem (`proposal_id`) |
| `marketplace.offer_expiring_soon` (v2) | marketplace | `notifications.notify_offer_expiration` | offre, titre, contexte vendeur (`seller_context_type/id`), échéance ; destinataires (`offer.edit`) résolus à la livraison |
| `visibility.offer_viewed` | visibility | `marketplace.sync_offer_views` | offre, date |
| `visibility.offer_shared` | visibility | `marketplace.sync_offer_shares` | offre, date |
| `visibility.ranking_settings_changed` | visibility (admin) | `marketplace.refresh_scores_after_ranking_change` | liste des champs modifiés ; recalcul idempotent des scores |
| `reviews.review_posted` (v3) | reviews | `notifications.notify_review_posted` | auteur, contexte vendeur (`seller_context_type/id`), identifiants et titre public de l'offre ; plus de `recipient_id` : destinataires (`review.reply`) résolus à la livraison ; nom de l'auteur et extrait relus à la diffusion |
| `reviews.review_replied` | reviews | `notifications.notify_review_reply` | identifiants, contexte vendeur et titre public de l'offre ; l'auteur de l'avis voit le nom du vendeur (organisation, prestataire, personne), jamais celui du membre |
| `identity.membership_changed` | identity | `notifications.notify_membership_change`, `notifications.purge_context_notifications` | organisation, compte concerné, type de changement, rôles, auteur ; ni nom ni coordonnée ; la révocation supprime les notifications de l'organisation du membre |
| `identity.seller_context_status_changed` | identity | `marketplace.sync_seller_visibility`, `notifications.notify_organization_status` | contexte, motif normalisé, auteur ; propriétaires et administrateurs prévenus (organisation seulement) |
| `identity.organization_verification_changed` | identity | `notifications.notify_kyb_decision` | organisation, type de pièce, décision ; ni motif ni décideur |
| `reviews.crossed_reviews_detected` (v2) | reviews | `moderation.file_crossed_reviews_report` | avis, deux comptes, `reviews_count` (couples auteur-offre), fenêtre en jours |

Ajouter un événement : déclarer le type dans `platform_core/catalog.py`, publier avec `publish_event('<domaine>.<fait>', ...)` (type littéral), écrire l'abonné idempotent dans `events.py` du domaine récepteur (il n'appelle que des `services.py`). Un contrôle Django (`platform_core.E001`/`E002`) et des tests de frontières vérifient le catalogue, les émetteurs et les abonnés. Le `name` d'un abonné est stocké en base : ne jamais le renommer sans migration.

Exploitation : `python manage.py dispatch_outbox --stats` (décomptes ; code de sortie 1 s'il existe une livraison `dead`), `--requeue <id|dead>` (relance journalisée dans l'AuditLog, comme l'action « Relancer » de l'admin Django, qui n'affiche pas les charges utiles). `purge_outbox` supprime les événements traités après 7 jours (`OUTBOX_RETENTION_DAYS`) et en échec définitif après 30 jours (`OUTBOX_DEAD_RETENTION_DAYS`). En test, utiliser `apps.platform_core.testing.dispatch_outbox_now()` pour diffuser de façon synchrone.

**Vérification manuelle de la concurrence** (hors `manage.py test`, la base de test en mémoire n'accepte pas les accès parallèles) : `SECRET_KEY=... NUM_PROXIES=1 python scripts/check_outbox_concurrency.py --events 60 --workers 3`. Elle sème une base SQLite temporaire, lance plusieurs `dispatch_outbox` en parallèle et vérifie l'absence de doublon, de perte et de « database is locked ». À refaire après toute modification de `platform_core/services.py` et avant le passage à MySQL.

Les totaux `views_count` et `shares_count` d'une offre sont recalculés à la source : **les compteurs journaliers de `visibility` sont la seule source** (pas de `max()` avec la valeur stockée ; une valeur divergente est écrasée au prochain événement) : la valeur `shares_count` renvoyée par l'endpoint de partage est « au mieux » (à jour dans le cas normal, sinon le total précédent).

## Avis, notes et réglages (L0-07, ADR 0004)

- **Pas de score de confiance** (règle 4). Les moyennes ne sont jamais stockées : `reviews.services.get_offer_ratings` et `get_seller_ratings` les calculent à la lecture (somme et nombre en base, arrondi à une décimale, demi supérieur) ; une moyenne est `null` sous `ReviewSettings.min_reviews_to_display`, le nombre d'avis reste exact ; un avis masqué sort de toutes les notes. Les offres portent `offer_rating` et `seller_rating` (`{average, count}`), jamais fusionnés.
- **Un avis = un visiteur, une offre** (unicité `(auteur, offre)` en base) ; il note l'offre et son vendeur, après une prise de contact (`marketplace.get_review_contact`, tous canaux). La note vendeur qui compte est la dernière non masquée de chaque auteur pour un même vendeur : drapeau `counts_for_seller` recalculé par `reviews.services.reconcile_seller_flag` (couche service, pas de contrainte conditionnelle).
- **Droit d'avis et garde-fous (L0-10, T3).** `GET /api/interactions/reviews/eligibility/?post=<uuid>` (authentifié, portée `review_eligibility`) renvoie `{can_review, reason, available_at, review_id}` ; `reason` : `own_offer`, `no_contact`, `contact_rejected`, `already_reviewed`, `recently_deleted`, `offer_unavailable`, `too_early` (avec `available_at` = plus ancien contact + `delay_after_contact_hours`, borne incluse). Une offre inconnue ou non publique que l'appelant n'a pas contactée répond le même 404 `offer_not_found`. `POST /reviews/` applique la même évaluation (`reviews.services.assess_eligibility`) : 403 `own_offer`, `not_eligible`, `contact_rejected`, `review_too_early` ; 404 `offer_not_found` (offre inconnue, ou non publique sans contact) ; 409 `already_reviewed`, `review_recently_deleted`, `offer_unavailable` ; 429 `daily_limit` (puis throttle `review`, 429 `throttled`). Les canaux MESSAGE, CALL et WHATSAPP comptent tous comme preuve de contact.
- **Contact fictif.** Le vendeur concerné signale un avis avec `POST /api/moderation/reports/` (`target_type=REVIEW`, `reason=CONTACT_FICTIF`) : 403 `not_seller` pour tout autre appelant, 400 `invalid_reason` hors avis, 409 `duplicate_report` s'il existe un signalement ouvert. Le dépôt est journalisé (`CONTACT_FICTIF_REPORTED`), entre dans la file de modération (statut « en attente », compteur du tableau de bord) et gèle l'avis pour son auteur sans le masquer. Quand le modérateur le « résout » (API ou admin), `moderation.services.apply_resolution` appelle `reviews.services.reject_fictitious_contact` : l'avis est masqué (`REVIEW_HIDDEN`), l'auteur ne peut plus le supprimer ni en écrire un autre pour l'offre (`contact_rejected`). Un rejet laisse l'avis intact. Aucun effet sur le classement (règle 4).
- **Champs du recours (L0-20).** Pour l'auteur de l'avis seulement (`is_mine`), la lecture d'un avis expose `contest_report_id` (signalement « contact fictif » ouvert, sinon `null`), `contest_responded` et `can_delete` (faux si avis masqué, réponse du vendeur reçue ou signalement grave ouvert). `can_edit` reste vrai pendant un signalement ouvert (le verrou ne porte que sur la suppression). Le recours a sa propre portée de débit `report_response` (30/h). Limite connue : le plafond quotidien de signalements n'est pas atomique entre requêtes simultanées. Déploiement : `NUM_PROXIES=1` est obligatoire derrière Nginx (`common.E001`).
- **Recours et garde-fous (corrections d'intégration).** L'auteur d'un avis signalé « contact fictif » est notifié (dépôt, décision) et peut répondre une fois : `POST /api/moderation/reports/{id}/author-response/`. Un signalement grave ouvert interdit la suppression de l'avis, pas sa modification. `ModerationSettings` règle le délai cible (tableau de bord : `overdue_contact_fictif_count`) et le plafond quotidien de signalements « contact fictif » ; un avis déjà rejeté pour ce motif ne peut plus être signalé (`report_already_rejected`). `ReviewSettings.min_account_age_hours` (403 `account_too_new`) et un délai contact-avis d'au moins 1 h. `GET /posts/` est limité (`offer_list`).
- **Réglages en base** (règle 11, modifiés dans l'admin, journalisés dans l'`AuditLog` avec ancienne et nouvelle valeur) : `reviews.ReviewSettings` (seuil d'affichage, limite quotidienne, fenêtre de modification, délai après contact, avis croisés), `marketplace.MarketplaceSettings.duplicate_contact_window_hours`, `visibility.RankingSettings` (poids vues 1, favoris 3, contacts 5, partages 8, demi-vie 72 h, proximité 1,2 / 1,1 / 1,0 ; validation dans `clean()`). Le score stocké sur l'offre est E x R ; la proximité D est appliquée à la lecture (section suivante).
- **Format d'erreur** (`common.exception_handler`) : toute erreur hors champ vaut `{"detail": "<message français>", "code": "<code_machine>"}` ; les erreurs de champs gardent le format DRF.
- **Contextes** : `common/contexts.py` (constantes `USER` / `ORGANIZATION`), `identity.services.acts_for_context` et `public_display_name` sont les coutures que L0-09 étendra aux organisations.

## Classement organique P x E x R x D (L0-08, CDC 3.5, ADR 0004)

- **Stocké** : `Offer.visibility_score = E x R`. E = `1 + ln(1 + w_v.vues + w_f.favoris + w_c.contacts + w_s.partages)`, R = `0,5 ** (âge / demi-vie)`. Aucune note, aucun avis, aucun terme « Sponsorisé » (règles 4 et 5). Tous les poids viennent de `visibility.RankingSettings`.
- **Recalcul** (`marketplace.services.refresh_visibility_score` pour une offre, `refresh_all_scores` en lot), toujours depuis les compteurs sources, donc rejouable : vue ou partage (événements), favori ajouté ou retiré, contact (`create_contact_event`, même transaction), réglages modifiés (événement `visibility.ranking_settings_changed`), récence (commande `refresh_visibility_scores`, cron :15 chaque heure, affiche « N offres mises à jour. »), action d'administration `recalculate_all_scores`. Le lot recompte aussi `likes_count` (depuis `Favorite`) et `contacts_count` (depuis `ContactEvent.is_counted`).
- **Contact compté** : `ContactEvent.is_counted` vaut vrai pour le premier contact d'un expéditeur sur une offre dans la fenêtre `MarketplaceSettings.duplicate_contact_window_hours`, tous canaux confondus ; `count_contacts_by_offer` (graphiques du tableau de bord) et `contacts_count` utilisent ce même filtre.
- **Lecture** : pour le tri par défaut `-visibility_score`, la liste `GET /api/marketplace/posts/` ordonne par `visibility_score x D` dans la requête SQL (`Case/When` + `ExpressionWrapper`, pagination exacte), puis `-created_at`, puis `id` (ordre stable). D = `proximity_same_commune` / `proximity_same_city` / `proximity_default`. Commune de référence : paramètre `near=<uuid commune>` (invalide : ignoré), sinon commune du profil de l'utilisateur connecté, sinon aucune proximité. D n'est jamais exposé. Les autres valeurs de `ordering` ne changent pas. P = 1 (recherche et catégorie sont des filtres stricts).

## Tâches planifiées (cron)

Déclarées dans `cron/crontab` (conteneur `cron`) ; chacune est une commande de gestion testée. Hors Docker, les lancer à la main ou par le cron de la machine.

| Commande | Module | Fréquence | Rôle |
|---|---|---|---|
| `purge_offer_trash` | marketplace | quotidienne, 02:00 | supprime définitivement les offres en corbeille depuis plus de N jours |
| `expire_offers` | marketplace | quotidienne, 02:05 | expire les offres échues, notifie les échéances proches |
| `lift_expired_sanctions` | moderation | quotidienne, 02:10 | lève les suspensions arrivées à échéance (journalisé) |
| `purge_offer_views` | visibility | quotidienne, 02:20 | purge les vues uniques anciennes |
| `purge_otp_codes` | identity | horaire | supprime les OTP expirés |
| `refresh_daily_contacts` | marketplace | horaire (:05) | recalcule les contacts comptés du jour pour les graphiques |
| `refresh_visibility_scores` | marketplace | horaire (:15) | recalcule le score organique E x R (récence, favoris et contacts recomptés) |
| `dispatch_outbox` | platform_core | chaque minute | diffuse les événements de domaine aux abonnés |
| `purge_outbox` | platform_core | quotidienne, 02:30 | supprime les anciens événements (7 j traités, 30 j en échec) |

Anciens noms (reset R3) : `purge_trash`, `expire_posts`, `cleanup_otp_codes`, `refresh_dashboard_aggregates`.

## Rôles

`setup_roles` (idempotent, lancé au démarrage du conteneur) recale les groupes `Modérateur` et `Administrateur` exactement sur les tables de `moderation/management/commands/setup_roles.py` (moindre privilège : pas d'accès aux messages, notifications, OTP ni à `payments`). Il échoue si une permission listée n'existe pas.

### Droits de modération et données personnelles

- L'API `/api/moderation/` exige les droits Django portés par les groupes (`moderation.view_report`, `change_report`, `view_sanction`, `add_sanction`) : un compte `is_staff` sans groupe n'a aucun accès. Suspension, bannissement et leur levée : administrateur seulement. Un signalement est ouvert à tout utilisateur connecté (10 par heure) mais sa réponse reste minimale pour lui.
- **Consigne** : ne jamais écrire de donnée personnelle (e-mail, téléphone, adresse, pièce d'identité) dans les notes de décision, les motifs de sanction (`reason`), les descriptions de signalement ni les `details` du journal d'audit. Ces textes sont libres, conservés et lus par le personnel.
- Le groupe Modérateur a `identity.user view` : l'admin Django lui montre l'e-mail et le téléphone des comptes. Finalité : instruction des vérifications KYC et des signalements. **À valider avec LEG-PRV** (et durée de conservation du journal et des signalements, question ouverte).
- Le Modérateur a `reviews.review change` uniquement pour masquer ou réafficher un avis : `ReviewAdmin` rend tous les autres champs en lecture seule pour lui (seul un super-administrateur réécrit un avis, hors preuve de contact et drapeau calculé, toujours en lecture seule). Les réglages des avis (`reviews.reviewsettings`) relèvent de l'Administrateur.
