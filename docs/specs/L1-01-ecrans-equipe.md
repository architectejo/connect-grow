# L1-01-D1 : Spécification d'écran, équipe, invitations et acceptation

> **Amendée par `L1-01-ecrans-gouvernance.md` (ADR 0010, 25/11/2026)** : §2.5, §2.6, §2.7 (E6c supprimé), §3.3, §4.4.2, §4.4.3, §4.5 (`organization_limit_reached`), §6 (textes « propriétaire ») et §10 décision 4 sont remplacés ; le reste reste en vigueur.


- **Date :** 09/11/2026 ; **auteur :** designer-ux ; **destinataire :** dev-frontend (F1, F2, F3)
- **Sources :** CDC v1.2 §3.1 ; `docs/adr/0008-equipe-organisation-invitations.md` ; `docs/specs/L1-01-contrat-api.md` (contrat figé : les écrans ne montrent que ce qu'il expose) ; `docs/specs/L1-01-organisations.md` (stories b à h, k) ; `docs/specs/L0-09-ecrans-contextes.md` (§2, §7.7, §16).
- **Périmètre :** E6 Équipe (liste, rôle, retrait, transfert), invitations (création, lien, liste, révocation), page d'acceptation, bloc « blocages de suppression » des Paramètres. **Hors périmètre :** revendication, KYB, page publique, plans.
- **Aucune dépendance graphique nouvelle.** Tout vient de shadcn/ui, lucide-react et Tailwind déjà installés.

## 0. Écrans livrés

| ID | Écran | Route | Fichier | Tâche |
|---|---|---|---|---|
| E6 | Équipe (remplace la version réduite de L0-09) | `/organizations/:id/team` (existante) | `pages/OrganizationTeam.tsx` | F1, F2 (onglet Invitations) |
| E6a | Dialogue « Inviter une personne » (2 étapes : choix, lien) | dialogue de E6 | `components/team/InviteDialog.tsx` | F2 |
| E6b | Dialogue « Changer le rôle » (1 ou 2 étapes) | dialogue de E6 | `components/team/ChangeRoleDialog.tsx` | F1 |
| E6c | Dialogue « Transférer la propriété » | dialogue de E6 | `components/team/TransferOwnershipDialog.tsx` | F1 |
| E6d | Alerte « Retirer un membre » | dialogue de E6 | `components/team/RemoveMemberDialog.tsx` | F1 |
| E6e | Alerte « Annuler une invitation » | dialogue de E6 | `components/team/RevokeInvitationDialog.tsx` | F2 |
| E15 | Page d'acceptation | `/organization-invitation` (**nouvelle**, publique, hors `RequireAuth`) | `pages/OrganizationInvitation.tsx` | F2 |
| E16 | Bloc « Équipes et suppression du compte » | section de `/settings` | `components/settings/AccountDeletionBlockers.tsx` | F3 |

Les dialogues E6a à E6e sont chargés à l'ouverture (`React.lazy` + `Suspense`), pas avec la page. `OrganizationInvitation` est une route `lazy` comme les autres pages de `App.tsx`.

---

## 1. Révision de L0-09 §7.7 (point 5 de la demande)

Le formulaire « Ajout par numéro de téléphone ou e-mail d'un compte existant » est **abandonné** (décision C1, ADR 0008 : aucune recherche de compte, ce serait un oracle d'existence ; l'e-mail n'est pas vérifié).

**Ce qui le remplace :** le bouton **« Inviter une personne »** (propriétaire et administrateur) qui ouvre E6a. Il n'y a **aucun champ téléphone, e-mail ni identifiant**. L'utilisateur choisit un rôle (Éditeur ou Analyste), saisit une étiquette facultative, et reçoit un **lien à usage unique** qu'il transmet lui-même (WhatsApp, SMS personnel). Le serveur n'envoie rien (hypothèse Q-L1-2).

Autres corrections de L0-09 §7.7 (cible L1-01) :

| L0-09 | Remplacé par | Raison |
|---|---|---|
| Bouton « Ajouter un membre » (`team.add`) | « Inviter une personne » (`team.invite.open`) | C1 |
| Menu « Retirer » sur une ligne propriétaire | Absent ; texte « Rétrogradez d'abord ce propriétaire. » | `409 owner_must_be_demoted` (ADR 0008 §5.2) |
| Actions désactivées sur la ligne du dernier propriétaire (`aria-describedby`) | Aucun menu sur sa propre ligne ; badge d'information ; refus serveur affiché (voir 2.6) | Le seul acteur capable de viser ce propriétaire est lui-même (ligne sans menu) ; `last_effective_owner` dépend des offres actives, que l'écran ne connaît pas |
| Badge « Dernier propriétaire » | « Seul propriétaire actif » (`team.lastOwner`) | `is_last_effective_owner` désigne le seul propriétaire **effectif**, pas le seul propriétaire |
| Ligne propre : menu « Quitter » | Pas de menu sur sa propre ligne ; la carte « Quitter l'organisation » (existante) reste en bas de page | Un seul chemin de sortie, pas deux |
| Tableau « Que peut faire chaque rôle ? » | Conservé, déplacé en bas, replié par défaut (`Collapsible`) | Moins de défilement en 3G |
| `Alert` `team.notAvailable` | Supprimée | Fonction livrée |

Réponse à la question **Q-F6** de L0-09 : les membres sont affichés par `display_name` abrégé (« Marie K. »), sans photo, téléphone, e-mail ni nom complet.

---

## 2. E6 : Équipe `/organizations/:id/team`

### 2.1 Objectif et utilisateur

Voir qui fait partie de l'organisation et avec quel rôle ; pour les propriétaires et administrateurs, faire évoluer l'équipe. **Action principale :** « Inviter une personne » (propriétaire, administrateur) ; pour éditeur et analyste, aucune action principale (lecture seule).

Capacités lues dans `org.capabilities` (déjà fournies par `OrganizationInternal`) et `org.my_role` :
- `org.manage_members` : bouton Inviter, onglet Invitations, menu « Retirer », badge `is_last_effective_owner` (le serveur renvoie `null` sinon).
- `org.manage_roles` : menu « Changer le rôle ». « Transférer la propriété » : en plus `my_role === "OWNER"`.

### 2.2 Parcours

1. Entrée : menu de l'espace organisation (`OrganizationPage section="team"`), notification « Vous avez rejoint… » (lien `/organizations/<id>/team`, ADR 0008 §6), notification d'invitation acceptée ou refusée (même lien).
2. Liste des membres (`GET members/`). Éditeur et analyste s'arrêtent là (plus la carte « Quitter »).
3. Propriétaire ou administrateur : actions par ligne (2.5), « Inviter une personne » (section 3), onglet « Invitations » (section 3.4).
4. Sortie : retour à l'espace de l'organisation ; après un transfert, l'utilisateur reste sur l'écran avec son nouveau rôle.

Cas d'erreur : voir 2.6 et 2.7.

### 2.3 Structure

**Mobile (< 768 px), de haut en bas** (`AccountShell` + sous-menu de l'organisation, existant) :
1. `PageHeader` : titre « Équipe ». Pour `org.manage_members` : `Button` pleine largeur « Inviter une personne » (icône `UserPlus`, `min-h-11`).
2. Zone `aria-live="polite"` visuellement cachée (`sr-only`) annonçant le résultat des actions.
3. Si `org.manage_members` : `Tabs` à deux onglets, « Membres » et « Invitations ». Sinon : pas d'onglets, la liste seule.
4. Onglet Membres : cartes empilées (`Card` allégée, `rounded-2xl border bg-card p-4`), une par membre :
   ```
   ┌───────────────────────────────────┐
   │ (MK) Marie K.  (vous)        [⋯]  │  UserAvatar initiales, nom, bouton menu 44 px
   │ [RoleBadge]  [Seul propriétaire…] │
   │ Membre depuis novembre 2026       │
   └───────────────────────────────────┘
   ```
5. Bouton « Voir plus de membres » (si `next` non nul ; pagination par `?page=`, 20 par page, `useInfiniteQuery`).
6. Carte « Quitter l'organisation » (`LeaveOrganizationCard`, existante).
7. `Collapsible` « Que peut faire chaque rôle ? » (contenu L0-09 §7.7 point 4, existant).

**Desktop (>= 768 px) :** colonne `max-w-4xl`. Mêmes blocs ; le bouton Inviter est aligné à droite de l'en-tête ; la liste des membres est un `Table` (colonnes : Membre, Rôle, Membre depuis, Actions) avec `caption` `sr-only` et `scope="col"`. Les invitations sont un `Table` (Rôle, Étiquette, Créée par, Expire le, Actions).

### 2.4 Composants

**Réutilisés (noms exacts) :** `OrganizationPage`, `PageHeader`, `RoleBadge`, `UserAvatar` (sans `src` : initiales, aucune image), `Badge`, `Card`, `Tabs`, `Table`, `Button`, `DropdownMenu` / `DropdownMenuItem` / `DropdownMenuSeparator`, `AlertDialog`, `Alert`, `Checkbox`, `Label`, `Input`, `RadioGroup` (`ui/radio-group.tsx`), `Collapsible`, `Skeleton`, `ErrorState`, `EmptyState`, `AccessDenied`, `OfflineBanner`, `ResponsiveDialog` (`components/common/ResponsiveDialog.tsx`), `Field`, `errorProps`, `fieldInputClass`, `PasswordInput` (`components/auth/FormFields.tsx`), `FormAlert`, `LeaveOrganizationCard`, `useOnlineStatus`, `useIsMobile`, `describeApiError`, `getApiErrorCode`, `parseApiErrors`, `formatMonthYear`, `sonner`.

**Modification d'un composant existant :** `ResponsiveDialog` gagne une prop facultative `dismissible?: boolean` (défaut `true`). Si `false` : le clic extérieur et le glissé vers le bas ne ferment pas (`onInteractOutside` préventif pour `Dialog`, `dismissible={false}` pour `Drawer`) ; Échap et le bouton explicite ferment. Utilisée seulement par l'étape « lien » de E6a (3.3).

**Nouveaux composants (justifiés) :**

| Composant | Justification | Props |
|---|---|---|
| `MemberRow` (carte mobile et ligne `Table`) | Aucun composant de liste de membres n'existe ; porte le menu selon rôle de l'acteur et de la cible | `member`, `actor: {role, capabilities}`, `onAction(type, member)` |
| `MemberActionsMenu` | Isole la matrice 2.5 pour qu'elle soit testable seule (Vitest) | `actorRole`, `capabilities`, `target` |
| `InvitationRow` | Idem pour les invitations | `invitation`, `canRevoke`, `onRevoke` |
| `CopyLinkField` | Champ en lecture seule + boutons Copier / Partager, avec repli sans `navigator.clipboard` | `value`, `onCopied` |
| `InviteDialog`, `ChangeRoleDialog`, `TransferOwnershipDialog`, `RemoveMemberDialog`, `RevokeInvitationDialog` | Un dialogue par action sensible ; états et erreurs propres | voir sections |
| `SensitiveConfirmFields` | Case « Je confirme » + `PasswordInput`, partagé par E6b et E6c (même exigence serveur : `confirm` et `password`) | `idPrefix`, `error`, `disabled`, `value`, `onChange` |
| Hooks `use-organization-team.ts` | `useMembers(orgId)` (infinite), `useChangeMemberRole`, `useRemoveMember`, `useTransferOwnership`, `useInvitations(orgId)`, `useCreateInvitation`, `useRevokeInvitation`, `useInvitationPreview`, `useAcceptInvitation`, `useDeclineInvitation`, `useAccountDeletionBlockers` | |

### 2.5 Menu d'actions par ligne (`MemberActionsMenu`)

Le **serveur reste l'arbitre** : chaque refus (`DENY_PERMISSION`…) est géré (2.6). Le menu n'affiche que ce que le rôle de l'acteur permet, pour ne pas proposer d'action vouée au refus.

| Acteur \ cible | OWNER | ADMIN | EDITOR | ANALYST | Soi-même |
|---|---|---|---|---|---|
| **OWNER** | Changer le rôle, Transférer la propriété | Changer le rôle, Transférer la propriété, Retirer | idem ADMIN | idem ADMIN | aucun menu |
| **ADMIN** | aucun menu ; texte « Réservé aux propriétaires » | Changer le rôle (ADMIN, EDITOR, ANALYST), Retirer | idem | idem | aucun menu |
| **EDITOR, ANALYST** | aucun menu | aucun menu | aucun menu | aucun menu | aucun menu |

- Cible OWNER pour un acteur OWNER : pas de « Retirer » ; sous le badge de rôle, texte discret « Pour retirer ce propriétaire, rétrogradez-le d'abord. » (`team.ownerRemoveHint`).
- « Retirer » est séparé des autres entrées par `DropdownMenuSeparator` et stylé destructif (icône `UserMinus` + texte, jamais la couleur seule).
- Chaque `DropdownMenuItem` : `min-h-11`. Le bouton déclencheur : `aria-label` « Actions pour {{name}} », `min-h-11 min-w-11`, `aria-haspopup="menu"`.
- Les dialogues sont montés **hors** du `DropdownMenuContent` (état au niveau de la page) pour que le focus soit rendu au bouton `⋯` à la fermeture.
- Ligne de l'acteur : `(vous)` après le nom (`is_self`). Si `is_last_effective_owner === true` sur sa propre ligne, ligne d'aide : « Si vous quittez l'organisation, elle n'aura plus de propriétaire disponible. Nommez d'abord un autre propriétaire. » (`team.lastOwnerSelfHint`).
- Badge `team.lastOwner` affiché seulement si `is_last_effective_owner === true` (jamais si `null` ou `false`). Il a une icône (`ShieldAlert`) et un texte ; `title` et `aria-describedby` vers : « Les autres propriétaires, s'il y en a, ne peuvent pas agir actuellement (compte inactif ou restreint). » (`team.lastOwnerHelp`). Ce texte ne dit rien d'une sanction et ne désigne personne.

### 2.6 E6b : Changer le rôle (`ChangeRoleDialog`)

`ResponsiveDialog` (feuille basse sur mobile). Titre : « Changer le rôle de {{name}} ».

**Étape 1 (choix).** `RadioGroup` des rôles autorisés, chacun avec sa description (`role.*_desc`). Propriétaire : OWNER, ADMIN, EDITOR, ANALYST. Administrateur : ADMIN, EDITOR, ANALYST (jamais OWNER). Rôle actuel présélectionné et marqué « (rôle actuel) ». Le bouton « Enregistrer le rôle » est désactivé tant que le rôle est inchangé. Focus initial : le radio présélectionné.

**Étape 2 (confirmation renforcée)** : affichée **seulement** si le nouveau rôle est `OWNER` **ou** si le rôle actuel de la cible est `OWNER` (contrat 1.2). Même dialogue, le contenu est remplacé (pas de nouvelle fenêtre) ; bouton « Retour » (étape 1) :
- Promotion : « {{name}} deviendra propriétaire. Cette personne pourra gérer toute l'équipe, rétrograder les autres propriétaires et archiver l'organisation. Vous resterez propriétaire. »
- Rétrogradation : « {{name}} ne sera plus propriétaire. Cette personne perdra l'archivage de l'organisation et la gestion des propriétaires. »
- `SensitiveConfirmFields` : `Checkbox` « Je confirme ce changement » et `PasswordInput` (étiquette « Votre mot de passe », `autoComplete="current-password"`, `fieldInputClass`), texte d'aide « Nous vous le demandons pour protéger l'organisation. Il n'est pas conservé. »
- Bouton « Confirmer le changement », désactivé tant que la case n'est pas cochée et le mot de passe vide. Corps envoyé : `{role, confirm: true, password}` ; hors étape 2 : `{role}` seul (jamais de mot de passe inutile).

**Résultat.** Succès (`200` + `Member`) : fermeture, mise à jour de la ligne, `toast` « Le rôle de {{name}} est maintenant {{role}}. », annonce `aria-live`, focus rendu au bouton `⋯`. Même rôle (réponse sans changement) : fermeture sans toast.

**Erreurs** (affichées dans le dialogue par `FormAlert` `role="alert"`, valeurs conservées) :

| Réponse | Affichage |
|---|---|
| `403 reauthentication_failed` | Erreur sous le champ mot de passe : « Mot de passe incorrect. » ; champ vidé, focus sur le champ. Le dialogue reste ouvert. |
| `429` ou échec répété du limiteur | « Trop de tentatives. Réessayez dans quelques minutes. » (texte existant de `rateLimitMessage` si disponible) ; bouton désactivé |
| `409 last_owner` | « Une organisation doit toujours avoir au moins un propriétaire. » (`errors.code.last_owner_demote`, existant) |
| `409 last_effective_owner` | « Cette organisation a des offres actives : elle doit garder au moins un propriétaire disponible. Nommez d'abord un autre propriétaire. » |
| `403 DENY_PERMISSION` | Texte existant `errors.deny.PERMISSION.org` ; fermeture du dialogue et rechargement de la liste et de `my_role` |
| `404 member_not_found` | Fermeture, `toast` « Cette personne ne fait plus partie de l'équipe. », rechargement de la liste |
| `400 user_unavailable` | « Ce changement n'est pas possible pour ce compte pour le moment. » (neutre) |
| `400 {"role": [...]}` | Message de champ du serveur sous la liste de rôles |
| `403 DENY_RELATION` | Flux existant de perte de profil (`useActiveContext`, `ContextLostAlert`) : l'acteur a été retiré entre-temps |
| `403 DENY_SECURITY`, `DENY_OBJECT_STATE` | `describeApiError` existant |
| Réseau coupé | « Connexion perdue. Réessayez quand vous êtes reconnecté. » ; rien n'est mis en file |

### 2.7 E6c : Transférer la propriété (`TransferOwnershipDialog`)

Entrée de menu « Transférer la propriété à {{name}} » (acteur OWNER, cible non soi-même). `ResponsiveDialog`, titre « Transférer la propriété à {{name}} ».

Contenu :
1. Texte : « {{name}} deviendra propriétaire. Vous ne serez plus propriétaire et prendrez le rôle choisi ci-dessous. Vous pourrez continuer à agir dans l'organisation avec ce rôle. »
2. `RadioGroup` « Votre rôle après le transfert » : Administrateur (présélectionné), Éditeur, Analyste (`my_new_role`). Jamais Propriétaire.
3. Texte : « Pour garder le rôle de propriétaire tout en nommant {{name}}, utilisez plutôt « Changer le rôle » et choisissez Propriétaire. » (`team.transferAlt`).
4. `SensitiveConfirmFields` (case « Je confirme le transfert de propriété », mot de passe).
5. Boutons : « Annuler » (focus initial) et « Transférer la propriété » (destructif ; désactivé jusqu'à case cochée + mot de passe).

Corps : `{membership_id, my_new_role, confirm: true, password}`. Succès (`200 {new_owner, me}`) : fermeture, `toast` « La propriété a été transférée à {{name}}. », invalidation de `members`, de l'organisation (nouveau `my_role`, capacités) et de `contexts` (le rôle mémorisé du profil actif est mis à jour) ; annonce `aria-live`.

Erreurs : `reauthentication_failed`, `429`, `DENY_PERMISSION`, `404 member_not_found`, `400 user_unavailable`, réseau : comme 2.6. `400 invalid_transfer` (inatteignable par l'interface : pas d'entrée sur sa propre ligne) : message générique « Ce transfert n'est pas possible. ». `confirmation_required` et `password_required` : inatteignables (boutons désactivés) ; si reçus, message générique d'erreur.

### 2.8 E6d : Retirer un membre (`RemoveMemberDialog`)

`AlertDialog`. Titre : « Retirer {{name}} de l'équipe ? ». Texte : « {{name}} perdra immédiatement l'accès à l'organisation. Son compte personnel et ses offres personnelles ne changent pas. Les offres, avis et messages de l'organisation restent à l'organisation. Les invitations qu'elle avait créées et qui ne sont pas encore utilisées sont annulées. » Boutons : « Annuler » (focus initial) et « Retirer » (destructif). Pas de mot de passe (le contrat n'en exige pas pour ce cas).

Succès (`204`) : fermeture, ligne retirée, `toast` « {{name}} a été retiré de l'équipe. », focus déplacé sur le titre de la liste (`tabIndex={-1}`), annonce `aria-live`. Invalider aussi la liste des invitations.

Erreurs : `404 member_not_found` (déjà retiré : même issue qu'un succès avec `toast.info` « Cette personne ne fait plus partie de l'équipe. ») ; `403 DENY_PERMISSION` ; `409 owner_must_be_demoted` : « Cette personne est propriétaire. Changez d'abord son rôle, puis retirez-la. » (inatteignable par l'interface, conservé par prudence) ; `409 last_owner`, `last_effective_owner` : textes de 2.6 ; `400 use_leave` : inatteignable ; `429`, réseau : comme 2.6.

### 2.9 États de E6

| État | Rendu |
|---|---|
| Chargement | `Skeleton` : 3 cartes (mobile) ou 3 lignes (desktop) de hauteur fixe, pour éviter les sauts de mise en page ; le bouton Inviter est déjà actif (il ne dépend pas de la liste) |
| Vide | Sans objet (le compte connecté est membre). Par prudence : `EmptyState` « Aucun membre à afficher. » |
| Erreur de liste | `ErrorState` (« Impossible de charger l'équipe. ») + bouton « Réessayer » ; les autres blocs de la page restent affichés |
| Hors ligne | `OfflineBanner` ; liste déjà chargée conservée en mémoire ; tous les boutons d'action désactivés avec le texte `common.offlineAction` associé par `aria-describedby` ; aucune action mise en file |
| Succès d'une action | `toast` + annonce `aria-live` (2.6 à 2.8) |
| Permission refusée | `DENY_RELATION` : `AccessDenied` (déjà géré par `OrganizationPage`). `DENY_SECURITY` (suspendue, compte restreint) et `DENY_OBJECT_STATE` (archivée) : `OrganizationUnavailableView` existante. Éditeur et analyste : aucune action visible, ce n'est pas un état d'erreur |
| Plus de page | « Voir plus de membres » : bouton avec indicateur de chargement ; en cas d'échec, message sous le bouton, la liste déjà chargée reste |

### 2.10 Données et source

| Donnée affichée | Champ API |
|---|---|
| Nom | `Member.display_name` |
| « (vous) » | `Member.is_self` |
| Rôle | `Member.role` |
| Membre depuis | `Member.joined_at` (affiché au mois et à l'année, `formatMonthYear`) |
| Badge « Seul propriétaire actif » | `Member.is_last_effective_owner === true` |
| Actions disponibles | `OrganizationInternal.my_role`, `OrganizationInternal.capabilities` |
| Cible d'une action | `Member.membership_id` (identifiant interne, jamais affiché) |

Aucun autre champ n'est lu. Le téléphone, l'e-mail, le nom complet, la photo et l'identifiant de compte n'existent pas dans la réponse et ne sont ni demandés ni affichés.

---

## 3. Invitations (E6a, onglet Invitations, E6e)

### 3.1 Objectif et utilisateur

Donner accès à une personne **sans** la chercher dans la base de comptes : le propriétaire ou l'administrateur crée un lien à usage unique et le transmet lui-même. **Action principale du dialogue :** « Créer le lien » puis « Copier le lien ».

### 3.2 Parcours de création

1. Appui sur « Inviter une personne » (E6) : ouverture de E6a (étape 1), focus sur le premier choix de rôle.
2. Choix du rôle (Éditeur ou Analyste), étiquette facultative, « Créer le lien ».
3. `POST invitations/` : le dialogue passe à l'étape 2 (le jeton est en mémoire locale du dialogue uniquement).
4. L'utilisateur copie ou partage le lien, puis ferme (« Terminer »).
5. L'onglet « Invitations » est sélectionné et rechargé ; la nouvelle ligne y apparaît (sans lien : le lien n'est plus relisible).

### 3.3 E6a : structure du dialogue

**Étape 1 : « Inviter une personne »** (`ResponsiveDialog`, `dismissible` par défaut).
1. Texte d'introduction : « Vous obtenez un lien à envoyer vous-même à la personne (par exemple sur WhatsApp). Elle l'ouvre, se connecte et accepte. Le lien ne fonctionne qu'une seule fois. »
2. `RadioGroup` « Rôle » : Éditeur (« Publie et modifie les offres, répond aux avis et aux messages. »), Analyste (« Consulte les statistiques et les offres. Ne peut rien modifier. »). Les descriptions viennent de `role.EDITOR_desc` et `role.ANALYST_desc`. Aucun choix présélectionné (le bouton reste désactivé jusqu'au choix : éviter de donner un rôle par inadvertance).
3. `Alert` d'information : « Pour donner le rôle Administrateur ou Propriétaire, invitez d'abord la personne, puis changez son rôle une fois qu'elle a rejoint l'équipe. » (`team.invite.rolesNote`).
4. `Field` « Étiquette (facultatif) » : `Input` `maxLength={60}`, compteur « {{n}}/60 » en `aria-live` désactivé (pas d'annonce par frappe), aide : « Un repère pour retrouver cette invitation, par exemple « Jean, comptable ». Visible par les propriétaires et administrateurs de l'organisation, supprimée dès que l'invitation est utilisée ou annulée. Ne mettez ni téléphone ni adresse. »
5. Texte de validité : « Le lien est valable {{days}} jours. » seulement si `invitation_ttl_days` est lu de `GET organizations/limits/` ; sinon omis. Jamais de valeur codée en dur.
6. Boutons : « Annuler » et « Créer le lien » (désactivé sans rôle ; spinner pendant l'appel).

**Étape 2 : « Lien d'invitation »** (`dismissible={false}`, titre « Votre lien d'invitation »).
1. `Alert` d'avertissement (icône `AlertTriangle`) : « Ce lien ne sera plus affichable après la fermeture de cette fenêtre. Quiconque le possède peut rejoindre l'équipe avec le rôle {{role}} : envoyez-le seulement à la personne concernée. » (`role="alert"` à l'apparition de l'étape).
2. `CopyLinkField` : `Input` `readOnly`, `aria-label` « Lien d'invitation », sélection complète au focus, `inputMode="none"`, texte tronqué ; en dessous :
   - Bouton principal « Copier le lien » (`min-h-12`, pleine largeur sur mobile). Succès : le libellé devient « Lien copié » 3 s (icône `Check`), annonce `aria-live` « Lien copié », sans répéter le lien.
   - Bouton secondaire « Partager » (icône `Share2`) **affiché seulement si `navigator.share` existe** : `navigator.share({ title, text, url })` avec le texte `team.invite.shareText`. Une annulation par l'utilisateur (`AbortError`) n'est pas une erreur.
   - Si `navigator.clipboard` est absent ou refuse (contexte non sécurisé, WebView) : repli `document.execCommand("copy")` sur le champ sélectionné ; si cela échoue aussi : message « Copie impossible. Appuyez longuement sur le lien pour le copier. »
3. Texte : « Rôle : {{role}}. Expire le {{date}}. » (`expires_at` de la réponse ; date complète, ex. « 16 novembre 2026 »).
4. Bouton « Terminer ». Si ni Copier ni Partager n'a été utilisé, un texte sous le bouton rappelle : « Vous n'avez pas encore copié le lien. » Ce texte n'empêche pas de fermer.
5. À la fermeture : le jeton est supprimé de l'état (`mutation.reset()`, variable remise à `undefined`).

**Construction du lien (exacte) :** `` `${window.location.origin}/organization-invitation#token=${link_token}` ``. Le jeton est dans le **fragment** : il n'est jamais envoyé au serveur dans une URL.

**Règles de non-fuite du jeton (à tester par Vitest et relues par l'auditeur) :**
- ne jamais le mettre dans `localStorage`, `sessionStorage`, une clé React Query, le cache persistant, un `toast`, une région `aria-live`, `console.*`, un message d'erreur, une URL de navigation ou un attribut `data-*` ;
- la mutation de création s'exécute avec `gcTime: 0` ; le résultat n'est pas dans le cache de requêtes ;
- l'étiquette n'est jamais journalisée côté client non plus.

**Erreurs de création :**

| Réponse | Affichage (`FormAlert`, étape 1, valeurs conservées) |
|---|---|
| `409 invitation_limit_reached` | « Le nombre maximal d'invitations en attente est atteint. Annulez une invitation inutilisée pour en créer une nouvelle. » |
| `429` | « Vous avez créé beaucoup d'invitations. Réessayez plus tard. » + délai `Retry-After` si lisible |
| `400 {"label": [...]}` | Message du serveur sous le champ étiquette (« Cette étiquette est trop longue. » si le serveur renvoie un message générique, 60 caractères au plus) |
| `400 {"role": [...]}`, `400 invitation_role_not_allowed` | « Ce rôle ne peut pas être donné par invitation. » (inatteignable par l'interface) |
| `403 DENY_PERMISSION` | `errors.deny.PERMISSION.org`, fermeture, rechargement de `my_role` |
| `403 DENY_SECURITY`, `DENY_OBJECT_STATE`, `DENY_RELATION` | Flux existant (`describeApiError`, `OrganizationUnavailableView`, perte de profil) |
| Réseau coupé | « Connexion perdue. Réessayez quand vous êtes reconnecté. » ; **le bouton ne relance pas automatiquement** (éviter deux invitations) |

Pour éviter les doubles invitations sur réseau lent : le bouton est désactivé pendant l'appel ; après un échec réseau **sans réponse**, l'invitation a peut-être été créée : le message ajoute « Vérifiez l'onglet Invitations avant de réessayer. »

### 3.4 Onglet « Invitations » (propriétaire et administrateur)

Requête déclenchée **à l'ouverture de l'onglet** (pas au chargement de la page : une requête de moins en 3G). `GET invitations/?status=PENDING`, pagination « Voir plus ».

Ligne (carte mobile, ligne de `Table` desktop) :
- `RoleBadge` ;
- étiquette en gras, ou « Sans étiquette » en texte atténué (`invitation.label` vide) ;
- « Créée par {{name}} » ; « Créée par vous » si `is_mine` ;
- « Expire le {{date}} » (`expires_at`) ;
- bouton « Annuler l'invitation » (icône `X`, `min-h-11`) → E6e.

Une ligne dont `status !== "PENDING"` ou dont `expires_at` est dépassée s'affiche avec le `Badge` « Expirée » et **sans** bouton d'annulation (le serveur présente `EXPIRED` en lecture ; une annulation répondrait `409 invitation_not_pending`).

Texte d'en-tête de l'onglet : « Ces liens n'ont pas encore été utilisés. Un lien ne peut pas être affiché une seconde fois : pour en obtenir un nouveau, annulez l'invitation et créez-en une autre. » (`team.invitations.intro`).

**États :** chargement `Skeleton` ×2 ; vide `EmptyState` « Aucune invitation en attente. » avec action « Inviter une personne » ; erreur `ErrorState` + « Réessayer » ; hors ligne : liste en mémoire conservée, boutons désactivés, `common.offlineAction`.

### 3.5 E6e : annuler une invitation

`AlertDialog`. Titre : « Annuler cette invitation ? ». Texte : « Le lien ne fonctionnera plus. Si la personne l'a déjà reçu, elle ne pourra pas rejoindre l'équipe avec ce lien. » Boutons : « Garder l'invitation » (focus initial) et « Annuler l'invitation » (destructif). Les libellés évitent « Annuler » seul, ambigu entre fermer le dialogue et révoquer.

Succès (`204`) : ligne retirée, `toast` « Invitation annulée. », focus sur le titre de l'onglet. Erreurs : `409 invitation_not_pending` ou `404 invitation_not_found` : `toast.info` « Cette invitation n'est plus en attente. » et rechargement ; `403 DENY_PERMISSION` ; `429` ; réseau : comme 2.6.

### 3.6 Données

| Donnée | Champ API |
|---|---|
| Rôle, étiquette, créateur, expiration, « Créée par vous » | `Invitation.role`, `label`, `created_by_display_name`, `expires_at`, `is_mine` |
| Statut | `Invitation.status` (jamais d'autre état que `PENDING` ou `EXPIRED` dans l'écran) |
| Lien (étape 2 seulement) | `link_token` de la réponse `201`, une seule fois |
| Durée de validité avant création | `invitation_ttl_days` de `GET organizations/limits/` (additif ; omis s'il manque) |

---

## 4. E15 : Page d'acceptation `/organization-invitation`

### 4.1 Objectif et utilisateur

Une personne a reçu un lien d'une organisation. Elle voit à quoi on l'invite (si elle est connectée) et accepte ou refuse. **Action principale :** « Rejoindre l'organisation » (connecté) ou « Se connecter » (non connecté).

### 4.2 Gestion du jeton (avant tout rendu)

Au montage, avant tout appel :
1. Lire `window.location.hash` ; extraire `token` (`new URLSearchParams(hash.slice(1)).get("token")`).
2. Si présent **et** conforme à `^[A-Za-z0-9_-]{1,128}$` : le ranger dans `sessionStorage` sous la clé `connecte.orgInvitation.v1`, puis **effacer la barre d'adresse** : `history.replaceState(null, "", "/organization-invitation")`.
3. Sinon (fragment absent ou non conforme) : lire `sessionStorage`.
4. Aucun jeton trouvé : afficher l'état « Lien incomplet » (4.6) sans appel réseau.
5. Le jeton est toujours envoyé dans le **corps** d'un `POST`, jamais dans une URL, un en-tête ni une clé de requête.
6. Le jeton n'est supprimé de `sessionStorage` que sur : acceptation réussie, refus réussi, `404 invitation_invalid`, `409 already_member`, déconnexion volontaire. Il est conservé sur : réseau coupé, `429`, `403 phone_verification_required`, `409 organization_limit_reached`. **Révision L1-01-F2 (audit S2)** : il est aussi effacé à toute fin de session (déconnexion, `401` de session expirée, déconnexion depuis un autre onglet), au-delà de 60 minutes dans l'onglet, et s'il est lu par un autre compte que celui qui a obtenu le premier aperçu ; la page affiche alors « Lien incomplet ».

Un lien partagé dans WhatsApp ne transmet pas le fragment aux serveurs (aperçu de lien compris).

### 4.3 Parcours

**Visiteur non connecté** (`useAuth().isAuthenticated === false`) :
1. Ouverture du lien : jeton rangé, URL nettoyée.
2. Écran d'invitation **générique** (4.4.1), **sans appel API** : il ne révèle ni le nom de l'organisation, ni le rôle, ni la validité du lien.
3. « Se connecter » → `/login?next=/organization-invitation` ; « Créer un compte » → `/register?next=/organization-invitation`. Le jeton reste dans `sessionStorage` pendant la connexion et l'inscription (OTP compris).
4. Retour automatique sur `/organization-invitation` : le jeton est lu dans `sessionStorage`, l'aperçu s'affiche (parcours connecté).

**Visiteur connecté :**
1. `POST organization-invitations/preview/` (corps `{token}`).
2. Aperçu (4.4.2) : « Rejoindre l'organisation » ou « Refuser ».
3. Acceptation → écran de succès (4.4.3). Refus → écran de refus.

### 4.4 Structure (mobile et desktop identiques ; colonne centrée `max-w-md`, `AppShell` sans sous-menu, une carte)

#### 4.4.1 Non connecté

1. Icône `MailOpen` (décorative), `h1` « Vous avez reçu une invitation ».
2. Texte : « Quelqu'un vous invite à rejoindre une équipe sur Connecte+. Connectez-vous ou créez un compte pour voir de quelle organisation il s'agit. »
3. Bouton principal « Se connecter » (pleine largeur, `min-h-12`) ; bouton secondaire « Créer un compte ».
4. Texte discret : « N'acceptez que les invitations de personnes que vous connaissez. »

Aucun appel API, aucun nom d'organisation, aucun rôle, aucune date.

#### 4.4.2 Connecté : aperçu

États : chargement `Skeleton` (carte) ; succès :
1. `h1` « Invitation à rejoindre une organisation ».
2. Bloc identité : `UserAvatar shape="square"` en initiales (`name = organization_name`, pas d'image), nom de l'organisation (`h2`, tronqué avec `title` et `aria-label` complet), `SellerTypeBadge contextType="ORGANIZATION" orgType={org_type}`.
3. Liste de définition : « Invitation de » `invited_by_display_name` ; « Rôle proposé » `RoleBadge` + `role.*_desc` ; « Valable jusqu'au » date de `expires_at`.
4. Texte : « En acceptant, vous agirez au nom de cette organisation avec ce rôle. Votre profil personnel et vos offres personnelles ne changent pas. Vous pourrez quitter l'organisation à tout moment. »
5. Bouton principal « Rejoindre l'organisation » ; bouton secondaire « Refuser l'invitation » (variante `outline`, ouvre un `AlertDialog` : titre « Refuser cette invitation ? », texte « Le lien ne pourra plus être utilisé. Vous pourrez demander une nouvelle invitation. », boutons « Garder l'invitation » (focus initial) et « Refuser »).
6. Aucune mention de vérification, de note, de plan ni de prix (règles 2, 3, 4).

#### 4.4.3 Succès de l'acceptation

`h1` « Vous avez rejoint {{name}} » (le nom vient de la réponse `accept`) ; texte « Vous avez le rôle {{role}}. » ; bouton principal « Ouvrir l'organisation » : sélectionne le profil `ORGANIZATION:<organization_id>` (après invalidation de `contexts`, ce profil apparaît à l'appel suivant) puis navigue vers `/organizations/<organization_id>` ; lien secondaire « Rester sur mon profil » → `/dashboard`. Le profil actif **ne change jamais sans cet appui** (l'utilisateur sait sous quelle identité il agit). Focus sur le `h1` ; annonce `aria-live` ; jeton supprimé de `sessionStorage`.

#### 4.4.4 Refus réussi

`h1` « Invitation refusée » ; texte « Le lien ne peut plus être utilisé. » ; lien « Retour à l'accueil ». Jeton supprimé.

### 4.5 Erreurs (aperçu, acceptation, refus)

Toutes dans la même carte, `role="alert"`, avec un bouton d'action unique. **Aucune ne donne le nom de l'organisation, ni la raison précise d'un `invitation_invalid`.**

| Réponse | Titre | Texte | Action |
|---|---|---|---|
| `404 invitation_invalid` (tout cas) | « Cette invitation n'est plus valable » | « Le lien a peut-être expiré, été annulé ou déjà été utilisé. Demandez un nouveau lien à la personne qui vous l'a envoyé. » | « Retour à l'accueil » ; jeton supprimé |
| Aucun jeton (4.2 point 4) | « Lien incomplet » | « Ouvrez à nouveau le lien tel que vous l'avez reçu, en entier. » | « Retour à l'accueil » |
| `403 phone_verification_required` | « Vérifiez d'abord votre numéro » | « Pour rejoindre une organisation, votre numéro de téléphone de connexion doit être vérifié. Votre invitation reste valable : revenez ensuite sur ce lien. » | « Vérifier mon numéro » (point d'entrée existant de vérification du téléphone) ; jeton conservé |
| `409 organization_limit_reached` | « Vous avez atteint la limite d'organisations » | « Un compte ne peut pas faire partie d'un nombre illimité d'organisations. Quittez une organisation dont vous ne faites plus usage, puis revenez sur ce lien tant qu'il est valable. » | « Voir mes profils » (`/profiles`) ; jeton conservé |
| `409 already_member` | « Vous faites déjà partie de cette organisation » | « Cette invitation ne change pas votre rôle. Si vous voulez un autre rôle, demandez-le à un propriétaire ou à un administrateur. » | « Voir mes profils » ; jeton supprimé |
| `403 DENY_SECURITY` (compte restreint) | « Action temporairement impossible » | Texte existant `errors.deny.SECURITY.action` | « Retour à l'accueil » |
| `401` (session expirée) | « Lien incomplet » : la fin de session efface le jeton (audit S2, L1-01-F2) | le texte invite à rouvrir le lien depuis le message reçu | « Retour à l'accueil » |
| `429` | « Trop de tentatives » | « Patientez quelques minutes puis rouvrez le lien. » | « Réessayer » (désactivé pendant le délai si `Retry-After` est lisible) ; jeton conservé |
| Réseau coupé | « Connexion perdue » | « Votre invitation n'a pas été modifiée. Réessayez quand vous êtes reconnecté. » | « Réessayer » ; jeton conservé ; **aucune action n'est mise en file** |
| `400 {"token": [...]}` | traité comme `invitation_invalid` | | |

Sur les trois erreurs propres à la cible (`phone_verification_required`, `organization_limit_reached`, `already_member`), le serveur garde l'invitation `PENDING` : le message dit seulement l'état de **l'appelant**, jamais une information sur l'organisation.

### 4.6 États

| État | Rendu |
|---|---|
| Chargement de l'aperçu | `Skeleton` de la carte ; bouton principal absent |
| Hors ligne | `OfflineBanner` ; boutons « Rejoindre » et « Refuser » désactivés, `common.offlineAction` ; le jeton reste en `sessionStorage` |
| Succès / refus | 4.4.3 et 4.4.4 |
| Erreur | 4.5 |
| Permission refusée | `DENY_SECURITY` en 4.5 ; la page n'utilise pas `AccessDenied` (aucune notion d'accès à une page : c'est une action de l'appelant) |

### 4.7 Données et source

| Donnée | Champ API |
|---|---|
| Nom, type de l'organisation | `preview.organization_name`, `preview.org_type` |
| Rôle proposé | `preview.role` |
| Validité | `preview.expires_at` |
| Inviteur | `preview.invited_by_display_name` |
| Succès | `accept.organization_id`, `accept.organization_name`, `accept.role` (`membership_id` non affiché) |

`useInvitationPreview` est un `useQuery` à fonction `POST` : `queryKey: ["org-invitation-preview"]` **sans** le jeton, `staleTime: 0`, `gcTime: 0`, `retry: false` pour les 4xx, `refetchOnWindowFocus: false`. Ne jamais persister cette clé.

---

## 5. E16 : « Équipes et suppression du compte » (Paramètres, F3)

### 5.1 Objectif et utilisateur

Dire à l'utilisateur quelles organisations l'empêcheraient de supprimer son compte, et quoi faire. **Lecture seule : aucun bouton de suppression de compte n'existe en V1** (aucune story ne le livre, Q-L1-10).

### 5.2 Structure (mobile et desktop identiques)

Section en bas de `pages/Settings.tsx`, dans un `Collapsible` fermé par défaut, titre « Équipes et suppression du compte » (`h2`, bouton déclencheur `min-h-11`, `aria-expanded`). **La requête `GET me/account-deletion-blockers/` part à la première ouverture**, pas au chargement de Paramètres (une requête de moins en 3G).

Contenu ouvert :
1. Texte : « Avant de supprimer un compte, il faut qu'aucune organisation ne dépende de lui. Cette section liste ce qui doit être réglé. »
2. Si `organizations` n'est pas vide : `Alert` d'information (pas destructive) « Vous êtes le seul propriétaire de {{count}} organisation(s). Elles doivent être réglées avant toute suppression de votre compte. » puis une carte par organisation :
   - nom (`h3`, tronqué avec `title`) ; `Badge` « Suspendue » si `status === "SUSPENDED"` (icône + texte) ;
   - texte selon `suggested_action` :
     - `transfer_ownership` : « {{count}} autre(s) membre(s) pourraient devenir propriétaires. Transférez la propriété pour régler ce point. » (`other_members_count`, pluriel i18n) ; bouton « Ouvrir l'équipe » → `/organizations/<organization_id>/team` ;
     - `archive` : « Vous êtes le seul membre. Archivez l'organisation si vous n'en avez plus besoin. » ; bouton « Ouvrir l'organisation » → `/organizations/<organization_id>` (où se trouve la carte « Archiver l'organisation ») ;
     - `wait_for_unsuspension` : « Cette organisation est suspendue. Vous ne pouvez pas la modifier : attendez la levée de la suspension ou contactez le support de Connecte+. » ; aucun bouton.
3. Si `has_other_blocker === true` : `Alert` « D'autres conditions empêchent actuellement la suppression de votre compte. Contactez le support de Connecte+ pour en savoir plus. » **Jamais de détail ni de motif** (confidentialité d'un signalement ou d'une sanction).
4. Si `organizations` est vide **et** `has_other_blocker === false` : « Aucune de vos organisations n'empêche la suppression de votre compte. La suppression du compte n'est pas disponible dans l'application : pour la demander, contactez le support de Connecte+. »

Après une action faite sur l'écran d'équipe, un retour sur Paramètres doit recharger la requête (`staleTime: 0` ; pas de cache : le contrat dit que le blocage disparaît à l'appel suivant).

### 5.3 États

| État | Rendu |
|---|---|
| Chargement | `Skeleton` de 2 cartes |
| Vide | cas 4 ci-dessus |
| Erreur | `ErrorState` compact + « Réessayer » |
| Hors ligne | `OfflineBanner` ; si déjà chargée, la liste reste en mémoire ; sinon texte « Reconnectez-vous pour voir cette section. » |
| Permission refusée | sans objet (route authentifiée, uniquement le compte appelant) |

### 5.4 Composants

Réutilisés : `Collapsible`, `Alert`, `Badge`, `Button` (`asChild` + `Link`), `Skeleton`, `ErrorState`, `OfflineBanner`. Nouveau : `AccountDeletionBlockers` (justifié : unité testable indépendante de `Settings.tsx`).

### 5.5 Données

| Donnée | Champ API |
|---|---|
| Liste | `organizations[].organization_id`, `name`, `status`, `other_members_count`, `suggested_action` |
| Autre blocage | `has_other_blocker` (booléen seul) |

---

## 6. Contenus : clés i18n proposées

Dans `src/i18n/locales/fr.ts` (le garde-fou `i18n-guard.test.ts` exige toutes les clés). Pluriels : suffixes `_one` / `_other` selon la convention i18next déjà employée.

### 6.1 Équipe (`team.*`)

| Clé | Texte |
|---|---|
| `team.title` | Équipe (existante) |
| `team.invite.open` | Inviter une personne |
| `team.tabs.members` | Membres |
| `team.tabs.invitations` | Invitations |
| `team.list.since` | Membre depuis {{date}} |
| `team.you` | (vous) |
| `team.loadMore` | Voir plus de membres |
| `team.loadError` | Impossible de charger l'équipe. |
| `team.empty` | Aucun membre à afficher. |
| `team.lastOwner` | Seul propriétaire actif (remplace l'ancien texte) |
| `team.lastOwnerHelp` | Les autres propriétaires, s'il y en a, ne peuvent pas agir actuellement (compte inactif ou restreint). |
| `team.lastOwnerSelfHint` | Si vous quittez l'organisation, elle n'aura plus de propriétaire disponible. Nommez d'abord un autre propriétaire. |
| `team.ownersOnly` | Réservé aux propriétaires (existante) |
| `team.ownerRemoveHint` | Pour retirer ce propriétaire, rétrogradez-le d'abord. |
| `team.menuLabel` | Actions pour {{name}} |
| `team.changeRole` | Changer le rôle |
| `team.transfer` | Transférer la propriété |
| `team.remove` | Retirer de l'équipe |
| `team.changeRoleTitle` | Changer le rôle de {{name}} |
| `team.currentRole` | (rôle actuel) |
| `team.saveRole` | Enregistrer le rôle |
| `team.back` | Retour |
| `team.promoteOwnerBody` | {{name}} deviendra propriétaire. Cette personne pourra gérer toute l'équipe, rétrograder les autres propriétaires et archiver l'organisation. Vous resterez propriétaire. |
| `team.demoteOwnerBody` | {{name}} ne sera plus propriétaire. Cette personne perdra l'archivage de l'organisation et la gestion des propriétaires. |
| `team.confirmChange` | Je confirme ce changement |
| `team.confirmRoleButton` | Confirmer le changement |
| `team.passwordLabel` | Votre mot de passe |
| `team.passwordHelp` | Nous vous le demandons pour protéger l'organisation. Il n'est pas conservé. |
| `team.roleChanged` | Le rôle de {{name}} est maintenant {{role}}. |
| `team.transferTitle` | Transférer la propriété à {{name}} |
| `team.transferBody` | {{name}} deviendra propriétaire. Vous ne serez plus propriétaire et prendrez le rôle choisi ci-dessous. Vous pourrez continuer à agir dans l'organisation avec ce rôle. |
| `team.transferMyRole` | Votre rôle après le transfert |
| `team.transferAlt` | Pour garder le rôle de propriétaire tout en nommant {{name}}, utilisez plutôt « Changer le rôle » et choisissez Propriétaire. |
| `team.transferConfirm` | Je confirme le transfert de propriété |
| `team.transferButton` | Transférer la propriété |
| `team.transferred` | La propriété a été transférée à {{name}}. |
| `team.removeTitle` | Retirer {{name}} de l'équipe ? |
| `team.removeBody` | {{name}} perdra immédiatement l'accès à l'organisation. Son compte personnel et ses offres personnelles ne changent pas. Les offres, avis et messages de l'organisation restent à l'organisation. Les invitations qu'elle avait créées et qui ne sont pas encore utilisées sont annulées. |
| `team.removeButton` | Retirer |
| `team.removed` | {{name}} a été retiré de l'équipe. |
| `team.alreadyGone` | Cette personne ne fait plus partie de l'équipe. |
| `team.networkLost` | Connexion perdue. Réessayez quand vous êtes reconnecté. |
| `team.rolesTitle`, `team.yourRole`, `team.leave*`, `team.archive*` | existantes, inchangées |
| `team.notAvailable`, `team.add`, `team.removeTitle` (ancien texte), `team.needAnotherOwner` | **supprimées** |

### 6.2 Invitations (`team.invite.*`, `team.invitations.*`)

| Clé | Texte |
|---|---|
| `team.invite.title` | Inviter une personne |
| `team.invite.intro` | Vous obtenez un lien à envoyer vous-même à la personne (par exemple sur WhatsApp). Elle l'ouvre, se connecte et accepte. Le lien ne fonctionne qu'une seule fois. |
| `team.invite.roleLabel` | Rôle |
| `team.invite.rolesNote` | Pour donner le rôle Administrateur ou Propriétaire, invitez d'abord la personne, puis changez son rôle une fois qu'elle a rejoint l'équipe. |
| `team.invite.labelLabel` | Étiquette (facultatif) |
| `team.invite.labelHelp` | Un repère pour retrouver cette invitation, par exemple « Jean, comptable ». Visible par les propriétaires et administrateurs de l'organisation, supprimée dès que l'invitation est utilisée ou annulée. Ne mettez ni téléphone ni adresse. |
| `team.invite.validity` | Le lien est valable {{days}} jours. |
| `team.invite.create` | Créer le lien |
| `team.invite.linkTitle` | Votre lien d'invitation |
| `team.invite.linkWarning` | Ce lien ne sera plus affichable après la fermeture de cette fenêtre. Quiconque le possède peut rejoindre l'équipe avec le rôle {{role}} : envoyez-le seulement à la personne concernée. |
| `team.invite.linkField` | Lien d'invitation |
| `team.invite.copy` | Copier le lien |
| `team.invite.copied` | Lien copié |
| `team.invite.copyFailed` | Copie impossible. Appuyez longuement sur le lien pour le copier. |
| `team.invite.share` | Partager |
| `team.invite.shareTitle` | Invitation à rejoindre une équipe sur Connecte+ |
| `team.invite.shareText` | Je vous invite à rejoindre l'équipe de « {{org}} » sur Connecte+ (lien à usage unique, valable jusqu'au {{date}}) : |
| `team.invite.summary` | Rôle : {{role}}. Expire le {{date}}. |
| `team.invite.notCopied` | Vous n'avez pas encore copié le lien. |
| `team.invite.done` | Terminer |
| `team.invite.errLimit` | Le nombre maximal d'invitations en attente est atteint. Annulez une invitation inutilisée pour en créer une nouvelle. |
| `team.invite.errRate` | Vous avez créé beaucoup d'invitations. Réessayez plus tard. |
| `team.invite.errRole` | Ce rôle ne peut pas être donné par invitation. |
| `team.invite.errLabel` | Cette étiquette est invalide (60 caractères au plus). |
| `team.invite.errNetwork` | Connexion perdue. Vérifiez l'onglet Invitations avant de réessayer. |
| `team.invitations.intro` | Ces liens n'ont pas encore été utilisés. Un lien ne peut pas être affiché une seconde fois : pour en obtenir un nouveau, annulez l'invitation et créez-en une autre. |
| `team.invitations.noLabel` | Sans étiquette |
| `team.invitations.createdBy` | Créée par {{name}} |
| `team.invitations.createdByMe` | Créée par vous |
| `team.invitations.expires` | Expire le {{date}} |
| `team.invitations.expired` | Expirée |
| `team.invitations.empty` | Aucune invitation en attente. |
| `team.invitations.revoke` | Annuler l'invitation |
| `team.invitations.revokeTitle` | Annuler cette invitation ? |
| `team.invitations.revokeBody` | Le lien ne fonctionnera plus. Si la personne l'a déjà reçu, elle ne pourra pas rejoindre l'équipe avec ce lien. |
| `team.invitations.keep` | Garder l'invitation |
| `team.invitations.revoked` | Invitation annulée. |
| `team.invitations.notPending` | Cette invitation n'est plus en attente. |

### 6.3 Acceptation (`invitation.*`)

| Clé | Texte |
|---|---|
| `invitation.guest.title` | Vous avez reçu une invitation |
| `invitation.guest.body` | Quelqu'un vous invite à rejoindre une équipe sur Connecte+. Connectez-vous ou créez un compte pour voir de quelle organisation il s'agit. |
| `invitation.guest.login` | Se connecter |
| `invitation.guest.register` | Créer un compte |
| `invitation.guest.caution` | N'acceptez que les invitations de personnes que vous connaissez. |
| `invitation.preview.title` | Invitation à rejoindre une organisation |
| `invitation.preview.invitedBy` | Invitation de |
| `invitation.preview.role` | Rôle proposé |
| `invitation.preview.validUntil` | Valable jusqu'au |
| `invitation.preview.body` | En acceptant, vous agirez au nom de cette organisation avec ce rôle. Votre profil personnel et vos offres personnelles ne changent pas. Vous pourrez quitter l'organisation à tout moment. |
| `invitation.accept` | Rejoindre l'organisation |
| `invitation.decline` | Refuser l'invitation |
| `invitation.declineTitle` | Refuser cette invitation ? |
| `invitation.declineBody` | Le lien ne pourra plus être utilisé. Vous pourrez demander une nouvelle invitation. |
| `invitation.declineConfirm` | Refuser |
| `invitation.keep` | Garder l'invitation |
| `invitation.joined.title` | Vous avez rejoint {{name}} |
| `invitation.joined.body` | Vous avez le rôle {{role}}. |
| `invitation.joined.open` | Ouvrir l'organisation |
| `invitation.joined.stay` | Rester sur mon profil |
| `invitation.declined.title` | Invitation refusée |
| `invitation.declined.body` | Le lien ne peut plus être utilisé. |
| `invitation.backHome` | Retour à l'accueil |
| `invitation.err.invalid.title` | Cette invitation n'est plus valable |
| `invitation.err.invalid.body` | Le lien a peut-être expiré, été annulé ou déjà été utilisé. Demandez un nouveau lien à la personne qui vous l'a envoyé. |
| `invitation.err.missing.title` | Lien incomplet |
| `invitation.err.missing.body` | Ouvrez à nouveau le lien tel que vous l'avez reçu, en entier. |
| `invitation.err.phone.title` | Vérifiez d'abord votre numéro |
| `invitation.err.phone.body` | Pour rejoindre une organisation, votre numéro de téléphone de connexion doit être vérifié. Votre invitation reste valable : revenez ensuite sur ce lien. |
| `invitation.err.phone.action` | Vérifier mon numéro |
| `invitation.err.limit.title` | Vous avez atteint la limite d'organisations |
| `invitation.err.limit.body` | Un compte ne peut pas faire partie d'un nombre illimité d'organisations. Quittez une organisation dont vous ne faites plus usage, puis revenez sur ce lien tant qu'il est valable. |
| `invitation.err.member.title` | Vous faites déjà partie de cette organisation |
| `invitation.err.member.body` | Cette invitation ne change pas votre rôle. Si vous voulez un autre rôle, demandez-le à un propriétaire ou à un administrateur. |
| `invitation.err.profiles` | Voir mes profils |
| `invitation.err.rate.title` | Trop de tentatives |
| `invitation.err.rate.body` | Patientez quelques minutes puis rouvrez le lien. |
| `invitation.err.network.title` | Connexion perdue |
| `invitation.err.network.body` | Votre invitation n'a pas été modifiée. Réessayez quand vous êtes reconnecté. |
| `invitation.retry` | Réessayer |

### 6.4 Blocages de suppression (`deletionBlockers.*`)

| Clé | Texte |
|---|---|
| `deletionBlockers.title` | Équipes et suppression du compte |
| `deletionBlockers.intro` | Avant de supprimer un compte, il faut qu'aucune organisation ne dépende de lui. Cette section liste ce qui doit être réglé. |
| `deletionBlockers.summary_one` | Vous êtes le seul propriétaire de {{count}} organisation. Elle doit être réglée avant toute suppression de votre compte. |
| `deletionBlockers.summary_other` | Vous êtes le seul propriétaire de {{count}} organisations. Elles doivent être réglées avant toute suppression de votre compte. |
| `deletionBlockers.suspended` | Suspendue |
| `deletionBlockers.transfer_one` | {{count}} autre membre pourrait devenir propriétaire. Transférez la propriété pour régler ce point. |
| `deletionBlockers.transfer_other` | {{count}} autres membres pourraient devenir propriétaires. Transférez la propriété pour régler ce point. |
| `deletionBlockers.openTeam` | Ouvrir l'équipe |
| `deletionBlockers.archive` | Vous êtes le seul membre. Archivez l'organisation si vous n'en avez plus besoin. |
| `deletionBlockers.openOrg` | Ouvrir l'organisation |
| `deletionBlockers.wait` | Cette organisation est suspendue. Vous ne pouvez pas la modifier : attendez la levée de la suspension ou contactez le support de Connecte+. |
| `deletionBlockers.other` | D'autres conditions empêchent actuellement la suppression de votre compte. Contactez le support de Connecte+ pour en savoir plus. |
| `deletionBlockers.none` | Aucune de vos organisations n'empêche la suppression de votre compte. La suppression du compte n'est pas disponible dans l'application : pour la demander, contactez le support de Connecte+. |
| `deletionBlockers.offline` | Reconnectez-vous pour voir cette section. |
| `deletionBlockers.error` | Impossible de charger cette section. |

### 6.5 Codes d'erreur (`errors.code.*`, utilisés par `describeApiError`)

À ajouter à `BUSINESS_CODES` de `lib/api-errors.ts` : `last_effective_owner`, `owner_must_be_demoted`, `reauthentication_failed`, `invitation_invalid`, `invitation_limit_reached`, `invitation_not_found`, `invitation_not_pending`, `already_member`, `member_not_found`, `user_unavailable`, `invalid_transfer`, `use_leave`, `confirmation_required`, `password_required`, `invitation_role_not_allowed`.

| Clé | Texte |
|---|---|
| `errors.code.last_effective_owner` | Cette organisation a des offres actives : elle doit garder au moins un propriétaire disponible. Nommez d'abord un autre propriétaire. |
| `errors.code.owner_must_be_demoted` | Cette personne est propriétaire. Changez d'abord son rôle, puis retirez-la. |
| `errors.code.reauthentication_failed` | Mot de passe incorrect. |
| `errors.code.member_not_found` | Cette personne ne fait plus partie de l'équipe. |
| `errors.code.user_unavailable` | Ce changement n'est pas possible pour ce compte pour le moment. |
| `errors.code.invalid_transfer` | Ce transfert n'est pas possible. |
| `errors.code.invitation_not_pending` | Cette invitation n'est plus en attente. |
| `errors.code.invitation_not_found` | Cette invitation n'est plus en attente. |
| `errors.code.invitation_limit_reached` | (= `team.invite.errLimit`) |
| `errors.code.already_member` | Vous faites déjà partie de cette organisation. |
| `errors.code.invitation_invalid` | Cette invitation n'est plus valable. |

**Textes existants à ne pas réutiliser tels quels pour l'acceptation :** `errors.code.phone_verification_required` (« …pour créer une organisation ») et `errors.code.organization_limit_reached` (« …pour en créer une nouvelle ») parlent de la **création** d'une organisation ; la page d'acceptation utilise les clés `invitation.err.*` ci-dessus.

**Carte « Quitter l'organisation » (existante) :** elle doit aussi gérer `409 last_effective_owner` (contrat §4 : `leave/` peut maintenant le renvoyer) avec le texte `errors.code.last_effective_owner`, en plus de `last_owner`. À ajouter par F1.

Aucun texte n'emploie « garanti », « certifié », « de confiance », « vendeur vérifié » seul (garde `client-rules.test.ts`).

---

## 7. Accessibilité

- **Cibles tactiles :** 44 px minimum (`min-h-11 min-w-11`) pour tout bouton, élément de menu, radio (la ligne entière du `RadioGroup` est cliquable via `Label`), case à cocher (zone étendue par son `Label`) et lien.
- **Focus :** focus visible (anneau du thème). Dialogues : focus initial sur l'action sûre (« Annuler », « Garder l'invitation ») pour les alertes ; sur le premier radio pour E6a et E6b ; sur l'`h1` de la carte pour E15 après un changement d'état. Échap ferme (sauf l'étape « lien » : Échap ferme, pas le clic extérieur). Focus rendu au déclencheur à la fermeture : bouton `⋯` de la ligne, bouton « Inviter une personne ». Après retrait d'un membre ou annulation d'une invitation (le déclencheur disparaît) : focus sur le titre de la liste concernée (`tabIndex={-1}`).
- **Annonces :** une région `aria-live="polite"` unique dans E6 reçoit : rôle changé, propriété transférée, membre retiré, invitation annulée, lien copié (sans le lien). Les erreurs : `role="alert"`. Le jeton n'est jamais annoncé.
- **Tableau :** `caption` `sr-only`, `scope="col"`, la colonne Actions a un en-tête « Actions » `sr-only`.
- **Ne jamais compter sur la couleur seule :** rôles (`RoleBadge` icône + texte), « Seul propriétaire actif » (icône + texte), « Suspendue », « Expirée » (texte), actions destructives (texte et icône).
- **Mot de passe :** `PasswordInput` avec bascule d'affichage existante, `autoComplete="current-password"`, `aria-invalid` et `aria-describedby` via `errorProps`. Le champ n'est jamais pré-rempli ni mémorisé par l'application.
- **Clavier :** menu `⋯` ouvrable avec Entrée et Espace, flèches dans le menu.
- **Zoom 200 % :** aucune largeur fixe ; noms tronqués avec `title` et `aria-label` complet ; boutons à retour à la ligne autorisé.
- **Langue :** tout en français ; libellés de boutons à verbe d'action (« Retirer », « Transférer la propriété »), jamais « OK ».

## 8. Réseau faible

- Aucune image : avatars en initiales, icônes lucide déjà dans le bundle (`UserPlus`, `UserMinus`, `Share2`, `Check`, `ShieldAlert`, `MailOpen`, `AlertTriangle` : importés un par un).
- `OrganizationInvitation` et les 5 dialogues sont en `React.lazy` ; `OrganizationTeam` ne charge que la liste à l'ouverture. Requêtes par écran : E6 = `members/` (+ `invitations/` à l'ouverture de l'onglet) ; E15 connecté = `preview/` seul ; E16 = 1 requête à l'ouverture de la section.
- Pagination de 20 par page avec « Voir plus » (pas de défilement infini automatique).
- **Aucune action différée ni file hors ligne** pour : invitation, rôle, retrait, transfert, acceptation, refus. Boutons désactivés avec raison affichée (`common.offlineAction`). Valeurs saisies conservées après un échec (rôle choisi, étiquette). Un mot de passe est vidé après un échec de ressaisie.
- Anti-doublon : boutons désactivés pendant l'appel ; aucun nouvel essai automatique sur les `POST` (pas de `retry` React Query pour les mutations).
- **Pas de cache persistant** (`persistQueryClient`, service worker) pour `members/`, `invitations/`, `organization-invitations/*`, `account-deletion-blockers/` : données personnelles et jetons (réponses `Cache-Control: private, no-store`). La liste n'existe qu'en mémoire de l'onglet. Vérifier la configuration PWA (`vite.config.ts`) : ces routes sont en `NetworkOnly`.
- **Risque assumé** : sur un Android d'entrée de gamme, l'onglet peut être déchargé pendant la saisie du code OTP (l'utilisateur passe dans l'application SMS) et `sessionStorage` est alors perdu. Le message « Lien incomplet » (4.5) demande de rouvrir le lien reçu, qui contient toujours le jeton dans son fragment ; aucune solution de repli persistante (`localStorage`) n'est retenue pour ne pas laisser un jeton porteur sur l'appareil.

## 9. Conformité aux règles verrouillées

| Règle | Application |
|---|---|
| 1. Un compte, plusieurs contextes | L'acceptation ajoute un contexte organisation au compte existant ; elle ne crée pas de type de compte ; le profil actif ne change qu'à l'appui sur « Ouvrir l'organisation » |
| 2. Permissions ≠ droits commerciaux | Aucun plan, prix, abonnement ni paiement dans ces écrans ; les rôles sont décrits par `role.*_desc` (capacités d'équipe seulement) ; aucun paramètre de plan dans les requêtes |
| 3. La vérification ne s'achète jamais | Aucune mention, badge ni synthèse de vérification dans l'équipe, l'invitation ou l'aperçu. L'aperçu d'invitation n'en renvoie pas |
| 4. Aucun score de confiance | Aucune note, étoile ni score ; la liste n'est pas triée par un indicateur de qualité (ordre serveur : rôle puis ancienneté) |
| 5. « Sponsorisé » | Sans objet : aucun contenu promotionnel dans ces écrans ; `StatusBadge` n'est pas utilisé |
| 6. Aucune commission | Aucun montant |
| 10. Données personnelles par finalité | Membres : `display_name` abrégé seulement, sans photo, téléphone ni e-mail ; l'aperçu d'invitation n'est offert qu'à un compte connecté (pas de nom d'organisation avant connexion, pas d'énumération anonyme) ; étiquette : consigne de ne pas y mettre de donnée personnelle, visible seulement par les gestionnaires, supprimée par le serveur à la fin de l'invitation ; blocages de suppression : comptage, jamais d'identité ; jeton jamais dans une URL d'API, ni journalisé, ni persistant (hors `sessionStorage` du visiteur) |
| 12. Journalisation | Côté serveur ; l'interface n'affiche aucun journal. La ressaisie du mot de passe n'est jamais stockée côté client |

---

## 10. Décisions de design à valider

1. **Pas de menu sur sa propre ligne.** « Quitter l'organisation » reste la carte existante en bas de page. Pas de « Transférer la propriété » depuis la ligne de soi : on l'initie depuis la ligne de la personne choisie.
2. **« Retirer » absent sur un propriétaire** (le serveur répond `owner_must_be_demoted` ; l'interface l'anticipe en renvoyant vers « Changer le rôle »), contrairement à L0-09 §7.7 qui l'affichait.
3. **Aucun blocage préventif sur le « dernier propriétaire »** : le serveur arbitre (`last_owner`, `last_effective_owner`). Le badge « Seul propriétaire actif » informe sans bloquer, car l'écran ne connaît pas les offres actives.
4. **Deux chemins vers un nouveau propriétaire :** « Changer le rôle » → Propriétaire (ajoute un propriétaire) et « Transférer la propriété » (l'acteur prend un rôle inférieur). Les deux exigent la case de confirmation et le mot de passe.
5. **Pas de rôle présélectionné** à la création d'une invitation (éviter un rôle donné par inadvertance).
6. **Le texte de partage cite le nom de l'organisation** (`team.invite.shareText`). La page d'acceptation, elle, ne le montre qu'après connexion. Si l'on préfère que le message partagé soit lui aussi anonyme, retirer `{{org}}`.
7. **Le profil actif ne change pas tout seul** après acceptation (bouton « Ouvrir l'organisation »).
8. **Onglets Membres / Invitations** (au lieu de deux sections empilées) pour limiter le défilement mobile ; la requête des invitations part à l'ouverture de l'onglet.
9. **Étape 2 du dialogue d'invitation non fermable par clic extérieur** (prop `dismissible` ajoutée à `ResponsiveDialog`), pour éviter de perdre un lien non relisible.
10. **Étiquette visible par tous les gestionnaires** (le contrat l'expose à `org.manage_members`), alors que la story L1-01c la destinait à l'inviteur seul ; le texte d'aide le dit.
11. **Jeton en `sessionStorage` seulement** (pas de `localStorage`) : accepté même si un onglet déchargé oblige à rouvrir le lien.

## 11. Questions ouvertes

1. **Pairs administrateurs :** L0-09 laisse un administrateur changer le rôle d'un autre administrateur et le retirer ; le contrat dit seulement « jamais un propriétaire ». À confirmer par l'architecte (`can_manage_role_of`) ; l'interface suit L0-09 et gère `DENY_PERMISSION`.
2. **Valeur de `invitation_ttl_days`** : le contrat annonce son ajout à `GET organizations/limits/` (ADR 0008 §4.2). Si B2a ne le livre pas, la phrase de validité avant création est omise (`expires_at` après création reste exact).
3. **Parcours d'inscription avec `?next=` :** `Login` gère `next` via `safeNext` ; à vérifier pour `Register` (et son étape OTP). Sinon, F2 doit l'ajouter ou conserver la destination dans `sessionStorage`. `safeNext` doit accepter `/organization-invitation` (sans fragment).
4. **Point d'entrée de « Vérifier mon numéro »** (`invitation.err.phone.action`) : la route de vérification du téléphone dans l'application n'est pas dans cette spec ; F2 la repère ou la crée en accord avec le chef de projet.
5. **Support :** les textes de E16 renvoient au « support de Connecte+ » pour supprimer un compte. Aucun canal de support n'est décrit dans les sources (Q-L1-10, LEG-PRV). À valider avec le client ; sinon retirer la phrase.
6. **Pluriel du nombre d'organisations** : `max_organizations_per_account` n'est pas affiché dans le message de limite (`invitation.err.limit.body`) car la valeur n'est pas dans le contrat d'acceptation ; l'afficher exigerait de lire `organizations/limits/` pour un compte qui n'a rien d'autre à y faire.
7. **Aucun écran d'historique des invitations** (`?status=ACCEPTED|DECLINED|REVOKED|EXPIRED` n'est pas utilisé) : le contrat le permet ; non retenu en V1 pour la simplicité. À demander si l'historique des 30 jours doit être visible.
8. **Organisation archivée :** le contrat autorise le transfert sur archivée mais refuse la liste des membres (`DENY_OBJECT_STATE`) : aucun écran d'équipe n'est donc possible pour elle. À signaler à l'architecte si ce cas est voulu.
