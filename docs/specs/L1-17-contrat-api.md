# L1-17, L1-19, L1-20 — Contrat d'API figé : cycle de vie, restrictions et changement de nom des organisations

- **Amendement A-L17 / D-L17 (25-26/11/2026) :** décisions du chef de projet C1, C2, C3, C5, C6, C8, QU-2 (`docs/specs/L1-17-cycle-de-vie-organisations.md` §7, §10.2) et QD-1, QD-2, QD-4, QD-5 (`docs/specs/L1-17-ecrans-cycle-de-vie.md` §17). Sections modifiées : 0, 0.1, 0.2, 1.1, 1.2, 2.1, 2.3 et 2.4 (nouvelles), 3.1, 3.3, 4.3, 5, 7, 8, 9.
- **Version 1 (25/11/2026) ; auteur :** architecte-technique ; **ADR :** `docs/adr/0011-cycle-de-vie-organisations.md` (à recopier avec ce contrat dans les briefs L1-17-B1 à B4, L1-19-B2, L1-20-B5, F-L17-1 à F-L17-4).
- **Amende :** `docs/specs/L1-01-contrat-api.md` §0 (ordre des contrôles), ADR 0006 §9.1, §9.2, §21 (`contexts/`, `OrganizationInternal`, `archive/`, `unavailable`). **En cas de contradiction, ce document prévaut** sur ces sections pour les points listés.
- **Préfixes :** `ID = /api/v1/accounts/`, `MK = /api/v1/marketplace/` (ADR 0007). Aucune route nouvelle sous un autre préfixe que `ID`.
- **Tâche qui livre chaque point :** indiquée entre crochets, ex. [B1].

## 0. Conventions

- Authentification JWT ; toutes les routes ci-dessous sont authentifiées (401 sinon). En-tête `X-Context` **ignoré** (organisation désignée par le chemin ; `acting_context_exempt`).
- Pagination : `?page=`, `?page_size=` (défaut 20, plafond 100), enveloppe `{"count", "next", "previous", "results"}`.
- Erreur non liée à un champ : `{"detail": "<français>", "code": "<code>"}` ; erreur de champ : `{"<champ>": ["<message>"]}` ; 429 + `Retry-After`. Dates ISO 8601 UTC ; identifiants UUID ; `Cache-Control: private, no-store`.
- **Ordre des contrôles d'une route d'organisation (remplace L1-01 §0) :**
  1. non-membre ou organisation inexistante ou `ERASED` : `403 DENY_RELATION` ;
  2. suspension totale (`FULL_SUSPENSION` active) : `403 DENY_SECURITY`, sauf capacités `org.leave`, `org.view_restrictions`, `org.archive` ;
  3. cycle de vie `CLOSING` : `403 DENY_OBJECT_STATE`, sauf `org.view_internal`, `org.leave`, `org.archive`, `org.view_restrictions`, `offer.view_internal`, `stats.view` ; `ARCHIVED` : `403 DENY_OBJECT_STATE`, sauf `org.leave`, `org.view_restrictions` ;
  4. compte désactivé ou restreint : `403 DENY_SECURITY` (sauf `org.leave`) ;
  5. capacité du rôle ou périmètre : `403 DENY_PERMISSION` ;
  6. **restriction ciblée** : `403 DENY_RESTRICTION` ;
  7. règles métier (400, 404, 409).
- **Nouveau code `DENY_RESTRICTION`** (403), famille des refus de contexte :

```json
403 {"detail": "Cette action est actuellement restreinte pour cette organisation.", "code": "DENY_RESTRICTION",
     "measure": "PUBLICATION_BLOCK"}
```

  `measure` est la seule clé additive ; jamais de catégorie, de motif ni de date. **`DENY_RESTRICTION` et `measure` sont réservés aux membres de l'organisation** qui détiennent la capacité refusée (sinon `DENY_PERMISSION`). **Un acheteur ou tout non-membre ne les reçoit jamais** (C2) : il reçoit le refus neutre existant `403 {"detail": "…", "code": "seller_contact_unavailable"}`, identique au cas « organisation sans canal de contact » (section 5). Le front n'affiche pas `detail` : clés i18n par `measure`.
- **Données personnelles :** aucune réponse ne contient de note interne, d'auteur d'une restriction ou d'une décision, d'origine (`source_*`), de nom de membre.

### 0.1 Valeurs

| Nom | Valeurs |
|---|---|
| `lifecycle_status` | `ACTIVE`, `DORMANT`, `CLOSING`, `ARCHIVED` (`ERASED` n'est jamais servi aux membres) |
| `measure` | `FULL_SUSPENSION`, `PUBLICATION_BLOCK`, `PUBLIC_VISIBILITY_HIDDEN`, `CONTACT_BLOCK`, `MESSAGING_BLOCK`, `REVIEW_REPLY_BLOCK`, `TEAM_CHANGES_BLOCK`, `PROFILE_EDIT_BLOCK` |
| `required_action.code` | `NONE`, `CONTACT_SUPPORT`, `SUBMIT_DOCUMENTS`, `REGULARIZE_GOVERNANCE`, `REMOVE_CONTENT`, `UPDATE_PROFILE`, `AWAIT_REVIEW` |
| `appeal.mode` | `NONE`, `SUPPORT_REQUEST` |
| `disclosure` | `STANDARD`, `LIMITED` |
| `lifecycle.origin` (C6) | `MEMBERS` (fermeture demandée ou annulée, activité confirmée), `CONNECTE_PLUS` (archivage ou restauration décidés par le personnel ; conversion de l'existant), `AUTOMATIC` (dormance, sortie de dormance constatée, archivage faute d'administrateur principal) |
| capacités ajoutées | `org.view_restrictions` (Administrateur principal, Administrateur) ; `org.request_name_change` (QD-5 : **mêmes rôles que `org.verification_submit`**, Administrateur principal et Administrateur ; jamais Éditeur, Analyste, Membre) ; `org.confirm_activity` (QD-2 : Administrateur principal, Administrateur ; bloquée par aucune mesure ciblée) ; `org.archive` = « Fermer l'organisation » (Administrateur principal) |

### 0.2 Objets communs

**`RestrictionSummary`** (tout membre ; lu sans requête supplémentaire) :

```json
{"suspended": false, "measures": ["PUBLICATION_BLOCK"]}
```

`measures` : mesures des restrictions **effectives**, sans doublon, ordre alphabétique ; contient `FULL_SUSPENSION` si et seulement si `suspended` est vrai.

**`Lifecycle`** :

```json
{"status": "ARCHIVED", "since": "2026-11-25T10:00:00Z", "closure_effective_at": null, "origin": "CONNECTE_PLUS"}
```

`closure_effective_at` : non nul seulement en `CLOSING`. `origin` (C6) : qui a provoqué la dernière transition (0.1) ; servi seulement aux détenteurs de `org.view_restrictions` (Administrateur principal, Administrateur), `null` pour les autres rôles ; jamais l'auteur, le motif codé détaillé ni la note interne. Texte front pour `ARCHIVED` + `CONNECTE_PLUS` : « Cette organisation a été archivée par décision de Connecte+. »

## 1. Lectures existantes amendées [B1]

### 1.1 `OrganizationInternal` (`GET ID organizations/<id>/internal/`, réponse des écritures qui le renvoient)

Ajouts (les autres clés sont inchangées, y compris `governance` de L1-01 §7.6) :

```json
{
  "status": "ACTIVE",
  "lifecycle": {"status": "ACTIVE", "since": "2026-11-01T08:00:00Z", "closure_effective_at": null, "origin": null},
  "restrictions": {"suspended": false, "measures": []},
  "restricted_capabilities": [],
  "name_locked": false
}
```

- `status` : **déprécié, dérivé**, retiré par L1-19-B2 après la fusion de F-L17-1 : `SUSPENDED` si `restrictions.suspended`, sinon `ARCHIVED` si `lifecycle.status` vaut `CLOSING` ou `ARCHIVED`, sinon `ACTIVE`. Le front ne doit plus le lire après F-L17-1.
- `restricted_capabilities` (QD-1, additif) : capacités que le rôle et le périmètre du demandeur donneraient mais que les **restrictions ciblées en cours** retirent (ex. `["offer.edit", "offer.publish"]` sous `PUBLICATION_BLOCK` pour un Éditeur) ; ordre alphabétique ; `[]` sans restriction ciblée. Ne contient jamais une capacité que le rôle n'a pas, ni les refus dus au cycle de vie ou à la suspension totale (ceux-ci se lisent dans `lifecycle` et `restrictions.suspended`). Visible de tout membre : elle se déduit des mesures, déjà visibles. Le front s'en sert pour expliquer, à l'endroit de l'action manquante, qu'elle est restreinte (et non interdite par le rôle).
- `name_locked` : vrai si `PATCH name` ou `legal_name` renverrait `409 name_locked_by_verification`.
- Lisible en `ACTIVE`, `DORMANT`, `CLOSING` (capacité `org.view_internal`). Suspendue : `403 DENY_SECURITY` ; archivée : `403 DENY_OBJECT_STATE` (inchangés).
- [B5] ajout de `"legal_name": ""` (chaîne pour `org.edit_profile`, `null` pour les autres rôles, comme `nif`) et `"name_change": {"open_request_id": null}` (`null` pour les rôles sans `org.request_name_change`).

### 1.2 `GET ID contexts/`

- **`results`** contient le personnel, le prestataire actif et les organisations **opérationnelles** dont le compte est membre actif : `lifecycle_status` `ACTIVE` ou `DORMANT` **et** non suspendues (une restriction ciblée ne retire pas l'organisation de `results`). Chaque élément `ORGANIZATION` gagne :

```json
{"lifecycle_status": "DORMANT", "restrictions": {"suspended": false, "measures": ["PUBLICATION_BLOCK"]},
 "restricted_capabilities": ["offer.edit", "offer.publish"]}
```

  `capabilities` = capacités **réellement exerçables** (rôle, périmètre, cycle de vie et mesures appliqués) : une capacité bloquée par une restriction ciblée n'y figure pas ; elle figure dans `restricted_capabilities` (QD-1, même règle qu'en 1.1). Invariant : `capabilities` et `restricted_capabilities` sont disjointes, et leur union est l'ensemble des capacités du rôle dans son périmètre. `status` reste `"ACTIVE"` sur tout élément de `results` (inchangé). Les éléments `USER` et `PROVIDER` ne changent pas.
- **`unavailable`** contient les organisations dont le compte est membre actif et qui sont `CLOSING`, `ARCHIVED` ou suspendues. Chaque élément a **exactement 12 clés** (`lifecycle_origin` ajoutée par l'amendement A-L17, C6 : même règle que `lifecycle.origin` en 0.2, `null` sans `org.view_restrictions`) :

```json
{
  "type": "ORGANIZATION", "id": "<uuid>", "name": "Atelier X", "role": "OWNER", "org_type": "ENTREPRISE",
  "photo": null, "migrated_from_business": false,
  "status": "SUSPENDED",
  "lifecycle_status": "ACTIVE",
  "restrictions": {"suspended": true, "measures": ["FULL_SUSPENSION"]},
  "lifecycle_origin": null,
  "capabilities": ["org.archive", "org.leave", "org.view_restrictions"]
}
```

  `status` : dérivé et déprécié comme en 1.1 (retiré par L1-19-B2 : 11 clés ensuite). **Pas de `restricted_capabilities` ni de `closure_effective_at` dans `unavailable` en V1** (QD-1, QD-4) : la date de fermeture se lit dans `internal/` (`lifecycle.closure_effective_at`), lisible en `CLOSING` grâce à `org.view_internal` (section 0, contrôle 3). Seule exception : une organisation à la fois `CLOSING` **et** suspendue répond `403 DENY_SECURITY` à `internal/` (le contrôle 2 passe avant) ; le front affiche alors un texte sans date (« La fermeture est en cours. »). `capabilities` n'est **plus** toujours `["org.leave"]` : c'est la liste exerçable selon 0 (ex. un analyste d'une organisation suspendue : `["org.leave"]` ; l'Administrateur principal d'une organisation en fermeture : `["offer.view_internal", "org.archive", "org.leave", "org.view_internal", "org.view_restrictions", "stats.view"]`). Toujours absents : catégorie, motif, dates de restriction, auteur, NIF, membres.
- Nombre de requêtes inchangé (3, `assertNumQueries`).

### 1.3 `GET ID organizations/` (annuaire public) et `GET MK sellers/organization/<id>/`

- Annuaire : seulement les organisations `ACTIVE` (pas `DORMANT`), sans `FULL_SUSPENSION` ni `PUBLIC_VISIBILITY_HIDDEN`, plus les conditions existantes (Administrateur principal effectif, revue de création levée). Clés de réponse inchangées.
- Profil vendeur public : `200` pour `ACTIVE` et `DORMANT` sans mesure de masquage ; `404` sinon (inchangé dans sa forme). Aucune clé de cycle de vie ni de restriction n'est publique.

## 2. Restrictions [B2]

### 2.1 `GET ID organizations/<id>/restrictions/`

- Capacité `org.view_restrictions` (Administrateur principal, Administrateur). Permise sous suspension, en `CLOSING`, en `ARCHIVED`. Autres rôles : `403 DENY_PERMISSION`. Compte restreint : `403 DENY_SECURITY`.
- Paramètre `?history=true` : inclut les restrictions levées ou expirées (défaut : effectives seulement). Toute autre valeur : `400 invalid_filter`.
- Tri : effectives d'abord, puis `since` décroissant, puis `id`. Paginé.

```json
200 {"count": 1, "next": null, "previous": null, "results": [
  {
    "id": "<uuid>",
    "status": "ACTIVE",
    "measure": "FULL_SUSPENSION",
    "scope": {"type": "ORGANIZATION", "id": null},
    "category": {"code": "verification_identity", "label": "Vérification et identité"},
    "explanation": "Texte de la catégorie, configuré en back-office.",
    "communicated_reason": "Les pièces fournies ne correspondent pas à la dénomination déclarée.",
    "disclosure": "STANDARD",
    "since": "2026-11-20T09:00:00Z",
    "ends_at": null,
    "required_action": {"code": "CONTACT_SUPPORT", "detail": null},
    "appeal": {"mode": "SUPPORT_REQUEST", "deadline": null},
    "lifted_at": null
  }
]}
```

- `status` : `ACTIVE`, `LIFTED`, `EXPIRED` (une restriction dont `ends_at` est passée est présentée `EXPIRED` même avant le cron).
- `required_action.code` est toujours **réalisable** sous la mesure (C1, 2.3) : jamais `SUBMIT_DOCUMENTS`, `REMOVE_CONTENT` ni `UPDATE_PROFILE` sous `FULL_SUSPENSION`, jamais `UPDATE_PROFILE` sous `PROFILE_EDIT_BLOCK`.
- `disclosure = LIMITED` : `communicated_reason` vaut `null` ; `category`, `explanation`, `required_action`, `appeal` restent servis.
- `category.label` et `explanation` viennent du back-office (configurables) ; le libellé de `measure` et de `required_action.code` est traduit par le front.
- **Test d'ensemble de clés exact.** Jamais : `internal_note`, `imposed_by`, `lifted_by`, `source_type`, `source_id`, `lift_reason`.

### 2.2 Refus d'une action par une restriction ciblée

Toutes les routes existantes protégées par une capacité listée en ADR 0011 §4.2 renvoient `403 DENY_RESTRICTION` (section 0) au lieu d'agir, après les contrôles 1 à 5. Exemples : `POST MK posts/` sous `PUBLICATION_BLOCK` ; réponse à un avis sous `REVIEW_REPLY_BLOCK` ; invitation, confirmation, nomination, changement de rôle, retrait de membre sous `TEAM_CHANGES_BLOCK` ; `PATCH organizations/<id>/` sous `PROFILE_EDIT_BLOCK`. Restent permis sous `PUBLICATION_BLOCK` : suppression, mise en corbeille et pause d'une offre.

### 2.3 Compatibilité mesure × action requise (C1, contrôle en service et dans le back-office)

| Action requise | Incompatible avec |
|---|---|
| `SUBMIT_DOCUMENTS` | `FULL_SUSPENSION` |
| `REMOVE_CONTENT` | `FULL_SUSPENSION` |
| `UPDATE_PROFILE` | `FULL_SUSPENSION`, `PROFILE_EDIT_BLOCK` |
| `NONE`, `CONTACT_SUPPORT`, `AWAIT_REVIEW`, `REGULARIZE_GOVERNANCE` | — |

La pose ou la modification d'une restriction (back-office) refuse une combinaison incompatible, y compris avec une autre restriction effective de la même organisation : erreur de champ `required_action`, code `required_action_incompatible`. Aucune route d'API membre n'est concernée.

### 2.4 Notifications de restriction (QU-2)

Pose, **modification** (texte communiqué, divulgation, action requise, recours, échéance), levée et expiration sont notifiées (ADR 0011 §7). Modification : Administrateur principal et Administrateur, texte neutre « La restriction appliquée à « {name} » a été mise à jour. Consultez le détail. », lien `/organizations/<id>/restrictions`. Aucune nouvelle route.

## 3. Cycle de vie [B3]

### 3.1 `POST ID organizations/<id>/closure/` — demander la fermeture

Remplace **`POST organizations/<id>/archive/`, supprimée** (404 après B3 ; aucun client externe).

- Administrateur principal effectif (`org.archive`), y compris sous suspension. Throttle `org_sensitive`.
- **Délai affiché avant la demande (C3) :** `GET ID organizations/limits/` gagne la clé additive `"closure_delay_days": 0` (entier, réglage `IdentitySettings.closure_delay_days` ; 0 = fermeture immédiate si aucune obligation). Route lisible quel que soit l'état de l'organisation, y compris sous suspension. Le dialogue en déduit « immédiatement » ou « au plus tôt dans N jours » ; la date réelle est `closure_effective_at` de la réponse.

```json
{"confirm": true, "password": "<mot de passe>", "reason_code": "activity_ended"}
```

`reason_code` : `activity_ended`, `duplicate`, `merged_into_other`, `no_longer_needed`, `other`.

```json
200 {"organization_id": "<uuid>", "lifecycle_status": "ARCHIVED", "closure_effective_at": null,
     "pending_obligations": []}
200 {"organization_id": "<uuid>", "lifecycle_status": "CLOSING", "closure_effective_at": "2026-12-02T10:00:00Z",
     "pending_obligations": ["payments_open"]}
```

`pending_obligations` : codes seulement (`payments_open`, `refunds_open`, `tickets_sold`, `subscriptions_active`, `provider_unavailable`) ; vide en V1 tant qu'aucun module n'est inscrit.

| Erreur | Cas |
|---|---|
| `400 {"confirm": [...]}` | `confirm` absent ou faux |
| `400 {"reason_code": [...]}` | code inconnu |
| `403 reauthentication_failed` | mauvais mot de passe (limiteur `org_reauth` partagé) |
| `403 DENY_RELATION`, `DENY_OBJECT_STATE` (archivée), `DENY_SECURITY` (compte), `DENY_PERMISSION` (non Administrateur principal ou non effectif) | section 0 |
| `409 closure_already_requested` | déjà `CLOSING` |

### 3.2 `DELETE ID organizations/<id>/closure/` — annuler

Administrateur principal effectif ; sans mot de passe ; throttle `org_write`.

```json
200 {"organization_id": "<uuid>", "lifecycle_status": "ACTIVE", "closure_effective_at": null, "pending_obligations": []}
```

Erreurs : `409 closure_not_pending` (pas en `CLOSING`) ; `403 DENY_OBJECT_STATE` (déjà archivée) ; section 0.

### 3.3 `POST ID organizations/<id>/resume/` — confirmer l'activité d'une organisation dormante

Capacité **`org.confirm_activity`** (QD-2 ; Administrateur principal, Administrateur), et non `org.edit_profile` : elle n'est bloquée par **aucune** restriction ciblée, en particulier pas par `PROFILE_EDIT_BLOCK` (sinon une organisation inactive au profil restreint ne pourrait plus se réactiver) ; elle reste refusée sous suspension totale (`DENY_SECURITY`), en `CLOSING` et en `ARCHIVED` (`DENY_OBJECT_STATE`). Corps `{"confirm": true}` ; throttle `org_write`. `200` : `OrganizationInternal` avec `lifecycle.status = "ACTIVE"`. Erreurs : `400 {"confirm": [...]}` ; `409 organization_not_dormant` ; section 0.

### 3.4 `POST ID organizations/<id>/leave/`

Inchangé : `204` en `CLOSING` et `ARCHIVED` aussi ; dernier Administrateur principal : `409 last_owner` sauf en `ARCHIVED` (inchangé).

## 4. Changement de nom [B5]

### 4.1 `PATCH ID organizations/<id>/` (amendé)

- Champ ajouté : `legal_name` (2 à 255 caractères après normalisation, ou chaîne vide ; mêmes règles et codes que `name` : `invalid_name`).
- Nom verrouillé (pièce `VALIDE` ou `EN_ATTENTE`) : `name` ou `legal_name` modifié -> `409 {"detail": "Le nom est verrouillé depuis la vérification. Faites une demande de modification du nom.", "code": "name_locked_by_verification"}` (code inchangé, message changé).

### 4.2 Objet `NameChangeRequest`

```json
{
  "id": "<uuid>",
  "status": "DOCUMENTS_REQUIRED",
  "change_type": "LEGAL_NAME_CHANGE",
  "current_display_name": "Atelier X",
  "current_legal_name": "Atelier X SARL",
  "proposed_display_name": "Atelier Y",
  "proposed_legal_name": "Atelier Y SARL",
  "reason_code": "legal_rename",
  "note": "",
  "documents": [{"id": "<uuid>", "document_type": "RCCM", "status": "EN_ATTENTE"}],
  "requested_at": "2026-11-25T10:00:00Z",
  "decided_at": null,
  "decision_reason": null,
  "is_mine": true
}
```

`status` : `DOCUMENTS_REQUIRED`, `PENDING_REVIEW`, `COMPLETED`, `REJECTED`, `CANCELLED`, `VOID`. `change_type` : `TYPO_CORRECTION`, `DISPLAY_NAME_CHANGE`, `LEGAL_NAME_CHANGE`. `reason_code` : `typo`, `rebranding`, `legal_rename`, `legal_form_change`, `other`. `decision_reason` : `approved`, `documents_insufficient`, `authority_not_established`, `new_entity_required`, `protected_name_conflict`, `other`. Jamais : identité du demandeur (seulement `is_mine`), du réviseur, URL de fichier.

### 4.3 Routes

| Méthode et chemin | Qui | Corps | Réponse | Erreurs propres |
|---|---|---|---|---|
| `GET ID organizations/<id>/name-change-requests/` | `org.request_name_change` | — | `200` liste paginée, plus récentes d'abord | — |
| `POST ID organizations/<id>/name-change-requests/` | `org.request_name_change` (Administrateur principal, Administrateur, QD-5 ; permis sous `PROFILE_EDIT_BLOCK`) ; throttle `org_sensitive` | `{"change_type", "proposed_display_name", "proposed_legal_name", "reason_code", "note", "confirm": true, "password"}` | `201` `NameChangeRequest` | `400` champs (`invalid_name`, `nothing_to_change` si aucun nom proposé ou identiques aux actuels, `confirm`) ; `403 reauthentication_failed` ; `409 name_change_not_required` (nom non verrouillé : utiliser `PATCH`) ; `409 name_change_already_open` |
| `POST ID organizations/<id>/name-change-requests/<rid>/cancel/` | demandeur ou Administrateur principal effectif ; throttle `org_write` | — | `200` `NameChangeRequest` (`CANCELLED`) | `403 DENY_PERMISSION` (C8 : membre ayant `org.request_name_change`, typiquement un Administrateur, qui n'est ni le demandeur ni Administrateur principal effectif ; il voit déjà la demande, d'où 403 et non 404) ; `404 name_change_request_not_found` (inexistante ou d'une autre organisation) ; `409 name_change_not_open` |
| `POST ID organizations/<id>/kyc/documents/` (existant) | `org.verification_submit` | multipart, **ajout** de `name_change_request_id` (facultatif) | `201` (inchangé) | `400 {"document_type": [...]}` si le type n'est pas `NAME_CHANGE_PROOF`, `RCCM` ou `ARRETE_ONG` pour une pièce rattachée ; `404 name_change_request_not_found` ; `409 name_change_not_open` |

Le dépôt de la première pièce sur une demande `DOCUMENTS_REQUIRED` la fait passer en `PENDING_REVIEW`. Une pièce rattachée ne donne **aucun badge** tant que la demande n'est pas `COMPLETED`. La décision se prend dans le back-office (équipe Vérification) : aucune route du personnel en V1.

## 5. Effets côté acheteur et public [B2]

| Mesure | Route | Réponse |
|---|---|---|
| `FULL_SUSPENSION` | contact, révélation, échange, nouvelle conversation vers l'organisation | `403 DENY_SECURITY` (inchangé) |
| `CONTACT_BLOCK` | contact, révélation, échange | `403 seller_contact_unavailable` (neutre, C2 ; aucune clé `measure`) ; `allowed_channels` de l'offre : `[]` |
| `MESSAGING_BLOCK` | nouvelle conversation vers l'organisation **et** nouveau message de l'acheteur dans une conversation déjà ouverte (C5) | `403 seller_contact_unavailable` (neutre, C2) ; l'historique de la conversation reste lisible par l'acheteur |
| `CLOSING`, `ARCHIVED` | contact, révélation, échange, conversation | `403 DENY_OBJECT_STATE` (inchangé pour l'archivée) |
| `FULL_SUSPENSION`, `PUBLIC_VISIBILITY_HIDDEN`, `CLOSING`, `ARCHIVED` | fiche d'offre, liste, profil vendeur | offres non publiques (404 ou absentes, règle existante de `seller_is_public`) |
| `DORMANT` | annuaire | absente ; profil et offres inchangés |

Aucune réponse faite à un acheteur, à un tiers ou au public ne mentionne une restriction, une mesure, une catégorie ou un cycle de vie : le corps de `seller_contact_unavailable` est strictement identique à celui d'une organisation sans canal (test d'égalité). Les refus `DENY_SECURITY` (suspension totale) et `DENY_OBJECT_STATE` (fermeture, archivage) déjà servis aux acheteurs restent inchangés dans cette version.

## 6. Back-office (admin Django ; aucune route d'API) [B1 à B5]

Poser, modifier, lever une restriction ; gérer les catégories ; archiver par décision du personnel ; enregistrer, préparer, décider une restauration ; décider d'un changement de nom. Toutes les actions passent par les services d'ADR 0011 §6 (permissions, conflits d'intérêts, double contrôle, audit). Les formulaires affichent la consigne : « Ne mentionnez ni une autre personne, ni une sanction de compte, ni un moyen d'enquête. »

## 7. Codes d'erreur ajoutés, modifiés ou supprimés

| HTTP | `code` | Routes | Statut | Tâche |
|---|---|---|---|---|
| 403 | `DENY_RESTRICTION` (+ clé `measure`) | toute route protégée par une capacité restreignable, **membres seulement** | nouveau | B2 |
| 403 | `seller_contact_unavailable` | contact, révélation, échange, conversation (nouvelle ou existante) sous `CONTACT_BLOCK` / `MESSAGING_BLOCK` | sens étendu (refus neutre à l'acheteur, C2, C5) | B2 |
| 403 | `DENY_PERMISSION` | + annulation d'une demande de nom par un membre ni demandeur ni Administrateur principal effectif (C8) | étendu | B5 |
| 400 | `required_action_incompatible` (erreur de champ `required_action`) | back-office seulement (2.3) | nouveau | B2 |
| 403 | `DENY_SECURITY` | routes d'organisation | sens précisé : suspension totale de l'organisation ou compte restreint | B1 |
| 403 | `DENY_OBJECT_STATE` | routes d'organisation | sens étendu : `CLOSING` (hors capacités permises) et `ARCHIVED` | B1, B3 |
| 403 | `reauthentication_failed` | + 3.1, 4.3 | étendu | B3, B5 |
| 400 | `invalid_filter` | + 2.1 | étendu | B2 |
| 400 | `nothing_to_change` | 4.3 | nouveau | B5 |
| 404 | `name_change_request_not_found` | 4.3 | nouveau | B5 |
| 409 | `closure_already_requested`, `closure_not_pending`, `organization_not_dormant` | 3.1 à 3.3 | nouveaux | B3 |
| 409 | `name_change_not_required`, `name_change_already_open`, `name_change_not_open` | 4.3 | nouveaux | B5 |
| 409 | `name_locked_by_verification` | `PATCH organizations/<id>/` | message changé ; porte aussi sur `legal_name` | B5 |
| — | route `POST organizations/<id>/archive/` | — | **supprimée** (remplacée par 3.1) | B3 |
| — | champ `status` de `OrganizationInternal` et de `unavailable` | — | **déprécié** (B1), **retiré** (B2, après F-L17-1) | B1, B2 |

## 8. Qui voit quoi

| Information | Public | Membre (tout rôle) | Administrateur principal, Administrateur | Personnel |
|---|---|---|---|---|
| Cycle de vie | non | oui (`lifecycle`, `lifecycle_status`) | oui | oui |
| Origine de la dernière transition (`origin` : membres, Connecte+, automatique) | non | non | oui (C6) | oui (avec auteur) |
| Existence d'une restriction ciblée | non (acheteur : refus neutre `seller_contact_unavailable`) | oui (mesures) | oui | oui |
| Suspendue oui/non, mesures | non | oui (`restrictions`) | oui | oui |
| Catégorie, explication, motif communiqué, action requise, recours, depuis, échéance | non | non | oui (`restrictions/`), motif masqué si `LIMITED` | oui |
| Note interne, auteur, origine, preuves | non | non | non | oui (back-office) |
| Demande de changement de nom | non | non | oui | oui |
| Nouveau nom en cours d'examen | non | non | oui | oui |
| Dénomination légale | non (L1-02c) | non | oui | oui |
| Demande de restauration | non | non | non (passe par l'aide) | oui |

## 9. Ce qui change pour le front livré

| Écran ou module | Changement | Tâche |
|---|---|---|
| `api/types.ts`, fixtures, test de contrat | `Lifecycle` (avec `origin`), `RestrictionSummary`, `restricted_capabilities` (`internal/`, `results`), `lifecycle_status`, `restrictions`, 12 clés de `unavailable` (dont `lifecycle_origin`), `closure_delay_days` de `limits/`, capacités calculées ; `OrganizationStatus` dérivé jusqu'à son retrait | F-L17-1 |
| `lib/api-errors.ts`, `fr.ts` | `DENY_RESTRICTION` par `measure` ; libellés des mesures, actions requises, cycle de vie ; nouveaux codes 409 | F-L17-1 |
| `OrganizationStatusBadge` | statuts « Dormante », « Fermeture en cours » ; suspendue lue dans `restrictions.suspended` | F-L17-1 |
| `OrganizationUnavailableView` | décide d'après `lifecycle_status` et `restrictions` ; lien « Voir le détail » si `org.view_restrictions` ; annulation de fermeture si `org.archive` en `CLOSING` ; texte de l'archivée (restauration par l'aide) | F-L17-2, F-L17-3 |
| Nouvel écran « Restrictions » (`/organizations/:id/restrictions`) | 2.1 | F-L17-2 |
| Espace organisation | bannière « restriction en cours » (mesures) ; bannière dormante + « Confirmer l'activité » (3.3) ; formulaires qui reçoivent `DENY_RESTRICTION` | F-L17-2, F-L17-3 |
| `ArchiveOrganizationCard`, `use-organizations.ts` | `archive/` -> `closure/` (mot de passe, motif, état `CLOSING`, date d'effet ; délai lu dans `limits/`) ; vue archivée : « archivée par décision de Connecte+ » si `origin = CONNECTE_PLUS` | F-L17-3 |
| Fiche d'offre, messagerie (côté acheteur) | `seller_contact_unavailable` aussi dans une conversation existante (saisie désactivée, texte neutre existant) | F-L17-2 |
| Profil de l'organisation | `legal_name` ; message du nom verrouillé avec lien « Demander une modification du nom » ; parcours de demande et suivi | F-L17-4 |
