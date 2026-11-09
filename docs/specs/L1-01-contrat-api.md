# L1-01 — Contrat d'API figé : équipe d'organisation, invitations, transfert de propriété, blocages de suppression

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
