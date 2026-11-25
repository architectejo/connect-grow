# L1-17, L1-19, L1-20 — Stories, critères d'acceptation et textes : cycle de vie, restrictions et nom des organisations

- **Tâche :** A-L17 (ADR 0011 §16).
- **Date :** 25/11/2026 ; **auteur :** analyste-fonctionnel.
- **Statut :** proposition, à valider par le chef de projet. Les textes des catégories sont **provisoires** jusqu'à la Matrice Sanctions (DOC-01).
- **Sources :** réponses verrouillées du client Q4, Q17, Q33, Q34, Q35 (et Q1, Q19, Q24 par renvoi) dans `docs/client/ConnectePlus_Reponses_Consolidees_Q1-Q36.md` ; `docs/adr/0011-cycle-de-vie-organisations.md` ; `docs/specs/L1-17-contrat-api.md` ; `docs/specs/impact-reponses-client-Q1-Q36.md` (K8, K9, K10, QO-8, §4) ; `docs/specs/L0-09-ecran-organisation-suspendue.md` ; CDC v1.2 §3.1, §3.17 ; CLAUDE.md §4.
- **Décisions du chef de projet appliquées :** recommandations QL-1 à QL-13 de l'ADR 0011 §17 retenues ; code `DENY_RESTRICTION` accepté ; durées de dormance et d'organisation orpheline à **0 (désactivées)** en attendant le client (QO-8).
- **Ce document ne modifie** ni le code, ni le CDC, ni l'ADR. Le diff du CDC (section 8) est une proposition.

---

## 0. Lecture rapide

### 0.1. Stories et tâches qui les livrent

| Story | Titre | Tâches | Réf. client |
|---|---|---|---|
| L1-17a | Séparer cycle de vie et sanctions, convertir l'existant | L1-17-B1, F-L17-1 | Q17, Q33, Q34 |
| L1-17b | Suspension totale posée et levée par le personnel | L1-17-B1, F-L17-2 | Q33 |
| L1-17c | Demander la fermeture d'une organisation | L1-17-B3, F-L17-3 | Q4, Q34 |
| L1-17d | Annuler une fermeture en cours | L1-17-B3, F-L17-3 | Q34 |
| L1-17e | Organisation inactive (dormante) et confirmation d'activité | L1-17-B3, F-L17-3 | Q34 |
| L1-17f | Archivage par décision du personnel | L1-17-B3 | Q34 |
| L1-17g | Organisation sans administrateur principal : restriction puis archivage automatiques | L1-17-B3 | Q17 |
| L1-17h | Restauration exceptionnelle d'une organisation archivée | L1-17-B4, F-L17-3 (texte) | Q34 |
| L1-19a | Poser, modifier, lever une restriction ciblée (back-office) | L1-19-B2 | Q33 |
| L1-19b | Effets de chaque mesure et refus `DENY_RESTRICTION` | L1-19-B2, F-L17-2 | Q33 |
| L1-19c | Consulter le détail des restrictions (administrateurs) | L1-19-B2, F-L17-2 | Q33 |
| L1-19d | Ce que voient les autres rôles, les acheteurs et le public | L1-19-B2, F-L17-2 | Q33 |
| L1-19e | Catégories de restriction configurables | L1-17-B1 (semence), L1-19-B2 (admin) | Q33, règle 11 |
| L1-19f | Notifications de restriction | L1-19-B2 | Q33 |
| L1-20a | Dénomination légale, nom d'affichage et historique | L1-20-B5, F-L17-4 | Q35 |
| L1-20b | Demander une modification du nom | L1-20-B5, F-L17-4 | Q35, Q1 |
| L1-20c | Justificatifs rattachés, sans badge avant décision | L1-20-B5, F-L17-4 | Q35, règle 3 |
| L1-20d | Décision par l'équipe Vérification | L1-20-B5 | Q35 |
| L1-20e | Annuler une demande ; clôture automatique | L1-20-B5, F-L17-4 | Q35 |

### 0.2. Vocabulaire employé dans les textes

| Terme technique | Terme affiché |
|---|---|
| `OWNER` | Administrateur principal |
| `ADMIN` | Administrateur |
| `EDITOR`, `ANALYST`, `MEMBER` | Éditeur, Analyste, Membre |
| `ACTIVE` | Active |
| `DORMANT` | **Inactive** (voir C7) |
| `CLOSING` | Fermeture en cours |
| `ARCHIVED` | Archivée |
| restriction `FULL_SUSPENSION` | Suspendue / suspension totale |
| autre restriction | Restriction |
| Aide et Support (L1-21) | l'aide Connecte+ |

---

## 1. Analyse de conformité

### 1.1. Règles verrouillées (CLAUDE.md §4)

| Règle | Verdict | Justification |
|---|---|---|
| 1. Compte unique | Conforme | Une restriction d'organisation ne touche pas les contextes personnel et prestataire des membres (Q17 : « les sanctions de l'organisation ne s'étendent pas automatiquement à tous ses membres »). Critère L1-19b-12. |
| 2. Permissions ≠ droits commerciaux | Conforme | Aucun plan, pass ni paiement ne lève une restriction ni ne restaure une organisation. Critères L1-19a-11, L1-17h-14. |
| 3. Vérification non achetable | Conforme | Changement de nom décidé par l'équipe Vérification ; pièces rattachées sans badge avant décision ; le nouveau nom n'hérite de rien pendant l'examen (Q35). |
| 4. Aucun score de confiance | Conforme | Une restriction est un état factuel, pas une note ; la dormance n'est pas un signal de qualité. Textes 6.1 : « Ce n'est pas une note. » |
| 8. États indépendants | Conforme et renforcée | Cycle de vie, restrictions, gouvernance et demandes sont séparés (Q17, Q34 : « Archivage ≠ suspension ≠ exclusion ≠ suppression »). |
| 10. Données par finalité | Conforme sous réserve de C2 | Motif communiqué réservé aux administrateurs ; note interne jamais exposée ; dénomination légale non publique. Point C2 : la clé `measure` renvoyée à un acheteur. |
| 11. Configurable | Conforme | Catégories, explications, durées en back-office ; durées à 0 tant que le client ne les a pas fixées. |
| 12. Audit | Conforme | ADR 0011 §8 ; critères d'audit dans chaque story. |
| 5, 6, 7, 9 | Non touchées | La fermeture ne détient aucun fonds ; les obligations ouvertes sont lues, jamais compensées. |

### 1.2. Périmètre V1 et CDC

- **Périmètre :** L1-17 à L1-20 sont dans le lot 1 depuis les réponses du client (analyse d'impact §3.2). Rien ne touche un domaine hors V1.
- **Hors périmètre de ce document :** effacement ou anonymisation (`ERASED`, L1-24) ; fermeture de compte (ADR 0012) ; régularisation d'une organisation sans administrateur principal (L1-02f) ; noms protégés (L1-02g) ; Aide et Support (L1-21) ; taxonomie finale des sanctions (DOC-01) ; matrice des modifications sensibles (DOC-02) ; affichage public de la dénomination légale et de « anciennement » (L1-02c).
- **CDC :** §3.1 ne décrit ni cycle de vie, ni restriction, ni changement de nom ; §3.17 ne cite pas les restrictions d'organisation ni la restauration. Le CDC est en retard sur les réponses verrouillées (source 1) : diff en section 8.

---

## 2. Stories L1-17 — Cycle de vie

Conventions des critères :
- « Membre » = appartenance `ACTIVE`. « Administrateur principal effectif » au sens de l'ADR 0010.
- Les codes d'erreur et les formes de réponse sont ceux du contrat `docs/specs/L1-17-contrat-api.md` (ci-après « contrat »).
- « Le cron » désigne la commande nommée, lancée une fois dans le test (pas d'attente réelle).

### L1-17a — Séparer cycle de vie et sanctions, convertir l'existant

En tant que **staff** (et, par effet, tout membre),
je veux que l'état d'une organisation soit lu sur des axes séparés (cycle de vie, restrictions, gouvernance),
afin qu'une suspension, une fermeture et une perte d'administrateur ne s'écrasent jamais.
Réf. : CDC §3.1 ; Q17, Q33, Q34 ; ADR 0011 D1, D2, §10 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné une base contenant des organisations `ACTIVE`, `SUSPENDED` (avec chacun des 4 anciens motifs et un motif vide) et `ARCHIVED`, quand la migration `0023` est appliquée, alors : chaque `ACTIVE` reste `lifecycle_status = ACTIVE` sans restriction ; chaque `ARCHIVED` devient `ARCHIVED` avec `lifecycle_reason = legacy_status` et une ligne d'historique de cycle de vie ; chaque `SUSPENDED` devient `ACTIVE` + une restriction `FULL_SUSPENSION` effective.
- [ ] 2. Étant donné une suspension convertie, alors sa catégorie est `verification_identity` pour l'ancien motif `verification` et `other` pour tous les autres motifs (y compris vide) ; `disclosure = LIMITED` ; motif communiqué vide ; action requise `CONTACT_SUPPORT` ; recours `SUPPORT_REQUEST` ; aucune ligne d'`AuditLog` écrite par la migration.
- [ ] 3. Étant donné 200 organisations fabriquées des trois statuts, quand on convertit, revient en arrière, puis reconvertit, alors les comptages par statut sont identiques aux trois étapes.
- [ ] 4. Étant donné une organisation `CLOSING` ou une restriction effective autre que `FULL_SUSPENSION`, quand on tente le retour arrière de `0023`, alors la migration échoue avec un message qui ne contient que des comptages (aucun nom, aucun identifiant).
- [ ] 5. Étant donné le code après `0024`, quand le test de garde « lecteur oublié » s'exécute, alors il échoue si `Organization.STATUS_`, `organization__status` ou `suspension_reason` apparaissent hors des migrations.
- [ ] 6. Étant donné une organisation à la fois `ARCHIVED`, suspendue et sans administrateur principal (`MISSING`), alors les trois états se lisent simultanément (cycle de vie, résumé de restriction, gouvernance) et aucun n'est modifié par la lecture des autres.
- [ ] 7. Étant donné un membre de chaque rôle (5 rôles) et chaque combinaison cycle de vie (4 valeurs servies) × mesure (8 + aucune), quand on appelle `organization_gate` pour chaque capacité, alors le code de refus suit exactement l'ordre du contrat §0 (test paramétré case par case).
- [ ] 8. Étant donné une nouvelle capacité ajoutée au catalogue sans classement dans la table des mesures, alors un test échoue.
- [ ] 9. Étant donné `GET contexts/`, alors `results` contient les organisations `ACTIVE` ou `DORMANT` non suspendues, avec `lifecycle_status` et `restrictions` ; `unavailable` contient les `CLOSING`, `ARCHIVED` ou suspendues, chaque élément ayant exactement 11 clés (10 après retrait de `status`) ; le nombre de requêtes SQL reste 3.
- [ ] 10. Étant donné un élément de `results` ou `unavailable`, alors `capabilities` contient uniquement les capacités réellement exerçables (rôle, périmètre, cycle de vie, mesures) : pour l'Administrateur principal d'une organisation `CLOSING`, exactement `["offer.view_internal", "org.archive", "org.leave", "org.view_internal", "org.view_restrictions", "stats.view"]`.
- [ ] 11. Étant donné le champ `status` dérivé (période de transition), alors il vaut `SUSPENDED` si `restrictions.suspended`, sinon `ARCHIVED` si `CLOSING` ou `ARCHIVED`, sinon `ACTIVE`.

Règles métier :
- Une restriction n'est jamais supprimée par l'application ; une transition de cycle de vie ne pose ni ne lève de restriction, sauf les deux cas système de L1-17g et L1-17h.
- La revue de création (ADR 0010) n'est pas une restriction et n'apparaît jamais dans `restrictions`.

Hors périmètre : `ERASED` (L1-24) ; données de production (aucune, ADR 0002).

Questions ouvertes : aucune.

### L1-17b — Suspension totale posée et levée par le personnel

En tant que **staff** (groupe « Administrateur »),
je veux suspendre entièrement une organisation puis lever la suspension, avec une catégorie et un motif communiqué,
afin d'appliquer une sanction proportionnée et explicable (Q33 : « suspension totale ou restriction ciblée »).
Réf. : CDC §3.17 (Modération) ; Q33, Q17 ; ADR 0011 D3, §4.2, §6.2 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné un compte du personnel avec `impose_organizationrestriction`, quand il pose une `FULL_SUSPENSION` avec une catégorie active, alors une restriction `ACTIVE` est créée, `public_visibility_blocked` devient vrai dans la même transaction, une ligne `ORG_RESTRICTION_IMPOSED` est écrite et l'événement `identity.organization_restriction_changed` (`imposed`) est en outbox.
- [ ] 2. Étant donné une organisation suspendue, alors : son profil vendeur public répond 404 ; ses offres sont absentes des listes et leur fiche répond 404 ; elle est absente de l'annuaire ; contact, révélation, échange et nouvelle conversation répondent `403 DENY_SECURITY`.
- [ ] 3. Étant donné un membre d'une organisation suspendue, quand il appelle une route d'organisation, alors il reçoit `403 DENY_SECURITY`, sauf pour `org.leave`, `org.view_restrictions` (Administrateur principal, Administrateur) et `org.archive` (fermeture, Administrateur principal).
- [ ] 4. Étant donné un compte du personnel qui est ou a été membre de l'organisation, ou qui l'a créée, quand il tente de poser ou de lever une restriction, alors il reçoit `403 interest_conflict` et une ligne `ORG_RESTRICTION_DENIED` est écrite même si la transaction est annulée.
- [ ] 5. Étant donné un compte du groupe « Modérateur » seul, alors il ne voit pas l'action « Poser une restriction » et le service refuse (QL-7).
- [ ] 6. Étant donné deux `FULL_SUSPENSION` actives de causes différentes, quand le personnel lève l'une, alors l'organisation reste suspendue ; quand il lève la seconde, alors `public_visibility_blocked` redevient faux et l'événement de visibilité porte la raison `reactivated`.
- [ ] 7. Étant donné une organisation suspendue dont l'Administrateur principal est remplacé (nomination ADR 0010), alors la suspension reste active (Q17 : « le remplacement de l'administrateur ne l'annule pas »).
- [ ] 8. Étant donné une organisation suspendue, quand son Administrateur principal la ferme (L1-17c), alors elle devient `ARCHIVED` et la restriction reste `ACTIVE` (QL-3).
- [ ] 9. Étant donné une restriction avec une note interne contenant une chaîne sentinelle, alors la sentinelle n'apparaît dans aucune réponse d'API, ligne d'`AuditLog`, événement d'outbox, notification ni journal applicatif.

Règles métier : une suspension totale garde le code `DENY_SECURITY` (compatibilité du front livré) ; la mesure, la catégorie et le périmètre d'une restriction ne changent jamais (on lève et on repose).

Hors périmètre : écran du personnel hors admin Django ; sanction du compte d'une personne (`moderation.Sanction`).

Questions ouvertes : aucune.

### L1-17c — Demander la fermeture d'une organisation

En tant qu'**organisation** (Administrateur principal effectif),
je veux fermer mon organisation en confirmant par mon mot de passe et en donnant un motif,
afin de mettre fin à sa présence sur Connecte+ sans effacer son historique.
Réf. : CDC §3.1 ; Q4, Q34 ; ADR 0011 D7, §6.3 ; contrat §3.1 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné `closure_delay_days = 0` et aucune obligation ouverte, quand l'Administrateur principal envoie `POST closure/` avec `confirm = true`, le bon mot de passe et un `reason_code` valide, alors la réponse est `200` avec `lifecycle_status = "ARCHIVED"`, `closure_effective_at = null`, `pending_obligations = []`, et l'historique contient deux transitions (`ACTIVE -> CLOSING`, `CLOSING -> ARCHIVED`).
- [ ] 2. Étant donné `closure_delay_days = 7`, quand la fermeture est demandée à l'instant T, alors la réponse indique `CLOSING` et `closure_effective_at = T + 7 jours` ; quand le cron `process_organization_lifecycle` tourne à T + 6 jours, l'organisation reste `CLOSING` ; à T + 7 jours, elle devient `ARCHIVED`.
- [ ] 3. Étant donné un module d'obligations inscrit qui renvoie `["payments_open"]`, quand le délai est écoulé, alors l'organisation reste `CLOSING` et la réponse ou la relecture expose `pending_obligations = ["payments_open"]` sans aucun détail.
- [ ] 4. Étant donné un module d'obligations qui lève une erreur, alors la fermeture reste `CLOSING` avec `provider_unavailable` (échec fermé).
- [ ] 5. Étant donné un mauvais mot de passe, alors `403 reauthentication_failed`, aucune transition, et une ligne `ORG_SENSITIVE_REAUTH_FAILED` avec `action=close_organization`.
- [ ] 6. Étant donné `confirm` absent ou faux, alors `400 {"confirm": [...]}` ; étant donné un `reason_code` inconnu, alors `400 {"reason_code": [...]}`.
- [ ] 7. Étant donné un Administrateur (non principal), un Éditeur, un Analyste ou un Membre, alors `403 DENY_PERMISSION`.
- [ ] 8. Étant donné une organisation déjà `CLOSING`, alors `409 closure_already_requested` ; déjà `ARCHIVED`, alors `403 DENY_OBJECT_STATE`.
- [ ] 9. Étant donné une organisation suspendue, quand l'Administrateur principal demande la fermeture, alors elle est acceptée (QL-3).
- [ ] 10. Étant donné une organisation `DORMANT`, alors la fermeture est acceptée comme pour `ACTIVE`.
- [ ] 11. Étant donné le passage en `CLOSING`, alors : les invitations en attente deviennent inacceptables ; les nominations ouvertes et la demande de changement de nom ouverte passent `VOID` (`organization_unavailable`) ; tous les membres actifs et tous les Administrateurs principaux reçoivent la notification 6.12 ; une ligne `ORG_CLOSURE_REQUESTED` est écrite avec `reauth=true`.
- [ ] 12. Étant donné une organisation `CLOSING`, alors : profil et offres non publics ; contact et conversation `403 DENY_OBJECT_STATE` ; les membres gardent seulement les capacités du contrat §0 point 3.
- [ ] 13. Étant donné une organisation `CLOSING` ou `ARCHIVED`, quand un membre la quitte, alors `204` ; le dernier Administrateur principal reçoit `409 last_owner` en `CLOSING` et `204` en `ARCHIVED`.
- [ ] 14. Étant donné `POST organizations/<id>/archive/` après la livraison, alors `404`.
- [ ] 15. Le throttle `org_sensitive` s'applique (11e appel dans l'heure : `429` avec `Retry-After`).

Règles métier :
- Aucun double contrôle de la fermeture en V1 (QL-4) : ressaisie, notification de tous, annulation possible pendant `CLOSING`, restauration ensuite.
- Les restrictions actives survivent à l'archivage et bloqueront l'effacement (L1-24).
- La fermeture n'efface ni n'anonymise rien.

Hors périmètre : effacement (L1-24) ; inscription réelle des modules au registre d'obligations (L1-12, lot 2) ; sort des droits commerciaux d'une organisation archivée (ADR 0009, L1-12).

Questions ouvertes : C3 (le dialogue ne connaît pas le délai) ; QC-5 (droits commerciaux restants).

### L1-17d — Annuler une fermeture en cours

En tant qu'**organisation** (Administrateur principal effectif),
je veux annuler une fermeture tant qu'elle n'a pas pris effet,
afin de corriger une erreur ou une fermeture faite par un autre Administrateur principal.
Réf. : Q34 ; ADR 0011 D7 ; contrat §3.2 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné une organisation `CLOSING`, quand un Administrateur principal effectif (y compris un autre que le demandeur) envoie `DELETE closure/`, alors `200` avec `lifecycle_status = "ACTIVE"`, une transition `closure_cancelled`, une ligne `ORG_CLOSURE_CANCELLED` et la notification « fermeture annulée » à tous les membres actifs.
- [ ] 2. Aucun mot de passe n'est demandé.
- [ ] 3. Étant donné une organisation `ACTIVE`, alors `409 closure_not_pending` ; `ARCHIVED`, alors `403 DENY_OBJECT_STATE`.
- [ ] 4. Étant donné un Administrateur, alors `403 DENY_PERMISSION`.
- [ ] 5. Étant donné une annulation et une finalisation par le cron simultanées, alors un seul des deux aboutit (transition conditionnelle) et l'état final est cohérent avec l'historique.
- [ ] 6. Étant donné une fermeture annulée, alors les nominations et la demande de nom passées `VOID` ne sont pas rouvertes.

Hors périmètre : réouverture automatique d'objets annulés.

Questions ouvertes : aucune.

### L1-17e — Organisation inactive (dormante) et confirmation d'activité

En tant qu'**organisation** (Administrateur principal ou Administrateur),
je veux être prévenu que mon organisation est considérée comme inactive et pouvoir confirmer qu'elle est toujours en activité,
afin de revenir dans l'annuaire sans démarche lourde.
Réf. : Q34 (« une longue inactivité conduit à Inactive/Dormante, pas à Archivée ») ; ADR 0011 D8, §6.5 ; contrat §3.3 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné `dormancy_after_days = 0` (valeur livrée), quand le cron tourne sur une organisation sans activité depuis 10 ans, alors elle reste `ACTIVE`.
- [ ] 2. Étant donné une saisie de `dormancy_after_days` à 1, 29 ou 3 651 en back-office, alors elle est refusée ; 0, 30 et 3 650 sont acceptés ; chaque modification écrit `SETTINGS_CHANGED`.
- [ ] 3. Étant donné `dormancy_after_days = 30` et une organisation dont `last_activity_at` date de 31 jours, quand le cron tourne, alors elle devient `DORMANT` (`dormancy`), une ligne `ORG_DORMANT` est écrite et les Administrateurs principaux et Administrateurs reçoivent la notification 6.12.
- [ ] 4. Étant donné une organisation `DORMANT`, alors : elle est absente de l'annuaire ; son profil vendeur public répond 200 ; ses offres restent publiques ; tous ses membres gardent toutes leurs capacités ; elle reste dans `results` de `contexts/`.
- [ ] 5. Étant donné un membre avec `org.edit_profile`, quand il envoie `POST resume/` avec `confirm = true`, alors `200`, `lifecycle.status = "ACTIVE"`, `last_activity_at` = maintenant, une ligne `ORG_RESUMED`.
- [ ] 6. Étant donné une organisation `ACTIVE`, alors `POST resume/` répond `409 organization_not_dormant` ; sans `confirm`, `400 {"confirm": [...]}` ; un Éditeur reçoit `403 DENY_PERMISSION`.
- [ ] 7. Étant donné une organisation `DORMANT` qui publie une offre (activité postérieure à l'entrée), quand le cron tourne, alors elle redevient `ACTIVE` (`activity_detected`).
- [ ] 8. Étant donné une requête de lecture d'un utilisateur, alors aucune écriture de `last_activity_at` n'a lieu (calcul par le cron seulement).
- [ ] 9. Étant donné le signal `last_login`, si la connexion JWT ne le met pas à jour, alors ce signal est absent du calcul et l'omission est écrite dans le rapport de B3.

Règles métier : la dormance ne retire aucune capacité et n'est jamais un signal de qualité (règle 4) ; la revérification d'informations expirées relève de L1-02d.

Hors périmètre : valeur réelle du délai (QO-8).

Questions ouvertes : QO-8 ; QL-1 à confirmer par le client.

### L1-17f — Archivage par décision du personnel

En tant que **staff** (groupe « Administrateur »),
je veux archiver une organisation avec un motif codé,
afin de traiter un doublon, une fraude établie ou une décision d'une autorité.
Réf. : Q34 ; ADR 0011 §5.1, §6.3 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné la permission `archive_organization_staff` et une organisation `ACTIVE`, `DORMANT` ou `CLOSING`, quand le personnel archive avec un motif de la liste 6.9, alors elle devient `ARCHIVED` (`staff_decision`), une ligne `ORG_ARCHIVED` avec `reason=staff_decision` est écrite et tous les membres actifs reçoivent la notification d'archivage.
- [ ] 2. Étant donné un acteur sans la permission, ou en conflit d'intérêts, alors refus (`403 interest_conflict` dans le second cas).
- [ ] 3. Étant donné une organisation `ARCHIVED`, alors l'action est refusée (`409 invalid_lifecycle_transition`).
- [ ] 4. Étant donné l'archivage, alors aucune restriction n'est posée ni levée.
- [ ] 5. Étant donné une réponse d'API servie à un membre, alors le motif de l'archivage (`lifecycle_reason`) n'y figure pas.

Questions ouvertes : C6 (faut-il dire au membre que l'archivage vient de Connecte+ ?).

### L1-17g — Organisation sans administrateur principal : restriction puis archivage automatiques

En tant que **staff** (et, par effet, l'organisation),
je veux qu'une organisation restée sans administrateur principal soit d'abord restreinte puis archivée selon des délais configurables,
afin d'appliquer Q17 (« restreinte puis archivée selon son cycle de vie ») sans promotion automatique.
Réf. : Q17 ; ADR 0011 D6 a, §6.3 ; ADR 0010 (B10) ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné `orphan_restrict_after_days = 0` et `orphan_archive_after_days = 0` (valeurs livrées), alors le cron ne pose aucune restriction et n'archive rien.
- [ ] 2. Étant donné les deux valeurs non nulles avec la seconde inférieure ou égale à la première, alors la saisie est refusée.
- [ ] 3. Étant donné `orphan_restrict_after_days = 30` et une organisation `MISSING` depuis 31 jours, quand le cron tourne, alors une restriction `PUBLICATION_BLOCK`, catégorie `governance`, action `REGULARIZE_GOVERNANCE`, origine `governance`, acteur nul, est posée ; un second passage du cron n'en crée pas de seconde.
- [ ] 4. Étant donné cette organisation revenue à `OK`, quand le cron tourne, alors la restriction `governance` est levée (`governance_restored`) ; une autre restriction posée par le personnel reste active.
- [ ] 5. Étant donné `orphan_archive_after_days = 180` et une organisation `MISSING` depuis 181 jours, quand le cron tourne, alors elle devient `ARCHIVED` (`orphaned`) et les membres reçoivent le texte « archivée faute d'administrateur principal ».
- [ ] 6. Étant donné une organisation à la fois suspendue et orpheline, alors elle suit la même règle et la suspension reste active après archivage.
- [ ] 7. Aucun Éditeur, Analyste ni Membre n'est promu à aucun moment (Q17).
- [ ] 8. Étant donné un appel à `impose_system_restriction` avec une origine autre que `governance` ou `restoration`, alors `ValueError` (test).

Hors périmètre : la récupération formelle de l'administration (L1-02f).

Questions ouvertes : QO-8.

### L1-17h — Restauration exceptionnelle d'une organisation archivée

En tant que **staff** (groupes « Vérification » pour préparer, « Administrateur » pour décider),
je veux restaurer une organisation archivée après des contrôles faits par deux personnes différentes,
afin de corriger une erreur d'archivage ou une fermeture sans autorité, sur le même objet (Q34).
Réf. : CDC §3.17 ; Q34 ; ADR 0011 D5, §4.6, §5.3, §6.6 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné une organisation `ARCHIVED`, quand le personnel enregistre une demande (demandeur, motif de la liste 6.9, référence d'aide facultative), alors une demande `OPEN` est créée avec l'instantané du motif d'archivage et une ligne `ORG_RESTORATION_REQUESTED`.
- [ ] 2. Étant donné une organisation `ACTIVE`, `DORMANT` ou `CLOSING`, alors `409 restoration_not_applicable` ; `ERASED`, alors `409 restoration_impossible`.
- [ ] 3. Étant donné une demande déjà ouverte (`OPEN` ou `READY_FOR_DECISION`), alors une seconde est refusée.
- [ ] 4. Étant donné trois contrôles cochés sur quatre, alors la demande reste `OPEN` ; les quatre cochés, elle passe `READY_FOR_DECISION` avec `prepared_by`.
- [ ] 5. Étant donné le même compte pour la préparation et la décision, ou pour l'enregistrement et la décision, alors `403 four_eyes_required`, quels que soient ses groupes.
- [ ] 6. Étant donné un compte du personnel qui est, a été membre, a créé l'organisation ou est le demandeur, alors il ne peut ni préparer ni décider (`403 interest_conflict`).
- [ ] 7. Étant donné une décision d'approbation, alors : l'organisation garde **le même identifiant** et passe `ARCHIVED -> ACTIVE` (`restored`) ; l'historique antérieur est intact ; les restrictions existantes restent ; une ligne `ORG_RESTORED` contient `restrictions_active=<n>`.
- [ ] 8. Étant donné `reverification_required = vrai` (défaut), alors une restriction `PUBLIC_VISIBILITY_HIDDEN`, catégorie `verification_identity`, action `SUBMIT_DOCUMENTS`, origine `restoration` est posée, le numéro de contact de l'organisation repasse non vérifié, et le profil public répond 404 jusqu'à la levée par l'équipe Vérification.
- [ ] 9. Étant donné `reverification_required` décoché sans motif de décision, alors refus.
- [ ] 10. Étant donné l'organisation sortie d'`ARCHIVED` entre la préparation et la décision, alors la décision échoue (revalidation) et la demande passe `VOID`.
- [ ] 11. Étant donné une demande ouverte depuis plus de `restoration_request_ttl_days`, quand le cron tourne, alors elle passe `VOID`.
- [ ] 12. Étant donné un refus, alors la demande passe `REJECTED` et le demandeur (s'il a un compte) reçoit la notification neutre 6.12.
- [ ] 13. Étant donné une restauration, alors aucune invitation, nomination ni demande de nom antérieure n'est rouverte ; si l'organisation est `MISSING`, elle le reste (régularisation par L1-02f).
- [ ] 14. Aucun membre, aucune route d'API et aucun paiement ne peut déclencher une restauration.

Règles métier : restauration = acte exceptionnel du personnel ; demande reçue par l'aide (QL-6) ; avant L1-21, par un canal externe du support, enregistrée par le personnel.

Hors périmètre : demande de restauration dans l'application (dette 2.6 B) ; revérification des licences et des destinations de paiement (C4).

Questions ouvertes : C4 ; QC-6.

---

## 3. Stories L1-19 — Restrictions ciblées

### L1-19a — Poser, modifier, lever une restriction ciblée

En tant que **staff** (groupe « Administrateur » ; « Vérification » pour lever les restrictions de revérification),
je veux poser une restriction limitée à une fonction (publication, contact, messagerie, réponses aux avis, équipe, profil, visibilité),
afin de sanctionner au plus juste sans suspendre toute l'organisation (Q33).
Réf. : CDC §3.17 ; Q33 ; ADR 0011 §4.2, §4.4, §5.2, §6.2 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné chacune des 7 mesures ciblées, quand le personnel la pose, alors la restriction est `ACTIVE`, `active_restriction_measures` contient le code (trié, sans doublon) et `public_visibility_blocked` n'est vrai que pour `PUBLIC_VISIBILITY_HIDDEN`.
- [ ] 2. Étant donné une catégorie inactive, une mesure inconnue, une action requise ou un mode de recours hors liste, alors erreur de champ et rien n'est créé.
- [ ] 3. Étant donné un périmètre `UNIT`, alors refus (V1 : `ORGANIZATION` seul).
- [ ] 4. Étant donné un motif communiqué de 501 caractères ou un détail d'action de 301 caractères, alors refus ; le formulaire affiche la consigne 6.6.
- [ ] 5. Étant donné une combinaison mesure × action requise interdite par la table 6.4 (après décision C1), alors refus avec un message de champ.
- [ ] 6. Étant donné une restriction active, quand le personnel modifie le motif communiqué, la divulgation, l'action requise, le recours ou l'échéance, alors la modification est enregistrée avec `ORG_RESTRICTION_UPDATED` (noms de champs seulement) ; la mesure, la catégorie et le périmètre ne sont pas modifiables.
- [ ] 7. Étant donné une échéance `ends_at` passée, alors `GET restrictions/` présente la restriction `EXPIRED` immédiatement ; la mesure reste appliquée jusqu'au passage du cron `sync_organization_restrictions` (au plus 10 minutes, échec fermé) ; après le cron, la restriction est `EXPIRED`, le résumé recalculé et `ORG_RESTRICTION_EXPIRED` écrit.
- [ ] 8. Étant donné une levée et une expiration simultanées, alors une seule transition a lieu.
- [ ] 9. Étant donné un compte du groupe « Vérification », alors il ne peut lever que les restrictions d'origine `restoration` et de catégorie `verification_identity` (contrôle en service).
- [ ] 10. Étant donné un résumé dénormalisé volontairement faussé, quand le cron tourne, alors il est corrigé.
- [ ] 11. Aucun service de restriction ne reçoit de plan, de prix ni de paiement (test d'introspection) ; aucun membre ne peut lever une restriction.

Règles métier : plusieurs restrictions de même mesure peuvent coexister ; lever l'une ne lève pas l'autre (Q17).

Hors périmètre : qui, parmi les modérateurs, peut poser quoi (DOC-01, QL-7).

Questions ouvertes : C1.

### L1-19b — Effets de chaque mesure et refus `DENY_RESTRICTION`

En tant qu'**organisation** (tout membre),
je veux que seule la fonction restreinte soit bloquée, avec un message clair,
afin de continuer à travailler sur le reste.
Réf. : Q33 ; ADR 0011 §4.2, D10 ; contrat §0, §2.2, §5 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné `PUBLICATION_BLOCK`, quand un Éditeur crée, modifie, renouvelle ou republie une offre, alors `403 DENY_RESTRICTION` avec `measure = "PUBLICATION_BLOCK"` ; quand il met en pause, supprime ou met à la corbeille une offre, alors l'action réussit ; les offres déjà publiées restent visibles.
- [ ] 2. Étant donné `PUBLIC_VISIBILITY_HIDDEN`, alors profil et offres non publics (404 ou absents) et aucune capacité des membres n'est retirée.
- [ ] 3. Étant donné `CONTACT_BLOCK`, alors `allowed_channels = []` sur les offres de l'organisation et contact, révélation, échange répondent `403 DENY_RESTRICTION` (`CONTACT_BLOCK`) à l'acheteur.
- [ ] 4. Étant donné `MESSAGING_BLOCK`, alors une nouvelle conversation vers l'organisation répond `403 DENY_RESTRICTION` (`MESSAGING_BLOCK`) et un membre avec `message.reply` reçoit `403 DENY_RESTRICTION` en répondant.
- [ ] 5. Étant donné `REVIEW_REPLY_BLOCK`, alors répondre à un avis répond `403 DENY_RESTRICTION` ; les réponses déjà publiées restent visibles.
- [ ] 6. Étant donné `TEAM_CHANGES_BLOCK`, alors inviter, confirmer une invitation d'Administrateur, nommer, changer un rôle, retirer un membre répondent `403 DENY_RESTRICTION` ; quitter l'organisation répond `204`.
- [ ] 7. Étant donné `PROFILE_EDIT_BLOCK`, alors `PATCH organizations/<id>/` répond `403 DENY_RESTRICTION` ; `POST name-change-requests/` reste possible.
- [ ] 8. Étant donné un Analyste (sans `offer.publish`) sous `PUBLICATION_BLOCK`, quand il tente de publier, alors `403 DENY_PERMISSION` et la réponse ne contient pas `measure` (l'ordre du contrat §0 empêche l'oracle).
- [ ] 9. Étant donné une réponse `DENY_RESTRICTION`, alors elle contient exactement `detail`, `code`, `measure` ; jamais de catégorie, de motif ni de date (test d'ensemble de clés exact).
- [ ] 10. Étant donné `contexts/`, alors les capacités bloquées par une mesure ne figurent pas dans `capabilities` ; l'organisation reste dans `results`.
- [ ] 11. Étant donné un refus `DENY_RESTRICTION` dans un formulaire du front, alors le texte affiché vient de la clé i18n de la mesure (6.3), jamais de `detail`.
- [ ] 12. Étant donné une restriction de l'organisation, alors le contexte personnel et le contexte prestataire de ses membres ne sont pas affectés (publication personnelle possible).

Règles métier : réduire l'exposition (pause, suppression) est toujours permis ; la suspension totale garde `DENY_SECURITY`.

Questions ouvertes : C2 (acheteur), C5 (conversations existantes sous `MESSAGING_BLOCK`).

### L1-19c — Consulter le détail des restrictions (administrateurs)

En tant qu'**organisation** (Administrateur principal, Administrateur),
je veux voir pour chaque restriction : statut, catégorie, explication, motif, ce qui est bloqué, périmètre, depuis, échéance, action requise et recours,
afin de comprendre la mesure et savoir quoi faire (Q33 : « UI souhaitée »).
Réf. : Q33 ; ADR 0011 D4 ; contrat §2.1 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné un Administrateur principal ou un Administrateur, quand il appelle `GET restrictions/`, alors `200` avec les restrictions effectives triées (effectives, puis `since` décroissant, puis `id`), y compris sous suspension, en `CLOSING` et en `ARCHIVED`.
- [ ] 2. Étant donné `?history=true`, alors les restrictions levées et expirées sont incluses ; toute autre valeur : `400 invalid_filter`.
- [ ] 3. Étant donné un Éditeur, un Analyste ou un Membre, alors `403 DENY_PERMISSION` ; un non-membre ou une organisation inexistante : `403 DENY_RELATION` ; un compte restreint : `403 DENY_SECURITY`.
- [ ] 4. Étant donné `disclosure = LIMITED`, alors `communicated_reason = null` et `category`, `explanation`, `required_action`, `appeal` restent servis ; l'écran affiche le texte 6.6.
- [ ] 5. Étant donné un élément de la réponse, alors son ensemble de clés est exactement celui du contrat §2.1 ; `internal_note`, `imposed_by`, `lifted_by`, `source_type`, `source_id`, `lift_reason` n'y figurent jamais.
- [ ] 6. Étant donné une restriction convertie de l'ancien statut, alors l'écran montre « Autre motif », son explication, « Certains détails ne peuvent pas être communiqués », l'action « Contacter l'aide Connecte+ » et aucun motif.
- [ ] 7. Étant donné `ends_at = null`, alors l'écran affiche « Jusqu'à décision contraire » ; sinon la date au format local.
- [ ] 8. Étant donné aucune restriction effective, alors l'état vide 6.7 s'affiche.

Hors périmètre : preuves internes, auteur, historique d'audit (personnel seulement).

Questions ouvertes : aucune.

### L1-19d — Ce que voient les autres rôles, les acheteurs et le public

En tant que **personnel** (Éditeur, Analyste, Membre), **visiteur** ou **acheteur connecté**,
je veux savoir ce qui est bloqué sans accéder aux éléments sensibles,
afin de ne pas être induit en erreur, sans divulgation (Q33 : « un membre ordinaire ne voit pas automatiquement les éléments sensibles »).
Réf. : Q33 ; ADR 0011 D4 ; contrat §8 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné un Éditeur, un Analyste ou un Membre, alors `contexts/` et `internal/` exposent `restrictions = {suspended, measures}` et rien d'autre sur les restrictions.
- [ ] 2. Étant donné ces rôles, alors la bannière du front liste les mesures (6.2, libellé court) et le texte 6.7 « adressez-vous à un administrateur » ; aucun lien vers le détail.
- [ ] 3. Étant donné un visiteur anonyme ou un acheteur, alors aucune réponse publique ne contient de cycle de vie, de restriction ni de catégorie (test sur les clés du profil vendeur, des listes et des fiches d'offre).
- [ ] 4. Étant donné un acheteur refusé par `CONTACT_BLOCK` ou `MESSAGING_BLOCK`, alors le front affiche le texte neutre 6.3 (« ne peut pas être contactée pour le moment »), sans le mot « restriction ».

Questions ouvertes : C2.

### L1-19e — Catégories de restriction configurables

En tant que **staff** (groupe « Administrateur »),
je veux gérer les catégories (libellé, explication, action par défaut, ordre, activation) sans développement,
afin de suivre la future Matrice Sanctions (DOC-01).
Réf. : Q33 (« catégories illustratives, configurables et non exhaustives ») ; règle 11 ; ADR 0011 §4.3 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné une base vierge migrée, alors 9 catégories existent avec les codes, libellés et actions par défaut de la table 6.1.
- [ ] 2. Étant donné une explication de 1 001 caractères, alors refus.
- [ ] 3. Étant donné une catégorie utilisée par une restriction, alors sa suppression est impossible ; sa désactivation la retire du formulaire de pose et elle reste lisible sur les restrictions existantes.
- [ ] 4. Étant donné un code existant, alors un second avec le même code est refusé ; le code n'est pas modifiable après création.
- [ ] 5. Chaque création ou modification écrit `SETTINGS_CHANGED`.
- [ ] 6. Étant donné une modification de l'explication, alors `GET restrictions/` sert le nouveau texte pour toutes les restrictions de cette catégorie.

Règles métier : la migration pose un texte neutre ; les textes 6.1 sont saisis avant la production (ADR 0011 §4.3).

Questions ouvertes : QC-2 (validation des textes par le client).

### L1-19f — Notifications de restriction

En tant qu'**organisation**,
je veux être prévenu quand une restriction est posée, modifiée de façon importante ou levée,
afin de réagir dans les délais.
Réf. : Q33 ; ADR 0011 §7 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné une `FULL_SUSPENSION` posée, alors tous les membres actifs (hors acteur) reçoivent le texte de suspension ; les Administrateurs principaux et Administrateurs reçoivent en plus la phrase « Consultez le détail et l'action requise. » avec le lien `/organizations/<id>/restrictions`.
- [ ] 2. Étant donné une restriction ciblée posée, alors seuls les Administrateurs principaux et Administrateurs sont notifiés.
- [ ] 3. Étant donné une levée ou une expiration, alors les mêmes destinataires que pour la pose reçoivent le texte de levée.
- [ ] 4. Étant donné une notification ou un événement, alors ni motif communiqué, ni note interne, ni détail d'action n'y figurent (le nom de l'organisation n'est pas dans la charge utile de l'événement ; il est lu à l'envoi).

Questions ouvertes : faut-il notifier une modification (`updated`) de l'échéance ou de l'action requise ? Recommandation : oui pour les Administrateurs principaux et Administrateurs (texte 6.12) ; à valider par le chef de projet.

---

## 4. Stories L1-20 — Changement de nom contrôlé

### L1-20a — Dénomination légale, nom d'affichage et historique

En tant qu'**organisation** (Administrateur principal, Administrateur),
je veux renseigner la dénomination légale à côté du nom d'affichage,
afin que la vérification porte sur le bon nom (Q35 : « dénomination légale/enregistrée ; nom commercial/d'affichage ; historique »).
Réf. : Q35, Q1 ; ADR 0011 D9, §4.7 ; contrat §4.1 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné une organisation non verrouillée, quand un membre avec `org.edit_profile` modifie `legal_name`, alors la valeur est normalisée comme `name` (2 à 255 caractères ou vide ; sinon `invalid_name`) et une ligne `OrganizationNameHistory` (`FREE_EDIT`) est écrite.
- [ ] 2. Étant donné toute modification de `name` ou de `legal_name`, verrouillée ou non, alors une ligne d'historique est écrite.
- [ ] 3. Étant donné un nom verrouillé (pièce `VALIDE` ou `EN_ATTENTE`), quand `name` ou `legal_name` est modifié par `PATCH`, alors `409 name_locked_by_verification` avec le nouveau message du contrat ; `name_locked = true` dans `internal/`.
- [ ] 4. Étant donné un rôle sans `org.edit_profile`, alors `legal_name` vaut `null` dans `internal/`.
- [ ] 5. Étant donné une réponse publique, alors `legal_name` n'y figure pas.
- [ ] 6. Étant donné une ligne d'`AuditLog` ou un événement, alors aucun ancien ni nouveau nom n'y figure.

Hors périmètre : affichage public de la dénomination légale et de « anciennement » (L1-02c) ; confirmation de la dénomination à la validation du RCCM (QL-13, interface L1-02).

### L1-20b — Demander une modification du nom

En tant qu'**organisation** (Administrateur principal, Administrateur),
je veux demander la modification d'un nom vérifié en choisissant le type de changement,
afin de corriger une faute ou d'enregistrer un changement légitime sans perdre l'historique.
Réf. : Q35 ; ADR 0011 §5.4, §6.7 ; contrat §4.2, §4.3 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné un nom verrouillé, quand un Administrateur envoie une demande valide avec le bon mot de passe, alors `201` et le statut initial vaut : `PENDING_REVIEW` pour `TYPO_CORRECTION` ; `DOCUMENTS_REQUIRED` pour `LEGAL_NAME_CHANGE` ; pour `DISPLAY_NAME_CHANGE`, `DOCUMENTS_REQUIRED` si `display_name_change_requires_document` est vrai, sinon `PENDING_REVIEW`.
- [ ] 2. Étant donné un nom non verrouillé, alors `409 name_change_not_required`.
- [ ] 3. Étant donné aucun nom proposé, ou des noms identiques aux actuels, alors `400 nothing_to_change`.
- [ ] 4. Étant donné une demande déjà ouverte (`DOCUMENTS_REQUIRED` ou `PENDING_REVIEW`), alors `409 name_change_already_open`.
- [ ] 5. Étant donné un mauvais mot de passe, alors `403 reauthentication_failed` et `ORG_SENSITIVE_REAUTH_FAILED` avec `action=request_name_change`.
- [ ] 6. Étant donné un Éditeur, un Analyste ou un Membre, alors `403 DENY_PERMISSION` sur `GET` et `POST`.
- [ ] 7. Étant donné `PROFILE_EDIT_BLOCK`, alors la demande est acceptée ; étant donné une suspension totale, `403 DENY_SECURITY` ; `CLOSING` ou `ARCHIVED`, `403 DENY_OBJECT_STATE`.
- [ ] 8. Étant donné une demande en cours, alors le nom public reste l'ancien jusqu'à la décision (QL-5) ; le nom proposé est visible seulement des Administrateurs principaux, Administrateurs et du personnel.
- [ ] 9. Étant donné l'objet `NameChangeRequest`, alors ni l'identité du demandeur (seulement `is_mine`), ni celle du réviseur, ni une URL de fichier n'y figurent.
- [ ] 10. Le throttle `org_sensitive` s'applique.

Règles métier : une nouvelle entité juridique ne passe pas par cette demande : elle crée une nouvelle organisation (Q35) ; rien n'est transféré par renommage.

Questions ouvertes : QC-3 (justificatifs selon les formes d'entités en RDC) ; QC-4 (changement de forme juridique = même entité ?).

### L1-20c — Justificatifs rattachés, sans badge avant décision

En tant qu'**organisation** (Administrateur principal, Administrateur),
je veux joindre des justificatifs à ma demande,
afin que l'équipe Vérification puisse décider.
Réf. : Q35 ; règle 3 ; ADR 0011 §4.7 ; contrat §4.3 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné une demande `DOCUMENTS_REQUIRED`, quand une première pièce de type `NAME_CHANGE_PROOF`, `RCCM` ou `ARRETE_ONG` est déposée avec `name_change_request_id`, alors la demande passe `PENDING_REVIEW`.
- [ ] 2. Étant donné un autre type de pièce avec `name_change_request_id`, alors `400 {"document_type": [...]}`.
- [ ] 3. Étant donné une demande d'une autre organisation ou inexistante, alors `404 name_change_request_not_found` ; une demande close, `409 name_change_not_open`.
- [ ] 4. Étant donné une pièce rattachée validée par le personnel alors que la demande n'est pas `COMPLETED`, alors `get_verified_claims` ne produit aucun badge à partir d'elle.
- [ ] 5. Étant donné la demande `COMPLETED`, alors une pièce `RCCM` ou `ARRETE_ONG` rattachée et `VALIDE` compte normalement.

### L1-20d — Décision par l'équipe Vérification

En tant que **staff** (groupe « Vérification »),
je veux accepter, refuser ou demander des pièces pour une demande de modification du nom,
afin de garantir la continuité juridique et d'éviter l'usurpation (Q1, Q35).
Réf. : Q35 ; ADR 0011 §6.7 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné une demande `PENDING_REVIEW` de type `LEGAL_NAME_CHANGE` sans pièce rattachée `VALIDE`, alors l'approbation est refusée.
- [ ] 2. Étant donné une approbation, alors : les noms proposés sont appliqués ; une ligne d'historique avec le type et la demande est écrite ; `ORG_NAME_CHANGED` et `ORG_NAME_CHANGE_REVIEWED` sont écrits ; l'événement `name_change_changed` (`completed`) est émis ; le demandeur, les Administrateurs principaux et les Administrateurs sont notifiés.
- [ ] 3. Étant donné un nom courant différent de l'instantané de la demande, alors la décision passe la demande `VOID` (`name_changed_meanwhile`) sans rien appliquer.
- [ ] 4. Étant donné un refus, alors `decision_reason` est obligatoire et visible des Administrateurs principaux et Administrateurs avec le texte 6.10.
- [ ] 5. Étant donné le refus `new_entity_required`, alors le texte indique de créer une nouvelle organisation et l'organisation existante ne change pas.
- [ ] 6. Étant donné « Demander des pièces », alors la demande repasse `DOCUMENTS_REQUIRED` et les destinataires sont notifiés.
- [ ] 7. Étant donné un réviseur en conflit d'intérêts (règle de la décision KYB, ADR 0006 §18 n°3), alors refus.

Hors périmètre : signal de nom protégé (L1-02g).

### L1-20e — Annuler une demande ; clôture automatique

En tant qu'**organisation** (demandeur ou Administrateur principal effectif),
je veux annuler une demande ouverte,
afin de corriger une erreur de saisie.
Réf. : Q35 ; contrat §4.3 ; lot 1.

Critères d'acceptation :
- [ ] 1. Étant donné une demande ouverte, quand le demandeur ou un Administrateur principal effectif annule, alors `200` avec `status = "CANCELLED"` et `ORG_NAME_CHANGE_CANCELLED`.
- [ ] 2. Étant donné un Administrateur qui n'est pas le demandeur, alors refus (code à préciser par l'architecte, voir C8).
- [ ] 3. Étant donné une demande close, alors `409 name_change_not_open`.
- [ ] 4. Étant donné l'organisation passée `CLOSING` ou `ARCHIVED`, alors la demande ouverte passe `VOID` (`organization_unavailable`).

---

## 5. Ce que voit chaque rôle

| Information ou action | Public, acheteur | Membre | Analyste | Éditeur | Administrateur | Administrateur principal | Personnel |
|---|---|---|---|---|---|---|---|
| Cycle de vie (badge, bannière) | non | oui | oui | oui | oui | oui | oui |
| « Suspendue » oui/non, liste des mesures | non (fonction indisponible) | oui | oui | oui | oui | oui | oui |
| Écran « Restrictions » (catégorie, explication, motif, action, recours, dates) | non | non | non | non | oui (motif masqué si divulgation limitée) | oui (idem) | oui |
| Note interne, auteur, origine, preuves | non | non | non | non | non | non | oui |
| Bouton « Confirmer l'activité » (inactive) | — | non | non | non | oui | oui | — |
| Fermer l'organisation | — | non | non | non | non | oui | archivage par le personnel |
| Annuler la fermeture | — | non | non | non | non | oui (tout Administrateur principal effectif) | — |
| Demander une modification du nom, voir les demandes | non | non | non | non | oui | oui | décision (Vérification) |
| Annuler une demande de nom | — | non | non | non | si demandeur | oui | — |
| Dénomination légale | non (L1-02c) | non | non | non | oui | oui | oui |
| Demande de restauration | non | non | non | non | non (passe par l'aide) | non (idem) | oui |
| Quitter l'organisation | — | oui dans tous les états | oui | oui | oui | oui (sauf `last_owner` hors archivée) | — |

---

## 6. Textes français

Principes : phrases courtes ; aucune preuve interne ; aucun nom de personne ; aucune accusation ; pas de « garantie » ni de « vérifié » hors contexte factuel ; rien qui laisse croire qu'un paiement règle une restriction. Les clés i18n sont indicatives (le designer et le développeur front les fixent).

### 6.1. Catégories (semence de la migration, éditables en back-office)

Texte « Ce que cela veut dire » (≤ 1 000 caractères), affiché aux Administrateurs principaux et Administrateurs.

| Code | Libellé | Action par défaut | Explication |
|---|---|---|---|
| `verification_identity` | Vérification et identité | `SUBMIT_DOCUMENTS` | Cette mesure concerne les informations qui permettent d'identifier l'organisation ou la personne qui la représente : pièces fournies, dénomination, numéro d'enregistrement, numéro de contact. Elle est prise quand ces informations sont incomplètes, ne concordent pas, ont expiré ou doivent être confirmées de nouveau. Elle ne signifie pas, à elle seule, qu'une faute a été commise. Suivez l'action indiquée ; l'équipe de vérification de Connecte+ examinera ensuite le dossier. |
| `security_integrity` | Sécurité et intégrité | `CONTACT_SUPPORT` | Cette mesure protège l'organisation, ses membres ou les utilisateurs de Connecte+ quand un risque de sécurité a été constaté : accès inhabituel, compte compromis, usage automatisé ou contournement des protections de la plateforme. Certains détails ne peuvent pas être communiqués pour ne pas affaiblir ces protections. Suivez l'action indiquée. Si vous pensez qu'il s'agit d'une erreur, demandez un réexamen. |
| `publication_content` | Publication et contenu | `REMOVE_CONTENT` | Cette mesure concerne ce qui est publié au nom de l'organisation : offres, photos, descriptions, profil ou réponses aux avis. Elle est prise quand un contenu ne respecte pas les règles de publication de Connecte+, par exemple un produit interdit, une information trompeuse, un contenu offensant ou copié. Retirez le contenu concerné si l'action le demande. |
| `commercial_activity` | Activités commerciales, Marketplace et services | `CONTACT_SUPPORT` | Cette mesure concerne la façon dont l'organisation propose ses produits ou services sur Connecte+ : annonces répétées ou trompeuses, prix ou disponibilités non respectés, plaintes répétées de clients, activité différente de celle déclarée. Suivez l'action indiquée pour retrouver un fonctionnement normal. |
| `payments_financial_risk` | Paiements, transactions et risques financiers | `CONTACT_SUPPORT` | Cette mesure concerne des paiements faits sur Connecte+ par l'organisation ou à son profit : contestation, opération signalée par le fournisseur de paiement, risque de fraude financière. Un simple échec de paiement n'entraîne jamais cette mesure. Connecte+ ne détient pas d'argent pour l'organisation. Suivez l'action indiquée. |
| `recruitment_regulated` | Recrutement, prestations et activités réglementées | `SUBMIT_DOCUMENTS` | Cette mesure concerne les offres d'emploi, les appels d'offres, les prestations ou les activités qui demandent une autorisation particulière, comme une licence ou un agrément. Elle est prise quand une annonce ne respecte pas les règles qui s'y appliquent, ou quand une autorisation doit être justifiée. Suivez l'action indiquée, en général fournir le document demandé. |
| `trust_fraud_impersonation` | Confiance, fraude, usurpation et comportement abusif | `CONTACT_SUPPORT` | Cette mesure est prise quand des éléments laissent penser que l'organisation est utilisée pour tromper des utilisateurs, se faire passer pour une autre organisation ou une autre personne, ou harceler. Pour protéger les personnes concernées et l'examen en cours, certains détails peuvent ne pas être communiqués. Ce n'est pas une note sur la qualité de vos produits ou services. Si vous pensez qu'il s'agit d'une erreur, demandez un réexamen. |
| `governance` | Gouvernance de l'organisation | `REGULARIZE_GOVERNANCE` | Cette mesure est prise quand l'organisation n'a plus d'administrateur principal en mesure d'agir, ou quand l'autorité sur l'organisation est contestée. Elle limite certaines actions le temps que l'administration soit régularisée. Quand elle a été posée automatiquement faute d'administrateur principal, elle est levée dès qu'un administrateur principal est de nouveau en place. |
| `other` | Autre motif | `CONTACT_SUPPORT` | Cette mesure ne relève d'aucune des catégories précédentes. Le motif communiqué et l'action indiquée précisent ce qui est attendu. Si rien n'est précisé, adressez-vous à l'aide Connecte+. |

Contrôle : aucune explication ne cite un signal anti-abus précis, un seuil, un tiers ni une sanction de compte.

### 6.2. Mesures (« Ce qui est bloqué »)

Libellé court (badge, liste) et phrase (écran « Restrictions », bannière).

| Mesure | Libellé court | Phrase |
|---|---|---|
| `FULL_SUSPENSION` | Suspension totale | L'organisation est suspendue : son profil et ses offres ne sont plus visibles du public, et personne ne peut agir en son nom. Vous pouvez consulter cet état et quitter l'organisation. |
| `PUBLICATION_BLOCK` | Publication bloquée | Il n'est pas possible de publier, modifier, renouveler ou republier des offres. Les offres déjà en ligne restent visibles ; vous pouvez les mettre en pause ou les supprimer. |
| `PUBLIC_VISIBILITY_HIDDEN` | Profil masqué au public | Le profil et les offres de l'organisation ne sont pas visibles du public. Votre équipe peut continuer à travailler dans l'espace de l'organisation. |
| `CONTACT_BLOCK` | Contact désactivé | Les visiteurs ne peuvent pas obtenir les moyens de contact de l'organisation (appel, WhatsApp, numéro). |
| `MESSAGING_BLOCK` | Messagerie bloquée | Personne ne peut ouvrir de nouvelle conversation avec l'organisation, et l'équipe ne peut pas répondre aux messages. |
| `REVIEW_REPLY_BLOCK` | Réponses aux avis bloquées | Il n'est pas possible de répondre aux avis. Les réponses déjà publiées restent visibles. |
| `TEAM_CHANGES_BLOCK` | Équipe gelée | Il n'est pas possible d'inviter, de nommer ou de retirer des membres, ni de changer leurs rôles. Chacun peut toujours quitter l'organisation. |
| `PROFILE_EDIT_BLOCK` | Modification du profil bloquée | Il n'est pas possible de modifier le profil de l'organisation. Une demande de modification du nom reste possible. |

Périmètre : `ORGANIZATION` → « Toute l'organisation ».

### 6.3. Refus `DENY_RESTRICTION`

**Membres (formulaires) :**

| Mesure | Texte |
|---|---|
| `PUBLICATION_BLOCK` | Publication impossible pour le moment : une restriction s'applique à cette organisation. |
| `MESSAGING_BLOCK` | Réponse impossible pour le moment : la messagerie de cette organisation est restreinte. |
| `REVIEW_REPLY_BLOCK` | Réponse impossible pour le moment : les réponses aux avis sont restreintes pour cette organisation. |
| `TEAM_CHANGES_BLOCK` | Modification de l'équipe impossible pour le moment : une restriction s'applique à cette organisation. |
| `PROFILE_EDIT_BLOCK` | Modification du profil impossible pour le moment. Vous pouvez demander une modification du nom. |
| (toute mesure, rôle Administrateur principal ou Administrateur) | + lien « Voir le détail » vers `/organizations/<id>/restrictions` |
| (autres rôles) | + « Pour en savoir plus, adressez-vous à un administrateur de l'organisation. » |

**Acheteurs (aucune mention de restriction, D4) :**

| Mesure | Texte |
|---|---|
| `CONTACT_BLOCK` | Cette organisation ne peut pas être contactée pour le moment. (clé existante `seller_contact_unavailable`) |
| `MESSAGING_BLOCK` | Il n'est pas possible d'écrire à cette organisation pour le moment. |

### 6.4. Actions requises

| Code | Libellé | Phrase |
|---|---|---|
| `NONE` | Aucune action requise | Vous n'avez rien à faire. La mesure prendra fin à la date indiquée ou après examen. |
| `CONTACT_SUPPORT` | Contacter l'aide Connecte+ | Adressez-vous à l'aide Connecte+ pour connaître la suite. (lien quand L1-21 existe ; texte seul avant) |
| `SUBMIT_DOCUMENTS` | Envoyer des pièces | Envoyez ou mettez à jour les pièces demandées depuis l'onglet Vérification. |
| `REGULARIZE_GOVERNANCE` | Régulariser l'administration | L'organisation doit retrouver un administrateur principal. Suivez la procédure de régularisation de l'administration. |
| `REMOVE_CONTENT` | Retirer un contenu | Retirez le contenu concerné (offre, photo, description ou réponse). |
| `UPDATE_PROFILE` | Mettre à jour le profil | Corrigez les informations du profil de l'organisation. |
| `AWAIT_REVIEW` | Examen en cours | Aucune démarche n'est attendue de votre part : l'équipe Connecte+ examine la situation. |

Le détail facultatif (`required_action_detail`, ≤ 300 caractères) s'affiche sous la phrase.

**Compatibilité mesure × action (proposition pour C1, à valider) :** une action est réalisable seulement si la capacité qu'elle demande n'est pas bloquée.

| Action | Capacité nécessaire | Incompatible avec |
|---|---|---|
| `SUBMIT_DOCUMENTS` | `org.verification_submit` | `FULL_SUSPENSION` |
| `REMOVE_CONTENT` | `offer.delete` (ou retrait de réponse) | `FULL_SUSPENSION` |
| `UPDATE_PROFILE` | `org.edit_profile` | `FULL_SUSPENSION`, `PROFILE_EDIT_BLOCK` |
| `NONE`, `CONTACT_SUPPORT`, `AWAIT_REVIEW`, `REGULARIZE_GOVERNANCE` | aucune capacité d'organisation | aucune |

### 6.5. Recours

| Mode | Texte |
|---|---|
| `SUPPORT_REQUEST` | Vous pouvez demander un réexamen à l'aide Connecte+. |
| `SUPPORT_REQUEST` + échéance | Vous pouvez demander un réexamen à l'aide Connecte+ jusqu'au {{date}}. |
| `NONE` | Aucun réexamen n'est proposé pour cette mesure. |

### 6.6. Divulgation limitée et consigne du personnel

- Membre (`LIMITED`) : « Certains détails ne peuvent pas être communiqués, pour protéger un examen en cours ou d'autres personnes. »
- Consigne du formulaire du personnel (motif et détail) : « Écrivez pour l'organisation. Ne mentionnez ni une autre personne, ni une sanction de compte, ni un moyen d'enquête, ni une preuve interne. Choisissez « divulgation limitée » si le motif ne peut pas être communiqué. »

### 6.7. Écran « Restrictions » et bannières

| Élément | Texte |
|---|---|
| Titre | Restrictions |
| Introduction | Voici les mesures qui s'appliquent à l'organisation, leur raison et ce que vous pouvez faire. |
| Libellés des champs | Statut ; Catégorie ; Ce que cela veut dire ; Motif communiqué ; Ce qui est bloqué ; Périmètre ; Depuis ; Jusqu'au ; Action requise ; Recours |
| Échéance nulle | Jusqu'à décision contraire |
| Statut `ACTIVE` / `LIFTED` / `EXPIRED` | En vigueur / Levée le {{date}} / Terminée le {{date}} |
| État vide | Aucune restriction ne s'applique à cette organisation. |
| Historique | Afficher les restrictions passées |
| Bannière restriction (Administrateur principal, Administrateur) | Une restriction s'applique à cette organisation : {{mesures}}. [Voir le détail et l'action requise] |
| Bannière restriction (autres rôles) | Une restriction s'applique à cette organisation : {{mesures}}. Pour en savoir plus, adressez-vous à un administrateur de l'organisation. |
| Vue suspendue, lien (Administrateur principal, Administrateur) | Voir le détail de la suspension |

### 6.8. Cycle de vie

| Élément | Texte |
|---|---|
| Badges | Active ; Inactive ; Fermeture en cours ; Archivée ; Suspendue (restriction) |
| Bannière inactive (Administrateur principal, Administrateur) | « {{name}} » est considérée comme inactive : elle n'apparaît plus dans l'annuaire des organisations. Son profil et ses offres restent visibles. Confirmez qu'elle est toujours en activité. [Confirmer l'activité] |
| Bannière inactive (autres rôles) | Cette organisation est considérée comme inactive. Un administrateur peut confirmer qu'elle est toujours en activité. |
| Succès « Confirmer l'activité » | Merci. L'organisation est de nouveau active. |
| Dialogue de fermeture : titre | Fermer l'organisation |
| Dialogue : effets | Le profil et les offres de l'organisation ne seront plus visibles du public. Plus personne ne pourra agir en son nom. Son historique est conservé. Tant que la fermeture est en cours, un administrateur principal peut l'annuler. Ensuite, seule une restauration exceptionnelle par l'aide Connecte+ est possible. |
| Dialogue : sous restriction | Les restrictions en cours restent enregistrées après la fermeture. |
| Dialogue : motif (libellé) | Pourquoi fermez-vous l'organisation ? |
| Motifs (`reason_code`) | `activity_ended` : L'activité a cessé ; `duplicate` : C'est un doublon d'une autre organisation sur Connecte+ ; `merged_into_other` : L'organisation a fusionné avec une autre ; `no_longer_needed` : Nous n'utilisons plus Connecte+ pour cette organisation ; `other` : Autre raison |
| Dialogue : mot de passe | Pour confirmer, saisissez votre mot de passe. |
| Dialogue : bouton | Fermer l'organisation |
| Résultat immédiat | Organisation fermée. Elle est maintenant archivée. |
| Bannière fermeture en cours | La fermeture de « {{name}} » a été demandée. Elle prendra effet au plus tôt le {{date}}. [Annuler la fermeture] (Administrateur principal seulement) |
| Fermeture en attente d'obligations | Elle attend la fin des opérations suivantes : {{liste}}. |
| Succès de l'annulation | La fermeture a été annulée. L'organisation est de nouveau active. |
| Vue archivée : corps | Son profil et ses offres ne sont plus visibles du public. Elle ne peut plus être modifiée. Son historique est conservé. |
| Vue archivée : recours (Administrateur principal) | Une organisation archivée ne peut pas être rouverte depuis l'application. En cas d'erreur, ou si la fermeture a été faite sans autorité, une restauration exceptionnelle peut être demandée à l'aide Connecte+. |
| Vue archivée : recours (autres rôles) | Pour toute question, adressez-vous à un administrateur principal de l'organisation. (inchangé) |
| Capacité `org.archive` | Fermer l'organisation |

**Obligations ouvertes (`pending_obligations`) :** `payments_open` : un paiement en cours ; `refunds_open` : un remboursement en cours ; `tickets_sold` : des billets vendus pour un événement à venir ; `subscriptions_active` : des abonnements en cours ; `provider_unavailable` : une vérification n'a pas pu être faite, elle sera relancée automatiquement.

### 6.9. Libellés du personnel (back-office)

- **Archivage par le personnel :** `duplicate` Doublon ; `fraud_confirmed` Fraude établie ; `legal_decision` Décision d'une juridiction ou d'une autorité ; `orphaned_unresolved` Administration non régularisée ; `other` Autre.
- **Levée :** `resolved` Situation régularisée ; `appeal_upheld` Réexamen favorable ; `issued_in_error` Posée par erreur ; `superseded` Remplacée par une autre mesure ; `governance_restored` Administration régularisée ; `reverification_done` Revérification faite ; `expired` Échéance atteinte ; `other` Autre.
- **Restauration, motif de la demande :** `archiving_error` Erreur d'archivage ; `technical_error` Erreur technique ou administrative ; `closure_without_authority` Fermeture faite sans autorité valable ; `legitimate_contest` Contestation légitime ; `other` Autre cas justifié.
- **Restauration, contrôles :** Les données nécessaires existent encore ; L'organisation est identifiée ; L'autorité actuelle du représentant est établie ; Les sanctions et restrictions en cours ont été examinées ; Revérification nécessaire (coché par défaut).
- **Restauration, décision :** `restored` Restauration accordée ; `authority_not_established` Autorité du demandeur non établie ; `data_unavailable` Données nécessaires indisponibles ; `restriction_prevents` Une restriction en cours s'y oppose ; `new_entity_required` Nouvelle entité : une nouvelle organisation doit être créée ; `other` Autre.

### 6.10. Changement de nom

| Élément | Texte |
|---|---|
| Lien depuis le nom verrouillé | Demander une modification du nom |
| Message du nom verrouillé (`orgEdit.nameLocked`, remplace le texte actuel) | Le nom est verrouillé depuis la vérification. Pour le changer, faites une demande de modification du nom. |
| Idem, pièce en cours d'examen (`nameLockedPending`) | Le nom est verrouillé tant qu'une pièce de vérification est en cours d'examen ou validée. Pour le changer, faites une demande de modification du nom. |
| Titre du formulaire | Demander une modification du nom |
| Introduction | Le nom de l'organisation a été vérifié : il ne se modifie plus directement. L'équipe de vérification de Connecte+ examinera votre demande. Le nom actuel reste affiché jusqu'à la décision. |
| Type `TYPO_CORRECTION` | Corriger une faute de frappe — Une erreur d'orthographe ou de saisie dans le nom. Aucune pièce n'est demandée. |
| Type `DISPLAY_NAME_CHANGE` | Changer le nom d'affichage — Le nom sous lequel l'organisation apparaît sur Connecte+ change, sa dénomination légale reste la même. Une pièce peut être demandée. |
| Type `LEGAL_NAME_CHANGE` | Changer la dénomination légale — Le nom enregistré de l'organisation a changé (RCCM, arrêté…). Une pièce officielle portant le nouveau nom est obligatoire. |
| Avertissement nouvelle entité | S'il s'agit d'une autre entité (nouvelle société, nouvelle association), ne faites pas de demande : créez une nouvelle organisation. Un changement de nom ne transfère ni vérification, ni avis, ni historique d'une organisation à une autre. |
| Motifs (`reason_code`) | `typo` Faute de frappe ou d'orthographe ; `rebranding` Nouveau nom commercial ; `legal_rename` Changement de dénomination enregistré ; `legal_form_change` Changement de forme juridique ; `other` Autre raison |
| Champ note | Précisions (facultatif, 500 caractères au plus). Ne donnez pas d'informations sur d'autres personnes. |
| Dénomination légale (champ du profil) | Dénomination légale — Le nom exact inscrit au registre (RCCM, arrêté d'enregistrement). Elle n'est pas affichée sur le profil public. |
| Statuts | `DOCUMENTS_REQUIRED` Pièces à fournir ; `PENDING_REVIEW` En cours de vérification ; `COMPLETED` Acceptée ; `REJECTED` Refusée ; `CANCELLED` Annulée ; `VOID` Close sans suite |
| Pièces à fournir | Ajoutez une pièce qui montre le nouveau nom, par exemple un RCCM ou un arrêté mis à jour. |
| Suivi en cours | Demande en cours de vérification. Nom proposé : « {{proposed}} ». |
| Motifs de refus | `documents_insufficient` Les pièces fournies ne suffisent pas à justifier le changement. ; `authority_not_established` L'autorité de la personne qui demande n'a pas pu être établie. ; `new_entity_required` Le nouveau nom correspond à une autre entité. Créez une nouvelle organisation : rien n'est transféré par un changement de nom. ; `protected_name_conflict` Le droit d'utiliser ce nom n'a pas été établi. ; `other` La demande n'a pas pu être acceptée. Pour en savoir plus, adressez-vous à l'aide Connecte+. |
| Clôture sans suite | `organization_unavailable` L'organisation est en cours de fermeture ou archivée. ; `name_changed_meanwhile` Le nom a été modifié entre-temps. ; `superseded` Remplacée par une autre demande. |

### 6.11. Codes d'erreur nouveaux ou modifiés

| Code | Texte |
|---|---|
| `DENY_RESTRICTION` | Voir 6.3 (par mesure). |
| `closure_already_requested` | La fermeture de cette organisation est déjà demandée. |
| `closure_not_pending` | Aucune fermeture n'est en cours pour cette organisation. |
| `organization_not_dormant` | Cette organisation est déjà active. |
| `name_change_not_required` | Le nom n'est pas verrouillé : vous pouvez le modifier directement dans le profil. |
| `name_change_already_open` | Une demande de modification du nom est déjà en cours. |
| `name_change_not_open` | Cette demande n'est plus en cours. |
| `name_change_request_not_found` | Demande introuvable. |
| `nothing_to_change` | Indiquez un nom différent du nom actuel. |
| `name_locked_by_verification` | Le nom est verrouillé depuis la vérification. Faites une demande de modification du nom. |

### 6.12. Notifications (reprend ADR 0011 §7 ; textes complétés)

| Événement | Destinataires | Texte |
|---|---|---|
| Suspension totale posée | tous les membres actifs | L'organisation « {name} » a été suspendue : ses offres ne sont plus publiques. (+ Administrateur principal, Administrateur : « Consultez le détail et l'action requise. ») |
| Restriction ciblée posée | Administrateur principal, Administrateur | Une restriction s'applique à « {name} ». Consultez le détail et l'action requise. |
| Restriction modifiée (proposé) | Administrateur principal, Administrateur | La restriction appliquée à « {name} » a été mise à jour. Consultez le détail. |
| Restriction levée ou terminée | mêmes destinataires que la pose | La restriction appliquée à « {name} » a été levée. / texte existant « réactivée » pour la dernière suspension |
| Fermeture demandée | tous les membres actifs | La fermeture de « {name} » a été demandée. Elle prendra effet au plus tôt le {date}. |
| Fermeture annulée | tous les membres actifs | La fermeture de « {name} » a été annulée. |
| Archivée (fermeture ou personnel) | tous les membres actifs | texte existant « archivée » |
| Archivée faute d'administrateur principal | tous les membres actifs | « {name} » a été archivée faute d'administrateur principal. Une restauration peut être demandée à l'aide Connecte+. |
| Inactive | Administrateur principal, Administrateur | « {name} » est considérée comme inactive. Confirmez qu'elle est toujours en activité. |
| Restaurée | membres actifs, demandeur | « {name} » a été restaurée. (+ si revérification : « Elle redeviendra visible du public après vérification. ») |
| Restauration refusée | demandeur | Votre demande de restauration de « {name} » n'a pas été acceptée. Pour en savoir plus, adressez-vous à l'aide Connecte+. |
| Nom : pièces à fournir | demandeur, Administrateur principal, Administrateur | Des pièces sont nécessaires pour examiner la demande de modification du nom de « {name} ». |
| Nom : accepté | idem | Le nom de l'organisation est désormais « {name} ». |
| Nom : refusé | idem | La demande de modification du nom de « {name} » n'a pas été acceptée. Le motif est indiqué dans l'espace de l'organisation. |

### 6.13. Textes existants à remplacer (`frontend/src/i18n/locales/fr.ts`)

| Clé | Ancien | Nouveau |
|---|---|---|
| `org.unavailable.recourse.ARCHIVED.OWNER` | Un archivage ne peut pas être annulé depuis l'application. Pour toute question, contactez le support de Connecte+. | Texte 6.8 « Vue archivée : recours (Administrateur principal) ». |
| `orgEdit.nameLocked`, `orgEdit.nameLockedPending` | … contactez le support de Connecte+. | Textes 6.10. |
| `capability.archive`, `org.home.archiveTitle` | Archiver l'organisation | Fermer l'organisation |
| `org.home.archiveBody` | Réservé aux administrateurs principaux. Les offres de l'organisation ne seront plus visibles. | Réservé aux administrateurs principaux. Le profil et les offres ne seront plus visibles du public ; l'historique est conservé. |
| `org.unavailable.archivedDone` | Organisation archivée. | Organisation fermée. Elle est maintenant archivée. |

`orgEdit.nifLocked` renvoie encore au support : hors périmètre (DOC-02, L1-21), à signaler.

---

## 7. Contradictions et risques détectés (pour le chef de projet)

| # | Constat | Options | Recommandation |
|---|---|---|---|
| **C1** | Le contrat §2.1 donne en exemple `FULL_SUSPENSION` + `SUBMIT_DOCUMENTS`. Or sous suspension totale, `org.verification_submit` est refusé (ADR §4.2) : l'action requise est impossible. Même problème pour `REMOVE_CONTENT` et `UPDATE_PROFILE` sous suspension, et `UPDATE_PROFILE` sous `PROFILE_EDIT_BLOCK`. Q33 exige une « action disponible ». | (a) Validation en service : combinaisons interdites (table 6.4) ; exemple du contrat corrigé. (b) Ajouter `org.verification_submit` aux capacités permises sous suspension totale. (c) Les pièces passent par l'aide. | (a) en V1, plus simple et sans nouvelle ouverture ; (b) à étudier avec l'auditeur si le cas « suspendu pour pièces » est fréquent. À trancher avant L1-19-B2 (architecte). |
| **C2** | Le contrat §5 renvoie à un **acheteur** `403 DENY_RESTRICTION` + `measure = CONTACT_BLOCK`. L'ADR D4 et le contrat §5 disent « aucune réponse publique ne mentionne une restriction ». La clé `measure` révèle l'existence d'une sanction à un tiers. | (a) Garder, le front affiche un texte neutre (6.3). (b) Renvoyer à l'acheteur le code neutre existant (`seller_contact_unavailable` ou équivalent), sans `measure`. | (b), plus conforme à la règle 10 et à D4 ; à défaut (a) minimum. À trancher avant B2 (architecte, revue S-L17-2). |
| **C3** | Le dialogue de fermeture ne peut pas dire si la fermeture est immédiate ou différée : `closure_delay_days` n'est exposé par aucune route avant la demande. | (a) Exposer le délai (clé additive dans `internal/` pour l'Administrateur principal). (b) Texte générique « immédiatement ou à la date indiquée ». | (a), additif. À trancher avant F-L17-3. |
| **C4** | Q34 demande de revérifier après restauration « admins, délégations, contacts, licences, destinations de paiement ». L'ADR couvre visibilité, contact et gouvernance ; ni licences (L1-02b, L1-04b) ni destinations de paiement (L1-12). | Interfaces à ajouter dans ces tâches. | Noter dans les briefs de L1-02b et L1-12. |
| **C5** | `MESSAGING_BLOCK` : l'ADR bloque les nouvelles conversations et les réponses de l'équipe ; rien n'est dit des **messages d'un acheteur dans une conversation existante**. | (a) Acceptés (l'équipe ne peut pas répondre). (b) Refusés. | (b), pour ne pas laisser un acheteur écrire sans réponse possible ; texte acheteur 6.3. À trancher avant B2. |
| **C6** | Un membre d'une organisation archivée par le personnel ne sait pas que l'archivage vient de Connecte+ (motif non exposé). Q33 vise les suspensions, Q34 la traçabilité interne. | (a) Rien de plus. (b) Exposer `lifecycle.reason` (`member_closure`, `orphaned`, `staff_decision`) aux Administrateurs principaux et Administrateurs. | (b) avec un texte neutre « archivée par décision de Connecte+ » ; question utilisateur (QU-1). |
| **C7** | Le contrat §9 nomme le statut « Dormante » ; Q34 dit « Inactive/dormante ». | — | « Inactive » à l'écran (plus clair) ; « dormante » reste interne. Pour D-L17. |
| **C8** | Le contrat §4.3 ne donne pas le code de refus quand un Administrateur non demandeur annule une demande de nom. | `403 DENY_PERMISSION` ou `404 name_change_request_not_found`. | `403 DENY_PERMISSION` (l'Administrateur voit déjà la demande). Architecte. |
| **C9** | CDC §3.17 cite un rôle interne « support » ; l'ADR n'en donne aucune permission. La demande de restauration, reçue par l'aide, est enregistrée par le groupe « Vérification ». | — | Cohérent en V1 ; à revoir avec L1-21 et DOC-03. |
| **R1** | Les restrictions converties sont `LIMITED` + « Autre motif » : l'Administrateur principal d'une organisation convertie lira peu d'information. | — | Accepté (règle 10 : la cause est souvent la sanction d'une autre personne). Le personnel requalifie au besoin. |
| **R2** | Tant que L1-21 n'existe pas, « Contacter l'aide Connecte+ » et « demander un réexamen » sont du texte sans lien. Q19 exige un canal avant le lancement. | — | L1-21 avant la production. |

---

## 8. Proposition de modification du CDC (diff texte, non appliquée)

Ce diff **remplace** la puce « Cycle de vie et suspension » proposée dans `impact-reponses-client-Q1-Q36.md` §4 ; les autres propositions de ce document restent valables.

**§0.4 Glossaire — ajouter**
- Nouveau : `Restriction | Mesure prise par Connecte+ sur une organisation : suspension totale ou blocage d'une fonction (publication, contact, messagerie, réponses aux avis, équipe, profil, visibilité). Elle porte une catégorie, un motif communiqué, une date, une action requise et un recours.`
- Nouveau : `Cycle de vie | État opérationnel d'une organisation : active, inactive, fermeture en cours, archivée, supprimée. Il est indépendant des restrictions.`

**§3.1 — Organisations, puce « Une vérification ne s'achète jamais »**
- Ancien : `Une vérification ne s'achète jamais ; un plan payant ne la modifie pas.`
- Nouveau : `Une vérification ne s'achète jamais ; un plan payant ne la modifie pas et ne lève aucune restriction.`

**§3.1 — Organisations, ajouter trois puces**
- Nouveau : `Cycle de vie : active, inactive (longue absence d'activité : l'organisation sort de l'annuaire mais garde son profil et ses offres ; elle redevient active en confirmant son activité), fermeture en cours, archivée, puis supprimée ou anonymisée selon la politique de conservation. Seul un administrateur principal ferme l'organisation, avec son mot de passe et un motif ; il peut annuler tant que la fermeture est en cours. Les délais (inactivité, fermeture, organisation sans administrateur principal) sont configurables et désactivés tant qu'ils ne sont pas validés.`
- Nouveau : `Restrictions et suspensions : séparées du cycle de vie et de la gouvernance. Connecte+ peut suspendre toute l'organisation ou bloquer une seule fonction. Les administrateurs principaux et administrateurs voient la catégorie, une explication, le motif communiqué (sauf divulgation limitée), ce qui est bloqué, la date, l'échéance, l'action requise et le recours ; les autres membres voient seulement ce qui est bloqué ; le public voit seulement que l'organisation ou la fonction est indisponible. Un échec de paiement ne suspend jamais une organisation. Remplacer l'administrateur principal ne lève pas une restriction indépendante. Une organisation restée sans administrateur principal peut être restreinte puis archivée.`
- Nouveau : `Restauration et nom : une organisation archivée peut être restaurée à titre exceptionnel par le personnel (demande reçue par l'aide, contrôles par une personne, décision par une autre, audit) ; c'est le même objet, avec son historique, et une revérification peut être exigée. Après suppression ou anonymisation, la restauration est impossible. Le nom vérifié ne se modifie que par une demande contrôlée (correction typographique, nom d'affichage ou dénomination légale), avec justificatifs et décision de l'équipe de vérification ; le nom actuel reste affiché pendant l'examen. Une nouvelle entité crée une nouvelle organisation : rien n'est transféré par renommage.`

**§3.17 — ligne « Vérifications »**
- Ancien : `File KYC/KYB, consultation des pièces, validation ou refus motivé, badge précis`
- Nouveau : `File KYC/KYB, consultation des pièces, validation ou refus motivé, badge précis ; demandes de modification du nom ; préparation des restaurations d'organisation`

**§3.17 — ligne « Modération »**
- Ancien : `Signalements (offres, avis, profils, messages), validation des campagnes ONG, sanctions, recours`
- Nouveau : `Signalements (offres, avis, profils, messages), validation des campagnes ONG, sanctions des comptes, restrictions et suspensions d'organisation (catégories configurables), archivage et décision de restauration d'une organisation (double contrôle), recours`

**§3.17 — ligne « Paramètres »**
- Ancien : `Pondérations du classement, durées d'expiration, seuils anti-abus`
- Nouveau : `Pondérations du classement, durées d'expiration, seuils anti-abus, délais du cycle de vie des organisations (inactivité, fermeture, organisation sans administrateur principal, validité d'une demande de restauration)`

**§5.6 — ajouter deux lignes**
- Nouveau : `Expiration des restrictions d'organisation et resynchronisation | Toutes les 10 minutes`
- Nouveau : `Cycle de vie des organisations (fin de fermeture, inactivité, organisations sans administrateur principal, demandes de restauration échues) | Toutes les heures`

**§11.1 — ligne `identity`**
- Ancien : `User, Context, Organization, Membership, Role, VerificationRequest, OtpCode`
- Nouveau : `User, Context, Organization, Membership, Role, VerificationRequest, OtpCode, RestrictionCategory, OrganizationRestriction, OrganizationLifecycleTransition, OrganizationRestorationRequest, OrganizationNameChangeRequest, OrganizationNameHistory`

**§11.2 — ajouter**
- Nouveau : `OrganizationLifecycleChanged / OrganizationRestrictionChanged / OrganizationRestorationChanged / OrganizationNameChangeChanged | identity | notifications (plus tard payments, events)`

---

## 9. Lignes proposées pour le backlog (non appliquées)

| ID | Tâche | Agents | Statut proposé | Réf. |
|---|---|---|---|---|
| A-L17 | Stories, critères et textes L1-17/19/20 ; diff CDC | analyste-fonctionnel | Fait (`docs/specs/L1-17-cycle-de-vie-organisations.md`) | ADR 0011 |
| A-L17-C | Trancher C1, C2, C5, C8 (contrat v1.1) avant L1-19-B2 ; C3 avant F-L17-3 | architecte-technique | À faire | ADR 0011, contrat L1-17 |
| CDC-L17 | Appliquer le diff §8 au CDC (sur accord) | analyste-fonctionnel | À faire | §3.1, §3.17, §5.6, §11 |
| SEED-L17 | Saisir les explications 6.1 en back-office avant la production | personnel (ou migration de données) | À faire | règle 11 |

---

## 10. Questions

### 10.1. Pour le client (via l'utilisateur)

| # | Question | Bloquant ? | Recommandation |
|---|---|---|---|
| **QO-8** | Durées : inactivité ; délai avant restriction puis archivage d'une organisation sans administrateur principal. | Non (livré à 0, désactivé) | Proposition de l'équipe : 365 jours ; 30 jours ; 180 jours. |
| **QC-1** | Confirmer les recommandations marquées « client » de l'ADR 0011 §17 : QL-1 (effets de l'inactivité), QL-3 (fermeture sous suspension), QL-5 (ancien nom affiché pendant l'examen), QL-7 (modérateur sans pouvoir de restriction en V1), QL-8 (9 catégories), QL-10 (revérification par défaut après restauration), QL-11 (autres rôles : mesures sans motif), QL-13 (dénomination légale). | Non (appliquées en attendant) | Valider en bloc. |
| **QC-2** | Valider les 9 explications de catégorie (6.1), en attendant la Matrice Sanctions (DOC-01). | Non (avant production) | Valider ou amender. |
| **QC-3** | Justificatifs acceptés pour un changement de dénomination selon les formes d'entités en RDC (Q35 ⚖️). | Non (avant production) | Liste par forme, dans la matrice documentaire (L1-02b). |
| **QC-4** | Un changement de forme juridique (par exemple SARL en SA) est-il un changement de nom de la même entité, ou une nouvelle entité ? | Non | Avis juridique ; d'ici là, traité comme `LEGAL_NAME_CHANGE` avec pièce obligatoire. |
| **QC-5** | Que deviennent les droits commerciaux (plan, promotion) d'une organisation fermée ? | Non (L1-12) | Aucun remboursement automatique ; à fixer avec L1-12. |
| **QC-6** | Faut-il communiquer au demandeur le motif du refus d'une restauration ? | Non | Oui, motif codé neutre (liste 6.9) par l'aide. |
| **QC-7** | Délai de recours par défaut d'une restriction (ou aucun) ? | Non | Aucun délai par défaut en V1 ; défini par DOC-01. |

### 10.2. Pour l'utilisateur ou le chef de projet

| # | Question | Recommandation |
|---|---|---|
| **QU-1** | C6 : dire aux administrateurs qu'un archivage vient de Connecte+ ? | Oui, texte neutre. |
| **QU-2** | Notifier la modification d'une restriction (`updated`) ? | Oui, Administrateur principal et Administrateur. |
| **QU-3** | C1, C2, C5, C8 à faire trancher par l'architecte avant L1-19-B2 ; C3 avant F-L17-3. | Brief architecte A-L17-C. |
