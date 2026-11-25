# L1-01 — Contrat d'API figé : équipe d'organisation, invitations, transfert de propriété, blocages de suppression

- **Version 2 (25/11/2026) :** section 7 « Amendement ADR 0010 » (gouvernance : Administrateur principal, rôle `MEMBER`, périmètre, invitations v2 avec confirmation, nominations, anti-abus de création, état de gouvernance). **La section 7 prévaut sur les sections 0 à 6 en cas de contradiction.** Briefs B5 à B10, F1-bis, F2-bis, F4, F5, F6 : recopier les sections 0 à 7.
- **Date :** 09/11/2026 ; **auteur :** architecte-technique ; **ADR :** `docs/adr/0008-equipe-organisation-invitations.md` (à recopier avec ce contrat dans les briefs B1, B2b, B4, F1, F2, F3)
- **Périmètre :** L1-01b, c, d, e, f, h, k. Hors périmètre : revendication, secours, noms réservés (L1-01i, j, l).
- **Préfixe :** `ID = /api/v1/accounts/` (ADR 0007). Aucune route n'est créée sous un autre préfixe.

## 0. Conventions

- **Authentification :** JWT (`Authorization: Bearer`). Toutes les routes ci-dessous sont authentifiées (401 sinon).
- **En-tête `X-Context` : IGNORÉ** par toutes ces routes. L'organisation est désignée par le chemin ; l'autorisation se fait d'après le rôle réel du compte dans cette organisation. Chaque vue déclare `acting_context_exempt`.
- **Pagination** (listes `members/` et `invitations/`) : `?page=` et `?page_size=` (défaut 20, plafond 100, ADR 0007), enveloppe `{"count": n, "next": url|null, "previous": url|null, "results": [...]}`. Exception documentée : `me/account-deletion-blockers/` n'est pas paginée (bornée par `max_organizations_per_account`, 100 au plus, comme `contexts/`).
- **Format d'erreur :** erreur non liée à un champ : `{"detail": "<message en français>", "code": "<code>"}`. Erreur de champ : `{"<champ>": ["<message>"]}` (format DRF). Refus de contexte : 403 avec `code` parmi `DENY_RELATION`, `DENY_SECURITY`, `DENY_OBJECT_STATE`, `DENY_PERMISSION`. Dépassement de débit : 429 + `Retry-After`.
- **Ordre des contrôles d'une route d'organisation :** non-membre (`403 DENY_RELATION`, **aussi pour une organisation inexistante**) ; état de l'organisation (suspendue `DENY_SECURITY`, archivée `DENY_OBJECT_STATE`, sauf mention) ; état du compte (désactivé ou restreint : `DENY_SECURITY`) ; capacité (`DENY_PERMISSION`) ; règles métier (400, 404, 409).
- **Réponses** `Cache-Control: private, no-store`. Dates en ISO 8601 UTC. Identifiants en UUID.
- **Données personnelles :** aucune réponse ni aucun journal (audit, outbox, notification) ne contient de téléphone, d'e-mail, de nom complet, de jeton ni d'étiquette en dehors des réponses expressément listées. Les réponses d'API n'exposent aucun identifiant de compte d'un tiers (hors `membership_id`). **Décision du chef de projet (L1-01-B1) :** les identifiants internes de compte (UUID) sont autorisés dans l'audit et l'outbox, pour la traçabilité (règle 12) ; jamais de nom, de téléphone, d'e-mail ni de jeton.

### Objet `Member` (clés exactes, ni plus ni moins)

```json
{
  "membership_id": "uuid",
  "display_name": "Marie K.",
  "role": "OWNER | ADMIN | EDITOR | ANALYST",
  "joined_at": "2026-11-09T08:00:00Z",
  "is_self": false,
  "is_last_effective_owner": null
}
```

`display_name` = `public_display_name(full_name)`. `is_last_effective_owner` : `true` uniquement sur la ligne du seul propriétaire effectif de l'organisation ; `false` sur les autres lignes ; `null` partout si l'appelant n'a pas `org.manage_members` (analyste, éditeur). Jamais de téléphone, e-mail, nom complet, photo, identifiant de compte, historique, pièces.

### Objet `Invitation` (liste réservée à `org.manage_members`)

```json
{
  "invitation_id": "uuid",
  "role": "EDITOR | ANALYST",
  "status": "PENDING | ACCEPTED | DECLINED | REVOKED | EXPIRED",
  "label": "Jean, comptable",
  "created_at": "...", "expires_at": "...",
  "created_by_display_name": "Paul M.",
  "is_mine": true
}
```

`status` est **effectif** : une `PENDING` échue est présentée `EXPIRED`. `label` est vide dès que l'invitation n'est plus `PENDING`. Jamais le jeton ni son empreinte.

---

## 1. Équipe (B1, F1)

### 1.1 Lister les membres (L1-01b)

`GET ID organizations/<uuid:pk>/members/` — capacité `org.view_internal` (tous les rôles).

- `200` paginé de `Member`. Seulement `ACTIVE`. Ordre : propriétaires, administrateurs, éditeurs, analystes, puis `joined_at`, puis `membership_id`.
- `403 DENY_RELATION` (non-membre, ancien membre, organisation inexistante), `DENY_SECURITY` (organisation suspendue ou compte restreint), `DENY_OBJECT_STATE` (archivée).
- Nombre de requêtes SQL indépendant de la taille de la page (`assertNumQueries`).

### 1.2 Changer le rôle d'un membre (L1-01e, et promotion d'un second propriétaire, L1-01h)

`PATCH ID organizations/<uuid:pk>/members/<uuid:membership_id>/` — capacité `org.manage_roles`.

```json
{"role": "ADMIN", "confirm": true, "password": "..."}
```

- `role` obligatoire parmi `OWNER`, `ADMIN`, `EDITOR`, `ANALYST`. `confirm` et `password` **obligatoires seulement** si le nouveau rôle est `OWNER` **ou** si le rôle actuel de la cible est `OWNER` ; ignorés sinon. **Exception :** si le nouveau rôle est identique au rôle actuel, le cas est traité AVANT la ressaisie (200 sans mot de passe, sans quota `org_sensitive`, sans compteur d'échecs, sans trace ni événement), après les contrôles d'autorisation habituels.
- `200` + `Member` (même clés). Même rôle : `200` sans trace ni événement. Effet sur les capacités dès la requête suivante de la cible.
- Règles : un administrateur ne touche jamais un propriétaire et n'attribue jamais `OWNER` (`403 DENY_PERMISSION`) ; éditeur et analyste : `403 DENY_PERMISSION`.
- Erreurs : `400 {"role": [...]}` (rôle absent ou inconnu) ; `400 confirmation_required` ; `400 password_required` ; `403 reauthentication_failed` ; `404 member_not_found` (membre inexistant, révoqué ou d'une autre organisation) ; `400 user_unavailable` (compte de la cible inactif ou restreint, neutre) ; `409 last_owner` ; `409 last_effective_owner` (voir ADR 0008 §9) ; `429`.

### 1.3 Retirer un membre (L1-01f)

`DELETE ID organizations/<uuid:pk>/members/<uuid:membership_id>/` — capacité `org.manage_members`. Pas de corps.

- `204`. Appartenance `REVOKED` (`end_reason = removed`), effet immédiat : la requête suivante de la personne retirée, avec le même jeton d'accès, sous `X-Context: ORGANIZATION:<id>` donne `403 DENY_RELATION` ; son contexte personnel reste utilisable. Ses invitations en attente sont révoquées.
- Erreurs : `403 DENY_PERMISSION` (administrateur sur un propriétaire ; éditeur ; analyste) ; `400 use_leave` (soi-même : utiliser `POST organizations/<id>/leave/`, inchangé) ; `409 owner_must_be_demoted` (cible `OWNER` : la rétrograder d'abord par 1.2) ; `404 member_not_found` ; `409 last_owner` ; `409 last_effective_owner` ; `429`.

### 1.4 Transférer la propriété (L1-01h)

`POST ID organizations/<uuid:pk>/transfer-ownership/` — capacité `org.manage_roles`, acteur `OWNER` uniquement. Throttle `org_sensitive` (compté seulement pour ce POST et pour les PATCH de rôle portant `password` ou `role=OWNER` ; jamais pour DELETE).

```json
{"membership_id": "uuid", "my_new_role": "ADMIN", "confirm": true, "password": "..."}
```

- `my_new_role` facultatif parmi `ADMIN` (défaut), `EDITOR`, `ANALYST` (jamais `OWNER`). `confirm` doit valoir `true` et `password` est obligatoire.
- `200 {"new_owner": Member, "me": Member}`. Une seule transaction : la cible devient `OWNER`, l'acteur prend `my_new_role` ; deux `MEMBERSHIP_ROLE_CHANGED` au plus (un seul si la cible est déjà `OWNER` : transfert vers un co-propriétaire) et un `ORG_OWNERSHIP_TRANSFERRED` ; un seul événement de visibilité `owners_changed`. `is_last_effective_owner` des deux `Member` suit le rôle effectif de l'appelant après transfert (`null` s'il est devenu éditeur ou analyste). Toute erreur laisse l'état inchangé.
- Autorisé sur organisation archivée, refusé sur suspendue (`DENY_SECURITY`).
- Erreurs : `403 DENY_PERMISSION` (administrateur, éditeur, analyste) ; `400 confirmation_required` ; `400 password_required` ; `403 reauthentication_failed` ; `404 member_not_found` ; `400 invalid_transfer` (soi-même) ; `400 user_unavailable` ; `400 {"my_new_role": [...]}` ; `429`. Aucun paramètre de plan ou de paiement.

---

## 2. Invitations (B2b, F2)

### 2.1 Créer une invitation (L1-01c)

`POST ID organizations/<uuid:pk>/invitations/` — capacité `org.manage_members`. Throttles `invitation_create` (20/h par compte) et `invitation_create_org` (50/jour par organisation).

```json
{"role": "EDITOR", "label": "Jean, comptable"}
```

- `role` obligatoire, **`EDITOR` ou `ANALYST`**. `label` facultatif, 60 caractères au plus, espaces de bord retirés ; caractères de contrôle, séparateurs de ligne ou de paragraphe et marques bidirectionnelles ou BOM refusés (`400 {"label": [...]}`), ZWJ et ZWNJ permis.
- `201` :
```json
{"invitation_id": "uuid", "role": "EDITOR", "status": "PENDING", "label": "Jean, comptable",
 "created_at": "...", "expires_at": "...", "link_token": "<43 caractères A-Za-z0-9_->"}
```
  `link_token` n'est renvoyé que dans cette réponse, jamais relisible. Le front construit le lien de partage : `<origine du front>/organization-invitation#token=<link_token>`.
- Erreurs : `400 invitation_role_not_allowed` (`OWNER` ou `ADMIN`) ; `400 {"role": [...]}` (absent ou inconnu) ; `400 {"label": [...]}` (trop long ou non textuel) ; `403 DENY_*` (organisation suspendue, archivée, compte restreint, rôle sans capacité) ; `409 invitation_limit_reached` ; `429`.

### 2.2 Lister les invitations

`GET ID organizations/<uuid:pk>/invitations/?status=PENDING` — capacité `org.manage_members`.

- `status` facultatif parmi `PENDING` (défaut), `ACCEPTED`, `DECLINED`, `REVOKED`, `EXPIRED` ; autre valeur : `400 {"status": [...]}`. Les lignes closes sont conservées `invitation_history_days` jours.
- `200` paginé d'`Invitation`, du plus récent au plus ancien.

### 2.3 Révoquer une invitation

`DELETE ID organizations/<uuid:pk>/invitations/<uuid:invitation_id>/` — capacité `org.manage_members` (tout membre habilité peut révoquer toute invitation de l'organisation).

- `204`. Le lien devient inutilisable (`404 invitation_invalid` côté cible).
- Erreurs : `404 invitation_not_found` (inexistante ou d'une autre organisation) ; `409 invitation_not_pending` ; `403 DENY_*` ; `429`.

### 2.4 Aperçu d'une invitation (L1-01d)

`POST ID organization-invitations/preview/` — authentifié, aucune capacité. Le jeton voyage dans le **corps**, jamais dans l'URL.

```json
{"token": "<jeton>"}
```

- `200 {"organization_name": "...", "org_type": "ENTREPRISE", "role": "EDITOR", "expires_at": "...", "invited_by_display_name": "Paul M."}`. Aucune donnée de l'équipe. Sans effet de bord (n'écrit ni statut ni audit).
- `404 invitation_invalid` pour **tout** cas invalide (voir 2.7). `400 {"token": [...]}` si le champ est absent. `429`.

### 2.5 Accepter

`POST ID organization-invitations/accept/` — authentifié. Corps `{"token": "<jeton>"}`.

- `200 {"organization_id": "uuid", "organization_name": "...", "role": "EDITOR", "membership_id": "uuid"}`. L'appartenance `ACTIVE` est créée (ou l'ancienne ligne réactivée) dans la même transaction que l'audit et les événements. Le contexte de l'organisation apparaît dans `GET ID contexts/` à l'appel suivant.
- Erreurs : `404 invitation_invalid` (voir 2.7) ; `403 DENY_SECURITY` (compte restreint) ; `403 phone_verification_required` ; `409 organization_limit_reached` ; `409 already_member` ; `400 {"token": [...]}` ; `429`. Pour les trois erreurs propres à la cible, l'invitation **reste `PENDING`**.
- Deux acceptations simultanées du même jeton : une seule réussit, l'autre reçoit `404 invitation_invalid`.

### 2.6 Refuser

`POST ID organization-invitations/decline/` — authentifié. Corps `{"token": "<jeton>"}`.

- `204`. L'invitation passe à `DECLINED`, le jeton est inutilisable, l'inviteur est notifié sans nom.
- `404 invitation_invalid` (invitation non vivante, **y compris organisation suspendue ou archivée** : aucune écriture, audit ni événement) ; `400 {"token": [...]}` ; `429`.

### 2.7 Réponse uniforme `invitation_invalid`

```json
404 {"detail": "Cette invitation n'est pas valide.", "code": "invitation_invalid"}
```

Corps strictement identique pour : jeton de forme incorrecte, jeton inconnu, invitation expirée, révoquée, déjà acceptée ou refusée, organisation suspendue ou archivée, organisation absente, inviteur retiré, parti, rétrogradé sous l'autorité requise ou dont le compte est inactif ou restreint, rôle de l'invitation hors `INVITABLE_ROLES`. Throttles `invitation_redeem` (60/h par IP) et `invitation_redeem_user` (30/h par compte), plus un compteur d'échecs par compte (5 échecs puis délai croissant, 429) qui **ne compte que les jetons mal formés ou inconnus** (jamais une invitation connue mais morte ; un aperçu réussi n'efface pas le compteur). Le quota `invitation_create_org` (2.1) n'est compté qu'après autorisation réussie.

---

## 3. Blocages de suppression de compte (L1-01k, B4, F3)

`GET ID me/account-deletion-blockers/` — authentifié, aucune capacité, strictement le compte appelant.

```json
200 {
  "organizations": [
    {"organization_id": "uuid", "name": "Boutique Aza", "status": "ACTIVE | SUSPENDED",
     "other_members_count": 3, "suggested_action": "transfer_ownership | archive | wait_for_unsuspension"}
  ],
  "has_other_blocker": false
}
```

- `organizations` : organisations `ACTIVE` ou `SUSPENDED` dont le compte est le **seul** propriétaire actif (règle de `assert_account_removable`, source unique de décision). `suggested_action` : `wait_for_unsuspension` si `SUSPENDED` ; sinon `transfer_ownership` si `other_members_count > 0`, sinon `archive`. `other_members_count` : comptage seulement, jamais d'identité.
- `has_other_blocker` : vrai si une sanction bloquante ou un signalement grave ouvert empêche la suppression ; **jamais détaillé**.
- Liste vide et `false` : rien n'empêche (la suppression libre-service n'existe pas en V1). Sans cache : le blocage disparaît à l'appel suivant un transfert ou un archivage. Aucune écriture d'audit en lecture.

---

## 4. Tableau des codes d'erreur

| HTTP | `code` | Routes |
|---|---|---|
| 400 | `confirmation_required` | 1.2, 1.4 |
| 400 | `password_required` | 1.2, 1.4 |
| 400 | `use_leave` | 1.3 |
| 400 | `invalid_transfer` | 1.4 |
| 400 | `user_unavailable` | 1.2, 1.4 |
| 400 | `invitation_role_not_allowed` | 2.1 |
| 400 | erreur de champ DRF (`role`, `my_new_role`, `label`, `status`, `token`) | toutes |
| 403 | `DENY_RELATION`, `DENY_SECURITY`, `DENY_OBJECT_STATE`, `DENY_PERMISSION` | toutes les routes d'organisation |
| 403 | `reauthentication_failed` | 1.2, 1.4 |
| 403 | `phone_verification_required` | 2.5 |
| 404 | `member_not_found` | 1.2, 1.3, 1.4 |
| 404 | `invitation_not_found` | 2.3 |
| 404 | `invitation_invalid` (uniforme) | 2.4, 2.5, 2.6 |
| 409 | `last_owner` | 1.2, 1.3 |
| 409 | `last_effective_owner` | 1.2, 1.3 (et `leave/`) |
| 409 | `owner_must_be_demoted` | 1.3 |
| 409 | `invitation_limit_reached` | 2.1 |
| 409 | `invitation_not_pending` | 2.3 |
| 409 | `organization_limit_reached` | 2.5 |
| 409 | `already_member` | 2.5 |
| 429 | (throttle DRF) | toutes |

Changement de comportement existant : `POST organizations/<id>/leave/` peut maintenant répondre `409 last_effective_owner` en plus de `last_owner` (ADR 0008 §9).

## 5. Ce qui est exposé à qui

| Donnée | Membre (tout rôle) | Propriétaire, administrateur | Cible d'une invitation | Public |
|---|---|---|---|---|
| Liste des membres (`display_name` abrégé, rôle, `joined_at`) | oui | oui | non | non |
| `is_last_effective_owner` | `null` | oui | non | non |
| Liste des invitations, `label`, `created_by_display_name` | non | oui | non | non |
| Jeton | non | une seule fois, à la création | l'a reçu de l'inviteur | non |
| Aperçu (nom et type de l'organisation, rôle, échéance, inviteur abrégé) | non | non | oui, avec le jeton | non |
| Audit, outbox, notifications | UUID et codes seulement ; notifications sans nom de personne ; jamais jeton ni étiquette | idem | idem | non |

## 6. Hors contrat

`POST organizations/<id>/members/` n'existe pas (405). Aucun endpoint n'appelle `add_member`. Aucune route de revendication, de secours, de noms réservés ni de suppression de compte. Aucun paramètre de plan, de prix ou de paiement (règle 2).

---

## 7. Amendement ADR 0010 (25/11/2026) — gouvernance des organisations

- **ADR :** `docs/adr/0010-gouvernance-organisations.md`. Conventions de la section 0 inchangées (JWT, `X-Context` ignoré, pagination, format d'erreur, ordre des contrôles, `Cache-Control: private, no-store`, UUID, dates ISO 8601 UTC, aucune donnée personnelle hors réponses listées).
- **Préfixe :** `ID = /api/v1/accounts/` ; personnel : même préfixe, routes `staff/...`.
- **Livraison par tâche :** 7.1 (B5, B6), 7.2 (B6, B9), 7.3 (B9), 7.4 (B7), 7.5 (B8), 7.6 (B8, B10). Chaque tâche front se branche sur la sous-section de sa tâche backend.

### 7.1 Rôles, libellés et périmètre (B5, B6)

- **Valeurs de `role`** partout (`Member`, `Invitation`, aperçu, `contexts/`, `internal/`) : `OWNER | ADMIN | EDITOR | ANALYST | MEMBER`. Les codes ne changent pas ; **libellés français imposés** (front, i18n) : `OWNER` = « Administrateur principal », `ADMIN` = « Administrateur », `EDITOR` = « Éditeur », `ANALYST` = « Analyste », `MEMBER` = « Membre ». Le mot « propriétaire » disparaît de toute interface et de tout message d'erreur (`detail`).
- **Capacités de `MEMBER`** : `["org.leave", "org.view_internal"]` (liste triée renvoyée par `contexts/` et `internal/`).
- **Objet `Scope`** (nouveau, clés exactes) : `{"type": "ORGANIZATION", "id": null}`. V1 : seule valeur produite et acceptée. Toute autre valeur en entrée : erreur de champ `400 {"scope": ["Ce périmètre n'est pas encore disponible."]}`.
- **Objet `Member`** (section 0) : **ajout** de `"scope": Scope`. Les six clés existantes ne changent pas. Ordre de la liste : Administrateurs principaux, administrateurs, éditeurs, analystes, **membres**, puis `joined_at`, puis `membership_id`.
- **Messages** des codes existants (`last_owner`, `last_effective_owner`, `owner_must_be_demoted`, `last_owner_account`) : codes inchangés, `detail` réécrit avec « administrateur principal ». Le front affiche ses propres textes par code (i18n).

### 7.2 Changer le rôle d'un membre (amende la section 1.2 ; B6, B9)

`PATCH ID organizations/<uuid:pk>/members/<uuid:membership_id>/` — capacité `org.manage_roles`.

```json
{"role": "ADMIN", "scope": {"type": "ORGANIZATION", "id": null}, "confirm": true, "password": "..."}
```

- `role` obligatoire parmi `ADMIN`, `EDITOR`, `ANALYST`, `MEMBER` (et `OWNER`, refusé ci-dessous). `scope` facultatif (défaut : organisation entière).
- `role = "OWNER"` (B9) : **`400 {"detail": "Pour nommer un administrateur principal, utilisez une nomination.", "code": "use_primary_admin_nomination"}`**, après les contrôles d'autorisation (un éditeur reçoit toujours `403 DENY_PERMISSION`) et avant toute ressaisie.
- Cible actuellement `OWNER` :
  - soi-même : `confirm` + `password` obligatoires (inchangé) ;
  - un autre Administrateur principal, organisation à vérification standard : `confirm` + `password` obligatoires (inchangé) ; tous les Administrateurs principaux restants sont notifiés ;
  - un autre Administrateur principal, organisation à vérification renforcée : **`409 {"code": "primary_admin_change_requires_verification"}`** (le front renvoie vers l'aide, L1-21).
- `200` + `Member` (avec `scope`). Autres erreurs : celles de la section 1.2, plus `400 {"scope": [...]}`.
- Personne ne délègue un périmètre plus large que le sien (`403 DENY_PERMISSION`) ; sans effet visible en V1 (tous les périmètres sont `ORGANIZATION`).

**Section 1.4 `POST organizations/<id>/transfer-ownership/` : SUPPRIMÉE** (B9). Remplacée par une nomination de genre `TRANSFER` (7.3). Après B9 la route n'est plus routée (`404`).

### 7.3 Nominations d'un Administrateur principal (B9)

**Objet `PrimaryAdminNomination`** (clés exactes) :

```json
{
  "nomination_id": "uuid",
  "kind": "PROMOTE | TRANSFER",
  "status": "PENDING_ACCEPTANCE | PENDING_REVIEW | COMPLETED | DECLINED | CANCELLED | REJECTED | EXPIRED | VOID",
  "target": {"membership_id": "uuid", "display_name": "Marie K."},
  "initiated_by_display_name": "Paul M.",
  "initiator_new_role": "ADMIN | EDITOR | ANALYST | MEMBER | null",
  "requires_review": false,
  "created_at": "...", "expires_at": "...", "decided_at": null,
  "is_target_me": false,
  "can_cancel": true
}
```

`status` est **effectif** : une nomination ouverte échue est présentée `EXPIRED`. `initiator_new_role` vaut `null` pour `PROMOTE`. `target.membership_id` peut désigner une appartenance terminée (nomination close) : le front n'en fait pas un lien. `can_cancel` : vrai si l'appelant est l'initiateur ou un Administrateur principal effectif et que la nomination est ouverte. Jamais de téléphone, d'e-mail, de nom complet ni d'identifiant de compte.

#### 7.3.1 Créer

`POST ID organizations/<uuid:pk>/primary-admin-nominations/` — appelant Administrateur principal effectif. Throttles `org_sensitive`, `nomination_create_org` (compté après autorisation).

```json
{"membership_id": "uuid", "kind": "PROMOTE", "my_new_role": null, "confirm": true, "password": "..."}
```

- `kind` obligatoire. `my_new_role` : obligatoire pour `TRANSFER` (parmi `ADMIN`, `EDITOR`, `ANALYST`, `MEMBER`), ignoré pour `PROMOTE`.
- `201` + `PrimaryAdminNomination` (`PENDING_ACCEPTANCE`). La cible et tous les Administrateurs principaux sont notifiés. **Aucun rôle ne change à ce stade.**
- Erreurs : `403 DENY_RELATION | DENY_SECURITY | DENY_OBJECT_STATE` (non-membre, organisation suspendue ou archivée, compte restreint) ; `403 DENY_PERMISSION` (pas Administrateur principal effectif) ; `400 confirmation_required` ; `400 password_required` ; `403 reauthentication_failed` ; `404 member_not_found` ; `400 invalid_nomination` (soi-même, ou cible déjà Administrateur principal) ; `400 user_unavailable` (neutre) ; `409 nomination_already_open` (nomination ouverte pour cette cible, ou `TRANSFER` déjà ouvert dans l'organisation) ; `400 {"kind": [...]}`, `400 {"my_new_role": [...]}` ; `429`.

#### 7.3.2 Lister

`GET ID organizations/<uuid:pk>/primary-admin-nominations/?status=open|closed` — capacité `org.view_internal`.

- `status` facultatif : `open` (défaut : `PENDING_ACCEPTANCE`, `PENDING_REVIEW` non échues) ou `closed` (les autres, conservées `invitation_history_days` jours) ; autre valeur : `400 {"status": [...]}`.
- Administrateur principal et administrateur : toutes les nominations de l'organisation. Autres rôles : **seulement** celles qui les visent (`is_target_me = true`). Paginé, du plus récent au plus ancien.

#### 7.3.3 Accepter, refuser (la cible seulement)

`POST ID organizations/<uuid:pk>/primary-admin-nominations/<uuid:nomination_id>/accept/` — corps `{"confirm": true}`.
`POST ID organizations/<uuid:pk>/primary-admin-nominations/<uuid:nomination_id>/decline/` — pas de corps.

- `accept` : `200` + `PrimaryAdminNomination` avec `status = COMPLETED` (la cible est Administrateur principal dès la requête suivante ; pour `TRANSFER`, l'initiateur a pris `initiator_new_role`) **ou** `status = PENDING_REVIEW` (organisation à vérification renforcée : aucun rôle ne change avant la décision de l'équipe Vérification).
- `decline` : `204`.
- Erreurs : `404 nomination_not_found` (inexistante, autre organisation, ou l'appelant n'est pas la cible : réponse identique) ; `409 nomination_not_pending` (décidée, annulée, échue, invalidée) ; `400 confirmation_required` (accept) ; `403 DENY_SECURITY` (compte restreint, organisation suspendue) ; `403 DENY_OBJECT_STATE` (archivée) ; `409 last_owner` / `409 last_effective_owner` (`TRANSFER` qui violerait un invariant : la nomination reste ouverte) ; `429`.

#### 7.3.4 Annuler

`POST ID organizations/<uuid:pk>/primary-admin-nominations/<uuid:nomination_id>/cancel/` — initiateur ou Administrateur principal effectif ; pas de corps ; `204`. Erreurs : `404 nomination_not_found` ; `409 nomination_not_pending` ; `403 DENY_PERMISSION` ; `429`.

#### 7.3.5 Revue par l'équipe Vérification (personnel ; aucun écran `frontend` en V1)

- `GET ID staff/primary-admin-nominations/?status=PENDING_REVIEW` — permission `identity.review_primaryadminnomination`. Paginé. Élément : `PrimaryAdminNomination` **plus** `"organization": {"id", "name", "org_type", "assurance_level"}`.
- `POST ID staff/primary-admin-nominations/<uuid:nomination_id>/decision/` — corps `{"decision": "APPROVE | REJECT", "reason_code": "authority_confirmed | authority_not_established | documents_required | conflict_detected | other"}`. `200` + objet. Erreurs : `403 DENY_PERMISSION` (permission absente **ou conflit d'intérêts** : réviseur membre actif de l'organisation, initiateur ou cible) ; `404 nomination_not_found` ; `409 nomination_not_pending` ; `400 {"decision": [...]}`, `400 {"reason_code": [...]}` ; `409 last_owner`, `409 last_effective_owner` ; `429`.

### 7.4 Invitations v2 (B7 ; amende la section 2)

**Objet `Invitation`** (section 0) — valeurs élargies et clés **ajoutées** :

```json
{
  "role": "ADMIN | EDITOR | ANALYST | MEMBER",
  "status": "PENDING | AWAITING_CONFIRMATION | ACCEPTED | DECLINED | REVOKED | REJECTED | EXPIRED",
  "scope": {"type": "ORGANIZATION", "id": null},
  "requires_confirmation": true,
  "accepted_at": null,
  "confirmation_expires_at": null,
  "accepted_by_display_name": null,
  "accepted_by_phone_hint": null,
  "can_confirm": false
}
```

- `requires_confirmation` : vrai pour `role = ADMIN`.
- `accepted_at`, `confirmation_expires_at` : renseignés à partir de `AWAITING_CONFIRMATION`.
- `accepted_by_display_name` (« Marie K. ») et `accepted_by_phone_hint` (`"••47"`) : **seulement** si `status = AWAITING_CONFIRMATION` **et** `can_confirm = true` ; `null` sinon.
- `can_confirm` : l'appelant est l'émetteur et peut toujours déléguer ce rôle, ou un Administrateur principal effectif, et l'invitation est `AWAITING_CONFIRMATION` non échue.
- `status` effectif : une `AWAITING_CONFIRMATION` dont `confirmation_expires_at` est passée est présentée `EXPIRED`.

#### 7.4.1 Créer (2.1 amendé)

Corps : `{"role": "ADMIN", "label": "...", "scope": {"type": "ORGANIZATION", "id": null}}` (`scope` facultatif). `role` parmi `ADMIN`, `EDITOR`, `ANALYST`, `MEMBER`, **dans la limite de ce que l'appelant peut déléguer** ; `OWNER` ou rôle non délégable : `400 invitation_role_not_allowed`. Réponse `201` : clés de la section 2.1 **plus** `scope` et `requires_confirmation`. Pas de ressaisie du mot de passe à la création.

#### 7.4.2 Lister (2.2 amendé)

`status` accepte en plus `AWAITING_CONFIRMATION` et `REJECTED`. Le front affiche les `AWAITING_CONFIRMATION` en tête de l'écran d'équipe (action requise).

#### 7.4.3 Révoquer (2.3)

Inchangé : seulement `PENDING`. Sur une `AWAITING_CONFIRMATION` : `409 invitation_not_pending` (utiliser `reject/`).

#### 7.4.4 Aperçu (2.4 amendé)

```json
200 {"organization_name": "...", "org_type": "ENTREPRISE", "role": "ADMIN", "expires_at": "...",
     "invited_by_display_name": "Paul M.",
     "scope": {"type": "ORGANIZATION", "id": null},
     "capabilities": ["contact.manage_channels", "contact.view_requesters", "message.reply", "..."],
     "requires_confirmation": true}
```

- `capabilities` : liste triée des codes du rôle proposé ; le front les traduit en « accès » lisibles (table i18n par code, regroupée par thème : organisation, équipe, offres, avis, contact, messages, statistiques, facturation).
- Si `requires_confirmation` : le front affiche **avant** le bouton Accepter : « Pour ce rôle, la personne qui vous a invité(e) devra confirmer votre identité. Elle verra votre nom abrégé et les deux derniers chiffres de votre numéro de téléphone. Aucun accès ne vous sera ouvert avant cette confirmation. »
- Erreurs inchangées (`404 invitation_invalid` uniforme).

#### 7.4.5 Accepter (2.5 amendé)

- Rôle sans confirmation : `200 {"status": "ACTIVE", "organization_id", "organization_name", "role", "membership_id"}` (clé `status` **ajoutée**, toujours `ACTIVE`).
- Rôle `ADMIN` : **`202`** `{"status": "AWAITING_CONFIRMATION", "invitation_id": "uuid", "organization_name": "...", "role": "ADMIN", "confirmation_expires_at": "..."}`. Ni `organization_id` ni `membership_id` ; l'organisation **n'apparaît pas** dans `contexts/`.
- Erreurs : celles de la section 2.5, avec **`409 organization_limit_reached` remplacé par `409 account_review_required`** (7.5), plus `409 already_awaiting_confirmation` (la personne attend déjà une confirmation pour cette organisation ; l'invitation reste `PENDING`).

#### 7.4.6 Confirmer, rejeter (émetteur habilité ou Administrateur principal effectif)

`POST ID organizations/<uuid:pk>/invitations/<uuid:invitation_id>/confirm/` — corps `{"confirm": true, "password": "..."}`. Throttle `org_sensitive`.

- `200` + `Member` de la personne entrée (appartenance `ACTIVE` créée au rôle de l'invitation, avec `scope`). La personne est notifiée ; son contexte apparaît dans `contexts/` à l'appel suivant.
- Erreurs : `403 DENY_*` (ordre de la section 0) ; `403 DENY_PERMISSION` (ni émetteur habilité, ni Administrateur principal effectif) ; `400 confirmation_required` ; `400 password_required` ; `403 reauthentication_failed` ; `404 invitation_not_found` ; `409 invitation_not_awaiting_confirmation` (autre statut ou échue) ; `400 user_unavailable` (la personne n'est plus éligible : compte inactif ou restreint, téléphone non vérifié, plafond technique ; réponse neutre, l'invitation reste `AWAITING_CONFIRMATION`) ; `409 already_member` ; `429`.

`POST ID organizations/<uuid:pk>/invitations/<uuid:invitation_id>/reject/` — pas de corps ; `204` ; mêmes acteurs. Erreurs : `404 invitation_not_found` ; `409 invitation_not_awaiting_confirmation` ; `403 DENY_*` ; `429`.

#### 7.4.7 Côté personne qui a accepté

- `GET ID organization-invitations/awaiting/` — authentifié ; paginé. Élément : `{"invitation_id", "organization_name", "org_type", "role", "scope", "accepted_at", "confirmation_expires_at", "status": "AWAITING_CONFIRMATION | EXPIRED"}` ; ses seules invitations `AWAITING_CONFIRMATION` (et `EXPIRED` depuis moins de 7 jours, pour information).
- `POST ID organization-invitations/<uuid:invitation_id>/withdraw/` — authentifié, la personne qui a accepté seulement ; `204` (`AWAITING_CONFIRMATION -> DECLINED`). `404 invitation_not_found` pour toute autre invitation (y compris celle d'autrui : réponse identique) ; `409 invitation_not_awaiting_confirmation` ; `429`.

### 7.5 Création d'organisation et limites (B8 ; amende ADR 0006 §9.2 et §17.2 B)

- `POST ID organizations/` : **`409 organization_limit_reached` n'existe plus.** Remplacé par `409 {"detail": "Votre compte doit être examiné par l'équipe Connecte+ avant de créer ou de rejoindre d'autres organisations.", "code": "account_review_required"}`. Aucun chiffre, nulle part. Même code à l'acceptation (7.4.5) ; à la confirmation (7.4.6), refus neutre `400 user_unavailable`.
- Nouveau throttle `org_create_burst` en plus de `org_create` : `429` + `Retry-After` (message générique de dépassement, sans valeur).
- Au-delà du seuil interne de revue : **`201` normal**. L'organisation est créée et utilisable par son équipe, mais absente de l'annuaire et des pages publiques ; `governance.under_review = true` (7.6).
- `GET ID organizations/limits/` : la clé **`max_organizations_per_account` est retirée**. Réponse exacte :

```json
200 {"max_categories_per_context": 5, "name_min_length": 2, "name_max_length": 255,
     "description_max_length": 2000, "invitation_ttl_days": 7, "max_pending_invitations": 20}
```

Le front ne garde aucune valeur par défaut de plafond d'organisations (`lib/organization-form.ts`).

### 7.6 État de gouvernance (B8, B10)

- `OrganizationInternal` (`GET organizations/<id>/internal/`, réponse de `POST organizations/`) : **ajout** de

```json
"governance": {"primary_admin_state": "OK | MISSING", "under_review": false}
```

  `primary_admin_state` (B10 ; vaut `OK` avant B10) : `MISSING` = aucun Administrateur principal actif (compte actif, sans sanction bloquante). `under_review` (B8) : création retenue en revue. Jamais `assurance_level`, jamais de seuil.
- `GET ID contexts/` : chaque élément `ORGANIZATION` de `results` gagne la même clé `governance`. Les éléments de `unavailable` gardent **exactement** leurs 9 clés (ADR 0006 §21). `results` reste non paginé ; sa borne est le plafond technique interne.
- Textes front (i18n) : `MISSING` : « Cette organisation n'a plus d'administrateur principal actif. Son administration doit être régularisée : contactez l'aide Connecte+. Elle n'apparaît plus publiquement en attendant. » ; `under_review` : « Votre organisation est en cours d'examen par l'équipe Connecte+. Elle n'apparaît pas encore publiquement. Vous pouvez déjà la compléter. »

### 7.7 Codes d'erreur ajoutés, modifiés ou supprimés

| HTTP | `code` | Routes | Statut |
|---|---|---|---|
| 400 | `use_primary_admin_nomination` | 7.2 | nouveau |
| 400 | `invalid_nomination` | 7.3.1 | nouveau |
| 400 | erreurs de champ `scope`, `kind`, `my_new_role`, `decision`, `reason_code` | 7.2 à 7.4 | nouveau |
| 400 | `invitation_role_not_allowed` | 7.4.1 | sens élargi (rôle non délégable par l'appelant) |
| 403 | `reauthentication_failed` | + 7.3.1, 7.4.6 | étendu |
| 404 | `nomination_not_found` | 7.3 | nouveau |
| 404 | `invitation_not_found` | + 7.4.6, 7.4.7 | étendu |
| 409 | `primary_admin_change_requires_verification` | 7.2 | nouveau |
| 409 | `nomination_already_open` | 7.3.1 | nouveau |
| 409 | `nomination_not_pending` | 7.3.3 à 7.3.5 | nouveau |
| 409 | `invitation_not_awaiting_confirmation` | 7.4.6, 7.4.7 | nouveau |
| 409 | `already_awaiting_confirmation` | 7.4.5 | nouveau |
| 409 | `account_review_required` | `POST organizations/`, 7.4.5 | **remplace** `organization_limit_reached` |
| 409 | `organization_limit_reached` | — | **supprimé** |
| — | route `POST organizations/<id>/transfer-ownership/` | — | **supprimée** (7.3, genre `TRANSFER`) |

### 7.8 Ce qui change pour le front livré

| Écran ou module | Changement | Tâche |
|---|---|---|
| Tous (`fr.ts`) | « Propriétaire » -> « Administrateur principal » ; rôle « Membre » ; textes des codes 7.7 | F1-bis (libellés), puis chaque tâche pour ses codes |
| Équipe (`OrganizationTeam`, `components/team/*`, `use-organization-team`) | menu de rôle sans `OWNER`, avec `MEMBER` ; `Member.scope` lu (affiché « Toute l'organisation ») ; dialogue de transfert **remplacé** par « Proposer comme administrateur principal » (genre `PROMOTE` ou `TRANSFER` + rôle de repli) ; liste des nominations ; carte « Vous êtes proposé(e) » pour la cible ; refus `primary_admin_change_requires_verification` | F5 |
| Invitations (`Invitations*`, `use-organization-invitations`, `lib/invitations.ts`) | rôles `ADMIN` et `MEMBER` (`ADMIN` proposé seulement aux Administrateurs principaux et administrateurs) ; ligne `AWAITING_CONFIRMATION` avec nom abrégé, indice, échéance, boutons Confirmer (mot de passe) et Rejeter | F2-bis |
| Page d'acceptation (`OrganizationInvitation`) | aperçu : périmètre, accès traduits, avertissement de confirmation ; réponse `202` : écran « en attente de confirmation » (aucune bascule de contexte) ; liste « mes adhésions en attente » avec retrait | F2-bis |
| Création (`OrganizationNew`, `organization-form.ts`, `api/types.ts`, `api-errors.ts`) | suppression de `max_organizations_per_account` ; `account_review_required` ; bannière `under_review` | F4 |
| Espace organisation | bannière `governance.primary_admin_state = MISSING` | F6 |
| Blocages de suppression (F3) | en pause (ADR 0012) ; `suggested_action = transfer_ownership` mènera à la nomination | — |
