# L1-17, L1-19, L1-20 (D-L17) : Spécification d'écran, cycle de vie, restrictions et changement de nom des organisations

- **Date :** 25/11/2026 ; **auteur :** designer-ux ; **destinataires :** dev-frontend (F-L17-1 à F-L17-4), qa-testeur (Q-L17), analyste-fonctionnel (A-L17, textes de catégories).
- **Sources :** `docs/adr/0011-cycle-de-vie-organisations.md` (D1 à D11, §4.2 mesures, §5 machines d'états, §7 notifications) ; `docs/specs/L1-17-contrat-api.md` (**les écrans ne montrent que ce que le contrat expose**) ; réponses du client Q17, Q19, Q33, Q34, Q35 ; `docs/specs/L0-09-ecran-organisation-suspendue.md` (vue indisponible, amendée ici) ; `docs/specs/L1-01-ecrans-gouvernance.md` (E18 bannière de gouvernance, `HELP_LINKS`, amendée ici pour l'ordre des bannières).
- **Aucune dépendance graphique nouvelle.** shadcn/ui (`Alert`, `AlertDialog`, `Badge`, `RadioGroup`, `Checkbox`, `Collapsible`, `Select`, `Textarea`), lucide-react et Tailwind, déjà installés, suffisent.
- **Aucun lien d'aide** tant que L1-21 (Aide et Support) n'existe pas : tout lien d'aide passe par `HELP_LINKS` (`lib/help.ts`), `undefined` en V1 ; sans lien, **aucune phrase « contactez »** (Q19).

### Ce que ce document remplace

| Document, section | Sort |
|---|---|
| L0-09 UX-SUSP §4.2 (structure de la vue indisponible) | **Amendée** par la section 4 (états `CLOSING`, suspendue + archivée, lien vers le détail, fermeture, annulation) |
| L0-09 UX-SUSP §5.1 clés `org.unavailable.recourse.*` | **Remplacées** par la section 11.3 (plus de « contactez le support ») |
| L0-09 UX-SUSP §5.2 liste « Ce qui n'est pas possible » | **Conservée** pour suspendue, fermeture en cours et archivée |
| L0-09 UX-SUSP P4 (après archivage) | **Remplacé** par la section 7 (fermeture) |
| L0-09 UX-SUSP §6.2 « un seul texte par statut, sans motif » (S1) | **Caduque** pour `OWNER` et `ADMIN` : Q33 leur ouvre le détail (écran E19). Reste vraie pour les autres rôles. |
| L1-01-D2 §3.2 et §3.3 (emplacement et ordre de E18) | **Amendés** par la section 5 (ordre global des bannières) |
| `ArchiveOrganizationCard` (`OrganizationActions.tsx`) | **Remplacée** par `CloseOrganizationCard` (section 7) |
| `orgEdit.nameLocked`, `orgEdit.nameLockedPending`, `errors.code.name_locked_by_verification` | **Remplacés** par la section 9.1 |

---

## 0. Lecture rapide

1. **Trois axes indépendants, trois affichages indépendants.** Le cycle de vie (`lifecycle_status` : Active, Inactive, Fermeture en cours, Archivée), les restrictions (`restrictions.suspended`, `restrictions.measures`) et la gouvernance (`governance.primary_admin_state`) ont chacun leur badge et leur bannière. Aucun n'en cache un autre : une organisation peut être à la fois archivée, suspendue et « administration à régulariser ».
2. **Deux niveaux de lecture d'une restriction (Q33).** Tout membre voit **ce qui est bloqué** (liste des mesures). L'Administrateur principal et l'Administrateur voient en plus **pourquoi et quoi faire** : catégorie, explication, motif communiqué (masqué si divulgation limitée), périmètre, depuis, échéance, action requise, recours. Personne ne voit la note interne, l'auteur, l'origine, les preuves.
3. **Un refus par restriction n'est jamais une perte de profil.** `DENY_RESTRICTION` laisse l'utilisateur dans son profil, garde son formulaire, et dit quelle fonction est restreinte. Côté acheteur, le refus reste neutre (« ne peut pas être contactée pour le moment »), sans le mot « restriction ».
4. **La fermeture remplace l'archivage** : motif, ressaisie du mot de passe, date d'effet, annulation possible pendant « Fermeture en cours ».
5. **Le nom vérifié se change par une demande** (trois types), avec justificatifs ; l'ancien nom reste affiché publiquement pendant l'examen ; « nouvelle entité » = refus motivé et renvoi vers la création d'une organisation.

### 0.1 Écrans

| ID | Écran | Route ou hôte | Fichier (proposé) | Tâche |
|---|---|---|---|---|
| E19 | Restrictions (détail pour `OWNER`/`ADMIN`, vue réduite pour les autres rôles) | `/organizations/:id/restrictions` | `pages/OrganizationRestrictions.tsx`, `components/organizations/RestrictionCard.tsx` | F-L17-2 |
| E4 amendé | Vue indisponible : suspendue, fermeture en cours, archivée, cumuls | `OrganizationPage` (toutes sous-routes sauf E19) | `components/organizations/OrganizationUnavailableView.tsx` | F-L17-2 (suspendue), F-L17-3 (fermeture, archivée) |
| E20 | Bannières d'état de l'organisation : restriction en cours, inactive ; cumul avec E18 | `OrganizationPage`, cartes de `/profiles` | `components/organizations/OrganizationStateBanners.tsx`, `RestrictionBanner.tsx`, `DormantBanner.tsx` | F-L17-2 (restriction), F-L17-3 (inactive) |
| E21 | Refus `DENY_RESTRICTION` dans les écrans existants | éditeur d'offre, avis, messages, équipe, profil, contact | `lib/api-errors.ts`, `components/common/RestrictionNotice.tsx` | F-L17-1 (texte), F-L17-2 (intégration) |
| E22 | Fermer l'organisation (carte + dialogue) | carte de `/organizations/:id` et de la vue indisponible suspendue | `components/organizations/CloseOrganizationCard.tsx`, `CloseOrganizationDialog.tsx` | F-L17-3 |
| E23 | Annuler la fermeture | carte de la vue indisponible `CLOSING` | `components/organizations/CancelClosureCard.tsx` | F-L17-3 |
| E24 | Confirmer l'activité (organisation inactive) | bouton de la bannière E20 inactive | `DormantBanner.tsx` | F-L17-3 |
| E25 | Nom verrouillé et dénomination légale dans le formulaire de profil | `/organizations/:id/edit` | `pages/OrganizationEdit.tsx` | F-L17-4 |
| E26 | Demander une modification du nom (formulaire, justificatifs, suivi, annulation) | `/organizations/:id/name-change` | `pages/OrganizationNameChange.tsx`, `components/organizations/NameChangeForm.tsx`, `NameChangeTracker.tsx`, `NameChangeDocuments.tsx` | F-L17-4 |

Dialogues chargés à l'ouverture (`React.lazy` + `Suspense fallback={null}`), comme dans L1-01.

---

## 1. Principes communs

1. **Une action principale par écran.** E19 : « Voir ce qu'il faut faire » n'est pas un bouton ; l'action principale est le lien de l'action requise de la première restriction effective (s'il existe). E4 : selon l'état (4.3). E26 : « Envoyer la demande », puis « Envoyer le justificatif ».
2. **Le serveur arbitre.** L'interface affiche une action seulement si la capacité est dans la liste reçue (`contexts/` ou `internal/`), et gère chaque code du contrat. Elle ne connaît pas le caractère « effectif » d'un Administrateur principal ni les délais configurés (`closure_delay_days`, `dormancy_after_days`) : ils ne sont **jamais** affichés ni devinés (ADR 0011 §4.8 : seules des dates d'échéance sont communiquées).
3. **Aucun texte ne nomme une personne, une sanction de compte, une preuve ou un moyen d'enquête.** Les seuls textes libres affichés viennent du serveur : `category.label`, `explanation`, `communicated_reason`, `required_action.detail` (rédigés par le personnel sous consigne).
4. **Le statut n'est jamais porté par la couleur seule** : icône + mot dans chaque badge et chaque bannière.
5. **Une seule région `aria-live="polite"` propre à la page** (section 13). Erreurs : `role="alert"` dans leur dialogue ou leur carte.
6. **Aucune action différée.** Hors ligne : boutons désactivés avec `common.offlineAction` relié par `aria-describedby` ; rien n'est mis en file.
7. **Le `detail` des réponses d'erreur n'est jamais affiché** : clés i18n par `code` et, pour `DENY_RESTRICTION`, par `measure`.

---

## 2. Données et dérivations (F-L17-1)

### 2.1 Sources

| Donnée | Champ API | Qui la reçoit |
|---|---|---|
| Cycle de vie | `contexts/ results[].lifecycle_status`, `unavailable[].lifecycle_status` ; `internal/ lifecycle.{status, since, closure_effective_at}` | tout membre |
| Suspendue, mesures | `contexts/ results[].restrictions`, `unavailable[].restrictions` ; `internal/ restrictions` | tout membre |
| Capacités exerçables | `contexts/ results[].capabilities`, `unavailable[].capabilities` ; `internal/ capabilities` | tout membre |
| Détail des restrictions | `GET organizations/<id>/restrictions/` (contrat §2.1) | `org.view_restrictions` |
| Gouvernance | `internal/ governance`, `contexts/ results[].governance` (ADR 0010) | tout membre ; **absent de `unavailable`** |
| Nom verrouillé | `internal/ name_locked` | tout membre |
| Dénomination légale | `internal/ legal_name` (chaîne pour `org.edit_profile`, `null` sinon) | `OWNER`, `ADMIN` |
| Demande de nom ouverte | `internal/ name_change.open_request_id` (`null` si aucune ; objet `name_change` `null` pour les rôles sans `org.request_name_change`) | `OWNER`, `ADMIN` |
| Demandes de nom | `GET organizations/<id>/name-change-requests/` | `org.request_name_change` |

Le champ déprécié `status` (`internal/`, `unavailable[]`) **n'est plus lu** après F-L17-1 (contrat §1.1).

### 2.2 Fonction pure `organizationStates(ctx)` (`lib/organization-state.ts`, nouvelle)

Entrée : un élément de `results` ou de `unavailable`, ou `OrganizationInternal`. Sortie :

```ts
interface OrganizationStates {
  lifecycle: "ACTIVE" | "DORMANT" | "CLOSING" | "ARCHIVED";
  suspended: boolean;                 // restrictions.suspended
  targetedMeasures: TargetedMeasure[]; // restrictions.measures sans FULL_SUSPENSION, ordre de 2.3
  canViewRestrictions: boolean;       // capabilities inclut "org.view_restrictions"
}
```

`lifecycle_status` absent (serveur antérieur) : `"ACTIVE"` ; `restrictions` absent : `{suspended: false, measures: []}`. Une valeur de mesure inconnue est ignorée à l'affichage (pas de plantage) et journalisée en développement seulement.

### 2.3 Ordre d'affichage des mesures (constante `MEASURE_ORDER`)

`FULL_SUSPENSION`, `PUBLIC_VISIBILITY_HIDDEN`, `PUBLICATION_BLOCK`, `CONTACT_BLOCK`, `MESSAGING_BLOCK`, `REVIEW_REPLY_BLOCK`, `TEAM_CHANGES_BLOCK`, `PROFILE_EDIT_BLOCK`. (Du plus large au plus étroit ; le serveur renvoie l'ordre alphabétique, le front retrie.)

### 2.4 Où l'organisation est affichée selon son état

| État | Liste de `contexts/` | Espace `/organizations/:id` |
|---|---|---|
| `ACTIVE` ou `DORMANT`, non suspendue (avec ou sans restriction ciblée) | `results` | pages normales + bannières E20 |
| suspendue (tout cycle de vie), `CLOSING`, `ARCHIVED` | `unavailable` | vue indisponible E4 (sauf `/restrictions` : E19) |

---

## 3. E19 : Restrictions

### 3.1 Objectif et utilisateur

Dire à l'Administrateur principal ou à l'Administrateur (`org.view_restrictions`) **ce qui est restreint, pourquoi (dans la mesure communiquée), depuis quand, jusqu'à quand, ce qu'il doit faire et s'il peut demander un réexamen** (Q33). Pour les autres rôles : **ce qui est bloqué**, sans catégorie ni motif. Lecture seule : aucun membre ne lève une restriction.

### 3.2 Parcours

| # | Entrée | Comportement |
|---|---|---|
| P1 | Bannière E20 « Restriction en cours » : lien « Voir le détail » (rôles `canViewRestrictions`) | navigation vers E19 |
| P2 | Vue indisponible suspendue (E4) : bouton « Voir le détail et l'action requise » | navigation vers E19 |
| P3 | Notification (`/organizations/<id>/restrictions`, ADR 0011 §7) | E19 directement |
| P4 | Refus `DENY_RESTRICTION` dans un formulaire (E21) : lien « Voir le détail » | E19 |
| P5 | Saisie directe de l'URL par un rôle sans la capacité | vue réduite (3.5), **sans appel** à `restrictions/` |

Sortie : lien retour « Retour à l'organisation » (`/organizations/:id`) ; lien de l'action requise (3.4) ; lien de recours si `HELP_LINKS.appeal` est défini.

Cas d'erreur :

| Code | Comportement |
|---|---|
| `403 DENY_PERMISSION` | rôle changé entre-temps : relire `contexts/` une fois, puis afficher la vue réduite (3.5) |
| `403 DENY_RELATION` | `AccessDenied` avec `org.denied.relation` (existant) + lien « Mes profils » |
| `403 DENY_SECURITY` | compte restreint : `AccessDenied` avec `org.denied.accountRestricted` **réécrit** (11.3, sans « contactez ») |
| `400 invalid_filter` | erreur de programmation : `ErrorState` générique, trace en développement |
| 5xx, réseau | `ErrorState` + « Réessayer » ; si un cache existe, il reste affiché avec la mention `restrictions.stale` |
| 429 | `rateLimitMessage` (existant) dans `ErrorState` |

### 3.3 Structure

E19 n'utilise **pas** `children(org)` d'`OrganizationPage` (qui exige `internal/`, refusé sous suspension et en `ARCHIVED`). La page lit l'en-tête dans `contexts/` (`results` ou `unavailable` : `name`, `org_type`, `photo`, `role`, `lifecycle_status`, `restrictions`, `capabilities`) et la liste dans `restrictions/`. Elle est rendue dans `AccountShell`, **sans** `OrganizationTabs` (pas d'onglet « Restrictions » : l'écran n'existe que s'il y a quelque chose à lire).

**Mobile (< 768 px), de haut en bas :**

```
← Retour à l'organisation                       lien, min-h-11
ENTREPRISE                                      eyebrow
[logo] Atelier X                                <h1> (nom, tronqué + title)
(⏸ Suspendue) (⊘ Restriction en cours)        badges d'état (12.2)
Restrictions                                    <h2> « Restrictions en cours (2) »
┌─────────────────────────────────────────┐
│ Publication bloquée          (En cours) │    RestrictionCard (3.4)
│ Catégorie       Publication et contenu   │
│ Ce que cela veut dire   <explanation>    │
│ Motif communiqué        <texte>          │
│ Ce qui est concerné     <effet> · Toute l'organisation
│ Depuis          20 novembre 2026         │
│ Jusqu'au        Jusqu'à la levée         │
│ Action requise  Retirer un contenu       │
│                 <detail>                 │
│                 [Voir les offres]        │  lien selon 3.4
│ Recours         Un réexamen peut être    │
│                 demandé jusqu'au …       │
└─────────────────────────────────────────┘
┌──── carte suivante … ────┐
[Voir les restrictions passées]                 bouton secondaire (variant="outline")
Restrictions passées                            <h2>, après chargement
┌── carte compacte : mesure, statut (Levée/Expirée), du … au … ──┐
```

**Desktop (≥ 1024 px) :** même ordre, colonne unique `max-w-2xl` dans `AccountShell` (menu latéral à gauche). Les lignes de la carte passent en grille `dl` à deux colonnes (`grid-cols-[12rem_1fr]`) ; sur mobile, intitulé au-dessus de la valeur.

Aucune restriction effective (toutes levées depuis la notification) : `EmptyState` icône `CheckCircle2`, titre `restrictions.empty.title`, texte `restrictions.empty.body`, bouton « Voir les restrictions passées » conservé.

### 3.4 `RestrictionCard` (nouveau) : contenu ligne par ligne

Élément `<article aria-labelledby>` ; titre `<h3>`.

| Ligne | Source | Règle d'affichage |
|---|---|---|
| Titre | `measure` | `restriction.measure.<MEASURE>.label` |
| Badge d'état | `status` | `ACTIVE` « En cours » (`Clock`) ; `LIFTED` « Levée » (`CheckCircle2`) ; `EXPIRED` « Expirée » (`CalendarX`). `Badge variant="outline"`. |
| Catégorie | `category.label` | texte du serveur, tel quel |
| Ce que cela veut dire | `explanation` | texte du serveur ; `whitespace-pre-line` ; absent si vide |
| Motif communiqué | `communicated_reason`, `disclosure` | `STANDARD` et non vide : texte du serveur. `STANDARD` et vide : ligne absente. `LIMITED` (`null`) : texte fixe `restriction.reasonLimited` en `text-muted-foreground`, **sans** guillemets ni icône d'alerte. |
| Ce qui est concerné | `measure`, `scope` | `restriction.measure.<MEASURE>.effect` puis « · » puis `scopeLabel(scope)` (L1-01-D2 §2.4 : « Toute l'organisation ») |
| Depuis | `since` | `formatLongDate` (existant, `lib/format.ts`) |
| Jusqu'au | `ends_at` | date longue ; `null` : `restriction.untilLifted` |
| Action requise | `required_action.code`, `.detail` | libellé `restriction.action.<CODE>` ; `detail` non nul en dessous ; lien d'action selon le tableau ci-dessous |
| Recours | `appeal.mode`, `.deadline` | `NONE` : `restriction.appeal.none`. `SUPPORT_REQUEST` : `restriction.appeal.available` (+ `restriction.appeal.deadline` si `deadline`) ; lien « Demander un réexamen » **seulement si** `HELP_LINKS.appeal` est défini |
| Levée / expirée | `lifted_at`, `ends_at` | cartes `LIFTED` : « Levée le {date} » ; `EXPIRED` : « Expirée le {ends_at} ». Cartes passées : seules les lignes Titre, Badge, Catégorie, Depuis, Levée/Expirée (compactes). |

**Lien de l'action requise** (un seul, `Button variant="link"`, cible ≥ 44 px) :

| `required_action.code` | Lien affiché si… | Cible |
|---|---|---|
| `SUBMIT_DOCUMENTS` | `org.verification_submit` dans les capacités exerçables | `/organizations/:id/verification`, « Envoyer les pièces » |
| `UPDATE_PROFILE` | `org.edit_profile` exerçable | `/organizations/:id/edit`, « Modifier le profil » |
| `REGULARIZE_GOVERNANCE` | `HELP_LINKS.governance` défini | lien d'aide (L1-01-D2 §3.3) |
| `CONTACT_SUPPORT` | `HELP_LINKS.restrictions` défini | lien d'aide |
| `REMOVE_CONTENT` | organisation dans `results` **et** profil actif = cette organisation | `/dashboard`, « Voir les offres de l'organisation » ; sinon texte seul |
| `AWAIT_REVIEW`, `NONE` | jamais | — |

L'**action principale** de l'écran est le lien d'action de la première carte effective dans l'ordre de tri du serveur ; elle n'est pas dupliquée en haut de page.

### 3.5 Vue réduite (rôles sans `org.view_restrictions` : `EDITOR`, `ANALYST`, `MEMBER`)

Même en-tête. Puis une carte unique « Ce qui est restreint » : liste `<ul>` des mesures de `restrictions.measures` (ordre 2.3), chaque ligne = libellé + effet. En dessous : `restrictions.reduced.who` (« Le détail et l'action à mener sont visibles des administrateurs principaux et des administrateurs de l'organisation. »). Aucun appel à `restrictions/`, aucun bouton « Voir les restrictions passées », aucune catégorie, aucune date.

Si `restrictions.measures` est vide : `EmptyState` `restrictions.empty.title` sans bouton.

### 3.6 États

| État | Comportement |
|---|---|
| Chargement | `contexts/` en cours : `Skeleton` d'en-tête ; `restrictions/` en cours : 2 `Skeleton` `h-48 rounded-2xl`, conteneur `aria-busy="true"` |
| Vide | 3.3 (dernier paragraphe) |
| Erreur | 3.2 |
| Hors ligne | cache React Query affiché + `OfflineBanner` global ; « Voir les restrictions passées » désactivé si l'historique n'est pas en cache (`aria-describedby` vers `common.offlineAction`) |
| Succès | sans objet (lecture seule) |
| Permission refusée | vue réduite (3.5) ou `AccessDenied` (3.2) |
| Organisation absente de `contexts/` (ni `results` ni `unavailable`) | `AccessDenied` `org.denied.relation` |

---

## 4. E4 amendé : vue indisponible (suspendue, fermeture en cours, archivée)

### 4.1 Règle de sélection (remplace L0-09 §6.1)

`OrganizationPage` rend `OrganizationUnavailableView` quand l'id est dans `unavailable`, **sauf** pour la route `/organizations/:id/restrictions` (E19). La vue calcule `organizationStates(org)` et empile **un bloc d'état par axe**, dans cet ordre :

1. bloc du cycle de vie si `lifecycle` vaut `ARCHIVED` ou `CLOSING` ;
2. bloc de suspension si `suspended`.

| Cas | Badges d'en-tête | Blocs |
|---|---|---|
| suspendue, `ACTIVE` ou `DORMANT` | « Suspendue » | Suspension |
| `CLOSING` | « Fermeture en cours » | Fermeture |
| `CLOSING` + suspendue | « Fermeture en cours », « Suspendue » | Fermeture, puis Suspension |
| `ARCHIVED` | « Archivée » | Archivage |
| `ARCHIVED` + suspendue | « Archivée », « Suspendue » | Archivage, puis Suspension |

Une restriction ciblée (sans suspension) d'une organisation `CLOSING` ou `ARCHIVED` n'a pas de bloc ici (elle ne change rien à ce qui est possible) ; elle reste lisible dans E19 par les rôles autorisés, via le lien du bloc de cycle de vie (4.2, « Voir les restrictions »).

### 4.2 Structure (mobile, de haut en bas ; desktop : colonne `max-w-2xl`, même ordre)

```
ENTREPRISE
[logo] Atelier X                        (⌛ Fermeture en cours) (⏸ Suspendue)
┌ Bloc Fermeture (Alert, bordure border-warning/60) ─────────────────┐
│ La fermeture de cette organisation est en cours                    │
│ Elle prendra effet au plus tôt le 2 décembre 2026.                 │
│ Ses offres ne sont plus visibles du public. …                       │
└────────────────────────────────────────────────────────────────────┘
┌ Bloc Suspension (Alert, bordure border-warning/60) ────────────────┐
│ Cette organisation est suspendue                                   │
│ …                                                                  │
│ [Voir le détail et l'action requise]     (OWNER, ADMIN)            │
└────────────────────────────────────────────────────────────────────┘
[Annuler la fermeture]  carte E23          (org.archive, CLOSING)
Votre rôle            carte (existante)
Ce qui n'est pas possible actuellement     carte (existante)
Fermer l'organisation carte E22            (org.archive, pas CLOSING ni ARCHIVED)
Quitter l'organisation carte (existante)   (org.leave)
```

Blocs : `Alert` **sans** rôle vivant (`role` retiré, comme E18 : la vue est atteinte volontairement ; la seule annonce est le titre de page), titre `h2` `text-base`, icône `aria-hidden`.

| Bloc | Icône | Bordure | Titre | Corps | Lien ou bouton |
|---|---|---|---|---|---|
| Suspension | `PauseCircle` | `border-warning/60` | `org.unavailable.title.SUSPENDED` (existant) | `org.unavailable.body.SUSPENDED` (existant) ; `org.unavailable.migrated` si `migrated_from_business` | `canViewRestrictions` : bouton `Button` (variante par défaut) « Voir le détail et l'action requise » → E19 ; sinon texte `org.unavailable.recourse.SUSPENDED.other` (réécrit, 11.3) |
| Fermeture | `Hourglass` | `border-warning/60` | `org.unavailable.title.CLOSING` | `org.unavailable.effectiveAt` (si date connue, 4.4) puis `org.unavailable.body.CLOSING` | `canViewRestrictions` et `targetedMeasures` non vide : lien « Voir les restrictions » → E19 |
| Archivage | `Archive` | `border-border`, icône `text-muted-foreground` | `org.unavailable.title.ARCHIVED` (existant) | `org.unavailable.body.ARCHIVED` (existant) puis texte de restauration (4.5) | idem lien « Voir les restrictions » si `canViewRestrictions` et (`suspended` ou `targetedMeasures` non vide) — sauf si le bloc Suspension porte déjà le bouton |

**Masqué** (inchangé, L0-09 §4.2) : onglets, « Agir sous ce profil », « Voir le profil public », « Modifier le profil », pièces, liste des capacités. Rien n'est grisé.

### 4.3 Action principale selon l'état

| État | Action principale (bouton plein, une seule) | Actions secondaires (bouton `outline`) |
|---|---|---|
| suspendue, rôle `canViewRestrictions` | « Voir le détail et l'action requise » | Fermer (si `org.archive`), Quitter |
| `CLOSING`, `org.archive` | « Annuler la fermeture » (E23) | Quitter |
| `ARCHIVED`, `HELP_LINKS.restoration` défini, `OWNER`/`ADMIN` | lien « Demander une restauration » | Quitter |
| tous les autres cas | aucune (vue informative) | Quitter |

`CLOSING` + suspendue : « Annuler la fermeture » reste l'action principale ; le bouton du bloc Suspension passe en `variant="outline"`.

### 4.4 Date d'effet d'une fermeture en cours

`unavailable[]` ne porte pas `closure_effective_at` (11 clés, contrat §1.2). La vue l'obtient ainsi :

1. Juste après la demande de fermeture (E22) : la réponse `POST closure/` est passée dans l'état de navigation (`navigate(..., { state: { closure: response } })`), y compris `pending_obligations` ; aucun appel de plus.
2. Sinon, si `org.view_internal` est dans `unavailable[].capabilities` (permise en `CLOSING`) : un appel `GET internal/` (une fois, en ligne, cache React Query de l'organisation) pour lire `lifecycle.closure_effective_at`.
3. Sinon, ou en échec : le corps s'affiche sans la phrase de date (aucun message d'erreur : l'information est accessoire).

Date passée (finalisation en attente du cron ou d'une obligation) : `org.unavailable.effectivePending` à la place de `effectiveAt`.

`pending_obligations` non vide (seulement disponible au point 1) : sous le corps, `org.closure.obligationsIntro` puis liste des libellés `org.closure.obligation.<code>` (11.5). Codes inconnus : `org.closure.obligation.other`.

### 4.5 Texte de restauration d'une organisation archivée (Q34, QL-6)

| Rôle | `HELP_LINKS.restoration` défini | Non défini (V1 avant L1-21) |
|---|---|---|
| `OWNER`, `ADMIN` | `org.unavailable.restoration.available` + lien « Demander une restauration » | `org.unavailable.restoration.noLink` |
| autres | `org.unavailable.recourse.ARCHIVED.other` (existant) | idem |

### 4.6 Alerte « profil perdu » (`ContextLostAlert`)

`LostReason` gagne `org_closing`. Sélection : id trouvé dans `unavailable` → `suspended` vrai : `org_suspended` ; sinon `lifecycle` `CLOSING` : `org_closing` ; `ARCHIVED` : `org_archived`. Si l'organisation est à la fois suspendue et `CLOSING`/`ARCHIVED`, la raison de cycle de vie l'emporte (elle est la plus durable). Clé nouvelle : `errors.lost.closing`. Le lien « Voir l'état de l'organisation » est inchangé.

Exception (L0-09 P4 conservé) : après une fermeture demandée par l'utilisateur lui-même (E22), aucune alerte de perte : retour silencieux au profil personnel si le profil actif était cette organisation.

### 4.7 `/profiles` : cartes

- Section « Organisations indisponibles » (existante) : badges de 12.2 selon les axes (jusqu'à deux badges).
- Section « Organisations » (`results`) : sous `RoleBadge`, un badge par état actif, dans l'ordre : « Restriction en cours » (`targetedMeasures` non vide), « Inactive » (`DORMANT`), puis les badges de gouvernance E18 (inchangés).

---

## 5. E20 : bannières d'état sur l'espace d'une organisation disponible

### 5.1 Emplacement et ordre global (amende L1-01-D2 §3.2 et §3.3)

`OrganizationPage` rend `OrganizationStateBanners` entre le chargement réussi de `internal/` et `OrganizationTabs`, sur toutes les sections (Aperçu, Profil, Vérification, Équipe, Demande de nom), pour **tous les rôles**. Ordre de haut en bas, chaque bannière étant indépendante (cumul permis, aucune ne remplace l'autre) :

1. **Restriction en cours** (`RestrictionBanner`) si `targetedMeasures` non vide ;
2. **Administration à régulariser** (E18, `governance.primary_admin_state === "MISSING"`) ;
3. **Organisation en cours d'examen** (E18, `governance.under_review`) ;
4. **Organisation inactive** (`DormantBanner`) si `lifecycle === "DORMANT"`.

Justification de l'ordre : d'abord ce qui bloque une action maintenant, puis ce qui empêche la présence publique, enfin ce qui demande une simple confirmation.

**Cumul fréquent (Q17, ADR 0011 D6 a) :** une organisation orpheline au-delà du délai porte la bannière « Administration à régulariser » **et** une restriction `PUBLICATION_BLOCK` de catégorie « Gouvernance ». Les deux bannières s'affichent ; la restriction a son propre texte (ce qui est bloqué), la gouvernance le sien (pourquoi la présence publique est suspendue). Le détail E19 montre la catégorie « Gouvernance de l'organisation » et l'action « Régulariser l'administration ».

**Mobile :** au-delà de deux bannières, les bannières 3 et 4 passent en forme compacte (titre + bouton ou lien, corps dans un `Collapsible` « Plus de détails ») pour que le contenu de la page reste visible au premier écran (360 × 640). Desktop : toutes dépliées.

Toutes les bannières : `Alert` **sans rôle vivant**, titre `h2` `text-base`, icône `aria-hidden`, pas de bouton de fermeture (l'état persiste tant que le serveur le renvoie).

### 5.2 `RestrictionBanner`

| Élément | Contenu |
|---|---|
| Icône | `Ban` ; bordure `border-warning/60`, fond `bg-background` |
| Titre | `restriction.banner.title` (« Certaines fonctions de cette organisation sont restreintes ») |
| Corps | liste `<ul>` des libellés courts `restriction.measure.<MEASURE>.label` (2.3) ; si une seule mesure : phrase `restriction.measure.<MEASURE>.effect` à la place de la liste |
| Lien | `canViewRestrictions` : « Voir le détail et l'action requise » → E19. Sinon : texte `restrictions.reduced.who` (pas de lien) |

`PUBLIC_VISIBILITY_HIDDEN` seule : même bannière (elle ne bloque aucune action, mais l'équipe doit savoir que son profil n'est pas public).

### 5.3 `DormantBanner` (E24)

| Élément | Contenu |
|---|---|
| Icône | `Moon` ; bordure `border-border` (ni sanction ni erreur) |
| Titre | `org.dormant.title` (« Organisation considérée comme inactive ») |
| Corps | `org.dormant.body` |
| Bouton | `org.edit_profile` exerçable : « Confirmer que l'organisation est active » (`Button` taille par défaut, pleine largeur sur mobile). Sinon : texte `org.dormant.askAdmin`. |

Parcours E24 : un tap envoie `POST resume/ {"confirm": true}` (le libellé du bouton vaut consentement ; action réversible et sans risque : pas de dialogue). Pendant l'envoi : bouton désactivé + `Loader2`.

| Réponse | Comportement |
|---|---|
| `200` | mise à jour du cache `internal/` avec la réponse, invalidation de `contexts/` ; la bannière disparaît ; annonce dans la région vivante de la page : `org.dormant.done` ; pas de toast (évite deux annonces) |
| `409 organization_not_dormant` | déjà réactivée (cron ou autre membre) : même issue que `200`, relecture de `internal/` et `contexts/`, annonce `org.dormant.done` |
| `400 {"confirm": …}` | erreur de programmation ; message générique `errors.generic` sous le bouton (`role="alert"`) |
| `403 DENY_RESTRICTION` (`PROFILE_EDIT_BLOCK`) | texte E21 de la mesure sous le bouton ; relecture de `contexts/` (le bouton disparaîtra) |
| `403` autres, réseau, 429 | `describeApiError` sous le bouton, `role="alert"` |
| hors ligne | bouton désactivé, `common.offlineAction` |

---

## 6. E21 : refus `DENY_RESTRICTION` dans les écrans existants

### 6.1 Règles techniques (F-L17-1)

- `DENY_RESTRICTION` est ajouté à `DENY_CODES` **mais pas** à `CONTEXT_DENY_CODES` : il ne déclenche **jamais** la perte de profil ni le retour au profil personnel.
- Nouvelle fonction `restrictionMeasure(error): string | null` (lit la clé `measure` d'une réponse 403 `DENY_RESTRICTION`).
- `describeApiError` : `DENY_RESTRICTION` → `errors.restriction.<measure>` ; mesure absente ou inconnue → `errors.restriction.generic`.
- Après un `DENY_RESTRICTION` reçu par un **membre**, invalider `contexts/` et `internal/` de l'organisation (une fois) : les capacités et la bannière se mettent à jour.
- Les saisies en cours sont **conservées** (brouillon d'offre, réponse à un avis, message, formulaire de profil, invitation).

### 6.2 Composant `RestrictionNotice` (nouveau, `components/common/`)

Affiche dans un formulaire ou une carte le texte du refus et, pour les rôles `canViewRestrictions`, un lien « Voir le détail » vers E19 ; pour les autres rôles : `errors.restriction.askAdmin`. Rendu : `Alert` `role="alert"` (réponse à une action de l'utilisateur), icône `Ban`, bordure `border-warning/60` (pas `destructive` : ce n'est pas une erreur de saisie). Props : `{ measure: string | null; organizationId: Uuid; canViewDetail: boolean }`.

### 6.3 Tableau par écran (membre de l'organisation)

| Écran | Action refusée | Mesure | Comportement |
|---|---|---|---|
| Éditeur d'offre (`PostEditor`) | publier, modifier, renouveler, reprendre | `PUBLICATION_BLOCK` | `RestrictionNotice` à la place du message général, au-dessus du bouton d'envoi ; brouillon conservé ; focus sur la notice |
| Mes offres, tableau de bord | renouveler, reprendre une offre | `PUBLICATION_BLOCK` | `RestrictionNotice` dans la carte ou le dialogue de l'offre ; « Mettre en pause » et « Supprimer » restent proposés (permis) |
| Avis (`ReviewsSection`) | répondre à un avis | `REVIEW_REPLY_BLOCK` | `RestrictionNotice` sous le champ de réponse ; texte conservé |
| Messages (`Messages`) | répondre dans une conversation | `MESSAGING_BLOCK` | `RestrictionNotice` au-dessus de la zone de saisie ; message conservé dans le champ ; **pas** `organizationDeniedKey` (qui afficherait « accès refusé ») |
| Équipe (`OrganizationTeam`, dialogues E6a, E6b, E6f, E6g, retrait) | inviter, confirmer, nommer, changer un rôle, retirer | `TEAM_CHANGES_BLOCK` | `RestrictionNotice` dans le dialogue (mode `kind: "form"` de `lib/team.ts`), choix conservés ; « Quitter l'organisation » reste disponible |
| Profil (`OrganizationEdit`) | enregistrer le profil | `PROFILE_EDIT_BLOCK` | `RestrictionNotice` en haut du formulaire (remplace `formError`) ; champs conservés ; **lien supplémentaire** « Demander une modification du nom » si `name_locked` et `org.request_name_change` (la demande reste permise, ADR 0011 §4.2) |
| Vérification (`OrganizationVerification`) | sans objet | — | aucune mesure ciblée ne bloque `org.verification_submit` |
| Moyens de contact (`contact-settings`) | sans objet pour le membre | — | `CONTACT_BLOCK` ne retire aucune capacité ; la bannière E20 explique que les visiteurs ne voient pas les moyens de contact |
| Bannière inactive (E24) | confirmer l'activité | `PROFILE_EDIT_BLOCK` | 5.3 |

**Avant l'action** : les points d'entrée dépendent des capacités exerçables (qui excluent déjà les capacités restreintes, contrat §1.2). Un bouton disparaît donc sans explication locale ; l'explication est portée par la bannière E20 visible sur toute la section. Voir la question QD-1 (champ additif `restricted_capabilities` pour afficher une notice à l'emplacement du bouton).

### 6.4 Côté acheteur et public (aucune mention de restriction)

| Écran | Code reçu | Texte |
|---|---|---|
| Fiche d'offre : « Contacter », « Voir le numéro », échange | `403 DENY_RESTRICTION` `CONTACT_BLOCK` | `errors.code.seller_contact_unavailable` (existant : « Cette organisation ne peut pas être contactée pour le moment. ») ; boutons de contact absents si `allowed_channels` vaut `[]` |
| Nouvelle conversation vers l'organisation | `403 DENY_RESTRICTION` `MESSAGING_BLOCK` | même texte |
| Idem | `403 DENY_SECURITY`, `DENY_OBJECT_STATE` | même texte (inchangé) |

La fonction `describeApiError` reçoit une option `asBuyer: true` dans ces écrans pour choisir ce texte neutre au lieu de `errors.restriction.*`.

---

## 7. E22 : fermer l'organisation (remplace l'archivage)

### 7.1 Objectif et utilisateur

L'Administrateur principal (`org.archive`, libellé « Fermer l'organisation ») met fin à la présence de l'organisation sur Connecte+. Effets à comprendre avant de confirmer : offres et profil retirés du public, équipe sans action possible, fermeture effective à une date donnée par le serveur, annulable tant qu'elle est « en cours », restauration exceptionnelle seulement ensuite.

### 7.2 Points d'entrée

- `/organizations/:id` (Aperçu), carte `CloseOrganizationCard` en bas de page, si `org.archive` exerçable et `lifecycle` `ACTIVE` ou `DORMANT`.
- Vue indisponible suspendue (E4), si `org.archive` dans `unavailable[].capabilities` (fermeture permise sous suspension, QL-3) et `lifecycle` ni `CLOSING` ni `ARCHIVED`.

### 7.3 Carte

Titre `org.closure.cardTitle` (« Fermer l'organisation ») ; texte `org.closure.cardBody` ; bouton `outline` destructif (patron de `LeaveOrganizationCard`) « Fermer l'organisation » (`LogOut` remplacé par `DoorClosed`).

### 7.4 Dialogue `CloseOrganizationDialog` (`ResponsiveDialog`, feuille basse sur mobile ; `dismissible` faux pendant l'envoi)

De haut en bas :

1. Titre : `org.closure.title` (« Fermer « {{name}} » ? »).
2. **Ce qui va se passer** (`<ul>`, toujours visible, pas replié) : `org.closure.effects.public`, `.team`, `.history`, `.cancel`, `.restore`.
3. **Si suspendue** (`restrictions.suspended`) : paragraphe `org.closure.suspendedNote` (la suspension reste en vigueur après la fermeture).
4. **Motif** (`RadioGroup`, obligatoire, aucune option présélectionnée) : `activity_ended`, `duplicate`, `merged_into_other`, `no_longer_needed`, `other` (libellés 11.5). Chaque option est une ligne de 44 px minimum. Pour `merged_into_other` : aide sous l'option `org.closure.reason.mergedHint`.
5. `SensitiveConfirmFields` (existant) : case `org.closure.confirmLabel`, mot de passe (`team.passwordLabel`).
6. Pied : « Annuler » (focus initial), « Fermer l'organisation » (`variant="destructive"`), désactivé tant que motif, case et mot de passe ne sont pas renseignés.

Aucune date ni aucun délai n'est affiché avant l'envoi (le délai est un réglage du back-office, non exposé) : la date d'effet est montrée après la réponse.

### 7.5 Réponses et erreurs

| Réponse | Comportement |
|---|---|
| `200` `lifecycle_status: "ARCHIVED"` | fermeture du dialogue ; si le profil actif est cette organisation : `switchToPersonal()` silencieux ; invalidation de `contexts/` ; `toast.success(org.closure.doneArchived)` ; navigation `/organizations/:id` (vue archivée) |
| `200` `lifecycle_status: "CLOSING"` | même chose, toast `org.closure.doneClosing` (avec la date `formatLongDate(closure_effective_at)`) ; navigation avec `state.closure` (4.4) |
| `400 {"reason_code": …}` | message sous le groupe de motifs (`aria-describedby`), focus sur le groupe |
| `400 {"confirm": …}` | message sous la case |
| `403 reauthentication_failed` | message `errors.code.reauthentication_failed` relié au mot de passe ; mot de passe vidé ; focus sur le champ |
| `403 DENY_PERMISSION` | `FormAlert` `org.closure.err.permission` (Administrateur principal non effectif ou rôle changé) ; bouton désactivé ; relecture de `contexts/` |
| `403 DENY_OBJECT_STATE` | `FormAlert` `org.closure.err.alreadyArchived` ; relecture de `contexts/` ; à la fermeture du dialogue, la page affiche la vue archivée |
| `409 closure_already_requested` | même issue qu'un succès `CLOSING` (un autre Administrateur principal l'a demandée) : toast `org.closure.err.alreadyRequested`, relecture, navigation |
| `403 DENY_SECURITY` | `FormAlert` `errors.deny.SECURITY.action` (réécrit, 11.3) |
| 429 | `rateLimitMessage` dans `FormAlert` ; mot de passe vidé |
| réseau | `FormAlert` `errors.network` ; saisies conservées sauf le mot de passe |

Aucun envoi automatique répété (action sensible).

### 7.6 E23 : annuler la fermeture

Carte `CancelClosureCard` dans la vue `CLOSING` si `org.archive` est dans `unavailable[].capabilities`. Titre `org.closure.cancelTitle`, texte `org.closure.cancelBody`, bouton plein « Annuler la fermeture ». `AlertDialog` de confirmation (focus initial sur « Retour ») : titre `org.closure.cancelConfirmTitle`, texte `org.closure.cancelConfirmBody`, boutons « Retour » / « Annuler la fermeture ». Pas de mot de passe (contrat §3.2).

| Réponse `DELETE closure/` | Comportement |
|---|---|
| `200` | invalidation de `contexts/` ; toast `org.closure.cancelled` ; l'organisation repasse dans `results` : `OrganizationPage` affiche l'espace normal. Le profil actif **n'est pas** changé automatiquement. |
| `409 closure_not_pending` | relecture de `contexts/` ; toast `org.closure.err.notPending` |
| `403 DENY_OBJECT_STATE` | fermeture déjà effective : message `org.closure.err.alreadyArchived` dans la carte ; relecture (la vue passe en « Archivée ») |
| `403 DENY_PERMISSION` | message `org.closure.err.permission` dans la carte |
| réseau, 429 | message dans la carte (`role="alert"`) |

### 7.7 Textes à mettre à jour ailleurs

`role.OWNER_desc` : « archiver » → « fermer ». `capability.archive` : « Fermer l'organisation ». `errors.code.last_owner` : « … ou l'organisation doit être fermée. ». `team.archive*` et `org.home.archive*` : supprimés avec `ArchiveOrganizationCard`. Le mot « archivée » reste pour l'**état** (Q34 : Archivée), « Fermer » pour l'**action**.

---

## 8. Reprise d'une organisation inactive

Voir 5.3 (E24). Points complémentaires :
- L'Aperçu d'une organisation `DORMANT` est inchangé (offres et profil restent publics, ADR 0011 D8) ; seule la bannière s'ajoute.
- Le badge « Inactive » n'apparaît **jamais** publiquement (contrat §1.3).
- Les notifications « considérée comme inactive » (ADR 0011 §7) mènent à `/organizations/<id>`, où la bannière porte le bouton.

---

## 9. E25, E26 : nom verrouillé et demande de modification du nom

### 9.1 E25 : formulaire de profil (`OrganizationEdit`)

Champs, dans cet ordre : Type (fixe), **Nom affiché** (`name`), **Dénomination légale** (`legal_name`, nouveau, affiché seulement si `legal_name !== null`), Description, Catégories, Commune, NIF, Logo.

| Élément | Règle |
|---|---|
| Libellé de `name` | `orgEdit.displayNameLabel` (« Nom affiché ») |
| `legal_name` | libellé `orgEdit.legalNameLabel`, aide `orgEdit.legalNameHint` ; même validation que `name` côté serveur (`invalid_name`) ; vide permis |
| `name_locked === true` | les deux champs en `readOnly` (jamais `disabled`, pour rester lisibles et sélectionnables) ; aide commune `orgEdit.nameLocked` ; sous les champs, lien `Button variant="link"` « Demander une modification du nom » → E26, **si** `org.request_name_change` est dans les capacités |
| Demande ouverte (`name_change.open_request_id` non nul) | à la place du lien : `orgEdit.nameChangeOpen` + lien « Suivre la demande » → E26 ; et sous le champ `name`, rien d'autre (le nouveau nom n'est pas lu ici, pour ne pas ajouter d'appel) |
| `409 name_locked_by_verification` (course : verrou posé entre-temps) | valeurs remises, message `errors.code.name_locked_by_verification` (réécrit) sur le champ modifié, focus ; lien E26 sous le message |

Aperçu (`OrganizationHome`) : si `name_change.open_request_id` non nul, ligne d'information sous l'en-tête : `org.home.nameChangeOpen` + lien « Suivre la demande ». Aucun nouveau nom affiché à cet endroit (aucun appel de plus).

### 9.2 E26 : objectif et utilisateur

L'Administrateur principal ou l'Administrateur (`org.request_name_change`) demande à l'équipe Vérification de corriger ou de changer un nom verrouillé (Q35), suit la demande, envoie les justificatifs, l'annule au besoin. Le nom public ne change qu'après acceptation.

### 9.3 Parcours

```
E25 lien « Demander une modification du nom »
  → E26 : chargement de internal/ (déjà en cache) et de name-change-requests/?page_size=5
      ├─ demande ouverte (DOCUMENTS_REQUIRED ou PENDING_REVIEW) → Suivi (9.6)
      ├─ name_locked faux → redirection /organizations/:id/edit (le nom se modifie directement)
      └─ sinon → Formulaire (9.4) ; sous le formulaire, « Demandes précédentes » si la liste n'est pas vide
  Formulaire → « Envoyer la demande » (ressaisie) → 201
      ├─ status DOCUMENTS_REQUIRED → Suivi, section Justificatifs mise en avant (focus sur son titre)
      └─ status PENDING_REVIEW (correction d'une faute) → Suivi
  Suivi → envoi de justificatifs (0..n) → PENDING_REVIEW → décision (notification) → Suivi affiche le résultat
  Suivi → « Annuler la demande » → CANCELLED → Formulaire disponible de nouveau
```

Accès refusé : rôle sans `org.request_name_change` → `AccessDenied` `errors.deny.PERMISSION.org`. Organisation indisponible : vue E4 (la route est couverte par `OrganizationPage`).

### 9.4 Formulaire (structure mobile, de haut en bas ; desktop : colonne `max-w-2xl`)

1. `PageHeader` : titre `nameChange.title` (« Demander une modification du nom »), description `nameChange.description`.
2. **Encadré « Avant de commencer »** (`Alert` neutre, icône `Info`) : `nameChange.before.publicName`, `nameChange.before.noInherit`, `nameChange.before.newEntity` + lien « Créer une organisation » (`/organizations/new`).
3. **Noms actuels** (`dl`) : « Nom affiché » = `name` ; « Dénomination légale » = `legal_name` ou `nameChange.legalEmpty`.
4. **Type de modification** (`RadioGroup`, obligatoire, sans présélection ; chaque option = libellé + description sur deux lignes, 44 px min.) :

| Valeur | Libellé | Description |
|---|---|---|
| `TYPO_CORRECTION` | « Corriger une faute » | « Faute de frappe, accent, majuscule, espace. Le nom reste le même. » |
| `DISPLAY_NAME_CHANGE` | « Changer le nom affiché » | « Nouveau nom commercial ou d'usage, pour la même organisation. » |
| `LEGAL_NAME_CHANGE` | « Changer la dénomination légale » | « Le nom officiel enregistré a changé (RCCM, arrêté). Un justificatif est obligatoire. » |

5. **Champs de nom** (apparaissent après le choix du type ; transition sans animation si `prefers-reduced-motion`) :

| Type | Champs | Règles d'interface |
|---|---|---|
| `TYPO_CORRECTION` | « Nom affiché corrigé » et « Dénomination légale corrigée », **préremplis** avec les valeurs actuelles | au moins un champ modifié, sinon message `nameChange.err.nothing` au moment de l'envoi |
| `DISPLAY_NAME_CHANGE` | « Nouveau nom affiché » (obligatoire, vide au départ) | — |
| `LEGAL_NAME_CHANGE` | « Nouvelle dénomination légale » (obligatoire) ; case « Changer aussi le nom affiché » qui révèle « Nouveau nom affiché » | — |

Seuls les champs modifiés sont envoyés (`proposed_display_name`, `proposed_legal_name` ; non modifié = chaîne vide).

6. **Motif** (`reason_code`) : `TYPO_CORRECTION` → `typo` imposé, pas de contrôle affiché. `DISPLAY_NAME_CHANGE` → `Select` : `rebranding`, `other`. `LEGAL_NAME_CHANGE` → `Select` : `legal_rename`, `legal_form_change`, `other`. Libellés 11.6.
7. **Précision** (`note`, `Textarea`, facultative, 500 caractères, compteur `n/500` en `aria-live="off"`) ; aide `nameChange.noteHint` (consigne : aucune information sur une autre personne).
8. `SensitiveConfirmFields` : case `nameChange.confirmLabel` ; mot de passe.
9. Bouton plein « Envoyer la demande » (action principale unique) ; lien « Annuler » (retour E25, confirmation `AlertDialog` si saisies en cours, patron existant `leaveOpen` d'`OrganizationEdit`).

### 9.5 Erreurs de l'envoi (`POST name-change-requests/`)

| Code | Comportement |
|---|---|
| `400 {"proposed_display_name": …}` / `{"proposed_legal_name": …}` (`invalid_name`) | message sur le champ, focus |
| `400 nothing_to_change` | `nameChange.err.nothing` en tête de formulaire (`role="alert"`), focus sur le premier champ de nom |
| `400 {"confirm": …}` | sous la case |
| `403 reauthentication_failed` | sur le mot de passe, champ vidé, focus |
| `409 name_change_not_required` | le nom n'est plus verrouillé : `nameChange.err.notRequired` + lien « Modifier le profil » (`/edit`) ; relecture de `internal/` |
| `409 name_change_already_open` | relecture de la liste ; affichage du Suivi de la demande ouverte ; message `nameChange.err.alreadyOpen` en tête (annonce vivante) |
| `403 DENY_PERMISSION` | `errors.deny.PERMISSION.org` |
| `403 DENY_OBJECT_STATE`, `DENY_SECURITY` | `OrganizationPage` relit `contexts/` ; message `describeApiError` en tête |
| 429, réseau | `FormAlert` ; saisies conservées sauf le mot de passe |

### 9.6 Suivi d'une demande (`NameChangeTracker`)

Structure (mobile, de haut en bas) :

```
Demande de modification du nom          <h2>
(◷ Justificatifs à envoyer)             badge de statut
Type            Changer la dénomination légale
Demandée le     25 novembre 2026         (+ « par vous » si is_mine)
┌ Nom affiché publiquement : Atelier X           ┐  inchangé pendant l'examen
│ Nouveau nom demandé : Atelier Y                │
│   (En cours de vérification)                   │  badge outline, icône Clock
│ Dénomination légale actuelle : Atelier X SARL  │
│ Nouvelle dénomination demandée : Atelier Y SARL│
└────────────────────────────────────────────────┘
Précision       <note>  (si non vide)
Justificatifs   <h3> (NameChangeDocuments, 9.7)
[Annuler la demande]                    bouton outline destructif
```

| `status` | Badge (icône + texte) | Message sous le badge |
|---|---|---|
| `DOCUMENTS_REQUIRED` | `FileUp` « Justificatifs à envoyer » | `nameChange.status.DOCUMENTS_REQUIRED.body` ; la section Justificatifs porte l'action principale |
| `PENDING_REVIEW` | `Clock` « En cours d'examen » | `nameChange.status.PENDING_REVIEW.body` |
| `COMPLETED` | `CheckCircle2` « Acceptée » | `nameChange.status.COMPLETED.body` |
| `REJECTED` | `XCircle` « Refusée » | texte par `decision_reason` (11.6) ; pour `new_entity_required` : texte + lien « Créer une organisation » |
| `CANCELLED` | `Ban` « Annulée » | `nameChange.status.CANCELLED.body` |
| `VOID` | `MinusCircle` « Sans suite » | `nameChange.status.VOID.body` |

Le libellé « En cours de vérification » accompagne **toujours** le nouveau nom tant que la demande est ouverte ; le nouveau nom n'est **jamais** accompagné d'un badge de vérification (`VerifiedClaims` n'est pas rendu dans cette page).

**Annuler la demande** : visible si statut ouvert et (`is_mine` ou rôle `OWNER`). `AlertDialog` (focus initial « Retour ») : titre `nameChange.cancel.title`, texte `nameChange.cancel.body`. Réponses : `200` → Suivi en `CANCELLED`, annonce vivante `nameChange.cancel.done`, formulaire de nouveau proposé en dessous ; `404 name_change_request_not_found` / `409 name_change_not_open` → relecture de la liste, annonce `nameChange.err.notOpen` ; `403 DENY_PERMISSION` (Administrateur principal non effectif) → `errors.deny.PERMISSION.org` dans le dialogue.

**Demandes précédentes** : sous le formulaire ou le suivi, `Collapsible` fermé par défaut « Demandes précédentes ({{count}}) » ; chaque ligne : type, date, badge de statut, motif de décision s'il existe. Aucune pièce, aucun nom de personne.

### 9.7 Justificatifs (`NameChangeDocuments`)

- Visible si statut `DOCUMENTS_REQUIRED` ou `PENDING_REVIEW`.
- Liste des pièces de `documents[]` : libellé du type (`kyc.docs.<type>.title`, `NAME_CHANGE_PROOF` : nouveau libellé « Justificatif de changement de nom ») + état (`EN_ATTENTE` « En cours d'examen », `VALIDE` « Validée », `REFUSE` « Refusée »), réutilise les tons de `DocumentRow`. Aucun fichier, aucune URL (contrat §4.2).
- Ajout : `Select` du type (options : `NAME_CHANGE_PROOF` toujours ; `RCCM` si `org_type` `ENTREPRISE` ; `ARRETE_ONG` si `ONG` ; selon la règle de pièces exigées existante), puis bouton « Choisir un fichier » (`input type="file"`, `KYC_ACCEPT_ATTR`, contrôle `checkKycFile` existant), envoi via `POST kyc/documents/` avec `name_change_request_id`. Action principale en `DOCUMENTS_REQUIRED` : « Envoyer le justificatif ».
- Texte d'aide : `nameChange.docs.hint` (exemples de pièces) et `nameChange.docs.noBadge`.
- Capacité : `org.verification_submit` absente → pas de bouton, texte `nameChange.docs.askAdmin`.

| Réponse | Comportement |
|---|---|
| `201` | relecture de la demande ; si elle passe `PENDING_REVIEW`, annonce `nameChange.docs.sentReview` ; sinon `nameChange.docs.sent` |
| `400 {"document_type": …}` | message sous le `Select` |
| `404 name_change_request_not_found`, `409 name_change_not_open` | relecture ; `nameChange.err.notOpen` |
| erreurs de fichier (taille, format) | `uploadErrorMessage` existant |
| réseau, 429 | message sous le bouton ; le fichier choisi reste sélectionné pour réessayer |

### 9.8 États de E26

| État | Comportement |
|---|---|
| Chargement | `Skeleton` du formulaire (3 blocs) ; `aria-busy` |
| Vide | aucune demande : formulaire seul |
| Erreur de lecture de la liste | `ErrorState` + « Réessayer » (le formulaire n'est pas affiché sur une hypothèse : risque de `name_change_already_open`) |
| Hors ligne | dernier état en cache ; boutons d'envoi, d'annulation et d'ajout de pièce désactivés avec `common.offlineAction` |
| Succès | 9.5, 9.6, 9.7 (annonces vivantes, pas de toast en plus) |
| Permission refusée | 9.3 |

---

## 10. États de synthèse par écran

| Écran | Chargement | Vide | Erreur | Hors ligne | Succès | Permission refusée |
|---|---|---|---|---|---|---|
| E19 | Skeleton en-tête + 2 cartes | `EmptyState` | `ErrorState` | cache + historique désactivé | — | vue réduite / `AccessDenied` |
| E4 | couvert par `contexts/` | — | `ErrorState` | cache, actions désactivées | toasts 7.5, 7.6 | `AccessDenied` (non-membre) |
| E20 | couvert par `internal/` | pas de bannière | — | bannières en cache, bouton E24 désactivé | annonce `org.dormant.done` | bouton absent + `org.dormant.askAdmin` |
| E21 | bouton d'envoi avec `Loader2` | — | `RestrictionNotice` | bouton désactivé | — | `DENY_PERMISSION` inchangé |
| E22, E23 | bouton avec `Loader2` | — | `FormAlert` / message dans la carte | bouton désactivé | toast + navigation | carte absente sans `org.archive` |
| E25, E26 | Skeleton | formulaire | `ErrorState` / `FormAlert` | boutons désactivés | annonces vivantes | `AccessDenied` |

---

## 11. Contenus : clés i18n (`i18n/locales/fr.ts`)

Les libellés des **catégories** et leurs **explications** ne sont pas dans `fr.ts` : ils viennent du back-office (`category.label`, `explanation`). Les textes ci-dessous pour mesures et actions requises sont des **propositions** que l'analyste (A-L17) peut reformuler ; les clés sont figées.

### 11.1 États et badges

| Clé | Texte |
|---|---|
| `org.status.SUSPENDED` | Suspendue (existant) |
| `org.status.ARCHIVED` | Archivée (existant) |
| `org.status.CLOSING` | Fermeture en cours |
| `org.status.DORMANT` | Inactive |
| `org.status.RESTRICTED` | Restriction en cours |
| `org.status.aria` | Statut de l'organisation : {{status}} (existant) |

### 11.2 Mesures (`restriction.measure.<MEASURE>.label` / `.effect`)

| Mesure | `label` | `effect` |
|---|---|---|
| `FULL_SUSPENSION` | Suspension de l'organisation | Le profil et les offres ne sont plus visibles du public. L'équipe ne peut plus agir au nom de l'organisation. |
| `PUBLIC_VISIBILITY_HIDDEN` | Profil masqué au public | Le profil et les offres ne sont pas visibles du public. L'équipe peut continuer à travailler. |
| `PUBLICATION_BLOCK` | Publication bloquée | Impossible de publier, de modifier ou de renouveler une offre. Mettre une offre en pause ou la supprimer reste possible. |
| `CONTACT_BLOCK` | Contact bloqué | Les visiteurs ne peuvent ni demander à être contactés ni voir les moyens de contact de l'organisation. |
| `MESSAGING_BLOCK` | Messagerie bloquée | Personne ne peut ouvrir une nouvelle conversation avec l'organisation, et l'équipe ne peut pas répondre aux messages. |
| `REVIEW_REPLY_BLOCK` | Réponse aux avis bloquée | L'équipe ne peut pas répondre aux avis. |
| `TEAM_CHANGES_BLOCK` | Équipe figée | Impossible d'inviter, de confirmer, de nommer, de changer un rôle ou de retirer une personne. Chacun peut toujours quitter l'organisation. |
| `PROFILE_EDIT_BLOCK` | Modification du profil bloquée | Impossible de modifier le profil. Une demande de modification du nom reste possible. |

### 11.3 Écran Restrictions, recours, textes réécrits sans « contactez »

| Clé | Texte |
|---|---|
| `restrictions.title` | Restrictions |
| `restrictions.activeHeading` | Restrictions en cours ({{count}}) |
| `restrictions.back` | Retour à l'organisation |
| `restrictions.showHistory` | Voir les restrictions passées |
| `restrictions.historyHeading` | Restrictions passées |
| `restrictions.historyEmpty` | Aucune restriction passée. |
| `restrictions.empty.title` | Aucune restriction en cours |
| `restrictions.empty.body` | Toutes les fonctions de l'organisation sont disponibles. |
| `restrictions.reduced.title` | Ce qui est restreint |
| `restrictions.reduced.who` | Le détail et l'action à mener sont visibles des administrateurs principaux et des administrateurs de l'organisation. |
| `restrictions.stale` | Affichage de la dernière version enregistrée. |
| `restrictions.pageTitle` | Restrictions · {{name}} |
| `restriction.status.ACTIVE` | En cours |
| `restriction.status.LIFTED` | Levée |
| `restriction.status.EXPIRED` | Expirée |
| `restriction.field.category` | Catégorie |
| `restriction.field.explanation` | Ce que cela veut dire |
| `restriction.field.reason` | Motif communiqué |
| `restriction.field.scope` | Ce qui est concerné |
| `restriction.field.since` | Depuis |
| `restriction.field.until` | Jusqu'au |
| `restriction.field.action` | Action requise |
| `restriction.field.appeal` | Recours |
| `restriction.reasonLimited` | Le détail du motif n'est pas communiqué, pour protéger une vérification en cours ou d'autres personnes. |
| `restriction.untilLifted` | Jusqu'à la levée de la mesure |
| `restriction.liftedOn` | Levée le {{date}} |
| `restriction.expiredOn` | Expirée le {{date}} |
| `restriction.action.NONE` | Aucune action n'est demandée. |
| `restriction.action.CONTACT_SUPPORT` | Un échange avec l'équipe Connecte+ est nécessaire. |
| `restriction.action.SUBMIT_DOCUMENTS` | Envoyer des pièces de vérification. |
| `restriction.action.REGULARIZE_GOVERNANCE` | Régulariser l'administration de l'organisation. |
| `restriction.action.REMOVE_CONTENT` | Retirer le contenu concerné. |
| `restriction.action.UPDATE_PROFILE` | Mettre à jour le profil de l'organisation. |
| `restriction.action.AWAIT_REVIEW` | Aucune action de votre part : l'équipe Connecte+ examine la situation. |
| `restriction.actionLink.SUBMIT_DOCUMENTS` | Envoyer les pièces |
| `restriction.actionLink.UPDATE_PROFILE` | Modifier le profil |
| `restriction.actionLink.REMOVE_CONTENT` | Voir les offres de l'organisation |
| `restriction.actionLink.help` | Voir comment faire |
| `restriction.appeal.none` | Aucun recours n'est prévu pour cette mesure. |
| `restriction.appeal.available` | Un réexamen de cette mesure peut être demandé. |
| `restriction.appeal.deadline` | Jusqu'au {{date}}. |
| `restriction.appeal.link` | Demander un réexamen |
| `restriction.banner.title` | Certaines fonctions de cette organisation sont restreintes |
| `restriction.banner.detail` | Voir le détail et l'action requise |
| `org.unavailable.recourse.SUSPENDED.other` (**réécrit**) | Le détail de cette mesure est visible des administrateurs principaux et des administrateurs de l'organisation. |
| `org.unavailable.recourse.SUSPENDED.OWNER` | **supprimée** (remplacée par le bouton vers E19) |
| `org.unavailable.recourse.ARCHIVED.OWNER` | **supprimée** (remplacée par 4.5) |
| `org.unavailable.seeDetail` | Voir le détail et l'action requise |
| `org.unavailable.seeRestrictions` | Voir les restrictions |
| `org.denied.accountRestricted` (**réécrit**) | Votre compte est limité pour le moment. |
| `errors.deny.SECURITY.action` (**réécrit**) | Cette action est temporairement impossible : le compte ou l'organisation est limité. |

Les liens d'aide (`restriction.actionLink.help`, `restriction.appeal.link`, `org.unavailable.restoration.link`) ne sont rendus que si la clé correspondante de `HELP_LINKS` est définie. `HELP_LINKS` (`lib/help.ts`, créé par F4 de L1-01 ou par F-L17-2 s'il n'existe pas encore) gagne : `restrictions?`, `appeal?`, `restoration?`.

### 11.4 Vue indisponible : cycle de vie

| Clé | Texte |
|---|---|
| `org.unavailable.title.CLOSING` | La fermeture de cette organisation est en cours |
| `org.unavailable.body.CLOSING` | Ses offres ne sont plus visibles du public. L'équipe ne peut plus agir en son nom. Un administrateur principal peut annuler la fermeture tant qu'elle n'a pas pris effet. |
| `org.unavailable.effectiveAt` | Elle prendra effet au plus tôt le {{date}}. |
| `org.unavailable.effectivePending` | Elle prendra effet dès que les dernières vérifications seront terminées. |
| `org.unavailable.restoration.available` | Une restauration exceptionnelle peut être demandée. Elle est examinée par l'équipe Connecte+ et n'est jamais automatique. |
| `org.unavailable.restoration.link` | Demander une restauration |
| `org.unavailable.restoration.noLink` | Une organisation archivée ne peut pas être rouverte depuis l'application. |
| `errors.lost.closing` | La fermeture de cette organisation est en cours. Vous agissez maintenant sous votre profil personnel. |

### 11.5 Fermeture

| Clé | Texte |
|---|---|
| `org.closure.cardTitle` | Fermer l'organisation |
| `org.closure.cardBody` | Réservé aux administrateurs principaux. L'organisation et ses offres ne seront plus visibles. |
| `org.closure.open` | Fermer l'organisation |
| `org.closure.title` | Fermer « {{name}} » ? |
| `org.closure.effectsTitle` | Ce qui va se passer |
| `org.closure.effects.public` | Le profil et les offres de l'organisation ne seront plus visibles du public. |
| `org.closure.effects.team` | Plus personne ne pourra agir au nom de l'organisation. Chaque membre pourra encore la quitter. |
| `org.closure.effects.history` | Les avis, l'historique et les informations de l'organisation sont conservés. |
| `org.closure.effects.cancel` | Tant que la fermeture est en cours, un administrateur principal peut l'annuler. Tous les membres sont prévenus. |
| `org.closure.effects.restore` | Une fois la fermeture effective, l'organisation ne peut être rouverte que par une restauration exceptionnelle, examinée par l'équipe Connecte+. |
| `org.closure.suspendedNote` | La suspension en cours restera en vigueur après la fermeture. |
| `org.closure.reasonLabel` | Pourquoi fermez-vous l'organisation ? |
| `org.closure.reason.activity_ended` | L'activité a pris fin |
| `org.closure.reason.duplicate` | Cette organisation est un doublon |
| `org.closure.reason.merged_into_other` | Elle a rejoint une autre organisation |
| `org.closure.reason.no_longer_needed` | Nous n'utilisons plus Connecte+ pour cette organisation |
| `org.closure.reason.other` | Autre raison |
| `org.closure.reason.mergedHint` | Rien n'est transféré automatiquement vers l'autre organisation : avis, mentions de vérification et offres restent attachés à celle-ci. |
| `org.closure.confirmLabel` | Je confirme la fermeture de cette organisation |
| `org.closure.submit` | Fermer l'organisation |
| `org.closure.doneArchived` | Organisation fermée. |
| `org.closure.doneClosing` | Fermeture demandée. Elle prendra effet au plus tôt le {{date}}. |
| `org.closure.obligationsIntro` | La fermeture attend la fin des éléments suivants : |
| `org.closure.obligation.payments_open` | des paiements en cours |
| `org.closure.obligation.refunds_open` | des remboursements en cours |
| `org.closure.obligation.tickets_sold` | des billets vendus pour un événement à venir |
| `org.closure.obligation.subscriptions_active` | des abonnements en cours |
| `org.closure.obligation.provider_unavailable` | une vérification technique, qui sera refaite automatiquement |
| `org.closure.obligation.other` | d'autres éléments en cours |
| `org.closure.err.permission` | Seul un administrateur principal actif peut fermer l'organisation ou annuler sa fermeture. |
| `org.closure.err.alreadyArchived` | La fermeture de cette organisation a déjà pris effet. |
| `org.closure.err.alreadyRequested` | La fermeture de cette organisation a déjà été demandée. |
| `org.closure.err.notPending` | Aucune fermeture n'est en cours pour cette organisation. |
| `org.closure.cancelTitle` | Annuler la fermeture |
| `org.closure.cancelBody` | L'organisation redeviendra active, avec son équipe et ses offres. |
| `org.closure.cancelConfirmTitle` | Annuler la fermeture de « {{name}} » ? |
| `org.closure.cancelConfirmBody` | Tous les membres seront prévenus. |
| `org.closure.cancelConfirm` | Annuler la fermeture |
| `org.closure.cancelBack` | Retour |
| `org.closure.cancelled` | Fermeture annulée. L'organisation est de nouveau active. |
| `capability.archive` (**réécrit**) | Fermer l'organisation |

### 11.6 Inactivité

| Clé | Texte |
|---|---|
| `org.dormant.title` | Organisation considérée comme inactive |
| `org.dormant.body` | Aucune activité n'a été constatée depuis longtemps. L'organisation n'apparaît plus dans l'annuaire, mais son profil et ses offres restent visibles. |
| `org.dormant.confirm` | Confirmer que l'organisation est active |
| `org.dormant.askAdmin` | Un administrateur principal ou un administrateur peut confirmer qu'elle est toujours active. |
| `org.dormant.done` | Merci. L'organisation est de nouveau considérée comme active. |

### 11.7 Changement de nom

| Clé | Texte |
|---|---|
| `orgEdit.displayNameLabel` | Nom affiché |
| `orgEdit.legalNameLabel` | Dénomination légale |
| `orgEdit.legalNameHint` | Nom officiel enregistré (RCCM ou arrêté). Il n'est pas affiché publiquement pour l'instant. |
| `orgEdit.nameLocked` (**réécrit**) | Le nom est verrouillé depuis la vérification. Pour le changer, faites une demande de modification du nom. |
| `orgEdit.nameLockedPending` | **supprimée** (un seul texte ; le verrou couvre les pièces en attente et validées) |
| `errors.code.name_locked_by_verification` (**réécrit**) | Le nom est verrouillé depuis la vérification. Faites une demande de modification du nom. |
| `orgEdit.requestNameChange` | Demander une modification du nom |
| `orgEdit.nameChangeOpen` | Une demande de modification du nom est en cours d'examen. |
| `orgEdit.followNameChange` | Suivre la demande |
| `org.home.nameChangeOpen` | Une demande de modification du nom est en cours. Le nom actuel reste affiché jusqu'à la décision. |
| `nameChange.title` | Demander une modification du nom |
| `nameChange.description` | L'équipe de vérification de Connecte+ examine chaque demande. |
| `nameChange.before.title` | Avant de commencer |
| `nameChange.before.publicName` | Pendant l'examen, l'ancien nom reste affiché publiquement. |
| `nameChange.before.noInherit` | Le nouveau nom ne reprend pas automatiquement les mentions de vérification de l'ancien. |
| `nameChange.before.newEntity` | S'il s'agit d'une autre entité (nouvelle société, autre association), changer le nom n'est pas possible : créez une nouvelle organisation. Rien ne lui est transféré. |
| `nameChange.createOrg` | Créer une organisation |
| `nameChange.currentTitle` | Noms actuels |
| `nameChange.legalEmpty` | Non renseignée |
| `nameChange.typeLabel` | Type de modification |
| `nameChange.type.TYPO_CORRECTION` | Corriger une faute |
| `nameChange.type.TYPO_CORRECTION_desc` | Faute de frappe, accent, majuscule, espace. Le nom reste le même. |
| `nameChange.type.DISPLAY_NAME_CHANGE` | Changer le nom affiché |
| `nameChange.type.DISPLAY_NAME_CHANGE_desc` | Nouveau nom commercial ou d'usage, pour la même organisation. |
| `nameChange.type.LEGAL_NAME_CHANGE` | Changer la dénomination légale |
| `nameChange.type.LEGAL_NAME_CHANGE_desc` | Le nom officiel enregistré a changé (RCCM, arrêté). Un justificatif est obligatoire. |
| `nameChange.field.displayCorrected` | Nom affiché corrigé |
| `nameChange.field.legalCorrected` | Dénomination légale corrigée |
| `nameChange.field.displayNew` | Nouveau nom affiché |
| `nameChange.field.legalNew` | Nouvelle dénomination légale |
| `nameChange.field.alsoDisplay` | Changer aussi le nom affiché |
| `nameChange.reasonLabel` | Motif |
| `nameChange.reason.typo` | Correction d'une faute |
| `nameChange.reason.rebranding` | Nouveau nom commercial |
| `nameChange.reason.legal_rename` | Changement de nom enregistré |
| `nameChange.reason.legal_form_change` | Changement de forme juridique (par exemple SARL vers SA) |
| `nameChange.reason.other` | Autre motif |
| `nameChange.noteLabel` | Précision (facultatif) |
| `nameChange.noteHint` | Expliquez le changement. N'indiquez aucune information sur une autre personne. |
| `nameChange.confirmLabel` | Je confirme que cette demande concerne la même organisation |
| `nameChange.submit` | Envoyer la demande |
| `nameChange.sent` | Demande envoyée. |
| `nameChange.trackerTitle` | Demande de modification du nom |
| `nameChange.requestedOn` | Demandée le {{date}} |
| `nameChange.byYou` | par vous |
| `nameChange.publicName` | Nom affiché publiquement |
| `nameChange.proposedDisplay` | Nouveau nom demandé |
| `nameChange.currentLegal` | Dénomination légale actuelle |
| `nameChange.proposedLegal` | Nouvelle dénomination demandée |
| `nameChange.underVerification` | En cours de vérification |
| `nameChange.status.DOCUMENTS_REQUIRED` | Justificatifs à envoyer |
| `nameChange.status.DOCUMENTS_REQUIRED.body` | Envoyez au moins un justificatif pour que la demande soit examinée. |
| `nameChange.status.PENDING_REVIEW` | En cours d'examen |
| `nameChange.status.PENDING_REVIEW.body` | L'équipe de vérification examine la demande. Vous recevrez une notification. |
| `nameChange.status.COMPLETED` | Acceptée |
| `nameChange.status.COMPLETED.body` | Le nouveau nom est appliqué. Les mentions de vérification seront revues pour ce nom. |
| `nameChange.status.REJECTED` | Refusée |
| `nameChange.status.CANCELLED` | Annulée |
| `nameChange.status.CANCELLED.body` | Cette demande a été annulée. |
| `nameChange.status.VOID` | Sans suite |
| `nameChange.status.VOID.body` | Cette demande n'a plus d'objet : l'organisation ou son nom a changé entre-temps. |
| `nameChange.decision.approved` | Demande acceptée. |
| `nameChange.decision.documents_insufficient` | Les justificatifs ne permettent pas de confirmer le changement. Vous pouvez faire une nouvelle demande avec d'autres pièces. |
| `nameChange.decision.authority_not_established` | La demande n'a pas pu être rattachée à une personne habilitée à représenter l'organisation. |
| `nameChange.decision.new_entity_required` | Il s'agit d'une nouvelle entité : son nom ne peut pas remplacer celui de cette organisation. Créez une nouvelle organisation, qui suivra sa propre vérification. Rien n'est transféré depuis celle-ci (avis, mentions de vérification, offres). |
| `nameChange.decision.protected_name_conflict` | Ce nom ne peut pas être attribué à cette organisation. |
| `nameChange.decision.other` | La demande n'a pas été acceptée. |
| `nameChange.cancel.open` | Annuler la demande |
| `nameChange.cancel.title` | Annuler cette demande ? |
| `nameChange.cancel.body` | Le nom actuel ne change pas. Les justificatifs envoyés ne seront pas examinés pour cette demande. |
| `nameChange.cancel.confirm` | Annuler la demande |
| `nameChange.cancel.back` | Retour |
| `nameChange.cancel.done` | Demande annulée. |
| `nameChange.previous` | Demandes précédentes ({{count}}) |
| `nameChange.docs.title` | Justificatifs |
| `nameChange.docs.hint` | Par exemple : nouveau RCCM, arrêté modifié, procès-verbal de l'assemblée qui a décidé le changement. |
| `nameChange.docs.noBadge` | Ces pièces servent uniquement à examiner la demande. Elles ne donnent aucune mention de vérification avant la décision. |
| `nameChange.docs.typeLabel` | Type de pièce |
| `nameChange.docs.choose` | Choisir un fichier |
| `nameChange.docs.submit` | Envoyer le justificatif |
| `nameChange.docs.sent` | Justificatif envoyé. |
| `nameChange.docs.sentReview` | Justificatif envoyé. La demande est maintenant en cours d'examen. |
| `nameChange.docs.askAdmin` | Un administrateur principal ou un administrateur peut envoyer les justificatifs. |
| `kyc.docs.NAME_CHANGE_PROOF.title` | Justificatif de changement de nom |
| `nameChange.err.nothing` | Indiquez un nom différent du nom actuel. |
| `nameChange.err.notRequired` | Le nom n'est pas verrouillé : vous pouvez le modifier directement dans le profil. |
| `nameChange.err.alreadyOpen` | Une demande est déjà en cours pour cette organisation. |
| `nameChange.err.notOpen` | Cette demande n'est plus en cours. |

### 11.8 Refus `DENY_RESTRICTION` (`errors.restriction.*`)

| Clé | Texte |
|---|---|
| `errors.restriction.PUBLICATION_BLOCK` | La publication d'offres est restreinte pour cette organisation. Votre saisie est conservée. |
| `errors.restriction.REVIEW_REPLY_BLOCK` | La réponse aux avis est restreinte pour cette organisation. Votre texte est conservé. |
| `errors.restriction.MESSAGING_BLOCK` | La messagerie est restreinte pour cette organisation. Votre message est conservé. |
| `errors.restriction.TEAM_CHANGES_BLOCK` | Les changements d'équipe sont restreints pour cette organisation. Chacun peut toujours la quitter. |
| `errors.restriction.PROFILE_EDIT_BLOCK` | La modification du profil est restreinte pour cette organisation. Vos modifications sont conservées dans le formulaire. |
| `errors.restriction.CONTACT_BLOCK` | Les demandes de contact sont restreintes pour cette organisation. |
| `errors.restriction.generic` | Cette action est actuellement restreinte pour cette organisation. |
| `errors.restriction.askAdmin` | Le détail est visible des administrateurs principaux et des administrateurs de l'organisation. |
| `errors.restriction.seeDetail` | Voir le détail |
| `errors.code.closure_already_requested` | La fermeture de cette organisation a déjà été demandée. |
| `errors.code.closure_not_pending` | Aucune fermeture n'est en cours pour cette organisation. |
| `errors.code.organization_not_dormant` | L'organisation est déjà considérée comme active. |
| `errors.code.name_change_not_required` | = `nameChange.err.notRequired` |
| `errors.code.name_change_already_open` | = `nameChange.err.alreadyOpen` |
| `errors.code.name_change_not_open` | = `nameChange.err.notOpen` |
| `errors.code.name_change_request_not_found` | = `nameChange.err.notOpen` |
| `errors.code.nothing_to_change` | = `nameChange.err.nothing` |

Ces codes sont ajoutés à `BUSINESS_CODES` (`lib/api-errors.ts`).

---

## 12. Composants

### 12.1 Réutilisés (noms exacts)

`AccountShell`, `OrganizationPage` (adapté), `PageHeader`, `UserAvatar` (`shape="square"`), `RoleBadge`, `SellerTypeBadge`, `AccessDenied`, `ErrorState`, `EmptyState`, `Skeleton`, `Badge`, `Button`, `Alert`/`AlertTitle`/`AlertDescription`, `AlertDialog`, `ResponsiveDialog`, `RadioGroup`, `Select`, `Checkbox`, `Textarea`, `Collapsible`, `SensitiveConfirmFields`, `Field`/`errorProps` (`auth/FormFields`), `LeaveOrganizationCard`, `ContextLostAlert`, `OfflineBanner`, `useActiveContext`, `useOptionalActiveContext`, `useOnlineStatus`, `describeApiError`, `formatLongDate`, `checkKycFile`, `KYC_ACCEPT_ATTR`, `uploadErrorMessage`, `useUploadOrganizationDocument` (étendu d'un paramètre `nameChangeRequestId`), `scopeLabel` (`lib/team.ts`), `GovernanceBanner` (E18, L1-01-D2).

### 12.2 Modifiés

| Composant | Changement |
|---|---|
| `OrganizationStatusBadge` | `status: "SUSPENDED" \| "ARCHIVED" \| "CLOSING" \| "DORMANT" \| "RESTRICTED"` ; icônes : `PauseCircle`, `Archive`, `Hourglass`, `Moon`, `Ban`. Rendu d'un badge par état ; le parent en rend plusieurs. Reste distinct de `StatusBadge` (règle 5). |
| `OrganizationUnavailableView` | section 4 ; lit `organizationStates` ; ne lit plus `status` |
| `OrganizationPage` | route `restrictions` exclue de la vue indisponible ; rend `OrganizationStateBanners` ; héberge la région vivante unique (13) |
| `OrganizationEdit` | 9.1 (`legal_name`, verrou des deux champs, lien E26, `RestrictionNotice`) |
| `OrganizationHome` | `CloseOrganizationCard` à la place d'`ArchiveOrganizationCard` ; ligne « demande de nom en cours » |
| `UnavailableOrganizationsSection`, cartes de `Profiles.tsx` | badges 4.7 |
| `lib/api-errors.ts` | `DENY_RESTRICTION`, `restrictionMeasure`, codes 11.8, option `asBuyer` ; `lostMessageKey` gère `org_closing` |
| `lib/active-context.ts` | `LostReason` + `org_closing` |
| `PostEditor`, `ReviewsSection`, `Messages`, dialogues d'équipe (`lib/team.ts`, `lib/invitations.ts`) | `RestrictionNotice` sur `DENY_RESTRICTION` (6.3) |

### 12.3 Nouveaux (justifiés)

| Composant | Justification | Props |
|---|---|---|
| `pages/OrganizationRestrictions.tsx` | E19 ; ne peut pas être un enfant d'`OrganizationPage` (il faut le lire sous suspension et archivage, sans `internal/`) | — (lit `:id`) |
| `components/organizations/RestrictionCard.tsx` | une carte = une restriction (3.4) ; réutilisée en forme compacte pour l'historique | `{ restriction: OrganizationRestriction; compact?: boolean; links: RestrictionLinks }` |
| `components/organizations/OrganizationStateBanners.tsx` | ordonne et empile les bannières (5.1), y compris E18 | `{ org: OrganizationInternal }` |
| `components/organizations/RestrictionBanner.tsx` | 5.2 | `{ organizationId; measures; canViewDetail }` |
| `components/organizations/DormantBanner.tsx` | 5.3, action E24 | `{ org: OrganizationInternal }` |
| `components/common/RestrictionNotice.tsx` | un seul rendu des refus de restriction dans 6 écrans | 6.2 |
| `components/organizations/CloseOrganizationCard.tsx`, `CloseOrganizationDialog.tsx` | remplace l'archivage (motif + ressaisie + date d'effet) | `{ org: { id; name; capabilities; suspended } }` |
| `components/organizations/CancelClosureCard.tsx` | E23 | `{ org: UnavailableOrganization }` |
| `pages/OrganizationNameChange.tsx`, `NameChangeForm.tsx`, `NameChangeTracker.tsx`, `NameChangeDocuments.tsx` | E26 ; formulaire à part entière avec envoi de fichiers (une page plutôt qu'une feuille basse : clavier et sélecteur de fichiers Android) | — |
| `lib/organization-state.ts` | dérivation unique des trois axes (2.2), testée sans rendu | — |
| Hooks `useOrganizationRestrictions(id, {history})`, `useRequestClosure`, `useCancelClosure`, `useResumeOrganization`, `useNameChangeRequests`, `useCreateNameChangeRequest`, `useCancelNameChangeRequest` (`hooks/use-organizations.ts`) | une mutation par route du contrat | — |

---

## 13. Accessibilité

- **Région vivante unique.** `OrganizationPage` rend un seul `<div role="status" aria-live="polite" className="sr-only">` et expose `announce(text)` par contexte React (`useOrganizationAnnouncer`). `OrganizationTeam` abandonne sa propre région au profit de celle-ci (sinon deux régions sur `/team`). E19 et E26 l'utilisent. Les bannières et les blocs d'état n'ont **aucun** rôle vivant. Les erreurs sont en `role="alert"` dans leur dialogue, carte ou formulaire. (La région globale de changement de profil d'`ActiveContextContext` reste inchangée.)
- **Cibles ≥ 44 px** : boutons, liens d'action (`min-h-11`), options de `RadioGroup` (ligne entière cliquable), cases (`SensitiveConfirmFields` le fait déjà), lignes du `Collapsible`.
- **Focus.** Dialogues : focus initial sur l'action non destructive (« Annuler », « Retour »). Après erreur de champ : focus sur le premier champ en erreur. Après création d'une demande de nom : focus sur le titre `h2` du suivi (`tabIndex={-1}`). Après `DENY_RESTRICTION` : focus sur la `RestrictionNotice`. Après annulation de fermeture : focus sur le `h1` de l'espace rechargé. Focus visible : `focus-visible:ring-2 ring-ring` (existant).
- **Titres.** Une seule `h1` par page (nom de l'organisation, ou titre de E26). Cartes de restriction : `h3` sous `h2` « Restrictions en cours ». `document.title` : E19 `restrictions.pageTitle` ; vue indisponible `org.unavailable.pageTitle` avec le premier badge.
- **Listes de définitions** : lignes de `RestrictionCard` en `<dl>`/`<dt>`/`<dd>` ; « En cours de vérification » est un texte (pas une icône seule).
- **Couleur.** Bordures `border-warning/60` pour suspension, fermeture, restriction ; texte toujours `text-foreground` (jamais `text-warning` pour du texte courant, contraste insuffisant). Statuts toujours icône + mot.
- **Zoom 200 % et petits écrans (320 px)** : pas de largeur fixe ; noms tronqués avec `title` ; grille `dl` repliée en une colonne sous 768 px.
- **Mouvement** : apparition des champs de E26 sans animation si `prefers-reduced-motion: reduce`.
- **Lecteur d'écran** : la date longue est lue en clair (« 20 novembre 2026 ») ; ne pas utiliser de format numérique seul.

---

## 14. Réseau faible et mobile

- **Zéro requête de plus** pour les bannières, les badges et la vue réduite : tout vient de `contexts/` et `internal/`, déjà chargés.
- **E19** : un appel `restrictions/` (page 1, 20 éléments, quelques kilo-octets) ; historique chargé **à la demande** seulement. Cache React Query 5 min ; relecture au focus de fenêtre désactivée.
- **E4 en `CLOSING`** : au plus un appel `internal/` pour la date (4.4) ; aucun si la réponse de la fermeture est dans l'état de navigation.
- **E26** : `name-change-requests/?page_size=5` ; aucune image ; envoi de pièces : contrôle de taille et de format avant envoi (`checkKycFile`), barre de progression existante si présente dans `DocumentRow`, sinon `Loader2`. Pas de compression d'un PDF.
- **Aucune action différée ni rejouée automatiquement** (fermeture, annulation, reprise, demande de nom, envoi de pièce, réponses) : hors ligne, boutons désactivés avec la raison.
- **Mobile** : bannières compactes au-delà de deux (5.1) ; boutons pleine largeur sous 768 px ; pas de barre d'action fixe (masquée par le clavier) ; `ResponsiveDialog` en feuille basse pour la fermeture.
- **Images** : seul le logo (`UserAvatar`, ≤ 40 px, initiales si absent).

---

## 15. Conformité aux règles verrouillées

| Règle | Application |
|---|---|
| 2. Permissions ≠ droits commerciaux | Aucun écran ne propose d'acheter, de payer ou d'utiliser un plan pour lever une restriction, éviter une fermeture ou accélérer une demande de nom. Aucun lien vers la facturation dans E19, E4, E26. |
| 3. La vérification ne s'achète pas et dit ce qui est vérifié | Le nouveau nom est toujours marqué « En cours de vérification » et n'est jamais accompagné de `VerifiedClaims` ; textes `nameChange.before.noInherit` et `nameChange.docs.noBadge` ; aucune mention « vérifié » sur une demande non aboutie ; la décision est celle de l'équipe Vérification. |
| 4. Aucun score de confiance | Une restriction est affichée comme un état factuel (mesure, dates), jamais comme une note, un niveau ou une couleur de « fiabilité ». La dormance n'est pas présentée comme un signal de qualité. |
| 5. « Sponsorisé » | Non concerné ; `StatusBadge` (réservé à « Sponsorisé ») n'est pas utilisé pour les statuts d'organisation. |
| 8. États indépendants | Un badge et un bloc par axe ; cumuls explicitement rendus (4.1, 5.1). |
| 10. Données par finalité | Aucun écran n'affiche note interne, auteur, origine, preuve, nom de membre ; motif masqué en divulgation limitée avec un texte qui ne dit pas pourquoi précisément ; détail réservé à `org.view_restrictions` ; acheteurs : texte neutre sans le mot « restriction » ; `legal_name` visible des seuls rôles qui le reçoivent ; aucune URL de pièce. |
| 12. Audit | Fermeture, annulation, reprise, demande de nom passent par les routes qui journalisent (ADR 0011 §8) ; ressaisie du mot de passe pour fermeture et demande de nom. |
| Q19 | Aucune phrase « contactez » sans lien ; liens d'aide conditionnels (`HELP_LINKS`). |

---

## 16. Décisions de design à valider

| # | Décision | Pourquoi | Alternative |
|---|---|---|---|
| DV-1 | Libellé de l'état `DORMANT` : **« Inactive »** (le contrat dit « Dormante ») | Mot courant, compris sans explication ; Q34 dit « Inactive/dormante » | « Dormante » (plus proche du modèle, moins clair pour le public visé) |
| DV-2 | E19 est une **page** sans onglet, atteinte par bannière, notification ou refus | L'écran n'a de sens que s'il y a une restriction ; un onglet vide permanent est du bruit | Onglet « Restrictions » visible quand `measures` non vide |
| DV-3 | Les rôles sans `org.view_restrictions` voient **les mesures** (bannière, vue réduite) mais ni catégorie ni motif | Q33 + QL-11 ; ils doivent comprendre pourquoi un bouton a disparu | Ne rien montrer aux éditeurs, analystes, membres |
| DV-4 | Ordre des bannières : restriction, administration à régulariser, en cours d'examen, inactive (amende L1-01-D2 qui mettait `MISSING` en premier) | Ce qui bloque une action maintenant d'abord | Gouvernance en premier |
| DV-5 | Refus `DENY_RESTRICTION` côté acheteur : **même texte neutre** que `seller_contact_unavailable` | Règle 10 et contrat §5 : aucune réponse publique ne mentionne une restriction | Texte spécifique (révélerait une mesure à un tiers) |
| DV-6 | Confirmer l'activité d'une organisation inactive : **un tap, sans dialogue** | Action réversible, sans effet sur les tiers | Dialogue de confirmation (une étape de plus en 3G) |
| DV-7 | Fermeture : **aucun délai affiché avant l'envoi**, date d'effet après la réponse | Le délai est un réglage non exposé (ADR 0011 §4.8) | Exposer `closure_delay_days` dans un endpoint de réglages publics |
| DV-8 | Demande de nom : **page dédiée**, pas un dialogue | Formulaire long + envoi de fichiers sur Android d'entrée de gamme | Feuille basse (`ResponsiveDialog`) |
| DV-9 | Correction d'une faute : champs **préremplis**, motif `typo` imposé et non affiché | Moins de saisie, moins d'erreurs | Champs vides et motif à choisir |
| DV-10 | Après une restriction ciblée, le bouton concerné **disparaît** (capacités calculées par le serveur) et l'explication est dans la bannière | Contrat §1.2 sans changement | QD-1 : notice à l'emplacement du bouton |
| DV-11 | Recours `SUPPORT_REQUEST` sans `HELP_LINKS.appeal` : phrase « Un réexamen de cette mesure peut être demandé. » **sans** lien ni moyen | Informer d'un droit sans inventer de canal | Masquer la ligne Recours tant que L1-21 n'existe pas (QD-3) |

---

## 17. Questions ouvertes

### 17.1 Pour l'architecte ou le chef de projet

- **QD-1 (capacités restreintes).** Ajouter à `contexts/ results[]` et `internal/` une clé additive `restricted_capabilities` (capacités du rôle bloquées par une mesure ciblée) permettrait d'afficher `RestrictionNotice` **à l'emplacement** du bouton (« Publier une offre ») au lieu de le faire disparaître. Recommandation : oui (une liste de chaînes, zéro requête de plus). Sans elle, la spec fonctionne avec la bannière seule (DV-10).
- **QD-2 (reprise sous `PROFILE_EDIT_BLOCK`).** `POST resume/` exige `org.edit_profile`, que `PROFILE_EDIT_BLOCK` refuse : une organisation inactive et restreinte sur son profil ne peut pas confirmer son activité (seul le cron la réactivera). Recommandation : rattacher `resume/` à une capacité non restreignable ou l'exempter de cette mesure. À trancher avant B3.
- **QD-3 (recours sans canal).** Tant que L1-21 n'existe pas, faut-il afficher « Un réexamen peut être demandé » sans moyen de le faire (DV-11) ou masquer la ligne ? Q19 exige un canal fonctionnel avant le lancement ; la question ne vaut que pour la recette.
- **QD-4 (date d'effet dans `unavailable`).** Ajouter `closure_effective_at` aux éléments `unavailable` (12e clé, nulle hors `CLOSING`) éviterait l'appel `internal/` de 4.4. Recommandation : non en V1 (la clé ne sert qu'à un état rare) ; à reconsidérer si la recette 3G le demande.
- **QD-5 (pièces de la demande de nom).** `org.verification_submit` et `org.request_name_change` sont-ils détenus par les mêmes rôles (`OWNER`, `ADMIN`) ? La spec prévoit le cas contraire (`nameChange.docs.askAdmin`), à confirmer pour éviter un texte inutile.

### 17.2 Pour le client (via l'utilisateur)

- **QC-1 (libellé).** « Inactive » ou « Dormante » pour l'organisation sans activité (DV-1) ?
- **QC-2 (motif de fermeture « fusion »).** Le texte `org.closure.reason.mergedHint` affirme que rien n'est transféré vers l'autre organisation (Q35 par analogie). À confirmer.
- **QC-3 (textes des catégories).** Les explications des neuf catégories sont saisies en back-office (A-L17) ; elles apparaissent telles quelles dans E19 : prévoir une relecture par le client avant la production.

---

## 18. Critères d'acceptation (front)

### F-L17-1
- [ ] `organizationStates` : 4 cycles de vie × suspendue oui/non × mesures vides/non vides ; champs absents tolérés.
- [ ] `DENY_RESTRICTION` dans `DENY_CODES`, absent de `CONTEXT_DENY_CODES` ; un refus de restriction ne change jamais le profil actif (test).
- [ ] `describeApiError` : une clé par mesure, repli `generic`, `asBuyer` → texte neutre.
- [ ] Badges « Inactive », « Fermeture en cours », « Restriction en cours » ; le champ `status` n'est plus lu (recherche statique).

### F-L17-2
- [ ] E19 `OWNER`/`ADMIN` : toutes les lignes de 3.4 ; `LIMITED` → texte fixe, jamais `null` affiché ; aucune clé hors contrat rendue (test d'ensemble de clés de la fixture).
- [ ] E19 autres rôles : vue réduite, **aucun appel** à `restrictions/` (test réseau).
- [ ] E19 accessible sous suspension et en `ARCHIVED` (la vue indisponible ne la masque pas).
- [ ] Vue indisponible : 5 cas de 4.1 × rôles (`OWNER`, `ADMIN`, `EDITOR`) ; bouton « Voir le détail » seulement avec `org.view_restrictions`.
- [ ] Bannières : ordre 5.1, cumul restriction + `MISSING` affiché ; aucun rôle vivant sur les bannières ; une seule région `aria-live` sur chaque page d'organisation.
- [ ] 6.3 : chaque écran conserve la saisie et affiche `RestrictionNotice` ; 6.4 : texte neutre côté acheteur, sans le mot « restreint ».
- [ ] Aucun texte « contactez » sans lien (`grep -i "contactez" fr.ts` ne renvoie que des textes accompagnés d'un lien conditionnel, ou rien).

### F-L17-3
- [ ] Dialogue de fermeture : motif obligatoire, case, mot de passe ; chaque code de 7.5 ; mot de passe vidé après erreur.
- [ ] `200 ARCHIVED` et `200 CLOSING` : navigation, toast, aucune alerte de perte.
- [ ] Vue `CLOSING` : date (état de navigation ou `internal/`), obligations, annulation (`200`, `409`, `DENY_OBJECT_STATE`).
- [ ] Bannière inactive : bouton selon `org.edit_profile` ; `200` et `409 organization_not_dormant` → bannière retirée et annonce.
- [ ] Archivée : texte 4.5 selon `HELP_LINKS.restoration`.

### F-L17-4
- [ ] `legal_name` affiché seulement si non nul ; deux champs `readOnly` si `name_locked` ; lien E26 selon la capacité.
- [ ] E26 : trois types, champs conditionnels, `nothing_to_change`, `already_open`, `not_required`, ressaisie.
- [ ] Suivi : ancien nom « affiché publiquement » + nouveau nom « En cours de vérification », aucun `VerifiedClaims` ; six statuts ; `new_entity_required` avec lien de création.
- [ ] Justificatifs : envoi rattaché (`name_change_request_id`), passage en examen annoncé, aucune URL de fichier.

### Recette (Q-L17)
Android d'entrée de gamme, 3G simulée, TalkBack : E19, vue `CLOSING` + suspendue, dialogue de fermeture, E26 avec envoi d'une pièce de 2 Mo ; zoom 200 % ; navigation clavier complète.
