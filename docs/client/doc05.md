**CATALOGUE DES OFFRES, PLANS, PASSES & ENTITLEMENTS**

**Plateforme Écosystème RDC**

*Document 05 - Architecture commerciale et droits d'usage V1*

Version de travail · Septembre 2026

**Les prix définitifs ne sont pas fixés dans ce document.**

# 1. Objet du document

Ce document définit comment la plateforme transforme son modèle économique en capacités commerciales concrètes. Il précise ce qui est gratuit, ce qui peut relever d'un abonnement, d'un pass temporaire, d'un achat ponctuel ou d'une promotion, et surtout ce qu'un paiement ne peut jamais acheter.

Il complète le Document 04 - Modèle financier - en séparant clairement le prix, qui reste à décider, du droit d'usage technique, appelé ici entitlement.

# 2. Les cinq notions à ne jamais confondre

| **Notion**                | **Question à laquelle elle répond**                       | **Exemple**                                             | **Le paiement peut-il la créer ?**      |
|---------------------------|-----------------------------------------------------------|---------------------------------------------------------|-----------------------------------------|
| Identité / contexte actif | Au nom de qui agit-on ?                                   | Individu; Prestataire individuel; ABC SARL              | Non                                     |
| Permission                | Que peut faire cet acteur dans ce contexte ?              | Publier une offre d'emploi pour une branche             | Non, elle vient d'une autorité légitime |
| Éligibilité               | Cet acteur/cette catégorie peut-il utiliser la fonction ? | Catégorie sensible nécessitant une vérification         | Non                                     |
| Entitlement               | Quelle capacité commerciale/limite est active ?           | 3 annonces actives; accès Team Inbox; Pass recrutement  | Oui                                     |
| Vérification              | Qu'a effectivement contrôlé la plateforme ?               | Téléphone vérifié; identité vérifiée; autorité vérifiée | Non - jamais achetable                  |

# 3. Invariants commerciaux verrouillés

- Le compte gratuit reste réellement utile: découverte, participation de base et accès essentiel ne sont pas artificiellement dégradés pour forcer le paiement.

- La plateforme ne prélève pas, dans le modèle actuel, de commission en pourcentage sur les ventes Marketplace, prestations ordinaires ou salaires.

- Les frais d'un fournisseur externe de paiement, banque ou Mobile Money peuvent s'appliquer sans devenir une commission plateforme.

- Un plan ou pass achète des capacités, quotas, outils, productivité ou visibilité; jamais une autorité organisationnelle.

- La vérification ne peut pas être achetée et un badge vérifié n'est pas une garantie de qualité, sécurité ou performance.

- La promotion payante doit être clairement identifiable comme sponsorisée et ne doit pas être confondue avec un classement organique, une recommandation ou une vérification.

- Un abonnement Enterprise ne peut pas contourner le consentement, la confidentialité, les règles de marché ou les permissions.

- Les prix, quotas numériques exacts et seuils sont configurables et ne doivent pas être codés en dur dans les applications.

# 4. Architecture générale des offres

| **Famille commerciale** | **Client principal**                  | **Mécanisme**                              | **Finalité V1**                                                      |
|-------------------------|---------------------------------------|--------------------------------------------|----------------------------------------------------------------------|
| Free / accès de base    | Tous les utilisateurs éligibles       | Gratuit                                    | Découverte, participation et fonctions essentielles                  |
| Particulier Premium     | Individu / ménage                     | Abonnement périodique, préférence annuelle | Outils personnels avancés et avantages transversaux                  |
| Professionnel           | Prestataire individuel                | Abonnement SaaS                            | Gérer et développer une activité de service                          |
| Business                | Organisation                          | Abonnement SaaS                            | Présence, équipe et opérations commerciales de base                  |
| Business Pro            | Organisation                          | Abonnement SaaS supérieur                  | Plus de capacité, collaboration et outils avancés                    |
| Enterprise              | Organisation complexe                 | Contrat/abonnement                         | Gouvernance, volume, multi-branches et capacités avancées autorisées |
| Passes                  | Individu / organisation selon produit | Entitlement temporaire                     | Accès intensif ou ponctuel sans abonnement annuel                    |
| Achats ponctuels        | Acteur éligible                       | Paiement unique                            | Publication/action spécifique                                        |
| Promotion               | Propriétaire/gestionnaire d'objet     | Achat ou crédit inclus                     | Visibilité sponsorisée étiquetée                                     |

# 5. Accès gratuit - socle commun

| **Domaine**             | **Capacités gratuites de référence**                               | **Limites / conditions**                         |
|-------------------------|--------------------------------------------------------------------|--------------------------------------------------|
| Compte & identité       | Créer compte, gérer profil personnel, changer de contexte autorisé | Vérification/éligibilité selon actions sensibles |
| Découverte              | Accueil, Explorer, recherche, filtres, fiches publiques            | Contenus privés/restrictifs exclus               |
| Marketplace acheteur    | Rechercher, acheter, suivre commandes, messages contextuels        | Paiement/provider selon transaction              |
| Marketplace particulier | Publier des objets personnels autorisés                            | Limites anti-spam/volume configurables           |
| Services client         | Découvrir, contacter, demander devis, réserver si disponible       | Selon politique du service                       |
| Emploi candidat         | Rechercher, sauvegarder, postuler, suivre candidatures             | Candidature de base gratuite                     |
| Événements              | Découvrir, RSVP/s'inscrire, acheter billet                         | Billet payant = prix de l'événement              |
| Restaurants             | Découvrir, commander, suivre commande                              | Frais externes/livraison selon commande          |
| Messagerie              | Conversations liées aux interactions autorisées                    | Anti-spam, sécurité, contexte                    |
| Avis                    | Publier avis si interaction éligible                               | Règles de preuve/modération                      |
| Support                 | Signaler problème, ouvrir case/appeal éligible                     | Selon catégorie et priorité                      |

# 6. Particulier Premium

Particulier Premium est un abonnement de commodité et de productivité pour l'utilisateur individuel. Il ne transforme pas la personne en entreprise et ne crée aucun avantage injustifié dans les emplois, la confiance ou la modération.

| **Capacité**                  | **Free**                                          | **Particulier Premium**                            | **Règle**                                      |
|-------------------------------|---------------------------------------------------|----------------------------------------------------|------------------------------------------------|
| Recherches sauvegardées       | Base / limité configurable                        | Capacité étendue                                   | Pas de priorité cachée                         |
| Alertes                       | Essentielles                                      | Alertes avancées et préférences                    | Fréquence configurable                         |
| Organisation personnelle      | Historique de base                                | Tableaux de suivi enrichis                         | Commandes, candidatures, réservations, billets |
| Recrutement domestique        | Accès à la découverte/candidatures comme candidat | Avantages récurrents côté employeur particulier    | Ne prend pas de commission sur salaire         |
| Listes candidats sauvegardées | Selon pass/limite                                 | Inclus ou quota supérieur                          | Données privées selon finalité                 |
| Marketplace particulier       | Publication de base                               | Capacités/quotas additionnels possibles            | Ne devient pas vendeur commercial              |
| Avantages événement/booking   | Fonctions essentielles                            | Outils de gestion/sauvegarde/alertes améliorés     | Pas de passe-droit sur capacité réelle         |
| Support                       | Standard                                          | Canal/priorité opérationnelle raisonnable possible | Jamais priorité sécurité ou décision biaisée   |

# 7. Plan Professionnel - Prestataire individuel

| **Capacité**       | **Free / profil de base**               | **Professionnel**                             | **Notes**                                   |
|--------------------|-----------------------------------------|-----------------------------------------------|---------------------------------------------|
| Profil prestataire | Création si éligible                    | Profil enrichi et outils pro                  | Vérification séparée                        |
| Services publiés   | Quota de base configurable              | Quota supérieur                               | Catégories sensibles restent contrôlées     |
| Demandes de devis  | Recevoir/répondre de base               | Outils de suivi et modèles améliorés          | Aucun paiement n'achète la préférence       |
| Booking            | Fonctions de base si service compatible | Calendrier/ressources/paramètres plus avancés | Disponibilité réelle distincte des horaires |
| Portfolio/médias   | Base                                    | Capacité supérieure                           | Modération applicable                       |
| Analytics          | Basique                                 | Statistiques opérationnelles enrichies        | Pas de surveillance invasive                |
| Promotion          | Achat ponctuel possible                 | Crédits/allocations possibles                 | Toujours Sponsorisé                         |
| Historique clients | Contextuel                              | Outils de suivi améliorés                     | Pas de CRM privé hors finalité              |
| Support            | Standard                                | Support commercial amélioré                   | Sécurité/modération indépendantes           |

# 8. Plans Business, Business Pro et Enterprise

| **Capacité**                 | **Business**                 | **Business Pro**                    | **Enterprise**                                   |
|------------------------------|------------------------------|-------------------------------------|--------------------------------------------------|
| Profil organisation          | Oui                          | Oui                                 | Oui                                              |
| Membres équipe               | Quota configurable           | Quota supérieur                     | Volume/contrat configurable                      |
| Branches/départements        | Base / limité                | Multi-branches renforcé             | Structure complexe autorisée                     |
| Rôles & permissions          | Granulaires                  | Granulaires + gestion avancée       | Granulaires + gouvernance avancée                |
| Services / produits / offres | Quotas de base               | Quotas supérieurs                   | Volumes contractuels                             |
| Jobs & recrutement           | Fonctions entreprise de base | Pipeline/collaboration enrichis     | Discovery opt-in et volumes avancés si autorisés |
| Team Inbox                   | Base                         | Assignation/collaboration renforcée | Routage/équipes avancés                          |
| Booking/resources            | Base selon module            | Capacité supérieure                 | Configuration organisationnelle avancée          |
| Événements/ticketing         | Oui selon éligibilité        | Quotas/outils supérieurs            | Volumes/contrat                                  |
| Formation workforce          | Demande/gestion de base      | Cohortes et suivi enrichis          | Capacités organisationnelles avancées            |
| Analytics                    | Opérationnel de base         | Rapports enrichis                   | Rapports organisationnels avancés                |
| Promotion                    | Achat/crédits possibles      | Allocation supérieure possible      | Contrat/allocations                              |
| Support                      | Standard business            | Support renforcé                    | Support contractuel possible                     |
| SSO/SCIM                     | Non V1                       | Non V1                              | Post-V1                                          |
| API avancée                  | Non V1                       | Non V1                              | Post-V1                                          |

La différence entre Business, Business Pro et Enterprise doit être principalement une différence de capacité, collaboration, gouvernance et volume - jamais une différence de vérité, de confiance ou d'accès illégitime aux données.

# 9. Recrutement privé - trois produits distincts

| **Produit**                | **Nature**        | **Cas d'usage**                              | **Droits possibles**                                                               | **Ce qu'il ne fait pas**                   |
|----------------------------|-------------------|----------------------------------------------|------------------------------------------------------------------------------------|--------------------------------------------|
| Publication unique         | Paiement ponctuel | Un ménage a un seul besoin de recrutement    | 1 poste actif pendant une période définie; candidatures; messages; filtres de base | Ne crée pas un abonnement permanent        |
| Pass Recrutement 30 jours  | Pass temporaire   | Période intensive de recrutement             | Plusieurs publications/quotas; filtres avancés; shortlist; outils de suivi         | Ne remplace pas Particulier Premium annuel |
| Particulier Premium annuel | Abonnement        | Ménage utilisant régulièrement la plateforme | Avantages de recrutement récurrents + autres bénéfices individuels                 | Ne garantit pas un candidat ni un résultat |

Les exemples historiques de 10 USD pour un pass et 25 USD/an pour Premium restent des illustrations de réflexion, pas des prix approuvés. Le moteur doit accepter des prix et limites configurables par marché.

# 10. Promotion

| **Objet promouvable V1**          | **Acteur qui peut promouvoir**     | **Conditions**                               |
|-----------------------------------|------------------------------------|----------------------------------------------|
| Annonce Marketplace               | Propriétaire/gestionnaire éligible | Objet actif, conforme et catégorie autorisée |
| Service                           | Prestataire/organisation autorisé  | Service publié et éligible                   |
| Profil professionnel/organisation | Propriétaire/gestionnaire autorisé | Selon politique de visibilité                |
| Offre d'emploi                    | Employeur/recruteur autorisé       | Ne modifie jamais l'évaluation des candidats |
| Événement public éligible         | Organisateur autorisé              | Pas d'événement privé/restrictif             |
| Formation publique éligible       | Provider autorisé                  | Programme actif et conforme                  |

Toute promotion doit conserver un Promotion Record: objet, propriétaire, période, audience autorisée, produit commercial, paiement/crédit utilisé et statut. L'interface doit afficher explicitement le caractère sponsorisé.

# 11. Entitlement Engine - modèle fonctionnel

| **Champ**               | **Description**                                                   |
|-------------------------|-------------------------------------------------------------------|
| entitlement_id          | Identifiant stable du droit commercial                            |
| holder_type / holder_id | Individu, profil prestataire ou organisation qui détient le droit |
| product_code            | Produit commercial ayant créé le droit                            |
| capability_code         | Capacité accordée, ex. JOB_POST_ACTIVE, TEAM_MEMBER_LIMIT         |
| scope                   | Module, organisation, branche ou objet concerné                   |
| limit_type              | Boolean, count, amount, storage, duration, feature level          |
| limit_value             | Valeur configurée                                                 |
| used_value              | Consommation actuelle si quota                                    |
| starts_at / expires_at  | Fenêtre de validité                                               |
| source_transaction      | Référence de paiement/abonnement/promotion                        |
| status                  | Pending, Active, Suspended, Expired, Revoked                      |
| market                  | Marché/règles applicables                                         |
| metadata                | Paramètres versionnés nécessaires                                 |

# 12. Bibliothèque initiale de capability codes

| **Capability code**      | **Capacité**                           | **Type de limite** |
|--------------------------|----------------------------------------|--------------------|
| CAP-PUB-LISTING          | Publier annonces Marketplace           | count              |
| CAP-PUB-SERVICE          | Publier services                       | count              |
| CAP-JOB-POST             | Publier offres d'emploi                | count              |
| CAP-HH-JOB-POST          | Publier emploi domestique              | count              |
| CAP-HH-SHORTLIST         | Listes candidats employeur particulier | feature/count      |
| CAP-TEAM-MEMBER          | Membres d'équipe organisation          | count              |
| CAP-BRANCH               | Branches gérées                        | count              |
| CAP-TEAM-INBOX           | Boîte partagée / assignation           | feature level      |
| CAP-BOOKING-RESOURCE     | Ressources réservables                 | count              |
| CAP-EVENT-PUBLISH        | Événements publiés                     | count              |
| CAP-TICKET-SELL          | Billetterie événement                  | feature            |
| CAP-TRAINING-PUBLISH     | Programmes de formation                | count              |
| CAP-TRAINING-COHORT      | Cohortes privées                       | count              |
| CAP-ANALYTICS            | Niveau d'analytics                     | feature level      |
| CAP-SAVED-SEARCH         | Recherches sauvegardées                | count              |
| CAP-ALERT                | Alertes avancées                       | count/frequency    |
| CAP-PROMO-CREDIT         | Crédits de promotion                   | amount/count       |
| CAP-MEDIA-STORAGE        | Médias/stockage                        | storage            |
| CAP-ENTERPRISE-DISCOVERY | Découverte candidats opt-in            | feature            |
| CAP-SUPPORT-SLA          | Niveau de support commercial           | feature level      |

# 13. Ordre d'évaluation d'un accès payant

| **Étape** | **Contrôle**                   | **Exemple**                                        |
|-----------|--------------------------------|----------------------------------------------------|
| 1         | Authentification               | Utilisateur connecté                               |
| 2         | Contexte actif                 | Agit comme ABC SARL                                |
| 3         | Relation / membership          | Membre actif de ABC SARL                           |
| 4         | Permission + scope             | Peut publier des jobs pour Branche Kinshasa        |
| 5         | Éligibilité                    | Organisation/catégorie autorisée                   |
| 6         | Entitlement                    | Plan permet encore une offre active                |
| 7         | Règles marché/catégorie        | Publication permise en RDC                         |
| 8         | Consentement & confidentialité | Données candidat utilisées pour finalité autorisée |
| 9         | État sécurité                  | Compte non suspendu/bloqué                         |
| 10        | Allow / Deny                   | Action autorisée ou refusée avec motif exploitable |

Cette séquence empêche une erreur fréquente: considérer qu'un abonnement actif suffit à autoriser une action.

# 14. Cycle de vie abonnement, pass et quota

| **Événement**              | **Comportement attendu**                                                                     |
|----------------------------|----------------------------------------------------------------------------------------------|
| Achat initié               | Entitlement Pending; aucune capacité sensible n'est activée sur simple retour écran.         |
| Paiement confirmé          | Entitlement Active avec dates/limites.                                                       |
| Renouvellement réussi      | Prolonge ou crée nouvelle période selon règles; historique conservé.                         |
| Paiement échoué            | Grace period éventuelle configurable; pas de faux statut Paid.                               |
| Expiration                 | Nouvelles actions payantes bloquées; historique métier conservé.                             |
| Upgrade                    | Nouvelles capacités/limites prennent effet selon politique de prorata.                       |
| Downgrade                  | Ne supprime pas brutalement les objets existants; limite nouvelles créations si dépassement. |
| Quota consommé             | Action suivante bloquée ou propose upgrade/pass si approprié.                                |
| Remboursement / chargeback | Entitlement réévalué selon politique et audit.                                               |
| Suspension sécurité        | Peut bloquer l'usage même si entitlement payé.                                               |

# 15. Matrice de séparation - ce que l'argent n'achète jamais

| **Élément**                           | **Achetable ?** | **Raison**                                       |
|---------------------------------------|-----------------|--------------------------------------------------|
| Identité vérifiée                     | Non             | Résultat d'un contrôle, pas un produit           |
| Autorité sur une organisation         | Non             | Doit provenir d'une relation/validation légitime |
| Permission de voir les CV             | Non             | Dépend du rôle recrutement et du scope           |
| Accès aux messages privés             | Non             | Finalité et permissions                          |
| Accès aux données d'un enfant         | Non             | Relation parent/tuteur/école autorisée           |
| Classement 'meilleur candidat'        | Non             | Pas de verdict autonome ni avantage payant       |
| Badge 'recommandé'                    | Non             | Éviter l'endorsement trompeur                    |
| Résultat de modération favorable      | Non             | Indépendance sécurité/conformité                 |
| Priorité dans un processus d'embauche | Non             | Le paiement ne biaise pas la sélection           |
| Contournement des règles marché       | Non             | Compliance prévaut sur entitlement               |

# 16. Mapping commercial par contexte utilisateur

| **Contexte**                | **Produit principal possible**  | **Produits complémentaires**                     | **Base gratuite préservée**                          |
|-----------------------------|---------------------------------|--------------------------------------------------|------------------------------------------------------|
| Individu                    | Particulier Premium             | Pass recrutement; promotion personnelle éligible | Oui                                                  |
| Prestataire individuel      | Professionnel                   | Promotion; quotas/passes spécifiques             | Oui                                                  |
| Employeur particulier       | Particulier Premium             | Publication unique; Pass recrutement 30 jours    | Oui pour activité candidat/consommateur              |
| Organisation petite/moyenne | Business                        | Promotion; passes/module add-ons futurs          | Oui pour présence/découverte de base selon stratégie |
| Organisation avancée        | Business Pro                    | Promotion; capacité supplémentaire               | Selon offre                                          |
| Grande organisation         | Enterprise                      | Contrats/capacités configurées                   | Selon offre                                          |
| Candidat / travailleur      | Aucun plan requis pour postuler | Premium individuel optionnel pour productivité   | Postuler reste gratuit                               |
| Participant événement       | Aucun plan requis               | Billet si événement payant                       | Découverte/inscription gratuite si événement gratuit |

# 17. Mesures et analytics commerciaux

| **KPI**                  | **Définition**                                  | **Pourquoi**                          |
|--------------------------|-------------------------------------------------|---------------------------------------|
| Free → Paid conversion   | % holders gratuits devenant payants par segment | Mesurer valeur perçue                 |
| Paid retention           | % abonnements conservés par cohorte             | Santé SaaS                            |
| Churn                    | Résiliations/expiration non renouvelée          | Identifier problèmes d'offre          |
| ARPU / ARPA              | Revenu moyen individu / compte organisation     | Pilotage pricing                      |
| Entitlement utilization  | Quota consommé / quota accordé                  | Voir si plan est sur/sous-dimensionné |
| Pass repeat rate         | Acheteurs de pass revenant                      | Décider pass vs abonnement            |
| Promotion repeat rate    | Réachat promotion après campagne                | Valeur commerciale                    |
| Upgrade / downgrade      | Mouvements entre niveaux                        | Comprendre maturité clients           |
| Support load by plan     | Volume et complexité support                    | Dimensionner coût de service          |
| Gross revenue by product | Revenu par famille commerciale                  | Priorisation                          |

Le futur modèle financier devra progressivement remplacer les hypothèses par ces données observées.

# 18. Paramètres administrables

| **Paramètre**                         | **Administrable sans nouvelle version app ?** |
|---------------------------------------|-----------------------------------------------|
| Prix et devise                        | Oui                                           |
| Période abonnement/pass               | Oui                                           |
| Quota par capability                  | Oui                                           |
| Marché éligible                       | Oui                                           |
| Produit actif/inactif                 | Oui                                           |
| Grace period                          | Oui                                           |
| Crédits promotion inclus              | Oui                                           |
| Limites membres/branches/publications | Oui                                           |
| Texte commercial et labels            | Oui                                           |
| Règles légales/policy liées           | Oui, avec gouvernance/audit                   |
| Permission organisationnelle          | Non via catalogue commercial - gérée par IAM  |

# 19. Décisions ouvertes avant commercialisation

| **Décision**                                      | **Statut**                                              |
|---------------------------------------------------|---------------------------------------------------------|
| Prix exacts de tous les plans                     | TBD - à tester avec marché et modèle financier          |
| Facturation mensuelle vs annuelle par offre       | Préférence forte pour annuel; configuration à finaliser |
| Quotas exacts par niveau                          | TBD après tests produit/coûts                           |
| Périodes de grâce et prorata                      | TBD avec fournisseur de paiement/comptabilité           |
| Frais externes répercutés ou absorbés             | TBD par canal/provider                                  |
| Taxes et documents fiscaux                        | À valider juridiquement/fiscalement en RDC              |
| Politique de remboursement des abonnements/passes | TBD selon droit applicable et produit                   |
| SLA Enterprise                                    | TBD contractuellement                                   |
| Add-ons V1 éventuels                              | À limiter pour éviter complexité commerciale excessive  |

# 20. Recommandation de packaging V1

Pour le lancement, conserver une gamme lisible: Free comme socle, Particulier Premium pour les particuliers, Professionnel pour les prestataires individuels, Business et Business Pro pour la majorité des organisations, Enterprise pour les besoins contractuels complexes, puis seulement quelques passes à forte utilité comme le recrutement privé et la promotion. Les add-ons multiples doivent rester exceptionnels en V1.

Cette structure donne au moteur technique assez de souplesse pour évoluer sans obliger l'interface commerciale à devenir complexe.

# 21. Liens avec les autres documents maîtres

| **Document**                          | **Lien**                                                                   |
|---------------------------------------|----------------------------------------------------------------------------|
| Document 01 - Référentiel Fonctionnel | Définit les capacités que les entitlements peuvent activer/limiter.        |
| Document 02 - Parcours Utilisateurs   | UF-27 Achat plan/pass et UF-28 Promotion utilisent ce catalogue.           |
| Document 03 - Référentiel Taxonomique | Éligibilité et règles peuvent dépendre de catégories/marchés.              |
| Document 04 - Modèle financier        | Les prix et taux d'adoption futurs alimentent le modèle.                   |
| Cahier des charges développeur        | Implémente IAM, Entitlement Engine, Billing et Promotion selon ces règles. |

# 22. Critères d'acceptation techniques

- Une modification de prix ou quota ne nécessite pas une nouvelle version mobile.

- Une capacité payante ne peut être utilisée que si permission, éligibilité et entitlement sont tous valides.

- Le paiement confirmé est la source autoritative pour l'activation commerciale.

- Un downgrade ou une expiration ne supprime pas l'historique métier de l'utilisateur.

- Les consommations de quotas sont atomiques et auditables afin d'éviter les doubles consommations.

- Les produits commerciaux et capability codes sont versionnés.

- Les interfaces distinguent clairement gratuit, inclus, limite atteinte, pass disponible et upgrade possible.

- Les décisions de sécurité, vérification et confidentialité restent indépendantes de la facturation.
