# L1-01 — Organisations : création, revendication, invitation, membres et rôles (analyse fonctionnelle)

- **Date :** 09/11/2026
- **Auteur :** analyste-fonctionnel
- **Statut :** proposition, à valider par le chef de projet (CP), puis à planifier par `architecte-technique` (nouvel ADR qui amende l'ADR 0006 §17.2 C et §4.3)
- **Réf. :** CDC v1.2 §3.1 (Organisations, Rôles, « Une revendication d'organisation existante ne donne aucun droit avant validation »), §11.1 ; règles verrouillées 1, 2, 3, 10, 12 (et 5, 11 en appui) ; dossier client IAM-005, IAM-006, IAM-007, ORG-001, ORG-003, TRU-003, UF-02, UF-04, UF-29 (doc 02) ; doc 06 §6, §7, §14, §19 à §22 ; doc 07 §3, §5 ; doc 09 §8 (« Organization Claim & Authority Review ») et OPS-10, OPS-AC-16 ; doc 13 §5 (`OrganizationClaim`, `AuthorizedRepresentative`).
- **Sources lues :** `docs/specs/L0-09-compte-contextes.md`, `docs/specs/L0-09-ecrans-contextes.md` (E6), `docs/specs/L0-09-ecran-organisation-suspendue.md`, `docs/adr/0006-compte-unique-contextes-organisations.md` (sections 4, 5, 9, 15, 17 à 21), `docs/suivi/JOURNAL.md` (entrées L0-09 du 09/11/2026), code `backend/apps/identity/` (lecture seule : `organizations.py`, `capabilities.py`, `urls.py`, `models.py`), `backend/apps/notifications/events.py`.

---

## 0. Résumé

La **moitié « règles et services » de L1-01 existe déjà** (livrée par L0-09, T1) : création, rôles, plafond, `last_owner`, sortie volontaire, transfert de propriété, révocation, audit, événement `identity.membership_changed`, notifications d'équipe. Ce qui manque est tout ce qui est **exposé à un utilisateur** : aucun endpoint de liste, de changement de rôle, de retrait ni de transfert ; aucun mécanisme d'**invitation avec acceptation de la cible** ; aucune **revendication** ; aucun **chemin de secours** pour une organisation sans propriétaire effectif ; aucun écran d'équipe (l'écran E6 de L0-09 est volontairement réduit).

Trois points de conception dominent :

1. **L'ajout direct d'un membre reste interdit d'exposition** (ADR 0006 §17.5.2). Il est remplacé par une **invitation** que la cible accepte. Le contrat « cible » de l'ADR §17.2 C (`POST members/` avec un identifiant de compte) doit être amendé : il révélerait l'existence des comptes et suppose une vérification d'e-mail qui n'existe pas (seul `phone_verified` existe).
2. **La revendication n'a aucune base de code** (doc 13 `OrganizationClaim`, jamais créé). Elle exige un nouveau modèle, un dépôt de preuves en stockage privé, une file du personnel et, point délicat, **un pouvoir du personnel de créer une appartenance**, ce que l'ADR 0006 §11.4 avait écarté (« le personnel n'attribue pas de rôle »). Cette exception doit être décidée et encadrée (quatre yeux, audit, conflit d'intérêts).
3. **« Organisation sans propriétaire » est un cas qui existe déjà de fait** : un propriétaire unique dont le compte est désactivé ou sanctionné laisse l'organisation sans propriétaire *effectif* (ses offres sont masquées depuis T9, ADR §20 T9-1 n°4), sans que le garde-fou `last_owner` s'y oppose (il ne compte que les appartenances, pas l'état des comptes).

**Onze stories** (L1-01a à L1-01k) et une story de moindre priorité (L1-01l, noms réservés). Aucune règle verrouillée n'est contredite. Une contradiction d'architecture (§7, C1) et une extension de pouvoir du personnel (§7, C2) sont à trancher avant planification.

---

## 1. Analyse de conformité

| Règle / source | Verdict | Remarque |
|---|---|---|
| Règle 1 (compte unique) | Conforme | Inviter ou revendiquer ne crée jamais de compte ni de « type de compte ». Une invitation envoyée à une personne sans compte la conduit à l'inscription normale, puis à l'acceptation (doc 02 UF-02, variante « invitation reçue avant création du compte »). |
| Règle 2 (permissions ≠ droits commerciaux) | À protéger | Aucune fonction d'équipe ne reçoit de plan. Un futur plafond de membres par plan (L1-11) produira `DENY_ENTITLEMENT` avant l'appel, jamais un changement de rôle. Test de signature déjà en place (ADR §12) à étendre aux nouveaux services. |
| Règle 3 (la vérification ne s'achète pas) | À protéger | Approuver une revendication **ne crée aucun badge** de vérification (§1 de L1-01i). L'« Autorité vérifiée » de doc 07 §3 reste hors périmètre. Le paiement d'un plan ne remplace jamais la validation d'autorité (doc 02 UF-04). |
| Règle 10 (données par finalité) | À protéger fortement | Liste des membres : `display_name` abrégé seulement (ADR §17.1 Q-F6). Invitation : l'identifiant saisi (téléphone) est une donnée personnelle de tiers : jamais dans l'audit ni dans l'outbox ni dans une notification ; stocké haché si possible. Preuves de revendication : stockage privé, jamais visibles des autres membres. |
| Règle 12 (AuditLog) | À appliquer | Liste des actions en §4.1. |
| Règles 4, 5, 6, 7, 8, 9 | Non concernées | — |
| Règle 11 (configurable) | Point d'attention | Durée de validité d'une invitation, plafond d'invitations en attente, plafond de revendications par compte, pièces demandées pour une revendication : réglages en base (`IdentitySettings`) ; les valeurs de §6 sont des **valeurs de départ provisoires**, pas des décisions du client. |
| Périmètre V1 | Conforme | Branches et départements (doc 06, doc 13 `Branch`) restent hors V1 (écart E2 de L0-09, non tranché par le client). Rôles supplémentaires de doc 06 (recruteur, facturation…) hors V1 (E1). |
| CDC §3.1 | Conforme | « Création, revendication ou invitation » = les trois activations du contexte Organisation. « Une revendication d'organisation existante ne donne aucun droit avant validation » est la règle directrice de L1-01i/j. |
| ADR 0001 / CLAUDE.md §5 | Contraintes | Pas d'unicité conditionnelle (une invitation en attente par cible = règle de service) ; UUID ; pas de clé étrangère inter-domaines hors `User` ; tâches différées par commande cron (expiration des invitations), pas de Celery. |

---

## 2. Inventaire : ce qui existe et ce qui manque

### 2.1. Déjà livré par L0-09 (à ne pas refaire)

| Capacité | Où | État |
|---|---|---|
| Création d'une organisation (4 types, nom normalisé, catégories, ville, logo, plafond 10, téléphone vérifié exigé, anti double soumission 10 s) | `organizations.create_organization`, `POST organizations/` | Livré, testé, exposé |
| Rôles OWNER / ADMIN / EDITOR / ANALYST, matrice de capacités, `can_manage_role_of` (R9, R10) | `capabilities.py` | Livré (constantes) |
| Règle `last_owner` (R8) : rétrogradation, retrait, départ ; message particulier pour organisation suspendue | `_apply_role_change`, `_end_membership` | Livré (services) |
| Sortie volontaire | `leave_organization`, `POST organizations/<id>/leave/` | Livré, exposé (permise sur organisation suspendue ou archivée) |
| Changement de rôle | `change_member_role` | Service seulement, **aucun endpoint** |
| Retrait d'un membre (`end_reason = removed`) | `revoke_member` | Service seulement, **aucun endpoint** |
| Transfert de propriété (deux changements de rôle, une transaction, audit `ORG_OWNERSHIP_TRANSFERRED`) | `transfer_ownership` | Service seulement, **aucun endpoint** |
| Ajout direct de membre / réactivation d'un ancien membre (même ligne, R12) | `add_member` | Service seulement, **non exposable** (docstring et ADR §17.5.2) |
| Audit `MEMBERSHIP_ADDED`, `MEMBERSHIP_ROLE_CHANGED`, `MEMBERSHIP_REVOKED`, `ORG_CREATED`, `ORG_UPDATED`, avec `context_type/id` | `_audit_membership`, `record_audit` | Livré |
| Événement `identity.membership_changed` (`added`, `reactivated`, `role_changed`, `revoked`) et abonnés : notification de la personne concernée, purge des notifications d'organisation à la révocation ou rétrogradation | `notifications/events.py` | Livré |
| Révocation immédiate (aucun cache), états d'organisation, garde de compte, refus neutre `user_unavailable` pour une cible inconnue, inactive, restreinte ou au plafond | `_authorize_member`, `_unavailable_user_error` | Livré |
| Garde de suppression de compte : refus si dernier propriétaire (active ou suspendue), sanction bloquante, signalement grave | `assert_account_removable` | Livré (admin et récepteur `pre_delete`) |
| Liste des contextes, organisations « indisponibles » (suspendue, archivée) | `GET contexts/` | Livré |
| Écran E6 « Équipe » réduit (mon rôle, quitter, description des rôles) | `docs/specs/L0-09-ecrans-contextes.md` §7.7 | Spécifié ; livré côté front selon L0-09 |
| Suspension, réactivation, archivage ; conflit d'intérêts du personnel à la réactivation | `suspend/reactivate/archive_organization` | Livré |

### 2.2. Ce qui manque réellement

| Manque | Story |
|---|---|
| Endpoint de liste des membres (le service de lecture n'existe pas non plus : aucun `list_members`) | L1-01b |
| Modèle et parcours d'**invitation** avec acceptation (aucune trace dans le code ; `Membership.INVITED` n'existe pas) | L1-01c, L1-01d |
| Endpoints de changement de rôle, retrait, transfert | L1-01e, L1-01f, L1-01h |
| **Revendication** : modèle, preuves, file du personnel, décision, notifications | L1-01i, L1-01j |
| Détection et **chemin de secours** d'une organisation sans propriétaire effectif | L1-01j |
| Événement de visibilité lors d'un changement d'appartenance d'un propriétaire (dette ADR §20 T9-1 n°4) | L1-01e, L1-01f, L1-01j |
| Préalables d'équipe à la **suppression de compte** (liste des blocages, parcours guidé) ; la suppression libre-service elle-même n'est dans aucune source | L1-01k |
| Liste de noms réservés et signalement d'usurpation d'une organisation (cible `organization` absente de `moderation`) | L1-01l |
| Écrans d'équipe complets (E6 cible), d'invitation, d'acceptation, de revendication | Découpage §8 |

---

## 3. Règles de gestion

- **R-L1.** Toute opération d'équipe est faite par un service d'`identity` sous `transaction.atomic()`, verrou de l'organisation, autorisation recalculée sous verrou, audit synchrone avec contexte, événement dans la même transaction (acquis L0-09, ADR §7.2).
- **R-L2.** Un membre est désigné par son `membership_id` dans l'API, jamais par l'identifiant du compte (ADR §17.2 C).
- **R-L3.** Une invitation n'ouvre **aucun droit** tant qu'elle n'est pas acceptée par la cible. Elle est unique en usage, expire, se révoque, et ne contient aucune donnée personnelle de l'invité en clair dans l'audit, l'outbox ou les notifications.
- **R-L4.** Une invitation ne peut **pas** conférer le rôle OWNER (hypothèse de travail H3 ; doc 02 UF-04 : « invitation comme simple membre sans droit d'administration »). Devenir propriétaire passe par la promotion d'un membre existant (L1-01e/h) ou par une revendication validée (L1-01j).
- **R-L5.** Au moment de l'**acceptation**, tout est revérifié : invitation non expirée ni révoquée ni utilisée ; organisation ACTIVE ; compte de la cible actif, non restreint, téléphone vérifié ; plafond d'organisations de la cible (ADR §17.5.2) ; l'inviteur a **toujours** l'autorité pour ce rôle (membre actif, `org.manage_members`, `can_manage_role_of`). Sinon refus uniforme `invitation_invalid`.
- **R-L6.** Une revendication **ne donne aucun droit** tant qu'elle n'est pas approuvée (CDC §3.1 ; doc 02 UF-04 ; doc 13 : « ne remplace jamais automatiquement un admin existant »). Un propriétaire existant n'est **jamais** remplacé automatiquement (doc 09 §8, OPS-10, OPS-AC-16).
- **R-L7.** L'approbation d'une revendication est une **action du personnel**, journalisée, refusée si le décideur est ou a été membre ou créateur de l'organisation, ou s'il est le demandeur (même principe que la décision KYB et la réactivation). Quand l'organisation a un propriétaire effectif (revendication « contestée »), la décision exige **deux personnels distincts** (doc 09 §8 : « four-eye si contesté/sensible »).
- **R-L8.** **Propriétaire effectif** : appartenance `OWNER` `ACTIVE` dont le compte est actif et sans sanction bloquante. Une organisation sans propriétaire effectif est « orpheline » (définition de travail, §4.10).
- **R-L9.** Le paiement d'un plan ne remplace jamais une validation d'autorité, et un rôle ne donne ni badge ni classement (règles 2, 3 ; R13 de L0-09).
- **R-L10.** Les erreurs sur la cible d'une action d'équipe (compte inconnu, inactif, restreint, au plafond) restent **neutres** et identiques (`user_unavailable`, 400) ; une invitation inconnue, expirée, révoquée, déjà utilisée ou destinée à un autre contexte répond par un **404 uniforme** `invitation_invalid` (pas d'oracle).

---

## 4. Actions journalisées et événements (règle 12)

### 4.1. `AuditLog` (nouvelles actions ; `details` sans donnée personnelle, UUID et codes seulement)

| Code | Cible | Contenu minimal |
|---|---|---|
| `INVITATION_CREATED` | `organizationinvitation` | acteur, rôle proposé, organisation, durée (jamais le téléphone ni l'e-mail, jamais le jeton) |
| `INVITATION_ACCEPTED` / `INVITATION_DECLINED` | idem | acteur = cible ; rôle |
| `INVITATION_REVOKED` | idem | acteur (membre habilité) |
| `INVITATION_EXPIRED` | idem | système (commande cron), un enregistrement par lot avec comptage |
| `INVITATION_REFUSED` | organisation | acteur, motif normalisé (`expired`, `revoked`, `used`, `limit`, `authority_lost`) ; sans identifiant de la personne visée si inconnue |
| `ORG_CLAIM_SUBMITTED` / `ORG_CLAIM_WITHDRAWN` | `organizationclaim` | acteur, organisation |
| `ORG_CLAIM_EVIDENCE_ADDED` | `organizationclaim` | acteur, type de pièce (code), pas de nom de fichier |
| `ORG_CLAIM_DECIDED` | `organizationclaim` | décideur, décision (`approved`, `rejected`, `info_requested`), motif codé, rôle accordé, second approbateur le cas échéant |
| `ORG_OWNERSHIP_RESTORED` | `organization` | personnel, bénéficiaire (UUID), cas (`claim`, `rescue`), second approbateur |
| `ORG_OWNERSHIP_TRANSFERRED`, `MEMBERSHIP_*` | existants | inchangés |
| `ACCOUNT_DELETION_BLOCKED_BY_ORG` | `user` | acteur, nombre d'organisations bloquantes (UUID de l'organisation seulement) |
| `ORG_NAME_RESERVED_REFUSED` | `organization` | acteur, code du motif (pas le nom) |

### 4.2. Événements de domaine (outbox ; à déclarer dans `platform_core/catalog.py`)

| Type | Émetteur | Abonnés (proposition) |
|---|---|---|
| `identity.membership_changed` (existant) | acceptation d'invitation (`added` ou `reactivated`), promotion, retrait, départ, secours | inchangés (notification de la personne, purge) ; **plus** : recalcul de la visibilité si le membre concerné est (ou était) propriétaire |
| `identity.organization_invitation_changed` (v1, nouveau) | création, acceptation, refus, révocation, expiration | `notifications` (informe l'inviteur d'une acceptation ou d'un refus ; informe une cible déjà titulaire de compte, si le rattachement est possible sans énumération — voir H1) |
| `identity.organization_claim_changed` (v1, nouveau) | dépôt, retrait, décision | `notifications` (demandeur ; propriétaires et administrateurs effectifs en cas de revendication contestée, **sans identité du demandeur** — voir H5) |

Charges utiles : UUID, codes ; jamais de nom, téléphone, e-mail, jeton, nom de fichier.

---

## 5. User stories

Conventions : préfixe d'API `ID = /api/v1/accounts/` (L0-11 livré). « Neutre » = réponse identique quel que soit l'état de la cible.

### L1-01a — Créer une organisation (livrée par L0-09 ; non-régression et compléments)

En tant que **personnel** (compte connecté, téléphone vérifié), je veux créer une organisation dont je deviens propriétaire, afin d'agir au nom de mon entreprise, boutique, ONG ou structure d'événements.

Réf. : CDC §3.1 ; dossier client IAM-005, UF-04, ORG-003 ; lot 1 (L0-09 T1/T8 livrés).
**État : Fait.** Rien à développer, sauf la liste des dettes ci-dessous.

Critères d'acceptation (verrouillés par les tests existants, à ne pas supprimer) :
- [ ] Étant donné un compte actif avec téléphone vérifié, quand il crée une organisation (type parmi quatre, nom 2 à 255 caractères après normalisation NFKC), alors une organisation `ACTIVE` et une appartenance `OWNER` `ACTIVE` existent dans une seule transaction et `ORG_CREATED` est journalisé.
- [ ] Étant donné un compte sans téléphone vérifié, alors `403 phone_verification_required` ; étant donné le plafond atteint, alors `409 organization_limit_reached` ; étant donné une double soumission identique sous 10 s, alors la même organisation est renvoyée sans consommer le plafond.
- [ ] Étant donné la création, alors aucun plan, aucune vérification et aucun badge n'est attribué.

Règles métier : R-L9 ; D5 (plafond 10) et Q-CP5 (téléphone vérifié) de l'ADR 0006.
Hors périmètre : KYB (L1-02) ; page publique (L1-03) ; noms réservés (L1-01l).
Questions ouvertes : Q-CLI4 (plafond), Q-CLI8 (homonymes, voir L1-01l).

---

### L1-01b — Voir l'équipe de l'organisation

En tant que **membre d'une organisation** (tout rôle), je veux voir la liste de l'équipe avec le rôle de chacun, afin de savoir qui peut agir et à qui m'adresser.

Réf. : CDC §3.1 ; dossier client IAM-006 ; ADR 0006 §17.1 Q-F6 et §17.2 C ; lot 1.
Dépend de : aucune (le service de lecture est à créer).

Critères d'acceptation (testables) :
- [ ] Étant donné un membre actif de n'importe quel rôle (analyste compris), quand il appelle `GET ID organizations/<uuid>/members/`, alors il reçoit `200` paginé (`count, next, previous, results`) ; chaque élément contient **exactement** `membership_id, display_name, role, joined_at, is_self`.
- [ ] Étant donné la charge, alors un test d'exhaustivité des clés et de motifs vérifie l'absence de téléphone, e-mail, nom complet, photo du compte, identifiant du compte, historique et pièces ; `display_name` vaut `public_display_name` (« Marie K. »).
- [ ] Étant donné les membres `REVOKED` ou les invitations en attente, alors ils ne figurent **pas** dans cette liste (les invitations ont leur propre ressource, L1-01c).
- [ ] Étant donné l'ordre, alors propriétaires, puis administrateurs, éditeurs, analystes, puis `joined_at` croissant, puis `membership_id`.
- [ ] Étant donné un non-membre, un ancien membre ou un membre dont l'organisation est suspendue, alors `403 DENY_RELATION` (non-membre ou révoqué) ou `403 DENY_SECURITY` (suspendue) ; archivée : `403 DENY_OBJECT_STATE` (ordre de contrôle de l'ADR §17.1 Q-F4).
- [ ] Étant donné un compte restreint ou désactivé, alors refus `DENY_SECURITY` (sauf la sortie volontaire).
- [ ] Étant donné une organisation de 200 membres, alors le nombre de requêtes SQL ne dépend pas de la taille de la page (`assertNumQueries`).
- [ ] Étant donné l'indicateur « dernier propriétaire » demandé par l'UX (`team.lastOwner`), alors un booléen `is_last_effective_owner` est exposé **uniquement** sur la ligne concernée et uniquement aux propriétaires et administrateurs (voir question Q-L1-9).

Règles métier : R-L2, règle 10 (liste jamais publique ; le public ne voit pas qui administre).
Hors périmètre : page publique de l'organisation (L1-03) ; photo d'un membre.
Questions ouvertes : aucune propre.

---

### L1-01c — Inviter une personne à rejoindre l'organisation

En tant que **propriétaire ou administrateur**, je veux inviter une personne avec un rôle précis et pouvoir annuler l'invitation, afin d'agrandir mon équipe sans donner d'accès avant que la personne accepte.

Réf. : CDC §3.1 ; dossier client IAM-005, IAM-006, UF-04 (« invitation comme simple membre sans droit d'administration »), UF-02 (variante invitation reçue avant création du compte) ; ADR 0006 §17.5.2 ; lot 1.
Dépend de : L1-01b (affichage) ; ADR à produire (modèle d'invitation).
Revue `auditeur-securite` **obligatoire** (énumération de comptes, jeton, escalade de rôle).

Hypothèse de travail H1 (mécanisme, à confirmer par le CP) : **invitation par lien à usage unique**, sans recherche de compte. L'inviteur choisit un rôle (et peut saisir une étiquette libre facultative pour s'y retrouver, ex. « Jean, comptable », stockée en clair mais jamais journalisée ; elle est destinée à l'inviteur seul). Le serveur renvoie un lien contenant un **jeton aléatoire** que l'inviteur transmet lui-même (WhatsApp, SMS personnel…). Aucune réponse ne dépend de l'existence d'un compte. Voir §7, C1 pour l'écart avec l'ADR §17.2 C.

Critères d'acceptation (testables) :
- [ ] Étant donné un propriétaire ou un administrateur actif d'une organisation `ACTIVE`, quand il appelle `POST ID organizations/<uuid>/invitations/` avec `{"role": "EDITOR", "label": "..."}`, alors `201` et un corps `{invitation_id, role, status: "PENDING", expires_at, link_token}` ; `link_token` n'est renvoyé **qu'à cette réponse** (jamais relisible), et la base ne stocke que son **empreinte** (hachage) ; l'audit `INVITATION_CREATED` existe sans jeton ni étiquette.
- [ ] Étant donné le jeton, alors il comporte au moins 128 bits d'aléa cryptographique (test sur la longueur et la source) et sa comparaison est à temps constant.
- [ ] Étant donné un rôle `OWNER` demandé, alors `400` code `invitation_role_not_allowed` (R-L4) ; étant donné un administrateur qui demande `ADMIN`, alors c'est permis par la matrice (`can_manage_role_of`) **sauf** décision contraire sur H3 ; étant donné un éditeur ou un analyste, alors `403 DENY_PERMISSION`.
- [ ] Étant donné une organisation suspendue, archivée, ou un compte inviteur restreint, alors `403 DENY_SECURITY` / `DENY_OBJECT_STATE` / `DENY_SECURITY` et rien n'est écrit.
- [ ] Étant donné la durée de validité, alors elle vient de `IdentitySettings.invitation_ttl_days` (règle 11 ; valeur de départ 7, **à confirmer**) et `expires_at` est calculée serveur.
- [ ] Étant donné le plafond d'invitations en attente par organisation (`IdentitySettings.max_pending_invitations`, valeur de départ à confirmer) atteint, alors `409 invitation_limit_reached`.
- [ ] Étant donné la limite de débit (throttle par compte et par organisation, ex. `invitation_create`), alors un dépassement répond `429` sans écrire.
- [ ] Étant donné `GET ID organizations/<uuid>/invitations/` (`org.manage_members`), alors la liste paginée contient `invitation_id, role, status (PENDING, ACCEPTED, DECLINED, REVOKED, EXPIRED), label, created_at, expires_at, created_by_display_name` ; jamais le jeton, jamais l'empreinte.
- [ ] Étant donné `DELETE ID organizations/<uuid>/invitations/<id>/`, quand un membre ayant `org.manage_members` (et l'autorité sur le rôle proposé, R9) l'appelle, alors l'invitation passe à `REVOKED` et un usage ultérieur du lien répond `404 invitation_invalid`.
- [ ] Étant donné la révocation du **membre inviteur** ou la perte de son autorité (rétrogradé sous `org.manage_members`), alors ses invitations en attente deviennent inacceptables (revérifié à l'acceptation, R-L5) ; un test le vérifie.
- [ ] Étant donné l'API, alors aucun endpoint n'appelle `identity.organizations.add_member` (test de garde de routes ; la docstring de `add_member` est mise à jour pour dire qu'il n'est plus qu'un noyau interne de l'acceptation).
- [ ] Étant donné la commande planifiée `expire_invitations` (cron, ajoutée au test de crontab), alors elle passe à `EXPIRED` les invitations échues, de façon idempotente, avec une seule trace `INVITATION_EXPIRED` par exécution.
- [ ] Étant donné une charge d'outbox ou de notification liée à l'invitation, alors une recherche des valeurs sentinelles (étiquette, jeton) n'y trouve rien.

Règles métier : R-L3, R-L4, R-L5, R-L10 ; règle 10 ; l'invitation n'ouvre aucun droit.
Hors périmètre : envoi automatique de SMS ou d'e-mail par la plateforme (coût, anti-abus, e-mail non vérifié : Q-L1-2) ; invitation en masse ; invitation à un rôle de doc 06 hors des quatre.
Questions ouvertes : Q-L1-1 (mécanisme), Q-L1-2 (canal d'envoi), Q-L1-3 (OWNER et ADMIN par invitation), Q-L1-7 (valeurs de départ).

---

### L1-01d — Accepter ou refuser une invitation

En tant que **personne invitée** (compte connecté), je veux voir ce à quoi on m'invite, puis accepter ou refuser, afin de ne rejoindre une organisation que si je le décide.

Réf. : CDC §3.1 ; dossier client IAM-005, UF-02, UF-04 ; ADR 0006 §17.5.2 (« plafond vérifié à l'acceptation, pas à l'envoi ») ; lot 1.
Dépend de : L1-01c.
Revue `auditeur-securite` obligatoire.

Critères d'acceptation (testables) :
- [ ] Étant donné un jeton valide, quand un compte connecté appelle `POST ID organization-invitations/preview/` avec `{"token": "..."}`, alors il reçoit `200 {organization_name, org_type, role, expires_at, invited_by_display_name}` **sans** aucune donnée de l'équipe ; pour tout jeton inconnu, expiré, révoqué, déjà utilisé ou dont l'inviteur n'a plus l'autorité : `404 invitation_invalid` (corps et durée de réponse indiscernables, test sur le corps).
- [ ] Étant donné `POST ID organization-invitations/accept/` avec un jeton valide, quand la cible est un compte actif, non restreint, avec téléphone vérifié, sous le plafond, et que l'organisation est `ACTIVE`, alors une appartenance `ACTIVE` du rôle invité est créée (ou l'ancienne ligne est réactivée : unicité `(organization, user)`, R12), l'invitation passe à `ACCEPTED`, `INVITATION_ACCEPTED` et `MEMBERSHIP_ADDED` sont journalisés et `identity.membership_changed` est publié dans la **même transaction**.
- [ ] Étant donné la cible au plafond d'organisations (ADR §17.5.2 : appartenances actives dans organisations actives), alors `409 organization_limit_reached` **à l'acceptation** ; l'invitation reste `PENDING`.
- [ ] Étant donné un compte sans téléphone vérifié, alors `403 phone_verification_required` (aligné sur Q-CP5) ; l'invitation reste `PENDING`.
- [ ] Étant donné la cible déjà membre actif de l'organisation, alors `409 already_member` ; l'invitation passe à `ACCEPTED` sans doublon de membre. [à confirmer : ou reste `PENDING`]
- [ ] Étant donné deux acceptations simultanées du même jeton (deux sessions), alors une seule réussit (mise à jour conditionnelle `PENDING -> ACCEPTED`), l'autre reçoit `404 invitation_invalid` ; une seule appartenance existe.
- [ ] Étant donné un jeton rejoué après acceptation, alors `404 invitation_invalid`.
- [ ] Étant donné `POST ID organization-invitations/decline/`, alors l'invitation passe à `DECLINED`, l'inviteur est notifié (sans identité de la cible au-delà de son `public_display_name`), et le jeton est inutilisable.
- [ ] Étant donné un visiteur non connecté qui ouvre le lien, alors le front le conduit à la connexion ou à l'inscription puis le ramène à l'écran d'acceptation avec le jeton conservé côté navigateur (pas dans les journaux serveur de l'URL : le jeton voyage dans le fragment ou dans le corps, jamais dans une URL d'API en `GET`).
- [ ] Étant donné les tentatives de devinette de jeton, alors un throttle par compte et par IP (`invitation_redeem`) limite les essais ; au-delà, `429`.
- [ ] Étant donné l'inviteur révoqué ou rétrogradé entre l'envoi et l'acceptation, alors `404 invitation_invalid` (R-L5) et `INVITATION_REFUSED` (`authority_lost`) est journalisé.
- [ ] Étant donné l'acceptation, alors le membre n'a **que** les capacités de son rôle (le contexte actif ne confère rien par lui-même, règle 2) ; aucune vérification ni badge n'est créé.
- [ ] Étant donné la notification de bienvenue existante (« Vous avez rejoint une organisation »), alors elle reste produite par l'abonné existant sans donnée supplémentaire.

Règles métier : R-L3, R-L5, R-L10 ; plafond comptant seulement les appartenances actives en organisation active (ADR §17.5.5).
Hors périmètre : acceptation sans compte ; rejoindre « librement » une organisation publique ; invitation d'un compte restreint (refus neutre).
Questions ouvertes : Q-L1-1, Q-CLI4 (plafond).

---

### L1-01e — Changer le rôle d'un membre

En tant que **propriétaire ou administrateur**, je veux changer le rôle d'un membre, afin d'ajuster ses droits sans le retirer.

Réf. : CDC §3.1 ; dossier client IAM-006, IAM-007 ; doc 06 §7 (« ne peut déléguer au-delà de son autorité ») ; ADR 0006 §5, §17.2 C ; lot 1.
Dépend de : L1-01b.
Revue `auditeur-securite` obligatoire (escalade de rôle).

Critères d'acceptation (testables) :
- [ ] Étant donné `PATCH ID organizations/<uuid>/members/<membership_id>/` avec `{"role": "ADMIN"}`, quand un propriétaire l'appelle sur un membre actif, alors `200` avec le membre (mêmes clés que L1-01b), `MEMBERSHIP_ROLE_CHANGED` journalisé (rôle avant et après), `identity.membership_changed` (`role_changed`) publié ; l'effet sur les capacités est immédiat à la requête suivante de la cible.
- [ ] Étant donné un administrateur, quand il tente de changer un propriétaire, ou d'attribuer `OWNER`, ou de s'attribuer un rôle supérieur, alors `403 DENY_PERMISSION` et rien n'est modifié.
- [ ] Étant donné un éditeur ou un analyste, alors `403 DENY_PERMISSION`.
- [ ] Étant donné le dernier propriétaire **effectif** (R-L8) que l'on rétrograde, ou le seul propriétaire de l'organisation, alors `409 last_owner` (tableau de messages UX : « Une organisation doit toujours avoir au moins un propriétaire. ») et l'état est inchangé.
- [ ] Étant donné la cible `REVOKED` ou inexistante, alors `404 member_not_found` ; étant donné un `membership_id` d'une **autre** organisation, alors le même `404` (pas d'accès entre organisations).
- [ ] Étant donné une cible dont le compte est inactif ou restreint, alors `400 user_unavailable` (neutre).
- [ ] Étant donné un changement vers le même rôle, alors `200` sans trace ni événement (idempotent).
- [ ] Étant donné la promotion vers `OWNER` : voir L1-01h (mêmes règles et exigences de confirmation).
- [ ] Étant donné la rétrogradation d'un membre qui perd `review.reply` ou `offer.edit`, alors ses notifications correspondantes sont purgées (comportement existant, test de non-régression).
- [ ] Étant donné un changement qui touche un propriétaire (promotion ou rétrogradation), alors l'événement de visibilité du vendeur est émis (dette ADR §20 T9-1 n°4 : sans lui, la visibilité attend la commande horaire).
- [ ] Étant donné deux changements concurrents sur la même organisation, alors l'invariant « au moins un propriétaire » tient (test de concurrence déjà conçu pour L0-09 ; à rejouer sur MySQL, registre de recette ADR §17.5.4).

Règles métier : R8, R9, R10, R-L2, R-L9.
Hors périmètre : rôles configurables (Q-CLI1) ; branches.
Questions ouvertes : Q-L1-9.

---

### L1-01f — Retirer un membre

En tant que **propriétaire ou administrateur**, je veux retirer un membre de l'organisation, afin de couper immédiatement son accès (départ, erreur, conflit).

Réf. : CDC §3.1 (« Le départ d'un membre retire son accès sans supprimer son compte personnel ») ; dossier client IAM-006, UF-29 (« Admin peut modifier/révoquer l'accès », « Départ de l'organisation coupe l'accès sans supprimer le compte personnel »), doc 06 §19, AC-07 ; lot 1.
Dépend de : L1-01b.

Critères d'acceptation (testables) :
- [ ] Étant donné `DELETE ID organizations/<uuid>/members/<membership_id>/`, quand un propriétaire retire un membre actif, alors `204`, l'appartenance passe à `REVOKED` (`end_reason = removed`, `ended_by`), `MEMBERSHIP_REVOKED` est journalisé et `identity.membership_changed` (`revoked`) est publié.
- [ ] Étant donné la requête suivante de la personne retirée avec son **même jeton** d'accès et `X-Context: ORGANIZATION:<id>`, alors `403 DENY_RELATION` ; son contexte personnel reste utilisable et ses offres personnelles sont intactes.
- [ ] Étant donné les offres, avis, conversations de l'organisation écrites par la personne retirée, alors ils restent à l'organisation (`created_by` reste trace) ; ses notifications d'organisation sont purgées et elle reçoit une notification **personnelle** de retrait (comportement existant).
- [ ] Étant donné un administrateur, quand il tente de retirer un propriétaire, alors `403 DENY_PERMISSION` ; un éditeur ou un analyste : `403 DENY_PERMISSION`.
- [ ] Étant donné qu'on se retire soi-même par cette route, alors `400 use_leave` (la sortie volontaire garde `POST …/leave/`).
- [ ] Étant donné le dernier propriétaire (organisation ACTIVE ou SUSPENDED), alors `409 last_owner` ; organisation ARCHIVED : permis et tracé (règle existante, ADR §17.5.6).
- [ ] Étant donné la révocation d'un propriétaire, alors l'événement de visibilité du vendeur est émis (dette ADR §20 T9-1 n°4).
- [ ] Étant donné un membre retiré qui détenait des invitations en attente, alors elles deviennent inacceptables (L1-01c).
- [ ] Étant donné un ancien membre, alors il ne peut **pas** se réinviter lui-même ; il faut une nouvelle invitation acceptée (réactivation de la même ligne, R12).
- [ ] Étant donné un membre retiré qui ne peut plus lire une conversation d'organisation, alors l'historique reste lisible par les membres habilités (acquis T7, test de non-régression).

Règles métier : R9, R11, R-L2.
Hors périmètre : suppression de compte ; blocage de la réinvitation (liste noire) : non demandé.
Questions ouvertes : aucune propre.

---

### L1-01g — Quitter une organisation (livrée par L0-09 ; compléments de parcours)

En tant que **membre**, je veux quitter une organisation, afin de ne plus agir en son nom sans perdre mon compte personnel.

Réf. : CDC §3.1 ; dossier client IAM-006, UF-29 ; doc 06 §19 ; lot 1 (service et endpoint livrés par L0-09).
**État : Fait**, avec trois compléments.

Critères d'acceptation (nouveaux, au-delà des tests existants) :
- [ ] Étant donné le dernier propriétaire d'une organisation ACTIVE qui tente de partir, alors `409 last_owner` ; le message UX de L1-01 lui indique la marche à suivre : transférer la propriété (L1-01h) ou archiver.
- [ ] Étant donné un propriétaire qui part alors qu'un autre propriétaire existe mais que ce dernier est **inactif ou sanctionné** (donc non effectif, R-L8), alors le départ est **permis** par la règle actuelle (elle compte les appartenances) mais **provoque** une organisation sans propriétaire effectif ; **comportement à trancher** (Q-L1-9) : refuser avec `last_owner` ou accepter et signaler.
- [ ] Étant donné un départ qui touche un propriétaire, alors l'événement de visibilité est émis (dette T9-1).

Règles métier : R8, R11.
Hors périmètre : bouton « Quitter » de l'écran E6 (déjà spécifié, D10).
Questions ouvertes : Q-L1-9.

---

### L1-01h — Transférer la propriété (et promouvoir un propriétaire)

En tant que **propriétaire**, je veux transférer la propriété à un autre membre (ou en nommer un second), afin de pouvoir quitter l'organisation ou de la sécuriser.

Réf. : CDC §3.1 ; dossier client IAM-006 ; doc 09 §8 (« Changement owner/admin : preuve renforcée + audit ») ; ADR 0006 §5 (« le transfert = deux changements de rôle, plusieurs propriétaires étant permis ») ; lot 1.
Dépend de : L1-01e.
Revue `auditeur-securite` obligatoire.

Critères d'acceptation (testables) :
- [ ] Étant donné `POST ID organizations/<uuid>/transfer-ownership/` avec `{"membership_id": "...", "my_new_role": "ADMIN"}`, quand un propriétaire l'appelle sur un membre actif, alors la cible devient `OWNER` et l'acteur prend `my_new_role` (par défaut `ADMIN`, jamais `OWNER`) dans **une seule transaction** ; deux `MEMBERSHIP_ROLE_CHANGED` et un `ORG_OWNERSHIP_TRANSFERRED` sont journalisés ; deux événements `membership_changed` sont publiés.
- [ ] Étant donné un administrateur, un éditeur ou un analyste, alors `403 DENY_PERMISSION` ; une cible `REVOKED` ou d'une autre organisation : `404 member_not_found` ; soi-même : `400 invalid_transfer` ; cible inactive ou restreinte : `400 user_unavailable`.
- [ ] Étant donné un échec en cours d'opération (ex. verrou perdu, invariant violé), alors rien n'est modifié (atomicité testée).
- [ ] Étant donné la **nomination d'un second propriétaire sans quitter** (promotion simple via `PATCH …/members/<id>/` avec `OWNER`), alors seul un propriétaire peut le faire, l'action est journalisée comme `MEMBERSHIP_ROLE_CHANGED` et notifie la cible.
- [ ] Étant donné l'action la plus sensible de l'organisation (donne l'archivage et, plus tard, la facturation), alors le serveur exige une **confirmation explicite** dans la requête (`{"confirm": true}`) et, selon la décision Q-L1-5, une **nouvelle saisie du mot de passe** ; sans cela `400 confirmation_required`.
- [ ] Étant donné qu'une organisation SUSPENDED ou ARCHIVED, alors le transfert suit les règles existantes (`_authorize_member(..., allow_archived=True)` : permis sur archivée, refusé sur suspendue).
- [ ] Étant donné le transfert, alors la cible reçoit une notification (existante) et l'événement de visibilité est émis.
- [ ] Étant donné un plan payant, un abonnement ou un paiement, alors ni le transfert ni la promotion n'en dépendent ni ne les modifient (test d'absence de paramètre, règle 2).

Règles métier : R8, R9, R10, R-L9.
Hors périmètre : transfert à un compte qui n'est pas déjà membre (il faut d'abord inviter puis promouvoir) ; consentement de la cible à devenir propriétaire (Q-L1-4).
Questions ouvertes : Q-L1-4, Q-L1-5.

---

### L1-01i — Revendiquer une organisation existante

En tant que **personne qui représente une organisation déjà présente sur la plateforme**, je veux déposer une demande de revendication avec des preuves d'autorité, afin d'être validée avant d'obtenir un rôle, sans jamais écarter un propriétaire existant.

Réf. : CDC §3.1 (« Une revendication d'organisation existante ne donne aucun droit avant validation ») ; dossier client IAM-005, UF-04 (« Une revendication en attente ne permet pas d'administrer l'organisation » ; « Le paiement d'un plan ne remplace pas la validation d'autorité »), doc 06 §7 (« Claim organisation »), doc 07 §5 (Organisation : « représentant/autorité »), doc 09 §8, doc 13 `OrganizationClaim` ; lot 1.
Dépend de : ADR (modèle de revendication, stockage des preuves) ; L1-01j (décision).
Revue `auditeur-securite` obligatoire (fraude, fichiers).

**Qu'est-ce qu'une « fiche existante » ?** Aucune source ne le définit pour la V1. Dans le code, toute organisation naît avec un propriétaire. Deux cas se présentent donc : (a) une organisation créée par un tiers, avec ou sans mauvaise foi (**homonyme ou usurpation**, Q-CLI8) ; (b) une organisation **sans propriétaire effectif** (propriétaire sanctionné ou désactivé, compte inaccessible). L'absence de fiche pré-créée par le personnel est constatée. Hypothèse H4 : la revendication vise toute organisation `ACTIVE` ou `SUSPENDED` listée ou connue du demandeur, à laquelle il n'a pas déjà un rôle suffisant ; elle n'est pas un import en masse.

Critères d'acceptation (testables) :
- [ ] Étant donné un compte actif, non restreint, avec téléphone vérifié, quand il appelle `POST ID organizations/<uuid>/claims/` avec `{"requested_role": "OWNER", "statement": "..."}` (texte libre borné à 1 000 caractères, sans donnée personnelle exigée), alors `201 {claim_id, status: "PENDING", ...}` et `ORG_CLAIM_SUBMITTED` est journalisé ; **aucune appartenance n'est créée** et le contexte de l'organisation n'apparaît pas dans `GET contexts/` du demandeur.
- [ ] Étant donné une revendication `PENDING`, alors le demandeur ne peut, au titre de cette demande, ni lire l'espace interne, ni publier, ni inviter, ni voir la liste d'équipe (test d'absence de capacité : `DENY_RELATION`).
- [ ] Étant donné `POST ID organizations/<uuid>/claims/<id>/evidence/` (multipart, type de pièce et fichier), alors la pièce est stockée dans le **stockage privé hors `MEDIA_ROOT`**, avec les mêmes contrôles de type, de taille, de pixels et de contenu PDF que les pièces KYB (ADR §18 n°4 et 5), sans métadonnées EXIF ; aucune réponse JSON ne contient l'URL ni le contenu du fichier ; `ORG_CLAIM_EVIDENCE_ADDED` est journalisé sans nom de fichier.
- [ ] Étant donné les pièces d'une revendication, alors elles sont **invisibles** des membres de l'organisation revendiquée (règle 10) et ne produisent **aucun claim public** (`verified_claims` inchangé, règle 3).
- [ ] Étant donné un compte qui a déjà une revendication `PENDING` sur la même organisation, alors `409 claim_exists` ; au-delà du plafond de revendications en attente par compte (`IdentitySettings`, valeur de départ à confirmer), `409 claim_limit_reached` ; débit limité (throttle `org_claim`, `429`).
- [ ] Étant donné un membre actif **déjà propriétaire**, alors `409 already_owner` ; un membre d'un autre rôle peut revendiquer `OWNER` seulement si l'organisation n'a pas de propriétaire effectif (sinon `409 owner_exists`, la promotion se fait par un propriétaire, L1-01e).
- [ ] Étant donné `DELETE ID organizations/<uuid>/claims/<id>/`, alors le demandeur retire sa demande (`WITHDRAWN`), ses pièces sont supprimées du stockage privé (sauf conservation décidée par Q-CLI6, voir H6), `ORG_CLAIM_WITHDRAWN` est journalisé.
- [ ] Étant donné `GET ID claims/mine/`, alors le demandeur lit le statut, le motif codé d'un refus éventuel, les demandes d'information ; jamais l'identité du personnel décideur.
- [ ] Étant donné les propriétaires et administrateurs effectifs d'une organisation visée, alors ils sont notifiés qu'**une revendication a été déposée**, **sans identité** du demandeur (hypothèse H5 : prévenir sans nommer ; Q-L1-6), avec un lien « Contester » inactif en V1 (le personnel contactera). Une organisation sans propriétaire effectif ne notifie personne.
- [ ] Étant donné une organisation `ARCHIVED`, alors `409 DENY_OBJECT_STATE` (Q-SUSP3 : la restauration d'une organisation archivée n'est pas décidée).
- [ ] Étant donné la revendication, alors elle ne consomme aucun plan, n'en exige aucun et un plan payant ne l'accélère pas (règle 2 ; le délai de traitement ne dépend pas d'un plan).

Règles métier : R-L6, R-L9 ; règle 10 (preuves privées) ; règle 3 (aucun badge).
Hors périmètre : parcours KYB (L1-02) ; « Autorité vérifiée » comme claim public (doc 07 §3, non retenu par le CDC §3.1) ; revendication de masse d'une fiche importée ; revendication d'un profil prestataire (L1-04).
Questions ouvertes : Q-CLI8, Q-CLI6, Q-L1-6, Q-L1-8 (preuves demandées, rôle accordé).

---

### L1-01j — Décider d'une revendication et secourir une organisation sans propriétaire

En tant que **personnel habilité à la vérification**, je veux examiner une revendication, la décider avec un second avis quand elle est contestée, et réattribuer un propriétaire à une organisation orpheline, afin qu'aucune organisation ne reste sans autorité valide et qu'aucun propriétaire légitime ne soit écarté.

Réf. : doc 09 §8 (existence, identité du demandeur, lien, conflit, scope, « Changement owner/admin : preuve renforcée + audit, four-eye si contesté »), OPS-10, OPS-AC-16 ; dossier client IAM-005, IAM-006 ; ADR 0006 §15 et §17.5.1 (« chemin de secours audité du personnel (réattribution du propriétaire sur preuve) et sort d'une organisation devenue orpheline ») ; règles 3, 12 ; lot 1.
Dépend de : L1-01i.
Revue `auditeur-securite` obligatoire. **Étend le pouvoir du personnel** (§7, C2).

Définition (H7) : une organisation est **sans propriétaire effectif** (R-L8) quand aucune appartenance `OWNER` `ACTIVE` n'a un compte actif et sans sanction bloquante. Cas typiques : propriétaire unique banni ou désactivé ; organisation convertie `SUSPENDED` dont le titulaire est parti ; propriétaires tous partis d'une organisation archivée (hors périmètre, voir ci-dessous).

Critères d'acceptation (testables) :
- [ ] Étant donné la file `GET ID claims/review-queue/` réservée à la permission dédiée (`review_organizationclaim`, ajoutée à `setup_roles` et à l'admin ; une permission inconnue fait toujours échouer `setup_roles`), alors elle liste les revendications `PENDING` avec : organisation (id, nom, type, statut), indicateur `has_effective_owner`, demandeur sous forme `{id interne du dossier, display_name abrégé}`, ancienneté, nombre de pièces ; **jamais** téléphone, e-mail ni pièces d'identité en clair.
- [ ] Étant donné `GET …/claims/<id>/evidence/<id>/download/`, alors le téléchargement est réservé à `review_organizationclaim` et refusé (403, `KYC_DOWNLOAD_DENIED`-équivalent journalisé) au demandeur lui-même et à tout (ancien) membre de l'organisation.
- [ ] Étant donné `POST ID claims/<id>/decision/` avec `{"decision": "approved", "granted_role": "OWNER", "reason_code": "..."}`, quand l'organisation **n'a pas** de propriétaire effectif, alors l'appartenance est créée (ou la ligne existante réactivée, R12) avec le rôle accordé **dans la même transaction** que `ORG_CLAIM_DECIDED` et `ORG_OWNERSHIP_RESTORED` ; `identity.membership_changed` est publié ; l'événement de visibilité est émis ; le demandeur est notifié.
- [ ] Étant donné une organisation **avec** propriétaire effectif (revendication contestée), alors une première approbation ne fait que passer la demande à `AWAITING_SECOND_APPROVAL` ; elle n'est exécutée que par la décision d'un **second** membre du personnel **différent** (test : même personne deux fois = `403`) ; aucun rôle `OWNER` n'est accordable dans ce cas (`409 owner_exists`, voir H8) ; le rôle maximal accordable est `ADMIN`.
- [ ] Étant donné un décideur qui est ou a été membre (tout statut), créateur de l'organisation, ou le demandeur, alors `403 interest_conflict` et trace du refus (même règle que la réactivation et la décision KYB, ADR §20 correction 2).
- [ ] Étant donné `decision = rejected`, alors le motif est un **code** d'une liste fermée (`insufficient_evidence`, `not_authorized`, `existing_owner_contests`, `duplicate`, `other`) ; aucun texte libre contenant des données personnelles n'est exposé au demandeur ; `info_requested` renvoie à l'état `NEEDS_INFO` et permet un nouveau dépôt de pièces.
- [ ] Étant donné un compte demandeur devenu inactif ou restreint entre-temps, alors l'approbation est refusée avec `400 user_unavailable` (neutre côté demandeur).
- [ ] Étant donné l'approbation, alors **aucun badge de vérification** n'est créé ni modifié (test : `verified_claims` identique avant et après) et **aucun plan** n'intervient (test d'absence de paramètre).
- [ ] Étant donné une organisation `SUSPENDED`, alors l'approbation donne l'appartenance **sans** lever la suspension (la levée reste l'action `reactivate_organization`) ; une organisation `ARCHIVED` : refus.
- [ ] Étant donné la liste des organisations sans propriétaire effectif (`GET ID organizations/orphans/` ou vue d'administration filtrée, réservée à la permission de revue), alors chaque ligne porte : organisation, statut, nombre de membres actifs par rôle (comptage, pas de noms), date depuis laquelle elle est orpheline ; aucune coordonnée.
- [ ] Étant donné une organisation orpheline qui a des membres actifs (ex. un administrateur), alors ce membre peut déposer une revendication de rôle `OWNER` (L1-01i) : elle suit le même parcours ; il n'y a **aucun** chemin de secours hors de ce parcours (pas d'« action de support » sans dossier).
- [ ] Étant donné la commande de détection `list_orphan_organizations` (lecture seule, cron facultatif), alors elle sort des UUID et des comptages, jamais de donnée personnelle (`check_legacy_conversion`-style).
- [ ] Étant donné les SLA : aucune valeur n'est codée ; si un délai de traitement est promis, il vient d'un réglage et le client doit l'avoir fixé (Q-L1-8).

Règles métier : R-L6, R-L7, R-L8, R-L9 ; règle 12 (quatre yeux, acteur, second approbateur, ancien statut, motif codé).
Hors périmètre : organisation ARCHIVED sans membre (restauration : Q-SUSP3) ; fusion d'organisations en doublon ; contestation par le propriétaire en place (bouton inactif en V1 : traité par le personnel hors application, Q-L1-6) ; suspension préventive d'une organisation usurpatrice (action de modération existante).
Questions ouvertes : Q-L1-5, Q-L1-6, Q-L1-8, Q-CLI8.

---

### L1-01k — Préalables d'équipe à la suppression de compte

En tant que **personnel (utilisateur) qui veut quitter la plateforme**, je veux savoir quelles organisations m'empêchent de supprimer mon compte et les résoudre (transférer ou quitter), afin que la suppression ne laisse aucune organisation orpheline.

Réf. : ADR 0006 §17.5.1 (`assert_account_removable`, dette « suppression de compte et dernier propriétaire »), §19.3.5, §20 (T9-3 : « Pas de “supprimer mon compte” exposé en V1 ; le chemin est l'admin (L1) ») ; CDC §3.1 (« sans supprimer son compte personnel » : sens inverse) ; règle 10 ; lot 1.
**Lacune de source :** ni le CDC ni le dossier client ne décrivent une suppression libre-service du compte ni sa durée de conservation (LEG-PRV, doc 12). Cette story ne crée **pas** la suppression : elle livre seulement le **côté équipe** du parcours.

Critères d'acceptation (testables) :
- [ ] Étant donné `GET ID me/account-deletion-blockers/` (authentifié), alors la réponse liste les organisations où le compte est **seul propriétaire actif** d'une organisation ACTIVE ou SUSPENDED (même règle que `assert_account_removable`) : `{organization_id, name, status, other_members_count, suggested_action}` avec `suggested_action` parmi `transfer_ownership`, `archive`, `wait_for_unsuspension` ; aucune donnée d'un autre membre n'est exposée (comptage seulement).
- [ ] Étant donné les deux autres blocages de la garde (`blocking_sanction`, `open_grave_report`), alors ils ne sont **pas** détaillés (pas de fuite d'un signalement : un seul code `other_blocker` générique).
- [ ] Étant donné qu'aucune organisation ne bloque, alors `200` avec une liste vide ; le front affiche que l'équipe n'empêche rien (la suppression elle-même n'est pas offerte tant que la story correspondante n'existe pas).
- [ ] Étant donné la résolution d'un blocage par transfert (L1-01h) ou archivage, alors le blocage disparaît à l'appel suivant (sans cache).
- [ ] Étant donné l'invariant « dernier propriétaire » sur une organisation SUSPENDED, alors le message explique l'issue (déjà implémenté : attendre la levée ou contacter le support).
- [ ] Étant donné une tentative d'écriture d'un audit, alors `ACCOUNT_DELETION_BLOCKED_BY_ORG` n'enregistre que des UUID.
- [ ] Étant donné une suppression future, alors la garde `assert_account_removable` reste l'unique point de décision (pas de seconde règle dans l'API) ; l'**exposition utilisateur** de la suppression exige d'abord de traiter le risque TOCTOU noté en ADR §20 T9-3 n°6 a (verrouillage) ; cette dette est liée à la story future.

Règles métier : règle 10 ; R8.
Hors périmètre : endpoint « supprimer mon compte », délai de réflexion, e-mail de confirmation, conservation des sanctions et signalements (LEG-PRV).
Questions ouvertes : Q-L1-10 (la suppression libre-service est-elle voulue en V1 ? qui la porte ?).

---

### L1-01l — Noms réservés et signalement d'usurpation d'une organisation

En tant que **modérateur / personnel**, je veux empêcher la création d'une organisation sous un nom réservé ou imitant une organisation vérifiée, et recevoir les signalements d'usurpation, afin de limiter le risque d'usurpation avant la revendication.

Réf. : ADR 0006 §14 (Q-CLI8), §17.5.3, §19.2 (collision de noms, signalement) ; dossier client OPS-10 ; règles 3, 10 ; lot 1 (priorité inférieure ; peut suivre L1-01i/j).

Critères d'acceptation (testables) :
- [ ] Étant donné une liste de noms réservés **configurable en base** (règle 11, éditable au back-office, vide au départ : aucune valeur n'est inventée), quand un nom normalisé (casse, accents, espaces, ponctuation repliés) correspond à une entrée, alors la création et le renommage sont refusés par `400 name_reserved` (message neutre, sans dire quelle entrée) et `ORG_NAME_RESERVED_REFUSED` est journalisé sans le nom.
- [ ] Étant donné une organisation dont le nom normalisé correspond à celui d'une organisation **ayant un claim vérifié**, alors la création est **permise** (homonymes légitimes, A12 de l'ADR) mais l'organisation est **marquée pour revue** et n'affiche aucun badge ; test : aucun claim n'est copié.
- [ ] Étant donné `POST` d'un signalement d'usurpation avec cible `organization` (ajoutée à `moderation.TARGET_RESOLVERS`), alors les membres de cette organisation ne peuvent pas la signaler (`acts_for_context`), un tiers le peut, et le signalement arrive dans la file de modération existante.
- [ ] Étant donné la liste, alors les modifications sont auditées (`SETTINGS_CHANGED`) comme les autres réglages.

Règles métier : règle 3 (la collision de noms ne vaut jamais vérification) ; règle 11.
Hors périmètre : unicité des noms (interdite si conditionnelle ; inutile si absolue, A12) ; détection phonétique.
Questions ouvertes : Q-CLI8 (qui fournit la liste ; faux positifs acceptables ?).

---

## 6. Dettes de L0-09 qui relèvent de L1-01

| # | Dette | Source | Traitée par |
|---|---|---|---|
| D1 | `add_member` : ajout direct sans consentement, non exposable ; invitation + acceptation + revue sécurité requises | ADR §17.5.2 ; docstring `organizations.add_member` | L1-01c, L1-01d |
| D2 | Chemin de secours audité du personnel (réattribution du propriétaire sur preuve) ; sort d'une organisation orpheline | ADR §15, §17.5.1 ; JOURNAL 09/11/2026 « Dettes ouvertes » | L1-01i, L1-01j |
| D3 | Endpoints d'équipe (`members`) et « supprimer mon compte » (côté équipe) à livrer avant L1-01 selon le journal | JOURNAL 09/11/2026 (fin) | L1-01b, e, f, h, k |
| D4 | Liste de noms réservés ; signalement d'usurpation ; collision avec une organisation vérifiée | ADR §17.5.3, §19.2, §14 Q-CLI8 | L1-01l |
| D5 | Un changement d'appartenance (départ, révocation, promotion d'un propriétaire) n'annonce pas d'événement de visibilité ; la commande horaire `sync_seller_visibility` rattrape | ADR §20 T9-1 n°4 | L1-01e, f, g, h, j |
| D6 | TOCTOU de la garde de suppression de compte ; à traiter si la suppression est exposée | ADR §20 T9-3 n°6 a | L1-01k (point de vigilance) |
| D7 | Registre de recette MySQL : deux ajouts simultanés d'un compte quand il reste une place ; deux départs simultanés de deux propriétaires | ADR §17.5.4 | QA, hors CI ; à rejouer avant production |
| D8 | `Membership.status = INVITED` « s'ajoutera avec L1-01 sans changer le schéma » (ADR §4.3) : **à réviser** : un invité sans compte n'a pas de `user` ; modèle d'invitation séparé recommandé | ADR §4.3 | ADR à produire (§7, C1) |
| D9 | Cache partagé obligatoire pour les throttles (LocMemCache par processus) : les limites `invitation_*`, `org_claim` n'ont de sens global qu'avec lui | ADR §19.2 | Prérequis de production (DoD) |
| D10 | Vérification d'e-mail absente (seul `phone_verified`) : aucune invitation ou revendication ne peut s'appuyer sur un e-mail | ADR 0002 (dette connue) ; L0-09 spec §Hors périmètre | Contrainte de conception (H1, H2) |
| D11 | Notification de statut d'organisation : lien `/organizations/<uuid>` ; notification KYB et de membership gardent `link='/dashboard'` | ADR §21 n°7 c ; `notifications/events.py` | L1-01 (corriger le lien vers l'écran Équipe) |
| D12 | Q-SUSP3 (restauration d'une organisation archivée) et Q-SUSP5 (prévenir les propriétaires d'organisations converties suspendues) | JOURNAL ; `L0-09-ecran-organisation-suspendue.md` §10 | Question client ; Q-SUSP5 se règle en grande partie par la revendication |
| D13 | Messages `last_owner` UX « variante [L1-01] » pour rétrogradation et retrait | `L0-09-ecrans-contextes.md` (clé `last_owner`) | Front L1-01 |
| D14 | `ContextDenied` pour une organisation inexistante renvoie `DENY_RELATION` (pas d'oracle) : les nouvelles routes doivent suivre | ADR §15 n°3 | Toutes les stories |

---

## 7. Contradictions et lacunes (exposées, non tranchées)

| # | Constat | Options | Recommandation de l'analyste |
|---|---|---|---|
| **C1** | **ADR 0006 §17.2 C** prévoit `POST members/ {"identifier": téléphone ou e-mail}` avec réponse neutre `202` pour un compte inconnu, et l'écran E6 cible (UX §7.7) « formulaire par numéro de téléphone ou e-mail d'un compte existant ». Or §17.5.2 interdit l'ajout direct et exige invitation + acceptation. De plus, l'e-mail n'est pas vérifié (D10), et une recherche par identifiant, même neutre, est un oracle par le temps de réponse, la notification, ou l'effet sur l'inviteur. | (a) Lien à usage unique, sans recherche de compte (H1). (b) Invitation adressée à un téléphone vérifié, rattachée au compte qui possède ce numéro. (c) Les deux. | (a), complété par (b) plus tard si le client veut une notification in-app. Amender l'ADR §17.2 C (remplacer `POST members/` par `invitations/`) et §4.3 (modèle d'invitation séparé). |
| **C2** | **Le personnel ne devait jamais attribuer de rôle** (ADR §11.4 : « `Membership` en lecture seule ; le personnel n'attribue pas de rôle »). Revendication et secours exigent précisément que le personnel **crée** une appartenance. | (a) Service d'attribution unique, réservé à la décision de revendication, avec quatre yeux, conflit d'intérêts, audit, motif codé, jamais depuis l'admin. (b) Refuser tout pouvoir du personnel : pas de secours. | (a). Doc 09 §8 prévoit « Créer membership/role limité » après « Authority verified » ; le conflit n'est qu'avec l'ADR. À acter dans le nouvel ADR ; l'admin Django `Membership` reste en lecture seule. |
| C3 | Doc 06 donne des rôles supplémentaires (recruteur, facturation, branche…) et un « Owner / Org Admin » regroupés ; le CDC §3.1 en fixe quatre. | Déjà en E1/E3 de L0-09. | Maintenir quatre rôles (CDC fait foi). Pas de nouvelle question. |
| C4 | Doc 02 UF-04 : « Choix Créer, Revendiquer ou Rejoindre… 6. Configuration profil public, **branches** et modules ». Les branches sont hors V1 (E2). | — | Ignorer branches (hors périmètre). |
| C5 | Doc 02 UF-04 : « 4. Validation de l'autorité selon le cas » et doc 07 §5 : contrôles « représentant/autorité » pour l'organisation, doc 07 §3 : badge « Autorité vérifiée » distinct. Le CDC §3.1 ne cite pas ce badge. | Badge public d'autorité ou statut interne seulement. | Statut interne seulement en L1-01 (règle 3 : un badge dit précisément ce qui a été vérifié ; aucun libellé validé par le client). Question Q-L1-8. |
| C6 | **Aucune source ne décrit une « fiche existante » pré-créée** (import, annuaire). La revendication de doc 13 suppose une organisation existante qui n'a pas de propriétaire légitime. | Voir L1-01i. | H4 ; question au client Q-L1-6. |
| C7 | Le CDC et le dossier client ne décrivent ni suppression libre-service du compte, ni durée de conservation (LEG-PRV). Le brief demande le côté équipe. | — | L1-01k limitée aux blocages ; Q-L1-10. |
| C8 | La règle `last_owner` compte les **appartenances**, pas l'état des comptes : une organisation peut être sans propriétaire effectif (R-L8) alors que l'invariant est respecté. | (a) Refuser le départ/retrait/rétrogradation qui laisse zéro propriétaire **effectif**. (b) Garder la règle actuelle + secours (L1-01j). | (b) pour L1-01 (une règle plus stricte bloquerait des opérations légitimes quand un propriétaire est temporairement sanctionné) ; trancher avec le CP : Q-L1-9. |

---

## 8. Questions : statut des Q-CLI1 à Q-CLI8 et nouvelles questions

### 8.1. Q-CLI déjà ouvertes (L0-09 spec §5.4) : lesquelles bloquent L1-01

Légende : **Bloque** = la story concernée ne peut pas être clôturée sans réponse ; **Ne bloque pas** = l'hypothèse de travail suffit pour planifier et développer, et reste réversible par réglage ou petite modification.

| # | Sujet | Bloque ? | Hypothèse de travail par défaut | Si le client répond autrement |
|---|---|---|---|---|
| Q-CLI1 | 4 rôles suffisent ; branches hors V1 ; plusieurs propriétaires | Ne bloque pas | Quatre rôles en constantes, pas de branches, plusieurs propriétaires permis (déjà appliqué, D4 du CP). | Rôles configurables : tables derrière `can/authorize` ; branches : nouveau périmètre. |
| Q-CLI2 | Pièces KYB par type d'organisation ; une organisation non vérifiée publie-t-elle ? | Ne bloque pas L1-01 (relève de L1-02). Touche la revendication : les preuves d'autorité sont distinctes des pièces KYB | Revendication : preuves d'autorité libres (voir H6), pas de lien avec `OrganizationDocumentRequirement` ; publication indépendante de la vérification. | Si le client veut réutiliser les pièces KYB pour prouver l'autorité : relier revendication et `KycDocument` (à instruire en L1-02). |
| Q-CLI3 | Ce que le contexte personnel peut publier | Non | Sans objet pour L1-01. | — |
| Q-CLI4 | Nombre d'organisations par compte | Ne bloque pas | 10 appartenances actives en organisation active, réglable (acquis) ; vérifié à l'acceptation d'une invitation. | Réglage 1 à 100 ; séparer « créées » et « rejointes » = un second réglage. |
| Q-CLI5 | Consentement du contact de l'organisation | Non | Sans objet pour L1-01. | — |
| Q-CLI6 | Conservation des pièces et de l'audit | **Bloque** la clôture de L1-01i (preuves de revendication) mais pas son développement | H6 : pièces de revendication conservées dans le stockage privé jusqu'à la décision, puis **aucune purge automatique** (comme les pièces KYB ; `kyb_file_retention_days = 0`) ; retrait immédiat si le demandeur retire sa demande. Aucune durée inventée. Un réglage dédié (`claim_file_retention_days`, 0 = illimité) est posé, sans valeur. | Commande de purge planifiée après la réponse. |
| Q-CLI7 | Vérification d'identité du prestataire | Non | Sans objet. | — |
| Q-CLI8 | Unicité des noms, usurpation avant revendication | **Bloque L1-01i/j** (définition de la revendication) et **L1-01l** | A12 : homonymes permis ; plafond par compte ; nom verrouillé après vérification ; **revendication encadrée par le personnel** ; noms réservés = liste en base vide au départ ; signalement d'usurpation par la modération. | Unicité des noms normalisés en couche service si le client l'impose : prévoir les faux positifs. |

### 8.2. Questions nouvelles de L1-01

| # | Question | Destinataire | Hypothèse de travail |
|---|---|---|---|
| Q-L1-1 | **Mécanisme d'invitation :** lien à usage unique (H1), ou invitation rattachée à un téléphone vérifié ? Et peut-on inviter une personne sans compte (doc 02 UF-02) ? | CP, puis client | Lien à usage unique ; la personne sans compte s'inscrit puis accepte ; aucune recherche de compte. |
| Q-L1-2 | La plateforme envoie-t-elle elle-même un SMS ou un e-mail d'invitation (coût, anti-abus, e-mail non vérifié) ? | CP, client | Non en V1 : l'inviteur transmet le lien lui-même. |
| Q-L1-3 | Une invitation peut-elle conférer `ADMIN` ? (doc 02 UF-04 : « invitation comme simple membre sans droit d'administration »). | Client | `EDITOR` et `ANALYST` par invitation de tout membre habilité ; `ADMIN` seulement par invitation d'un **propriétaire** (R9 étendu) ; `OWNER` jamais (R-L4). À défaut de réponse, plus prudent : `ADMIN` par promotion, comme `OWNER`. |
| Q-L1-4 | Faut-il le **consentement** de la personne promue propriétaire ? | CP | Non en V1 : notification, confirmation explicite de l'acteur (L1-01h). |
| Q-L1-5 | Nouvelle saisie du mot de passe pour les actions critiques (transfert de propriété, archivage, approbation par le personnel) ? Aucune source ne l'impose ; doc 09 §8 demande une « preuve renforcée » pour owner/admin. | CP, client | Confirmation explicite côté API (`confirm: true`) ; ré-authentification : à décider (recommandée pour le transfert). |
| Q-L1-6 | **Qu'est-ce qu'une « fiche existante » revendicable** ? Le propriétaire en place est-il prévenu d'une revendication, avec ou sans identité du demandeur ? Peut-il la contester dans l'application ? | Client | H4/H5 : toute organisation active ou suspendue ; propriétaires et administrateurs prévenus **sans** identité du demandeur ; contestation traitée hors application par le personnel. |
| Q-L1-7 | Valeurs de départ des réglages : durée de validité d'une invitation (7 jours), plafond d'invitations en attente par organisation, plafond de revendications par compte. | CP | Réglages en base ; valeurs provisoires à poser par le CP, marquées « à confirmer » dans le code et dans le journal (aucune source). |
| Q-L1-8 | **Revendication : preuves attendues** (RCCM, mandat, lettre, pièce du représentant), **rôle accordé** (OWNER seulement sans propriétaire effectif ; ADMIN au plus sinon), **délai de traitement promis**, et **badge public** « Autorité vérifiée » ou pas (doc 07 §3). | Client | Preuves libres typées (`MANDATE`, `ID_REPRESENTATIVE`, `REGISTRATION_DOC`, `OTHER`) ; règles de rôle de H8 ; aucun SLA promis ; aucun badge. |
| Q-L1-9 | Faut-il refuser (a) un départ, retrait ou rétrogradation qui laisse zéro propriétaire **effectif**, ou (b) accepter et signaler ? Et affiche-t-on « dernier propriétaire » sur la ligne ? | CP | (b) : règle actuelle + secours ; indicateur `is_last_effective_owner` visible des propriétaires et administrateurs. |
| Q-L1-10 | La suppression libre-service du compte est-elle voulue en V1 ? Sinon, que fait-on de « supprimer mon compte » du backlog ? (Rien dans le CDC.) | CP, client (LEG-PRV) | Hors L1-01 ; L1-01k seulement. |
| Q-L1-11 | Qui fournit la **liste initiale de noms réservés** (grandes banques, administrations, opérateurs) ? | Client | Liste vide, alimentée en back-office. |
| Q-L1-12 | Le personnel de vérification est-il le bon rôle pour décider d'une revendication, ou faut-il un groupe distinct ? | CP | Permission dédiée `review_organizationclaim`, attribuée par `setup_roles` au groupe de vérification ; **jamais** au modérateur. |

### 8.3. Hypothèses de travail citées dans les stories (récapitulatif)

| # | Hypothèse | Questions liées |
|---|---|---|
| H1 | Invitation par lien à usage unique, jeton haché en base, aucune recherche de compte. | Q-L1-1, Q-L1-2 |
| H2 | Aucune invitation ni revendication ne s'appuie sur un e-mail (non vérifié) ; seul `phone_verified` compte. | D10 |
| H3 | `OWNER` jamais par invitation ; `ADMIN` par invitation d'un propriétaire seulement (à défaut de réponse : par promotion). | Q-L1-3 |
| H4 | Une « fiche existante » est toute organisation `ACTIVE` ou `SUSPENDED` ; pas d'import en masse. | Q-L1-6 |
| H5 | Propriétaires et administrateurs effectifs sont prévenus d'une revendication, sans identité du demandeur. | Q-L1-6 |
| H6 | Pièces de revendication en stockage privé, sans purge automatique tant que Q-CLI6 n'a pas de réponse. | Q-CLI6 |
| H7 | « Sans propriétaire effectif » = aucune appartenance `OWNER` `ACTIVE` avec compte actif et non sanctionné. | Q-L1-9 |
| H8 | Revendication : `OWNER` accordable seulement sans propriétaire effectif ; sinon `ADMIN` au plus, avec second approbateur. | Q-L1-8 |

---

## 9. Découpage proposé en tâches

Ordre critique : **ADR → B1 → B2 → (B3 ‖ B4) → B5/B6**, front en parallèle une fois le contrat figé. Une seule branche touche les migrations `identity` à la fois (ADR 0006 §10.1 ; `identity 0001 à 0014` existent).

| ID | Tâche | Agent | Contenu | Dépend de | Taille |
|---|---|---|---|---|---|
| **L1-01-A** | ADR (numéro libre suivant 0007) amendant ADR 0006 §4.3 et §17.2 C | architecte-technique | Modèle `OrganizationInvitation` (empreinte du jeton, statut, rôle, inviteur, expiration, étiquette) ; `OrganizationClaim` + `OrganizationClaimEvidence` ; service d'attribution par le personnel (C2) ; événements ; contrat d'API figé ; réglages `IdentitySettings` ; règle « propriétaire effectif » ; plan de migrations (une migration par changement logique) | cette spec | M |
| **L1-01-B1** | Endpoints d'équipe (L1-01b, e, f, h) | dev-backend | `members/` (liste, PATCH, DELETE), `transfer-ownership/`, service de lecture `list_members`, sérialiseurs, throttles `org_write`, OpenAPI, test de garde de routes, événement de visibilité sur mouvement de propriétaire | ADR | M |
| **L1-01-B2** | Invitations (L1-01c, d) | dev-backend, **auditeur-securite** | Modèle, services (`create`, `preview`, `accept`, `decline`, `revoke`), endpoints, throttles, commande `expire_invitations` + crontab, audit, événement, retrait de l'exposition de `add_member` (docstring et test), neutralité des réponses | ADR, B1 | L |
| **L1-01-B3** | Revendication et secours (L1-01i, j) | dev-backend, **auditeur-securite** | Modèles, dépôt de pièces (réutilise le contrôle de fichiers KYB et le stockage privé), file du personnel, téléchargement, décision à quatre yeux, conflit d'intérêts, permission `review_organizationclaim` + `setup_roles` + admin (lecture), notifications, détection des orphelines, commande `list_orphan_organizations` | ADR, B1 | L |
| **L1-01-B4** | Préalables de suppression (L1-01k) | dev-backend | `account-deletion-blockers`, tests, audit | B1 | S |
| **L1-01-B5** | Noms réservés et signalement d'usurpation (L1-01l) | dev-backend | Réglage de noms réservés (admin, audit de réglage), cible `organization` dans `moderation`, marquage pour revue | ADR ; Q-L1-11 | M |
| **L1-01-D** | Spécifications d'écran | designer-ux | E6 cible (liste, changer le rôle, retirer, transférer), invitation (création, liste, révocation, lien à copier), écran d'acceptation (connecté, non connecté), revendication (dépôt, statut), « mes revendications », état d'organisation orpheline, blocages de suppression ; **réviser le formulaire d'ajout par identifiant** de UX §7.7 (C1) ; textes `last_owner` variantes | ADR (contrat) | M |
| **L1-01-F1** | Front équipe | dev-frontend | Écran Équipe complet (L1-01b, e, f, h), `RoleBadge`, menus selon rôle et cible, gestion de `last_owner`, `DENY_*`, i18n, tests Vitest (masquage **et** gestion du refus serveur) | B1, D | M |
| **L1-01-F2** | Front invitation | dev-frontend | Création et liste d'invitations, lien copiable, page d'acceptation avec conservation du jeton après connexion/inscription (hors URL d'API), refus/acceptation, erreurs neutres | B2, D | M |
| **L1-01-F3** | Front revendication | dev-frontend | Parcours « Revendiquer », dépôt de pièces, suivi, états, notification | B3, D | M |
| **L1-01-F4** | Front back-office | dev-frontend ou admin Django | File du personnel : à trancher avec l'architecte (admin Django suffisant pour la file ? cohérent avec la file KYC existante) | B3 | S |
| **L1-01-S** | Revue sécurité | auditeur-securite | Menaces : énumération de comptes par invitation/aperçu (timing, corps, codes), entropie et stockage du jeton, rejeu, concurrence d'acceptation, escalade après rétrogradation de l'inviteur, IDOR sur `membership_id` / `invitation_id` / `claim_id`, fichiers de preuve (ClamAV, prérequis de production ADR §18 n°4), fuite dans audit/outbox/notifications, throttle partagé (D9), fraude à la revendication (usurpation), conflit d'intérêts du personnel, quatre yeux contournable | B2, B3 | — |
| **L1-01-Q** | Recette | qa-testeur | Scénarios de §10 ; non-régression `identity`, `notifications`, `marketplace`, `moderation`, `common.DomainBoundariesTests` ; test de concurrence MySQL au registre | tout | M |

Relecture (`relecteur-code`) à la fin de chaque tâche. `DomainBoundariesTests` doit rester vert (pas de clé étrangère inter-domaines ; la cible `organization` de la modération passe par `identity.services`).

---

## 10. Scénarios de recette (pour `qa-testeur`)

1. Création -> invitation `EDITOR` -> acceptation par un second compte -> l'éditeur publie sous l'organisation et lit « Qui a demandé » (`contact.view_requesters`) ; il ne peut ni inviter, ni changer un rôle, ni retirer un membre (`DENY_PERMISSION`).
2. Invitation expirée, révoquée, rejouée, acceptée en double : réponses identiques `invitation_invalid`.
3. Inviteur rétrogradé après l'envoi : l'invitation devient inacceptable.
4. Cible au plafond d'organisations : refus à l'acceptation, invitation toujours `PENDING`.
5. Administrateur qui tente de promouvoir `OWNER`, de retirer un propriétaire, de s'élever : `DENY_PERMISSION`.
6. Retrait d'un membre : sa requête suivante avec le même jeton est refusée sous l'organisation et acceptée en personnel.
7. Dernier propriétaire : départ, retrait, rétrogradation refusés ; transfert puis départ réussis.
8. Propriétaire unique sanctionné : organisation masquée ; un administrateur dépose une revendication `OWNER` ; le personnel (sans lien) approuve ; l'organisation redevient publique ; trace `ORG_OWNERSHIP_RESTORED`.
9. Revendication contestée : une approbation seule n'exécute rien ; la même personne ne peut pas approuver deux fois ; le rôle `OWNER` n'est pas accordable ; l'ancien propriétaire reste en place.
10. Décideur membre ou créateur : `interest_conflict`.
11. Aucune fuite : charges de `members/`, `invitations/`, `claims/`, `account-deletion-blockers/`, audit, outbox, notifications ; aucune valeur sentinelle (téléphone, jeton, étiquette, nom de fichier).
12. Aucun plan ni abonnement n'altère un rôle, une invitation, une revendication ni un claim (test d'absence).
13. Blocages de suppression : seul propriétaire d'une organisation active ou suspendue listé ; disparaît après transfert.

---

## 11. Propositions pour `docs/suivi/BACKLOG.md` (non appliquées)

| ID | Tâche | Agents | Statut | Réf. |
|---|---|---|---|---|
| L1-01-A | ADR : invitation, revendication, secours, attribution par le personnel | architecte-technique | À faire | §3.1, IAM-005/006 |
| L1-01-B1 | Endpoints d'équipe : liste, rôle, retrait, transfert | dev-backend | À faire | §3.1, IAM-006 |
| L1-01-B2 | Invitations avec acceptation de la cible | dev-backend, auditeur-securite | À faire | §3.1, IAM-005 |
| L1-01-B3 | Revendication et secours d'une organisation sans propriétaire | dev-backend, auditeur-securite | À faire | §3.1, IAM-005, UF-04 |
| L1-01-B4 | Préalables d'équipe à la suppression de compte | dev-backend | À faire | ADR 0006 §17.5.1 |
| L1-01-B5 | Noms réservés et signalement d'usurpation | dev-backend | À faire | ADR 0006 §17.5.3 |
| L1-01-D | Spécifications d'écran équipe, invitation, revendication | designer-ux | À faire | §3.1 |
| L1-01-F1 à F3 | Front : équipe, invitation, revendication | dev-frontend | À faire | §3.1 |
| L1-01-S / Q | Revue sécurité ; recette | auditeur-securite, qa-testeur | À faire | §3.1 |

La ligne L1-01 existante devient une ligne « parent » ; elle ne se clôt que quand les lignes précédentes sont `Fait`.

---

## 12. Propositions de mise à jour du CDC (diff texte, à n'appliquer que sur accord)

**§3.1 — Organisations (après « Une revendication d'organisation existante ne donne aucun droit avant validation. »)**
- Ancien : `Une revendication d'organisation existante ne donne aucun droit avant validation.`
- Nouveau (si les hypothèses H1, H4, H8 sont validées) : `Une personne rejoint une organisation sur invitation d'un propriétaire ou d'un administrateur ; l'invitation ne donne aucun droit tant que la personne ne l'a pas acceptée, expire et peut être annulée ; elle ne confère jamais le rôle de propriétaire. Une revendication d'organisation existante ne donne aucun droit avant validation par le personnel de vérification ; elle ne remplace jamais un propriétaire existant ; elle ne crée aucun badge de vérification. Une organisation sans propriétaire actif peut se voir attribuer un propriétaire sur preuve d'autorité, avec trace d'audit.`

**§11.1 — ligne `identity`** : ajouter `OrganizationInvitation, OrganizationClaim` (si l'ADR retient ces noms).

**§11.2 — tableau des événements** : ajouter `OrganizationInvitationChanged | identity | notifications` et `OrganizationClaimChanged | identity | notifications`.

---

## 13. Points ouverts et risques

1. **C1 et C2 sont à trancher avant planification** (mécanisme d'invitation ; pouvoir d'attribution du personnel). Ils modifient deux décisions de l'ADR 0006.
2. **Revendication sans définition de « fiche existante »** (C6, Q-L1-6) : risque de construire un parcours qui ne sert à rien en V1 si le client n'importe aucune fiche. L1-01j (secours) reste utile dans tous les cas.
3. **Surface d'attaque nouvelle** : jetons d'invitation (devinette, rejeu), preuves de revendication (fichiers), pouvoir du personnel de créer des propriétaires (collusion). Revue sécurité obligatoire, quatre yeux, conflit d'intérêts, audit.
4. **Dépendance à `phone_verified` seul** : aucun mécanisme n'établit l'autorité d'une personne sur une organisation sauf les preuves de revendication jugées par le personnel (doc 02 UF-02 : « Un e-mail professionnel ne prouve pas à lui seul l'autorité organisationnelle »).
5. **Valeurs de départ sans source** (durées, plafonds) : marquées « à confirmer » ; aucune ne doit devenir une règle commerciale sans accord.
6. **Concurrence** : verrous sans effet sous SQLite ; recette MySQL au registre (D7) ; l'acceptation concurrente repose sur une mise à jour conditionnelle.
7. **Exposition de « supprimer mon compte »** non décidée (Q-L1-10) ; ne pas la livrer sans réponse du client (LEG-PRV) et sans traiter le TOCTOU (D6).
8. **Prérequis de production** : cache partagé pour les throttles (D9), analyse antivirus des pièces (ClamAV, ADR §18 n°4), limite de taille Nginx.
