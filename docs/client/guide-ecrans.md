**GUIDE FONCTIONNEL  
DES ÉCRANS & PARCOURS UTILISATEURS**

Plateforme Écosystème RDC

Spécification écran par écran - Version de référence V1

Document complémentaire au Cahier des charges développeur et au Journal de conception.  
Septembre 2026

| **Objet -** Décrire, pour chaque écran, ce qui est visible, comment les éléments fonctionnent, les règles métier qui les gouvernent, les variantes selon le rôle actif, les états d’erreur et les liens avec le reste de l’écosystème. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# Mode d’emploi du guide

- Ce document décrit l’expérience visible et le comportement attendu. Le cahier des charges reste la référence normative pour l’architecture, la sécurité, les objets métier et les exigences non visuelles.

- La navigation mobile permanente est : Accueil · Explorer · + Publier · Messages · Compte. Elle doit rester cohérente dans les modules principaux.

- Un même compte peut agir dans plusieurs contextes : Individu, Prestataire individuel, Employeur particulier, Membre d’organisation, Administrateur d’organisation ou Représentant autorisé. Le changement de contexte ne crée pas un nouveau compte.

- Les droits commerciaux (abonnement, pass, quota) ne remplacent jamais les permissions, l’éligibilité, la vérification, le consentement ou les règles de marché.

- Les mockups sont des références de direction. Lorsqu’un écran nécessaire n’a pas encore de mockup dédié, il est marqué « Écran fonctionnel à maqueter ».

- Les interfaces doivent fonctionner en français en priorité et être préparées pour l’internationalisation et les réalités de connexion mobile en RDC.

# Carte des parcours

- Découverte : Accueil → Explorer → Résultat → Profil/Fiche → Action contextuelle.

- Commerce : Marketplace → Fiche produit → Commande → Paiement → Fulfillment/Livraison → Historique → Avis.

- Services : Explorer → Prestataire/Entreprise → Service → Demande de devis → Discussion → Acceptation → Réservation/Exécution → Avis.

- Emploi : Emplois → Offre → Candidature → Pipeline → Entretien → Décision; côté employeur : publier → présélection → comparaison factuelle → entretien.

- Événement : Découverte → Détail → Inscription/Billet → Paiement si applicable → QR → Check-in.

- Compte : Mon espace → À traiter → activités → profils → sécurité/vérification/abonnements.

# 1. Accueil

| **Rôle de cet écran -** Être le point d’entrée universel : comprendre rapidement ce que la plateforme permet, rechercher dans tout l’écosystème et accéder aux opportunités pertinentes sans transformer l’accueil en tableau de bord surchargé. |
|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image1.png" style="width:4.7in;height:4.2952in" />

Mockup de référence - Accueil

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- En-tête avec identité active, notifications et accès au contexte du compte.

- Recherche universelle visible immédiatement.

- Raccourcis vers Entreprises & Services, Marketplace, Emplois, Événements et autres domaines activés.

- Blocs de découverte : contenus récents, pertinents, sponsorisés clairement identifiés, ou opportunités liées au contexte.

- Navigation permanente Accueil · Explorer · + Publier · Messages · Compte.

## Comment l’écran fonctionne

- La recherche accepte mots-clés, catégories, métiers, services, produits et lieux; elle envoie vers Explorer avec filtres préremplis.

- Les cartes ouvrent l’objet correspondant : entreprise, service, produit, emploi, événement, restaurant, etc.

- La personnalisation doit rester explicable et ne jamais mélanger contenu sponsorisé et recommandation organique.

- Le contenu dépend du marché actif, de la localisation disponible, des catégories activées et de l’identité active.

## Comportement selon le contexte utilisateur

- Visiteur : découverte et recherche; authentification demandée au moment d’une action nécessitant un compte.

- Individu : accès à ses activités et opportunités générales.

- Prestataire/Organisation : même accueil public, mais raccourcis contextuels vers gestion et publication.

- Aucun plan payant ne doit transformer artificiellement un acteur en « plus fiable ».

## Navigation et actions principales

- Recherche → Explorer.

- Catégorie → résultats filtrés.

- Carte → fiche détaillée.

- \+ Publier → menu universel de création.

- Messages/Compte → espaces personnels.

## Règles métier et données

- Sponsorisé doit être étiqueté.

- Vérifié décrit une vérification précise, jamais une recommandation.

- Les contenus privés, restreints ou non éligibles ne sont jamais exposés par l’accueil.

- La localisation améliore les résultats mais ne doit pas être obligatoire pour utiliser l’app.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Accueil → Explorer → Fiche Entreprise/Prestataire.

- Accueil → Marketplace → Produit.

- Accueil → Emplois → Offre.

- Accueil → Événements → Détail.

## Points de conception / décisions verrouillées

- La navigation centrale + Publier est une règle structurante et ne doit pas être remplacée par une multitude de boutons de création.

# 2. Explorer & recherche universelle

| **Rôle de cet écran -** Fournir un moteur de découverte transversal mais structuré, capable de retrouver des acteurs et objets différents sans les confondre. |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image2.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Explorer & recherche universelle

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Barre de recherche, filtres et onglets/types de résultats.

- Résultats Entreprises, Prestataires, Services, Produits, Emplois, Événements, Lieux, Restaurants, Formations selon disponibilité.

- Filtres par catégorie, localisation, attributs, disponibilité, prix ou autres champs pertinents au domaine.

- Possibilité d’enregistrer une recherche/alerte lorsque le contexte le permet.

## Comment l’écran fonctionne

- Une requête large peut afficher plusieurs familles de résultats; un onglet affine ensuite le type.

- Les filtres sont alimentés par la taxonomie et ses attributs, pas par des champs codés en dur écran par écran.

- Les alias/synonymes locaux aident à trouver une catégorie canonique sans créer des doublons.

- Le moteur ne déclare pas un acteur « meilleur »; il sépare pertinence, vérification, avis et promotion.

## Comportement selon le contexte utilisateur

- Visiteur : filtres et consultation publique.

- Utilisateur connecté : favoris, recherches sauvegardées, alertes.

- Entreprise/prestataire : peut voir ses propres contenus comme un utilisateur public, sans privilège de classement lié au plan.

## Navigation et actions principales

- Résultat → fiche.

- Filtre → mise à jour de la liste.

- Enregistrer → Mes alertes.

- Retour Accueil sans perdre inutilement la requête.

## Règles métier et données

- La taxonomie canonique est administrable.

- La recherche respecte visibilité, marché, éligibilité, confidentialité et statut du contenu avant classement.

- Les données sensibles ne deviennent jamais filtrables simplement parce qu’elles existent dans le profil.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Explorer → Entreprise/Prestataire/Produit/Emploi/Événement.

- Recherche sauvegardée → Compte/Alertes.

# 3. + Publier - passerelle universelle

| **Rôle de cet écran -** Centraliser toutes les créations possibles et afficher uniquement celles que l’identité active a le droit et la capacité d’utiliser. |
|--------------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image3.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - + Publier - passerelle universelle

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Choix contextuels : vendre un article, proposer un service, ajouter un produit, publier une offre d’emploi, créer un événement, créer une campagne, etc.

- Option « Promouvoir quelque chose » pour sélectionner un objet existant éligible.

- Indication de l’identité au nom de laquelle la publication sera faite.

## Comment l’écran fonctionne

- Le menu se construit selon identité active + permissions + éligibilité + entitlements + règles du marché.

- Choisir une action ouvre le formulaire spécialisé, jamais un formulaire générique monstrueux.

- Si plusieurs identités peuvent publier, l’utilisateur choisit ou confirme le contexte avant la création.

- Promouvoir ne crée pas un nouvel objet : il référence un objet existant autorisé.

## Comportement selon le contexte utilisateur

- Individu : vente personnelle, événement privé si éligible, emploi à domicile selon offre.

- Prestataire : service, disponibilité, contenus professionnels autorisés.

- Organisation : produits, services, emplois, événements, formations, campagnes selon type et permissions.

- Membre sans permission de publication : option masquée ou expliquée sans contournement.

## Navigation et actions principales

- Type de publication → formulaire spécialisé.

- Changer d’identité → sélecteur de contexte.

- Annuler → retour à l’écran précédent.

## Règles métier et données

- Abonnement/pass = capacité commerciale, pas autorité organisationnelle.

- Les catégories réglementées peuvent imposer vérification ou être interdites.

- Les brouillons doivent être sauvegardables.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- \+ Publier → Marketplace/Service/Emploi/Événement/Campagne.

- Publication créée → fiche + tableau de bord correspondant.

## Points de conception / décisions verrouillées

- Décision verrouillée : « Promouvoir quelque chose » fait partie de la version finale du menu.

# 4. Profil Entreprise / Organisation

| **Rôle de cet écran -** Présenter une organisation comme un acteur structuré de l’écosystème et regrouper ses offres publiques sans confondre identité, vérification et promotion. |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image4.png" style="width:4.7in;height:4.2952in" />

Mockup de référence - Profil Entreprise / Organisation

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Nom, secteur, localisation générale, description, contacts publics autorisés.

- Badges de vérification précis et informations de confiance.

- Onglets ou sections Services, Produits, Emplois, Événements, Formations et autres offres applicables.

- Actions : contacter, demander un devis, réserver, suivre/favori selon le module.

## Comment l’écran fonctionne

- Chaque bloc est alimenté par un objet métier spécialisé; le profil n’est pas une copie de toutes les données internes.

- Les actions sont contextuelles : demander un devis sur un service, postuler à un emploi, acheter un produit, etc.

- Les branches peuvent être représentées si l’organisation les utilise.

## Comportement selon le contexte utilisateur

- Public : informations publiques seulement.

- Membre de l’organisation : voit le même profil public; la gestion passe par le dashboard, pas par des contrôles cachés dans la fiche publique.

- Représentant autorisé : actions de gestion seulement si permission explicite.

## Navigation et actions principales

- Service → détail/service/devis.

- Produit → Marketplace.

- Emploi → offre.

- Événement → détail.

- Contacter → conversation contextualisée.

## Règles métier et données

- Un abonnement ne produit pas un badge de vérification.

- Adresse exacte non publiée lorsqu’elle est sensible.

- Avis et vérifications gardent leur provenance.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Explorer/Accueil → Profil organisation.

- Profil → Devis/Marketplace/Emploi/Événement/Messages.

# 5. Profil Prestataire individuel

| **Rôle de cet écran -** Permettre à une personne d’offrir professionnellement ses services sans l’obliger à se présenter comme une entreprise. |
|------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image2.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Profil Prestataire individuel

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Photo/identité publique choisie, métier/service, zone générale, disponibilité, expérience, compétences, langues.

- Vérifications granulaires et références professionnelles validées sans coordonnées privées.

- Avis contextuels et actions Contact / Demander un devis / Proposer un emploi lorsque pertinentes.

## Comment l’écran fonctionne

- Le profil distingue activité professionnelle publique et compte personnel privé.

- Le prestataire peut aussi être candidat à un emploi; ces rôles coexistent sans créer plusieurs logins.

- La disponibilité peut être structurée mais ne doit pas exposer des détails de sécurité inutiles.

## Comportement selon le contexte utilisateur

- Prestataire : gère son profil et ses services depuis Mon espace.

- Client : consulte et contacte.

- Employeur particulier/organisation : peut proposer une opportunité dans le respect du consentement et des règles de recrutement.

## Navigation et actions principales

- Contact → message contextualisé.

- Service → devis/réservation.

- Proposer un emploi → invitation/opportunité, jamais candidature automatique.

## Règles métier et données

- Téléphone vérifié, identité vérifiée, références vérifiées sont des statuts distincts.

- Aucune vérification ne garantit sécurité ou qualité.

- Garde d’enfants/soins peuvent exiger des contrôles renforcés avant visibilité.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Explorer → Prestataire.

- Prestataire → Devis/Réservation/Messages/Emploi.

# 6. Marketplace - recherche, filtres et résultats

| **Rôle de cet écran -** Permettre de découvrir des articles proposés par particuliers, prestataires ou entreprises tout en gardant une distinction claire du type de vendeur. |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image5.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Marketplace - recherche, filtres et résultats

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Recherche et catégories Marketplace.

- Filtres pertinents : état, prix, localisation, livraison/retrait, attributs de catégorie.

- Cartes produit avec vendeur, prix, état et informations essentielles.

- Indication Particulier / Professionnel / Entreprise vérifiée lorsque justifiée.

## Comment l’écran fonctionne

- La taxonomie définit les attributs de filtre par catégorie.

- Le produit et l’offre du vendeur sont conceptuellement séparés pour permettre des fiches riches sans dupliquer la définition produit.

- Le classement ne transforme pas la promotion en recommandation.

## Comportement selon le contexte utilisateur

- Acheteur : recherche, favori, commande.

- Particulier vendeur : parcours simplifié.

- Entreprise : catalogue et gestion plus riche via dashboard.

## Navigation et actions principales

- Carte → fiche produit.

- Filtres → résultats.

- Favori → Mon espace.

- Vendre → + Publier.

## Règles métier et données

- Catégories interdites/restreintes contrôlées.

- État du produit normalisé.

- Disponibilité/stock doit refléter l’état commercial autoritatif.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Marketplace → Produit → Commande.

- Marketplace → Profil vendeur.

# 7. Fiche produit Marketplace

| **Rôle de cet écran -** Donner suffisamment d’information pour décider d’acheter ou contacter le vendeur, puis initier une commande traçable. |
|-----------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image5.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Fiche produit Marketplace

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Photos, titre, prix/devise, état, description, attributs, vendeur, localisation générale.

- Options de retrait/livraison applicables.

- Actions acheter/commander, contacter, favori, signaler.

## Comment l’écran fonctionne

- Commander crée un Order avec lignes, sans considérer automatiquement le paiement comme réussi.

- Pour un article unique, une réservation de stock peut passer l’offre à Reserved puis Sold après réussite.

- La conversation conserve le contexte de l’article.

## Comportement selon le contexte utilisateur

- Acheteur : commande/contact.

- Vendeur propriétaire : voit la fiche publique mais gère stock/prix depuis son espace.

## Navigation et actions principales

- Acheter → Checkout.

- Contacter → Messages.

- Vendeur → profil.

- Signaler → Case/Support.

## Règles métier et données

- Stock, paiement et fulfillment sont des états séparés.

- Achat vérifié signifie interaction/commande enregistrée, pas qualité garantie.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Produit → Checkout → Paiement → Mes commandes → Avis.

# 8. Checkout / Commande Marketplace

| **Rôle de cet écran -** Transformer une intention d’achat en commande claire, avec mode de remise et paiement explicites. |
|---------------------------------------------------------------------------------------------------------------------------|

<img src="media/image5.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Checkout / Commande Marketplace

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Récapitulatif article, quantité si applicable, vendeur, montant, devise.

- Choix retrait, livraison vendeur ou partenaire si disponible.

- Choix Mobile Money/intégration approuvée ou espèces à la remise lorsque autorisé.

- Résumé des montants item et livraison séparés.

## Comment l’écran fonctionne

- Création idempotente de la commande pour éviter doublons.

- Paiement fournisseur passe par Initiated/Pending/Successful/Failed/Expired/Cancelled; le callback fournisseur est autoritatif.

- Espèces restent Unpaid jusqu’à confirmation de réception autorisée.

## Comportement selon le contexte utilisateur

- Acheteur confirme la commande.

- Vendeur reçoit l’ordre et agit sur fulfillment.

- Partenaire de livraison reçoit uniquement les données nécessaires si une Delivery Request existe.

## Navigation et actions principales

- Confirmer → paiement ou confirmation de commande cash.

- Retour → fiche sans dupliquer la commande.

## Règles métier et données

- Jamais de bouton libre « J’ai payé » faisant foi.

- Chaque changement monétaire est traçable.

- Pas de wallet/escrow général V1.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Checkout → Paiement → Confirmation → Mes commandes.

# 9. Mes commandes & suivi

| **Rôle de cet écran -** Permettre à l’acheteur de suivre séparément commande, paiement et remise/livraison. |
|-------------------------------------------------------------------------------------------------------------|

<img src="media/image6.png" style="width:4.7in;height:7.05in" />

Mockup de référence - Mes commandes & suivi

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Liste des commandes, statuts, montant, vendeur, date.

- Détail : statut commercial, paiement, fulfillment et livraison séparés.

- Actions contextuelles : contacter, confirmer réception cash si autorisé, signaler problème, consulter remboursement.

## Comment l’écran fonctionne

- La vue compose plusieurs états sans les fusionner.

- Les notifications sont déclenchées sur transitions significatives et dédupliquées.

- Une annulation enregistre acteur, raison, heure et conséquence paiement.

## Comportement selon le contexte utilisateur

- Acheteur : ses commandes uniquement.

- Vendeur : commandes reçues via dashboard, pas via l’espace acheteur.

## Navigation et actions principales

- Commande → détail.

- Problème → Case/Support.

- Commande terminée → avis contextuel.

## Règles métier et données

- Historique immuable des événements financiers critiques.

- Remboursement = objet séparé lié au paiement original.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Compte → Mes commandes.

- Commande → Messages/Support/Avis.

# 10. Services & recherche de prestataires

| **Rôle de cet écran -** Découvrir une prestation et passer d’une recherche vague à une demande structurée. |
|------------------------------------------------------------------------------------------------------------|

<img src="media/image7.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Services & recherche de prestataires

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Résultats prestataires/entreprises et services.

- Filtres par catégorie, zone, mode de prestation, disponibilité ou attributs métier.

- Informations de confiance pertinentes.

## Comment l’écran fonctionne

- Service et profession sont reliés mais distincts.

- Le moteur peut afficher plusieurs fournisseurs pour une même catégorie sans déclarer un gagnant.

## Comportement selon le contexte utilisateur

- Client : recherche et devis.

- Prestataire : apparaît selon profil/service/éligibilité.

## Navigation et actions principales

- Résultat → profil/service.

- Demander un devis → formulaire.

## Règles métier et données

- Les catégories et attributs proviennent de la taxonomie.

- Vérification et avis restent séparés.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Explorer → Service → Devis → Messages.

# 11. Demande de devis

| **Rôle de cet écran -** Capturer le besoin du client de manière assez structurée pour obtenir des réponses comparables sans imposer un formulaire rigide à tous les métiers. |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image7.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Demande de devis

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Description du besoin, catégorie/service, localisation, photos/documents si utiles, délai, budget facultatif, options propres au service.

- Choix d’un prestataire précis ou envoi contrôlé à plusieurs prestataires éligibles lorsque cette fonctionnalité est activée.

## Comment l’écran fonctionne

- Le formulaire adapte ses champs à la catégorie.

- La demande crée un Quote Request; les réponses sont des Quote objects versionnables.

- Un besoin de visite technique peut déclencher une réservation avant devis final.

## Comportement selon le contexte utilisateur

- Client : crée et reçoit.

- Prestataire/organisation : répond si autorisé.

## Navigation et actions principales

- Envoyer → confirmation + suivi.

- Réponse → comparaison/discussion.

## Règles métier et données

- Anti-spam et limitation du multi-envoi.

- Documents privés accessibles uniquement aux parties autorisées.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Service → Demande → Mes devis → Conversation.

# 12. Devis reçu, comparaison & acceptation

| **Rôle de cet écran -** Permettre au client de comprendre, discuter et accepter/refuser une proposition sans transformer la plateforme en arbitre de qualité. |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image7.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Devis reçu, comparaison & acceptation

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Lignes de devis, total, devise, durée, validité, conditions, version.

- Actions Accepter / Poser une question / Refuser.

- Comparaison factuelle de plusieurs devis lorsque disponibles.

## Comment l’écran fonctionne

- Toute révision crée une nouvelle version traçable.

- Acceptation change le workflow commercial mais ne marque pas automatiquement un paiement de service.

- Le paiement général des services reste hors V1 sauf flux explicitement intégré.

## Comportement selon le contexte utilisateur

- Client : compare et décide.

- Prestataire : voit statut et discussion.

## Navigation et actions principales

- Question → conversation contextuelle.

- Accepter → suite de prestation/réservation selon service.

## Règles métier et données

- Pas de score « meilleur devis ».

- Prix et conditions affichés tels que proposés.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Mes devis → Messages → Réservation/Exécution.

# 13. Réservations & disponibilités

| **Rôle de cet écran -** Permettre de réserver une ressource, une capacité ou un rendez-vous selon le type d’offre. |
|--------------------------------------------------------------------------------------------------------------------|

<img src="media/image8.png" style="width:4.7in;height:4.2952in" />

Mockup de référence - Réservations & disponibilités

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Calendrier/date, créneaux, durée, capacité ou ressource, règles de réservation.

- Résumé et statut Requested/Pending/Confirmed/Modified/Completed/Cancelled.

## Comment l’écran fonctionne

- Le modèle sous-jacent peut être ressource précise, inventaire par type, capacité, rendez-vous ou nuitées.

- Heures d’ouverture et disponibilité réservable sont distinctes.

- Exceptions, buffers, préavis et réservations existantes modifient la disponibilité.

## Comportement selon le contexte utilisateur

- Client : demande/réserve.

- Fournisseur : confirme selon mode configuré.

## Navigation et actions principales

- Choisir créneau → récapitulatif → confirmation.

- Modifier/annuler selon règles.

## Règles métier et données

- Conflits empêchés côté serveur.

- Pas de double réservation sur ressource exclusive.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Restaurant/Hôtel/Salon/Service → Réservation → Mon espace.

# 14. Restaurants & commande alimentaire

| **Rôle de cet écran -** Réunir découverte du restaurant, menu, panier, paiement et fulfillment sans créer une flotte propriétaire. |
|------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image9.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Restaurants & commande alimentaire

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Liste restaurants, fiche, menu, articles, panier.

- Mode retrait, livraison restaurant ou livraison partenaire.

- Paiement et confirmation.

- Suivi commande alimentaire.

## Comment l’écran fonctionne

- Food Order a son propre état : Received/Accepted/Preparing/Ready/Picked up/Delivered/Collected/Completed.

- Delivery Request reste séparée et n’écrase jamais l’état de la commande.

- Le restaurant peut accepter/refuser selon disponibilité; la préparation peut affecter l’annulation/remboursement.

## Comportement selon le contexte utilisateur

- Client : commande.

- Restaurant : gère menu/commandes.

- Entreprise de livraison : reçoit mission si sélectionnée.

## Navigation et actions principales

- Restaurant → menu → panier → mode → paiement → suivi.

## Règles métier et données

- Montant nourriture et livraison distincts.

- Responsable de collecte cash explicitement défini.

- Pas de GPS flotte/routage avancé requis en V1.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Explorer → Restaurant → Food Order → Delivery Request → Mes commandes.

# 15. Livraison partenaire

| **Rôle de cet écran -** Coordonner client, marchand et entreprise de livraison avec un workflow distinct du paiement et de la commande. |
|-----------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image9.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Livraison partenaire

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Statut Requested/Accepted/Heading to pickup/Picked up/In delivery/Delivered et exceptions.

- Informations nécessaires au pickup/dropoff, sans exposer des données inutiles.

- Contact contextuel et preuve/confirmation de remise selon règles.

## Comment l’écran fonctionne

- Une Delivery Request est liée à Food Order ou Marketplace Order.

- L’entreprise de livraison publie zones, horaires, types supportés et règles de prix.

- Le client voit un parcours compréhensible même si plusieurs objets métier sont composés.

## Comportement selon le contexte utilisateur

- Client : suit.

- Marchand : voit l’avancement utile.

- Livraison : uniquement données de fulfillment nécessaires.

## Navigation et actions principales

- Suivi → détail livraison.

- Problème → Case.

## Règles métier et données

- Séparation stricte des montants.

- Cash collection responsibility explicite.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Commande → Livraison → Confirmation → Avis/Support.

# 16. Emplois - recherche & détail d’offre

| **Rôle de cet écran -** Permettre à un candidat de trouver une opportunité et comprendre les exigences avant de postuler. |
|---------------------------------------------------------------------------------------------------------------------------|

<img src="media/image10.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Emplois - recherche & détail d’offre

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Recherche emploi, filtres métier/localisation/type/arrangement.

- Détail : employeur, rôle, exigences essentielles/préférées, compétences, expérience, salaire si publié, modalités.

- Label Employeur particulier pour emploi à domicile.

## Comment l’écran fonctionne

- Occupation, skills, qualifications et expérience sont structurés séparément.

- La plateforme peut montrer une correspondance factuelle ✓/○/⚠ sans verdict de recrutement.

- « Non trouvé » dans le profil ne signifie pas absence réelle de compétence.

## Comportement selon le contexte utilisateur

- Candidat : recherche/postule gratuitement en principe.

- Employeur particulier ou organisation : publie selon droits.

## Navigation et actions principales

- Postuler → candidature structurée.

- Sauvegarder → Mon espace.

- Contacter seulement selon politique de l’offre.

## Règles métier et données

- Pas de discrimination par critères protégés.

- Pas de ranking candidat « meilleur » autonome.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Emplois → Offre → Candidature → Suivi → Entretien.

# 17. Candidature & suivi candidat

| **Rôle de cet écran -** Collecter une candidature réutilisable mais contextualisée, puis rendre le pipeline compréhensible au candidat. |
|-----------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image10.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Candidature & suivi candidat

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- CV/profil, réponses de présélection, documents autorisés, consentements.

- Statut de candidature et prochaines actions.

- Invitation à entretien et possibilité de confirmer/rescheduler/decliner.

## Comment l’écran fonctionne

- La candidature est un objet distinct du profil.

- Les réponses et documents sont visibles uniquement aux recruteurs autorisés.

- Une invitation par Enterprise discovery devient candidature uniquement si la personne postule.

## Comportement selon le contexte utilisateur

- Candidat : ses candidatures.

- Recruteur : seulement celles relevant de son scope.

## Navigation et actions principales

- Soumettre → confirmation.

- Entretien → événement opérationnel restreint.

## Règles métier et données

- Consentement et rétention des données de recrutement.

- Aucun plan ne permet de contourner la confidentialité.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Offre → Candidature → Messages/Entretien.

# 18. Dashboard recrutement & comparaison factuelle

| **Rôle de cet écran -** Aider le recruteur à gérer le pipeline et comparer les preuves pertinentes sans automatiser la décision humaine. |
|------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image10.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Dashboard recrutement & comparaison factuelle

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Liste candidats, étapes pipeline, filtres, indicateurs factuels.

- Vue candidat avec exigences Essential/Preferred, réponses, références autorisées.

- Planification entretien, kit d’entretien, collaboration interne.

## Comment l’écran fonctionne

- La comparaison montre présence/absence/non renseigné de critères documentés.

- Les permissions peuvent être limitées par offre, branche ou département.

- Les évaluations sophistiquées restent post-V1.

## Comportement selon le contexte utilisateur

- Recruteur : accès recrutement.

- Billing manager : aucun accès automatique aux dossiers candidats.

- Admin organisation : délègue permissions.

## Navigation et actions principales

- Candidat → dossier.

- Planifier → entretien.

- Étape pipeline → mise à jour auditée.

## Règles métier et données

- Pas de rejet autonome fondé sur IA.

- Références contactées avec consentement.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Dashboard → Candidat → Entretien → Décision humaine.

# 19. Formation & développement des compétences

| **Rôle de cet écran -** Relier besoins de compétences, employeurs et prestataires de formation dans le même écosystème. |
|-------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Programme, compétences enseignées, prérequis, niveau, format, lieu, durée, calendrier, capacité, prix, information certificat.

- Options cohorte privée/entreprise, devis, invitation et inscription.

## Comment l’écran fonctionne

- Une offre d’emploi ou un besoin d’entreprise peut référencer une formation pertinente avec explication factuelle.

- Employeur peut inviter employés/candidats avec consentement.

- Participation et complétion sont suivies administrativement.

## Comportement selon le contexte utilisateur

- Apprenant/candidat : voit/invite/s’inscrit.

- Employeur : demande cohorte/devis.

- Prestataire de formation : gère programme et sessions.

## Navigation et actions principales

- Programme → devis/inscription.

- Session → réservation/participation.

## Règles métier et données

- Certificat conserve provenance.

- Complétion ne signifie pas compétence vérifiée ni éligibilité à l’embauche.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Jobs ↔ Skills ↔ Training ↔ Professional development.

## Points de conception / décisions verrouillées

- Écran fonctionnel à maqueter : le moteur est V1 mais un mockup dédié Formation reste à produire.

# 20. Événements - découverte & détail

| **Rôle de cet écran -** Découvrir des événements publics et gérer correctement visibilité, inscription, invitation et accès. |
|------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image8.png" style="width:4.7in;height:4.2952in" />

Mockup de référence - Événements - découverte & détail

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Liste/agenda, filtres, détail date/heure/lieu/organisateur/programme.

- Mode public, ciblé, non listé, invitation ou interne selon objet.

- Inscription, billet, invitation ou RSVP selon type.

## Comment l’écran fonctionne

- RSVP, registration et invitation sont des concepts distincts.

- Événements privés personnels ne sont ni indexés ni promus.

- Événements opérationnels restreints (entretien, admission) ne passent jamais par la découverte publique.

## Comportement selon le contexte utilisateur

- Public : découvre public.

- Invité : accède via invitation autorisée.

- Organisateur : gère depuis dashboard.

## Navigation et actions principales

- Détail → inscription/billet.

- Lieu → fiche lieu si public.

## Règles métier et données

- Visibilité appliquée avant recherche.

- Capacité et accès contrôlés.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Accueil/Explorer → Événement → Ticket/Registration → Mon espace.

# 21. Billetterie, paiement & QR

| **Rôle de cet écran -** Gérer les événements payants avec un enchaînement traçable Ticket Order → Payment → Ticket → Check-in. |
|--------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image8.png" style="width:4.7in;height:4.2952in" />

Mockup de référence - Billetterie, paiement & QR

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Types de billets, prix, quantité, dates de vente, limites.

- Checkout, paiement, confirmation, billet numérique/QR.

- Statut billet Valid/Checked-in/Cancelled/Refunded.

## Comment l’écran fonctionne

- QR/token unique; double scan détecté.

- Annulation événement déclenche workflow de remboursement et notification.

- Report d’événement conserve choix configurables billet/remboursement.

## Comportement selon le contexte utilisateur

- Participant : achète et présente billet.

- Organisateur/staff autorisé : scanne/check-in.

## Navigation et actions principales

- Acheter → paiement → billet.

- QR → check-in.

## Règles métier et données

- Paiement provider authoritative.

- Refund séparé et immuable.

- Pas de wallet.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Événement → Ticket Order → Paiement → Ticket → Check-in.

# 22. Écoles - parcours parent / bénéficiaire

| **Rôle de cet écran -** Permettre au parent/tuteur de découvrir une école, gérer un bénéficiaire privé et suivre une demande sans créer de profil public d’enfant. |
|--------------------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image11.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Écoles - parcours parent / bénéficiaire

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Découverte école, profil, ajout privé du bénéficiaire, demande d’admission, suivi, communications/documents.

- Sélecteur du bénéficiaire autorisé dans le contexte approprié.

## Comment l’écran fonctionne

- Beneficiary est un objet privé lié à des relations autorisées.

- Le parent ne voit que les bénéficiaires auxquels il est relié.

- Les documents scolaires restent contextuels et minimisés.

## Comportement selon le contexte utilisateur

- Parent/tuteur : accès bénéficiaire autorisé.

- École : personnel autorisé gère admissions.

- Public : profil école seulement.

## Navigation et actions principales

- École → admission.

- Demande → suivi/messages.

## Règles métier et données

- Aucun profil public enfant.

- Consentement et minimisation renforcés.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Explorer → École → Admission → Suivi → Communication.

# 23. École - administration admissions

| **Rôle de cet écran -** Donner à l’établissement une vue structurée des candidatures et décisions, séparée des données publiques. |
|-----------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image11.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - École - administration admissions

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Dashboard, demandes, dossier candidat, planification entretien, décision, élèves inscrits/communication.

## Comment l’écran fonctionne

- Permissions par section/rôle possibles.

- Entretien = événement opérationnel restreint.

- Décision enregistrée et communiquée aux personnes autorisées.

## Comportement selon le contexte utilisateur

- Personnel école autorisé seulement.

- Parent ne voit que son propre dossier/bénéficiaire.

## Navigation et actions principales

- Demande → dossier → entretien → décision.

## Règles métier et données

- Audit des décisions/actions sensibles.

- Données enfant jamais exposées dans Explorer.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Admissions ↔ Booking ↔ Messaging ↔ Beneficiary.

# 24. Campagnes, associations & volontariat

| **Rôle de cet écran -** Permettre aux organisations éligibles de publier campagnes et opportunités de volontariat sans les confondre avec emplois ou commerce. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Profil association, campagne, cause, objectif, mises à jour datées, besoins en biens/volontaires/contributions selon configuration.

- Volunteer Opportunity distincte d’une offre d’emploi.

## Comment l’écran fonctionne

- Types campagne : collecte, biens, volontariat, sensibilisation, projet communautaire.

- Contribution garde son contexte et sa provenance.

- Promotion soumise à règles plus strictes.

## Comportement selon le contexte utilisateur

- Public : découvre campagne autorisée.

- Organisation éligible : publie/gère.

- Volontaire : s’inscrit selon opportunité.

## Navigation et actions principales

- Campagne → contribution/volontariat/messages.

## Règles métier et données

- Éligibilité forte et modération.

- Pas de promesse d’impact non vérifiée.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Explorer → Organisation → Campagne → Participation.

## Points de conception / décisions verrouillées

- Écran fonctionnel à maqueter : architecture et règles V1 définies, mais aucun mockup dédié n’est encore verrouillé.

# 25. Messagerie contextuelle

| **Rôle de cet écran -** Permettre aux utilisateurs de communiquer tout en conservant le contexte métier de la conversation. |
|-----------------------------------------------------------------------------------------------------------------------------|

<img src="media/image12.png" style="width:4.7in;height:4.2952in" />

Mockup de référence - Messagerie contextuelle

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Boîte de réception, filtres, identité active, conversations.

- Carte contexte : produit, devis, candidature, livraison, événement, réservation, etc.

- Actions structurées liées au contexte.

- Pour organisations : Team Inbox, assignation et réponses selon permissions.

## Comment l’écran fonctionne

- Une conversation sait pourquoi elle existe.

- Messages humains et événements système sont visuellement distingués.

- La conversation persiste après clôture de l’objet selon règles de rétention.

- Push notification n’est pas le message lui-même.

## Comportement selon le contexte utilisateur

- Individu : conversations personnelles.

- Organisation : boîte d’équipe selon rôle/branche.

- Livraison/recruteur/prestataire : uniquement contextes autorisés.

## Navigation et actions principales

- Contexte → objet source.

- Action structurée → workflow source.

## Règles métier et données

- Anti-spam, pièces jointes contrôlées, confidentialité.

- Identité d’envoi explicite.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Tous modules → Messages → retour objet.

# 26. Notifications & À traiter

| **Rôle de cet écran -** Séparer information, alerte et action requise pour éviter une boîte de notifications inutilisable. |
|----------------------------------------------------------------------------------------------------------------------------|

<img src="media/image13.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Notifications & À traiter

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Centre de notifications par catégories.

- Vue À traiter avec actions prioritaires.

- Préférences de canaux et rappels.

## Comment l’écran fonctionne

- Une notification informe; une Action Item représente une tâche nécessitant action.

- Événements similaires sont dédupliqués.

- Les droits de l’utilisateur déterminent les actions visibles.

## Comportement selon le contexte utilisateur

- Individu : actions personnelles.

- Organisation : actions selon rôle/branche.

## Navigation et actions principales

- Notification → objet.

- À traiter → action directe ou contexte.

## Règles métier et données

- Pas de données sensibles inutiles dans push externe.

- Préférences respectées sauf communications obligatoires de sécurité/transaction.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Tous modules → Notifications/À traiter → objet concerné.

# 27. Mon espace / Compte

| **Rôle de cet écran -** Donner à une personne un cockpit transversal pour ses activités, profils, sécurité et obligations sans mélanger toutes les identités. |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image6.png" style="width:4.7in;height:7.05in" />

Mockup de référence - Mon espace / Compte

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- À traiter, Mes activités, Mes profils, Compte.

- Commandes, devis, réservations, candidatures, recrutements, annonces, événements, favoris, alertes, bénéficiaires selon usage.

- Sélecteur d’identité/profil.

- Vérification, abonnement/pass, confidentialité, sécurité, aide.

## Comment l’écran fonctionne

- L’utilisateur change de contexte actif sans changer de login.

- Les activités apparaissent selon leur relation à la personne.

- Les modules non utilisés restent discrets grâce à la divulgation progressive.

## Comportement selon le contexte utilisateur

- Individu : base.

- Prestataire/Employeur particulier : sections supplémentaires.

- Membre organisation : accès au dashboard si autorisé.

## Navigation et actions principales

- Carte activité → module correspondant.

- Changer profil → recalcul permissions et menus.

## Règles métier et données

- Authentication ≠ Identity ≠ Permission.

- Données privées jamais copiées dans profil public.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Compte ↔ toutes activités.

# 28. Dashboard Prestataire / Entreprise

| **Rôle de cet écran -** Fournir un espace opérationnel adapté au type d’acteur, du prestataire solo à l’organisation multi-utilisateur. |
|-----------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image14.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Dashboard Prestataire / Entreprise

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- À traiter, indicateurs, messages, devis, commandes, réservations, recrutement, catalogue, événements, promotions selon modules actifs.

- Gestion équipe/roles/branches pour organisations.

- Accès + Publier conservé dans l’architecture mobile.

## Comment l’écran fonctionne

- Dashboard est modulaire : une école, un restaurant et une entreprise de construction n’affichent pas les mêmes blocs.

- Les indicateurs sont calculés à partir des objets autoritatifs; ils ne remplacent pas les workflows.

- Progressive disclosure évite surcharge.

## Comportement selon le contexte utilisateur

- Prestataire solo : ses propres objets.

- Organisation member : scope selon permissions.

- Admin organisation : équipe/roles/configuration autorisée.

## Navigation et actions principales

- À traiter → objet.

- Module → liste détaillée.

- \+ Publier → passerelle universelle.

## Règles métier et données

- Permissions granulaires par module/action/objet/branche.

- Plan commercial peut limiter quota/capacité mais pas donner accès aux données d’un autre rôle.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Dashboard ↔ Orders/Quotes/Recruitment/Bookings/Events/Team.

# 29. Confiance, vérification & références

| **Rôle de cet écran -** Rendre la confiance explicable en montrant exactement ce qui a été vérifié et par quelle logique, sans score universel. |
|-------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image15.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Confiance, vérification & références

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Centre de vérification, statuts par type, détail des contrôles, références, signalement/modération, historique utile.

- Sur profils publics : badges précis, avis et provenance.

## Comment l’écran fonctionne

- Chaque Verification Record a type, statut, preuve/provenance et visibilité appropriée.

- Références professionnelles peuvent afficher un nombre/statut sans exposer les coordonnées du référent.

- Signalement crée un Case distinct.

## Comportement selon le contexte utilisateur

- Utilisateur : soumet preuves autorisées.

- Staff plateforme : traite selon rôle restreint.

- Public : ne voit que résultats de vérification destinés à être publics.

## Navigation et actions principales

- Vérifier → workflow.

- Signaler → Case.

- Faire appel → Appeal.

## Règles métier et données

- Vérification non achetable.

- Aucun trust score universel.

- Documents d’identité restent privés.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Profil ↔ Trust Center ↔ Case Management.

# 30. Plans, Passes, Promotion & facturation plateforme

| **Rôle de cet écran -** Expliquer les capacités commerciales disponibles et permettre l’achat de droits/quotas sans confondre paiement et autorisation. |
|---------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image16.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Plans, Passes, Promotion & facturation plateforme

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Plans Individu/Professionnel/Business/Enterprise conceptuels, passes temporaires, comparaison de capacités.

- Promotion d’objets existants éligibles.

- Historique facturation plateforme, reçus/factures selon obligations.

## Comment l’écran fonctionne

- Entitlement Engine active capacités/limites après paiement confirmé.

- Pass recrutement 30 jours, publication unique et premium annuel sont des produits distincts.

- Promotion est étiquetée Sponsorisé et n’altère pas la vérification.

## Comportement selon le contexte utilisateur

- Individu/household : premium ou pass.

- Prestataire/entreprise : plans selon besoins.

- Organisation : seuls rôles billing autorisés achètent/modifient.

## Navigation et actions principales

- Choisir plan → paiement plateforme.

- Promouvoir → sélectionner objet.

## Règles métier et données

- Prix exacts non figés.

- Pas de pourcentage de commission comme modèle principal.

- Frais fournisseur de paiement peuvent s’appliquer.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Compte/Dashboard → Plans → Paiement → Entitlements.

# 31. Abonnements de services & engagements récurrents externes

| **Rôle de cet écran -** Permettre de suivre des services récurrents connectés ou des engagements externes sans prétendre traiter tous les paiements. |
|------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image17.png" style="width:4.7in;height:5.14295in" />

Mockup de référence - Abonnements de services & engagements récurrents externes

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Découverte service récurrent, détail/plan, souscription/suivi, interventions/support.

- Vue consolidée des engagements récurrents externes lorsque l’utilisateur les enregistre.

- Côté fournisseur : clients abonnés, interventions, facturation/paiements selon intégration.

## Comment l’écran fonctionne

- Connected Service Subscription est distinct de Platform Subscription.

- External Recurring Commitment peut être suivi sans que la plateforme soit le processeur du paiement.

- Rappels et statut restent explicites sur leur source.

## Comportement selon le contexte utilisateur

- Client : suit ses engagements.

- Prestataire/entreprise : gère abonnements connectés.

## Navigation et actions principales

- Service → souscription.

- Engagement → rappel/détail.

## Règles métier et données

- Ne pas afficher un paiement comme confirmé sans source autoritative.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Services ↔ Subscriptions ↔ Notifications ↔ Compte.

# 32. Confidentialité, consentements & sécurité du compte

| **Rôle de cet écran -** Donner à l’utilisateur une vue compréhensible de ses choix de confidentialité, consentements, sessions et données sensibles. |
|------------------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image18.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Confidentialité, consentements & sécurité du compte

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Centre confidentialité, visibilité profil, consentements, localisation, recommandations, sécurité, sessions/appareils, connexions.

- Historique ou état des consentements importants.

## Comment l’écran fonctionne

- Les consentements sont spécifiques au but; une autorisation de candidature ne vaut pas découverte recruteur.

- Révocation agit pour les usages futurs selon contraintes légales/transactionnelles.

- MFA/step-up pour opérations sensibles.

## Comportement selon le contexte utilisateur

- Individu : ses paramètres.

- Organisation : politiques organisationnelles distinctes des préférences personnelles.

## Navigation et actions principales

- Modifier → confirmation.

- Session suspecte → révoquer.

## Règles métier et données

- Data minimization, purpose limitation, retention.

- Les réglages privés ne sont pas exposés publiquement.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Compte → Confidentialité/Sécurité → modules affectés.

# 33. Admin / Back-office

| **Rôle de cet écran -** Permettre à la plateforme d’opérer, configurer et modérer l’écosystème avec séparation des responsabilités et audit. |
|----------------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image19.png" style="width:4.7in;height:4.2952in" />

Mockup de référence - Admin / Back-office

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Dashboard, files de vérification, modération, utilisateurs/organisations, taxonomy center, contenus, commerce, support/cases, billing, promotion, configuration marché, sécurité.

- Feature flags et contrôles d’urgence.

## Comment l’écran fonctionne

- Chaque rôle staff reçoit un périmètre minimal.

- Actions financières/sensibles peuvent exiger double contrôle.

- Taxonomie administrable : créer, renommer, réordonner, alias, activer/désactiver, fusionner selon gouvernance.

## Comportement selon le contexte utilisateur

- Platform staff uniquement; rôles spécialisés.

- Support n’obtient pas automatiquement accès financier complet.

## Navigation et actions principales

- File → dossier → action auditée.

- Market config → règles du marché.

## Règles métier et données

- Audit immuable des actions sensibles.

- Pas d’accès global par défaut.

- Désactivation préférée à suppression destructive pour catégories utilisées.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Admin ↔ tous domaines via permissions contrôlées.

# 34. Desktop & responsive

| **Rôle de cet écran -** Transposer les mêmes parcours sur grand écran sans créer une seconde application conceptuellement différente. |
|---------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image20.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Desktop & responsive

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Accueil/Explorer en grille, dashboards en panneaux/tableaux, messagerie avec contexte latéral, recrutement et commandes en vues plus denses.

## Comment l’écran fonctionne

- Les objets, statuts et actions sont identiques à mobile.

- Desktop peut afficher simultanément liste + détail; mobile séquence les vues.

- Les URL/deep links doivent pointer vers l’objet et restaurer le contexte autorisé.

## Comportement selon le contexte utilisateur

- Même identité et permissions sur tous appareils.

## Navigation et actions principales

- Navigation latérale peut compléter la barre principale sur desktop sans changer les noms des domaines.

## Règles métier et données

- Responsive par contenu, pas simple agrandissement du mobile.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Tous écrans mobile ↔ équivalent desktop.

# 35. Onboarding, connexion & choix du contexte actif

| **Rôle de cet écran -** Faire entrer l’utilisateur dans l’écosystème avec le minimum de friction et préparer l’usage multi-identité. |
|--------------------------------------------------------------------------------------------------------------------------------------|

<img src="media/image21.png" style="width:6.8in;height:4.53333in" />

Mockup de référence - Onboarding, connexion & choix du contexte actif

| **Lecture du mockup -** Le visuel fixe la direction UX et les parcours. Les prix, noms, logos, textes générés ou valeurs chiffrées visibles restent illustratifs tant qu’ils ne sont pas explicitement validés dans les règles métier. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Ce que l’utilisateur trouve sur l’écran

- Bienvenue/connexion/inscription, informations de base, choix initial d’intérêts facultatifs, accès à Mon espace.

- Création ultérieure Prestataire, Organisation ou Employeur particulier sans nouveau login.

## Comment l’écran fonctionne

- L’onboarding ne doit pas forcer l’utilisateur à choisir définitivement un « type de compte ».

- Les identités supplémentaires se créent au moment où le besoin apparaît.

- Une organisation peut être créée, revendiquée ou rejointe.

## Comportement selon le contexte utilisateur

- Visiteur → compte individuel de base.

- Utilisateur existant → connexion et restauration contexte.

## Navigation et actions principales

- Connexion → Accueil.

- Créer profil pro/org → workflow dédié.

## Règles métier et données

- MFA proportionnelle au risque.

- Récupération de compte sécurisée.

## États particuliers à prévoir

- Chargement avec squelette plutôt qu’un écran blanc.

- État vide avec explication et prochaine action utile.

- Erreur réseau avec bouton Réessayer sans perdre les données déjà saisies.

- Contenu supprimé, expiré ou devenu indisponible avec message explicite.

- Session expirée : réauthentification puis retour au contexte en cours lorsque cela est sûr.

## Responsive, accessibilité et faible connexion

- Mobile prioritaire; zones tactiles suffisamment grandes et hiérarchie lisible.

- Desktop conserve le même modèle mental mais exploite colonnes, panneaux latéraux et tableaux.

- Images compressées et chargement progressif; pagination/infinite scroll contrôlé.

- Actions critiques accessibles au clavier et avec libellés compréhensibles; contraste et taille de texte accessibles.

## Relations avec les autres écrans

- Onboarding → Accueil → Mon espace → création d’identités.

# Annexe A - Écrans encore à maqueter explicitement

- Formation & développement des compétences : programme, cohorte, inscription, gestion fournisseur.

- Campagnes / associations / volontariat : découverte, détail campagne, opportunité volontaire, gestion organisation.

- Checkout Marketplace détaillé et Mes commandes final : certains parcours apparaissent dans les collages mais méritent des écrans dédiés haute fidélité.

- Billetterie événement dédiée : sélection billet, checkout, ticket QR et check-in.

- États d’erreur/offline transversaux : maquettes de référence pour faible connexion, reprise, conflit et réconciliation.

# Annexe B - Règles transversales à appliquer à tous les écrans

- Ne jamais utiliser le plan payant comme preuve de confiance, de vérification ou de qualité.

- Ne jamais exposer une donnée privée parce qu’elle existe techniquement dans le modèle.

- Toute action doit être évaluée selon : authentification → identité active → relation/membership → permission et scope → éligibilité → entitlement → règles marché/catégorie → consentement/confidentialité → état sécurité.

- Les statuts monétaires viennent d’une confirmation fournisseur, d’une confirmation cash autorisée, d’un remboursement fournisseur ou d’une action administrative auditée.

- Les états commande, paiement, fulfillment, livraison et case restent indépendants.

- Les écrans doivent distinguer contenu organique, sponsorisé, vérifié, avis et références.

- Les créations passent par + Publier lorsque c’est une action utilisateur générale; les dashboards peuvent proposer des raccourcis sans casser cette architecture.

- Prévoir chargement, vide, erreur, expiration, annulation, permissions insuffisantes et réseau instable pour chaque workflow critique.

- Les montants stockent valeur + devise; CDF et USD doivent être supportés au minimum selon configuration marché.

- Le français est la langue de lancement; architecture i18n extensible aux langues pertinentes.

# Annexe C - Statut des mockups

| **Important -** Les mockups inclus dans ce guide sont des références fonctionnelles et visuelles issues du travail de conception. Ils ne constituent pas à eux seuls une spécification de données. Les règles écrites de ce guide et du cahier des charges prévalent sur tout texte accidentel, prix fictif ou artefact visible dans une image. |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
