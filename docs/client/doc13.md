**DICTIONNAIRE DE DONNÉES & CATALOGUE DES OBJETS MÉTIER**

**Plateforme Écosystème RDC**

*Document 13 - Modèle conceptuel, objets, relations, états et invariants V1*

Version de référence V1 / Post-V1 - Septembre 2026

# 1. Objet

Ce document définit le langage de données commun de la plateforme. Il ne constitue pas un schéma SQL final: il décrit les objets métier, leurs identifiants, relations, états, responsabilités, données sensibles et invariants afin que mobile, web, backend, Admin, analytics et intégrations parlent du même système.

Règle d'architecture: un même concept métier possède une source de vérité identifiable. Les interfaces peuvent afficher des vues combinées, mais ne doivent pas fusionner des objets dont les cycles de vie sont indépendants.

# 2. Conventions générales

| **Convention** | **Règle**                                                                                               |
|----------------|---------------------------------------------------------------------------------------------------------|
| Identifiants   | UUID/identifiant opaque recommandé; jamais exposer un compteur sensible comme mécanisme d'autorisation. |
| Timestamps     | created_at, updated_at et événements critiques en UTC; présentation localisée.                          |
| Money          | Montant en unité mineure ou decimal contrôlé + currency; jamais float binaire.                          |
| Status         | Enum/version contrôlée; transitions validées côté serveur.                                              |
| Soft delete    | Utiliser état/archivage lorsque l'historique doit rester traçable.                                      |
| Audit          | Actions sensibles reliées à actor, reason, timestamp et target.                                         |
| Market         | market_id/ruleset lorsque comportement varie géographiquement.                                          |
| Policy version | Décisions trust/legal/config reliées à version applicable.                                              |
| PII            | Classification et field-level disclosure; pas de duplication inutile.                                   |
| External refs  | Provider reference séparée de l'ID interne.                                                             |

# 3. Carte des domaines

| **Domaine**  | **Objets principaux**                                                               |
|--------------|-------------------------------------------------------------------------------------|
| Identity     | User, Identity, Session, ContactPoint, Consent                                      |
| Organization | Organization, Membership, RoleAssignment, Branch                                    |
| Provider     | ProviderProfile, Availability, ServiceArea                                          |
| Taxonomy     | TaxonomyNode, AttributeDefinition, Alias, PolicyRule                                |
| Publishing   | Listing, MediaAsset, Publication                                                    |
| Marketplace  | ProductListing, InventoryItem, Cart/Checkout intent, Order, OrderLine               |
| Payments     | Payment, PaymentAttempt, Refund, LedgerEntry, ReconciliationCase                    |
| Services     | ServiceOffering, QuoteRequest, Quote                                                |
| Booking      | Resource, AvailabilityRule, Booking                                                 |
| Food         | RestaurantProfile, Menu, MenuItem, FoodOrder                                        |
| Delivery     | DeliveryProvider, DeliveryService, DeliveryRequest                                  |
| Recruitment  | JobPosting, CandidateProfile, Application, PipelineStage, Interview, ReferenceCheck |
| Training     | TrainingProgram, Cohort, Enrollment, CompletionRecord                               |
| Events       | Event, Registration, TicketOrder, Ticket, CheckIn                                   |
| Campaigns    | Campaign, VolunteerOpportunity, Participation                                       |
| Schools      | SchoolProfile, Beneficiary, GuardianRelationship, AdmissionCase                     |
| Messaging    | Conversation, ConversationParticipant, Message                                      |
| Trust        | VerificationRecord, Review, Report, ModerationAction                                |
| Support      | Case, CaseEvent, Appeal                                                             |
| Commercial   | Plan, Pass, Subscription, Entitlement, UsageCounter, Promotion                      |
| Admin        | StaffRole, AuditEvent, FeatureFlag, MarketConfig                                    |

# 4. User, Identity & Acting Context

| **Objet**     | **Champs clés**                                      | **Relations / invariants**                                                  |
|---------------|------------------------------------------------------|-----------------------------------------------------------------------------|
| User          | user_id, status, locale, market, created_at          | Compte humain principal; ne signifie pas buyer/seller/candidate.            |
| Identity      | identity_id, user_id, type, display_name, status     | Contexte personnel/professionnel autorisé; un User peut en avoir plusieurs. |
| ContactPoint  | type, value_normalized, verified_at, visibility      | Téléphone/email; valeur privée par défaut.                                  |
| Session       | session_id, user_id, device, created/expires/revoked | Révocable; security state appliqué.                                         |
| ActingContext | user_id, identity/org, membership, branch            | Contexte actif calculé; ne confère pas de permission à lui seul.            |
| ConsentRecord | subject, purpose, status, policy_version, timestamp  | Historique de consentement; révocation n'efface pas l'historique.           |

# 5. Organization, Branch & Membership

| **Objet**                | **Champs clés**                                            | **Règles**                                                       |
|--------------------------|------------------------------------------------------------|------------------------------------------------------------------|
| Organization             | organization_id, legal/display name, type, status, market  | Entreprise, école, restaurant, nonprofit, delivery company, etc. |
| Branch                   | branch_id, organization_id, name, location, status         | Scope organisationnel; hiérarchie simple V1.                     |
| Membership               | membership_id, user_id, organization_id, status, joined_at | Relation d'autorité; distincte du profil public.                 |
| RoleAssignment           | membership_id, role_code, scopes, valid_from/to            | Permissions dérivées; scope branche/module possible.             |
| AuthorizedRepresentative | subject/org, evidence_ref, status                          | Autorité vérifiée distincte de l'identité.                       |
| OrganizationClaim        | claimant, organization, status, evidence, case_id          | Ne remplace jamais automatiquement un admin existant.            |

# 6. ProviderProfile

| **Champ**              | **Description**                        | **Classification**     |
|------------------------|----------------------------------------|------------------------|
| provider_profile_id    | Profil d'un prestataire individuel     | Internal/Public ID     |
| identity_id            | Identité propriétaire                  | Private relation       |
| profession_category_id | Métier/service canonique               | Public                 |
| headline/description   | Présentation                           | Public                 |
| general_location       | Zone générale                          | Public                 |
| exact_address          | Si nécessaire opérationnellement       | Restricted             |
| availability_summary   | Disponibilité publiée                  | Public                 |
| skills                 | Références Taxonomy/Skills             | Public selon choix     |
| languages              | Langues                                | Public                 |
| verification_claims    | Claims dérivés de Verification Records | Public précis          |
| service_area           | Zones couvertes                        | Public/Operational     |
| status                 | Draft/Active/Suspended/Archived        | Internal/Public effect |

# 7. Taxonomy objects

| **Objet**           | **Champs**                                                 | **Invariant**                                                   |
|---------------------|------------------------------------------------------------|-----------------------------------------------------------------|
| TaxonomyNode        | node_id, domain, parent_id, canonical_code, labels, status | ID stable même si label change.                                 |
| TaxonomyAlias       | alias, language, market, node_id                           | Alias pointe vers canonique; pas catégorie parallèle.           |
| AttributeDefinition | attribute_id, type, unit, allowed_values                   | Séparé des catégories pour éviter explosion.                    |
| NodeAttribute       | node_id, attribute_id, required/filterable                 | Applicabilité configurable.                                     |
| PolicyRule          | node/content_type/market, state, requirements              | Allowed/Restricted/VerificationRequired/NotPermitted.           |
| TaxonomyVersion     | version_id, effective_at, changelog                        | Clients consomment version/API; pas hard-code source de vérité. |

# 8. Publication & Media

| **Objet**                  | **Champs clés**                                                        | **Règles**                                      |
|----------------------------|------------------------------------------------------------------------|-------------------------------------------------|
| Publication                | publication_id, owner_ref, content_type, object_id, visibility, status | Couche commune de publication/discovery.        |
| MediaAsset                 | asset_id, owner, storage_ref, mime, size, status                       | Stockage privé/public contrôlé; scan/policy.    |
| LocationRef                | location_id, type, coordinates/general label                           | Exactitude selon purpose/privacy.               |
| ContactAction              | object_ref, allowed_channels                                           | N'expose pas nécessairement coordonnées brutes. |
| PublicationModerationState | publication, state, reason, action_ref                                 | Séparé de l'objet métier.                       |

# 9. Marketplace objects

| **Objet**        | **Champs clés**                                                             | **Invariant**                                      |
|------------------|-----------------------------------------------------------------------------|----------------------------------------------------|
| ProductListing   | listing_id, seller_ref, category, title, price, currency, condition, status | Vendeur particulier/pro clairement identifié.      |
| InventoryItem    | inventory_id, listing_id, quantity/unique_state, reserved_qty               | Stock source de vérité.                            |
| StockReservation | reservation_id, inventory, qty, expires_at, order_ref                       | TTL; libération idempotente.                       |
| Order            | order_id, buyer, seller, status, totals, currency                           | État commercial distinct Payment/Fulfillment.      |
| OrderLine        | order_id, listing/product snapshot, qty, unit_price                         | Snapshot immuable du prix/description nécessaires. |
| Fulfillment      | fulfillment_id, order_id, method, status                                    | Pickup/seller delivery/partner delivery.           |
| ReturnRequest    | return_id, order_line, reason, status, case_id                              | Politique/loi configurable.                        |

# 10. Payment, Refund & Ledger

| **Objet**               | **Champs clés**                                                              | **Invariant**                                          |
|-------------------------|------------------------------------------------------------------------------|--------------------------------------------------------|
| Payment                 | payment_id, payer, purpose_ref, amount, currency, method, status             | Une source financière distincte de l'Order.            |
| PaymentAttempt          | attempt_id, payment_id, provider, idempotency_key, provider_ref, status      | Chaque tentative traçable.                             |
| ProviderEvent           | provider_event_id, provider, external_id, payload_ref, verified, received_at | Déduplication + preuve webhook.                        |
| Refund                  | refund_id, payment_id, amount, reason, status, provider_ref                  | Objet immuable/append history; Approved ≠ Refunded.    |
| LedgerEntry             | entry_id, account/purpose, amount, direction, source_ref, timestamp          | Append-only/protected; correction par nouvelle entrée. |
| ReconciliationCase      | payment/refund, local_state, provider_state, mismatch_reason                 | Résolution auditée.                                    |
| CashReceiptConfirmation | collector_ref, order/purpose, amount, confirmed_at                           | Cash reste Unpaid avant confirmation autorisée.        |

# 11. Service, Quote & Booking

| **Objet**        | **Champs clés**                                                | **Règles**                                 |
|------------------|----------------------------------------------------------------|--------------------------------------------|
| ServiceOffering  | service_id, provider/org, taxonomy, pricing_mode, area, status | Prix fixe/à partir/devis selon modèle.     |
| QuoteRequest     | request_id, requester, service/category, requirements, status  | Contexte client; données minimales.        |
| Quote            | quote_id, request_id, provider, amount/terms, validity, status | Version/snapshot des conditions.           |
| Resource         | resource_id, owner, type, capacity, status                     | Personne/room/equipment/etc. selon module. |
| AvailabilityRule | resource/service, recurrence/window/exceptions                 | Source disponibilité.                      |
| Booking          | booking_id, customer, resource/service, start/end, status      | Conflit/capacité contrôlés serveur.        |

# 12. Restaurant, Menu & FoodOrder

| **Objet**             | **Champs clés**                                               | **Invariant**                                           |
|-----------------------|---------------------------------------------------------------|---------------------------------------------------------|
| RestaurantProfile     | organization_id, cuisine/taxonomy, hours, fulfillment options | Organisation spécialisée, pas compte séparé.            |
| Menu                  | menu_id, restaurant, schedule, status                         | Peut être versionné.                                    |
| MenuItem              | item_id, menu, name, price, availability, modifiers           | Snapshot dans order line.                               |
| FoodOrder             | food_order_id, customer, restaurant, status, totals           | Received/Accepted/Preparing/Ready/etc.; Payment séparé. |
| FoodOrderLine         | food_order_id, item snapshot, qty, modifiers                  | Immuable pour transaction.                              |
| RestaurantFulfillment | food_order, pickup/own_delivery/partner_delivery              | Crée DeliveryRequest si partner.                        |

# 13. Delivery & Fulfillment

| **Objet**                    | **Champs clés**                                                      | **Règles**                                |
|------------------------------|----------------------------------------------------------------------|-------------------------------------------|
| DeliveryProvider             | organization_id, status, verification refs                           | Société partenaire.                       |
| DeliveryService              | provider, zones, hours, pricing_rule, supported_types                | Offre structurée.                         |
| DeliveryRequest              | delivery_id, source_order_ref, provider, pickup/dropoff refs, status | Cycle indépendant de l'Order.             |
| DeliveryAssignment           | delivery, provider/team/agent ref, assigned_at                       | V1 peut rester niveau société.            |
| DeliveryProof                | delivery, type, timestamp, evidence_ref                              | Preuve configurable.                      |
| CashCollectionResponsibility | delivery/order, responsible_party, amount                            | Toujours explicite si cash.               |
| DeliveryException            | delivery, code, case_id                                              | Failure/return/cancel sans écraser order. |

# 14. Job & Recruitment

| **Objet**                | **Champs clés**                                                        | **Règles**                                        |
|--------------------------|------------------------------------------------------------------------|---------------------------------------------------|
| JobPosting               | job_id, employer_ref, occupation, location, contract/work mode, status | Employer type explicite, y compris particulier.   |
| CandidateProfile         | identity_id, occupations, skills, location, discovery_consent          | Pas un compte séparé.                             |
| Application              | application_id, job_id, candidate, status, submitted_at                | Candidature historique.                           |
| ApplicationSnapshot      | CV/profile fields at submit                                            | Évite modification rétroactive du dossier soumis. |
| PipelineStage            | application, stage_code, changed_at                                    | Étapes employeur; pas verdict autonome.           |
| Interview                | interview_id, application, schedule, participants, status              | Permissions contextuelles.                        |
| ReferenceRequest         | candidate/application, referee contact private, consent, status        | Contact jamais public.                            |
| CandidateDiscoveryRecord | candidate, org/recruiter, reason/context                               | Accès seulement si consentement/permission.       |

# 15. Workforce Training

| **Objet**          | **Champs clés**                                                                                 | **Invariant**                                |
|--------------------|-------------------------------------------------------------------------------------------------|----------------------------------------------|
| TrainingProgram    | program_id, provider, skills, occupation relevance, prerequisites, format, duration, price mode | Pertinence factuelle.                        |
| TrainingCohort     | cohort_id, program, employer/private/public, schedule, capacity                                 | Cohorte publique/corporate.                  |
| TrainingInvitation | cohort, participant, inviter, context, status                                                   | Consentement/relationship.                   |
| Enrollment         | participant, cohort, status                                                                     | Accès limité au contexte training.           |
| AttendanceRecord   | enrollment, session, presence                                                                   | Administratif.                               |
| CompletionRecord   | enrollment, completed_at, issuer, evidence_ref                                                  | Provenance; n'implique pas compétence.       |
| CredentialClaim    | completion/certificate, claim text, verification state                                          | Ne pas confondre avec platform verification. |

# 16. Event, Ticket & CheckIn

| **Objet**         | **Champs clés**                                                | **Invariant**                               |
|-------------------|----------------------------------------------------------------|---------------------------------------------|
| Event             | event_id, organizer, type, visibility, schedule, venue, status | Public/private/restricted.                  |
| EventRegistration | event, attendee, status                                        | Distinct TicketOrder.                       |
| TicketType        | event, name, price, capacity, sale window                      | Inventory/capacity.                         |
| TicketOrder       | ticket_order_id, buyer, event, amount, status                  | Payment séparé.                             |
| Ticket            | ticket_id, ticket_order, attendee optional, token, status      | Unique; Valid/CheckedIn/Cancelled/Refunded. |
| CheckIn           | checkin_id, ticket, scanner, timestamp, result                 | Duplicate scan détectable.                  |
| GuestInvitation   | event, invitee/contact, status                                 | Invitation ≠ registration.                  |
| EventChange       | event, type cancel/postpone, effective_at                      | Déclenche communications/refund rules.      |

# 17. Campaigns, Nonprofits & Volunteering

| **Objet**             | **Champs clés**                                            | **Règles**                                   |
|-----------------------|------------------------------------------------------------|----------------------------------------------|
| Campaign              | campaign_id, organizer, purpose, dates, status             | Séparé Event.                                |
| VolunteerOpportunity  | opportunity_id, organization, role, schedule, requirements | Participation non emploi sauf explicitement. |
| VolunteerApplication  | opportunity, user, status                                  | Privacy/context.                             |
| CampaignParticipation | campaign, user/org, type, status                           | Support/participation.                       |
| DonationIntent        | campaign, donor, amount, status                            | Seulement si flux légal/payment activé.      |
| CampaignVerification  | campaign/org, verification refs                            | Claims précis.                               |

# 18. School, Beneficiary & Guardian

| **Objet**              | **Champs clés**                                                 | **Invariant**                  |
|------------------------|-----------------------------------------------------------------|--------------------------------|
| SchoolProfile          | organization_id, levels, campus info                            | Organisation spécialisée.      |
| Beneficiary            | beneficiary_id, minimal identity/profile fields, status         | Jamais profil public d'enfant. |
| GuardianRelationship   | guardian_user, beneficiary, relationship_type, authority_status | Source d'accès parent/tuteur.  |
| SchoolEnrollment       | beneficiary, school, section/class refs, status                 | Accès school-scoped.           |
| AdmissionCase          | applicant/beneficiary, school, status, evidence refs            | Données restreintes.           |
| BeneficiaryEventAccess | beneficiary/guardian, event, authorization                      | Private/restricted.            |
| SchoolDocument         | beneficiary/school, document_type, storage_ref                  | Sensitive/restricted.          |

# 19. Messaging & Notifications

| **Objet**               | **Champs clés**                                          | **Règles**                                 |
|-------------------------|----------------------------------------------------------|--------------------------------------------|
| Conversation            | conversation_id, context_type/ref, owner_scope, status   | Contextuelle à quote/order/job/etc.        |
| ConversationParticipant | conversation, principal_ref, role, joined/left           | Accès dérivé; révocable.                   |
| Message                 | message_id, conversation, sender, body/media, created_at | Persistent; moderation/report possible.    |
| MessageReceipt          | message, participant, delivered/read_at                  | Optionnel selon privacy/product.           |
| Notification            | notification_id, recipient, type, object_ref, status     | Dédoublée par event/key.                   |
| ActionItem              | recipient/team, action_type, object_ref, due/status      | Alimente À traiter.                        |
| NotificationPreference  | user, channel/type, preference                           | Respect obligations + critical exceptions. |

# 20. Verification, Review & Trust

| **Objet**             | **Champs clés**                                                                                                        | **Invariant**                                       |
|-----------------------|------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------|
| VerificationRecord    | verification_id, subject, type, method, status, assurance, evidence_ref, reviewer, dates, public_claim, policy_version | Claim public dérivé, preuve privée.                 |
| Review                | review_id, author, subject/object, interaction_ref, rating/text, status                                                | Interaction eligibility; pas universal trust score. |
| ReferenceVerification | subject, referee private, status, verified_at                                                                          | Public seulement compte/statut approprié.           |
| SuspiciousSignal      | signal_id, subject, signal_type, source, confidence/context                                                            | Signal ≠ décision finale.                           |
| TrustRestriction      | subject, capability/scope, reason, start/end                                                                           | Mesure proportionnée/auditée.                       |

# 21. Report, Case, Moderation & Appeal

| **Objet**        | **Champs clés**                                                   | **Règles**                      |
|------------------|-------------------------------------------------------------------|---------------------------------|
| Report           | report_id, reporter, target, category, evidence, created_at       | Entrée signalement.             |
| Case             | case_id, type, priority, subject refs, owner/team, status, reason | Objet opérationnel central.     |
| CaseEvent        | case, actor, action, note/evidence ref, timestamp                 | Timeline append-only.           |
| ModerationAction | target, action_type, reason, policy_version, actor                | Avant/après traçable.           |
| Appeal           | appeal_id, original_decision_ref, appellant, status, reviewer     | Décision initiale préservée.    |
| SafetyEscalation | case, severity, restricted notes, owner                           | Accès renforcé.                 |
| Resolution       | case, resolution_code, outcome, resolved_at                       | Structuré pour analytics/audit. |

# 22. Plans, Passes & Entitlements

| **Objet**          | **Champs clés**                                          | **Invariant**                     |
|--------------------|----------------------------------------------------------|-----------------------------------|
| CommercialProduct  | product_id, type plan/pass, market, status, price config | Prix configurable, pas hard-code. |
| PlanVersion        | plan, version, capabilities, quotas, effective dates     | Abonnés reliés à version.         |
| Subscription       | subscriber_ref, plan_version, status, period dates       | Commercial, pas permission.       |
| PassGrant          | subject, pass_type, start/end, status                    | Temporaire.                       |
| Entitlement        | subject, capability_code, source, limit, valid_from/to   | Droit d'usage, pas autorité.      |
| UsageCounter       | subject, capability, period, used/limit                  | Atomicité nécessaire.             |
| PromotionCredit    | subject, units/value, expiry, source                     | Ne modifie pas trust.             |
| BillingTransaction | commercial purpose, payment_ref, invoice/receipt refs    | Relié Payment sans le remplacer.  |

# 23. Promotion

| **Objet**                 | **Champs clés**                                               | **Règles**                             |
|---------------------------|---------------------------------------------------------------|----------------------------------------|
| PromotionCampaign         | promotion_id, owner, object_ref, placement, start/end, status | Objet promu doit rester éligible.      |
| PromotionBudget/CreditUse | promotion, entitlement/credit refs                            | Pas commission transaction.            |
| SponsoredPlacement        | promotion, placement, label, ranking inputs                   | Toujours identifié sponsorisé.         |
| PromotionMetric           | promotion, metric_type, count/date                            | Analytics séparé.                      |
| PromotionRestriction      | promotion, reason, moderation/case ref                        | Stop promotion sans restaurer contenu. |

# 24. Admin, Staff & Configuration

| **Objet**           | **Champs clés**                                             | **Invariant**                |
|---------------------|-------------------------------------------------------------|------------------------------|
| StaffAccount        | staff_user, employment/status refs, MFA state               | Pas compte partagé.          |
| StaffRoleAssignment | staff, role, scope, valid_from/to                           | Least privilege.             |
| AuditEvent          | actor, action, target, before/after refs, reason, timestamp | Protected/append-oriented.   |
| FeatureFlag         | flag_id, market/audience, state, version                    | Kill switch/config.          |
| MarketConfig        | market_id, currencies, providers, localization, ruleset     | Versionné.                   |
| PolicyVersion       | policy_id, version, effective_at, source/approval refs      | Décisions reproductibles.    |
| AdminExport         | requester, dataset/scope, purpose, status, artifact ref     | Permission + audit + expiry. |

# 25. Relations métier critiques

| **Relation**                      | **Cardinalité conceptuelle** | **Règle**                                 |
|-----------------------------------|------------------------------|-------------------------------------------|
| User → Identity                   | 1:N                          | Un compte, plusieurs activités/contextes. |
| User ↔ Organization               | N:N via Membership           | Jamais par simple sélection UI.           |
| Organization → Branch             | 1:N                          | Scope organisationnel.                    |
| Order → Payment                   | 1:N possible                 | Retries/attempts sans écraser Order.      |
| Order → Fulfillment               | 1:N selon évolution          | État indépendant.                         |
| Order/FoodOrder → DeliveryRequest | 0:N                          | Seulement partner delivery.               |
| Payment → Refund                  | 1:N                          | Cumul ≤ montant remboursable.             |
| Job → Application                 | 1:N                          | Candidate privacy scoped.                 |
| Application → Interview           | 1:N                          | Pas de verdict automatique.               |
| TrainingProgram → Cohort          | 1:N                          | Cohorte privée/publique.                  |
| Event → TicketType                | 1:N                          | Capacité contrôlée.                       |
| TicketOrder → Ticket              | 1:N                          | Émission après règle paiement.            |
| Conversation → Context object     | N:1                          | Contextual access.                        |
| VerificationRecord → Subject      | N:1                          | Plusieurs types de verification.          |
| Case → Business objects           | N:N refs                     | Un case peut relier plusieurs objets.     |
| CommercialProduct → Entitlement   | 1:N rules                    | Commercial != permission.                 |

# 26. Machines d'état de référence

| **Objet**         | **États V1 indicatifs**                                                                                                      |
|-------------------|------------------------------------------------------------------------------------------------------------------------------|
| Payment           | Initiated, Pending, Successful, Failed, Expired, Cancelled, ReconciliationRequired                                           |
| Refund            | Requested, UnderReview, Approved, Submitted, Processing, Refunded, Failed, Cancelled, Rejected                               |
| Marketplace Order | Draft/Placed, Confirmed, Cancelled, Completed + exception refs                                                               |
| FoodOrder         | Received, Accepted, Preparing, Ready, PickedUp/Delivered/Collected, Completed, Declined/Cancelled/Failed                     |
| DeliveryRequest   | Requested, Accepted, HeadingToPickup, PickedUp, InDelivery, Delivered, Declined, Cancelled, Failed, ReturnRequired, Returned |
| Ticket            | PendingIssue, Valid, CheckedIn, Cancelled, Refunded                                                                          |
| Application       | Submitted, InReview, Shortlisted, Interview, Offer/Outcome states configured, Withdrawn/Closed                               |
| Case              | Open, Triaged, Assigned, InReview, WaitingUser, WaitingProvider, WaitingInternal, Escalated, Resolved, Closed, Reopened      |
| Verification      | Pending, InReview, MoreInfo, Verified, Failed, Expired, Revoked                                                              |
| Entitlement       | Scheduled, Active, Exhausted, Expired, Revoked                                                                               |

# 27. Classification des données

| **Classe**       | **Exemples**                                                            | **Règle**                                                 |
|------------------|-------------------------------------------------------------------------|-----------------------------------------------------------|
| PUBLIC           | Nom entreprise, service publié, prix listing, public verification claim | Indexable seulement si visibilité le permet.              |
| ACCOUNT          | Préférences, saved searches, historique personnel                       | Utilisateur + services autorisés.                         |
| OPERATIONAL      | Adresse livraison active, booking details, order contact                | Seulement parties opérationnelles nécessaires.            |
| CONFIDENTIAL     | CV, applications, quotes privés, team data                              | Purpose + permission.                                     |
| HIGHLY SENSITIVE | Pièces identité, preuves verification, child docs, security evidence    | Accès très restreint; audit.                              |
| FINANCIAL        | Provider refs, payment/refund records                                   | Finance/authorized systems; minimiser données instrument. |
| SECURITY         | Session, auth factors, risk signals, incident evidence                  | Restricted; ne jamais public.                             |

# 28. Rétention & suppression - modèle de métadonnées

| **Champ**             | **Description**                                      |
|-----------------------|------------------------------------------------------|
| retention_class       | Classe définie après validation juridique.           |
| retention_start_event | Ex. account closure, case closure, transaction date. |
| retention_duration    | Configurable; À VALIDER JURIDIQUEMENT.               |
| legal_hold            | Empêche suppression si applicable.                   |
| deletion_method       | Delete/anonymize/archive selon objet.                |
| evidence_required     | Audit de suppression si requis.                      |
| owner                 | Domaine responsable.                                 |
| policy_version        | Règle ayant déclenché traitement.                    |

# 29. Invariants inter-domaines

- INV-01: aucun entitlement commercial ne crée une Membership, RoleAssignment ou VerificationRecord.

- INV-02: Payment Successful ne signifie pas automatiquement Order Completed.

- INV-03: Delivered ne signifie pas automatiquement Cash Paid.

- INV-04: Refund Approved ne signifie pas Refunded.

- INV-05: Training Completion ne signifie pas competence verified.

- INV-06: Identity Verified ne signifie pas safe/recommended/qualified.

- INV-07: Candidate discovery nécessite consentement/eligibility/permission indépendamment du plan Enterprise.

- INV-08: un enfant/beneficiary ne possède jamais de profil public V1.

- INV-09: DeliveryProvider ne reçoit que les données nécessaires à une mission assignée.

- INV-10: supprimer/retirer un membre organisation révoque l'accès mais ne supprime pas l'historique audit.

- INV-11: chaque changement financier est relié à une source autoritative/auditée.

- INV-12: chaque objet publié possède owner_ref, visibility et moderation state.

- INV-13: une catégorie NotPermitted bloque publication indépendamment de l'entitlement.

- INV-14: un Case peut observer/corréler les objets, mais ne remplace pas leur state machine.

- INV-15: les clients ne sont jamais la source autoritative d'un état financier.

# 30. Événements de domaine prioritaires

| **Event**                 | **Producteurs** | **Consommateurs possibles**         |
|---------------------------|-----------------|-------------------------------------|
| UserRegistered            | Identity        | Notifications, analytics            |
| MembershipChanged         | Organization    | Authorization, messaging, audit     |
| PublicationActivated      | Publishing      | Search, notifications               |
| OrderPlaced               | Commerce        | Payment, inventory, notifications   |
| PaymentStatusChanged      | Payments        | Commerce, ticketing, entitlements   |
| RefundStatusChanged       | Payments        | Commerce, support, notifications    |
| FoodOrderAccepted         | Food            | Customer notifications, fulfillment |
| DeliveryStatusChanged     | Delivery        | Order view, notifications           |
| ApplicationSubmitted      | Recruitment     | Employer inbox, notifications       |
| InterviewScheduled        | Recruitment     | Messaging/calendar notification     |
| TrainingEnrollmentChanged | Training        | Provider/employer/participant       |
| EventCancelled            | Events          | Tickets, refunds, notifications     |
| TicketCheckedIn           | Events          | Analytics/audit                     |
| VerificationStatusChanged | Trust           | Profile/public claim/eligibility    |
| CaseEscalated             | Support         | Ops alerts                          |
| EntitlementChanged        | Commercial      | Authorization capability checks     |
| PolicyVersionActivated    | Admin           | Relevant rule engines/caches        |

# 31. API & serialization rules

| **Règle**              | **Exigence**                                                  |
|------------------------|---------------------------------------------------------------|
| Stable IDs             | IDs opaques et non réutilisés.                                |
| Versioning             | Breaking API changes versionnés.                              |
| Enums                  | Clients tolèrent nouveaux états non destructivement.          |
| Money                  | amount + currency explicites.                                 |
| Dates                  | ISO 8601 API; timezone explicite si horaire local métier.     |
| Pagination             | Cursor recommandé pour grands flux.                           |
| Errors                 | code machine + message utilisateur localisable.               |
| Authorization          | Backend décide; UI hiding n'est pas sécurité.                 |
| Field filtering        | Réponse API retire champs non autorisés, pas seulement UI.    |
| Idempotency            | Clé sur créations/financial actions critiques.                |
| Optimistic concurrency | Version/ETag utile sur objets sensibles.                      |
| Snapshots              | Transaction lines conservent valeurs historiques nécessaires. |

# 32. Indexation & recherche

| **Donnée**                       | **Indexable?**                                                 |
|----------------------------------|----------------------------------------------------------------|
| Public Organization/Profile      | Oui si Active/Public.                                          |
| Public Service/Product/Event/Job | Oui selon visibility/policy.                                   |
| Private Event                    | Non dans index public.                                         |
| CandidateProfile                 | Seulement index privé spécialisé si consentement/eligibility.  |
| Exact home address               | Non public.                                                    |
| Identity documents               | Jamais.                                                        |
| Beneficiary/child                | Jamais public.                                                 |
| Messages                         | Pas index public; recherche interne contextuelle si autorisée. |
| Cases/moderation evidence        | Jamais public.                                                 |
| Taxonomy aliases                 | Oui comme aide de recherche, retourne canonique.               |

# 33. Analytics & minimisation

| **Principe**        | **Règle**                                         |
|---------------------|---------------------------------------------------|
| Event analytics     | Utiliser IDs pseudonymisés lorsque possible.      |
| PII                 | Ne pas copier email/téléphone dans chaque event.  |
| Financial analytics | Mesures agrégées; provider secrets exclus.        |
| Candidate analytics | Pas de scoring de personne universel.             |
| Child data          | Éviter analytics individualisées non nécessaires. |
| Retention           | Analytics raw data suit policy dédiée.            |
| Access              | Business dashboards ne voient que leur scope.     |
| Experiments         | Consent/privacy et feature eligibility respectés. |

# 34. Objets explicitement hors V1

| **Objet/capacité**                      | **Statut**                                                  |
|-----------------------------------------|-------------------------------------------------------------|
| PlatformWallet / StoredBalance          | Hors V1.                                                    |
| GeneralEscrowAccount                    | Hors V1.                                                    |
| Loan/CreditAccount                      | Hors V1.                                                    |
| UniversalTrustScore                     | Interdit par design.                                        |
| AutonomousHiringDecision                | Interdit par design.                                        |
| DriverTelematics/RouteOptimization      | Post-V1.                                                    |
| ComplexMultiSellerSettlement            | Post-V1.                                                    |
| AdvancedAssessment/TestEngine           | Post-V1.                                                    |
| LMSContentEngine                        | Post-V1.                                                    |
| SSO/SCIM objects                        | Post-V1.                                                    |
| General DelegationGrant                 | Post-V1 avancé.                                             |
| ManagedHeadhuntingMandate deep workflow | Future specialized recruitment app; bridge object possible. |

# 35. Critères d'acceptation du modèle de données

| **Test**   | **Critère**                                                                |
|------------|----------------------------------------------------------------------------|
| DATA-AC-01 | User peut exercer plusieurs activités sans comptes dupliqués.              |
| DATA-AC-02 | Membership/RoleAssignment déterminent l'autorité organisationnelle.        |
| DATA-AC-03 | Order, Payment, Fulfillment et Delivery conservent des états indépendants. |
| DATA-AC-04 | Retry payment crée/trace attempt sans double effet.                        |
| DATA-AC-05 | Refund cumulatif ne dépasse pas montant remboursable.                      |
| DATA-AC-06 | Cash Delivered ne change pas Payment sans confirmation.                    |
| DATA-AC-07 | Candidate discovery consent est interrogé au moment de l'accès.            |
| DATA-AC-08 | Training Completion n'écrit aucun VerifiedSkill automatique.               |
| DATA-AC-09 | Verification evidence n'apparaît jamais dans profil public.                |
| DATA-AC-10 | Child/Beneficiary est exclu de search public.                              |
| DATA-AC-11 | Delivery assignment contrôle disclosure adresse/contact.                   |
| DATA-AC-12 | Taxonomy label peut changer sans casser node_id.                           |
| DATA-AC-13 | Entitlement expiry n'efface pas objets historiques.                        |
| DATA-AC-14 | Staff role revoke coupe accès sans effacer AuditEvent.                     |
| DATA-AC-15 | Ticket duplicate scan est détectable.                                      |
| DATA-AC-16 | Conversation access suit participant/context scope.                        |
| DATA-AC-17 | Case closure n'altère pas l'état financier source.                         |
| DATA-AC-18 | Feature flag peut bloquer nouveau flux sans supprimer données.             |
| DATA-AC-19 | Financial objects conservent external provider refs.                       |
| DATA-AC-20 | Toute donnée Highly Sensitive a une règle d'accès et de retention.         |

# 36. Livrables techniques dérivés

| **Livrable**               | **Dérivation**                                     |
|----------------------------|----------------------------------------------------|
| ERD logique                | Objets/relations de ce document.                   |
| Database schema            | ERD + contraintes + index + migrations.            |
| OpenAPI schema             | Objets exposables + field-level access.            |
| Event catalog              | Section événements de domaine + payload contracts. |
| Authorization matrix       | Document 06 + object ownership/scopes.             |
| Data classification map    | Section 27 + Document 12.                          |
| Retention schedule         | Section 28 après validation juridique.             |
| Analytics event dictionary | Events utiles sans duplication PII.                |
| Seed/test data model       | Document 10 + objets ici.                          |
| Admin object views         | Document 09 + classifications.                     |

# 37. Règles pour le développeur

- Ne pas créer un type de compte distinct pour chaque activité.

- Ne pas stocker un même état dans plusieurs objets comme source de vérité concurrente.

- Ne pas utiliser le frontend comme contrôle d'autorisation.

- Ne pas coupler un plan commercial à une permission organisationnelle.

- Ne pas fusionner Payment, Order et Delivery dans une seule colonne status.

- Ne pas hard-coder prix, catégories, aliases, règles marché ou seuils juridiques.

- Ne pas rendre public un champ simplement parce qu'il existe dans l'objet.

- Utiliser transactions/locks/idempotency sur stock, booking, quota et finance.

- Conserver snapshots transactionnels lorsque l'objet source peut changer.

- Documenter toute divergence entre schéma final et ce modèle conceptuel.

# 38. Liens avec la suite documentaire

| **Document**        | **Lien**                                          |
|---------------------|---------------------------------------------------|
| Document 01         | Fonctionnalités qui consomment/créent les objets. |
| Document 02         | Parcours qui déclenchent transitions.             |
| Document 03         | TaxonomyNode/Attribute/Alias/PolicyRule.          |
| Document 05         | CommercialProduct/Subscription/Entitlement.       |
| Document 06         | Ownership, permissions et scopes sur objets.      |
| Document 07         | Verification/Review/Report/Moderation.            |
| Document 08         | Order/Payment/Refund/Fulfillment/Delivery.        |
| Document 09         | Case/Admin/Audit/Staff views.                     |
| Document 10         | Tests des invariants.                             |
| Document 12         | Classification, retention et legal gates.         |
| Document 14 à venir | Index maître de toute la documentation.           |

# 39. Règle finale

Le modèle de données doit préserver la vérité métier avant la commodité d'interface. Lorsque deux concepts peuvent évoluer indépendamment, être autorisés différemment, avoir des preuves distinctes ou être corrigés séparément, ils doivent rester des objets distincts. Cette séparation est particulièrement impérative pour identité/autorité, permissions/entitlements, commande/paiement/fulfillment/livraison, verification/recommandation, formation/compétence et case/décision métier.
