**MANUEL BACK-OFFICE & OPÉRATIONS DE LA PLATEFORME**

**Plateforme Écosystème RDC**

*Document 09 - Administration, files de travail, contrôles et procédures V1*

Version de référence V1 / Post-V1 - Septembre 2026

# 1. Objet et principes

Ce manuel définit le fonctionnement quotidien du back-office: qui traite quoi, dans quelle file, avec quelles permissions, quelles preuves, quels contrôles et quel audit. Le back-office n'est pas un super-compte. Chaque membre du personnel agit dans un rôle interne limité par module, action, scope, finalité et niveau de sensibilité.

- Moindre privilège: aucun accès staff global par défaut.

- Séparation des fonctions: support, vérification, modération, finance, sécurité, taxonomie et administration ont des responsabilités distinctes.

- Case-first: toute intervention significative sur un utilisateur, paiement, vérification ou contenu doit être reliée à un dossier, événement ou motif auditable.

- Four-eye: les opérations à fort impact utilisent un second contrôle selon seuil/politique.

- Pas de modification silencieuse: les corrections créent un historique avant/après.

- Les décisions commerciales ne peuvent jamais acheter une décision de confiance, sécurité ou modération.

- Les données privées ne sont affichées au staff que lorsqu'elles sont nécessaires à la tâche.

# 2. Carte du back-office V1

| **Espace**           | **Fonction principale**                       | **Utilisateurs internes** |
|----------------------|-----------------------------------------------|---------------------------|
| Ops Home             | Vue d'ensemble, alertes, files et SLA         | Leads/ops selon scope     |
| Support Cases        | Questions, interactions, incidents ordinaires | Support                   |
| Trust & Verification | Identité, organisation, autorité, références  | Verification reviewers    |
| Moderation           | Contenus, spam, comportements                 | Moderators                |
| Safety               | Cas urgents/personnes vulnérables             | Safety/Trust restreint    |
| Commerce Ops         | Commandes, food, delivery exceptions          | Commerce support          |
| Finance Ops          | Paiements, refunds, reconciliation            | Finance                   |
| Organization Claims  | Revendications/autorité organisation          | Trust + org ops           |
| Taxonomy Center      | Catégories, attributs, aliases, policy states | Taxonomy admins           |
| Plans & Entitlements | Produits, quotas, règles commerciales         | Commercial/admin autorisé |
| Promotion            | Campagnes sponsorisées, crédits, éligibilité  | Commercial ops            |
| Market Configuration | Règles pays/marché, features, providers       | Platform admins           |
| Audit & Security     | Logs, incidents, actions privilégiées         | Security/audit            |
| Staff & Access       | Rôles internes et scopes                      | Restricted administrators |

# 3. Rôles internes et séparation des fonctions

| **Rôle**              | **Peut principalement**              | **Ne doit pas automatiquement**              |
|-----------------------|--------------------------------------|----------------------------------------------|
| Support Agent         | Traiter cases et contexte nécessaire | Voir pièces identité, approuver gros refunds |
| Commerce Ops          | Exceptions commandes/livraisons      | Modifier verification                        |
| Verification Reviewer | Examiner preuves assignées           | Voir billing complet ou CV sans finalité     |
| Moderator             | Traiter contenu/comportement         | Effectuer overrides financiers               |
| Safety Specialist     | Cas sécurité graves                  | Accès commercial sans besoin                 |
| Finance Ops           | Paiements, refunds, reconciliation   | Lire messages privés/CV hors case            |
| Taxonomy Admin        | Catégories, attributs, policy states | Voir PII utilisateurs                        |
| Commercial Admin      | Plans, quotas, promotion             | Accorder permissions org ou verification     |
| Platform Config Admin | Features, marchés, providers         | Traiter cas métier ordinaires                |
| Security/Audit        | Incidents, logs, accès privilégiés   | Altérer preuves/audit                        |
| Ops Lead              | Supervision, réassignation, escalade | Bypass automatique des contrôles             |

# 4. Ops Home - tableau de pilotage

| **Bloc**             | **Contenu**                               | **Règle**                             |
|----------------------|-------------------------------------------|---------------------------------------|
| À traiter            | Files assignées à l'utilisateur/équipe    | Pas de données hors scope             |
| Urgences             | P0/P1 safety, security, payment anomalies | Toujours avant priorités commerciales |
| SLA                  | Cases proches/en dépassement              | Seuils configurables                  |
| Finance exceptions   | ReconciliationRequired, refunds failed    | Finance scope                         |
| Verification backlog | Pending/NeedsReview/expirations           | Trust scope                           |
| Moderation backlog   | Reports/appeals                           | Moderation scope                      |
| System health        | Providers, queues, webhook failures       | Ops/technical summary                 |
| Change calendar      | Policy/config releases planifiées         | Admins autorisés                      |

# 5. Case Management - objet central

| **Champ**           | **Exigence**                                                                                |
|---------------------|---------------------------------------------------------------------------------------------|
| case_id             | Stable et unique                                                                            |
| case_type           | Support, interaction, safety, moderation, verification, commerce, payment, appeal, security |
| priority            | P0/P1/P2/P3                                                                                 |
| subject/object refs | Utilisateur, org, order, payment, listing, job, event, etc.                                 |
| parties             | Parties impliquées avec rôle dans le case                                                   |
| owner/team          | Responsable actuel                                                                          |
| status              | Open, WaitingUser, WaitingProvider, InReview, Escalated, Resolved, Closed                   |
| reason codes        | Catégorie structurée                                                                        |
| evidence refs       | Pièces nécessaires, privées                                                                 |
| actions             | Journal chronologique                                                                       |
| resolution          | Décision/résultat structuré                                                                 |
| SLA timestamps      | Création, first response, due, resolved                                                     |
| appeal link         | Lien vers contestation éventuelle                                                           |

# 6. Workflow Support

| **Étape**            | **Action**                                                          |
|----------------------|---------------------------------------------------------------------|
| Intake               | Identifier utilisateur, objet et catégorie; éviter doublons.        |
| Authenticate context | Vérifier que le demandeur peut recevoir les informations demandées. |
| Triage               | Priorité, équipe, SLA, besoin d'escalade.                           |
| Investigate          | Consulter uniquement données nécessaires.                           |
| Resolve              | Réponse, correction autorisée, ou passage à équipe spécialisée.     |
| Communicate          | Message clair, sans exposer données d'une autre partie.             |
| Close                | Reason/resolution code + notes + satisfaction optionnelle.          |
| Reopen               | Permis selon politique/nouvelle information.                        |

# 7. Verification Queue

| **État** | **Action staff**                            | **Sortie**                           |
|----------|---------------------------------------------|--------------------------------------|
| Pending  | Vérifier complétude et type de preuve       | InReview / MoreInfo                  |
| InReview | Comparer preuve aux critères/version policy | Verified / Failed / MoreInfo         |
| MoreInfo | Demander information précise                | Retour Pending/InReview              |
| Verified | Créer/mettre à jour Verification Record     | Public claim autorisé                |
| Failed   | Reason code + explication appropriée        | Pas de badge                         |
| Expired  | Demander renouvellement si requis           | Statut public ajusté                 |
| Revoked  | Preuve invalide/compromise                  | Audit + notification + éventuel case |

Le reviewer ne choisit jamais un statut parce que l'utilisateur paie. Le système doit afficher le produit commercial séparément des preuves.

# 8. Organization Claim & Authority Review

| **Contrôle**           | **Exemples de preuve**                                  | **Décision**                             |
|------------------------|---------------------------------------------------------|------------------------------------------|
| Existence organisation | Registre/document/site/contact autorisé selon politique | Existence checked / MoreInfo             |
| Identité du demandeur  | Verification Record approprié                           | Continue/stop                            |
| Lien avec organisation | Fonction, mandat, contact organisation                  | Authority verified/failed                |
| Conflit claim          | Claim existant ou contestation                          | Escalation; pas d'écrasement automatique |
| Scope d'autorité       | Organisation/branche/opération                          | Créer membership/role limité             |
| Changement owner/admin | Preuve renforcée + audit                                | Four-eye si contesté/sensible            |

# 9. Moderation Queue

| **Action**            | **Règle**                                                                  |
|-----------------------|----------------------------------------------------------------------------|
| Open report           | Voir contenu signalé, raison, contexte nécessaire.                         |
| Deduplicate           | Regrouper reports sur même objet sans perdre reporters.                    |
| Assess                | Appliquer policy version et marché.                                        |
| Temporary restriction | Seulement proportionnée au risque.                                         |
| Decision              | No action, warning, edit request, remove, feature restriction, suspension. |
| Notify                | Reason code et voie d'appel si applicable.                                 |
| Appeal                | Nouvelle revue appropriée; historique initial conservé.                    |
| Pattern flag          | Répétitions peuvent déclencher suspicious review, pas score universel.     |

# 10. Safety Queue

| **Priorité** | **Exemple**                                            | **Procédure**                                        |
|--------------|--------------------------------------------------------|------------------------------------------------------|
| P0           | Menace immédiate, exploitation, compromission critique | Escalade immédiate; containment; préserver preuves   |
| P1           | Fraude active importante, accès données sensibles      | Restriction préventive proportionnée + investigation |
| P2           | Harcèlement, conflit sérieux sans danger immédiat      | Traitement prioritaire standard                      |
| P3           | Spam/qualité faible                                    | Batch/asynchrone possible                            |

Les procédures impliquant autorités publiques, obligations de signalement ou mineurs doivent être validées juridiquement avant lancement.

# 11. Commerce Operations Queue

| **Exception**          | **Vue staff**                                     | **Action possible**                              |
|------------------------|---------------------------------------------------|--------------------------------------------------|
| Seller non-fulfillment | Order, payment, messages contextuels, fulfillment | Contact, case, refund workflow                   |
| Food decline/failure   | Food Order + payment + restaurant state           | Resolution/refund                                |
| Delivery failure       | Delivery Request + order                          | Reassign/return/case selon règle                 |
| Cash disagreement      | Collector, confirmations, amounts                 | Evidence + resolution; pas d'édition silencieuse |
| Stock oversell         | Reservation/history                               | Cancel/refund/merchant review                    |
| Ticket issue           | Ticket Order, payment, ticket/check-in            | Corrective workflow                              |
| Event cancellation     | Affected tickets/payments                         | Batch cases/refund workflow                      |

# 12. Finance Operations

| **Queue**               | **Déclencheur**                  | **Action**                                    |
|-------------------------|----------------------------------|-----------------------------------------------|
| Payment Pending aged    | Pending au-delà seuil            | Provider query/reconciliation                 |
| ReconciliationRequired  | Local/provider incohérent        | Comparer sources autoritatives                |
| Duplicate charge        | Deux paiements réels             | Case + refund approprié                       |
| Refund Requested        | Case/policy approuvable          | Review/approve selon seuil                    |
| Refund Failed           | Provider failure                 | Retry contrôlé/escalation                     |
| Unauthorized allegation | Utilisateur conteste transaction | Case + provider/security                      |
| Cash discrepancy        | Montant/statut contesté          | Audit collector + case                        |
| Platform Billing issue  | Subscription/pass/promotion      | Corriger entitlement via transaction vérifiée |

# 13. Refund approvals et four-eye

| **Niveau**                                   | **Exemple de contrôle**                                    |
|----------------------------------------------|------------------------------------------------------------|
| Faible montant / règle automatique autorisée | Workflow standard selon policy.                            |
| Montant supérieur au seuil                   | Second approver requis.                                    |
| Override financier                           | Toujours reason + case + audit; rôle restreint.            |
| Refund partiel répété                        | Vérifier cumul remboursable.                               |
| Event mass refund                            | Batch contrôlé + rapport de rapprochement.                 |
| Provider exception                           | Ne jamais marquer Refunded sans confirmation autoritative. |

# 14. Reconciliation Console

| **Colonne/outil**  | **Utilité**                                       |
|--------------------|---------------------------------------------------|
| Internal status    | État Payment/Refund local                         |
| Provider status    | Dernier statut vérifié                            |
| Amount/currency    | Comparer exactement                               |
| Provider reference | Rapprochement                                     |
| Last webhook/query | Diagnostic                                        |
| Mismatch reason    | Classification exception                          |
| Action             | Re-query, link case, submit controlled correction |
| Audit trail        | Avant/après + acteur/source                       |

# 15. Taxonomy Center

| **Action**        | **Règle**                                                     |
|-------------------|---------------------------------------------------------------|
| Créer catégorie   | ID canonique stable; labels séparés.                          |
| Renommer          | Ne pas changer l'ID; versionner label.                        |
| Réordonner        | Configuration UI/search sans migration métier.                |
| Désactiver        | Ne pas supprimer objets historiques.                          |
| Fusionner         | Mapping/migration explicite.                                  |
| Aliases           | FR/EN/local/common terms validés.                             |
| Attributs/filtres | Associer par catégorie/type contenu.                          |
| Applicabilité     | Définir profils/objets autorisés.                             |
| Policy state      | Allowed / Restricted / Verification Required / Not Permitted. |
| Publish version   | Validation, changelog, rollback plan.                         |

# 16. Plans, Passes & Entitlements Console

| **Action**               | **Contrôle**                                                               |
|--------------------------|----------------------------------------------------------------------------|
| Créer/modifier produit   | Versionné; prix/devise/marché configurables.                               |
| Modifier quota           | Affecte nouvelles périodes selon politique; éviter surprises rétroactives. |
| Activer/désactiver offre | Feature flag/catalog state.                                                |
| Grant manuel             | Exception très restreinte, reason + expiry + audit.                        |
| Revoke entitlement       | Reason; ne modifie pas permissions/verification.                           |
| Voir consommation        | Usage vs limit.                                                            |
| Changer prix             | Ne nécessite pas release mobile.                                           |
| Migration plan           | Règles explicites pour abonnés existants.                                  |

# 17. Promotion Operations

| **Contrôle**         | **Règle**                                                                   |
|----------------------|-----------------------------------------------------------------------------|
| Éligibilité objet    | Actif, conforme, public et catégorie promouvable.                           |
| Ownership/permission | Seul owner/manager autorisé.                                                |
| Paiement/crédit      | Entitlement ou transaction valide.                                          |
| Période              | Start/end explicites.                                                       |
| Label                | Toujours Sponsorisé/équivalent.                                             |
| Safety/moderation    | Une promotion peut être stoppée si objet devient non conforme.              |
| Reporting            | Impressions/clicks/actions selon métriques disponibles.                     |
| No endorsement       | Promotion ne change ni verification ni classement organique non sponsorisé. |

# 18. Market & Feature Configuration

| **Paramètre**       | **Exemples**                     | **Gouvernance**              |
|---------------------|----------------------------------|------------------------------|
| Market              | RDC/Kinshasa puis autres marchés | Versionné                    |
| Currency            | USD/CDF selon produit/provider   | Finance/config               |
| Payment provider    | Mobile Money adapters            | Technical + finance approval |
| Feature flag        | Module/feature activé par marché | Release governance           |
| Category policy     | Restricted/not permitted         | Trust/legal/taxonomy         |
| Commercial products | Plans/passes disponibles         | Commercial admin             |
| Legal text version  | Terms/privacy notices            | Legal validation             |
| Localization        | FR/EN et autres langues          | Content/config               |
| Limits              | Upload, quotas, rate limits      | Ops/security                 |

# 19. Staff Access Administration

| **Action**          | **Exigence**                                                     |
|---------------------|------------------------------------------------------------------|
| Créer staff account | Identité interne + MFA recommandé/obligatoire selon rôle.        |
| Attribuer rôle      | Scope minimal nécessaire.                                        |
| Temporary access    | Durée explicite pour accès exceptionnel.                         |
| Privileged role     | Approval supplémentaire.                                         |
| Role change         | Audit + invalidation permissions.                                |
| Departure           | Révocation immédiate sessions/credentials.                       |
| Periodic review     | Recertification des accès sensibles.                             |
| Break-glass         | Si implémenté: usage exceptionnel, très visible, audité et revu. |

# 20. Audit Log

| **Événement audité**            | **Données minimales**                             |
|---------------------------------|---------------------------------------------------|
| Login staff / privileged access | actor, timestamp, device/session, result          |
| Case access sensible            | actor, case, purpose, timestamp                   |
| Verification decision           | subject, type, decision, reviewer, policy version |
| Moderation action               | object, before/after, reason, actor               |
| Refund/financial override       | amount, refs, approvers, reason                   |
| Role/permission change          | target, old/new, scope, actor                     |
| Taxonomy/policy change          | version, before/after, actor                      |
| Config/feature flag change      | market, old/new, actor                            |
| Export                          | actor, dataset/scope, purpose                     |
| Impersonation if ever used      | staff, target, start/end, reason                  |

# 21. Data export et outils de masse

| **Fonction**               | **Protection**                                                                |
|----------------------------|-------------------------------------------------------------------------------|
| CSV export                 | Permission dédiée; scope; watermark/log si approprié.                         |
| Bulk moderation            | Preview + confirmation + rollback/appeal plan.                                |
| Bulk refunds               | Dry-run/report + approvals + idempotency.                                     |
| Bulk notifications         | Audience preview + dedup + unsubscribe/legal rules where applicable.          |
| Bulk entitlement migration | Simulation + reconciliation.                                                  |
| Bulk taxonomy change       | Impact analysis + versioning.                                                 |
| Search staff               | Limiter champs et résultats selon rôle; pas de people browsing sans finalité. |

# 22. Notifications internes et escalades

| **Événement**             | **Destinataire**               |
|---------------------------|--------------------------------|
| P0 Safety                 | Safety lead/on-call            |
| Payment mismatch critique | Finance Ops                    |
| Refund failed répété      | Finance lead                   |
| Provider outage           | Ops/technical + affected teams |
| Verification backlog SLA  | Trust lead                     |
| Moderation appeal overdue | Moderation lead                |
| Suspicious pattern        | Trust/Security selon signal    |
| Privileged config change  | Audit/admin reviewers          |

# 23. Provider / intégration incident

| **Incident**                    | **Réponse opérationnelle**                                                            |
|---------------------------------|---------------------------------------------------------------------------------------|
| Mobile Money outage             | Désactiver/initier fallback selon policy; afficher statut honnête; préserver Pending. |
| SMS/email outage                | Retry queue; ne pas falsifier verification.                                           |
| Object storage issue            | Bloquer upload sensible si intégrité incertaine.                                      |
| Delivery partner outage         | Stop assignment/reassign selon contrat.                                               |
| Search index delay              | Source transactionnelle reste autoritative.                                           |
| Webhook backlog                 | Queue/replay idempotent.                                                              |
| Third-party verification outage | Pending/Unavailable; pas de faux Verified.                                            |

# 24. Procédures d'ouverture et fermeture de journée

| **Moment**       | **Checklist V1**                                                                           |
|------------------|--------------------------------------------------------------------------------------------|
| Début de journée | Provider health; P0/P1; reconciliation exceptions; failed refunds; queues SLA.             |
| Pendant journée  | Traiter par priorité; documenter escalades; surveiller incidents.                          |
| Fin de journée   | Rapprochement exceptions; unresolved P0/P1 handoff; refunds critiques; provider anomalies. |
| Hebdomadaire     | Backlog, SLA, appeals, verification aging, abuse patterns, access changes.                 |
| Mensuel          | Access review sensible, policy changes, finance reconciliation summary, KPI ops.           |

# 25. KPIs opérationnels

| **KPI**                            | **Définition**                                        |
|------------------------------------|-------------------------------------------------------|
| First response time                | Temps jusqu'à première réponse humaine/système utile. |
| Resolution time                    | Temps de création à résolution.                       |
| SLA breach rate                    | % cases dépassant objectif.                           |
| Backlog aging                      | Âge des dossiers ouverts.                             |
| Appeal overturn rate               | Décisions modifiées/annulées en appel.                |
| Verification turnaround            | Temps de contrôle.                                    |
| Refund success time                | Approved → Refunded.                                  |
| Reconciliation exception rate      | Transactions nécessitant revue.                       |
| Repeat offender / abuse recurrence | Récidive après mesure, contextuelle.                  |
| Staff access exceptions            | Nombre d'accès privilégiés/temporaires.               |

# 26. Business continuity & incident command

| **Niveau** | **Exemple**                                           | **Gouvernance**                           |
|------------|-------------------------------------------------------|-------------------------------------------|
| SEV-1      | Paiements incorrects, fuite données, outage critique  | Incident commander + containment immédiat |
| SEV-2      | Module majeur indisponible, provider critique dégradé | Lead technique/ops + communication        |
| SEV-3      | Fonction secondaire dégradée                          | Queue normale priorisée                   |
| SEV-4      | Défaut mineur                                         | Backlog produit/tech                      |

Les seuils, astreintes, contacts et obligations de notification doivent être complétés avant production.

# 27. Ce que le back-office ne doit jamais permettre

- Modifier directement un Payment Successful en Failed ou inversement sans source autoritative et audit.

- Marquer un refund Refunded avant confirmation provider.

- Accorder « Verified » manuellement sans Verification Record et preuve/policy.

- Donner accès aux CV à un Billing Manager par simple choix d'interface.

- Afficher les pièces d'identité dans une recherche générale staff.

- Supprimer l'historique d'une sanction ou transaction pour « nettoyer » un dossier.

- Utiliser un abonnement payé pour annuler une décision de sécurité.

- Modifier un rôle organisationnel contesté sans preuve d'autorité.

- Exporter massivement des données sans permission, finalité et audit.

- Utiliser un compte super-admin partagé.

# 28. Critères d'acceptation V1

| **Test**  | **Critère**                                                                             |
|-----------|-----------------------------------------------------------------------------------------|
| OPS-AC-01 | Un Support Agent ne peut pas ouvrir une pièce d'identité hors case autorisé.            |
| OPS-AC-02 | Un Moderator ne peut pas effectuer un refund.                                           |
| OPS-AC-03 | Un Finance Ops ne peut pas attribuer Verified.                                          |
| OPS-AC-04 | Toute décision de verification conserve reviewer, preuve ref et policy version.         |
| OPS-AC-05 | Un changement taxonomy conserve ID canonique et changelog.                              |
| OPS-AC-06 | Un grant manuel d'entitlement exige reason, actor et expiration/règle.                  |
| OPS-AC-07 | Un refund au-dessus du seuil exige second approver.                                     |
| OPS-AC-08 | Une correction reconciliation crée une entrée audit avant/après.                        |
| OPS-AC-09 | Un staff retiré perd immédiatement sessions/permissions sensibles.                      |
| OPS-AC-10 | Un export de données sensibles est journalisé avec scope et finalité.                   |
| OPS-AC-11 | Un bulk refund rejoué ne crée pas de doubles remboursements.                            |
| OPS-AC-12 | Un provider outage n'entraîne jamais de faux Payment Successful.                        |
| OPS-AC-13 | Une promotion suspendue pour policy ne restaure pas automatiquement l'objet.            |
| OPS-AC-14 | Un appeal affiche la décision initiale et la décision de révision.                      |
| OPS-AC-15 | Un P0 Safety apparaît avant les tickets commerciaux prioritaires.                       |
| OPS-AC-16 | Un claim organisation conflictuel ne peut pas écraser l'admin existant automatiquement. |
| OPS-AC-17 | Un changement de feature flag critique est audité.                                      |
| OPS-AC-18 | Une recherche staff respecte field-level access.                                        |
| OPS-AC-19 | Le système interdit un compte super-admin partagé.                                      |
| OPS-AC-20 | Les actions staff sensibles ont un reason code exploitable.                             |

# 29. V1 vs Post-V1

| **V1**                                | **Post-V1**                              |
|---------------------------------------|------------------------------------------|
| Queues spécialisées + Case Management | Workflow engine plus sophistiqué         |
| RBAC/scopes staff                     | Just-in-time privileged access avancé    |
| Audit actions sensibles               | SIEM/SOC avancé                          |
| Reconciliation console                | Automatisation financière avancée        |
| Taxonomy Center                       | Governance/workflows multi-stage avancés |
| Feature flags/config marché           | Progressive delivery sophistiquée        |
| Basic bulk tools sécurisés            | Automation/ops orchestration avancée     |
| Dashboards KPI opérationnels          | Advanced analytics/data warehouse        |
| Manual review suspicious activity     | Risk graph/ML avancé sous gouvernance    |

# 30. Points à finaliser avant production

| **Sujet**                            | **Statut**                                  |
|--------------------------------------|---------------------------------------------|
| SLA exacts par type de case          | À définir                                   |
| Seuils refunds/four-eye              | À définir Finance/Risk                      |
| Staffing et horaires d'astreinte     | À définir lancement Kinshasa                |
| Procédures autorités/urgence         | À valider juridiquement                     |
| Rétention audit/cases                | À valider juridiquement                     |
| Provider runbooks                    | À finaliser après choix fournisseurs        |
| MFA/SSO staff exact                  | MFA V1 recommandé; architecture à finaliser |
| Break-glass process                  | À définir si implémenté                     |
| Contacts escalation delivery/payment | À contractualiser                           |
| Disaster recovery targets            | À définir techniquement                     |

# 31. Liens avec la suite documentaire

| **Document**                                     | **Relation**                                                    |
|--------------------------------------------------|-----------------------------------------------------------------|
| Document 05 - Plans & Entitlements               | Console commerciale et grants contrôlés.                        |
| Document 06 - Accès                              | Source des rôles, scopes et permissions staff.                  |
| Document 07 - Trust/Safety                       | Queues verification, moderation, safety et appeals.             |
| Document 08 - Commerce                           | Finance, refunds, reconciliation et disputes.                   |
| Document 10 à venir - Plan de Tests & Recette V1 | Transformera OPS-AC et autres invariants en tests bout-en-bout. |
| Document 11 à venir - Plan de Lancement Kinshasa | Dimensionnera staffing, support et readiness opérationnelle.    |
