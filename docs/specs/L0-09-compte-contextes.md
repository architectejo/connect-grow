# L0-09 — Compte unique et contextes : analyse fonctionnelle

- **Date :** 10/10/2026
- **Auteur :** analyste-fonctionnel
- **Statut :** proposition, à valider par le chef de projet (CP) puis à planifier par l'architecte-technique (ADR 0006 attendu)
- **Réf. :** CDC v1.2 §3.1, §3.2, §3.3, §3.4, §3.15, §3.17, §4.2, §5.4, §11.1, §11.2, §11.4 ; règles verrouillées 1, 2, 3, 4, 10, 11, 12 ; dossier client : IAM-001 à IAM-008, ORG-001/002/003 (doc 01), UF-02 à UF-04 (doc 02), doc 06 (rôles et permissions, §2, §3, §6, §7, §19 à §22), doc 07 (§3 à §5), doc 09 §8, doc 10 (IAM-01 à IAM-08), doc 13 §4 à §6 et invariants.
- **Sources lues dans le code (lecture seule) :** `backend/apps/identity` (models, services, serializers, views, urls, admin), `backend/apps/marketplace` (models, services, views, serializers), `backend/apps/reviews`, `backend/apps/visibility`, `backend/apps/common/contexts.py`, `connect-grow/src` (branche `frontend`).

---

## 0. Résumé

Le compte reste unique (`User`). On supprime `User.user_type` (PARTICULIER / ENTREPRISE) et `BusinessProfile`. On les remplace par :

1. le **contexte personnel** (toujours présent) ;
2. le **contexte prestataire individuel** (`ProviderProfile`, activé depuis le compte, sans second identifiant) ;
3. le **contexte organisation** (`Organization` + `Membership` + rôle : propriétaire, administrateur, éditeur, analyste).

Le **contexte actif** est choisi par le client, **revérifié par le serveur à chaque requête** (appartenance, rôle, état), et toute action est attribuée à ce contexte.

État du code qui facilite le travail : la « couture » existe déjà (ADR 0004) : `apps/common/contexts.py` (constantes `USER`, `ORGANIZATION`), `identity.services.acts_for_context`, `Offer.seller_context_type/_id`, `Review.seller_context_type/_id`. Il manque le contexte `PROVIDER` et tout ce qui est derrière : `Offer.seller` est encore une clé étrangère vers `User` (ADR 0002 parlait seulement de `organization_id`, ce qui ne couvre pas les trois contextes : voir écart E7).

**Dix stories** (L0-09a à L0-09j), livrables séparément, avec un ordre imposé par les dépendances (§2). Les migrations `identity` sont à sérialiser (une seule branche touche `identity/models.py` à la fois, ADR 0002 étape 9).

---

## 1. Analyse de conformité

| Règle / source | Verdict | Remarque |
|---|---|---|
| Règle 1 (compte unique, plusieurs contextes) | Appliquée par cette tâche | `user_type` et `BusinessProfile` contredisent la règle ; ils disparaissent (L0-09h). L'inscription ne propose plus « Particulier / Entreprise » (CDC §3.1 : le contexte personnel s'active « À l'inscription »). |
| Règle 2 (permissions ≠ droits commerciaux) | À protéger | Le calcul de permission ne reçoit aucun paramètre de plan. Un plan ne crée jamais un `Membership`, un rôle ou une vérification (doc 13 INV-01). Les quotas (membres d'équipe, offres actives) viendront de L1-11 et ne produiront que `DENY_ENTITLEMENT`, jamais un changement de rôle. |
| Règle 3 (vérification jamais achetée, badge précis) | Écart du code actuel | `BusinessProfile.is_verified` est un booléen unique, exposé comme « Vérifié ». Le CDC §3.1 et doc 07 §3 exigent un libellé qui dit ce qui a été vérifié (« RCCM vérifié »). Traité en L0-09d. |
| Règle 4 (pas de score universel, notes par contexte) | Compatible | Les avis pointent déjà un contexte vendeur. Une personne qui vend à titre personnel, comme prestataire et comme membre d'une organisation a trois notes distinctes (CDC §3.4 « Séparation »). |
| Règle 10 (données par finalité) | À protéger | Pièces KYB et pièce du représentant en stockage privé (existant). Le téléphone d'un membre n'est jamais le contact de l'organisation par défaut (L0-09f). |
| Règle 11 (configurable) | Point d'attention | Les pièces exigées par type d'organisation (RCCM pour une entreprise, arrêté pour une ONG) sont une règle de marché : lues en base, pas codées en dur (L0-09d). La liste des 4 types d'organisation et des 4 rôles vient du CDC : elle peut rester en constantes de code (voir D4). |
| Règle 12 (AuditLog) | À appliquer | Liste des actions journalisées en §3.4. |
| Règle 6, 7, 8, 9 | Non concernées | Aucune. |
| Périmètre V1 | Conforme | Restaurants, écoles, livraison, formation (types d'organisation de doc 06/13) restent hors V1. Les types V1 sont les quatre du CDC §3.1. |
| ADR 0001 / CLAUDE.md §5 | Contraintes | UUID partout, aucune clé étrangère entre domaines sauf `User`, pas de contrainte d'unicité conditionnelle (garantie en couche service), accès aux autres domaines via `services.py`. |

---

## 2. Découpage en stories et dépendances

```
L0-09a  Organization / Membership / rôles / permissions
   |--- L0-09b  Contexte actif (résolution serveur + codes de refus)
   |       |--- L0-09c  Prestataire individuel (ProviderProfile)
   |       |--- L0-09d  Vérification des organisations (KYC -> organisation, badge précis)
   |       |--- L0-09e  Offres et statistiques rattachées au contexte vendeur
   |                |--- L0-09f  Contact, avis, notifications, messagerie rattachés au contexte vendeur
   |--- L0-09g  Inscription, /me/ et profils publics minimaux (retrait de user_type / business_profile côté API)
                 \
L0-09h  Migration des données + suppression de l'ancien modèle   (après c, d, e, f, g)
L0-09i  Front : sélecteur de contexte, inscription, organisation, adaptations  (contrat figé après b, g ; livraison après h)
L0-09j  Recette de non-régression et des scénarios IAM-01 à IAM-07 de doc 10
```

Principe « étendre puis contracter » : a à g ajoutent le nouveau modèle à côté de l'ancien (tests verts à chaque étape) ; seule L0-09h supprime `user_type`, `BusinessProfile`, `BusinessProfileCategory` et `Offer.seller`.

Limite avec les autres tâches (à confirmer, question Q-CP1) :

| Sujet | L0-09 | Laissé à |
|---|---|---|
| Créer une organisation, en devenir propriétaire | Oui (a, g) | — |
| Invitation, révocation, changement de rôle par API et écran | Règles et services oui (a) ; endpoints et écrans non | L1-01 |
| Revendication d'une organisation existante | Non | L1-01 (doc 06 §7 : « Claim organisation » ; CDC : aucun droit avant validation) |
| Dépôt des pièces et décision KYB | Rattachement à l'organisation et badge précis minimal (d) | L1-02 (parcours complet, autres types de preuve, expiration) |
| Page publique façon Facebook | Non (profil minimal compatible avec l'existant) | L1-03, L1-04 |
| Plans, quotas, limites de membres | Non | L1-11 |
| Boîte d'équipe et messagerie temps réel | Règle intérimaire (f) | L2-09 |

---

## 3. Règles de gestion transversales

### 3.1. Contextes (CDC §3.1 ; doc 01 IAM-003/004 ; doc 13 §4)

- **R1.** Un compte (`User`) a toujours un contexte personnel. Il ne se crée pas, ne se supprime pas.
- **R2.** Le contexte prestataire individuel est facultatif, unique par compte, activé par l'utilisateur. Il a son propre identifiant (UUID du `ProviderProfile`), distinct de l'identifiant du compte, pour que sa note vendeur ne se mélange pas avec celle du contexte personnel.
- **R3.** Un contexte organisation existe pour chaque `Membership` actif d'une organisation active. Un compte peut être membre de plusieurs organisations (doc 13 : relation N:N). Le plafond éventuel est une question ouverte (Q-CLI4).
- **R4.** Le contexte actif **ne confère aucune permission** (doc 13 ActingContext ; doc 10 IAM-03 : « pas d'autorité par simple sélection »). Il désigne seulement sous quelle identité l'action est tentée ; le serveur recalcule l'autorisation à chaque requête.
- **R5.** Un contexte invalide, inconnu ou non autorisé ne retombe **jamais** silencieusement sur le contexte personnel : il est refusé (sinon une offre d'organisation serait publiée à titre personnel).
- **R6.** Chaque objet créé porte le contexte qui agit (`*_context_type`, `*_context_id`) et l'auteur réel (`created_by`, FK vers `User`). L'organisation propriétaire d'un objet garde l'objet quand l'auteur la quitte (doc 06 §19 : « objets/historique restent à l'organisation »).
- **R7.** Le contexte actif est toujours affiché dans l'interface (CDC §3.1).

### 3.2. Rôles d'organisation (CDC §3.1 : propriétaire, administrateur, éditeur, analyste)

Matrice **proposée** pour validation (la source donne les noms des rôles, pas leurs droits ; elle s'appuie sur doc 06 §5, §6, §7). Légende : O = oui, N = non.

| Capacité (code) | Propriétaire | Administrateur | Éditeur | Analyste |
|---|---|---|---|---|
| `org.view_internal` (voir l'espace interne) | O | O | O | O |
| `org.edit_profile` (nom, description, logo, coordonnées publiques) | O | O | N (voir Q-CP3) | N |
| `org.manage_members` (inviter, révoquer) | O | O (sauf propriétaires) | N | N |
| `org.manage_roles` (attribuer un rôle) | O | O (rôles Administrateur, Éditeur, Analyste ; jamais Propriétaire) | N | N |
| `org.transfer_ownership`, `org.archive` | O | N | N | N |
| `org.verification_submit` (déposer des pièces KYB) | O | O | N | N |
| `offer.publish` / `offer.edit` / `offer.delete` | O | O | O | N |
| `review.reply` (répondre aux avis) | O | O | O | N |
| `contact.view_requesters` (liste « Qui a demandé », données personnelles du demandeur) | O | O | O | N |
| `contact.manage_channels` (numéro et canaux de contact de l'organisation) | O | O | N | N |
| `stats.view` (graphiques et compteurs) | O | O | O | O |
| `billing.view` / `billing.manage` (plans, lot 1 L1-11) | O / O | O / N | N | N |

Règles associées :

- **R8.** Une organisation a au moins un propriétaire actif en permanence. Rétrograder, révoquer ou voir partir le dernier propriétaire est refusé (`LAST_OWNER`).
- **R9.** Un administrateur ne peut ni attribuer, ni retirer, ni modifier le rôle de propriétaire, ni agir sur un propriétaire (doc 06 §7 : « ne peut déléguer au-delà de son autorité »).
- **R10.** Un propriétaire ou un administrateur ne s'attribue pas un rôle supérieur à lui-même.
- **R11.** Le départ ou la révocation d'un membre met son `Membership` à `REVOKED` : ses permissions cessent **immédiatement** (doc 06 §19, AC-07 ; doc 10 IAM-06). Le compte personnel, ses offres personnelles, ses avis restent intacts (CDC §3.1).
- **R12.** Une relation `(organisation, utilisateur)` existe au plus une fois. Un retour d'un ancien membre réactive la même ligne (unicité inconditionnelle, portable MySQL).
- **R13.** Le rôle donne des permissions ; il ne donne **pas** de vérification, de badge ni de classement (règles 2, 3).
- **R14.** Une organisation suspendue (`SUSPENDED`) n'est plus utilisable comme contexte (`DENY_SECURITY`) ; ses offres ne sont plus publiques ; ses données sont conservées (doc 06 AC-15, §21 « Suspension compte/org »).

### 3.3. Données par finalité (règle 10 ; doc 06 §17 ; doc 07 §5)

| Donnée | Public | Membres autorisés | Personnel de vérification | Remarque |
|---|---|---|---|---|
| Nom, type, description, logo, ville et commune, catégories, badges précis, ancienneté | Oui | Oui | Oui | |
| Adresse exacte de l'organisation, position GPS précise | Jamais | Selon rôle `org.edit_profile` | Si dossier | Le public voit « adresse générale » (CDC §3.2) |
| Téléphone / e-mail de l'organisation | Jamais directement (révélation par canal consenti, ADR 0005) | `contact.manage_channels` | Non | Voir L0-09f |
| Téléphone / e-mail d'un membre | Jamais | Non (sauf lui-même) | Non | Jamais exposé via l'organisation |
| Pièces KYB (RCCM, arrêté, identification nationale), pièce du représentant | Jamais | Dépôt et statut, pas de relecture du fichier | Rôles `review_kycdocument` uniquement | Stockage privé existant. Durée de conservation : question ouverte Q-CLI6 (LEG-PRV) |
| Liste des membres et rôles | Non | `org.view_internal` | Non | Le public ne voit pas qui administre (à confirmer par le designer-ux pour ORG-001) |

### 3.4. Actions journalisées (règle 12 ; doc 06 §21 ; AC-14)

`AuditLog.record(...)` synchrone, dans la même transaction que l'action (même exception que pour `decide_kyc_document`, ADR 0002 notes R1). Les champs `details` ne contiennent aucune donnée personnelle : identifiants UUID, codes de rôle, motifs normalisés.

| Action (code) | Cible (`target_type`) | Contenu minimal |
|---|---|---|
| `ORG_CREATED` | `organization` | acteur, type d'organisation |
| `ORG_UPDATED` (champs d'identité : nom, type) | `organization` | acteur, champs modifiés (noms de champs, pas les valeurs) |
| `ORG_SUSPENDED` / `ORG_REACTIVATED` | `organization` | acteur (personnel), motif normalisé |
| `ORG_OWNERSHIP_TRANSFERRED` | `organization` | ancien et nouveau propriétaire (UUID), acteur |
| `MEMBERSHIP_ADDED` / `MEMBERSHIP_ROLE_CHANGED` / `MEMBERSHIP_REVOKED` | `membership` | acteur, cible (UUID), rôle avant/après, organisation (doc 06 AC-14 : acteur, cible, scope, horodatage) |
| `PROVIDER_ACTIVATED` / `PROVIDER_ARCHIVED` | `providerprofile` | acteur |
| `KYC_VALIDE` / `KYC_REFUSE` / `KYC_REVOKED` (existants) | `kycdocument` | inchangé |
| `CONTACT_CHANNEL_CHANGED` d'un contexte organisation | `organization` | acteur, canal, activé ou retiré |

La simple bascule de contexte n'est pas journalisée (non sensible, volume), mais toute action sensible exécutée sous un contexte organisation enregistre l'identifiant de l'organisation dans l'audit.

### 3.5. Codes de refus (doc 06 §20)

Les refus d'autorisation exposent un code stable dans le corps de la réponse, sans révéler d'information sensible :

| Code | Cas dans cette tâche |
|---|---|
| `DENY_AUTH` | jeton absent ou invalide |
| `DENY_CONTEXT` | contexte demandé inexistant, mal formé, ou incompatible avec l'action |
| `DENY_RELATION` | pas de `Membership` actif |
| `DENY_PERMISSION` | rôle sans la capacité |
| `DENY_SECURITY` | organisation ou compte suspendu |
| `DENY_OBJECT_STATE` | prestataire archivé, offre supprimée, etc. |

`DENY_ENTITLEMENT`, `DENY_ELIGIBILITY`, `DENY_MARKET_RULE` ne sont pas produits par L0-09 (L1-11 et suivantes).

---

## 4. User stories

### L0-09a — Organisation, appartenance et rôles (modèle et services)

En tant que **personnel** (utilisateur connecté), je veux créer une organisation dont je deviens le propriétaire et y avoir un rôle précis, afin d'agir au nom d'une entreprise, d'une boutique, d'une ONG ou d'une structure d'événements sans second compte.

Réf. : CDC §3.1 (Organisations, Rôles), §11.1 (identity : Organization, Membership, Role) ; dossier client IAM-005, IAM-006, IAM-007, UF-04, doc 06 §6/§7/§19, doc 13 §5 ; lot 0 (prépare L1-01).
Dépend de : aucune. Bloque : toutes les autres.

Critères d'acceptation (testables) :
- [ ] Étant donné un utilisateur actif connecté, quand il crée une organisation de type `ENTREPRISE`, `BOUTIQUE`, `ONG` ou `ORGANISATEUR_EVENEMENTS` avec un nom de 2 à 255 caractères, alors une `Organization` (UUID, statut `ACTIVE`) et un `Membership` `OWNER` `ACTIVE` pour ce utilisateur sont créés dans une seule transaction ; si la création du `Membership` échoue, aucune organisation n'existe.
- [ ] Étant donné un type hors des quatre valeurs ou un nom vide ou d'un seul caractère, alors la création est refusée (400) et rien n'est écrit.
- [ ] Étant donné la création réussie, alors une entrée `AuditLog` `ORG_CREATED` existe avec l'acteur et l'organisation ; ses `details` ne contiennent ni nom ni téléphone ni e-mail.
- [ ] Étant donné la matrice du §3.2, alors un test paramétré (rôle x capacité) vérifie chaque case ; une capacité non accordée renvoie `DENY_PERMISSION`.
- [ ] Étant donné un utilisateur sans `Membership` actif, quand il demande une capacité interne de l'organisation, alors il reçoit `DENY_RELATION`, quel que soit son plan ou son statut `is_staff`.
- [ ] Étant donné une organisation avec un seul propriétaire actif, quand on tente de le rétrograder, de le révoquer ou qu'il quitte l'organisation, alors l'opération est refusée avec le code `LAST_OWNER` et l'état est inchangé.
- [ ] Étant donné un administrateur, quand il tente d'attribuer ou de retirer le rôle `OWNER`, ou de modifier un propriétaire, alors `DENY_PERMISSION`.
- [ ] Étant donné un membre révoqué (`REVOKED`), quand il tente l'une des capacités qu'il avait un instant avant, alors la requête suivante est refusée (`DENY_RELATION`) sans délai de cache ; son compte personnel se connecte toujours et ses offres personnelles restent actives.
- [ ] Étant donné un ancien membre réinvité, alors la même ligne `Membership` repasse à `ACTIVE` (aucune seconde ligne pour le couple organisation-utilisateur).
- [ ] Étant donné une organisation `SUSPENDED`, alors toute capacité de ses membres sous ce contexte renvoie `DENY_SECURITY`.
- [ ] Étant donné la liste des signatures de `identity.services`, alors aucune fonction de calcul de permission ne reçoit de plan, de prix ou d'entitlement en paramètre (test d'absence ; garde-fou règle 2).
- [ ] Étant donné le module, alors `DomainBoundariesTests` reste vert : aucune clé étrangère vers un autre domaine ; les catégories de l'organisation passent par une table de liaison interne `category_id` (UUID) validée via `catalog.services`.
- [ ] Étant donné chaque changement de rôle ou de statut de `Membership`, alors l'événement `MembershipChanged` est publié dans l'outbox (consommateurs futurs : messagerie, notifications) et l'`AuditLog` correspondant du §3.4 est écrit.

Règles métier : R8 à R14 ; matrice §3.2 (à valider) ; types d'organisation limités aux quatre du CDC §3.1.
Hors périmètre : endpoints et écrans d'invitation et de gestion des membres (L1-01) ; revendication (L1-01) ; branches et départements ; plafonds de membres liés au plan (L1-11) ; rôles supplémentaires de doc 06 (recruteur, gestionnaire de facturation, etc.).
Questions ouvertes : Q-CP1, Q-CP3, Q-CP5, Q-CLI1, Q-CLI2, Q-CLI4, Q-CLI5.

---

### L0-09b — Contexte actif : liste, sélection et contrôle serveur

En tant que **personnel**, prestataire ou membre d'organisation, je veux choisir sous quel contexte j'agis et voir ce contexte en permanence, afin que chaque action soit attribuée à la bonne identité.

Réf. : CDC §3.1 (Contextes, « Le contexte actif est toujours affiché »), §4.2 (permissions vérifiées côté serveur) ; dossier client IAM-003, UF-02, UF-05, doc 06 §1 et §24, doc 10 IAM-02/03/05/06, doc 13 ActingContext ; lot 0.
Dépend de : L0-09a.

Critères d'acceptation (testables) :
- [ ] Étant donné un utilisateur connecté, quand il appelle la liste de ses contextes, alors la réponse contient le contexte personnel (toujours, en premier), le contexte prestataire s'il est actif, et un élément par `Membership` `ACTIVE` d'une organisation `ACTIVE` ; chaque élément porte `type`, `id`, `name`, et `role` pour une organisation.
- [ ] Étant donné un `Membership` révoqué, une organisation suspendue ou un prestataire archivé, alors ce contexte n'apparaît pas dans la liste.
- [ ] Étant donné une requête sans indication de contexte, alors le contexte personnel est utilisé.
- [ ] Étant donné une requête avec un contexte (mécanisme figé par l'architecte, voir D3) qui désigne une organisation dont l'utilisateur n'est pas membre actif, alors la réponse est 403 `DENY_RELATION` et **aucun** repli sur le contexte personnel n'a lieu (aucune écriture).
- [ ] Étant donné un contexte mal formé ou inexistant, alors 403 `DENY_CONTEXT`.
- [ ] Étant donné un utilisateur du personnel (`is_staff`) qui n'est pas membre, quand il désigne une organisation comme contexte, alors le refus est le même (`DENY_RELATION`) : le personnel n'agit pas « dans » un contexte client.
- [ ] Étant donné deux requêtes simultanées de deux onglets avec des contextes différents, alors chacune est traitée sous son propre contexte (aucun état de contexte partagé côté serveur entre requêtes).
- [ ] Étant donné la révocation d'un membre pendant sa session, quand il envoie la requête suivante sous le contexte de cette organisation, alors elle est refusée ; son jeton d'accès reste valide pour le contexte personnel.
- [ ] Étant donné la résolution du contexte, alors elle ajoute au plus 2 requêtes SQL par requête authentifiée (`assertNumQueries`).
- [ ] Étant donné une action sensible exécutée sous un contexte organisation, alors l'`AuditLog` contient l'UUID de l'organisation et l'UUID de l'utilisateur acteur.
- [ ] Étant donné une réponse 403 d'autorisation, alors le corps contient `code` (parmi §3.5) et un message en français, sans nom d'organisation ni information sur d'autres membres.

Règles métier : R4, R5, R6, R7 ; codes §3.5.
Hors périmètre : mémorisation du dernier contexte choisi (peut être purement locale côté front) ; délégation d'une action à un tiers (IAM-008, post-V1) ; contexte de branche.
Questions ouvertes : D3 (mécanisme de transport du contexte), Q-CP4.

---

### L0-09c — Activer le profil de prestataire individuel

En tant que **personnel**, je veux activer un profil de prestataire depuis mon compte, sans nouveau mot de passe ni numéro, afin de proposer mes services sous mon nom sans me présenter comme une entreprise.

Réf. : CDC §3.1 (contexte Prestataire individuel), §3.2 (dernier paragraphe : profil sans se présenter comme une entreprise) ; dossier client IAM-004, UF-03, ORG-002, doc 13 §6 (ProviderProfile), doc 07 §5 ; lot 0 (le profil public complet est L1-04).
Dépend de : L0-09b.

Critères d'acceptation (testables) :
- [ ] Étant donné un utilisateur actif, quand il active le profil prestataire, alors un `ProviderProfile` (UUID propre, statut `ACTIVE`) est créé et aucun `User` supplémentaire n'est créé.
- [ ] Étant donné un profil déjà actif, quand il tente de l'activer à nouveau, alors la demande est idempotente (même profil, pas de doublon ; 200 ou 409 selon le contrat figé).
- [ ] Étant donné la création, alors une entrée `AuditLog` `PROVIDER_ACTIVATED` existe.
- [ ] Étant donné un profil actif, alors le contexte `PROVIDER` apparaît dans la liste de L0-09b, avec un identifiant différent de celui du compte.
- [ ] Étant donné une charge publique du profil prestataire, alors elle ne contient ni adresse exacte, ni téléphone, ni e-mail, ni pièce d'identité (test d'exhaustivité des clés).
- [ ] Étant donné un compte suspendu ou banni (sanction active), alors l'activation est refusée (`DENY_SECURITY`).
- [ ] Étant donné un plan gratuit, alors l'activation reste possible (aucun plan requis, règle 2).
- [ ] Étant donné l'archivage du profil, alors ses offres ne sont plus publiques, les données sont conservées et `PROVIDER_ARCHIVED` est journalisé ; les avis déjà reçus restent rattachés à l'identifiant du profil.
- [ ] Étant donné un autre utilisateur, alors il ne peut ni lire la partie privée ni modifier ni utiliser le contexte `PROVIDER` d'autrui (`DENY_CONTEXT`).

Règles métier : R2 ; un seul profil prestataire par compte (service + unicité inconditionnelle sur le compte) ; le profil prestataire n'est pas une organisation (pas de membres, pas de rôles).
Hors périmètre : éligibilité par catégorie sensible, références, vérification d'identité obligatoire avant publication (TRU-002, doc 07 §6) ; page publique complète (L1-04) ; plan « Professionnel » (L1-11).
Questions ouvertes : Q-CLI3, Q-CLI7.

---

### L0-09d — Vérification des organisations : pièces KYB et badge précis

En tant que **propriétaire ou administrateur d'une organisation**, je veux déposer les pièces de mon organisation et en voir le statut ; en tant que **visiteur**, je veux lire exactement ce qui a été vérifié, afin de ne pas confondre badge et garantie.

Réf. : CDC §3.1 (Organisations : vérification KYB, badge précis, « ne s'achète jamais »), §3.17 (file KYC/KYB) ; règle 3 ; dossier client TRU-003, doc 07 §3 à §5, doc 09 §8 ; lot 0 (adapte l'existant ; le parcours complet reste L1-02).
Dépend de : L0-09a, L0-09b.

Critères d'acceptation (testables) :
- [ ] Étant donné une organisation, quand un propriétaire ou un administrateur dépose un fichier valide (types et taille contrôlés comme aujourd'hui), alors la pièce est rattachée à l'organisation (`organization`), stockée hors `MEDIA_ROOT`, statut `EN_ATTENTE`.
- [ ] Étant donné un éditeur ou un analyste, quand il dépose ou supprime une pièce, alors `DENY_PERMISSION`.
- [ ] Étant donné un utilisateur non membre, quand il liste ou télécharge les pièces d'une organisation, alors il est refusé ; le téléchargement du fichier reste réservé aux détenteurs de `review_kycdocument` (comportement existant conservé).
- [ ] Étant donné les types de pièces exigés par type d'organisation, alors ils sont lus en base (configurables au back-office), avec pour valeur initiale celle qui sera validée par le client (voir E5, Q-CLI2) ; aucune liste de pièces n'est codée en dur dans la décision de vérification.
- [ ] Étant donné une pièce validée, alors l'API publique de l'organisation expose une liste `verified_claims` dont chaque élément porte un code et un libellé précis (exemple : « RCCM vérifié », « Identification nationale vérifiée », « Représentant vérifié ») et la date de vérification.
- [ ] Étant donné que toutes les pièces exigées sont validées, alors un libellé de synthèse « Organisation vérifiée » peut s'afficher, **toujours accompagné** de la liste de ses composantes ; il ne s'affiche jamais seul sans moyen de voir ce qui a été vérifié.
- [ ] Étant donné la réponse publique, alors elle ne contient plus de booléen `is_verified` nu (le filtre `?is_verified=` de la liste des entreprises est remplacé par un filtre sur la synthèse, ou sur un claim précis).
- [ ] Étant donné la décision (validation, refus, révocation d'une pièce), alors elle n'est possible que par le point d'entrée du personnel de vérification, dans la même transaction que son `AuditLog` (`KYC_*`), et le recalcul des claims suit (test : aucune autre écriture de claims dans le code).
- [ ] Étant donné un décideur qui est membre (actif ou ancien membre depuis moins de la durée définie en Q-CP6) de l'organisation concernée, alors la décision est refusée (extension de la règle existante « pas de décision sur sa propre pièce »).
- [ ] Étant donné l'achat ou l'expiration d'un plan, la modification d'un rôle ou l'ajout d'un membre, alors les claims de l'organisation sont inchangés (test de non-influence).
- [ ] Étant donné le départ d'un membre qui avait déposé une pièce, alors la pièce et sa validation restent à l'organisation.

Règles métier : R13 ; doc 07 §1 (« La vérification ne peut jamais être achetée ») ; un badge ne dit ni « sûre », ni « solvable », ni « recommandée » (libellés doc 07 §3, à fournir par le designer-ux/le contenu).
Hors périmètre : preuve d'autorité distincte (« Autorité vérifiée », doc 07 §3) ; expiration et renouvellement de preuves ; vérification d'identité du prestataire individuel ; revendication ; nouveaux types de pièces.
Questions ouvertes : Q-CLI2, Q-CLI6, Q-CP6, E5.

---

### L0-09e — Offres et statistiques rattachées au contexte vendeur

En tant que **membre d'une organisation, prestataire ou personnel**, je veux publier et gérer des offres sous le contexte actif, afin que l'offre affiche le bon type de vendeur et reste à l'organisation si son auteur part.

Réf. : CDC §3.3 (« Le type de vendeur est toujours visible sur l'offre »), §3.1 (contextes), §3.6 ; dossier client MKT-001, IAM-003, doc 06 §8 ; ADR 0002 ligne `marketplace.Offer`, ADR 0004 (couture `seller_context_*`) ; lot 0.
Dépend de : L0-09b, L0-09c (pour `PROVIDER`).

Critères d'acceptation (testables) :
- [ ] Étant donné un modèle `Offer` portant `seller_context_type`, `seller_context_id` et `created_by` (FK `User`), quand une offre est créée sous un contexte, alors ces trois champs sont renseignés à partir du contexte résolu en L0-09b et non d'un champ envoyé par le client.
- [ ] Étant donné un client qui envoie dans le corps un autre contexte vendeur que le contexte résolu, alors la valeur est ignorée ou rejetée (400), jamais appliquée.
- [ ] Étant donné le contexte organisation, quand un propriétaire, un administrateur ou un éditeur publie, modifie, met en pause, renouvelle ou supprime (corbeille) une offre de l'organisation, alors c'est autorisé, y compris si l'auteur est un autre membre ; un analyste reçoit `DENY_PERMISSION`.
- [ ] Étant donné un membre révoqué qui était l'auteur d'une offre de l'organisation, quand il tente de la modifier, alors `DENY_RELATION`.
- [ ] Étant donné le contexte prestataire, alors la publication exige un `ProviderProfile` actif (sinon `DENY_CONTEXT`) ; en contexte personnel, elle reste possible dans les limites de la question Q-CLI3.
- [ ] Étant donné la liste « Mes offres » et la corbeille, alors elles ne montrent que les offres du contexte actif (le même utilisateur voit des listes différentes selon le contexte).
- [ ] Étant donné la fiche publique d'une offre, alors le vendeur est exposé sous la forme `seller = {context_type, context_id, display_name, logo/photo, verified_claims, member_since}` ; `context_type` prend les valeurs `USER`, `PROVIDER`, `ORGANIZATION` et l'interface l'affiche (particulier, prestataire, organisation) ; aucun e-mail ni téléphone n'y figure.
- [ ] Étant donné le filtre `?seller=<uuid>`, alors il désigne un identifiant de contexte vendeur (et non un identifiant de compte) ; un identifiant inconnu renvoie une liste vide.
- [ ] Étant donné une organisation ou un prestataire suspendu ou archivé, ou un compte inactif pour le contexte `USER`, alors ses offres ne sont plus listées publiquement (remplace la condition actuelle `seller__is_active`).
- [ ] Étant donné les compteurs de visibilité (vues, contacts, partages) et les endpoints de statistiques, alors ils sont agrégés par contexte vendeur ; les membres ayant `stats.view` (dont l'analyste) les lisent, un non-membre reçoit `DENY_RELATION`.
- [ ] Étant donné `count_active_offers`, alors il compte par contexte vendeur (préparation des quotas de L1-11, sans aucun plafond codé).
- [ ] Étant donné les vérifications de modération qui supposent « l'offre appartient au sanctionné » (masquage d'offre), alors elles s'appliquent au contexte vendeur de l'offre via le service `marketplace` (test avec offre d'organisation).

Règles métier : R6 ; le plan ne modifie ni le type de vendeur affiché, ni la visibilité organique (règle 5 : la promotion est un autre mécanisme).
Hors périmètre : champs « Sur devis », partage social (L1-05) ; quotas par plan (L1-11) ; promotion (L1-13).
Questions ouvertes : Q-CLI3, Q-CP2, Q-CP7.

---

### L0-09f — Contact, avis, notifications et messagerie rattachés au contexte vendeur

En tant que **acheteur**, je veux contacter une organisation ou un prestataire et noter son offre et son vendeur ; en tant que **membre autorisé**, je veux répondre au nom de l'organisation, afin que l'interlocuteur et la note soient l'organisation et non une personne.

Réf. : CDC §3.4 (note vendeur par contexte, séparation), §3.15, §3.1 ; règles 4 et 10 ; ADR 0004 (D7, contexte vendeur), ADR 0005 (consentement) ; dossier client MSG-001/003, doc 06 §14 ; lot 0.
Dépend de : L0-09e. **Taille :** élevée ; l'architecte peut scinder en f1 (avis et notifications) et f2 (contact et messagerie).

Critères d'acceptation (testables) :
- [ ] Étant donné une offre d'organisation, quand un visiteur connecté demande les canaux disponibles, alors ils sont déduits des consentements **du contexte organisation** (propres à l'organisation), jamais de ceux de l'auteur de l'offre.
- [ ] Étant donné une organisation sans numéro de contact propre vérifié, alors seul le canal message est proposé (par défaut protecteur, règle 10) ; le téléphone personnel d'un membre n'est jamais révélé au titre d'une offre d'organisation.
- [ ] Étant donné la modification du numéro personnel d'un membre, alors les canaux de l'organisation ne changent pas.
- [ ] Étant donné la gestion du numéro et des canaux de l'organisation, alors seuls propriétaires et administrateurs (`contact.manage_channels`) peuvent la modifier ; l'opération est journalisée (`CONTACT_CHANNEL_CHANGED`).
- [ ] Étant donné la liste « Qui a demandé » d'un contexte organisation, alors elle est lisible par propriétaire, administrateur et éditeur, et l'analyste ne voit que des compteurs (pas les données personnelles des demandeurs).
- [ ] Étant donné un acheteur qui est lui-même membre actif de l'organisation vendeuse, quand il contacte ou note une offre de cette organisation, alors c'est refusé (extension de « contact de sa propre offre refusé »).
- [ ] Étant donné un avis sur une offre d'organisation, alors `seller_context_type = ORGANIZATION` et `seller_context_id` = UUID de l'organisation ; l'avis n'est pas compté dans la note du contexte personnel des membres.
- [ ] Étant donné `identity.acts_for_context`, alors il renvoie vrai pour : le contexte `USER` du compte lui-même ; le contexte `PROVIDER` du propriétaire du profil ; le contexte `ORGANIZATION` des membres actifs ; faux dans tous les autres cas (dont membre révoqué, organisation suspendue).
- [ ] Étant donné une réponse publique à un avis d'organisation, alors seuls propriétaire, administrateur et éditeur peuvent répondre (`review.reply`) ; la réponse affiche l'organisation et non le nom du membre.
- [ ] Étant donné la notification d'un nouvel avis ou d'un nouveau contact d'organisation, alors elle est envoyée aux membres actifs ayant la capacité correspondante (via un service `identity` de résolution des destinataires) ; un membre révoqué n'en reçoit plus.
- [ ] Étant donné une conversation issue d'une offre d'organisation, alors tout membre actif ayant le droit de répondre y accède ; après révocation, il ne peut plus la lire, et l'historique reste à l'organisation (doc 06 §14, AC-12).
- [ ] Étant donné la détection d'avis réciproques répétés (CDC §3.4), alors son comportement est inchangé pour les contextes `USER` et documenté pour les autres contextes (voir E9) ; aucune régression sur les tests existants.

Règles métier : R4, R6, R11 ; note par contexte, jamais agrégée entre contextes ni dans le classement organique (règle 4).
Hors périmètre : boîte d'équipe, attribution d'une conversation à un membre, indicateurs de frappe (L2-09) ; contact initié « au nom d'une organisation » comme acheteur (voir Q-CP8) ; texte juridique de consentement propre aux organisations (Q-CLI5).
Questions ouvertes : Q-CP8, Q-CLI5, E9.

---

### L0-09g — Inscription au compte unique, `/me/` et profils publics minimaux

En tant que **visiteur**, je veux créer un seul compte personnel puis choisir plus tard de devenir prestataire ou de créer une organisation, afin de ne pas devoir choisir un « type de compte » dès l'inscription.

Réf. : CDC §3.1 (Inscription ; contexte personnel « À l'inscription »), §3.2 ; dossier client IAM-001, UF-02, doc 10 IAM-01 à IAM-03 ; lot 0.
Dépend de : L0-09a, L0-09b (et L0-09c, L0-09d pour les profils publics).

Critères d'acceptation (testables) :
- [ ] Étant donné l'inscription, quand le corps contient un e-mail ou un téléphone (+ OTP), un mot de passe et un nom, alors un `User` est créé sans type de compte, sans profil entreprise, sans organisation.
- [ ] Étant donné un corps contenant les champs retirés `user_type` ou `business_profile`, alors ils n'ont aucun effet (aucune organisation créée) ; un test le vérifie.
- [ ] Étant donné la lecture de `me/`, alors la charge ne contient plus `user_type` ni `business_profile` ; elle contient les informations du compte et la liste des contextes (ou le lien vers elle, selon le contrat figé).
- [ ] Étant donné la mise à jour de `me/`, alors les anciens champs `business_profile.*` ne sont plus acceptés ; les champs de l'organisation se modifient par l'endpoint de l'organisation (rôles `org.edit_profile`).
- [ ] Étant donné un propriétaire ou un administrateur, quand il modifie le nom, la description, le logo, les catégories de l'organisation, alors les mêmes validations qu'aujourd'hui s'appliquent (logo ré-encodé sans métadonnées, taille plafonnée, existence des catégories vérifiée via `catalog`).
- [ ] Étant donné la liste publique des organisations (remplaçante de la liste des entreprises), alors elle est publique, paginée, filtrable par recherche texte et par claim de vérification, triée par nom puis identifiant, et n'expose que les champs publics du §3.3.
- [ ] Étant donné le profil public minimal d'un vendeur (organisation, prestataire ou personnel), alors il affiche nom public, photo ou logo, type de vendeur, claims précis, ancienneté (« Sur Connecte+ depuis <mois année> », source : date de création de l'organisation ou du profil prestataire, ou d'inscription du compte pour `USER`), note vendeur ; le nom d'un compte personnel suit `public_display_name` (« Marie K. »).
- [ ] Étant donné la charge publique de n'importe quel profil, alors un test d'exhaustivité des clés vérifie l'absence de téléphone, e-mail, adresse exacte, pièce d'identité, liste des membres.

Règles métier : §3.3 (données par finalité).
Hors périmètre : page façon Facebook, onglets, couverture, abonnés (L1-03) ; invitation et revendication (L1-01) ; vérification d'e-mail (dette connue ADR 0002).
Questions ouvertes : Q-CP2, Q-CLI8.

---

### L0-09h — Migration des données et suppression de l'ancien modèle

En tant que **équipe de développement**, je veux migrer les données de développement existantes et supprimer `user_type`, `BusinessProfile` et `Offer.seller`, afin qu'il ne reste qu'un seul modèle de contextes.

Réf. : CDC §11.4 (écart « Types de compte Particulier / Business » -> L0-09), ADR 0002 (migration `0002` ordinaire, aucune donnée de production) ; règle 1 ; lot 0.
Dépend de : L0-09c, L0-09d, L0-09e, L0-09f, L0-09g.

Critères d'acceptation (testables) :
- [ ] Étant donné une base de développement contenant des comptes `ENTREPRISE` avec `BusinessProfile`, offres, pièces KYC, avis, compteurs de visibilité, contacts et conversations, quand la migration s'exécute, alors, pour chaque `BusinessProfile`, une `Organization` (type et règle de correspondance : D2) est créée avec un `Membership` `OWNER` pour l'ancien titulaire ; nom, bio, logo, catégories et NIF sont repris ; les pièces KYC sont rattachées à l'organisation avec leur statut et leur historique ; les claims se recalculent à l'identique de l'ancien `is_verified`.
- [ ] Étant donné les offres d'un compte migré, alors `seller_context_type = ORGANIZATION` et `seller_context_id` = UUID de l'organisation, `created_by` = l'ancien vendeur ; les offres des comptes `PARTICULIER` passent en `USER`.
- [ ] Étant donné les avis, compteurs de visibilité, contacts et notifications référant un vendeur migré, alors leur contexte vendeur est mis à jour de façon cohérente (les notes d'un ancien compte entreprise sont désormais celles de l'organisation).
- [ ] Étant donné un compte `PARTICULIER` migré, alors il n'obtient ni organisation ni profil prestataire.
- [ ] Étant donné la migration exécutée deux fois sur le même jeu (ou reprise après échec), alors aucun doublon d'organisation ou de membre n'est créé (idempotence).
- [ ] Étant donné la fin de la migration, alors `User.user_type`, `BusinessProfile`, `BusinessProfileCategory`, `Offer.seller` n'existent plus ; la recherche de `user_type`, `BusinessProfile`, `business_profile` dans `backend/apps` ne renvoie plus que des migrations historiques.
- [ ] Étant donné une base SQLite vierge, alors `migrate`, `setup_roles` et `makemigrations --check --dry-run` passent ; la suite `python manage.py test apps` est verte, nombre de tests non inférieur au nombre actuel.
- [ ] Étant donné `setup_roles`, alors les permissions des nouveaux modèles (organisation, appartenance, prestataire, vérification) sont attribuées aux bons groupes de personnel (vérificateur : pièces ; administrateur : organisations en lecture et suspension ; aucun accès aux téléphones des membres) et une permission inconnue fait toujours échouer la commande.
- [ ] Étant donné le script `backend/scripts/recette_contrat_http.py` et le test de contrat du front (`backend-contract.test.ts`), alors ils sont mis à jour et verts.

Règles métier : aucune perte du lien d'avis ; aucun fichier KYC déplacé hors du stockage privé ; pas de sauvegarde ni de base exportée dans le dépôt.
Hors périmètre : toute donnée de production (il n'y en a pas) ; migration des conversations par participants vers la boîte d'équipe (L2-09).
Questions ouvertes : D1, D2.

---

### L0-09i — Front : sélecteur de contexte, inscription simplifiée, organisation

En tant que **utilisateur connecté**, je veux voir et changer mon contexte actif, créer mon organisation et activer mon profil prestataire, afin d'agir clairement sous la bonne identité.

Réf. : CDC §3.1, §6.2 (parcours), §6.3 (états de l'interface), §4.6 (français, i18n) ; dossier client IAM-003/004/005, UF-02/03/04, guide-ecrans ; lot 0. Spec d'écran à produire par `designer-ux` (nouveau parcours).
Dépend de : contrat figé après L0-09b et L0-09g ; livraison alignée sur L0-09h.

Critères d'acceptation (testables) :
- [ ] Étant donné un utilisateur connecté, alors la barre de navigation et l'espace Compte affichent le contexte actif (nom + type) à tout moment, et un sélecteur liste ses contextes (personnel, prestataire, organisations avec rôle).
- [ ] Étant donné un changement de contexte, alors toutes les requêtes suivantes portent le nouveau contexte, les caches React Query dépendants du contexte (mes offres, statistiques, corbeille, messages, réglages de contact) sont invalidés et un test (Vitest) vérifie qu'aucune donnée de l'ancien contexte reste affichée.
- [ ] Étant donné la page d'inscription, alors elle ne propose plus le choix Particulier / Entreprise et n'envoie ni `user_type` ni `business_profile` ; les textes passent par l'i18n.
- [ ] Étant donné un utilisateur sans organisation, quand il choisit « Créer une organisation », alors un formulaire (nom, type parmi quatre, catégories, ville) crée l'organisation et propose de basculer sur ce contexte.
- [ ] Étant donné un utilisateur sans profil prestataire, alors une action « Activer mon profil prestataire » est proposée dans « Mes profils », sans second identifiant.
- [ ] Étant donné un rôle sans droit (par exemple l'analyste qui voit « Publier »), alors l'action est masquée **et** le refus serveur `DENY_PERMISSION` est géré avec un message en français (le masquage n'est jamais le contrôle, doc 06 §24).
- [ ] Étant donné la révocation d'un membre pendant sa session, quand une requête renvoie `DENY_RELATION`, alors l'interface retire ce contexte de la liste et bascule sur le contexte personnel avec un message.
- [ ] Étant donné les pages et composants qui lisent `user_type`, `business_profile` ou `is_verified` (`Register`, `Settings`, `Verification`, `Dashboard`, `PostEditor`, `AccountShell`, `Navbar`, `SellerProfile`, `SellerCard`, `PostCard`, `Businesses`, `lib/post.ts`, `api/types.ts`, `DesignSystem`), alors ils lisent le nouveau contrat ; `npm run lint && npm run test && npm run build` passent.
- [ ] Étant donné un badge de vérification, alors il affiche le libellé précis de chaque claim (« RCCM vérifié ») et jamais un « Vérifié » seul.
- [ ] Étant donné chaque offre, carte vendeur et page vendeur, alors le type de vendeur (particulier, prestataire, organisation) est visible (CDC §3.3).

Règles métier : R4, R5, R7 ; l'interface ne décide jamais de l'autorisation.
Hors périmètre : page d'organisation façon Facebook (L1-03), écrans d'invitation et de gestion des membres (L1-01), boîte d'équipe (L2-09) ; passe i18n finale (L0-18, qui suit L0-09).
Questions ouvertes : Q-CP4.

---

### L0-09j — Recette de non-régression et des scénarios d'identité

En tant que **responsable qualité**, je veux vérifier les scénarios IAM du client et la non-régression des modules touchés, afin de clore L0-09.

Réf. : doc 10 IAM-01 à IAM-08 et AC-07, AC-08, AC-10, AC-14 de doc 06 §22 (partie applicable) ; CDC §10.1.
Dépend de : L0-09h, L0-09i.

Critères d'acceptation (testables) :
- [ ] IAM-01 : création de compte, téléphone vérifié, aucun profil entreprise créé.
- [ ] IAM-02 : changement Personnel -> Prestataire : le contexte change, les capacités se recalculent (publication possible seulement avec profil actif).
- [ ] IAM-03 : changement Personnel -> Organisation : refusé sans `Membership` actif ; accepté avec.
- [ ] IAM-05 : compte suspendu : actions sensibles refusées quel que soit le contexte.
- [ ] IAM-06 et AC-07 : membre retiré : accès révoqué à la requête suivante.
- [ ] AC-08 (partie L0-09) : aucun chemin d'achat ou de plan ne modifie un claim de vérification ni un rôle.
- [ ] AC-14 : un changement de rôle est journalisé avec acteur, cible, organisation et horodatage.
- [ ] Non-régression : suites `identity`, `marketplace`, `reviews`, `visibility`, `messaging`, `notifications`, `moderation`, `common.DomainBoundariesTests` vertes ; contrat HTTP (script de recette) à jour.
- [ ] Hors périmètre de cette recette (non applicables en V1 CDC) : IAM-04 (session expirée, déjà couverte), IAM-07 (branches), IAM-08 (récupération, déjà couverte par les tests existants).

Règles métier : voir §3.
Hors périmètre : AC-01 à AC-06, AC-09 à AC-13, AC-15 de doc 06 qui portent sur recrutement, plans, remboursements, messagerie d'équipe (lots suivants).
Questions ouvertes : aucune propre.

---

## 5. Écarts et ambiguïtés à trancher

### 5.1. Contradictions entre sources (exposées, non tranchées)

| # | Contradiction | Options | Recommandation de l'analyste |
|---|---|---|---|
| E1 | **Rôles.** CDC §3.1 : propriétaire, administrateur, éditeur, analyste (4). Doc 06 §6 : Owner/Org Admin (un seul rôle), Branch Manager, Recruiter, Hiring Manager, Sales Manager, Customer Service, Billing Manager, Event Manager, Training Manager, etc. Doc 06 §23 : « rôles configurables dans un cadre contrôlé » en V1. | (a) 4 rôles du CDC, fixes. (b) 4 rôles de base + permissions affinables plus tard. (c) rôles du doc 06. | (a)/(b) : le CDC fait foi pour le périmètre V1 (README du dossier client). Les rôles recruteur, facturation, événements sont des capacités à rattacher plus tard (L2-07, L1-11, L2-01). À confirmer par le client (Q-CLI1). |
| E2 | **Branches.** Doc 13 §5 : `Branch` « hiérarchie simple V1 » ; doc 06 AC-01/IAM-07 : scope par branche. CDC §11.1 : aucune entité `Branch`. | (a) hors V1. (b) ajouter `Branch`. | (a) : ni le CDC ni le backlog ne le demandent. Question client Q-CLI1. |
| E3 | **Propriétaire et administrateur.** CDC : deux rôles. Doc 06 : « Owner / Org Admin » regroupés. | Garder deux rôles (propriétaire seul peut transférer et archiver) ou un. | Garder deux (CDC). Q-CLI1. |
| E4 | **Chevauchement de backlog.** L1-01 = « création, revendication, invitation, membres et rôles » : recouvre L0-09. | Voir le tableau du §2. | Découpage du §2 (Q-CP1). |
| E5 | **Pièces KYB.** CDC §3.1 : « RCCM ou arrêté d'enregistrement (ONG), identification nationale, pièce du représentant ». Le code exige les trois types fixes (RCCM, ID nationale, pièce du gérant) et ne connaît pas l'arrêté d'une ONG. Doc 07 §3 distingue en plus « Organisation vérifiée » et « Autorité vérifiée ». | Pièces exigées par type d'organisation, en base. | Configurable en base (règle 11) ; valeurs initiales à valider par le client (Q-CLI2). |
| E6 | **« Offre personnelle ».** CDC §3.1 : le contexte personnel permet de « publier une offre personnelle » et les « offres de services » relèvent du prestataire. CDC §3.3 : type « Produit ou service » sans restriction par contexte. Doc 06 §8 : « Publier offre commerciale : Individual — Non par défaut ». | (a) contexte personnel : produits d'occasion et objets personnels seulement ; services réservés au prestataire ou à l'organisation. (b) tout permis partout. | (a) semble le plus cohérent avec doc 06 ; à confirmer (Q-CLI3). Impact sur le formulaire d'offre et sur L1-05. |
| E7 | **ADR 0002 incomplet.** La ligne `marketplace.Offer` indique « `Offer.seller` devient `organization_id` en L0-09 » : cela ne couvre pas le contexte prestataire ni l'offre personnelle (CDC §3.3 : trois types de vendeur). ADR 0004 est correct (`seller_context_type/id`). | Amender l'ADR 0002 dans le futur ADR 0006. | Utiliser `seller_context_type/id` + `created_by`. |
| E8 | **Entité « Context ».** CDC §11.1 liste `Context` dans `identity` ; doc 13 parle d'`Identity` et d'`ActingContext` (calculé). Le brief demande `Membership` et rôles sans entité `Context`. | Contexte purement calculé (personnel = compte, prestataire = `ProviderProfile`, organisation = `Membership`) ou table `Context`. | Calculé (doc 13 : « Contexte actif calculé »). Proposition de mise à jour du CDC §11.1 en §6. |
| E9 | **Avis réciproques entre organisations.** ADR 0004 §Risques : « Avis croisés calculés entre `USER` seulement ; à revoir pour les organisations (L0-09) ». | Étendre à des paires (contexte, utilisateur) ou accepter le risque V1. | À décider avec l'architecte ; comportement documenté dans L0-09f. |

### 5.2. Décisions à prendre par le chef de projet

| # | Question | Recommandation |
|---|---|---|
| D1 | Faut-il une vraie migration de données (`RunPython`) ou réinitialiser la base de développement ? ADR 0002 : aucune donnée de production. | Écrire la migration de données (testée sur un jeu fabriqué) : elle sert aussi de preuve de la correspondance des avis et des pièces. Réinitialiser reste possible par ADR. |
| D2 | Un ancien compte `ENTREPRISE` devient-il une `Organization` de type `ENTREPRISE`, ou un prestataire individuel (le libellé actuel est « Entreprise / Artisan ») ? | Organization de type `ENTREPRISE` pour tous les `BusinessProfile` (c'est la seule donnée disponible ; l'utilisateur peut ensuite activer un profil prestataire). |
| D3 | Transport du contexte actif : en-tête de requête, claim du JWT, ou paramètre. Contraintes de l'analyste : revalidation à chaque requête (R4, AC-07), pas d'état serveur partagé, pas de repli silencieux (R5). Un claim JWT figé pendant 15 minutes serait contraire à la révocation immédiate sauf contrôle en base à chaque requête. | Architecte : en-tête dédié (par exemple `X-Acting-Context: ORGANIZATION:<uuid>`), validé en base à chaque requête. |
| D4 | Rôles et capacités : constantes dans le code ou tables ? | Constantes en V1 (4 rôles du CDC) ; tables si le client demande des rôles configurables (doc 06 §23). Les droits restent indépendants des plans dans les deux cas. |
| D5 | Plafond de contextes par compte (organisations créées, organisations rejointes). | Pas de valeur dans la source : paramètre en base, valeur par défaut à fixer avec le client (Q-CLI4). |
| D6 | Messagerie intérimaire pour les offres d'organisation avant L2-09 (participants = membres ayant `review.reply` ?). | Oui, décrit en L0-09f ; à valider avec l'architecte. |

### 5.3. Questions à poser au chef de projet (Q-CP)

| # | Question |
|---|---|
| Q-CP1 | Valide-t-on le découpage L0-09 / L1-01 / L1-02 du §2 (invitation, revendication et parcours KYB complet restent en lot 1) ? |
| Q-CP2 | Le profil public minimal du vendeur (L0-09g) suffit-il avant L1-03/L1-04, ou veut-on sauter l'étape et livrer les profils complets avec L0-09 ? |
| Q-CP3 | L'éditeur peut-il modifier la description et le logo de l'organisation, ou seulement les contenus (offres, publications) ? Proposition du §3.2 : non pour l'identité de l'organisation. |
| Q-CP4 | Le dernier contexte choisi est-il mémorisé côté serveur (préférence de compte) ou seulement dans le navigateur ? Proposition : navigateur. |
| Q-CP5 | La création d'une organisation exige-t-elle un numéro de téléphone vérifié (anti-abus) ? La source n'impose rien. |
| Q-CP6 | Durée pendant laquelle un ancien membre ne peut pas décider sur la vérification de son ancienne organisation : aucune valeur dans la source. |
| Q-CP7 | Une offre dont l'auteur quitte l'organisation reste-t-elle à l'organisation ? (Proposition du §3.1 R6, conforme à doc 06 §19.) |
| Q-CP8 | Un acheteur peut-il contacter un vendeur « au nom d'une organisation » en V1 ? Proposition : non, le contact reste personnel (doc 06 §8 le prévoit « si achat org autorisé »). |

### 5.4. Questions à poser au client (Q-CLI)

| # | Question | Pourquoi c'est bloquant |
|---|---|---|
| Q-CLI1 | Les 4 rôles du CDC (propriétaire, administrateur, éditeur, analyste) suffisent-ils pour la V1 ? Les branches/départements sont-ils hors V1 ? Plusieurs propriétaires sont-ils permis ? | E1, E2, E3 : fige la matrice et le modèle. |
| Q-CLI2 | Pièces KYB exigées par type d'organisation (entreprise, boutique informelle sans RCCM, ONG, organisateur d'événements) ; une organisation non vérifiée peut-elle publier et être visible ? | E5 ; très de petits commerces de Kinshasa n'ont pas de RCCM. Le code actuel autorise la publication sans vérification : à confirmer. |
| Q-CLI3 | Que peut publier le contexte personnel : objets d'occasion seulement, ou aussi des services ? | E6 ; conditionne le formulaire d'offre. |
| Q-CLI4 | Combien d'organisations par compte (créées et rejointes) ? Une organisation par personne suffit-elle au lancement ? | Anti-abus ; paramètre. |
| Q-CLI5 | Qui consent à la révélation du numéro de contact d'une organisation, et quel texte de consentement s'applique (LEG-PRV-03 est encore provisoire pour les particuliers) ? | Texte juridique ; sans réponse, l'organisation n'offre que le canal message (L0-09f). |
| Q-CLI6 | Durée de conservation des pièces KYB et de la pièce du représentant après refus, retrait ou fermeture de l'organisation ; durée de conservation de l'audit des membres (LEG-PRV, déjà ouverte pour `AuditLog`). | Aucune valeur dans la source ; ne pas inventer. |
| Q-CLI7 | Le profil prestataire peut-il publier sans vérification d'identité ? Quelles catégories exigent une vérification renforcée (doc 07 §6) ? | Hors L0-09 mais conditionne l'activation (TRU-002). |
| Q-CLI8 | Nom d'une organisation : unicité ou homonymes autorisés avec revendication ? Comment lutter contre l'usurpation du nom d'une entreprise connue avant L1-01 (revendication) ? | Risque d'usurpation en lot 0/1 ; l'unicité conditionnelle est interdite par ADR 0001. |

---

## 6. Propositions de mise à jour du CDC (diff texte, à n'appliquer que sur accord)

**§11.1 — ligne `identity`**
- Ancien : `| identity | User, Context, Organization, Membership, Role, VerificationRequest, OtpCode |`
- Nouveau : `| identity | User, ProviderProfile, Organization, Membership, VerificationRequest, ContactPoint, ContactConsent, OtpCode |` (le contexte actif est calculé, il n'a pas de table ; les rôles sont des constantes ou une table selon D4)

**§11.2 — tableau des événements, ajouter une ligne**
- Nouveau : `| MembershipChanged | identity | messaging, notifications, moderation |` (doc 13 : MembershipChanged -> Authorization, messaging, audit)

**§3.1 — après « Rôles dans l'organisation… »**
- Ancien : `Rôles dans l'organisation : propriétaire, administrateur, éditeur, analyste. Le départ d'un membre retire son accès sans supprimer son compte personnel.`
- Nouveau (si la matrice du §3.2 est validée) : `Rôles dans l'organisation : propriétaire, administrateur, éditeur, analyste. Le propriétaire gère tout, transfère et archive ; l'administrateur gère l'équipe (sauf propriétaires), le profil et la vérification ; l'éditeur gère les offres et répond aux avis et aux contacts ; l'analyste lit les statistiques. Une organisation a toujours au moins un propriétaire. Le départ d'un membre retire son accès immédiatement sans supprimer son compte personnel, ses offres personnelles ni ses avis.`

**§3.1 — Organisations, vérification**
- Ancien : `Le badge affiche précisément ce qui a été vérifié (par exemple « RCCM vérifié »).`
- Nouveau : ajouter `Les pièces exigées dépendent du type d'organisation et se configurent dans le back-office. La mention « Organisation vérifiée » ne s'affiche qu'accompagnée de la liste de ce qui a été vérifié.`

**§11.4 — ligne d'écart « Types de compte Particulier / Business »**
- Ajouter la tâche détaillée : `L0-09a à L0-09j (voir docs/specs/L0-09-compte-contextes.md)`.

---

## 7. Estimation de l'impact sur l'API et le code existants (pour l'architecte)

Comptage indicatif par recherche de `user_type|BusinessProfile|business_profile|is_verified|PARTICULIER|ENTREPRISE` : environ 278 occurrences dans 23 fichiers du backend (dont une large part de tests et `scripts/recette_contrat_http.py`) et environ 40 occurrences dans 17 fichiers du front. Les références à `seller` hors tests : environ 128 occurrences dans 23 fichiers.

### 7.1. Endpoints existants (préfixes actuels `/api/accounts/`, `/api/marketplace/` ; L0-11 les passera sous `/api/v1/`)

| Endpoint | Changement |
|---|---|
| `POST accounts/register/` | Retrait de `user_type`, `business_profile` (sérialiseur `UserSerializer.create`) |
| `GET/PATCH accounts/me/` | Retrait de `user_type`, `business_profile` ; ajout de la liste de contextes ou lien |
| `GET accounts/businesses/` (`BusinessListView`) | Devient la liste des organisations ; clés `business_name`, `is_verified` -> `name`, `verified_claims` ; filtre `?is_verified` remplacé ; filtre sur `user_type='ENTREPRISE'` supprimé |
| `accounts/kyc/documents/` (liste, dépôt, suppression) | Rattachés à une organisation (ressource imbriquée ou paramètre) ; permission par rôle d'organisation au lieu de `request.user.business_profile` |
| `accounts/kyc/review-queue/`, `decision/`, `download/` | Chemins stables ; la file affiche l'organisation ; règle « décideur membre » ; `recompute_verification` devient un recalcul de claims |
| `accounts/contact-settings/*` | Passent à un contexte (personnel, prestataire, organisation) : `ContactPoint` (OneToOne `User`) et `ContactConsent` (`user`, `channel`) à porter par contexte. **Impact fort sur ADR 0005.** |
| Nouveaux | contextes de l'utilisateur ; organisations (création, lecture publique, modification) ; profil prestataire (activation, lecture, archivage) ; (plus tard L1-01 : membres) |
| `marketplace` offres (`OfferViewSet`) | `serializer.save(seller=request.user)` -> contexte résolu ; filtres `seller=request.user`, `seller__is_active`, `?seller=` ; « mes offres » et corbeille par contexte ; propriété d'une offre (`instance.seller_id == request.user.id`) -> `acts_for_context` + capacité |
| Sérialiseur du vendeur (`SellerSerializer`) | `user_type`, `business_profile` remplacés par `seller = {context_type, context_id, ...}` ; contrat consommé par `SellerCard`, `PostCard`, `SellerProfile`, `lib/post.ts`, test de contrat |
| Contacts / révélations (`create_contact_event`, `reveal_contact`, `list_reveals_for_seller`, `get_allowed_channels`, `get_contact_endpoint`) | Utilisent `offer.seller_id` (compte vendeur) : à passer au contexte vendeur ; contact de sa propre offre -> membre de l'organisation |
| `GET reviews/?seller=` | Déjà générique (identifiant de contexte) ; `acts_for_context` et résolution des destinataires à étendre |
| `stats/dashboard/`, `stats/post/<id>/` | Agrégation par contexte (`DailyVisibilityCounter.seller` FK `User` -> contexte) |
| Modération | `Sanction` cible un compte ; sanction d'organisation (suspension) à prévoir (Q à poser à l'architecte) ; vérifs « l'offre appartient au sanctionné » ; `UserSanctioned` consommé par `marketplace` (masquage des offres d'un compte : étendre aux offres des contextes du compte ?) |
| Admin et `setup_roles` | `BusinessProfile`, `BusinessProfileCategory`, `user_type` à retirer ; nouveaux modèles à enregistrer ; permissions de groupes |

### 7.2. Modèles et migrations

- `identity` : ajout `Organization`, `OrganizationCategory` (liaison interne), `Membership`, `ProviderProfile` (+ liaison catégories) ; `KycDocument.business_profile` -> `organization` (FK interne autorisée, même domaine) ; suppression ensuite de `User.user_type`, `BusinessProfile`, `BusinessProfileCategory`. Migrations `0006+` sérialisées.
- `marketplace` : `Offer.seller` (FK) -> `seller_context_type`, `seller_context_id`, `created_by` ; index `offer_seller_deleted` à refaire ; propriétés `seller_context_*` deviennent des champs.
- `visibility` : `DailyVisibilityCounter.seller` (FK `User`) -> contexte vendeur.
- `reviews` : `seller_context_*` existent déjà ; données à recontextualiser (L0-09h).
- `messaging`, `notifications`, `moderation` : voir tableau ci-dessus ; événement `reviews.review_posted` v2 déjà prêt (`recipient_id`, contexte).
- `common/contexts.py` : ajouter `CONTEXT_PROVIDER`.
- Outbox : nouvel événement `MembershipChanged` (ADR 0003).
- `DomainBoundariesTests` : tout rester vert ; les services `identity` exposent par lot : `get_contexts_for_user`, `acts_for_context`, `resolve_acting_context`, `can(user, context, capacity)`, `get_context_recipients(context, capacity)`, `get_seller_summaries` (nouvelle forme).

### 7.3. Front (`connect-grow`, branche `frontend`)

Fichiers qui lisent `user_type`, `business_profile` ou `is_verified` du compte ou du vendeur : `pages/Register.tsx`, `Settings.tsx`, `Verification.tsx`, `Dashboard.tsx`, `PostEditor.tsx`, `SellerProfile.tsx`, `Businesses.tsx`, `DesignSystem.tsx`, `components/layout/Navbar.tsx`, `AccountShell.tsx`, `components/common/SellerCard.tsx`, `PostCard.tsx`, `lib/post.ts`, `lib/validation.ts` (erreurs imbriquées), `api/types.ts`, `api/backend-contract.test.ts`, `hooks/use-marketplace.ts`, `hooks/use-account.ts`, `contexts/AuthContext.tsx`. Nouveau : fournisseur de contexte actif, en-tête de requête dans `api/client.ts`, sélecteur, écrans de création d'organisation et d'activation prestataire (spec `designer-ux` à produire).

### 7.4. Estimation de taille (ordre de grandeur, pour planification)

| Story | Taille relative |
|---|---|
| L0-09a | M |
| L0-09b | M |
| L0-09c | S |
| L0-09d | M |
| L0-09e | L |
| L0-09f | L (scindable) |
| L0-09g | M |
| L0-09h | M |
| L0-09i | L |
| L0-09j | S |

### 7.5. Risques

1. Réécriture massive des tests existants (remplacement de `user_type` et `seller` dans plus de 20 fichiers) : ne pas laisser baisser le nombre de tests.
2. Régression silencieuse du contexte : un repli sur le personnel publierait au mauvais nom : couvert par les critères de L0-09b (R5).
3. Fuite de données personnelles par l'organisation (téléphone d'un membre) : couvert par L0-09f et le test d'exhaustivité des clés de L0-09g.
4. Conflit de migrations `identity` avec une autre tâche en cours : sérialiser (ADR 0002 étape 9).
5. Le texte de consentement de contact (ADR 0005, LEG-PRV-03) n'est pas défini pour les organisations : comportement par défaut protecteur imposé.
6. Usurpation d'une organisation avant la revendication (L1-01) : Q-CLI8.

---

## 8. Lignes proposées pour `docs/suivi/BACKLOG.md` (non appliquées : écriture limitée à ce fichier)

| ID | Tâche | Agents | Statut | Réf. |
|---|---|---|---|---|
| L0-09a | Organization, Membership, rôles et capacités (services, audit, outbox `MembershipChanged`) | architecte-technique, dev-backend | À faire | §3.1, IAM-005/006/007 |
| L0-09b | Contexte actif : liste, résolution serveur, codes de refus | dev-backend | À faire | §3.1, IAM-003 |
| L0-09c | Profil prestataire individuel (activation, contexte `PROVIDER`) | dev-backend | À faire | §3.1, IAM-004 |
| L0-09d | Vérification des organisations : pièces rattachées, badge précis | dev-backend, auditeur-securite | À faire | §3.1, TRU-003 |
| L0-09e | Offres et statistiques par contexte vendeur | dev-backend | À faire | §3.3, MKT-001 |
| L0-09f | Contact, avis, notifications, messagerie par contexte vendeur | dev-backend | À faire | §3.4, §3.15 |
| L0-09g | Inscription au compte unique, `/me/`, profils publics minimaux | dev-backend | À faire | §3.1, §3.2 |
| L0-09h | Migration des données et suppression de `user_type` / `BusinessProfile` | dev-backend | À faire | §11.4 |
| L0-09i | Front : sélecteur de contexte, inscription, organisation | designer-ux, dev-frontend | À faire | §3.1, UF-02 à UF-04 |
| L0-09j | Recette L0-09 (IAM-01 à IAM-06) | qa-testeur | À faire | doc 10 |

Revue de sécurité (`auditeur-securite`) obligatoire pour L0-09b (contexte et permissions), L0-09d et L0-09f (données personnelles, pièces).
