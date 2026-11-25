# Connecte+ — Réponses consolidées au questionnaire de validation (Q1 à Q36)

| | |
|---|---|
| **Document** | Consolidé à partir du questionnaire du 9 novembre 2026 |
| **Préparé pour** | L'équipe de développement IMARATECH Group SARL |
| **Source** | « Connecte+ — Questions de validation pour le client » |
| **Auteur du questionnaire** | Ingénieur Jonathan Mwamba, cofondateur IMARATECH Group SARL |
| **Statut** | Q1 à Q35 : décisions verrouillées • Q36 : réponse finalisée, décision produit en attente de proposition |
| **Objet** | Consolider les décisions produit, règles métier, garde-fous, responsabilités et points à valider |
| **Version** | Version consolidée — 2026 |

> Conversion fidèle en Markdown du PDF `ConnectePlus_Reponses_Consolidees_Q1-Q36.pdf` (23 pages). Légende des notes : ⚖️ validation juridique requise ou recommandée ; ⚙️ proposition ou validation technique requise.

---

## 1. Objet et règles de lecture

Ce document consolide les réponses validées au questionnaire de Jonathan Mwamba. Il ne remplace pas les validations juridiques, fiscales, réglementaires, de paiement ou de sécurité qui doivent être réalisées par les spécialistes compétents. Les décisions ci-dessous constituent des exigences produit et métier à traduire en architecture, parcours, permissions, états, contrôles et critères d'acceptation.

> **STATUT** — Q1 à Q35 : décisions produit verrouillées. Q36 : réponse formellement donnée au questionnaire, mais décision d'intégrer le troc volontairement suspendue jusqu'à réception d'une proposition structurée de l'équipe de développement.

### Responsabilité de l'équipe de développement

Les spécifications expriment la vision produit, les règles métier, le comportement attendu, les garde-fous et les critères d'acceptation. Elles ne remplacent pas le jugement d'ingénierie. L'équipe de développement reste responsable de l'architecture technique, de la stratégie d'implémentation, de la sécurité technique, des performances, de la fiabilité, des intégrations, des tests, du déploiement et de l'identification des dépendances et cas limites.

- Lorsqu'une décision métier manque, présenter les options viables, leurs conséquences et une recommandation professionnelle — pas seulement une question ouverte.
- Signaler les contradictions, risques techniques, dépendances externes et décisions manquantes avant implémentation.
- Les exigences transversales doivent être rappelées dans chaque module concerné sous « Exigences déjà validées ayant un impact sur ce module ».
- Si deux développeurs raisonnables peuvent lire une exigence et implémenter des comportements métier matériellement différents, l'exigence doit être précisée avant développement.

### Principes transversaux déjà verrouillés

- Un seul compte humain peut agir dans plusieurs contextes légitimes ; Utilisateur ≠ Organisation.
- Authentification ≠ identité vérifiée ≠ organisation vérifiée ≠ autorité vérifiée ≠ qualification vérifiée ≠ réputation.
- Organisation = objet partagé indépendant de ses administrateurs ; les relations humaines passent par memberships, rôles, permissions et périmètres.
- Rôle = ce que la personne peut faire ; Scope/Périmètre = où, sur quoi et dans quelle branche/département elle peut le faire.
- Permissions et entitlements commerciaux sont séparés : payer n'accorde ni autorité, ni vérification, ni confiance, ni qualification.
- Les indicateurs de vérification sont factuels et non achetables.
- Les données sensibles sont accessibles selon finalité, nécessité, rôle et périmètre ; accès sensibles auditables.
- Les états commerciaux, paiement, fulfillment/livraison et litige restent séparés ; aucun état ne doit écraser les autres.
- Les taxonomies, seuils, durées, catégories et matrices appelées à évoluer doivent être configurables en back-office plutôt que codées en dur.

---

## 2. Réponses consolidées — Questions 1 à 36

### Synthèse

| N° | Sujet | Réf. | Statut |
|---|---|---|---|
| Q1 | Nom d'une organisation : homonymes et usurpation | Q-CLI8 | Verrouillée |
| Q2 | Qu'est-ce qu'une fiche « déjà existante » à revendiquer ? | Q-L1-6 | Verrouillée |
| Q3 | Revendication : preuves, rôle, délai et badge | Q-L1-8 | Verrouillée |
| Q4 | Conservation des documents des organisations | Q-CLI6 | Verrouillée |
| Q5 | Base légale du partage du numéro | LEG-PRV-01 a | Verrouillée |
| Q6 | Validité de l'accord et texte à afficher | LEG-PRV-03 a | Verrouillée |
| Q7 | Numéro visible par tous | LEG-PRV-03 b | Verrouillée |
| Q8 | Conservation de la trace d'une demande de numéro | LEG-PRV-05 a | Verrouillée |
| Q9 | Quand le vendeur retire son accord | LEG-PRV-04 a | Verrouillée |
| Q10 | Listes des numéros communiqués | LEG-PRV-04 b | Verrouillée |
| Q11 | Adresse IP et lutte contre la copie automatique | LEG-PRV-09 | Verrouillée |
| Q12 | Usage commercial des numéros | LEG-PRV-11 | Verrouillée |
| Q13 | WhatsApp et transfert du numéro | LEG-PRV-12 / 06 | Verrouillée |
| Q14 | Le modérateur peut-il voir le numéro ? | LEG-PRV-01 c | Verrouillée |
| Q15 | Conservation des avis et des réponses | LEG-PRV-05 b | Verrouillée |
| Q16 | Conservation après sanction ou suppression de compte | LEG-PRV sanctions | Verrouillée |
| Q17 | Organisation suspendue sans propriétaire | LEG-PRV orpheline | Verrouillée |
| Q18 | Table de correspondance des anciens comptes entreprise | LEG-PRV mapping | Verrouillée |
| Q19 | Contact du support dans l'application | Q-SUSP1 | Verrouillée |
| Q20 | Prévenir les propriétaires des anciens comptes entreprise | Q-SUSP5 | Verrouillée |
| Q21 | Les quatre rôles suffisent-ils ? | Q-CLI1 | Verrouillée |
| Q22 | Nombre d'organisations par compte | Q-CLI4 | Verrouillée |
| Q23 | Rôle donné par une invitation | Q-L1-3 | Verrouillée |
| Q24 | Suppression de son compte par l'utilisateur | Q-L1-10 | Verrouillée |
| Q25 | Liste des noms réservés | Q-L1-11 | Verrouillée |
| Q26 | Qui décide d'une revendication ? | Q-L1-12 | Verrouillée |
| Q27 | Documents demandés selon le type d'organisation | Q-CLI2 | Verrouillée |
| Q28 | Ce que peut publier un particulier | Q-CLI3 | Verrouillée |
| Q29 | Prestataires de services | Q-CLI7 | Verrouillée |
| Q30 | Qui accepte de partager le numéro d'une organisation ? | Q-CLI5 | Verrouillée |
| Q31 | Affichage du nom de l'auteur d'un avis | LEG-PRV-01 d / D11 | Verrouillée |
| Q32 | Moins de 3 avis | D3 | Verrouillée |
| Q33 | Motif de suspension visible | Q-SUSP2 | Verrouillée |
| Q34 | Restaurer une organisation archivée | Q-SUSP3 | Verrouillée |
| Q35 | Nom non modifiable après validation | A13 | Verrouillée |
| Q36 | Troc entre particuliers | Troc | **En attente — proposition dev** |

---

### PARTIE 1 — Questions urgentes : revendication et identité organisationnelle

#### Q1. Nom d'une organisation : homonymes et usurpation

*Réf. Q-CLI8 — Question d'origine : Deux organisations peuvent-elles porter le même nom ? Si oui, comment éviter que quelqu'un se fasse passer pour une entreprise connue avant que celle-ci ne s'inscrive vraiment ?*

> **VALIDÉE / VERROUILLÉE** — Les noms identiques ne doivent pas être interdits automatiquement, mais le premier enregistrement d'un nom ne crée aucun droit de propriété ni aucune présomption d'autorité.

**Décisions et exigences**

- Une organisation légalement établie doit pouvoir prouver son existence, son identité et, lorsque cela est pertinent, ses droits sur sa dénomination, ainsi que l'autorité de la personne qui agit pour elle.
- Distinguer le nom d'affichage, l'identité/dénomination légale et les droits vérifiés. Les documents exigés varient selon la forme juridique ou organisationnelle.
- En cas d'homonymie ou de conflit, les justificatifs vérifiés priment sur l'antériorité d'inscription sur Connecte+. La plateforme peut limiter ou suspendre l'usage contesté pendant l'examen, sans prétendre trancher une question relevant d'un tribunal ou d'une autorité compétente.
- Un changement légitime de nom reste possible par procédure contrôlée, avec justificatifs, revérification et historique d'audit.
- Les noms réservés/protégés sont traités avec des contrôles renforcés (voir Q25).

**Note :** ⚖️ Validation juridique recommandée pour les conflits de dénomination et les preuves recevables.

#### Q2. Qu'est-ce qu'une fiche « déjà existante » à revendiquer ?

*Réf. Q-L1-6 — Question d'origine : Aucun document du projet ne décrit de fiche créée à l'avance. Quelles organisations peuvent être revendiquées ? Le propriétaire actuel doit-il être prévenu quand quelqu'un revendique sa fiche ? Peut-il contester directement dans l'application ?*

> **VALIDÉE / VERROUILLÉE** — Connecte+ ne doit pas créer à l'avance des fiches d'organisations destinées à être revendiquées ultérieurement.

**Décisions et exigences**

- La création d'une organisation est initiée par une personne autorisée, puis soumise aux contrôles de vérification applicables.
- La « revendication » n'est donc pas un mécanisme général de prise en charge de fiches précréées.
- Exception : migration/récupération d'anciens comptes ou dossiers historiques. Dans ce cas, il s'agit d'une récupération et d'une vérification d'autorité, pas d'une revendication libre.
- Les conflits entre personnes prétendant administrer une même organisation sont des conflits d'autorité et suivent un processus de vérification/contestation adapté.

#### Q3. Revendication : preuves, rôle, délai et badge

*Réf. Q-L1-8 — Question d'origine : Quelles preuves faut-il demander ? Quel rôle donner à la personne acceptée ? Quel délai annoncer ? Souhaitez-vous un badge public « Autorité vérifiée » ?*

> **VALIDÉE / VERROUILLÉE** — Séparer strictement authentification, vérification d'identité, vérification de l'organisation, vérification de l'autorité et vérification des qualifications professionnelles.

**Décisions et exigences**

- Chaîne de contrôle : Organisation → documents d'existence/identité → représentant ou organe compétent → mandat/PV/délégation si nécessaire → administrateur Connecte+ autorisé.
- Le rôle supérieur de plateforme est « Administrateur principal », et non « Propriétaire ». La propriété juridique, la représentation légale et l'administration de la plateforme sont distinctes.
- Les délégations doivent être traçables, révocables, limitées au besoin et, lorsque pertinent, assorties d'une durée et d'un périmètre.
- Indicateur public recommandé : « Organisation vérifiée ». Il atteste un contrôle factuel et ne constitue ni recommandation, ni garantie de qualité, solvabilité ou confiance.
- La vérification est indépendante des plans payants : elle ne peut pas être achetée.
- Pour un particulier, la vérification d'identité n'est pas exigée pour la simple navigation/achat. Pour un prestataire individuel, elle devient pertinente pour l'activité professionnelle publique ; les activités réglementées nécessitent des contrôles supplémentaires de qualification/licence.

**Note :** Taxonomie à préserver : Authentifié ≠ Identité vérifiée ≠ Organisation vérifiée ≠ Autorité vérifiée ≠ Qualification vérifiée ≠ Réputation.

#### Q4. Conservation des documents des organisations

*Réf. Q-CLI6 — Question d'origine : Combien de temps garder les documents après refus, retrait ou fermeture ? Même question pour l'historique des changements de membres.*

> **VALIDÉE / VERROUILLÉE** — Refus d'une conservation uniforme et illimitée. La politique doit distinguer validité du document, conservation de l'original, référence minimisée/masquée et historique d'audit.

**Décisions et exigences**

- Classer au minimum : documents comptables/financiers ; documents juridiques de l'organisation ; preuves d'autorité/gouvernance ; pièces d'identité personnelles ; preuves et journaux de vérification.
- Pour une demande refusée, ne pas conserver indéfiniment l'original ; conserver seulement ce qui est justifié pour sécurité, fraude, contestation ou décision.
- Cycle de fermeture : actif → archivé/restreint → suppression ou anonymisation lorsque applicable.
- Accès aux documents sensibles strictement limité et journalisé ; legal hold possible lorsqu'une obligation ou un litige le justifie.
- Les durées doivent être configurables et validées juridiquement, pas codées en dur.
- L'autorité d'un représentant peut avoir une date de début, une date de fin et un statut ; à expiration, les droits correspondants expirent/sont suspendus jusqu'au renouvellement. Prévoir revérification périodique ou déclenchée par événement.

**Note :** ⚖️ À valider juridiquement selon les catégories de données et obligations applicables en RDC.

---

### PARTIE 2 — Avant mise en ligne : données personnelles, avis, sanctions et support

#### Q5. Base légale du partage du numéro

*Réf. LEG-PRV-01 a — Question d'origine : Sur quelle base légale repose la communication du numéro d'un vendeur à un utilisateur connecté ? Un accord séparé par canal et retirable suffit-il ?*

> **VALIDÉE / VERROUILLÉE** — Ne pas traiter tous les numéros comme une seule donnée. Distinguer numéro de compte/sécurité, contact professionnel, contact transactionnel et identifiant/destination de paiement.

**Décisions et exigences**

- Particulier : numéro personnel privé par défaut ; messagerie Connecte+ comme canal normal. Il peut volontairement autoriser appel/WhatsApp par canal ou communiquer lui-même son numéro.
- Prestataire individuel : contact professionnel distinct du numéro privé/de compte, avec canaux et horaires configurables.
- Organisation : contact professionnel/service client désigné, idéalement non lié au numéro personnel d'un dirigeant ou salarié ; plusieurs contacts fonctionnels possibles.
- Transaction : une fois une commande/paiement engagé, le retrait d'un contact optionnel ne doit pas rendre impossible livraison, retour, réclamation ou garantie. Un canal transactionnel approprié doit subsister pendant la période nécessaire.
- Paiement : destination Mobile Money/bancaire distincte du contact commercial ; le fournisseur de paiement peut traiter la transaction sans exposer le numéro personnel du vendeur.
- Le consentement est approprié pour la divulgation optionnelle d'un numéro personnel ; d'autres bases légales peuvent s'appliquer aux contacts professionnels/transactionnels. Le retrait cesse les divulgations futures mais n'efface pas ce que le destinataire a déjà vu.

**Note :** ⚖️ Base légale exacte et durée post-transaction à valider juridiquement.

#### Q6. Validité de l'accord et texte à afficher

*Réf. LEG-PRV-03 a — Question d'origine : L'accord est-il valable s'il est donné dans les réglages, avec un texte daté et versionné ? Quelle formulation afficher ?*

> **VALIDÉE / VERROUILLÉE** — Prévoir une information claire et, lorsqu'il est juridiquement requis, un consentement explicite, daté, versionné et traçable, présenté au moment pertinent — pas uniquement dans les réglages.

**Décisions et exigences**

- Le choix doit être contextuel au moment où l'utilisateur active la visibilité ou le canal ; les réglages servent ensuite à consulter, modifier ou retirer ce choix.
- Particulier : privé par défaut et choix séparé par canal. Prestataire : séparation contact privé/professionnel. Organisation : coordonnées professionnelles avec règles de gestion spécifiques.
- Tracer version du texte, date/heure, contact concerné, finalité, canaux, visibilité et modifications.
- Réutiliser un choix déjà valable pour éviter les demandes répétitives ; redemander une information/consentement si finalité, destinataires ou visibilité changent substantiellement.
- La version « 2026-10-v1 » reste provisoire. Les versions lingala et swahili doivent être des traductions fidèles du texte français juridiquement validé.

**Note :** ⚖️ Texte final et base juridique à valider avant mise en production.

#### Q7. Numéro visible par tous

*Réf. LEG-PRV-03 b — Question d'origine : Un vendeur peut-il rendre son numéro visible par tout le monde, y compris les personnes non connectées, s'il le demande expressément ?*

> **VALIDÉE / VERROUILLÉE** — Pas de règle unique pour tous les profils.

**Décisions et exigences**

- Particulier : le numéro personnel ne doit pas être public pour les visiteurs non connectés en V1.
- Prestataire individuel : peut désigner un contact professionnel distinct comme public, y compris éventuellement pour les visiteurs non connectés, avec information claire.
- Organisation : peut publier un numéro professionnel/commercial/service client et des horaires ou fonctions associés.
- Le numéro d'authentification, récupération ou sécurité ne devient jamais automatiquement public ; l'identifiant de paiement non plus.
- La publication nécessite une désignation explicite. Prévoir des mesures raisonnables anti-scraping.
- Un contact professionnel public n'autorise pas la réutilisation libre pour démarchage non sollicité ou constitution de bases de données.

**Note :** ⚖️ Validation juridique recommandée pour la publication publique et la prospection.

#### Q8. Conservation de la trace d'une demande de numéro

*Réf. LEG-PRV-05 a — Question d'origine : Combien de temps conserver la trace de l'accès à un numéro, y compris après fermeture d'un compte ?*

> **VALIDÉE / VERROUILLÉE** — Conserver une trace lorsque l'utilisateur obtient une coordonnée protégée via Connecte+, mais refuser une conservation détaillée illimitée.

**Décisions et exigences**

- Avant l'accès, informer l'utilisateur que l'action est enregistrée et que le titulaire pourra savoir quel compte Connecte+ a accédé à la coordonnée.
- Prévoir pour le titulaire un « Historique d'accès à mes coordonnées » : nom public/identifiant Connecte+, date/heure, contexte (annonce, commande, service) et type/canal.
- Conserver un journal interne plus détaillé uniquement pour les fonctions autorisées de sécurité/audit.
- Prévoir des rapports de confidentialité/activité (mensuels, trimestriels ou annuels selon usage) avec volumes et comptes distincts.
- Trois niveaux : journal détaillé pendant une période justifiée ; rapports synthétiques séparés ; statistiques réellement anonymisées à plus long terme lorsque licite.
- Si un numéro professionnel est public et consultable sans connexion, l'identité du visiteur ne peut pas être garantie ; seulement des statistiques agrégées.
- Les durées sont configurables et juridiquement validées.

**Note :** ⚖️ Valider divulgation du nom public, information préalable, durées, fermeture de compte et anonymisation.

#### Q9. Quand le vendeur retire son accord

*Réf. LEG-PRV-04 a — Question d'origine : Faut-il prévenir les personnes qui ont déjà reçu le numéro ? Peuvent-elles continuer à l'utiliser ?*

> **VALIDÉE / VERROUILLÉE** — Le retrait arrête les divulgations futures par Connecte+, mais ne peut pas effacer rétroactivement un numéro déjà vu ou enregistré par un tiers.

**Décisions et exigences**

- Pas de notification automatique à tous les anciens destinataires par défaut.
- Un accès antérieur ne vaut pas permission permanente d'utiliser la coordonnée pour des finalités nouvelles ou sans rapport.
- Pour une transaction/service actif, le retrait ne doit pas empêcher commande, livraison, réservation, retour, réclamation, litige ou garantie ; Connecte+ peut informer que le canal a changé et orienter vers la messagerie ou un nouveau contact.
- Le journal Q8 conserve la trace de l'accès et de la modification/retrait.
- Retirer un numéro professionnel public signifie cesser de l'afficher ; Connecte+ ne peut garantir la disparition des copies déjà faites par des tiers.

**Note :** ⚖️ À valider juridiquement.

#### Q10. Listes des numéros communiqués

*Réf. LEG-PRV-04 b — Question d'origine : Le vendeur peut-il demander la liste des personnes ayant obtenu son numéro ? Le visiteur peut-il demander la liste des numéros obtenus ?*

> **VALIDÉE / VERROUILLÉE** — Le vendeur dispose du journal contrôlé Q8. Le visiteur ne reçoit pas un carnet permanent de numéros privés ; Connecte+ privilégie les Favoris/Contacts basés sur les profils.

**Décisions et exigences**

- Créer « Mes contacts / Favoris Connecte+ » permettant d'enregistrer un profil, une organisation ou un prestataire, pas une copie permanente du numéro privé.
- Depuis un favori, l'utilisateur retrouve le profil, les offres actuelles, la messagerie et les canaux actuellement autorisés.
- Si un numéro personnel est retiré, il disparaît des canaux proposés, mais le profil peut rester favori sauf blocage/suppression/restriction.
- Un vendeur peut toujours communiquer volontairement son numéro dans une conversation.
- Les anciens numéros professionnels ne sont pas conservés comme historique de carnet d'adresses.
- Parcours privilégié : Profil/Contact Connecte+ → Messagerie Connecte+ → canaux actuellement autorisés → numéro personnel uniquement si nécessaire ou volontaire.

**Note :** ⚖️ À valider pour les droits d'accès et de suppression.

#### Q11. Adresse IP et lutte contre la copie automatique

*Réf. LEG-PRV-09 — Question d'origine : La plateforme peut-elle conserver l'adresse IP ou une version brouillée pour empêcher la collecte automatique ? Pendant combien de temps ?*

> **VALIDÉE / VERROUILLÉE** — Oui, des signaux techniques peuvent être utilisés temporairement et de manière proportionnée pour détecter/limiter le scraping, sans archive permanente de toutes les IP complètes.

**Décisions et exigences**

- Utiliser si nécessaire IP complète temporaire, version minimisée/tronquée/pseudonymisée ou signal dérivé, selon la finalité.
- Ne jamais considérer l'IP seule comme preuve d'identité ou de fraude.
- Combiner fréquence de requêtes, nombre de coordonnées consultées, vitesse d'action, session, compte, appareil et signaux réseau.
- Réponse progressive : limitation/délai → réauthentification/CAPTCHA → restriction temporaire d'accès aux coordonnées → alerte sécurité.
- Pas de sanction permanente automatique sur une simple anomalie ; cas importants/ambigus soumis à examen humain autorisé.
- Les restrictions significatives doivent être traçables et auditables. Durées proposées par l'équipe technique et configurables.

**Note :** ⚙️ Proposition technique + ⚖️ validation juridique requises.

#### Q12. Usage commercial des numéros

*Réf. LEG-PRV-11 — Question d'origine : Une personne qui obtient un numéro peut-elle l'utiliser pour du démarchage commercial ? Faut-il afficher un rappel ?*

> **VALIDÉE / VERROUILLÉE** — Non : une coordonnée protégée communiquée pour une interaction donnée ne doit pas être réutilisée pour du démarchage commercial non sollicité sans base/accord distinct.

**Décisions et exigences**

- Afficher un rappel contextuel : « Ces coordonnées vous sont communiquées uniquement dans le cadre de cette interaction. Elles ne doivent pas être utilisées pour du démarchage commercial non sollicité. Pour promouvoir une entreprise, un produit, un service ou une nouvelle activité, utilisez les outils de publication et de promotion proposés par Connecte+. »
- Un opt-in marketing séparé et explicite pourra exister.
- Un numéro professionnel public n'est pas une liste marketing librement exploitable.
- Le spam répété est signalable et peut entraîner des restrictions progressives après vérification.
- Favori ≠ consentement marketing. Transaction ≠ consentement marketing. Obtention d'un numéro ≠ constitution d'une liste marketing.
- Les notifications promotionnelles volontaires doivent être gérées par la plateforme ; le vendeur ne reçoit pas automatiquement la liste des téléphones/e-mails des personnes intéressées.
- Distinguer Favori (unilatéral/privé) et Partenariat professionnel (bilatéral/explicite/structuré).

**Note :** ⚖️ Validation juridique du démarchage et des consentements.

#### Q13. WhatsApp et transfert du numéro

*Réf. LEG-PRV-12 / 06 — Question d'origine : Quand l'utilisateur ouvre un lien WhatsApp, faut-il l'informer ? Existe-t-il une règle sur l'envoi de données hors de la RDC ?*

> **VALIDÉE / VERROUILLÉE** — La messagerie Connecte+ est le canal interne principal. WhatsApp et autres services externes restent optionnels et doivent être accompagnés d'une information contextuelle avant la sortie de Connecte+.

**Décisions et exigences**

- Message recommandé : « Vous allez quitter Connecte+ et ouvrir WhatsApp, un service externe. Les données traitées par WhatsApp sont soumises aux conditions et à la politique de confidentialité de ce service. » Bouton : « Continuer vers WhatsApp ».
- La messagerie Connecte+ doit être un moteur contextuel réutilisable : Marketplace, Services, Recrutement, Restaurants, Événements, collaboration professionnelle et Support.
- Dans une conversation Marketplace, afficher le contexte utile : produit, vendeur, commande, statut, livraison/paiement et actions pertinentes.
- Distinguer notifications de messages directs, alertes génériques, promotions et mises à jour de commande.
- Le backend doit modéliser un canal de communication externe générique, pas coder WhatsApp comme unique solution.
- L'équipe doit vérifier le flux réel de données Meta/WhatsApp avant toute affirmation technique et documenter les tiers, données, finalités et mécanismes de transfert international.

**Note :** ⚖️ Validation juridique + ⚙️ validation technique Meta/WhatsApp.

#### Q14. Le modérateur peut-il voir le numéro ?

*Réf. LEG-PRV-01 c — Question d'origine : En cas de litige sur un avis signalé comme « contact fictif », le modérateur peut-il voir le numéro du vendeur et le canal utilisé ?*

> **VALIDÉE / VERROUILLÉE** — Le modérateur ordinaire ne voit pas automatiquement le numéro privé complet. L'accès dépend de la fonction, de la finalité et de la nécessité.

**Décisions et exigences**

- Privilégier les preuves factuelles minimisées : accès à une coordonnée protégée oui/non, date/heure, canal, annonce, conversation Connecte+, commande/devis/réservation, etc., avec numéro masqué.
- Distinguer les niveaux de preuve : voir un numéro ≠ converser ; ouvrir WhatsApp ≠ envoyer un message ; messages ≠ transaction ; commande créée ≠ exécutée.
- Accès exceptionnel à une donnée sensible : fonction spécialement autorisée, motif, dossier/case ID, authentification renforcée, approbation si nécessaire et audit.
- Séparer accès interne autorisé et communication externe à une autorité/tiers.
- Généraliser le principe aux pièces d'identité, adresses, paiements, documents de vérification, recrutement, conversations privées et données scolaires/mineurs.
- Les développeurs/administrateurs techniques n'ont pas un accès illimité par défaut aux données de production.

**Note :** ⚙️ Permissions granulaires + ⚖️ validation juridique.

#### Q15. Conservation des avis et des réponses

*Réf. LEG-PRV-05 b — Question d'origine : Combien de temps conserver les avis et réponses, y compris masqués ? Que faire si l'auteur demande la suppression ?*

> **VALIDÉE / VERROUILLÉE** — Distinguer visibilité publique, conservation technique et suppression. Un avis publié peut rester tant qu'il demeure légitimement pertinent, mais son auteur doit pouvoir le modifier, l'actualiser ou le supprimer.

**Décisions et exigences**

- Le motif de suppression peut être demandé pour comprendre le contexte, sans bloquer une suppression ordinaire : expérience modifiée, correction, problème résolu, publication non autorisée, données personnelles, pression/coercition, avis ne correspondant pas à l'expérience, autre.
- Si l'expérience change, proposer éventuellement Mettre à jour ou Supprimer ; un avis peut être marqué comme actualisé par son auteur.
- Publication non autorisée : retirer et proposer des contrôles de sécurité, sans conclure automatiquement à un piratage.
- Pression/coercition : permettre un signalement confidentiel distinct ; la suppression de l'avis n'efface pas le signalement.
- Données personnelles : correction/retrait rapide.
- Avis masqué/modéré : retrait public immédiat, copie restreinte uniquement pendant la durée justifiée pour appel, modération, fraude, sécurité, litige ou obligation légale.
- Les réponses suivent la visibilité de l'avis parent. Les raisons de suppression sont elles-mêmes des données et doivent être minimisées/retirées selon politique configurable.

**Note :** ⚖️ Durées et obligations à valider juridiquement.

#### Q16. Conservation après sanction ou suppression de compte

*Réf. LEG-PRV sanctions — Question d'origine : Combien de temps conserver sanctions, signalements et avis après suppression ? Peut-on garder un identifiant brouillé des comptes bannis ?*

> **VALIDÉE / VERROUILLÉE** — Suppression du compte, suppression des données, anonymisation et fin d'une sanction sont des notions distinctes. Refus de conserver tout indéfiniment.

**Décisions et exigences**

- Suppression volontaire ordinaire : suppression/dissociation/anonymisation progressive par catégorie, sous réserve des transactions, litiges, comptabilité, sécurité et obligations légales.
- La sanction est un objet distinct du compte : catégorie, gravité, motif, date, durée/statut, références de preuve, appel et résultat, audit.
- Pour empêcher le retour après une sanction qui le justifie, conserver le minimum nécessaire pendant une durée appropriée ; privilégier un identifiant anti-abus sécurisé/dérivé/pseudonymisé plutôt que le document d'identité complet.
- Une correspondance technique n'est jamais une preuve : IP/appareil/famille/réseau/numéro recyclé peuvent produire des faux positifs. Utiliser plusieurs signaux et examen humain pour les cas importants/ambigus.
- Un avis légitime peut rester après suppression du compte sous forme dissociée, par exemple « Ancien utilisateur Connecte+ ». Une sanction sans lien avec l'avis ne l'invalide pas automatiquement.
- Les signalements et preuves nécessaires à une enquête active suivent leur propre cycle de conservation.
- Les durées restent configurables ; legal hold possible.

**Note :** À détailler dans la future Matrice Sanctions, Modération & Enforcement. ⚖️

#### Q17. Organisation suspendue sans propriétaire

*Réf. LEG-PRV orpheline — Question d'origine : Que faire d'une organisation suspendue dont plus personne n'est propriétaire ?*

> **VALIDÉE / VERROUILLÉE** — L'organisation est un objet distinct des personnes qui l'administrent. La perte du dernier Administrateur principal ne supprime ni ne condamne automatiquement l'organisation.

**Décisions et exigences**

- Statuts séparés : compte humain, autorité de la personne dans l'organisation, état administratif de l'organisation et sanctions de l'organisation.
- Si le dernier Administrateur principal disparaît : état « Organisation sans administrateur principal / administration à régulariser ». L'organisation peut être simultanément suspendue et orpheline.
- Aucun éditeur, analyste ou employé n'est promu automatiquement.
- Récupération formelle : identité, existence de l'organisation, autorité actuelle et justificatifs adaptés.
- Si la suspension est indépendante de la perte de l'administrateur, le remplacement de l'administrateur ne l'annule pas.
- Un changement réel de direction/contrôle accompagné de mesures correctives peut justifier un réexamen, jamais une réactivation automatique.
- Les sanctions de la personne et de l'organisation sont distinctes ; les sanctions de l'organisation ne s'étendent pas automatiquement à tous ses membres.
- Si aucune représentation n'est rétablie, l'organisation peut être restreinte puis archivée selon son cycle de vie.

**Note :** Ajouter un volet « Remédiation et réintégration organisationnelle » à la matrice d'enforcement.

#### Q18. Table de correspondance des anciens comptes entreprise

*Réf. LEG-PRV mapping — Question d'origine : Combien de temps conserver le tableau reliant les anciens comptes entreprise aux nouvelles organisations ?*

> **VALIDÉE / VERROUILLÉE** — Le mapping legacy est un outil temporaire de migration/réconciliation, pas une donnée à conserver jusqu'à une vague « fin de projet ».

**Décisions et exigences**

- Le conserver pendant migration → vérification/réconciliation → correction des anomalies → récupération des anciens responsables → période raisonnable de support/contestation → clôture formelle de migration.
- Il sert aux doublons, mauvaises attributions, données manquantes, plaintes d'anciens responsables, provenance et récupération.
- Après la période détaillée, une provenance/audit minimale peut être conservée plus longtemps si justifié.
- Accès restreint ; consultations/modifications sensibles journalisées.
- La durée exacte doit être proposée par l'équipe technique, configurable et juridiquement validée ; prévoir suppression/minimisation planifiée.

**Note :** ⚙️ + ⚖️

#### Q19. Contact du support dans l'application

*Réf. Q-SUSP1 — Question d'origine : Quel moyen de contact du support afficher dans l'application ?*

> **VALIDÉE / VERROUILLÉE** — Créer une véritable architecture Aide et Support ; ne pas livrer un simple texte « contactez le support » sans lien fonctionnel.

**Décisions et exigences**

- Point d'entrée principal : Aide et Support dans l'application.
- Parcours : catégorie du problème → questions/diagnostic → réponse ou procédure en libre-service → « problème résolu ? » → intervention humaine si nécessaire.
- Un cas humain crée un ticket structuré : numéro de dossier, catégorie, date, compte/organisation/objet concerné, messages, pièces jointes, statut, équipe responsable, historique et résolution.
- Messagerie de support intégrée privilégiée lorsque l'utilisateur peut se connecter.
- Prévoir obligatoirement un canal externe sans authentification pour perte d'accès, panne, récupération ou restriction : page/formulaire officiel et/ou e-mail.
- Téléphone/WhatsApp ne sont pas le canal principal ; s'ils existent, utiliser un canal professionnel officiel, jamais le numéro personnel d'un employé.
- Au moins un canal de support réellement fonctionnel doit exister avant lancement ; coordonnées configurables, pas codées en dur.

**Note :** À développer ensuite dans l'architecture Help, Support & Case Management.

#### Q20. Prévenir les propriétaires des anciens comptes entreprise

*Réf. Q-SUSP5 — Question d'origine : Les anciens comptes entreprise convertis en organisations suspendues doivent-ils être prévenus par SMS ou e-mail ?*

> **VALIDÉE / VERROUILLÉE** — Oui, mais comme parcours d'information, récupération et régularisation — pas comme un message externe unique et opaque.

**Décisions et exigences**

- Expliquer la migration, l'organisation correspondante, la raison de la régularisation, les actions à effectuer, la récupération/vérification et le support.
- Utiliser les anciens canaux fiables : e-mail et/ou SMS ; les deux lorsque justifié. Minimiser les informations sensibles dans les messages externes.
- Contrôle de l'ancien e-mail/téléphone ≠ identité vérifiée ≠ autorité actuelle vérifiée.
- Séquence limitée : notification initiale → rappel si aucune action → éventuellement rappel final avant changement important de statut/période. Arrêt après résolution ou fin de finalité.
- Ajouter une notification in-app de migration.
- Parcours : notification → explication → récupération/régularisation → vérification → restauration des droits si conditions remplies.
- Créer à terme un Centre d'aide et de règles avec articles compréhensibles ; les contenus doivent être centralisés, versionnés et non codés en dur.

**Note :** ⚖️ Conservation et contenu des notifications à valider.

---

### PARTIE 3 — À confirmer : rôles, vérification, publication, avis et cycle de vie

#### Q21. Les quatre rôles suffisent-ils ?

*Réf. Q-CLI1 — Question d'origine : Les 4 rôles propriétaire, administrateur, éditeur, analyste suffisent-ils ? Branches/départements exclus ? Plusieurs propriétaires ?*

> **VALIDÉE / VERROUILLÉE** — Ne pas figer l'architecture autour de quatre rôles ni du concept de « propriétaire » de plateforme. Utiliser Rôle → Permissions → Périmètre.

**Décisions et exigences**

- Rôles V1 simples possibles : Administrateur principal, Administrateur, Éditeur/Gestionnaire, Analyste ; libellés à affiner.
- Modèle : Utilisateur → Organisation → Membership/RoleAssignment → Permissions → Scope, avec délégation, révocation, expiration, vérification d'autorité et audit selon besoin.
- Branches, établissements et départements ne doivent pas être exclus du modèle technique. L'UI avancée peut être progressive, mais les permissions doivent pouvoir être limitées par agence/site/branche/département/module/objet.
- Exemples : responsable Lubumbashi uniquement ; recrutement à l'échelle organisation ; Marketplace Kinshasa uniquement.
- Pas de « plusieurs propriétaires ». Une organisation peut avoir plusieurs administrateurs ; l'autorité supérieure passe par un ou plusieurs Administrateurs principaux dûment autorisés lorsque la gouvernance le permet.
- Les actions sensibles peuvent nécessiter authentification renforcée, revérification ou double contrôle.
- L'architecture doit permettre ultérieurement des rôles personnalisés/granulaires sans exiger un constructeur complexe en V1.

**Note :** Critères d'acceptation : pas d'auto-escalade ; perte d'un admin ≠ perte de l'organisation ; changements d'autorité sensibles auditables.

#### Q22. Nombre d'organisations par compte

*Réf. Q-CLI4 — Question d'origine : Combien d'organisations une même personne peut-elle avoir ? Une seule au lancement ? Faut-il afficher un plafond ?*

> **VALIDÉE / VERROUILLÉE** — Refus d'un plafond global arbitraire de 10 organisations actives par compte.

**Décisions et exigences**

- Une même personne peut légitimement créer, administrer, représenter ou simplement rejoindre plusieurs organisations sans multiplier ses comptes personnels.
- Distinguer organisations créées, organisations où la personne est Administrateur principal, administrateur délégué ou simple membre.
- Pas de plafond universel bas ; appliquer plutôt des protections anti-abus contre création massive/rapide/automatisée, usurpation, organisations fictives et contournement de sanctions.
- Utiliser rate limits, vérifications, signaux de risque et examen humain. Un grand nombre de relations peut être un signal, jamais une preuve de fraude.
- Ne pas afficher de seuil technique exploitable comme limite commerciale si ce seuil sert uniquement à la sécurité.

**Note :** Principe : plusieurs relations légitimes, contrôles proportionnés au niveau d'autorité et au risque.

#### Q23. Rôle donné par une invitation

*Réf. Q-L1-3 — Question d'origine : Une invitation peut-elle donner le rôle d'administrateur ?*

> **VALIDÉE / VERROUILLÉE** — Oui, une invitation peut attribuer différents rôles/permissions/périmètres si l'émetteur est autorisé à les déléguer. « Simple membre » est un type d'invitation, pas la règle universelle.

**Décisions et exigences**

- Invitation possible comme simple membre, Éditeur/Gestionnaire, Analyste ou Administrateur selon droits de l'émetteur.
- Une personne ne peut pas déléguer des droits qu'elle n'est pas autorisée à déléguer ; un admin limité à une branche ne peut pas créer un admin global sans autorisation.
- Le rôle Administrateur principal ne doit pas être accordé par une invitation ordinaire : procédure renforcée Q3/Q17/Q21.
- Avant acceptation, le destinataire voit l'émetteur, l'organisation, le rôle proposé, le périmètre et les accès ; il peut accepter ou refuser.
- Tracer invitation, émetteur, rôle, scope, acceptation/refus et droits finaux.
- Exemple : Amina, Administratrice principale de Société XYZ, invite Patrick comme Administrateur des activités commerciales — Kinshasa, avec produits/commandes/messages clients, sans droits de gouvernance principale.

#### Q24. Suppression de son compte par l'utilisateur

*Réf. Q-L1-10 — Question d'origine : L'utilisateur doit-il pouvoir supprimer lui-même son compte dans la première version ?*

> **VALIDÉE / VERROUILLÉE** — Oui. La suppression en libre-service doit exister en V1, mais elle déclenche un processus contrôlé de fermeture et non une destruction immédiate et inconditionnelle.

**Décisions et exigences**

- Compte sans obligations non résolues : fermeture puis suppression/anonymisation/dissociation selon Q4/Q16.
- Transaction, paiement, remboursement, livraison, plainte ou litige actif : demande enregistrée, fermeture complète différée/adaptée ; état « fermeture en cours » avec accès minimal nécessaire.
- Dernier Administrateur principal : avertir et demander régularisation de la gouvernance lorsque possible ; mécanisme d'organisation orpheline Q17 sinon.
- Sanction/enquête : l'utilisateur peut quitter la plateforme, mais ne peut pas effacer sanction/preuves ni contourner une exclusion.
- Conserver uniquement les données justifiées par obligations légales/comptables/sécurité, pas l'ensemble du compte indéfiniment.
- Avis conservé après suppression : dissociation possible (« Ancien utilisateur Connecte+ »), sous réserve du droit de suppression de l'avis Q15.
- Cycle : Actif → demande de fermeture → contrôles → fermeture ou attente/régularisation → résolution → fermeture finale.

**Note :** ⚖️ Politique de conservation à valider.

#### Q25. Liste des noms réservés

*Réf. Q-L1-11 — Question d'origine : Qui fournit la liste de départ des noms réservés ?*

> **VALIDÉE / VERROUILLÉE** — Démarrer la V1 avec une liste ciblée de noms protégés/réservés, configurable et administrable, sans prétendre couvrir toutes les organisations de RDC.

**Décisions et exigences**

- Priorités : institutions/administrations publiques, grandes banques et institutions financières, télécoms/Mobile Money, grands services publics et entités à fort risque d'usurpation.
- Nom protégé ≠ interdit : il déclenche une vérification renforcée avant représentation publique.
- Vérifier existence → identité → autorité. Détecter variantes de casse, ponctuation, espaces, orthographe, alias et similarités trompeuses comme signaux de revue, jamais comme preuve.
- La liste ne remplace pas les documents, l'existence juridique ou l'autorité du représentant.
- Lorsque possible, croiser RCCM, Identification Nationale, NIF, reconnaissance ONG/ASBL, licences/agréments avec une source officielle/administration compétente.
- L'équipe doit étudier les canaux réels en RDC (GUCE/RCCM, Identification Nationale, DGI/NIF, autorités ONG/ASBL) sans supposer qu'une API publique existe.
- Liste gérée en back-office avec audit.

**Note :** Nom protégé ≠ Organisation vérifiée ≠ Représentant vérifié ≠ Autorité vérifiée. ⚙️ + ⚖️

#### Q26. Qui décide d'une revendication ?

*Réf. Q-L1-12 — Question d'origine : La décision est-elle prise par l'équipe de vérification, ou par un autre groupe ?*

> **VALIDÉE / VERROUILLÉE** — Les dossiers standards sont décidés par une fonction/équipe de vérification autorisée ; les dossiers ambigus, conflictuels ou à risque élevé sont escaladés et peuvent exiger un second contrôle.

**Décisions et exigences**

- Cas d'escalade : plusieurs demandeurs, documents contradictoires, mandat contesté/révoqué, conflit d'administrateurs, nom protégé/organisation à risque, usurpation, organisation sous restriction pertinente.
- Le modérateur ordinaire ne décide pas de l'autorité organisationnelle ; il peut signaler, prendre une mesure conservatoire dans son périmètre et référer le dossier.
- Connecte+ n'est pas un tribunal : un véritable conflit juridique de propriété/représentation peut rester en attente/restreint jusqu'à preuve ou décision d'une autorité compétente.
- Audit : organisation, demandeur, date, preuves, sources/méthodes, décision, fonction/reviewer, second contrôle/escalade, motif et réexamen ultérieur.
- Distinguer inscription, création/configuration du profil, vérification de l'organisation, vérification de l'autorité et revendication/récupération.
- Niveaux : standard à faible risque avec vérification progressive et hypothèse de grâce configurable de 90 jours ; renforcé pour activités sensibles/réglementées ; pré-vérification obligatoire pour banques, finance, paiement/Mobile Money, télécoms, ministères et grandes entités publiques.
- Les réseaux sociaux/sites servent de corroboration éventuelle, jamais de preuve suffisante d'existence ou d'autorité. L'onboarding assisté ne doit pas permettre à l'équipe commerciale de valider elle-même la vérification.

**Note :** La période de 90 jours est une hypothèse V1 configurable, à confirmer juridiquement et opérationnellement.

#### Q27. Documents demandés selon le type d'organisation

*Réf. Q-CLI2 — Question d'origine : Quels documents exiger selon entreprise, boutique informelle, ONG, organisateur ? Une organisation non vérifiée peut-elle publier ?*

> **VALIDÉE / VERROUILLÉE** — Utiliser une matrice documentaire progressive selon type d'acteur, forme juridique, activité, niveau de vérification et réglementation du secteur — pas une liste plate identique pour tous.

**Décisions et exigences**

- Particulier ordinaire : pas de RCCM simplement pour participer.
- Acteur économique/professionnel indépendant informel : peut opérer sans se présenter comme société ; vérifier l'identité lorsque l'activité professionnelle publique le justifie ; licence/autorisation séparée si activité réglementée.
- Organisation formelle : existence juridique + identité + représentant + autorité, avec RCCM/Identification Nationale/NIF ou autres pièces selon applicabilité.
- ASBL/ONG : parcours distinct adapté à leur régime.
- Activité réglementée : documents de forme + licence/agrément/autorisation sectorielle.
- Noms protégés/haut risque : vérification renforcée ou préalable selon Q26.
- La pièce d'identité du représentant ne suffit jamais seule à prouver son autorité.
- Vendeur en ligne sans local public : supporter l'identité, l'activité, le mode d'exploitation et la livraison sans imposer la publication du domicile.
- UX progressive et non stigmatisante ; la complexité doit être portée par le système/back-office, pas par l'utilisateur.

**Note :** La matrice documentaire doit être configurable et validée selon le droit/réglementation RDC.

#### Q28. Ce que peut publier un particulier

*Réf. Q-CLI3 — Question d'origine : Un compte personnel peut-il publier uniquement des objets d'occasion, ou aussi des services ?*

> **VALIDÉE / VERROUILLÉE** — Un même compte humain peut agir dans plusieurs contextes. Le Particulier Free reste utile, mais certaines publications nécessitent un Pass ou Premium et les activités professionnelles récurrentes utilisent un contexte professionnel.

**Décisions et exigences**

- Particulier Free : acheter, demander devis, réserver, postuler à un emploi, participer à des événements, favoris, messagerie, etc.
- Vente Marketplace personnelle : Marketplace Selling Pass ; incluse dans Particulier Premium.
- Recrutement domestique/privé : Recruitment Pass ; inclus Premium.
- Création d'événement éligible : Event Pass ; incluse Premium.
- Publication de location de son propre bien immobilier : Property Rental Pass ; incluse Premium.
- Particulier Free : maximum de travail V1 de 10 activations de Pass éligibles au total sur 12 mois glissants ; les promotions ne comptent pas. Paramètres/prix configurables. Hypothèse Premium : environ 50 USD/an, non finale.
- Recherche/candidature emploi gratuite.
- Particulier Premium ≠ Professionnel. Une activité commerciale récurrente ou prestation professionnelle publique passe par le contexte Prestataire/Professionnel, sans nouveau login.
- Occasionnel/personnel vs professionnel/récurrent est plus important que neuf/occasion ; l'état du produit reste un attribut séparé.
- « + Publier » doit être contextuel : Contexte actif → type d'activité → éligibilité → permission → entitlement/pass → règles de catégorie → publication.

**Note :** Rappeler dans les spécifications les contextes : Visiteur, Particulier, Premium, Prestataire, Employeur particulier, Organisation, Membre/Admin/Administrateur principal, Représentant autorisé, Staff.

| Capacité du Particulier | Free | Pass requis | Premium |
|---|---|---|---|
| Acheter, devis, réserver, favoris, messagerie, événements | Oui | — | Oui |
| Recherche et candidature emploi | Oui (gratuit) | — | Oui |
| Vente Marketplace personnelle | Avec pass | Marketplace Selling Pass | Inclus |
| Recrutement domestique/privé | Avec pass | Recruitment Pass | Inclus |
| Création d'événement éligible | Avec pass | Event Pass | Inclus |
| Location de son propre bien immobilier | Avec pass | Property Rental Pass | Inclus |
| Plafond Free | 10 activations de Pass sur 12 mois glissants (promotions exclues) — configurable | | |

*(Tableau de synthèse ajouté pour lecture ; il reprend uniquement les éléments de Q28.)*

#### Q29. Prestataires de services

*Réf. Q-CLI7 — Question d'origine : Un prestataire peut-il publier sans vérification d'identité ? Certaines catégories demandent-elles une vérification renforcée ?*

> **VALIDÉE / VERROUILLÉE** — La vérification est progressive et proportionnée au risque. Authentification, identité, qualification, licence/autorisation et réputation restent séparées.

**Décisions et exigences**

- Prestataire ordinaire non réglementé : onboarding progressif ; identité vérifiée lorsque la capacité professionnelle publique pertinente est activée.
- Activités à conséquences élevées peuvent recevoir des contrôles de plateforme même si elles ne sont pas juridiquement réglementées ; classification de risque ≠ qualification légale de profession réglementée.
- Activité réglementée/sensible : identité seule insuffisante ; vérifier qualification/statut/licence/inscription/autorisation et validité avant activation publique lorsque applicable.
- Badges factuels seulement : « Identité vérifiée », « Qualification professionnelle vérifiée », « Autorisation professionnelle vérifiée ». Ne pas afficher « Coach vérifié » si seule l'identité est contrôlée.
- Interdire le contournement par choix d'une catégorie moins risquée ou description trompeuse de l'activité réelle.
- Confiance continue : Avant → Pendant → Après. Après une interaction éligible, questionnaire privé distinct de l'avis public : « Le service réellement fourni correspondait-il au service présenté sur Connecte+ ? Oui / En partie / Non ». Branches factuelles si écart.
- Signalement permanent disponible. Un signalement ≠ culpabilité ; combiner gravité, preuves, répétition, rapports indépendants, contexte/historique ; protection urgente possible si risque sérieux, puis examen humain.
- Mesures possibles : information/correction/reclassification/vérification supplémentaire/licence/restriction temporaire/retrait d'offre/sanction.
- Matrice configurable : acteur → activité → sous-catégorie → risque → identité → vérification renforcée → qualification → licence → source → visibilité avant vérification → capacités → validité → revérification → indicateur public.

**Note :** Exigence : contrôle continu de la conformité entre activité déclarée et activité réellement exercée. ⚖️

#### Q30. Qui accepte de partager le numéro d'une organisation ?

*Réf. Q-CLI5 — Question d'origine : Qui donne l'accord pour communiquer le numéro de contact d'une organisation : propriétaire seul ou administrateur ? Quel texte afficher ?*

> **VALIDÉE / VERROUILLÉE** — L'organisation détermine, selon sa gouvernance, qui est autorisé ; Connecte+ traduit cette autorité en rôles, permissions et périmètres. Ni « propriétaire seul » ni « tous les administrateurs ».

**Décisions et exigences**

- Chaîne : Organisation → autorité compétente → mandat/délégation si nécessaire → Administrateur principal/admin autorisé → invitation/attribution → rôle + permissions + scope → action autorisée.
- La coordonnée appartient au profil de l'organisation ; le droit de la gérer appartient à une personne autorisée. Révoquer cette personne ne supprime pas automatiquement la coordonnée de l'organisation.
- Distinguer numéro professionnel/public, numéro personnel d'un membre, numéro d'authentification/récupération, destination de paiement et contact transactionnel.
- Texte recommandé : « Vous êtes sur le point d'utiliser ce numéro comme coordonnée professionnelle de [Nom de l'organisation]. Confirmez que vous êtes autorisé(e) à gérer cette coordonnée pour l'organisation et vérifiez ses paramètres de visibilité avant sa publication. »
- Une modification sensible (contact principal établi, e-mail officiel, domaine, compte externe officiel, Administrateur principal, délégation importante, identité légale vérifiée, compte de règlement) peut nécessiter authentification renforcée, motif, preuve d'autorité, double contrôle et notifications.
- Principe maker-checker : l'initiateur ne doit pas être l'unique approbateur de sa propre demande sensible. Notifier via l'ancien canal de confiance lorsque pertinent.
- Audit : demandeur, date, contexte, permission, ancienne/nouvelle valeur, autorité, validateur, résultat.

**Note :** Réutiliser la future Matrice des modifications organisationnelles sensibles. ⚖️

#### Q31. Affichage du nom de l'auteur d'un avis

*Réf. LEG-PRV-01 d / D11 — Question d'origine : Sous quelle forme afficher le nom de l'auteur : nom complet, prénom + initiale, ou pseudo ?*

> **VALIDÉE / VERROUILLÉE** — Afficher « Prénom + initiale du nom » (ex. Marie K.) accompagné de l'image de profil publique actuelle ou d'un avatar, sans exposer automatiquement l'identité légale complète.

**Décisions et exigences**

- Identité publique ≠ identité interne du compte ≠ identité légale vérifiée. L'avis reste relié en interne à un compte unique pour traçabilité/modération/édition/suppression/abus.
- Ajouter un indicateur factuel d'interaction lorsqu'il est établi : « Achat effectué via Connecte+ », « Prestation réservée via Connecte+ », etc. Cela ne garantit pas la véracité de toutes les affirmations de l'avis.
- Pas de pseudonyme libre comme règle standard V1 ; des contextes particuliers de confidentialité pourront être étudiés plus tard.
- Afficher l'image/Avatar public actuel choisi par l'utilisateur : photo personnelle, fleur, illustration, image symbolique ou avatar plateforme, sous réserve des règles de contenu.
- Si l'image de profil change, les anciens avis montrent la nouvelle image actuelle ; l'avis ne conserve pas une copie figée indépendante.
- Jamais utiliser automatiquement selfie de vérification, photo de pièce d'identité ou image privée de vérification comme avatar public.
- Sans image : avatar par défaut/initiales. Après suppression du compte si l'avis est conservé : avatar générique + « Ancien utilisateur Connecte+ ».

#### Q32. Moins de 3 avis

*Réf. D3 — Question d'origine : Sous 3 avis, faut-il cacher seulement la note moyenne ou aussi les avis eux-mêmes ?*

> **VALIDÉE / VERROUILLÉE** — Cacher uniquement la moyenne agrégée tant qu'il y a moins de 3 avis éligibles ; les avis individuels et leur propre note en étoiles restent visibles.

**Décisions et exigences**

| Nombre d'avis éligibles | Affichage |
|---|---|
| 0 | « Pas encore d'avis » |
| 1 | « 1 avis » ; avis individuel + sa note visibles ; aucune moyenne globale |
| 2 | « 2 avis » ; les deux avis + leurs notes visibles ; aucune moyenne globale |
| 3 ou plus | Moyenne globale + nombre d'avis + avis individuels et notes respectives |

- Option d'information : « La note moyenne est affichée à partir de 3 avis. »
- Le seuil se calcule sur les avis publiés éligibles ; avis supprimés, invalidés ou exclus par modération ne doivent pas gonfler le compteur ni la moyenne.
- Éviter les affichages trompeurs du type « —/5 » lorsque la moyenne n'est pas encore publiée.

#### Q33. Motif de suspension visible

*Réf. Q-SUSP2 — Question d'origine : Le propriétaire et les administrateurs doivent-ils voir la catégorie du motif de suspension de leur organisation ?*

> **VALIDÉE / VERROUILLÉE** — Oui. Les administrateurs/représentants autorisés doivent normalement voir au minimum la catégorie, une explication compréhensible, le périmètre affecté et l'action/recours disponible, sans exposer nécessairement toutes les preuves internes.

**Décisions et exigences**

- Modèle : Catégorie → motif communiqué → périmètre affecté → mesure/statut → action disponible → recours → preuves internes → historique/audit.
- Catégories illustratives, configurables et non exhaustives :
  1. Vérification et identité ;
  2. Sécurité et intégrité ;
  3. Publication/contenu ;
  4. Activités commerciales/Marketplace/services ;
  5. Paiements/transactions/risques financiers ;
  6. Recrutement/prestations/activités réglementées ;
  7. Confiance/fraude/usurpation/comportement abusif.
- Un simple échec de paiement ne déclenche pas automatiquement une suspension.
- Séparer suspension totale et restriction ciblée : publication, fonction, module, activité, branche, permission ou organisation entière selon gravité.
- Sécurité/confidentialité/enquête : les détails peuvent être limités pour protéger méthodes, tiers ou investigation, mais fournir une catégorie utile et la prochaine action lorsque raisonnablement possible.
- UI souhaitée : Statut, Catégorie, Motif, Périmètre affecté, Depuis, Action requise, Recours/réexamen si disponible.
- L'accès au dossier dépend des permissions ; un membre ordinaire ne voit pas automatiquement les éléments sensibles.

**Note :** La taxonomie définitive appartient à la future Matrice Sanctions, Modération & Enforcement. ⚖️

#### Q34. Restaurer une organisation archivée

*Réf. Q-SUSP3 — Question d'origine : Le support peut-il restaurer une organisation archivée ?*

> **VALIDÉE / VERROUILLÉE** — Modifier la proposition par défaut : une organisation archivée n'est pas réactivée par un simple bouton de support, mais une restauration exceptionnelle, contrôlée et auditée peut être possible tant que les données nécessaires existent.

**Décisions et exigences**

- Cycle de vie : Active → Inactive/dormante → Fermeture en cours → Archivée → Supprimée/anonymisée.
- Une longue inactivité conduit à Inactive/Dormante, pas à Archivée. L'organisation inactive peut revenir normalement, avec revérification si informations expirées.
- Archivée = présence opérationnelle fermée ; données historiques nécessaires conservées selon politique de rétention. Archivage ≠ suspension ≠ exclusion permanente ≠ suppression.
- Les sanctions et le cycle de vie opérationnel restent séparés.
- Restauration exceptionnelle : erreur d'archivage, erreur technique/administrative, fermeture sans autorité valable, contestation légitime ou autre cas justifié.
- Parcours : demande → motif d'archivage → vérifier que les données existent → vérifier organisation/représentant/autorité actuels → vérifier sanctions/restrictions → revérification si nécessaire → décision autorisée → restaurer/refuser.
- Si restauration approuvée, restaurer le même objet Organisation et conserver l'historique ; ne pas créer un doublon. Revérifier admins, délégations, contacts, licences, destinations de paiement si nécessaire.
- Tracer archivage/restauration : dates, motifs, demandeur, preuves, contrôles, décideur, résultat.
- Après suppression ou anonymisation irréversible, restauration impossible ; une nouvelle inscription éventuelle est une nouvelle création, pas une restauration.

**Note :** ⚖️ Règles de rétention et effets de fermeture à valider.

#### Q35. Nom non modifiable après validation

*Réf. A13 — Question d'origine : Dès qu'un document est validé, le nom de l'organisation ne peut plus être modifié. Acceptez-vous cette règle ?*

> **VALIDÉE / VERROUILLÉE** — Le nom vérifié est verrouillé contre l'édition ordinaire, mais il n'est pas définitivement immuable. Prévoir une procédure contrôlée de correction/changement, et distinguer clairement changement de nom d'une même entité et création d'une nouvelle entité.

**Décisions et exigences**

- Modèle de données : dénomination légale/enregistrée ; nom commercial/d'affichage ; historique des anciennes dénominations lorsque applicable.
- Après vérification, pas d'édition directe : action « Demander une modification du nom » avec type de modification, motif, justificatifs, vérification d'autorité, authentification renforcée si nécessaire, validation, revérification, notification et audit.
- Une correction typographique/administrative n'est pas forcément traitée comme un changement complet de dénomination.
- Pendant l'examen, le nouveau nom peut être indiqué « En cours de vérification » et ne doit pas hériter automatiquement du statut vérifié précédent.
- Même entité juridique/organisationnelle avec changement légitime de dénomination : conserver le même objet Organisation et sa continuité historique.
- Nouvelle entité juridiquement/organisationnellement distincte : créer un nouvel objet Organisation Connecte+, même propriétaires, dirigeants, adresse ou activité ; suivre ses propres procédures de vérification/activation.
- Ne jamais transférer artificiellement identité, vérification, réputation, avis, transactions, autorisations ou sanctions par simple renommage.
- Le même compte utilisateur peut administrer l'ancienne et la nouvelle organisation ; Utilisateur ≠ Organisation.
- Historique interne : ancien nom → nouveau nom → date → type/motif → justificatifs/autorité → demandeur → validation → résultat. L'affichage public « anciennement… » sera défini séparément.
- Intégrer le changement de nom à la future Matrice des modifications organisationnelles sensibles.

**Note :** ⚖️ Justificatifs et continuité juridique selon les formes d'entités en RDC à valider.

---

### PARTIE 3F — Périmètre fonctionnel

#### Q36. Troc entre particuliers

*Réf. Troc — Question d'origine : L'échange d'objets entre particuliers (troc) n'apparaît pas dans votre dossier. Souhaitez-vous cette fonction ?*

> **EN ATTENTE — PROPOSITION DEV** — Décision produit en attente d'une proposition fonctionnelle et technique de l'équipe de développement. Le troc n'est pas activé en V1 tant que sa valeur, ses risques et ses règles ne sont pas démontrés.

**Décisions et exigences**

- L'équipe doit expliquer le besoin utilisateur, les cas d'usage, les utilisateurs concernés, la valeur ajoutée par rapport à la vente classique, la complexité induite et sa recommandation professionnelle V1/later/non.
- Définir précisément le modèle : objet ↔ objet, plusieurs objets ↔ un objet, objet + argent ↔ objet, offre/contre-proposition, remise en main propre, livraison, etc.
- Connecte+ ne doit pas arbitrer la valeur subjective des biens : l'équivalence économique relève de l'accord volontaire des parties.
- En revanche, la proposition doit traiter fraude, contrefaçon, fausse description, bien défectueux présenté comme fonctionnel, non-remise et non-conformité.
- L'absence de paiement monétaire ne doit pas créer une zone moins contrôlée de la Marketplace. Définir biens autorisés/interdits, détection/signalement, prévention du contournement, éléments de traçabilité et articulation avec modération/sanctions.
- Présenter le parcours transactionnel : publication → proposition → contre-proposition → acceptation bilatérale → accord enregistré → remise/livraison → confirmations → transaction terminée ou litige.
- Définir annulation, cas où une seule partie a déjà remis/expédié son bien, confirmations des deux parties et échanges mixtes avec argent.
- Préciser le rôle réel de Connecte+ en litige : enregistrer, vérifier factuellement, faciliter, modérer, investiguer, sanctionner ou orienter vers des recours. Ne pas créer une fausse impression de garantie.
- Préciser si un troc terminé ouvre droit à un avis transactionnel et quelle preuve d'interaction est requise.
- Expliquer l'intégration avec l'architecture Commerce existante et l'effort technique.
- Recommandation attendue : A) intégrer V1 ; B) prévoir architecture mais reporter ; C) ne pas intégrer ; ou autre approche motivée.

**Note :** STATUT : réponse au questionnaire finalisée, mais décision produit volontairement laissée en attente de la proposition de Jonathan/l'équipe.

---

## 3. Travaux complémentaires identifiés pendant le questionnaire

Le questionnaire a révélé plusieurs chantiers qui ne doivent pas être perdus. Ils ne constituent pas tous des fonctionnalités V1 immédiatement livrables, mais ils doivent être suivis dans le backlog produit/architecture.

### Matrice Sanctions, Modération & Enforcement

- Définir violations par module, gravité, seuils de preuve, première/récidive, mesures automatiques conservatoires vs décisions humaines, avertissement/retrait/restriction/suspension/exclusion, durée, appel, réintégration, contournement et rétention.
- Inclure fraude, spam, scraping, coercition d'avis, usurpation, abus de vérification, paiements suspects, produits interdits/contrefaits, recrutement abusif, etc.
- Ajouter remédiation organisationnelle, changement réel de contrôle/direction, mesures correctives et réexamen sans réactivation automatique.

### Matrice des modifications organisationnelles sensibles

- Pour chaque changement : type, risque, demandeur autorisé, approbateur, preuve, step-up authentication, double contrôle, notifications, audit, récupération après changement non autorisé.
- Inclure contact principal, e-mail/domaine officiel, comptes externes, Administrateur principal, délégations importantes, identité/dénomination vérifiée, comptes de paiement/règlement.

### Help, Support & Case Management

- Centre d'aide, FAQ/recherche, diagnostic guidé, tickets, messagerie, routage, priorités, pièces jointes, statuts, notifications, escalade, récupération, fraude/paiement, appels/recours, permissions staff, rétention et métriques.
- Prévoir une couche règles/politiques compréhensible : niveau 1 « que s'est-il passé/que faire ? », niveau 2 explication/exemples, niveau 3 règle complète.

### Économie informelle, formalisation et fiscalité RDC

- Rechercher les règles actuelles de fiscalité/formalisation, facture normalisée, distinction activité occasionnelle vs professionnelle récurrente, obligations des acteurs informels et gouvernance des demandes d'autorités.
- Concevoir un accompagnement progressif à la formalisation sans aider à contourner les obligations fiscales ou réglementaires.

### Appels vocaux via Connecte+

- Étudier séparément appel internet in-app (WebRTC/SDK voix) et appel PSTN masqué/callback.
- Analyser disponibilité +243/opérateurs, coût/minute, consommation data, réseau RDC, arrière-plan/push, TURN, sécurité, abus et coûts à l'échelle.
- Ne pas confondre statut « en ligne » et « disponible pour les appels » ; prévoir disponibilité volontaire et horaires.

### Favoris et Partenariats professionnels

- Favoris : sauvegarde privée/unilatérale d'un profil, sans consentement marketing.
- Partenariat professionnel : relation bilatérale, explicite, structurée, distincte d'un favori et ne constituant pas une certification Connecte+.

### Taxonomie V1 et matrices de vérification

- Définir catégories/sous-catégories/attributs, synonymes FR/EN/Lingala/termes courants, règles par acteur et filtres, configurables en back-office.
- Finaliser la matrice acteur → activité → risque → identité → qualification → licence → visibilité → validité → revérification → indicateur public.

### Stratégie de lancement et onboarding institutionnel

- Prévoir onboarding digital, assisté à distance et assisté sur site avec mêmes contrôles de vérification.
- Séparer fonctions commerciales/onboarding de la fonction qui approuve la vérification.

---

## 4. Points externes déjà signalés dans le questionnaire

Le document source mentionne deux sujets hors des 36 questions, déjà inscrits au planning et dépendant d'une validation externe. Ils restent ouverts :

- **Campagnes des ONG et dons :** validation juridique à obtenir. L'architecture financière ne doit pas supposer une garde générale de fonds par Connecte+ sans validation spécifique.
- **Publication automatique sur une page Facebook :** validation Meta nécessaire (application, permissions et conditions techniques). Ne pas promettre la fonctionnalité avant validation effective.

---

## 5. Rappel final à l'équipe de développement

Les décisions ci-dessus doivent être traduites en objets, états, permissions, transitions, contrôles, notifications, audit, erreurs compréhensibles et critères d'acceptation. Pour chaque module majeur, la documentation technique/fonctionnelle doit au minimum préciser :

1. Objectif
2. Acteurs
3. Conditions d'entrée
4. Parcours utilisateur
5. États et transitions
6. Permissions et périmètres
7. Exceptions et cas limites
8. Données et audit
9. Notifications
10. Guidage utilisateur
11. Contraintes sécurité/confidentialité/juridiques
12. Critères d'acceptation

Les décisions métier validées ne doivent pas être remplacées silencieusement par des choix techniques par défaut. Inversement, lorsque la spécification laisse un véritable choix d'ingénierie, l'équipe de développement doit proposer et justifier la solution technique appropriée.

> **FIN** — Questionnaire consolidé : Q1-Q35 verrouillées ; Q36 renvoyée à l'équipe de développement pour proposition et recommandation avant décision produit sur le troc.
