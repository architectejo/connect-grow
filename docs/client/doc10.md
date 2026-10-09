**PLAN DE TESTS & RECETTE V1**

**Plateforme Écosystème RDC**

*Document 10 - Stratégie QA, UAT, sécurité fonctionnelle et critères Go/No-Go*

Version de référence V1 - Septembre 2026

# 1. Objectif de la recette

Ce plan transforme les exigences fonctionnelles, commerciales, de confidentialité, de sécurité et d'exploitation des Documents 01 à 09 en un programme de validation reproductible. La recette V1 doit démontrer non seulement que les parcours normaux fonctionnent, mais aussi que les erreurs, retries, pertes réseau, permissions, paiements ambigus et actions administratives sont traités sans corruption d'état ni fuite de données.

Un test est considéré réussi uniquement lorsque le résultat visible, l'état backend, les événements/audits et les effets secondaires attendus sont cohérents.

# 2. Niveaux de test

| **Niveau**                | **Responsable principal** | **But**                                                                 |
|---------------------------|---------------------------|-------------------------------------------------------------------------|
| Unit tests                | Développement             | Valider logique locale, state transitions, calculs et règles atomiques. |
| Integration tests         | Développement/QA          | Valider DB, queues, providers/adapters, outbox, storage et APIs.        |
| API/contract tests        | QA/Backend                | Garantir contrats versionnés et erreurs stables.                        |
| End-to-end                | QA                        | Valider parcours multi-modules sur environnement proche production.     |
| Security functional tests | QA/Security               | Permissions, scopes, privacy, session, abuse controls.                  |
| Resilience tests          | QA/Engineering            | Timeouts, retries, duplication, perte réseau, provider outage.          |
| UAT métier                | Product/Ops/Finance/Trust | Confirmer que le produit répond aux règles opérationnelles.             |
| Regression                | QA/CI                     | Empêcher réintroduction de défauts critiques.                           |
| Pilot acceptance          | Équipe lancement          | Valider readiness réelle avec utilisateurs/partenaires pilotes.         |

# 3. Environnements

| **Environnement** | **Usage**                               | **Données**                                                              |
|-------------------|-----------------------------------------|--------------------------------------------------------------------------|
| DEV               | Développement quotidien                 | Synthétiques uniquement                                                  |
| TEST/QA           | Tests automatisés et manuels            | Jeux synthétiques contrôlés                                              |
| STAGING/UAT       | Recette métier proche production        | Synthétiques + comptes pilotes autorisés; aucune donnée sensible inutile |
| PRODUCTION        | Exploitation réelle                     | Accès strict; tests destructifs interdits                                |
| Provider Sandbox  | Paiement/SMS/verification si disponible | Références de test provider                                              |

# 4. Sévérité des défauts

| **Niveau**    | **Définition**                                         | **Exemples**                                               |
|---------------|--------------------------------------------------------|------------------------------------------------------------|
| S0 - Blocker  | Empêche lancement ou menace intégrité/sécurité         | Double charge, fuite CV, paiement faux succès, auth bypass |
| S1 - Critical | Fonction majeure incorrecte sans workaround acceptable | Stock double vendu, refund dupliqué, enfant public         |
| S2 - Major    | Impact important avec workaround limité                | Notification critique manquante, filtre principal cassé    |
| S3 - Minor    | Défaut non bloquant                                    | Texte, alignement, petit problème UX                       |
| S4 - Cosmetic | Pure présentation sans impact métier                   | Espacement/icône                                           |

# 5. Critères d'entrée et de sortie

| **Gate**      | **Critère**                                                                                                 |
|---------------|-------------------------------------------------------------------------------------------------------------|
| Entrée QA     | Build déployable, migrations appliquées, seed data, APIs stables, logs disponibles.                         |
| Entrée UAT    | Parcours S0/S1 automatisés verts; défauts connus documentés.                                                |
| Sortie UAT    | 100% scénarios critiques exécutés; aucun S0/S1 ouvert; S2 acceptés explicitement seulement avec mitigation. |
| Go production | Payments/provider, security, backup/recovery, support queues, monitoring et runbooks validés.               |
| Pilot exit    | KPIs et incidents du pilote dans limites convenues; corrections critiques terminées.                        |

# 6. Jeu de données de recette

| **Persona / objet** | **Exemples requis**                                             |
|---------------------|-----------------------------------------------------------------|
| Individus           | Nouveau compte, compte vérifié, compte suspendu, Premium expiré |
| Providers           | Standard, catégorie sensible, vérification pending/expired      |
| Organisations       | Business, Business Pro, Enterprise; branches A/B                |
| Staff               | Support, Finance, Moderator, Verification, Taxonomy, Security   |
| Jobs                | Public, domestique, fermé, branche A/B                          |
| Candidates          | Opt-in discovery, opt-out, candidatures multiples               |
| Marketplace         | Produit stock, article unique, vendeur particulier/commercial   |
| Food                | Restaurant open/closed, item out-of-stock, pickup/delivery      |
| Events              | Gratuit, payant, privé, annulé/reporté                          |
| Payments            | Pending, success, failed, expired, duplicate, reconciliation    |
| Delivery            | Assigned/unassigned, cash collector variants                    |
| School              | Parent A/B, beneficiary relationships distinctes                |

# 7. Format standard d'un cas de test

| **Champ**        | **Contenu**                               |
|------------------|-------------------------------------------|
| Test ID          | Identifiant stable ex. PAY-E2E-004        |
| Requirement refs | Document/feature/acceptance criteria liés |
| Priority         | Critical/High/Medium/Low                  |
| Preconditions    | État initial, comptes, permissions, data  |
| Steps            | Actions reproductibles                    |
| Expected UI      | Résultat utilisateur                      |
| Expected backend | États objets/DB                           |
| Expected events  | Outbox/queue/webhook/notification         |
| Expected audit   | Entrées d'audit nécessaires               |
| Evidence         | Screenshots/log refs/transaction refs     |
| Result           | Pass/Fail/Blocked                         |
| Defect link      | Ticket bug si Fail                        |

# 8. Identité, authentification et contextes

| **ID** | **Scénario**                             | **Résultat attendu**                                   |
|--------|------------------------------------------|--------------------------------------------------------|
| IAM-01 | Créer compte et vérifier téléphone/email | Compte actif; Verification Records corrects            |
| IAM-02 | Changer Individual → Provider            | Contexte change; permissions recalculées               |
| IAM-03 | Changer Individual → Organization        | Membership requis; pas d'autorité par simple sélection |
| IAM-04 | Session expirée pendant action           | Réauth sans duplication d'action critique              |
| IAM-05 | Compte suspendu                          | Actions sensibles refusées malgré entitlement          |
| IAM-06 | Membre retiré d'organisation             | Accès révoqué immédiatement                            |
| IAM-07 | Changement de branche                    | Ancien scope inaccessible                              |
| IAM-08 | Récupération compte                      | Anciennes sessions révoquées selon policy              |

# 9. Autorisation et confidentialité

| **ID**  | **Scénario**                                 | **Résultat**               |
|---------|----------------------------------------------|----------------------------|
| AUTH-01 | Recruiter Branche A ouvre candidat Branche B | DENY_SCOPE                 |
| AUTH-02 | Billing Manager ouvre CV                     | DENY_PERMISSION            |
| AUTH-03 | Enterprise recherche candidat opt-out        | Aucun dossier divulgué     |
| AUTH-04 | Entitlement actif sans permission            | DENY_PERMISSION            |
| AUTH-05 | Permission valide, quota épuisé              | DENY_ENTITLEMENT           |
| AUTH-06 | Parent A ouvre bénéficiaire Parent B         | DENY_RELATION/PRIVACY      |
| AUTH-07 | Delivery provider non assigné ouvre adresse  | Refus                      |
| AUTH-08 | Support ouvre ID hors case                   | Refus + audit si tentative |
| AUTH-09 | Pièce identité via URL publique              | Impossible                 |
| AUTH-10 | Suspension sécurité + plan actif             | DENY_SECURITY              |

# 10. Accueil, Explorer, recherche et + Publier

| **ID** | **Scénario**                         | **Résultat**                                   |
|--------|--------------------------------------|------------------------------------------------|
| NAV-01 | Recherche universelle multi-domaines | Résultats typés et routage correct             |
| NAV-02 | Alias taxonomique FR/EN/local validé | Trouve catégorie canonique                     |
| NAV-03 | \+ Publier en contexte Individual    | Seulement actions éligibles                    |
| NAV-04 | \+ Publier en contexte Org Recruiter | Job visible; billing admin seul ne le voit pas |
| NAV-05 | Catégorie Not Permitted              | Publication bloquée avec motif                 |
| NAV-06 | Contenu privé/restrictif             | Absent de recherche publique                   |
| NAV-07 | Faible réseau pendant recherche      | Retry/état erreur sans crash                   |

# 11. Marketplace

| **ID** | **Scénario**                   | **Résultat**                          |
|--------|--------------------------------|---------------------------------------|
| MKT-01 | Acheter produit stock          | Order + stock + payment cohérents     |
| MKT-02 | Deux acheteurs, article unique | Un seul succès; aucun oversell        |
| MKT-03 | Payment expired                | Réservation libérée une fois          |
| MKT-04 | Vendeur annule payé            | Refund workflow distinct              |
| MKT-05 | Cash order                     | Unpaid jusqu'à confirmation autorisée |
| MKT-06 | Return materially different    | Case créé; historique intact          |
| MKT-07 | Article interdit signalé       | Moderation + commerce case            |
| MKT-08 | Avis sans interaction éligible | Refus selon policy                    |

# 12. Paiements et idempotency

| **ID** | **Scénario**                | **Résultat**                      |
|--------|-----------------------------|-----------------------------------|
| PAY-01 | Double clic checkout        | Une commande/charge               |
| PAY-02 | Double webhook Successful   | Aucun double effet                |
| PAY-03 | Timeout après provider call | Pending/ReconciliationRequired    |
| PAY-04 | Webhook avant réponse app   | État final correct au refresh     |
| PAY-05 | Montant provider différent  | ReconciliationRequired            |
| PAY-06 | Failed puis retry           | Nouveau Payment; ancien immutable |
| PAY-07 | App fermée après paiement   | Pas de nouvelle charge au retour  |
| PAY-08 | Provider indisponible       | Aucun faux succès                 |
| PAY-09 | Duplicate real charge       | Case + refund contrôlé            |
| PAY-10 | Notification retry          | Pas de message dupliqué           |

# 13. Refunds et reconciliation

| **ID** | **Scénario**                       | **Résultat**                          |
|--------|------------------------------------|---------------------------------------|
| REF-01 | Full refund                        | Requested→Approved→Submitted→Refunded |
| REF-02 | Partial refund                     | Montant correct; balance remboursable |
| REF-03 | Deux partial refunds               | Cumul ≤ original                      |
| REF-04 | Provider refund failed             | Failed visible; retry contrôlé        |
| REF-05 | Approved non confirmé              | UI n'affiche pas Refunded             |
| REF-06 | Refund rejoué                      | Idempotent                            |
| REC-01 | Local Pending/provider Successful  | Correction idempotente                |
| REC-02 | Local Successful/provider mismatch | Manual review; pas d'auto-downgrade   |
| REC-03 | Admin correction                   | Reason + before/after + audit         |

# 14. Restaurants et Food Ordering

| **ID** | **Scénario**                             | **Résultat**                                 |
|--------|------------------------------------------|----------------------------------------------|
| FOD-01 | Order accepted→preparing→ready→collected | Transitions valides                          |
| FOD-02 | Restaurant decline paid order            | Resolution/refund                            |
| FOD-03 | Item rupture                             | Pas de substitution silencieuse              |
| FOD-04 | Cancel avant Accept                      | Policy appliquée                             |
| FOD-05 | Cancel après Preparing                   | Policy/reason/resolution                     |
| FOD-06 | Pickup cash                              | Paid seulement confirmation collecteur       |
| FOD-07 | Restaurant offline temporaire            | Commande non perdue; retry/timeout explicite |

# 15. Livraison partenaire

| **ID** | **Scénario**                      | **Résultat**                               |
|--------|-----------------------------------|--------------------------------------------|
| DLV-01 | Create Delivery Request           | Distinct Food/Marketplace Order            |
| DLV-02 | Provider accepte mission          | Accès données minimales activé             |
| DLV-03 | Provider non assigné              | Adresse/contact privés                     |
| DLV-04 | PickedUp puis delivery fail       | Order et Delivery states restent distincts |
| DLV-05 | ReturnRequired→Returned           | Historique complet                         |
| DLV-06 | Cash collector = delivery company | Montants food/delivery séparés             |
| DLV-07 | Partner outage                    | Pas d'assignation fantôme; résolution      |

# 16. Jobs & recrutement

| **ID** | **Scénario**                        | **Résultat**                                      |
|--------|-------------------------------------|---------------------------------------------------|
| JOB-01 | Candidat postule gratuitement       | Application créée sans plan requis                |
| JOB-02 | Household Employer publie avec pass | Entitlement consommé correctement                 |
| JOB-03 | Pass expiré                         | Nouvelle publication bloquée; historique conservé |
| JOB-04 | Recruiter voit jobs assignés        | Scope correct                                     |
| JOB-05 | Candidate opt-out discovery         | Invisible en Enterprise discovery                 |
| JOB-06 | Entretien planifié                  | Invitations/permissions correctes                 |
| JOB-07 | Référence avec consentement         | Contact privé; statut vérifié possible            |
| JOB-08 | Billing manager tente shortlist     | Refus                                             |
| JOB-09 | Aucune décision autonome hiring     | Système ne produit pas verdict final              |

# 17. Workforce Training

| **ID** | **Scénario**                      | **Résultat**                                 |
|--------|-----------------------------------|----------------------------------------------|
| TRN-01 | Provider publie programme         | Skills/taxonomy/eligibility corrects         |
| TRN-02 | Employer demande cohorte privée   | Quote/booking/context créés                  |
| TRN-03 | Invite candidat avec consentement | Accès formation seulement                    |
| TRN-04 | Provider voit participant         | Pas dossier emploi complet                   |
| TRN-05 | Completion enregistrée            | Provenance/date/provider                     |
| TRN-06 | Completion utilisée recrutement   | Factual input, pas competence/hiring verdict |

# 18. Events & Ticketing

| **ID** | **Scénario**                   | **Résultat**                                         |
|--------|--------------------------------|------------------------------------------------------|
| EVT-01 | Événement gratuit              | Registration sans Payment                            |
| EVT-02 | Événement payant               | Ticket seulement après Payment Successful            |
| EVT-03 | Double scan QR                 | Second scan refusé/alerté                            |
| EVT-04 | Refund ticket                  | Ticket invalidé                                      |
| EVT-05 | Event cancelled                | Tous tickets affectés + workflow refund/notification |
| EVT-06 | Event postponed                | Ticket/options selon policy                          |
| EVT-07 | Événement privé                | Absent recherche/index public                        |
| EVT-08 | Check-in staff autre événement | Refus scope                                          |

# 19. Services, devis et booking

| **ID** | **Scénario**                    | **Résultat**                                              |
|--------|---------------------------------|-----------------------------------------------------------|
| SRV-01 | Client demande devis            | Quote Request + conversation contextuelle                 |
| SRV-02 | Provider répond                 | Seulement provider/org autorisé                           |
| SRV-03 | Booking ressource disponible    | Réservation créée                                         |
| SRV-04 | Deux bookings même capacité     | Conflit empêché selon règle                               |
| SRV-05 | Provider plan expire            | Historique conservé; nouvelles capacités premium bloquées |
| SRV-06 | Catégorie sensible non vérifiée | Publication/booking bloqué selon policy                   |

# 20. Messaging, notifications et À traiter

| **ID** | **Scénario**                              | **Résultat**                                       |
|--------|-------------------------------------------|----------------------------------------------------|
| MSG-01 | Conversation créée depuis quote/job/order | Contexte/identity fixés                            |
| MSG-02 | Team Inbox réassignation                  | Nouvel accès; ancien révoqué si scope retiré       |
| MSG-03 | Membre quitte org                         | Plus d'accès conversation org                      |
| MSG-04 | Block user                                | Nouveaux messages bloqués; preuves conservées      |
| NTF-01 | Webhook retry                             | Notification dédupliquée                           |
| NTF-02 | À traiter                                 | Action disparaît seulement après résolution réelle |
| NTF-03 | P0 safety                                 | Priorité supérieure au commercial                  |

# 21. Trust, verification et moderation

| **ID** | **Scénario**                | **Résultat**                                                    |
|--------|-----------------------------|-----------------------------------------------------------------|
| TRU-01 | Utilisateur achète Premium  | Aucun Verified automatique                                      |
| TRU-02 | Identity verified           | Public claim précis; preuve privée                              |
| TRU-03 | Sensitive category pending  | Publication bloquée si requis                                   |
| TRU-04 | Référence vérifiée          | Coordonnées référent non publiques                              |
| MOD-01 | Report contenu              | Case + triage                                                   |
| MOD-02 | Suspension                  | Reason + audit + appeal si éligible                             |
| MOD-03 | Appeal                      | Décision initiale préservée                                     |
| MOD-04 | Avis négatif valide         | Pas supprimé car défavorable                                    |
| SEC-01 | Suspicious automated signal | Review/restriction proportionnée; pas verdict irréversible seul |

# 22. Schools, parent et bénéficiaire

| **ID** | **Scénario**                    | **Résultat**                     |
|--------|---------------------------------|----------------------------------|
| SCH-01 | Parent voit enfant autorisé     | Accès relationnel correct        |
| SCH-02 | Parent tente autre bénéficiaire | Refus                            |
| SCH-03 | Recherche publique enfant       | Aucun résultat/profil public     |
| SCH-04 | School staff admission          | Seulement rôle/purpose autorisé  |
| SCH-05 | Document sensible               | Field-level access + audit       |
| SCH-06 | Événement scolaire privé        | Invitation/relationship required |

# 23. Plans, passes, quotas et promotion

| **ID** | **Scénario**               | **Résultat**                               |
|--------|----------------------------|--------------------------------------------|
| ENT-01 | Paiement plan confirmé     | Entitlement Active                         |
| ENT-02 | Payment plan Pending       | Pas de capacité sensible activée           |
| ENT-03 | Quota atteint              | Action bloquée; upgrade/pass possible      |
| ENT-04 | Downgrade                  | Objets historiques non supprimés           |
| ENT-05 | Manual grant staff         | Reason + audit + expiry/rule               |
| PRM-01 | Promouvoir objet éligible  | Label Sponsorisé                           |
| PRM-02 | Objet devient non conforme | Promotion stoppée sans restaurer contenu   |
| PRM-03 | Promotion                  | Ne change pas verification/organic ranking |

# 24. Back-office

| **ID** | **Scénario**               | **Résultat**                   |
|--------|----------------------------|--------------------------------|
| OPS-01 | Support ouvre ID hors case | Refus                          |
| OPS-02 | Moderator tente refund     | Refus                          |
| OPS-03 | Finance tente Verified     | Refus                          |
| OPS-04 | Refund \> seuil            | Second approver                |
| OPS-05 | Taxonomy rename            | Canonical ID inchangé          |
| OPS-06 | Bulk refund rejoué         | Pas de double refund           |
| OPS-07 | Staff désactivé            | Sessions/permissions révoquées |
| OPS-08 | Export sensible            | Permission + purpose + audit   |
| OPS-09 | Feature flag critique      | Audit                          |
| OPS-10 | Claim org conflictuel      | Pas d'écrasement automatique   |

# 25. Faible connectivité, offline et reprise

| **ID** | **Scénario**                    | **Résultat**                                             |
|--------|---------------------------------|----------------------------------------------------------|
| NET-01 | Réseau perdu pendant formulaire | Données non sensibles préservées si sûr; retry clair     |
| NET-02 | Réseau perdu après Create       | Refresh/retry idempotent                                 |
| NET-03 | Paiement initié puis offline    | Au retour, lire serveur/provider; pas nouvelle charge    |
| NET-04 | Upload interrompu               | Reprise ou retry; pas document corrompu considéré valide |
| NET-05 | Queue notification retardée     | Transaction métier reste correcte                        |
| NET-06 | Search indisponible             | Message/fallback; source DB non corrompue                |
| NET-07 | Offline ticket scan si activé   | Conflits synchronisés et double scan détectable          |
| NET-08 | App relancée                    | État serveur autoritatif récupéré                        |

# 26. Performance et capacité V1

| **Domaine**   | **Test minimum**                                               |
|---------------|----------------------------------------------------------------|
| Search        | Temps de réponse sous charge cible définie; pagination stable. |
| Checkout      | Concurrence sans doubles créations.                            |
| Ticket scan   | Débit de check-in cible sans duplication.                      |
| Messaging     | Envoi/réception et persistance sous charge.                    |
| Notifications | Queue absorbe pics sans rejouer transaction.                   |
| Admin queues  | Pagination/filtrage sur backlog réaliste.                      |
| Media         | Uploads limités, résilients et sécurisés.                      |
| Database      | Locks/concurrence testés sur stock, booking, quotas.           |

Les seuils chiffrés de performance doivent être définis avec l'équipe technique à partir de la capacité d'infrastructure et des objectifs du pilote.

# 27. Sécurité technique - minimum de recette

| **Test**               | **Attendu**                                                |
|------------------------|------------------------------------------------------------|
| Authorization bypass   | Impossible via API directe.                                |
| IDOR                   | Changer un ID objet ne donne pas accès à l'objet d'autrui. |
| Rate limiting          | OTP, login, messaging, payment endpoints protégés.         |
| Session revoke         | Révocation effective rapidement.                           |
| File upload            | Type/taille/scan/policy; pas d'exécution.                  |
| Secrets                | Absents des clients/logs.                                  |
| Webhook authentication | Événements non authentiques rejetés.                       |
| Audit tampering        | Utilisateur/staff ordinaire ne peut altérer logs.          |
| PII in logs            | Minimisée.                                                 |
| Privilege escalation   | Rôle inférieur ne peut s'accorder rôle supérieur.          |

# 28. Accessibilité, localisation et compatibilité

| **Axe**        | **Recette**                                                            |
|----------------|------------------------------------------------------------------------|
| FR/EN          | Labels, erreurs et contenus clés cohérents.                            |
| Long text      | Pas de clipping sur traductions longues.                               |
| Dates/heures   | Timezone/format cohérents par marché.                                  |
| Currency       | USD/CDF et devise transaction correctement affichées.                  |
| Accessibility  | Navigation, contrastes, labels, focus et lecteurs d'écran selon cible. |
| Mobile sizes   | Téléphones petits/moyens/grands.                                       |
| Web responsive | Desktop/tablette/mobile.                                               |
| Android target | Versions supportées définies et testées.                               |
| Poor bandwidth | Images/requests optimisées; états loading/error.                       |

# 29. Automatisation prioritaire

| **Suite automatisée**    | **Inclure en priorité**                                  |
|--------------------------|----------------------------------------------------------|
| Smoke CI                 | Login, search, publish basic, order, application, event. |
| Payments regression      | PAY-01 à PAY-10 + refunds.                               |
| Authorization regression | AUTH-01 à AUTH-10.                                       |
| Commerce state machines  | Order/Payment/Fulfillment/Delivery invariants.           |
| Entitlements             | Activation, expiry, quota, downgrade.                    |
| Privacy                  | Candidate, child, address, ID document.                  |
| Webhook replay           | Payment/refund/notification idempotency.                 |
| Migration tests          | DB schema/data migrations sur snapshot synthétique.      |
| API contracts            | Client/backend compatibility.                            |

# 30. UAT par équipe métier

| **Équipe**               | **Parcours à signer**                                      |
|--------------------------|------------------------------------------------------------|
| Product                  | Accueil, Explorer, +Publier, Compte, cross-module journeys |
| Commerce Ops             | Marketplace, food, delivery exceptions                     |
| Finance                  | Payments, refunds, reconciliation, billing                 |
| Recruitment              | Jobs, household recruitment, privacy, training link        |
| Events                   | Ticketing, check-in, cancellation                          |
| Trust/Safety             | Verification, moderation, appeals, sensitive categories    |
| Support                  | Case lifecycle, messaging, user communications             |
| Admin                    | Taxonomy, entitlements, config, audit                      |
| School/Beneficiary owner | Parent/beneficiary privacy                                 |
| Technical Ops            | Monitoring, queues, provider outage, recovery              |

# 31. Matrice de traçabilité documentaire

| **Source**  | **Tests couverts**                               |
|-------------|--------------------------------------------------|
| Document 01 | Fonctionnalités V1 et critères d'acceptation     |
| Document 02 | Parcours UF-01 à UF-30                           |
| Document 03 | Taxonomie, aliases, applicability, policy states |
| Document 05 | Plans, passes, quotas, promotion                 |
| Document 06 | Roles/permissions/scopes/field access            |
| Document 07 | Trust, verification, moderation, safety          |
| Document 08 | Commerce/payment/refund/dispute state machines   |
| Document 09 | Back-office, staff separation, audit             |

# 32. Go / No-Go V1

| **Condition**                   | **Go**                                    |
|---------------------------------|-------------------------------------------|
| S0/S1 ouverts                   | 0                                         |
| Paiements critiques             | 100% scénarios critiques passés           |
| Authorization/privacy critiques | 100% passés                               |
| Backups/recovery                | Test de restauration réussi               |
| Monitoring/alerts               | Actifs et testés                          |
| Provider readiness              | Sandbox + production checklist signée     |
| Support/finance/trust queues    | Staff et runbooks prêts                   |
| Legal launch blockers           | Aucun blocker non résolu                  |
| Known S2                        | Documentés, mitigation + owner + échéance |
| Rollback                        | Procédure testée/validée                  |

# 33. Pilot / Beta Kinshasa - recette en conditions réelles

| **Phase**          | **Validation**                                               |
|--------------------|--------------------------------------------------------------|
| Internal alpha     | Équipe interne, données synthétiques, bugs bloquants.        |
| Closed beta        | Petit groupe entreprises/providers/utilisateurs consentants. |
| Commerce pilot     | Transactions limitées, reconciliation quotidienne.           |
| Recruitment pilot  | Employeurs/candidats pilotes, privacy monitoring.            |
| Events pilot       | Un nombre limité d'événements/tickets/check-ins.             |
| Operational review | Backlog, support, fraud signals, provider incidents.         |
| Expansion gate     | Étendre seulement après critères qualité/stabilité convenus. |

# 34. Rapport de recette

| **Section**       | **Contenu**                                            |
|-------------------|--------------------------------------------------------|
| Build             | Version app/backend/schema/config                      |
| Environment       | Staging/UAT + provider versions                        |
| Execution         | Tests planned/executed/pass/fail/blocked               |
| Defects           | Par sévérité/module/owner                              |
| Critical evidence | Payment, privacy, security, recovery                   |
| Known risks       | Acceptés avec mitigation                               |
| Sign-offs         | Product, QA, Engineering, Ops, Finance, Trust          |
| Decision          | Go / Conditional Go / No-Go avec conditions factuelles |

# 35. Tests post-déploiement

- Smoke production non destructif immédiatement après release.

- Vérifier providers, queues, webhooks, notifications et monitoring.

- Contrôler qu'aucune migration n'a modifié permissions ou entitlements de façon inattendue.

- Comparer taux d'erreur, latence, paiement pending et reconciliation aux seuils attendus.

- Prévoir rollback/feature disable si un invariant critique est violé.

- Ajouter tout incident production comme test de non-régression avant release suivante.

# 36. Propriété et maintenance du plan

| **Artefact**                    | **Owner**                      |
|---------------------------------|--------------------------------|
| Test cases fonctionnels         | QA + Product                   |
| Automated suites                | Engineering + QA               |
| Payment/provider tests          | Finance Ops + Engineering + QA |
| Security tests                  | Security/Engineering + QA      |
| UAT scripts                     | Product/Ops owners             |
| Regression pack                 | QA                             |
| Go/No-Go evidence               | Release owner                  |
| Postmortem regression additions | Owner du domaine + QA          |

# 37. Décisions ouvertes

| **Sujet**                               | **Statut**                                  |
|-----------------------------------------|---------------------------------------------|
| Outil de gestion des tests              | À choisir                                   |
| Objectifs chiffrés performance          | À définir après architecture/infrastructure |
| Versions Android/navigateurs supportées | À définir avant beta                        |
| Niveau WCAG cible                       | À formaliser                                |
| Device lab                              | À définir selon audience RDC                |
| Provider sandbox scenarios exacts       | Après choix providers                       |
| SLA de correction par sévérité          | À définir équipe                            |
| Taille/cohortes beta                    | Document 11 - lancement                     |
| Seuils expansion                        | Document 11 - lancement                     |

# 38. Règle finale

La recette V1 n'est pas une démonstration de happy path. Elle est la preuve que la plateforme conserve ses invariants lorsque les utilisateurs cliquent deux fois, perdent le réseau, changent de rôle, dépassent un quota, paient sans recevoir immédiatement une confirmation, contestent une décision ou rencontrent une défaillance provider. Les scénarios d'exception sont donc des critères de lancement, pas des tests optionnels.
