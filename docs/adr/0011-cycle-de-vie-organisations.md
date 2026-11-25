# ADR 0011 — Cycle de vie, restrictions et changement de nom des organisations (L1-17, L1-19, L1-20)

- **Amendement A-L17 / D-L17 (25-26/11/2026) :** décisions C1, C2, C3, C5, C6, C8, QU-2 du chef de projet (`docs/specs/L1-17-cycle-de-vie-organisations.md` §7, §10.2) et QD-1, QD-2, QD-4, QD-5 (`docs/specs/L1-17-ecrans-cycle-de-vie.md` §17) intégrées en D8, D10, 4.2, 4.4, 5.1, 6.1, 6.2, 6.3, 7 ; détail dans l'en-tête du contrat.
- **Statut :** proposé (à valider par le chef de projet ; points de la section 17 marqués « utilisateur » ou « client » à faire valider par Anicet ou Jonathan)
- **Date :** 25/11/2026
- **Décideurs :** client (décisions verrouillées Q17, Q33, Q34, Q35, Q4), chef de projet (découpage L1-17 à L1-20), architecte technique (rédaction, modèle)
- **Amende :** ADR 0006 §4.2 (`status`, `suspension_reason`), §6.2 (résolution du contexte), §7.1 (`is_seller_context_public`, `acts_for_context`, `suspend_organization`, `reactivate_organization`, `archive_organization`), §9.2 (`archive/`, verrou du nom), A9 (raisons de l'événement de statut), A13 (verrou du nom : procédure de demande), A14 (code `DENY_RESTRICTION`), §19.1 n°2, §20 (correction 2 de T9-2 : réactivation d'une archivée), §21 (clés de `unavailable`) ; ADR 0008 §9 (organisations suspendues et archivées) et §19 de l'ADR 0006 n°6 (départ d'une archivée) ; ADR 0010 §4.5 (index `org_primary_admin_state`), §6.3 (« organisation `ACTIVE` »), §15 (interfaces soldées) ; ADR 0009 §4 et §6 (obligations ouvertes, droits d'une organisation fermée).
- **Contrat d'API :** `docs/specs/L1-17-contrat-api.md` (à recopier dans les briefs des tâches de la section 16).
- **Réf. :** réponses du client Q4, Q17, Q24 (par analogie), Q33, Q34, Q35, Q1, Q16 (`docs/client/ConnectePlus_Reponses_Consolidees_Q1-Q36.md`) ; analyse d'impact `docs/specs/impact-reponses-client-Q1-Q36.md` (K8, K9, K10, QO-8) ; spec `docs/specs/L0-09-ecran-organisation-suspendue.md` ; CLAUDE.md §4 (règles 2, 3, 4, 8, 10, 11, 12) et §5 ; ADR 0001, 0003, 0006, 0008, 0009, 0010.

**Hors périmètre** (interfaces seulement, section 14) : effacement ou anonymisation d'une organisation (`ERASED`, exécuté par L1-24 avec la politique de conservation et le gel juridique) ; fermeture de compte (ADR 0012) ; régularisation d'une organisation sans Administrateur principal (L1-02f) ; noms protégés (L1-02g) ; Aide et Support (L1-21) ; matrice des sanctions (DOC-01) ; matrice des modifications sensibles (DOC-02) ; affichage public de la dénomination légale et de « anciennement » (L1-02c).

---

## 1. Contexte

Le code livré (L0-09, T9, B-SUSP) porte un **statut unique** `Organization.status` (`ACTIVE`, `SUSPENDED`, `ARCHIVED`) et un `suspension_reason` à quatre codes jamais montrés. Ce champ mêle une **sanction** (`SUSPENDED`) et un **cycle de vie** (`ARCHIVED`). Les réponses verrouillées du client l'interdisent :

| Réponse | Exigence | Code livré qui la contredit |
|---|---|---|
| Q34 | Cycle Active → Inactive/dormante → Fermeture en cours → Archivée → Supprimée/anonymisée. Inactivité = dormante, jamais archivée. Archivage ≠ suspension ≠ exclusion ≠ suppression. Sanctions et cycle de vie séparés. Restauration exceptionnelle, contrôlée, auditée, **du même objet**. Après suppression irréversible : nouvelle création seulement. | `status` unique ; `archive_organization` « irréversible par l'API » ; `reactivate_organization` refuse une archivée ; ni dormante ni fermeture en cours. |
| Q33 | Les administrateurs voient : statut, catégorie (7 catégories illustratives, configurables), motif communiqué, périmètre affecté, depuis, action requise, recours ; pas les preuves internes. Suspension totale **ou** restriction ciblée (publication, fonction, module, activité, branche, permission). Un échec de paiement ne suspend pas. Un membre ordinaire ne voit pas les éléments sensibles. | Suspension totale seulement ; 4 motifs codés en dur, jamais exposés ; écran L0-09 sans motif. |
| Q17 | Statuts séparés : compte, autorité, état administratif, sanctions. Une organisation peut être **à la fois** suspendue et orpheline. Remplacer l'administrateur n'annule pas une suspension indépendante. Sans représentation rétablie : restreinte, puis archivée. | Orphelinat stocké par l'ADR 0010 (B10) ; aucune restriction ni archivage d'une orpheline. |
| Q35, Q1 | Nom vérifié verrouillé contre l'édition ordinaire mais changeable par une **demande contrôlée** (type, motif, justificatifs, autorité, authentification renforcée, validation, revérification, audit). Dénomination légale, nom d'affichage, historique. Le nouveau nom n'hérite pas du statut vérifié. Nouvelle entité = nouvelle organisation ; rien n'est transféré par renommage. | Un seul champ `name` ; verrou `409 name_locked_by_verification` qui renvoie à un support inexistant. |
| Q4, Q16 | Fermeture : actif → archivé/restreint → suppression ou anonymisation ; durées configurables ; gel juridique. Sanction = objet distinct, avec catégorie, motif, durée, recours, audit. | Aucune durée ; aucune trace structurée de suspension. |

**Constat d'architecture favorable.** Seul le domaine `identity` lit `Organization.status` (vérifié par recherche : `acting.py`, `organizations.py`, `sellers.py`, `organization_reads.py`, `invitations.py`, `services.py`, `admin.py`). Les autres domaines passent par `identity.services` (`is_seller_context_public`, `ensure_seller_context_accepts_contact`, `authorize_on`, `can`) et par l'événement `identity.seller_context_status_changed`. La séparation se fait donc **dans un seul domaine**, sans transaction inter-domaines. Côté tests, 117 occurrences dans 27 fichiers (dont `marketplace`, `messaging`, `common`) créent des organisations suspendues ou archivées par l'ORM : un utilitaire de test unique les absorbe (section 12).

## 2. Options étudiées

### 2.1 Où vivent les restrictions d'organisation

| # | Option | Verdict |
|---|---|---|
| A | **Dans `identity`** (`OrganizationRestriction`), à côté du cycle de vie ; `moderation` garde les signalements et les sanctions des comptes | **Retenue.** L'autorisation (`authorize_on`, `_authorize_member`, `contexts/`, visibilité publique) est dans `identity` : la mesure en vigueur s'y lit dans la même requête que l'appartenance (zéro requête de plus grâce au résumé dénormalisé, 4.3). La restauration (Q34) contrôle cycle de vie et restrictions dans **une** transaction d'un seul domaine. Découpage futur en services : `moderation` deviendrait un client de l'API d'`identity`, pas l'inverse. |
| B | Dans `moderation` (`Sanction` généralisée à `subject_type/subject_id`) | Rejetée : chaque autorisation d'organisation appellerait `moderation` (une requête de plus, déjà deux pour la garde du compte) ; la restauration et la fermeture couvriraient deux domaines (interdit sans outbox) ; une clé étrangère vers `Organization` serait interdite. |
| C | Garder `status` et ajouter des drapeaux | Rejetée : c'est le défaut actuel (K9) ; une suspension et un archivage s'écrasent. |

Conséquence assumée : la **sanction d'un compte** (`moderation.Sanction`) et la **restriction d'une organisation** (`identity.OrganizationRestriction`) sont deux objets distincts, ce que Q17 exige (« les sanctions de la personne et de l'organisation sont distinctes »). DOC-01 pourra unifier la taxonomie (catégories) sans fusionner les tables.

### 2.2 Ce qu'est une « mesure » (restriction ciblée)

| # | Option | Verdict |
|---|---|---|
| A | Liste JSON de capacités bloquées sur chaque restriction | Rejetée : les codes de capacité sont internes et évoluent ; une ligne écrite aujourd'hui ne signifierait plus la même chose demain ; illisible pour le personnel. |
| B | **Liste fermée de mesures en code** (`FULL_SUSPENSION`, `PUBLICATION_BLOCK`…), chacune associée à un effet testé (capacités refusées, visibilité, contact) ; **catégories de motif configurables** en back-office | **Retenue.** Les mesures sont du code d'application (un effet = un chemin de refus testé) ; ce qui doit évoluer sans développement (catégories, libellés, explications, durées) est en base (règle 11). |

### 2.3 Résumé des restrictions pour l'autorisation

| # | Option | Verdict |
|---|---|---|
| A | Requête des restrictions actives à chaque autorisation | Rejetée : une requête de plus sur le chemin chaud ; les listes (`contexts/`, annuaire, drapeaux de visibilité) devraient joindre une table de plus. |
| B | **Dénormalisation sur `Organization`** : `active_restriction_measures` (codes triés) et `public_visibility_blocked` (booléen), recalculés sous verrou à chaque pose, levée ou expiration, et resynchronisés par cron | **Retenue.** Même mécanique que `seller_is_public` (ADR 0006 A7) et `primary_admin_state` (ADR 0010 D9). Écart maximal après une échéance (`ends_at`) : la période du cron (10 min), **en échec fermé** (la mesure reste appliquée un peu plus longtemps, jamais moins). |

### 2.4 Migration du statut unique

| # | Option | Verdict |
|---|---|---|
| A | **Étendre puis contracter dans la même tâche** (deux migrations) : ajouter `lifecycle_status` et les restrictions, convertir, puis retirer `status` et `suspension_reason` ; champ d'API `status` conservé **dérivé** le temps que le front migre | **Retenue.** Aucune donnée de production (ADR 0002) ; pas de colonne morte qu'un lecteur oublié lirait périmée (le retrait fait échouer les tests de tout lecteur oublié) ; retour arrière réel par reconstruction (10.2). |
| B | Garder `status` synchronisé pendant une période | Rejetée : deux sources de vérité, exactement le problème à résoudre. |

### 2.5 Nom pendant l'examen d'une demande de changement (Q35)

| # | Option | Verdict |
|---|---|---|
| A | **Le nom public reste l'ancien jusqu'à la décision** ; le nouveau nom est visible en interne « en cours de vérification » | **Retenue pour la V1** (recommandation, QL-5). Aucun nom non vérifié n'est affiché à côté de badges obtenus pour l'ancien nom (règle 3) ; Q35 dit « peut être indiqué », pas « doit ». |
| B | Afficher publiquement le nouveau nom marqué « en cours de vérification » et masquer les badges pendant l'examen | Réservée (ajout additif possible) : plus juste pour un renommage légitime mais pénalise l'organisation et complique l'affichage public (L1-02c). |

### 2.6 Restauration : qui la demande

| # | Option | Verdict |
|---|---|---|
| A | **Demande reçue par l'Aide et Support (L1-21), enregistrée par le personnel** dans le back-office ; double contrôle (préparation, décision) | **Retenue pour la V1** (QL-6). Q34 décrit un acte exceptionnel du personnel ; aucune surface publique nouvelle ; le demandeur est tracé. |
| B | Endpoint de demande pour l'Administrateur principal encore membre de l'organisation archivée | Ajout additif possible (champ `channel = IN_APP` déjà prévu). |

## 3. Décisions

1. **D1 — Trois axes indépendants (règle 8).** L'état d'une organisation se lit sur des champs distincts qu'aucun n'écrase : **cycle de vie** (`lifecycle_status`), **restrictions** (lignes `OrganizationRestriction` + résumé dénormalisé), **gouvernance** (`primary_admin_state`, ADR 0010), **revue de création** (`creation_review_status`, ADR 0010), **demande de changement de nom**, **demande de restauration**. Exemple valide : `ARCHIVED` + suspendue + `MISSING`.
2. **D2 — Cycle de vie opérationnel.** `ACTIVE`, `DORMANT`, `CLOSING`, `ARCHIVED`, `ERASED` (section 5.1). Aucune transition du cycle de vie ne pose ni ne lève une restriction, sauf les deux cas système listés en D6.
3. **D3 — Restrictions.** Objet `OrganizationRestriction` : mesure (liste fermée, 4.2), périmètre (organisation entière en V1 ; branche réservée), catégorie configurable, motif communiqué, niveau de divulgation, depuis, échéance, action requise, recours, note interne (personnel seul), origine. Plusieurs restrictions actives peuvent coexister, y compris de même mesure (causes différentes ; lever l'une ne lève pas l'autre, Q17).
4. **D4 — Ce que voient les membres (Q33).** Administrateurs principaux et administrateurs (`org.view_restrictions`) : le détail de chaque restriction (catégorie, explication, motif communiqué sauf divulgation limitée, mesure, périmètre, depuis, échéance, action requise, recours) ; jamais la note interne, l'auteur, l'origine ni les preuves. Autres rôles : seulement « suspendue oui/non » et la liste des mesures (ce qui est bloqué), sans catégorie ni motif. Public : rien (l'organisation ou la fonction est simplement indisponible).
5. **D5 — Restauration exceptionnelle (Q34).** Objet `OrganizationRestorationRequest`, double contrôle obligatoire (une personne prépare les contrôles, une autre décide ; aucune n'est ni membre, ni ancien membre, ni créatrice, ni demandeuse). La restauration rouvre **le même objet** (`ARCHIVED -> ACTIVE`), conserve l'historique, ne lève aucune restriction, et peut exiger une revérification (D6). `ERASED` : restauration impossible (`409 restoration_impossible`).
6. **D6 — Restrictions posées par le système (liste fermée).** (a) **Gouvernance** (Q17) : organisation `MISSING` depuis plus de `orphan_restrict_after_days` -> `PUBLICATION_BLOCK`, catégorie `governance`, action requise `REGULARIZE_GOVERNANCE`, levée automatiquement au retour à `OK` ; au-delà de `orphan_archive_after_days` -> archivage système. (b) **Restauration avec revérification** : `PUBLIC_VISIBILITY_HIDDEN`, catégorie `verification_identity`, action `SUBMIT_DOCUMENTS`, levée par le personnel Vérification. **Aucune autre origine système n'est acceptée** par le service (test) : un échec de paiement, un signal anti-abus ou une note ne posent jamais de restriction automatique (Q33).
7. **D7 — Fermeture par les membres.** `POST closure/` remplace `POST archive/` : Administrateur principal effectif, ressaisie du mot de passe, motif codé ; passage à `CLOSING` ; finalisation en `ARCHIVED` dès que le délai `closure_delay_days` est écoulé **et** qu'aucune obligation ouverte n'est signalée par les modules concernés (registre, 6.4). Délai 0 et aucune obligation : `CLOSING` puis `ARCHIVED` dans la même transaction (comportement actuel conservé). Annulation possible pendant `CLOSING` par tout Administrateur principal effectif. Fermeture permise sous suspension (QL-3) : les restrictions survivent à l'archivage et bloquent l'effacement.
8. **D8 — Dormance.** `ACTIVE -> DORMANT` par le cron quand aucune activité n'est constatée depuis `dormancy_after_days` (0 = désactivé, défaut tant que le client n'a pas fixé la valeur, QO-8). Effets : aucune capacité retirée ; sortie de l'annuaire ; profil et offres restent publics ; bannière aux administrateurs. Retour `ACTIVE` par l'action « Confirmer l'activité » (`POST resume/`) ou par le cron dès qu'une activité nouvelle est constatée. La revérification d'informations expirées relève de la vérification (L1-02d), pas du cycle de vie.
9. **D9 — Changement de nom contrôlé (Q35).** Champs `name` (nom d'affichage, inchangé) et `legal_name` (dénomination légale, nouveau), historique append-only `OrganizationNameHistory`, objet `OrganizationNameChangeRequest` (trois types : correction typographique, changement du nom d'affichage, changement de dénomination légale). Le verrou A13 reste ; il porte sur les deux champs ; le message renvoie à la demande. Justificatifs = pièces KYB rattachées à la demande, **exclues du calcul des badges** tant que la demande n'est pas aboutie. Décision par l'équipe Vérification (ADR 0010 §9.1). « Nouvelle entité » : refus motivé `new_entity_required`, l'organisation doit être créée à part (rien n'est transféré).
10. **D10 — Code de refus `DENY_RESTRICTION`** (403), ajouté à la famille A14 : refus d'une capacité par une restriction ciblée, avec la clé additive `measure`. **Réservé aux membres de l'organisation** (C2) : un acheteur ou un tiers ne reçoit jamais `DENY_RESTRICTION` ni `measure`, mais le refus neutre existant `403 seller_contact_unavailable` (celui d'une organisation sans canal, ADR 0006 §19.3 n°4), qui ne révèle aucune mesure. La suspension totale garde `DENY_SECURITY` ; `CLOSING` et `ARCHIVED` gardent `DENY_OBJECT_STATE` (compatibilité du front livré).
11. **D11 — Ce qui ne change pas.** `org_type` immuable ; homonymes permis (A12) ; `org.leave` toujours permis (sauf `last_owner` sur une organisation non archivée) ; la revue de création (ADR 0010 D8) reste un état propre, **pas** une restriction (une restriction a une catégorie et un motif communiqués, ce qui révélerait le seuil caché de Q22) ; aucun service ne reçoit de plan, de prix ni de droit commercial (règle 2) ; `is_staff` n'ouvre rien.

## 4. Modèle de données (domaine `identity`)

UUID partout (`BaseModel`). Aucune clé étrangère hors d'`identity`, sauf vers `User`. Longueurs explicites. Aucune unicité conditionnelle (invariants en service, sous verrou d'organisation). Aucune fonction SQL propre à un moteur.

### 4.1 `Organization` (ajouts, retraits)

| Champ | Type | Défaut | Remarques |
|---|---|---|---|
| `lifecycle_status` | `CharField(12)`, choix | `'ACTIVE'` | `ACTIVE`, `DORMANT`, `CLOSING`, `ARCHIVED`, `ERASED` |
| `lifecycle_changed_at` | `DateTimeField` | `timezone.now` | « depuis » du cycle de vie |
| `lifecycle_reason` | `CharField(30)`, blank | `''` | exposé aux seuls détenteurs de `org.view_restrictions` sous une forme réduite (`origin` : `MEMBERS`, `CONNECTE_PLUS`, `AUTOMATIC`, contrat §0.2, C6 ; jamais l'auteur ni la note) ; code de la dernière transition (`member_closure`, `closure_cancelled`, `dormancy`, `resumed`, `activity_detected`, `orphaned`, `staff_decision`, `restored`, `legacy_status`) |
| `closure_effective_at` | `DateTimeField`, nul | | `CLOSING` seulement : date de finalisation au plus tôt |
| `last_activity_at` | `DateTimeField`, nul | | calculé par le cron (6.5) ; jamais écrit sur une requête de lecture |
| `active_restriction_measures` | `CharField(255)`, blank | `''` | résumé dénormalisé : codes des mesures actives, triés, séparés par des virgules ; lu en Python, jamais filtré en SQL |
| `public_visibility_blocked` | `BooleanField` | `False` | vrai si une restriction active a la mesure `FULL_SUSPENSION` ou `PUBLIC_VISIBILITY_HIDDEN` ; filtré en SQL (annuaire, drapeaux de visibilité) |
| `legal_name` | `CharField(255)`, blank | `''` | dénomination légale (D9, tâche L1-20-B5) ; non publique en V1 (L1-02c décidera) ; minimisée comme le NIF (`org.edit_profile` seulement) |
| ~~`status`~~ | retiré | | remplacé par `lifecycle_status` + restrictions (10.2) |
| ~~`suspension_reason`~~ | retiré | | remplacé par la catégorie de la restriction |

Index : `org_lifecycle_type (lifecycle_status, org_type)` remplace `org_status_type` ; `org_lifecycle_activity (lifecycle_status, last_activity_at)` (dormance) ; `org_lifecycle_closure (lifecycle_status, closure_effective_at)` (finalisation). **Amendement ADR 0010 :** l'index de B10 devient `org_primary_admin_state (primary_admin_state, primary_admin_missing_since)` (il ne doit plus citer `status`).

Permissions Django (`Meta.permissions`) : `suspend_organization` est **remplacée** par `impose_organizationrestriction` (« Peut restreindre ou suspendre une organisation ») et `lift_organizationrestriction` ; ajout de `archive_organization_staff` (« Peut archiver une organisation par décision du personnel »).

### 4.2 Mesures (constantes pures, `identity/capabilities.py`, aucune importation de modèle)

| Mesure | Effet sur les capacités des membres | Effet public et entrant |
|---|---|---|
| `FULL_SUSPENSION` | tout refusé (`DENY_SECURITY`) sauf `org.leave`, `org.view_restrictions`, `org.archive` (fermeture, QL-3) | organisation et offres non publiques ; contact, révélation, échange, message entrants refusés (`DENY_SECURITY`, inchangé) |
| `PUBLICATION_BLOCK` | `offer.publish`, `offer.edit` (création, modification, renouvellement, reprise) refusés ; `offer.delete` et la mise en pause restent permis (réduire l'exposition est toujours permis) | aucun ; les offres déjà publiées restent |
| `PUBLIC_VISIBILITY_HIDDEN` | aucune | organisation et offres non publiques (usage contesté d'un nom pendant l'examen, Q1 ; revérification après restauration, D6) |
| `CONTACT_BLOCK` | aucune | canaux de contact vides, révélation et échange entrants refusés (`403 seller_contact_unavailable`, neutre, C2) |
| `MESSAGING_BLOCK` | `message.reply` refusé | nouvelle conversation **et** nouveau message d'un acheteur dans une conversation déjà ouverte refusés (`403 seller_contact_unavailable`, neutre, C5) ; l'historique reste lisible |
| `REVIEW_REPLY_BLOCK` | `review.reply` refusé | aucun |
| `TEAM_CHANGES_BLOCK` | `org.manage_members`, `org.manage_roles` refusés (invitations, confirmations, nominations, rôles, retraits) ; `org.leave` permis | aucun (conflit d'autorité, L1-02e) |
| `PROFILE_EDIT_BLOCK` | `org.edit_profile` refusé ; **la demande de changement de nom reste permise** (`org.request_name_change`, c'est le remède) | aucun |

Une mesure inconnue lève une erreur de programmation. La matrice rôle x cycle de vie x mesure x capacité est testée case par case (test paramétré). Toute nouvelle capacité doit être classée dans cette table (test qui échoue sinon).

**Capacités ajoutées (ADR 0006 §5 amendé) :** `org.view_restrictions` (Administrateur principal, Administrateur) ; `org.request_name_change` (Administrateur principal, Administrateur : mêmes rôles que `org.verification_submit`, QD-5) ; `org.confirm_activity` (Administrateur principal, Administrateur ; absente de toute liste de blocage des mesures ciblées, QD-2). Lecture partagée `restricted_capabilities(role, scope, measures)` : capacités du rôle retirées par les seules mesures ciblées, exposée dans `contexts/` et `internal/` (QD-1). `org.archive` garde son code et prend le libellé « Fermer l'organisation » (Administrateur principal seul, inchangé).

**Capacités permises selon le cycle de vie** (avant toute restriction) :

| Cycle de vie | Capacités encore exerçables (selon le rôle) | Refus |
|---|---|---|
| `ACTIVE`, `DORMANT` | toutes | — |
| `CLOSING` | `org.view_internal`, `org.leave`, `org.archive` (annuler la fermeture), `org.view_restrictions`, `offer.view_internal`, `stats.view` | `DENY_OBJECT_STATE` |
| `ARCHIVED` | `org.leave`, `org.view_restrictions` | `DENY_OBJECT_STATE` |
| `ERASED` | aucune (plus aucune appartenance) | `DENY_RELATION` |

**Règle unique (`capabilities.organization_gate(capability, lifecycle_status, measures) -> code de refus | None`)**, appelée par `acting.authorize_on`, `acting.resolve_acting_context`, `organizations._authorize_member`, `acting.get_contexts_for_user` et `get_unavailable_organizations` (capacités affichées = capacités réellement exerçables). Ordre des contrôles d'une route d'organisation (ADR 0006 §6.2 et contrat L1-01 §0 amendés) : non-membre (`DENY_RELATION`) ; suspension totale (`DENY_SECURITY`, sauf capacités permises) ; cycle de vie (`DENY_OBJECT_STATE`, sauf capacités permises) ; état du compte (`DENY_SECURITY`, sauf `org.leave`) ; capacité du rôle (`DENY_PERMISSION`) ; périmètre (`DENY_PERMISSION`) ; **restriction ciblée (`DENY_RESTRICTION`)**. La restriction ciblée vient **après** le rôle : un membre sans la capacité reçoit `DENY_PERMISSION` et n'apprend rien de la restriction.

### 4.3 `RestrictionCategory` (nouveau, règle 11)

| Champ | Type | Remarques |
|---|---|---|
| `code` | `CharField(40)`, **unique** (inconditionnel) | stable, jamais réutilisé |
| `label` | `CharField(120)` | affiché aux administrateurs de l'organisation |
| `explanation` | `TextField`, 1 000 caractères au plus (validateur) | texte compréhensible par défaut (« Ce que cela veut dire ») |
| `default_required_action` | `CharField(30)` | code de 4.4 |
| `position` | `PositiveSmallIntegerField` | ordre d'affichage du back-office |
| `is_active` | `BooleanField`, défaut vrai | une catégorie retirée reste lisible sur les restrictions passées |
| `legacy_code` | `CharField(30)`, blank | correspondance des anciens `suspension_reason` (migration seulement) |

Valeurs posées par la migration (provisoires, éditables, taxonomie finale = DOC-01) : `verification_identity` « Vérification et identité » ; `security_integrity` « Sécurité et intégrité » ; `publication_content` « Publication et contenu » ; `commercial_activity` « Activités commerciales, Marketplace et services » ; `payments_financial_risk` « Paiements, transactions et risques financiers » ; `recruitment_regulated` « Recrutement, prestations et activités réglementées » ; `trust_fraud_impersonation` « Confiance, fraude, usurpation et comportement abusif » (les sept catégories de Q33) ; `governance` « Gouvernance de l'organisation » (D6 a) ; `other` « Autre motif ». Les explications sont rédigées par l'analyste fonctionnel (tâche D-L17) et saisies avant la production ; la migration pose un texte neutre. Suppression : `PROTECT` depuis les restrictions ; retrait par `is_active = False`. Édition dans l'admin Django, journalisée (`SETTINGS_CHANGED` via `record_settings_change`).

### 4.4 `OrganizationRestriction` (nouveau)

| Champ | Type | Remarques |
|---|---|---|
| `organization` | FK `Organization`, `CASCADE`, `related_name='restrictions'` | une organisation n'est jamais supprimée physiquement (`ERASED` garde la ligne) : la cascade ne joue pas en pratique |
| `measure` | `CharField(30)`, choix 4.2 | |
| `scope_type` | `CharField(20)`, défaut `'ORGANIZATION'` | `ORGANIZATION` seul accepté en V1 ; `UNIT` réservé (branche, Q33) ; mêmes constantes que `Membership` |
| `scope_id` | `UUIDField`, nul | `CheckConstraint` `orgrestr_scope_consistent` (même forme que `membership_scope_consistent`) |
| `category` | FK `RestrictionCategory`, `PROTECT` | |
| `communicated_reason` | `CharField(500)`, blank | motif communiqué aux administrateurs ; **aucune donnée personnelle d'un tiers** (consigne du formulaire, revue `auditeur-securite`) |
| `disclosure` | `CharField(10)`, défaut `'STANDARD'` | `STANDARD`, `LIMITED` (sécurité, enquête, tiers : motif communiqué masqué, catégorie et action requise montrées, Q33) |
| `required_action` | `CharField(30)` | `NONE`, `CONTACT_SUPPORT`, `SUBMIT_DOCUMENTS`, `REGULARIZE_GOVERNANCE`, `REMOVE_CONTENT`, `UPDATE_PROFILE`, `AWAIT_REVIEW` ; **compatibilité contrôlée en service** (C1, table ci-dessous) |
| `required_action_detail` | `CharField(300)`, blank | précision facultative, mêmes consignes |
| `appeal_mode` | `CharField(20)`, défaut `'SUPPORT_REQUEST'` | `NONE`, `SUPPORT_REQUEST` (par L1-21) |
| `appeal_deadline` | `DateTimeField`, nul | |
| `status` | `CharField(10)` | `ACTIVE`, `LIFTED`, `EXPIRED` |
| `starts_at` | `DateTimeField` | « depuis » |
| `ends_at` | `DateTimeField`, nul | nul = jusqu'à levée |
| `source_type` | `CharField(20)` | `staff`, `report`, `governance`, `restoration`, `legacy_status` |
| `source_id` | `UUIDField`, nul | ex. identifiant d'un signalement `moderation.Report` ou d'une demande de restauration (UUID, sans clé étrangère) |
| `internal_note` | `TextField`, 2 000 caractères au plus | **personnel seulement** : jamais dans une réponse d'API, l'audit, l'outbox, une notification ni un journal applicatif (test à sentinelle) |
| `imposed_by` | FK `User`, `SET_NULL`, nul, `related_name='+'` | nul = système |
| `lifted_by` | FK `User`, `SET_NULL`, nul, `related_name='+'` | |
| `lifted_at` | `DateTimeField`, nul | |
| `lift_reason` | `CharField(30)`, blank | `resolved`, `appeal_upheld`, `issued_in_error`, `superseded`, `governance_restored`, `reverification_done`, `expired`, `other` |

**Compatibilité mesure × action requise (C1).** Une action requise n'est acceptée que si la capacité qu'elle suppose reste exerçable sous la mesure (et sous toute autre restriction effective de l'organisation au moment de la pose ou de la modification) ; sinon erreur de champ `400 {"required_action": ["Action impossible sous cette mesure."]}` (code `required_action_incompatible`). La catégorie ne peut pas proposer par défaut une action incompatible : le formulaire retombe sur `CONTACT_SUPPORT`.

| Action requise | Capacité supposée | Incompatible avec |
|---|---|---|
| `SUBMIT_DOCUMENTS` | `org.verification_submit` | `FULL_SUSPENSION` |
| `REMOVE_CONTENT` | `offer.delete` | `FULL_SUSPENSION` |
| `UPDATE_PROFILE` | `org.edit_profile` | `FULL_SUSPENSION`, `PROFILE_EDIT_BLOCK` |
| `NONE`, `CONTACT_SUPPORT`, `AWAIT_REVIEW`, `REGULARIZE_GOVERNANCE` | aucune | aucune |

Une suspension totale posée en attendant des pièces porte donc `CONTACT_SUPPORT` ou `AWAIT_REVIEW` ; ouvrir `org.verification_submit` sous suspension reste une option à étudier avec l'auditeur (spec A-L17 C1 b), hors V1.

Index : `orgrestr_org_status (organization, status)`, `orgrestr_status_ends (status, ends_at)`. Restriction **effective** = `status = ACTIVE` et `starts_at <= now` et (`ends_at` nul ou `> now`). Une restriction n'est jamais supprimée par l'application (historique ; conservation : L1-24).

### 4.5 `OrganizationLifecycleTransition` (nouveau, append-only)

`organization` FK `CASCADE` ; `from_status`, `to_status` `CharField(12)` ; `reason` `CharField(30)` (codes de 4.1) ; `actor` FK `User` `SET_NULL` nul (nul = système) ; `request_id` `UUIDField` nul (demande de restauration ou de fermeture) ; `created_at` (hérité). Index `orglc_org_created (organization, created_at)`. Aucune mise à jour ni suppression par l'application (admin en lecture seule). Sert l'historique interne de Q34 (« dates, motifs, demandeur, contrôles, décideur, résultat ») avec la demande de restauration ; survit à la purge éventuelle de l'`AuditLog`.

### 4.6 `OrganizationRestorationRequest` (nouveau, tâche L1-17-B4)

| Champ | Type | Remarques |
|---|---|---|
| `organization` | FK `Organization`, `CASCADE` | |
| `requester` | FK `User`, `SET_NULL`, nul | la personne qui demande (membre, ancien membre, représentant) |
| `channel` | `CharField(20)`, défaut `'SUPPORT'` | `SUPPORT` ; `IN_APP` réservé (2.6) |
| `support_case_ref` | `CharField(64)`, blank | référence opaque du dossier d'aide (L1-21) |
| `ground` | `CharField(30)` | `archiving_error`, `technical_error`, `closure_without_authority`, `legitimate_contest`, `other` (Q34) |
| `archived_reason` | `CharField(30)` | instantané de `lifecycle_reason` au moment de la demande |
| `status` | `CharField(20)` | `OPEN`, `READY_FOR_DECISION`, `COMPLETED`, `REJECTED`, `CANCELLED`, `VOID` |
| `check_data_available`, `check_organization_identity`, `check_representative_authority`, `check_restrictions_reviewed` | `BooleanField`, défaut faux | contrôles de Q34 ; les quatre vrais pour passer en `READY_FOR_DECISION` |
| `reverification_required` | `BooleanField`, défaut vrai | D6 b ; décoché seulement avec un motif de décision |
| `recorded_by`, `prepared_by`, `decided_by` | FK `User`, `SET_NULL`, nul | trois rôles du personnel ; `prepared_by != decided_by` (en service) |
| `prepared_at`, `decided_at` | `DateTimeField`, nul | |
| `decision_reason` | `CharField(30)`, blank | `restored`, `authority_not_established`, `data_unavailable`, `restriction_prevents`, `new_entity_required`, `other` |
| `internal_note` | `TextField`, 2 000 caractères au plus | personnel seulement (mêmes règles que 4.4) |

Index : `orgrest_org_status (organization, status)`, `orgrest_status_created (status, created_at)`. Invariant (service, sous verrou) : au plus une demande ouverte (`OPEN` ou `READY_FOR_DECISION`) par organisation. Permissions : `prepare_organizationrestorationrequest`, `decide_organizationrestorationrequest`.

### 4.7 Changement de nom (nouveaux, tâche L1-20-B5)

**`OrganizationNameChangeRequest`**

| Champ | Type | Remarques |
|---|---|---|
| `organization` | FK `Organization`, `CASCADE` | |
| `requested_by` | FK `User`, `SET_NULL`, nul | |
| `change_type` | `CharField(30)` | `TYPO_CORRECTION`, `DISPLAY_NAME_CHANGE`, `LEGAL_NAME_CHANGE` |
| `current_display_name`, `current_legal_name` | `CharField(255)` (blank pour le légal) | instantanés à la création |
| `proposed_display_name`, `proposed_legal_name` | `CharField(255)`, blank | au moins un renseigné et différent de l'actuel ; même normalisation que `name` (NFKC, homoglyphes, `invalid_name`) |
| `reason_code` | `CharField(30)` | `typo`, `rebranding`, `legal_rename`, `legal_form_change`, `other` |
| `requester_note` | `CharField(500)`, blank | visible du personnel et des administrateurs de l'organisation |
| `status` | `CharField(20)` | `DOCUMENTS_REQUIRED`, `PENDING_REVIEW`, `COMPLETED`, `REJECTED`, `CANCELLED`, `VOID` |
| `reviewed_by` | FK `User`, `SET_NULL`, nul | équipe Vérification |
| `decision_reason` | `CharField(30)`, blank | `approved`, `documents_insufficient`, `authority_not_established`, `new_entity_required`, `protected_name_conflict`, `other` |
| `decided_at`, `applied_at` | `DateTimeField`, nul | |
| `void_reason` | `CharField(30)`, blank | `organization_unavailable`, `name_changed_meanwhile`, `superseded` |

Index : `orgname_org_status (organization, status)`, `orgname_status_created (status, created_at)`. Invariant : au plus une demande ouverte (`DOCUMENTS_REQUIRED`, `PENDING_REVIEW`) par organisation. Permission : `review_organizationnamechangerequest` (groupe « Vérification »).

**`OrganizationNameHistory`** (append-only) : `organization` FK ; `old_display_name`, `new_display_name`, `old_legal_name`, `new_legal_name` `CharField(255)` blank ; `change_type` `CharField(30)` (les trois types + `FREE_EDIT` pour une modification ordinaire d'une organisation non verrouillée) ; `request` FK `OrganizationNameChangeRequest` `SET_NULL` nul ; `applied_by` FK `User` `SET_NULL` nul. Index `orgnamehist_org (organization, created_at)`. Toute modification de `name` ou `legal_name`, verrouillée ou non, écrit une ligne (anti-usurpation, Q1).

**`KycDocument`** : ajout `name_change_request` FK `OrganizationNameChangeRequest`, `SET_NULL`, nul ; nouveau type `NAME_CHANGE_PROOF` (« Justificatif de changement de nom ») ajouté aux choix (aucune longueur changée). **Règle de badge :** `get_verified_claims` ignore toute pièce rattachée à une demande qui n'est pas `COMPLETED` (le nouveau nom n'hérite de rien, et un justificatif validé ne crée pas de badge pour un nom qui n'est pas encore affiché). Après `COMPLETED`, une pièce `RCCM` ou `ARRETE_ONG` validée compte normalement.

### 4.8 `IdentitySettings` (règle 11)

| Champ | Type | Défaut | Bornes | Remarques |
|---|---|---|---|---|
| `dormancy_after_days` | PositiveSmallInteger | **0** (désactivé) | 0 ou 30 à 3 650 | QO-8 : valeur à fixer par le client |
| `closure_delay_days` | PositiveSmallInteger | **0** | 0 à 90 | 0 = comportement actuel (QL-2) ; exposé par `GET organizations/limits/` (C3) |
| `orphan_restrict_after_days` | PositiveSmallInteger | **0** (désactivé) | 0 ou 1 à 3 650 | QO-8 |
| `orphan_archive_after_days` | PositiveSmallInteger | **0** (désactivé) | 0 ou 1 à 3 650 ; strictement supérieur au précédent si les deux sont non nuls (validation du modèle) | QO-8 |
| `restoration_request_ttl_days` | PositiveSmallInteger | 30 (provisoire) | 7 à 365 | une demande ouverte au-delà passe `VOID` (`expired`) |
| `display_name_change_requires_document` | Boolean | vrai | — | `LEGAL_NAME_CHANGE` exige toujours au moins une pièce validée ; `TYPO_CORRECTION` jamais |

Toutes les durées sont **provisoires** et désactivées par défaut quand le client ne les a pas fixées ; aucune n'est communiquée comme une règle aux utilisateurs (seules des dates d'échéance le sont). Modifications journalisées (`SETTINGS_CHANGED`).

## 5. Machines d'états

### 5.1 Cycle de vie

```
ACTIVE  --cron : aucune activité depuis dormancy_after_days (> 0)----------------> DORMANT   (système, dormancy)
DORMANT --resume (org.confirm_activity) | cron : activité postérieure à l'entrée------> ACTIVE    (resumed | activity_detected)
ACTIVE|DORMANT --closure (Administrateur principal effectif, ressaisie)------------> CLOSING   (member_closure)
CLOSING --cancel (Administrateur principal effectif)------------------------------> ACTIVE    (closure_cancelled)
CLOSING --délai écoulé ET aucune obligation (immédiat si délai 0 ; sinon cron)------> ARCHIVED  (member_closure)
ACTIVE|DORMANT --cron : MISSING depuis orphan_archive_after_days (> 0)--------------> ARCHIVED  (système, orphaned)
ACTIVE|DORMANT|CLOSING --personnel (archive_organization_staff, motif)-------------> ARCHIVED  (staff_decision)
ARCHIVED --restauration approuvée (double contrôle)---------------------------------> ACTIVE    (restored)
ARCHIVED --effacement (L1-24 : rétention écoulée, aucun gel, aucune restriction active)--> ERASED (terminal)
```

Transitions refusées : toute autre (`409 invalid_lifecycle_transition` côté service ; côté membre, l'état bloque d'abord par `DENY_OBJECT_STATE`). Chaque transition, dans la transaction qui la provoque et sous verrou d'organisation : écriture de `lifecycle_status`, `lifecycle_changed_at`, `lifecycle_reason` ; ligne `OrganizationLifecycleTransition` ; `AuditLog` ; événement `identity.organization_lifecycle_changed` ; et, si la visibilité publique peut changer, `identity.seller_context_status_changed` (`deliver_now`, ADR 0006 §19.3 n°3).

Effets annexes : entrée en `CLOSING` ou `ARCHIVED` : invitations `PENDING` de l'organisation inacceptables (déjà le cas), nominations ouvertes `VOID` (`organization_unavailable`), demande de changement de nom ouverte `VOID` ; sortie d'`ARCHIVED` par restauration : rien n'est réouvert automatiquement.

### 5.2 Restriction

```
(pose par le personnel ou le système) -> ACTIVE
ACTIVE --levée (personnel, ou système pour les origines governance)--> LIFTED (lift_reason)
ACTIVE --ends_at atteint (cron ; présentée EXPIRED en lecture dès l'échéance)--> EXPIRED
ACTIVE --modification du texte communiqué, de l'action requise, du recours ou de l'échéance (personnel)--> ACTIVE (audit ORG_RESTRICTION_UPDATED)
LIFTED, EXPIRED : terminaux (une nouvelle mesure = une nouvelle ligne)
```

La mesure, la catégorie et le périmètre d'une restriction ne changent jamais : on lève et on repose (l'historique reste lisible). Chaque pose, levée, expiration ou modification recalcule le résumé dénormalisé de l'organisation dans la même transaction.

### 5.3 Demande de restauration

```
(enregistrement par le personnel, recorded_by) -> OPEN
OPEN --contrôles cochés (prepared_by, permission prepare)--> READY_FOR_DECISION
READY_FOR_DECISION --approve (decided_by != prepared_by, permission decide, revalidation complète)--> COMPLETED  (organisation ARCHIVED -> ACTIVE)
OPEN|READY_FOR_DECISION --reject (decide)--> REJECTED
OPEN|READY_FOR_DECISION --cancel (personnel, demande retirée)--> CANCELLED
OPEN|READY_FOR_DECISION --organisation plus ARCHIVED, ou TTL dépassé (cron)--> VOID
```

### 5.4 Demande de changement de nom

```
(création, ressaisie) -> TYPO_CORRECTION : PENDING_REVIEW ; sinon DOCUMENTS_REQUIRED (ou PENDING_REVIEW si aucune pièce n'est exigée)
DOCUMENTS_REQUIRED --première pièce déposée et rattachée--> PENDING_REVIEW
PENDING_REVIEW --documents_required (Vérification)--> DOCUMENTS_REQUIRED
PENDING_REVIEW --approve (Vérification ; pour LEGAL_NAME_CHANGE au moins une pièce rattachée VALIDE)--> COMPLETED (nom appliqué, historique)
PENDING_REVIEW|DOCUMENTS_REQUIRED --reject (Vérification, decision_reason)--> REJECTED
PENDING_REVIEW|DOCUMENTS_REQUIRED --cancel (demandeur ou Administrateur principal effectif)--> CANCELLED
* ouvert --organisation CLOSING ou ARCHIVED, ou nom modifié par une autre voie--> VOID
```

## 6. Services

Fichiers : `identity/lifecycle.py` (cycle de vie), `identity/restrictions.py` (restrictions), `identity/restoration.py`, `identity/name_changes.py`, ré-exportés par `identity/services.py` (les autres domaines n'importent jamais ces sous-modules). Règles communes (ADR 0008 §5, ADR 0010 §6) : `transaction.atomic()` ; ressaisie du mot de passe **avant** le verrou ; `_lock_organization` en premier ; autorisation recalculée sous verrou ; audit synchrone ; événement outbox dans la même transaction ; ordre de verrouillage unique : organisation, puis demande (restauration, nom, nomination, invitation), puis restrictions, puis appartenances, puis comptes. Aucun service ne reçoit de plan ni de prix.

### 6.1 Lectures partagées (appelées par `acting`, `sellers`, `organization_reads`, `organizations`, `invitations`, `governance`)

- `_membership_state(user_id, org_id)` renvoie en plus `organization__lifecycle_status` et `organization__active_restriction_measures` (même requête, même jointure).
- `capabilities.organization_gate(...)` (4.2) remplace `_check_organization_status` et `_ensure_organization_usable` ; `allow_inactive` et `allow_archived` disparaissent au profit des tables de capacités permises.
- `is_organization_operational(org)` : `lifecycle_status in (ACTIVE, DORMANT)` et pas de `FULL_SUSPENSION` (remplace « `status == ACTIVE` » dans les invitations, nominations, création d'appartenance).
- `get_seller_context_public_flags` (ORGANIZATION) : `lifecycle_status in (ACTIVE, DORMANT)` **et** `public_visibility_blocked = False` **et** propriétaire effectif **et** `creation_review_status != PENDING` (ADR 0010).
- Annuaire `GET organizations/` : `lifecycle_status = ACTIVE` (les dormantes en sortent, D8) **et** `public_visibility_blocked = False` et les conditions existantes.
- `ensure_seller_context_accepts_contact(type, id, kind)` : `FULL_SUSPENSION` -> `DENY_SECURITY` (inchangé) ; `CLOSING`, `ARCHIVED`, `ERASED` -> `DENY_OBJECT_STATE` ; `CONTACT_BLOCK` (contact, révélation, échange) ou `MESSAGING_BLOCK` (nouvelle conversation, nouveau message d'acheteur dans une conversation existante) -> `403 seller_contact_unavailable` (neutre ; jamais `DENY_RESTRICTION` ni `measure` pour un non-membre, C2, C5). `kind` est un paramètre additif (`contact`, `reveal`, `exchange`, `message`), défaut `contact`.
- `get_allowed_channels` d'une organisation : vide si `CONTACT_BLOCK`.
- `acts_for_context` : « organisation non suspendue » devient « sans `FULL_SUSPENSION` » (sens inchangé).
- `count_active_memberships` (plafond technique, ADR 0010) : appartenances actives d'organisations `lifecycle_status in (ACTIVE, DORMANT, CLOSING)` (une suspension ne libère plus de place : ce n'est pas une sortie).
- `get_restriction_summary(org)` -> `{suspended: bool, measures: [...]}` (lu dans le résumé dénormalisé, sans requête).

### 6.2 Restrictions (`identity/restrictions.py`)

- `impose_restriction(actor, org_id, measure, category_code, communicated_reason='', disclosure='STANDARD', required_action=None, required_action_detail='', appeal_mode='SUPPORT_REQUEST', appeal_deadline=None, ends_at=None, source_type='staff', source_id=None, internal_note='')` : permission `identity.impose_organizationrestriction` ; **conflit d'intérêts** : refus (`403 interest_conflict`, trace `ORG_RESTRICTION_DENIED` écrite hors transaction comme aujourd'hui) si l'acteur est ou a été membre, ou est créateur ; mesure, catégorie active, action requise, recours validés (erreurs de champ) ; périmètre `ORGANIZATION` seul ; organisation non `ERASED` ; création ; `_refresh_restriction_summary` ; audit `ORG_RESTRICTION_IMPOSED` ; événement `identity.organization_restriction_changed` (`imposed`) ; si la visibilité publique change : `seller_context_status_changed` (`suspended` pour `FULL_SUSPENSION`, compatibilité des abonnés et des textes ; `restricted` sinon).
- `impose_system_restriction(org, measure, category_code, source_type, source_id)` : interne, `source_type in ('governance', 'restoration')` seulement (sinon `ValueError` : D6) ; acteur nul ; idempotente (pas de seconde ligne active de même mesure et même origine pour la même source).
- `lift_restriction(actor, restriction_id, lift_reason)` : permission `identity.lift_organizationrestriction` ; même conflit d'intérêts ; `ACTIVE -> LIFTED` (mise à jour conditionnelle) ; résumé ; audit `ORG_RESTRICTION_LIFTED` ; événements (`lifted` ; visibilité `reactivated` si la dernière `FULL_SUSPENSION` tombe, `restriction_lifted` sinon).
- `lift_system_restrictions(org, source_type, lift_reason)` : interne (gouvernance rétablie, revérification faite).
- `update_restriction_disclosure(actor, restriction_id, **fields)` : texte communiqué, divulgation, action requise (compatibilité C1 revérifiée), recours, échéance ; jamais mesure, catégorie, périmètre ; événement `identity.organization_restriction_changed` (`updated`, notifié, QU-2) ; audit `ORG_RESTRICTION_UPDATED` (noms de champs seulement).
- `list_restrictions_for_members(actor, org_id, include_history=False)` : `org.view_restrictions` ; lecture permise sous `FULL_SUSPENSION`, `CLOSING`, `ARCHIVED` (4.2).
- `expire_organization_restrictions(now)` et `sync_restriction_summaries()` : cron (6.5).
- `_refresh_restriction_summary(org)` : relit les restrictions effectives de l'organisation (une requête), écrit `active_restriction_measures` et `public_visibility_blocked` si différents.

### 6.3 Cycle de vie (`identity/lifecycle.py`)

- `request_closure(actor, org_id, reason_code, confirm, password)` : ressaisie (action d'audit `close_organization`, limiteur `org_reauth`) ; sous verrou : Administrateur principal **effectif** avec `org.archive` (permise sous `FULL_SUSPENSION`, QL-3) ; `lifecycle_status in (ACTIVE, DORMANT)` sinon `409 closure_already_requested` (`CLOSING`) ; transition `CLOSING`, `closure_effective_at = now + closure_delay_days` ; puis `_try_finalize_closure` dans la même transaction. Notifications : tous les membres actifs et tous les Administrateurs principaux.
- `cancel_closure(actor, org_id)` : Administrateur principal effectif ; `CLOSING -> ACTIVE` ; `409 closure_not_pending` sinon.
- `_try_finalize_closure(org)` : si `now >= closure_effective_at` et `open_obligations(org) == []` -> `ARCHIVED` ; sinon reste `CLOSING` et renvoie les codes d'obligation (sans détail).
- `resume_organization(actor, org_id)` : `org.confirm_activity` (non bloquée par `PROFILE_EDIT_BLOCK`, QD-2) ; `DORMANT -> ACTIVE` (`resumed`), `last_activity_at = now` ; `409 organization_not_dormant` sinon.
- `archive_by_staff(staff, org_id, reason_code)` : permission `identity.archive_organization_staff` ; conflit d'intérêts ; depuis `ACTIVE`, `DORMANT`, `CLOSING` ; motif codé (`duplicate`, `fraud_confirmed`, `legal_decision`, `orphaned_unresolved`, `other`).
- `process_organization_lifecycle(now)` (cron horaire, idempotent, par lots de 500) : (1) finalisation des `CLOSING` échues ; (2) calcul de `last_activity_at` (6.5) puis dormance et sortie de dormance ; (3) organisations `MISSING` : restriction système puis archivage système selon les délais (lit `primary_admin_state`, `primary_admin_missing_since` de l'ADR 0010 ; une organisation suspendue et orpheline suit la même règle) ; levée des restrictions `governance` des organisations revenues à `OK` ; (4) demandes de restauration échues -> `VOID`. Un délai à 0 désactive l'étape correspondante.

### 6.4 Obligations ouvertes (registre, sans import direct)

`IDENTITY_CLOSURE_OBLIGATION_PROVIDERS` (réglage Django, liste de chemins de modules ; même patron que `moderation.TARGET_RESOLVERS`) : chaque module listé expose `open_closure_obligations(context_type, context_id) -> list[str]` (codes, ex. `payments_open`, `refunds_open`, `tickets_sold`, `subscriptions_active`). **V1 : liste vide** (L1-11/L1-12 et le lot 2 l'enrichiront ; ADR 0009 : `payments`). Un module en erreur compte comme obligation ouverte `provider_unavailable` (échec fermé : la fermeture attend, elle ne perd pas d'obligation). Aucune transaction inter-domaines : lecture seule, revérifiée par le cron.

### 6.5 Activité (dormance)

`last_activity_at` = maximum de : `Organization.updated_at` ; dernière transition de cycle de vie ; dernier changement d'appartenance (`Membership.joined_at`, `ended_at`) ; dernière connexion d'un Administrateur principal ou administrateur actif (`User.last_login`, **à condition** que la connexion JWT le mette à jour : `SIMPLE_JWT['UPDATE_LAST_LOGIN']` à vérifier et activer dans la tâche B3, sinon ce signal est omis et documenté) ; dernière activité d'offre du contexte (`marketplace.services.last_offer_activity_by_seller_context(ids)`, nouvelle lecture par lot, publique dans la façade `marketplace.services`). Calcul par lots dans le cron seulement ; aucune écriture sur une requête utilisateur.

### 6.6 Restauration (`identity/restoration.py`)

- `record_restoration_request(staff, org_id, requester_id, ground, support_case_ref='', internal_note='')` : permission `prepare_organizationrestorationrequest` ; organisation `ARCHIVED` (sinon `409 restoration_not_applicable` ; `ERASED` : `409 restoration_impossible`) ; invariant une demande ouverte ; `archived_reason` instantané ; audit `ORG_RESTORATION_REQUESTED`.
- `complete_restoration_checks(staff, request_id, checks, reverification_required)` : même permission ; conflit d'intérêts (ni membre, ni ancien membre, ni créateur, ni demandeur) ; les quatre contrôles vrais -> `READY_FOR_DECISION` ; `prepared_by`.
- `decide_restoration(staff, request_id, decision, decision_reason)` : permission `decide_organizationrestorationrequest` ; `staff != prepared_by` et `staff != recorded_by` (`403 four_eyes_required`) ; conflit d'intérêts ; **revalidation complète** sous verrou (organisation toujours `ARCHIVED`, contrôles toujours vrais) ; `APPROVE` : transition `ARCHIVED -> ACTIVE` (`restored`, `request_id`), si `reverification_required` : `impose_system_restriction(PUBLIC_VISIBILITY_HIDDEN, verification_identity, 'restoration', request.id)` et remise à non vérifié du numéro de contact de l'organisation (`ContactPoint.is_verified = False`, l'organisation refait l'OTP) ; `_refresh_primary_admin_state` (ADR 0010 ; si `MISSING`, la régularisation passe par L1-02f) ; les restrictions existantes restent ; audit `ORG_RESTORED` ; événements. `REJECT` : `REJECTED`, notification neutre au demandeur s'il a un compte.

### 6.7 Changement de nom (`identity/name_changes.py`)

- `update_organization` (amendé) : accepte `legal_name` ; verrou étendu aux deux champs (`409 name_locked_by_verification`, message : « Le nom est verrouillé depuis la vérification. Faites une demande de modification du nom. ») ; chaque changement non verrouillé écrit `OrganizationNameHistory(FREE_EDIT)`.
- `create_name_change_request(actor, org_id, change_type, proposed_display_name, proposed_legal_name, reason_code, note, confirm, password)` : ressaisie (`request_name_change`) ; sous verrou : `org.request_name_change` (permise sous `PROFILE_EDIT_BLOCK`) ; organisation opérationnelle ; nom verrouillé (sinon `409 name_change_not_required` : utiliser `PATCH`) ; validations de nom ; invariant (`409 name_change_already_open`) ; instantanés ; statut initial (5.4) ; audit ; événement `requested`. Interface L1-02g : si le nom proposé touche un nom protégé, la demande porte un signal de revue renforcée (ajout de L1-02g).
- `attach_name_change_document` : le dépôt `POST organizations/<id>/kyc/documents/` reçoit `name_change_request_id` (additif) ; types permis : `NAME_CHANGE_PROOF`, `RCCM`, `ARRETE_ONG` ; passage `DOCUMENTS_REQUIRED -> PENDING_REVIEW`.
- `cancel_name_change_request(actor, ...)` ; `review_name_change_request(staff, request_id, decision, decision_reason)` : permission `review_organizationnamechangerequest` ; conflit d'intérêts identique à la décision KYB (ADR 0006 §18 n°3) ; `APPROVE` exige pour `LEGAL_NAME_CHANGE` une pièce rattachée `VALIDE` ; revalidation (nom courant égal à l'instantané, sinon `VOID name_changed_meanwhile`) ; application des noms, `OrganizationNameHistory`, audit `ORG_NAME_CHANGED`, événements `identity.organization_updated` (`fields`) et `name_change_changed` (`completed`).

## 7. Événements de domaine (outbox, ADR 0003)

| Type | Version | Charge utile (UUID et codes seulement) | Abonnés |
|---|---|---|---|
| `identity.organization_lifecycle_changed` (**nouveau**) | 1 | `organization_id`, `from_status`, `to_status`, `reason`, `actor_id` (nul = système), `request_id`, `closure_effective_at` | `notifications.notify_organization_lifecycle` (nouveau) ; plus tard `payments`, `events` (fermeture) |
| `identity.organization_restriction_changed` (**nouveau**) | 1 | `organization_id`, `restriction_id`, `measure`, `change` (`imposed`, `lifted`, `expired`, `updated`), `category_code`, `actor_id` | `notifications.notify_organization_restriction` (nouveau) |
| `identity.seller_context_status_changed` (existant) | 1 | **valeurs additives** de `reason` : `closing`, `restored`, `restricted`, `restriction_lifted`, `dormant`, `resumed` ; `suspended` et `reactivated` gardent leur sens (pose et levée de la dernière `FULL_SUSPENSION`) ; `archived` inchangé | `marketplace.sync_seller_visibility` (recalcule, ignore la raison) : aucun changement ; `notifications.notify_organization_status` : ignore les nouvelles raisons (les notifications viennent des deux nouveaux types) |
| `identity.organization_restoration_changed` (**nouveau**) | 1 | `organization_id`, `request_id`, `change` (`recorded`, `ready`, `completed`, `rejected`, `cancelled`, `voided`), `requester_id` | `notifications.notify_restoration_outcome` (`completed`, `rejected` seulement) |
| `identity.organization_name_change_changed` (**nouveau**) | 1 | `organization_id`, `request_id`, `change_type`, `change` (`requested`, `documents_required`, `ready`, `completed`, `rejected`, `cancelled`, `voided`), `actor_id` | `notifications.notify_name_change` |
| `identity.organization_updated` (existant) | 1 | `fields` peut contenir `legal_name` | sans abonné (inchangé) |

Déclarations dans `platform_core/catalog.py` (contrôle `platform_core.E001`). **Jamais dans une charge utile :** motif communiqué, note interne, détail d'action requise, nom de l'organisation, ancien ou nouveau nom, nom de personne, téléphone, e-mail.

**Notifications (textes neutres, liens vers `/organizations/<uuid>`) :**

| Événement | Destinataires | Texte |
|---|---|---|
| restriction `imposed`, `FULL_SUSPENSION` | tous les membres actifs (hors acteur) | texte existant « L'organisation « {name} » a été suspendue : ses offres ne sont plus publiques. » ; pour `OWNER`, `ADMIN` en plus : « Consultez le détail et l'action requise. » (lien `/organizations/<id>/restrictions`) |
| restriction ciblée `imposed` | `OWNER`, `ADMIN` | « Une restriction s'applique à « {name} ». Consultez le détail et l'action requise. » |
| restriction `updated` (QU-2) | `OWNER`, `ADMIN` | « La restriction appliquée à « {name} » a été mise à jour. Consultez le détail. » |
| restriction `lifted`, `expired` | mêmes destinataires que la pose | « La restriction appliquée à « {name} » a été levée. » / texte existant « réactivée » pour la dernière suspension |
| cycle de vie `CLOSING` | tous les membres actifs | « La fermeture de « {name} » a été demandée. Elle prendra effet au plus tôt le {date}. » |
| `CLOSING -> ACTIVE` | tous les membres actifs | « La fermeture de « {name} » a été annulée. » |
| `-> ARCHIVED` | tous les membres actifs | texte existant « archivée » ; raison `orphaned` : « « {name} » a été archivée faute d'administrateur principal. Une restauration peut être demandée à l'aide Connecte+. » |
| `-> DORMANT` | `OWNER`, `ADMIN` | « « {name} » est considérée comme inactive. Confirmez qu'elle est toujours en activité. » |
| restauration `completed` | membres actifs, demandeur | « « {name} » a été restaurée. » (+ si revérification : « Elle redeviendra publique après vérification. ») |
| restauration `rejected` | demandeur | « Votre demande de restauration de « {name} » n'a pas été acceptée. » |
| nom `documents_required`, `completed`, `rejected` | demandeur, `OWNER`, `ADMIN` | textes par `change` |

## 8. Journal d'audit (règle 12)

`details` au format `clé=valeur; …`, UUID et codes seulement ; jamais de motif communiqué, de note interne, de nom d'organisation, d'ancien ni de nouveau nom (les noms sont dans `OrganizationNameHistory`, d'accès restreint). `AuditLog.action` est un champ libre : aucune migration `moderation`.

| Action | Acteur | Cible | `details` |
|---|---|---|---|
| `ORG_RESTRICTION_IMPOSED` | personnel ou nul | restriction | `organization; measure; category; disclosure; source=; ends_at=` |
| `ORG_RESTRICTION_UPDATED` | personnel | restriction | `organization; fields=` |
| `ORG_RESTRICTION_LIFTED` / `_EXPIRED` | personnel, nul | restriction | `organization; measure; reason=` |
| `ORG_RESTRICTION_DENIED` | personnel | organisation | `reason=interest_conflict; operation=impose\|lift` (remplace `ORG_REACTIVATION_DENIED`) |
| `ORG_CLOSURE_REQUESTED`, `ORG_CLOSURE_CANCELLED` | Administrateur principal | organisation | `reason=; effective_at=; reauth=true` |
| `ORG_ARCHIVED` (existant) | acteur ou nul | organisation | + `reason=member_closure\|orphaned\|staff_decision; obligations=none` |
| `ORG_DORMANT`, `ORG_RESUMED` | nul / membre | organisation | `last_activity=<date>` / — |
| `ORG_RESTORATION_REQUESTED`, `_CHECKS_COMPLETED`, `_REJECTED`, `_CANCELLED`, `_VOIDED` | personnel | demande | `organization; ground; reverification_required` |
| `ORG_RESTORED` | décideur | organisation | `request; prepared_by; reverification_required; restrictions_active=<n>` |
| `ORG_NAME_CHANGE_REQUESTED`, `_CANCELLED`, `_REVIEWED`, `_VOIDED` | membre, personnel | demande | `organization; change_type; decision=; reason=` |
| `ORG_NAME_CHANGED` | décideur ou membre (`FREE_EDIT`) | organisation | `change_type; request=` |
| `ORG_SENSITIVE_REAUTH_FAILED` (existant) | | | nouvelles valeurs `action=close_organization\|request_name_change` |
| `ORG_UPDATED` (existant) | | | `fields` peut contenir `legal_name` |

Les actions `ORG_SUSPENDED`, `ORG_REACTIVATED`, `ORG_REACTIVATION_DENIED` ne sont plus écrites ; les lignes historiques restent lisibles.

## 9. Permissions, ressaisie, throttles, back-office

| Opération | Qui | Règles |
|---|---|---|
| Lire les restrictions (détail) | `org.view_restrictions` (Administrateur principal, Administrateur) | permise sous suspension, fermeture, archivage ; compte restreint : `DENY_SECURITY` |
| Demander la fermeture, annuler | Administrateur principal effectif (`org.archive`) | fermeture : ressaisie |
| Confirmer l'activité (dormante) | `org.confirm_activity` (Administrateur principal, Administrateur) | non bloquée par `PROFILE_EDIT_BLOCK` (QD-2) |
| Demander un changement de nom, annuler | `org.request_name_change` | création : ressaisie |
| Poser, modifier, lever une restriction | personnel, `impose_organizationrestriction`, `lift_organizationrestriction` | conflit d'intérêts |
| Archiver par décision du personnel | personnel, `archive_organization_staff` | conflit d'intérêts, motif codé |
| Préparer, décider une restauration | personnel, `prepare_…`, `decide_…` | double contrôle, conflit d'intérêts |
| Décider d'un changement de nom | personnel, `review_organizationnamechangerequest` | conflit d'intérêts |

`setup_roles` : groupe **« Administrateur »** : `impose_`, `lift_organizationrestriction`, `archive_organization_staff`, `decide_organizationrestorationrequest`, `view`/`add`/`change` de `restrictioncategory` ; retrait de `suspend_organization`. Groupe **« Vérification »** (ADR 0010) : `prepare_organizationrestorationrequest`, `review_organizationnamechangerequest`, `lift_organizationrestriction` limité par le service aux restrictions d'origine `restoration` et de catégorie `verification_identity` (contrôle en service, pas seulement par groupe). Groupe **« Modérateur »** : rien en V1 (QL-7, DOC-01). Un même compte du personnel ne peut pas préparer et décider la même restauration, quels que soient ses groupes.

Back-office (admin Django, pas d'écran `frontend` en V1, comme la suspension actuelle) : `OrganizationAdmin` (lecture seule, colonnes cycle de vie, « suspendue », gouvernance ; actions « Poser une restriction », « Archiver » via formulaires qui appellent les services) ; `OrganizationRestrictionAdmin` (liste filtrable, actions « Lever », « Modifier ce qui est communiqué ») ; `RestrictionCategoryAdmin` ; `OrganizationRestorationRequestAdmin` (enregistrer, préparer, décider) ; `OrganizationNameChangeRequestAdmin` (pièces, décision). Toute action passe par un service (aucune écriture directe du modèle par l'admin).

Throttles : `org_sensitive` (existant, 10/h) : `closure/` (POST), création de demande de nom ; `org_write` (existant, 30/h) : `DELETE closure/`, `resume/`, annulation de demande de nom ; `staff_review` (ADR 0010) : actions du personnel.

## 10. Migrations, données existantes, retour arrière

Une seule tâche à la fois dans `identity/migrations/` ; chaque migration appliquée sur une base SQLite vierge ; `makemigrations --check --dry-run` vert. Numérotation indicative, **après** B8 (`0020`), B9 (`0021`), B10 (`0022`).

### 10.1 Séquence

| Migration | Tâche | Contenu |
|---|---|---|
| `0023_organization_lifecycle_restrictions` | L1-17-B1 | `AddField` `lifecycle_status`, `lifecycle_changed_at`, `lifecycle_reason`, `active_restriction_measures`, `public_visibility_blocked` ; `CreateModel` `RestrictionCategory`, `OrganizationRestriction` (+ `CheckConstraint`, index), `OrganizationLifecycleTransition` ; **`RunPython` de semence** des 9 catégories (4.3, avec `legacy_code`) ; **`RunPython` de conversion** (10.2) ; permissions `impose_`, `lift_organizationrestriction`, `archive_organization_staff` |
| `0024_remove_organization_status` | L1-17-B1 | `RemoveIndex org_status_type`, `RemoveField status`, `RemoveField suspension_reason`, `AddIndex org_lifecycle_type` ; retrait de la permission `suspend_organization` (`AlterModelOptions`) |
| `0025_lifecycle_closure_dormancy` | L1-17-B3 | `closure_effective_at`, `last_activity_at`, index `org_lifecycle_activity`, `org_lifecycle_closure` ; réglages `dormancy_after_days`, `closure_delay_days`, `orphan_restrict_after_days`, `orphan_archive_after_days` |
| `0026_organization_restoration` | L1-17-B4 | `OrganizationRestorationRequest` (+ index, permissions) ; réglage `restoration_request_ttl_days` |
| `0027_organization_name_change` | L1-20-B5 | `Organization.legal_name` ; `OrganizationNameChangeRequest`, `OrganizationNameHistory` ; `KycDocument.name_change_request`, choix `NAME_CHANGE_PROOF` ; réglage `display_name_change_requires_document` ; permission |

### 10.2 Conversion du statut unique (sans perte)

`RunPython` de `0023`, idempotent, par lots de 500, modèles historiques seulement :

| Avant (`status`, `suspension_reason`) | Après |
|---|---|
| `ACTIVE` | `lifecycle_status = ACTIVE` ; aucune restriction |
| `ARCHIVED` | `lifecycle_status = ARCHIVED`, `lifecycle_reason = legacy_status`, `lifecycle_changed_at = updated_at` ; transition `ACTIVE -> ARCHIVED` (`legacy_status`, acteur nul) |
| `SUSPENDED` + motif | `lifecycle_status = ACTIVE` ; une `OrganizationRestriction(FULL_SUSPENSION)` : catégorie dont `legacy_code` = motif (`verification` -> `verification_identity` ; `moderation`, `legal`, `other`, vide -> `other`), `disclosure = LIMITED`, `communicated_reason = ''`, `required_action = CONTACT_SUPPORT`, `appeal_mode = SUPPORT_REQUEST`, `starts_at = updated_at` (meilleure approximation, documentée), `source_type = legacy_status`, `imposed_by = NULL` ; résumé dénormalisé posé |

Pourquoi `LIMITED` et `other` : une organisation convertie par T9 est suspendue à cause de la **sanction d'une autre personne** (son ancien propriétaire) ; montrer « Modération » ou un motif reviendrait à divulguer cette sanction aux administrateurs (règle 10, raisonnement S1 de la spec L0-09). Le personnel requalifie au besoin. Aucune `AuditLog` n'est écrite par la migration (aucune action humaine ; la trace est `source_type = legacy_status` et la transition).

### 10.3 Retour arrière

- `0024` inverse : recrée `status` (défaut `ACTIVE`), `suspension_reason`, l'index et la permission (schéma seulement).
- `0023` inverse : `RunPython` inverse qui **reconstruit** `status` et `suspension_reason` : `FULL_SUSPENSION` effective -> `SUSPENDED` + `legacy_code` de sa catégorie (sinon `other`) ; `lifecycle_status in (ARCHIVED)` -> `ARCHIVED` ; `ACTIVE`, `DORMANT` -> `ACTIVE`. **Garde** (échec explicite, transaction annulée, message sans donnée personnelle, comptages seulement) s'il existe : une organisation `CLOSING` ou `ERASED`, ou une restriction effective autre que `FULL_SUSPENSION` (non représentable). Puis suppression des tables et champs.
- `0025` à `0027` : retrait des champs et tables ; garde de `0027` si une pièce KYB est rattachée à une demande (le rattachement serait perdu) ; aucune donnée de production (ADR 0002).
- Répétition obligatoire dans B1 sur une copie fabriquée (au moins 200 organisations des trois statuts) : comptages identiques après conversion, après retour arrière, après re-conversion.

### 10.4 Commandes planifiées

| Commande | Fréquence | Tâche | Rôle |
|---|---|---|---|
| `sync_organization_restrictions` (**nouvelle**) | `*/10 * * * *` | L1-19-B2 (squelette en B1) | expiration des restrictions échues ; resynchronisation des résumés dénormalisés (filet) |
| `process_organization_lifecycle` (**nouvelle**) | `35 * * * *` | L1-17-B3 (+ B4 pour les demandes échues) | 6.3 |
| `sync_organization_governance` (ADR 0010) | inchangée | — | ses écarts d'état alimentent l'étape orpheline de la commande précédente |

Ajout à `backend/cron/crontab` et à `SCHEDULED_COMMANDS` du test de crontab.

## 11. Concurrence et parades (verrous effectifs sous MySQL, écritures sérialisées sous SQLite)

| Risque | Parade |
|---|---|
| Deux poses simultanées de restrictions sur la même organisation | verrou d'organisation ; résumé recalculé depuis la table (pas d'incrément) |
| Levée et expiration simultanées | mise à jour conditionnelle depuis `ACTIVE` ; un seul gagnant |
| Fermeture pendant la pose d'une suspension | même verrou ; les deux s'appliquent (axes indépendants) |
| Fermeture demandée deux fois, ou fermeture et annulation | transition conditionnelle depuis l'état attendu |
| Obligation créée entre le contrôle et l'archivage (autre domaine) | limite connue (pas de transaction inter-domaines) ; l'archivage n'efface rien ; les modules propriétaires refusent toute nouvelle obligation pour une organisation non opérationnelle (`is_organization_operational`) |
| Restauration approuvée pendant un effacement (L1-24) | verrou d'organisation ; l'effacement exige l'absence de demande ouverte |
| Deux demandes de restauration ou de changement de nom | invariant compté sous verrou d'organisation |
| Résumé périmé après échéance d'une restriction | échec fermé jusqu'au cron (10 min au plus) ; la lecture du détail présente déjà `EXPIRED` |
| Interblocage | ordre unique (section 6) |

Registre de recette MySQL : pose simultanée de deux restrictions ; fermeture et suspension simultanées ; deux décisions de restauration simultanées.

## 12. Sécurité, données personnelles, tests

- **Règle 10.** Motif communiqué et détail d'action : 500 et 300 caractères, consigne « aucune information sur une autre personne, aucun moyen d'enquête » dans le formulaire du back-office ; `disclosure = LIMITED` les masque. Note interne : jamais exposée (test à sentinelle sur toutes les réponses d'organisation, l'audit, l'outbox, les notifications). Détail des restrictions réservé à `org.view_restrictions`. `legal_name` minimisé comme le NIF.
- **Aucune fuite de la sanction d'un tiers.** Les restrictions converties de T9 sont `LIMITED` + `other` ; aucune réponse n'indique qu'un compte membre est sanctionné.
- **Oracle.** `restrictions/` d'une organisation inexistante ou d'un non-membre : `403 DENY_RELATION` (règle existante) ; `DENY_RESTRICTION` n'est renvoyé qu'à un membre qui détient la capacité refusée ; un acheteur reçoit `seller_contact_unavailable`, identique au cas « organisation sans canal » (C2, test d'égalité des corps de réponse).
- **Escalade.** Aucun membre ne lève une restriction ; aucune restriction n'est levée par un paiement, un plan ou une nomination (test d'introspection étendu à `restrictions.py`, `lifecycle.py`, `restoration.py`, `name_changes.py`) ; un changement d'Administrateur principal ne lève rien (Q17, test).
- **Double contrôle de la restauration.** `prepared_by != decided_by`, `recorded_by != decided_by`, conflit d'intérêts sur les trois.
- **Usurpation par renommage.** Verrou maintenu ; historique complet ; badges non hérités ; nouvelle entité refusée par renommage.
- **Utilitaire de test** `identity/testing.py` : `make_suspended(org, measure='FULL_SUSPENSION')`, `make_archived(org)`, `make_closing(org)`, utilisé par les 27 fichiers de tests concernés (`identity`, `marketplace`, `messaging`, `common`) ; il passe par les services (ou par un chemin interne documenté) pour garder le résumé cohérent.
- **Test de garde « lecteur oublié »** : recherche statique échouant si `Organization.STATUS_`, `organization__status` ou `suspension_reason` réapparaissent hors migrations.
- **Revues obligatoires** `auditeur-securite` : B1 (non-régression de toutes les gardes), B2 (exposition du motif, règle 10), B4 (restauration), B5 (renommage, usurpation).

## 13. Règles verrouillées (CLAUDE.md §4) vérifiées

| Règle | Verdict | Justification |
|---|---|---|
| 1. Compte unique, contextes | Respectée | Les restrictions d'une organisation ne touchent pas les contextes personnels de ses membres (Q17, test) ; nouvelle entité = nouvelle organisation, administrable par le même compte. |
| 2. Permissions ≠ droits commerciaux | Respectée | Aucun service ne reçoit de plan ; une restriction n'est levée par aucun achat ; `billing.*` refusé sous suspension, fermeture et archivage comme toute capacité non listée. |
| 3. Vérification non achetable | Respectée | Changement de nom et restauration décidés par le personnel ; pièces rattachées exclues des badges avant décision ; le nouveau nom n'hérite de rien. |
| 4. Aucun score de confiance | Respectée | Une restriction est un état factuel, jamais une note ; elle n'entre pas dans le classement (elle masque ou non) ; la dormance n'est pas un signal de qualité. |
| 8. États indépendants | Respectée | Cycle de vie, restrictions, gouvernance, revue de création, demandes : champs et objets distincts, aucun n'écrase l'autre. |
| 10. Données par finalité | Respectée | Section 12. |
| 11. Configurable | Respectée | Catégories, explications, durées en back-office ; durées désactivées tant que non fixées. |
| 12. Audit | Respectée | Section 8 ; historique de cycle de vie et de nom en tables append-only. |
| 5, 6, 7, 9 | Non touchées | La fermeture ne détient aucun fonds ; les obligations sont lues, jamais compensées. |

## 14. Impacts sur le code livré et interfaces

| Livraison | Ce qui change | Fichiers principaux |
|---|---|---|
| L0-09, T8, B-SUSP (`identity`) | `status`/`suspension_reason` remplacés ; `_check_organization_status`, `_ensure_organization_usable`, `allow_inactive`/`allow_archived` remplacés par `organization_gate` ; `suspend_organization`, `reactivate_organization` remplacés par `impose_restriction`, `lift_restriction` (le formulaire `SuspensionReasonForm` devient le formulaire de restriction) ; `archive_organization` -> `request_closure` ; `contexts/` et `unavailable` (11 clés, capacités calculées) ; `_last_owner_error` lit la suspension par le résumé | `models.py`, `acting.py`, `organizations.py`, `sellers.py`, `organization_reads.py`, `invitations.py`, `services.py`, `admin.py`, `views_organizations.py`, `urls.py`, `serializers.py`, `views_account_blockers.py`, `templates/admin/identity/suspend_reason.html` |
| T9 (`legacy_conversion.py`, `0011`) | aucune modification : la migration historique écrit encore `status` sur le modèle historique ; `0023` convertit ensuite | — |
| ADR 0010 (B8 à B10, à venir) | « organisation `ACTIVE` » devient `is_organization_operational` ; index B10 sans `status` ; nominations et invitations refusées sous `TEAM_CHANGES_BLOCK` (`DENY_RESTRICTION`) | `governance.py`, `invitations.py` |
| `notifications` | deux nouveaux abonnés, textes 7 ; `notify_organization_status` ignore les nouvelles raisons | `notifications/events.py`, `notifications/subscribers` |
| `marketplace` | nouvelle lecture `last_offer_activity_by_seller_context` (façade) ; appels d'`ensure_seller_context_accepts_contact` avec `kind` ; tests via l'utilitaire | `marketplace/services.py`, tests |
| `messaging` | appel d'`ensure_seller_context_accepts_contact(kind='message')` ; tests | `messaging/services.py`, tests |
| Front (`frontend`) | types `OrganizationStatus` -> `lifecycle_status` + `restrictions` ; `OrganizationStatusBadge`, `OrganizationUnavailableView` (CLOSING, détail des restrictions, annulation) ; bannières dormante et restriction ciblée ; `DENY_RESTRICTION` ; `archive/` -> `closure/` avec mot de passe ; demande de changement de nom ; texte de l'archivée (restauration par l'aide) | `api/types.ts`, `components/organizations/*`, `contexts/ActiveContextContext.tsx`, `hooks/use-organizations.ts`, `hooks/use-contexts.ts`, `pages/Profiles.tsx`, `lib/api-errors.ts`, `i18n/locales/fr.ts` |

**Interfaces avec les autres ADR et tâches**
- **ADR 0010** : `primary_admin_state`, `primary_admin_missing_since` lus par `process_organization_lifecycle` ; `creation_review_status` **non converti** (D11) ; QG-9 soldé (le transfert depuis une archivée reste retiré : la restauration est le chemin).
- **ADR 0012 (fermeture de compte)** : même registre d'obligations (6.4) réutilisable par contexte ; la fermeture d'un compte rend une organisation `MISSING`, qui suit l'étape orpheline.
- **ADR 0009** : `payments` s'inscrit au registre d'obligations ; un droit commercial d'une organisation `ARCHIVED` n'est ni remboursé ni prolongé par la plateforme (à préciser par L1-12) ; aucun plan ne lève une restriction (test).
- **L1-24** : transition `ARCHIVED -> ERASED` (anonymisation : nom remplacé par un libellé neutre côté lecture, logo, description, NIF, `legal_name`, contacts, invitations, nominations, appartenances retirés ; restrictions et historiques minimisés selon la politique), gel juridique, durées ; l'événement `identity.seller_context_removed` devra accepter `ORGANIZATION` **seulement** pour une organisation `ERASED`.
- **L1-21** : lien d'aide dans l'action requise `CONTACT_SUPPORT`, le recours `SUPPORT_REQUEST`, le texte de l'archivée ; `support_case_ref` des demandes de restauration ; tant que L1-21 n'existe pas, texte sans lien (comme aujourd'hui).
- **L1-02** : `PUBLIC_VISIBILITY_HIDDEN` de revérification levée par l'équipe Vérification ; L1-02c décidera de l'affichage public de `legal_name` et de « anciennement » ; L1-02e utilise `TEAM_CHANGES_BLOCK` et `PROFILE_EDIT_BLOCK` pendant un conflit d'autorité ; L1-02g signale les noms protégés dans les demandes.
- **DOC-01** : taxonomie finale des catégories, qui peut poser quelles mesures (modérateur), durées types, recours.

## 15. Conséquences

- 6 nouveaux modèles (`RestrictionCategory`, `OrganizationRestriction`, `OrganizationLifecycleTransition`, `OrganizationRestorationRequest`, `OrganizationNameChangeRequest`, `OrganizationNameHistory`), 8 champs ajoutés et 2 retirés sur `Organization`, 1 sur `KycDocument`, 6 réglages, 5 migrations `identity`, 4 nouveaux types d'événement, 4 abonnés, 2 commandes planifiées, 1 code de refus, 2 capacités, 6 permissions du personnel, 1 route retirée (`archive/`) et environ 8 routes ajoutées (contrat).
- **Risques acceptés :** `starts_at` approximé pour les suspensions converties ; écart de 10 minutes après l'échéance d'une restriction (échec fermé) ; obligation créée pendant la finalisation d'une fermeture (lecture inter-domaines non transactionnelle) ; `last_login` peut manquer comme signal d'activité ; la dormance et l'archivage d'orphelines ne s'appliquent qu'après que le client a fixé les durées.
- **Dettes :** périmètre `UNIT` des restrictions déclaré mais inactif ; demande de restauration dans l'application (2.6 B) ; nom public « en cours de vérification » (2.5 B) ; écrans du personnel hors admin Django ; recours structuré (DOC-01, L2-12).

## 16. Découpage en tâches

**Préalables :** ADR et contrat validés ; B8, B9, B10 livrés (migrations `identity` en série ; B1 réécrit les mêmes lectures de visibilité que B8 et B10). Les tâches de conception et le front démarrent sur le contrat figé, en parallèle des tâches B de L1-01.

| ID | Agent | Contenu | Dépend de | Parallélisable avec |
|---|---|---|---|---|
| **A-L17** | analyste-fonctionnel | Textes d'explication des 9 catégories, libellés des mesures et des actions requises, motifs de fermeture, de restauration et de changement de nom ; critères d'acceptation L1-17, L1-19, L1-20 ; mise à jour du CDC §3.1 (diff de l'analyse d'impact §4) | ADR | D-L17 |
| **D-L17** | designer-ux | Spécifications : écran « Restrictions » (Q33 : statut, catégorie, motif, périmètre, depuis, action requise, recours ; divulgation limitée ; rôles sans détail) ; vue indisponible étendue (suspendue, fermeture en cours avec annulation, archivée avec restauration par l'aide) ; bannières dormante et restriction ciblée ; refus `DENY_RESTRICTION` dans les formulaires (offre, équipe, profil, messages, avis) ; dialogue de fermeture (effets, motif, mot de passe, date d'effet, obligations) ; parcours « Demander une modification du nom » (type, justificatifs, état en cours, nom verrouillé) | contrat | B8 à B10, B1 |
| **L1-17-B1** | dev-backend | Fondation : modèle (4.1 à 4.5 sans 4.6, 4.7), semence, conversion, contraction ; `organization_gate` + matrice testée ; réécriture de toutes les lectures (6.1) ; pose et levée de `FULL_SUSPENSION` par le personnel (admin) ; `contexts/` et `internal/` (contrat §1) ; champ `status` dérivé ; utilitaire de test et adaptation des 27 fichiers ; test « lecteur oublié » ; migrations `0023`, `0024` avec répétition du retour arrière | B10 | D-L17, F-L17-1 (sur fixture) |
| **S-L17-1** | auditeur-securite | Revue B1 : toutes les gardes (contexte, objet, membre, visibilité, contact), aucune fuite de motif ni de sanction d'un tiers, conversion | B1 | B2 |
| **L1-19-B2** | dev-backend | Restrictions ciblées : sept mesures (effets 4.2), `DENY_RESTRICTION`, `restrictions/`, résumé par rôle, `ensure_seller_context_accepts_contact(kind)`, admin complet (poser, modifier, lever, catégories), restrictions système (interfaces pour B3, B4), `sync_organization_restrictions` + crontab, événement et notifications ; **retrait du champ `status` dérivé** une fois F-L17-1 fusionnée | B1 | F-L17-2 (contrat) |
| **S-L17-2** | auditeur-securite | Revue B2 : règle 10 (motif, note interne, divulgation limitée), oracle, escalade | B2 | B3 |
| **L1-17-B3** | dev-backend | Cycle de vie : `closure/` (POST, DELETE), registre d'obligations, finalisation, `resume/`, archivage par le personnel, dormance et activité (6.5, `UPDATE_LAST_LOGIN`), étape orpheline (restriction puis archivage), `process_organization_lifecycle` + crontab, notifications ; suppression de `archive/` ; migration `0025` | B2 | F-L17-3 (contrat) |
| **L1-17-B4** | dev-backend | Restauration : modèle, services, double contrôle, revérification (restriction système, contact), admin, expiration, notifications ; migration `0026` | B3 | F-L17-3 |
| **S-L17-3** | auditeur-securite | Revue B4 : double contrôle, conflit d'intérêts, revalidation | B4 | B5 |
| **L1-20-B5** | dev-backend | Changement de nom : `legal_name`, historique, demandes, pièces rattachées exclues des badges, revue Vérification, verrou étendu et nouveau message ; migration `0027` | B4 (migrations) | F-L17-4 (contrat) |
| **S-L17-4** | auditeur-securite | Revue B5 : usurpation, badges non hérités, ressaisie, IDOR | B5 | — |
| **F-L17-1** | dev-frontend | Types et contrat (`lifecycle_status`, `restrictions`, 11 clés de `unavailable`, capacités calculées), `DENY_RESTRICTION` dans `api-errors`, badges de statut (dormante, fermeture en cours) ; fixtures | contrat | B1 |
| **F-L17-2** | dev-frontend | Écran « Restrictions », vue indisponible avec détail pour `OWNER`/`ADMIN`, bannières et refus de restriction ciblée | D-L17, F-L17-1 | B2 |
| **F-L17-3** | dev-frontend | Dialogue de fermeture (`closure/`), état « fermeture en cours » et annulation, bannière dormante et `resume/`, texte de l'archivée | D-L17, F-L17-1 | B3, B4 |
| **F-L17-4** | dev-frontend | Demande de modification du nom (formulaire, pièces, suivi, annulation), `legal_name` dans le formulaire de profil, message du nom verrouillé | D-L17, F-L17-1 | B5 |
| **R** | relecteur-code | Après chaque tâche B et F | tâche | — |
| **Q-L17** | qa-testeur | Recette : conversion et retour arrière ; organisation suspendue + archivée + orpheline ; chaque mesure ciblée de bout en bout ; fermeture avec et sans délai, annulation ; dormance (délai court en test) ; orpheline restreinte puis archivée ; restauration (double contrôle, revérification, refus `ERASED`) ; changement de nom (trois types, badges) ; non-régression `identity`, `marketplace`, `messaging`, `notifications`, `DomainBoundariesTests` ; entrées du registre MySQL | B5, F-L17-4 | — |

**Chemin critique :** B8 -> B9 -> B10 -> **B1 -> B2 -> B3 -> B4 -> B5** (série imposée par les migrations et par les fichiers partagés `acting.py`, `organizations.py`, `sellers.py`). B2 n'a pas de migration : il peut avancer en parallèle de B3 si deux développeurs se répartissent les fichiers (`restrictions.py` contre `lifecycle.py`), au prix d'une fusion dans `acting.py` ; recommandé en série. **En parallèle dès maintenant :** A-L17, D-L17, F-L17-1 (sur fixture). Chaque F est fusionnée après sa tâche B.

## 17. Questions restantes (avec recommandation)

| # | Question | Pour | Recommandation |
|---|---|---|---|
| **QO-8** | Durées : dormance, délai avant restriction puis archivage d'une orpheline | client | Livrer avec 0 (désactivé). Proposition de l'équipe à soumettre : dormance 365 jours ; orpheline restreinte après 30 jours, archivée après 180 jours. Le client valide (Q4 : durées validées juridiquement). |
| **QL-1** | Effets de la dormance : sortie de l'annuaire, profil et offres publics, aucune capacité retirée | client | Valider. Alternative plus forte : masquer le profil public (pénalise une organisation simplement silencieuse). |
| **QL-2** | Délai de fermeture (`closure_delay_days`) : 0 (immédiat, comportement actuel) ou délai de rétractation | utilisateur | 0 en V1 ; passer à 7 si l'audit le demande (une fermeture hostile par un Administrateur principal compromis reste restaurable). |
| **QL-3** | Fermeture permise sous suspension totale | utilisateur, client | Oui : par analogie avec Q24 (on peut partir, on n'efface pas la sanction) ; la restriction survit à l'archivage et bloque l'effacement. |
| **QL-4** | Double contrôle de la fermeture quand il existe plusieurs Administrateurs principaux | utilisateur | Non en V1 : ressaisie + notification de tous + annulation possible pendant `CLOSING` + restauration. |
| **QL-5** | Nom affiché pendant l'examen d'un changement : ancien nom (2.5 A) | client | Valider A ; B en ajout si le client le souhaite. |
| **QL-6** | Demande de restauration par l'Aide et Support seulement en V1 | utilisateur | Valider ; dépend de L1-21 (avant L1-21 : courriel ou canal externe du support, enregistré par le personnel). |
| **QL-7** | Le modérateur peut-il poser des restrictions ciblées (publication, réponse aux avis, messagerie) ? | client (DOC-01) | Non en V1 (Administrateur seul, comme la suspension aujourd'hui) ; ouvrir par permission quand DOC-01 fixe la matrice. |
| **QL-8** | Taxonomie : 7 catégories de Q33 + « Gouvernance » + « Autre » | client (DOC-01) | Valider comme semence provisoire ; textes d'explication rédigés par l'analyste (A-L17). |
| **QL-9** | Motif communiqué en texte libre (500 caractères) en plus de l'explication de catégorie | utilisateur, auditeur-securite | Oui, avec consigne et revue S-L17-2 ; alternative : modèles de motifs par catégorie seulement (moins utile, plus sûr). |
| **QL-10** | Restauration : revérification par défaut (organisation non publique jusqu'à vérification, numéro de contact à revérifier) | client | Valider (Q34 « revérifier si nécessaire » : défaut prudent, décochable avec motif). |
| **QL-11** | Éditeurs, analystes, membres : voient « suspendue » et la liste des mesures, sans catégorie ni motif | client | Valider (Q33 « un membre ordinaire ne voit pas automatiquement les éléments sensibles »). |
| **QL-12** | Nouveau code `DENY_RESTRICTION` (famille A14) | chef de projet | Valider ; sinon `DENY_SECURITY` avec une clé additive, moins lisible pour le front. |
| **QL-13** | Dénomination légale (`legal_name`) : saisie par l'organisation avant vérification, confirmée par le personnel à la validation du RCCM | client | Valider ; affichage public décidé par L1-02c. |
