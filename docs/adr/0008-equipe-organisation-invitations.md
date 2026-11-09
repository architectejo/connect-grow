# ADR 0008 — Équipe d'organisation : invitations par lien, endpoints d'équipe, transfert de propriété (L1-01b à h, k)

- **Statut :** proposé (à valider par le chef de projet puis l'utilisateur pour les points de la section 15)
- **Date :** 09/11/2026
- **Décideurs :** chef de projet (décisions C1, C2, Q-L1-2, Q-L1-3, Q-L1-5, Q-L1-9 reprises ci-dessous), architecte technique
- **Amende :** ADR 0006 §4.3 (statut `INVITED` de `Membership`), §17.2 C (ligne `POST members/` avec `identifier`), §17.5.2 (« L1-01 doit implémenter invitation + acceptation »), §11.4 (en partie, voir 11).
- **Contrat d'API figé :** `docs/specs/L1-01-contrat-api.md` (à recopier dans les briefs backend et frontend).
- **Réf. :** CDC v1.2 §3.1 (IAM-005, IAM-006), règles verrouillées 1, 2, 3, 10, 12 ; ADR 0001, 0003, 0006, 0007 ; `docs/specs/L1-01-organisations.md`.

Hors périmètre de cet ADR : revendication, secours d'organisation orpheline, noms réservés, KYB, page publique, plans (L1-01i, j, l ; bloqués par Q-CLI8, Q-L1-6, Q-L1-8).

---

## 1. Contexte

L0-09 a livré les services d'équipe (`add_member`, `change_member_role`, `revoke_member`, `transfer_ownership`, `leave_organization`) mais seul `leave/` est exposé. L'ADR 0006 §17.2 C prévoyait un ajout par identifiant (`POST members/ {"identifier": ...}`) avec réponse neutre, et §4.3 un statut `Membership.INVITED`. Les deux se heurtent à des faits établis depuis :

- l'ajout direct sans consentement est interdit d'exposition (§17.5.2) ;
- une recherche de compte par téléphone ou e-mail est un oracle d'existence (corps, temps, notification) ;
- l'e-mail n'est pas vérifié (seul `phone_verified` existe) ;
- un invité sans compte n'a pas de `user` : une ligne `Membership` ne peut pas le représenter (clé `(organization, user)` unique, plafond d'organisations compté sur les appartenances, comptage des propriétaires, destinataires de notifications : chacun devrait filtrer `INVITED`).

## 2. Options étudiées

| # | Option | Verdict |
|---|---|---|
| A | `Membership.status = INVITED` | Rejetée : pas de `user` pour un invité sans compte ; tous les comptages et destinataires existants devraient exclure `INVITED` (régression silencieuse du plafond, de `last_owner` et des notifications). |
| B | Invitation adressée à un téléphone vérifié, rattachée au compte porteur | Rejetée en V1 : recherche de compte = oracle ; coût et anti-abus d'un SMS plateforme (Q-L1-2). Reste possible plus tard sans casser le modèle (ajout d'un champ). |
| C | **Modèle `OrganizationInvitation` séparé, lien à usage unique, jeton haché, sans recherche de compte** | **Retenue** (décision C1 du chef de projet). |

## 3. Décision

1. **Invitation par lien à usage unique** (modèle séparé, aucun statut `INVITED`). Le serveur renvoie le jeton **une seule fois** à la création ; l'inviteur le transmet lui-même (hypothèse Q-L1-2 : aucun envoi plateforme en V1). Aucune réponse de l'API ne dépend de l'existence d'un compte.
2. **Rôles invitables : `EDITOR` et `ANALYST` seulement** (hypothèse Q-L1-3). `OWNER` jamais (invariant, aussi en `CHECK` en base) ; `ADMIN` par promotion (PATCH), pas par invitation. La liste vit dans une constante de service (`INVITABLE_ROLES`) : l'assouplir ne demande aucune migration.
3. **Tout est revérifié à l'acceptation** : jeton valide et non expiré ; organisation `ACTIVE` ; inviteur toujours membre actif avec `org.manage_members` et `can_manage_role_of(rôle courant, rôle invité)` ; cible active, non restreinte, téléphone vérifié, sous le plafond d'organisations, pas déjà membre actif.
4. **Une invitation n'ouvre aucun droit** tant qu'elle n'est pas acceptée ; elle n'est jamais lue par un autre domaine.
5. **Le personnel n'attribue jamais de rôle dans cette tâche** (C2). Le service d'attribution propre à la revendication viendra avec L1-01i/j : il devra amender l'ADR 0006 §11.4 (« `Membership` en lecture seule ; le personnel n'attribue pas de rôle ») et ne pas passer par l'admin Django. Rien n'est changé ici ; `Membership` reste en lecture seule dans l'admin.
6. **Transfert de propriété** : une transaction, deux changements de rôle, `confirm: true` obligatoire et **ressaisie du mot de passe** (Q-L1-5, hypothèse retenue). Même exigence pour toute opération qui touche un siège de propriétaire (voir 8).
7. **Départ qui ne laisse aucun propriétaire effectif** (Q-L1-9, règle exacte en 9) : refusé tant que l'organisation active a des offres actives.
8. **Événement de visibilité** (dette ADR 0006 §20 T9-1 n°4) : tout changement d'appartenance qui touche un propriétaire émet `identity.seller_context_status_changed` avec `reason = "owners_changed"` (voir 6).
9. **L1-01k** : seul `GET me/account-deletion-blockers/` ; aucune suppression libre-service.

## 4. Modèle de données

Domaine `identity`, fichier `models.py`. Toutes les clés primaires sont des UUID (`BaseModel`). Aucune clé étrangère vers un autre domaine ; `User` autorisé.

### 4.1 `OrganizationInvitation`

| Champ | Type | Remarques |
|---|---|---|
| `id` | UUID PK | `BaseModel`, aussi `created_at`, `updated_at` |
| `organization` | FK `Organization`, `CASCADE`, `related_name='invitations'` | même domaine |
| `role` | `CharField(20)`, choix `ROLE_CHOICES` | jamais `OWNER` : `CheckConstraint(~Q(role='OWNER'), name='orginv_role_not_owner')` (portable MySQL 8.0.16+, SQLite) ; `ADMIN` refusé en service, pas en base |
| `status` | `CharField(10)` | `PENDING`, `ACCEPTED`, `DECLINED`, `REVOKED`, `EXPIRED` ; défaut `PENDING` |
| `token_hash` | `CharField(64)`, **unique** inconditionnel | SHA-256 hexadécimal du jeton (jeton de 256 bits : un hachage rapide suffit, pas de sel) ; le jeton n'est jamais stocké |
| `label` | `CharField(60)`, blank | étiquette libre de l'inviteur (« Jean, comptable »). **Vidée dès que l'invitation quitte `PENDING`** (minimisation, règle 10). Jamais dans l'audit, l'outbox, une notification, un journal |
| `created_by` | FK `User`, `SET_NULL`, nul, `related_name='+'` | inviteur |
| `expires_at` | `DateTimeField` | calculée serveur : `now + IdentitySettings.invitation_ttl_days` |
| `closed_at` | `DateTimeField`, nul | passage hors `PENDING` |
| `closed_by` | FK `User`, `SET_NULL`, nul, `related_name='+'` | cible (acceptée, refusée), membre qui révoque ; nul pour `EXPIRED` |

Index (noms explicites) : `orginv_org_status (organization, status)` ; `orginv_status_expires (status, expires_at)` (cron) ; `orginv_created_by (created_by, status)` (balayage à la perte d'autorité). L'unicité de `token_hash` crée son propre index. **Aucune unicité conditionnelle** : il n'y a pas de limite « une invitation en attente par cible » (le lien n'est pas lié à une personne) ; le plafond d'invitations en attente par organisation est garanti en service sous verrou.

### 4.2 `IdentitySettings` (règle 11)

Trois champs ajoutés, modifiables en back-office, changements audités comme les autres réglages (`record_settings_change`). Les valeurs sont **provisoires, à confirmer** (aucune source client).

| Champ | Type | Défaut | Bornes |
|---|---|---|---|
| `invitation_ttl_days` | PositiveSmallInteger | 7 | 1 à 30 |
| `max_pending_invitations` | PositiveSmallInteger | 20 | 1 à 200 (par organisation) |
| `invitation_history_days` | PositiveSmallInteger | 30 | 1 à 365 (conservation des lignes closes) |

`GET organizations/limits/` gagne `invitation_ttl_days` et `max_pending_invitations` (additif).

### 4.3 Machine d'états

```
PENDING --accept--> ACCEPTED      (cible, atomique, mise à jour conditionnelle)
PENDING --decline-> DECLINED      (cible)
PENDING --revoke--> REVOKED       (membre org.manage_members, ou balayage « autorité perdue » : inviteur retiré,
                                   parti ou rétrogradé sous le rôle invité)
PENDING --cron----> EXPIRED       (expires_at <= now)
ACCEPTED, DECLINED, REVOKED, EXPIRED : terminaux (aucun retour, label vidé)
```

Une invitation `PENDING` dont l'organisation est suspendue ou archivée reste `PENDING` mais inacceptable (404 uniforme) ; elle expire normalement. Une `PENDING` échue mais pas encore balayée est présentée `EXPIRED` en lecture et est inacceptable (la condition `expires_at > now` est dans la mise à jour conditionnelle).

## 5. Services (`identity/organizations.py`, exposés par `identity/services.py`)

Aucun service ne reçoit de plan, prix ni entitlement (règle 2). Toute écriture : `transaction.atomic()`, `_lock_organization` en premier, autorisation recalculée sous verrou, audit synchrone avec `context=(CONTEXT_ORGANIZATION, org.pk)`, événement outbox dans la même transaction.

### 5.1 Invitations

- `create_invitation(actor, organization_id, role, label='') -> (invitation, token)` : `_authorize_member(actor, org, 'org.manage_members')` ; rôle dans `INVITABLE_ROLES` sinon 400 `invitation_role_not_allowed` (rôle inconnu : 400 de validation) ; comptage des `PENDING` non échues sous verrou de l'organisation, `>= max_pending_invitations` -> 409 `invitation_limit_reached` ; jeton `secrets.token_urlsafe(32)` (43 caractères, 256 bits) ; `token_hash = sha256(jeton)` ; audit `INVITATION_CREATED` ; événement `created`. Le jeton n'est renvoyé qu'ici.
- `list_invitations(actor, organization_id, status_filter) -> queryset` : `org.manage_members`, lecture seule, jamais le jeton ni son empreinte.
- `revoke_invitation(actor, organization_id, invitation_id)` : `org.manage_members` ; mise à jour conditionnelle `PENDING -> REVOKED` (0 ligne : 404 `invitation_not_found` si l'invitation n'est pas de cette organisation, 409 `invitation_not_pending` sinon) ; label vidé ; audit `INVITATION_REVOKED` (`reason=manual`) ; événement `revoked`.
- `preview_invitation(user, token) -> dict` : lecture sans effet (`organization_name`, `org_type`, `role`, `expires_at`, `invited_by_display_name`). Mêmes contrôles de validité que l'acceptation (3, points jeton, expiration, organisation active, autorité de l'inviteur), **sans** les contrôles propres à la cible. Toute invalidité : 404 `invitation_invalid`.
- `accept_invitation(user, token) -> Membership`, ordre exact :
  1. forme du jeton (chaîne `[A-Za-z0-9_-]`, 1 à 128 caractères) sinon 404 `invitation_invalid` (pas de 400 : pas de renseignement) ; `FailureLimiter.check` ;
  2. recherche par `token_hash` ; absente : `FailureLimiter.failure` et 404 ;
  3. `transaction.atomic()` : verrou de l'organisation (inexistante : 404 `invitation_invalid`) ; **prise de l'invitation par mise à jour conditionnelle** `filter(pk, status=PENDING, expires_at__gt=now).update(status=ACCEPTED, closed_at, closed_by, label='')` : 0 ligne -> 404 ; organisation non `ACTIVE` -> 404 ; autorité de l'inviteur (appartenance active, `org.manage_members`, `can_manage_role_of`) perdue -> 404. **Puis seulement** les contrôles propres à la cible : compte restreint `DENY_SECURITY`, `phone_verified` faux -> 403 `phone_verification_required`, plafond (`_ensure_under_limit`, verrou du compte) -> 409 `organization_limit_reached`, déjà membre actif -> 409 `already_member` ; toute levée d'exception annule la transaction et donc la prise : l'invitation reste `PENDING` ;
  4. `_activate_membership(...)` (noyau extrait de `add_member`, voir 5.3) : crée la ligne ou réactive la même (R12), `added_by = inviteur`, `joined_at = now` ;
  5. audits `INVITATION_ACCEPTED` (acteur = cible) et `MEMBERSHIP_ADDED` (acteur = cible, `via=invitation`, `invited_by=<uuid>`) ; événements `identity.membership_changed` (`added` ou `reactivated`) et `identity.organization_invitation_changed` (`accepted`) ;
  6. `FailureLimiter.success`.
  Les refus après identification de l'invitation (tout sauf « jeton inconnu ») sont journalisés **hors transaction** (sinon la trace serait annulée avec elle) : `INVITATION_REFUSED`, `target=invitation`, `details = organization=<uuid>; reason=<code>` avec `reason` parmi `expired`, `revoked`, `used`, `authority_lost`, `org_inactive`, `account_restricted`, `phone_unverified`, `limit`, `already_member`. Un jeton inconnu n'est pas journalisé (rien à rattacher ; bruit contrôlé par les throttles).
- `decline_invitation(user, token)` : mêmes étapes 1 et 2 ; conditionnelle `PENDING -> DECLINED` (+ `expires_at > now`) ; sinon 404 ; aucun contrôle de plafond, de téléphone ni d'autorité (refuser est toujours possible tant que l'invitation est vivante) ; audit `INVITATION_DECLINED` ; événement `declined`.
- `sweep_invitations_of_inviter(actor, organization, inviter_id, keep_role=None)` (interne) : appelée dans la transaction de `_end_membership` (retrait ou départ de l'inviteur) et de `_apply_role_change` (l'inviteur perd `org.manage_members` ou n'a plus l'autorité sur le rôle invité). Passe ses `PENDING` à `REVOKED` (`reason=authority_lost`), label vidé, un audit `INVITATION_REVOKED` par invitation (acteur = auteur du changement). C'est le nettoyage ; **la garantie de sécurité reste la revérification à l'acceptation**.
- `expire_invitations(now) -> int` : voir 10.

### 5.2 Équipe (lectures et écritures par `membership_id`)

Nouvelles fonctions, qui résolvent le membre **dans l'organisation du chemin** sous verrou (autre organisation ou inexistant : 404 `member_not_found`) puis appellent les mêmes noyaux privés que les fonctions existantes. Les signatures actuelles par `user_id` sont conservées (une trentaine de tests) ; l'API n'appelle que les nouvelles.

- `list_members(actor, organization_id) -> queryset` : `org.view_internal` ; `select_related('user')`, `only('full_name')` ; seulement `ACTIVE` ; ordre rôle (propriétaire, administrateur, éditeur, analyste via `Case/When`), `joined_at`, `id`. Le serializer calcule `display_name = public_display_name(full_name)`, `is_self`, `is_last_effective_owner` (nombre de requêtes indépendant de la page).
- `change_role(actor, organization_id, membership_id, new_role, confirm=False, password=None)`.
- `remove_member(actor, organization_id, membership_id)` : refuse soi-même (400 `use_leave`) ; refuse cible `OWNER` (409 `owner_must_be_demoted`, décision de l'architecte : retirer un propriétaire exige de le rétrograder d'abord, ce qui impose la ressaisie du mot de passe ; réversible).
- `transfer_ownership_to(actor, organization_id, membership_id, my_new_role=ADMIN, confirm=False, password=None)`.

### 5.3 Refactorisations imposées

- Extraire de `add_member` le noyau `_activate_membership(inviter, organization, target_user, role, joined_via)` (création ou réactivation, audit, événement, sans autorisation). `add_member` le réutilise ; sa docstring dit « noyau interne, jamais exposé » ; un test de garde de routes vérifie qu'aucune vue ne l'importe.
- `_effective_owner_ids(organization_id)` et `count_effective_owners(organization_id)` : propriétaires `ACTIVE` dont le compte est actif et sans sanction bloquante. **Une seule définition**, partagée avec `get_seller_context_public_flags` (`sellers.py`, qui l'applique déjà) : B1 y rattache `sellers.py`.
- `_publish_owners_changed(organization, actor)` : `publish_event('identity.seller_context_status_changed', payload={'context_type': 'ORGANIZATION', 'context_id': <uuid>, 'reason': 'owners_changed', 'actor_id': ...}, deliver_now=True)`. Appelée par `_apply_role_change` et `_end_membership` quand l'ancien ou le nouveau rôle est `OWNER` (pas par `create_organization`).

## 6. Événements de domaine (outbox, ADR 0003)

| Type | Version | Charge utile (UUID et codes seulement) | Abonnés |
|---|---|---|---|
| `identity.membership_changed` (existant) | 1 | clés existantes ; **ajout additif** `via` (`"invitation"` ou absent). Pour une acceptation, `actor_id` = l'**inviteur** (identifiant de qui a ajouté, cohérent avec `added_by`) afin que l'abonné existant envoie toujours la notification de bienvenue (il ignore `actor_id == user_id`). L'`AuditLog` reste, lui, au nom de l'acceptant. | inchangés |
| `identity.organization_invitation_changed` (**nouveau**, v1) | 1 | `organization_id`, `invitation_id`, `change` (`created`, `accepted`, `declined`, `revoked`), `role`, `actor_id`, `inviter_id` | `notifications.notify_invitation_outcome` (nouveau) |
| `identity.seller_context_status_changed` (existant) | 1 | nouvelle valeur `reason = "owners_changed"` | `marketplace.sync_seller_visibility` (recalcule, ignore le motif) ; `notifications.notify_organization_status` (ignore tout motif absent de `_STATUS_MESSAGES`) : **aucun changement d'abonné** |

- L'expiration par cron n'émet **aucun** événement (pas de notification de masse) ; elle laisse une trace d'audit par exécution.
- Jamais dans une charge utile : nom, téléphone, e-mail, jeton, étiquette. La déclaration du nouveau type est ajoutée à `platform_core/catalog.py` avec son abonné (le contrôle `platform_core.E001` doit rester vert).
- `notify_invitation_outcome` : pour `accepted` et `declined`, notifie **l'inviteur seul** s'il est toujours destinataire de `org.manage_members` (`get_organization_recipients`), contexte de notification = l'organisation, lien `/organizations/<uuid>/team`. Texte neutre sans nom : « Une invitation à rejoindre « {organisation} » avec le rôle {rôle} a été acceptée / refusée. » Rien n'est notifié pour `created`, `revoked`.
- Dette D11 corrigée au passage : la notification de bienvenue et de changement de rôle (`notify_membership_change`) pointe vers `/organizations/<uuid>/team` au lieu de `/dashboard` (pas pour `revoked`, qui reste personnelle).

## 7. Journal d'audit (règle 12)

`details` au format existant `clé=valeur; …`, UUID et codes seulement. Jamais de téléphone, e-mail, nom, jeton, étiquette, nom de fichier.

| Action | Acteur | Cible | `details` |
|---|---|---|---|
| `INVITATION_CREATED` | inviteur | `organizationinvitation` | `organization; role; ttl_days` |
| `INVITATION_ACCEPTED` | cible | idem | `organization; role; invited_by` |
| `INVITATION_DECLINED` | cible | idem | `organization; role` |
| `INVITATION_REVOKED` | membre ou auteur du changement | idem | `organization; role; reason=manual\|authority_lost` |
| `INVITATION_REFUSED` | cible | idem | `organization; reason=<code>` (voir 5.1) |
| `INVITATION_EXPIRED` | système (acteur nul) | aucune | `count=<n>` (une trace par exécution, seulement si `n > 0`) |
| `MEMBERSHIP_ADDED` | cible | `membership` | existant + `via=invitation; invited_by` |
| `MEMBERSHIP_ROLE_CHANGED`, `MEMBERSHIP_REVOKED`, `ORG_OWNERSHIP_TRANSFERRED` | existants | existants | + `reauth=true` quand une ressaisie de mot de passe a été exigée |
| `ORG_SENSITIVE_REAUTH_FAILED` (**nouveau**) | acteur | `organization` | `action=transfer\|promote_owner\|demote_owner` (échec de ressaisie, journalisé hors transaction) |

`AuditLog.action` est un champ libre : aucune migration `moderation`.

## 8. Permissions, ressaisie du mot de passe, throttles

### 8.1 Permissions par capacité (inchangées : `org.manage_members` et `org.manage_roles` = OWNER, ADMIN aujourd'hui)

| Opération | Capacité | Règles en plus (sous verrou) |
|---|---|---|
| Lister les membres | `org.view_internal` | tout rôle ; ordre des contrôles : non-membre `DENY_RELATION`, état de l'organisation, état du compte, capacité |
| Changer un rôle | `org.manage_roles` | `can_manage_role_of` sur le rôle courant **et** le nouveau ; invariants `last_owner`, `last_effective_owner` |
| Retirer un membre | `org.manage_members` | `can_manage_role_of` ; pas soi-même ; pas un `OWNER` |
| Transférer la propriété | `org.manage_roles` | acteur `OWNER` ; cible membre actif disponible, différente de soi |
| Inviter, lister, révoquer | `org.manage_members` | rôle dans `INVITABLE_ROLES` ; plafond de pendantes |
| Prévisualiser, accepter, refuser | authentifié, aucune capacité | revérifications de 5.1 |
| `account-deletion-blockers` | authentifié, aucune capacité | strictement le compte appelant |

`is_staff` et `is_superuser` n'ouvrent rien. L'en-tête `X-Context` est **ignoré** par toutes ces routes (organisation désignée par le chemin ; autorisation par objet d'après le rôle réel dans **cette** organisation, ADR 0006 §6.4) ; chaque vue déclare `acting_context_exempt = EXEMPT_REASON` (test de garde de routes).

### 8.2 Ressaisie du mot de passe (Q-L1-5, hypothèse retenue)

Exigée (`confirm: true` **et** `password`) pour : le transfert de propriété ; une promotion vers `OWNER` ; la rétrogradation d'un `OWNER`. Ordre : validation du corps (`confirmation_required`, `password_required`, 400) ; contrôle du mot de passe **avant** de poser le verrou (le hachage est lent) par `check_password` ; échec -> 403 `reauthentication_failed` + `FailureLimiter('org_reauth', threshold=5)` clé = identifiant du compte (le compteur est celui de l'attaquant, pas d'une victime) + audit `ORG_SENSITIVE_REAUTH_FAILED` ; succès : `limiter.success`. Pas de « fenêtre de confiance » : la ressaisie est demandée à chaque opération sensible. Le mot de passe n'est jamais journalisé (vues sous `sensitive_post_parameters('password', 'token')`).

### 8.3 Throttles (`identity/throttles.py`, taux dans `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`)

| Scope | Classe | Taux | Clé |
|---|---|---|---|
| `org_write` (existant) | `OrganizationWriteThrottle` | 30/h | compte ; PATCH et DELETE de membre, DELETE d'invitation |
| `org_sensitive` | `OrganizationSensitiveThrottle` | 10/h | compte ; transfert et PATCH exigeant la ressaisie |
| `invitation_create` | `InvitationCreateThrottle` | 20/h | compte (écritures seulement) |
| `invitation_create_org` | `InvitationCreateOrgThrottle` | 50/jour | identifiant de l'organisation (chemin) |
| `invitation_redeem` | `InvitationRedeemIpThrottle` | 60/h | IP (preview, accept, decline ; `IpThrottle`) |
| `invitation_redeem_user` | `InvitationRedeemUserThrottle` | 30/h | compte |
| `account_blockers` | réutiliser `ContextsListThrottle`-style | 120/h | compte |

Dépassement : 429, aucune écriture. Prérequis de production (D9) : cache partagé entre processus, sinon ces limites sont par processus.

## 9. Règle « propriétaire effectif » et départ sans propriétaire effectif (Q-L1-9)

**Définition (R-L8).** Propriétaire effectif : appartenance `OWNER` `ACTIVE` dont le compte est actif et sans sanction bloquante (même définition que la visibilité publique, `sellers.py`).

**Règle retenue, appliquée dans le noyau privé commun à `leave_organization` et `change_role` (rétrogradation d'un `OWNER`) ; `remove_member` ne peut jamais réduire les propriétaires (cible `OWNER` refusée), après l'écriture et sous verrou, comme `last_owner` :**

> Refus `409 last_effective_owner` si, **après** l'opération : (1) l'organisation est `ACTIVE` ; (2) `count_effective_owners == 0` ; (3) **avant** l'opération il y en avait au moins un (l'opération est la cause) ; (4) l'organisation a au moins une offre active.

*Offre active* = non supprimée, statut `ACTIVE`, non échue (`expires_at` nul ou futur), pour le contexte vendeur `(ORGANIZATION, id)`. Lecture via un nouveau service `marketplace.services.seller_has_active_offers(context_type, context_id) -> bool` (une requête `exists`, import local depuis `identity` comme `_context_has_grave_evidence`, pas de clé étrangère).

Si l'organisation n'a aucune offre active, l'opération est **permise** (l'organisation devient orpheline sans effet public) ; l'audit porte `orphaned=true` dans `details` et l'événement `owners_changed` est émis. Le garde `last_owner` (qui compte les appartenances) reste appliqué **avant** et prévaut. Les organisations suspendues (déjà masquées) et archivées ne sont pas concernées par `last_effective_owner`. Limite connue : une offre peut être publiée entre le contrôle et la validation (pas de transaction inter-domaines, règle d'architecture) ; l'organisation devient alors orpheline avec une offre non publique, rattrapée par `sync_seller_visibility` ; elle sera secourable par L1-01j.

`is_last_effective_owner` dans la liste des membres (voir contrat) : vrai uniquement sur la ligne du seul propriétaire effectif, et **seulement** pour un appelant `org.manage_members` (sinon `null`).

## 10. Migrations, commande planifiée, retour arrière

- `identity 0015_organizationinvitation` : `CreateModel` + 3 index + `UniqueConstraint`/`unique` sur `token_hash` + `CheckConstraint`. Réversible (suppression de la table). Aucune donnée existante touchée.
- `identity 0016_identitysettings_invitations` : 3 `AddField` avec défaut. Réversible.
- Aucune migration de données. Aucune migration dans `moderation`, `notifications`, `marketplace`.
- Une seule branche touche les migrations `identity` à la fois (règle 10.1 de l'ADR 0006). Chaque migration est appliquée sur une base SQLite vierge ; `makemigrations --check --dry-run` vert.
- Commande `python manage.py expire_invitations` (`identity/management/commands/`) : (1) `PENDING` avec `expires_at <= now` -> `EXPIRED` (mise à jour de masse, label vidé), idempotente ; (2) suppression des lignes closes depuis plus de `invitation_history_days` jours, par lots de 500 ; (3) un `INVITATION_EXPIRED` `count=<n>` si `n > 0`. Ligne `backend/cron/crontab` horaire (`7 * * * *`) et ajout de `expire_invitations` à `SCHEDULED_COMMANDS` du test de crontab.
- Compatibilité : `add_member` conservée (tests) mais plus exposable ; `POST organizations/<id>/members/` n'est **pas** routé (405).

## 11. Concurrence et parades (couche service ; verrous effectifs sous MySQL, sérialisation d'écriture sous SQLite)

| Risque | Parade |
|---|---|
| Deux acceptations du même jeton | prise par `UPDATE ... WHERE status='PENDING' AND expires_at > now` : une seule ligne modifiée, l'autre reçoit 404 ; une seule appartenance (`membership_org_user_uniq` en filet) |
| Acceptation et révocation simultanées | même mise à jour conditionnelle des deux côtés : un seul gagnant |
| Acceptation en même temps que la rétrogradation ou le retrait de l'inviteur | verrou d'organisation d'abord (ordre unique : organisation, puis invitation, puis appartenance de l'inviteur, puis compte de la cible) ; l'autorité est lue sous verrou ; le balayage tourne dans la transaction qui change l'appartenance |
| Plafond d'organisations de la cible | `_ensure_under_limit` (verrou du compte) à l'acceptation, jamais à l'envoi |
| Dépassement du plafond de pendantes | comptage sous verrou d'organisation à la création |
| Échec après prise de l'invitation (plafond, téléphone, déjà membre) | exception dans le `atomic` : la prise est annulée, l'invitation reste `PENDING` |
| Deux départs de deux propriétaires (invariant `last_owner`) | déjà couvert (vérification après écriture, sous verrou) ; **registre de recette MySQL** (ADR 0006 §17.5.4, D7) à enrichir : deux acceptations simultanées du même jeton, acceptation contre révocation |
| Transfert contre changement de rôle concurrent | un seul verrou d'organisation ; invariants vérifiés après écriture, la transaction est annulée si violés |
| Interblocage | ordre de verrouillage identique partout (organisation puis comptes) |
| Rejeu après acceptation | `status != PENDING` -> 404 uniforme |

Aucun contrôle de concurrence ne s'appuie sur une contrainte conditionnelle ni sur une fonction SQL propre à un moteur.

## 12. Sécurité : synthèse (revues obligatoires en section 13)

- Jeton : 256 bits (`secrets.token_urlsafe(32)`), jamais stocké (SHA-256 seul), recherche par égalité sur l'empreinte indexée (aucune comparaison caractère par caractère exploitable : l'attaquant ne contrôle pas l'empreinte). Pas dans une URL d'API ; le front le lit dans le **fragment** (`#token=`) de l'URL de partage, le range en `sessionStorage` et nettoie la barre d'adresse (`history.replaceState`), puis l'envoie dans le **corps** d'un `POST`. Réponses `Cache-Control: private, no-store`.
- Pas d'oracle : jeton inconnu, échu, révoqué, utilisé, organisation inactive, autorité perdue, tout donne **le même** `404 invitation_invalid` (même corps). Les 403 et 409 propres à la cible (téléphone, plafond, déjà membre, compte restreint) ne sont renvoyés qu'**après** validité de l'invitation, et ne concernent que l'état de l'appelant. Le temps de réponse n'est pas rendu constant (inexploitable sans jeton valide de 256 bits).
- Risque accepté, **lien transmis** : quiconque détient le lien et un compte éligible peut l'utiliser (jeton porteur). Mesures : rôles limités à éditeur et analyste, usage unique, expiration courte, révocation, notification de l'inviteur à l'acceptation. Le rattachement à un téléphone vérifié (option B) reste une évolution possible.
- Étiquette : donnée saisie par l'inviteur sur un tiers ; stockée en clair tant que `PENDING`, vidée ensuite, jamais exposée hors liste des membres habilités, jamais journalisée. Test à sentinelle sur audit, outbox, notifications, journaux.
- Escalade : `INVITABLE_ROLES` en service, `CHECK` anti-`OWNER` en base, balayage et revérification de l'autorité, `can_manage_role_of` partout, ressaisie du mot de passe pour tout siège de propriétaire.
- IDOR : `membership_id` et `invitation_id` toujours filtrés par l'organisation du chemin ; autre organisation = 404 identique à inexistant ; l'organisation inexistante répond comme un non-membre (`DENY_RELATION`, D14).
- Données personnelles (règle 10) : liste des membres limitée à `display_name` abrégé ; blocages de suppression sans donnée d'un autre membre (comptage seulement).

---

## 13. Découpage en tâches

Dépendances : **ADR et contrat validés d'abord.** Les écrans (D) et les tâches B1 et B2a peuvent démarrer en parallèle. Les fichiers partagés (`urls.py`, `throttles.py`, `settings.py`, `organizations.py`) sont modifiés par plusieurs tâches : soit worktrees séparés avec fusion par le chef de projet, soit exécution séquentielle dans l'ordre B1, B2a, B2b, B4. Une seule tâche touche `identity/migrations/` à la fois (B2a).

| ID | Agent | Contenu | Dépend de | Parallélisable avec |
|---|---|---|---|---|
| **D1** | designer-ux | Écran Équipe cible (liste, changer le rôle, retirer, transférer avec confirmation et mot de passe, indicateur `last_effective_owner`), invitation (création, lien à copier une fois, liste, révocation), page d'acceptation (connecté ou non, jeton en fragment), états d'erreur (`invitation_invalid`, `organization_limit_reached`, `already_member`, `phone_verification_required`), bloc « blocages de suppression » ; **révise le formulaire « ajout par identifiant »** de L0-09 §7.7 | contrat | B1, B2a |
| **B1** | dev-backend | Équipe (L1-01b, e, f, h) : `list_members`, `change_role`, `remove_member`, `transfer_ownership_to`, ressaisie du mot de passe (limiter, audit), règle `last_effective_owner`, `count_effective_owners` partagé avec `sellers.py`, `marketplace.services.seller_has_active_offers`, événement `owners_changed`, vues et URL, throttles `org_sensitive`, OpenAPI (`extend_schema`), tests (exhaustivité des clés, IDOR, escalade, atomicité du transfert, concurrence logique, `assertNumQueries`, absence de plan) | ADR | D1, B2a, F1 (sur contrat) |
| **B2a** | dev-backend | Modèle `OrganizationInvitation`, migrations 0015 et 0016, réglages, admin en lecture seule, type d'événement et abonné `notify_invitation_outcome` (squelette), commande `expire_invitations` + crontab + test de crontab, throttles de création et d'échange | ADR | D1, B1 |
| **B2b** | dev-backend | Services d'invitation (5.1), `_activate_membership`, balayage dans `_end_membership` et `_apply_role_change`, vues et URL, audits, événements, lien de notification D11, tests (rejeu, concurrence logique, révocation de l'inviteur, plafond à l'acceptation, uniformité du 404, sentinelles audit/outbox/notifications, garde de routes `add_member`, aucun plan) | B1, B2a | F1 |
| **B4** | dev-backend | L1-01k : `account_removal_blockers(user)` factorisé avec `assert_account_removable` (point de décision unique), endpoint `me/account-deletion-blockers/`, tests | B1 | B2b, F1, F2 |
| **S1** | auditeur-securite | Revue de B1 : escalade, ressaisie, IDOR `membership_id`, oracle d'état, fuite dans audit et outbox | B1 | B2b |
| **S2** | auditeur-securite | Revue de B2a et B2b : jeton, rejeu, concurrence d'acceptation, uniformité des réponses, autorité de l'inviteur, throttles, étiquette, fuite audit, outbox, notifications, journaux, `Cache-Control` | B2b | F2 |
| **F1** | dev-frontend | Écran Équipe (L1-01b, e, f, h) : liste, menus selon rôle **et** gestion du refus serveur, dialogue de transfert (ressaisie), messages `last_owner` / `last_effective_owner`, i18n, Vitest | contrat, D1 | B1 |
| **F2** | dev-frontend | Invitations : création, lien copiable une seule fois, liste, révocation ; page d'acceptation avec jeton en fragment conservé en `sessionStorage` après connexion ou inscription, nettoyage de l'URL, erreurs neutres | contrat, D1 | B2b |
| **F3** | dev-frontend | Blocages de suppression dans Paramètres (lecture seule ; la suppression n'existe pas) | B4, contrat | |
| **R** | relecteur-code | Après **chaque** tâche B et F | tâche | |
| **Q** | qa-testeur | Scénarios 1 à 7 et 11 à 13 de la spec L1-01 §10 ; non-régression `identity`, `notifications`, `marketplace`, `moderation`, `DomainBoundariesTests` ; entrées au registre MySQL | tout | |

**Revues `auditeur-securite` obligatoires : S1 (après B1) et S2 (après B2a et B2b, avant livraison de F2).** B4 : relecture seule (lecture du compte appelant, aucune donnée tierce). L'auditeur relit aussi F2 sur le seul point du jeton (fragment, `sessionStorage`, aucune écriture dans les journaux ni les liens).

## 14. Conséquences

- Nouveau modèle, 2 migrations `identity`, 1 type d'événement, 1 abonné, 1 commande cron, 6 scopes de throttle, 11 routes (voir le contrat).
- ADR 0006 §4.3 : `INVITED` n'existera **pas** ; §17.2 C : la ligne `POST members/` est remplacée par `invitations/` ; §17.5.2 : réalisé par cet ADR ; §11.4 : inchangé jusqu'à L1-01i/j (qui devra l'amender).
- L'écran E6 cible de L0-09 (« ajout par numéro ou e-mail d'un compte existant ») est à réviser par D1.
- Tests existants conservés ; `add_member` reste utilisé par eux (docstring et garde de routes mises à jour).
- Dettes prises ou laissées : D1 (invitation), D5 (visibilité sur mouvement de propriétaire) soldées ; D8 (statut `INVITED`) soldée par abandon ; D9 (cache partagé des throttles) et D7 (recette MySQL) restent des prérequis de production ; D6 (TOCTOU de suppression) reste attachée à la future suppression libre-service.
- Risques acceptés : lien transmis (porteur), fenêtre entre contrôle des offres actives et validation, pas de notification à la cible (aucun canal plateforme).

## 15. Questions restantes (recommandations)

| # | Question | Pour | Recommandation |
|---|---|---|---|
| 1 | Valeurs de départ : validité 7 jours, 20 invitations en attente, historique 30 jours | utilisateur | Valider ; réglables sans migration. |
| 2 | `ADMIN` par invitation (Q-L1-3) | client | Garder interdit en V1 (promotion explicite par un propriétaire) ; l'ouvrir = modifier `INVITABLE_ROLES`, sans migration. |
| 3 | Canal d'envoi (Q-L1-2) : l'inviteur copie le lien (WhatsApp, SMS personnel) | client | Confirmer. Un envoi plateforme exigerait un téléphone vérifié de la cible et une option B. |
| 4 | Ressaisie du mot de passe (Q-L1-5) et sa portée (transfert, promotion et rétrogradation d'un propriétaire) | utilisateur | Valider ; coûte une saisie, évite le détournement d'une session ouverte. |
| 5 | Retrait direct d'un propriétaire refusé (`owner_must_be_demoted`) | utilisateur | Valider (décision de l'architecte, deux appels au lieu d'un). |
| 6 | Règle `last_effective_owner` (Q-L1-9) liée aux offres actives, et définition d'« offre active » | utilisateur, client | Valider ; alternative plus stricte (refus sans condition d'offres) bloquerait des départs légitimes pendant une sanction. |
| 7 | Acceptation par une cible **déjà membre** : 409 et l'invitation reste `PENDING` (jamais de changement de rôle par invitation) | utilisateur | Valider. |
| 8 | Aperçu d'invitation réservé aux comptes connectés (pas de nom d'organisation avant connexion) | designer, utilisateur | Valider (limite l'énumération anonyme) ; à reconsidérer si l'UX l'exige. |
| 9 | Pas de journal d'audit pour la lecture `account-deletion-blockers` (la spec L1-01 §k prévoyait `ACCOUNT_DELETION_BLOCKED_BY_ORG`) | chef de projet | Ne rien journaliser en lecture ; l'audit sera posé par la future suppression qui refusera réellement. |
| 11 | Un co-propriétaire sanctionné ou inactif (non effectif) ne peut être ni rétrogradé ni retiré par l'équipe tant qu'il reste le seul autre siège (`remove_member` refuse `OWNER`, `change_role` exige un autre propriétaire effectif quand des offres sont actives) | chef de projet | Laissé tel quel en V1 ; à traiter par le chemin de secours audité L1-01j. |
| 12 | Cache partagé entre processus en production : requis par le limiteur d'échecs de ressaisie (`FailureLimiter.acquire`, atomique au sein d'un cache) et par les throttles (D9) | devops | Prérequis de production ; sinon les compteurs sont par processus. |
| 10 | Q-L1-10 : suppression libre-service du compte voulue en V1 ? | client (LEG-PRV) | Hors L1-01 ; aucune livraison sans réponse. |
