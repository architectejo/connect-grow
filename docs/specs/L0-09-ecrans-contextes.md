# L0-09i / T0 — Spécification d'écran : contextes, organisations, prestataire, vérification, vendeur

- **Date :** 10/10/2026
- **Auteur :** designer-ux
- **Destinataire :** dev-frontend (tâches F1 et F2 du plan de l'ADR 0006 §13)
- **Réf. :** CDC v1.2 §3.1, §3.3, §6 ; CLAUDE.md règles 1, 2, 3, 10 ; ADR 0006 §5 (rôles), §6 (contexte actif), §9 (contrat d'API), §14 (valeurs provisoires Q-CLI) ; story L0-09i de `docs/specs/L0-09-compte-contextes.md`.
- **Statut :** proposition. Les décisions à valider sont en section 14, les questions ouvertes en section 15.

---

## 0. Lecture rapide

1. **Vocabulaire de l'interface.** Le mot « contexte » n'apparaît jamais à l'écran. L'utilisateur voit « profil actif » et « Agir en tant que ». Trois sortes de profils : **Personnel**, **Prestataire**, **Organisation**.
2. **Une seule vérité côté client :** `GET /api/accounts/contexts/` donne la liste des profils et, pour chacun, `role` et `capabilities`. Le front masque d'après `capabilities`, mais le serveur décide toujours (doc 06 §24). Chaque refus `DENY_*` est géré (section 9).
3. **Périmètre réel de L0-09.** L'ADR 0006 §9 n'expose en HTTP que : création d'organisation, lecture interne, modification, archivage, **sortie volontaire (`leave`)**, vérification (pièces), prestataire, liste publique, profil vendeur. Il n'existe **aucun endpoint** pour lister les membres, inviter, changer un rôle ou retirer un membre (reporté à L1-01). La section 7 décrit donc deux niveaux : ce qui est livré en L0-09, et l'écran cible de L1-01 (marqué **[L1-01]**, à ne pas coder tant que les endpoints n'existent pas).
4. **Aucun repli silencieux** vers le profil personnel : tout retour au personnel s'accompagne d'un message persistant qui dit pourquoi (section 3.4).

---

## 1. Plan des écrans

| # | Écran / parcours | Route proposée | Fichier proposé | Statut |
|---|---|---|---|---|
| E1 | Sélecteur de profil actif + bandeau du profil actif | (barre de navigation, toutes pages) | `components/layout/ContextSwitcher.tsx`, `ActiveContextBanner.tsx` | nouveau |
| E2 | Mes profils (liste, création, activation) | `/profiles` | `pages/Profiles.tsx` | nouveau |
| E3 | Créer une organisation | `/organizations/new` | `pages/OrganizationNew.tsx` | nouveau |
| E4 | Espace d'une organisation (aperçu, mon rôle, quitter, archiver) | `/organizations/:id` | `pages/OrganizationHome.tsx` | nouveau |
| E5 | Modifier le profil de l'organisation | `/organizations/:id/edit` | `pages/OrganizationEdit.tsx` | nouveau |
| E6 | Équipe | `/organizations/:id/team` | `pages/OrganizationTeam.tsx` | nouveau (L0-09 : réduit ; cible L1-01) |
| E7 | Vérification de l'organisation | `/organizations/:id/verification` | remplace `pages/Verification.tsx` | refonte |
| E8 | Activer / modifier le profil prestataire | boîte de dialogue dans E2 | `components/profiles/ProviderDialog.tsx` | nouveau |
| E9 | Type de vendeur et mentions de vérification sur offres, cartes vendeur, profils publics | `SellerCard`, `PostCard`, `/seller/:contextType/:id` | `SellerCard.tsx`, `PostCard.tsx`, `pages/SellerProfile.tsx` | refonte |
| E10 | Annuaire des organisations | `/businesses` (route conservée, titre changé) | `pages/Businesses.tsx` | refonte |
| E11 | Inscription simplifiée | `/register` | `pages/Register.tsx` | modification |
| E12 | Adaptations des écrans existants au profil actif (navigation, tableau de bord, éditeur d'offre, messages, réglages de contact, formulaires toujours personnels) | — | voir section 12 | modification |
| E13 | Messages d'erreur `DENY_*` et codes métier | — | `lib/api-errors.ts` + clés `errors.*` | nouveau |
| E14 | Message d'information : anciens comptes entreprise | bandeau dans E2, E4, tableau de bord | `components/profiles/LegacyOrgNotice.tsx` | nouveau |

Anciennes pages sans suite : l'onglet « Boutique » de `Settings.tsx` (devient E5), l'item `Vérification` de `AccountShell` (devient E7, visible seulement sous un profil organisation).

---

## 2. Composants

### 2.1. À réutiliser (noms exacts)

| Besoin | Composant existant |
|---|---|
| Gabarits | `AppShell`, `AccountShell`, `RequireAuth` (`components/layout/`), `PageHeader` (`components/common/PageHeader.tsx`) |
| États | `EmptyState`, `ErrorState` (`components/common/StateViews.tsx`), `OfflineBanner`, `Skeleton` (`ui/skeleton.tsx`) |
| Identité | `UserAvatar` (props `src`, `name`, `size`, `shape="square"` pour une organisation), `StatusBadge` (pour `sponsored` seulement ; voir 2.2) |
| Formulaires | `Field`, `errorProps`, `fieldInputClass`, `FormAlert`, `PhoneInput` (`components/auth/FormFields.tsx`), `Input`, `Textarea`, `Checkbox`, `Label`, `Switch`, `ui/form` si déjà utilisé, `CommuneSelect` (`components/common/CommuneSelect.tsx`) |
| Menus et fenêtres | `DropdownMenu` + `DropdownMenuRadioGroup` / `DropdownMenuRadioItem` (déjà exportés par `ui/dropdown-menu.tsx`), `Drawer` (`ui/drawer.tsx`, feuille basse mobile), `Sheet`, `Dialog`, `AlertDialog`, `Popover`, `Tabs`, `Alert` (`ui/alert.tsx`), `Badge` (`ui/badge.tsx`), `Card`, `Separator` |
| Messages | `sonner` (`toast`) pour les confirmations brèves ; `Alert` pour tout message qui doit rester |
| Réseau | `useOnlineStatus` (`hooks/use-online-status.ts`), `useIsMobile` (`hooks/use-mobile.tsx`) |
| Données | `useCities`, `useCategories` (`hooks/use-marketplace.ts`), `compressImage`, `formatFileSize` (`lib/image.ts`), `formatMonthYear`, `formatRelativeDate` (`lib/format.ts`), `parseApiErrors` (`lib/validation.ts`) |
| Existants à adapter | `DocumentRow` de `pages/Verification.tsx` (à extraire en `components/verification/DocumentRow.tsx`), `ImageField` de `pages/Settings.tsx` (à extraire en `components/common/ImageField.tsx` : réutilisé par E5 et E3), `ContactSettingsSection`, `NotificationItem` |

### 2.2. Nouveaux composants (justifiés)

| Composant | Justification | Props principales |
|---|---|---|
| `ActiveContextProvider` + `useActiveContext()` + `useCan(capability)` (`contexts/ActiveContextContext.tsx`, hors UI) | Aucun composant existant ne porte l'état du profil actif. Lit/écrit le stockage local, expose `contexts`, `active`, `setActive`, `can`. | — |
| `ContextSwitcher` | Sélecteur dans la barre de navigation : `DropdownMenu` (desktop) ou `Drawer` (mobile, selon `useIsMobile`). | `className` |
| `ActiveContextBanner` | Bandeau « vous agissez au nom de… » (CDC §3.1 : contexte actif toujours affiché). | — |
| `ContextLostAlert` | `Alert` persistant affiché après un retour forcé au profil personnel (section 3.4). | `reason`, `lostName` |
| `RoleBadge` | Libellé du rôle (Propriétaire, Administrateur, Éditeur, Analyste) : `Badge` + icône ; le sens ne repose jamais sur la couleur seule. | `role` |
| `SellerTypeBadge` | Type de vendeur toujours visible (CDC §3.3) : Particulier, Prestataire, Organisation. | `contextType`, `orgType?`, `size?`, `compact?` |
| `VerifiedClaims` | Liste des mentions précises + libellé de synthèse + aide « Que signifie ce badge ? ». Remplace tout usage de `StatusBadge kind="verified"`. | `claims`, `summary`, `compact?`, `showHelp?` |
| `AccessDenied` | État « permission refusée », composé à partir de `EmptyState` (icône `Lock`). Aucun état équivalent n'existe dans `StateViews.tsx`. | `title?`, `description`, `action?` |
| `LegacyOrgNotice` | Message d'information des anciens comptes entreprise (E14). | `organizationName`, `onDismiss` |
| `lib/api-errors.ts` : `getApiErrorCode(error)`, `describeApiError(error, ctx)` | Un seul endroit qui traduit `code` → texte français et → action (retirer le profil, rafraîchir). | — |

Aucune dépendance graphique nouvelle : tout vient de shadcn/ui, lucide-react et Tailwind déjà installés.

**À supprimer :** `badge.verified: "Vérifié"` dans `fr.ts` et la valeur `verified` de `StatusBadgeKind` (règle 3 : jamais un « Vérifié » nu). `StatusBadge` conserve `sponsored`, `trending`, `exchangeable`, `service`, `NEUF`, `OCCASION`, `RECONDITIONNE`.

---

## 3. E1 — Sélecteur de profil actif et bandeau

### 3.1. Objectif
Savoir à tout instant sous quelle identité l'on agit, et en changer en deux gestes. Action principale : choisir un profil.

### 3.2. Données et stockage
- Source : `GET /api/accounts/contexts/` (ADR §9.1), enveloppe `{count, next: null, previous: null, results}`. Clé React Query : `["contexts", userId]`, `staleTime` 5 min, rechargée à la connexion, au retour de focus, après création/archivage/départ.
- Ordre : celui du serveur (Personnel, Prestataire, organisations par nom).
- **Mémorisation (Q-CP4).** Clé `localStorage` : `connecte.activeContext.v1`. Valeur : `{"userId", "type", "id", "name", "role", "orgType"}`.
  - Écrite à chaque choix. Effacée à la déconnexion. Ignorée et supprimée si `userId` diffère du compte connecté (évite qu'un autre utilisateur du même téléphone hérite d'un profil d'organisation).
  - L'`name` mémorisé permet d'afficher le profil actif immédiatement en 3G, avant que `contexts/` n'ait répondu.
  - **Pas d'écoute de l'événement `storage`** : chaque onglet garde son profil. Un nouvel onglet démarre sur le dernier choix. Le bandeau de chaque onglet est toujours exact.
- **Absence de valeur mémorisée :** profil personnel (en-tête absent côté serveur). C'est un choix explicite, pas un repli.
- **Valeur mémorisée absente de la liste reçue** (révoqué, suspendu, archivé) : retour au personnel **avec** `ContextLostAlert` (3.4). Jamais silencieux.
- En-tête : `api/client.ts` ajoute `X-Context: <TYPE>:<uuid>` à toute requête authentifiée dont le profil actif n'est pas `USER`. Les endpoints qui l'ignorent le tolèrent (ADR §6.4).

### 3.3. Structure

**Mobile (< 768 px).**
```
┌──────────────────────────────┐
│ Logo            [cloche] [☰] │  header fixe h-16 (existant)
├──────────────────────────────┤
│ [avatar] Agir en tant que    │  bandeau h-9, pleine largeur,
│ Atelier X · Administrateur ⌄ │  bouton (ouvre le Drawer)
├──────────────────────────────┤
│ contenu                      │
```
- Le bandeau est **toujours présent pour un utilisateur connecté**, y compris en profil personnel (fond `bg-muted`, texte « Profil personnel »). En profil prestataire ou organisation : fond `bg-primary/10`, bordure basse `border-primary/30`, nom + rôle.
- Il est un `<button>` de pleine largeur (cible 44 px minimum : `min-h-11` ; le visuel h-9 plus zone de tap par padding vertical).
- Le bandeau est rendu **dans le `<header>` fixe** de `Navbar.tsx`, sous le `<nav>`. `AppShell` doit ajouter `pt-[calc(5rem+2.25rem)]` (au lieu de `pt-20`) quand l'utilisateur est connecté, sur mobile ; sur desktop voir ci-dessous.
- Le `Sheet` du menu (☰) affiche en tête le nom du compte (pas le nom d'une organisation) et un rappel « Profil actif : … » avec un bouton « Changer de profil » (même Drawer).
- `BottomNav` : voir 12.1 pour l'item « Publier » selon les capacités.

**Desktop (≥ 768 px).**
- Dans `Navbar`, avant la cloche : un `DropdownMenuTrigger` en pastille : `UserAvatar size="sm"` (carré si organisation) + nom tronqué (`max-w-[10rem] truncate`) + icône `ChevronsUpDown`. Sous le nom, en `text-[11px]` : le type (« Personnel », « Prestataire », « Entreprise »…).
- Profil actif ≠ personnel : un bandeau h-9 sous la barre (même contenu que mobile) avec, à droite, le bouton lien « Passer au profil personnel ». Profil personnel : pas de bandeau (la pastille suffit).
- Le menu avatar existant (Tableau de bord, Favoris, Paramètres, Corbeille, Déconnexion) reste et gagne « Mes profils » (`/profiles`). Son libellé de tête affiche **toujours le nom du compte** (`user.full_name`), jamais le nom d'une organisation (aujourd'hui `business_profile.business_name`).

**Contenu du menu / Drawer.**
```
Agir en tant que
(•) Personnel            Marie Kabongo                     ✓
( ) Prestataire          Marie couture
( ) Entreprise           Atelier X          Administrateur
( ) ONG                  Aide Kin           Éditeur
─────────────
Mes profils
Créer une organisation
```
- Un élément par profil de `contexts/` : avatar, nom, type, rôle (organisations seulement). L'élément actif porte une coche et `aria-checked="true"`.
- Pied : lien « Mes profils » (`/profiles`) et lien « Créer une organisation » (`/organizations/new`).
- Liste vide de profils annexes (seulement Personnel) : le menu ne montre que Personnel et les deux liens ; ce n'est pas une erreur.

### 3.4. Comportements
1. **Choisir un profil** : met à jour le stockage et l'état, annule les requêtes en cours dépendantes (`queryClient.cancelQueries`), annonce le changement (live region), ferme le menu, remet le focus sur le déclencheur. Aucune requête réseau n'est nécessaire (fonctionne hors ligne).
2. **Clés React Query dépendantes du profil** (mes offres, corbeille, tableau de bord et statistiques, « qui a demandé », conversations, réglages de contact) : préfixées `[contextType, contextId, …]`. Un changement de profil montre donc l'état de chargement (`Skeleton`) et **jamais** les données de l'ancien profil. Interdit : `keepPreviousData` / `placeholderData` sur ces requêtes.
3. **Redirection après changement** si la page courante dépend du profil et n'a pas de sens pour le nouveau : `/edit-post/*`, `/create-post` avec formulaire non modifié → `/dashboard` ; avec formulaire modifié → `AlertDialog` « Changer de profil ? » (texte 3.6) avant d'agir. Les pages `organizations/:id/*` ne dépendent pas du profil actif (ADR §6.4 : identifiant dans le chemin) : pas de redirection.
4. **Retour forcé au personnel** (`ContextLostAlert`). Déclencheurs : valeur mémorisée absente de la liste ; réponse 403 `DENY_RELATION`, `DENY_CONTEXT`, `DENY_SECURITY` ou `DENY_OBJECT_STATE` à une requête portant `X-Context` **et** profil actif absent de la liste rechargée (la règle complète est en section 9). Effets : profil actif = personnel, stockage mis à jour, `Alert` `variant="destructive"` **persistant** en haut du contenu (`role="alert"`), fermable par un bouton « J'ai compris », texte selon la cause (9.2). Elle reste affichée après navigation jusqu'à fermeture ou 30 min. Jamais un simple toast.

### 3.5. États
| État | Comportement |
|---|---|
| Chargement de `contexts/` (premier chargement) | Si un profil est mémorisé : afficher son nom mémorisé, avec une pastille de chargement discrète (`animate-pulse`) ; sinon `Skeleton` h-9. Le menu ouvert pendant le chargement affiche 3 lignes `Skeleton`. |
| Erreur de chargement | Le bandeau affiche le profil mémorisé ; dans le menu : `ErrorState` compact (« Impossible de charger vos profils. »), bouton « Réessayer ». Les profils déjà en cache restent sélectionnables. |
| Hors ligne | Le sélecteur reste utilisable avec la liste en cache (`OfflineBanner` global prévient). Liens « Créer une organisation » désactivés avec texte « Connexion requise ». |
| Vide | Voir 3.3 (seul Personnel). |
| Permission refusée | Sans objet pour le sélecteur ; voir `ContextLostAlert`. |
| Succès | Annonce vocale + bandeau mis à jour. Pas de toast (le bandeau est la confirmation). |

### 3.6. Textes (clés i18n)
| Clé | Texte |
|---|---|
| `context.actAs` | `Agir en tant que` |
| `context.active` | `Profil actif` |
| `context.activeAria` | `Profil actif : {{name}}, {{type}}. Changer de profil.` |
| `context.bannerPersonal` | `Vous agissez en tant que : profil personnel` |
| `context.bannerProvider` | `Vous agissez en tant que prestataire : {{name}}` |
| `context.bannerOrganization` | `Vous agissez au nom de {{name}} · {{role}}` |
| `context.switchToPersonal` | `Passer au profil personnel` |
| `context.change` | `Changer de profil` |
| `context.switched` | `Vous agissez maintenant : {{name}}.` (live region) |
| `context.type.USER` | `Personnel` |
| `context.type.PROVIDER` | `Prestataire` |
| `context.type.ORGANIZATION` | `Organisation` |
| `context.myProfiles` | `Mes profils` |
| `context.createOrg` | `Créer une organisation` |
| `context.loadError` | `Impossible de charger vos profils.` |
| `context.offlineNeeded` | `Connexion requise.` |
| `context.leaveFormTitle` | `Changer de profil ?` |
| `context.leaveFormDescription` | `Les modifications non enregistrées de ce formulaire seront perdues.` |
| `context.leaveFormConfirm` | `Changer de profil` |
| `context.alwaysPersonal` | `Cette action est toujours faite avec votre profil personnel.` |
| `role.OWNER` | `Propriétaire` |
| `role.ADMIN` | `Administrateur` |
| `role.EDITOR` | `Éditeur` |
| `role.ANALYST` | `Analyste` |
| `orgType.ENTREPRISE` | `Entreprise` |
| `orgType.BOUTIQUE` | `Boutique` |
| `orgType.ONG` | `ONG` |
| `orgType.ORGANISATEUR_EVENEMENTS` | `Organisateur d'événements` |

### 3.7. Accessibilité
- Déclencheur desktop : `aria-label={context.activeAria}`, `aria-haspopup="menu"`. Le menu est un `DropdownMenuRadioGroup` (rôles `menuitemradio`, `aria-checked`), navigation flèches/Début/Fin/Échap/Entrée assurée par Radix. Focus visible : anneau `ring-2 ring-ring` (déjà dans le thème).
- Mobile : `Drawer` avec `DrawerTitle` = « Agir en tant que » ; liste en `role="radiogroup"`, chaque ligne `role="radio"` + `aria-checked` (même patron que le choix de type de compte de `Register.tsx`), hauteur ≥ 48 px, focus piégé, Échap et balayage vers le bas ferment, focus rendu au bandeau.
- Le bandeau : `<div role="region" aria-label="Profil actif">` contenant le bouton ; ne pas utiliser `aria-live` sur le bandeau lui-même (bruyant au chargement). L'annonce du changement passe par une live region `aria-live="polite"` visuellement masquée (`sr-only`), montée une seule fois dans `ActiveContextProvider`.
- Distinction de profil jamais par la couleur seule : texte « au nom de », icône (`UserRound`, `Briefcase`, `Building2`) et libellé du type.
- Contraste : textes sur `bg-primary/10` en `text-foreground` (pas `text-primary` en `text-xs`).

### 3.8. Réseau faible
Zéro appel pour changer de profil. Une seule requête (`contexts/`) mise en cache, rechargée en arrière-plan. Pas d'image obligatoire : logos d'organisation affichés par `ImageWithFallback` avec initiales.

---

## 4. E2 — Mes profils

### 4.1. Objectif et utilisateur
Voir ses trois sortes de profils et en ajouter. Utilisateur : tout compte connecté. **Action principale : « Créer une organisation »** (bouton du `PageHeader`). L'activation du prestataire est une action secondaire dans sa carte.

### 4.2. Parcours
Entrée : menu avatar → « Mes profils » ; lien « Mes profils » du sélecteur ; page d'accueil du compte après inscription (texte de bienvenue, 11.2) ; lien depuis un état vide (12.3). Sorties : E3, E4, ouverture de E8, bascule de profil actif.

### 4.3. Structure (mobile puis desktop identiques, une colonne ; desktop : `AccountShell` avec menu latéral, cartes en `max-w-2xl`)
Gabarit `AccountShell`. Nouvel item de menu : `{ to: "/profiles", label: "Mes profils", icon: Users }` placé avant « Paramètres ».
1. `PageHeader` : eyebrow « Compte », titre « Mes profils », description « Votre compte est unique. Vous pouvez agir sous plusieurs profils : personnel, prestataire, ou au nom d'une organisation. », action « Créer une organisation ».
2. `LegacyOrgNotice` (si applicable, E14).
3. Carte « Profil personnel » : avatar, nom du compte, mention « Toujours disponible ». Bouton « Agir sous ce profil » (ou badge « Profil actif »). Lien « Modifier mes informations » → `/settings`.
4. Carte « Profil prestataire » (voir 4.4).
5. Section « Organisations » (`<h2>`), liste de cartes (voir 4.5) ou `EmptyState`.

### 4.4. Carte prestataire
Source : `GET /api/accounts/provider/` (404 `provider_not_found` = non activé : état normal, pas une erreur).
| État | Contenu |
|---|---|
| Non activé | Titre « Profil prestataire », texte « Proposez vos services sous votre nom, sans vous présenter comme une entreprise. Aucun nouveau mot de passe ni nouveau numéro. L'activation est gratuite. » Bouton « Activer mon profil prestataire » (ouvre E8). |
| Actif | Nom d'affichage, `SellerTypeBadge` Prestataire, `bio` (2 lignes), boutons « Agir sous ce profil » / badge « Profil actif », « Modifier », « Désactiver ». |
| Archivé (`status = ARCHIVED`) | Texte « Ce profil est désactivé. Ses offres ne sont plus visibles. Les avis reçus sont conservés. » Bouton « Réactiver mon profil prestataire » (appelle `provider/activate/`, réponse 200). |
| Chargement | `Skeleton` h-28. |
| Erreur | `ErrorState` compact + « Réessayer » (hors 404). |
| Restriction du compte (`DENY_SECURITY`) | `Alert` : voir 9.3. Bouton d'activation désactivé. |

### 4.5. Carte organisation
Source : éléments `ORGANIZATION` de `contexts/` (nom, `org_type`, `role`, logo). Contenu : `UserAvatar shape="square"`, nom, `SellerTypeBadge`, `RoleBadge`, badge « Profil actif » si applicable. Actions : « Ouvrir » (→ `/organizations/:id`, lien principal couvrant la carte, patron « after:absolute after:inset-0 » de `Businesses.tsx`), bouton « Agir sous ce profil » (désactivé et remplacé par le badge si déjà actif). Les organisations suspendues et archivées ne figurent pas dans `contexts/` : elles n'apparaissent pas ici (limite à valider, section 15).

### 4.6. États de la page
| État | Comportement |
|---|---|
| Chargement | 3 `Skeleton` (personnel, prestataire, une organisation). |
| Vide (aucune organisation) | `EmptyState` icône `Building2`, titre « Aucune organisation », description « Créez une organisation pour publier au nom de votre entreprise, boutique, ONG ou structure d'événements, et travailler avec une équipe. » action « Créer une organisation ». |
| Erreur de `contexts/` | `ErrorState` avec « Réessayer ». |
| Hors ligne | Liste en cache affichée ; boutons « Créer », « Activer », « Réactiver », « Désactiver » désactivés avec `aria-describedby` vers `common.offlineAction` (« Reconnectez-vous pour effectuer cette action. »). « Agir sous ce profil » reste actif (local). |
| Permission refusée | Pas de cas (page du compte). |
| Succès | Après activation du prestataire : toast « Profil prestataire activé. » + bouton du toast « Agir sous ce profil » ; la carte passe à l'état Actif. |

### 4.7. Textes
| Clé | Texte |
|---|---|
| `profiles.title` | `Mes profils` |
| `profiles.eyebrow` | `Compte` |
| `profiles.description` | `Votre compte est unique. Vous pouvez agir sous plusieurs profils : personnel, prestataire, ou au nom d'une organisation.` |
| `profiles.personal.title` | `Profil personnel` |
| `profiles.personal.hint` | `Toujours disponible.` |
| `profiles.personal.edit` | `Modifier mes informations` |
| `profiles.actAs` | `Agir sous ce profil` |
| `profiles.isActive` | `Profil actif` |
| `profiles.provider.title` | `Profil prestataire` |
| `profiles.provider.intro` | `Proposez vos services sous votre nom, sans vous présenter comme une entreprise. Aucun nouveau mot de passe ni nouveau numéro. L'activation est gratuite.` |
| `profiles.provider.activate` | `Activer mon profil prestataire` |
| `profiles.provider.edit` | `Modifier` |
| `profiles.provider.archive` | `Désactiver` |
| `profiles.provider.archived` | `Ce profil est désactivé. Ses offres ne sont plus visibles. Les avis reçus sont conservés.` |
| `profiles.provider.reactivate` | `Réactiver mon profil prestataire` |
| `profiles.provider.activated` | `Profil prestataire activé.` |
| `profiles.provider.archiveTitle` | `Désactiver le profil prestataire ?` |
| `profiles.provider.archiveDescription` | `Vos offres publiées sous ce profil ne seront plus visibles. Vos avis sont conservés. Vous pourrez le réactiver à tout moment.` |
| `profiles.provider.archiveConfirm` | `Désactiver le profil` |
| `profiles.provider.archived_toast` | `Profil prestataire désactivé.` |
| `profiles.orgs.title` | `Organisations` |
| `profiles.orgs.emptyTitle` | `Aucune organisation` |
| `profiles.orgs.emptyDescription` | `Créez une organisation pour publier au nom de votre entreprise, boutique, ONG ou structure d'événements, et travailler avec une équipe.` |
| `profiles.orgs.open` | `Ouvrir {{name}}` |
| `common.offlineAction` | `Reconnectez-vous pour effectuer cette action.` |

### 4.8. Accessibilité
Chaque section est un `<section aria-labelledby>`. Les cartes organisation sont des `<article>` avec un seul lien principal ; les boutons secondaires ne sont pas imbriqués dans le lien. Les boutons « Agir sous ce profil » ont `aria-label="Agir sous ce profil : {{name}}"`. Le focus après activation du prestataire va au titre de la carte (`tabIndex={-1}`).

### 4.9. Réseau faible
Deux requêtes (`contexts/` déjà en cache ; `provider/`). Logos : `loading="lazy"`, taille d'affichage 40 px (le serveur sert un WebP ré-encodé).

---

## 5. E8 — Activer ou modifier le profil prestataire (boîte de dialogue)

- **Composant :** `Dialog` (desktop) / `Drawer` (mobile) contenant un formulaire. **Action principale :** « Activer le profil ».
- **Champs :** `display_name` (obligatoire, 2 à 255 car., **pré-rempli avec le nom du compte**), `bio` (facultatif, 2 000 car. au plus, compteur), catégories (facultatif, mêmes composants que l'éditeur d'offre : `useCategories`).
- **Décision de design :** l'activation passe par ce formulaire au lieu d'un appel direct, parce que le nom d'affichage du prestataire est **public** et que le nom du compte est un nom complet, alors que le compte personnel n'est publié que sous la forme « Marie K. » (`public_display_name`). L'utilisateur doit voir et pouvoir changer ce qui sera public. À valider (section 14, D3).
- **Texte d'aide sous le nom :** « Ce nom est public. Il apparaît sur vos offres et votre profil prestataire. »
- **Erreurs de champ :** `display_name` trop court (« Saisissez au moins 2 caractères. »), trop long (« 255 caractères au maximum. »), `bio` (« 2 000 caractères au maximum. »). Erreur serveur par champ via `parseApiErrors` ; `DENY_SECURITY` → `FormAlert` (9.3).
- **États :** envoi en cours (bouton désactivé + `Loader2`), hors ligne (bouton désactivé + `common.offlineAction`), succès (fermeture + toast `profiles.provider.activated`).

| Clé | Texte |
|---|---|
| `provider.dialogTitleActivate` | `Activer mon profil prestataire` |
| `provider.dialogTitleEdit` | `Modifier mon profil prestataire` |
| `provider.displayName` | `Nom affiché` |
| `provider.displayNameHint` | `Ce nom est public. Il apparaît sur vos offres et votre profil prestataire.` |
| `provider.bio` | `Présentation (facultatif)` |
| `provider.categories` | `Catégories (facultatif)` |
| `provider.submitActivate` | `Activer le profil` |
| `provider.submitEdit` | `Enregistrer` |
| `provider.nameTooShort` | `Saisissez au moins 2 caractères.` |
| `provider.tooLong` | `Texte trop long.` |

Accessibilité : `DialogTitle` + `DialogDescription`, focus initial sur « Nom affiché », Échap ferme (confirmer si modifié), erreurs reliées par `aria-describedby` via `errorProps`.

---

## 6. E3 — Créer une organisation

### 6.1. Objectif
Créer une organisation dont l'utilisateur devient propriétaire (`POST /api/accounts/organizations/`). **Action principale :** « Créer l'organisation ».

### 6.2. Parcours
1. Entrée : `/organizations/new` (depuis E2, sélecteur, états vides).
2. **Garde-fou téléphone (Q-CP5).** Si `user.phone_verified` est faux (champ à fournir par `me/` ; voir question Q-F1), la page affiche à la place du formulaire un `Alert` (non destructif) « Vérifiez d'abord votre numéro de connexion » avec le bouton « Vérifier mon numéro » → `/settings` (onglet « Coordonnées »). Le formulaire n'est pas affiché. Si le champ est inconnu du front, le formulaire s'affiche et le 403 `phone_verification_required` est traité à l'envoi (9.4).
3. Saisie : nom, type, description, catégories, ville/commune, NIF, logo.
4. Envoi → `201` → invalidation de `["contexts", userId]` → navigation vers `/organizations/:id` avec l'état `{ justCreated: true }`.
5. Erreurs : 400 par champ, 403 `phone_verification_required`, 409 `organization_limit_reached`, 403 `DENY_SECURITY`, 429 (throttle 5/jour), réseau.

### 6.3. Structure
Gabarit `AccountShell`, colonne unique `max-w-2xl`, mobile et desktop identiques (sur mobile les champs sont en pleine largeur ; la barre d'action reste en bas du formulaire, pas fixe, pour éviter de masquer les champs avec le clavier).
1. `PageHeader` : titre « Créer une organisation », description « Une organisation vous permet de publier sous le nom de votre entreprise, boutique, ONG ou structure d'événements, et de travailler avec une équipe. Vous en serez le propriétaire. »
2. Groupe « Type d'organisation » (obligatoire) : 4 cartes radio (patron de `Register.tsx` : `role="radiogroup"`, boutons `role="radio"`, `aria-checked`), grille `grid-cols-1 sm:grid-cols-2`. Icônes : `Building2` Entreprise, `Store` Boutique, `HeartHandshake` ONG, `CalendarDays` Organisateur d'événements. Chaque carte : titre + description d'une ligne (clés ci-dessous).
3. `Field` « Nom de l'organisation » (obligatoire, 2 à 255 car.). Aide : « Ce nom est public. Une fois une pièce de vérification validée, il ne pourra plus être modifié. »
4. `Field` « Présentation » (`Textarea`, facultatif, 2 000 car., compteur).
5. `Field` « Catégories » (facultatif, sélection multiple).
6. `Field` « Commune » (`CommuneSelect`, facultatif). Aide : « Seule la commune est affichée publiquement. L'adresse exacte n'est jamais publiée. »
7. `Field` « Numéro d'identification fiscale (NIF) » (facultatif). Aide : « Non publié. Utilisé uniquement pour le dossier de l'organisation. »
8. `ImageField` « Logo » (facultatif, compression existante `compressImage`).
9. `FormAlert` (erreur générale).
10. Bouton « Créer l'organisation » (pleine largeur sur mobile) + lien « Annuler » (retour).

### 6.4. États
| État | Comportement |
|---|---|
| Chargement | `Skeleton` pour les listes de communes/catégories ; le formulaire reste saisissable. |
| Vide | Sans objet. |
| Erreur de champ | Sous le champ, `role="alert"`, focus sur le premier champ en erreur. |
| Erreur serveur/réseau | `FormAlert` « Connexion impossible… » (`errors.network`) ; les valeurs saisies sont conservées. |
| Téléphone non vérifié | `Alert` bloquant (voir parcours 2) ou, après 403, `FormAlert` `errors.phone_verification_required`. |
| Plafond atteint | `FormAlert` `errors.organization_limit_reached` + lien « Mes profils ». |
| Hors ligne | Bouton désactivé, texte `common.offlineAction`, brouillon conservé en mémoire. **Aucun envoi différé** : une création d'organisation est une action sensible et soumise à un plafond ; elle n'est jamais mise en file. |
| Succès | Navigation vers E4 (voir 7.4). |
| Permission refusée | `DENY_SECURITY` (compte restreint) : `FormAlert` 9.3. |
| Envoi | Bouton désactivé + `Loader2` ; protection contre le double envoi. |

### 6.5. Textes
| Clé | Texte |
|---|---|
| `orgNew.title` | `Créer une organisation` |
| `orgNew.description` | `Une organisation vous permet de publier sous le nom de votre entreprise, boutique, ONG ou structure d'événements, et de travailler avec une équipe. Vous en serez le propriétaire.` |
| `orgNew.type` | `Type d'organisation` |
| `orgType.ENTREPRISE_desc` | `Société, commerce, artisan, prestataire de services.` |
| `orgType.BOUTIQUE_desc` | `Point de vente ou vitrine de produits.` |
| `orgType.ONG_desc` | `Association, fondation, organisation à but non lucratif.` |
| `orgType.ORGANISATEUR_EVENEMENTS_desc` | `Structure qui organise des événements.` |
| `orgNew.name` | `Nom de l'organisation` |
| `orgNew.nameHint` | `Ce nom est public. Une fois une pièce de vérification validée, il ne pourra plus être modifié.` |
| `orgNew.nameRequired` | `Saisissez le nom de l'organisation (2 caractères au moins).` |
| `orgNew.typeRequired` | `Choisissez un type d'organisation.` |
| `orgNew.descriptionLabel` | `Présentation (facultatif)` |
| `orgNew.categories` | `Catégories (facultatif)` |
| `orgNew.commune` | `Commune (facultatif)` |
| `orgNew.communeHint` | `Seule la commune est affichée publiquement. L'adresse exacte n'est jamais publiée.` |
| `orgNew.nif` | `Numéro d'identification fiscale (NIF) (facultatif)` |
| `orgNew.nifHint` | `Non publié. Utilisé uniquement pour le dossier de l'organisation.` |
| `orgNew.logo` | `Logo (facultatif)` |
| `orgNew.submit` | `Créer l'organisation` |
| `orgNew.phoneRequiredTitle` | `Vérifiez d'abord votre numéro de connexion` |
| `orgNew.phoneRequiredBody` | `Pour créer une organisation, votre numéro de téléphone de connexion doit être vérifié par SMS.` |
| `orgNew.phoneRequiredAction` | `Vérifier mon numéro` |
| `orgNew.created` | `Organisation créée.` |

### 6.6. Accessibilité
Chaque champ a un `<label>` (via `Field`). Le groupe de type est un `radiogroup` nommé par un `<legend>` ; flèches gauche/droite changent la sélection (roving tabindex) en plus du clic ; la sélection n'est pas portée par la couleur seule (coche + `aria-checked`). Compteurs de caractères en `aria-live="off"`, limite annoncée dans l'aide. Boutons ≥ 44 px. `autoComplete="organization"` sur le nom.

### 6.7. Réseau faible
Un seul envoi multipart ; logo compressé côté client avant l'envoi (`compressImage`). Communes et catégories déjà en cache React Query. Pas de pré-chargement d'images.

---

## 7. E4, E5, E6 — Espace d'une organisation

Les trois pages sont dans `AccountShell`, avec un sous-menu horizontal sous le titre (patron des onglets défilants de `AccountShell` : liens arrondis `NavLink`, `overflow-x-auto`) : **Aperçu**, **Profil**, **Vérification**, **Équipe**. Une entrée n'est affichée que si la capacité correspond (tableau 7.1). Les URL portent l'identifiant : le profil actif n'a pas à être celui de l'organisation.

### 7.1. Ce que voit et peut faire chaque rôle (matrice de l'ADR §5 traduite en interface)

Légende : **V** visible et actif ; **L** lecture seule ; **—** masqué (le serveur refuse de toute façon avec `DENY_PERMISSION`).

| Élément d'interface | Capacité | Propriétaire | Administrateur | Éditeur | Analyste |
|---|---|---|---|---|---|
| Ouvrir l'espace (Aperçu, rôle propre, statut) | `org.view_internal` | V | V | V | V |
| Onglet « Profil » : modifier nom, présentation, logo, catégories, commune, NIF | `org.edit_profile` | V | V | L (résumé sans champs modifiables) | L |
| Onglet « Vérification » : voir l'état des pièces | `org.view_internal` | V | V | L | L |
| Envoyer / supprimer une pièce | `org.verification_submit` | V | V | — | — |
| Onglet « Équipe » : voir mon rôle, quitter | `org.leave` | V | V | V | V |
| Équipe **[L1-01]** : ajouter/inviter, retirer un membre | `org.manage_members` | V | V (jamais sur un propriétaire) | — | — |
| Équipe **[L1-01]** : changer un rôle | `org.manage_roles` | V (tous les rôles) | V (Administrateur, Éditeur, Analyste ; jamais Propriétaire) | — | — |
| Archiver l'organisation | `org.archive` | V | — | — | — |
| Publier, modifier, supprimer une offre (boutons dans « Mes offres », éditeur) | `offer.publish/edit/delete` | V | V | V | — |
| Voir « Mes offres », corbeille | `offer.view_internal` | V | V | V | V (lecture) |
| Répondre à un avis | `review.reply` | V | V | V | — |
| Liste « Qui a demandé » (données du demandeur) | `contact.view_requesters` | V | V | V | — (compteurs seulement) |
| Réglages de contact de l'organisation | `contact.manage_channels` | V | V | — | — |
| Messages de l'organisation | `message.reply` | V | V | — | — |
| Statistiques, graphiques | `stats.view` | V | V | V | V |

Règle d'implémentation : `useCan("<capacité>")` lit `capabilities` du profil actif ; pour les pages `organizations/:id/*` c'est le champ `capabilities` de `OrganizationInternal`. Le masquage n'est jamais le contrôle : tout refus serveur est géré (section 9).

### 7.2. E4 — Aperçu `/organizations/:id`

**Objectif :** donner le statut de l'organisation, le rôle de l'utilisateur et les actions utiles. Action principale : **« Agir sous ce profil »** (bouton primaire du `PageHeader`) ; si déjà actif, remplacé par le badge « Profil actif ». 

**Structure (identique mobile/desktop ; desktop : deux colonnes à partir de `lg`).**
1. `PageHeader` : eyebrow = type (`orgType.*`), titre = nom, description = présentation ; action = bouton ci-dessus.
2. Sous-menu (7).
3. Si `location.state.justCreated` : `Alert` de succès « Votre organisation est créée. Vous en êtes le propriétaire. La prochaine étape recommandée est d'envoyer les pièces de vérification. » avec lien « Envoyer les pièces » (visible si `org.verification_submit`).
4. `LegacyOrgNotice` si applicable (E14).
5. Carte « Votre rôle » : `RoleBadge` + description du rôle (clés `role.*_desc`) + liste « Ce que vous pouvez faire » dérivée des capacités (3 à 6 lignes courtes, voir clés `capability.*`).
6. Carte « Vérification » : `VerifiedClaims` (mentions actuelles) ou « Aucune mention pour l'instant. », lien « Voir le détail » → E7.
7. Carte « Profil public » : aperçu (`UserAvatar`, nom, `SellerTypeBadge`, commune), lien « Voir le profil public » → `/seller/organization/:id`.
8. Carte « Quitter l'organisation » (tous les rôles) : texte court et bouton `variant="outline"` destructif doux « Quitter l'organisation » → `AlertDialog` (7.5).
9. Carte « Archiver l'organisation » (propriétaire seulement) : texte et bouton « Archiver l'organisation » → `AlertDialog` (7.6).

**États.**
| État | Comportement |
|---|---|
| Chargement | `Skeleton` : titre, carte rôle, carte vérification. |
| Vide | Sans objet. |
| Erreur réseau/500 | `ErrorState` + « Réessayer ». |
| `DENY_RELATION` (non-membre, ex. lien partagé, ou ancien membre) | `AccessDenied` : « Vous n'avez pas accès à cette organisation. » bouton « Mes profils ». |
| `DENY_SECURITY` (organisation suspendue) | `AccessDenied` : « Cette organisation est suspendue. Ses offres ne sont plus visibles. Pour en savoir plus, contactez le support de Connecte+. » |
| `DENY_OBJECT_STATE` (organisation archivée) | `AccessDenied` : « Cette organisation est archivée. » bouton « Mes profils ». |
| Hors ligne | Données en cache affichées ; boutons Quitter et Archiver désactivés (`common.offlineAction`). |
| Succès | Toast selon l'action. |

**Textes.**
| Clé | Texte |
|---|---|
| `org.home.activate` | `Agir sous ce profil` |
| `org.home.createdTitle` | `Votre organisation est créée.` |
| `org.home.createdBody` | `Vous en êtes le propriétaire. La prochaine étape recommandée est d'envoyer les pièces de vérification.` |
| `org.home.createdAction` | `Envoyer les pièces` |
| `org.home.roleTitle` | `Votre rôle` |
| `org.home.canTitle` | `Ce que vous pouvez faire` |
| `org.home.verificationTitle` | `Vérification` |
| `org.home.noClaims` | `Aucune mention de vérification pour l'instant.` |
| `org.home.seeDetail` | `Voir le détail` |
| `org.home.publicTitle` | `Profil public` |
| `org.home.seePublic` | `Voir le profil public` |
| `org.home.leaveTitle` | `Quitter l'organisation` |
| `org.home.leaveBody` | `Vous perdrez l'accès à cette organisation. Les offres de l'organisation lui restent.` |
| `org.home.archiveTitle` | `Archiver l'organisation` |
| `org.home.archiveBody` | `Réservé au propriétaire. Les offres de l'organisation ne seront plus visibles.` |
| `org.tabs.overview` | `Aperçu` |
| `org.tabs.profile` | `Profil` |
| `org.tabs.verification` | `Vérification` |
| `org.tabs.team` | `Équipe` |
| `role.OWNER_desc` | `Gère l'organisation, l'équipe, les rôles et l'archivage.` |
| `role.ADMIN_desc` | `Gère le profil, la vérification, l'équipe (sauf les propriétaires), les contacts et les messages.` |
| `role.EDITOR_desc` | `Publie et modifie les offres, répond aux avis et voit qui a demandé à être contacté.` |
| `role.ANALYST_desc` | `Consulte les statistiques et les offres. Ne peut rien modifier.` |
| `capability.edit_profile` | `Modifier le profil de l'organisation` |
| `capability.verification_submit` | `Envoyer les pièces de vérification` |
| `capability.manage_members` | `Gérer l'équipe` |
| `capability.manage_roles` | `Attribuer les rôles` |
| `capability.offers` | `Publier et modifier les offres` |
| `capability.review_reply` | `Répondre aux avis` |
| `capability.view_requesters` | `Voir qui a demandé à contacter l'organisation` |
| `capability.manage_channels` | `Gérer les moyens de contact` |
| `capability.messages` | `Répondre aux messages` |
| `capability.stats` | `Consulter les statistiques` |
| `capability.archive` | `Archiver l'organisation` |

**Accessibilité.** Une seule `<h1>` ; cartes en `<section aria-labelledby>`. Les actions destructives sont des boutons (pas des liens) et ouvrent un `AlertDialog` dont le focus initial est sur « Annuler ».

### 7.3. E5 — Modifier le profil `/organizations/:id/edit`

- **Objectif :** `PATCH organizations/:id/` (multipart). Action principale : « Enregistrer ».
- **Accès :** `org.edit_profile` (propriétaire, administrateur). Éditeur/analyste : la route affiche `AccessDenied` « Seuls le propriétaire et les administrateurs peuvent modifier le profil de l'organisation. » ; l'entrée « Profil » du sous-menu est remplacée par un lien de lecture vers le profil public.
- **Champs :** nom (voir verrou), type (**lecture seule**, affiché en `Badge`, l'API refuse la modification), présentation, catégories, commune, NIF, logo (changer / retirer : `ImageField` + bouton « Retirer le logo » qui envoie `logo = null`).
- **Verrou du nom (A13).** Si l'une des pièces exigées est à l'état `VALIDE` (donnée de `verification.required`), le champ nom est `readOnly` avec le texte « Le nom ne peut plus être modifié car une pièce de vérification a été validée. Pour le changer, contactez le support de Connecte+. » Dans tous les cas, le 409 `name_locked_by_verification` renvoyé par le serveur est affiché sous le champ nom avec le même texte et le nom est remis à sa valeur d'origine (le serveur reste la référence).
- **États :** chargement (`Skeleton` formulaire), erreur de champ, `FormAlert` pour erreur générale, hors ligne (bouton désactivé), enregistrement (spinner), succès (toast « Profil enregistré. » + reste sur la page), `DENY_PERMISSION` (rôle changé entre-temps) → `FormAlert` 9.2 puis rechargement de `contexts/` et de l'organisation.
- **Quitter avec modifications non enregistrées :** `AlertDialog` (patron de `Settings.tsx`).

| Clé | Texte |
|---|---|
| `orgEdit.title` | `Profil de l'organisation` |
| `orgEdit.typeFixed` | `Le type d'organisation ne peut pas être modifié.` |
| `orgEdit.nameLocked` | `Le nom ne peut plus être modifié car une pièce de vérification a été validée. Pour le changer, contactez le support de Connecte+.` |
| `orgEdit.removeLogo` | `Retirer le logo` |
| `orgEdit.save` | `Enregistrer` |
| `orgEdit.saved` | `Profil enregistré.` |
| `orgEdit.readOnly` | `Seuls le propriétaire et les administrateurs peuvent modifier le profil de l'organisation.` |
| `orgEdit.unsavedTitle` | `Quitter sans enregistrer ?` |
| `orgEdit.unsavedBody` | `Vos modifications seront perdues.` |

### 7.4. Parcours « après création »
`OrganizationNew` → `201` → `/organizations/:id` avec l'alerte `org.home.created*`. L'utilisateur n'est **pas** basculé automatiquement sur le nouveau profil : un seul bouton primaire « Agir sous ce profil » le propose. Raison : une bascule automatique changerait le profil sans demande (règle de lisibilité du profil actif).

### 7.5. Quitter l'organisation (tous rôles) — `AlertDialog`
- Titre : « Quitter l'organisation ? » Description : « Vous perdrez immédiatement l'accès à cette organisation, à ses offres et à ses messages. Votre compte personnel et vos propres offres ne changent pas. Les offres de l'organisation lui restent. » Boutons : « Annuler » (focus initial), « Quitter l'organisation ».
- Succès (`204`) : retirer l'organisation de `contexts/` ; si c'était le profil actif, bascule vers le personnel avec `ContextLostAlert` raison `left` (« Vous avez quitté l'organisation. Vous agissez maintenant sous votre profil personnel. ») ; navigation vers `/profiles` ; toast « Vous avez quitté l'organisation. ».
- Erreur `409 last_owner` : le dialogue se ferme, une `Alert` destructive reste dans la page : « Vous êtes le dernier propriétaire : vous ne pouvez pas quitter l'organisation. Un autre propriétaire doit d'abord être nommé, ou l'organisation doit être archivée. » En L0-09, comme la nomination d'un propriétaire n'est pas encore disponible dans l'interface, la seconde option (archivage) n'est offerte qu'aux propriétaires ; le texte reste identique.
- Erreurs `DENY_RELATION` (déjà retiré) : traiter comme un succès côté liste (rafraîchir et rediriger), avec message « Vous ne faites plus partie de cette organisation. »

### 7.6. Archiver l'organisation (propriétaire) — `AlertDialog`
- Titre : « Archiver cette organisation ? » Description : « Les offres de l'organisation ne seront plus visibles. L'archivage ne peut pas être annulé depuis l'application. Tous les membres perdront l'accès à ce profil. » Case à cocher obligatoire « Je comprends » ; bouton « Archiver l'organisation » désactivé tant qu'elle n'est pas cochée ; « Annuler » avec le focus initial.
- Succès : `ARCHIVED` ; même sortie que 7.5 avec raison `archived` ; toast « Organisation archivée. ».

### 7.7. E6 — Équipe `/organizations/:id/team`

**Livré en L0-09 (aucun endpoint de liste de membres n'existe) :**
1. Carte « Votre rôle » (comme 7.2) avec description.
2. `Alert` d'information : « La gestion de l'équipe (inviter, changer un rôle, retirer un membre) n'est pas encore disponible. »
3. Carte « Quitter l'organisation » (7.5).
4. Tableau « Que peut faire chaque rôle ? » : 4 lignes (rôle + description `role.*_desc`), en lecture. Le rôle de l'utilisateur est repéré par `aria-current="true"` et un libellé « Votre rôle ».

**[L1-01] Cible (à implémenter quand les endpoints existent ; ne pas coder avant).**
- En-tête : titre « Équipe », action principale **« Ajouter un membre »** (propriétaire, administrateur).
- Liste des membres (mobile : cartes empilées ; desktop : `Table`) : avatar, nom affiché du compte, `RoleBadge`, depuis le (`joined_at`), menu `⋯` (`DropdownMenu`).
- Menu `⋯` par ligne, selon le rôle de l'utilisateur et celui de la cible :
  | Utilisateur \ cible | Propriétaire | Administrateur | Éditeur | Analyste |
  |---|---|---|---|---|
  | Propriétaire | Changer le rôle, Retirer | Changer le rôle, Retirer | Changer le rôle, Retirer | Changer le rôle, Retirer |
  | Administrateur | aucune action (ligne sans menu, texte « Réservé aux propriétaires ») | Changer le rôle (vers Admin/Éditeur/Analyste), Retirer | idem | idem |
  | Éditeur, Analyste | aucun menu | aucun menu | aucun menu | aucun menu |
  Sur sa propre ligne : l'action est « Quitter l'organisation ».
- « Changer le rôle » : `Dialog`/`Drawer` avec liste radio des rôles autorisés, chacun avec sa description. L'option « Propriétaire » n'est proposée qu'aux propriétaires. Rétrograder le dernier propriétaire → `409 last_owner`.
- « Retirer » : `AlertDialog` « Retirer {{name}} de l'organisation ? Cette personne perdra immédiatement l'accès. Ses offres restent à l'organisation. » Le dernier propriétaire ne peut pas être retiré (`last_owner`).
- Dernier propriétaire : la ligne porte la mention « Dernier propriétaire » (`Badge`), et les actions qui le concernent sont désactivées avec `aria-describedby` vers « Nommez d'abord un autre propriétaire. »
- Aucun e-mail ni téléphone de membre affiché (règle 10).
- Ajout : formulaire par numéro de téléphone ou e-mail d'un compte existant (modalité d'invitation à fixer par L1-01).

| Clé | Texte |
|---|---|
| `team.title` | `Équipe` |
| `team.notAvailable` | `La gestion de l'équipe (inviter, changer un rôle, retirer un membre) n'est pas encore disponible.` |
| `team.rolesTitle` | `Que peut faire chaque rôle ?` |
| `team.yourRole` | `Votre rôle` |
| `team.leaveTitle` | `Quitter l'organisation ?` |
| `team.leaveBody` | `Vous perdrez immédiatement l'accès à cette organisation, à ses offres et à ses messages. Votre compte personnel et vos propres offres ne changent pas. Les offres de l'organisation lui restent.` |
| `team.leaveConfirm` | `Quitter l'organisation` |
| `team.left` | `Vous avez quitté l'organisation.` |
| `team.archiveTitle` | `Archiver cette organisation ?` |
| `team.archiveBody` | `Les offres de l'organisation ne seront plus visibles. L'archivage ne peut pas être annulé depuis l'application. Tous les membres perdront l'accès à ce profil.` |
| `team.archiveConsent` | `Je comprends` |
| `team.archiveConfirm` | `Archiver l'organisation` |
| `team.archived` | `Organisation archivée.` |
| `team.add` **[L1-01]** | `Ajouter un membre` |
| `team.changeRole` **[L1-01]** | `Changer le rôle` |
| `team.remove` **[L1-01]** | `Retirer de l'organisation` |
| `team.removeTitle` **[L1-01]** | `Retirer {{name}} de l'organisation ?` |
| `team.removeBody` **[L1-01]** | `Cette personne perdra immédiatement l'accès. Ses offres restent à l'organisation.` |
| `team.lastOwner` **[L1-01]** | `Dernier propriétaire` |
| `team.ownersOnly` **[L1-01]** | `Réservé aux propriétaires` |
| `team.needAnotherOwner` **[L1-01]** | `Nommez d'abord un autre propriétaire.` |

États de E6 : chargement (`Skeleton` ×2), erreur (`ErrorState`), vide (sans objet en L0-09 ; **[L1-01]** : une organisation a toujours au moins un membre), hors ligne (boutons désactivés), permission refusée (`DENY_RELATION` → `AccessDenied` 7.2).

---

## 8. E7 — Vérification de l'organisation `/organizations/:id/verification`

### 8.1. Objectif et utilisateur
Déposer les pièces de l'organisation et lire exactement ce qui a été vérifié. Utilisateurs : propriétaire et administrateur (dépôt) ; éditeur et analyste (lecture). **Action principale :** « Envoyer » sur la première pièce non fournie.

### 8.2. Règles de rédaction (règle 3, à respecter dans tous les textes)
- On écrit ce qui a été examiné : « RCCM vérifié », « Identification nationale vérifiée », « Représentant vérifié », « Arrêté d'enregistrement vérifié ». Jamais « garanti », « certifié », « sûr », « de confiance », « recommandé », « vendeur vérifié » seul, ni « Vérifié » seul.
- La synthèse « Organisation vérifiée » n'est affichée que si `verification_summary.complete` est vrai, et **toujours suivie de la liste de ses mentions**.
- On ne présente jamais la vérification comme payante, accélérée par un plan ou liée à un rôle.
- Aucune barre de progression en pourcentage de « confiance ». Le décompte porte sur les pièces : « 1 pièce validée sur 3 ».

### 8.3. Structure (mobile puis desktop identiques, colonne `max-w-2xl` ; `AccountShell` + sous-menu de 7)
1. `PageHeader` : titre « Vérification de l'organisation », description « Chaque pièce examinée et validée par notre équipe ajoute une mention précise au profil de l'organisation, par exemple « RCCM vérifié ». Cela indique que le document a été examiné : ce n'est ni une garantie de qualité, ni une recommandation. »
2. Carte « Mentions affichées sur votre profil » : `VerifiedClaims` (mentions + date « vérifiée en octobre 2026 »). Vide : « Aucune mention pour l'instant. » Ligne : « Pièces validées : 1 sur 3. »
3. Bandeau d'information (`Alert` neutre, icône `Info`) : « La vérification ne peut pas être achetée. Aucun abonnement ni paiement ne la fournit. Elle ne dépend pas non plus du rôle des membres. »
4. Liste `<ul>` des pièces exigées pour le type (`verification.required`, dans l'ordre reçu). Chaque ligne (`DocumentRow` extrait de l'existant) : icône, intitulé (clé `kyc.docs.<document_type>.title`), consigne (clé `…description`), état, motif de refus, boutons.
5. Note de confidentialité (`Lock`) : « Vos pièces sont conservées dans un espace privé, accessibles uniquement aux personnes habilitées de l'équipe de vérification. Elles ne sont jamais publiées et jamais visibles par les autres membres de l'organisation. » (Le fichier n'est jamais renvoyé par l'API.)
6. Si le rôle n'a pas `org.verification_submit` : `Alert` « Seuls les administrateurs principaux et les administrateurs peuvent envoyer des pièces, en consulter le détail et lire les motifs de refus. » et aucun bouton d'envoi ni de suppression.

### 8.4. États d'une pièce (`state` de `verification.required`)
| État | Pastille | Texte | Actions (si `org.verification_submit`) |
|---|---|---|---|
| `NONE` | neutre | `Non envoyée` | « Envoyer » |
| `EN_ATTENTE` | `Clock`, ton warning | `En cours d'examen · envoyée {{date}}` | « Supprimer » |
| `VALIDE` | `CheckCircle2`, ton success | `Validée` + mention (ex. « RCCM vérifié ») | aucune (serveur : 409 si suppression) |
| `REFUSE` | `XCircle`, ton destructif | `Refusée` + « Motif du refus : … » (`rejection_reason`) | « Envoyer à nouveau », « Supprimer » |

Source des pièces et motifs : `GET organizations/:id/kyc/documents/`, réservé depuis L1-01-B6 aux rôles qui ont `org.verification_submit` (administrateur principal, administrateur) ; les autres rôles ne voient que l'état agrégé et le motif n'est jamais affiché (champs `document_type_label`, `status`, `rejection_reason`, `uploaded_at`, `reviewed_at`). La pièce la plus récente par type l'emporte. Aucune URL de fichier n'est affichée (le serveur n'en renvoie pas).

### 8.5. Envoi d'une pièce
- Contrôles locaux avant envoi (patron actuel) : PDF, JPG ou PNG ; 10 Mo maximum. Messages : « Formats acceptés : PDF, JPG ou PNG. » et « Fichier trop lourd ({{size}}). 10 Mo maximum. »
- Envoi : bouton désactivé + `Loader2` + texte « Envoi en cours, ne fermez pas la page. »
- Pas de compression automatique des pièces (lisibilité d'un document d'identité). Le poids affiché aide l'utilisateur ; voir D5 en section 14.
- Erreurs : 400 type non exigé (« Cette pièce n'est pas demandée pour ce type d'organisation. »), 403 `DENY_PERMISSION`, réseau (« L'envoi a échoué. Vérifiez votre connexion puis réessayez. » ; le fichier doit être re-sélectionné), 429 throttle.
- **Pas d'envoi différé** hors ligne : une pièce d'identité n'est pas mise en file dans le navigateur. Bouton désactivé hors ligne avec `common.offlineAction`.

### 8.6. États de la page
| État | Comportement |
|---|---|
| Chargement | `Skeleton` de la carte de synthèse + 3 lignes. |
| Vide | Sans objet (les pièces exigées sont toujours listées). Si la liste d'exigences du type est vide (configuration back-office), `EmptyState` : « Aucune pièce n'est demandée pour ce type d'organisation pour le moment. » et aucune synthèse n'est affichée (`summary.label` est nul). |
| Erreur | `ErrorState` + « Réessayer ». |
| Hors ligne | Lecture seule ; boutons désactivés. |
| Permission refusée | `DENY_RELATION` → `AccessDenied` ; `DENY_PERMISSION` à l'envoi → message 9.2 + actualisation des capacités. |
| Succès | Toast « Pièce envoyée. Elle sera examinée par notre équipe. » ; la ligne passe à `EN_ATTENTE`. |

### 8.7. Textes
| Clé | Texte |
|---|---|
| `verif.title` | `Vérification de l'organisation` |
| `verif.description` | `Chaque pièce examinée et validée par notre équipe ajoute une mention précise au profil de l'organisation, par exemple « RCCM vérifié ». Cela indique que le document a été examiné : ce n'est ni une garantie de qualité, ni une recommandation.` |
| `verif.claimsTitle` | `Mentions affichées sur votre profil` |
| `verif.noClaims` | `Aucune mention pour l'instant.` |
| `verif.claimDate` | `vérifiée en {{date}}` |
| `verif.validatedCount_one` | `{{count}} pièce validée sur {{total}}` |
| `verif.validatedCount_other` | `{{count}} pièces validées sur {{total}}` |
| `verif.notPaid` | `La vérification ne peut pas être achetée. Aucun abonnement ni paiement ne la fournit. Elle ne dépend pas non plus du rôle des membres.` |
| `verif.privacy` | `Vos pièces sont conservées dans un espace privé, accessibles uniquement aux personnes habilitées de l'équipe de vérification. Elles ne sont jamais publiées et jamais visibles par les autres membres de l'organisation.` |
| `verif.readOnly` | `Seuls les administrateurs principaux et les administrateurs peuvent envoyer des pièces, en consulter le détail et lire les motifs de refus.` |
| `verif.noRequirements` | `Aucune pièce n'est demandée pour ce type d'organisation pour le moment.` |
| `verif.state.NONE` | `Non envoyée` |
| `verif.state.EN_ATTENTE` | `En cours d'examen` |
| `verif.state.VALIDE` | `Validée` |
| `verif.state.REFUSE` | `Refusée` |
| `verif.sentOn` | `envoyée {{date}}` |
| `verif.rejectionReason` | `Motif du refus : ` |
| `verif.send` | `Envoyer` |
| `verif.sendAgain` | `Envoyer à nouveau` |
| `verif.sending` | `Envoi en cours, ne fermez pas la page.` |
| `verif.sent` | `Pièce envoyée. Elle sera examinée par notre équipe.` |
| `verif.badFormat` | `Formats acceptés : PDF, JPG ou PNG.` |
| `verif.tooHeavy` | `Fichier trop lourd ({{size}}). 10 Mo maximum.` |
| `verif.notRequired` | `Cette pièce n'est pas demandée pour ce type d'organisation.` |
| `verif.sendFailed` | `L'envoi a échoué. Vérifiez votre connexion puis réessayez.` |
| `verif.cannotDeleteValidated` | `Une pièce validée ne peut pas être supprimée.` |
| `kyc.docs.RCCM.title` | `Registre du commerce (RCCM)` |
| `kyc.docs.RCCM.description` | `Extrait ou certificat d'immatriculation de l'organisation.` |
| `kyc.docs.ID_NATIONALE.title` | `Identification nationale` |
| `kyc.docs.ID_NATIONALE.description` | `Attestation d'identification nationale de l'organisation.` |
| `kyc.docs.PIECE_GERANT.title` | `Pièce d'identité du représentant` |
| `kyc.docs.PIECE_GERANT.description` | `Carte d'électeur, passeport ou permis de conduire en cours de validité.` |
| `kyc.docs.ARRETE_ONG.title` | `Arrêté d'enregistrement` |
| `kyc.docs.ARRETE_ONG.description` | `Arrêté ou acte d'enregistrement de l'association ou de l'ONG.` |
| `claims.RCCM_VERIFIED` | `RCCM vérifié` |
| `claims.NATIONAL_ID_VERIFIED` | `Identification nationale vérifiée` |
| `claims.REPRESENTATIVE_VERIFIED` | `Représentant vérifié` |
| `claims.NGO_DECREE_VERIFIED` | `Arrêté d'enregistrement vérifié` |
| `claims.summary` | `Organisation vérifiée` |
| `claims.helpTrigger` | `Que signifie cette mention ?` |
| `claims.helpTitle` | `Ce que signifie une mention de vérification` |
| `claims.helpBody` | `Chaque mention indique qu'un document précis a été examiné par l'équipe de Connecte+ à la date indiquée. Elle ne garantit ni la qualité des produits ou services, ni la solvabilité, ni le comportement de l'organisation. La vérification ne peut pas être achetée.` |
| `claims.unknown` | (fallback : afficher `label` renvoyé par l'API si le code n'est pas dans le dictionnaire) |

Le libellé de pièce `document_type` inconnu : afficher `document_type_label` de l'API (jamais le code brut).

### 8.8. Accessibilité
`<ul>` de pièces ; l'état est un texte avec icône (pas de couleur seule) ; le bouton « Envoyer » a `aria-label="Envoyer : {{titre}}"` (patron existant) ; l'`<input type="file">` reste `sr-only` avec `tabIndex={-1}` et la même étiquette ; après suppression, le focus revient au titre de la ligne. `AlertDialog` de suppression : patron existant (`kyc.deleteConfirm*`, `common.cancel`).

### 8.9. Réseau faible
Deux requêtes (`verification/` incluse dans `OrganizationInternal`, `kyc/documents/` seulement avec `org.verification_submit`). Aucune image. Fichiers jusqu'à 10 Mo : message d'attente explicite et possibilité de renvoyer.

---

## 9. E13 — Erreurs `DENY_*` et codes métier

### 9.1. Principe
`lib/api-errors.ts` extrait `response.data.code` (réponse `{"detail","code"}`, ADR §9). Le texte affiché vient **des clés i18n**, pas du `detail` serveur (déjà en français, mais sans nom de profil ni contexte : le front ajoute le nom connu localement). Aucun message n'affiche le nom d'une autre personne.

**Règle de traitement des 4 codes qui concernent le profil actif (`DENY_CONTEXT`, `DENY_RELATION`, `DENY_SECURITY`, `DENY_OBJECT_STATE`)** pour une requête qui portait `X-Context` :
1. Recharger `contexts/` immédiatement.
2. Si le profil actif **n'y figure plus** : retour forcé au personnel + `ContextLostAlert` (texte colonne « Profil perdu » du tableau 9.2).
3. S'il y figure encore : le refus est local à l'action ; afficher le texte colonne « Action refusée » à l'endroit de l'action (`FormAlert`, `Alert` ou toast d'erreur) et ne pas changer de profil.
Cette règle évite de deviner la cause : la liste du serveur fait foi.

### 9.2. Codes d'autorisation (403)
| Code | Profil perdu (`ContextLostAlert`, persistant) | Action refusée (local) |
|---|---|---|
| `DENY_CONTEXT` | `Le profil sélectionné n'est pas disponible. Vous agissez maintenant sous votre profil personnel.` | `Cette action n'est pas possible avec le profil sélectionné.` |
| `DENY_RELATION` | `Vous ne faites plus partie de cette organisation. Vous agissez maintenant sous votre profil personnel.` | `Vous n'avez pas accès à cet élément.` |
| `DENY_PERMISSION` | (ne fait jamais perdre le profil) | `Votre rôle ne permet pas cette action. Demandez à un propriétaire ou à un administrateur de l'organisation.` (hors organisation : `Vous n'avez pas le droit d'effectuer cette action.`) |
| `DENY_SECURITY` | `Cette organisation est suspendue. Vous agissez maintenant sous votre profil personnel.` | `Cette action est temporairement impossible : le compte ou l'organisation est limité. Contactez le support de Connecte+.` |
| `DENY_OBJECT_STATE` | `Ce profil est archivé. Vous agissez maintenant sous votre profil personnel.` | `Cet élément n'est plus dans un état qui permet cette action.` |

Cas particuliers :
- `DENY_OBJECT_STATE` sur modification du profil prestataire : « Votre profil prestataire est désactivé. Réactivez-le pour le modifier. » avec bouton « Réactiver ».
- `DENY_RELATION` sur la modification d'une offre dont on était l'auteur : « Vous ne faites plus partie de l'organisation propriétaire de cette offre. »
- `DENY_PERMISSION` : après affichage, recharger `contexts/` (le rôle a peut-être changé) pour réaligner les boutons masqués.
- Les 401 gardent le comportement actuel de déconnexion / rafraîchissement du jeton.

### 9.3. Codes métier
| Code | HTTP | Où | Texte |
|---|---|---|---|
| `last_owner` | 409 | quitter ; **[L1-01]** rétrograder/retirer | `Vous êtes le dernier propriétaire : vous ne pouvez pas quitter l'organisation. Un autre propriétaire doit d'abord être nommé, ou l'organisation doit être archivée.` Variante **[L1-01]** pour rétrogradation/retrait : `Une organisation doit toujours avoir au moins un propriétaire.` |
| `organization_limit_reached` | 409 | création | `Vous avez atteint le nombre maximal d'organisations pour un compte. Quittez ou archivez une organisation pour en créer une nouvelle.` (le plafond est un réglage : le chiffre n'est pas codé en dur) |
| `phone_verification_required` | 403 | création | `Vérifiez d'abord votre numéro de téléphone de connexion pour créer une organisation.` + bouton « Vérifier mon numéro » → `/settings` |
| `name_locked_by_verification` | 409 | modification | `Le nom ne peut plus être modifié car une pièce de vérification a été validée. Pour le changer, contactez le support de Connecte+.` |
| `seller_not_settable` | 400 | publication | (erreur de programmation : le front n'envoie jamais de vendeur) `L'opération n'a pas abouti. Réessayez.` + journal console en développement |
| `provider_not_found` | 404 | `provider/` | pas une erreur : état « non activé » |
| `channel_not_allowed` | 4xx | révélation de contact | clé existante ; pas de changement |
| 429 | 429 | création d'organisation, envoi de pièces | `errors.tooManyAttempts*` existants |
| réseau | — | partout | `errors.network` |

### 9.4. Clés
`errors.deny.CONTEXT.lost`, `errors.deny.CONTEXT.action`, `errors.deny.RELATION.lost`, `errors.deny.RELATION.action`, `errors.deny.PERMISSION.org`, `errors.deny.PERMISSION.generic`, `errors.deny.SECURITY.lost`, `errors.deny.SECURITY.action`, `errors.deny.OBJECT_STATE.lost`, `errors.deny.OBJECT_STATE.action`, `errors.code.last_owner`, `errors.code.last_owner_demote`, `errors.code.organization_limit_reached`, `errors.code.phone_verification_required`, `errors.code.name_locked_by_verification`, `errors.code.seller_not_settable`, avec les textes des tableaux ci-dessus. Raisons de `ContextLostAlert` supplémentaires : `errors.lost.left` (« Vous avez quitté l'organisation. Vous agissez maintenant sous votre profil personnel. ») et `errors.lost.archived` (« L'organisation est archivée. Vous agissez maintenant sous votre profil personnel. »). Bouton : `errors.lost.dismiss` (« J'ai compris »). Titre : `errors.lost.title` (« Votre profil actif a changé »).

### 9.5. Accessibilité
`role="alert"` pour `ContextLostAlert` et `FormAlert` ; le titre de l'`Alert` est un vrai titre (`AlertTitle`). Le bouton de fermeture a un nom accessible. Après un retour forcé, le focus va sur l'alerte (`tabIndex={-1}` + `focus()`).

---

## 10. E9 — Type de vendeur et mentions de vérification (offres et profils publics)

### 10.1. Objectif
Dire à chaque endroit qui vend (CDC §3.3 : le type de vendeur est toujours visible) et ce qui a été vérifié, sans score de confiance (règle 4) et sans confondre promotion et classement (règle 5).

### 10.2. Objet vendeur (ADR §9.6)
`seller = { context_type: USER|PROVIDER|ORGANIZATION, context_id, display_name, photo, org_type, verified_claims[], verification_summary{complete,label}, member_since }`. Disparaissent : `id`, `full_name`, `user_type`, `date_joined`, `business_profile`, `is_verified`.

### 10.3. `SellerTypeBadge`
| `context_type` | Forme complète | Forme compacte (cartes d'offre) | Icône (lucide) |
|---|---|---|---|
| `USER` | `Particulier` | `Particulier` | `UserRound` |
| `PROVIDER` | `Prestataire` | `Prestataire` | `Briefcase` |
| `ORGANIZATION` | `Organisation · {{orgType}}` (ex. « Organisation · Boutique ») | `{{orgType}}` (ex. « Boutique ») | `Building2` |
Style : `Badge variant="outline"` neutre, jamais vert (le vert est réservé à « vérifié »). Le texte est toujours présent (pas d'icône seule).

### 10.4. `VerifiedClaims`
- Forme **complète** (profil vendeur, `SellerCard`, E4/E7) : une pastille par mention (`BadgeCheck` + `claims.<CODE>`), ton `success` du `StatusBadge` actuel ; si `summary.complete` : ligne en tête « Organisation vérifiée » **suivie** des pastilles ; bouton texte « Que signifie cette mention ? » → `Popover` avec `claims.helpBody`.
- Forme **compacte** (`PostCard`, annuaire) : au plus 2 pastilles puis « +N » (`aria-label` « et N autre(s) mention(s) de vérification ») ; pas de ligne de synthèse isolée. Aucune pastille si pas de mention (pas de « Non vérifié »).
- Date : `title`/texte « vérifiée en {{date}} » (`formatMonthYear(verified_at)`) dans la forme complète seulement.
- Interdits : `StatusBadge kind="verified"`, tout libellé « Vérifié » seul, tout classement ou tri par vérification, toute étoile ou jauge de confiance.

### 10.5. `SellerCard` (fiche d'offre)
Structure : avatar (carré si organisation, rond sinon) + nom (lien) → `SellerTypeBadge` (forme complète) → `VerifiedClaims` (complète) → `RatingBlock kind="seller"` (existant, **note de ce vendeur uniquement**, avec « Sur Connecte+ depuis {{date}} », source `member_since`) → actions de contact existantes.
- Lien du nom : `/seller/{type en minuscules}/{context_id}`.
- Les anciens usages `seller.business_profile?.logo`, `seller.user_type === "ENTREPRISE"` et `sellerDisplayName/isSellerVerified` (`lib/post.ts`) sont remplacés par `seller.photo`, `seller.context_type`, `seller.display_name`, `seller.verified_claims`.
- **Organisation : canal Message seul.** Quand `allowed_channels` de l'offre est `["MESSAGE"]`, `ContactActions` n'affiche **que** « Message » (aucun bouton Appeler/WhatsApp grisé) et, sous les actions : « Cette organisation se contacte par message dans Connecte+. » (`contact.orgMessageOnly`). Le front ne déduit rien du type de vendeur : il suit `allowed_channels` du serveur (qui tient compte de l'interrupteur `org_phone_channels_enabled`). Un compte qui est membre actif de l'organisation vendeuse ne voit pas les boutons de contact (le serveur refuse ; message : « Vous ne pouvez pas contacter votre propre organisation. »).
- `Rating` : texte inchangé (« Note du vendeur »). Aucun score universel : la note n'est jamais agrégée entre les profils d'une même personne (règle 4).

### 10.6. `PostCard`
Ligne vendeur sous le titre : `UserAvatar size="xs"` + `display_name` tronqué + `SellerTypeBadge compact`. Si l'offre est promue, le badge `StatusBadge kind="sponsored"` « Sponsorisé » reste sur l'image, **sans lien avec** les mentions de vérification (séparation promotion/classement/vérification : règles 3 et 5).

### 10.7. Profil public `/seller/:contextType/:id` (`pages/SellerProfile.tsx`)
Source : `GET marketplace/sellers/<user|provider|organization>/<uuid>/` (ADR §9.7). `/u/:id` devient une redirection vers `/seller/user/:id`.
Structure (mobile : colonne ; desktop : en-tête en ligne puis grille d'offres) :
1. Avatar 80 px + nom (`<h1>`) + `SellerTypeBadge` complète.
2. `VerifiedClaims` complète.
3. Ligne « Sur Connecte+ depuis {{date}} » ; commune si présente (organisation).
4. `RatingBlock kind="seller"` (`seller_rating`).
5. Présentation (`description`) si non vide.
6. Compteur « {{count}} offre(s) active(s) » (`active_offers_count`).
7. Grille des offres du vendeur (`GET posts/?seller=<id>&seller_type=<TYPE>`), `PostCard`.
Pas de bouton de contact sur le profil (le contact se fait depuis une offre) ; pas d'adresse, téléphone, e-mail, liste de membres (jamais fournis par l'API).
États : chargement (`Skeleton` en-tête + `PostCardSkeleton` ×6) ; erreur (`ErrorState`) ; 404 (`EmptyState` icône `SearchX` « Ce vendeur n'existe pas ou n'est plus visible. » + lien « Voir le marketplace ») ; aucune offre (`EmptyState` « Aucune offre active pour le moment. ») ; hors ligne (page en cache).
Textes : `seller.type.USER` « Particulier », `seller.type.PROVIDER` « Prestataire », `seller.type.ORGANIZATION` « Organisation · {{orgType}} », `seller.typeCompact.ORGANIZATION` « {{orgType}} », `seller.offersCount_one` « {{count}} offre active », `seller.offersCount_other` « {{count}} offres actives », `seller.noOffers` « Aucune offre active pour le moment. », `seller.notFound` « Ce vendeur n'existe pas ou n'est plus visible. », `contact.orgMessageOnly` « Cette organisation se contacte par message dans Connecte+. », `contact.ownOrg` « Vous ne pouvez pas contacter votre propre organisation. ».

Le nom d'un compte personnel est celui du serveur (« Marie K. ») ; le front n'essaie jamais de reconstituer un nom complet.

### 10.8. Accessibilité
`SellerTypeBadge` et `VerifiedClaims` ont un texte lisible par lecteur d'écran (pas d'`aria-hidden` sur le libellé). Les pastilles sont dans une `<ul aria-label="Vérifications">`. `Popover` d'aide : bouton avec `aria-expanded`, contenu `role="dialog"` géré par Radix, Échap ferme.

### 10.9. Réseau faible
Avatars et logos avec `ImageWithFallback` (initiales sans image) ; tailles ≤ 80 px ; aucun appel supplémentaire : `seller` est déjà dans l'objet offre. Le profil public est une requête + une liste paginée.

---

## 11. E10, E11 — Annuaire et inscription

### 11.1. E10 — Annuaire (`/businesses`, `pages/Businesses.tsx`)
- Titre : eyebrow « Organisations », titre « Les organisations de Kinshasa », description « Entreprises, boutiques, ONG et organisateurs d'événements inscrits sur Connecte+. Les mentions indiquent précisément quels documents ont été examinés. Le tri est alphabétique. »
- Filtres (au-dessus de la liste) : recherche texte (existante), puces de type (`orgType.*`, sélection unique, « Tous » par défaut), `Select` « Mention de vérification » (« Toutes », puis les 4 codes `claims.*`), `Switch` « Toutes les pièces exigées sont vérifiées » (paramètre `fully_verified=true`). Remplace le `Switch` « Vérifiées uniquement ».
- Carte : logo carré, nom, commune (`MapPin`), `SellerTypeBadge compact`, `VerifiedClaims compact`, présentation 3 lignes, « Voir le profil » → `/seller/organization/:id`.
- Source : `GET organizations/` paginé (`page`, `page_size`, `search`, `org_type`, `claim`, `fully_verified`), bouton « Voir plus d'organisations » (existant, clé `businesses.loadMore` à renommer). Navigation : libellé `nav.businesses` « Entreprises » → « Organisations ». À valider (D6).
- États : chargement (`Skeleton` ×6), vide « Aucune organisation ne correspond à votre recherche. » avec action « Effacer les filtres », erreur (`ErrorState`), hors ligne (cache), pas de promotion dans cette liste.
- Clés : `directory.eyebrow`, `directory.title`, `directory.description`, `directory.filterType`, `directory.filterClaim`, `directory.filterClaimAll`, `directory.filterFully`, `directory.empty`, `directory.clear`, `directory.loadMore` (« Voir plus d'organisations »).

### 11.2. E11 — Inscription
- Retirer le groupe « Vous êtes » (cartes Particulier/Entreprise), le champ « Nom de l'entreprise », `user_type` et `business_profile` du schéma Zod et de la charge utile (`createAccount`).
- Étapes (Stepper « Votre compte » → « Vérification ») et OTP inchangés. Bouton principal inchangé.
- Sous le titre : description « Gratuit, en moins d'une minute. » (inchangée). Ajouter sous le formulaire, au-dessus du bouton, une ligne d'aide : « Un seul compte suffit. Vous pourrez ensuite activer un profil prestataire ou créer une organisation depuis « Mes profils ». » (`register.oneAccount`).
- Toast de bienvenue : titre « Bienvenue sur Connecte+ ! », description « Votre compte est prêt. Vous pouvez activer un profil prestataire ou créer une organisation depuis « Mes profils ». » (`register.welcomeDescription`). Plus de message conditionné au type.
- Redirection après inscription : inchangée (`next`).

---

## 12. E12 — Adaptation des écrans existants au profil actif

### 12.1. Navigation
- **Navbar** : voir E1. Le nom affiché dans le menu avatar = `user.full_name`. Ajouter « Mes profils ». Le bouton « Publier » (desktop) n'est affiché que si `useCan("offer.publish")`.
- **BottomNav** : l'item central « Publier » n'est affiché que si `useCan("offer.publish")` ; sinon la grille passe à `grid-cols-4` (Accueil, Explorer, Messages, Profil). « Messages » n'est affiché que si le profil actif a `message.reply` (profil personnel et prestataire : toujours ; organisation : propriétaire et administrateur).
- **AccountShell** : la carte d'identité latérale montre `active.name` et `context.type.*` à la place de « Compte entreprise / Compte particulier ». Items : « Vérification » devient visible seulement si le profil actif est une organisation et renvoie vers `/organizations/{id}/verification` ; ajout de « Mes profils ». Les items dépendants d'une capacité absente sont masqués : « Messages » (`message.reply`), « Tableau de bord » (`stats.view`), « Corbeille » (`offer.view_internal`).
- `BottomNav` et menus mobiles conservent un libellé « Profil » ; le bandeau du profil actif reste visible.

### 12.2. Tableau de bord, corbeille, mes offres
- En-tête de page : sous le titre, ligne `ActiveContextBanner`-like « Offres et statistiques de : {{name}} ».
- Actions d'offre (modifier, mettre en pause, renouveler, vendue, corbeille) masquées si pas `offer.edit` / `offer.delete` (analyste : lecture seule, texte « Votre rôle permet de consulter ces offres, pas de les modifier. »).
- « Qui a demandé » : masqué sans `contact.view_requesters` (analyste) ; à la place, les compteurs du tableau de bord.
- Réponse aux avis : bouton masqué sans `review.reply`. La réponse affiche le nom de l'organisation, jamais celui du membre.
- Statistiques sans `stats.view` : `AccessDenied` (cas théorique : tous les rôles ont `stats.view`).

### 12.3. États vides dépendants du profil
- Tableau de bord, « Mes offres », corbeille en **profil personnel** alors que le compte est membre d'au moins une organisation et n'a aucune offre personnelle : `EmptyState` avec, en plus de l'action « Publier », une phrase « Vos offres d'entreprise se trouvent peut-être sous une organisation. » et un lien « Changer de profil » qui ouvre le sélecteur. Clé : `emptyOffers.otherProfiles`. (Réduit la confusion après la migration des anciens comptes, section 13.)

### 12.4. Éditeur d'offre (`PostEditor`)
- En haut du formulaire, ligne non modifiable : « Publication au nom de : {{name}} · {{typeLabel}} » avec lien « Changer » (sélecteur ; confirmation si le formulaire est modifié). En édition : « Offre de : {{name}} » (nom du vendeur de l'offre, sans lien « Changer »).
- Le corps de la requête ne contient **aucun** champ vendeur (`seller*`, `created_by`) : le serveur déduit le vendeur de `X-Context`.
- Erreurs : `DENY_PERMISSION` (analyste qui contournerait l'interface) → message 9.2 ; `DENY_OBJECT_STATE` (prestataire archivé) → « Votre profil prestataire est désactivé. Réactivez-le pour publier. » avec lien vers E2 ; `DENY_RELATION` (révoqué) → retour forcé au personnel, le brouillon n'est pas envoyé en personnel (aucune écriture sous un autre profil que celui affiché).
- Un brouillon rempli n'est jamais republié automatiquement sous un autre profil.

### 12.5. Messages et réglages de contact
- **Messages** sous un profil organisation : liste = conversations de l'organisation (`X-Context`). Réservé à `message.reply` (propriétaire, administrateur). Éditeur/analyste : `AccessDenied` « Les messages de l'organisation sont réservés au propriétaire et aux administrateurs. ». Les messages envoyés par l'organisation s'affichent sous le nom de l'organisation (`sender_name`), jamais sous le nom du membre.
- **Réglages de contact** (`ContactSettingsSection`, onglet « Coordonnées » de `Settings`) : le profil actif organisation ouvre les réglages **de l'organisation** (`contact-settings/` avec `X-Context`), réservés à `contact.manage_channels`. En-tête de section : « Contact avec les acheteurs — {{name}} ». Éditeur/analyste : `AccessDenied` (« Seuls le propriétaire et les administrateurs gèrent les moyens de contact. »).
  - Tant que l'appel et WhatsApp sont fermés pour les organisations, la section n'affiche **que** le canal « Message dans Connecte+ » (actif, non désactivable ici) et le texte : « Les appels et WhatsApp ne sont pas encore proposés pour les organisations. Les acheteurs vous écrivent par message ; aucun numéro n'est transmis. » (`contactSettings.orgMessageOnly`). Le front ne code pas l'interrupteur en dur : il masque Appel/WhatsApp quand la réponse serveur ne les propose pas (voir Q-F3).
  - Le numéro personnel du membre n'est jamais proposé comme numéro de l'organisation (pas de « Utiliser mon numéro de connexion » en profil organisation).
- **Écrans toujours personnels** (contact d'un vendeur, révélation de numéro, avis, favoris, signalement, notifications, `me/`) : aucune dépendance au profil actif. Quand le profil actif n'est pas personnel, ajouter sous le bouton d'envoi de `ReviewForm`, dans `ContactRevealDialog`, et en tête de `Favorites` la ligne `context.alwaysPersonal` : « Cette action est toujours faite avec votre profil personnel. » (le front sait que l'en-tête est ignoré, ADR §6.4).
- **Notifications** : liste unique du compte ; chaque élément rattaché à une organisation affiche une étiquette `Badge` avec le nom du profil (`context.name`) ; un clic ouvre la cible sans changer le profil actif (sauf si la cible n'est lisible que sous ce profil : alors demander « Ouvrir sous le profil {{name}} ? »). Les notifications d'une organisation quittée disparaissent (supprimées côté serveur).

### 12.6. Paramètres (`Settings`)
- Retirer l'onglet « Boutique » (`business_profile.*`). Onglets : Profil, Coordonnées, Sécurité.
- Dans « Profil » : sous le nom, un lien « Gérer mes profils (prestataire, organisations) » → `/profiles`.
- Dans « Coordonnées » : si le téléphone de connexion n'est pas vérifié, le bouton « Vérifier mon numéro » de E3 arrive ici.

---

## 13. E14 — Migration des anciens comptes entreprise

### 13.1. Contexte
Les comptes qui avaient un profil entreprise reçoivent une organisation de type Entreprise dont ils sont propriétaires (ADR §10.3). Offres, avis, pièces de vérification et statistiques sont repris par l'organisation. Leur numéro et consentement de contact personnels **ne sont pas** repris : l'organisation n'offre que le canal Message. Leur profil personnel n'a plus d'offres.

### 13.2. Affichage
`LegacyOrgNotice` : `Alert` d'information (non destructif, icône `Info`), fermable (« J'ai compris »), mémorisation locale `connecte.legacyNotice.<orgId>`. Affiché pour chaque organisation migrée, dans E2 (en tête), E4 et le tableau de bord (profil personnel). Détection : champ à fournir par le serveur (question Q-F2) ; sans lui, le message ne peut pas être ciblé.

### 13.3. Textes
| Clé | Texte |
|---|---|
| `legacy.title` | `Votre compte entreprise est devenu une organisation` |
| `legacy.body` | `« {{name}} » est maintenant une organisation dont vous êtes le propriétaire. Vos offres, vos avis et vos pièces de vérification y ont été conservés. Pour publier ou gérer vos offres, choisissez ce profil dans « Agir en tant que ».` |
| `legacy.contact` | `Pour l'instant, les acheteurs contactent l'organisation par message dans Connecte+. L'appel et WhatsApp ne sont pas repris : votre numéro personnel n'est jamais transmis au nom de l'organisation.` |
| `legacy.action` | `Agir sous ce profil` |
| `legacy.dismiss` | `J'ai compris` |

Action principale du message : « Agir sous ce profil » ; « J'ai compris » est secondaire.

---

## 14. Décisions de design à valider

| # | Décision | Pourquoi | Alternative |
|---|---|---|---|
| D1 | Le mot « contexte » n'est jamais affiché ; l'interface parle de « profil actif » et « Agir en tant que ». | Compréhensible en français courant. | « Mode » ou « Compte » (ambigu avec le compte unique). |
| D2 | Mobile : bandeau du profil actif h-9, **toujours** visible pour un utilisateur connecté, dans le header fixe. Desktop : pastille dans la barre, bandeau seulement hors profil personnel. | CDC §3.1 : le contexte actif est toujours affiché ; sur 360 px la barre n'a pas la place d'une pastille. Coût : 36 px de hauteur utile sur mobile (`AppShell` à ajuster). | Pastille dans la barre sur mobile (rejetée : ne tient pas à côté du logo, de la cloche et du menu). |
| D3 | L'activation du profil prestataire passe par un petit formulaire (nom affiché pré-rempli, public) plutôt qu'un appel direct. | Évite de publier par défaut le nom complet du compte alors que le profil personnel affiche « Marie K. » (règle 10). | Activation en un tap avec le nom du compte, modifiable ensuite (moins d'étapes, mais publication involontaire). |
| D4 | Après création d'une organisation, **pas de bascule automatique** : un bouton « Agir sous ce profil ». | Le profil actif ne change que par un geste explicite. | Bascule automatique (plus rapide, mais l'utilisateur peut publier au mauvais nom). |
| D5 | Aucune compression des pièces de vérification (PDF/JPG/PNG, 10 Mo max), message d'attente explicite, pas d'envoi différé. | Lisibilité des pièces d'identité ; action sensible. Coût sur 3G : un envoi de plusieurs Mo peut échouer, l'utilisateur doit renvoyer. | Compresser les images à 2000 px / qualité 0,85 avec `compressImage`. |
| D6 | « Entreprises » devient « Organisations » dans la navigation et l'annuaire ; la route `/businesses` est conservée. | L'annuaire contient aussi boutiques, ONG et organisateurs d'événements. | Garder « Entreprises » (inexact pour une ONG). |
| D7 | Mémorisation locale du profil actif avec nom mémorisé, liée à l'identifiant du compte, sans synchronisation entre onglets. | Q-CP4 ; affichage immédiat en 3G ; pas de fuite entre comptes sur un même téléphone. | Mémorisation en `sessionStorage` (oublie au rechargement de l'onglet). |
| D8 | Un retour forcé au profil personnel se signale par une `Alert` persistante fermable (pas par un toast). | « Jamais de repli silencieux » : le message doit rester lisible malgré la lenteur du réseau. | Toast de 5 s (peut être manqué). |
| D9 | Le masquage suit `capabilities` du serveur ; aucun rôle n'est codé en dur dans le front. Les libellés de capacités (section 7.2) sont des textes, pas des règles. | Doc 06 §24 : l'interface ne décide jamais. Un changement de matrice ne demande pas de modifier le front. | Tableau de permissions dupliqué dans le front (risque de divergence). |
| D10 | Un « Quitter l'organisation » est proposé même au possible dernier propriétaire : le refus `last_owner` est traité par un message. | Aucune donnée ne dit combien de propriétaires existent (pas de liste de membres en L0-09). | Griser le bouton (impossible sans liste). |
| D11 | Écran « Équipe » réduit en L0-09 (rôle, quitter, description des rôles) ; écran cible décrit mais marqué [L1-01]. | Aucun endpoint de gestion de membres dans l'ADR 0006 §9. | Livrer des écrans sans endpoint (impossible). |

---

## 15. Questions ouvertes

### 15.1. Pour l'utilisateur (client)
1. **Q-CLI1/D11 :** le client accepte-t-il que, en V1-lot 0, l'équipe ne se gère pas dans l'interface (uniquement « Quitter ») ? Sinon, avancer L1-01.
2. **Q-CLI2 :** les pièces par type (valeurs provisoires de l'ADR §4.3) sont reprises telles quelles dans les textes `kyc.docs.*`. À confirmer, notamment « Pièce d'identité du représentant » (ex-« gérant »).
3. **Q-CLI5 :** les libellés `contact.orgMessageOnly` et `contactSettings.orgMessageOnly` supposent l'interrupteur fermé. À reprendre à son ouverture.
4. **Q-CLI8 / A13 :** le texte de verrouillage du nom renvoie au « support de Connecte+ » : existe-t-il un point de contact à citer (adresse, page) ? Aucune page de support n'existe dans le front.
5. **Q-CLI4 :** le texte du plafond évite le chiffre (réglable). Le client veut-il l'afficher ?
6. Les organisations **suspendues ou archivées** disparaissent de « Mes profils » (le serveur ne les liste pas). Faut-il les montrer, en lecture seule, avec leur statut ? Cela demande un champ ou un endpoint supplémentaire.

### 15.2. Pour le backend / l'architecte (contrat à compléter avant F1)
- **Q-F1 :** `me/` doit exposer `phone_verified` (booléen) pour afficher le garde-fou de E3 avant l'envoi. Sinon le message n'apparaît qu'après le 403.
- **Q-F2 :** un indicateur d'organisation issue d'un ancien compte entreprise (par exemple `migrated_from_business_profile: true` sur l'élément `ORGANIZATION` de `contexts/`, retiré avec `LegacyAccountMapping`) pour cibler le message de la section 13.
- **Q-F3 :** la réponse de `contact-settings/` en contexte organisation doit dire quels canaux sont proposables (ex. `available_channels: ["MESSAGE"]`), pour que le front ne code pas l'état de l'interrupteur.
- **Q-F4 :** pour la sortie de `GET organizations/:id/internal/` d'une organisation archivée, confirmer le code (`DENY_OBJECT_STATE` supposé).
- **Q-F5 :** nombre maximal de catégories par organisation et par prestataire, et si `category_ids` peut être vide à la création (le formulaire suppose « facultatif »).
- **Q-F6 :** liste des membres et noms affichables (E6 cible, L1-01) : quels champs publics d'un membre sont montrés aux autres membres (nom complet ou nom abrégé ?).

---

## 16. Récapitulatif accessibilité et réseau faible (transversal)

- Cibles tactiles ≥ 44 px ; ordre de focus logique ; focus visible (anneau du thème) ; `aria-live` polite pour les changements de profil ; `role="alert"` pour les erreurs et pertes de profil ; aucun sens porté par la couleur seule (icône + texte pour rôles, états, types de vendeur, mentions).
- Dialogues : focus initial sur l'action sûre (« Annuler »), Échap ferme, focus rendu au déclencheur.
- Textes lisibles à 200 % de zoom : pas de largeur fixe ; noms d'organisation tronqués avec `title` et `aria-label` complet.
- Réseau faible : liste des profils en cache et mémorisée (nom) ; changement de profil sans requête ; aucune action sensible (création d'organisation, pièces, archivage, départ) mise en file hors ligne ; boutons désactivés avec raison affichée ; valeurs saisies conservées en cas d'échec ; images ≤ 80 px avec repli sur initiales ; une requête par écran en dehors de `contexts/`.

## 17. Conformité

- **Règle 1 :** un seul compte ; l'inscription ne demande plus de type ; les profils s'ajoutent depuis « Mes profils ».
- **Règle 2 :** aucun écran ne lie un plan à un rôle, une permission ou une vérification ; aucun prix n'apparaît dans ces écrans.
- **Règle 3 :** mentions précises (« RCCM vérifié »…), synthèse toujours accompagnée de sa liste, aide « Que signifie cette mention ? », texte « ne peut pas être achetée » ; aucun « garanti », « certifié » ni « Vérifié » seul.
- **Règle 4 :** aucun score de confiance ; la note du vendeur est celle du profil vendeur de l'offre, séparée de celle des autres profils de la même personne.
- **Règle 5 :** « Sponsorisé » reste un badge distinct, sans lien avec la vérification ni le tri de l'annuaire (alphabétique).
- **Règle 10 :** seule la commune est publique ; NIF non publié ; aucun téléphone/e-mail de membre ; pièces jamais renvoyées par l'API ; le nom public du prestataire est confirmé par l'utilisateur.
- **Badge « Sponsorisé » :** libellé inchangé (`badge.sponsored`).
