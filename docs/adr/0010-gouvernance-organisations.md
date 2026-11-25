# ADR 0010 — Gouvernance des organisations : Administrateur principal, périmètre, invitations v2, anti-abus de création (L1-01-R)

- **Statut :** proposé (décisions 1 à 3 de l'utilisateur du 25/11/2026 appliquées ; points de la section 17 à valider par le chef de projet, ceux marqués « utilisateur » à faire valider par Anicet ou Jonathan)
- **Date :** 25/11/2026
- **Décideurs :** utilisateur (périmètre lot 1, invitation `ADMIN` avec confirmation par l'émetteur, nomination d'un Administrateur principal), chef de projet (recommandations K1, K3, K5, Q17 de l'analyste), architecte technique (rédaction, choix de modèle)
- **Amende :** ADR 0006 §5 (matrice des rôles : libellés, rôle `MEMBER`, périmètre), §4.3 (`Membership`, `IdentitySettings.max_organizations_per_account`), D5, A12 (garde-fou « plafond par compte »), A15 (borne de `contexts/`), §17.2 B (`limits/`) ; ADR 0008 §3.2, §3.3, §3.6, §4.1, §4.3, §5.1, §5.2, §8.2, §9, §12, §15 n°2 ; ADR 0009 §6 (ligne « 10 organisations par compte »), D11 (libellé seulement).
- **Contrat d'API :** `docs/specs/L1-01-contrat-api.md`, section 7 « Amendement ADR 0010 » (à recopier dans les briefs B5 à B10 et F1-bis, F2-bis, F4, F5, F6).
- **Réf. :** réponses du client Q3, Q17, Q21, Q22, Q23, Q26, Q30 (`docs/client/ConnectePlus_Reponses_Consolidees_Q1-Q36.md`, décisions verrouillées) ; analyse d'impact `docs/specs/impact-reponses-client-Q1-Q36.md` (K1 à K7) ; CLAUDE.md §4 (règles 1, 2, 3, 4, 8, 10, 11, 12) et §5 ; ADR 0001, 0003, 0006, 0007, 0008, 0009.

**Hors périmètre** (interfaces seulement, section 15) : fermeture de compte (ADR 0012), cycle de vie et restrictions d'organisation (ADR 0011), plans et passes (ADR 0009), récupération d'autorité, conflits d'autorité et secours d'organisation orpheline (L1-02e, L1-02f, ex-L1-01i, j), noms protégés (L1-02g, ex-L1-01l), délégation datée (L1-02d).

---

## 1. Contexte

L1-01 a livré (B1, B2a, B2b, B4, F1, F2) une équipe à quatre rôles figés (`OWNER` libellé « Propriétaire », `ADMIN`, `EDITOR`, `ANALYST`), sans périmètre, des invitations limitées à éditeur et analyste, une promotion vers `OWNER` en libre-service (ressaisie du mot de passe seule) et un plafond affiché de 10 organisations par compte. Les réponses verrouillées du client contredisent ce modèle :

| Réponse | Exigence | Code livré qui la contredit |
|---|---|---|
| Q3, Q21 | Rôle supérieur « Administrateur principal », jamais « Propriétaire ». Modèle Rôle → Permissions → Périmètre ; branches, sites, départements non exclus du modèle. Pas de « plusieurs propriétaires », mais « un ou plusieurs Administrateurs principaux dûment autorisés lorsque la gouvernance le permet ». Pas d'auto-escalade. | `ROLE_CHOICES` (`capabilities.py`), messages des services, `fr.ts` ; `Membership` sans périmètre. |
| Q23 | Invitation possible comme simple membre, Éditeur, Analyste ou Administrateur selon ce que l'émetteur peut déléguer ; jamais Administrateur principal. Aperçu : émetteur, organisation, rôle, périmètre, accès. | `INVITABLE_ROLES = (EDITOR, ANALYST)` ; aperçu sans périmètre ni accès. |
| Q21, Q30 | Actions sensibles : authentification renforcée, double contrôle ; l'initiateur n'est pas l'unique approbateur de sa demande. | `change_role(..., OWNER)` et `transfer_ownership_to` immédiats. |
| Q22 | Aucun plafond global bas ; anti-abus par limites de débit, signaux, examen humain ; ne pas afficher un seuil de sécurité. | `max_organizations_per_account = 10`, `409 organization_limit_reached`, exposé par `GET organizations/limits/`. |
| Q17 | État « sans administrateur principal / administration à régulariser », cumulable avec une suspension ; aucune promotion automatique. | Orphelinat calculé (`count_effective_owners`) mais ni stocké, ni affiché. |
| Q26 | Revue par l'équipe de vérification pour les organisations à risque élevé ; le modérateur ordinaire ne décide pas de l'autorité. | Aucun niveau de vérification ; aucun groupe « Vérification ». |

**Décisions de l'utilisateur (25/11/2026), appliquées sans nouveau débat :**

- **U1.** Tout est intégré au lot 1 (périmètre dans le modèle, etc.).
- **U2.** Invitation comme Administrateur **autorisée** si l'émetteur peut déléguer ce rôle. Parade au lien porteur : **confirmation par l'émetteur** (ou un Administrateur principal) de qui a rejoint ; aucun droit avant. Administrateur principal jamais par invitation. L'aperçu montre émetteur, organisation, rôle, périmètre et accès.
- **U3.** Nomination d'un Administrateur principal : la personne promue **accepte** ; **tous** les Administrateurs principaux sont notifiés ; **ressaisie du mot de passe** de l'initiateur ; **revue par l'équipe de vérification** seulement pour les organisations à vérification renforcée (banques, finance, Mobile Money, télécoms, ministères, grandes entités publiques ; liste configurable).

**Lecture de Q21 (pluralité).** Je lis comme l'analyste : le client refuse le **concept** de « propriétaire » (propriété juridique ≠ administration de plateforme), pas la pluralité. La phrase « l'autorité supérieure passe par un ou plusieurs Administrateurs principaux dûment autorisés lorsque la gouvernance le permet » autorise explicitement plusieurs Administrateurs principaux ; « dûment autorisés » porte sur la **procédure** d'attribution (U3), pas sur un nombre. Nuance : « lorsque la gouvernance le permet » vise la gouvernance **de l'organisation** (ses statuts). V1 n'impose aucun plafond ; une option par organisation « un seul Administrateur principal » est notée en question (section 17, QG-4).

## 2. Options étudiées

### 2.1 Code technique du rôle supérieur (K1)

| # | Option | Verdict |
|---|---|---|
| A | **Garder `OWNER` en base et dans l'API ; tous les libellés deviennent « Administrateur principal »** | **Retenue.** Le code n'est pas visible du client ; aucune migration de données, aucun changement de contrat sur les valeurs. |
| B | Renommer en `PRIMARY_ADMIN` | Rejetée : migration de données sur `Membership.role`, contrainte `orginv_role_not_owner`, fixtures, contrat front, codes d'erreur ; aucun gain fonctionnel. |

La correspondance est figée ici : **`OWNER` = « Administrateur principal »**. Les codes d'erreur existants (`last_owner`, `last_effective_owner`, `owner_must_be_demoted`), les clés JSON (`is_last_effective_owner`) et les actions d'audit historiques (`ORG_OWNERSHIP_TRANSFERRED`) restent ; seuls les messages changent. Tout **nouveau** identifiant emploie `primary_admin`.

### 2.2 Périmètre (K3)

| # | Option | Verdict |
|---|---|---|
| A | **Périmètre additif sur `Membership`** : `scope_type` (défaut `ORGANIZATION`), `scope_id` nul ; une appartenance = un rôle dans un périmètre | **Retenue.** Migration additive et réversible ; aucune lecture existante ne change ; `ORGANIZATION` seul actif en V1. |
| B | Table `RoleAssignment` (une appartenance porte N couples rôle-périmètre) | Rejetée en V1 : toutes les lectures de rôle (`get_active_role`, `get_user_context_roles`, comptages de `OWNER`, destinataires) seraient réécrites ; aucun écran ne l'exige en V1. Chemin d'évolution documenté en 4.6 (étendre puis contracter). |
| C | Rien en V1 | Rejetée : décision U1 et Q21 (« ne doivent pas être exclus du modèle technique »). |

### 2.3 Représentation de l'adhésion « en attente de confirmation » (U2)

| # | Option | Verdict |
|---|---|---|
| A | Nouveau statut `Membership.PENDING_CONFIRMATION` | Rejetée : même défaut que `INVITED` (ADR 0008 §2 A) : la ligne `(organisation, compte)` existe, R12 (réactivation) et `already_member` doivent l'interpréter, et toute lecture future qui filtrerait `exclude(status=REVOKED)` au lieu de `status=ACTIVE` ouvrirait des droits. |
| B | **L'invitation porte l'attente** : `OrganizationInvitation.status = AWAITING_CONFIRMATION`, avec `accepted_by` ; l'appartenance n'est créée qu'à la confirmation | **Retenue.** Aucune ligne `Membership` avant confirmation : aucun droit possible par construction (échec fermé). Les comptages, destinataires et contextes ne changent pas. |

### 2.4 Nomination d'un Administrateur principal (U3)

| # | Option | Verdict |
|---|---|---|
| A | Garder `PATCH role=OWNER` et ajouter un drapeau « acceptée » | Rejetée : un PATCH qui ne change pas le rôle est trompeur ; pas d'objet pour l'expiration, l'annulation, la revue, l'audit. |
| B | **Objet de demande `PrimaryAdminNomination`** (machine d'états propre : acceptation, revue éventuelle, expiration, annulation, invalidation) | **Retenue.** États indépendants (règle 8) ; la revue du personnel s'y greffe sans toucher `Membership`. |

### 2.5 Anti-abus de création (K5, Q22)

| # | Option | Verdict |
|---|---|---|
| A | Seuil élevé caché, refus neutre au-delà | Rejetée seule : c'est encore un plafond (déguisé). |
| B | **Limites de débit + mise en revue au-delà d'un seuil non affiché + plafond technique haut et caché** (borne de sûreté des listes non paginées) | **Retenue.** Conforme à Q22 (rate limits, signal, examen humain, seuil non affiché). |
| C | Aucune limite | Rejetée : `GET contexts/` n'est pas paginé (ADR 0006 A15) ; une liste non bornée devient un vecteur de déni de service. |

## 3. Décisions

1. **D1 — Libellés.** `OWNER` est libellé « Administrateur principal » partout (back et front). Codes inchangés (2.1).
2. **D2 — Rôle `MEMBER` (« Membre »).** Ajouté, rang 0, capacités `org.view_internal` et `org.leave` seulement. Il matérialise le « simple membre » de Q22 et Q23, qui le cite comme un type d'invitation distinct d'Analyste. Ajout additif (valeur de `choices`, aucune colonne) ; à confirmer par le client (QO-6, section 17), sans bloquer.
3. **D3 — Périmètre.** `Membership.scope_type` / `scope_id` (et les mêmes champs sur l'invitation). Types déclarés : `ORGANIZATION` (actif), `CITY`, `UNIT` (réservés, refusés en V1 par une erreur de champ `400 {"scope": [...]}`). Un Administrateur principal a toujours le périmètre `ORGANIZATION` (contrainte `CHECK` en base). Délégation : `can_delegate(acteur, rôle visé, périmètre visé)` = `can_manage_role_of` **et** `scope_covers(périmètre de l'acteur, périmètre visé)`. L'autorisation par objet reçoit le périmètre de l'objet (`target_scope`, défaut : organisation entière).
4. **D4 — Invitations v2.** Rôles invitables : `ADMIN`, `EDITOR`, `ANALYST`, `MEMBER`, chacun seulement si l'émetteur peut le déléguer (D3). `OWNER` jamais (service + `CHECK` existant). Une invitation `ADMIN` acceptée passe en **`AWAITING_CONFIRMATION`** : aucune appartenance, aucun droit, jusqu'à ce que l'**émetteur** (s'il a toujours l'autorité de déléguer `ADMIN`) ou **un Administrateur principal effectif** confirme, avec ressaisie de son mot de passe, en voyant le nom abrégé et les deux derniers chiffres du téléphone vérifié de la personne qui a accepté (information annoncée à cette personne avant qu'elle accepte). Les autres rôles restent en acceptation directe (ADR 0008). L'aperçu renvoie en plus le périmètre, la liste des capacités et `requires_confirmation`.
5. **D5 — Nomination d'un Administrateur principal.** `PATCH role=OWNER` et `POST transfer-ownership/` sont remplacés par `PrimaryAdminNomination` (genres `PROMOTE` : un Administrateur principal de plus ; `TRANSFER` : l'initiateur se retire au rôle choisi à l'aboutissement). Création par un Administrateur principal effectif, ressaisie de son mot de passe ; **acceptation explicite par la cible** ; notification de **tous** les Administrateurs principaux à chaque étape ; si l'organisation est à **vérification renforcée** (D6), revue par l'équipe Vérification (personne ni membre de l'organisation, ni initiatrice) avant application. Toute condition revérifiée au moment d'appliquer.
6. **D6 — Niveau d'assurance de l'organisation.** `Organization.assurance_level` (`STANDARD`, `ENHANCED`, `PRE_VERIFICATION` : les trois niveaux de Q26). `ENHANCED` ou `PRE_VERIFICATION` = « vérification renforcée » pour D5. Fixé (a) par le personnel Vérification (service audité) ou (b) automatiquement relevé quand l'organisation a une catégorie listée dans `HighAssuranceCategory` (table configurable en back-office). Le niveau stocké ne **baisse jamais** automatiquement (retirer une catégorie sensible ne fait pas sortir de la revue) ; seule une décision du personnel l'abaisse. Ce champ appartient ensuite à L1-02a, qui l'étend sans le redéfinir. Il n'est **ni public, ni achetable, ni un score** (règles 3, 4).
7. **D7 — Rétrogradation d'un autre Administrateur principal.** Organisation `STANDARD` : permise comme aujourd'hui (ressaisie), plus notification de tous les Administrateurs principaux et de la cible. Organisation à vérification renforcée : refusée (`409 primary_admin_change_requires_verification`) et renvoyée au parcours de conflit d'autorité (L1-02e). Se rétrograder soi-même reste permis (sous `last_owner`, `last_effective_owner`).
8. **D8 — Fin du plafond affiché.** `max_organizations_per_account` disparaît de l'API et de toute interface. Remplacements (valeurs **proposées, à confirmer par l'utilisateur**, jamais communiquées aux utilisateurs) :
   - limites de débit de création : `org_create` 5/jour (existant) + `org_create_burst` 2/heure ;
   - **mise en revue** : à partir de la 5e organisation créée par le même compte sur 30 jours glissants, chaque nouvelle création réussit mais l'organisation est **retenue en revue** (`creation_review_status = PENDING`) : utilisable en interne, absente de l'annuaire et des pages publiques, jusqu'à décision du personnel (levée, ou suspension par le chemin existant) ;
   - **plafond technique de sûreté** : 200 appartenances actives par compte (`max_memberships_hard_limit`), refus neutre `409 account_review_required` sans chiffre, à la création comme à l'acceptation ou à la confirmation d'une invitation.
9. **D9 — Organisation sans Administrateur principal.** État stocké `Organization.primary_admin_state` (`OK`, `MISSING`) et `primary_admin_missing_since`. `MISSING` = aucun Administrateur principal **effectif** (définition unique d'ADR 0008 §9). Cumulable avec tout statut (`SUSPENDED`, `ARCHIVED`). **Aucune promotion automatique.** Le service le recalcule dans chaque transaction qui touche un siège d'Administrateur principal ; une commande planifiée le resynchronise (désactivation de compte, sanction, levée de sanction). Il est montré aux membres (bannière « administration à régulariser ») ; la régularisation relève de L1-02f.
10. **D10 — Ce qui ne change pas.** Invitation par lien à usage unique (ADR 0008 D1) ; jeton haché ; `404 invitation_invalid` uniforme ; `last_owner` et `last_effective_owner` pour les départs et rétrogradations **volontaires** (Q24 « avertir et demander régularisation » : la fermeture de compte suit sa propre règle, ADR 0012) ; retrait direct d'un Administrateur principal refusé (`owner_must_be_demoted`) ; `is_staff` n'ouvre rien ; aucun service ne reçoit de plan, prix ou droit commercial (règle 2).

## 4. Modèle de données (domaine `identity`)

Toutes les clés primaires sont des UUID (`BaseModel`). Aucune clé étrangère hors de `identity`, sauf vers `User`. Longueurs explicites ; aucune unicité conditionnelle ; aucune fonction SQL propre à un moteur.

### 4.1 Rôles et capacités (`capabilities.py`, constantes pures)

```python
ROLE_MEMBER = 'MEMBER'
ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR, ROLE_ANALYST, ROLE_MEMBER)
ROLE_CHOICES = ((ROLE_OWNER, "Administrateur principal"), (ROLE_ADMIN, "Administrateur"),
                (ROLE_EDITOR, "Éditeur"), (ROLE_ANALYST, "Analyste"), (ROLE_MEMBER, "Membre"))
ROLE_RANK = {ROLE_OWNER: 4, ROLE_ADMIN: 3, ROLE_EDITOR: 2, ROLE_ANALYST: 1, ROLE_MEMBER: 0}
SCOPE_ORGANIZATION, SCOPE_CITY, SCOPE_UNIT = 'ORGANIZATION', 'CITY', 'UNIT'
ACTIVE_SCOPE_TYPES = (SCOPE_ORGANIZATION,)          # V1
def scope_covers(holder_scope, target_scope) -> bool  # ORGANIZATION couvre tout ; égalité sinon
def can_delegate(actor_role, actor_scope, target_role, target_scope) -> bool
```

Matrice (ADR 0006 §5 amendée ; O = Administrateur principal) :

| Capacité | O | A | E | An | **M** |
|---|---|---|---|---|---|
| `org.view_internal`, `org.leave` | O | O | O | O | **O** |
| toutes les autres | inchangé | inchangé | inchangé | inchangé | **N** |

`MEMBER` n'a ni `stats.view` ni `offer.view_internal` (moindre privilège ; un « simple membre » voit l'espace interne et l'équipe, rien d'autre). `billing.*` (ADR 0009 D11) : inchangé, `MEMBER` = N. `PERSONAL_CAPABILITIES` inchangé. La matrice reste testée case par case (5 rôles × capacités).

`can_manage_role_of` : inchangé pour `OWNER` et `ADMIN` ; `MEMBER` est géré par `OWNER` et `ADMIN` comme `ANALYST`. `can_delegate` ajoute la règle de Q23 : « un administrateur limité à une branche ne crée pas un administrateur global » (`scope_covers` faux). En V1, tous les périmètres valent `ORGANIZATION` : la règle est testée par des tests purs sur des périmètres fictifs `CITY`.

### 4.2 `Membership` (ajouts)

| Champ | Type | Remarques |
|---|---|---|
| `scope_type` | `CharField(20)`, défaut `'ORGANIZATION'`, choix `SCOPE_CHOICES` | V1 : seule valeur acceptée par les services |
| `scope_id` | `UUIDField`, nul | nul pour `ORGANIZATION` ; identifiant de ville (`catalog`, par UUID, sans clé étrangère) ou d'unité (future table `OrganizationUnit`) |
| `role` | choix étendus à `MEMBER` (aucun changement de longueur) | |

Contraintes ajoutées (portables SQLite, MySQL 8.0.16+) :
- `CheckConstraint(~(Q(role='OWNER') & ~Q(scope_type='ORGANIZATION')), name='membership_owner_org_scope')` : un Administrateur principal a toujours le périmètre organisation entière ;
- `CheckConstraint(Q(scope_type='ORGANIZATION', scope_id__isnull=True) | (~Q(scope_type='ORGANIZATION') & Q(scope_id__isnull=False)), name='membership_scope_consistent')`.

Index : aucun nouveau en V1 (`scope_*` n'est jamais filtré tant que `ORGANIZATION` est seul). L'unicité `(organization, user)` reste : en V1, une personne a un seul rôle dans une organisation.

### 4.3 `OrganizationInvitation` (ajouts et changements)

| Champ | Type | Remarques |
|---|---|---|
| `status` | **`CharField(24)`** (au lieu de 10) | valeurs : `PENDING`, `AWAITING_CONFIRMATION`, `ACCEPTED`, `DECLINED`, `REVOKED`, `REJECTED`, `EXPIRED` |
| `scope_type`, `scope_id` | comme 4.2 | périmètre proposé |
| `accepted_by` | FK `User`, `SET_NULL`, nul, `related_name='+'` | personne qui a accepté une invitation à confirmer |
| `accepted_at` | `DateTimeField`, nul | |
| `confirmation_expires_at` | `DateTimeField`, nul | `accepted_at + admin_invitation_confirmation_hours` |
| `confirmed_by` | FK `User`, `SET_NULL`, nul, `related_name='+'` | émetteur ou Administrateur principal qui confirme ou rejette |
| `confirmation_code_hash` | `CharField(64)`, blank | **décision S3 (QG-2)** : empreinte HMAC-SHA256 (clé du projet, sel propre, identifiant de l'invitation) du code de rattachement à 6 chiffres ; vidée à la sortie de l'attente |
| `confirmation_code_failures` | `PositiveSmallIntegerField`, défaut 0 | codes faux saisis sur cette invitation ; au 5e, `REJECTED` (`reason=code_failed`) |

`closed_at`, `closed_by` gardent leur sens (passage à un état terminal). Pour une invitation confirmée : `closed_by` = confirmateur ; `accepted_by` = la personne entrée. `label` est vidé dès la sortie de `PENDING` (inchangé, donc aussi en `AWAITING_CONFIRMATION`). Index ajouté : `orginv_accepted_by (accepted_by, status)` (liste « mes adhésions en attente »). `CheckConstraint` `orginv_role_not_owner` inchangé.

**Constante de service** `CONFIRMATION_REQUIRED_ROLES = (ROLE_ADMIN,)` (liste en service, comme `INVITABLE_ROLES` ; l'élargir ne demande aucune migration). `INVITABLE_ROLES = (ADMIN, EDITOR, ANALYST, MEMBER)`.

### 4.4 `PrimaryAdminNomination` (nouveau)

| Champ | Type | Remarques |
|---|---|---|
| `organization` | FK `Organization`, `CASCADE`, `related_name='primary_admin_nominations'` | |
| `target_membership` | FK `Membership`, `CASCADE`, `related_name='+'` | cible : membre actif au moment de la création |
| `target_user` | FK `User`, `SET_NULL`, nul, `related_name='+'` | copie (audit, notifications, filtre « me concerne ») |
| `initiated_by` | FK `User`, `SET_NULL`, nul, `related_name='+'` | Administrateur principal initiateur |
| `kind` | `CharField(10)` | `PROMOTE`, `TRANSFER` |
| `initiator_new_role` | `CharField(20)`, blank | `TRANSFER` seulement : `ADMIN` (défaut), `EDITOR`, `ANALYST`, `MEMBER` |
| `status` | `CharField(20)` | `PENDING_ACCEPTANCE`, `PENDING_REVIEW`, `COMPLETED`, `DECLINED`, `CANCELLED`, `REJECTED`, `EXPIRED`, `VOID` |
| `requires_review` | `BooleanField` | instantané à la création (D6), recalculé à l'acceptation (le niveau ne baisse pas, donc seulement de faux à vrai) |
| `expires_at` | `DateTimeField` | `created_at + primary_admin_nomination_ttl_days` pour l'acceptation ; puis `+ primary_admin_review_ttl_days` à l'entrée en revue |
| `accepted_at` | `DateTimeField`, nul | |
| `reviewed_by` | FK `User`, `SET_NULL`, nul, `related_name='+'` | membre du personnel Vérification |
| `review_reason` | `CharField(30)`, blank | code fermé (`authority_confirmed`, `authority_not_established`, `documents_required`, `conflict_detected`, `other`) ; jamais de texte libre |
| `closed_at` | `DateTimeField`, nul | |
| `closed_by` | FK `User`, `SET_NULL`, nul, `related_name='+'` | |
| `void_reason` | `CharField(30)`, blank | `target_left`, `target_role_changed`, `target_unavailable`, `initiator_lost_authority`, `organization_unavailable`, `superseded` |

Index : `pan_org_status (organization, status)`, `pan_target_status (target_user, status)`, `pan_status_expires (status, expires_at)`. Permission Django : `('review_primaryadminnomination', "Peut décider d'une nomination d'administrateur principal")`.

**Invariants en service, sous verrou d'organisation (aucune unicité conditionnelle) :** au plus une nomination ouverte (`PENDING_ACCEPTANCE` ou `PENDING_REVIEW`) par cible ; au plus une nomination `TRANSFER` ouverte par organisation.

### 4.5 `Organization` (ajouts)

| Champ | Type | Défaut | Remarques |
|---|---|---|---|
| `assurance_level` | `CharField(20)` | `'STANDARD'` | `STANDARD`, `ENHANCED`, `PRE_VERIFICATION` (D6) ; jamais public |
| `primary_admin_state` | `CharField(10)` | `'OK'` | `OK`, `MISSING` (D9) |
| `primary_admin_missing_since` | `DateTimeField`, nul | | posé au passage à `MISSING`, effacé au retour à `OK` ; lu par L1-17 (délais de restriction puis d'archivage, ADR 0011) |
| `creation_review_status` | `CharField(10)` | `'NONE'` | `NONE`, `PENDING`, `CLEARED` (D8) |

Index : `org_primary_admin_state (primary_admin_state, status)` (file du personnel L1-02f) ; `org_creation_review (creation_review_status)`. Permissions Django ajoutées : `set_assurance_level`, `review_organization_creation`.

### 4.6 `HighAssuranceCategory` (nouveau, règle 11)

`category_id` `UUIDField` **unique** (inconditionnel ; référence `catalog` par UUID, existence vérifiée par `catalog.services`), `level` `CharField(20)` (`ENHANCED` ou `PRE_VERIFICATION`), `note` `CharField(120)`, blank. Édité dans l'admin Django (groupe Vérification), changements audités (`record_settings_change`). Aucune valeur semée : la liste est fournie par le client et saisie en back-office (Q25, Q26 : banques, Mobile Money, télécoms, ministères…). **Limite connue :** les catégories du catalogue sont commerciales ; une banque peut n'en porter aucune « sensible ». Le relèvement manuel par le personnel (D6 a) et, plus tard, les noms protégés (L1-02g) couvrent ce cas.

### 4.7 `IdentitySettings` (règle 11)

| Champ | Type | Défaut proposé | Bornes | Visible des utilisateurs |
|---|---|---|---|---|
| `max_organizations_per_account` → **renommé** `max_memberships_hard_limit` | PositiveInteger | **200** | 50 à 1 000 | **jamais** |
| `org_creation_review_window_days` | PositiveSmallInteger | 30 | 1 à 365 | jamais |
| `org_creation_review_threshold` | PositiveSmallInteger | 5 | 2 à 100 | jamais |
| `admin_invitation_confirmation_hours` | PositiveSmallInteger | 72 | 1 à 336 | oui (date d'échéance renvoyée, pas la règle) |
| `primary_admin_nomination_ttl_days` | PositiveSmallInteger | 7 | 1 à 30 | oui (date d'échéance) |
| `primary_admin_review_ttl_days` | PositiveSmallInteger | 30 | 1 à 180 | oui (date d'échéance) |

Texte d'aide des trois premiers : « Seuil de sécurité interne : ne jamais le communiquer comme une limite. » Toutes les valeurs sont **provisoires, à confirmer** (Q22 demande à l'équipe de proposer).

### 4.8 Évolution prévue (non livrée)

- **Plusieurs rôles par personne et par organisation** : table `RoleAssignment(membership, role, scope_type, scope_id, expires_at)` ; migration « étendre » (copie de `Membership.role/scope_*`), lecture double, puis « contracter ». Les fonctions `get_active_role`, `get_user_context_roles`, `count_*_owners`, `get_organization_recipients` sont les seuls points de lecture à réécrire (liste tenue dans la docstring de `capabilities.py`).
- **Unités** : table `OrganizationUnit(organization, unit_type BRANCH|SITE|DEPARTMENT, name, parent, city_id)` ; `scope_type='UNIT'` devient actif.
- **Délégation datée** (Q3) : `Membership.expires_at` avec un gestionnaire `Membership.objects.effective()` utilisé par toutes les lectures ; L1-02d.
- **Avant d'activer `CITY` ou `UNIT`** (note L1-01-B6) : en V1 le périmètre est **fermé par défaut** ; une appartenance non `ORGANIZATION` n'a que `org.leave`. Points d'application : `capabilities.scope_allows` (règle unique), `acting.authorize` / `authorize_on` / `can` (via `ActingContext.scope_type`, `scope_id`), `organizations._authorize_member`, `sellers.get_user_context_roles` (rôle nul), `sellers.org_capability_scope_q` (destinataires : `get_context_recipients`, `_organizations_with_team`, `get_accessible_organization_ids`, `context_reads.get_organization_recipients`), `acting.get_contexts_for_user` (capacités affichées), invitations (`_inviter_has_authority`, `create_invitation`, `sweep_invitations_of_inviter`). Pour activer un type : (1) l'ajouter à `ACTIVE_SCOPE_TYPES` ; (2) donner à chaque objet métier son périmètre (ville d'une offre, unité) et le passer en `target_scope` à `authorize_on`/`can` ou aux lectures par lot ; (3) remplacer le rôle nul de `get_user_context_roles` et le filtre `scope_type=ORGANIZATION` des destinataires par un calcul objet par objet ; (4) accepter `scope` en entrée des invitations (B7) et du PATCH ; (5) définir la hiérarchie éventuelle (une unité dans une ville) dans `scope_covers` ; (6) revoir les listes (`members/`, marketplace `my_posts`, statistiques) pour les filtrer par périmètre plutôt que les refuser.

## 5. Machines d'états

### 5.1 Invitation (ADR 0008 §4.3 amendé)

```
PENDING --accept (rôle sans confirmation)--> ACCEPTED                    (cible ; appartenance créée)
PENDING --accept (rôle ADMIN)-------------> AWAITING_CONFIRMATION       (cible ; aucune appartenance)
PENDING --decline--> DECLINED   PENDING --revoke--> REVOKED   PENDING --cron--> EXPIRED
AWAITING_CONFIRMATION --confirm--> ACCEPTED   (émetteur autorisé ou Administrateur principal effectif, ressaisie ; appartenance créée)
AWAITING_CONFIRMATION --reject---> REJECTED   (idem, sans ressaisie)
AWAITING_CONFIRMATION --withdraw-> DECLINED   (la personne qui a accepté)
AWAITING_CONFIRMATION --cron / lecture après confirmation_expires_at--> EXPIRED
AWAITING_CONFIRMATION --5e code de rattachement faux--> REJECTED   (reason=code_failed ; décision S3)
AWAITING_CONFIRMATION --émetteur retiré, ou désactivé / sanctionné--> REJECTED   (reason=authority_lost ; décision S3)
AWAITING_CONFIRMATION --balayage (organisation non ACTIVE, émetteur ET tous les Administrateurs principaux sans autorité)--> reste, mais inconfirmable ; expire normalement
ACCEPTED, DECLINED, REVOKED, REJECTED, EXPIRED : terminaux
```

Une `AWAITING_CONFIRMATION` n'est pas révocable par `DELETE` (`409 invitation_not_pending`) : on la **rejette** (le rejet trace un motif humain distinct). Le balayage `sweep_invitations_of_inviter` ne touche que `PENDING` : une invitation en attente de confirmation peut encore être confirmée par un Administrateur principal après le **départ volontaire** ou la **rétrogradation** de l'émetteur (U2 « ou un administrateur principal »). **Amendement S3 (L1-01-B7)** : si l'émetteur est **retiré** de l'organisation (même transaction que le retrait) ou si son compte est **désactivé**, y compris par une sanction bloquante (après la transaction de `set_account_active`, organisation par organisation), ses attentes passent à `REJECTED` (`reason=authority_lost`) : on ne laisse pas entrer quelqu'un sur la foi d'un émetteur écarté. La liste des invitations expose `inviter_has_authority` (calcul par lot) pour avertir dans les autres cas. Les invitations ouvertes (`PENDING` et `AWAITING_CONFIRMATION` non échues) comptent dans `max_pending_invitations`.

### 5.2 Nomination d'un Administrateur principal

```
(création, ressaisie) -> PENDING_ACCEPTANCE
PENDING_ACCEPTANCE --accept (cible), requires_review faux--> COMPLETED      (rôles appliqués)
PENDING_ACCEPTANCE --accept (cible), requires_review vrai--> PENDING_REVIEW
PENDING_ACCEPTANCE --decline (cible)--> DECLINED
PENDING_ACCEPTANCE | PENDING_REVIEW --cancel (initiateur ou tout Administrateur principal effectif)--> CANCELLED
PENDING_REVIEW --approve (Vérification)--> COMPLETED                         (rôles appliqués)
PENDING_REVIEW --reject (Vérification)--> REJECTED
PENDING_* --expires_at dépassé (cron ; lecture : présentée EXPIRED)--> EXPIRED
PENDING_* --invalidation dans la transaction qui la provoque--> VOID (void_reason)
COMPLETED, DECLINED, CANCELLED, REJECTED, EXPIRED, VOID : terminaux
```

Invalidations (`VOID`, même transaction que la cause) : la cible quitte, est retirée ou change de rôle (`target_left`, `target_role_changed`) ; l'initiateur cesse d'être Administrateur principal (`initiator_lost_authority`, sauf la nomination `TRANSFER` en cours d'application) ; une autre nomination aboutit pour la même cible (`superseded`). Compte cible désactivé ou restreint, organisation suspendue ou archivée : **pas** d'invalidation immédiate (ces états sont réversibles) ; l'application est refusée tant qu'ils durent, la nomination expire sinon.

### 5.3 État de gouvernance (D9)

```
OK --(dernier Administrateur principal effectif perdu : départ hors V1 volontaire, désactivation, sanction, fermeture de compte ADR 0012)--> MISSING
MISSING --(un Administrateur principal redevient effectif : levée de sanction, réactivation, récupération L1-02f)--> OK
```

Aucune transition `MISSING -> OK` par promotion d'un membre existant (Q17) : les nominations exigent un initiateur Administrateur principal effectif, et il n'y en a pas. Seul L1-02f (personnel Vérification) attribue un siège dans cet état.

## 6. Services (`identity/organizations.py`, `identity/invitations.py`, nouveau `identity/governance.py` ; exposés par `identity/services.py`)

Règles communes (ADR 0008 §5) : `transaction.atomic()`, `_lock_organization` en premier, autorisation recalculée sous verrou, audit synchrone avec contexte, événement outbox dans la même transaction ; ressaisie du mot de passe **avant** le verrou ; ordre de verrouillage unique : organisation, puis invitation ou nomination, puis appartenances, puis comptes. Aucun service ne reçoit de plan ni de prix.

### 6.1 Rôles et périmètre

- `_validate_role(role)` accepte `MEMBER`. `_validate_scope(scope)` : absent = `ORGANIZATION` ; type hors `ACTIVE_SCOPE_TYPES` -> erreur de champ `400 {"scope": ["..."]}`.
- `change_role(actor, org_id, membership_id, new_role, scope=None, confirm, password)` : `new_role == OWNER` -> `400 use_primary_admin_nomination` (avant toute ressaisie) ; cible `OWNER` différente de l'acteur et organisation `assurance_level != STANDARD` -> `409 primary_admin_change_requires_verification` ; cible `OWNER` (soi-même ou autre, organisation `STANDARD`) : ressaisie comme aujourd'hui ; contrôle `can_delegate` sur le rôle et le périmètre visés ; après écriture : invariants, `_refresh_primary_admin_state`, `void_nominations_for_target`, notification `owners_changed`.
- `authorize_on(user, ctx_type, ctx_id, capability, target_scope=None, ...)` et `can(...)` : paramètre additif ; `target_scope=None` = organisation entière ; refus `DENY_PERMISSION` si `scope_covers` faux. Aucun appelant actuel ne change (défaut).
- `get_role_label(role)` : libellés de 4.1 (notifications).

### 6.2 Invitations

- `create_invitation(actor, org_id, role, label='', scope=None, after_authorization=None)` : `role in INVITABLE_ROLES` **et** `can_delegate(...)`, sinon `400 invitation_role_not_allowed` ; `OWNER` idem. Pas de ressaisie à la création (aucun droit n'est ouvert à ce stade ; la ressaisie est à la confirmation).
- `preview_invitation(user, token)` : ajoute `scope`, `capabilities` (= `capabilities_for_role(role)`), `requires_confirmation`. Validité : `role in INVITABLE_ROLES` et autorité de l'émetteur (`can_delegate`) ; inchangé sinon.
- `accept_invitation(user, token)` : étapes 1 à 3 d'ADR 0008 §5.1 inchangées jusqu'aux contrôles propres à la cible (compte restreint, téléphone, **plafond technique** `account_review_required`, déjà membre). Puis :
  - rôle hors `CONFIRMATION_REQUIRED_ROLES` : comme aujourd'hui (`ACCEPTED`, `_activate_membership`) ;
  - rôle `ADMIN` : la prise conditionnelle écrit `AWAITING_CONFIRMATION`, `accepted_by`, `accepted_at`, `confirmation_expires_at` ; **aucune** appartenance ; audit `INVITATION_ACCEPTED_AWAITING_CONFIRMATION` ; événement `awaiting_confirmation` ; réponse 202. Une même personne ne peut avoir qu'une invitation `AWAITING_CONFIRMATION` par organisation : sinon `409 already_awaiting_confirmation` (contrôle en service sous verrou d'organisation).
- `confirm_invitation(actor, org_id, invitation_id, confirm, password)` : ressaisie (avant verrou) ; sous verrou : invitation de cette organisation (`404 invitation_not_found`) en `AWAITING_CONFIRMATION` non échue (`409 invitation_not_awaiting_confirmation`) ; acteur = émetteur ayant toujours `can_delegate(ADMIN, scope)`, **ou** Administrateur principal effectif, sinon `403 DENY_PERMISSION` ; l'acteur n'est jamais la personne qui a accepté (impossible de toute façon : elle n'est pas membre) ; contrôles de la personne entrée **revérifiés** (active, non restreinte, téléphone vérifié, plafond technique, pas déjà membre) : `400 user_unavailable` (réponse neutre), `409 already_member` ; mise à jour conditionnelle `AWAITING_CONFIRMATION -> ACCEPTED` ; `_activate_membership(actor=confirmateur, target=accepted_by, role, added_by=émetteur, via='invitation')` ; audits `INVITATION_CONFIRMED` et `MEMBERSHIP_ADDED` ; événements `confirmed` et `membership_changed` (`added`).
- `reject_invitation(actor, org_id, invitation_id)` : mêmes acteurs, sans ressaisie ; `AWAITING_CONFIRMATION -> REJECTED` ; audit `INVITATION_REJECTED` ; événement `rejected` (la personne est notifiée sans nom du confirmateur).
- `list_my_awaiting_invitations(user)`, `withdraw_awaiting_invitation(user, invitation_id)` (`AWAITING_CONFIRMATION -> DECLINED`, audit `INVITATION_WITHDRAWN`, événement `declined`).
- `phone_hint(user) -> str` : `"••" + deux derniers chiffres` du téléphone de connexion vérifié ; renvoyé **seulement** dans la liste des invitations `AWAITING_CONFIRMATION`, aux seuls acteurs habilités à confirmer. Relu **en direct** sur le compte (jamais figé à l'acceptation) : simple indice, la preuve est le code de rattachement.
- **Code de rattachement (décision S3, QG-2 tranché)** : tiré par `secrets` à l'acceptation d'une invitation `ADMIN`, renvoyé dans la seule réponse 202 (et par `regenerate_confirmation_code`, qui invalide l'ancien sans remettre le compteur à zéro). `confirm_invitation` exige `code` (`400 confirmation_code_required` avant la ressaisie), le compare à temps constant après la ressaisie et sous verrou ; code faux : `400 confirmation_code_invalid`, essai décompté et tracé (`INVITATION_CONFIRMATION_CODE_FAILED`, jamais le code ; l'erreur est levée après la transaction pour conserver le compteur) ; 5e faux : `REJECTED`, `409 confirmation_code_exhausted`, notification neutre. Jamais dans l'audit, l'outbox, les notifications, les journaux (`sensitive_post_parameters('password', 'code')`).

### 6.3 Nominations (`identity/governance.py`)

- `create_primary_admin_nomination(actor, org_id, membership_id, kind, my_new_role=None, confirm, password)` : ressaisie (avant verrou, action d'audit `promote_owner` ou `transfer`) ; sous verrou : acteur Administrateur principal **effectif** (`org.manage_roles` et rôle `OWNER`, compte actif non restreint), organisation `ACTIVE` (suspendue `DENY_SECURITY`, archivée `DENY_OBJECT_STATE` ; le transfert depuis une organisation archivée, permis par ADR 0008, est **retiré** : l'archivée relève d'ADR 0011) ; cible active de cette organisation, ni soi ni déjà `OWNER` (`400 invalid_nomination`), disponible (`400 user_unavailable`) ; invariants 4.4 (`409 nomination_already_open`) ; `requires_review = assurance_level_effective(org) != STANDARD` ; création ; audit ; événement `requested` (notifie cible et tous les Administrateurs principaux).
- `accept_primary_admin_nomination(user, org_id, nomination_id, confirm)` : `confirm: true` (pas de mot de passe : la cible reçoit un rôle, elle n'en donne pas) ; sous verrou : nomination ouverte de cette organisation dont `user` est la cible (`404 nomination_not_found` sinon, y compris pour un autre membre) ; `PENDING_ACCEPTANCE` non échue (`409 nomination_not_pending`) ; **revalidation complète** (cible toujours membre actif au même rôle, disponible ; initiateur toujours Administrateur principal effectif ; organisation `ACTIVE`), sinon `VOID` ou refus ; si `requires_review` (recalculé) : `PENDING_REVIEW` ; sinon `_apply_nomination` ; audit ; événements.
- `_apply_nomination(nomination, actor)` : `_apply_role_change(target, OWNER)` (forcer `scope = ORGANIZATION`) ; si `TRANSFER` : `_apply_role_change(initiateur, initiator_new_role)` ; invariants `last_owner`, `last_effective_owner` ; `_refresh_primary_admin_state` ; `ORG_PRIMARY_ADMIN_NOMINATION_COMPLETED` (+ `ORG_OWNERSHIP_TRANSFERRED` conservé pour `TRANSFER`, compatibilité des rapports) ; un seul `owners_changed` ; `void_nominations_for_target` sur les autres nominations ouvertes de la cible (`superseded`).
- `decline_primary_admin_nomination(user, ...)`, `cancel_primary_admin_nomination(actor, ...)` (initiateur ou tout Administrateur principal effectif).
- `review_primary_admin_nomination(staff, nomination_id, decision, reason_code)` : permission `identity.review_primaryadminnomination` ; **conflit d'intérêts** : le réviseur n'est ni membre actif de l'organisation, ni l'initiateur, ni la cible (`403 DENY_PERMISSION`) ; `APPROVE` : revalidation complète puis `_apply_nomination` ; `REJECT` : `REJECTED` ; audit avec `review_reason`.
- `void_nominations_for_target(actor, organization, user_id, reason)` et `void_nominations_by_initiator(...)` : appelées par `_apply_role_change` et `_end_membership` (même transaction).
- `assurance_level_effective(org)` = max(`org.assurance_level`, niveau de ses catégories dans `HighAssuranceCategory`) ; `update_organization` relève `assurance_level` stocké si une catégorie sensible est ajoutée (jamais de baisse).
- `set_organization_assurance_level(staff, org_id, level, reason_code)` : permission `identity.set_assurance_level` ; audit `ORG_ASSURANCE_LEVEL_CHANGED` ; si le niveau devient renforcé, les nominations `PENDING_ACCEPTANCE` passent `requires_review = vrai`.
- `expire_primary_admin_nominations(now)` (cron).

### 6.4 Création et anti-abus (D8)

- `create_organization` : `_ensure_under_limit` devient `_ensure_under_hard_limit` (même verrou de compte, réglage `max_memberships_hard_limit`, erreur `409 account_review_required` neutre) ; puis comptage des organisations créées par le compte sur la fenêtre (`created_by = compte`, `created_at >= now - window`, tous statuts) ; si `>= org_creation_review_threshold` : `creation_review_status = PENDING`, audit `ORG_CREATION_HELD_FOR_REVIEW` (`count` non journalisé : seulement `threshold_reached=true`), événement `identity.organization_governance_changed` (`creation_review`). La double soumission idempotente (L009-02) n'est pas comptée.
- `clear_organization_creation_review(staff, org_id)` : permission `identity.review_organization_creation` ; `PENDING -> CLEARED` ; audit `ORG_CREATION_REVIEW_CLEARED` ; événement de visibilité (`seller_context_status_changed`, raison `creation_review_cleared`). Refus : le personnel suspend par le chemin existant (`suspend_organization`, motif `moderation`).
- Visibilité publique : `is_seller_context_public` et l'annuaire `GET organizations/` excluent `creation_review_status = PENDING` (même mécanique que la règle « propriétaire effectif », sous-requête sans requête par ligne). Les offres publiées par une organisation en revue sont non publiques (`seller_is_public = False`), rattrapées par `sync_seller_visibility`.

### 6.5 État de gouvernance (D9)

- `_refresh_primary_admin_state(organization, actor)` : appelé sous verrou après toute écriture qui touche un siège `OWNER` (changement de rôle, départ, nomination appliquée, et plus tard fermeture de compte ADR 0012, récupération L1-02f) ; compare `count_effective_owners` à l'état stocké ; à chaque changement : écriture, audit `ORG_PRIMARY_ADMIN_STATE_CHANGED`, événement `identity.organization_governance_changed`.
- Commande `sync_organization_governance` (horaire) : (1) recalcul par lots de `primary_admin_state` pour toutes les organisations (lecture par lot `effective_owner_ids_by_organization`, 500 par lot), écriture et événement seulement en cas d'écart ; (2) `expire_primary_admin_nominations` ; (3) suppression des nominations closes depuis plus de `invitation_history_days` jours (l'audit reste). Idempotente. Rattrape les désactivations et sanctions, dont `moderation` n'informe pas `identity` par événement aujourd'hui.
- Abonné `identity.on_account_status_changed` (événement existant `seller_context_status_changed`, raisons `account_deactivated`, `account_reactivated`) : recalcul immédiat des organisations du compte (optimisation ; la commande reste le filet).

## 7. Événements de domaine (outbox, ADR 0003)

| Type | Version | Charge utile (UUID et codes seulement) | Abonnés |
|---|---|---|---|
| `identity.organization_invitation_changed` (existant) | 1 | clés existantes ; **valeurs additives** de `change` : `awaiting_confirmation`, `confirmed`, `rejected` ; **clé additive** `accepted_by_id` (pour ces trois valeurs) | `notifications.notify_invitation_outcome` (étendu) |
| `identity.membership_changed` (existant) | 1 | inchangé ; à la confirmation : `actor_id` = émetteur (comme ADR 0008 §6), `via = "invitation"`, **clé additive `confirmed: true`** (L1-01-B7) : `notify_membership_change` n'envoie alors pas « Vous avez rejoint… » | inchangés |
| `identity.primary_admin_nomination_changed` (**nouveau**) | 1 | `organization_id`, `nomination_id`, `kind`, `change` (`requested`, `accepted`, `review_requested`, `completed`, `declined`, `cancelled`, `rejected`, `expired`, `voided`), `target_user_id`, `initiator_id`, `actor_id`, `requires_review` | `notifications.notify_primary_admin_nomination` (nouveau) |
| `identity.organization_governance_changed` (**nouveau**) | 1 | `organization_id`, `change` (`primary_admin_missing`, `primary_admin_restored`, `creation_review`, `creation_review_cleared`), `actor_id` | `notifications.notify_governance_change` (nouveau) ; L1-02f et ADR 0011 s'y abonneront |
| `identity.seller_context_status_changed` (existant) | 1 | nouvelle valeur de `reason` : `creation_review_cleared` (et `owners_changed` inchangé) | `marketplace.sync_seller_visibility` (recalcule, ignore le motif) : aucun changement d'abonné |

Déclarations dans `platform_core/catalog.py` (contrôle `platform_core.E001` vert). L'expiration par cron n'émet aucun événement pour les invitations (ADR 0008) ; pour les nominations elle émet `expired` (peu nombreuses ; l'initiateur doit savoir). Jamais dans une charge utile : nom, téléphone, indice de téléphone, e-mail, jeton, étiquette, mot de passe.

**Notifications (textes neutres, sans nom de personne ; lien `/organizations/<uuid>/team`) :**

| Événement | Destinataires | Texte |
|---|---|---|
| invitation `awaiting_confirmation` | émetteur (s'il peut encore confirmer) **et** tous les Administrateurs principaux effectifs | « Une invitation comme Administrateur pour « {organisation} » a été acceptée. Confirmez l'identité de la personne avant de lui ouvrir l'accès. » |
| invitation `confirmed` / `rejected` | la personne qui a accepté (contexte personnel pour `rejected`) ; pour `confirmed`, les comptes qui pouvaient confirmer (émetteur habilité, Administrateurs principaux effectifs), sauf l'auteur | « Votre accès à « {organisation} » est confirmé. » (**seule** notification de la personne, décision du chef de projet) / « Votre demande pour rejoindre « {organisation} » n'a pas été confirmée. » (aussi pour un rejet automatique : `code_failed`, `authority_lost`) |
| nomination `requested` | cible ; tous les Administrateurs principaux effectifs (initiateur exclu) | « Vous êtes proposé(e) comme administrateur principal de « {organisation} ». » / « Une nomination d'administrateur principal est en cours pour « {organisation} ». » |
| nomination `review_requested`, `completed`, `declined`, `cancelled`, `rejected`, `expired`, `voided` | initiateur, cible, tous les Administrateurs principaux effectifs (l'acteur exclu) | textes par `change` dans `notifications/events.py` |
| D7 : rétrogradation d'un autre Administrateur principal (`membership_changed` `role_changed` avec `old_role = OWNER`) | tous les Administrateurs principaux restants (en plus de la cible, déjà notifiée) | « Un administrateur principal de « {organisation} » a changé de rôle. » |
| gouvernance `primary_admin_missing` | membres actifs `OWNER` et `ADMIN` | « « {organisation} » n'a plus d'administrateur principal actif. L'administration doit être régularisée. » (lien vers l'aide, L1-21) |
| gouvernance `creation_review` | créateur | « « {organisation} » est en cours d'examen par l'équipe Connecte+. Elle n'apparaît pas encore publiquement. » |

## 8. Journal d'audit (règle 12)

`details` au format `clé=valeur; …`, UUID et codes seulement ; jamais de nom, téléphone, indice de téléphone, e-mail, jeton, étiquette, mot de passe. `AuditLog.action` est un champ libre : aucune migration `moderation`.

| Action | Acteur | Cible | `details` |
|---|---|---|---|
| `INVITATION_CREATED` (existant) | émetteur | invitation | + `scope_type; scope_id` |
| `INVITATION_ACCEPTED_AWAITING_CONFIRMATION` | personne qui accepte | invitation | `organization; role; invited_by` |
| `INVITATION_CONFIRMED` | confirmateur | invitation | `organization; role; accepted_by; invited_by; confirmer_basis=inviter\|primary_admin; reauth=true` |
| `INVITATION_REJECTED` | confirmateur | invitation | `organization; role; accepted_by` |
| `INVITATION_WITHDRAWN` | personne qui avait accepté | invitation | `organization; role` |
| `INVITATION_CONFIRMATION_CODE_FAILED` (S3) | confirmateur | invitation | `organization; role; failures=<n>` |
| `INVITATION_CONFIRMATION_CODE_REGENERATED` (S3) | personne qui avait accepté | invitation | `organization; role` |
| `INVITATION_REJECTED` automatique (S3) | auteur du retrait, de la désactivation ou du 5e code faux (nul pour un système) | invitation | `organization; role; accepted_by; reason=authority_lost\|code_failed` |
| `INVITATION_REFUSED` (existant) | cible | invitation | nouvelles raisons : `hard_limit`, `already_awaiting` |
| `MEMBERSHIP_ADDED`, `MEMBERSHIP_ROLE_CHANGED` (existants) | | | + `scope_type` quand ≠ `ORGANIZATION` |
| `ORG_PRIMARY_ADMIN_NOMINATION_REQUESTED` | initiateur | nomination | `organization; target_user; kind; requires_review; reauth=true` |
| `ORG_PRIMARY_ADMIN_NOMINATION_ACCEPTED` / `_DECLINED` / `_CANCELLED` / `_EXPIRED` / `_VOIDED` | acteur (nul pour le cron) | nomination | `organization; kind; reason=<void_reason>` le cas échéant |
| `ORG_PRIMARY_ADMIN_NOMINATION_REVIEWED` | personnel | nomination | `organization; decision=approve\|reject; review_reason` |
| `ORG_PRIMARY_ADMIN_NOMINATION_COMPLETED` | acceptant ou personnel | nomination | `organization; target_user; kind; initiator; initiator_new_role` |
| `ORG_OWNERSHIP_TRANSFERRED` (existant) | idem | organisation | conservé pour `TRANSFER` |
| `ORG_SENSITIVE_REAUTH_FAILED` (existant) | | | nouvelles valeurs `action=confirm_admin_invitation\|nominate_primary_admin` |
| `ORG_ASSURANCE_LEVEL_CHANGED` | personnel ou système | organisation | `old=; new=; reason=<code>\|category` |
| `ORG_CREATION_HELD_FOR_REVIEW`, `ORG_CREATION_REVIEW_CLEARED` | système / personnel | organisation | `threshold_reached=true` / — |
| `ORG_PRIMARY_ADMIN_STATE_CHANGED` | acteur ou système | organisation | `old=OK; new=MISSING; cause=membership\|sync` |

## 9. Permissions, ressaisie, throttles

### 9.1 Opérations

| Opération | Qui | Règles (sous verrou) |
|---|---|---|
| Changer un rôle (hors `OWNER`) | `org.manage_roles` | `can_delegate` sur rôle courant et visé, périmètre ; D7 pour la cible `OWNER` |
| Inviter | `org.manage_members` | `role in INVITABLE_ROLES` et `can_delegate` |
| Confirmer, rejeter une invitation `AWAITING_CONFIRMATION` | émetteur avec `can_delegate(ADMIN)` toujours vrai, ou Administrateur principal effectif | confirmer : ressaisie |
| Lister les invitations (dont indice de téléphone) | `org.manage_members` ; l'indice n'est servi que si l'appelant peut confirmer **cette** invitation | |
| Créer une nomination | Administrateur principal effectif | ressaisie |
| Lister les nominations | `org.view_internal` ; `OWNER` et `ADMIN` voient toutes celles de l'organisation, les autres rôles seulement celles qui les visent | |
| Accepter, refuser une nomination | la cible seulement | `confirm: true` pour accepter |
| Annuler une nomination | initiateur ou Administrateur principal effectif | |
| Décider d'une nomination en revue | personnel, permission `identity.review_primaryadminnomination`, hors conflit d'intérêts | groupe « Vérification » |
| Niveau d'assurance, levée de revue de création | personnel, permissions `identity.set_assurance_level`, `identity.review_organization_creation` | groupe « Vérification » |

`setup_roles` : nouveau groupe **« Vérification »** (`identity.primaryadminnomination` : `view`, `review` ; `identity.organization` : `view`, `set_assurance_level`, `review_organization_creation` ; `identity.highassurancecategory` : `view`, `add`, `change`, `delete` ; `identity.membership` : `view`). Le groupe « Modérateur » ne reçoit **aucune** de ces permissions (Q26 : le modérateur ne décide pas de l'autorité). Le groupe « Administrateur » n'en hérite pas non plus (séparation des fonctions ; un même compte du personnel peut appartenir aux deux groupes, décision d'organisation interne). L1-02a rattachera la revue des pièces KYB à ce groupe.

### 9.2 Ressaisie du mot de passe (ADR 0008 §8.2, portée amendée)

Exigée pour : créer une nomination (les deux genres) ; confirmer une invitation `ADMIN` ; rétrograder un Administrateur principal (soi-même ou un autre, organisation `STANDARD`). N'est **plus** exigée pour : `PATCH role=OWNER` (route refusée), `transfer-ownership/` (supprimée). Même limiteur `org_reauth`, même audit d'échec.

### 9.3 Throttles (taux proposés, à confirmer)

| Scope | Taux | Clé | Routes |
|---|---|---|---|
| `org_create` (existant) | 5/jour | compte | `POST organizations/` |
| `org_create_burst` (**nouveau**) | 2/heure | compte | idem |
| `org_sensitive` (existant) | 10/heure | compte | confirmation d'invitation, création de nomination, rétrogradation d'un Administrateur principal |
| `org_write` (existant) | 30/heure | compte | rejet d'invitation, acceptation, refus, annulation de nomination, retrait d'adhésion en attente |
| `nomination_create_org` (**nouveau**) | 5/jour | organisation (compté après autorisation, comme `invitation_create_org`) | création de nomination |
| `staff_review` (**nouveau**) | 300/heure | compte du personnel | décisions du personnel |

Prérequis de production inchangé (D9 d'ADR 0008) : cache partagé entre processus.

## 10. Migrations, commandes, retour arrière

Une seule tâche touche `identity/migrations/` à la fois ; chaque migration est appliquée sur une base SQLite vierge ; `makemigrations --check --dry-run` vert. Numérotation indicative (la dernière livrée est `0016_identitysettings_invitations`).

| Migration | Tâche | Contenu | Retour arrière |
|---|---|---|---|
| `0017_role_labels` | B5 | `AlterField` des `choices` de `Membership.role` et `OrganizationInvitation.role` (libellé « Administrateur principal ») | sans effet en base ; réversible |
| `0018_membership_scope_member_role` | B6 | `choices` + `MEMBER` ; `AddField` `scope_type` (défaut `ORGANIZATION`), `scope_id` sur `Membership` et `OrganizationInvitation` ; deux `CheckConstraint` 4.2 | `RemoveConstraint`, `RemoveField` ; **garde de données** : la migration inverse échoue avec un message explicite s'il existe une appartenance ou une invitation `MEMBER` ou un périmètre ≠ `ORGANIZATION` |
| `0019_invitation_confirmation` | B7 | `AlterField status` 10 -> 24 ; `AddField` `accepted_by`, `accepted_at`, `confirmation_expires_at`, `confirmed_by` ; index `orginv_accepted_by` ; `IdentitySettings.admin_invitation_confirmation_hours` | inverse : garde (refuse s'il existe des lignes `AWAITING_CONFIRMATION` ou `REJECTED`), puis retrait ; `AlterField` 24 -> 10 sûr après la garde |
| `0020_invitation_confirmation_code` | B7 (correction S3) | `AddField` `confirmation_code_hash`, `confirmation_code_failures` | retrait des deux colonnes. **Les numéros suivants (B8, B9, B10) sont décalés d'un cran** (0021 à 0023). |
| `0020_creation_antiabuse` | B8 | `RenameField max_organizations_per_account -> max_memberships_hard_limit`, `AlterField` (défaut 200, bornes 50 à 1 000) ; **`RunPython`** : valeur existante portée à `max(valeur, 200)` ; `AddField` `org_creation_review_window_days`, `org_creation_review_threshold`, `Organization.creation_review_status`, index ; permission `review_organization_creation` | inverse : `RunPython` inverse sans effet (la valeur reste ; documenté) ; `RenameField` inverse ; retrait des champs |
| `0021_primary_admin_nomination` | B9 | `Organization.assurance_level` ; `HighAssuranceCategory` ; `PrimaryAdminNomination` (+ index, permission) ; permission `set_assurance_level` ; réglages `primary_admin_nomination_ttl_days`, `primary_admin_review_ttl_days` | suppression des tables et champs (aucune donnée de production, ADR 0002) |
| `0022_primary_admin_state` | B10 | `Organization.primary_admin_state`, `primary_admin_missing_since`, index ; **`RunPython`** de remplissage : `MISSING` si aucune appartenance `OWNER` `ACTIVE` dont le compte est actif (les sanctions ne sont pas lisibles depuis une migration : la première exécution de `sync_organization_governance` corrige) | retrait des champs |

**Données existantes.** Aucune donnée de production (ADR 0002). Les organisations à plusieurs `OWNER` (obtenus par promotion sous ADR 0008) deviennent, **sans écriture**, des organisations à plusieurs Administrateurs principaux : le code est le même. Aucune revue rétroactive (risque accepté, section 16). Les invitations `PENDING` existantes reçoivent `scope_type = ORGANIZATION` par défaut ; leur rôle (`EDITOR`, `ANALYST`) est inchangé.

**Commandes planifiées.** `expire_invitations` (existante) : ajoute `AWAITING_CONFIRMATION` échues -> `EXPIRED`. `sync_organization_governance` (**nouvelle**, horaire `17 * * * *`) : 6.5. Ajout à `backend/cron/crontab` et à `SCHEDULED_COMMANDS` du test de crontab. `setup_roles` : groupe « Vérification ».

**Routes supprimées.** `POST organizations/<id>/transfer-ownership/` est retirée (B9) ; aucun client externe n'existe (pré-production). F5 est livrée dans le même lot que B9.

## 11. Concurrence et parades (couche service ; verrous effectifs sous MySQL, écritures sérialisées sous SQLite)

| Risque | Parade |
|---|---|
| Deux acceptations du même jeton `ADMIN` | prise conditionnelle `PENDING -> AWAITING_CONFIRMATION` : une seule ligne ; l'autre : `404 invitation_invalid` |
| Confirmation et rejet simultanés ; confirmation et retrait de la personne | mise à jour conditionnelle depuis `AWAITING_CONFIRMATION` : un seul gagnant |
| Confirmation pendant que la personne rejoint ailleurs jusqu'au plafond technique | `_ensure_under_hard_limit` (verrou du compte) revérifié à la confirmation |
| Confirmation alors que l'émetteur vient d'être rétrogradé | autorité relue sous verrou d'organisation ; un Administrateur principal peut toujours confirmer |
| Deux nominations simultanées pour la même cible | comptage des nominations ouvertes sous verrou d'organisation |
| Acceptation de nomination et départ de la cible | même verrou ; `_end_membership` invalide la nomination dans sa transaction ; l'acceptation relit la cible sous verrou |
| Deux `TRANSFER` croisés (A -> B, B -> A) | une `TRANSFER` ouverte par organisation ; la seconde : `409 nomination_already_open` |
| Approbation du personnel pendant que l'initiateur perd son siège | revalidation complète dans `review_primary_admin_nomination` sous verrou ; `VOID` sinon |
| Deux créations simultanées au seuil de revue | comptage sous le verrou du compte (`_ensure_under_hard_limit` le pose) ; au pire les deux sont retenues en revue (sûr) |
| État de gouvernance désynchronisé (sanction sans événement) | `sync_organization_governance` horaire ; écart maximal documenté : une heure |
| Interblocage | ordre unique : organisation, puis invitation ou nomination, puis appartenances, puis comptes |

Registre de recette MySQL (ADR 0006 §17.5.4) enrichi : deux confirmations simultanées ; acceptation de nomination contre retrait de la cible ; deux `TRANSFER` croisés.

**Point ouvert (revue S3 de B7, non corrigé ici).** Sous SQLite, deux écritures concurrentes réelles (deux processus) sur la même organisation peuvent faire échouer la seconde en `database is locked` (erreur 500) au lieu de l'attendre : `select_for_update` est sans effet sous SQLite et l'écriture sérialisée n'attend que `timeout`. La parade relève du verrou commun `lock_row` de l'ADR 0009 (fichiers d'une autre tâche) ; les services d'invitation et de gouvernance devront l'adopter quand il sera livré. Sans effet sur la sécurité (l'opération perdante n'écrit rien) ; à couvrir par la recette MySQL.

## 12. Sécurité et données personnelles

- **Lien porteur `ADMIN` (U2).** Un lien transmis à un tiers ne donne **aucun** droit : la personne qui accepte attend la confirmation ; le confirmateur voit le nom abrégé et l'indice de téléphone, ressaisit son mot de passe **et saisit le code de rattachement à 6 chiffres que la personne lui communique** (QG-2 tranché par la revue S3 : code **en plus** du nom et de l'indice). Un tiers qui a intercepté le lien détient bien un code, mais le confirmateur doit l'obtenir de la personne avec qui il communique réellement : s'il appelle la personne qu'il voulait inviter, celle-ci n'a pas de code. 5 codes faux rejettent l'attente. **Risque résiduel** : un confirmateur qui obtient le code par le même canal que celui où le lien a fui (par exemple en le demandant dans la messagerie compromise), ou qui le recopie sans vérifier son interlocuteur ; atténuations : consignes à l'écran, notification à tous les Administrateurs principaux, audit, retrait possible du membre. L'indice de téléphone est relu en direct (le numéro peut changer après l'acceptation) : il n'est qu'un indice, la preuve est le code.
- **Indice de téléphone (règle 10).** Deux chiffres, servis à la seule personne habilitée à confirmer **cette** invitation, pendant la seule attente ; finalité : identifier qui a rejoint. Annoncé avant l'acceptation (texte de l'aperçu). Jamais dans l'audit, l'outbox, les notifications ni les journaux. Test à sentinelle.
- **Pas d'auto-escalade (Q21).** `OWNER` jamais par invitation (service + `CHECK`) ; `OWNER` jamais par `PATCH` ; la nomination exige une seconde personne (la cible) et, si renforcé, une troisième (Vérification, hors organisation) ; un Administrateur principal ne peut pas s'auto-nommer ni nommer un compte qu'il contrôle sans que ce compte accepte (risque résiduel « deux comptes de la même personne » : couvert par la revue en organisation renforcée ; accepté en `STANDARD`).
- **Oracle.** Les nouvelles erreurs ciblant une invitation suivent ADR 0008 §12 (`404 invitation_invalid` uniforme avant validité ; `400 user_unavailable` neutre pour l'état d'un tiers). `404 nomination_not_found` identique pour une nomination inexistante, d'une autre organisation ou ne visant pas l'appelant.
- **Seuils cachés (Q22).** `max_memberships_hard_limit`, `org_creation_review_*` ne figurent dans aucune réponse, aucun message, aucun texte d'interface ; test d'introspection sur `limits/`, `contexts/`, `internal/`.
- **IDOR.** `invitation_id`, `nomination_id`, `membership_id` toujours filtrés par l'organisation du chemin.
- **Revues obligatoires** : `auditeur-securite` sur B7 (S3), B9 (S4), B8 (S5, seuils cachés et revue).

## 13. Règles verrouillées (CLAUDE.md §4) vérifiées

| Règle | Verdict | Justification |
|---|---|---|
| 1. Compte unique, contextes | Respectée | `MEMBER` est un rôle dans une organisation, pas un type de compte ; aucun plafond bas sur les contextes (Q22). |
| 2. Permissions ≠ droits commerciaux | Respectée | Aucun service de gouvernance ne reçoit de plan ; test d'introspection étendu à `governance.py` ; `CAP-TEAM-MEMBER` (ADR 0009) compte des appartenances confirmées, jamais l'inverse. |
| 3. Vérification non achetable | Respectée | `assurance_level` fixé par le personnel ou par catégorie ; la revue Vérification n'est liée à aucun paiement ; `assurance_level` n'est pas un badge public. |
| 4. Aucun score de confiance | Respectée | La mise en revue de création est un signal interne binaire, ni note, ni agrégat, ni facteur de classement. |
| 8. États indépendants | Respectée | Appartenance, invitation, nomination, état de gouvernance, revue de création, statut d'organisation : six champs distincts, aucun n'écrase l'autre (une organisation peut être `SUSPENDED` + `MISSING` + `PENDING`). |
| 10. Données par finalité | Respectée | Indice de téléphone limité (12) ; aucune nouvelle donnée publique. |
| 11. Configurable | Respectée | Seuils, durées, catégories sensibles en back-office (4.6, 4.7). |
| 12. Audit | Respectée | Section 8. |
| 5, 6, 7, 9 | Non touchées | — |

## 14. Ce qui casse dans le code livré

| Livraison | Ce qui change | Fichiers principaux |
|---|---|---|
| **L0-09** (création, `limits/`, `contexts/`) | `_ensure_under_limit` -> plafond technique caché + revue ; `409 organization_limit_reached` -> `409 account_review_required` ; `limits/` perd `max_organizations_per_account` ; A15 : `contexts/` borné par le plafond technique (200) ; `MEMBER` dans `contexts/` | `organizations.py`, `organization_reads.py`, `models.py`, `admin.py`, `tests_organizations*.py`, `tests_contexts*.py` |
| **B1** (équipe) | `change_role` vers `OWNER` refusé (`use_primary_admin_nomination`) ; `transfer_ownership_to` et la route `transfer-ownership/` supprimés ; D7 ; messages « propriétaire » ; `Member.scope` ; invalidation des nominations dans `_apply_role_change` et `_end_membership` ; `_refresh_primary_admin_state` | `organizations.py`, `views_organizations.py`, `urls.py`, `tests_team.py` (tests de transfert et de promotion à réécrire) |
| **B2a** (modèle d'invitation) | `status` 10 -> 24, nouveaux champs, `INVITABLE_ROLES`, réglage | `models.py`, migration, `admin.py` |
| **B2b** (services d'invitation) | `ADMIN` et `MEMBER` invitables ; `_inviter_has_authority` via `can_delegate` ; acceptation en deux temps ; aperçu enrichi ; tests « `ADMIN` refusé » inversés | `invitations.py`, `views_invitations.py`, `tests_invitations*.py`, `notifications/events.py` |
| **B4** (blocages) | `suggested_action = transfer_ownership` désigne désormais une **nomination** (valeur inchangée) ; messages ; refonte complète par ADR 0012 (F3 en pause) | `organizations.py` |
| **F1** (écran Équipe) | libellés ; option « Propriétaire » du menu de rôle retirée ; dialogue de transfert remplacé par « Proposer comme administrateur principal » (nomination, deux genres) ; liste des nominations ; bannière `primary_admin_state` ; `MEMBER` | `components/team/*`, `hooks/use-organization-team.ts`, `pages/OrganizationTeam.tsx`, `i18n/locales/fr.ts` |
| **F2** (invitations) | rôles `ADMIN`, `MEMBER` et choix du périmètre (organisation seule) ; aperçu avec périmètre, accès, avertissement de confirmation ; acceptation 202 ; statut `AWAITING_CONFIRMATION` (confirmer avec mot de passe, rejeter, indice) ; « mes adhésions en attente » | `pages/OrganizationInvitation.tsx`, `components/team/Invitations*`, `lib/invitations.ts`, `hooks/use-organization-invitations.ts` |
| **Front création** | message `organization_limit_reached` -> `account_review_required` ; `organization-form.ts` ne lit plus `max_organizations_per_account` ; bannière « en cours d'examen » | `pages/OrganizationNew.tsx`, `lib/organization-form.ts`, `api/types.ts`, `lib/api-errors.ts` |

## 15. Interfaces avec les autres ADR et tâches

- **ADR 0011 (cycle de vie, restrictions).** Lit `primary_admin_state` et `primary_admin_missing_since` (restriction puis archivage d'une organisation orpheline, délais QO-8) ; pourra convertir `creation_review_status = PENDING` en restriction ciblée « revue de création » (le champ resterait la source de vérité de la revue). Le transfert depuis une organisation archivée, retiré ici, y sera repris avec la restauration exceptionnelle.
- **ADR 0012 (fermeture de compte).** Fin d'appartenance `end_reason = 'account_closed'` qui **contourne** `last_owner` et `last_effective_owner` (Q24 : avertir puis orpheline), appelle `_refresh_primary_admin_state` et `void_nominations_*` ; les invitations `AWAITING_CONFIRMATION` de la personne passent à `DECLINED`. Interface à exposer par ce lot : `governance.void_all_for_user(actor, user_id, reason)`.
- **ADR 0009 (plans).** Libellé de `billing.purchase` (Administrateur principal) ; ligne §6 « 10 organisations par compte : anti-abus » à remplacer par « plafond technique caché + revue (ADR 0010 D8) ; aucun plan ne le relève (test) » ; `CAP-TEAM-MEMBER` : les invitations en attente de confirmation ne consomment pas de place, la confirmation en consomme une (contrôle d'entitlement au moment de la confirmation, ordre « permission puis entitlement » d'ADR 0009 §7).
- **L1-02a** reprend `assurance_level` (et le relie aux pièces) ; **L1-02d** la délégation datée ; **L1-02e** les conflits d'autorité (dont D7 en organisation renforcée) ; **L1-02f** la régularisation des organisations `MISSING` (service du personnel qui attribue un siège `OWNER` : amende ADR 0006 §11.4 et ADR 0008 D5, hors de ce lot) ; **L1-02g** pourra relever `assurance_level` d'une organisation au nom protégé.
- **L1-21 (support).** Lien d'aide des messages `account_review_required`, `primary_admin_change_requires_verification` et de la bannière `MISSING`.

## 16. Conséquences

- 2 nouveaux modèles (`PrimaryAdminNomination`, `HighAssuranceCategory`), 4 champs sur `Organization`, 2 sur `Membership`, 5 sur `OrganizationInvitation`, 5 réglages, 6 migrations `identity`, 2 nouveaux types d'événement, 3 abonnés, 1 commande planifiée, 3 scopes de throttle, 1 groupe du personnel, 1 route supprimée et environ 12 routes ajoutées (contrat, section 7).
- ADR 0006 §5 (matrice), D5, A12 (« plafond par compte » retiré des garde-fous), A15 (borne = plafond technique), §17.2 B amendés ; ADR 0008 §3.2 (rôles invitables), §3.6 et §8.2 (portée de la ressaisie), §4.3 (machine d'états), §12 (risque du lien porteur : traité par confirmation pour `ADMIN`), §15 n°2 (soldé) amendés ; ADR 0009 §6 à corriger (section 15).
- **Risques acceptés :** pas de revue rétroactive des `OWNER` existants (données de test seulement) ; confirmateur inattentif (12) ; écart d'une heure de l'état de gouvernance après une sanction ; catégories du catalogue imparfaites pour détecter les organisations sensibles (relèvement manuel) ; deux comptes d'une même personne en organisation `STANDARD` (Q22 : signal, pas preuve).
- **Dettes :** `Membership` à rôle unique (4.8) ; périmètres `CITY` et `UNIT` déclarés mais inactifs ; délégation datée (L1-02d) ; prérequis de production inchangés (cache partagé, recette MySQL).

## 17. Questions restantes (avec recommandation)

| # | Question | Pour | Recommandation |
|---|---|---|---|
| **QO-6** | « Simple membre » (Q23) : rôle distinct ou Analyste ? | client | **Rôle distinct `MEMBER`** (D2) : Q23 l'énumère à côté d'Analyste, et Q22 distingue « simple membre » d'administrateur. Capacités minimales (espace interne, équipe, quitter). Si le client répond « = Analyste », une migration de données `MEMBER -> ANALYST` suffit (réversible). Livrer sans attendre. |
| **QG-1** | Valeurs anti-abus : 2 créations/heure, 5/jour, revue dès la 5e création sur 30 jours, plafond technique 200 appartenances | utilisateur | Valider (toutes en back-office ; Q22 demande une proposition de l'équipe). |
| **QG-2** | Confirmation `ADMIN` : nom abrégé + deux derniers chiffres du téléphone, ou code de rattachement à ressaisir | utilisateur, auditeur-securite | **Tranché (revue S3, décision du chef de projet, L1-01-B7)** : code de rattachement à 6 chiffres **en plus** du nom abrégé et de l'indice (§6.2, §12). |
| **QG-3** | Délais : confirmation 72 h, nomination 7 jours, revue 30 jours | utilisateur | Valider (réglables). |
| **QG-4** | « Lorsque la gouvernance le permet » (Q21) : faut-il une option par organisation « un seul Administrateur principal » ? | client | Non en V1 (aucun plafond) ; ajout additif possible (`Organization.single_primary_admin`, refus des nominations `PROMOTE`). |
| **QG-5** | Organisation `MISSING` : rester non publique comme aujourd'hui (règle « propriétaire effectif ») ? Q17 dit « ne condamne pas automatiquement ». | utilisateur, client | **Garder non publique** : sans Administrateur principal personne ne répond de l'organisation ; ce n'est ni une sanction ni une suppression (l'organisation, ses données et son équipe restent), et l'état est expliqué aux membres. À confirmer car la lecture inverse est possible. |
| **QG-6** | Organisation retenue en revue de création : invisible publiquement jusqu'à la levée (D8) | utilisateur | Valider ; alternative : visible avec signal interne seulement (plus exposée à l'abus massif). |
| **QG-7** | Rétrogradation d'un autre Administrateur principal en organisation `STANDARD` : immédiate avec ressaisie et notifications (D7) | utilisateur | Valider ; alternative plus stricte : acceptation par la cible ou par un autre Administrateur principal (double contrôle). |
| **QG-8** | Liste initiale de `HighAssuranceCategory` et organisations à relever en `ENHANCED` | client (Q25, Q26) | Le client fournit ; aucune valeur inventée. |
| **QG-9** | Le transfert depuis une organisation archivée (permis par ADR 0008) est retiré jusqu'à ADR 0011 | chef de projet | Valider. |

## 18. Découpage en tâches

**Préalables :** ADR et contrat (section 7 de `L1-01-contrat-api.md`) validés ; F2 actuelle terminée et fusionnée sur le contrat ADR 0008 (recommandation de l'analyste). **Migrations `identity` en série** (une tâche B à la fois dans `identity/migrations/`, ordre B5, B6, B7, B8, B9, B10). Les tâches front et design avancent en parallèle sur le contrat figé.

| ID | Agent | Contenu | Dépend de | Parallélisable avec |
|---|---|---|---|---|
| **D2** | designer-ux | Spécifications : invitation `ADMIN` (aperçu avec périmètre, accès, avertissement « l'émetteur verra votre nom et les deux derniers chiffres de votre numéro »), page « adhésion en attente de confirmation », confirmation côté émetteur (indice, mot de passe, rejet), dialogue « Proposer comme administrateur principal » (deux genres, mot de passe), carte de nomination côté cible (accepter, refuser), liste des nominations, bannières « administration à régulariser » et « organisation en cours d'examen », message neutre `account_review_required` | contrat | B5 à B10 |
| **B5** | dev-backend | Libellés « Administrateur principal » : `ROLE_CHOICES`, messages des services (`organizations.py`, `invitations.py`), `get_role_label`, textes de `notifications/events.py` ; migration `0017` ; tests des messages | ADR | F1-bis, D2 |
| **F1-bis** | dev-frontend | Libellés dans `fr.ts` (≈ 30 entrées) et composants d'équipe ; aucun changement de contrat | contrat | B5 |
| **B6** | dev-backend | `MEMBER` (matrice testée case par case), `scope_covers`, `can_delegate`, `scope_type`/`scope_id` sur `Membership` et invitation, `CHECK`, `_validate_scope`, `target_scope` dans `authorize_on`/`can`, `Member.scope`, `contexts/` ; migration `0018` avec garde inverse ; tests purs de délégation sur périmètres fictifs `CITY` | B5 | D2, F1-bis |
| **B7** | dev-backend | Invitations v2 : `INVITABLE_ROLES` élargi, acceptation en deux temps, `confirm`, `reject`, `withdraw`, `awaiting/`, aperçu enrichi, indice de téléphone, abonné `notify_invitation_outcome` étendu, `expire_invitations` étendue ; migration `0019` ; tests (rejeu, concurrence logique, confirmation par l'émetteur puis par un Administrateur principal après départ de l'émetteur, sentinelles indice et étiquette, uniformité 404) | B6 | F2-bis (sur contrat) |
| **S3** | auditeur-securite | Revue B7 : lien porteur, confirmation, indice de téléphone, escalade, oracle | B7 | B8 |
| **F2-bis** | dev-frontend | Invitations v2 côté front (section 7.4 du contrat) | contrat, D2, F2 fusionnée | B7 |
| **B8** | dev-backend | Anti-abus : plafond technique caché, revue de création, `org_create_burst`, `limits/` sans le plafond, visibilité publique exclue en revue, service du personnel de levée, permission ; migration `0020` ; tests d'introspection des seuils cachés | B7 (migrations) | F4 |
| **S5** | auditeur-securite | Revue B8 : aucun seuil divulgué, neutralité des refus, contournement par double soumission | B8 | B9 |
| **F4** | dev-frontend | Création d'organisation : `account_review_required`, retrait du plafond, bannière « en cours d'examen » | contrat, D2 | B8 |
| **B9** | dev-backend | `governance.py` : nominations (création, acceptation, refus, annulation, revue du personnel, expiration, invalidations), `assurance_level`, `HighAssuranceCategory`, D7, suppression de `transfer-ownership/`, refus `PATCH role=OWNER`, groupe « Vérification » dans `setup_roles`, événement et abonné de notification ; migration `0021` ; tests (maker-checker, conflit d'intérêts du réviseur, concurrence logique, invariants, revalidation à l'application, absence de plan) | B8 (migrations) | F5 (sur contrat) |
| **S4** | auditeur-securite | Revue B9 : escalade, auto-nomination, conflit d'intérêts, ressaisie, IDOR `nomination_id` | B9 | B10 |
| **F5** | dev-frontend | Nominations : dialogue, liste, carte de la cible, retrait du dialogue de transfert ; livrée dans le même lot que B9 | contrat, D2 | B9 |
| **B10** | dev-backend | État `primary_admin_state` : `_refresh_primary_admin_state`, `sync_organization_governance` + crontab + test de crontab, abonné aux changements de statut de compte, événement et notification ; migration `0022` avec remplissage | B9 | F6 |
| **F6** | dev-frontend | Bannière « administration à régulariser » (champ `governance` de `OrganizationInternal` et `contexts/`) | contrat, D2 | B10 |
| **R** | relecteur-code | Après chaque tâche B et F | tâche | — |
| **Q** | qa-testeur | Recette L1-01 révisée : invitation `ADMIN` de bout en bout (lien transmis à un tiers : aucun droit), nomination `STANDARD` et renforcée, D7, création au-delà du seuil, plafond technique, organisation `MISSING` après désactivation ; non-régression `identity`, `notifications`, `marketplace`, `moderation`, `DomainBoundariesTests` ; entrées du registre MySQL | B10, F6 | — |

**Chemin critique :** B5 -> B6 -> B7 -> B8 -> B9 -> B10 (série imposée par les migrations). **En parallèle :** D2 dès le départ ; F1-bis avec B5 ; F2-bis, F4, F5, F6 dès D2 livré, chacune fusionnée après sa tâche backend. Option pour raccourcir : B8 avant B7 (indépendants hors migrations) si la confirmation `ADMIN` attend l'avis de S3 sur QG-2.
