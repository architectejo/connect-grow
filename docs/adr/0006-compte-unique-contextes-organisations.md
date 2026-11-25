# ADR 0006 — Compte unique, contextes, organisations, rôles et contexte actif (L0-09a à L0-09j)

- **Statut :** proposé (à valider par le chef de projet ; les points de la section 15 sont à faire valider par l'utilisateur)
- **Date :** 10/10/2026
- **Décideurs :** chef de projet (décisions Q-CP et D de la section 2) ; rédaction : architecte-technique
- **Tâche :** L0-09 (analyse : `docs/specs/L0-09-compte-contextes.md`)
- **Références :** CLAUDE.md §4 (règles 1, 2, 3, 4, 10, 11, 12) et §5 ; CDC v1.2 §3.1, §3.3, §5.4, §11.1 à §11.4 ; dossier client IAM-001 à IAM-008, ORG-001 à ORG-003, TRU-003, doc 06 §19 à §24, doc 07 §3 à §5, doc 13 §4 à §6 ; ADR 0001, 0002 (amendé ici), 0003, 0004, 0005.

## 1. Contexte

Le compte est unique (`identity.User`) mais le code le contredit : `User.user_type` (PARTICULIER / ENTREPRISE), `BusinessProfile` (un profil entreprise par compte, booléen `is_verified`), `Offer.seller` (clé étrangère vers le compte), `DailyVisibilityCounter.seller`, `KycDocument.business_profile`, `ContactPoint`/`ContactConsent` rattachés au compte. La « couture » existe déjà : `apps/common/contexts.py` (`USER`, `ORGANIZATION`), `identity.services.acts_for_context`, `Review.seller_context_type/id`, `Offer.seller_context_*` en propriétés.

Ce qui manque : le contexte `PROVIDER`, les organisations avec rôles, la résolution du contexte actif par le serveur, et le rattachement de tout ce qui est « côté vendeur » (offres, compteurs, contact, avis, notifications, messagerie) à un contexte et non à un compte.

Contraintes : SQLite seul et code portable MySQL (ADR 0001) ; UUID partout ; aucune clé étrangère entre domaines sauf vers `User` ; pas de transaction sur deux domaines hors outbox (ADR 0003) ; pas d'unicité conditionnelle ; règles 1 à 3 : un plan ne donne jamais un rôle, une permission ni une vérification.

## 2. Décisions du chef de projet (intégrées, avec leurs raisons)

| # | Décision | Raison | Traduction dans cet ADR |
|---|---|---|---|
| Q-CP1 | Découpage L0-09 / L1-01 / L1-02 validé. L0-09 livre le modèle, les services, la création, la sortie volontaire et la vérification minimale ; invitation, révocation par un tiers (écrans et endpoints), revendication et parcours KYB complet restent aux lots 1. | Évite de livrer deux fois la gestion d'équipe. | Les services d'équipe existent et sont testés (T1) ; seuls `leave/` et la création sont exposés en HTTP (section 9). |
| Q-CP2 | Profil public minimal suffisant avant L1-03/L1-04. | Pas de page « façon Facebook » en lot 0. | Endpoint unique `sellers/<type>/<id>/` (section 9.7). |
| Q-CP3 | Un éditeur ne modifie pas l'identité de l'organisation (nom, logo, description). | Séparer contenu et identité publique. | Capacité `org.edit_profile` : propriétaire et administrateur seulement. |
| Q-CP4 | Dernier contexte mémorisé dans le navigateur. | Aucune préférence serveur ; évite un état partagé entre onglets. | Aucun champ en base ; le front applique la mémorisation (T10). |
| Q-CP5 | Téléphone de connexion vérifié exigé pour créer une organisation. | Anti-abus. | `User.phone_verified` contrôlé à la création : 403 `phone_verification_required`. |
| Q-CP6 | Un ancien membre ne décide plus jamais de la vérification de son ancienne organisation. | Conflit d'intérêts. | Interdiction **sans durée** : toute ligne `Membership` (quel que soit son statut) pour le couple (organisation, décideur) bloque la décision. |
| Q-CP7 | Une offre reste à l'organisation quand son auteur part. | Doc 06 §19. | `Offer.seller_context_*` = propriétaire ; `created_by` = trace de l'auteur, nul si le compte disparaît. |
| Q-CP8 | En V1 un acheteur ne contacte pas « au nom d'une organisation ». | Hors périmètre doc 06 §8. | Contact, avis, favoris, signalement : toujours en contexte personnel ; l'en-tête de contexte y est ignoré. |
| D1 | Migration de données, pas de réinitialisation. | Sert de preuve de correspondance (pièces, avis). | Section 10 : `RunPython` idempotents par domaine. |
| D2 | Un ancien `BusinessProfile` devient une `Organization` de type `ENTREPRISE`. | Seule donnée disponible. | Section 10.2. |
| D4 | Rôles en constantes (propriétaire, administrateur, éditeur, analyste) ; plusieurs propriétaires permis ; jamais zéro. | Le CDC fixe 4 rôles ; aucune demande de rôles configurables. | `identity/capabilities.py` ; refus `last_owner`. |
| D5 | Plafond de 10 organisations par compte, configurable. | Anti-abus, règle 11. | `IdentitySettings.max_organizations_per_account` (défaut 10). |
| D6 | Intérim messagerie : une organisation n'offre que le canal `MESSAGE`, routé vers propriétaires et administrateurs, tant que L2-09 n'existe pas. | La boîte d'équipe n'existe pas. | Capacité `message.reply` (propriétaire, administrateur) ; section 11.3. |
| — | `ContactPoint`/`ContactConsent` restent au compte pour une offre en contexte personnel ou prestataire ; pour une organisation, le numéro appartient à l'organisation, le consentement est donné par un propriétaire ou un administrateur (valeur provisoire, Q-CLI5). | Règle 10. | Section 4.4 et section 11.2 (interrupteur désactivé par défaut). |

## 3. Décisions de l'architecte

| # | Décision | Écartées |
|---|---|---|
| A1 | **Transport du contexte actif (D3)** : en-tête HTTP `X-Context: <TYPE>:<uuid>` (section 6), revalidé en base à **chaque** requête qui en a besoin. Pas de claim JWT, pas de paramètre d'URL, pas d'état serveur. | Claim JWT : figé 15 min, contraire à la révocation immédiate (R11) sauf contrôle en base, qui le rend inutile et impose un rafraîchissement du jeton à chaque bascule. Paramètre `?context=` : se retrouve dans les journaux, les liens partagés et les caches, facile à oublier sur un POST. Session serveur : état partagé entre onglets. |
| A2 | **Contexte calculé, pas de table `Context`** (écart E8). Personnel = le compte ; prestataire = `ProviderProfile` ; organisation = `Membership`. | Table `Context` : duplique trois sources de vérité. |
| A3 | **Schéma vendeur** (amende l'ADR 0002, écart E7) : `Offer.seller_context_type` (CharField 20), `Offer.seller_context_id` (UUID), `Offer.created_by` (FK `User`, `SET_NULL`, nul permis). Même couple sur `DailyVisibilityCounter`. Plus de `Offer.seller`. | `Offer.organization_id` (ADR 0002) : ne couvre pas le prestataire ni l'offre personnelle. |
| A4 | **Autorisation par objet, contexte par en-tête seulement à la création et pour les listes « de mon contexte »** (section 6.4). Une action sur un objet existant est autorisée d'après le contexte propriétaire **de l'objet** et le rôle réel de l'utilisateur, jamais d'après l'en-tête. | Tout par en-tête : un oubli d'en-tête ferait échouer l'édition d'une offre d'organisation, et une confusion d'en-tête attribuerait mal l'action. |
| A5 | **Capacités en constantes, rôles en constantes** (D4) dans `identity/capabilities.py`. La fonction de décision ne reçoit ni plan, ni prix, ni droit commercial (test de signature, règle 2). `is_staff` n'ouvre rien. | Tables de rôles : prématuré (doc 06 §23 demande des rôles configurables, pas le CDC). Bascule possible plus tard sans changer les appelants (ils appellent `can(...)`). |
| A6 | **`is_verified` devient `verified_claims` dérivés**, sans stockage : calculés à la lecture à partir des pièces `VALIDE` et du tableau `OrganizationDocumentRequirement` (règle 11). Il n'existe donc aucun champ qu'un plan, un rôle ou un autre code puisse écrire (règle 3). | Colonne de claims recalculée : une seconde source de vérité à garder cohérente. |
| A7 | **Visibilité publique du vendeur dénormalisée** : `Offer.seller_is_public` (bool, défaut vrai, indexé), recalculée par un abonné d'événement `identity.seller_context_status_changed` qui relit la source (idempotent) et par une commande de réconciliation `sync_seller_visibility`. Remplace `seller__is_active`. | Jointure vers `identity` : interdite. Liste d'exclusion récupérée à chaque requête : ne tient pas la charge et rend les listes dépendantes d'un service externe. |
| A8 | **Messagerie** : `Conversation.seller_context_type/id` (nuls pour l'existant). Le côté vendeur d'une conversation d'organisation **n'est pas** dans `participants` : l'accès se calcule en direct par capacité `message.reply`, pour qu'une révocation coupe l'accès immédiatement. | Copier les membres dans `participants` : instantané périmé (AC-12). |
| A9 | **Un seul événement de statut vendeur** `identity.seller_context_status_changed` (organisation suspendue, réactivée, archivée ; prestataire activé ou archivé ; compte désactivé ou réactivé) plutôt qu'un événement par cas. | Trois types, trois abonnés identiques. |
| A10 | **Journal d'audit structuré** : `AuditLog` reçoit `context_type` (CharField 20, nul) et `context_id` (UUID, nul, indexé) pour retrouver tout ce qui s'est fait sous une organisation ; `details` reste sans donnée personnelle (clé=valeur). | Fouiller `details` en texte : fragile. |
| A11 | **Migrations de données dans les migrations**, une par domaine, qui lisent uniquement la table de correspondance `identity.LegacyAccountMapping` (deux UUID, sans donnée personnelle) via le modèle historique. Exception documentée et limitée aux migrations (lecture seule). | Commande de gestion orchestrant tous les domaines : doit importer les services de tous (cycles) et dépend d'un geste manuel ; chaîne d'événements outbox : plus complexe sans gain sur des données de développement. |
| A12 | **Noms d'organisations non uniques** (Q-CLI8) : pas de contrainte d'unicité (interdite si conditionnelle ; inutile si absolue car bloquerait les homonymes légitimes). Garde-fous : plafond par compte, claims visibles, signalement. | Unicité du nom : usurpation facile par réservation, homonymes légitimes bloqués. |
| A13 | **`org_type` immuable par l'API** ; **renommage refusé** dès qu'une pièce de l'organisation est validée (409 `name_locked_by_verification`), sauf action du personnel. | Un compte vérifié qui se renomme en une marque connue sans nouvelle vérification (règle 3). À valider, section 15. |
| A14 | **Codes d'erreur** : les codes d'autorisation du client sont conservés en majuscules (`DENY_CONTEXT`, `DENY_RELATION`, `DENY_PERMISSION`, `DENY_SECURITY`, `DENY_OBJECT_STATE`), tous en 403. Les erreurs métier sont en minuscules (convention du dépôt) : `last_owner` (409), `organization_limit_reached` (409), `phone_verification_required` (403), `name_locked_by_verification` (409), `seller_not_settable` (400). Les 401 gardent les codes natifs DRF/JWT (équivalent de `DENY_AUTH`). | — |
| A15 | **`GET contexts/` est une liste bornée non paginée** (au plus 2 + plafond d'organisations), servie dans l'enveloppe `{count, next: null, previous: null, results}` pour garder la même forme que les autres listes. Seule exception à la pagination systématique. | — |

## 4. Modèle de données (domaine `identity`, sauf mention)

Tous les modèles héritent de `BaseModel` (UUID, `created_at`, `updated_at`). Aucune clé étrangère hors de `identity` sauf vers l'utilisateur. Références aux autres domaines par UUID (`city_id`, `commune_id`, `category_id`), existence vérifiée via `catalog.services`.

### 4.1 Constantes partagées (`apps/common/contexts.py`, aucun modèle)

Ajouter : `CONTEXT_PROVIDER = 'PROVIDER'`, la liste `CONTEXT_CHOICES` à trois entrées, la dataclass immuable `ActingContext(user_id, type, id, role=None)`, les constantes `DENY_*`, l'exception `ContextDenied(code, detail)` (sous-classe de `CodedAPIException`, 403) et la fonction `audit_context_args(ctx)` qui renvoie `(type, id)` pour `AuditLog`.

### 4.2 `Organization`

| Champ | Type | Remarque |
|---|---|---|
| `name` | CharField(255) | 2 à 255 caractères ; non unique (A12) |
| `org_type` | CharField(30) | `ENTREPRISE`, `BOUTIQUE`, `ONG`, `ORGANISATEUR_EVENEMENTS` ; immuable par l'API (A13) |
| `description` | TextField, blank | 2 000 caractères au plus (validateur) |
| `logo` | ImageField, nul | `upload_to='organization_logos/'`, mêmes validateurs et ré-encodage que `BusinessProfile.logo` |
| `nif` | CharField(50), blank | repris de l'existant ; **non public** |
| `city_id`, `commune_id` | UUIDField, nul, indexés | adresse générale seulement (règle 10) ; pas d'adresse exacte en V1 |
| `status` | CharField(12) | `ACTIVE`, `SUSPENDED`, `ARCHIVED` |
| `suspension_reason` | CharField(30), blank | motif normalisé, jamais de texte libre |
| `created_by` | FK `User`, `SET_NULL`, nul | |
| `legacy_business_profile_id` | UUIDField, nul | pour l'idempotence de la migration ; retiré avec la table de correspondance |

Index : `(status, org_type)`, `(name)`. Pas d'unicité. Propriétés de modèle : aucune logique métier (elle vit dans les services).

`OrganizationCategory(organization FK, category_id UUID)` : table de liaison interne, unicité `(organization, category_id)` (inconditionnelle).

### 4.3 `Membership`, `ProviderProfile`, `IdentitySettings`, exigences de pièces

`Membership` : `organization` (FK `Organization`, CASCADE), `user` (FK `User`, CASCADE), `role` CharField(20) (`OWNER`, `ADMIN`, `EDITOR`, `ANALYST`), `status` CharField(10) (`ACTIVE`, `REVOKED` ; `INVITED` s'ajoutera avec L1-01 sans changer le schéma), `end_reason` CharField(12) blank (`removed`, `left`), `joined_at` DateTime, `ended_at` DateTime nul, `added_by` FK `User` `SET_NULL` nul, `ended_by` FK `User` `SET_NULL` nul.
- **Unicité `(organization, user)`** inconditionnelle (R12) : un retour réactive la même ligne.
- Index `(user, status)` (liste des contextes), `(organization, role, status)` (comptage des propriétaires, destinataires).
- Aucune règle « au moins un propriétaire » en base : garantie en couche service sous verrou (section 7.2).

`ProviderProfile` : `user` OneToOneField(`User`, CASCADE) (une seule ligne par compte, unicité inconditionnelle), `display_name` CharField(255), `bio` TextField blank (2 000), `status` CharField(10) (`ACTIVE`, `ARCHIVED`), `archived_at` nul. `ProviderProfileCategory(provider FK, category_id UUID)` comme pour l'organisation. Photo publique : celle du compte (le profil prestataire n'a pas de photo propre ; `contexts/` renvoie donc la photo du compte pour `PROVIDER`).

`IdentitySettings(SingletonSettingsModel)` (règle 11, back-office) : `max_organizations_per_account` (PositiveInteger, défaut 10, validateurs 1 à 100) ; `org_phone_channels_enabled` (Boolean, **défaut faux**, voir Q-CLI5). Les modifications passent par `moderation.record_settings_change` (comme les autres réglages).

`OrganizationDocumentRequirement(org_type CharField(30), document_type CharField(20), position PositiveSmallInteger)` : unicité `(org_type, document_type)`. Édité dans l'admin Django. Valeurs initiales provisoires posées par une migration de données (Q-CLI2) : `ENTREPRISE` et `ORGANISATEUR_EVENEMENTS` : `RCCM`, `ID_NATIONALE`, `PIECE_GERANT` ; `BOUTIQUE` : `ID_NATIONALE`, `PIECE_GERANT` ; `ONG` : `ARRETE_ONG`, `ID_NATIONALE`, `PIECE_GERANT`. Le type de pièce `ARRETE_ONG` est ajouté aux choix de `KycDocument.document_type` (aucune longueur à changer).

### 4.4 Pièces KYB et contact

- `KycDocument` : ajout de `organization` (FK `Organization`, CASCADE, **nul** pendant l'étape « étendre ») et `uploaded_by` (FK `User`, `SET_NULL`, nul). `business_profile` reste jusqu'à la contraction. Le fichier, le stockage privé et la permission `review_kycdocument` ne changent pas.
- `ContactPoint` et `ContactConsent` (ADR 0005) : `user` devient **nullable** et on ajoute `organization` (FK `Organization`, CASCADE, nul). Unicités existantes conservées (`ContactPoint.user` unique, `(user, channel)`), plus `ContactPoint.organization` unique et `(organization, channel)` unique : portables, les valeurs nulles ne se comparent pas. La règle « exactement un des deux renseigné » est garantie par le service. `ContactConsent.granted_by` (FK `User`, `SET_NULL`, nul) trace qui a consenti pour l'organisation.
- Le numéro de contact d'une organisation n'est jamais le numéro d'un membre ; changer le numéro personnel d'un membre ne change rien pour l'organisation.

### 4.5 Autres domaines (colonnes ajoutées, toutes nulles ou à défaut sûr)

| Domaine | Modèle | Ajouts (étendre) | Contraction (h) |
|---|---|---|---|
| marketplace | `Offer` | `seller_context_type` (CharField 20, nul), `seller_context_id` (UUID, nul), `created_by` (FK `User` SET_NULL nul), `seller_is_public` (Boolean défaut vrai) ; `seller` devient nullable ; retrait des propriétés homonymes ; index `offer_seller_ctx_deleted (seller_context_type, seller_context_id, is_deleted)` | retrait de `seller` et de l'index `offer_seller_deleted`, colonnes de contexte NOT NULL |
| visibility | `DailyVisibilityCounter` | `seller_context_type`, `seller_context_id` (nuls), index `(seller_context_type, seller_context_id, date)` ; `seller` nullable | retrait de `seller` |
| reviews | `Review` | choix `PROVIDER` ajouté à `seller_context_type` (changement de `choices` uniquement) | — |
| messaging | `Conversation` | `seller_context_type`, `seller_context_id` (nuls ; nul = ancienne conversation par participants ; **aucun remplissage**) | — |
| messaging | `Message` | `sender_context_type`, `sender_context_id` (nuls ; **nul = l'expéditeur à titre personnel**, aucun remplissage) : identité affichée (organisation ou personne) | — |
| notifications | `Notification` | `context_type`, `context_id` (nuls ; **nul = personnel, norme unique**, aucun remplissage) | — |
| moderation | `AuditLog` | `context_type` (CharField 20, nul), `context_id` (UUID, nul, indexé) | — |

Les tables `Favorite`, `ContactEvent`, `ExchangeProposal` ne changent pas (l'acheteur est toujours un compte ; le vendeur se déduit de l'offre).

## 5. Rôles et capacités (figés)

Source unique : `apps/identity/capabilities.py` (constantes, aucune importation de modèle). O = propriétaire, A = administrateur, E = éditeur, An = analyste.

| Capacité | O | A | E | An | Remarque |
|---|---|---|---|---|---|
| `org.view_internal` | O | O | O | O | espace interne, statut, rôle propre |
| `org.leave` | O | O | O | O | sous réserve de `last_owner` |
| `org.edit_profile` | O | O | N | N | nom, description, logo, catégories, ville, NIF (Q-CP3) |
| `org.manage_members` | O | O | N | N | l'administrateur n'agit jamais sur un propriétaire (R9) |
| `org.manage_roles` | O | O | N | N | l'administrateur ne manipule que ADMIN, EDITOR, ANALYST ; seul un propriétaire attribue ou retire OWNER (le « transfert » = deux changements de rôle, plusieurs propriétaires étant permis) |
| `org.archive` | O | N | N | N | |
| `org.verification_submit` | O | O | N | N | dépôt et suppression d'une pièce |
| `offer.view_internal` | O | O | O | O | « mes offres », corbeille |
| `offer.publish`, `offer.edit`, `offer.delete` | O | O | O | N | |
| `review.reply` | O | O | O | N | |
| `contact.view_requesters` | O | O | O | N | liste « qui a demandé » ; l'analyste ne voit que des compteurs |
| `contact.manage_channels` | O | O | N | N | numéro et canaux de l'organisation |
| `message.reply` | O | O | N | N | **intérim D6** ; L2-09 élargira |
| `stats.view` | O | O | O | O | |

Contextes `USER` et `PROVIDER` : le titulaire a toutes les capacités « de contenu » (`offer.*`, `review.reply`, `contact.*`, `message.reply`, `stats.view`) et aucune capacité `org.*`. Les capacités de facturation (`billing.*`) ne sont pas définies ici : L1-11. La matrice est testée case par case (test paramétré rôle x capacité x résultat) ; une capacité inconnue lève une erreur de programmation, pas un refus.

Règles de garde en couche service (testées) : R8 (`last_owner`), R9, R10, R11 (révocation immédiate), R12, R13, R14.

## 6. Contexte actif (D3)

### 6.1 Format

En-tête `X-Context: <TYPE>:<uuid>` avec `TYPE` dans `USER`, `PROVIDER`, `ORGANIZATION` (majuscules, UUID au format canonique). `X-Context: USER` seul est accepté pour le personnel. **En-tête absent = contexte personnel.** En-tête présent mais vide, mal formé ou de type inconnu = refus ; jamais de repli silencieux (R5).

CORS : ajouter `x-context` à `CORS_ALLOW_HEADERS` (liste par défaut de `django-cors-headers` conservée, plus cet en-tête), sinon le navigateur bloque la requête préalable. Test de réglage dédié.

### 6.2 Résolution (`identity.services.resolve_acting_context(user, raw_header) -> ActingContext`)

| Cas | Résultat | Coût SQL |
|---|---|---|
| absent ou `USER[:id]` avec `id` = compte | `ActingContext(USER, user.id)` | 0 |
| `USER:<autre>` | 403 `DENY_CONTEXT` | 0 |
| `PROVIDER:<id>` : profil de cet utilisateur et actif | `ActingContext(PROVIDER, id)` | 1 |
| `PROVIDER:<id>` : inexistant ou d'un autre compte | 403 `DENY_CONTEXT` (pas d'oracle) | 1 |
| `PROVIDER:<id>` archivé | 403 `DENY_OBJECT_STATE` | 1 |
| `ORGANIZATION:<id>` : `Membership` ACTIVE et organisation ACTIVE | `ActingContext(ORGANIZATION, id, role)` | 1 (jointure) |
| `ORGANIZATION:<id>` : pas de membership actif, ou organisation inexistante | 403 `DENY_RELATION` (même réponse : pas d'oracle d'existence ; écart volontaire avec la spec qui prévoyait `DENY_CONTEXT` pour l'inexistant) | 1 |
| `ORGANIZATION:<id>` suspendue | 403 `DENY_SECURITY` | 1 |
| `ORGANIZATION:<id>` archivée | 403 `DENY_OBJECT_STATE` | 1 |
| mal formé | 403 `DENY_CONTEXT` | 0 |

Budget (amendé par l'audit L0-30) : **garde du compte** (2 requêtes : `User.is_active` relu en base, puis `moderation.is_user_restricted`) **+ au plus 1** requête pour le contexte. La garde s'applique à tout contexte, y compris le personnel sans en-tête : un compte désactivé ou sous suspension/bannissement est refusé en `DENY_SECURITY` (`_ensure_actor_usable`, même logique que `_authorize_member`), par `resolve_acting_context`, `authorize_on`, `can`, le mixin et `capability_permission`. Seule exception : la capacité `org.leave` (sortie volontaire). `is_staff` et `is_superuser` ne contournent rien. L'attribut `is_active` d'un objet en mémoire n'est jamais cru.

**Aucun cache** : ni `lru_cache`, ni cache Django, ni claim JWT ne portent un rôle ou une appartenance. Le résultat est mémorisé sur `request` pour la durée de la requête seulement. Révocation d'un membre = refus à la requête suivante, jeton d'accès toujours valide pour le contexte personnel.

### 6.3 Brique DRF (`apps/identity/acting.py`, exposée par `identity.services`)

- `get_acting_context(request) -> ActingContext` : résout l'en-tête une seule fois par requête (mémorisation sur `request`), lève `ContextDenied`.
- `authorize(ctx, capability)` : lève `ContextDenied('DENY_PERMISSION')` si le rôle n'a pas la capacité.
- `authorize_on(user, context_type, context_id, capability)` : autorisation **par objet** (section 6.4) ; codes `DENY_RELATION`, `DENY_PERMISSION`, `DENY_SECURITY`, `DENY_OBJECT_STATE`.
- `can(user_id, context_type, context_id, capability) -> bool` : variante sans exception pour les autres domaines et les sérialiseurs.
- Le message d'erreur est en français et ne contient jamais le nom d'une organisation ni d'autre membre.

### 6.4 Quels endpoints lisent l'en-tête

**Règle de la brique** : création et listes « de mon contexte » = en-tête (`acting_context`, `authorize_capability`) ; objet existant = propriétaire réel de l'objet (`authorize_object` du mixin, qui appelle `authorize_on` et ignore l'en-tête). Sans cela, un membre éditeur de A et analyste de B agirait sur un objet de B en présentant l'en-tête de A. **Écritures sensibles** : le contrôle fait par la vue précède l'écriture ; le service doit refaire `authorize_on` sous `transaction.atomic()`, juste avant d'écrire, pour prendre en compte une révocation ou une suspension survenue entre-temps. **Garde-fou** : `identity/tests_route_guard.py` échoue pour toute nouvelle vue d'écriture sans `ActingContextMixin`/`capability_permission` ni `acting_context_exempt`. **Cache** : toute réponse d'`/api/` porte `Vary: Authorization, X-Context` ; une requête portant `X-Context` reçoit `Cache-Control: private, no-store`.

| Catégorie | Endpoints | Règle |
|---|---|---|
| **Sensibles au contexte (en-tête lu)** | `POST posts/` ; `GET posts/?mine=true` ; `GET posts/trash/` ; `GET stats/dashboard/` ; `contact-settings/*` ; `GET contacts/reveals/received/` (« qui a demandé ») ; `GET conversations/` (boîte) | contexte résolu, puis `authorize(ctx, capacité)` |
| **Par objet (en-tête ignoré)** | `PATCH/DELETE/actions posts/<id>/` ; `GET stats/post/<id>/` ; réponse à un avis ; lecture et envoi dans une conversation ; routes `organizations/<id>/…` (identifiant dans le chemin) | `authorize_on(user, contexte de l'objet, capacité)` |
| **Toujours personnels (en-tête ignoré, non validé)** | `provider/` (activation, lecture, modification, archivage : profil du compte, sans identifiant dans le chemin), contact, révélation de numéro, avis, favoris, signalement, `me/`, notifications | Q-CP8 |

Un en-tête ignoré n'est pas un repli : ces endpoints n'ont qu'une identité possible. Le front le sait et l'indique dans l'interface (T10).

## 7. Services (frontières de modules)

Les autres domaines n'appellent que `identity.services` (façade). Le code d'`identity` est découpé pour permettre le travail en parallèle : `capabilities.py`, `acting.py`, `organizations.py`, `providers.py`, `verification.py`, tous ré-exportés par `services.py` (les autres domaines n'importent jamais ces sous-modules).

### 7.1 Signatures (nouvelles ou modifiées)

| Fonction | Rôle |
|---|---|
| `resolve_acting_context`, `authorize`, `authorize_on`, `can` | section 6 |
| `acts_for_context(user_id, type, id) -> bool` | vrai pour : `USER` = soi-même ; `PROVIDER` = propriétaire du profil (même archivé) ; `ORGANIZATION` = membre **actif** de tout rôle d'une organisation **non suspendue**. Sert au refus « je ne note pas et ne contacte pas ma propre offre ». Faux sinon (dont membre révoqué). |
| `get_user_context_roles(user_id) -> dict[(type,id), role]` | une à deux requêtes, pour calculer `is_owner` d'une page d'offres sans N+1 |
| `get_contexts_for_user(user) -> list` | liste de `GET contexts/` |
| `get_context_recipients(type, id, capability) -> list[UUID]` | comptes à notifier : USER = le compte, PROVIDER = son titulaire, ORGANIZATION = membres actifs ayant la capacité |
| `get_seller_summaries(contexts) -> dict[(type,id), SellerSummary]` | **remplace** la version par UUID de compte. `SellerSummary(context_type, context_id, display_name, photo, org_type, description, verified_claims, verification_summary, member_since)`. `display_name` : `public_display_name` pour `USER`, `display_name` du profil, nom de l'organisation. Aucun e-mail, téléphone, liste de membres. |
| `is_seller_context_public(type, id) -> bool` | `USER` : compte actif ; `PROVIDER` : profil ACTIVE et compte actif ; `ORGANIZATION` : ACTIVE. Source du recalcul de `Offer.seller_is_public`. |
| `get_verified_claims(org_ids) -> dict` | claims dérivés, par lot (une requête pièces, une requête exigences) |
| `create_organization`, `update_organization`, `archive_organization`, `suspend_organization`, `reactivate_organization` | cycle de vie, audit synchrone, événements |
| `add_member`, `change_member_role`, `revoke_member`, `leave_organization` | équipe (service seulement en L0-09 ; pas d'endpoint sauf `leave`) |
| `activate_provider`, `update_provider`, `archive_provider` | prestataire |
| `submit_kyb_document`, `delete_kyb_document`, `decide_kyc_document` (modifiée) | vérification ; `recompute_verification` **disparaît** |
| `set_account_active(user_id, active, actor)` | point unique de changement de `User.is_active` ; publie l'événement de statut vendeur ; appelé par `moderation` à la place de l'écriture directe (`Sanction.apply/lift`) |
| `get_allowed_channels(contexts)`, `get_contact_endpoint(type, id, channel)` (modifiées) | par contexte vendeur (section 11.2) |
| `get_contact_settings`, `set_contact_phone`, `verify_contact_phone`, `set_channel_consent` (modifiées) | reçoivent un « propriétaire de contact » (compte ou organisation) |

### 7.2 Règles d'écriture

- Toute écriture d'équipe : `transaction.atomic()`, verrou de ligne sur `Organization` (`select_for_update`, sans effet sous SQLite qui sérialise les écrivains, effectif sous MySQL), comptage des propriétaires actifs **après** verrou, `AuditLog` synchrone (avec `context_*`), `publish_event` dans la même transaction.
- `create_organization` : compte actif, `phone_verified`, absence de restriction, plafond (`IdentitySettings`) comptant les `Membership` ACTIVE du compte, existence des catégories et de la ville via `catalog.services`, puis `Organization` + `Membership(OWNER)` + `AuditLog('ORG_CREATED')` dans une seule transaction.
- `decide_kyc_document` : refus (403) si le décideur a une ligne `Membership` pour l'organisation (tout statut), ou est `uploaded_by`, ou `created_by` de l'organisation. Le calcul de claims n'écrit rien.
- Aucun service de ce module ne reçoit de plan ni d'entitlement. Les quotas de L1-11 s'ajouteront **avant** l'appel (`DENY_ENTITLEMENT`), jamais dans les fonctions de rôle.

## 8. Événements de domaine (outbox, ADR 0003)

À déclarer dans `platform_core/catalog.py`. Charges utiles : UUID et valeurs simples, aucune donnée personnelle.

| Type | Émetteur | Abonnés | Charge utile |
|---|---|---|---|
| `identity.membership_changed` (v1) | `add_member`, `change_member_role`, `revoke_member`, `leave_organization`, `create_organization` (change=`added`) | `notifications.notify_membership_change` (prévient la personne concernée) ; `notifications.purge_context_notifications` (sur `revoked` : supprime les notifications de ce compte rattachées à cette organisation) | `organization_id, user_id, change` (`added`, `role_changed`, `revoked`, `reactivated`), `old_role, new_role, actor_id` |
| `identity.seller_context_status_changed` (v1) | cycle de vie d'organisation, de prestataire, `set_account_active` | `marketplace.sync_seller_visibility` (recalcule `seller_is_public` depuis `is_seller_context_public`) ; `notifications.notify_organization_status` (propriétaires et administrateurs, organisation seulement) | `context_type, context_id, reason` (`suspended`, `reactivated`, `archived`, `activated`, `account_deactivated`, `account_reactivated`), `actor_id` |
| `identity.organization_verification_changed` (v1) | `decide_kyc_document` | `notifications.notify_kyb_decision` (propriétaires et administrateurs) | `organization_id, document_type, decision` |
| `marketplace.contact_recorded`, `marketplace.contact_revealed`, `marketplace.exchange_proposed` (**v2**) | marketplace | inchangés (messaging, notifications) | `seller_id` remplacé par `seller_context_type, seller_context_id` ; abonnés refusent la v1 |
| `reviews.review_posted` (**v3**) | reviews | `notifications.notify_review_posted` | `recipient_id` supprimé ; l'abonné résout les destinataires par `get_context_recipients(type, id, 'review.reply')` à la livraison |
| `marketplace.offer_expiring_soon` et notification d'expiration (**v2**) | marketplace | notifications | `seller_id` remplacé par le contexte ; destinataires : capacité `offer.edit` |
| `visibility.offer_viewed`, `visibility.offer_shared` | visibility | inchangés | `seller_id` remplacé par `seller_context_*` (version 1 conservée : l'abonné ne lit que `offer_id`) |

Les abonnés restent idempotents (recalcul depuis la source). Pas de migration d'événements en attente : en développement, vider l'outbox avant le déploiement des versions v2/v3, comme pour l'ADR 0004. Au moment de T1, les types sans abonné sont déclarés `no_subscriber=True` et le drapeau est retiré par la tâche qui ajoute l'abonné (le contrôle `platform_core.E001` reste vert à chaque étape).

**Contrainte pour L2-09 (messagerie temps réel)** : un consommateur WebSocket doit contrôler l'appartenance à la connexion **et** à chaque message, et fermer les connexions sur `identity.membership_changed` (révocation) : aucune souscription à un groupe d'organisation sans `can(..., 'message.reply')` recalculé.

## 9. Contrat d'API figé

Les chemins actuels sont conservés (L0-11 les passera sous `/api/v1/` : `identity` pour `/api/accounts/`, `marketplace` inchangé, ajout de `v1`). Les chemins **nouveaux** ci-dessous utilisent déjà le nom final de la ressource, de sorte que L0-11 n'ait qu'un préfixe à changer. Authentification : `Authorization: Bearer <jwt>`. Format d'erreur : `{"detail": "<français>", "code": "<code>"}` ; erreurs de champ : `{"<champ>": ["<message>"]}`. Préfixes : `ID = /api/accounts/`, `MK = /api/marketplace/`.

Toutes les réponses d'erreur d'autorisation de cette section sont des 403 avec `code` parmi `DENY_CONTEXT`, `DENY_RELATION`, `DENY_PERMISSION`, `DENY_SECURITY`, `DENY_OBJECT_STATE`. 401 : codes natifs.

### 9.1 `GET ID contexts/` (authentifié)

```json
200 {"count": 3, "next": null, "previous": null, "results": [
  {"type": "USER", "id": "<uuid compte>", "name": "Marie Kabongo", "role": null, "org_type": null,
   "photo": null, "capabilities": ["offer.view_internal", "offer.publish", "..."]},
  {"type": "PROVIDER", "id": "<uuid profil>", "name": "Marie couture", "role": null, "org_type": null, "photo": null, "capabilities": ["..."]},
  {"type": "ORGANIZATION", "id": "<uuid org>", "name": "Atelier X", "role": "ADMIN", "org_type": "ENTREPRISE",
   "photo": "https://.../organization_logos/x.webp", "capabilities": ["org.view_internal", "..."]}
]}
```
Ordre : `USER`, puis `PROVIDER` s'il est actif, puis les organisations par nom. Exclut de `results` : membership révoqué, organisation suspendue ou archivée, prestataire archivé. **Amendement 4 (§21) :** chaque élément porte `status` (toujours `ACTIVE` dans `results`) et la réponse porte une clé `unavailable` (voir §21). `capabilities` sert à masquer des boutons ; l'autorisation reste serveur (doc 06 §24). Exactement 3 requêtes depuis l'amendement 4 (profil prestataire, appartenances aux organisations actives, appartenances aux organisations indisponibles), quel que soit le nombre d'organisations (`assertNumQueries`). Throttle `contexts` : **600/h** par utilisateur. Note front : `staleTime` suffisant, pas de rechargement au retour de focus, et ne jamais retirer le contexte actif sur un 429 (garder le contexte courant et réessayer plus tard).

### 9.2 Organisations

**`POST ID organizations/`** (authentifié, JSON ou multipart ; throttle `org_create` 5/jour par compte)
```json
{"name": "Atelier X", "org_type": "ENTREPRISE", "description": "", "nif": "", "category_ids": ["<uuid>"],
 "city_id": "<uuid>|null", "commune_id": "<uuid>|null", "logo": "<fichier, optionnel>"}
```
`201` : `OrganizationInternal` (ci-dessous), `my_role = "OWNER"`. Erreurs : `400` champs (nom 2 à 255, type hors liste, catégorie inconnue) ; `403 phone_verification_required` ; `409 organization_limit_reached` ; `403 DENY_SECURITY` (compte restreint). Les champs `status`, `id`, `my_role` envoyés sont ignorés.

`OrganizationInternal` :
```json
{"id": "<uuid>", "name": "", "org_type": "", "description": "", "logo": null, "nif": "", "city_id": null, "commune_id": null,
 "category_ids": [], "status": "ACTIVE", "created_at": "", "my_role": "OWNER", "capabilities": [],
 "verification": {"required": [{"document_type": "RCCM", "label": "RCCM", "state": "NONE"}],
                  "verified_claims": [], "summary": {"complete": false, "label": null}}}
```
`state` : `NONE`, `EN_ATTENTE`, `VALIDE`, `REFUSE` (meilleur état par type, la plus récente pièce).

**`GET ID organizations/<uuid>/internal/`** (membre actif, `org.view_internal`) : `OrganizationInternal`. Non-membre : `403 DENY_RELATION`. Organisation suspendue : `403 DENY_SECURITY`.

**`PATCH ID organizations/<uuid>/`** (`org.edit_profile` ; JSON ou multipart ; throttle `org_write` 30/h) : `name`, `description`, `logo` (fichier ou `null` pour retirer), `category_ids`, `city_id`, `commune_id`, `nif`. `org_type` envoyé : `400`. Renommer une organisation ayant une pièce validée : `409 name_locked_by_verification`. `200` : `OrganizationInternal`. Audit `ORG_UPDATED` si le nom change (noms de champs seulement dans `details`).

**`POST ID organizations/<uuid>/archive/`** (`org.archive`, propriétaire) : `200` `OrganizationInternal` avec `status = "ARCHIVED"`. Les offres cessent d'être publiques (événement de statut). Irréversible par l'API (réactivation par le personnel).

**`POST ID organizations/<uuid>/leave/`** (tout membre actif, `org.leave`) : `204`. Dernier propriétaire : `409 last_owner`. Effet : `Membership` à `REVOKED`, `end_reason = left`, événement `identity.membership_changed`.

**`GET ID organizations/`** (public, paginé `StandardPagination`, remplace `businesses/`) : paramètres `search` (nom et description), `org_type`, `claim` (code de claim, ex. `RCCM_VERIFIED`), `fully_verified=true|false` (toute autre valeur : `400`), `page`, `page_size`. Tri : nom puis identifiant. Seules les organisations `ACTIVE`.
```json
{"count": 0, "next": null, "previous": null, "results": [
  {"id": "", "name": "", "org_type": "", "description": "", "logo": null, "city_id": null, "commune_id": null,
   "category_ids": [], "verified_claims": [{"code": "RCCM_VERIFIED", "label": "RCCM vérifié", "verified_at": "2026-10-01T10:00:00+01:00"}],
   "verification_summary": {"complete": false, "label": null}, "member_since": "2026-09-01T09:00:00+01:00"}]}
```
**Test d'exhaustivité des clés** : exactement ces clés. Jamais `is_verified`, `nif`, `status`, téléphone, e-mail, adresse exacte, membres, créateur.

Codes de claim (libellés en base de code, traduits par le front via la clé `code`) : `RCCM_VERIFIED` « RCCM vérifié », `NATIONAL_ID_VERIFIED` « Identification nationale vérifiée », `REPRESENTATIVE_VERIFIED` « Représentant vérifié », `NGO_DECREE_VERIFIED` « Arrêté d'enregistrement vérifié ». `verification_summary.label` vaut « Organisation vérifiée » seulement si **toutes** les pièces exigées du type sont validées **et** la liste d'exigences n'est pas vide ; le front l'affiche toujours avec la liste des claims.

### 9.3 Prestataire individuel

| Appel | Corps | Réponse |
|---|---|---|
| `GET ID provider/` | — | `200` `{id, display_name, bio, category_ids, status, created_at}` ou `404 provider_not_found` |
| `POST ID provider/activate/` | `{display_name?, bio?, category_ids?}` (défaut du nom : nom du compte) | `201` profil (création) ; `200` profil (déjà actif, idempotent) ; réactive un profil archivé (`200`) |
| `PATCH ID provider/` | `display_name, bio, category_ids` | `200` profil ; `403 DENY_OBJECT_STATE` si archivé |
| `POST ID provider/archive/` | — | `200` profil `ARCHIVED` ; offres retirées du public ; avis conservés |

Sur un profil déjà actif, le corps d'`activate/` est ignoré sans validation (200 idempotent, rien n'est modifié ni journalisé). Aucun plan requis (règle 2). Un compte restreint : `403 DENY_SECURITY`. Audit `PROVIDER_ACTIVATED`, `PROVIDER_ARCHIVED`.

### 9.4 Vérification d'une organisation (remplace `kyc/documents/`)

| Appel | Permission | Détail |
|---|---|---|
| `GET ID organizations/<uuid>/kyc/documents/` | `org.verification_submit` (décision L1-01-B6, 25/11/2026 ; les autres rôles reçoivent 403 `DENY_PERMISSION`) | pièces de l'organisation, paginé : `{id, document_type, document_type_label, status, rejection_reason, uploaded_at, reviewed_at}` ; **jamais** l'URL ni le contenu du fichier |
| `POST ID organizations/<uuid>/kyc/documents/` | `org.verification_submit` | multipart `{document_type, file}` ; mêmes contrôles de type et taille qu'aujourd'hui ; `201` ; `400` si le type n'est pas exigé pour ce `org_type` ; throttle `KycWriteThrottle` existant |
| `DELETE ID organizations/<uuid>/kyc/documents/<uuid>/` | `org.verification_submit` | seulement `EN_ATTENTE` ou `REFUSE` ; `204` ; `409` si `VALIDE` |
| `GET ID organizations/<uuid>/verification/` | `org.view_internal` | bloc `verification` de `OrganizationInternal` |

Inchangés (personnel de vérification, chemins stables) : `GET ID kyc/review-queue/`, `POST ID kyc/documents/<uuid>/decision/`, `GET ID kyc/documents/<uuid>/download/`. La file affiche `organization: {id, name, org_type}` à la place de l'utilisateur ; aucune coordonnée d'un membre. Décision par un (ancien) membre : `403` avec `detail` explicite.

### 9.5 Inscription et profil

- `POST ID register/` : `user_type` et `business_profile` ne sont plus lus ; s'ils sont envoyés, ils n'ont aucun effet (aucune organisation créée). Le reste est inchangé (OTP, mot de passe).
- `GET/PATCH ID me/` : disparaissent `user_type` et `business_profile`. Rien d'autre ne change (les contextes sont dans `contexts/`).
- `GET ID businesses/` : **supprimé** (remplacé par `organizations/`).

### 9.6 Offres (marketplace, chemins `MK posts/` conservés jusqu'à L0-11)

- `POST MK posts/` : en-tête `X-Context` ; capacité `offer.publish` du contexte ; le contexte `PROVIDER` doit être actif. Le corps ne contient plus de vendeur : `seller`, `seller_context_type`, `seller_context_id`, `created_by` envoyés → `400 {"seller_context_id": [...]}` avec code `seller_not_settable`. `seller_context_*` et `created_by` sont posés par le serveur. Erreurs : `403 DENY_CONTEXT|DENY_RELATION|DENY_PERMISSION|DENY_SECURITY|DENY_OBJECT_STATE`.
- `PATCH/DELETE` et actions de cycle de vie (pause, reprise, renouvellement, vendue, corbeille, restauration) : capacité `offer.edit` ou `offer.delete` du contexte **de l'offre**. Auteur révoqué : `403 DENY_RELATION`.
- `GET MK posts/?my_offers=true` (paramètre historique) et `GET MK posts/trash/` : en-tête `X-Context`, capacité `offer.view_internal`, uniquement les offres du contexte actif.
- `?seller=<uuid>` : désigne un **identifiant de contexte vendeur**, avec `seller_type=USER|PROVIDER|ORGANIZATION` facultatif (sans lui, n'importe quel type ; un identifiant inconnu donne une liste vide). Plus d'identifiant de compte.
- Objet offre (liste, fiche, favoris) : `seller` devient
```json
"seller": {"context_type": "ORGANIZATION", "context_id": "<uuid>", "display_name": "Atelier X", "photo": null,
           "org_type": "ENTREPRISE", "verified_claims": [], "verification_summary": {"complete": false, "label": null},
           "member_since": "2026-09-01T09:00:00+01:00"}
```
Disparaissent de `seller` : `id`, `full_name`, `user_type`, `date_joined`, `business_profile`. `seller_name` (racine) reste égal à `display_name` jusqu'à L0-11. `seller_rating` garde sa forme (ADR 0004 §7.1) mais porte sur le contexte vendeur. `is_owner` reste, et signifie « le demandeur peut modifier cette offre » (membre avec `offer.edit`, ou titulaire). `allowed_channels` : section 11.2. Le type de vendeur est toujours affiché (CDC §3.3). `created_by` n'est **pas** exposé publiquement.
- Visibilité publique : conditionnée par `Offer.seller_is_public` (et non plus `seller__is_active`).

### 9.7 Profil public minimal d'un vendeur (`marketplace`)

`GET MK sellers/<context_type>/<uuid>/` — `context_type` en minuscules dans le chemin : `user`, `provider`, `organization`. Public.
```json
200 {"context_type": "PROVIDER", "context_id": "<uuid>", "display_name": "", "photo": null, "description": "",
     "org_type": null, "verified_claims": [], "verification_summary": {"complete": false, "label": null},
     "member_since": "2026-09-01T09:00:00+01:00", "seller_rating": {"average": null, "count": 0}, "active_offers_count": 0}
404 vendeur inconnu ou non public
```
`description` : description de l'organisation, `bio` du prestataire, `null` pour un compte personnel. `display_name` d'un compte personnel : `public_display_name` (« Marie K. »). Test d'exhaustivité des clés : aucun téléphone, e-mail, adresse exacte, pièce d'identité, liste de membres.

### 9.8 Statistiques, contacts, avis, messagerie, notifications

- `GET MK stats/dashboard/` : en-tête `X-Context`, capacité `stats.view` ; agrégats du contexte actif. `GET MK stats/post/<uuid>/` : par objet, `stats.view` ; non-membre `403 DENY_RELATION`.
- `GET /api/interactions/contacts/reveals/received/` (« qui a demandé ») : en-tête `X-Context`, capacité `contact.view_requesters` ; l'analyste reçoit `403 DENY_PERMISSION` (il lit les compteurs du tableau de bord).
- `contact-settings/*` : mêmes chemins et mêmes corps qu'ADR 0005 ; chaque réponse ajoute `"context": {"type": "...", "id": "..."}`. Contexte `USER` ou `PROVIDER` : réglages du compte (inchangé). Contexte `ORGANIZATION` : réglages de l'organisation, capacité `contact.manage_channels`, audit `CONTACT_CHANNEL_CHANGED`.
- Avis : `POST /api/interactions/reviews/<uuid>/reply/` (chemin historique) autorisé par `review.reply` du contexte vendeur de l'avis ; la réponse affiche le nom de l'organisation, jamais celui du membre. `GET reviews/?seller=` inchangé (identifiant de contexte).
- `GET /api/interactions/conversations/` : en-tête `X-Context` ; `USER` ou `PROVIDER` : conversations où le compte est participant ; `ORGANIZATION` : conversations dont le contexte vendeur est cette organisation, capacité `message.reply`. Chaque message expose `sender_name` (nom de l'organisation si le message vient du côté organisation) et `sender_context: {type, id}`.
- `GET /api/interactions/notifications/` : toutes les notifications du compte, chacune avec `context: null | {type, id, name}`.

## 10. Migrations, ordre « étendre puis contracter »

### 10.1 Règles

1. **Seules T1 et T9 écrivent des migrations `identity`.** T1 pose en une fois tout le schéma d'extension d'`identity` (organisations, appartenances, prestataire, exigences, réglages, correspondance, colonnes de contact et de pièces) ; les tâches T2 à T8 n'ajoutent plus de modèle ni de colonne à `identity`. T5 porte les colonnes de `marketplace`, `visibility`, `messaging`, `notifications` et le changement de `choices` de `reviews` ; T1 porte la colonne d'audit de `moderation`. Chaque tâche revoit `makemigrations --check` avant de rendre la main.
2. Aucun autre chantier ne doit toucher les migrations de ces sept applications pendant T1, T5 et T9 (sérialisation demandée par le chef de projet).
3. Une migration par changement logique ; jamais de dépendance de migration entre domaines hors `identity` (test existant). Les migrations de données de `marketplace`, `visibility` et `reviews` dépendent d'une migration d'`identity` : autorisé.

### 10.2 Séquence

| Étape | Migrations | Réversible |
|---|---|---|
| **T1** `identity 0006_contexts_schema` (tous les nouveaux modèles, colonnes nulles) ; `identity 0007_seed_document_requirements` (exigences provisoires) ; `moderation 0003_auditlog_context` | oui (`migrate … zero` des seuls ajouts ; la graine est supprimée en retour) |
| **T5** `marketplace 0002_offer_seller_context` (colonnes + remplissage `RunPython` : `seller_context_type='USER'`, `seller_context_id=seller_id`, `created_by=seller_id`) ; `visibility 0002_counter_seller_context` (idem) ; `messaging 0002_conversation_message_contexts` (réel) ; `notifications 0002_notification_context` (schéma seul, nul = personnel, sans remplissage) ; `reviews 0003_provider_choice` | oui |
| **T9a** `identity 0008_convert_business_profiles` (`RunPython`) puis `marketplace 0003_convert_offers`, `visibility 0003_convert_counters`, `reviews 0004_convert_review_contexts` (dépendent de `identity 0008`) | données : non (voir 10.4) |
| **T9b** contraction : `identity 0009_contract_legacy_user_types` (retrait de `BusinessProfile`, `BusinessProfileCategory`, `User.user_type`, `KycDocument.business_profile` ; `KycDocument.organization` NOT NULL), `marketplace 0004_contract_offer_seller`, `visibility 0004_contract_counter_seller` | schéma : oui (colonnes recréées nulles), données : non |
| **Plus tard** (tâche de nettoyage, hors L0-09) : retrait de `LegacyAccountMapping` et `Organization.legacy_business_profile_id` | — |

### 10.3 Migration de données (D1, D2), règles

`identity 0008` (une transaction ; SQLite exécute le DDL dans la transaction) : pour chaque `BusinessProfile` sans ligne dans `LegacyAccountMapping` (idempotence) : créer `Organization` (`org_type='ENTREPRISE'`, `status='ACTIVE'`, nom = `business_name`, `description` = `bio`, `logo` = même nom de fichier, `nif`, ville et commune du compte, `created_by` = titulaire, `legacy_business_profile_id`), `OrganizationCategory` depuis `BusinessProfileCategory`, `Membership(OWNER, ACTIVE)` pour le titulaire, rattacher ses `KycDocument` (`organization`, `uploaded_by` = titulaire), inscrire `LegacyAccountMapping(user_id, organization_id)`. Un compte `ENTREPRISE` sans `BusinessProfile` et tout compte `PARTICULIER` ne reçoivent rien. Équivalence : les trois pièces exigées de `ENTREPRISE` sont celles de l'ancien `is_verified` ; un jeu de test vérifie `ancien is_verified == résumé complet` pour chaque profil.

`marketplace 0003`, `visibility 0003`, `reviews 0004` : pour chaque ligne de la table de correspondance, `UPDATE … WHERE seller_context_type='USER' AND seller_context_id=<user_id>` vers `(ORGANIZATION, organization_id)`, `created_by`/auteur inchangé. Les avis suivent l'organisation (la note de l'ancien compte entreprise devient celle de l'organisation). Les compteurs `contacts_count` et `likes_count` ne changent pas. Les conversations existantes restent sans `seller_context` (accès par participants, comme avant) : acceptable car ce sont des données de développement (ADR 0002 : aucune donnée de production) ; les nouvelles conversations d'organisation sont en accès par capacité. Les consentements et numéros de contact personnels des anciens titulaires restent au compte et **ne sont pas transférés** à l'organisation (le consentement donné à titre personnel ne vaut pas pour l'organisation) : une organisation migrée n'offre que `MESSAGE` jusqu'à un nouveau consentement.

### 10.4 Retour arrière et garde-fous

- Avant T9 : tag Git `pre-L0-09-conversion` et copie de `db.sqlite3` hors dépôt (jamais commitée). Le retour arrière réel après contraction est la restauration de cette copie : les migrations de conversion et de contraction sont déclarées réversibles pour le schéma uniquement (la partie données est un `noop` documenté).
- Test de migration (`MigrationExecutor`, état historique avant `identity 0008` puis avant, pendant et après) : jeu fabriqué avec comptes entreprise et particulier, pièces, offres, avis, compteurs, contacts ; vérifie rattachement, équivalence de vérification, avis suivis, aucun doublon en cas de double exécution.
- `grep -rn "user_type\|BusinessProfile\|business_profile" backend/apps` ne doit plus rien renvoyer hors migrations historiques à la fin de T9.
- Fichiers KYC jamais déplacés : le champ `file` garde le même chemin dans le stockage privé.

## 11. Impact sur les autres modules

### 11.1 `marketplace`, `visibility`
Tout `seller=request.user`, `seller_id`, `seller__is_active`, `offer.seller.is_active` est remplacé : création et listes par contexte (6.4), autorisation par objet via `identity.authorize_on`, visibilité par `seller_is_public`, notification d'expiration par contexte. `count_active_offers(context)` compte par contexte vendeur, sans aucun plafond (quotas : L1-11). `record_view(offer_id, seller_context_type, seller_context_id, …)` et `record_share` idem. `count_contacts_by_offer` renvoie `(offer_id, ctx_type, ctx_id, total)`. Commande `sync_seller_visibility` (recalcul complet depuis `identity.is_seller_context_public`, idempotent) ajoutée au cron (toutes les heures) et au test de crontab. `moderation` : les contrôles « l'offre appartient au sanctionné » passent par `marketplace.services` et le contexte de l'offre ; la sanction d'un compte masque les offres de ses contextes `USER` et `PROVIDER` (via `seller_is_public`), pas celles d'une organisation dont il est seulement membre (la suspension d'une organisation est une action du personnel sur `Organization`, pas une sanction de compte).

### 11.2 Contact (ADR 0005)
`create_contact_event`, `reveal_contact`, `list_reveals_for_seller`, `get_allowed_channels`, `get_contact_endpoint` raisonnent sur le **contexte vendeur de l'offre** :
- `USER` : comportement actuel. `PROVIDER` : réglages du compte titulaire (même `ContactPoint`/`ContactConsent`).
- `ORGANIZATION` : `MESSAGE` toujours proposé ; `CALL` et `WHATSAPP` seulement si `IdentitySettings.org_phone_channels_enabled` est vrai **et** l'organisation a un `ContactPoint` vérifié **et** un `ContactConsent` actif donné par un propriétaire ou un administrateur avec la version courante du texte. Par défaut (interrupteur faux), l'organisation n'offre que `MESSAGE` : c'est l'intérim D6 appliqué à la lettre, et le consentement des organisations (Q-CLI5) n'est pas ouvert sans réponse du client. Le téléphone personnel d'un membre n'est jamais remis au titre d'une offre d'organisation (test de non-fuite).
- Refus « sa propre offre » : `acts_for_context(sender, contexte vendeur)` (donc aussi un membre actif de l'organisation). Les quotas de révélation restent par compte acheteur.

### 11.3 `messaging`, `notifications`, `reviews`
Messagerie : voir A8 et 9.8. `open_contact_conversation` pose `seller_context_*` ; pour `USER` et `PROVIDER` le titulaire reste participant ; pour `ORGANIZATION` seul l'acheteur est participant. Notifications de contact : destinataires `get_context_recipients(..., 'message.reply')`. `Message.is_read` reste un booléen partagé du côté organisation (dette L2-09). Avis : `Review.seller_context_*` déjà en place ; `reply_to_review` et `is_review_seller` passent à `can(..., 'review.reply')` ; la vérification « auteur = vendeur » passe à `acts_for_context`. Avis croisés (E9) : détection inchangée pour `USER` ; `PROVIDER` ramené au compte titulaire ; **les organisations sont exclues de la détection en V1** (risque résiduel documenté, section 15) ; l'éligibilité à l'avis par contact réel et le plafond quotidien d'avis limitent l'abus.

### 11.4 `moderation`, `payments`, admin
`AuditLog.record(..., context=None)` et `record_audit(..., context=None)` : nouveau paramètre facultatif. `Sanction.apply/lift` appellent `identity.services.set_account_active`. `payments` (gelé) : `Transaction.seller` ne change pas (hors V1, refonte L1-12). Admin Django : `Organization` (lecture, actions « Suspendre » et « Réactiver » réservées à la permission `identity.suspend_organization`, audit `ORG_SUSPENDED`/`ORG_REACTIVATED`), `Membership` en **lecture seule** (le personnel n'attribue pas de rôle, il ne voit ni téléphone ni e-mail de membre), `OrganizationDocumentRequirement` et `IdentitySettings` modifiables par l'administrateur, `ProviderProfile` en lecture ; retrait de `BusinessProfile` à T9. `setup_roles` : permissions des nouveaux modèles par groupe (vérificateur : pièces ; administrateur : organisations en lecture et suspension, exigences, réglages) ; une permission inconnue fait toujours échouer la commande.

### 11.5 Front (`frontend`, branche `frontend`)
Nouveau : fournisseur de contexte actif (mémorisé dans `localStorage`, Q-CP4), en-tête `X-Context` ajouté par `api/client.ts` à toute requête authentifiée dont le contexte n'est pas `USER` (les endpoints qui l'ignorent le tolèrent), sélecteur de contexte toujours visible (CDC §3.1), invalidation des clés React Query dépendantes du contexte à la bascule (clés préfixées par `[type, id]`), gestion de `DENY_RELATION`/`DENY_OBJECT_STATE`/`DENY_SECURITY` (retrait du contexte, bascule sur le personnel, message en français), création d'organisation, activation du prestataire, badges par claim. Fichiers listés dans la spec §7.3 (`Register`, `Settings`, `Verification`, `Dashboard`, `PostEditor`, `AccountShell`, `Navbar`, `SellerProfile`, `SellerCard`, `PostCard`, `Businesses`, `lib/post.ts`, `api/types.ts`, `DesignSystem`, `backend-contract.test.ts`).

## 12. Sécurité, tests de non-régression et de non-fuite

À écrire avec les tâches (la tâche qui crée la fonctionnalité écrit son test) ; `auditeur-securite` relit T2, T4, T7 et T9.

**Autorisation**
- Matrice rôle x capacité complète ; `identity.services` : aucune fonction `can/authorize*/add_member/change_member_role/revoke_member` n'a de paramètre nommé `plan`, `price`, `entitlement`, `subscription` (test d'absence par introspection) ; un abonnement actif ne change ni rôle ni claim.
- `is_staff` / `is_superuser` sans membership : `DENY_RELATION` sur un contexte d'organisation.
- Révocation immédiate : requête de A avec `X-Context: ORGANIZATION:<id>` réussit, B révoque A, la requête suivante avec **le même jeton** renvoie `DENY_RELATION`, le contexte personnel reste utilisable.
- Deux requêtes concurrentes avec deux contextes : chacune traitée sous le sien (aucun état partagé).
- En-tête : absent, vide, mal formé, `USER:<autre>`, `PROVIDER:<autre compte>`, `ORGANIZATION:<inexistant>` ; aucune écriture n'a lieu dans les cas de refus (compter les lignes).
- Aucun repli : publier sous une organisation dont on est révoqué ne crée aucune offre personnelle.
- `last_owner` : rétrogradation, révocation, départ du dernier propriétaire ; deux propriétaires, l'un part, l'autre devient dernier ; concurrence (deux départs simultanés) : au plus un réussit.
- Administrateur : ne peut ni attribuer, ni retirer OWNER, ni agir sur un propriétaire ; ne peut pas s'attribuer un rôle supérieur.
- Décision KYB par un ancien membre : refusée sans limite de durée ; par l'auteur de la pièce ; par le créateur.
- Offre : le corps ne peut pas imposer le contexte vendeur ; un analyste ne publie pas ; un membre révoqué ne modifie pas l'offre dont il était l'auteur ; l'offre d'une organisation reste modifiable par les autres membres après le départ de l'auteur.
- Listes « mes offres », corbeille, statistiques, réglages de contact, boîte de messages : isolation stricte entre contextes d'un même utilisateur.

**Fuites de données (exhaustivité des clés, chaque charge publique et chaque événement)**
- `organizations/` (liste), `sellers/…`, objet `seller` des offres, `contexts/` : liste de clés exacte ; recherche de motifs téléphone, e-mail, `nif`, `kyc`, `members`.
- Un membre avec `ContactPoint` vérifié et `CALL` consenti : l'offre de son organisation n'expose jamais son numéro (`allowed_channels == ['MESSAGE']`, révélation `CALL` refusée `channel_not_allowed`), même avec `org_phone_channels_enabled` vrai tant que l'organisation n'a pas son propre numéro et son propre consentement.
- Changer le numéro personnel d'un membre ne modifie pas les canaux de l'organisation.
- `AuditLog.details` et charges utiles d'outbox : ni nom, ni e-mail, ni téléphone (test avec des valeurs sentinelles).
- Notifications d'un membre révoqué : supprimées pour cette organisation, et plus de nouvelles notifications ; conversation d'organisation illisible après révocation, historique conservé.
- Pièces KYB : aucune réponse JSON ne contient l'URL du fichier ; le téléchargement reste réservé à `review_kycdocument`.
- Analyste : pas de liste de demandeurs, pas de données personnelles.

**Non-régression**
- Suites `identity`, `marketplace`, `reviews`, `visibility`, `messaging`, `notifications`, `moderation`, `payments`, `platform_core` et `common.DomainBoundariesTests` vertes à chaque tâche ; le nombre de tests ne baisse pas (`python manage.py test apps`, objectif supérieur ou égal au décompte avant T1).
- `makemigrations --check --dry-run`, migrations sur base SQLite vierge, `setup_roles`, `migrate` d'une copie d'une base de développement avec anciennes données.
- Requêtes SQL : résolution du contexte (`assertNumQueries`, +1 au plus) ; liste d'offres de 20 éléments avec vendeurs d'organisation (aucun N+1 : `get_seller_summaries` par lot, `get_user_context_roles` une fois).
- Script `backend/scripts/recette_contrat_http.py` et `backend-contract.test.ts` à jour.
- Réglage CORS : `x-context` présent.
- Test de crontab : la nouvelle commande `sync_seller_visibility` est planifiée.

## 13. Plan de tâches

Légende : **I** = branche d'intégration `integ/L0-09` (changements de contrat JSON fusionnés avec le front en une fois) ; **D** = fusion directe dans `backend` (additif). Sérialisation des migrations : section 10.1.

| ID | Story | Agent | Contenu | Dépend de | Parallélisable avec | Branche |
|---|---|---|---|---|---|---|
| **T0** | — | designer-ux | Spécifications d'écran : sélecteur de contexte, création d'organisation, activation du prestataire, badges par claim, états de refus (`DENY_*`), profils publics ; libellés de claims et de types d'organisation | cet ADR | tout T1 à T9 | — |
| **T1** | L0-09a | dev-backend | `identity/0006` + `0007` (schéma complet, exigences provisoires), `moderation/0003` (`context_*`), constantes de `common/contexts.py`, `capabilities.py`, services d'équipe et de cycle de vie, `IdentitySettings`, admin (lecture seule), `AuditLog` avec contexte, déclaration des événements, `DomainBoundariesTests`, matrice et `last_owner` | cet ADR | T0 | D |
| **T2** | L0-09b | dev-backend, auditeur-securite | `acting.py`, `ContextDenied`, `authorize/authorize_on/can`, `GET contexts/`, CORS `x-context`, tests d'en-tête et de révocation immédiate, budget SQL | T1 | T0 | D |
| **T3** | L0-09c | dev-backend | `ProviderProfile` : services et endpoints 9.3, intégration à `contexts/` et `acts_for_context`, événement de statut | T2 | T4, T8 | D |
| **T4** | L0-09d | dev-backend, auditeur-securite | Pièces d'organisation (9.4), claims dérivés, exigences, règle de l'ancien membre, file de vérification, suppression de `recompute_verification` | T2 | T3, T8 | I |
| **T8** | L0-09g (identité) | dev-backend | `register/` et `me/` sans `user_type`/`business_profile`, `organizations/` (création, `internal`, `PATCH`, `archive`, `leave`, liste publique), throttles, remplace `businesses/` | T2 | T3, T4 | I |
| **T5** | L0-09e (+ profil vendeur) | dev-backend | Migrations d'extension de marketplace, visibility, messaging, notifications, reviews ; `Offer`/compteurs par contexte ; `seller_is_public` + abonné + `sync_seller_visibility` + cron (retirer alors `no_subscriber` de `identity.seller_context_status_changed` dans `platform_core/catalog.py` et le test `test_event_type_has_no_subscriber_yet` de `tests_provider.py`) ; `set_account_active` et branchement de `moderation` ; `get_seller_summaries` nouvelle forme ; objet `seller` ; `sellers/…` (9.7) ; statistiques par contexte ; `?seller=` | T2, T3, T4 (claims), T8 | — | I |
| **T6** | L0-09f1 | dev-backend | Avis (réponse, `acts_for_context`, destinataires), `review_posted` v3, notifications (`context`, abonnés d'équipe, de statut, de décision KYB, purge à la révocation), expiration v2 | T5 | T7 | I |
| **T7** | L0-09f2 | dev-backend, auditeur-securite | Contact par contexte vendeur, `ContactPoint/ContactConsent` d'organisation et interrupteur, `get_allowed_channels` par contexte, événements v2, messagerie par contexte (accès par capacité, `sender_context`) | T5 | T6 | I |
| **T9** | L0-09h | dev-backend, auditeur-securite | Migrations de conversion (T9a) puis de contraction (T9b), retrait du code et des tests obsolètes, admin, `setup_roles`, script de recette | T3, T4, T6, T7, T8 | F2 | I |
| **F1** | L0-09i (infrastructure) | dev-frontend | Types, `api/client.ts` (en-tête), fournisseur de contexte et sélecteur, gestion des `DENY_*`, création d'organisation, activation du prestataire, tests Vitest de non-persistance entre contextes (contre le contrat 9, avec des doubles) | T0, T2 (contrat figé ici) | T3 à T8 | I |
| **F2** | L0-09i (pages) | dev-frontend | Adaptation des pages et composants à `seller`, `verified_claims`, `organizations/`, suppression de `user_type`/`business_profile` ; `npm run lint && npm run test && npm run build` | F1, T8, T5 | T6, T7, T9 | I |
| **T10** | L0-09j | qa-testeur | Recette IAM-01 à IAM-06, AC-07, AC-08, AC-14, non-régression ; rapport | T9, F2 | — | I |

Relecture (`relecteur-code`) à la fin de chaque tâche ; `auditeur-securite` où indiqué. Fusion de `integ/L0-09` dans `backend` puis `frontend` après T10 (fusion des deux branches en même temps, car le contrat JSON des offres, des vendeurs, du profil et de la vérification change).

Ordre critique : T1 → T2 → {T3, T4, T8} → T5 → {T6, T7} → T9 → T10. Chemin du front : F1 dès T2 figé ; F2 après T5 et T8. Si un seul agent backend est disponible, ordre : T1, T2, T3, T8, T4, T5, T6, T7, T9.

Scission décidée de L0-09f : f1 (T6) et f2 (T7), parallélisables après T5 ; les fichiers communs (`notifications/events.py`, `notifications/services.py`) sont répartis par abonné (T6 : avis, équipe, statut, KYB ; T7 : contact, échange). Les colonnes de `notifications` et `messaging` sont posées par T5 pour éviter tout conflit de migration.

## 14. Questions client (non tranchées) : valeur provisoire et impact

| # | Question | Valeur provisoire retenue | Impact si le client répond autrement |
|---|---|---|---|
| Q-CLI1 | Les 4 rôles suffisent-ils ? Branches hors V1 ? Plusieurs propriétaires ? | 4 rôles en constantes, pas de branches, plusieurs propriétaires (décision D4 du chef de projet) | Rôles configurables : passer `capabilities.py` en tables (`Role`, `RolePermission`) derrière les mêmes fonctions `can/authorize` ; aucun appelant à changer. Branches : nouveau modèle et nouveau périmètre de portée, hors L0-09. |
| Q-CLI2 | Pièces KYB par type ; une organisation non vérifiée peut-elle publier ? | Table `OrganizationDocumentRequirement` : ENTREPRISE et ORGANISATEUR_EVENEMENTS : RCCM, ID, représentant ; BOUTIQUE : ID, représentant ; ONG : arrêté, ID, représentant ; **la publication ne dépend pas de la vérification** (comportement actuel) | Changement de pièces : édition de lignes en back-office, aucune migration. Publication conditionnée à la vérification : une règle de marché à ajouter dans `marketplace` (`DENY_ELIGIBILITY`), sans toucher à `identity`. |
| Q-CLI3 | Que publie le contexte personnel ? | Tout (produits et services), aucune restriction | Restreindre aux objets d'occasion : un contrôle dans `marketplace.create_offer` (type SERVICE interdit en `USER`) et le formulaire. Aucun schéma. |
| Q-CLI4 | Nombre d'organisations par compte | 10 `Membership` actifs par compte (créées ou rejointes), `IdentitySettings.max_organizations_per_account` | Valeur de réglage (1 à 100) ; si « créées » et « rejointes » doivent être comptées séparément : un second champ de réglage et un filtre sur `role='OWNER'`. |
| Q-CLI5 | Qui consent à la révélation du numéro d'une organisation, quel texte ? | Un propriétaire ou un administrateur ; **fonction fermée par défaut** (`org_phone_channels_enabled = faux`) : l'organisation n'offre que `MESSAGE` | Si le client change l'acteur (par ex. propriétaire seul) : changer la capacité `contact.manage_channels`. Si un texte propre est exigé : nouvelle version de `CONTACT_CONSENT_TEXT_VERSION` spécifique aux organisations ; interrupteur laissé fermé jusqu'à l'accord. |
| Q-CLI6 | Conservation des pièces KYB et de l'audit des membres | Aucune purge ; pas de durée inventée (dette LEG-PRV déjà ouverte) | Commande de purge planifiée après la réponse ; les pièces sont déjà isolées en stockage privé et rattachées à l'organisation. |
| Q-CLI7 | Vérification d'identité du prestataire ; catégories à vérification renforcée | Le prestataire s'active sans vérification d'identité ; aucune catégorie sensible gérée | `VerificationRequest` pour `ProviderProfile` (nouvelle table, claims dérivés comme pour les organisations) et règle d'éligibilité dans `marketplace`. |
| Q-CLI8 | Unicité des noms d'organisation, usurpation avant la revendication | Homonymes permis, plafond par compte, claims visibles, immuabilité du nom après vérification (A13), signalement (cible `organization` à ajouter à `moderation`, suivi L1-01) | Unicité des noms normalisés : possible seulement en couche service (pas d'unicité conditionnelle) avec liste de noms réservés en base ; coût : faux positifs sur les homonymes. |

## 15. Risques, dettes et points à valider

**À faire valider par l'utilisateur**
1. **A13** : le nom d'une organisation ne peut plus être modifié par l'API dès qu'une pièce est validée (contrainte forte pour les petites entreprises qui se renomment ; passage par le personnel).
2. **`org_phone_channels_enabled` fermé par défaut** : lecture stricte de D6 et de Q-CLI5 (aucun appel ni WhatsApp pour une organisation). À ouvrir quand le client répond.
3. Écart volontaire avec la spec : une organisation inexistante renvoie `DENY_RELATION` comme un non-membre (pas d'oracle d'existence), `DENY_CONTEXT` restant pour les formats invalides et les contextes d'un autre compte.
4. Codes métier en minuscules (`last_owner`) et codes d'autorisation en majuscules (A14).
5. Fusion groupée des tâches de contrat (branche `integ/L0-09`) : les clients du JSON actuel (front, script de recette) cassent au moment de la fusion, pas avant.
6. Données de développement : conversations existantes d'anciens comptes entreprise restent en accès par participants (pas de transfert à l'organisation) ; consentements de contact non transférés.

**Risques**
- **Dénormalisation `seller_is_public`** : un événement `dead` laisse une offre publique après une suspension. Parades : diffusion immédiate (ADR 0003), `dispatch_outbox --stats` en alerte, commande de réconciliation horaire, test de bout en bout (suspension d'une organisation, offre non listée).
- **Pas de cache du rôle** : une requête SQL de plus par appel sensible au contexte ; assumé (révocation immédiate).
- **Avis croisés entre organisations** (E9) : non détectés en V1 ; atténuation par contact réel et plafond d'avis ; à reprendre après L1-01.
- **Usurpation de nom** avant la revendication (Q-CLI8).
- **Volume des tests à réécrire** (environ 278 occurrences dans 23 fichiers backend, 40 dans 17 fichiers du front) : le nombre de tests ne doit pas baisser.
- **Concurrence `last_owner`** : le verrou de ligne n'a d'effet que sous MySQL ; sous SQLite l'écrivain unique suffit. Le test de concurrence s'appuie sur la mise à jour conditionnelle.
- **T5 est la plus lourde** (marketplace, visibility, quatre autres migrations) : si le calendrier l'exige, la scinder en T5a (schéma, `Offer` et compteurs) et T5b (visibilité du vendeur, profil vendeur, statistiques) ; T5b reste avant T6/T7.
- **Conflits de fichiers** : `identity/views.py` et `serializers.py` sont partagés entre T3, T4 et T8 ; chaque tâche crée ses propres fichiers (`views_organizations.py`, `views_provider.py`, `views_verification.py`, et sérialiseurs homonymes) et ne touche `urls.py` que pour ajouter ses routes.

**Dettes signalées**
- Voir la section 17.3 : suppression de compte et dernier propriétaire (chemin de secours audité, organisations orphelines), ajout direct de membre non exposable (invitation et acceptation en L1-01, revue sécurité), noms réservés et signalement d'usurpation, recette MySQL des verrous.
- `Message.is_read` partagé du côté organisation ; boîte d'équipe et attribution : L2-09.
- Durées de conservation de `AuditLog`, des pièces et des événements : LEG-PRV.
- `LegacyAccountMapping` et `Organization.legacy_business_profile_id` à retirer après la mise à jour des bases de développement.
- Vérification d'e-mail absente (dette ADR 0002), sans lien avec L0-09.
- Aucune clé primaire entière ni clé étrangère inter-domaines introduite par cet ADR.

## 16. Amendements aux ADR précédents

- **ADR 0002** : la ligne `marketplace.Offer` (« `Offer.seller` devient `organization_id` en L0-09 ») est remplacée par `seller_context_type/id` + `created_by` (A3). Les lignes `accounts.User` et `BusinessProfile` renvoient ici (note ajoutée dans l'ADR 0002).
- **ADR 0004** : « avis croisés calculés entre `USER` seulement ; à revoir pour les organisations » : voir E9 (section 11.3). `reviews.review_posted` passe en v3.
- **ADR 0005** : `ContactPoint` et `ContactConsent` deviennent rattachables à une organisation (section 4.4) ; `get_allowed_channels` et `get_contact_endpoint` travaillent par contexte vendeur ; événements de contact en v2.
- **CDC** (à appliquer sur accord de l'utilisateur, par `analyste-fonctionnel`) : §11.1 ligne `identity` (`User, ProviderProfile, Organization, Membership, VerificationRequest, ContactPoint, ContactConsent, OtpCode` ; contexte calculé, rôles en constantes) ; §11.2 ligne `MembershipChanged` ; §3.1 matrice de rôles (section 5) ; §3.1 vérification (exigences par type, libellé de synthèse accompagné de ses composantes) ; §11.4 tâches L0-09a à L0-09j.

## 17. Amendement 1 (10/10/2026) : réponses aux questions du designer (Q-F1 à Q-F6) et gestion d'équipe cible

- **Statut :** proposé, même validation que l'ADR. Les sections 1 à 16 ne sont pas modifiées ; en cas de divergence, **cette section prévaut** pour les points listés.
- **Origine :** `docs/specs/L0-09-ecrans-contextes.md` §14 et §15.2. Les décisions de design D1 à D11 de cette spec sont acceptées par le chef de projet. D10 (bouton « Quitter » toujours proposé, refus `last_owner` traité par un message) et D11 (écran Équipe réduit en L0-09) restent valables.

### 17.1 Décisions

| Question | Décision |
|---|---|
| **Q-F1** `phone_verified` dans `me/` | Le champ est **déjà** lu et exposé par `GET/PATCH ID me/` (`UserSerializer`, lecture seule). Il est **figé dans le contrat** : `"phone_verified": true|false`, jamais modifiable par `PATCH`. Aucun travail backend, sauf un test de contrat qui le verrouille (T8). Le garde-fou du front reste doublé par le 403 `phone_verification_required` (le serveur décide). |
| **Q-F2** Organisation issue d'un ancien compte entreprise | Booléen `migrated_from_business` (nom retenu) sur chaque élément de `GET ID contexts/` et dans `OrganizationInternal`. Valeur : `Organization.legacy_business_profile_id` non nul. Toujours `false` pour `USER` et `PROVIDER`. Aucune donnée personnelle. **Sera retiré avec `LegacyAccountMapping` et `legacy_business_profile_id`** (tâche de nettoyage de la section 15) : le front traite l'absence de la clé comme `false`. Sert uniquement à cibler un message d'information ; ne conditionne aucune autorisation. Le test d'exhaustivité des clés de `contexts/` (section 12) est mis à jour. |
| **Q-F3** Canaux proposables | `available_channels` (tableau parmi `MESSAGE`, `CALL`, `WHATSAPP`) ajouté à **chaque** réponse de `contact-settings/*`, à côté de `context`. Sens : canaux que ce contexte a le droit de configurer, indépendamment de l'état actuel (numéro, consentement) ; ce n'est pas `allowed_channels` d'une offre, qui reste le canal effectivement utilisable. `USER`, `PROVIDER` : les trois. `ORGANIZATION` : `["MESSAGE"]` tant que `IdentitySettings.org_phone_channels_enabled` est faux ; les trois quand il est vrai. Régler un canal absent de `available_channels` : `400 {"channel": [...]}` avec code `channel_not_available`. La valeur vient de la même fonction de service que `get_allowed_channels` (une seule source). |
| **Q-F4** Organisation archivée | `GET ID organizations/<uuid>/internal/` et les routes `organizations/<id>/…` : ordre de contrôle **non-membre (`DENY_RELATION`) puis état** ; un membre actif d'une organisation archivée reçoit `403 DENY_OBJECT_STATE` (suspendue : `DENY_SECURITY`, inchangé). Exception : `POST …/leave/` reste permis sur une organisation suspendue ou archivée (quitter ne doit jamais être bloqué) et renvoie `204`. Les membres d'une organisation archivée restent `ACTIVE` en base ; seul `leave/` les retire. L'organisation n'est pas listée par `contexts/` (inchangé, 9.1) ; la question client 15.1 n°6 de la spec (afficher les profils suspendus ou archivés en lecture seule) reste ouverte et ne bloque rien. |
| **Q-F5** `category_ids` | **Facultatif, liste vide permise** à la création et à la modification, pour organisation et prestataire (la publication d'offre ne dépend pas des catégories du vendeur). **Maximum 5**, **réglable** (règle 11) : nouveau champ `IdentitySettings.max_categories_per_context` (PositiveSmallInteger, défaut 5, validateurs 1 à 20). Doublons ignorés. Au-delà : `400 {"category_ids": ["..."]}` code `too_many_categories`. UUID inconnu : `400` code `unknown_category` (inchangé). Le front lit la limite dans `GET ID organizations/limits/` (17.2). |
| **Q-F6** Membre vu par les autres membres | Champs : `membership_id`, `display_name` (`public_display_name` : prénom + initiale du nom, « Marie K. »), `role`, `joined_at`, `is_self` (booléen). **Jamais** : téléphone, e-mail, nom complet, photo du compte, identifiant du compte, historique, pièces (règle 10). Les anciens membres (`REVOKED`) ne sont pas listés. Visible par tout membre actif (`org.view_internal`), analyste compris. Test d'exhaustivité des clés et de motifs téléphone et e-mail. |

### 17.2 Contrat d'API ajouté

Chemins sous `ID = /api/accounts/` (L0-11 ajoutera `v1`). Format d'erreur identique à la section 9.

**A. Modifications de réponses existantes (livrées en L0-09)**

- `GET ID me/` : confirme `phone_verified` (booléen, lecture seule).
- `GET ID contexts/` : chaque élément gagne `"migrated_from_business": false` (`true` pour une organisation issue d'un ancien profil entreprise).
- `OrganizationInternal` (9.2) gagne `"migrated_from_business"`.
- `contact-settings/*` : chaque réponse gagne `"available_channels": ["MESSAGE"]` (ou les trois canaux).
- `POST/PATCH organizations/`, `POST/PATCH provider/` : règle `category_ids` ci-dessus.

**B. `GET ID organizations/limits/`** (authentifié ; L0-09 ; le front ne code aucune limite)
```json
200 {"max_categories_per_context": 5, "max_organizations_per_account": 10,
     "name_min_length": 2, "name_max_length": 255, "description_max_length": 2000}
```
Valeurs issues de `IdentitySettings` et des validateurs, informatives (le serveur valide toujours). Rien de propre à l'utilisateur.

**C. Gestion d'équipe : contrat CIBLE pour L1-01 (non livré en L0-09, non inscrit au plan T1 à T10)**

Les services existent (T1 : `add_member`, `change_member_role`, `revoke_member`, `leave_organization`). L1-01 ajoute les endpoints, l'invitation et les écrans. Le front de L0-09 ne les appelle pas ; il en connaît les formes pour rester cohérent. Capacités : section 5.

| Appel | Capacité | Corps | Réponse |
|---|---|---|---|
| `GET ID organizations/<uuid>/members/` | `org.view_internal` | `page`, `page_size` | `200 {count,next,previous,results:[{"membership_id","display_name","role","joined_at","is_self"}]}` ; ordre : propriétaires, administrateurs, éditeurs, analystes, puis `joined_at` ; seulement `ACTIVE` |
| `POST ID organizations/<uuid>/members/` | `org.manage_members` | `{"identifier": "<téléphone ou e-mail du compte invité>", "role": "EDITOR"}` | `201` `{membership_id, display_name, role, joined_at, status}` (ajout direct en V1, `status = ACTIVE` ; avec invitation en L1-01 : `INVITED`, même route). Compte introuvable : même réponse que le succès côté contenu (`202 {"detail": "..."}` neutre), pas d'oracle d'existence. Erreurs : `400` rôle inconnu ; `403 DENY_PERMISSION` (administrateur demandant `OWNER`) ; `409 organization_limit_reached` (plafond de l'invité, formulé sans révéler son nombre) |
| `PATCH ID organizations/<uuid>/members/<membership_id>/` | `org.manage_roles` | `{"role": "ADMIN"}` | `200` membre ; `409 last_owner` ; `403 DENY_PERMISSION` (administrateur sur un propriétaire ou vers `OWNER`) |
| `DELETE ID organizations/<uuid>/members/<membership_id>/` | `org.manage_members` | — | `204` (`end_reason = removed`) ; `409 last_owner` ; `403 DENY_PERMISSION`. Un membre qui part lui-même passe par `leave/` |

Le `membership_id` (jamais l'identifiant du compte) identifie un membre. Chaque appel : audit synchrone avec contexte, événement `identity.membership_changed`, notification de la personne concernée, révocation immédiate (R11). Revue `auditeur-securite` obligatoire en L1-01 (énumération de comptes par `identifier`, escalade de rôle).

### 17.3 Impact sur le plan T1 à T10 (aucune tâche invalidée ni ajoutée)

| Tâche | Impact |
|---|---|
| **T1** | Ajouter `max_categories_per_context` à `IdentitySettings` (même migration `identity 0006`, règle 10.1 respectée) ; `Organization.legacy_business_profile_id` sert de source à `migrated_from_business` (déjà prévu). |
| **T2** | `contexts/` : clé `migrated_from_business` et test d'exhaustivité mis à jour ; 0 requête de plus (colonne lue avec l'organisation). |
| **T8** | `OrganizationInternal.migrated_from_business` ; validation `category_ids` (5 réglable, vide permis, codes `too_many_categories`) ; `leave/` permis sur organisation suspendue ou archivée ; `internal/` : `DENY_OBJECT_STATE` pour l'archivée ; endpoint `organizations/limits/` ; test de contrat de `me/.phone_verified`. |
| **T3** | Mêmes règles `category_ids` pour `provider/`. |
| **T7** | `available_channels` dans toutes les réponses `contact-settings/*`, refus `channel_not_available` ; tests : interrupteur fermé `["MESSAGE"]`, ouvert trois canaux. |
| **T9** | `migrated_from_business` vrai pour les organisations converties (T9a remplit `legacy_business_profile_id`), faux sinon : à ajouter au test de migration. |
| **T4, T5, T6** | Aucun. |
| **F1 / F2** | Consomment `phone_verified`, `migrated_from_business` (clé absente = faux), `available_channels`, `organizations/limits/`, `DENY_OBJECT_STATE`. L'écran Équipe réduit n'appelle rien de la partie C. |
| **T10** | Ajouter à la recette : message d'ancienne entreprise, canaux d'organisation, plafond de catégories, quitter une organisation archivée. |

Le chemin critique (T1 → T2 → {T3, T4, T8} → T5 → {T6, T7} → T9 → T10) ne change pas.

### 17.4 Risques et points à valider

1. `migrated_from_business` est une dette volontaire : à retirer avec `LegacyAccountMapping` (section 15) ; le front doit tolérer son absence.
2. `available_channels` (configurable) et `allowed_channels` (effectif, par offre) sont deux notions : à documenter dans l'OpenAPI.
3. Plafond de 5 catégories : valeur provisoire sans source client, modifiable en back-office sans migration.
4. Partie C non validée par le client : seuls les noms de routes, la forme d'un membre et les rôles sont stables ; le mécanisme d'ajout (direct ou invitation) est tranché en L1-01.
5. `leave/` sur organisation archivée : volontaire (quitter n'est jamais bloqué).
6. Question client ouverte, inchangée : afficher en lecture seule les profils suspendus ou archivés (spec 15.1 n°6).

### 17.5 Compléments issus de la relecture et de l'audit de T1 (L0-09a)

Ces points s'ajoutent à la section 15 (dettes et registre de recette) et prévalent sur les sections 1 à 16 en cas de divergence.

1. **Dernier propriétaire et suppression de compte (dette).** `identity.services.assert_account_removable(user)` refuse (409 `last_owner_account`) la suppression d'un compte qui est seul propriétaire actif d'une organisation active ; elle est branchée sur la suppression d'un compte dans l'admin (unitaire et en masse). Elle ne bloque pas la désactivation par sanction ou modération (`is_active = False`). **Dette à livrer avec L1-01 / la suppression de compte :** un chemin de secours audité du personnel (réattribution du propriétaire sur preuve) et le sort d'une organisation devenue orpheline. Conséquence connue : l'admin Membership étant en lecture seule, Django refuse aussi de supprimer depuis l'admin un compte qui a des appartenances ; ces comptes doivent d'abord quitter leurs organisations.
2. **Ajout direct de membre : INTERDIT d'exposition.** `add_member` est un service interne, sans le consentement de la cible. Aucun endpoint ne doit l'appeler en l'état. **L1-01 doit implémenter l'invitation et son acceptation par la cible** (plafond d'organisations vérifié à l'acceptation, pas à l'envoi), avec **revue obligatoire de `auditeur-securite`**. Les refus portant sur la cible (compte inconnu, inactif, restreint ou au plafond) renvoient une réponse unique et neutre (400 `user_unavailable`) pour ne pas révéler l'existence ni l'état d'un compte ; `change_member_role` et `transfer_ownership` appliquent la même réponse à une cible inactive ou restreinte.
3. **Noms d'organisation.** Normalisation NFKC, refus des caractères Unicode de catégories Cc, Cf, Zl et Zp (contrôle, direction, largeur nulle, séparateurs de ligne), repli des espaces multiples, retrait des espaces de bord ; longueur contrôlée après normalisation (code `invalid_name`). **Tâche L1-01 / modération (non codée ici) :** liste de noms réservés configurable et signalement d'usurpation d'une organisation.
4. **Verrou de la cible à l'ajout.** `add_member` verrouille le compte cible et vérifie son plafond avant toute lecture de ses appartenances. **Registre de recette MySQL :** vérifier, sur MySQL réel (le verrou de ligne est sans effet sous SQLite), deux ajouts simultanés d'un même compte à deux organisations quand il lui reste une seule place, et deux départs simultanés de deux propriétaires.
5. **Quota.** Le plafond d'organisations ne compte que les appartenances actives dans des organisations actives (une organisation archivée ou suspendue libère la place).
6. **Organisation archivée.** Le dernier propriétaire peut transférer la propriété puis quitter une organisation archivée (tracé dans `AuditLog`) ; sur une organisation active, `last_owner` reste appliqué.
7. **Entrées des services.** Types vérifiés (erreur de validation 400, jamais 500), `nif` refusé au-delà de 50 caractères (plus de troncature), logo validé (taille, pixels) avant écriture et supprimé du stockage si la transaction échoue. Limite : une transaction englobante annulée plus tard n'est pas détectable par le service.
8. **Codes de validation** posés dès T1 : `invalid_name`, `invalid_org_type`, `invalid_description`, `invalid_nif`, `invalid_logo`, `too_many_categories`, `unknown_category`, `unknown_city`, `unknown_commune`.
9. **Contacts.** Contrainte `CHECK` « exactement un de `user` et `organization` » sur `ContactPoint` et `ContactConsent` (migration `identity 0008`).


## 18. Amendement 2 (10/10/2026) : pièces KYB, durcissement après relecture et audit de T4 (L0-09d)

1. **Schéma.** Migration `0009` : `KycDocument.business_profile` devient nullable (les pièces d'organisation n'ont pas de profil) ; NOT NULL sur `organization` et retrait de `business_profile` à la contraction T9 ; retour arrière impossible dès qu'une pièce d'organisation existe. Migration `0010` : `IdentitySettings.kyb_file_retention_days` (règle 11).
2. **Claims.** Calculés à la lecture, jamais stockés. Seules les pièces **actuellement exigées** (`OrganizationDocumentRequirement`) et au statut `VALIDE` donnent un claim ; le libellé « Organisation vérifiée » exige toutes les pièces exigées (et au moins une exigence configurée) et s'affiche toujours avec la liste des claims.
3. **Conflit d'intérêts.** La décision **et le téléchargement** d'une pièce d'organisation sont refusés (403) au déposant, au créateur de l'organisation et à toute personne ayant une ligne `Membership` de tout statut. Le refus de téléchargement est journalisé (`KYC_DOWNLOAD_DENIED`).
4. **Contrôle des fichiers (sans dépendance).** JPEG et PNG sont ouverts avec Pillow (`verify()` puis rechargement) et plafonnés en pixels ; un PDF est refusé s'il contient `/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFile` ou `/OpenAction` (noms PDF avec échappements `#xx` décodés). **Prérequis de production : analyse antivirus (ClamAV) des pièces déposées**, ce contrôle d'octets ne la remplace pas.
5. **Minimisation (règle 10).** Les images JPEG/PNG d'une organisation sont ré-encodées dans le même format, sans métadonnées (EXIF, GPS), sans redimensionnement (un justificatif doit rester lisible) ; les PDF restent tels quels. Le ré-encodage reprend le principe de `common.images.reencode_image` mais pas sa sortie WebP réduite à 1024 px (illisible pour un justificatif, et le contrôle de type ne connaît que JPEG/PNG/PDF). **Question ouverte LEG-PRV : conservation de l'original.**
6. **Cycle de vie des fichiers.** Le fichier privé est supprimé avec sa ligne (signal `post_delete`, après validation de la transaction, y compris en cascade) ; un échec disque est journalisé sans erreur 500. Si une erreur survient après l'écriture d'un fichier au dépôt, il est supprimé. Commande planifiée `purge_kyb_files` : supprime le **fichier** (pas la ligne ni la décision, donc les claims restent) des pièces décidées depuis plus de `kyb_file_retention_days` jours ; 0 = illimité (défaut tant que LEG-PRV n'a pas répondu) ; une trace `KYC_FILE_PURGED` par pièce.
7. **Motif de refus.** `rejection_reason` : 500 caractères au plus, visible du déposant ; il ne doit contenir **aucune donnée personnelle**. **Dette : liste codée de motifs (L1-xx).**
8. **Lecture.** `verification/` et la liste des pièces restent lisibles pour une organisation suspendue ou archivée ; les écritures sont refusées.
9. **Prérequis de production et recette.** Limite de taille du corps de requête côté Nginx (alignée sur `KYC_MAX_FILE_MB`) ; limite par IP sur le dépôt de pièces à prévoir en plus du débit par compte ; test de concurrence MySQL (dépôt/décision simultanés sous `select_for_update`) au registre de recette, SQLite sérialisant les écrivains.

## 19. Amendement 2 (10/10/2026) : API des organisations (T8), verrous, minimisation et prérequis de production

- **Statut :** proposé, même validation que l'ADR. En cas de divergence, cette section prévaut pour les points listés.

### 19.1 Décisions du chef de projet appliquées en T8

1. **Codes de claim alignés sur le contrat figé (§9.2)** : `RCCM_VERIFIED`, `NATIONAL_ID_VERIFIED`, `REPRESENTATIVE_VERIFIED`, `NGO_DECREE_VERIFIED` (table `CLAIMS` de `identity/verification.py`, filtre `?claim=`). Libellés français inchangés.
2. **Verrous d'identité (A13 étendu).** Le renommage est refusé (409 `name_locked_by_verification`) tant qu'une pièce de l'organisation est `VALIDE` **ou `EN_ATTENTE`** ; le NIF est refusé (409 `nif_locked_by_verification`) dès qu'une pièce est `VALIDE`. Un nom ou un NIF inchangé après normalisation n'est pas un changement. Une pièce `REFUSE` ne verrouille rien. Le personnel passe par l'administration.
3. **Minimisation du NIF (règle 10).** `OrganizationInternal.nif` n'est renseigné que pour les rôles ayant `org.edit_profile` (propriétaire, administrateur) ; pour un éditeur ou un analyste la clé existe et vaut `null`. Il n'est jamais dans la liste publique.
4. **Logo.** Validé par décodage réel (taille, pixels, ré-encodage) avant toute écriture ; une image tronquée ou corrompue est un 400 `invalid_logo`, jamais une erreur serveur, et ne laisse aucun fichier.
5. **Villes.** `PATCH {"city_id": null}` retire aussi la commune (cohérence). Une commune d'une autre ville reste refusée (`unknown_commune`).
6. **Noms d'organisation et de prestataire.** Un nom mêlant latin, cyrillique et grec est refusé (`invalid_name`) pour limiter les homoglyphes (« Rawbаnk »).
7. **Liste publique.** Throttle par IP `org_list` (600/h) en plus des défauts anonyme/utilisateur ; création : `org_create` (5/jour) ; écritures : `org_write` (30/h). `search` est borné à 100 caractères (400 `search_too_long`).
8. **Événement ajouté** `identity.organization_updated` (noms de champs seulement, sans abonné) ; codes ajoutés : `org_type_immutable`, `invalid_claim`, `invalid_filter`, `search_too_long`, `nif_locked_by_verification`.
9. **Forme de `required`** dans `OrganizationInternal.verification` : `{document_type, label, state}` avec `state` = `VALIDE` si le claim du type est prouvé, sinon statut de la pièce la plus récente, `NONE` si rien n'est déposé. L'endpoint `organizations/<id>/verification/` (T4) garde son contrat propre (`requirements`, `MANQUANTE`).

### 19.2 Dettes et prérequis de production

- **Prérequis de production (DoD) : cache partagé obligatoire.** Les throttles (`org_*`, `provider_write`, OTP, etc.) s'appuient sur le cache Django, aujourd'hui `LocMemCache` par processus : sous plusieurs processus Daphne, les plafonds ne sont pas globaux. Un cache partagé (autre que LocMem, sans Redis imposé par les choix actuels : base ou fichier à évaluer) est requis avant la mise en production.
- **Collision de noms avec une organisation vérifiée** (usurpation) et **signalement d'usurpation à la modération** : non codés ; dette pour la modération et L1-01 (avec la liste de noms réservés, §17.3).
- **`SellerSummary.user_type`** (et `business_profile`) : retirés en T9 avec `BusinessProfile` et `User.user_type`.
- **6 requêtes pour la liste publique** (compte, page, catégories, plus trois requêtes de vérification : organisations, exigences, pièces validées) : valeur volontaire, indépendante du nombre d'organisations ; ne pas « optimiser » sans test de non-régression.
- **Imports et code morts** (sérialiseurs, vues et tests liés à `BusinessProfile`/`user_type`) : à contrôler en T9 (`grep -rn "user_type\|BusinessProfile\|business_profile" backend/apps`).
- **`scripts/recette_contrat_http.py`** : section organisations et inscription réécrites en T8 (non exécutée en CI) ; les routes KYC historiques y utilisent un `BusinessProfile` créé en base jusqu'à T9.

### 19.3 T5a (L0-09e) : offres et compteurs par contexte, écarts et dettes

1. **Pas d'oracle d'existence (écart volontaire à 6.4).** Sur une offre existante, un acteur étranger au contexte propriétaire reçoit **404 uniforme** quand l'offre n'est pas publique (pause, masquée, vendue, expirée, corbeille, vendeur non public) ; `DENY_RELATION` (403) n'est renvoyé que pour une offre publique, déjà visible de tous. Un membre au rôle insuffisant (ex. analyste) reçoit toujours `DENY_PERMISSION`. Même règle pour `stats/post/<id>/` (`marketplace.services.authorize_offer`).
2. **Journal.** Toute écriture sur une offre est tracée avec le contexte propriétaire : `OFFER_CREATED`, `OFFER_UPDATED` (noms de champs seulement), `OFFER_PAUSED`, `OFFER_RESUMED`, `OFFER_RENEWED`, `OFFER_SOLD`, `OFFER_TRASHED`, `OFFER_RESTORED`, `OFFER_IMAGES_ADDED`, `OFFER_IMAGE_DELETED`, `OFFER_DELETED` (aussi depuis l'admin). Aucune valeur personnelle dans `details`. Les photos passent par des services qui ré-autorisent sous transaction.
3. **Visibilité du vendeur synchrone.** `publish_event(..., deliver_now=True)` diffuse l'événement `identity.seller_context_status_changed` aux abonnés **dans la transaction de l'émetteur** (`set_account_active`, statut d'organisation, archivage de prestataire) : plus de fenêtre d'incohérence de `seller_is_public`, sans import de `marketplace` par `identity`. L'événement reste publié (reprise par le cron en cas d'échec d'un abonné) et la commande `sync_seller_visibility` reste le filet. L'admin `User` passe par `announce_account_status` quand `is_active` change. Reste hors de la transaction : une modification de `is_active` en base brute, rattrapée par la commande horaire (jusqu'à une heure).
4. **Organisation sans canal.** Tant que le contact d'équipe n'existe pas (T7), contact, échange et révélation d'une offre d'organisation renvoient `403 seller_contact_unavailable`, sans repli « écrire un message ».
5. **Effacement de compte (dette T9 / L1-xx).** Il n'existe pas de suppression de compte en V1. Quand elle sera livrée, prévoir la purge par contexte : offres, compteurs et avis des contextes `USER` et `PROVIDER` du compte (la cascade historique de `Offer.seller` ne les couvre plus après T9) ; les offres d'une organisation restent à l'organisation (`created_by` passe à nul). Jusqu'à T9, `create_offer` écrit encore `seller` pour le contexte personnel (cascade conservée).
6. **Passerelles T9.** Les `save()` de `Offer` et `DailyVisibilityCounter` posent le contexte `USER` quand seul `seller` est fourni (`TODO(T9)`) ; `seller_is_public` garde son défaut vrai, corrigé par la réconciliation. Retour arrière de `marketplace 0008` : impossible s'il existe des offres sans `seller`.
7. **Signalement d'une offre d'organisation (dette).** `get_report_authors` ne renvoie aucun auteur pour une offre d'organisation : un membre peut la signaler. Le correctif passe par `moderation` (contrôle `acts_for_context`), à faire avec T6.
8. **Contrat cassé pour le front.** L'objet `seller` des offres change (voir 9.6) et `seller_not_settable` rejette un corps contenant `seller`, `seller_context_*`, `created_by` ou `seller_is_public` : le front ne doit **pas** renvoyer l'objet `seller` lu d'une offre lors d'un `PATCH`. **Aucune livraison en production avant F2 et T9a** (fusion groupée de `integ/L0-09`).

### 19.4 T5b (L0-09e) : profil vendeur public, statistiques par contexte, colonnes de messagerie et de notifications

1. **Profil public.** `GET marketplace/sellers/<user|provider|organization>/<uuid>/` est livré selon 9.7 (clés exactes : `context_type, context_id, display_name, photo, description, org_type, verified_claims, verification_summary, member_since, seller_rating, active_offers_count`). La vue ne lit aucune authentification ni `X-Context`. Throttle `seller_profile` (600/h, par IP, connectés compris). `Cache-Control: public, max-age=60` seulement sans jeton ni `X-Context` (sinon le middleware d'API rend la réponse privée). Requêtes constantes, indépendantes du volume.
2. **404 uniforme (même corps)** pour : type inconnu, identifiant mal formé ou inexistant, compte désactivé ou sanctionné, profil archivé, organisation suspendue ou archivée, **et (règle 10) un contexte `USER` ou `PROVIDER` sans aucune offre active publique** : une personne ou un prestataire n'a une page publique que s'il publie. Une organisation `ACTIVE` reste publique (annuaire) même sans offre.
3. **Note.** `seller_rating` est la note du contexte seul (règle 4). Sous `min_reviews_to_display`, `average` est nul **et `count` vaut 0** (le nombre d'avis n'est pas public sous le seuil). Le tableau de bord du vendeur garde les chiffres exacts. Le classement organique ne lit aucune note (test de recalcul réel et test d'absence d'import de `reviews` dans `visibility`).
4. **Photo.** Le profil prestataire n'a pas de photo propre : `photo` vaut `null` pour `PROVIDER` dans le profil public **et** dans l'objet `seller` des offres (la photo personnelle du compte n'est plus exposée). **Dette :** photo propre du profil prestataire. **Question client LEG-PRV :** la photo personnelle d'un contexte `USER` reste publique (comme avant), provisoirement, à valider par le client. Les URL de média restent absolues (comme dans les offres) : une URL relative casserait le front, servi par une autre origine que l'API.
5. **Statistiques.** `stats/dashboard/` exposait déjà la note moyenne et le nombre d'avis du contexte actif ; `stats.view` est accordée aux quatre rôles (analyste compris) : verrouillé par tests.
6. **Colonnes (schéma seulement, aucun remplissage).** `messaging 0002_conversation_message_contexts` (`Conversation.seller_context_*`, index `conv_seller_ctx` ; `Message.sender_context_*`) et `notifications 0002_notification_context` (`Notification.context_*`, index `notif_user_ctx`), tout nul. **Norme unique : nul = personnel** (notification, message) et nul = ancienne conversation par participants ; T6 et T7 doivent traiter nul comme le contexte personnel. Aucun comportement ne change.
7. **Limite connue du cache public.** Pendant 60 s au plus, un profil mis en cache par un cache partagé peut rester servi après la suspension ou l'archivage du vendeur. Acceptée (donnée publique, durée courte).
8. **Prérequis de production.** `NUM_PROXIES=1` derrière Nginx et cache partagé pour les throttles (déjà en 19.2) ; le cache HTTP partagé doit respecter `Vary: Authorization, X-Context`. **Front (F2) :** afficher `description`, `display_name` et la bio comme du TEXTE (jamais `dangerouslySetInnerHTML`).

### 19.5 T6 (L0-09f1) : avis et notifications par contexte, écarts et dettes

1. **Réponse à un avis.** Autorisée par OBJET (`identity.authorize_on`, capacité `review.reply` du contexte vendeur de l'avis, en-tête `X-Context` ignoré), refaite sous `transaction.atomic()` dans `reply_to_review` et journalisée (`REVIEW_REPLIED`, contexte vendeur, aucune donnée personnelle). Codes : étranger, auteur de l'avis ou ancien membre : 403 `not_seller` (contrat ADR 0004 conservé) ; analyste : `DENY_PERMISSION` ; compte sanctionné ou organisation suspendue : `DENY_SECURITY` ; organisation ou prestataire archivé : `DENY_OBJECT_STATE`. `is_review_seller` (signalement « contact fictif ») passe aussi à `review.reply` : l'analyste ne signale plus.
2. **`is_post_owner` par lot.** `reviews.services.get_reply_contexts(user)` (via `identity.get_capable_contexts`) : 4 requêtes au plus par sérialisation, quel que soit le nombre d'avis (le N+1 de T2/T5a disparaît). Résultat identique à `can` (test).
3. **`reviews.review_posted` v3 et `marketplace.offer_expiring_soon` v2.** Plus de compte destinataire dans la charge utile : `seller_context_type/id` ; l'abonné résout les destinataires À LA LIVRAISON (`get_context_recipients`, capacités `review.reply` et `offer.edit`). L'événement d'expiration devient un événement PAR OFFRE (T5a publiait un événement par destinataire). Un contexte sans destinataire éligible (organisation avec seulement un analyste, propriétaires désactivés) ne produit aucune notification et l'événement est traité sans erreur. `reviews.review_replied` (v1, charge additive) porte le contexte vendeur à la place de `replier_id` : l'auteur de l'avis voit le nom de l'organisation ou du prestataire, jamais celui du membre. Le nom de l'auteur d'un avis dans la notification est son nom d'affichage (« Marie K. »).
4. **Contexte d'une notification.** `Notification.context_type/id` : nul = personnel ; le contexte `USER` est toujours stocké nul. `notifications.services.notify(..., context=(type, id))`. L'API expose `context: null | {type, id, name}` (`name` : nom actuel, nul si le contexte n'existe plus ; une à deux requêtes par page).
5. **Abonnés (sans donnée personnelle dans les charges utiles ni les textes).** `notify_membership_change` (personne concernée, jamais l'auteur de l'action ; le retrait est une notification PERSONNELLE), `purge_context_notifications` (révocation : supprime les notifications de ce compte pour cette organisation), `notify_organization_status` (suspension, archivage, réactivation : propriétaires et administrateurs hors auteur, quel que soit l'état de l'organisation via `identity.get_organization_recipients`), `notify_kyb_decision` (propriétaires et administrateurs ; ni motif ni décideur). Les drapeaux `no_subscriber` sont retirés du catalogue.
6. **Défense en profondeur à la lecture.** `notifications.services.visible_notifications` masque les notifications d'une organisation dont le compte n'est plus membre actif (la purge passe par l'outbox et peut être différée) ; une organisation suspendue ou archivée reste visible de ses membres. `mark_all_as_read`, `PATCH` et `DELETE` s'y limitent.
7. **Signalement d'une offre d'organisation (dette 19.3 n°7 soldée).** `marketplace.get_report_authors` renvoie pour toute offre l'ensemble des comptes qui agissent pour son contexte vendeur (`identity.get_context_member_accounts`, même définition qu'`acts_for_context`, par lot, équivalence testée case par case) ; `moderation.resolve_target_authors` accepte un UUID ou une collection. Un membre actif de l'organisation ne signale pas son offre ; un ancien membre ou un tiers le peut. `seller_owns_offer` (rattachement d'une sanction) reste inchangé : une offre d'organisation n'appartient jamais à un membre.
8. **Compte sanctionné.** `get_context_recipients` exclut les comptes désactivés ET sous sanction bloquante (`get_restricted_user_ids`). `visible_notifications` masque, pour un compte restreint, toutes les notifications de contexte (organisation, prestataire) et garde les personnelles (contexte nul) pour qu'il voie sa sanction ; tout réapparaît à la levée.
9. **Rôle et notifications.** Rétrogradation (`role_changed`) vers un rôle sans `review.reply` ou `offer.edit` : purge des notifications d'avis (COMMENT) et d'expiration (EXPIRATION) de l'organisation pour ce membre ; les autres restent. Retour d'un ancien membre (`reactivated`) : purge des notifications de l'organisation créées avant l'événement (lignes périmées), la notification de retour est conservée.
10. **Auto-signalement.** `get_context_member_accounts` couvre aussi une organisation suspendue (écart voulu avec `acts_for_context`) : la suspension n'autorise pas à signaler sa propre offre. `resolve_target_author` (auteur unique) ne répond que pour les avis, messages et comptes ; une offre, même d'organisation à un seul membre, n'a jamais d'auteur unique (`resolve_target_authors`).
11. **Dettes.** PROVIDER à titulaire unique : `get_context_recipients` et `get_context_member_accounts` supposent un seul compte par profil prestataire ; à revoir si un transfert de profil est introduit. Conservation des notifications d'organisation : aucune purge à date fixe (hors révocation, rétrogradation, retour) ; durée à décider avec le conseil juridique (dette LEG-PRV). Les notifications des abonnés de contact, d'échange et de messages restent à T7.

### 19.6 T7 (L0-09f2) : contact et messagerie par contexte vendeur, contrat et écarts

1. **`contact-settings/*` par contexte.** Mêmes chemins et mêmes corps qu'ADR 0005. L'en-tête `X-Context` désigne le contexte ; capacité `contact.manage_channels` pour **tous** les contextes (acquise au titulaire d'un compte ou d'un prestataire, propriétaire et administrateur seulement pour une organisation, y compris en lecture). Refus : `403 DENY_PERMISSION` (éditeur, analyste), `DENY_RELATION` (non-membre ou membre révoqué), `DENY_SECURITY` (compte restreint, organisation suspendue), `DENY_OBJECT_STATE` (archivée). Chaque réponse (GET, PUT numéro, POST vérification, PUT canal) gagne `"context": {"type", "id"}` et `"available_channels"`. `USER`/`PROVIDER` : mêmes lignes `ContactPoint`/`ContactConsent` du compte (inchangé), trois canaux. `ORGANIZATION` : lignes de l'organisation (`organization` renseigné, `user` nul), `available_channels = ["MESSAGE"]` tant que `org_phone_channels_enabled` est faux, les trois sinon (fonction unique `identity.services.get_available_channels`, partagée avec `get_context_allowed_channels`).
2. **Particularités d'une organisation.** (a) `PUT phone/` avec `use_login_phone: true` : `400 login_phone_not_allowed` (le numéro de connexion d'un membre ne devient jamais celui de l'organisation) ; `login_phone_masked` y vaut `null` et `can_use_login_phone` `false` (aucune donnée du membre dans la réponse). (b) Régler un canal absent de `available_channels` (CALL/WHATSAPP, interrupteur fermé) : `400` `{"channel": ["..."], "detail": "...", "code": "channel_not_available"}` ; le retrait d'un consentement reste toujours permis. (c) `PUT channels/MESSAGE/` `enabled: false` : `400 message_channel_required` (MESSAGE reste toujours proposé, ADR 11.2) ; `enabled: true` est un no-op. (d) `granted_by` conserve le compte qui a consenti ; changer le numéro révoque CALL et WHATSAPP (motif `phone_changed`) ; vérification du numéro par OTP comme pour un compte (mêmes limites de débit ; l'anti-SMS arbitraire s'applique au compte acteur). (e) Audit avec contexte, cible = l'organisation, sans numéro ni nom : `CONTACT_CHANNEL_CHANGED` (consentement donné, retiré, retiré automatiquement), `CONTACT_PHONE_CHANGED`, `CONTACT_PHONE_VERIFIED`. Les écritures revérifient la capacité sous la transaction (`authorize_on`) et verrouillent l'organisation.
3. **Canaux effectifs (`allowed_channels` des offres).** `get_context_allowed_channels` : organisation = `MESSAGE` si elle est ACTIVE et a au moins un destinataire (propriétaire ou administrateur actif, compte actif) ; `CALL`/`WHATSAPP` s'ajoutent seulement si l'interrupteur est ouvert ET l'organisation a son propre `ContactPoint` vérifié ET un consentement actif à la version courante du texte dont les 4 derniers chiffres correspondent au numéro actuel. Requêtes par lot, indépendantes du nombre de contextes. `seller_contact_unavailable` (403) ne reste que pour un contexte sans canal ni destinataire (organisation sans propriétaire ni administrateur actif, prestataire archivé). Une organisation « sans consentement » renvoie désormais `MESSAGE` (et non plus `[]`) et le refus d'une révélation `CALL`/`WHATSAPP` est `403 channel_not_allowed` (écart voulu avec 19.3.4).
4. **Révélation.** `get_context_contact_endpoint(type, id, canal)` : organisation = numéro de CONTACT de l'organisation, jamais le téléphone d'un membre ; quotas, anti-doublon, trace du refus (`contact.reveal_refused`), audit (`contact.number_revealed` sans numéro) inchangés ; notification « numéro demandé » aux membres ayant `contact.view_requesters` (propriétaire, administrateur, éditeur).
5. **Événements en version 2.** `marketplace.contact_recorded`, `contact_revealed`, `exchange_proposed` : `seller_id` remplacé par `seller_context_type` + `seller_context_id` ; charge utile = `contact_event_id`/`proposal_id`, `offer_id`, `offer_title`, `seller_context_type`, `seller_context_id`, `sender_id`, `channel` ; aucun compte de membre, aucun numéro. Les abonnés (`messaging.open_contact_conversation`, `messaging.open_exchange_conversation`, `notifications.notify_contact`, `notify_contact_revealed`, `notify_exchange`) acceptent la version 2 et, par tolérance pour les événements déjà en file, la version 1 (`seller_id` lu comme le contexte `USER` ; un type de contexte inconnu lève `PermanentEventError`), et résolvent les destinataires **à la livraison** (`get_context_recipients` : `message.reply` pour contact et échange, `contact.view_requesters` pour la révélation) : un membre révoqué entre la publication et la livraison n'est pas notifié. Les notifications d'organisation portent `context_type/context_id = ORGANIZATION` (rattachement pour la purge à la révocation, T6). `notifications.services.notify` gagne le paramètre facultatif `context=(type, id)`. La preuve de remise `ContactEvent.delivered_at` (événement `messaging.contact_message_delivered`) est conservée ; un prestataire archivé entre-temps n'ouvre pas de conversation (pas de remise).
6. **Messagerie.** `open_conversation_with_message` pose `Conversation.seller_context_*` ; organisation : l'acheteur est le seul participant (aucun membre copié), conversation unique par (offre, organisation, acheteur). Accès **par objet** (en-tête ignoré) pour lire, détailler et écrire : participant, ou membre actif d'une organisation ACTIVE avec `message.reply` (propriétaire, administrateur), compte actif et sans sanction bloquante, relu en base à chaque requête (révocation immédiate, historique conservé). Il n'existe pas de capacité de lecture seule : **lire exige `message.reply`** (plus strict que `org.view_internal`), pour qu'un éditeur ou un analyste ne lise pas les messages d'un acheteur ; L2-09 affinera. `GET conversations/` : sans en-tête, boîte personnelle (participants, comportement historique, sans garde de compte) ; avec `X-Context: ORGANIZATION:<id>`, conversations de cette organisation (capacité `message.reply`, sinon 403 `DENY_PERMISSION`/`DENY_RELATION`). `POST messages/` : un participant écrit à titre personnel (`sender_context` nul) ; un membre habilité non participant répond « en tant que » l'organisation (`sender_context_type/id` = organisation), accès revérifié sous la transaction (`ConversationAccessDenied` -> `400 {"conversation": ["Conversation introuvable."]}`, uniforme : aucun oracle d'existence). Les anciennes conversations (contexte nul) restent par participants.
7. **Contrat JSON des messages et conversations.** `Message` : ajout `sender_context: null | {type, id}` ; pour un message du côté organisation, `sender` = identifiant de l'organisation (jamais celui du compte du membre) et `sender_name` = nom de l'organisation ; `is_me` = vrai pour tout membre habilité de l'organisation expéditrice. `Conversation` : ajout `seller_context: null | {type, id}` ; `other_participant` d'une conversation d'organisation vue par l'acheteur = `{id: <organisation>, full_name: <nom de l'organisation>, photo: <logo>}` ; `last_message.sender_id` = identifiant de l'organisation pour un message du côté organisation. Notifications : l'acheteur lit « Nouveau message de <nom de l'organisation> ».
8. **Garde-fou des routes.** Retirées de `LEGACY_WRITE_ROUTES` : `contact-settings/phone/`, `phone/verify/`, `channels/<channel>/`, `messages/` et `messages/<pk>/` (désormais gardées par `ActingContextMixin`).
9. **Dettes et points ouverts.** `Message.is_read` reste un booléen partagé du côté organisation ; boîte d'équipe, attribution et notifications temps réel : L2-09 (contrôle d'appartenance à chaque message et fermeture des connexions à la révocation). `Message.sender` conserve l'auteur en interne (traçabilité, modération) ; la suppression d'un compte supprime en cascade ses messages, y compris ceux écrits au nom d'une organisation (à traiter avec l'effacement de compte, 19.3.5). Le consentement d'une organisation n'est pas invalidé quand le membre qui l'a donné part : c'est l'accord de l'organisation (`granted_by` sert à la trace). `get_report_authors` (signalement d'une offre d'organisation) reste une dette (19.3.7). Interrupteur `org_phone_channels_enabled` toujours fermé par défaut (Q-CLI5).
10. **Corrections après relecture et audit de T7.** (a) L'équipe d'une organisation voit l'acheteur sous une forme abrégée (`requester_display_name`, « Marie K. »), sans photo : notifications de contact et d'échange, `other_participant`, `sender_name` des messages de l'acheteur ; l'acheteur voit son propre nom (règle 10). (b) `Message.sender` passe en `SET_NULL` (migration `messaging 0003`) : supprimer un compte ne supprime plus ses messages, y compris ceux écrits au nom d'une organisation ; un message sans expéditeur ni contexte s'affiche « Utilisateur supprimé ». (c) Un acheteur n'écrit pas à une organisation suspendue (`403 DENY_SECURITY`) ou archivée (`403 DENY_OBJECT_STATE`) : contact, échange, révélation et message (`identity.services.ensure_seller_context_accepts_contact`). (d) Fermer `org_phone_channels_enabled` (enregistrement de `IdentitySettings`) retire tous les consentements CALL et WHATSAPP des organisations (motif `moderation`, un audit `CONTACT_CHANNEL_CHANGED` par consentement) ; la réouverture ne les réactive pas. (e) `PUT channels/<canal>/ enabled:false` reste permis à un compte restreint, pour les contextes `USER`, `PROVIDER` et `ORGANIZATION` (ADR 0005 C4, comme `org.leave`) ; l'activation, la lecture et le numéro restent refusés (`DENY_SECURITY`). (f) Services du propriétaire de contact : verrou de l'organisation AVANT la revérification de la capacité. (g) `POST messages/` : réponse identique « Conversation introuvable. » pour une conversation inexistante, mal formée ou interdite.
11. **Dettes notées.** Les noms d'organisation restent présents dans les titres de notification (« Nouveau message de <organisation> ») : une organisation au nom usurpateur ou réservé s'afficherait telle quelle (noms réservés, 17.5.3). Lire une conversation exige `message.reply` (propriétaire, administrateur) : l'éditeur et l'analyste n'ont ni la boîte ni la lecture, car aucune capacité de lecture seule n'existe ; une capacité dédiée est à définir avec L2-09. `messaging.services.get_context_names` fait doublon avec la résolution de noms de T6 : à supprimer après la fusion de T6 et T7. `messaging.services.is_participant` (code mort) a été supprimée.

## 20. Amendement 3 (24/10/2026) : plan de T9 (L0-09h), conversion puis contraction

- **Statut :** proposé, même validation que l'ADR. Plan détaillé : `docs/specs/L0-09-T9-conversion-contraction.md` (inventaire, règle de conversion, migrations, précautions, sous-tâches, risques). En cas de divergence, cette section et ce document prévalent sur §10.2 (numéros de migrations périmés : `identity 0011` à `0014`, `marketplace 0010` à `0012`, `visibility 0006` à `0008`, `reviews 0006`, `moderation 0005`).
- **Décisions :**
  1. **Conversion par migration de données** (A11 et D1 confirmés), précédée d'une commande de pré-vol en lecture seule `check_legacy_conversion` (aucune donnée personnelle en sortie). Pas de commande de gestion exécutante : seule la migration lie la conversion à la contraction par le graphe de dépendances.
  2. **Deux phases livrées séparément** : phase A (conversion, aucun champ retiré, retour arrière réel des déplacements de contexte, `noop` documenté pour la création des organisations), phase B (contraction, gardes en tête de chaque migration, **après accord explicite de l'utilisateur**, retour arrière du schéma seulement).
  3. **Propriétaire désactivé ou sanctionné : organisation `SUSPENDED`** à la conversion (sinon les offres d'un compte banni redeviennent publiques) ; réactivation par le personnel (permission `suspend_organization` à ajouter à `setup_roles`, qui n'a jamais reçu les permissions d'organisation de §11.4).
  4. **Aucune réinitialisation des migrations maintenant** ; une seule, en fin de projet, avec le passage à MySQL (nouvel ADR), qui retirera aussi `LegacyAccountMapping` et `legacy_business_profile_id` (conservés jusqu'alors pour `migrated_from_business`).
  5. **Traçabilité** : `moderation 0005` écrit un `AuditLog` `ORG_CONVERTED` par conversion (règle 12), sans événement de domaine.
  6. **Purge par contexte** (dette §19.3.5) : événement `identity.seller_context_removed` et abonnés `marketplace`, `visibility`, `reviews` pour les contextes `USER` et `PROVIDER` d'un compte supprimé (jamais `ORGANIZATION`), tâche T9-3 après la contraction.
- **Corrections de l'état annoncé :** `SellerSummary.user_type` n'existe plus ; `Review.seller_context_*` existe déjà mais les avis des anciens comptes entreprise pointent encore le compte (à convertir) ; `marketplace 0009` et `visibility 0005` ont déjà rempli les contextes `USER` (la conversion ne fait que les déplacer vers l'organisation) ; les routes `kyc/documents/` (liste, dépôt, suppression) restent à retirer.
- **Livraison de T9-1 (phase A, 24/10/2026) : écarts et précisions.**
  1. Migrations livrées : `identity 0011_convert_business_profiles`, `marketplace 0010_convert_offer_contexts`, `visibility 0006_convert_counter_contexts`, `reviews 0006_convert_review_contexts`, `moderation 0005_audit_legacy_conversion`, plus la commande `check_legacy_conversion` (lecture seule, identifiants et comptages) et le module pur `identity/legacy_conversion.py` (nettoyage des noms, partagé par la migration et la commande ; à retirer avec les migrations de conversion).
  2. Le retour arrière des migrations de contexte s'appuie sur `LegacyAccountMapping` (et non sur le `Membership` propriétaire) : plus simple et équivalent, la table n'étant pas retirée par T9. `seller_is_public` du retour arrière est repris de `User.is_active` ; `sync_seller_visibility` affine ensuite (sanctions).
  3. **Propriétaire sanctionné (corrigé après audit, 09/11/2026).** Propriétaire désactivé OU sous sanction bloquante en cours (`SUSPENSION_TEMPORAIRE`/`BANNISSEMENT`, active, `ends_at` nul ou futur) : organisation `SUSPENDED`. `identity 0011` lit `moderation.Sanction` en lecture seule (`apps.get_model`, une requête avant la boucle ; exception A11 étendue à la dépendance `identity 0011` -> `moderation 0004`, autorisée explicitement dans `common/tests.py`). Une sanction échue, levée ou un avertissement laisse l'organisation `ACTIVE`. `seller_is_public` d'une offre convertie devient faux si l'organisation n'est pas active et n'est jamais réécrit à vrai (un faux préexistant est conservé). Le pré-vol applique la même règle (« sera SUSPENDED »).
  4. **Visibilité selon les propriétaires (audit M3).** `get_seller_context_public_flags` (ORGANIZATION) exige en plus au moins un `Membership` `OWNER` actif dont le compte est actif et sans sanction bloquante ; `announce_account_status` annonce aussi le changement aux organisations dont le compte est propriétaire actif (la visibilité des offres suit ; le statut stocké ne change pas, pas de suspension automatique ; la levée de sanction rétablit la visibilité). Dette : un changement d'appartenance (départ, révocation d'un propriétaire) n'annonce pas encore d'événement de visibilité ; la commande horaire `sync_seller_visibility` rattrape.
  5. **Routes retirées dès T9-1 (audit M2).** `GET/POST kyc/documents/` et `DELETE kyc/documents/<id>/` répondent 404 ; les routes de file de vérification, de décision et de téléchargement restent. Le sérialiseur de pièces ne sert plus qu'à la lecture.
  6. **Adresse (LEG-PRV).** L'ancien profil n'avait ni ville ni commune ; celles du compte (donnée personnelle) ne sont pas reprises : `NULL`, l'organisation les renseigne.
  7. **Dettes documentées (audit).** (a) Les pièces d'identité du gérant, rattachées à l'organisation, restent visibles (état, pas le fichier) des membres habilités ; le fichier n'est accessible qu'au personnel habilité. (b) Les anciennes validations deviennent des badges de l'organisation convertie : le personnel peut les revoir (aucune vérification n'est recopiée, elles découlent des pièces `VALIDE`). (c) `LegacyAccountMapping` et `legacy_business_profile_id` sont des données **pseudonymisées** (elles relient un compte à une organisation), pas anonymes : durée de conservation à fixer (LEG-PRV), retrait à la réinitialisation de fin de projet. (d) Le retour arrière de `marketplace 0010`, `visibility 0006`, `reviews 0006` est réservé à une copie de base (avertissement dans la docstring et au journal). (e) Les migrations de contexte travaillent par ligne de correspondance (N+1) : acceptable avant la production ; un test borne le coût de `identity 0011` (200 profils).
  8. Une pièce déjà rattachée à une organisation reste telle quelle ; `uploaded_by` est posé sur les pièces rattachées par la conversion. L'ancien lien `business_profile` des pièces n'est pas effacé avant la contraction.
  9. La commande lit les modèles `BusinessProfile` et `KycDocument.business_profile` : elle sera retirée ou réécrite par T9-2.
- **Livraison de T9-2 (phase B, contraction, 09/11/2026) : écarts et précisions.**
  1. Migrations livrées : `identity 0012_kycdocument_organization_required` (pièce.organisation NOT NULL, retrait de `business_profile`), `0013_remove_business_profile` (suppression de `BusinessProfileCategory` puis `BusinessProfile`), `0014_remove_user_user_type` ; `marketplace 0011_remove_offer_seller` (index `offer_seller_deleted` et FK) et `0012_offer_seller_context_required` ; `visibility 0007_remove_counter_seller` et `0008_counter_seller_context_required`. Chacune commence par une garde `RunPython` (comptages seulement dans le message, aucune donnée personnelle) qui échoue, transaction annulée, si une pièce n'a pas d'organisation, si un profil n'a pas de ligne de correspondance, si une offre ou un compteur a un contexte nul ou reste au contexte `USER` d'un compte présent dans `LegacyAccountMapping`. `identity 0014` n'a pas de garde (le type n'est plus lu nulle part ; la conversion se décidait sur l'existence du profil).
  2. Retour arrière : schéma seulement (colonnes et tables recréées vides ; `seller`, `business_profile` et `user_type` non restitués). Répétition sur une copie fabriquée (275 profils, 375 offres/compteurs/avis/pièces) : comptages identiques avant et après la contraction et après le retour arrière jusqu'à l'état converti, re-contraction possible.
  3. **Commande `check_legacy_conversion` retirée** (elle lisait les modèles supprimés) ; ses tests (6) sont remplacés par les tests des gardes (`identity/tests_contraction.py`, dont l'absence de donnée personnelle dans les messages d'erreur). `identity/legacy_conversion.py` est conservé (lu par `identity 0011`), ainsi que `LegacyAccountMapping`, `Organization.legacy_business_profile_id` et `migrated_from_business` jusqu'à la réinitialisation de fin de projet.
  4. Code retiré : `User.user_type`, `BusinessProfile*`, `KycDocument.business_profile` et `REQUIRED_TYPES`, `recompute_verification`, branches « ancien profil » de `decide_kyc_document` et `get_document_for_download`, passerelles `Offer.save()` et `DailyVisibilityCounter.save()`, écriture de `offer.seller`, `BusinessProfileAdmin`, `user_type` de `UserAdmin`. Le contrat JSON ne change pas.
  5. `setup_roles` : retrait de `identity.businessprofile` ; l'administrateur reçoit `identity.organization` (`view`, `suspend`, donc la réactivation des organisations converties en `SUSPENDED`), `identity.membership` (`view`), `identity.organizationdocumentrequirement` (`view`, `add`, `change`, `delete`) et `identity.identitysettings` (`view`, `change`) ; le modérateur n'a aucune permission sur les organisations (matrice à confirmer par l'analyste).
  6. `scripts/recette_contrat_http.py` : plus de création de profil en base ; la vérification passe par `organizations/<id>/kyc/documents/` (dépôt, remplacement, refus d'un non-membre, file du personnel, décision, synthèse), schéma de vendeur aligné sur la fiche de contexte ; contrôles « anciens champs ignorés » conservés. Non rejoué contre un serveur dans cette tâche.
  7. Dettes : une suppression de compte ne purge plus rien par cascade (offres, compteurs rattachés à un contexte `USER`) : livré par T9-3 (voir ci-dessous). Le retour arrière de `identity 0009` reste impossible dès qu'une pièce d'organisation existe (inchangé).
- **Corrections après relecture et audit de T9-2 (09/11/2026).**
  1. **Ordre des gardes.** `marketplace 0011` et `visibility 0007` dépendent de `identity 0012` ; `identity 0013` (suppression des profils) dépend de `marketplace 0012` et `visibility 0008` : les gardes des autres domaines s'exécutent tant que les profils existent. Exception de dépendance inter-domaine ajoutée à `common/tests.py` (lecture seule, migration vouée à disparaître). Les gardes des offres et compteurs ne dépendent plus de `LegacyAccountMapping` : elles recoupent aussi les créateurs et propriétaires des organisations à `legacy_business_profile_id` non nul (test « table de correspondance vidée à la main »). Limite assumée : un compte converti qui aurait publié une offre personnelle légitime après la conversion bloque la contraction (faux positif volontaire, à traiter à la main sur une copie).
  2. **Réactivation par le personnel** : refusée pour une organisation ARCHIVED (choix des membres) ; pour une SUSPENDED, refusée si l'acteur est ou a été membre, ou créateur (403 `interest_conflict`, trace `ORG_REACTIVATION_DENIED` avec l'acteur et l'ancien statut, écrite hors transaction pour survivre au refus). `ORG_REACTIVATED` garde l'acteur et l'ancien statut.
  3. **Décision KYC** : refusée (409) sur une pièce d'une organisation SUSPENDED ou ARCHIVED.
  4. Les modifications d'`IdentitySettings` (dont `kyb_file_retention_days`) sont journalisées (`SETTINGS_CHANGED`, anciennes et nouvelles valeurs) par `SingletonSettingsAdminMixin` ; test ajouté. `seller` / `seller_id` restent dans `SERVER_OWNED_FIELDS` / `PROTECTED_FIELDS` pour rejeter les anciens clients (commenté).
  5. **Dettes** : (a) la description d'un profil est tronquée à 2000 caractères à la conversion (donnée perdue, non comptée par les gardes) ; (b) MySQL ne rend pas le DDL transactionnel : les gardes et reconstructions de table sont à rejouer sur une copie MySQL avant la production ; (c) double validation de la durée de rétention KYB (modèle et service) à unifier ; (d) accès du modérateur à `identity.user` (e-mail, téléphone) à valider (LEG-PRV) ; (e) `tests_contraction.py` dure environ 105 s (chaque scénario reconstruit sa base) ; (f) `scripts/check_outbox_concurrency.py` adapté (`owner_kwargs`), amorçage vérifié, exécution complète à rejouer hors de cette session.
- **Livraison de T9-3 (purge par contexte à la suppression, 09/11/2026) : écarts et précisions.**
  1. **Émission.** Point unique : récepteurs `post_delete` de `User` et de `ProviderProfile` (`identity/signals.py`, branchés par `IdentityConfig.ready`), qui appellent `identity.services.announce_seller_context_removed`. Ils couvrent la suppression par l'admin (`delete_model`, `delete_queryset`), le shell, la cascade et une future suppression de compte, sans que chaque appelant y pense, dans la transaction du collecteur de Django. La suppression d'un compte annonce `USER` et, s'il existe, `PROVIDER` (cascade). `ORGANIZATION` est refusée par le service (`ValueError`) et par chaque abonné (`PermanentEventError`) : une organisation n'est jamais purgée par cet événement. L'archivage d'un profil prestataire (`archive_provider`) ne purge rien (données et avis conservés, offres masquées) : seule la suppression définitive purge.
  2. **Événement.** `identity.seller_context_removed` v1, charge `{context_type, context_id}` (la `reason` du plan est retirée : le type suffit). Il est diffusé dans la transaction (`deliver_now`), précédé d'un `identity.seller_context_status_changed` (raison `context_removed`, sans acteur) : les offres cessent d'être publiques même si la purge échoue, qui est reprise par le cron (livraison `pending`, backoff). Abonnés : `marketplace.purge_seller_context`, `visibility.purge_seller_context`, `reviews.purge_seller_context`, idempotents.
  3. **Marketplace.** Supprime les offres du contexte (corbeille comprise) par `delete_offers` : galerie, favoris, contacts et propositions d'échange en cascade, compteurs et vues uniques de ces offres. Les fichiers (photo principale et galerie) n'étaient jamais effacés du disque, même à la suppression définitive d'une offre : des récepteurs `post_delete` sur `Offer` et `OfferImage` les retirent après validation de la transaction (un retour arrière ne perd rien ; un échec disque est journalisé, jamais remonté). Effet de bord voulu : la suppression définitive par le vendeur et la purge de corbeille effacent aussi les fichiers.
  4. **Visibilité.** Efface les compteurs rattachés au contexte (ceux des offres supprimées partent déjà avec elles : l'audit `visibility` ne compte que les compteurs restants).
  5. **Avis : suppression, pas anonymisation.** Les avis REÇUS par le contexte sont supprimés, réponses comprises. Un avis note un contexte précis (règle 4, notes par contexte) : sans lui il n'a plus de sujet, et son texte (écrit par un tiers à propos d'une personne) n'a plus de finalité (règle 10) ; un avis anonymisé ne servirait aucune note affichée. Les avis rédigés par le compte partaient déjà avec lui (`Review.user`). Les avis d'une organisation ne sont jamais touchés.
  6. **Audit (règle 12).** Une entrée par abonné qui a effacé quelque chose (`SELLER_CONTEXT_PURGED_MARKETPLACE`, `_VISIBILITY`, `_REVIEWS`), acteur nul (système), contexte `(type, id)`, détails = comptages seulement. Un rejeu ne réécrit rien. Aucun nom, e-mail ni numéro dans la charge utile ni dans le journal ; l'entrée `USER_ADMIN_DELETED` de l'admin est inchangée.
  7. **Dettes.** (a) Messagerie : un compte supprimé disparaît des participants et ses messages passent à `sender` nul selon le modèle ; une conversation dont tous les participants ont disparu reste (messages, `offer_id`, contexte vendeur) : purge à traiter avec L2-09 et l'effacement de compte (19.3.5). (b) Signalements (`moderation.Report`) et recours qui désignent une offre ou un avis purgé gardent leur identifiant et leurs motifs ; durée de conservation à fixer (LEG-PRV). (c) `DeletedReviewMark` et `ReviewDailyCount` restent liés à l'auteur (partent avec le compte supprimé). (d) Les notifications du compte partent par la clé étrangère `Notification.user` ; celles reçues par d'autres comptes au sujet d'une offre purgée gardent leur texte (titre d'offre). (e) Pas de « supprimer mon compte » exposé en V1 : le chemin est l'admin (L1).
- **Corrections après relecture et audit de T9-3 (09/11/2026).**
  1. **Preuves : la suppression est refusée.** `assert_account_removable` (point unique, appelé par `UserAdmin` et par un récepteur `pre_delete` sur `User`) refuse, en plus du dernier propriétaire : 409 `blocking_sanction` (sanction bloquante en cours : on désactive le compte, l'historique de sanction ne disparaît pas) et 409 `open_grave_report` (signalement ouvert pour motif grave visant le compte, une de ses offres, un de ses avis reçus, ou ceux de son profil prestataire). `assert_provider_removable` applique la même règle au profil prestataire (récepteur `pre_delete`). Les lectures passent par `moderation.has_open_grave_report` (par lot, sous-requêtes) et par `marketplace` / `reviews` (`has_open_grave_report_on_seller`) ; `identity` les importe localement (cycle d'import). Le récepteur rend la garde universelle (shell, cascade, future suppression de compte) : un refus annule toute la suppression. Refus de l'admin journalisé `USER_ADMIN_DELETE_REFUSED` (acteur, code stable, aucune donnée personnelle). La suppression redevient possible dès la clôture du signalement ou la levée de la sanction.
  2. **Dette ouverte, question au client (LEG-PRV).** `Sanction.user` est en CASCADE : une fois le compte supprimé, l'historique de ses sanctions disparaît ; une liste de blocage par identifiant haché des comptes bannis (pour empêcher le retour sous une autre identité) n'existe pas. À arbitrer avec le client.
  3. **Volume.** `delete_offers` travaille par lots de 500 (jamais une liste d'identifiants non bornée dans un `IN`) ; `purge_seller_context` compte par sous-requêtes. Testé avec 1100 offres portant chacune photo, favori, contact, échange, vue unique et compteur.
  4. **Vues uniques du compte.** La purge du contexte `USER` efface aussi les `OfferUniqueView` des clés `user:<id>` et `share:user:<id>` faites sur les offres d'autres vendeurs (audit `unique_views=`).
  5. **Défense en profondeur.** `marketplace.purge_seller_context` refuse (`PermanentEventError`) si le compte ou le profil existe encore (`identity.seller_context_exists`) ; un contexte inconnu reste un no-op.
  6. **Limites connues et à suivre.** (a) La purge est synchrone (`deliver_now`, dans la transaction de suppression) : acceptable aux volumes de V1, passer au différé (cron seul) si les volumes grossissent. (b) Un crash entre la validation et la suppression des fichiers laisse des fichiers orphelins : prévoir un nettoyage par cron. (c) Alerter sur les livraisons `dead` de `identity.seller_context_removed` (outbox). (d) Durée de conservation de `AuditLog.context_id` (identifiant d'un compte supprimé : pseudonyme) à fixer (LEG-PRV). (e) Conversations et messages conservés pour le correspondant (voir 7a ci-dessus).

## 21. Amendement 4 (09/11/2026) : organisations indisponibles dans `contexts/` (L0-09 B-SUSP)

Réf. : `docs/specs/L0-09-ecran-organisation-suspendue.md` (sections 3 et 10). Prévaut sur 9.1 en cas de divergence.

1. **Contrat.** `GET accounts/contexts/` ajoute `status` (`"ACTIVE"`, toujours, sur chaque élément de `results`) et une clé de premier niveau `unavailable`, TOUJOURS présente (`[]` par défaut). `unavailable` liste les organisations `SUSPENDED` ou `ARCHIVED` dont le compte est membre ACTIF ; chaque élément a exactement 9 clés : `type` (`ORGANIZATION`), `id`, `name`, `role`, `org_type`, `photo`, `capabilities` (toujours `["org.leave"]`, quel que soit le rôle), `migrated_from_business`, `status` (`SUSPENDED` ou `ARCHIVED`). Tri : nom insensible à la casse puis identifiant. Non paginé (borné par le plafond d'organisations). `results` reste réservé aux profils activables : « absent de `results` » signifie toujours « profil perdu ».
2. **Aucune fuite (règle 10).** Ni motif (`suspension_reason`), ni date, ni auteur, ni NIF, ni liste ou nom de membres. Test d'ensemble de clés exact et de non-fuite.
3. **Compte restreint.** `contexts/` n'applique aucune garde de compte : 200 avec `unavailable` rempli (testé).
4. **Coût.** Une requête de plus (jointure appartenance + organisation), sans N+1 : 3 requêtes au total (`assertNumQueries`). Implémentation : `acting.get_unavailable_organizations`, façade `identity.services`.
5. **`leave/`.** Inchangé et vérifié : `204` pour tout rôle sur une organisation suspendue ou archivée, y compris pour un compte restreint. Dernier propriétaire : organisation ARCHIVÉE, `204` (la fin de vie n'a plus besoin de propriétaire, tracé `MEMBERSHIP_REVOKED`) ; organisation SUSPENDED, `409 last_owner` (elle peut être réactivée et doit garder un propriétaire). `internal/` inchangé : `403 DENY_SECURITY` (suspendue), `403 DENY_OBJECT_STATE` (archivée).
6. **Notifications de statut (Q-SUSP4, décision du chef de projet).** `identity.seller_context_status_changed` notifie désormais toute l'équipe active (propriétaires, administrateurs, éditeurs, analystes ; destinataires = capacité `org.leave`, détenue par tous les rôles), hors auteur de l'action, avec le texte neutre inchangé (sans motif ni auteur). Le lien passe de `/dashboard` à `/organizations/<uuid>`.
7. **Dettes.** (a) Aucun événement ni notification pour une organisation créée `SUSPENDED` par la conversion T9 (Q-SUSP5, hors périmètre). (b) Pas de canal de support ni de motif exposé (Q-SUSP1, Q-SUSP2). (c) Les notifications KYB gardent `link='/dashboard'` (hors périmètre).
- **Corrections finales de T9-3 après seconde relecture et audit (09/11/2026).**
  1. **Auteur de preuves.** La garde `assert_account_removable` refuse aussi (409 `open_grave_report`) tant qu'un signalement grave ouvert vise un avis ÉCRIT par le compte (`Review.user` partirait en cascade) ou un message ENVOYÉ par lui (`reviews.has_open_grave_report_on_author`, `messaging.has_open_grave_report_on_sender`, sous-requêtes). L'appel `providerprofile` (inopérant : ce type de cible n'existe pas dans `TARGET_RESOLVERS`) est retiré ; un profil prestataire se contrôle par ses offres et avis reçus.
  2. **Organisation suspendue.** Le blocage `last_owner_account` couvre aussi les organisations SUSPENDED (une seule requête annotée, plus de N+1 ; test du nombre de requêtes). Une organisation ARCHIVED ne bloque pas. Le refus `last_owner` (départ ou changement de rôle du seul propriétaire) d'une organisation SUSPENDED porte un message qui explique l'issue : attendre la levée de la suspension ou contacter le support (le code reste `last_owner`).
  3. **Index.** `visibility 0009_unique_view_viewer_key_index` (additif) : index `visib_uview_viewer_key` sur `OfferUniqueView.viewer_key` (longueur 64 explicite, nom de 22 caractères : portable MySQL), qui sert à la purge des vues d'un compte.
  4. **Admin.** `delete_model` et `delete_queryset` passent par un point unique `_delete_one` : garde, puis trace `USER_ADMIN_DELETED` et suppression dans la même transaction (aucune trace d'une suppression qui échoue) ; un refus donne un message d'erreur, jamais un 500, et une trace `USER_ADMIN_DELETE_REFUSED`.
  5. **Nettoyage.** `CAP_ORG_LEAVE` est défini une seule fois (`capabilities.py`, exporté par `identity.services` pour `notifications`) ; `AvailableContext.status` n'a plus de valeur par défaut ; lignes de plus de 120 caractères reformatées dans `organizations.py`, `services.py`, `views.py` ; un seul import de `apps.moderation` dans `organizations.py`.
  6. **Limites et questions.** (a) **TOCTOU** : la garde ne verrouille rien ; un signalement ou une sanction créé entre le contrôle et la suppression n'est pas vu (le récepteur `pre_delete` réduit la fenêtre à l'intérieur de la transaction de suppression). Verrouillage à étudier si la suppression de compte est exposée aux utilisateurs (L1). (b) **Transaction de purge unique** : la suppression, le masquage et les trois purges partagent la transaction de l'émetteur (`deliver_now`) ; un abonné en échec est repris par le cron, mais une purge très volumineuse allonge la transaction. (c) **Livraison `dead`** : un `seller_context_removed` en échec définitif est visible dans l'admin de l'outbox (relance par action, journalisée) et `dispatch_outbox --stats` sort en erreur s'il existe des livraisons `dead` ; il n'y a PAS d'alerte automatique : dette (supervision à brancher en fin de projet). (d) **Questions au client (LEG-PRV)** : durée de conservation des sanctions, signalements et avis après suppression du compte ; identifiant pseudonymisé des auteurs signalés (liste de blocage des bannis) ; sort d'une organisation SUSPENDED sans propriétaire (aucune issue automatique : levée par le personnel ou archivage).
- **Recette T10 : décisions (09/11/2026).** (a) **L009-01** : l'annuaire `GET organizations/` applique la règle de visibilité des vendeurs (au moins un propriétaire actif, compte actif et sans sanction bloquante), exprimée en sous-requêtes (`moderation.blocking_sanctions_for`), sans requête par organisation. (b) **L009-02** : la création d'une organisation est idempotente pour une double soumission (même créateur, même nom à la casse près, même type, organisation ACTIVE, créée il y a moins de `DUPLICATE_SUBMISSION_WINDOW_SECONDS` = 10 s) : l'organisation existante est renvoyée (201, même corps), rien n'est recréé et le plafond n'est pas consommé ; constante nommée (aucun réglage existant dans `IdentitySettings`) ; des homonymes espacés restent permis (A12) ; limite : deux requêtes strictement simultanées peuvent encore passer ensemble, sans verrou. (c) **L009-04, dette hors périmètre** : un identifiant mal formé dans l'URL (UUID invalide) répond par une page 404 HTML et non par le JSON d'erreur des autres routes.
