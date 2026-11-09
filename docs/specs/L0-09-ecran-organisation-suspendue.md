# L0-09 UX-SUSP — Spécification : organisation suspendue ou archivée (propriétaire et équipe)

- **Date :** 09/11/2026
- **Auteur :** designer-ux
- **Destinataires :** architecte-technique (contrat, section 3), dev-backend (tâche B-SUSP), dev-frontend (tâche F-SUSP)
- **Réf. :** CDC v1.2 §3.1, §6 ; CLAUDE.md règles 3, 10, 12 ; ADR 0006 §6.2 (résolution du contexte), §9.1 et §9.2 (contrat), §20 (T9 : organisations converties `SUSPENDED`, réactivation par le personnel) ; spec `docs/specs/L0-09-ecrans-contextes.md` (E1, E2, E4, E13, E14, décisions D8 et D9).
- **Statut :** proposition. Décisions à valider en section 9, questions pour le client en section 10.

---

## 0. Lecture rapide

1. **Le problème.** Aujourd'hui `GET accounts/contexts/` ne renvoie que les organisations `ACTIVE` (`get_contexts_for_user`, `acting.py`). Une organisation suspendue ou archivée disparaît donc du sélecteur et de « Mes profils ». `GET organizations/<id>/internal/` répond `403 DENY_SECURITY` (suspendue) ou `403 DENY_OBJECT_STATE` (archivée), sans rôle ni nom. Le front ne peut afficher que des phrases génériques, et `DENY_SECURITY` est le même code quand c'est le **compte** qui est restreint : le texte actuel `org.denied.security` / `errors.deny.SECURITY.lost` (« Cette organisation est suspendue. ») peut donc être faux.
2. **Cas qui rend la correction nécessaire.** Après T9, un ancien compte entreprise dont le propriétaire était désactivé ou sous sanction devient une organisation `SUSPENDED` créée telle quelle. **Aucun événement de statut n'est émis** (la création n'est pas une transition) : aucune notification, aucun message. Le propriétaire n'a plus d'offres sous son profil personnel, aucune organisation dans le sélecteur, et rien ne lui explique pourquoi.
3. **La solution en une phrase.** Le serveur ajoute `status` aux profils et une liste `unavailable` dans la réponse de `contexts/` (une seule requête, déjà mise en cache) ; le front affiche, pour ces organisations, **un seul écran en lecture seule** (statut, rôle, quitter, recours) à la place de « accès refusé », et enrichit l'alerte « profil perdu ».
4. **Ce que l'interface ne dit jamais :** le motif, qui a décidé, la sanction du propriétaire, ni qu'une vérification est en cause (règle 10, règle 3). Un seul texte par statut, identique pour tous les motifs.
5. **Une seule action principale** sur l'écran : « Contacter le support » n'existe pas comme fonction (aucune page de support dans le front, aucun canal défini) ; l'écran est donc **informatif** et son action utile est secondaire : « Quitter l'organisation ». Voir section 6.

---

## 1. Objectif et utilisateur

- **Objectif.** Dire à un membre d'une organisation `SUSPENDED` ou `ARCHIVED` : (a) ce qui lui arrive, (b) ce qui n'est plus possible, (c) ce qu'il peut encore faire, (d) à qui s'adresser. Sans jamais le laisser dans un état silencieux (principe de la spec E1 : aucun repli silencieux).
- **Utilisateurs.** Propriétaire, administrateur, éditeur, analyste, connectés au compte unique, souvent sur Android d'entrée de gamme en 3G. Le propriétaire d'une organisation convertie (E14) est le cas le plus exposé : il n'a pas demandé la suspension et ne connaît pas le nouveau modèle.
- **Hors périmètre.** Le côté personnel (back-office, bouton de réactivation, motif choisi par le personnel) ; la gestion des membres (L1-01) ; une page ou un formulaire de support ; l'affichage public d'une organisation suspendue (le public reçoit 404, ADR §9.7) ; le cas « organisation `ACTIVE` dont le propriétaire est sanctionné » (le statut ne change pas, la restriction est portée par le compte : refus `DENY_SECURITY` du compte, texte `errors.deny.SECURITY.action`, déjà couvert).

## 2. Parcours

### 2.1. Points d'entrée

| # | Entrée | Comportement |
|---|---|---|
| P1 | **Retour forcé au profil personnel** (profil actif devenu suspendu/archivé : valeur mémorisée absente de `results`) | `ContextLostAlert` (existant) enrichi : texte selon le statut et lien « Voir l'état de l'organisation » (2.3). |
| P2 | **Mes profils** (`/profiles`) | Nouvelle section « Organisations indisponibles » sous « Organisations » (4.1). |
| P3 | **Lien direct / notification** `/organizations/:id` (et `/edit`, `/verification`, `/team`) | `OrganizationPage` détecte l'organisation dans `unavailable` et affiche la vue indisponible (4.2) à la place de `AccessDenied`. |
| P4 | **Après archivage par le propriétaire** (`POST archive/` → 200) | Pas de retour au personnel avec alerte destructive : navigation vers `/organizations/:id` qui affiche la vue « Archivée » (le propriétaire vient de le décider : pas d'alerte d'erreur). Toast `org.unavailable.archivedDone`. |
| P5 | **Tableau de bord / « Mes offres » en profil personnel**, sans offre, alors que `unavailable` n'est pas vide | Phrase d'aide + lien vers l'organisation (4.4). |
| P6 | **Notification** « Organisation suspendue / archivée » | Le lien de la notification passe de `/dashboard` à `/organizations/<id>` (tâche B-SUSP, 5.1). |

### 2.2. Parcours nominal (propriétaire d'une organisation convertie, suspendue à la conversion)

1. Connexion. `contexts/` répond : `results` = Personnel ; `unavailable` = « Atelier X », `SUSPENDED`, rôle `OWNER`.
2. Le profil mémorisé est Personnel : pas d'alerte « perdu ». La page d'accueil du compte ne montre aucune offre. Le tableau de bord personnel vide affiche la phrase P5 avec le lien « Voir Atelier X ».
3. Clic → `/organizations/:id` : vue indisponible (4.2) : badge « Suspendue », message, rôle, « Quitter l'organisation », texte de recours.
4. Sorties : retour à « Mes profils » ; quitter l'organisation (parcours 2.4) ; lire le texte de recours et contacter le support par un moyen extérieur à l'application (section 6).

### 2.3. Parcours « profil actif devenu indisponible »

1. L'utilisateur agit sous « Atelier X ». Un membre du personnel suspend l'organisation.
2. Sa prochaine requête avec `X-Context` reçoit `403 DENY_SECURITY`. Le front recharge `contexts/` (règle 9.1 existante), constate que le profil n'est plus dans `results`, **cherche son id dans `unavailable`**.
3. Trouvé → `ContextLostAlert` avec le texte spécifique au statut (4.3) et le lien « Voir l'état de l'organisation ». Non trouvé → texte générique existant `errors.deny.SECURITY.lost`, **corrigé** pour ne plus affirmer une suspension d'organisation (5.4).
4. Le profil actif devient Personnel (inchangé). Les formulaires en cours ne sont pas republiés sous un autre profil (règle E12.4, inchangée).

### 2.4. Quitter l'organisation depuis la vue indisponible

`org.leave` est la seule capacité conservée (ADR §9.2, §6.2 : seule exception à la garde de compte). Le parcours réutilise `LeaveOrganizationCard` et son `AlertDialog` (focus initial sur « Annuler »). Erreurs : `409 last_owner` (message existant `errors.code.last_owner`), réseau, hors ligne. Succès : `invalidateContexts`, toast « Vous avez quitté l'organisation. », navigation vers `/profiles` ; l'entrée disparaît de `unavailable`.

### 2.5. Cas d'erreur

| Cas | Comportement |
|---|---|
| `contexts/` en erreur (5xx, 429, réseau) sans cache | `ErrorState` avec « Réessayer » (existant) ; la vue indisponible ne s'affiche pas sur une hypothèse. |
| `403 DENY_SECURITY` sur `internal/` et id **absent** de `unavailable` | C'est le compte qui est restreint : `AccessDenied` avec `org.denied.accountRestricted` (5.3). |
| `403 DENY_RELATION` (non-membre, ancien membre) | Inchangé : `org.denied.relation`. Une organisation dont l'utilisateur n'est plus membre n'apparaît jamais dans `unavailable`. |
| Organisation réactivée entre-temps (cache périmé) | À l'ouverture de la vue, `contexts/` est relu une fois (en ligne). Si l'organisation est de nouveau dans `results` : redirection vers `/organizations/:id` normal, sans message. |
| Hors ligne | Vue servie depuis le cache React Query ; bouton « Quitter » désactivé avec `common.offlineAction`. Rien n'est mis en file. |

---

## 3. Contrat d'API à ajouter (ADR 0006 §9.1, amendement à valider par l'architecte)

### 3.1. Principe

- **Pas de nouvel endpoint.** `contexts/` est déjà appelé au démarrage, mis en cache 5 min, et c'est lui qui pilote la perte de profil. Ajouter une liste dans la même réponse coûte zéro requête supplémentaire sur 3G et garde une seule source de vérité.
- **`results` reste réservé aux profils sous lesquels on peut agir** (organisations `ACTIVE` seulement) : le sélecteur ne montre jamais un profil inutilisable, et la règle « absent de `results` = perdu » du front ne change pas.
- **`unavailable`** liste les organisations `SUSPENDED` ou `ARCHIVED` dont le compte est **membre actif** (Membership `ACTIVE`). Un ancien membre (révoqué, parti) n'y figure pas. Tri : nom insensible à la casse puis identifiant (même tri que `results`). Non paginé : borné par le plafond d'organisations (`organization_limit_reached`).
- **Le compte reste utilisable.** `contexts/` est déjà exempt des capacités ; il doit continuer de répondre `200` à un compte restreint (la liste d'un compte sanctionné doit contenir `unavailable` pour expliquer l'état) : à vérifier par un test.

### 3.2. Réponse `GET /api/accounts/contexts/` (champs ajoutés en gras dans la description)

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "type": "USER",
      "id": "6f1c0a52-0000-4000-8000-000000000001",
      "name": "Marie Kabongo",
      "role": null,
      "org_type": null,
      "photo": null,
      "capabilities": ["offer.view_internal"],
      "migrated_from_business": false,
      "status": "ACTIVE"
    },
    {
      "type": "ORGANIZATION",
      "id": "6f1c0a52-0000-4000-8000-0000000000a1",
      "name": "Aide Kin",
      "role": "EDITOR",
      "org_type": "ONG",
      "photo": null,
      "capabilities": ["offer.publish", "offer.edit", "offer.view_internal", "org.view_internal", "org.leave"],
      "migrated_from_business": false,
      "status": "ACTIVE"
    }
  ],
  "unavailable": [
    {
      "type": "ORGANIZATION",
      "id": "6f1c0a52-0000-4000-8000-0000000000b2",
      "name": "Atelier X",
      "role": "OWNER",
      "org_type": "ENTREPRISE",
      "photo": null,
      "capabilities": ["org.leave"],
      "migrated_from_business": true,
      "status": "SUSPENDED"
    }
  ]
}
```

(Les listes `capabilities` ci-dessus sont des exemples : la valeur réelle vient de la matrice de l'ADR §5.)

| Champ | Type | Règle |
|---|---|---|
| `status` (nouveau, **tous** les éléments de `results` et de `unavailable`) | `"ACTIVE"` \| `"SUSPENDED"` \| `"ARCHIVED"` | `results` : toujours `"ACTIVE"` (USER, PROVIDER et organisations). `unavailable` : `"SUSPENDED"` ou `"ARCHIVED"`. Valeurs identiques à `OrganizationStatus` (`types.ts`). |
| `unavailable` (nouveau, clé de premier niveau) | tableau | Toujours présent, vide `[]` s'il n'y a rien. Éléments de type `ORGANIZATION` uniquement (un prestataire archivé reste traité par `provider/`, hors périmètre). |
| `unavailable[].capabilities` | tableau de chaînes | Toujours `["org.leave"]` pour un membre actif de tout rôle. Le front affiche « Quitter » seulement si la capacité est présente (décision D9). |
| `unavailable[].role` | `OWNER` \| `ADMIN` \| `EDITOR` \| `ANALYST` | Rôle du membre dans l'organisation. |

**Champs volontairement absents** (règle 10 et règle 3) : motif de suspension (`suspension_reason`), date de suspension, auteur de la décision, nombre de membres, noms d'autres membres, NIF, état des pièces de vérification, sanction du propriétaire. `Organization.suspension_reason` (liste `moderation`, `verification`, `legal`, `other`) **ne sort pas de l'API** : même une catégorie « moderation » ou « legal » révèle la nature d'une décision du personnel, et pour les organisations converties la cause est la sanction d'une autre personne (le propriétaire) que l'éditeur n'a pas à connaître. Si le client souhaite afficher une catégorie, la seule forme admise est une liste blanche à deux valeurs `reason: "verification" | "other"` réservée aux rôles `OWNER` et `ADMIN` (question Q-SUSP2) ; elle n'est pas dans ce contrat.

### 3.3. Autres endpoints

| Endpoint | Changement |
|---|---|
| `GET organizations/<id>/internal/` | **Inchangé** (`403 DENY_SECURITY` suspendue, `403 DENY_OBJECT_STATE` archivée). Le front ne tente pas de lire le détail d'une organisation indisponible : il lit `unavailable`. |
| `POST organizations/<id>/archive/` | Inchangé (200 `OrganizationInternal` `status = "ARCHIVED"`). |
| `POST organizations/<id>/leave/` | Inchangé ; doit rester `204` pour une organisation suspendue ou archivée (ADR T8). |
| `OrganizationInternal.status` | Déjà présent. Aucun changement. |
| Notification `identity.seller_context_status_changed` | Le lien passe de `/dashboard` à `/organizations/<uuid>` ; voir 5.1. |
| Réponse 403 `DENY_SECURITY` : `detail` | Reste sans nom d'organisation ni motif. Le front n'affiche jamais `detail` (il utilise les clés i18n). |

### 3.4. Interface TypeScript attendue (pour dev-frontend, `api/types.ts`)

```ts
export interface AvailableContext { /* existant */ status: OrganizationStatus; }  // "ACTIVE" dans results
export interface UnavailableOrganization extends Omit<AvailableContext, "type"> {
  type: "ORGANIZATION"; status: "SUSPENDED" | "ARCHIVED"; role: OrganizationRole; org_type: OrganizationType;
}
export interface ContextsResponse { count: number; next: string | null; previous: string | null;
  results: AvailableContext[]; unavailable?: UnavailableOrganization[]; }  // absent = []
```

`unavailable` est typé optionnel pour tolérer un serveur plus ancien ; absent est traité comme `[]`. Le test de contrat `backend-identity-contract.test.ts` et la fixture `__fixtures__/contexts.json` sont mis à jour avec ce JSON. Les clés d'un élément de `results` passent de 8 à 9 (`active-context.test.ts` à ajuster).

---

## 4. Structure des écrans

Aucun nouvel écran de navigation. Quatre emplacements. Mobile et desktop ont la même structure ; seules les largeurs changent.

### 4.1. Mes profils (`/profiles`, E2) : section « Organisations indisponibles »

Placée sous la section « Organisations », **affichée seulement si `unavailable` n'est pas vide**. L'état vide de « Organisations » (« Aucune organisation ») ne s'affiche pas si `unavailable` est non vide (sinon contradiction) ; il est remplacé par la liste « Organisations » vide masquée.

```
Organisations indisponibles                         <h2>
Vous ne pouvez plus agir au nom de ces organisations.
┌───────────────────────────────────────────┐
│ [logo carré] Atelier X                     │  <article>, un seul lien principal
│ Entreprise · Propriétaire                  │
│ (⏸ Suspendue)                              │  badge texte + icône
│                          [Voir l'état]     │
└───────────────────────────────────────────┘
```

- Carte : `UserAvatar shape="square"`, nom (`truncate`, `title`), `SellerTypeBadge compact`, `RoleBadge`, **`OrganizationStatusBadge`** (nouveau, 5.2). Lien principal « Voir l'état » vers `/organizations/:id` (patron `after:absolute after:inset-0` de la carte organisation).
- **Aucun** bouton « Agir sous ce profil ». Aucune carte n'est cliquable pour devenir le profil actif.
- Chargement : couvert par le chargement de `contexts/` (3 `Skeleton`). Erreur / hors ligne : comme la section « Organisations ».

### 4.2. Vue indisponible `/organizations/:id` (et sous-routes), nouveau composant `OrganizationUnavailableView`

`OrganizationPage` (existant) : avant d'afficher `AccessDenied`, il consulte `unavailable` ; si l'id y figure, il rend `OrganizationUnavailableView` **à la place de** `children(org)` et **sans** `OrganizationTabs`. Les routes `/edit`, `/verification`, `/team` rendent la même vue (les onglets n'existent plus : pas de pièces, pas de formulaire, pas de rôles).

```
┌──────────────────────────────────────────┐
│ ENTREPRISE                               │  eyebrow (orgType)
│ [logo] Atelier X        (⏸ Suspendue)    │  <h1> + OrganizationStatusBadge
├──────────────────────────────────────────┤
│ (i) Cette organisation est suspendue      │  Alert (role="status"), titre + 2 paragraphes
│ Ses offres ne sont plus visibles…         │
│ Pour en savoir plus, contactez le support │
├──────────────────────────────────────────┤
│ Votre rôle                                │  Card : RoleBadge + role.<R>_desc (existant)
│ [Propriétaire]                            │
├──────────────────────────────────────────┤
│ Ce qui n'est pas possible actuellement    │  Card : liste à puces (6.1)
│ • Publier ou modifier des offres …        │
├──────────────────────────────────────────┤
│ Quitter l'organisation                    │  LeaveOrganizationCard (existant, adapté)
│ [Quitter l'organisation]                  │
└──────────────────────────────────────────┘
```

Ordre de haut en bas : `PageHeader` (sans bouton d'action ; **pas** de « Agir sous ce profil ») → `Alert` de statut → carte « Votre rôle » → carte « Ce qui n'est pas possible actuellement » → `LeaveOrganizationCard`. Desktop : `AccountShell` (menu latéral) et colonne unique `max-w-2xl` ; pas de grille à deux colonnes (le contenu est court et linéaire).

**Masqué dans cette vue (jamais désactivé grisé, pour ne pas laisser croire à une panne) :** onglets Aperçu/Profil/Vérification/Équipe ; « Agir sous ce profil » ; « Voir le profil public » (le public reçoit 404) ; « Modifier le profil » ; « Envoyer les pièces » ; carte « Vérification » ; carte « Archiver l'organisation » ; liste des capacités (`org.home.canTitle`).

**Conservé :** nom, logo, type, rôle, statut, quitter, texte de recours.

### 4.3. Alerte « profil perdu » (`ContextLostAlert`, existant)

Ajouter un second cas dans `lostMessageKey` : si l'id perdu est dans `unavailable`, utiliser `errors.lost.suspended` ou `errors.lost.archivedByStatus` (5.3). La structure ne change pas (titre, texte, nom du profil, « J'ai compris »). Ajouter, avant « J'ai compris », un lien-bouton secondaire « Voir l'état de l'organisation » → `/organizations/:id`. `LostReason` (`active-context.ts`) porte l'id perdu (champ `lostId`) pour construire le lien ; sans id, pas de lien.

Rappel : `lostMessageKey` renvoie aujourd'hui `errors.lost.archived` pour « archivé » (archivage par soi-même) et `errors.deny.<REASON>.lost` sinon. Le cas `ARCHIVED` d'une organisation archivée par un autre membre passe par `OBJECT_STATE` : même traitement que `SECURITY`.

### 4.4. États vides dépendants (E12.3)

Dans l'`EmptyState` du tableau de bord, de « Mes offres » et de la corbeille en profil personnel : si `unavailable` n'est pas vide et qu'il n'y a pas d'offre personnelle, ajouter la phrase `emptyOffers.unavailableOrg` avec le lien « Voir {{name}} » (première organisation de la liste ; si plusieurs : lien « Voir mes organisations indisponibles » vers `/profiles`). Cette phrase **remplace** `emptyOffers.otherProfiles` (qui renverrait vers un sélecteur où l'organisation n'apparaît plus).

### 4.5. Information de première connexion (organisations converties)

`LegacyOrgNotice` (E14) ne couvre que `results` : une organisation migrée et suspendue n'en bénéficie pas. Ne pas l'étendre (son action « Agir sous ce profil » est impossible). La vue 4.2 suffit : si `migrated_from_business` est vrai, elle ajoute **un paragraphe** `org.unavailable.migrated` sous le message de statut (5.3). Pas de bandeau global supplémentaire.

---

## 5. Contenus (français, clés i18n)

Principes : ton neutre ; phrases courtes ; aucune mention de motif, de sanction, d'auteur de la décision, de personnel de la plateforme nommé ; aucune promesse de réactivation ; aucun « garantie », « vérifié ». « Support de Connecte+ » reprend la formule déjà utilisée dans l'application (`errors.deny.SECURITY.action`, `org.nameLocked`).

### 5.1. Textes de statut (cœur)

| Clé | Texte |
|---|---|
| `org.status.SUSPENDED` | `Suspendue` |
| `org.status.ARCHIVED` | `Archivée` |
| `org.status.aria` | `Statut de l'organisation : {{status}}` |
| `org.unavailable.title.SUSPENDED` | `Cette organisation est suspendue` |
| `org.unavailable.title.ARCHIVED` | `Cette organisation est archivée` |
| `org.unavailable.body.SUSPENDED` | `Ses offres ne sont plus visibles du public. Vous ne pouvez plus la modifier ni agir en son nom pour le moment.` |
| `org.unavailable.body.ARCHIVED` | `Ses offres ne sont plus visibles du public. Elle ne peut plus être modifiée.` |
| `org.unavailable.recourse.SUSPENDED.OWNER` | `Pour en savoir plus sur cette suspension, contactez le support de Connecte+.` |
| `org.unavailable.recourse.SUSPENDED.other` | `Pour en savoir plus, adressez-vous au propriétaire de l'organisation ou au support de Connecte+.` |
| `org.unavailable.recourse.ARCHIVED.OWNER` | `Un archivage ne peut pas être annulé depuis l'application. Pour toute question, contactez le support de Connecte+.` |
| `org.unavailable.recourse.ARCHIVED.other` | `Pour toute question, adressez-vous au propriétaire de l'organisation.` |
| `org.unavailable.migrated` | `Cette organisation vient de votre ancien compte entreprise.` |
| `org.unavailable.roleTitle` | `Votre rôle` (réutiliser `org.home.roleTitle`) |
| `org.unavailable.blockedTitle` | `Ce qui n'est pas possible actuellement` |
| `org.unavailable.leaveBody` | `Vous perdrez l'accès à cette organisation. Elle n'apparaîtra plus dans vos profils.` |
| `org.unavailable.archivedDone` | `Organisation archivée.` (toast, P4) |
| `org.unavailable.listTitle` | `Organisations indisponibles` |
| `org.unavailable.listDescription` | `Vous ne pouvez plus agir au nom de ces organisations.` |
| `org.unavailable.see` | `Voir l'état` |
| `org.unavailable.seeAria` | `Voir l'état de {{name}}` |
| `org.unavailable.seeFromAlert` | `Voir l'état de l'organisation` |
| `emptyOffers.unavailableOrg` | `Vos offres d'entreprise sont liées à « {{name}} », qui n'est plus disponible pour le moment.` |
| `emptyOffers.unavailableOrgLink` | `Voir {{name}}` |
| `emptyOffers.unavailableOrgs` | `Certaines de vos organisations ne sont plus disponibles pour le moment.` |
| `emptyOffers.unavailableOrgsLink` | `Voir mes organisations` |

Règle de sélection du recours : `OWNER` → clé `.OWNER` ; `ADMIN`, `EDITOR`, `ANALYST` → clé `.other`. C'est la seule différence entre rôles (6.2).

### 5.2. Contenu de la carte « Ce qui n'est pas possible actuellement » (identique pour les deux statuts et tous les rôles)

| Clé | Texte |
|---|---|
| `org.unavailable.blocked.offers` | `Publier, modifier ou renouveler des offres.` |
| `org.unavailable.blocked.profile` | `Modifier le profil de l'organisation.` |
| `org.unavailable.blocked.verification` | `Envoyer ou consulter les pièces de vérification.` |
| `org.unavailable.blocked.messages` | `Répondre aux messages et aux avis.` |
| `org.unavailable.blocked.team` | `Gérer l'équipe et les rôles.` |

La liste est la même quel que soit le rôle : le serveur refuse tout pour tous (`unavailable[].capabilities = ["org.leave"]`). Elle ne dépend d'aucune capacité du rôle (inutile d'expliquer à un analyste ce qu'il ne pouvait de toute façon pas faire).

### 5.3. Textes de l'alerte « profil perdu » et de l'accès refusé

| Clé | Texte | Usage |
|---|---|---|
| `errors.lost.suspended` | `Cette organisation est suspendue. Vous agissez maintenant sous votre profil personnel.` | `ContextLostAlert`, id trouvé dans `unavailable` avec `SUSPENDED` |
| `errors.lost.archivedByStatus` | `Cette organisation est archivée. Vous agissez maintenant sous votre profil personnel.` | idem, `ARCHIVED` |
| `errors.deny.SECURITY.lost` (**modifié**) | `Votre profil n'est plus disponible pour le moment. Vous agissez maintenant sous votre profil personnel.` | id **absent** de `unavailable` (compte restreint ou cause inconnue) |
| `org.denied.security` (**modifié**) | `Cet accès est limité pour le moment.` | `AccessDenied` quand le 403 `DENY_SECURITY` ne correspond à aucune entrée de `unavailable` |
| `org.denied.accountRestricted` | `Votre compte est limité pour le moment. Pour en savoir plus, contactez le support de Connecte+.` | idem, avec le recours |
| `org.denied.archived` | `Cette organisation est archivée.` | (existant) cas résiduel `DENY_OBJECT_STATE` sans entrée dans `unavailable` |

Aucun texte n'indique pourquoi le compte est limité.

### 5.4. Corrections de textes existants

`org.denied.security` et `errors.deny.SECURITY.lost` affirment aujourd'hui « Cette organisation est suspendue » sur la seule foi de `DENY_SECURITY`. Après ce changement ils ne servent qu'au cas où l'on ne peut pas confirmer la suspension (5.3). `errors.deny.SECURITY.action` (« le compte ou l'organisation est limité ») reste valable : il parle d'une action, pas du profil.

### 5.5. Messages de notification (côté serveur, tâche B-SUSP)

Les textes de `_STATUS_MESSAGES` (`notifications/events.py`) sont déjà neutres : « L'organisation « {name} » a été suspendue : ses offres ne sont plus publiques. ». Les conserver. Changer seulement `link` (`/dashboard` devient `/organizations/<id>`). Les notifications d'une organisation restent visibles de ses membres même suspendue (ADR §19.3.6).

---

## 6. Actions masquées ou désactivées, par rôle et par statut

### 6.1. Principe

Pour `SUSPENDED` **et** `ARCHIVED`, le serveur refuse toute action d'organisation (la seule capacité conservée est `org.leave`). Les deux statuts ont donc **le même ensemble d'actions** ; ils ne diffèrent que par les textes (5.1). Le front n'applique pas de matrice de rôle ici : il lit `unavailable[].capabilities`.

### 6.2. Tableau

Légende : **V** visible et actif ; **—** masqué ; **T** texte seulement (pas de bouton).

| Élément | Propriétaire | Administrateur | Éditeur | Analyste |
|---|---|---|---|---|
| Badge de statut (`Suspendue` / `Archivée`) | V | V | V | V |
| Message de statut (titre + corps) | V | V | V | V |
| Rôle (`RoleBadge`) | V | V | V | V |
| Recours | T : « contactez le support de Connecte+ » | T : « propriétaire ou support » | T : idem | T : idem |
| Liste « Ce qui n'est pas possible » | V | V | V | V |
| Quitter l'organisation (`org.leave`) | V | V | V | V |
| Agir sous ce profil | — | — | — | — |
| Modifier le profil, vérification, équipe, archiver, offres, messages, avis, statistiques | — | — | — | — |
| Voir le profil public | — | — | — | — |

Le propriétaire est le seul à lire un recours qui renvoie directement au support : c'est lui qui est responsable de l'organisation. Les autres rôles sont dirigés d'abord vers le propriétaire (aucune liste de membres n'existe, on ne le nomme pas).

### 6.3. Cas particuliers

- **Dernier propriétaire qui quitte** : le serveur applique `last_owner` (409) ; le message existant `errors.code.last_owner` s'affiche dans le dialogue. Sur une organisation archivée, l'ADR §19 autorise le dernier propriétaire à quitter (point à confirmer avec le backend, section 10.2).
- **Compte restreint en même temps** (sanction du compte) : `contexts/` répond 200, `unavailable` est rempli, « Quitter » reste actif (`org.leave` fait exception à la garde du compte, ADR §6.2). Les autres écrans du compte gardent leur propre refus `DENY_SECURITY`.
- **Organisation réactivée** : elle revient dans `results` au prochain rechargement. Elle **n'est jamais** réactivée comme profil actif automatiquement (E1 : un changement de profil est un geste explicite). Une notification « Organisation réactivée » existe déjà pour propriétaires et administrateurs.

---

## 7. Composants

### 7.1. À réutiliser (noms exacts)

`AccountShell`, `OrganizationPage` (adapté), `PageHeader`, `UserAvatar` (`shape="square"`), `RoleBadge`, `SellerTypeBadge` (compact), `Alert`, `AlertTitle`, `AlertDescription` (`ui/alert.tsx`), `AccessDenied`, `ErrorState`, `Skeleton`, `Badge` (`ui/badge.tsx`), `Button`, `AlertDialog` (via `LeaveOrganizationCard`), `ContextLostAlert`, `useActiveContext`, `useContextsQuery`, `invalidateContexts`, `useOnlineStatus`, `common.offlineAction`, `describeApiError`, `organizationDeniedKey`.

### 7.2. À créer

| Composant | Justification | Props |
|---|---|---|
| `components/organizations/OrganizationStatusBadge.tsx` | Aucun composant ne porte un statut d'organisation. `StatusBadge` est réservé à `sponsored` & co (règle 5, pas de mélange avec des statuts de compte). Un `Badge` avec icône (`PauseCircle` suspendue, `Archive` archivée) et **texte toujours présent**. | `status: "SUSPENDED" \| "ARCHIVED"`, `className?` |
| `components/organizations/OrganizationUnavailableView.tsx` | Assemble 4.2 ; utilisé par `OrganizationPage` uniquement. | `org: UnavailableOrganization` |
| `components/profiles/UnavailableOrganizationsSection.tsx` | Section 4.1. | aucune (lit `useActiveContext().unavailable`) |
| Hook `useUnavailableOrganizations()` (dans `contexts/ActiveContextContext.tsx`) | Expose `unavailable` depuis la même requête `contexts/` (zéro appel de plus). | — |

### 7.3. À modifier

- `LeaveOrganizationCard` accepte `{ id: Uuid }` au lieu de `OrganizationInternal` (il n'utilise que `org.id`) et une clé de corps `org.unavailable.leaveBody`.
- `fetchContexts` renvoie `{ results, unavailable }` (ou conserve `AvailableContext[]` et expose un second sélecteur de la même réponse via `select`) ; le tri de l'ordre serveur est conservé.
- `evaluateSelection` / `ContextLostAlert` : porter `lostId` et la clé de message (4.3).
- `ArchiveOrganizationCard` : après succès, `navigate('/organizations/:id')` au lieu du retour forcé avec alerte « archivé » destructive (P4). La spec E4 restait muette ; ce changement évite une alerte rouge sur une action volontaire.
- `StatusBadge` : inchangé.

**Aucune nouvelle dépendance.** `PauseCircle` et `Archive` sont dans `lucide-react`.

---

## 8. États, accessibilité, réseau faible

### 8.1. États de la vue 4.2

| État | Comportement |
|---|---|
| Chargement | `OrganizationPage` : tant que `contexts/` charge, `Skeleton` existant (`aria-busy="true"`). Pas de flash de « accès refusé ». |
| Vide | Sans objet. |
| Erreur | `contexts/` en échec : `ErrorState` + « Réessayer ». |
| Hors ligne | Cache affiché, « Quitter » désactivé (`aria-describedby` vers `common.offlineAction`), `OfflineBanner` global. Aucune file d'attente. |
| Succès | Après « Quitter » : toast `org.leaveDone` (existant) + navigation `/profiles`. |
| Permission refusée | Cas 2.5 (compte restreint, non-membre). |
| Envoi | Bouton désactivé + `Loader2` (patron existant de `LeaveOrganizationCard`). |

### 8.2. Accessibilité

- **Statut à l'écran.** Le message est un `Alert` avec `role="status"` (lecture polie, non interruptive) : l'utilisateur est arrivé volontairement sur la page. Pas de `role="alert"` ici. Pas d'`aria-live` sur le conteneur de page.
- **Alerte « profil perdu »** : inchangée (`role="alert"` via `Alert variant="destructive"`, focus donné à l'alerte, `tabIndex={-1}`). Le lien « Voir l'état de l'organisation » est atteignable au clavier juste après le texte, avant « J'ai compris ».
- **Le statut n'est jamais porté par la couleur seule** : icône + mot (« Suspendue », « Archivée »). Le `Badge` du titre a un `aria-label` = `org.status.aria` ; le `<h1>` ne contient que le nom (pas le statut) pour éviter la répétition.
- **Titre de page** : `document.title` = « {{name}} · Suspendue » (clé `org.status.*`).
- **Cartes de la liste 4.1** : `<article>` avec un seul lien principal (`aria-label` = `org.unavailable.seeAria`) ; `<section aria-labelledby>` pour la section.
- **Dialogue de départ** : focus initial sur « Annuler » (existant).
- Contrastes : `Alert` suspendue avec fond `bg-background`, bordure `border-warning/60`, icône `text-warning` (jeton `--warning` déjà défini dans `index.css`) ; texte en `text-foreground`. Archivée : bordure `border-border`, icône `text-muted-foreground`. Texte jamais en `text-warning` (contraste insuffisant pour du texte courant).
- Cibles tactiles ≥ 44 px ; zoom 200 % : pas de largeur fixe, noms tronqués avec `title`.

### 8.3. Réseau faible et mobile

- **Zéro requête supplémentaire** : `unavailable` voyage dans `contexts/` (mis en cache 5 min, déjà appelé). Quelques centaines d'octets ajoutés au plus.
- **Une relecture** de `contexts/` à l'ouverture de la vue 4.2 (en ligne seulement) pour ne pas afficher « suspendue » après une réactivation. Elle ne bloque pas l'affichage : la vue en cache s'affiche, puis se met à jour.
- Aucune image obligatoire (le logo passe par `UserAvatar`, initiales si absent, ≤ 40 px).
- Mobile (< 768 px) : pleine largeur, cartes empilées, bouton « Quitter l'organisation » pleine largeur, pas de barre fixe (pour ne pas être masqué par le clavier).
- Aucune action en file différée : quitter une organisation est une action sensible.

---

## 9. Décisions de design à valider

| # | Décision | Pourquoi | Alternative |
|---|---|---|---|
| S1 | **Un seul texte par statut**, sans motif, pour tous les motifs et tous les rôles. | Règle 10 : aucun détail de sanction ni donnée du personnel ; pour une organisation convertie la cause est la sanction d'une autre personne. | Afficher `reason` à `OWNER`/`ADMIN` (liste blanche `verification`/`other`) : voir Q-SUSP2. |
| S2 | Liste `unavailable` **dans** `contexts/`, pas d'endpoint séparé. | Une requête de moins sur 3G ; même cache et même invalidation ; ne casse pas la règle « absent de `results` = perdu ». | Nouvel endpoint `contexts/unavailable/` (+ 1 appel) ; ou inclure ces organisations dans `results` avec `status` (casserait la règle de perte de profil et le sélecteur). |
| S3 | Les organisations indisponibles **n'apparaissent pas** dans le sélecteur de profil. | On ne présente pas un choix impossible ; l'état se lit dans « Mes profils » et l'alerte. | Les montrer grisées dans le sélecteur (bruit sur mobile, risque d'erreur de tap). |
| S4 | Même vue pour `SUSPENDED` et `ARCHIVED`, textes différents. | Le serveur refuse tout dans les deux cas ; une seule structure à tester. | Deux vues (coût sans bénéfice). |
| S5 | Pas de lien ni de bouton « Contacter le support » : texte seul. | Aucun canal de support n'existe (aucune page, aucune adresse dans le front, aucune fonction de ticket). Ne rien inventer. | Voir Q-SUSP1. |
| S6 | Recours différencié : propriétaire → support ; autres rôles → propriétaire ou support. | L'équipe n'a pas de liste de membres (L0-09) et n'a pas à contacter la plateforme à la place du responsable. | Même texte pour tous (plus simple, moins précis). |
| S7 | Après archivage volontaire, la vue « Archivée » s'affiche (pas d'alerte destructive). | Action voulue par le propriétaire ; l'alerte rouge de « profil perdu » est faite pour une perte subie. | Garder l'alerte (cohérent mais anxiogène). |
| S8 | Lien de notification de statut → `/organizations/<id>`. | `/dashboard` en profil personnel est vide et ne dit rien. | Laisser `/dashboard`. |

---

## 10. Questions ouvertes

### 10.1. Pour le client (via l'utilisateur)

- **Q-SUSP1 (recours).** Quel moyen de contact du support citer (adresse e-mail, numéro WhatsApp, page) ? Tant que la réponse n'est pas connue, le texte reste « contactez le support de Connecte+ » sans lien. Proposition quand le client répond : un réglage de back-office (règle 11) exposé à l'interface, pour ne pas coder l'adresse en dur ; si absent, aucun lien n'est affiché.
- **Q-SUSP2 (motif).** Le client souhaite-t-il que le propriétaire et les administrateurs voient une catégorie de motif ? Recommandation : non en V1. Si oui, uniquement `verification` ou `other`, jamais `legal` ni `moderation`, jamais l'auteur ni un texte libre.
- **Q-SUSP3 (archivage).** Une organisation archivée peut-elle être restaurée par le support ? Aujourd'hui la réactivation par le personnel est refusée pour `ARCHIVED` (ADR §20, correction 2). Le texte du propriétaire dit « ne peut pas être annulé depuis l'application » ; à reprendre si le client prévoit une restauration.
- **Q-SUSP4 (notifier toute l'équipe).** Aujourd'hui seuls propriétaires et administrateurs sont notifiés (`notify_organization_status`, hors auteur de l'action). Faut-il notifier aussi éditeurs et analystes (texte inchangé, neutre) ? Recommandation : oui ; à défaut, ils l'apprennent par l'alerte « profil perdu » au prochain usage.
- **Q-SUSP5 (organisations converties suspendues).** Prévenir par SMS ou e-mail les propriétaires d'organisations créées `SUSPENDED` par la conversion (aucun événement n'est émis, donc aucune notification) ? Recommandation : message unique envoyé par le personnel au moment de la mise en production, hors périmètre de cette spec.

### 10.2. Pour le backend / l'architecte

- Confirmer que `contexts/` répond 200 à un compte restreint et que `unavailable` y est calculé (test dédié).
- Confirmer que `leave/` fonctionne pour un dernier propriétaire d'une organisation archivée (ADR §19 point 6) et pour une suspendue (`409 last_owner` sinon).
- Amendement de l'ADR 0006 §9.1 : ajout de `status` aux éléments et de la clé `unavailable`.

---

## 11. Conformité

- **Règle 3.** Aucun badge de vérification ni aucune mention de vérification dans la vue ; le motif « vérification » n'est pas exposé. Le mot « vérifié » n'apparaît dans aucun texte de cette spec.
- **Règle 4.** Aucun score, aucune note affichée.
- **Règle 5.** Aucun badge « Sponsorisé » ici ; `StatusBadge` n'est pas utilisé pour les statuts d'organisation (pas de mélange promotion/statut).
- **Règle 10.** Contrat sans motif, sans date, sans auteur, sans NIF, sans liste de membres ; textes sans détail de sanction ni de données du personnel ; pas de nom de membre.
- **Règle 12.** Aucune action sensible nouvelle côté interface ; « Quitter » reste journalisé par le service existant.
- **Règle 2.** Aucun lien avec un plan payant.

---

## 12. Critères d'acceptation

### 12.1. Backend (B-SUSP)

- [ ] `GET accounts/contexts/` renvoie `status` sur chaque élément de `results` (valeur `ACTIVE`) et la clé `unavailable` (tableau, `[]` par défaut).
- [ ] Un membre actif d'une organisation `SUSPENDED` la voit dans `unavailable` avec `status = "SUSPENDED"`, son `role` exact et `capabilities = ["org.leave"]`, et **pas** dans `results`. Idem pour `ARCHIVED`.
- [ ] Un membre révoqué ou parti ne la voit pas ; un non-membre non plus.
- [ ] Aucun champ `suspension_reason`, `reason`, date, auteur ou nom d'autre membre dans la réponse (test d'ensemble de clés exact).
- [ ] Un compte restreint (sanction bloquante) reçoit 200 avec `unavailable`.
- [ ] Une organisation convertie `SUSPENDED` (T9) apparaît dans `unavailable` avec `migrated_from_business = true`.
- [ ] Nombre de requêtes SQL de `contexts/` borné (une requête supplémentaire au plus, pas de N+1).
- [ ] `notify_organization_status` : `link = /organizations/<id>` (et, si Q-SUSP4 accepté, destinataires élargis) ; test mis à jour.
- [ ] Contrat OpenAPI et fixture `backend-identity.json` mis à jour.

### 12.2. Frontend (F-SUSP)

- [ ] `/profiles` : une organisation suspendue ou archivée apparaît dans « Organisations indisponibles » avec le badge texte et le rôle, sans bouton « Agir sous ce profil » ; la section est absente quand `unavailable` est vide.
- [ ] `/organizations/:id` (et `/edit`, `/verification`, `/team`) d'une organisation indisponible : vue 4.2, pas de `AccessDenied`, pas d'onglets, pas de « Voir le profil public », pas de carte « Archiver ».
- [ ] Les textes `SUSPENDED` / `ARCHIVED` et les recours propriétaire / autres rôles correspondent aux clés 5.1 (un test par rôle et par statut : 8 combinaisons).
- [ ] Aucun texte ne contient de motif, de nom d'autre membre ni le mot « vérifié ».
- [ ] 403 `DENY_SECURITY` avec id absent de `unavailable` : `AccessDenied` « Votre compte est limité… », jamais « Cette organisation est suspendue ».
- [ ] Profil actif devenu suspendu : `ContextLostAlert` avec `errors.lost.suspended` et lien « Voir l'état de l'organisation » vers `/organizations/:id` ; le focus est sur l'alerte.
- [ ] Après « Quitter » : toast, retour `/profiles`, l'organisation n'est plus listée.
- [ ] Hors ligne : vue affichée depuis le cache, « Quitter » désactivé avec la raison.
- [ ] Après archivage par le propriétaire : vue « Archivée » (pas d'alerte destructive).
- [ ] Tableau de bord vide en profil personnel avec `unavailable` non vide : phrase `emptyOffers.unavailableOrg` et lien.
- [ ] Clavier : tout atteignable, focus visible, focus initial « Annuler » dans le dialogue.
- [ ] Aucune requête de plus au chargement (vérifié par un test qui compte les appels réseau).
- [ ] `npm run lint && npm run test && npm run build` passent.

### 12.3. Tests attendus

| Test | Niveau |
|---|---|
| Parseur de `contexts/` : `unavailable` absent, vide, rempli ; `status` présent | Vitest (`api/`, contrat sur la fixture) |
| `lostMessageKey` : id dans `unavailable` (SUSPENDED, ARCHIVED), id absent (compte restreint) | Vitest (`lib/api-errors.test.ts`, `active-context.test.ts`) |
| `OrganizationUnavailableView` : 4 rôles × 2 statuts (texte de recours, boutons présents/absents) | Vitest + Testing Library |
| `OrganizationPage` : DENY_SECURITY avec/sans entrée dans `unavailable` ; DENY_RELATION inchangé | Vitest |
| `UnavailableOrganizationsSection` : rendu, absence de « Agir sous ce profil », section masquée si vide | Vitest |
| Quitter : succès, `last_owner`, hors ligne | Vitest (avec `ContextSwitcher.test.tsx` comme modèle) |
| `contexts/` : statuts, rôles, exclusion des anciens membres, absence de motif, compte restreint, borne SQL | Django (`identity/tests_contexts*.py`) |
| Notification de statut : lien | Django (`notifications`) |
| Recette manuelle : Android d'entrée de gamme, 3G simulée, lecteur d'écran (TalkBack) sur la vue 4.2 | QA |

---

## 13. Découpage en tâches

| ID | Agent | Contenu | Dépend de |
|---|---|---|---|
| **A-SUSP** | architecte-technique | Amender l'ADR 0006 §9.1 (`status`, `unavailable`) ; confirmer les points 10.2. | Validation de S1 à S3 |
| **B-SUSP** | dev-backend | `get_contexts_for_user` : `status` + liste `unavailable` ; sérialiseur sans champ sensible ; lien de notification ; tests 12.1 ; fixtures de contrat. | A-SUSP |
| **F-SUSP-1** | dev-frontend | Types, `fetchContexts`, `useUnavailableOrganizations`, fixtures et test de contrat ; `lostMessageKey` / `ContextLostAlert` (lien, textes 5.3). | contrat figé (section 3) ; peut démarrer sur fixture avant B-SUSP |
| **F-SUSP-2** | dev-frontend | `OrganizationStatusBadge`, `OrganizationUnavailableView`, adaptation d'`OrganizationPage`, `LeaveOrganizationCard`, `ArchiveOrganizationCard` (P4). | F-SUSP-1 |
| **F-SUSP-3** | dev-frontend | `UnavailableOrganizationsSection` dans `/profiles`, phrases d'états vides (4.4), clés i18n 5.1 à 5.3, correction des textes 5.4. | F-SUSP-1 |
| Relecture | relecteur-code | Chaque tâche. | |
| Audit | auditeur-securite | Contrat de `contexts/` (aucune fuite de motif, de membre, de date) et textes. | B-SUSP |
| Recette | qa-testeur | Critères 12.1 et 12.2, 8 combinaisons rôle × statut, compte restreint, réseau coupé. | tout |

B-SUSP et F-SUSP-1 peuvent démarrer **en parallèle** une fois la section 3 figée (le front travaille sur la fixture). Les tâches F-SUSP-2 et F-SUSP-3 sont indépendantes entre elles après F-SUSP-1.
