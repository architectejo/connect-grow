# Questions à poser au client — Connecte+

Fichier tenu par le chef de projet. Toute nouvelle question destinée au client s'ajoute ici, dans la catégorie qui convient.
Dernière mise à jour : 09/11/2026.

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
| | | | | |
