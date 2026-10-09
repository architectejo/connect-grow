**REGISTRE JURIDIQUE, CONFORMITÉ & POLITIQUES À VALIDER**

**Plateforme Écosystème RDC**

*Document 12 - Registre de validation avant production et expansion*

Version de référence V1 - Septembre 2026

# 1. Objet et statut de ce document

Ce registre centralise les questions juridiques, réglementaires, fiscales, contractuelles et de conformité qui doivent être confirmées par des professionnels qualifiés avant lancement ou activation d'un flux concerné. Il ne constitue pas un avis juridique et ne remplace ni un conseil juridique en RDC, ni les exigences contractuelles des fournisseurs de paiement, partenaires ou autorités compétentes.

Règle: lorsqu'une réponse juridique n'est pas encore validée, le produit conserve une règle configurable ou un gate d'activation. Le logiciel ne doit pas transformer une hypothèse de travail en obligation juridique prétendument certaine.

# 2. Statuts du registre

| **Statut**     | **Signification**                                   |
|----------------|-----------------------------------------------------|
| OPEN           | Question identifiée, réponse non validée.           |
| IN REVIEW      | Analyse en cours par responsable/conseil.           |
| VALIDATED      | Position validée, source/date/version enregistrées. |
| CONDITIONAL    | Valide sous conditions ou pour un scope précis.     |
| BLOCKER        | Empêche lancement/activation tant que non résolu.   |
| SUPERSEDED     | Remplacé par décision/version plus récente.         |
| NOT APPLICABLE | Non applicable au scope après revue documentée.     |

# 3. Gouvernance de validation

| **Champ du registre** | **Exigence**                                              |
|-----------------------|-----------------------------------------------------------|
| legal_item_id         | Identifiant stable.                                       |
| domain                | Privacy, commerce, employment, payment, tax, etc.         |
| question              | Question précise à trancher.                              |
| market                | RDC / province / autre marché si pertinent.               |
| product_scope         | Module/flow concerné.                                     |
| risk_level            | Critical / High / Medium / Low.                           |
| launch_gate           | Oui/Non; fonctionnalité bloquée si nécessaire.            |
| owner                 | Responsable interne.                                      |
| reviewer              | Conseil juridique/fiscal/compliance compétent.            |
| source_refs           | Texte, contrat, décision, avis ou documentation provider. |
| decision              | Règle validée en langage opérationnel.                    |
| effective_date        | Date d'effet.                                             |
| review_date           | Date de prochaine revue.                                  |
| policy_version        | Version de policy/config associée.                        |
| implementation_refs   | Feature flag, rule/config, document, test.                |

# 4. Registre maître - Corporate & plateforme

| **ID**      | **Question à valider**                                                                | **Risque** | **Gate** |
|-------------|---------------------------------------------------------------------------------------|------------|----------|
| LEG-CORP-01 | Structure juridique de l'opérateur de plateforme et autorisations nécessaires en RDC. | Critical   | Oui      |
| LEG-CORP-02 | Mentions légales obligatoires dans app/site et informations opérateur.                | High       | Oui      |
| LEG-CORP-03 | Conditions générales d'utilisation et règles contractuelles par type d'utilisateur.   | Critical   | Oui      |
| LEG-CORP-04 | Capacité contractuelle des utilisateurs, notamment mineurs et représentants.          | High       | Oui      |
| LEG-CORP-05 | Règles applicables aux représentants autorisés d'organisations.                       | High       | Oui      |
| LEG-CORP-06 | Responsabilité/intermédiation de la plateforme selon chaque module.                   | Critical   | Oui      |
| LEG-CORP-07 | Processus de notification et modification des conditions/policies.                    | Medium     | Non      |
| LEG-CORP-08 | Exigences d'archivage des consentements et versions contractuelles.                   | High       | Oui      |

# 5. Données personnelles & confidentialité

| **ID**     | **Question à valider**                                                     | **Produit concerné** | **Gate** |
|------------|----------------------------------------------------------------------------|----------------------|----------|
| LEG-PRV-01 | Bases légales/finalités de traitement par catégorie de données.            | Tous modules         | Oui      |
| LEG-PRV-02 | Contenu et forme de la politique de confidentialité.                       | Tous modules         | Oui      |
| LEG-PRV-03 | Consentements nécessaires et situations où une autre base s'applique.      | Consent/Privacy      | Oui      |
| LEG-PRV-04 | Droits d'accès, correction, opposition, suppression/retention applicables. | Compte               | Oui      |
| LEG-PRV-05 | Durées de conservation par type de données et preuve.                      | Tous modules         | Oui      |
| LEG-PRV-06 | Transferts internationaux / hébergement hors RDC et garanties requises.    | Infrastructure       | Oui      |
| LEG-PRV-07 | Sous-traitants: contrats, instructions, sécurité et liste.                 | Providers            | Oui      |
| LEG-PRV-08 | Notification d'incident/violation de données: seuil, délai, destinataires. | Security             | Oui      |
| LEG-PRV-09 | Journalisation, monitoring et limites de surveillance interne.             | Admin/Security       | High     |
| LEG-PRV-10 | Export/portabilité des données et format requis.                           | Compte               | Medium   |
| LEG-PRV-11 | Marketing direct, opt-in/opt-out et communications promotionnelles.        | Growth               | High     |
| LEG-PRV-12 | Cookies/SDK/device identifiers et consentement applicable.                 | Web/Mobile           | High     |

# 6. Mineurs, écoles, parents & bénéficiaires

| **ID**     | **Question**                                             | **Règle produit provisoire**                         | **Gate** |
|------------|----------------------------------------------------------|------------------------------------------------------|----------|
| LEG-MIN-01 | Âge/capacité pour créer un compte ou consentir.          | Pas de supposition automatique; policy configurable. | Oui      |
| LEG-MIN-02 | Autorité parentale/tutelle et preuve de relation.        | Accès uniquement via relation autorisée.             | Oui      |
| LEG-MIN-03 | Traitement de données d'enfants par écoles/parents.      | Data minimization; pas de profil enfant public.      | Oui      |
| LEG-MIN-04 | Images, communications et événements impliquant mineurs. | Consent/purpose controls.                            | Oui      |
| LEG-MIN-05 | Conservation des dossiers bénéficiaires/enfants.         | Durée à valider.                                     | Oui      |
| LEG-MIN-06 | Signalement de risque/abus impliquant mineur.            | Safety escalation; procédure légale à valider.       | Oui      |

# 7. Marketplace & protection du consommateur

| **ID**     | **Question**                                                                | **Gate**        |
|------------|-----------------------------------------------------------------------------|-----------------|
| LEG-MKT-01 | Obligations d'information vendeur professionnel vs particulier.             | Oui             |
| LEG-MKT-02 | Règles prix, description, disponibilité et pratiques trompeuses.            | Oui             |
| LEG-MKT-03 | Droits de retour/rétractation applicables selon vendeur/produit/canal.      | Oui             |
| LEG-MKT-04 | Produits interdits, réglementés ou nécessitant autorisation.                | Oui             |
| LEG-MKT-05 | Responsabilité plateforme pour annonces, contrefaçon et produits dangereux. | Oui             |
| LEG-MKT-06 | Procédure notice/takedown et conservation de preuves.                       | High            |
| LEG-MKT-07 | Obligations de reçu/facture vendeur.                                        | Oui             |
| LEG-MKT-08 | Garanties légales/contractuelles et information utilisateur.                | High            |
| LEG-MKT-09 | Règles de livraison, perte, dommage et transfert de responsabilité.         | High            |
| LEG-MKT-10 | Litiges transfrontaliers si vendeurs/acheteurs hors RDC activés.            | Avant expansion |

# 8. Paiements, Mobile Money & flux financiers

| **ID**     | **Question**                                                           | **Règle d'architecture**                               | **Gate** |
|------------|------------------------------------------------------------------------|--------------------------------------------------------|----------|
| LEG-PAY-01 | Rôle juridique exact de la plateforme dans le paiement.                | Provider-agnostic; ne pas prétendre détenir les fonds. | Oui      |
| LEG-PAY-02 | Licences/agréments requis selon flux de paiement envisagés.            | Pas de wallet/escrow général V1.                       | Oui      |
| LEG-PAY-03 | Conditions contractuelles des providers Mobile Money/paiement.         | Adapter par provider.                                  | Oui      |
| LEG-PAY-04 | KYC/KYB exigé pour marchands/organisateurs/recipients.                 | Eligibility configurable.                              | Oui      |
| LEG-PAY-05 | Refund obligations, délais et responsabilités.                         | Refund workflow configurable.                          | Oui      |
| LEG-PAY-06 | Chargebacks/transactions non autorisées si provider les supporte.      | Case + provider process.                               | High     |
| LEG-PAY-07 | Cash collection par seller/restaurant/delivery company.                | Responsabilité explicite.                              | Oui      |
| LEG-PAY-08 | Settlement et éventuels reversements aux marchands/organisateurs.      | Ne pas inventer settlement propriétaire.               | Oui      |
| LEG-PAY-09 | Frais provider et présentation des frais aux utilisateurs.             | Prix/frais configurables.                              | Oui      |
| LEG-PAY-10 | Conservation des références/transactions et exigences AML applicables. | Data minimization + audit.                             | Oui      |

# 9. Fiscalité, facturation & comptabilité

| **ID**     | **Question**                                                                      | **Gate**        |
|------------|-----------------------------------------------------------------------------------|-----------------|
| LEG-TAX-01 | Taxes applicables aux abonnements, passes et promotion vendus par la plateforme.  | Oui             |
| LEG-TAX-02 | Devise(s), conversion et règles d'affichage comptable/fiscal.                     | Oui             |
| LEG-TAX-03 | Exigences de facture/reçu de la plateforme.                                       | Oui             |
| LEG-TAX-04 | Responsabilité de facture commerciale/fiscale du vendeur/restaurant/organisateur. | Oui             |
| LEG-TAX-05 | Traitement fiscal des remboursements/avoirs.                                      | High            |
| LEG-TAX-06 | Traitement des frais provider externes.                                           | High            |
| LEG-TAX-07 | Conservation des pièces comptables et transactions.                               | Oui             |
| LEG-TAX-08 | Obligations fiscales lors d'expansion dans autre marché.                          | Avant expansion |

# 10. Emploi, recrutement & household employment

| **ID**     | **Question**                                                              | **Règle produit provisoire**                                   | **Gate** |
|------------|---------------------------------------------------------------------------|----------------------------------------------------------------|----------|
| LEG-JOB-01 | Règles de publication d'offres et informations obligatoires.              | Template configurable.                                         | Oui      |
| LEG-JOB-02 | Critères de discrimination interdits dans offres/filtrage.                | Policy + moderation.                                           | Oui      |
| LEG-JOB-03 | Données candidats: collecte, partage, retention, consentement.            | Purpose-based access.                                          | Oui      |
| LEG-JOB-04 | Enterprise candidate discovery et consentement nécessaire.                | Opt-in distinct.                                               | Oui      |
| LEG-JOB-05 | Références professionnelles: consentement et responsabilité.              | Consent-based; contacts privés.                                | Oui      |
| LEG-JOB-06 | Statut/responsabilités Employeur particulier pour travail domestique.     | Label clair; règles à valider.                                 | Oui      |
| LEG-JOB-07 | Contrats/salaires/obligations employeur: rôle de la plateforme.           | Pas de commission salaire; ne pas se substituer à l'employeur. | Oui      |
| LEG-JOB-08 | Frais de recrutement éventuellement interdits aux candidats/travailleurs. | Candidature V1 gratuite.                                       | Oui      |
| LEG-JOB-09 | Conservation des dossiers après clôture d'un recrutement.                 | TBD.                                                           | High     |
| LEG-JOB-10 | Background/reference checks pour catégories sensibles.                    | Seulement contrôles légalement autorisés.                      | Oui      |

# 11. Prestataires individuels & professions réglementées

| **ID**     | **Question**                                                                          | **Gate**        |
|------------|---------------------------------------------------------------------------------------|-----------------|
| LEG-PRO-01 | Professions nécessitant licence, diplôme, ordre ou autorisation.                      | Oui             |
| LEG-PRO-02 | Formulation publique des badges/certifications.                                       | Oui             |
| LEG-PRO-03 | Validité/expiration des documents professionnels.                                     | High            |
| LEG-PRO-04 | Catégories à Enhanced Due Diligence: garde d'enfants, soins, sécurité, conduite, etc. | Oui             |
| LEG-PRO-05 | Responsabilité de la plateforme lors d'une mise en relation.                          | Oui             |
| LEG-PRO-06 | Assurance professionnelle éventuellement obligatoire/recommandée.                     | Selon catégorie |
| LEG-PRO-07 | Travail indépendant vs relation de travail: risques de requalification.               | Oui             |

# 12. Restaurants, alimentation & livraison

| **ID**     | **Question**                                                       | **Gate**      |
|------------|--------------------------------------------------------------------|---------------|
| LEG-FOD-01 | Autorisations/licences et obligations applicables aux restaurants. | Oui           |
| LEG-FOD-02 | Informations alimentaires/allergènes si légalement requises.       | Oui           |
| LEG-FOD-03 | Responsabilité pour sécurité alimentaire et incidents.             | Oui           |
| LEG-FOD-04 | Annulation/refund après préparation.                               | Oui           |
| LEG-DLV-01 | Statut contractuel des sociétés partenaires de livraison.          | Oui           |
| LEG-DLV-02 | Responsabilité perte/dommage/retard et preuve de remise.           | Oui           |
| LEG-DLV-03 | Collecte cash par livreur/société et reddition des fonds.          | Oui           |
| LEG-DLV-04 | Données de localisation/adresse transmises aux partenaires.        | Oui           |
| LEG-DLV-05 | Assurances/autorisation transport éventuellement requises.         | Selon service |

# 13. Événements & ticketing

| **ID**     | **Question**                                                  | **Gate**                                |
|------------|---------------------------------------------------------------|-----------------------------------------|
| LEG-EVT-01 | Conditions de vente des billets et informations organisateur. | Oui                                     |
| LEG-EVT-02 | Annulation/report: obligations refund/choice.                 | Oui                                     |
| LEG-EVT-03 | Frais de service éventuels et affichage.                      | Oui                                     |
| LEG-EVT-04 | Capacité/autorisation/conditions propres aux événements.      | Responsabilité organisateur à clarifier |
| LEG-EVT-05 | Événements privés et traitement guest list.                   | High                                    |
| LEG-EVT-06 | QR/ticket nominatif et données à l'entrée.                    | High                                    |
| LEG-EVT-07 | Événements impliquant mineurs.                                | Oui                                     |
| LEG-EVT-08 | Revente/transfert de billets si fonctionnalité future.        | Post-V1                                 |

# 14. Formation & certifications

| **ID**     | **Question**                                                  | **Gate**        |
|------------|---------------------------------------------------------------|-----------------|
| LEG-TRN-01 | Prestataires/organismes nécessitant autorisation ou agrément. | Selon catégorie |
| LEG-TRN-02 | Utilisation du terme certificat/certification/accréditation.  | Oui             |
| LEG-TRN-03 | Responsabilité sur résultats/compétence après formation.      | Oui             |
| LEG-TRN-04 | Données salariés/candidats partagées au training provider.    | Oui             |
| LEG-TRN-05 | Conditions corporate cohort/quote/cancellation.               | High            |

# 15. Nonprofits, campagnes & collecte de fonds

| **ID**     | **Question**                                            | **Gate** |
|------------|---------------------------------------------------------|----------|
| LEG-NPO-01 | Statut/verification des associations et organismes.     | Oui      |
| LEG-NPO-02 | Règles applicables aux appels aux dons/campagnes.       | Oui      |
| LEG-NPO-03 | Flux de paiement/collecte et responsabilité plateforme. | Oui      |
| LEG-NPO-04 | Transparence sur destination des fonds.                 | Oui      |
| LEG-NPO-05 | Campagnes interdites/restrictives et moderation.        | Oui      |
| LEG-NPO-06 | Reçus fiscaux/dons si applicables.                      | Oui      |

# 16. Contenus, modération & sécurité

| **ID**     | **Question**                                                         | **Gate** |
|------------|----------------------------------------------------------------------|----------|
| LEG-MOD-01 | Catégories de contenus illégaux/interdits à intégrer à policy RDC.   | Oui      |
| LEG-MOD-02 | Procédure de retrait et conservation des preuves.                    | Oui      |
| LEG-MOD-03 | Obligations face aux menaces, exploitation, fraude ou abus.          | Oui      |
| LEG-MOD-04 | Réponse aux demandes des autorités et vérification de leur validité. | Oui      |
| LEG-MOD-05 | Voie d'appel et notification de décision.                            | High     |
| LEG-MOD-06 | Conservation de contenus supprimés pour sécurité/litige.             | Oui      |
| LEG-MOD-07 | Diffamation, harcèlement et avis utilisateurs.                       | High     |
| LEG-MOD-08 | Suspension/termination contractuelle des comptes.                    | Oui      |

# 17. Verification, identité & documents

| **ID**     | **Question**                                                                | **Gate**                                  |
|------------|-----------------------------------------------------------------------------|-------------------------------------------|
| LEG-IDV-01 | Documents d'identité pouvant être collectés/validés.                        | Oui                                       |
| LEG-IDV-02 | Conservation ou non des copies après vérification.                          | Oui                                       |
| LEG-IDV-03 | Utilisation de prestataire tiers de verification.                           | Oui                                       |
| LEG-IDV-04 | Âge/minimum et vérification d'âge si nécessaire.                            | Oui                                       |
| LEG-IDV-05 | Claim public permis: « identité vérifiée », « organisation vérifiée », etc. | Oui                                       |
| LEG-IDV-06 | Renouvellement/expiration/revocation des vérifications.                     | High                                      |
| LEG-IDV-07 | Données biométriques si envisagées un jour.                                 | Post-V1; revue renforcée avant tout usage |

# 18. Marketing, promotion & classements

| **ID**     | **Question**                                              | **Gate**                               |
|------------|-----------------------------------------------------------|----------------------------------------|
| LEG-ADV-01 | Identification obligatoire des contenus sponsorisés.      | Oui                                    |
| LEG-ADV-02 | Allégations marketing interdites/trompeuses.              | Oui                                    |
| LEG-ADV-03 | Utilisation logos/marques/nom des partenaires.            | Oui                                    |
| LEG-ADV-04 | Règles concours/referrals/incentives si activés.          | Avant activation                       |
| LEG-ADV-05 | Ciblage publicitaire à partir de données personnelles.    | Oui si activé                          |
| LEG-ADV-06 | Publicité/ciblage impliquant mineurs.                     | Bloqué sans revue juridique spécifique |
| LEG-ADV-07 | Comparatifs/recommandations automatisées et transparence. | Post-V1/selon fonctionnalité           |

# 19. Propriété intellectuelle

| **ID**    | **Question**                                                                | **Gate**          |
|-----------|-----------------------------------------------------------------------------|-------------------|
| LEG-IP-01 | Licence accordée à la plateforme sur contenus utilisateurs.                 | Oui               |
| LEG-IP-02 | Garanties utilisateur sur droits des images/textes/logos.                   | Oui               |
| LEG-IP-03 | Procédure de plainte copyright/marque.                                      | Oui               |
| LEG-IP-04 | Usage des marques partenaires dans UI/marketing.                            | Oui               |
| LEG-IP-05 | Propriété des contenus/logiciels créés pour la plateforme par prestataires. | Oui               |
| LEG-IP-06 | Licences open source et obligations de distribution.                        | Oui avant release |

# 20. Accessibilité, égalité & non-discrimination

| **ID**    | **Question**                                                       | **Gate**  |
|-----------|--------------------------------------------------------------------|-----------|
| LEG-EQ-01 | Obligations d'accessibilité numérique applicables.                 | À valider |
| LEG-EQ-02 | Non-discrimination dans emploi/services/marketplace.               | Oui       |
| LEG-EQ-03 | Accommodation/accessibility dans événements/booking si applicable. | À valider |
| LEG-EQ-04 | Langues/informations obligatoires au consommateur.                 | Oui       |

# 21. Cybersécurité & preuve électronique

| **ID**     | **Question**                                                                  | **Gate**   |
|------------|-------------------------------------------------------------------------------|------------|
| LEG-SEC-01 | Exigences légales minimales de sécurité applicables aux données/transactions. | Oui        |
| LEG-SEC-02 | Valeur/procédure de conservation des logs comme preuve.                       | Oui        |
| LEG-SEC-03 | Signature électronique/acceptation numérique si utilisée.                     | Selon flux |
| LEG-SEC-04 | Notification des incidents aux parties/autorités.                             | Oui        |
| LEG-SEC-05 | Tests de sécurité et responsabilités prestataires.                            | Oui        |
| LEG-SEC-06 | Localisation/accès aux backups et logs.                                       | Oui        |

# 22. Contrats partenaires prioritaires

| **Contrat**           | **Clauses à couvrir**                                                        |
|-----------------------|------------------------------------------------------------------------------|
| Payment provider      | Rôles, settlement, refunds, fraud, outages, data, reconciliation, liability. |
| Delivery company      | Zones, SLA, cash collection, loss/damage, privacy, incidents.                |
| Restaurant/merchant   | Listings/menu, fulfillment, cancellations, refunds, compliance.              |
| Employer/Recruiter    | Jobs, candidate data, discrimination, confidentiality.                       |
| Training provider     | Program claims, participant data, completion/certificate provenance.         |
| Event organizer       | Ticketing, cancellation, refunds, capacity, check-in, attendee data.         |
| School                | Authority, parent/beneficiary data, minors, access.                          |
| Verification provider | Data handling, assurance, retention, incidents.                              |
| Cloud/communications  | Data processing, security, availability, subprocessors.                      |

# 23. Documents/policies à produire avant lancement

| **Document**                                      | **Statut attendu**         |
|---------------------------------------------------|----------------------------|
| Conditions Générales d'Utilisation                | Validé                     |
| Politique de Confidentialité                      | Validé                     |
| Politique Marketplace / vendeur                   | Validé                     |
| Politique Retours & Remboursements                | Validé                     |
| Conditions Ticketing / événements                 | Validé                     |
| Conditions Jobs & Recruitment                     | Validé                     |
| Politique Verification                            | Validé                     |
| Standards communautaires / contenu                | Validé                     |
| Politique de signalement & appeal                 | Validé                     |
| Politique cookies/SDK web si applicable           | Validé                     |
| Conditions plans/passes/promotion                 | Validé                     |
| Notices spécifiques mineurs/écoles si nécessaires | Validé avant activation    |
| Data Processing Agreements fournisseurs           | Signés selon rôle          |
| Partner agreements                                | Signés selon module activé |

# 24. Feature gates juridiques

| **Feature**                    | **Gate minimal**                                    |
|--------------------------------|-----------------------------------------------------|
| Mobile Money production        | LEG-PAY + provider contract + Finance/Ops readiness |
| Cash via delivery partner      | Contract + cash responsibility + dispute procedure  |
| Marketplace regulated category | Category legal status + verification/policy         |
| Household recruitment          | Employment/privacy rules + support/safety           |
| Candidate discovery            | Consent/privacy validation                          |
| Sensitive provider profile     | EDD requirements + public claim language            |
| Paid ticketing                 | Ticket/refund/tax/payment validation                |
| Private school/child data      | Minor/privacy/authority validation                  |
| Fundraising/donations          | NPO/payment/tax validation                          |
| New city/country               | Market-specific legal register review               |

# 25. Matrice risque x action

| **Niveau** | **Traitement**                                                                 |
|------------|--------------------------------------------------------------------------------|
| Critical   | Feature bloquée jusqu'à validation; executive/product/legal sign-off.          |
| High       | Validation avant public launch ou avant flux concerné.                         |
| Medium     | Peut avancer en staging/pilot contrôlé si mitigation documentée.               |
| Low        | Backlog conformité avec owner/date.                                            |
| Unknown    | Traiter comme High jusqu'à qualification si données/argent/sécurité impliqués. |

# 26. Processus de changement juridique

| **Étape**   | **Action**                                                             |
|-------------|------------------------------------------------------------------------|
| Detect      | Nouvelle loi, interprétation, contrat provider, incident ou expansion. |
| Assess      | Identifier modules, données, utilisateurs et contrats affectés.        |
| Decide      | Conseil qualifié formalise règle et date d'effet.                      |
| Version     | Mettre à jour policy/config/legal register.                            |
| Implement   | Feature flag, rule engine, UI/copy, data flow.                         |
| Test        | Ajouter/mettre à jour tests Document 10.                               |
| Communicate | Notifier utilisateurs/partenaires si requis.                           |
| Audit       | Conserver ancienne/nouvelle version et approbations.                   |
| Review      | Vérifier après mise en production.                                     |

# 27. Registre des décisions - modèle

| **Champ**          | **Exemple de format**                    |
|--------------------|------------------------------------------|
| Decision ID        | DEC-LEGAL-YYYY-NNN                       |
| Linked legal items | LEG-PAY-05; LEG-MKT-03                   |
| Decision summary   | Règle opérationnelle validée             |
| Scope              | RDC / Marketplace / professional sellers |
| Effective from     | YYYY-MM-DD                               |
| Approved by        | Role/name selon gouvernance              |
| Source             | Texte/avis/contrat référencé             |
| Product action     | Config/policy/UI change                  |
| Test refs          | REF-xx / MKT-xx                          |
| Next review        | YYYY-MM-DD                               |

# 28. Critères d'acceptation conformité

| **Test**  | **Critère**                                                                                    |
|-----------|------------------------------------------------------------------------------------------------|
| LEG-AC-01 | Chaque feature financière publique possède un legal owner et provider/contract owner.          |
| LEG-AC-02 | Aucun document d'identité n'est rendu public.                                                  |
| LEG-AC-03 | Les claims Verified correspondent à une décision validée et un Verification Record.            |
| LEG-AC-04 | Les politiques affichées sont versionnées et leur acceptation est traçable lorsque nécessaire. |
| LEG-AC-05 | Les durées de retention configurées correspondent au registre validé.                          |
| LEG-AC-06 | Une catégorie réglementée peut être désactivée sans release applicative.                       |
| LEG-AC-07 | Un changement de règle refund est versionné et testé.                                          |
| LEG-AC-08 | Le produit distingue reçu de paiement et facture fiscale/commerciale.                          |
| LEG-AC-09 | Candidate discovery respecte le consentement validé.                                           |
| LEG-AC-10 | Aucun profil public d'enfant n'existe.                                                         |
| LEG-AC-11 | Les demandes autorités passent par une procédure staff restreinte.                             |
| LEG-AC-12 | Les contrats partenaires identifient responsabilité data et incidents.                         |
| LEG-AC-13 | Le marketing ne présente pas verification comme garantie de sécurité/qualité.                  |
| LEG-AC-14 | Un feature gate bloque les flux dont le statut juridique est BLOCKER.                          |
| LEG-AC-15 | Une expansion marché déclenche une nouvelle revue conformité.                                  |
| LEG-AC-16 | Les anciennes versions de policies/décisions restent auditables.                               |
| LEG-AC-17 | Les frais/prix affichés viennent d'une configuration approuvée.                                |
| LEG-AC-18 | Les actions de suppression/retention respectent legal holds si applicables.                    |
| LEG-AC-19 | Toute nouvelle collecte de donnée sensible déclenche privacy review.                           |
| LEG-AC-20 | Le Go/No-Go Document 10 inclut les blockers de ce registre.                                    |

# 29. Priorités avant beta et avant GA

| **Moment**                 | **Must resolve**                                                                                               |
|----------------------------|----------------------------------------------------------------------------------------------------------------|
| Avant closed beta          | Privacy baseline, terms beta, staff confidentiality, pilot contracts, minors excluded/protected as applicable. |
| Avant paiements réels      | Payment role, provider contracts, refund rules, tax/receipt baseline, reconciliation.                          |
| Avant Marketplace public   | Seller obligations, prohibited goods, returns/disputes, consumer information.                                  |
| Avant recruitment public   | Candidate privacy, employer rules, household employment, discrimination policy.                                |
| Avant ticketing public     | Organizer terms, refund/cancellation, tax/payment.                                                             |
| Avant food/delivery public | Restaurant/delivery contracts, cash, privacy, responsibility.                                                  |
| Avant schools/minors       | Full minors/parent/school validation.                                                                          |
| Avant fundraising          | NPO/fundraising/payment/tax validation.                                                                        |
| Avant GA Kinshasa          | Tous launch blockers applicables = VALIDATED/CONDITIONAL avec controls.                                        |
| Avant expansion            | Market-specific refresh du registre.                                                                           |

# 30. Ce document ne doit pas faire

- Déclarer qu'une pratique est légale uniquement parce qu'elle est techniquement possible.

- Transformer un exemple de prix, délai ou seuil en obligation juridique.

- Supposer que les règles d'un autre pays s'appliquent automatiquement en RDC.

- Remplacer le conseil d'un avocat, fiscaliste ou spécialiste réglementaire qualifié.

- Inventer une licence, autorité, taxe ou délai réglementaire non vérifié.

- Figer dans le code une règle susceptible de changer par marché, catégorie ou provider.

- Confondre les conditions contractuelles d'un provider avec la loi générale.

- Utiliser « Verified » comme garantie de sécurité, qualité ou légalité globale.

# 31. Liens avec les documents maîtres

| **Document**               | **Lien conformité**                                                   |
|----------------------------|-----------------------------------------------------------------------|
| Document 03 - Taxonomie    | Policy states et catégories réglementées.                             |
| Document 05 - Plans        | Prix, facturation, promotion et entitlements.                         |
| Document 06 - Accès        | Purpose/scopes et staff access.                                       |
| Document 07 - Trust/Safety | Verification, moderation, evidence, appeals.                          |
| Document 08 - Commerce     | Payment/refund/return/dispute rules.                                  |
| Document 09 - Back-office  | Restricted staff procedures and audit.                                |
| Document 10 - Tests        | Legal acceptance criteria deviennent tests.                           |
| Document 11 - Lancement    | Les blockers conditionnent beta/GA/expansion.                         |
| Document 13 à venir        | Dictionnaire de données utilisera classifications/retention validées. |

# 32. Règle finale

La plateforme doit être conçue pour que la conformité puisse être prouvée, configurée et révisée. Une décision juridique validée doit pouvoir être reliée à une règle produit, une version de politique, une permission ou un feature gate, un test et un audit. Tant qu'une question critique n'est pas validée, le système doit privilégier la restriction ou la désactivation du flux concerné plutôt que l'hypothèse.
