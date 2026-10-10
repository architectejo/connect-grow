# ADR 0005 — Contact vendeur : consentement par canal et révélation du numéro (L0-10a-b à e)

- **Statut :** accepté (chef de projet, 10/10/2026, décisions déléguées par le client) ; les points LEG-PRV (section 9) restent ouverts.
- **Date :** 10/10/2026
- **Rédaction :** architecte-technique
- **Références :** CLAUDE.md §4 (règles 1, 3, 10, 11, 12) et §5 ; CDC v1.2 §3.15 ; `docs/specs/avis-classement-contact.md` (L0-10a-b à e, D12 à D16, section 3 LEG-PRV) ; ADR 0002 (frontières), 0003 (outbox), 0004 (avis après contact) ; doc13 (`ContactPoint`, `ContactAction`).

## 1. Contexte

Le CDC §3.15 prévoit « au choix un appel, une conversation WhatsApp ou un message interne », avec enregistrement de chaque prise de contact. Aujourd'hui, seule l'action « message » existe (`POST /api/interactions/contacts/`, `marketplace.ContactEvent`, événement `marketplace.contact_recorded`). Aucun numéro n'est exposé par l'API (test `apps/common/tests_privacy.py::test_no_phone_reveal_route`). Il faut ouvrir les canaux « appel » et « WhatsApp » sans jamais publier un numéro que le vendeur n'a pas décidé de partager (règle 10), avec trace (règle 12).

Dette constatée : le numéro de connexion (`identity.User.phone`) est le seul numéro du compte. Le réutiliser comme numéro de contact publierait un identifiant de connexion sans que son titulaire le sache.

## 2. Décisions

| # | Décision |
|---|---|
| C1 | **Deux objets dans `identity`** : `ContactPoint` (numéro de contact, distinct du numéro de connexion, D12) et `ContactConsent` (un accord par compte et par canal). `identity` est propriétaire des données personnelles et du consentement ; personne d'autre n'écrit dedans. |
| C2 | **Trois canaux** : `MESSAGE`, `CALL`, `WHATSAPP`. Défaut : `MESSAGE` actif, `CALL` et `WHATSAPP` inactifs. Accord par compte (pas par offre), révocable à tout moment, effet immédiat sur les révélations futures. `MESSAGE` peut aussi être désactivé (le vendeur choisit « quels moyens »), mais la ligne de consentement `MESSAGE` n'a pas besoin de texte versionné. |
| C3 | **Numéro de contact** : un seul par compte en V1, au format E.164 (`+243…`), vérifié par code SMS. Pré-rempli avec le numéro de connexion **proposé, jamais copié sans geste** : le vendeur confirme explicitement « Utiliser mon numéro de connexion ». Si ce numéro est déjà `phone_verified`, la copie est vérifiée d'emblée ; sinon, code SMS. Changer le numéro de contact **révoque automatiquement** `CALL` et `WHATSAPP` jusqu'à vérification du nouveau numéro et nouvelle acceptation. Changer le numéro de connexion ne modifie pas le numéro de contact. |
| C4 | **Consentement éclairé** : l'activation de `CALL` ou `WHATSAPP` exige `text_version` (version courante du texte, constante `CONTACT_CONSENT_TEXT_VERSION` côté `identity`). Le texte français est dans les fichiers i18n du front, clé par version ; le serveur ne stocke que la version. Texte obligatoire : quel numéro (masqué), qui le voit (tout utilisateur connecté qui clique), comment retirer l'accord, mention que WhatsApp (Meta) reçoit le numéro. Version périmée : refus `consent_version_mismatch`. |
| C5 | **Qui orchestre la révélation : `marketplace`** (propriétaire de l'offre et de `ContactEvent`). Il lit le numéro par `identity.services.get_contact_endpoint(seller_id, channel)` (lecture seule, lève `ChannelNotConsented`). Aucun modèle importé, aucune transaction à cheval : la lecture d'`identity` précède la transaction `marketplace`, et le numéro n'est renvoyé qu'**après** le commit de `ContactEvent` + outbox. Le consentement est relu juste avant l'écriture (fenêtre de course de quelques ms acceptée, section 8). |
| C6 | **Une révélation = une prise de contact** : un `ContactEvent` (canal `CALL`/`WHATSAPP`, `message` vide autorisé pour ces canaux), `is_counted` selon la règle existante, `delivered_at = created_at`. Événement outbox **distinct** : `marketplace.contact_revealed` (pas `contact_recorded`, car `messaging` ouvrirait une conversation vide). Charge utile : `contact_event_id`, `offer_id`, `offer_title`, `seller_id`, `sender_id`, `channel`. **Jamais de numéro, ni du vendeur ni du visiteur.** |
| C7 | **Abonnés** : `notifications` écoute `marketplace.contact_revealed` (notification au vendeur « [Nom] a demandé votre numéro pour [Offre] », nom via `identity.services.public_display_name`) ; `moderation` n'écoute rien (l'`AuditLog` est écrit par `marketplace` via `moderation.services.record_audit`, dans la transaction `marketplace` ; l'`AuditLog` est une trace, pas un état métier partagé : écart accepté de l'ADR 0003 section sur les transactions, déjà pratiqué par le code existant). |
| C8 | **Idempotence** : même visiteur, même offre, même canal `CALL`/`WHATSAPP` dans la fenêtre `duplicate_contact_window_hours` (24 h) : le contact est renvoyé de nouveau (200, `created: false`), sans nouveau `ContactEvent`, sans consommer le quota, **mais avec une entrée d'audit** (`contact.number_revealed`) car le numéro sort. Si le consentement a été révoqué entre-temps : 403, même pour un doublon. |
| C9 | **Limites réglables en back-office** (règle 11), dans `marketplace.MarketplaceSettings` : `reveal_daily_limit_account` (15), `reveal_daily_limit_new_account` (3), `new_account_hours` (24). Comptage par `ContactEvent` (canaux `CALL`/`WHATSAPP`, `sender`, 24 h glissantes), donc indépendant du cache. Limite **par IP** (30/h) : throttle DRF `contact_reveal_ip` dans `DEFAULT_THROTTLE_RATES` (paramètre d'infrastructure, comme les autres scopes ; écart assumé à la règle 11 pour ne pas persister d'adresse IP tant que LEG-PRV-07 n'a pas répondu). Compte « neuf » = ancienneté < `new_account_hours` **ou** `phone_verified` et e-mail vérifié tous deux faux. |
| C10 | **Preuve « message réellement échangé »** pour l'éligibilité aux avis : `ContactEvent.delivered_at` (nullable). `MESSAGE` : renseigné quand `messaging` a posé le message dans la conversation (événement `messaging.contact_message_delivered`, abonné `marketplace`). `CALL`/`WHATSAPP` : égal à `created_at` (le numéro a été effectivement remis). `get_review_contact` ne retient que les contacts `is_counted` **et** `delivered_at` non nul. Un message perdu (événement en échec définitif) n'ouvre donc pas de droit d'avis. La réponse du vendeur n'est pas exigée (le silence ne doit pas bloquer l'avis). D14 inchangée : un contact `CALL`/`WHATSAPP` ouvre le droit d'avis. |
| C11 | **`allowed_channels`** dans la fiche et la liste des offres : liste de codes (`["MESSAGE","CALL"]`), calculée par `identity.services.get_allowed_channels(seller_ids)` (une requête pour la page, motif `PreloadingListSerializer`). Un canal `CALL`/`WHATSAPP` n'y figure que si consentement actif **et** numéro de contact vérifié. Jamais de numéro, de dernier chiffre ni de masque dans la fiche. |
| C12 | **Aucun accès modérateur ou administrateur au numéro via l'API** (test existant conservé et étendu). Question LEG-PRV-12 ouverte pour l'admin Django. |

## 3. Modèle de données

### 3.1 `identity.ContactPoint` (nouveau)

| Champ | Type | Contrainte |
|---|---|---|
| `id` | UUID | PK (BaseModel) |
| `user` | OneToOneField(User, CASCADE) | un numéro de contact par compte |
| `phone` | CharField(20) | format `phone_validator` existant, E.164 |
| `is_verified` | BooleanField | défaut faux |
| `verified_at` | DateTimeField null | |
| `created_at`, `updated_at` | via BaseModel | |

Pas d'unicité sur `phone` (un numéro d'entreprise peut être partagé entre comptes). Index : aucun autre que l'unicité de `user`.

### 3.2 `identity.ContactConsent` (nouveau)

| Champ | Type | Contrainte |
|---|---|---|
| `user` | FK(User, CASCADE) | |
| `channel` | CharField(10) | `MESSAGE`, `CALL`, `WHATSAPP` |
| `is_granted` | BooleanField | défaut faux (vrai pour `MESSAGE` à la création du compte) |
| `text_version` | CharField(20, blank) | version acceptée |
| `granted_at`, `revoked_at` | DateTimeField null | |
| `phone_last4` | CharField(4, blank) | 4 derniers chiffres du numéro couvert, pour la preuve d'accord (le numéro complet reste dans `ContactPoint`) |
| `revoked_reason` | CharField(20, blank) | `user`, `phone_changed`, `moderation` |

Contrainte : `UniqueConstraint(user, channel)` inconditionnelle (portable). Les lignes manquantes valent « désactivé » (sauf `MESSAGE`), créées à la demande (`get_or_create` dans le service).

### 3.3 `marketplace.ContactEvent` (modifié)

- `delivered_at` DateTimeField null (C10).
- `message` : le champ reste obligatoire pour `MESSAGE` (validation au serializer, 1 à 2000 caractères) ; autorisé vide pour `CALL`/`WHATSAPP` (`blank=True`, `default=''`).
- Index nouveau : `(sender, channel, created_at)` nommé `contact_sender_channel_created` (comptage des quotas).

### 3.4 `marketplace.MarketplaceSettings` (ajout de 3 champs)

`reveal_daily_limit_account` (PositiveInteger, défaut 15, 1 à 1000), `reveal_daily_limit_new_account` (défaut 3, 1 à 1000), `new_account_hours` (défaut 24, 0 à 720). Modification journalisée par `moderation.services.record_settings_change` comme les réglages existants.

### 3.5 Migrations

- `identity` : `000N_contactpoint_contactconsent`. Données : aucune ligne à créer (les consentements sont créés à la demande, `MESSAGE` implicite actif). Retour arrière : suppression des deux tables.
- `marketplace` : `0000N_contactevent_delivered_at_and_reveal_limits`. Migration de données : `delivered_at = created_at` pour les `ContactEvent` existants (ils ont tous déjà une conversation, ou n'en auront pas : on ne rejoue pas). Retour arrière : suppression des colonnes, la donnée de remplissage n'est pas restituée.
- Aucune réinitialisation (ADR 0002 non invoqué). Test : migration appliquée sur base vierge et sur base contenant des `ContactEvent` (`delivered_at` rempli).

## 4. Services

`identity/services.py` (nouveaux) :

- `get_contact_settings(user)` : état complet pour l'écran (section 5.1).
- `set_contact_phone(user, *, phone=None, use_login_phone=False)` : crée ou remplace le `ContactPoint` ; révoque `CALL`/`WHATSAPP` (`phone_changed`) ; envoie un code SMS si non vérifié (réutilise l'infrastructure OTP, nouveau but `CONTACT_VERIFY`) ; écrit l'`AuditLog` (`contact.phone_changed`, sans numéro).
- `verify_contact_phone(user, code)` : marque vérifié ; ne réactive aucun canal.
- `set_channel_consent(user, channel, *, enabled, text_version=None)` : applique C2/C4 ; `AuditLog` `contact.consent_granted` / `contact.consent_revoked` (canal, version, jamais le numéro).
- `get_allowed_channels(seller_ids) -> dict[UUID, list[str]]` (C11).
- `get_contact_endpoint(seller_id, channel) -> ContactEndpoint(phone_e164)` ; lève `ChannelNotConsented` si le canal n'est pas actif, si le numéro n'est pas vérifié ou si le compte est inactif.
- `get_account_age_info(user_id)` : `(created_at, phone_verified, email_verified)` pour le palier « compte neuf » (évite que `marketplace` lise `User` directement ; il reçoit l'objet utilisateur de la requête, voir tâche T2).

`marketplace/services.py` :

- `reveal_contact(*, offer, sender, channel, request_meta) -> RevealResult` : enchaîne `_check_can_contact` (propre annonce, indisponible), sanction du visiteur, quotas (C9), `identity.get_contact_endpoint`, puis transaction : doublon (C8) sinon `ContactEvent` + `recount_contacts` + score + `publish_event('marketplace.contact_revealed')` + `record_audit`. Retourne `phone`, `contact_event_id`, `created`.
- `create_contact_event` (message) : ajoute le contrôle `MESSAGE` consenti (`channel_not_allowed`), garde le comportement existant.
- `list_reveals_for_seller(seller, channel=None)` : lignes `ContactEvent` de ses offres, canaux `CALL`/`WHATSAPP`, plus récentes d'abord ; noms résolus par `identity.get_full_names` + `public_display_name`.
- `mark_contact_delivered(contact_event_id)` (abonné à `messaging.contact_message_delivered`), idempotent.
- `get_review_contact` : filtre `delivered_at` non nul (C10).

`messaging/services.py` : `open_conversation_with_message` publie `messaging.contact_message_delivered` (charge `contact_event_id`) dans la transaction qui crée le message, à partir de l'événement d'origine. Les propositions d'échange ne le publient pas. Types à ajouter au catalogue `platform_core/catalog.py` : `marketplace.contact_revealed`, `messaging.contact_message_delivered`.

`moderation/services.py` : `is_user_restricted(user_id) -> bool` (sanction active empêchant le contact) à ajouter si absente (aucune fonction équivalente n'a été trouvée).

## 5. Contrat d'API (préfixes actuels ; L0-11 migrera vers `/api/v1/`)

Format d'erreur : `{"detail": "<français>", "code": "<code_machine>"}`. Validation de champs : `{"<champ>": ["…"]}` (DRF), code 400. Toutes les routes : authentifiées par JWT (`IsAuthenticated`), sauf mention contraire.

### 5.1 Réglages de contact du vendeur (domaine `identity`, préfixe `/api/accounts/`)

**GET `/api/accounts/contact-settings/`** → 200
```json
{
  "phone": {
    "masked": "+243 81 *** ** 45",
    "is_verified": true,
    "login_phone_masked": "+243 81 *** ** 45",
    "can_use_login_phone": true
  },
  "channels": {
    "MESSAGE": {"enabled": true},
    "CALL": {"enabled": false, "granted_at": null, "text_version": ""},
    "WHATSAPP": {"enabled": true, "granted_at": "2026-10-10T09:12:00Z", "text_version": "2026-10-v1"}
  },
  "current_text_version": "2026-10-v1"
}
```
`phone` vaut `null` si aucun numéro de contact n'existe encore. **Écart (T2, demande du front)** : `login_phone_masked` (null si le compte n'a pas de numéro de connexion) et `can_use_login_phone` (numéro de connexion présent **et** vérifié) sont aussi exposés **à la racine** de la réponse, car `phone` est null avant le premier numéro ; ils restent dupliqués dans `phone` quand celui-ci existe. Masque : `+243 81 *** ** 45` (hors indicatif, 4 chiffres visibles au plus). `MESSAGE` n'a que `enabled`. Numéros toujours masqués (jamais le numéro complet, même au propriétaire, pour limiter les fuites par journaux et captures). `Cache-Control: no-store`.

**PUT `/api/accounts/contact-settings/phone/`** — corps : `{"use_login_phone": true}` ou `{"phone": "+243812345678"}` (exclusifs). → 200, même corps que le GET. Si `use_login_phone` et `phone_verified` : vérifié d'emblée (aucun SMS). Sinon (numéro saisi), un code SMS est envoyé et `phone.is_verified` vaut faux ; renvoyer le même numéro non vérifié renvoie un nouveau code (re-demande), et renvoyer le numéro déjà enregistré ne révoque aucun canal. Throttles : `contact_settings` plus les limites OTP existantes (`otp`, `otp_phone`, `otp_phone_day`). Le but `CONTACT_VERIFY` est refusé par l'endpoint public `otp/request/`. Erreurs : 400 `phone_invalid`, 409 `login_phone_unverified` (`use_login_phone` demandé mais `phone_verified` faux : « Vérifiez d'abord votre numéro de connexion »), 429 (throttles OTP existants).

**POST `/api/accounts/contact-settings/phone/verify/`** — corps : `{"code": "123456"}` → 200 (même corps que le GET). Erreurs : 400 `otp_invalid`, 400 `otp_expired`, 429 `otp_attempts_exceeded`, 404 `contact_phone_missing`.

**PUT `/api/accounts/contact-settings/channels/{channel}/`** — `channel` ∈ `MESSAGE`, `CALL`, `WHATSAPP`. Corps : `{"enabled": true, "text_version": "2026-10-v1"}` (`text_version` obligatoire quand `enabled` est vrai pour `CALL`/`WHATSAPP`). → 200, même corps que le GET. Erreurs : 404 `channel_unknown` ; 409 `contact_phone_unverified` (« Vérifiez d'abord votre numéro. ») ; 400 `consent_version_mismatch` (« Le texte a changé, relisez-le avant d'accepter. ») ; 400 `consent_text_required`. Désactiver est toujours permis (idempotent).

Throttle d'écriture : scope `contact_settings` (20/h par utilisateur) pour les trois routes en écriture.

### 5.2 Fiche publique (domaine `marketplace`, existant)

`GET /api/marketplace/offers/` et `/{id}/` : champ ajouté `allowed_channels: ["MESSAGE", "CALL", "WHATSAPP"]` (ordre fixe). Anonyme et authentifié le voient. Aucun numéro, aucun indice sur le numéro.

### 5.3 Contacter par message (existant, complété)

**POST `/api/interactions/contacts/`** — corps inchangé : `{"offer": "<uuid>", "message": "…1 à 2000 car."}` → 201 (corps actuel). Ajouts : 403 `channel_not_allowed` si le vendeur a désactivé `MESSAGE`. Le doublon reste en 400 mais porte désormais `code: "contact_duplicate"`. Les autres refus gardent leur statut actuel avec les codes de 5.4.

### 5.4 Révéler un numéro (domaine `marketplace`)

**POST `/api/interactions/contacts/reveal/`** — authentification obligatoire.
Corps : `{"offer": "<uuid>", "channel": "CALL" | "WHATSAPP"}`. Pas de liste d'identifiants, pas de lecture par GET (aucune route ne renvoie plusieurs numéros).

Réponse 201 (première révélation) ou 200 (renvoi idempotent, `created: false`) :
```json
{
  "contact_event_id": "uuid",
  "channel": "CALL",
  "created": true,
  "phone": "+243812345678",
  "tel_url": "tel:+243812345678",
  "whatsapp_url": null
}
```
Pour `WHATSAPP` : `tel_url` vaut `null` et `whatsapp_url` vaut `https://wa.me/243812345678?text=<titre de l'offre, encodé>` (le texte prérempli ne contient que le titre public de l'offre). En-têtes : `Cache-Control: no-store`, `Pragma: no-cache`.

| Statut | `code` | Cas |
|---|---|---|
| 400 | `channel_invalid` | canal autre que `CALL`/`WHATSAPP` (le message passe par 5.3) |
| 401 | `not_authenticated` | visiteur anonyme ; rien n'est enregistré |
| 403 | `channel_not_allowed` | consentement absent, révoqué, ou numéro non vérifié. « Ce vendeur n'accepte pas ce moyen de contact. » |
| 403 | `own_offer` | l'annonce est celle du visiteur |
| 403 | `contact_restricted` | visiteur sanctionné |
| 404 | `offer_not_found` | offre inconnue, corbeille, masquée ou expirée (pas de distinction, pas de numéro) |
| 429 | `reveal_quota_account` | plus de 15 numéros différents en 24 h (réglable) |
| 429 | `reveal_quota_new_account` | compte neuf, plus de 3 en 24 h |
| 429 | `reveal_quota_ip` | plus de 30 par heure et par IP |

Toute réponse 429 porte l'en-tête `Retry-After` (secondes) et un `detail` français qui propose le message interne en repli. Pour les quotas par compte, `Retry-After` = délai avant que la plus ancienne révélation sorte de la fenêtre.

Cas limite : une 404 pour une offre indisponible, et non 409, réduit l'énumération (on ne distingue pas « n'existe pas » de « retirée »). Le code existant renvoie une erreur 400 `MarketplaceError` pour `message` ; la route de révélation utilise 404 et ne reprend pas ce comportement. L'ordre des contrôles est : authentification, canal valide, offre, propre annonce, sanction, quotas, consentement. Le quota passe avant le consentement pour que le refus de quota ne révèle pas lequel des vendeurs a consenti.

Throttles DRF : `contact_reveal_ip` (30/hour, clé = IP, classe sur le modèle de `identity/throttles.py`) ; `contact_reveal_user` (60/hour, filet technique contre les rafales ; les vrais plafonds métier sont en base).

### 5.5 Liste « qui a demandé mon numéro » (vendeur)

**GET `/api/interactions/contacts/reveals/received/?channel=CALL|WHATSAPP&page=N`** — pagination standard du projet (`count`, `next`, `previous`, `results`). Seulement les offres du vendeur connecté. Réponse :
```json
{"count": 1, "next": null, "previous": null, "results": [
  {"id": "uuid", "channel": "WHATSAPP", "created_at": "2026-10-10T09:12:00Z",
   "requester_display_name": "Marie K.",
   "offer": {"id": "uuid", "title": "Chaussures"}}
]}
```
Aucun numéro, aucun identifiant utilisateur du visiteur, aucune photo. Le vendeur ne peut pas bloquer ni répondre depuis cette liste (lot 2). `Cache-Control: no-store`. Throttle : scope `contact_reveals_list` (120/h par utilisateur).

## 6. Journal d'audit (règle 12)

Actions `AuditLog` (acteur, cible, détails sans numéro ni IP) :

| Action | Cible | Détails |
|---|---|---|
| `contact.phone_changed` | `user` du vendeur | « Numéro de contact modifié ; CALL et WHATSAPP désactivés » |
| `contact.phone_verified` | `user` | |
| `contact.consent_granted` | `user` | canal, version du texte, 4 derniers chiffres |
| `contact.consent_revoked` | `user` | canal, motif |
| `contact.number_revealed` | `offer` | canal, vendeur (UUID), `created` vrai/faux |
| `contact.reveal_refused` | `offer` | motif (`channel_not_allowed`, quota…) ; seulement pour les refus de quota et de consentement, pas pour les 401 |
| `contact.reveal_quota_exceeded` | `user` | quota concerné ; si le compte dépasse 3 fois la limite en 7 jours, `moderation.services.file_automatic_report` ouvre un signalement (T3) |

L'adresse IP n'est pas journalisée (LEG-PRV-07 ouverte). La durée de conservation du journal est LEG-PRV-05.

## 7. Frontières de modules

- `identity` : propriétaire de `ContactPoint`, `ContactConsent`. Expose uniquement des fonctions de `services.py` (aucun modèle exporté).
- `marketplace` : propriétaire de `ContactEvent` et des limites. Appelle `identity.services` et `moderation.services`.
- `messaging` : ne connaît pas le consentement. Publie `messaging.contact_message_delivered`.
- `notifications` : réagit à `marketplace.contact_revealed`.
- Aucun nouvel import de modèle d'un autre domaine ; le test `common.tests.DomainBoundariesTests` doit rester vert. Aucune clé étrangère nouvelle entre domaines (`ContactEvent.offer`/`sender` existent déjà : `sender` pointe vers l'utilisateur, `offer` est interne à `marketplace`).

## 8. Risques de sécurité et parades

| Risque | Parade |
|---|---|
| **Scraping en masse du numéro** | Authentification obligatoire ; 15/24 h par compte, 3/24 h pour un compte neuf, 30/h par IP ; pas de route par lots ; signalement automatique à 3 dépassements en 7 jours. Limite connue : comptes multiples derrière des IP différentes ; le palier « compte neuf » et la vérification de téléphone sont la protection de fond. CAPTCHA hors périmètre, à étudier si du scraping est observé. |
| **Énumération** (qui a consenti, quelles offres existent) | `allowed_channels` est public par construction (nécessaire à l'affichage des boutons) ; la route de révélation répond 404 uniforme pour toute offre indisponible et le quota précède le consentement. Le visiteur apprend seulement ce que la fiche montre déjà. |
| **Révocation en cours de session** | Le front ne garde jamais le numéro au-delà du clic (pas de stockage, pas de cache React Query pour la mutation, `gcTime: 0`). Le serveur relit le consentement à chaque appel, y compris pour un doublon. La fenêtre de course (révocation entre la lecture d'`identity` et le commit) est de quelques millisecondes sous SQLite (écritures sérialisées) ; elle est acceptée car le numéro déjà remis n'est pas rappelable (LEG-PRV-04). L'état affiché sur la fiche peut être périmé : un 403 `channel_not_allowed` doit rafraîchir la fiche et retirer le bouton. |
| **Fuite par cache** | `no-store` sur toutes les réponses contenant un numéro (révélation) ou un numéro masqué (réglages) ; le service worker exclut ces chemins (`cache-rules.ts`) ; test front. |
| **Fuite par journaux, événements, messages d'erreur** | Numéro absent de l'outbox, de l'`AuditLog`, des notifications et des exceptions ; `tel_url`/`whatsapp_url` ne sont construits qu'à la réponse. Tests de non-fuite (section 10). |
| **Usurpation / numéro d'un tiers** | Numéro de contact vérifié par SMS avant tout canal `CALL`/`WHATSAPP` ; changement de numéro révoque les accords. |
| **Détournement du lien WhatsApp** | `wa.me` construit côté serveur depuis le numéro vérifié, avec le titre encodé seulement. |
| **Pas de numéro sans trace** | `ContactEvent` créé dans la transaction avant l'envoi de la réponse ; si l'écriture échoue, la réponse est une erreur et ne contient pas de numéro. |
| **Contact fictif pour obtenir un avis** | C10 (preuve de remise réelle) + délai D5 + signalement « contact fictif » existant (`reviews.reject_fictitious_contact`). |
| **SMS arbitraire vers un numéro saisi** (L0-24, audit m2) | Un compte sans identifiant vérifié ne peut déclencher un SMS `CONTACT_VERIFY` qu'après `CONTACT_SMS_MIN_ACCOUNT_AGE_HOURS` heures (réglage `settings.py`, 24 par défaut) ; sinon 403 `account_too_new`. Le SMS nomme son but (« code pour publier ce numéro comme contact Connecte+ ; ne le communiquez à personne »). Les limites d'envoi des OTP s'ajoutent. |
| **Course entre vérification et changement de numéro** (L0-24, audit M1) | La vérification est une mise à jour conditionnelle (`pk`, `phone` du code, non vérifié) : si le numéro a changé entre-temps, rien n'est vérifié (`otp_invalid`). La création du `ContactPoint` est verrouillée (`select_for_update`) et rattrape une création concurrente par relecture. |
| **Preuve d'accord et numéro** (L0-24, audit m1) | `get_contact_endpoint` exige que `phone_last4` du consentement égale les 4 derniers chiffres du numéro actuel ; `set_channel_consent` n'écrit pas un accord si le numéro a changé pendant l'opération. |
| **Codes OTP et administration** (L0-24, audit m3, LEG-PRV-12) | Les codes `CONTACT_VERIFY` sont supprimés dès qu'ils ont servi (le numéro ne reste pas dans `OtpCode`) et l'admin `OtpCode` exclut ce but de sa liste. Un code non utilisé disparaît avec la purge OTP existante. |
| **Dénombrement à la baisse** (rafales parallèles dépassant le quota) | Comptage en base à chaque appel ; sous SQLite les écritures sont sérialisées ; sous MySQL (fin de projet) ajouter un verrou applicatif court ou un contrôle après insertion. Dette notée, comme celle de `create_contact_event`. |

## 9. Questions LEG-PRV restantes (à poser au client, ne bloquent pas le développement)

Les numéros renvoient à la section 3 de la spec ; ce document n'en tranche aucune.

1. **LEG-PRV-01** (question 1) : la base légale de la communication du numéro à un utilisateur connecté (consentement du vendeur par canal, révocable) suffit-elle ?
2. **LEG-PRV-03** (question 2) : texte exact du consentement et valeur d'un accord donné dans les réglages avec version. La version `2026-10-v1` est un texte provisoire.
3. **LEG-PRV-03** (question 3) : un vendeur peut-il rendre son numéro public à des non-connectés ? Non prévu en V1.
4. **LEG-PRV-05** (question 4) : durée de conservation de « X a obtenu le numéro de Y pour l'offre Z » (`ContactEvent`, `AuditLog`), après clôture de compte, et sort de la trace quand le visiteur efface son compte alors que son avis reste.
5. **LEG-PRV-04** (question 5) : informer ceux qui ont déjà le numéro quand l'accord est retiré ? Le numéro déjà remis reste-t-il utilisable ?
6. **LEG-PRV-04** (question 6) : droit d'accès du visiteur aux numéros qu'il a demandés (une route « mes révélations » n'est pas livrée) ; droit d'accès du vendeur (la liste 5.5 y répond en partie).
7. **LEG-PRV-09** (question 7) : conservation d'une adresse IP ou empreinte pour l'anti-scraping. Tant que non tranché : aucune IP persistée, limite IP uniquement en cache.
8. **LEG-PRV-11** (question 8) : mention « usage limité à l'objet de l'offre » (prospection) à afficher avec le numéro.
9. **LEG-PRV-12 / 06** (question 9) : information sur la transmission du numéro à WhatsApp (Meta), transfert hors RDC.
10. **LEG-PRV-01** (question 10, D11) : forme du nom du visiteur montré au vendeur (prénom + initiale proposé, `public_display_name`).
11. **LEG-PRV-05** (question 11) : durée de conservation des avis, sans lien direct avec cet ADR.
12. **LEG-PRV-01** (question 12) : le modérateur peut-il voir le numéro et le canal lors d'un litige « contact fictif » ? Aujourd'hui non : l'API n'expose aucun numéro et le canal n'est lisible que via l'avis (`contact_channel`).

## 10. Plan de tâches

Ordre : T1, puis T2 et T3 en parallèle, puis T4 ; le front (T5, T6) démarre une fois le contrat figé (peut être développé contre des mocks dès maintenant) et se branche après T2/T3.

| Tâche | Agent | Contenu | Dépend de |
|---|---|---|---|
| **T1 — Schéma et réglages** (L0-10a-b) | dev-backend | Modèles `ContactPoint`, `ContactConsent`, champs `ContactEvent`, réglages `MarketplaceSettings`, migrations (+ données), admin des réglages, catalogue d'événements, constante de version du texte. | — |
| **T2 — Consentement et numéro de contact** (L0-10a-b) | dev-backend | Services `identity` (section 4), 4 endpoints 5.1, nouveau but OTP `CONTACT_VERIFY`, throttle `contact_settings`, `AuditLog`, `allowed_channels` dans `OfferSerializer`/liste (une requête par page). | T1 |
| **T3 — Révélation et liste vendeur** (L0-10a-c, d) | dev-backend | `marketplace.reveal_contact`, endpoints 5.4 et 5.5, throttles, quotas, `no-store`, événement `contact_revealed`, abonné `notifications`, `is_user_restricted`, signalement automatique, contrôle `MESSAGE` consenti dans 5.3. | T1, T2 (`get_contact_endpoint`) |
| **T4 — Preuve de remise et avis** (L0-10a-c / L0-10) | dev-backend | `messaging.contact_message_delivered`, abonné `marketplace.mark_contact_delivered`, filtre dans `get_review_contact`, `delivered_at` du backfill. | T1 ; indépendant de T2/T3, parallélisable avec T3 |
| **T5 — Écran de consentement** (L0-10a-b) | dev-frontend | Section « Contact » dans `Settings` : numéro (proposé/saisi, code SMS), trois interrupteurs, dialogue de consentement versionné (textes i18n), états d'erreur, tests. Spec d'écran du designer-ux souhaitable pour le dialogue. | contrat (mocks) ; branchement après T2 |
| **T6 — Boutons de contact** (L0-10a-e) | dev-frontend | `ContactActions.tsx` : boutons selon `allowed_channels`, mutation de révélation (`gcTime: 0`, bouton désactivé en chargement), ouverture de `tel:`/`wa.me`, messages 401 (redirection connexion puis retour), 403 (rafraîchit la fiche), 429 (texte + repli message), liste « Qui a demandé » dans le tableau de bord vendeur, `HowItWorks` mis à jour, exclusion du cache dans `cache-rules.ts`. | contrat ; branchement après T3 |
| **T7 — Tests de non-fuite** | qa-testeur (ou dev-backend) | Section 11. | T2, T3 |
| Relecture / sécurité | relecteur-code, auditeur-securite (obligatoire : données personnelles) | Sur T2+T3 avant T7. | |

Chaque tâche est livrée avec ses tests ; le front exécute `npm run lint && npm run test && npm run build`.

## 11. Critères d'acceptation techniques et tests de non-fuite

Reprendre les critères de la spec (L0-10a-b, c, d, e) ; ajouts précis :

- [ ] Nouveau compte : `GET /contact-settings/` renvoie `MESSAGE` actif, `CALL` et `WHATSAPP` inactifs, `phone: null`.
- [ ] Activation refusée sans numéro vérifié (`contact_phone_unverified`), sans `text_version` (`consent_text_required`), avec une version périmée (`consent_version_mismatch`).
- [ ] Changement de numéro : `CALL` et `WHATSAPP` passent à inactif (`revoked_reason=phone_changed`), `AuditLog` écrit.
- [ ] Révocation puis révélation : 403 `channel_not_allowed`, y compris pour le même visiteur dans les 24 h.
- [ ] Révélation : un seul `ContactEvent`, un `AuditLog`, un événement outbox sans numéro ; second appel : 200, `created: false`, un second `AuditLog`, pas de second `ContactEvent`, quota inchangé.
- [ ] Quotas 15/3/30 : chaque dépassement donne 429 + `Retry-After` + code distinct ; les valeurs changent dès modification dans le back-office.
- [ ] Les réponses 5.1 et 5.4 portent `Cache-Control: no-store`.
- [ ] Avis : un `ContactEvent` `MESSAGE` sans `delivered_at` n'ouvre pas le droit d'avis ; un `CALL` révélé l'ouvre (après le délai D5).
- [ ] Le vendeur voit dans 5.5 le nom d'affichage et l'offre, jamais d'identifiant ni de numéro du visiteur.

Extension de `apps/common/tests_privacy.py` (classe dédiée, mêmes jeux de données que les tests existants) :

1. Aucun numéro de contact ni de connexion dans : liste et détail des offres (avant et après consentement, `allowed_channels` seul), profils vendeur, recherche, réponses d'écriture, notifications, conversations, avis, tableaux de bord.
2. Recherche par numéro (de connexion et de contact) : aucun résultat.
3. Seule la route 5.4, avec consentement actif, authentifiée, renvoie un numéro ; test d'inventaire : parcours de toutes les routes de l'API (`get_resolver`), aucune autre ne produit un numéro de contact lors d'un appel avec des données réelles (remplace `test_no_phone_reveal_route`).
4. Non-fuite vers modérateur et administrateur par l'API : numéro de contact, `ContactConsent`, 5.5.
5. Charge utile des événements `marketplace.contact_revealed` et `messaging.contact_message_delivered`, `AuditLog.details`, textes de notification : le numéro (complet ou masqué) n'y figure pas.
6. Numéro masqué du 5.1 : ne contient jamais plus de 4 chiffres en clair, et n'est jamais celui d'un autre compte.
7. Un visiteur ne peut pas lire les réglages d'un autre vendeur (aucune route par identifiant d'utilisateur).
8. Frontières : `DomainBoundariesTests` vert (aucun import de modèle croisé ajouté).

## 12. Dettes et points à valider

- **Écart noté** : la limite par IP est un paramètre de configuration, non un réglage de back-office (C9), tant que LEG-PRV-07 n'est pas tranché.
- `AuditLog` écrit dans la transaction `marketplace` (C7) : ce n'est pas un état métier d'un autre domaine, mais la règle « pas de transaction couvrant deux domaines » est interprétée largement ; si l'utilisateur la veut stricte, publier un événement `marketplace.contact_revealed` consommé par `moderation` (bascule simple, sans changement de contrat).
- Courses sous MySQL (quotas, révocation) : à revoir à l'introduction de MySQL.
- Valeurs par défaut (15, 3, 30, 24 h) et version de texte `2026-10-v1` provisoires, à valider avec le client.
- Aucun mécanisme de blocage de visiteur (lot 2).
- Pas de « mes révélations » côté visiteur (LEG-PRV-04, question 6).

### Ajouts L0-24 (audit sécurité et relecture de T1/T2)

- **Version du texte et accords existants** (décision du chef de projet, dette LEG-PRV-03) : un consentement reste valable après un changement de `CONTACT_CONSENT_TEXT_VERSION`. Cible, si le texte change de façon substantielle : la version majeure invalide les accords et impose une nouvelle acceptation. L'implémentation actuelle ne le fait pas (la preuve garde la version acceptée) ; à traiter avec la réponse du client sur LEG-PRV-03.
- **Migration `marketplace` 0005** : elle mêle schéma et remplissage de `delivered_at` ; son découpage est une dette notée (déjà fusionnée).
