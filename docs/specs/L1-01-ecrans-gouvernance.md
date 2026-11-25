# L1-01-D2 : Spécification d'écran, gouvernance des organisations (ADR 0010)

- **Date :** 25/11/2026 ; **auteur :** designer-ux ; **destinataires :** dev-frontend (F1-bis, F2-bis, F4, F5, F6), qa-testeur.
- **Sources :** `docs/adr/0010-gouvernance-organisations.md` (D1 à D10, §6.2, §7 notifications, §12, §18) ; `docs/specs/L1-01-contrat-api.md` §7 (contrat v2 : **les écrans ne montrent que ce qu'il expose**) ; réponses du client Q3, Q17, Q19, Q21, Q22, Q23, Q26, Q30 ; `docs/specs/L1-01-ecrans-equipe.md` (spec D1, amendée ici) ; `docs/specs/L0-09-ecrans-contextes.md` §6 (création).
- **Décisions de l'utilisateur appliquées :** invitation comme Administrateur avec confirmation par l'émetteur (ou un Administrateur principal) avant toute ouverture de droits ; nomination d'un Administrateur principal avec acceptation de la personne promue, notification de tous les Administrateurs principaux, ressaisie du mot de passe, revue Connecte+ pour les organisations à vérification renforcée ; libellé « Administrateur principal » partout ; plus aucun plafond affiché du nombre d'organisations.
- **Aucune dépendance graphique nouvelle.** shadcn/ui, lucide-react et Tailwind déjà installés suffisent.

> **Révision du 26/11/2026 — code de rattachement (QG-2 tranché par la revue S3).** Une invitation Administrateur acceptée renvoie un **code à 6 chiffres** (`confirmation_code`) montré à la seule personne qui a accepté. Elle le communique de vive voix à la personne qui l'a invitée ; le confirmateur l'obtient **en l'appelant au numéro qu'il connaît**, puis saisit le code **et** son mot de passe. 5 codes faux rejettent la demande. La personne peut obtenir un nouveau code (l'ancien cesse de valoir). La liste des invitations porte `inviter_has_authority`. Sections modifiées : 1 (principe 8), 4.4, 4.5, 7.3, 8 (entièrement), 9.1, 9.3, 9.4, 11.2, 11.3 (nouvelle), 11.4, 11.5, 14, 15.1, 15.2, 15.3, 16.2, 17, 18, 19, 20, 21 (Q-D2-2 soldée, Q-D2-10 ajoutée). Contrat : §7.4, §7.4.5 à §7.4.7, §7.7 amendés.

### Ce que ce document remplace dans `L1-01-ecrans-equipe.md`

| Section de D1 | Sort |
|---|---|
| §0 ligne E6c « Transférer la propriété » | **Supprimée** : remplacée par E6f (section 6). `TransferOwnershipDialog` et `useTransferOwnership` sont retirés. |
| §2.5 matrice du menu | **Remplacée** par la section 4.3 |
| §2.6 E6b « Changer le rôle » | **Amendée** par la section 5 (plus d'option Administrateur principal, rôle Membre, rétrogradation d'un autre Administrateur principal) |
| §2.7 E6c | **Supprimée** (section 6) |
| §3.3 E6a étape 1 (rôles, note `rolesNote`) et étape 2 (avertissement), erreur `invitation_limit_reached` | **Amendées** par la section 7 |
| §4.4.2 aperçu, §4.4.3 succès, §4.5 erreurs `organization_limit_reached` | **Amendés** par la section 9 |
| §6 tous les textes contenant « propriétaire » | **Remplacés** par la section 15.1 |
| §10 décision 4 (deux chemins vers un nouveau propriétaire) | **Caduque** : un seul chemin, la nomination |
| §11 question 8 (transfert sur organisation archivée) | **Soldée** : retiré par ADR 0010 (QG-9) |
| L0-09 §6 (E3) : plafond, `organization_limit_reached` | **Amendé** par la section 13 |

Tout le reste de D1 (structure de E6, CopyLinkField, gestion du jeton, accessibilité, réseau faible) **reste en vigueur**.

---

## 0. Écrans

| ID | Écran | Route ou hôte | Fichier | Tâche |
|---|---|---|---|---|
| — | Libellés des rôles, rôle Membre, tableau des rôles | toutes les pages | `i18n/locales/fr.ts`, `pages/OrganizationTeam.tsx` | F1-bis (libellés), F5 (Membre dans les menus) |
| E6 | Équipe (amendée) : section « À traiter », badge « Proposé(e) » | `/organizations/:id/team` | `pages/OrganizationTeam.tsx`, `components/team/*` | F2-bis, F5 |
| E6a | Inviter une personne (amendé) | dialogue de E6 | `components/team/InviteDialog.tsx` | F2-bis |
| E6b | Changer le rôle (amendé) | dialogue de E6 | `components/team/ChangeRoleDialog.tsx` | F5 |
| E6f | Proposer comme administrateur principal (**nouveau**, remplace E6c) | dialogue de E6 | `components/team/NominatePrimaryAdminDialog.tsx` | F5 |
| E6g | Confirmer l'accès d'un administrateur invité, avec code de rattachement (**nouveau**) | dialogue de E6 | `components/team/ConfirmAdminInvitationDialog.tsx` | F2-bis |
| E6h | Rejeter une demande d'accès (**nouveau**) | alerte de E6 | `components/team/RejectAdminInvitationDialog.tsx` | F2-bis |
| E6i | Répondre à une nomination : accepter, refuser (**nouveau**) | alerte de E6 | `components/team/NominationResponseDialog.tsx` | F5 |
| E6j | Annuler une nomination (**nouveau**) | alerte de E6 | `components/team/CancelNominationDialog.tsx` | F5 |
| E15 | Page d'acceptation (amendée) : aperçu enrichi, écran « Demande envoyée » avec le code | `/organization-invitation` | `pages/OrganizationInvitation.tsx` | F2-bis |
| E17 | Section « Demandes en attente de confirmation » (**nouvelle**) : nouveau code, retrait | section de `/profiles` | `components/profiles/AwaitingMembershipsSection.tsx`, `NewConfirmationCodeDialog.tsx`, `WithdrawAwaitingDialog.tsx` | F2-bis |
| E18 | Bannière de gouvernance (**nouvelle**) : « administration à régulariser », « en cours d'examen » ; badges sur les cartes de `/profiles` | `OrganizationPage` (toutes sections), `Profiles.tsx` | `components/organizations/GovernanceBanner.tsx` | F4 (`under_review`), F6 (`MISSING`) |
| E3 | Créer une organisation (amendé) : sans plafond, `account_review_required` | `/organizations/new` | `pages/OrganizationNew.tsx`, `lib/organization-form.ts` | F4 |

Tous les dialogues nouveaux sont chargés à l'ouverture (`React.lazy` + `Suspense fallback={null}`), comme ceux de D1.

---

## 1. Principes communs

1. **Une action principale par écran.** E6 : « Inviter une personne » (inchangé). Les cartes de la section « À traiter » portent chacune une action principale (Confirmer, Accepter la nomination) ; elles sont des cartes autonomes, pas une seconde action de la page.
2. **Le serveur arbitre.** L'interface ne propose que ce que le rôle de l'acteur permet (pour éviter les refus évidents), mais gère chaque code d'erreur du contrat. L'interface ne connaît **ni** le caractère « effectif » d'un Administrateur principal, **ni** le niveau de vérification de l'organisation (`assurance_level` n'est jamais exposé) : ces cas sont découverts par la réponse du serveur.
3. **Aucun droit avant confirmation, aucun rôle avant acceptation.** Les textes le disent explicitement à chaque étape (« Aucun accès n'est ouvert avant… », « Aucun rôle ne change avant… »).
4. **Aucun chiffre de seuil** (nombre d'organisations, nombre de créations, plafond technique) n'apparaît nulle part : ni texte, ni attribut, ni test d'interface qui l'affiche (Q22).
5. **Le mot « propriétaire »** disparaît de toute interface (contrat §7.1). Critère vérifiable : `grep -i "propriétaire" src/i18n/locales/fr.ts` ne renvoie rien (voir 15.1 pour la seule occurrence de sens différent, réécrite aussi).
6. **Une seule région `aria-live="polite"` par page** (E6 : celle qui existe ; `/profiles` : une nouvelle ; E15 : celle qui existe). Les erreurs sont en `role="alert"` dans leur dialogue ou leur carte.
7. **Aucune action différée.** Hors ligne, les boutons sont désactivés avec `common.offlineAction` relié par `aria-describedby` ; rien n'est mis en file.
8. **Le code de rattachement est un secret à usage unique** (révision du 26/11). Il n'est affiché qu'à la personne qui a accepté, dans la réponse qui le contient (202 ou « nouveau code ») ; il n'existe qu'en mémoire du composant qui l'affiche. **Jamais** dans : une région `aria-live`, un `toast`, un `title`, une URL, `localStorage`, `sessionStorage`, une clé ou un cache React Query (mutations avec `gcTime: 0`, résultat remis à zéro au démontage), `console.*`, un message d'erreur, un attribut `data-*`, le presse-papiers (aucun bouton « Copier » : on le dicte, on ne le colle pas dans une messagerie). Côté confirmateur, le code saisi est vidé après tout échec de code et à la fermeture du dialogue. Tests Vitest à sentinelle (valeur `"482913"` cherchée dans le stockage, le cache de requêtes, les régions vivantes et les toasts).

---

## 2. Rôles : libellés et tableau (F1-bis, F5)

### 2.1 Libellés imposés (contrat §7.1)

| Code | Libellé (`role.<code>`) | Description (`role.<code>_desc`) |
|---|---|---|
| `OWNER` | Administrateur principal | Répond de l'organisation sur Connecte+. Gère toute l'équipe, y compris les administrateurs, propose d'autres administrateurs principaux et peut archiver l'organisation. |
| `ADMIN` | Administrateur | Gère le profil, la vérification, l'équipe (sauf les administrateurs principaux), les contacts et les messages. |
| `EDITOR` | Éditeur | Publie et modifie les offres, répond aux avis et voit qui a demandé à être contacté. (inchangé) |
| `ANALYST` | Analyste | Consulte les statistiques et les offres. Ne peut rien modifier. (inchangé) |
| `MEMBER` | Membre | Voit l'espace interne de l'organisation et son équipe. Ne peut rien publier ni modifier, et ne voit pas les statistiques. |

`RoleBadge` : inchangé dans sa forme (icône `ShieldCheck` + texte). Le type `OrganizationRole` (`api/types.ts`) gagne `"MEMBER"`.

### 2.2 Ambiguïté « Membre » (rôle) et « membre » (personne de l'équipe)

Pour que le badge « Membre » ne se confonde pas avec l'appartenance à l'équipe :
- `team.since` devient « Dans l'équipe depuis {{date}} » ; `team.colSince` devient « Dans l'équipe depuis » ;
- l'onglet `team.tabs.members` garde « Membres » (pluriel générique) ;
- le rôle est toujours affiché par `RoleBadge` (badge + icône), jamais en texte courant.

### 2.3 Tableau « Que peut faire chaque rôle ? » (`Collapsible` de E6)

Ordre : `OWNER`, `ADMIN`, `EDITOR`, `ANALYST`, `MEMBER` (constante `ROLES` de `OrganizationTeam.tsx`). Contenu : `RoleBadge` + `role.<code>_desc`, ligne de l'acteur marquée « Votre rôle » (existant). Sous la liste, une note fixe : « Le rôle Administrateur principal ne s'obtient jamais par invitation : un administrateur principal propose la personne, qui doit accepter. » (`team.rolesOwnerNote`).

### 2.4 Périmètre

Objet `Scope` du contrat : V1 ne produit que `{"type": "ORGANIZATION", "id": null}`.
- Fonction pure `scopeLabel(scope, t)` dans `lib/team.ts` : `ORGANIZATION` → « Toute l'organisation » (`scope.ORGANIZATION`) ; toute autre valeur → « Périmètre limité » (`scope.limited`) (inatteignable en V1, aucune donnée inventée).
- Le périmètre est **affiché** (aperçu d'invitation, carte à confirmer, dialogue d'invitation) mais **n'est jamais choisi** en V1 : aucun contrôle de saisie, le champ `scope` n'est pas envoyé (défaut serveur). Pas de liste déroulante à une seule valeur.
- Il n'est **pas** affiché sur chaque ligne de membre (valeur unique en V1 : bruit visuel). Il l'est dans le dialogue « Changer le rôle » sous le titre : « Périmètre : Toute l'organisation » (`team.scopeLine`).

---

## 3. E18 : bannière de gouvernance (F4, F6)

### 3.1 Objectif

Informer les membres de deux états de l'organisation, sans les mélanger avec la suspension ou l'archivage (états indépendants, règle 8) :
- `governance.primary_admin_state === "MISSING"` : plus aucun Administrateur principal actif (Q17) ;
- `governance.under_review === true` : création retenue en revue par l'équipe Connecte+ (D8).

### 3.2 Emplacement

- **`OrganizationPage`** rend `GovernanceBanner` **entre** le chargement réussi et `OrganizationTabs`, donc sur toutes les sections (Aperçu, Profil, Vérification, Équipe), pour tous les rôles (le champ est servi à tous les membres).
- **`Profiles.tsx`**, carte d'organisation : sous `SellerTypeBadge` et `RoleBadge`, un `Badge variant="outline"` par état actif (voir 3.4). Source : `contexts/` (`results[].governance`). Les éléments `unavailable` n'ont pas cette clé : rien n'est affiché pour eux.

### 3.3 Contenu de la bannière

Composant `Alert` (pas de bouton de fermeture : l'état persiste tant que le serveur le renvoie). Si les deux états sont vrais, deux `Alert` empilées, `MISSING` en premier.

| État | Icône (lucide) | Variante | Titre | Texte |
|---|---|---|---|---|
| `MISSING` | `ShieldAlert` | `Alert` avec bordure `border-warning/50` (pas `destructive` : ce n'est ni une sanction ni une erreur) | « Administration à régulariser » (`governance.missing.title`) | « Cette organisation n'a plus d'administrateur principal actif. Son administration doit être régularisée par l'équipe Connecte+. Elle n'apparaît plus publiquement en attendant. Aucun membre n'est promu automatiquement. » (`governance.missing.body`) |
| `under_review` | `Clock` | `Alert` par défaut | « Organisation en cours d'examen » (`governance.review.title`) | « Votre organisation est en cours d'examen par l'équipe Connecte+. Elle n'apparaît pas encore publiquement. Vous pouvez déjà la compléter. » (`governance.review.body`) |

Lien d'aide (Q19 : pas de « contactez le support » sans lien fonctionnel) : sous le texte de `MISSING`, un lien « Comment régulariser l'administration » (`governance.missing.help`) **seulement si** une route d'aide est configurée (constante `HELP_LINKS.governance` dans `lib/help.ts`, `undefined` tant que L1-21 n'est pas livrée). Sans route, aucun lien et aucune phrase « contactez ». Voir question Q-D2-1.

Le texte de `MISSING` ne dit jamais pourquoi (désactivation, sanction, fermeture de compte) et ne désigne personne.

### 3.4 Badges sur `/profiles`

| État | Badge (icône + texte) | Clé |
|---|---|---|
| `MISSING` | `ShieldAlert` « Administration à régulariser » | `governance.missing.badge` |
| `under_review` | `Clock` « En cours d'examen » | `governance.review.badge` |

### 3.5 Accessibilité

`Alert` a `role="status"` implicite de shadcn : **le retirer** (rendre un `div` sans rôle vivant) pour ne pas créer une seconde région vivante à chaque navigation entre sections ; le titre est un `h2` visuellement compact (`text-base`). Icône `aria-hidden`. Contraste : texte `text-foreground`, jamais la couleur seule (titre explicite).

### 3.6 Après création (OrganizationHome)

Si `justCreated` et `under_review` : l'alerte « Votre organisation est créée » s'affiche telle quelle **et** la bannière `under_review` au-dessus (rendue par `OrganizationPage`). `org.home.createdBody` devient : « Vous en êtes l'administrateur principal. La prochaine étape recommandée est d'envoyer les pièces de vérification. »

### 3.7 Données

| Donnée | Champ API |
|---|---|
| État d'administration | `OrganizationInternal.governance.primary_admin_state` ; `contexts/ results[].governance.primary_admin_state` |
| Revue de création | `governance.under_review` (mêmes sources) |

Si `governance` est absent (serveur antérieur à B8) : aucune bannière. Le type TypeScript : `governance?: { primary_admin_state: "OK" | "MISSING"; under_review: boolean }`.

---

## 4. E6 : Équipe, amendements (F2-bis, F5)

### 4.1 Objectif et utilisateur

Inchangé (D1 §2.1). S'ajoute : traiter les demandes qui attendent une action de l'utilisateur (confirmer un administrateur invité, répondre à une nomination qui le vise, suivre ou annuler les nominations en cours).

### 4.2 Structure (mobile, de haut en bas)

1. `GovernanceBanner` (rendu par `OrganizationPage`, section 3).
2. Sous-menu de l'organisation (existant).
3. `PageHeader` « Équipe » + bouton « Inviter une personne » (inchangé).
4. Région `aria-live` unique (existante).
5. **Section « À traiter »** (`TeamPendingActions`, nouvelle, 4.4) : rendue **seulement si** elle contient au moins une carte. `h2` « À traiter » (`team.pending.title`) avec `tabIndex={-1}` (cible de focus après une action qui fait disparaître une carte).
6. `Tabs` Membres / Invitations (inchangés). L'onglet Invitations reste sur `status=PENDING`.
7. Cartes « Votre rôle » et « Quitter l'organisation » (existantes).
8. `Collapsible` « Que peut faire chaque rôle ? » (2.3).

**Desktop (>= 768 px) :** même ordre, colonne `max-w-4xl`. La section « À traiter » est une liste de cartes en une colonne (pas de `Table` : chaque carte a deux boutons et un texte d'aide).

### 4.3 Menu d'actions par ligne (`MemberActionsMenu`, remplace D1 §2.5)

`lib/team.ts` : `memberActions(actor, target, openNominationTargets)`.

| Acteur \ cible | OWNER | ADMIN | EDITOR | ANALYST | MEMBER | Soi-même |
|---|---|---|---|---|---|---|
| **OWNER** | Changer le rôle | Changer le rôle ; Proposer comme administrateur principal ; Retirer | idem ADMIN | idem | idem | aucun menu |
| **ADMIN** | aucun menu ; texte « Réservé aux administrateurs principaux » | Changer le rôle ; Retirer | idem | idem | idem | aucun menu |
| **EDITOR, ANALYST, MEMBER** | aucun menu | aucun | aucun | aucun | aucun | aucun menu |

- « Proposer comme administrateur principal » (icône `Crown`, `team.nominate`) est **masqué** si une nomination ouverte vise déjà ce membre (`openNominationTargets` contient `membership_id`, lu dans la liste des nominations, 4.6) ; la ligne affiche alors le badge « Proposé(e) administrateur principal » (`team.nominatedBadge`, icône `Crown` + texte).
- « Retirer » : jamais sur un `OWNER` (inchangé, `owner_must_be_demoted`). Texte sous le badge : « Pour retirer cet administrateur principal, changez d'abord son rôle. » (`team.ownerRemoveHint`).
- L'entrée « Transférer la propriété » et l'icône `ArrowRightLeft` disparaissent.
- Badge `team.lastOwner` : « Seul administrateur principal actif » (règle d'affichage inchangée : `is_last_effective_owner === true`).

### 4.4 Section « À traiter » (`TeamPendingActions`)

Ordre des cartes (de la plus personnelle à la plus générale) :

1. **Nominations qui me visent** : `nominations` ouvertes avec `is_target_me === true` → `NominationCard variant="target"` (4.6.2). Tous les rôles.
2. **Demandes d'accès à confirmer** : invitations `AWAITING_CONFIRMATION` → `AwaitingInvitationCard` (4.5). Seulement si `org.manage_members`. Celles avec `can_confirm === true` d'abord, puis les autres ; à égalité, `confirmation_expires_at` croissante (la plus urgente en haut ; tri côté client sur la page chargée).
3. **Nominations en cours** (les autres) : `NominationCard variant="manager"` (4.6.3). Seulement `my_role` `OWNER` ou `ADMIN` (le serveur ne renvoie les autres qu'à ces rôles).

Chaque groupe a un `h3` : « Une nomination vous concerne » (`team.pending.forMe`), « Demandes d'accès à confirmer » (`team.pending.toConfirm`), « Nominations en cours » (`team.pending.nominations`). Un groupe vide n'est pas rendu.

Une demande peut disparaître sans action de l'utilisateur : rejet automatique après 5 codes faux, ou parce que l'émetteur a été retiré, sanctionné ou désactivé (contrat §7.4). Aucun message n'est affiché pour ces disparitions : la liste est simplement à jour au rechargement.

**Requêtes (au chargement de E6, en parallèle de `members/`) :**
- `GET organizations/<id>/primary-admin-nominations/?status=open` (tous les rôles) ;
- `GET organizations/<id>/invitations/?status=AWAITING_CONFIRMATION` (seulement si `org.manage_members`).

Justification : ce sont des actions attendues, signalées par notification avec le lien `/organizations/<id>/team` ; elles doivent être visibles sans ouvrir d'onglet. Pagination : « Voir plus » sous le groupe si `next` (20 par page), comme les invitations.

**États de la section :**

| État | Rendu |
|---|---|
| Chargement | Aucun squelette (la section n'existe pas encore) : on n'annonce pas une section peut-être vide. La liste des membres a son propre squelette. |
| Vide | Section absente. |
| Erreur d'une des deux requêtes | Une ligne compacte dans la section : « Impossible de vérifier les demandes en attente. » + bouton « Réessayer » (`team.pending.loadError`, `common.retry`), `min-h-11`. La liste des membres reste affichée. |
| Hors ligne | Cartes déjà chargées conservées ; tous leurs boutons désactivés avec `common.offlineAction`. |

### 4.5 Carte « Demande d'accès à confirmer » (`AwaitingInvitationCard`)

**Cas `can_confirm === true`** (émetteur habilité ou Administrateur principal effectif) :

```
┌──────────────────────────────────────────────────┐
│ [RoleBadge Administrateur]  Toute l'organisation  │
│ Marie K. a accepté l'invitation                   │  h4
│ Téléphone se terminant par ••47                   │
│ Acceptée le 25 nov. 2026 à 14 h 05                │
│ À confirmer avant le 28 nov. 2026 à 14 h 05       │
│ Invitation créée par vous                         │
│ ⚠ (si inviter_has_authority = false) La personne │
│   qui a créé l'invitation ne peut plus donner ce  │
│   rôle…                                           │
│ ⓘ Pour confirmer, appelez la personne au numéro  │
│   que vous connaissez et demandez-lui le code à   │
│   6 chiffres affiché sur son écran.               │
│ [ Confirmer l'accès ]   [ Rejeter ]               │
└──────────────────────────────────────────────────┘
```

- Titre : « {{name}} a accepté l'invitation » (`team.awaiting.title`, `name = accepted_by_display_name`).
- Indice : composant `PhoneHint` : texte visible « Téléphone se terminant par ••47 » (`team.awaiting.phoneHint`, `hint = accepted_by_phone_hint` tel que reçu) ; `aria-label` « Téléphone se terminant par 4 7 » (`team.awaiting.phoneHintAria`, chiffres extraits du `hint` et séparés par une espace, pour une lecture chiffre par chiffre ; les puces ne sont pas lues). L'indice est **un indice**, pas une preuve : la preuve est le code (texte de la carte).
- Dates : `formatDateTime(accepted_at)`, `formatDateTime(confirmation_expires_at)`.
- Créateur : « Invitation créée par vous » si `is_mine`, sinon « Invitation créée par {{name}} » (`created_by_display_name`) (clés existantes `team.invitations.createdByMe` / `createdBy`).
- **Si `inviter_has_authority === false`** : `Alert` d'avertissement compacte (icône `AlertTriangle`, bordure `border-warning/50`), placée avant les boutons : « La personne qui a créé cette invitation ne peut plus donner ce rôle (elle a changé de rôle ou quitté l'équipe). Seul un administrateur principal peut encore confirmer ou rejeter cette demande. Assurez-vous que cette arrivée est toujours souhaitée. » (`team.awaiting.inviterNoAuthority`). Pas de badge de couleur seule.
- Consigne : `team.awaiting.callHint` (icône `Phone`) : « Pour confirmer, appelez la personne au numéro que vous connaissez et demandez-lui le code à 6 chiffres affiché sur son écran. Ne demandez pas le code par message. Si vous ne la reconnaissez pas, rejetez la demande. »
- Boutons : « Confirmer l'accès » (`Button` principal, `min-h-11`, ouvre E6g) ; « Rejeter » (`variant="outline"`, texte destructif + icône `X`, ouvre E6h). Sur mobile : pleine largeur, empilés, Confirmer en premier.
- `aria-label` des boutons : « Confirmer l'accès de {{name}} », « Rejeter la demande de {{name}} ».

**Cas `can_confirm === false`** (administrateur qui n'est pas l'émetteur, ou émetteur qui a perdu l'autorité) : le serveur renvoie `accepted_by_display_name` et `accepted_by_phone_hint` à `null`.
- Titre : « Une personne a accepté une invitation comme Administrateur » (`team.awaiting.titleAnonymous`).
- Lignes : rôle, périmètre, « À confirmer avant le {{date}} », créateur.
- Si `inviter_has_authority === false` : même avertissement que ci-dessus.
- Texte : « Seuls la personne qui a créé l'invitation et les administrateurs principaux peuvent confirmer ou rejeter cette demande. » (`team.awaiting.notYours`).
- Aucun bouton.

**Cas échu** (`status === "EXPIRED"`, renvoyé seulement si la requête est rejouée après échéance) : la carte n'est pas rendue (la liste est filtrée sur `AWAITING_CONFIRMATION` côté client aussi).

### 4.6 Nominations (`NominationCard`)

#### 4.6.1 Libellés communs

| Champ | Texte |
|---|---|
| `kind = PROMOTE` | « Nouvel administrateur principal » (`nomination.kind.PROMOTE`) |
| `kind = TRANSFER` | « Remplacement d'un administrateur principal » (`nomination.kind.TRANSFER`) |
| `status = PENDING_ACCEPTANCE` | Badge « En attente d'acceptation » (`nomination.status.PENDING_ACCEPTANCE`, icône `Hourglass`) |
| `status = PENDING_REVIEW` | Badge « Vérification par Connecte+ » (`nomination.status.PENDING_REVIEW`, icône `Clock`) |
| Échéance | « Échéance : {{date}} » (`nomination.expires`, `formatDateTime(expires_at)`) |
| TRANSFER | « {{initiator}} prendra le rôle {{role}}. » (`nomination.transferNote`, `initiator = initiated_by_display_name`, `role = role.<initiator_new_role>`) |

#### 4.6.2 Variante `target` (la nomination me vise)

**`PENDING_ACCEPTANCE` :**
- `h4` : « Vous êtes proposé(e) comme administrateur principal » (`nomination.target.title`).
- Texte : « {{initiator}} vous propose comme administrateur principal de « {{org}} ». » (`nomination.target.body`).
- Texte des responsabilités : `nomination.target.duties` : « En acceptant, vous répondrez de l'organisation sur Connecte+ : vous pourrez gérer toute l'équipe, y compris les administrateurs, proposer d'autres administrateurs principaux et archiver l'organisation. Tous les administrateurs principaux seront informés de votre réponse. »
- Si `kind = TRANSFER` : `nomination.transferNote`.
- Si `requires_review` : « Après votre acceptation, l'équipe Connecte+ vérifiera la nomination. Votre rôle ne changera qu'après sa décision. » (`nomination.target.reviewNote`).
- Échéance.
- Boutons : « Accepter la nomination » (principal, ouvre E6i en mode accepter) ; « Refuser » (`outline`, ouvre E6i en mode refuser).

**`PENDING_REVIEW` :**
- `h4` : « Votre nomination est en cours de vérification » (`nomination.target.reviewTitle`).
- Texte : « Vous avez accepté. L'équipe Connecte+ vérifie la nomination. Votre rôle actuel ne change pas avant sa décision. » (`nomination.target.reviewBody`) + échéance.
- Aucun bouton.

#### 4.6.3 Variante `manager` (Administrateur principal, administrateur)

- Ligne 1 : badge de genre (`nomination.kind.*`) + badge d'état.
- `h4` : « {{name}} » (`target.display_name`).
- « Proposé(e) par {{name}} » (`nomination.by`). Le contrat n'expose pas « l'appelant est l'initiateur » ; on affiche toujours `initiated_by_display_name` (voir question Q-D2-4).
- TRANSFER : `nomination.transferNote`.
- État `PENDING_ACCEPTANCE` : « En attente de la réponse de {{name}}. » (`nomination.manager.waitingTarget`). État `PENDING_REVIEW` : « {{name}} a accepté. L'équipe Connecte+ vérifie la nomination avant qu'elle prenne effet. » (`nomination.manager.waitingReview`).
- Échéance.
- Bouton « Annuler la nomination » (`outline`, icône `X`, `aria-label` « Annuler la nomination de {{name}} ») **seulement si** `can_cancel === true` → E6j.

Aucune nomination close n'est affichée en V1 (le contrat le permet par `?status=closed` ; non retenu, comme l'historique des invitations ; les issues sont notifiées). Voir Q-D2-5.

### 4.7 Données de E6 (ajouts à D1 §2.10)

| Donnée | Champ API |
|---|---|
| Rôle Membre | `Member.role = "MEMBER"` |
| Périmètre (dialogue de rôle) | `Member.scope` |
| Demandes à confirmer | `Invitation.status = AWAITING_CONFIRMATION`, `role`, `scope`, `accepted_at`, `confirmation_expires_at`, `accepted_by_display_name`, `accepted_by_phone_hint`, `can_confirm`, `inviter_has_authority`, `created_by_display_name`, `is_mine`, `invitation_id` (jamais affiché). Le code de rattachement n'est **jamais** dans cet objet. |
| Nominations | `PrimaryAdminNomination.kind`, `status`, `target.display_name`, `target.membership_id` (jamais affiché ; sert au badge de ligne), `initiated_by_display_name`, `initiator_new_role`, `requires_review`, `expires_at`, `is_target_me`, `can_cancel`, `nomination_id` (jamais affiché) |
| Nom de l'organisation (textes de nomination) | `OrganizationInternal.name` |
| État de gouvernance | `OrganizationInternal.governance` |

---

## 5. E6b : Changer le rôle, amendé (F5)

### 5.1 Rôles proposés (`assignableRoles(actorRole, targetRole)` dans `lib/team.ts`)

| Acteur | Rôles proposés (ordre d'affichage) |
|---|---|
| OWNER | Administrateur, Éditeur, Analyste, Membre |
| ADMIN (cible non OWNER) | Administrateur, Éditeur, Analyste, Membre |

**Administrateur principal n'est jamais proposé.** Sous le `RadioGroup`, texte : « Pour faire de {{name}} un administrateur principal, utilisez « Proposer comme administrateur principal » dans le menu de sa ligne. » (`team.changeRoleNominateHint`), affiché seulement si l'acteur est `OWNER` et la cible n'est pas `OWNER`.

Sous le titre : « Périmètre : Toute l'organisation » (`team.scopeLine`, 2.4).

### 5.2 Étape 2 (confirmation renforcée)

Affichée **seulement** si la cible est actuellement `OWNER` (seul cas où le contrat exige `confirm` + `password`). Corps envoyé : `{role, confirm: true, password}` ; sinon `{role}` seul.

Texte (`team.demoteOwnerBody`) : « {{name}} ne sera plus administrateur principal. Cette personne perdra la gestion des administrateurs, l'archivage de l'organisation et la possibilité de proposer un administrateur principal. Elle et tous les administrateurs principaux en seront informés. »

`SensitiveConfirmFields` : case « Je confirme ce changement », mot de passe (inchangés).

### 5.3 Erreurs ajoutées (en plus de D1 §2.6)

| Réponse | Affichage |
|---|---|
| `409 primary_admin_change_requires_verification` | `FormAlert` dans l'étape 2 : « Dans cette organisation, le changement de rôle d'un administrateur principal doit être traité par l'équipe Connecte+. Aucun changement n'a été fait. » (`errors.code.primary_admin_change_requires_verification`) + lien d'aide si `HELP_LINKS.governance` est défini. Le bouton « Confirmer le changement » est désactivé jusqu'à la fermeture ; mot de passe vidé. |
| `400 use_primary_admin_nomination` | Inatteignable (option absente). `FormAlert` : « Pour nommer un administrateur principal, utilisez « Proposer comme administrateur principal ». » (`errors.code.use_primary_admin_nomination`) |
| `400 {"scope": [...]}` | Inatteignable (`scope` non envoyé). Message du serveur dans `FormAlert`. |
| `409 last_owner` | « Une organisation doit toujours avoir au moins un administrateur principal. » (`errors.code.last_owner_demote`) |
| `409 last_effective_owner` | `errors.code.last_effective_owner` (15.1) |

Succès : inchangé (toast `team.roleChanged`, annonce, focus au bouton `⋯`). Après la rétrogradation d'un Administrateur principal : invalider aussi `nominations` (le serveur peut en avoir invalidé) et les invitations `AWAITING_CONFIRMATION` (`inviter_has_authority` peut avoir changé).

---

## 6. E6f : Proposer comme administrateur principal (F5, remplace E6c)

### 6.1 Objectif et utilisateur

Un Administrateur principal propose un membre de l'équipe comme Administrateur principal, soit **en plus** de lui (`PROMOTE`), soit **à sa place** (`TRANSFER`, il prend un autre rôle). **Action principale :** « Envoyer la proposition ». Aucun rôle ne change à ce stade.

### 6.2 Parcours

1. Ligne d'un membre non `OWNER` → menu `⋯` → « Proposer comme administrateur principal ».
2. Étape 1 : choix du genre (et du rôle de repli si `TRANSFER`), lecture du déroulé.
3. Étape 2 : case de confirmation + mot de passe → `POST primary-admin-nominations/`.
4. Succès (`201`) : fermeture, `toast` « Proposition envoyée à {{name}}. Aucun rôle ne change avant sa réponse. » (`team.nominate.sent`), annonce `aria-live` identique, invalidation de `nominations` ; la carte apparaît dans « À traiter » (groupe « Nominations en cours ») et le badge « Proposé(e) » sur la ligne ; focus sur le `h2` « À traiter ».
5. Sortie anticipée : « Annuler » ferme sans appel ; focus rendu au bouton `⋯`.

### 6.3 Structure (`ResponsiveDialog`, feuille basse sur mobile, `dismissible` par défaut)

Titre : « Proposer {{name}} comme administrateur principal » (`team.nominate.title`).

**Étape 1 :**
1. `RadioGroup` « Que souhaitez-vous faire ? » (`team.nominate.kindLabel`), aucun choix présélectionné :
   - `PROMOTE` : « Ajouter un administrateur principal » — « {{name}} devient administrateur principal. Vous le restez aussi. » (`team.nominate.promote`, `team.nominate.promoteDesc`)
   - `TRANSFER` : « Me remplacer » — « {{name}} devient administrateur principal. Vous prenez le rôle choisi ci-dessous. » (`team.nominate.transfer`, `team.nominate.transferDesc`). **Désactivé** si une nomination `TRANSFER` ouverte existe déjà dans la liste chargée, avec le texte relié par `aria-describedby` : « Un remplacement est déjà en cours dans l'organisation. » (`team.nominate.transferBusy`).
2. Si `TRANSFER` : `RadioGroup` « Votre rôle après le remplacement » (`team.nominate.myRoleLabel`) : Administrateur (présélectionné), Éditeur, Analyste, Membre (`my_new_role`).
3. Encadré « Comment ça se passe » (`ol` numérotée, texte `text-sm`) :
   1. « {{name}} reçoit une notification et doit accepter. » (`team.nominate.step1`)
   2. « Tous les administrateurs principaux sont informés à chaque étape. » (`team.nominate.step2`)
   3. « Pour certaines organisations, l'équipe Connecte+ vérifie aussi la nomination avant qu'elle prenne effet. » (`team.nominate.step3`)
   4. « Sans réponse avant l'échéance, la proposition expire. Vous pouvez l'annuler tant qu'elle n'a pas abouti. » (`team.nominate.step4`)
4. Boutons : « Annuler » et « Continuer » (désactivé sans genre choisi).

**Étape 2 :** (contenu remplacé dans le même dialogue, bouton « Retour »)
1. Récapitulatif : « {{name}} deviendra administrateur principal après son acceptation. » + pour `TRANSFER` : « Vous prendrez alors le rôle {{role}}. » (`team.nominate.summary`, `team.nominate.summaryTransfer`).
2. `SensitiveConfirmFields` : case « Je confirme cette proposition » (`team.nominate.confirm`) ; mot de passe (`team.passwordLabel`, `team.passwordHelp`).
3. Boutons : « Retour » et « Envoyer la proposition » (`team.nominate.submit`, désactivé tant que la case n'est pas cochée et le mot de passe vide ; `Loader2` pendant l'appel).

Corps : `{membership_id, kind, my_new_role: kind === "TRANSFER" ? choix : null, confirm: true, password}`.

Desktop : `Dialog` `max-w-lg`, même contenu.

### 6.4 Erreurs (`FormAlert` `role="alert"` dans le dialogue, choix conservés)

| Réponse | Affichage |
|---|---|
| `403 reauthentication_failed` | Sous le mot de passe : « Mot de passe incorrect. » ; champ vidé, focus dessus |
| `429` | `team.retryLater` (blocage via `use-rate-block` existant, bouton désactivé pendant `Retry-After`) |
| `409 nomination_already_open` | « Une nomination est déjà en cours pour cette personne, ou un remplacement est déjà en cours dans l'organisation. Consultez « À traiter ». » (`errors.code.nomination_already_open`) ; invalidation de `nominations` ; dialogue ouvert, bouton désactivé |
| `400 invalid_nomination` | « Cette personne est déjà administrateur principal. » (`errors.code.invalid_nomination`) ; fermeture et rechargement de `members` |
| `400 user_unavailable` | « Cette proposition n'est pas possible pour ce compte pour le moment. » (`team.nominate.unavailable`, neutre) |
| `404 member_not_found` | Fermeture, `toast` `team.alreadyGone`, rechargement de `members` |
| `403 DENY_PERMISSION` | « Seul un administrateur principal en activité peut proposer une nomination. » (`team.nominate.denied`) ; fermeture ; rechargement de l'organisation (`my_role`) |
| `403 DENY_RELATION`, `DENY_SECURITY`, `DENY_OBJECT_STATE` | Flux existants (perte de profil, `describeApiError`, `OrganizationUnavailableView`) |
| `400 confirmation_required`, `password_required`, `{"kind"}`, `{"my_new_role"}` | Inatteignables ; message générique `errors.generic` |
| Réseau coupé sans réponse | « Connexion perdue. La proposition a peut-être été envoyée : vérifiez « À traiter » avant de réessayer. » (`team.nominate.network`) ; à la reconnexion, invalidation de `nominations` |

---

## 7. E6a : Inviter une personne, amendé (F2-bis)

### 7.1 Rôles proposés (`invitableRoles(actorRole)` dans `lib/team.ts`)

| Acteur | Rôles, dans cet ordre (du moins au plus privilégié) |
|---|---|
| OWNER, ADMIN | Membre, Analyste, Éditeur, Administrateur |
| autres | aucun (bouton Inviter absent, inchangé) |

Aucun rôle présélectionné (inchangé). Chaque option : libellé + `role.<code>_desc`. L'option Administrateur porte en plus un `Badge variant="outline"` « Confirmation requise » (icône `UserCheck`, `team.invite.confirmBadge`) et la phrase : « Après l'acceptation, vous ou un administrateur principal devrez appeler la personne pour obtenir son code de confirmation. Aucun accès n'est ouvert avant. » (`team.invite.adminConfirmNote`).

Le serveur reste l'arbitre de « ce que l'émetteur peut déléguer » : `400 invitation_role_not_allowed` → erreur sous la liste des rôles, `team.invite.errRole` réécrit (15.2), et rechargement de l'organisation (`my_role`).

### 7.2 Autres changements de l'étape 1

- **Supprimer** `team.invite.rolesNote`. **Le remplacer** par : « Le rôle Administrateur principal ne peut pas être donné par invitation. Une fois la personne dans l'équipe, un administrateur principal peut la proposer. » (`team.invite.ownerNote`), `Alert` d'information.
- Ligne fixe sous les rôles : « Périmètre : Toute l'organisation » (`team.scopeLine`). Aucun contrôle.
- Champ `scope` non envoyé.
- `409 invitation_limit_reached` compte désormais les invitations en attente **et** les demandes à confirmer (contrat §7.4.1) : texte `team.invite.errLimit` réécrit (15.1).

### 7.3 Étape 2 (lien)

Si le rôle est `ADMIN` (`requires_confirmation === true` dans la réponse `201`), l'avertissement `team.invite.linkWarning` est remplacé par `team.invite.linkWarningAdmin` : « Ce lien ne sera plus affichable après la fermeture de cette fenêtre. Envoyez-le seulement à la personne concernée. Quiconque l'ouvre pourra demander à rejoindre l'équipe comme Administrateur, mais n'aura aucun accès avant que vous ou un administrateur principal confirmiez son identité : il faudra appeler la personne au numéro que vous connaissez et lui demander le code à 6 chiffres qu'elle aura reçu. »

Le reste (CopyLinkField, Partager, non-fuite du jeton) est inchangé.

### 7.4 Données

| Donnée | Source |
|---|---|
| Rôles proposés | `OrganizationInternal.my_role` (côté client) ; arbitrage serveur |
| Confirmation requise | réponse `201` `requires_confirmation` |
| Périmètre affiché | constante `ORGANIZATION` (V1) ; réponse `201` `scope` |

---

## 8. E6g, E6h : confirmer ou rejeter une demande d'accès (F2-bis)

### 8.1 Objectif et utilisateur

L'émetteur d'une invitation Administrateur, ou un Administrateur principal, vérifie que la personne qui a accepté le lien est bien celle qu'il voulait inviter, puis lui ouvre l'accès ou le lui refuse. **La preuve est le code de rattachement** : le confirmateur appelle la personne qu'il voulait inviter, au numéro qu'il connaît déjà, et lui demande le code affiché sur son écran. Si le lien a été transmis à un tiers, la personne appelée n'a pas de code. Le nom abrégé et l'indice de téléphone ne sont que des indices. **Action principale :** « Confirmer l'accès ».

### 8.2 Parcours

1. Entrée : notification « Une invitation comme Administrateur pour « {organisation} » a été acceptée… » (lien `/organizations/<id>/team`) ou visite de E6 ; carte dans « À traiter ».
2. Le confirmateur appelle la personne (hors application) et note le code qu'elle lui dicte.
3. « Confirmer l'accès » → E6g → code + case + mot de passe → `POST invitations/<id>/confirm/` → `200 Member`.
4. Code faux : erreur sous le champ, nouvel essai possible ; au 5e code faux (tous confirmateurs confondus), la demande est rejetée automatiquement.
5. Ou « Rejeter » → E6h → `POST invitations/<id>/reject/` → `204`.
6. Sortie : la carte disparaît ; pour une confirmation, la personne apparaît dans la liste des membres.

### 8.3 E6g : `ConfirmAdminInvitationDialog` (`ResponsiveDialog`)

Titre : « Confirmer l'accès de {{name}} » (`team.confirmInvite.title`).

1. Si `inviter_has_authority === false` : `Alert` d'avertissement `team.awaiting.inviterNoAuthority` en tête du dialogue.
2. Consigne (`Alert` d'information, icône `Phone`), titre « Appelez d'abord la personne » (`team.confirmInvite.callTitle`), texte : « Appelez {{name}} au numéro que vous connaissez déjà, pas à un numéro reçu avec la demande, et demandez-lui le code à 6 chiffres affiché sur son écran. Ne demandez pas le code par message. Si la personne que vous appelez n'a pas de code, rejetez la demande. » (`team.confirmInvite.callBody`).
3. Récapitulatif (`dl`) : « Personne » `{{name}}` ; « Téléphone » `PhoneHint` + texte `text-xs` « Vérifiez que ces chiffres correspondent au numéro que vous appelez. » (`team.confirmInvite.phoneCheck`) ; « Rôle » `RoleBadge ADMIN` ; « Périmètre » `scopeLabel`.
4. Texte : « En confirmant, {{name}} devient Administrateur de « {{org}} » immédiatement : cette personne pourra gérer le profil, la vérification, l'équipe (sauf les administrateurs principaux), les contacts et les messages. Les administrateurs principaux en sont informés. » (`team.confirmInvite.body`).
5. **Champ « Code à 6 chiffres »** (`team.confirmInvite.codeLabel`), composant `Field` + `Input` :
   - `inputMode="numeric"`, `autoComplete="off"` (**pas** `one-time-code` : Android proposerait un code SMS reçu par le confirmateur lui-même), `spellCheck={false}`, `maxLength={7}` (6 chiffres et une espace éventuelle), classes `font-mono text-lg tracking-widest`, largeur fixe `w-40` sur desktop, pleine largeur sur mobile ;
   - normalisation à la saisie et au collage : suppression de tout caractère non numérique, puis 6 chiffres au plus ; valeur envoyée = les 6 chiffres ;
   - aide (`aria-describedby`) : « Le code que la personne lit sur son écran, par exemple 482 913. » (`team.confirmInvite.codeHelp`) ;
   - validation locale : moins de 6 chiffres à l'envoi → « Saisissez les 6 chiffres du code. » (`team.confirmInvite.codeIncomplete`) ; aucun appel.
6. `SensitiveConfirmFields` : case « J'ai obtenu ce code en appelant {{name}}, et c'est bien la personne que j'ai voulu inviter » (`team.confirmInvite.check`) ; mot de passe.
7. Boutons : « Annuler » et « Confirmer l'accès » (`team.confirmInvite.submit`, désactivé tant que le code n'a pas 6 chiffres, la case n'est pas cochée ou le mot de passe est vide ; `Loader2` pendant l'appel).

Ordre de tabulation : avertissement éventuel (non focalisable), consigne, champ code, case, mot de passe, boutons. **Focus initial : le champ code.**

Corps : `{confirm: true, password, code}`.

**Succès (`200 Member`) :** fermeture ; code et mot de passe effacés de l'état ; `toast` « {{name}} a rejoint l'équipe comme Administrateur. » (`team.confirmInvite.done`) ; même texte dans `aria-live` ; invalidation de `invitations` (AWAITING) et `members` ; focus sur le `h2` « À traiter » s'il reste des cartes, sinon sur le titre de la liste des membres.

**Erreurs** (dans l'ordre de contrôle du serveur, contrat §7.4.6) :

| Réponse | Affichage |
|---|---|
| `403 DENY_RELATION`, `DENY_SECURITY`, `DENY_OBJECT_STATE` | Flux existants |
| `404 invitation_not_found`, `409 invitation_not_awaiting_confirmation` | Fermeture ; `toast.info` « Cette demande n'est plus en attente : elle a été traitée, retirée, rejetée ou a expiré. » (`team.awaiting.gone`) ; invalidation |
| `403 DENY_PERMISSION` | Fermeture ; `toast` « Vous ne pouvez plus confirmer cette demande. Un administrateur principal peut le faire. » (`team.confirmInvite.denied`) ; invalidation de l'organisation et de `invitations` |
| `400 confirmation_code_required` | Inatteignable (bouton désactivé) ; sous le champ code : `team.confirmInvite.codeIncomplete` ; focus sur le champ |
| `400 confirmation_required`, `password_required` | Inatteignables ; `errors.generic` |
| `403 reauthentication_failed` | Sous le mot de passe : « Mot de passe incorrect. Aucun essai de code n'a été compté. » (`team.confirmInvite.badPassword`) ; mot de passe vidé, **code conservé**, focus sur le mot de passe |
| `400 confirmation_code_invalid` | Sous le champ code : « Ce code est incorrect. Vérifiez-le avec {{name}} au téléphone. Après plusieurs codes incorrects, la demande est rejetée automatiquement. » (`team.confirmInvite.codeInvalid`) ; **code vidé**, mot de passe conservé (il était correct), focus sur le champ code. Aucun nombre d'essais restants (non exposé). |
| `409 confirmation_code_exhausted` | Fermeture ; code et mot de passe effacés ; `toast.error` durée 10 s : « Trop de codes incorrects : la demande a été rejetée automatiquement. Si cette personne doit rejoindre l'équipe, créez une nouvelle invitation. » (`team.confirmInvite.exhausted`) ; même texte dans `aria-live` ; invalidation ; focus sur le `h2` « À traiter » ou le titre de la liste des membres |
| `400 user_unavailable` | `FormAlert` : « Cette personne ne peut pas rejoindre l'organisation pour le moment. La demande reste en attente jusqu'à son échéance ; vous pouvez aussi la rejeter. » (`team.confirmInvite.unavailable`) ; code et mot de passe vidés ; dialogue ouvert |
| `409 already_member` | Fermeture ; `toast.info` « Cette personne fait déjà partie de l'équipe. » (`team.confirmInvite.alreadyMember`) ; invalidation `invitations` et `members` |
| `429` | `team.retryLater`, bouton bloqué pendant `Retry-After` |
| Autre 4xx avec `code` non prévu (dont un éventuel refus d'entitlement d'équipe, ADR 0009 `CAP-TEAM-MEMBER`, voir Q-D2-6) | `FormAlert` avec `describeApiError` ; dialogue ouvert |
| Réseau coupé sans réponse | « Connexion perdue. L'accès a peut-être été confirmé : vérifiez la liste avant de réessayer. » (`team.confirmInvite.network`) ; code conservé ; invalidation à la reconnexion |

Les essais de code sont comptés **par invitation**, tous confirmateurs confondus : le texte `codeInvalid` ne promet donc aucun nombre d'essais.

### 8.4 E6h : `RejectAdminInvitationDialog` (`AlertDialog`)

- Titre : « Rejeter la demande de {{name}} ? » (`team.rejectInvite.title`) ; si le nom est nul (impossible par contrat pour `can_confirm`), « Rejeter cette demande ? » (`team.rejectInvite.titleAnonymous`).
- Texte : « Cette personne n'aura aucun accès à l'organisation et le lien ne pourra plus être utilisé. Elle sera prévenue, sans voir votre nom. » (`team.rejectInvite.body`).
- Si `inviter_has_authority === false` : phrase ajoutée sous le texte : « La personne qui a créé cette invitation ne peut plus donner ce rôle. » (`team.rejectInvite.inviterNoAuthority`).
- Consigne d'usage (`text-sm`) : « Rejetez si la personne que vous avez appelée n'a pas de code, ou si vous ne savez pas qui a accepté. » (`team.rejectInvite.when`).
- Boutons : « Garder la demande » (focus initial, `team.rejectInvite.keep`) ; « Rejeter » (destructif, `team.rejectInvite.submit`).
- Pas de mot de passe ni de code (contrat).
- Succès (`204`) : `toast` « Demande rejetée. » (`team.rejectInvite.done`), annonce, invalidation, focus comme 8.3.
- Erreurs : `409 invitation_not_awaiting_confirmation`, `404 invitation_not_found` → `team.awaiting.gone` ; `403 DENY_PERMISSION` → `team.confirmInvite.denied` ; `429`, réseau : comme 8.3 (texte réseau : `team.networkLost`).

---

## 9. E15 : page d'acceptation, amendée (F2-bis)

### 9.1 Aperçu enrichi (remplace D1 §4.4.2 points 3 à 5)

Liste de définition (`dl`, une ligne par entrée) :
1. « Organisation » : bloc identité existant (initiales, nom, `SellerTypeBadge`).
2. « Invitation de » : `invited_by_display_name`.
3. « Rôle proposé » : `RoleBadge` + `role.<role>_desc`.
4. « Périmètre » : `scopeLabel(preview.scope)` (`invitation.preview.scope`).
5. « Valable jusqu'au » : `formatLongDate(expires_at)`.
6. « Accès » (`invitation.preview.access`) : composant `RoleAccessList` (9.2).

Si `role === "ADMIN"` : sous la liste, une phrase : « Ce rôle ne permet ni de nommer un administrateur principal, ni d'archiver l'organisation. » (`invitation.preview.adminLimits`).

Si `requires_confirmation === true` : **avant** les boutons, `Alert` d'information (icône `UserCheck`), titre « Confirmation nécessaire » (`invitation.preview.confirmTitle`), texte exact du contrat §7.4.4 : « Pour ce rôle, la personne qui vous a invité(e) devra confirmer votre identité. Elle verra votre nom abrégé et les deux derniers chiffres de votre numéro de téléphone. Aucun accès ne vous sera ouvert avant cette confirmation. » (`invitation.preview.confirmBody`), suivi de : « Après avoir accepté, vous recevrez un code à 6 chiffres. Vous le donnerez de vive voix à cette personne quand elle vous appellera. » (`invitation.preview.codeNote`). Le bouton principal devient « Accepter l'invitation » (`invitation.acceptPending`) au lieu de « Rejoindre l'organisation » (on ne rejoint pas encore). `aria-describedby` du bouton → l'`Alert`.

Texte de bas de carte (`invitation.preview.body`) inchangé pour les rôles sans confirmation ; avec confirmation : « Votre profil personnel et vos offres personnelles ne changent pas. Après confirmation, vous pourrez quitter l'organisation à tout moment. » (`invitation.preview.bodyPending`).

### 9.2 `RoleAccessList` (nouveau) : traduction des capacités

Entrée : `preview.capabilities` (codes triés). Fonction pure `groupCapabilities(codes)` dans `lib/role-access.ts`, table fixe :

| Thème (`access.group.*`) | Code → libellé (`access.cap.*`) |
|---|---|
| Organisation (`organization`) | `org.view_internal` → « Voir l'espace interne de l'organisation » ; `org.edit_profile` → « Modifier le profil de l'organisation » ; `org.verification_submit` → « Envoyer les pièces de vérification » ; `org.archive` → « Archiver l'organisation » ; `org.leave` → « Quitter l'organisation » |
| Équipe (`team`) | `org.manage_members` → « Inviter et retirer des membres » ; `org.manage_roles` → « Changer les rôles » |
| Offres (`offers`) | `offer.view_internal` → « Voir les offres, y compris les brouillons » ; `offer.publish` → « Publier des offres » ; `offer.edit` → « Modifier les offres » ; `offer.delete` → « Supprimer des offres » |
| Avis (`reviews`) | `review.reply` → « Répondre aux avis » |
| Contact (`contact`) | `contact.view_requesters` → « Voir qui a demandé à contacter l'organisation » ; `contact.manage_channels` → « Gérer les moyens de contact » |
| Messages (`messages`) | `message.reply` → « Répondre aux messages » |
| Statistiques (`stats`) | `stats.view` → « Consulter les statistiques » |
| Facturation (`billing`) | `billing.view` → « Voir les achats de visibilité de l'organisation » ; `billing.purchase` → « Acheter de la visibilité pour l'organisation » |

Rendu : un `ul` par thème non vide, précédé d'un `h3` `text-sm font-semibold` ; items `text-sm`, puce `Check` `aria-hidden`. Ordre des thèmes : celui du tableau. Codes inconnus : non traduits, regroupés en une ligne finale « et {{count}} autre(s) accès » (`access.others_one` / `_other`) pour ne jamais masquer un accès. Le libellé `billing.purchase` ne dit pas « plan » ni « abonnement » au sens d'une permission : c'est un accès, pas un droit commercial (règle 2).

Sur mobile, la liste est dans un `Collapsible` ouvert par défaut si `capabilities.length <= 6`, fermé sinon, déclencheur « Voir les {{count}} accès » (`invitation.preview.accessToggle`, `min-h-11`, `aria-expanded`). Desktop : toujours ouverte.

La table `CAPABILITY_LABELS` existante (`lib/organization-form.ts`, liste « Ce que vous pouvez faire ») peut être réécrite sur `groupCapabilities` (une seule source de libellés) ; non obligatoire pour F2-bis.

### 9.3 Parcours après « Accepter »

- `200` avec `status: "ACTIVE"` : inchangé (D1 §4.4.3).
- **`202` avec `status: "AWAITING_CONFIRMATION"`** : écran 9.4. Jeton supprimé de `sessionStorage` (l'invitation n'est plus `PENDING`). **Aucune** bascule de profil, **aucune** invalidation obligatoire de `contexts` (l'organisation n'y apparaît pas) ; invalider la clé `["my-awaiting-invitations"]` (E17). La mutation d'acceptation s'exécute avec `gcTime: 0` ; `confirmation_code` est copié dans l'état local de l'écran 9.4 puis la mutation est remise à zéro (`mutation.reset()`), pour que le code ne reste dans aucun cache.

### 9.4 Écran « Demande envoyée » (même carte `max-w-md`)

1. Icône `Hourglass` (décorative). `h1` « Demande envoyée à « {{name}} » » (`invitation.awaiting.title`, `name = organization_name` de la réponse 202), focus sur le `h1`.
2. Texte : « Vous avez accepté le rôle {{role}}. La personne qui vous a invité(e) ou un administrateur principal doit maintenant confirmer votre identité. » (`invitation.awaiting.body`).
3. **Bloc du code** (`section aria-labelledby`), bordure `rounded-2xl border-2 border-primary/40 p-4`, centré :
   - `h2` « Votre code de confirmation » (`invitation.awaiting.codeTitle`) ;
   - le code en grand : `font-mono text-4xl font-bold tracking-[0.3em]`, affiché en deux groupes de 3 (« 482 913 ») dans un `span aria-hidden="true"`, doublé d'un `span className="sr-only"` qui contient les chiffres séparés par des espaces (« 4 8 2 9 1 3 ») pour une lecture chiffre par chiffre ; `select-all` désactivé (`select-none`), **aucun bouton Copier ni Partager** ;
   - consigne (`text-sm`, sous le code) : « Donnez ce code **de vive voix** à la personne qui vous a invité(e), quand elle vous appelle ou en personne. Elle en a besoin pour vous ouvrir l'accès. Ne le communiquez à personne d'autre et ne l'envoyez pas par message, même si on vous le demande. » (`invitation.awaiting.codeInstruction`) ;
   - avertissement (`text-xs text-muted-foreground`) : « Ce code ne sera plus affiché quand vous quitterez cette page. Si vous l'oubliez, obtenez-en un nouveau depuis « Mes profils » : l'ancien ne fonctionnera plus. » (`invitation.awaiting.codeOnce`).
4. Ligne : « Confirmation attendue avant le {{date}}. » (`invitation.awaiting.deadline`, `formatDateTime(confirmation_expires_at)`).
5. `Alert` d'information : « Vous n'avez encore aucun accès à l'organisation. Vous serez prévenu(e) par une notification. Sans confirmation avant cette date, la demande expire et il faudra une nouvelle invitation. » (`invitation.awaiting.noAccess`).
6. Bouton principal « Voir mes profils » → `/profiles` (où se trouve E17) (`invitation.err.profiles`, existant).
7. Bouton secondaire `variant="ghost"` « Retirer ma demande » (`invitation.awaiting.withdraw`) → `WithdrawAwaitingDialog` (11.4) avec `invitation_id` de la réponse 202. Succès : écran « Demande retirée » (`h1` « Demande retirée », texte « Vous ne rejoindrez pas cette organisation. Le lien ne peut plus être utilisé. », lien « Retour à l'accueil ») ; le code est effacé de l'état.
8. Annonce `aria-live` : « Demande envoyée. Votre code de confirmation est affiché à l'écran. » (`invitation.awaiting.announce`). **Le code n'est jamais dans cette annonce.**

Le code est effacé de l'état au démontage de la page. Un rechargement de la page affiche « Lien incomplet » (le jeton a été supprimé) : la personne retrouve sa demande dans E17 et peut y obtenir un nouveau code.

### 9.5 Erreurs modifiées ou ajoutées (remplace les lignes correspondantes de D1 §4.5)

| Réponse | Titre | Texte | Action | Jeton |
|---|---|---|---|---|
| `409 account_review_required` (remplace `organization_limit_reached`) | « Examen du compte nécessaire » (`invitation.err.review.title`) | « Votre compte doit être examiné par l'équipe Connecte+ avant de rejoindre d'autres organisations. Votre invitation reste valable jusqu'à son échéance. » (`invitation.err.review.body`) | « Voir mes profils » ; lien d'aide si `HELP_LINKS.account` défini | conservé |
| `409 already_awaiting_confirmation` | « Une demande est déjà en attente » (`invitation.err.awaiting.title`) | « Vous avez déjà accepté une invitation comme Administrateur pour cette organisation. Attendez sa confirmation, ou retirez cette demande depuis « Mes profils » pour utiliser ce lien. » (`invitation.err.awaiting.body`) | « Voir mes profils » | conservé |

`lib/invitations.ts` : `kind: "limit"` est renommé `kind: "review"` (code `account_review_required`) ; nouveau `kind: "awaiting"`. Les clés `invitation.err.limit.*` sont **supprimées**.

### 9.6 Données (ajouts à D1 §4.7)

| Donnée | Champ API |
|---|---|
| Périmètre, accès, confirmation requise | `preview.scope`, `preview.capabilities`, `preview.requires_confirmation` |
| Réponse 202 | `status`, `invitation_id` (jamais affiché), `organization_name`, `role`, `confirmation_expires_at`, `confirmation_code` (affiché une fois, 9.4) |
| Réponse 200 | clé `status: "ACTIVE"` ajoutée, ignorée à l'affichage |

---

## 10. E6i, E6j : répondre à une nomination, annuler une nomination (F5)

### 10.1 E6i : `NominationResponseDialog` (`AlertDialog`, deux modes)

**Mode accepter :**
- Titre : « Devenir administrateur principal de « {{org}} » ? » (`nomination.accept.title`).
- Texte : `nomination.target.duties` (4.6.2) ; si `TRANSFER` : `nomination.transferNote` ; si `requires_review` : `nomination.target.reviewNote`.
- Boutons : « Pas maintenant » (focus initial, `nomination.accept.later`, ferme sans appel) ; « Accepter » (`nomination.accept.submit`).
- Corps : `{confirm: true}`. Pas de mot de passe (contrat).
- Succès `200` :
  - `status = COMPLETED` : `toast` « Vous êtes maintenant administrateur principal de « {{org}} ». » (`nomination.accept.done`) ; invalidation de l'organisation (`my_role`, `capabilities`), `contexts`, `members`, `nominations` ; focus sur le `h1` de la page (le menu change).
  - `status = PENDING_REVIEW` : `toast` « Nomination acceptée. L'équipe Connecte+ va la vérifier. » (`nomination.accept.review`) ; invalidation de `nominations` ; la carte passe en variante « en cours de vérification » ; focus sur son `h4`.
- Erreurs :

| Réponse | Affichage |
|---|---|
| `404 nomination_not_found`, `409 nomination_not_pending` | Fermeture ; `toast.info` « Cette nomination n'est plus en attente : elle a été annulée, a expiré ou n'est plus valable. » (`nomination.gone`) ; invalidation |
| `409 last_owner`, `409 last_effective_owner` | `FormAlert` : « La nomination ne peut pas aboutir pour le moment : l'organisation doit garder un administrateur principal disponible. Elle reste ouverte. » (`nomination.accept.invariant`) |
| `403 DENY_SECURITY`, `DENY_OBJECT_STATE` | Flux existants |
| `400 confirmation_required` | Inatteignable ; `errors.generic` |
| `429` | `team.retryLater` |
| Réseau | « Connexion perdue. Rechargez la page pour savoir si votre réponse a été prise en compte. » (`nomination.network`) |

**Mode refuser :**
- Titre : « Refuser cette nomination ? » (`nomination.decline.title`).
- Texte : « Votre rôle actuel ne change pas. {{initiator}} et les administrateurs principaux seront informés. » (`nomination.decline.body`).
- Boutons : « Garder la proposition » (focus initial) ; « Refuser » (destructif).
- Succès `204` : `toast` « Nomination refusée. » (`nomination.decline.done`), invalidation, focus sur le `h2` « À traiter » ou le titre de la liste des membres.
- Erreurs : comme le mode accepter (sans `last_*`).

### 10.2 E6j : `CancelNominationDialog` (`AlertDialog`)

- Titre : « Annuler la nomination de {{name}} ? » (`nomination.cancel.title`).
- Texte : « Aucun rôle ne change. {{name}} et les administrateurs principaux seront informés. » (`nomination.cancel.body`).
- Boutons : « Garder la nomination » (focus initial) ; « Annuler la nomination » (destructif).
- Succès `204` : `toast` « Nomination annulée. » (`nomination.cancel.done`) ; invalidation ; focus comme 10.1.
- Erreurs : `404`/`409 nomination_not_pending` → `nomination.gone` ; `403 DENY_PERMISSION` → « Vous ne pouvez plus annuler cette nomination. » (`nomination.cancel.denied`) + invalidation ; `429`, réseau : `team.retryLater`, `team.networkLost`.

### 10.3 Expiration

Une nomination échue est présentée `EXPIRED` par le serveur et sort de `?status=open` : la carte disparaît au rechargement. Si l'utilisateur agit sur une carte chargée avant l'échéance : `409 nomination_not_pending` → `nomination.gone`. L'interface **ne calcule pas** l'expiration elle-même (horloge du téléphone non fiable) ; elle affiche seulement la date.

---

## 11. E17 : « Demandes en attente de confirmation » sur `/profiles` (F2-bis)

### 11.1 Objectif

Permettre à la personne qui a accepté une invitation Administrateur de retrouver ses demandes en attente, d'obtenir un nouveau code de confirmation si elle a perdu le premier, et de retirer une demande. Ses organisations n'apparaissent pas encore dans « Mes profils » (aucune appartenance).

### 11.2 Structure

Section `AwaitingMembershipsSection` insérée dans `Profiles.tsx` **après** la section « Organisations » (avant « Organisations indisponibles »). Rendue **seulement si** la liste n'est pas vide.

- `h2` « Demandes en attente de confirmation » (`profiles.awaiting.title`), icône `Hourglass`.
- Texte : « Vous avez accepté ces invitations. Vous n'aurez accès à l'organisation qu'après la confirmation de votre identité par la personne qui vous a invité(e). Elle vous appellera pour vous demander votre code. » (`profiles.awaiting.intro`).
- Une carte par élément :
  - initiales de l'organisation (`UserAvatar shape="square"` sans image), nom (`h3`, tronqué, `title`), `SellerTypeBadge`, `RoleBadge`, périmètre ;
  - `status = AWAITING_CONFIRMATION` : « Acceptée le {{date}} » ; « Confirmation attendue avant le {{date}} » ; texte `text-xs` : « Votre code n'est pas réaffiché ici. Si vous ne l'avez plus, obtenez-en un nouveau. » (`profiles.awaiting.codeHint`) ; deux boutons : « Obtenir un nouveau code » (`outline`, icône `KeyRound`, `min-h-11`, `aria-label` « Obtenir un nouveau code pour {{name}} », ouvre 11.3) puis « Retirer ma demande » (`ghost`, texte destructif, `min-h-11`, `aria-label` « Retirer ma demande pour {{name}} », ouvre 11.4). Sur mobile : empilés, pleine largeur ;
  - `status = EXPIRED` : badge « Non confirmée à temps » (`profiles.awaiting.expired`, icône `Clock`) ; texte « Demandez une nouvelle invitation si vous souhaitez toujours rejoindre cette organisation. » (`profiles.awaiting.expiredHint`) ; aucun bouton.
- « Voir plus » si `next`.

Requête : `GET organization-invitations/awaiting/?page_size=10` au montage de `/profiles` (`staleTime: 60 s`, pas de cache persistant). La liste ne contient **jamais** de code.

### 11.3 `NewConfirmationCodeDialog` (`ResponsiveDialog`, deux étapes)

**Étape 1 (avertissement)** — titre « Obtenir un nouveau code ? » (`profiles.awaiting.newCodeTitle`) :
- Texte : « Un nouveau code sera créé pour « {{name}} ». L'ancien ne fonctionnera plus : si vous l'avez déjà donné, donnez le nouveau à la personne qui vous a invité(e). » (`profiles.awaiting.newCodeBody`).
- Boutons : « Garder mon code actuel » (focus initial, `profiles.awaiting.newCodeKeep`, ferme sans appel) ; « Obtenir un nouveau code » (`profiles.awaiting.newCodeSubmit`, `Loader2` pendant l'appel).
- Appel : `POST organization-invitations/<id>/confirmation-code/`, mutation `gcTime: 0`, sans `retry`.

**Étape 2 (code)** — même dialogue, contenu remplacé, `dismissible={false}` (le clic extérieur et le glissé ne ferment pas ; Échap et le bouton ferment), titre « Votre nouveau code » (`profiles.awaiting.newCodeShown`) :
- Bloc du code identique à 9.4 point 3 (même composant `ConfirmationCodeDisplay`, consigne `invitation.awaiting.codeInstruction`, avertissement `invitation.awaiting.codeOnce`).
- « Confirmation attendue avant le {{date}}. » (`confirmation_expires_at` de la réponse).
- Bouton unique « J'ai noté le code » (`profiles.awaiting.newCodeDone`) : ferme, efface le code de l'état (`mutation.reset()`), rend le focus au bouton « Obtenir un nouveau code » de la carte.
- Focus à l'apparition : le `h2` du bloc du code (`tabIndex={-1}`). Pas d'annonce `aria-live` du code ; annonce « Nouveau code affiché à l'écran. » (`profiles.awaiting.newCodeAnnounce`).

**Erreurs (étape 1, `FormAlert`) :**

| Réponse | Affichage |
|---|---|
| `404 invitation_not_found`, `409 invitation_not_awaiting_confirmation` | Fermeture ; `toast.info` « Cette demande n'est plus en attente. » (`team.invitations.notPending`, existant) ; rechargement de `awaiting/` **et** de `contexts` (la demande a peut-être été confirmée) |
| `429` | `team.retryLater` ; bouton bloqué pendant `Retry-After` |
| Réseau coupé sans réponse | « Connexion perdue. Un nouveau code a peut-être été créé et l'ancien ne fonctionne peut-être plus : réessayez pour en obtenir un. » (`profiles.awaiting.newCodeNetwork`) ; bouton de nouvel essai manuel (jamais automatique) |

### 11.4 `WithdrawAwaitingDialog` (`AlertDialog`)

- Titre : « Retirer votre demande pour « {{name}} » ? » (`profiles.awaiting.withdrawTitle`).
- Texte : « Vous ne rejoindrez pas cette organisation. Le lien ne pourra plus être utilisé ; il faudra une nouvelle invitation. » (`profiles.awaiting.withdrawBody`).
- Boutons : « Garder la demande » (focus initial) ; « Retirer ma demande » (destructif).
- Succès `204` : carte retirée, `toast` « Demande retirée. » (`profiles.awaiting.withdrawn`), annonce dans la région `aria-live` de `/profiles` (nouvelle, unique), focus sur le `h2` de la section, ou sur le `h2` « Organisations » si la section disparaît.
- Erreurs : `404 invitation_not_found`, `409 invitation_not_awaiting_confirmation` → `toast.info` « Cette demande n'est plus en attente. » (`team.invitations.notPending`, existant) + rechargement (la demande a peut-être été confirmée : invalider aussi `contexts`) ; `429` ; réseau : `team.networkLost`.

### 11.5 États

| État | Rendu |
|---|---|
| Chargement | Rien (section absente tant qu'on ne sait pas qu'elle est non vide) |
| Vide | Section absente |
| Erreur | Section absente ; aucune alerte (information secondaire ; la notification reste le canal principal). Nouvel essai à la prochaine visite. |
| Hors ligne | Liste en mémoire conservée ; boutons « Obtenir un nouveau code » et « Retirer ma demande » désactivés + `common.offlineAction` |

### 11.6 Après confirmation ou rejet

Quand la demande est confirmée (notification « Votre accès à « {organisation} » est confirmé. »), l'organisation apparaît dans `contexts/` et la demande disparaît de `awaiting/` au rechargement suivant. Aucune bascule automatique de profil. Une demande rejetée (par un confirmateur ou après 5 codes faux) disparaît aussi ; la notification « Votre demande pour rejoindre « {organisation} » n'a pas été confirmée. » en informe la personne, sans nom ni motif.

---

## 12. Rétrogradation d'un autre Administrateur principal (F5)

Synthèse du parcours, déjà couvert par E6b :

1. Acteur `OWNER`, ligne d'un autre `OWNER` → « Changer le rôle ».
2. Étape 1 : choix parmi Administrateur, Éditeur, Analyste, Membre.
3. Étape 2 : texte `team.demoteOwnerBody` (5.2, mentionne la notification), case + mot de passe.
4. Organisation standard : `200`, toast, la ligne change ; l'acteur n'est pas averti de la notification autrement que par le texte de l'étape 2.
5. Organisation à vérification renforcée : `409 primary_admin_change_requires_verification` (5.3). L'interface ne sait pas d'avance si l'organisation est renforcée et ne l'affiche jamais.
6. `409 last_owner` / `last_effective_owner` : textes 15.1.

Un administrateur (`ADMIN`) ne voit aucun menu sur une ligne `OWNER` (inchangé).

---

## 13. E3 : création d'organisation sans plafond (F4)

### 13.1 Changements

- `api/types.ts` : retirer `max_organizations_per_account` de `OrganizationLimits` ; ajouter les clés du contrat §7.5 si absentes (`invitation_ttl_days`, `max_pending_invitations`, facultatives).
- `lib/organization-form.ts` : retirer `max_organizations_per_account` de `FALLBACK_LIMITS`. Aucune valeur de plafond d'organisations ne subsiste dans le front (test : `grep max_organizations src` vide hors fixtures supprimées).
- `lib/api-errors.ts` : retirer `organization_limit_reached` de `BUSINESS_CODES` ; ajouter `account_review_required` et tous les codes de 15.3.
- `orgNew.description` : « … et de travailler avec une équipe. Vous en serez l'administrateur principal. »

### 13.2 Parcours et erreurs (remplace L0-09 §6.2 point 5 et §6.4 ligne « Plafond atteint »)

| Réponse | Affichage |
|---|---|
| `201`, `governance.under_review === false` | Inchangé : navigation vers `/organizations/:id` avec `justCreated` |
| `201`, `governance.under_review === true` | Même navigation ; la bannière `under_review` (section 3) s'affiche au-dessus de l'alerte de création. **Aucun texte ne dit pourquoi** (ni nombre de créations, ni seuil). |
| `409 account_review_required` | `FormAlert` : « Votre compte doit être examiné par l'équipe Connecte+ avant de créer ou de rejoindre d'autres organisations. » (`errors.code.account_review_required`, texte du contrat) ; lien d'aide si `HELP_LINKS.account` défini ; **pas** de lien « Mes profils » ni de conseil « quittez une organisation » (ce serait suggérer une limite) ; valeurs saisies conservées. |
| `429` (`org_create` ou `org_create_burst`, indiscernables) | `FormAlert` : « Vous avez créé plusieurs organisations récemment. Réessayez plus tard. » (`orgNew.rateLimited`) ; si `Retry-After` est lisible : « Réessayez dans {{minutes}} min. » (`orgNew.rateLimitedIn`) ; bouton désactivé pendant le délai. Aucun chiffre de quota. |
| Autres | Inchangées (L0-09 §6.4) |

Hors ligne : texte L0-09 §6.4 inchangé, mais la justification « soumise à un plafond » est retirée du code et des commentaires.

### 13.3 Textes supprimés

`errors.code.organization_limit_reached`, `invitation.err.limit.title`, `invitation.err.limit.body`. Le test `api-errors.test.ts` qui vérifie l'absence de chiffre est transposé sur `account_review_required`.

---

## 14. États de synthèse par écran

| Écran | Chargement | Vide | Erreur | Hors ligne | Succès | Permission refusée |
|---|---|---|---|---|---|---|
| E18 bannière | aucune bannière | aucune bannière | aucune (vient de `internal/`, déjà géré par `OrganizationPage`) | dernière valeur en mémoire | — | sans objet |
| E6 « À traiter » | section absente | section absente | ligne compacte + Réessayer | cartes conservées, boutons désactivés | toast + `aria-live` | `DENY_*` : flux de `OrganizationPage` |
| E6f | — | — | `FormAlert` par code (6.4) | bouton déclencheur désactivé | toast, carte et badge | `DENY_PERMISSION` : fermeture + rechargement |
| E6g | — | — | par code (8.3) ; code faux : erreur sous le champ ; 5e code faux : fermeture + toast | boutons désactivés, saisie conservée | toast, ligne membre | `DENY_PERMISSION` : toast + rechargement |
| E6h | — | — | par code (8.4) | boutons désactivés | toast | `DENY_PERMISSION` : toast + rechargement |
| E6i / E6j | — | — | par code (10.1, 10.2) | boutons désactivés | toast | `DENY_PERMISSION` (E6j) |
| E15 aperçu | `Skeleton` (existant) | — | 9.5 + D1 §4.5 | boutons désactivés | 200 : D1 §4.4.3 ; 202 : 9.4 (code affiché) | `DENY_SECURITY` : D1 |
| E17 | section absente | section absente | section absente ; nouveau code : 11.3 | liste conservée, boutons désactivés | nouveau code affiché ; retrait : toast | sans objet |
| E3 | inchangé | — | 13.2 | inchangé | navigation + bannière éventuelle | `DENY_SECURITY` inchangé |

---

## 15. Contenus : clés i18n

### 15.1 Remplacements « propriétaire » et textes modifiés (F1-bis, F2-bis)

| Clé | Nouveau texte |
|---|---|
| `role.OWNER` | Administrateur principal |
| `role.OWNER_desc`, `role.ADMIN_desc` | voir 2.1 |
| `role.MEMBER`, `role.MEMBER_desc` | **nouvelles**, voir 2.1 |
| `errors.deny.PERMISSION.org` | Votre rôle ne permet pas cette action. Demandez à un administrateur principal ou à un administrateur de l'organisation. |
| `errors.code.last_owner` | Vous êtes le dernier administrateur principal : vous ne pouvez pas quitter l'organisation. Un autre administrateur principal doit d'abord être nommé, ou l'organisation doit être archivée. |
| `errors.code.last_owner_demote` | Une organisation doit toujours avoir au moins un administrateur principal. |
| `errors.code.last_effective_owner` | Cette organisation a des offres actives : elle doit garder au moins un administrateur principal disponible. Proposez d'abord un autre administrateur principal. |
| `errors.code.owner_must_be_demoted` | Cette personne est administrateur principal. Changez d'abord son rôle, puis retirez-la. |
| clé `orgDenied` (contacts, l. 489 de `fr.ts`) | Seuls les administrateurs principaux et les administrateurs gèrent les moyens de contact. |
| `orgNew.description` | voir 13.1 |
| `org.unavailable.recourse.SUSPENDED.other` | Pour en savoir plus, adressez-vous à un administrateur principal de l'organisation ou au support de Connecte+. |
| `org.unavailable.recourse.ARCHIVED.other` | Pour toute question, adressez-vous à un administrateur principal de l'organisation. |
| `org.home.createdBody` | voir 3.6 |
| `org.home.archiveBody` | Réservé aux administrateurs principaux. Les offres de l'organisation ne seront plus visibles. |
| `orgEdit.readOnly` | Seuls les administrateurs principaux et les administrateurs peuvent modifier le profil de l'organisation. |
| `team.invite.labelHelp` | … Visible par les administrateurs principaux et les administrateurs de l'organisation, … (reste inchangé) |
| `team.invite.errLimit` | Le nombre maximal d'invitations ouvertes est atteint (liens en attente et demandes à confirmer). Annulez une invitation inutilisée ou traitez une demande à confirmer pour en créer une nouvelle. |
| `team.lastOwner` | Seul administrateur principal actif |
| `team.lastOwnerHelp` | Les autres administrateurs principaux, s'il y en a, ne peuvent pas agir actuellement (compte inactif ou restreint). |
| `team.lastOwnerSelfHint` | Si vous quittez l'organisation, elle n'aura plus d'administrateur principal disponible. Proposez d'abord un autre administrateur principal. |
| `team.ownersOnly` | Réservé aux administrateurs principaux |
| `team.ownerRemoveHint` | Pour retirer cet administrateur principal, changez d'abord son rôle. |
| `team.demoteOwnerBody` | voir 5.2 |
| `team.since` / `team.colSince` | Dans l'équipe depuis {{date}} / Dans l'équipe depuis |
| `invitation.err.member.body` | Cette invitation ne change pas votre rôle. Si vous voulez un autre rôle, demandez-le à un administrateur principal ou à un administrateur. |
| `verif.readOnly` | Seuls les administrateurs principaux et les administrateurs peuvent envoyer des pièces. |
| clé de migration (l. 1176, « … dont vous êtes le propriétaire … ») | « {{name}} » est maintenant une organisation dont vous êtes l'administrateur principal. (suite inchangée) |
| clé `messagesDenied` (l. 1207) | Les messages de l'organisation sont réservés aux administrateurs principaux et aux administrateurs. |
| clé `notMember` (l. 1208) | Vous ne faites plus partie de l'organisation qui a publié cette offre. |
| `deletionBlockers.*` (F3 en pause) | remplacer « propriétaire » par « administrateur principal » et « Transférez la propriété » par « Proposez un autre administrateur principal » ; refonte complète par ADR 0012 |

**Supprimées :** `team.transfer`, `team.transferTo`, `team.transferTitle`, `team.transferBody`, `team.transferMyRole`, `team.transferAlt`, `team.transferConfirm`, `team.transferButton`, `team.transferred`, `team.promoteOwnerBody`, `team.invite.rolesNote`, `errors.code.invalid_transfer`, `errors.code.organization_limit_reached`, `invitation.err.limit.*`.

### 15.2 Nouvelles clés

| Clé | Texte |
|---|---|
| `scope.ORGANIZATION` | Toute l'organisation |
| `scope.limited` | Périmètre limité |
| `team.scopeLine` | Périmètre : {{scope}} |
| `team.rolesOwnerNote` | Le rôle Administrateur principal ne s'obtient jamais par invitation : un administrateur principal propose la personne, qui doit accepter. |
| `team.changeRoleNominateHint` | Pour faire de {{name}} un administrateur principal, utilisez « Proposer comme administrateur principal » dans le menu de sa ligne. |
| `team.nominate` | Proposer comme administrateur principal |
| `team.nominatedBadge` | Proposé(e) administrateur principal |
| `team.nominate.title` | Proposer {{name}} comme administrateur principal |
| `team.nominate.kindLabel` | Que souhaitez-vous faire ? |
| `team.nominate.promote` | Ajouter un administrateur principal |
| `team.nominate.promoteDesc` | {{name}} devient administrateur principal. Vous le restez aussi. |
| `team.nominate.transfer` | Me remplacer |
| `team.nominate.transferDesc` | {{name}} devient administrateur principal. Vous prenez le rôle choisi ci-dessous. |
| `team.nominate.transferBusy` | Un remplacement est déjà en cours dans l'organisation. |
| `team.nominate.myRoleLabel` | Votre rôle après le remplacement |
| `team.nominate.howTitle` | Comment ça se passe |
| `team.nominate.step1` | {{name}} reçoit une notification et doit accepter. |
| `team.nominate.step2` | Tous les administrateurs principaux sont informés à chaque étape. |
| `team.nominate.step3` | Pour certaines organisations, l'équipe Connecte+ vérifie aussi la nomination avant qu'elle prenne effet. |
| `team.nominate.step4` | Sans réponse avant l'échéance, la proposition expire. Vous pouvez l'annuler tant qu'elle n'a pas abouti. |
| `team.nominate.continue` | Continuer |
| `team.nominate.summary` | {{name}} deviendra administrateur principal après son acceptation. |
| `team.nominate.summaryTransfer` | Vous prendrez alors le rôle {{role}}. |
| `team.nominate.confirm` | Je confirme cette proposition |
| `team.nominate.submit` | Envoyer la proposition |
| `team.nominate.sent` | Proposition envoyée à {{name}}. Aucun rôle ne change avant sa réponse. |
| `team.nominate.unavailable` | Cette proposition n'est pas possible pour ce compte pour le moment. |
| `team.nominate.denied` | Seul un administrateur principal en activité peut proposer une nomination. |
| `team.nominate.network` | Connexion perdue. La proposition a peut-être été envoyée : vérifiez « À traiter » avant de réessayer. |
| `team.pending.title` | À traiter |
| `team.pending.forMe` | Une nomination vous concerne |
| `team.pending.toConfirm` | Demandes d'accès à confirmer |
| `team.pending.nominations` | Nominations en cours |
| `team.pending.loadError` | Impossible de vérifier les demandes en attente. |
| `team.pending.loadMore` | Voir plus |
| `team.awaiting.title` | {{name}} a accepté l'invitation |
| `team.awaiting.titleAnonymous` | Une personne a accepté une invitation comme Administrateur |
| `team.awaiting.phoneHint` | Téléphone se terminant par {{hint}} |
| `team.awaiting.phoneHintAria` | Téléphone se terminant par {{digits}} |
| `team.awaiting.acceptedAt` | Acceptée le {{date}} |
| `team.awaiting.deadline` | À confirmer avant le {{date}} |
| `team.awaiting.inviterNoAuthority` | La personne qui a créé cette invitation ne peut plus donner ce rôle (elle a changé de rôle ou quitté l'équipe). Seul un administrateur principal peut encore confirmer ou rejeter cette demande. Assurez-vous que cette arrivée est toujours souhaitée. |
| `team.awaiting.callHint` | Pour confirmer, appelez la personne au numéro que vous connaissez et demandez-lui le code à 6 chiffres affiché sur son écran. Ne demandez pas le code par message. Si vous ne la reconnaissez pas, rejetez la demande. |
| `team.awaiting.notYours` | Seuls la personne qui a créé l'invitation et les administrateurs principaux peuvent confirmer ou rejeter cette demande. |
| `team.awaiting.confirm` | Confirmer l'accès |
| `team.awaiting.confirmAria` | Confirmer l'accès de {{name}} |
| `team.awaiting.reject` | Rejeter |
| `team.awaiting.rejectAria` | Rejeter la demande de {{name}} |
| `team.awaiting.gone` | Cette demande n'est plus en attente : elle a été traitée, retirée, rejetée ou a expiré. |
| `team.confirmInvite.title` | Confirmer l'accès de {{name}} |
| `team.confirmInvite.callTitle` | Appelez d'abord la personne |
| `team.confirmInvite.callBody` | Appelez {{name}} au numéro que vous connaissez déjà, pas à un numéro reçu avec la demande, et demandez-lui le code à 6 chiffres affiché sur son écran. Ne demandez pas le code par message. Si la personne que vous appelez n'a pas de code, rejetez la demande. |
| `team.confirmInvite.person` | Personne |
| `team.confirmInvite.phone` | Téléphone |
| `team.confirmInvite.phoneCheck` | Vérifiez que ces chiffres correspondent au numéro que vous appelez. |
| `team.confirmInvite.body` | En confirmant, {{name}} devient Administrateur de « {{org}} » immédiatement : cette personne pourra gérer le profil, la vérification, l'équipe (sauf les administrateurs principaux), les contacts et les messages. Les administrateurs principaux en sont informés. |
| `team.confirmInvite.codeLabel` | Code à 6 chiffres |
| `team.confirmInvite.codeHelp` | Le code que la personne lit sur son écran, par exemple 482 913. |
| `team.confirmInvite.codeIncomplete` | Saisissez les 6 chiffres du code. |
| `team.confirmInvite.codeInvalid` | Ce code est incorrect. Vérifiez-le avec {{name}} au téléphone. Après plusieurs codes incorrects, la demande est rejetée automatiquement. |
| `team.confirmInvite.exhausted` | Trop de codes incorrects : la demande a été rejetée automatiquement. Si cette personne doit rejoindre l'équipe, créez une nouvelle invitation. |
| `team.confirmInvite.badPassword` | Mot de passe incorrect. Aucun essai de code n'a été compté. |
| `team.confirmInvite.check` | J'ai obtenu ce code en appelant {{name}}, et c'est bien la personne que j'ai voulu inviter |
| `team.confirmInvite.submit` | Confirmer l'accès |
| `team.confirmInvite.done` | {{name}} a rejoint l'équipe comme Administrateur. |
| `team.confirmInvite.unavailable` | Cette personne ne peut pas rejoindre l'organisation pour le moment. La demande reste en attente jusqu'à son échéance ; vous pouvez aussi la rejeter. |
| `team.confirmInvite.alreadyMember` | Cette personne fait déjà partie de l'équipe. |
| `team.confirmInvite.denied` | Vous ne pouvez plus confirmer cette demande. Un administrateur principal peut le faire. |
| `team.confirmInvite.network` | Connexion perdue. L'accès a peut-être été confirmé : vérifiez la liste avant de réessayer. |
| `team.rejectInvite.title` | Rejeter la demande de {{name}} ? |
| `team.rejectInvite.titleAnonymous` | Rejeter cette demande ? |
| `team.rejectInvite.body` | Cette personne n'aura aucun accès à l'organisation et le lien ne pourra plus être utilisé. Elle sera prévenue, sans voir votre nom. |
| `team.rejectInvite.inviterNoAuthority` | La personne qui a créé cette invitation ne peut plus donner ce rôle. |
| `team.rejectInvite.when` | Rejetez si la personne que vous avez appelée n'a pas de code, ou si vous ne savez pas qui a accepté. |
| `team.rejectInvite.keep` | Garder la demande |
| `team.rejectInvite.submit` | Rejeter |
| `team.rejectInvite.done` | Demande rejetée. |
| `team.invite.confirmBadge` | Confirmation requise |
| `team.invite.adminConfirmNote` | Après l'acceptation, vous ou un administrateur principal devrez appeler la personne pour obtenir son code de confirmation. Aucun accès n'est ouvert avant. |
| `team.invite.ownerNote` | Le rôle Administrateur principal ne peut pas être donné par invitation. Une fois la personne dans l'équipe, un administrateur principal peut la proposer. |
| `team.invite.linkWarningAdmin` | voir 7.3 |
| `team.invite.errRole` | Vous ne pouvez pas donner ce rôle par invitation. |
| `nomination.kind.PROMOTE` | Nouvel administrateur principal |
| `nomination.kind.TRANSFER` | Remplacement d'un administrateur principal |
| `nomination.status.PENDING_ACCEPTANCE` | En attente d'acceptation |
| `nomination.status.PENDING_REVIEW` | Vérification par Connecte+ |
| `nomination.expires` | Échéance : {{date}} |
| `nomination.transferNote` | {{initiator}} prendra le rôle {{role}}. |
| `nomination.by` | Proposé(e) par {{name}} |
| `nomination.target.title` | Vous êtes proposé(e) comme administrateur principal |
| `nomination.target.body` | {{initiator}} vous propose comme administrateur principal de « {{org}} ». |
| `nomination.target.duties` | En acceptant, vous répondrez de l'organisation sur Connecte+ : vous pourrez gérer toute l'équipe, y compris les administrateurs, proposer d'autres administrateurs principaux et archiver l'organisation. Tous les administrateurs principaux seront informés de votre réponse. |
| `nomination.target.reviewNote` | Après votre acceptation, l'équipe Connecte+ vérifiera la nomination. Votre rôle ne changera qu'après sa décision. |
| `nomination.target.reviewTitle` | Votre nomination est en cours de vérification |
| `nomination.target.reviewBody` | Vous avez accepté. L'équipe Connecte+ vérifie la nomination. Votre rôle actuel ne change pas avant sa décision. |
| `nomination.target.accept` | Accepter la nomination |
| `nomination.target.decline` | Refuser |
| `nomination.manager.waitingTarget` | En attente de la réponse de {{name}}. |
| `nomination.manager.waitingReview` | {{name}} a accepté. L'équipe Connecte+ vérifie la nomination avant qu'elle prenne effet. |
| `nomination.manager.cancel` | Annuler la nomination |
| `nomination.manager.cancelAria` | Annuler la nomination de {{name}} |
| `nomination.accept.title` | Devenir administrateur principal de « {{org}} » ? |
| `nomination.accept.later` | Pas maintenant |
| `nomination.accept.submit` | Accepter |
| `nomination.accept.done` | Vous êtes maintenant administrateur principal de « {{org}} ». |
| `nomination.accept.review` | Nomination acceptée. L'équipe Connecte+ va la vérifier. |
| `nomination.accept.invariant` | La nomination ne peut pas aboutir pour le moment : l'organisation doit garder un administrateur principal disponible. Elle reste ouverte. |
| `nomination.decline.title` | Refuser cette nomination ? |
| `nomination.decline.body` | Votre rôle actuel ne change pas. {{initiator}} et les administrateurs principaux seront informés. |
| `nomination.decline.keep` | Garder la proposition |
| `nomination.decline.submit` | Refuser |
| `nomination.decline.done` | Nomination refusée. |
| `nomination.cancel.title` | Annuler la nomination de {{name}} ? |
| `nomination.cancel.body` | Aucun rôle ne change. {{name}} et les administrateurs principaux seront informés. |
| `nomination.cancel.keep` | Garder la nomination |
| `nomination.cancel.submit` | Annuler la nomination |
| `nomination.cancel.done` | Nomination annulée. |
| `nomination.cancel.denied` | Vous ne pouvez plus annuler cette nomination. |
| `nomination.gone` | Cette nomination n'est plus en attente : elle a été annulée, a expiré ou n'est plus valable. |
| `nomination.network` | Connexion perdue. Rechargez la page pour savoir si votre réponse a été prise en compte. |
| `invitation.preview.scope` | Périmètre |
| `invitation.preview.access` | Accès |
| `invitation.preview.accessToggle` | Voir les {{count}} accès |
| `invitation.preview.adminLimits` | Ce rôle ne permet ni de nommer un administrateur principal, ni d'archiver l'organisation. |
| `invitation.preview.confirmTitle` | Confirmation nécessaire |
| `invitation.preview.confirmBody` | Pour ce rôle, la personne qui vous a invité(e) devra confirmer votre identité. Elle verra votre nom abrégé et les deux derniers chiffres de votre numéro de téléphone. Aucun accès ne vous sera ouvert avant cette confirmation. |
| `invitation.preview.codeNote` | Après avoir accepté, vous recevrez un code à 6 chiffres. Vous le donnerez de vive voix à cette personne quand elle vous appellera. |
| `invitation.preview.bodyPending` | Votre profil personnel et vos offres personnelles ne changent pas. Après confirmation, vous pourrez quitter l'organisation à tout moment. |
| `invitation.acceptPending` | Accepter l'invitation |
| `invitation.awaiting.title` | Demande envoyée à « {{name}} » |
| `invitation.awaiting.body` | Vous avez accepté le rôle {{role}}. La personne qui vous a invité(e) ou un administrateur principal doit maintenant confirmer votre identité. |
| `invitation.awaiting.codeTitle` | Votre code de confirmation |
| `invitation.awaiting.codeAria` | Code : {{digits}} |
| `invitation.awaiting.codeInstruction` | Donnez ce code de vive voix à la personne qui vous a invité(e), quand elle vous appelle ou en personne. Elle en a besoin pour vous ouvrir l'accès. Ne le communiquez à personne d'autre et ne l'envoyez pas par message, même si on vous le demande. |
| `invitation.awaiting.codeOnce` | Ce code ne sera plus affiché quand vous quitterez cette page. Si vous l'oubliez, obtenez-en un nouveau depuis « Mes profils » : l'ancien ne fonctionnera plus. |
| `invitation.awaiting.deadline` | Confirmation attendue avant le {{date}}. |
| `invitation.awaiting.noAccess` | Vous n'avez encore aucun accès à l'organisation. Vous serez prévenu(e) par une notification. Sans confirmation avant cette date, la demande expire et il faudra une nouvelle invitation. |
| `invitation.awaiting.withdraw` | Retirer ma demande |
| `invitation.awaiting.announce` | Demande envoyée. Votre code de confirmation est affiché à l'écran. |
| `invitation.awaiting.withdrawnTitle` | Demande retirée |
| `invitation.awaiting.withdrawnBody` | Vous ne rejoindrez pas cette organisation. Le lien ne peut plus être utilisé. |
| `invitation.err.review.title` | Examen du compte nécessaire |
| `invitation.err.review.body` | Votre compte doit être examiné par l'équipe Connecte+ avant de rejoindre d'autres organisations. Votre invitation reste valable jusqu'à son échéance. |
| `invitation.err.awaiting.title` | Une demande est déjà en attente |
| `invitation.err.awaiting.body` | Vous avez déjà accepté une invitation comme Administrateur pour cette organisation. Attendez sa confirmation, ou retirez cette demande depuis « Mes profils » pour utiliser ce lien. |
| `access.group.organization` … `access.group.billing` | Organisation, Équipe, Offres, Avis, Contact, Messages, Statistiques, Facturation |
| `access.cap.<code avec « . » remplacé par « _ »>` | libellés de 9.2 (ex. `access.cap.org_view_internal`) |
| `access.others_one` / `access.others_other` | et {{count}} autre accès / et {{count}} autres accès |
| `profiles.awaiting.title` | Demandes en attente de confirmation |
| `profiles.awaiting.intro` | Vous avez accepté ces invitations. Vous n'aurez accès à l'organisation qu'après la confirmation de votre identité par la personne qui vous a invité(e). Elle vous appellera pour vous demander votre code. |
| `profiles.awaiting.acceptedAt` | Acceptée le {{date}} |
| `profiles.awaiting.deadline` | Confirmation attendue avant le {{date}} |
| `profiles.awaiting.codeHint` | Votre code n'est pas réaffiché ici. Si vous ne l'avez plus, obtenez-en un nouveau. |
| `profiles.awaiting.newCode` | Obtenir un nouveau code |
| `profiles.awaiting.newCodeAria` | Obtenir un nouveau code pour {{name}} |
| `profiles.awaiting.newCodeTitle` | Obtenir un nouveau code ? |
| `profiles.awaiting.newCodeBody` | Un nouveau code sera créé pour « {{name}} ». L'ancien ne fonctionnera plus : si vous l'avez déjà donné, donnez le nouveau à la personne qui vous a invité(e). |
| `profiles.awaiting.newCodeKeep` | Garder mon code actuel |
| `profiles.awaiting.newCodeSubmit` | Obtenir un nouveau code |
| `profiles.awaiting.newCodeShown` | Votre nouveau code |
| `profiles.awaiting.newCodeDone` | J'ai noté le code |
| `profiles.awaiting.newCodeAnnounce` | Nouveau code affiché à l'écran. |
| `profiles.awaiting.newCodeNetwork` | Connexion perdue. Un nouveau code a peut-être été créé et l'ancien ne fonctionne peut-être plus : réessayez pour en obtenir un. |
| `profiles.awaiting.expired` | Non confirmée à temps |
| `profiles.awaiting.expiredHint` | Demandez une nouvelle invitation si vous souhaitez toujours rejoindre cette organisation. |
| `profiles.awaiting.withdraw` | Retirer ma demande |
| `profiles.awaiting.withdrawAria` | Retirer ma demande pour {{name}} |
| `profiles.awaiting.withdrawTitle` | Retirer votre demande pour « {{name}} » ? |
| `profiles.awaiting.withdrawBody` | Vous ne rejoindrez pas cette organisation. Le lien ne pourra plus être utilisé ; il faudra une nouvelle invitation. |
| `profiles.awaiting.keep` | Garder la demande |
| `profiles.awaiting.withdrawn` | Demande retirée. |
| `governance.missing.title` | Administration à régulariser |
| `governance.missing.body` | voir 3.3 |
| `governance.missing.badge` | Administration à régulariser |
| `governance.missing.help` | Comment régulariser l'administration |
| `governance.review.title` | Organisation en cours d'examen |
| `governance.review.body` | voir 3.3 |
| `governance.review.badge` | En cours d'examen |
| `orgNew.rateLimited` | Vous avez créé plusieurs organisations récemment. Réessayez plus tard. |
| `orgNew.rateLimitedIn` | Réessayez dans {{minutes}} min. |

### 15.3 Codes d'erreur (`errors.code.*`, ajout à `BUSINESS_CODES`)

| Code | Texte |
|---|---|
| `account_review_required` | Votre compte doit être examiné par l'équipe Connecte+ avant de créer ou de rejoindre d'autres organisations. |
| `primary_admin_change_requires_verification` | Dans cette organisation, le changement de rôle d'un administrateur principal doit être traité par l'équipe Connecte+. Aucun changement n'a été fait. |
| `use_primary_admin_nomination` | Pour nommer un administrateur principal, utilisez « Proposer comme administrateur principal ». |
| `invalid_nomination` | Cette personne est déjà administrateur principal. |
| `nomination_already_open` | Une nomination est déjà en cours pour cette personne, ou un remplacement est déjà en cours dans l'organisation. Consultez « À traiter ». |
| `nomination_not_pending`, `nomination_not_found` | = `nomination.gone` |
| `invitation_not_awaiting_confirmation` | = `team.awaiting.gone` |
| `already_awaiting_confirmation` | = `invitation.err.awaiting.body` |
| `confirmation_code_required` | = `team.confirmInvite.codeIncomplete` |
| `confirmation_code_invalid` | Ce code est incorrect. Après plusieurs codes incorrects, la demande est rejetée automatiquement. (texte générique sans nom ; E6g utilise `team.confirmInvite.codeInvalid`) |
| `confirmation_code_exhausted` | = `team.confirmInvite.exhausted` |

Le garde `client-rules.test.ts` reste vert : aucun texte n'emploie « garanti », « certifié », « de confiance », « vendeur vérifié ». Les textes de revue disent « vérifie la nomination », jamais « organisation vérifiée ». Aucun texte n'affiche le nombre d'essais de code autorisés ou restants.

---

## 16. Composants

### 16.1 Réutilisés (noms exacts)

`OrganizationPage`, `PageHeader`, `RoleBadge`, `SellerTypeBadge`, `UserAvatar` (initiales, sans `src`), `Badge`, `Alert`/`AlertTitle`/`AlertDescription`, `AlertDialog`, `ResponsiveDialog` (prop `dismissible` de D1), `RadioGroup`, `Checkbox`, `Label`, `Input`, `Button`, `Collapsible`, `Tabs`, `DropdownMenu*`, `Skeleton`, `ErrorState`, `EmptyState`, `FormAlert`, `PasswordInput`, `Field`, `errorProps`, `fieldInputClass`, `SensitiveConfirmFields` (prop de libellé de case ajoutée si absente), `MemberRow`, `MemberActionsMenu`, `InviteDialog`, `ChangeRoleDialog`, `CopyLinkField`, `LeaveOrganizationCard`, `use-rate-block`, `useOnlineStatus`, `useIsMobile`, `describeApiError`, `getApiErrorCode`, `formatDateTime`, `formatLongDate`, `formatMonthYear`, `sonner`.

### 16.2 Nouveaux (justifiés)

| Composant ou module | Justification | Props / signature |
|---|---|---|
| `GovernanceBanner` | Deux états indépendants affichés sur toutes les sections ; un seul point de rendu dans `OrganizationPage` | `governance?: {primary_admin_state, under_review}` |
| `TeamPendingActions` | Regroupe les actions attendues en tête de E6 ; isole les deux requêtes et leur état | `org`, `onAnnounce`, `headingRef` |
| `AwaitingInvitationCard` | Deux variantes (`can_confirm` ou non), avertissement `inviter_has_authority` ; données personnelles limitées à une seule variante, testable seule | `invitation`, `online`, `onConfirm`, `onReject` |
| `PhoneHint` | Lecture correcte de l'indice par les lecteurs d'écran ; point unique pour garantir qu'il n'est jamais copié ailleurs | `hint: string` |
| `ConfirmationCodeDisplay` | Affichage du code (9.4, 11.3) : groupes de 3, lecture chiffre par chiffre, consigne ; point unique pour les tests de non-fuite | `code: string`, `headingId` |
| `ConfirmationCodeInput` | Champ de saisie du code (E6g) : normalisation des chiffres, `autoComplete="off"`, erreurs | `value`, `onChange`, `error`, `disabled` |
| `ConfirmAdminInvitationDialog`, `RejectAdminInvitationDialog` | Actions sensibles avec erreurs propres | `orgId`, `orgName`, `invitation`, `onClose`, `onDone`, `onAnnounce` |
| `NominationCard` | Variantes `target` et `manager` | `nomination`, `variant`, `orgName`, `online`, `onAccept`, `onDecline`, `onCancel` |
| `NominatePrimaryAdminDialog` | Remplace `TransferOwnershipDialog` (deux genres, deux étapes) | `orgId`, `member`, `transferBusy: boolean`, `onClose`, `onAnnounce` |
| `NominationResponseDialog` | Accepter / refuser, mêmes erreurs | `mode: "accept" \| "decline"`, `orgId`, `orgName`, `nomination`, … |
| `CancelNominationDialog` | Alerte destructive simple | `orgId`, `nomination`, … |
| `RoleAccessList` + `lib/role-access.ts` (`groupCapabilities`) | Traduction des codes de capacité en accès lisibles regroupés, testable (Vitest : chaque code de la matrice a un libellé) | `capabilities: string[]` |
| `AwaitingMembershipsSection`, `NewConfirmationCodeDialog`, `WithdrawAwaitingDialog` | Section de `/profiles`, nouveau code, retrait | — |
| `lib/team.ts` : `memberActions` (amendée), `assignableRoles`, `invitableRoles`, `scopeLabel` | Matrices pures testées case par case | — |
| `lib/confirmation-code.ts` : `normalizeCode(input)`, `formatCodeGroups(code)`, `spellDigits(code)` | Fonctions pures testées (collage « 482 913 », lettres, plus de 6 chiffres) | — |
| `lib/help.ts` : `HELP_LINKS` | Liens d'aide configurables (Q19), `undefined` avant L1-21 | `{ governance?: string; account?: string }` |
| Hooks (`use-organization-team.ts`, `use-organization-invitations.ts`, nouveau `use-primary-admin-nominations.ts`) | `useAwaitingInvitations(orgId, enabled)`, `useConfirmInvitation`, `useRejectInvitation`, `useMyAwaitingInvitations`, `useRegenerateConfirmationCode` (`gcTime: 0`), `useWithdrawAwaitingInvitation`, `useNominations(orgId)`, `useCreateNomination`, `useAcceptNomination`, `useDeclineNomination`, `useCancelNomination` | mutations sans `retry` |

**Retirés :** `TransferOwnershipDialog`, `useTransferOwnership`, l'action `transfer` de `TeamAction`.

---

## 17. Accessibilité

- **Cibles de 44 px** (`min-h-11 min-w-11`) : tous les boutons des cartes « À traiter », de E17, des dialogues, lignes de `RadioGroup` (label englobant), cases à cocher (label étendu), déclencheur du `Collapsible` des accès, champ du code (`min-h-11`).
- **Focus :**
  - E6f, E6b : focus initial sur le premier radio ; étape 2 : sur la case à cocher ; fermeture : bouton `⋯` de la ligne.
  - E6g : focus initial sur le **champ code** ; après un code faux : retour sur le champ code (vidé) ; après un mot de passe faux : sur le mot de passe. E6h, E6i, E6j, retrait E17, étape 1 du nouveau code : focus initial sur l'action sûre (« Garder… », « Pas maintenant »).
  - Après une action qui fait disparaître la carte déclencheuse (dont le rejet automatique après 5 codes faux) : `h2` « À traiter » (`tabIndex={-1}`) s'il reste des cartes, sinon titre de la liste des membres ; sur `/profiles` : `h2` de la section ou `h2` « Organisations ».
  - Après acceptation d'une nomination aboutie (`COMPLETED`) : le menu de la page change ; focus sur le `h1` de la page.
  - E15 écran 202 : focus sur le `h1` ; le bloc du code suit dans l'ordre de lecture. Étape 2 du nouveau code : focus sur le `h2` du bloc du code ; fermeture : bouton « Obtenir un nouveau code » de la carte.
- **Code de rattachement :**
  - affichage : groupes visuels « 482 913 » en `aria-hidden`, doublés d'un texte `sr-only` « 4 8 2 9 1 3 » (`spellDigits`), pour une lecture **chiffre par chiffre** (« quatre, huit, deux… » et non « quatre cent quatre-vingt-deux mille ») ;
  - **jamais** dans une région `aria-live`, un `toast`, un `aria-label` de bouton ni un `title` ; les annonces disent seulement « code affiché à l'écran » ;
  - saisie : `label` visible « Code à 6 chiffres », aide et erreur reliées par `aria-describedby` via `errorProps`, `aria-invalid` sur erreur ; pas de six cases séparées (un seul champ : plus simple au lecteur d'écran et au collage) ;
  - contraste : `text-foreground` sur `bg-card`, taille `text-4xl` (lisible à bout de bras pendant un appel).
- **Une seule région `aria-live="polite"`** par page : E6 (existante) reçoit `team.nominate.sent`, `team.confirmInvite.done`, `team.confirmInvite.exhausted`, `team.rejectInvite.done`, `nomination.accept.done`/`review`, `nomination.decline.done`, `nomination.cancel.done` ; `/profiles` reçoit `profiles.awaiting.withdrawn`, `profiles.awaiting.newCodeAnnounce` (région nouvelle, `sr-only`) ; E15 : `invitation.awaiting.announce`. **Jamais** l'indice de téléphone ni le code ; le nom abrégé seulement dans `team.confirmInvite.done` (déjà visible à l'écran).
- `GovernanceBanner` : sans rôle vivant (3.5).
- **Indice de téléphone :** `aria-label` chiffre par chiffre (4.5).
- **Couleur jamais seule :** badges d'état de nomination (icône + texte), « Confirmation requise », « Non confirmée à temps », avertissement `inviter_has_authority` (icône + texte), bannières (titre explicite).
- **Boutons à verbe d'action**, jamais « OK » ; « Annuler » seul n'est utilisé que pour fermer un dialogue de saisie ; les alertes destructives utilisent « Garder… » face à l'action.
- **Zoom 200 % :** cartes sans largeur fixe, boutons empilés sous 768 px, noms tronqués avec `title` ; le code `text-4xl` passe à la ligne entre ses deux groupes si nécessaire.

---

## 18. Réseau faible

- **Aucune image.** Avatars en initiales. Icônes lucide importées une par une : `Crown`, `Hourglass`, `Clock`, `UserCheck`, `ShieldAlert`, `AlertTriangle`, `Info`, `Phone`, `KeyRound`, `X`, `Check` (quelques centaines d'octets chacune).
- **Requêtes par écran :**
  - E6 : `internal/` + `members/` + `primary-admin-nominations/?status=open` + (si `org.manage_members`) `invitations/?status=AWAITING_CONFIRMATION`, en parallèle ; `invitations/?status=PENDING` à l'ouverture de l'onglet (inchangé).
  - E15 connecté : `preview/` seul ; `accept/` à l'appui.
  - `/profiles` : `contexts/` (existant) + `organization-invitations/awaiting/` ; `confirmation-code/` seulement à la demande.
  - E3 : inchangé.
- **Lazy :** tous les dialogues nouveaux.
- **Pas de cache persistant** pour `invitations/*`, `organization-invitations/*` (dont `awaiting/` et `confirmation-code/`), `primary-admin-nominations/*` : `NetworkOnly` dans la configuration PWA (`vite.config.ts`), comme D1 §8. L'indice de téléphone et le code n'existent qu'en mémoire de l'onglet.
- **Aucune action différée** : confirmation, rejet, nomination, acceptation, refus, annulation, retrait, nouveau code. Boutons désactivés hors ligne.
- **Anti-doublon :** boutons désactivés pendant l'appel ; pas de `retry` sur les mutations (en particulier `confirm/` : un nouvel essai automatique pourrait décompter un essai de code, et `confirmation-code/` : il invaliderait le code affiché) ; après un échec réseau sans réponse, texte qui demande de vérifier avant de réessayer (6.4, 8.3, 11.3), et invalidation de la liste à la reconnexion.
- Mot de passe vidé après tout échec de mot de passe ; code vidé après un code faux ; les deux effacés à la fermeture.
- **Appel du confirmateur :** l'étape « appeler la personne » se fait hors application (appel téléphonique normal, sans données). Le dialogue E6g peut rester ouvert pendant l'appel ; s'il est fermé, rien n'est perdu côté serveur (la saisie est à refaire).

---

## 19. Conformité aux règles verrouillées

| Règle | Application dans ces écrans |
|---|---|
| 1. Un compte, plusieurs contextes | « Membre » est un rôle dans une organisation, pas un type de compte. Aucun plafond affiché du nombre d'organisations (Q22) : aucun chiffre, aucun conseil « quittez une organisation pour en créer une ». L'acceptation 202 ne crée aucun contexte ; aucune bascule de profil automatique. |
| 2. Permissions ≠ droits commerciaux | Aucun plan, prix ni paiement dans les dialogues de nomination, de confirmation ou d'invitation. La liste d'accès traduit des capacités de rôle ; `billing.*` est présenté comme un accès, sans promesse commerciale. Aucune requête ne porte de paramètre de plan. |
| 3. Vérification non achetable, précise | `assurance_level` n'est jamais affiché. La revue Connecte+ est décrite comme « l'équipe Connecte+ vérifie **la nomination** », jamais comme un badge ou une « organisation vérifiée ». La confirmation d'un administrateur invité atteste seulement que la personne qui a accepté est celle que le confirmateur a appelée (code de rattachement), pas une identité légale ; aucun badge n'en résulte. La revue de création (« en cours d'examen ») n'est ni publique ni présentée comme une vérification. |
| 4. Aucun score de confiance | Aucune note, étoile ni indicateur. La revue de création est un état binaire montré aux seuls membres. Aucun tri par un indicateur de qualité. Le compteur d'essais de code n'est jamais affiché. |
| 5. Sponsorisé | Sans objet (aucun contenu promotionnel). |
| 10. Données personnelles par finalité | Indice de téléphone (`••47`) affiché **seulement** sur la carte et le dialogue de confirmation, pour un appelant `can_confirm`, pendant l'attente ; annoncé à la personne **avant** qu'elle accepte (texte du contrat) ; jamais dans un toast, une région vivante, une notification, une URL, un stockage, un journal client. Le **code de rattachement** n'est montré qu'à la personne qui a accepté, une fois par génération, jamais relisible ni stocké côté client (principe 8). Noms abrégés seulement. Aucun nom de confirmateur montré à la personne rejetée. |
| 12. Journalisation | Côté serveur (dont chaque code faux, sans le code). Les textes informent que « tous les administrateurs principaux sont informés » ; l'interface n'affiche aucun journal. Mot de passe et code jamais stockés. |
| Q21, Q30 (maker-checker) | Administrateur principal jamais par invitation (option absente, note explicite) ; jamais par « Changer le rôle » (option absente) ; la nomination exige l'acceptation de la cible ; l'ouverture d'un accès Administrateur exige un code détenu par la personne entrée et obtenu par le confirmateur hors du canal du lien ; aucune promotion automatique en état `MISSING` (texte de la bannière). |

---

## 20. Décisions de design à valider

1. **Section « À traiter » en tête de l'écran Équipe**, chargée avec la page (2 requêtes de plus en 3G), plutôt qu'un troisième onglet : les demandes à confirmer et les nominations sont des actions attendues, annoncées par notification vers cet écran.
2. **Pas de sélection de périmètre en V1** : le périmètre est affiché (« Toute l'organisation ») mais aucun contrôle n'est rendu tant qu'une seule valeur existe.
3. **Ordre des rôles à l'invitation du moins au plus privilégié** (Membre, Analyste, Éditeur, Administrateur), sans présélection, Administrateur marqué « Confirmation requise ».
4. **Nomination en deux étapes** (choix puis mot de passe), comme « Changer le rôle », avec le déroulé (acceptation, notifications, revue éventuelle, échéance) affiché avant l'envoi.
5. **« Me remplacer » désactivé** quand un remplacement est déjà en cours dans la liste chargée (anticipation de `nomination_already_open`).
6. **Acceptation de nomination sans mot de passe** (contrat : `confirm: true`), par une alerte « Pas maintenant / Accepter ».
7. **Demandes en attente côté personne invitée sur `/profiles`** (section affichée seulement si non vide), plus l'écran 202 avec « Retirer ma demande ».
8. **Bannières de gouvernance sur toutes les sections de l'organisation**, sans bouton de fermeture ; `MISSING` en style avertissement, pas destructif.
9. **« Dans l'équipe depuis »** remplace « Membre depuis » pour éviter la confusion avec le rôle « Membre ».
10. **Liens d'aide conditionnels** (`HELP_LINKS`) : aucune phrase « contactez le support » sans lien fonctionnel (Q19).
11. **Liste des accès repliée sur mobile au-delà de 6 accès** dans l'aperçu d'invitation.
12. **Aucun historique** des nominations closes ni des demandes rejetées dans l'interface V1.
13. **Code de rattachement sans bouton Copier ni Partager** (révision du 26/11) : le code se dicte au téléphone ; un bouton de copie pousserait à le coller dans la messagerie, le canal même où un lien peut avoir fui.
14. **Un seul champ de saisie pour le code** (pas six cases), `autoComplete="off"` : plus simple au lecteur d'écran, au collage, et sans suggestion des codes SMS du confirmateur.
15. **Nouveau code en deux étapes** (avertissement « l'ancien ne fonctionnera plus », puis affichage non fermable par clic extérieur) depuis E17.
16. **Consigne « appelez la personne au numéro que vous connaissez »** répétée sur la carte (E6), dans le dialogue (E6g) et dans l'avertissement du lien (E6a).

## 21. Questions ouvertes

- **Q-D2-1 (chef de projet, client) : lien d'aide.** Q19 interdit « contactez le support » sans lien fonctionnel ; L1-21 n'est pas livrée. Le texte du contrat §7.6 pour `MISSING` dit « contactez l'aide Connecte+ ». Proposition : retirer cette phrase du texte et afficher le lien seulement quand `HELP_LINKS.governance` existe. Les textes existants (`errors.deny.SECURITY.action`, `org.unavailable.recourse.*`, `orgEdit.nameLocked`…) ont le même défaut : à traiter avec L1-21.
- ~~**Q-D2-2 : QG-2.**~~ **Soldée le 26/11/2026** : code de rattachement retenu (revue S3) ; spec amendée (sections 8, 9.4, 11.3).
- **Q-D2-3 (architecte) : rôle de repli `MEMBER` pour un `TRANSFER`.** Le contrat l'autorise ; un ancien Administrateur principal ramené au rôle Membre perd les statistiques. Le garder dans les choix ? (la spec le garde, en dernier).
- **Q-D2-4 (architecte) : « Proposé(e) par vous ».** L'objet `PrimaryAdminNomination` n'a pas de booléen `is_mine` (contrairement à `Invitation`). Ajout additif souhaitable ; sans lui, l'initiateur lit son propre nom abrégé.
- **Q-D2-5 (utilisateur) : historique.** Faut-il afficher les nominations closes (refusées, expirées, rejetées par Connecte+) aux administrateurs principaux ? Le contrat le permet (`?status=closed`) ; non retenu en V1.
- **Q-D2-6 (architecte) : entitlement d'équipe à la confirmation** (ADR 0009 `CAP-TEAM-MEMBER`, ADR 0010 §15). Le code d'erreur renvoyé à `confirm/` quand la place d'équipe manque n'est pas dans le contrat §7.4.6. La spec le traite par `describeApiError` ; un texte dédié (sans incitation commerciale dans un dialogue de gouvernance) est à écrire quand le code sera figé.
- **Q-D2-7 (architecte) : `governance` dans `contexts/` pour les organisations où l'appelant n'est que `MEMBER` ou `ANALYST`.** La spec affiche les badges à tous les rôles ; à confirmer que le contrat ne restreint pas ce champ.
- **Q-D2-8 (client, QO-6) : libellé « Membre ».** Si le client confirme un rôle distinct, envisager un libellé moins ambigu (« Membre simple ») ; le contrat impose « Membre » à ce jour.
- **Q-D2-9 (chef de projet) : nomination vue par la cible ailleurs qu'en E6.** Un éditeur visé ne voit la carte que sur l'écran Équipe (lien de la notification). Faut-il aussi une alerte sur l'Aperçu de l'organisation (une requête de plus) ?
- **Q-D2-10 (architecte, chef de projet) : texte de la consigne du code.** Le contrat §7.4.5 impose « …de vive voix ou par un canal que vous partagez déjà… ». La spec (`invitation.awaiting.codeInstruction`) dit « de vive voix … ne l'envoyez pas par message », conformément à la consigne « par un appel » et au risque résiduel d'ADR 0010 §12 (code demandé par la messagerie compromise). Aligner le contrat sur ce texte, ou revenir au texte du contrat.
