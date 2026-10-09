**RÉFÉRENTIEL TAXONOMIQUE V1**

**Plateforme Écosystème RDC**

*Document 03 - Catégories, sous-catégories, attributs, filtres et alias*

Version V1 · Septembre 2026

# 1. Objet et principes

Ce référentiel définit la structure canonique utilisée pour classer, publier, rechercher et filtrer les objets de la plateforme. Il doit être administrable depuis le back-office et ne doit pas être codé en dur dans les applications clientes.

| **Principe**             | **Règle**                                                                                                                                             |
|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| Catégorie ≠ attribut     | Créer une catégorie pour une famille stable; utiliser un attribut pour une caractéristique variable comme marque, niveau, expérience, format ou état. |
| Un identifiant canonique | Chaque catégorie possède un code stable indépendant de son libellé traduit.                                                                           |
| Alias de recherche       | Les synonymes, abréviations, variantes locales et termes anglais pointent vers la catégorie canonique sans créer de doublon.                          |
| Applicabilité            | Une catégorie peut être autorisée seulement pour certains objets ou profils.                                                                          |
| Politique séparée        | Allowed / Restricted / Verification required / Not permitted est une métadonnée de politique, pas une catégorie.                                      |
| Vendeur séparé           | Particulier, Prestataire et Organisation décrivent l'acteur; ils ne font pas partie de la taxonomie produit.                                          |
| Évolution sûre           | Désactiver/fusionner plutôt que supprimer une catégorie déjà utilisée.                                                                                |
| Localisation             | Province, ville/commune/zone et rayon sont des dimensions géographiques séparées de la catégorie métier.                                              |

# 2. Modèle de données taxonomique

| **Objet**               | **Champs minimaux**                                                                           |
|-------------------------|-----------------------------------------------------------------------------------------------|
| Category                | id, code, parent_id, domain, labels, description, status, sort_order, policy_state            |
| Alias                   | category_id, language, alias_text, alias_type, market, normalized_text                        |
| Attribute Definition    | code, label, data_type, unit, required_mode, searchable, filterable, public, sensitive        |
| Attribute Applicability | attribute_id, category_id/domain, object_type, market, required/optional                      |
| Option Set              | attribute_id, option_code, labels, sort_order, status                                         |
| Policy Rule             | category/object_type/market, allowed state, verification requirement, publication restriction |
| Crosswalk               | source domain/category -\> related domain/category; relation type                             |
| Versioning              | taxonomy_version, effective_from, changed_by, change_reason                                   |

# 3. Domaines taxonomiques maîtres

| **Code** | **Domaine**                    | **Finalité**                                                  | **Objets principaux**          |
|----------|--------------------------------|---------------------------------------------------------------|--------------------------------|
| TX-ORG   | Organisations & établissements | Type d'organisation et secteurs d'activité                    | Organisation/Profile           |
| TX-SRV   | Services                       | Services proposés par prestataires et organisations           | Service Offering               |
| TX-MKT   | Marketplace                    | Biens physiques et équipements                                | Product/Listing                |
| TX-JOB   | Métiers & emplois              | Familles professionnelles, métiers et types d'emploi          | Job/Occupation/Profile         |
| TX-SKL   | Compétences                    | Compétences techniques, transversales et langues              | Profile/Job/Training           |
| TX-TRN   | Formation                      | Domaines et formats de formation                              | Training Program               |
| TX-EVT   | Événements                     | Types d'événements et finalités                               | Event                          |
| TX-PLC   | Lieux & réservations           | Types de lieux/ressources réservables                         | Place/Resource                 |
| TX-FOD   | Restaurants & alimentation     | Cuisine, établissement, menu                                  | Restaurant/Menu Item           |
| TX-DLV   | Livraison                      | Types de services et capacités de livraison                   | Delivery Service               |
| TX-NPO   | Associations & campagnes       | Causes, campagnes, volontariat                                | Campaign/Volunteer Opportunity |
| TX-SCH   | Éducation                      | Niveaux, sections et services scolaires                       | School/Admission               |
| TX-PRP   | Immobilier - routage           | Classification permettant de router vers futur objet Property | Discovery routing              |

# 4. TX-ORG - Organisations et secteurs

| **Code** | **Type canonique**                 | **Exemples / portée**                                   | **organization_type** |
|----------|------------------------------------|---------------------------------------------------------|-----------------------|
| ORG-BIZ  | Entreprise / Société               | Commerce, industrie, services professionnels            | business              |
| ORG-SOLE | Entreprise individuelle            | Activité commerciale formalisée portée par une personne | sole_business         |
| ORG-NPO  | Association / ONG / Fondation      | Organisation à but non lucratif                         | nonprofit             |
| ORG-SCH  | École / établissement éducatif     | Préscolaire, primaire, secondaire, formation            | school                |
| ORG-HLT  | Établissement de santé             | Clinique, centre, cabinet, laboratoire                  | health_facility       |
| ORG-RST  | Restaurant / alimentation          | Restaurant, café, traiteur, boulangerie                 | restaurant            |
| ORG-HTL  | Hôtel / hébergement                | Hôtel, guest house, lodge                               | hotel                 |
| ORG-VEN  | Lieu / espace événementiel         | Salle, centre, espace réservable                        | venue                 |
| ORG-PRC  | Cabinet / pratique professionnelle | Cabinet juridique, conseil, architecture, etc.          | professional_practice |
| ORG-COO  | Coopérative                        | Coopérative agricole, artisanale ou économique          | cooperative           |
| ORG-INS  | Institution                        | Institution publique/privée éligible                    | institution           |
| ORG-OTH  | Autre organisation                 | Cas validé ne correspondant pas aux types ci-dessus     | other_organization    |

## 4.1 Secteurs d'activité organisationnels

| **Code** | **Secteur**                                  | **Alias FR / EN / usage**                          |
|----------|----------------------------------------------|----------------------------------------------------|
| SEC-AGR  | Agriculture, élevage & agro-industrie        | ferme; agriculture; élevage; agro; agribusiness    |
| SEC-CON  | Construction, immobilier & BTP               | construction; bâtiment; travaux; génie civil; BTP  |
| SEC-RET  | Commerce & distribution                      | boutique; magasin; retail; grossiste; distribution |
| SEC-TEC  | Technologie, télécom & numérique             | informatique; IT; télécom; digital; logiciel       |
| SEC-FIN  | Finance, assurance & services financiers     | banque; microfinance; assurance; finance           |
| SEC-HLT  | Santé & bien-être                            | clinique; santé; médical; bien-être                |
| SEC-EDU  | Éducation & formation                        | école; université; centre de formation; cours      |
| SEC-HSP  | Hôtellerie, restauration & tourisme          | restaurant; hôtel; tourisme; hospitality           |
| SEC-TRN  | Transport, mobilité & logistique             | transport; livraison; logistique; courier          |
| SEC-ENE  | Énergie, eau & environnement                 | solaire; électricité; eau; environnement           |
| SEC-MFG  | Industrie & fabrication                      | usine; fabrication; manufacturing                  |
| SEC-MED  | Médias, communication & création             | media; publicité; communication; audiovisuel       |
| SEC-LEG  | Juridique, conseil & services professionnels | avocat; conseil; audit; consulting                 |
| SEC-BEA  | Beauté, mode & soins personnels              | salon; coiffure; beauté; mode                      |
| SEC-EVT  | Événementiel & loisirs                       | événement; fête; entertainment; loisirs            |
| SEC-NPO  | Social, humanitaire & développement          | ONG; humanitaire; social; développement            |
| SEC-SEC  | Sécurité & services de protection            | gardiennage; sécurité; protection                  |
| SEC-OTH  | Autres secteurs                              | autre activité                                     |

# 5. TX-SRV - Services

| **Code famille** | **Catégorie**            | **Sous-catégories V1**                                                                                                                                                                  |
|------------------|--------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| SRV-HOME         | Maison & entretien       | Ménage / nettoyage; Jardinage; Plomberie; Électricité; Peinture; Menuiserie; Maçonnerie / petites réparations; Climatisation / froid; Désinfection / lutte nuisibles; Déménagement      |
| SRV-PER          | Services personnels      | Coiffure / barber; Beauté / esthétique; Maquillage; Manucure / pédicure; Couture / retouches; Photographie personnelle                                                                  |
| SRV-CARE         | Aide à la personne       | Garde d'enfants / nanny; Aide ménagère; Aide aux personnes âgées; Accompagnement non médical; Cuisine à domicile; Chauffeur privé                                                       |
| SRV-EDU          | Éducation & tutorat      | Cours particuliers; Soutien scolaire; Langues; Informatique / numérique; Musique / arts; Préparation examens                                                                            |
| SRV-PRO          | Services professionnels  | Comptabilité; Conseil fiscal; Juridique; Traduction / interprétation; Graphisme; Marketing / communication; Développement web / logiciel; Conseil entreprise; Architecture / ingénierie |
| SRV-EVT          | Événementiel             | Organisation événement; Décoration; Traiteur; Photo / vidéo; DJ / musique; Location matériel événementiel; Sécurité événementielle                                                      |
| SRV-AUTO         | Automobile & mobilité    | Mécanique; Diagnostic; Électricité auto; Lavage / detailing; Pneus; Remorquage; Location avec chauffeur                                                                                 |
| SRV-TECH         | Technologie & réparation | Réparation téléphone; Réparation ordinateur; Réseaux / installation; CCTV / sécurité électronique; Installation solaire; Réparation électroménager                                      |
| SRV-BIZ          | Services aux entreprises | Nettoyage commercial; Maintenance; Recrutement; Formation workforce; Logistique; Impression; Sécurité / gardiennage                                                                     |

## 5.1 Attributs communs aux services

| **Code**                  | **Attribut**           | **Type**   | **Exemples**                                       | **Filtrable**                 |
|---------------------------|------------------------|------------|----------------------------------------------------|-------------------------------|
| service_mode              | Mode                   | enum       | sur_site; chez_prestataire; en_ligne; hybride      | Oui                           |
| service_area              | Zone desservie         | geo/radius | commune/ville/rayon                                | Oui                           |
| pricing_mode              | Mode de prix           | enum       | prix_fixe; à_partir_de; horaire; journalier; devis | Oui                           |
| availability              | Disponibilité          | schedule   | jours/heures/exceptions                            | Oui                           |
| experience_years          | Expérience             | number     | années                                             | Oui                           |
| languages                 | Langues                | multi-enum | FR; EN; LN; autres                                 | Oui                           |
| emergency_available       | Urgence                | boolean    | oui/non                                            | Oui                           |
| travel_fee                | Frais déplacement      | money/rule | montant/règle                                      | Oui                           |
| verification_requirements | Vérifications requises | policy     | selon catégorie                                    | Non public comme preuve brute |

# 6. TX-MKT - Marketplace

| **Code** | **Catégorie maître**                  | **Sous-catégories / exemples V1**                                                          |
|----------|---------------------------------------|--------------------------------------------------------------------------------------------|
| MKT-01   | Électronique & Technologie            | Téléphones; Tablettes; Ordinateurs; TV/Audio; Appareils photo; Réseau; Accessoires; Gaming |
| MKT-02   | Véhicules                             | Voitures; Motos; Camions/utilitaires; Vélos; Pièces & accessoires                          |
| MKT-03   | Maison, Mobilier & Électroménager     | Meubles; Cuisine; Réfrigération; Lavage; Climatisation; Décoration; Literie                |
| MKT-04   | Mode & Accessoires                    | Vêtements femme; homme; enfant; Chaussures; Sacs; Bijoux; Montres                          |
| MKT-05   | Beauté & Soins personnels             | Cosmétiques; Cheveux; Parfums; Soins; Appareils beauté                                     |
| MKT-06   | Bébé & Enfants                        | Poussettes; Sièges; Mobilier bébé; Jouets; Puériculture                                    |
| MKT-07   | Sports, Fitness & Loisirs             | Fitness; Sports collectifs; Outdoor; Jeux; Instruments                                     |
| MKT-08   | Outils, Bricolage & Construction      | Outils; Matériaux; Quincaillerie; Plomberie; Électricité bâtiment                          |
| MKT-09   | Équipement professionnel & commercial | Bureau; Restaurant; Boutique; Atelier; Médical non réglementé; Impression                  |
| MKT-10   | Agriculture, Élevage & Agroéquipement | Outils agricoles; Irrigation; Élevage; Transformation; Intrants autorisés                  |
| MKT-11   | Livres, Éducation & Fournitures       | Livres; Manuels; Papeterie; Fournitures scolaires; Matériel pédagogique                    |
| MKT-12   | Énergie, Solaire & Électricité        | Panneaux; Batteries; Onduleurs; Groupes électrogènes; Câbles; Éclairage                    |
| MKT-13   | Équipements & Pièces techniques       | Pièces industrielles; Pompes; Moteurs; Compresseurs; Pièces machines                       |
| MKT-14   | Événementiel & Fêtes                  | Décoration; Vaisselle; Tentes; Sonorisation; Éclairage; Mobilier événementiel              |
| MKT-15   | Animaux - fournitures & équipements   | Alimentation; Accessoires; Cages; Équipement élevage                                       |
| MKT-16   | Autres articles                       | Objets autorisés ne correspondant pas aux catégories précédentes                           |

## 6.1 Routage hors Marketplace

| **Intention détectée**                           | **Routage**                                             |
|--------------------------------------------------|---------------------------------------------------------|
| Maison/appartement/terrain à vendre ou louer     | Objet Property / immobilier, pas Marketplace générique. |
| Prestation de plomberie, coiffure, conseil, etc. | Services.                                               |
| Offre ou recherche d'emploi                      | Jobs.                                                   |
| Location d'une ressource avec calendrier         | Service/Resource + Booking.                             |
| Collecte de fonds / appel aux dons               | Campaign.                                               |
| Billet d'événement                               | Event Ticketing.                                        |
| Repas préparé par restaurant                     | Food Order/Menu.                                        |

## 6.2 Attributs Marketplace

| **Code**          | **Type**        | **Applicabilité**                 | **Exemples**                                     |
|-------------------|-----------------|-----------------------------------|--------------------------------------------------|
| condition         | enum            | Biens d'occasion/neufs            | neuf; comme_neuf; bon; acceptable; pour_pièces   |
| brand             | text/canonical  | Électronique, véhicule, outils... | Samsung; Lenovo; Toyota                          |
| model             | text            | Produits à modèle                 | ThinkPad T14; Corolla                            |
| year              | integer         | Véhicules/équipements             | 2024                                             |
| price             | money           | Offres vendues                    | USD/CDF selon marché                             |
| negotiable        | boolean         | Offres                            | oui/non                                          |
| quantity          | integer         | Stock commercial                  | 1..n                                             |
| one_off_item      | boolean         | Particulier                       | objet unique                                     |
| fulfillment_modes | multi-enum      | Offres                            | retrait; livraison_vendeur; livraison_partenaire |
| location          | geo             | Toutes offres physiques           | ville/commune/zone                               |
| warranty          | text/duration   | Produits applicables              | 3 mois; garantie fabricant                       |
| specifications    | key-value typed | Catégorie spécifique              | RAM, stockage, taille, puissance                 |

# 7. TX-JOB - Métiers, emplois et compétences

| **Code** | **Famille**                    | **Métiers / alias représentatifs**                                              |
|----------|--------------------------------|---------------------------------------------------------------------------------|
| JOB-ADM  | Administration & bureau        | Assistant administratif; Secrétaire; Réceptionniste; Office manager; Data entry |
| JOB-FIN  | Finance & comptabilité         | Comptable; Caissier; Auditeur; Contrôleur; Analyste finance                     |
| JOB-SAL  | Vente & commerce               | Vendeur; Commercial; Account manager; Merchandiser; Caissier commerce           |
| JOB-CS   | Service client                 | Agent service client; Call center; Customer success                             |
| JOB-TEC  | Technologie & IT               | Développeur; Support IT; Réseau; Data; Cybersécurité; Product/UX                |
| JOB-ENG  | Ingénierie & technique         | Ingénieur civil; Électricien; Mécanicien; Technicien; Maintenance               |
| JOB-CON  | Construction & métiers manuels | Maçon; Menuisier; Plombier; Peintre; Soudeur; Carreleur                         |
| JOB-AGR  | Agriculture & élevage          | Agronome; Ouvrier agricole; Éleveur; Technicien agricole                        |
| JOB-LOG  | Transport & logistique         | Chauffeur; Livreur; Magasinier; Dispatcher; Logisticien                         |
| JOB-HSP  | Hôtellerie & restauration      | Cuisinier; Serveur; Réception hôtel; Housekeeping; Chef                         |
| JOB-EDU  | Éducation & formation          | Enseignant; Éducateur; Formateur; Directeur d'études                            |
| JOB-HLT  | Santé & soins                  | Médecin; Infirmier; Pharmacien; Technicien labo; Caregiver selon règles         |
| JOB-MED  | Média & création               | Designer; Photographe; Vidéaste; Journaliste; Community manager                 |
| JOB-LEG  | Juridique & conseil            | Avocat; Juriste; Consultant; Conseiller                                         |
| JOB-DOM  | Emploi domestique / ménage     | Nanny; Aide ménagère; Jardinier; Chauffeur privé; Cuisinier domestique; Gardien |
| JOB-MGT  | Management & direction         | Manager; Responsable de branche; Directeur; Operations manager                  |
| JOB-NPO  | Humanitaire & développement    | Project officer; M&E; Field officer; Community mobilizer                        |

## 7.1 Attributs emploi

| **Attribut**           | **Type**    | **Valeurs / notes**                                                          |
|------------------------|-------------|------------------------------------------------------------------------------|
| employment_type        | multi-enum  | CDI; CDD; temporaire; stage; apprentissage; freelance/contract si applicable |
| work_mode              | enum        | sur_site; hybride; à_distance                                                |
| schedule               | enum/text   | temps_plein; temps_partiel; horaires; shifts                                 |
| location               | geo         | ville/commune/site                                                           |
| experience_level       | enum        | débutant; intermédiaire; expérimenté; manager; direction                     |
| experience_years       | number      | minimum/préféré séparables                                                   |
| education_level        | enum        | aucun formel; primaire; secondaire; technique; licence; master; doctorat     |
| salary_display         | money/range | facultatif/configurable selon règles marché                                  |
| essential_requirements | structured  | exigences indispensables documentées                                         |
| preferred_requirements | structured  | préférences séparées des exigences essentielles                              |
| household_employer     | boolean     | étiquette Employeur particulier                                              |
| application_deadline   | date        | date limite                                                                  |

## 7.2 TX-SKL - Compétences

| **Code** | **Famille**               | **Exemples**                                                                 |
|----------|---------------------------|------------------------------------------------------------------------------|
| SKL-TECH | Compétences techniques    | plomberie; Excel; JavaScript; soudure; conduite; cuisine; soins; maintenance |
| SKL-DIG  | Compétences numériques    | bureautique; email; CRM; réseaux sociaux; data; logiciels métier             |
| SKL-LANG | Langues                   | français; anglais; lingala; swahili; kikongo; tshiluba; autres               |
| SKL-SOFT | Compétences transversales | communication; organisation; service client; travail équipe; leadership      |
| SKL-LIC  | Licences / habilitations  | permis conduire; autorisation professionnelle; habilitation technique        |
| SKL-TOOL | Outils / équipements      | logiciel, machine, véhicule ou équipement maîtrisé                           |

# 8. TX-TRN - Formation

| **Code** | **Domaine**               | **Sous-domaines**                                              |
|----------|---------------------------|----------------------------------------------------------------|
| TRN-DIG  | Numérique & technologie   | Bureautique; développement; data; cybersécurité; réseaux       |
| TRN-BIZ  | Gestion & entreprise      | Management; finance; comptabilité; vente; entrepreneuriat      |
| TRN-TEC  | Métiers techniques        | Électricité; plomberie; mécanique; soudure; maintenance        |
| TRN-AGR  | Agriculture & agro        | Production; élevage; transformation; gestion exploitation      |
| TRN-HSP  | Hôtellerie & restauration | Cuisine; service; housekeeping; accueil                        |
| TRN-HLT  | Santé & care              | Formation autorisée selon règles; premiers secours; caregiving |
| TRN-LNG  | Langues                   | Français; anglais; lingala; autres                             |
| TRN-SFT  | Soft skills               | Communication; leadership; service client; organisation        |
| TRN-SAF  | Sécurité & conformité     | HSE; sécurité au travail; hygiène; conformité                  |
| TRN-EDU  | Éducation & pédagogie     | Pédagogie; gestion classe; développement éducatif              |

| **Attribut formation** | **Type**   | **Valeurs**                                  |
|------------------------|------------|----------------------------------------------|
| training_format        | enum       | présentiel; en_ligne; hybride                |
| audience               | multi-enum | public; employés; candidats; cohorte_privée  |
| level                  | enum       | initiation; débutant; intermédiaire; avancé  |
| duration               | duration   | heures/jours/semaines                        |
| schedule               | schedule   | sessions/dates                               |
| capacity               | integer    | places                                       |
| pricing_mode           | enum       | gratuit; par_personne; cohorte; devis        |
| skills_taught          | relation   | références TX-SKL                            |
| prerequisites          | structured | prérequis                                    |
| credential_claim       | structured | attestation/certificat + émetteur/provenance |
| delivery_language      | multi-enum | langues de formation                         |

# 9. TX-EVT - Événements

| **Code** | **Catégorie**            | **Exemples**                                          |
|----------|--------------------------|-------------------------------------------------------|
| EVT-BIZ  | Business & networking    | conférence; networking; salon; forum; lancement       |
| EVT-TRN  | Formation & atelier      | atelier; séminaire; masterclass; formation            |
| EVT-CUL  | Culture & divertissement | concert; spectacle; festival; exposition              |
| EVT-COM  | Communauté & social      | rencontre; activité communautaire; meetup             |
| EVT-SPT  | Sport & fitness          | tournoi; course; séance; compétition                  |
| EVT-REL  | Religieux / spirituel    | culte; conférence; rassemblement selon règles         |
| EVT-FAM  | Privé / familial         | anniversaire; mariage; réception privée               |
| EVT-OPS  | Opérationnel restreint   | entretien; admission; visite; consultation; réunion   |
| EVT-NPO  | Cause / association      | collecte; sensibilisation; volontariat; événement ONG |

| **Attribut événement** | **Type**      | **Valeurs**                                   |
|------------------------|---------------|-----------------------------------------------|
| visibility             | enum          | public; ciblé; non_listé; invitation; interne |
| participation_mode     | enum          | RSVP; inscription; approbation; billet        |
| attendance_mode        | enum          | présentiel; online; hybride                   |
| pricing                | enum          | gratuit; payant; mixte                        |
| capacity               | integer       | capacité                                      |
| audience               | structured    | public cible sans ciblage sensible interdit   |
| venue                  | relation/text | lieu/online                                   |
| ticket_types           | relation      | types de billets                              |
| organizer_type         | relation      | individu/organisation selon éligibilité       |

# 10. TX-PLC - Lieux et ressources réservables

| **Code** | **Famille**         | **Exemples**                                   |
|----------|---------------------|------------------------------------------------|
| PLC-HOT  | Hébergement         | hôtel; guest house; lodge; chambre             |
| PLC-VEN  | Salles & événements | salle de fête; conférence; réunion; coworking  |
| PLC-SPT  | Sport & loisirs     | terrain; salle fitness; espace loisirs         |
| PLC-BEA  | Beauté & bien-être  | salon; spa; barber; cabine                     |
| PLC-PRO  | Professionnel       | bureau; salle consultation; studio             |
| PLC-EDU  | Éducation           | salle de classe; laboratoire; espace formation |
| PLC-OTH  | Autres ressources   | ressource validée réservable                   |

| **Attribut ressource** | **Type**   | **Valeurs**                                           |
|------------------------|------------|-------------------------------------------------------|
| booking_model          | enum       | appointment; resource_inventory; capacity; date_range |
| capacity               | integer    | personnes/unités                                      |
| duration_rules         | duration   | min/max/step                                          |
| opening_hours          | schedule   | horaires d'ouverture                                  |
| bookable_availability  | schedule   | disponibilité réservable distincte                    |
| buffer                 | duration   | avant/après                                           |
| advance_notice         | duration   | préavis                                               |
| amenities              | multi-enum | wifi; parking; climatisation; accessibilité; etc.     |
| cancellation_policy    | policy ref | configurable                                          |

# 11. TX-FOD - Restaurants et alimentation

| **Dimension**      | **Valeurs V1**                                                                                                                       |
|--------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| Type établissement | Restaurant; Café; Boulangerie/Pâtisserie; Fast-food; Traiteur; Bar/boissons non réglementées selon politique                         |
| Cuisine            | Congolaise; Africaine; Grillades; Internationale; Française; Italienne; Indienne; Chinoise/asiatique; Fast-food; Végétarienne; Autre |
| Moment             | Petit-déjeuner; Déjeuner; Dîner; Snacks                                                                                              |
| Menu section       | Entrées; Plats; Accompagnements; Desserts; Boissons; Menus/combo                                                                     |
| Dietary tags       | Végétarien; vegan si déclaré; sans porc; allergènes déclarés; autres tags factuels                                                   |
| Fulfillment        | Retrait; livraison restaurant; livraison partenaire                                                                                  |

| **Attribut menu** | **Type**         | **Notes**                                       |
|-------------------|------------------|-------------------------------------------------|
| item_name         | text             | nom du plat                                     |
| menu_section      | enum             | section                                         |
| price             | money            | prix                                            |
| availability      | boolean/schedule | disponibilité                                   |
| options           | option groups    | taille, accompagnement, supplément              |
| allergen_info     | multi-enum/text  | déclaration provider; ne pas garantir l'absence |
| preparation_time  | duration         | estimation                                      |
| image             | media            | photo                                           |
| dietary_tags      | multi-enum       | tags déclaratifs                                |

# 12. TX-DLV - Livraison

| **Code**   | **Service**               | **Attributs clés**                                   |
|------------|---------------------------|------------------------------------------------------|
| DLV-FOOD   | Livraison alimentaire     | zones; horaires; capacité; type véhicule; prix/règle |
| DLV-PARCEL | Colis / documents         | poids; dimensions; zones; délai                      |
| DLV-MKT    | Livraison Marketplace     | taille/poids; zones; pickup/dropoff                  |
| DLV-BULK   | Marchandises volumineuses | capacité véhicule; manutention; devis                |

V1 classe les entreprises et services de livraison. Le driver-level dispatch, GPS temps réel, routage et flotte avancés restent Post-V1.

# 13. TX-NPO - Associations, campagnes et volontariat

| **Dimension** | **Catégories V1**                                                                                                                                          |
|---------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Cause         | Éducation; Santé; Enfance; Femmes; Handicap; Environnement; Développement communautaire; Aide humanitaire; Emploi/jeunesse; Culture; Autre cause autorisée |
| Type campagne | Collecte de fonds; collecte de biens; sensibilisation; projet communautaire                                                                                |
| Volontariat   | Terrain; événement; administratif; professionnel/skills-based; distance/online                                                                             |
| Engagement    | Ponctuel; récurrent; période définie                                                                                                                       |

La politique de collecte financière et les catégories sensibles doivent être configurées par marché et validées juridiquement. Une campagne n'est pas un produit Marketplace.

# 14. TX-SCH - Éducation et écoles

| **Dimension**      | **Valeurs V1**                                                                                                       |
|--------------------|----------------------------------------------------------------------------------------------------------------------|
| Niveau             | Crèche/garderie si autorisée; Maternelle/préscolaire; Primaire; Secondaire; Technique/professionnel; Formation       |
| Section secondaire | Générale; scientifique; littéraire; commerciale/gestion; technique - à configurer selon établissement/règles locales |
| Service scolaire   | Admission; information; visite; événement; communication parent; activité parascolaire                               |
| Bénéficiaire       | Relation privée enfant/élève; jamais catégorie publique de profil                                                    |

# 15. Alias, synonymes et multilingue

Les alias améliorent la recherche sans modifier le vocabulaire canonique. Les variantes Lingala et autres langues nationales doivent être validées par des locuteurs compétents avant publication à grande échelle; le système doit néanmoins être prêt à les accueillir.

| **Terme canonique** | **Alias de recherche initiaux**                  | **Routage**        |
|---------------------|--------------------------------------------------|--------------------|
| Aide ménagère       | ménagère; femme de ménage; housekeeper; maid     | SRV-CARE / JOB-DOM |
| Nanny               | nounou; garde enfant; babysitter                 | SRV-CARE / JOB-DOM |
| Chauffeur privé     | chauffeur; driver; conducteur privé              | SRV-CARE / JOB-DOM |
| Électricien         | électricité; electrician; technicien électricité | SRV-HOME / JOB-ENG |
| Plombier            | plomberie; plumber                               | SRV-HOME / JOB-CON |
| Téléphone           | smartphone; mobile; téléphone portable           | MKT-01             |
| Ordinateur portable | laptop; PC portable; notebook                    | MKT-01             |
| Groupe électrogène  | générateur; generator; groupe                    | MKT-12             |
| Livraison           | delivery; coursier; courier                      | TX-DLV             |
| Emploi              | job; travail; poste; vacancy; offre d'emploi     | TX-JOB             |
| Formation           | training; cours; atelier; workshop               | TX-TRN             |
| Devis               | quotation; quote; estimation                     | TX-SRV             |
| Événement           | event; activité; manifestation                   | TX-EVT             |

# 16. Matrice d'applicabilité profil / contenu

| **Domaine**                       | **Individu**                   | **Prestataire individuel**       | **Organisation**     | **Employeur particulier**       | **Notes**                                   |
|-----------------------------------|--------------------------------|----------------------------------|----------------------|---------------------------------|---------------------------------------------|
| Marketplace - annonce personnelle | Oui                            | Oui en contexte personnel        | Non                  | Oui en contexte personnel       | Vendeur particulier explicitement identifié |
| Marketplace - offre commerciale   | Non par défaut                 | Oui si éligible                  | Oui si autorisée     | Non                             | Commercial ≠ personnel                      |
| Services                          | Demande                        | Publie/répond                    | Publie/répond        | Demande                         | Catégories sensibles avec règles            |
| Emplois entreprise                | Candidat                       | Candidat                         | Publie si permission | Non comme entreprise            | Recruteur = rôle                            |
| Emploi domestique                 | Candidat                       | Candidat                         | Non par défaut       | Publie                          | Étiquette Employeur particulier             |
| Formation                         | Participant                    | Participant/provider si éligible | Provider/employeur   | Participant/employeur selon cas | Provenance certificat                       |
| Événements                        | Participant/organisateur privé | Organisateur si éligible         | Organisateur         | Organisateur privé              | Visibilité séparée                          |
| Campagnes                         | Participant                    | Selon éligibilité                | Oui si éligible      | Participant                     | Règles renforcées                           |
| Écoles                            | Parent/tuteur                  | Parent/tuteur                    | École                | Parent/tuteur                   | Pas de profil enfant public                 |

# 17. États de politique et catégories sensibles

| **État**              | **Sens**                                                   |
|-----------------------|------------------------------------------------------------|
| ALLOWED               | Publication/utilisation autorisée sous règles générales.   |
| RESTRICTED            | Autorisé avec limitations, revue ou règles spécifiques.    |
| VERIFICATION_REQUIRED | Action bloquée jusqu'à vérification requise.               |
| NOT_PERMITTED         | Non publiable/utilisable sur la plateforme dans ce marché. |

Les exemples de catégories nécessitant potentiellement des règles renforcées incluent garde d'enfants, caregiving, santé, certaines certifications, collecte de fonds, biens réglementés et catégories financières. Le statut exact doit être validé selon le marché, la loi applicable et les politiques de la plateforme; il ne doit pas être déduit du simple nom de catégorie.

# 18. Gouvernance du Taxonomy Center

| **Action admin**  | **Règle**                                                                |
|-------------------|--------------------------------------------------------------------------|
| Créer             | Nouveau code stable + labels + parent + domaine + applicabilité.         |
| Renommer          | Modifier label sans modifier code/id.                                    |
| Réordonner        | Change seulement l'affichage.                                            |
| Désactiver        | Empêche nouvelles publications; conserve historique.                     |
| Fusionner         | Redirige ancien code vers canonique avec journal de migration.           |
| Ajouter alias     | N'améliore que recherche/découverte; ne crée pas une nouvelle catégorie. |
| Modifier attribut | Évaluer impact sur objets existants avant rendre obligatoire.            |
| Changer politique | Journaliser auteur, motif, date effective et marché.                     |
| Versionner        | Publier une version taxonomique avec changelog.                          |

# 19. Crosswalks entre domaines

| **Source**           | **Relation**              | **Destination**               |
|----------------------|---------------------------|-------------------------------|
| Métier/occupation    | requires_or_prefers_skill | Compétence                    |
| Formation            | teaches_skill             | Compétence                    |
| Service              | related_to_occupation     | Métier                        |
| Organisation secteur | may_offer                 | Service                       |
| Restaurant           | offers                    | Menu Item                     |
| Marketplace product  | fulfilled_by              | Delivery service              |
| Job                  | may_link_training         | Training Program              |
| Event                | hosted_at                 | Place/Resource                |
| Campaign             | may_have                  | Event / Volunteer Opportunity |
| School admission     | may_schedule              | Restricted Event / Booking    |

# 20. Décisions verrouillées et points à valider

| **Verrouillé**                                              | **À valider/configurer**                                                              |
|-------------------------------------------------------------|---------------------------------------------------------------------------------------|
| Les 16 catégories Marketplace maîtres                       | Sous-catégories fines et attributs spécifiques par catégorie lors de l'import initial |
| Catégorie ≠ attribut                                        | Dictionnaire complet des marques/modèles à enrichir progressivement                   |
| Alias configurables et multilingues                         | Traductions Lingala/Swahili/Kikongo/Tshiluba avec validation humaine locale           |
| Prestataire individuel distinct d'une entreprise            | Vérifications exactes par profession sensible                                         |
| Emploi domestique distinct de services indépendants         | Règles locales détaillées d'emploi/recrutement                                        |
| Property, Services, Jobs, Campaigns routés hors Marketplace | Moment exact d'activation d'un module immobilier spécialisé                           |
| Taxonomie administrable, jamais hard-coded                  | Workflow de gouvernance éditoriale et responsables internes                           |
| Politique séparée de la catégorie                           | Matrice juridique/policy par marché et fournisseur                                    |

# 21. Utilisation par le développement

Le backend doit exposer les catégories et attributs via API versionnée. Les clients mobile/web ne doivent pas embarquer une copie métier figée comme source d'autorité. Les formulaires de publication, filtres de recherche, règles de validation et facettes doivent être dérivés des métadonnées applicables. Les objets enregistrent les IDs/codes canoniques; les labels sont résolus selon langue et marché.

Le prochain niveau de détail, à produire avec le Dictionnaire de données, pourra transformer les attributs de chaque sous-catégorie en schémas techniques précis. Ce Document 03 constitue la taxonomie produit V1 et la base du futur import initial du Taxonomy Center.
