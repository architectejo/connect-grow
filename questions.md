# Questions à poser au client — Connecte+

Fichier tenu par le chef de projet. Toute nouvelle question destinée au client s'ajoute ici, dans la catégorie qui convient.
Dernière mise à jour : 25/11/2026.

> **Le client a répondu (25/11/2026)** : `docs/client/ConnectePlus_Reponses_Consolidees_Q1-Q36.md`. Q1 à Q35 sont **verrouillées** ; Q36 (troc) attend une **proposition de l'équipe de développement**. Analyse d'impact en cours : `docs/specs/impact-reponses-client-Q1-Q36.md`. Les nouvelles questions s'ajoutent ci-dessous.

**Comment lire ce fichier**
- **Bloque** : la tâche citée ne peut pas être clôturée sans la réponse. **Ne bloque pas** : une hypothèse de travail permet d'avancer ; elle est réversible.
- **Hypothèse actuelle** : ce que le code ou la spec fait en attendant. Si le client répond autrement, on adapte.
- **Réponse** : à remplir au fur et à mesure (date, réponse, qui a répondu). Une question répondue est conservée, marquée « Répondu ».
- Les identifiants (Q-CLI…, LEG-PRV-…) renvoient aux specs et ADR de `docs/`, pour retrouver le détail technique.

## Sommaire des priorités

| Priorité | Questions | Pourquoi |
|---|---|---|
| **Bloquantes** | Q-CLI8, Q-L1-6, Q-L1-8, Q-CLI6 | Empêchent de lancer ou de clore la revendication d'organisation (L1-01i, j, l) |
| **Avant la mise en production** | Section 1 (juridique, LEG-PRV) entière, Q-SUSP1, Q-SUSP5 | Textes légaux, durées de conservation, communication aux propriétaires |
| **À confirmer, avancent par hypothèse** | Q-CLI1 à Q-CLI5, Q-CLI7, D3, D11, Q-L1-3, Q-L1-10, Q-L1-11, troc | Valeurs provisoires en place |

---

## 1. Protection des données et juridique (LEG-PRV)

Aucune de ces questions ne bloque le développement. Elles doivent être closes avant la production. Source : `docs/client/doc12.md`, `docs/adr/0005-contact-vendeur-consentement.md` §9, `docs/specs/avis-classement-contact.md` §3.

### 1.1. Numéro de contact du vendeur

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| LEG-PRV-01 (a) | Quelle base légale couvre la communication du numéro d'un vendeur à un utilisateur connecté (consentement du vendeur, exécution d'un service, intérêt légitime) ? Un consentement par canal, révocable, suffit-il ? | Consentement du vendeur, par canal, révocable | |
| LEG-PRV-03 (a) | Le consentement est-il valable s'il est donné dans un écran des réglages avec un texte versionné ? Quelle formulation exacte en français (puis lingala/swahili) faut-il montrer ? | Texte provisoire, version `2026-10-v1` | |
| LEG-PRV-03 (b) | Un vendeur peut-il rendre son numéro visible à tous, y compris aux non-connectés, s'il le demande expressément ? | Non prévu en V1 ; on veut savoir si c'est permis | |
| LEG-PRV-05 (a) | Durée de conservation de la trace « X a obtenu le numéro de Y pour l'offre Z, le [date] » (contacts et journal d'audit), y compris après la clôture d'un compte ? Que devient cette trace si le visiteur efface son compte alors que son avis reste ? | Aucune durée, aucune purge | |
| LEG-PRV-04 (a) | Quand le vendeur retire son accord, faut-il prévenir ceux qui ont déjà reçu le numéro ? Le numéro déjà remis reste-t-il utilisable par eux ? | Aucune information envoyée | |
| LEG-PRV-04 (b) | Le vendeur peut-il demander la liste des personnes qui ont obtenu son numéro ? Le visiteur peut-il obtenir la liste des numéros qu'il a demandés ? | Liste vendeur livrée en partie ; pas de route « mes révélations » pour le visiteur | |
| LEG-PRV-09 | La plateforme peut-elle conserver l'adresse IP (ou une empreinte hachée) des demandes de numéro pour limiter le scraping, et combien de temps ? | Aucune IP conservée ; limite IP uniquement en cache | |
| LEG-PRV-11 | Un visiteur qui obtient un numéro peut-il l'utiliser pour de la prospection commerciale ? Quelle mention afficher (« usage limité à l'objet de l'offre ») ? | Pas de mention affichée | |
| LEG-PRV-12 / 06 | WhatsApp (Meta) reçoit le numéro à l'ouverture du lien `wa.me` : faut-il informer le vendeur et le visiteur ? Transfert hors RDC ? | Aucune information affichée | |
| LEG-PRV-01 (c) | Le modérateur peut-il voir le numéro d'un vendeur et le canal utilisé lors d'un litige sur un avis « contact fictif » ? | Non : l'API n'expose aucun numéro au modérateur | |

### 1.2. Avis

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| LEG-PRV-01 (d) / D11 | Sous quelle forme afficher le nom de l'auteur d'un avis (nom complet, prénom + initiale, pseudo) ? | Prénom + initiale (« Marie K. ») | |
| LEG-PRV-05 (b) | Durée de conservation des avis et des réponses, y compris masqués, et conséquence d'une demande de suppression par leur auteur ? | Aucune durée | |
| D3 | Sous le seuil de 3 avis, le CDC dit « Pas encore d'avis ». Faut-il masquer seulement la moyenne (les avis déjà publiés restent lisibles) ou masquer aussi les avis ? | Moyenne masquée, avis lisibles, mention « 2 avis » | |

### 1.3. Comptes, organisations et conservation

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| Q-CLI6 | Durée de conservation des pièces KYB et de la pièce du représentant après refus, retrait ou fermeture de l'organisation ; durée de conservation de l'audit des membres. | Aucune purge (`kyb_file_retention_days = 0`), aucune durée inventée | |
| LEG-PRV-sanctions | Durée de conservation des sanctions, des signalements et des avis après suppression d'un compte. Faut-il conserver un identifiant pseudonymisé des comptes bannis pour empêcher le retour ? | Rien n'est purgé ; décision en attente | |
| LEG-PRV-orpheline | Que devient une organisation suspendue dont plus personne n'est propriétaire effectif (propriétaire supprimé ou banni) ? | Offres masquées, aucune issue automatique ; chemin de secours prévu en L1-01j | |
| LEG-PRV-mapping | Durée de conservation de la table de correspondance des anciens comptes entreprise (`LegacyAccountMapping`) | Conservée jusqu'à la réinitialisation de fin de projet | |

---

## 2. Organisations, rôles et vérification

### 2.1. Rôles et limites (L0-09, L1-01)

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| Q-CLI1 | Les 4 rôles (propriétaire, administrateur, éditeur, analyste) suffisent-ils pour la V1 ? Les branches ou départements sont-ils hors V1 ? Plusieurs propriétaires sont-ils permis ? | Oui aux trois ; rôles fixés dans le code | |
| Q-CLI4 | Combien d'organisations par compte (créées et rejointes) ? Une seule suffit-elle au lancement ? Le plafond doit-il être affiché dans l'écran ? | 10 appartenances actives, réglable ; chiffre non affiché | |
| Q-L1-3 | Une invitation peut-elle conférer le rôle administrateur ? (Doc 02 UF-04 : « invitation comme simple membre sans droit d'administration ».) | Éditeur et analyste par invitation ; administrateur seulement par promotion ; propriétaire jamais par invitation | |
| Q-L1-10 | La suppression libre-service du compte est-elle voulue en V1 ? Le CDC n'en parle pas. | Hors périmètre ; seuls les blocages côté équipe sont livrés | |
| LEG-PRV-invit-1 | Invitations d'équipe : durée de conservation des invitations closes (elles gardent l'identifiant de l'inviteur et de la personne qui a accepté) et durée de validité d'un lien. | 7 jours de validité, 30 jours de conservation après clôture, valeurs provisoires | |
| LEG-PRV-invit-2 | Invitation : l'inviteur peut saisir une étiquette libre (60 caractères), lisible par les membres habilités pendant la vie de l'invitation, effacée à la clôture. Quelle finalité et quelle mention d'aide faut-il afficher (« ne saisissez pas de coordonnées ») ? | Texte d'aide à poser par le front | |
| LEG-PRV-invit-3 | Un lien d'invitation transmis à un tiers permet de rejoindre l'équipe sans vérifier l'identité de la personne visée (seul le téléphone du compte qui accepte est vérifié). Est-ce acceptable pour les rôles éditeur et analyste ? Faut-il informer l'inviteur de ce risque (transmettre le lien par un canal privé, annuler en cas de doute) ? Une évolution possible est de rattacher l'invitation à un téléphone vérifié. | Accepté en V1, atténué par rôles limités, usage unique, expiration, révocation et notification de l'inviteur | |

### 2.2. Nom, usurpation et revendication (**bloquantes**)

Elles bloquent L1-01i (revendication), L1-01j (décision et secours) et L1-01l (noms réservés).

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| **Q-CLI8** | Nom d'une organisation : unicité ou homonymes autorisés avec revendication ? Comment lutter contre l'usurpation du nom d'une entreprise connue avant la revendication ? | Homonymes permis, plafond par compte, nom verrouillé après vérification, signalement d'usurpation par la modération | |
| **Q-L1-6** | Qu'est-ce qu'une « fiche existante » revendicable (aucune source ne décrit de fiche pré-créée) ? Le propriétaire en place est-il prévenu d'une revendication, avec ou sans l'identité du demandeur ? Peut-il la contester dans l'application ? | Toute organisation active ou suspendue ; propriétaires et administrateurs prévenus sans identité du demandeur ; contestation hors application | |
| **Q-L1-8** | Revendication : quelles preuves exiger (RCCM, mandat, lettre, pièce du représentant) ? Quel rôle accorder ? Quel délai de traitement promettre ? Un badge public « Autorité vérifiée » existe-t-il (doc 07 §3) ? | Preuves libres typées ; propriétaire seulement sans propriétaire effectif, administrateur au plus sinon ; aucun délai promis ; aucun badge | |
| Q-L1-11 | Qui fournit la liste initiale de noms réservés (grandes banques, administrations, opérateurs) ? | Liste vide, alimentée en back-office | |

### 2.3. Vérification et publication

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| Q-CLI2 | Pièces KYB exigées par type d'organisation (entreprise, boutique informelle sans RCCM, ONG, organisateur d'événements) ? Une organisation non vérifiée peut-elle publier et être visible ? Faut-il reprendre le libellé « Pièce d'identité du représentant » ? | Entreprise et organisateur : RCCM + ID + représentant ; boutique : ID + représentant ; ONG : arrêté + ID + représentant ; la publication ne dépend pas de la vérification | |
| Q-CLI3 | Que peut publier le contexte personnel : objets d'occasion seulement, ou aussi des services ? | Tout, sans restriction | |
| Q-CLI7 | Le profil prestataire peut-il publier sans vérification d'identité ? Quelles catégories exigent une vérification renforcée (doc 07 §6) ? | Aucune vérification d'identité ; aucune catégorie sensible | |

### 2.4. Contact d'une organisation

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| Q-CLI5 | Qui consent à la révélation du numéro de contact d'une organisation (propriétaire seul, ou aussi administrateur) ? Quel texte de consentement s'applique ? | Propriétaire ou administrateur ; fonction fermée : l'organisation n'offre que la messagerie | |

---

## 3. Suspension, archivage et support

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| Q-SUSP1 | Quel moyen de contact du support citer dans l'application (adresse e-mail, numéro WhatsApp, page) ? | Texte « contactez le support de Connecte+ » sans lien ; un réglage de back-office affichera l'adresse quand elle existe | |
| Q-SUSP2 | Le propriétaire et les administrateurs doivent-ils voir une catégorie de motif de suspension ? | Non en V1 | |
| Q-SUSP3 | Une organisation archivée peut-elle être restaurée par le support ? | Non : la réactivation est refusée pour une organisation archivée | |
| Q-SUSP5 | Faut-il prévenir par SMS ou e-mail les propriétaires d'organisations créées « suspendues » par la conversion des anciens comptes entreprise ? | Message unique envoyé par le personnel à la mise en production, hors application | |
| A13 | Le nom d'une organisation devient non modifiable dès qu'une pièce est validée (passage par le personnel). Le client l'accepte-t-il pour les petites entreprises qui se renomment ? | Verrou actif | |

---

## 4. Périmètre fonctionnel

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| Troc | Le troc entre particuliers (échange d'objets) est absent du dossier client. Le client le veut-il ? | Masqué derrière un interrupteur (`exchange_enabled`, éteint) | |
| Q-L1-12 | Qui décide d'une revendication : le personnel de vérification (hypothèse) ou un groupe distinct ? | Permission dédiée au groupe de vérification, jamais au modérateur | |

---

## 4 bis. Questions ouvertes après les réponses du client (25/11/2026)

Source : `docs/specs/impact-reponses-client-Q1-Q36.md` §5 et `docs/adr/0010-gouvernance-organisations.md` §17.

| ID | Question | Hypothèse actuelle | Réponse |
|---|---|---|---|
| QO-1 | Existe-t-il de vrais anciens comptes entreprise à migrer (avec des utilisateurs réels) ? Sinon Q18 et Q20 sont sans objet. | Aucune donnée de production (ADR 0002) | |
| QO-2 | Une contestation d'autorité est-elle notifiée à l'administrateur en place, et peut-il y répondre dans l'application ? | Notifié sans identité du demandeur ; réponse hors application | |
| QO-3 | Quel prix du Premium fait foi : environ 50 USD/an (Q28) ou 2 USD/mois (CDC §7) ? | Prix en base, non fixé | |
| QO-4 | Passes du particulier : sort des offres déjà publiées sans pass ; définition d'une « activation » ; durée d'un pass. | À définir avec L1-11 | |
| QO-5 | La location de son propre bien immobilier (Property Rental Pass) entre-t-elle en V1 ? L'immobilier n'est pas dans le périmètre actuel. | Hors V1 tant que non confirmé | |
| QO-6 | « Simple membre » (Q23) est-il un rôle distinct d'Analyste ? | Rôle « Membre » ajouté (consultation interne et départ seulement) | |
| QO-7 | Que se passe-t-il à la fin des 90 jours de grâce de vérification (Q26) ? | Restriction de la visibilité, à confirmer | |
| QO-8 | Seuils de dormance d'une organisation et délai avant archivage d'une organisation sans administrateur principal. | Réglables, livrés à 0 (désactivés). Proposition de l'équipe (ADR 0011) : dormance après 365 jours sans activité ; organisation sans administrateur principal restreinte à 30 jours puis archivée à 180 jours | |
| QO-9 | Délai de traitement annoncé pour une vérification ou une récupération. | Aucun délai promis | |
| QO-10 | Qui voit l'historique d'accès aux coordonnées d'une organisation ? | Administrateurs principaux et administrateurs | |
| QO-13 | Qui valide la grille des durées de conservation (juriste du client, IMARA TECH) ? | En attente | |
| QG-4 | Une organisation peut-elle choisir d'avoir un seul Administrateur principal (option de gouvernance) ? | Plusieurs permis, sans plafond | |
| QG-5 | Une organisation sans administrateur principal (Q17) reste-t-elle visible publiquement pendant la régularisation ? | Non publique jusqu'à régularisation | |
| LEG-PRV-invit-4 | Invitation comme Administrateur : la personne qui accepte voit annoncé que le confirmateur verra son nom abrégé et les deux derniers chiffres de son téléphone vérifié (finalité : vérifier l'identité avant un accès privilégié). Cette finalité et la mention d'information sont-elles valables ? Durée de conservation de « qui a accepté, quand » sur l'invitation close ? Faut-il le mentionner dans la politique de confidentialité (finalité « sécurité des accès d'organisation ») ? | Mention dans l'aperçu ; conservation 30 jours après clôture (réglable) | |
| QC-1 | Cycle de vie (ADR 0011 §17) : confirmez-vous les choix de l'équipe : la dormance ne retire aucune capacité (QL-1) ; une fermeture reste possible sous suspension (QL-3) ; l'ancien nom reste affiché pendant l'examen d'un changement (QL-5) ; le modérateur ne pose pas de restriction en V1 (QL-7) ; taxonomie de départ des 9 catégories (QL-8) ; revérification par défaut après une restauration (QL-10) ; les rôles ordinaires ne voient ni catégorie ni motif (QL-11) ; champ « dénomination légale » distinct du nom d'affichage (QL-13) ? | Appliqués tels quels | |
| QC-2 | Validez-vous les 9 explications de catégories de restriction (`docs/specs/L1-17-cycle-de-vie-organisations.md` §6) ? | Textes de l'équipe | |
| QC-3 | Changement de nom : quels justificatifs accepter selon les formes d'entités en RDC ? | Justificatifs libres, décidés par l'équipe Vérification | |
| QC-4 | Un changement de forme juridique est-il un changement de nom de la même entité ou une nouvelle entité ? | Nouvelle entité si le numéro d'enregistrement change | |
| QC-5 | Que deviennent les droits commerciaux (plans, promotions) d'une organisation fermée ? | À trancher avec L1-11 | |
| QC-6 | Faut-il communiquer au demandeur le motif d'un refus de restauration ? | Oui, motif communiqué court | |
| QC-7 | Quel délai de recours par défaut contre une restriction ? | Réglable, sans valeur | |
| QC-8 | Une organisation sans activité depuis longtemps : préférez-vous le libellé « Inactive » (choix de l'équipe) ou « Dormante » ? | « Inactive » | |
| QC-9 | Fermeture pour cause de fusion : le texte dit que rien n'est transféré automatiquement vers l'autre organisation (avis, abonnés, historique). Le confirmez-vous ? | Rien n'est transféré (Q35 : jamais de transfert par simple renommage) | |
| QG-8 | Liste initiale des catégories et organisations à vérification renforcée (banques, Mobile Money, télécoms, ministères…). | Liste vide, configurable en back-office | |

## 5. Autres blocages externes déjà notés au backlog

| Sujet | Tâche | Ce qu'on attend |
|---|---|---|
| Campagnes ONG et dons | L2-06 | Validation juridique du client |
| Publication automatique sur la page Facebook | L2-10 | Validation Meta (application, permissions) |

---

## Journal des réponses

À remplir quand le client répond : date, ID de la question, réponse, personne, impact sur le backlog.

| Date | ID | Réponse | Reçue de | Impact |
|---|---|---|---|---|
| 25/11/2026 | Q-CLI8, Q-L1-6, Q-L1-8, Q-CLI6 (Q1 à Q4) | Homonymes permis sans droit d'antériorité ; pas de fiches précréées (revendication = récupération d'anciens comptes et conflits d'autorité) ; badge « Organisation vérifiée » ; rôle supérieur « Administrateur principal » ; durées de conservation par catégorie, configurables | Client (questionnaire consolidé) | L1-01i/j/l et L1-02 à replanifier |
| 25/11/2026 | LEG-PRV-01 à 12 (Q5 à Q14) | Contacts distincts (compte, professionnel, transactionnel, paiement) ; consentement contextuel versionné ; historique d'accès à mes coordonnées ; rappel anti-démarchage ; avertissement avant WhatsApp ; modérateur sans numéro complet ; IP temporaire et proportionnée | Client | Écarts à mesurer avec L0-10a / ADR 0005 |
| 25/11/2026 | LEG-PRV-05 b, sanctions, orpheline, mapping (Q15 à Q18) | L'auteur modifie, actualise ou supprime son avis ; « Ancien utilisateur Connecte+ » ; sanction distincte du compte ; organisation « sans administrateur principal » sans promotion automatique ; mapping legacy temporaire | Client | À planifier |
| 25/11/2026 | Q-SUSP1, Q-SUSP5 (Q19, Q20) | Vraie architecture Aide et Support avant lancement ; parcours de migration par e-mail/SMS + in-app | Client | Nouveau chantier |
| 25/11/2026 | Q-CLI1, Q-CLI4, Q-L1-3, Q-L1-10, Q-L1-11, Q-L1-12 (Q21 à Q26) | Pas de « plusieurs propriétaires » ; périmètres (branches) à modéliser ; pas de plafond de 10 organisations ; invitation possible comme Administrateur ; suppression libre-service du compte en V1 ; liste de noms protégés ; escalade et second contrôle | Client | **Contradictions avec L1-01 livré** |
| 25/11/2026 | Q-CLI2, Q-CLI3, Q-CLI7, Q-CLI5 (Q27 à Q30) | Matrice documentaire progressive ; Pass et Premium pour le particulier ; vérification du prestataire proportionnée au risque ; gestion du numéro d'organisation par personne autorisée, maker-checker | Client | Impact L1-02, L1-11 |
| 25/11/2026 | D11, D3, Q-SUSP2, Q-SUSP3, A13 (Q31 à Q35) | « Marie K. » + avatar ; moyenne masquée sous 3 avis (hypothèse confirmée) ; catégorie de suspension visible ; restauration exceptionnelle d'une archivée ; changement de nom par procédure contrôlée | Client | À planifier |
| 25/11/2026 | Troc (Q36) | En attente d'une proposition de l'équipe (A intégrer V1, B architecture prévue mais reportée, C ne pas intégrer) | Client | Proposition à rédiger |
