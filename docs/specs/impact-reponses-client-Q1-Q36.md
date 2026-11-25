# Analyse d'impact — Réponses consolidées du client (Q1 à Q36)

- **Date :** 25/11/2026
- **Auteur :** analyste-fonctionnel
- **Statut :** analyse, à valider par le chef de projet (CP) puis par l'utilisateur (Anicet, Jonathan) pour les points marqués « décision utilisateur »
- **Source principale :** `docs/client/ConnectePlus_Reponses_Consolidees_Q1-Q36.md` (Q1 à Q35 verrouillées ; Q36 en attente d'une proposition de l'équipe). Selon CLAUDE.md §3.1, ces décisions sont la **première source de vérité** : elles priment sur le CDC v1.2, les ADR et le backlog.
- **Sources comparées :** `questions.md` (hypothèses actuelles), `docs/suivi/BACKLOG.md`, `docs/suivi/JOURNAL.md` (entrées du 09/11), ADR 0005, 0006, 0008, 0009, specs `L1-01-organisations.md`, `L1-01-contrat-api.md`, `L1-11-L1-12-plans-paiements.md`, CDC v1.2 (§1.4, §3.1 à §3.5, §3.14, §3.15, §3.17, §7). Code lu en lecture seule : `backend/apps/identity/` (`capabilities.py`, `models.py`, `organizations.py`, `organization_reads.py`), `backend/apps/reviews/` (`models.py`, `services.py`, `serializers.py`), `backend/apps/moderation/models.py`, `backend/apps/marketplace/models.py`, `connect-grow/src/i18n/locales/fr.ts`.
- **Ce document ne modifie** ni le code, ni le CDC, ni le backlog, ni les ADR.

Légende effort : **S** = moins de 2 jours-agent ; **M** = 2 à 5 jours-agent ; **L** = plus de 5 jours-agent ou nouvel ADR avec migration. Légende priorité : **Bloque L1-01** = à traiter avant de clore L1-01 ; **Avant production** = obligatoire avant l'ouverture au public ; **Plus tard** = backlog produit.

---

## 0. Synthèse

1. **Six décisions contredisent du code déjà livré** : Q21 (rôle « Propriétaire », pas de périmètre), Q22 (plafond de 10 organisations affiché), Q23 (invitations limitées à éditeur et analyste), Q24 (suppression de compte refusée par la garde actuelle), Q33/Q34 (statut d'organisation unique, archivage irréversible), Q15/Q16 (avis verrouillés après réponse, avis effacés avec le compte).
2. **Trois décisions contredisent des specs ou ADR non encore codés** : Q2/Q25 (revendication générique et refus des noms réservés de L1-01i et L1-01l), Q28 (ADR 0009 D7 : aucun pass en V1, publication gratuite illimitée du particulier).
3. **Q28 et Q24 élargissent le périmètre V1** (passes du particulier, suppression libre-service), comme Q19 (module Aide et Support) et Q21 (modèle de périmètre). CLAUDE.md §1 impose l'accord de l'utilisateur avant tout changement de périmètre V1 : le client a décidé, mais le planning et le budget changent.
4. **L1-01 peut être clos** sans attendre la revendication : je recommande de sortir L1-01i, j et l de L1-01 et de les rattacher à la vérification (famille L1-02), réécrits selon Q2, Q3, Q17, Q25, Q26.
5. **F2 (invitations front) doit être terminé sur le contrat actuel**, puis complété par un lot additif après l'ADR de gouvernance. **F3 (blocages de suppression) doit être mis en pause** : Q24 change le sens des « blocages ».
6. **Aucune règle verrouillée de CLAUDE.md §4 n'est contredite par le client.** Plusieurs décisions la renforcent (règles 3, 8, 10, 11, 12). Trois points demandent une vigilance (§6) : badge « Organisation vérifiée » face à la règle 3, questionnaire privé de conformité face à la règle 4, troc avec argent face aux règles 8 et 9.

---

## 1. Tableau d'impact Q1 à Q36

Abréviations des éléments touchés : **code** (module), **spec**, **ADR**, **CDC** (section), **BL** (ligne du backlog).

| Q | Décision du client (résumé) | Hypothèse actuelle (`questions.md`, code) | Écart | Éléments touchés | Effort | Priorité |
|---|---|---|---|---|---|---|
| **Q1** Homonymes | Homonymes permis. L'antériorité ne donne aucun droit. Les justificatifs vérifiés priment. Restriction possible de l'usage contesté pendant l'examen. Changement de nom par procédure contrôlée. | Homonymes permis (A12) ; verrou du nom après pièce ; signalement d'usurpation prévu (L1-01l, non livré). | **Ajustement** : distinguer nom d'affichage et dénomination légale ; restriction ciblée « usage du nom » absente. | code `identity.Organization.name`, `moderation` (cible `organization`) ; spec L1-01l ; ADR 0006 A12, A13 ; CDC §3.1 | M | Avant production |
| **Q2** Fiche « existante » | Aucune fiche précréée. La « revendication » se réduit à la récupération d'anciens comptes et aux conflits d'autorité. | H4 : toute organisation ACTIVE ou SUSPENDED revendicable par un tiers ; L1-01i générique. | **Contradiction** (spec seulement ; rien de livré). | spec L1-01 §L1-01i ; `questions.md` Q-L1-6 ; CDC §3.1 (« Création, revendication ou invitation ») ; BL L1-01 | M | Bloque L1-01 (clôture : sortir i/j/l) |
| **Q3** Preuves, rôle, badge | Chaîne Organisation → existence → représentant → mandat → administrateur autorisé. Rôle supérieur « Administrateur principal ». Délégations traçables, révocables, avec durée et périmètre. Indicateur public « Organisation vérifiée ». Vérification non achetable. Prestataire : identité pour l'activité publique. | Rôle `OWNER` libellé « Propriétaire » ; `Membership` sans durée ni périmètre ; claims KYB précis (« RCCM vérifié ») ; aucun badge d'autorité. | **Contradiction** (libellé) ; **ajustement** (délégation datée, badge). | code `identity/capabilities.py` (`ROLE_CHOICES`), `fr.ts` (≈ 33 libellés), `Membership` ; ADR 0006 §5, ADR 0008 ; CDC §3.1 | M | Bloque L1-01 (libellé, modèle) |
| **Q4** Conservation des pièces | Pas de durée uniforme. Cinq classes de documents. Original non conservé indéfiniment après refus. Cycle actif → archivé → suppression ou anonymisation. Legal hold. Durées configurables. Autorité d'un représentant datée, revérifiée. | `kyb_file_retention_days = 0` (illimité), réglage unique ; aucun legal hold ; aucune date d'autorité. | **Ajustement important.** | code `identity` (réglages, `kyc_files`, commande de purge) ; ADR 0006 §18 ; Q-CLI6 | L | Avant production |
| **Q5** Types de numéros | Distinguer numéro de compte, contact professionnel, contact transactionnel, destination de paiement. Particulier privé par défaut. Prestataire : contact pro distinct, canaux et horaires. Organisation : plusieurs contacts fonctionnels possibles. | `ContactPoint` : un par compte (partagé entre contexte personnel et prestataire), un par organisation ; option `use_login_phone` ; pas d'horaires. | **Ajustement.** | code `identity.ContactPoint`, `ContactConsent` ; ADR 0005 C1 à C3 ; ADR 0006 §4.4 | M | Avant production (contact pro du prestataire) ; plusieurs contacts : plus tard |
| **Q6** Consentement | Choix contextuel au moment d'activer, pas seulement dans les réglages. Trace : version, date, contact, finalité, canaux, visibilité, modifications. `2026-10-v1` provisoire. Lingala et swahili fidèles au français validé. | Choix dans les réglages ; état courant par canal + audit des changements ; texte `2026-10-v1`. | **Ajustement.** | front `ContactSettingsSection` et fiche offre ; historique append-only de consentement ; ADR 0005 C4 | M | Avant production |
| **Q7** Numéro public | Particulier : jamais public aux non-connectés en V1. Prestataire et organisation : numéro pro public possible, même hors connexion, sur désignation explicite. Numéro d'authentification et de paiement jamais publics. | Aucun numéro public ; révélation authentifiée seulement. | **Ajustement** (fonction optionnelle ; le défaut actuel est conforme). | `marketplace` (révélation), `identity` ; ADR 0005 §8 ; CDC §3.2 (onglet À propos : « téléphone ») | M | Plus tard |
| **Q8** Trace d'accès | Informer avant l'accès que le titulaire saura quel compte a accédé. « Historique d'accès à mes coordonnées ». Journal interne détaillé. Rapports périodiques. Trois niveaux de conservation. Durées configurables. | Liste « qui a demandé mon numéro » (ADR 0005 §5.5) et notification ; aucun avertissement préalable ; aucune durée. | **Ajustement.** | front (texte avant révélation) ; `marketplace` (rétention, rapports) ; ADR 0005 | S (texte) + M (rétention, rapports) | Avant production |
| **Q9** Retrait de l'accord | Arrête les divulgations futures. Pas de notification aux anciens destinataires. Canal transactionnel maintenu. | Effet immédiat ; aucune information envoyée. | **Aucun** (V1 sans commande). À reprendre au lot 2 (billets, abonnements). | — | S | Plus tard |
| **Q10** Listes de numéros | Journal contrôlé pour le titulaire. Pas de carnet de numéros pour le visiteur. « Mes contacts / Favoris » de profils. | Liste titulaire livrée ; `GET contacts/` du visiteur sans numéro ; favoris d'offres seulement. | **Ajustement** (favoris de profils). | BL L1-07 ; CDC §3.7 | M | Lot 1 (avec L1-07) |
| **Q11** IP et scraping | Signaux techniques temporaires et proportionnés. Réponse progressive : limite → réauthentification ou CAPTCHA → restriction temporaire des coordonnées → alerte. Pas de sanction permanente automatique. Durées proposées par l'équipe. | Aucune IP persistée ; throttles en cache ; signalement automatique à 3 dépassements en 7 jours. | **Ajustement.** CAPTCHA = service externe probable (accord utilisateur). | `marketplace`, `moderation` ; ADR 0005 §8 | M | Avant production |
| **Q12** Démarchage | Rappel contextuel (texte fourni). Opt-in marketing séparé possible. Favori, transaction, obtention d'un numéro ≠ consentement marketing. | Aucun rappel. | **Ajustement.** | front (texte au moment de la révélation), `fr.ts` | S | Avant production |
| **Q13** WhatsApp | Information avant de quitter Connecte+ (texte fourni). Messagerie contextuelle réutilisable. Canal externe modélisé de façon générique. Vérifier le flux Meta. | Lien `wa.me` direct ; canaux `CALL` et `WHATSAPP` codés en dur. | **Ajustement.** | front (écran intermédiaire) ; `identity.ContactConsent` (canal générique) ; BL L2-09 | S (écran) + M (canal générique) | Avant production (écran) ; canal générique avec L2-09 |
| **Q14** Modérateur et numéro | Le modérateur ordinaire ne voit pas le numéro. Preuves minimisées. Accès exceptionnel encadré (fonction, motif, dossier, authentification renforcée, approbation, audit). Pas d'accès illimité des techniciens. Niveaux de preuve distincts (voir un numéro ≠ converser). | Aucun numéro exposé à la modération par l'API (ADR 0005 C12). Une révélation vaut preuve de contact et ouvre l'avis (option C, L0-25). | **Conforme sur le défaut ; ajustement** (accès exceptionnel ; libellé de preuve). | `moderation`, `identity`, admin Django (superutilisateur) ; ADR 0005 C12 ; BL F-02 | M | Avant production |
| **Q15** Avis : conservation | L'auteur peut modifier, actualiser (marqué « actualisé »), supprimer. Motif facultatif. Signalement de coercition distinct. Avis masqué : copie restreinte. Réponses suivent l'avis parent. | Modifiable 48 h ; modification et suppression refusées après réponse du vendeur ; suppression refusée sous signalement grave ; suppression physique. | **Contradiction** (code et CDC §3.4). | `reviews/services.py` (`update_review`, `delete_review`), `DeletedReviewMark`, `serializers.py` (`can_edit`, `can_delete`), front ; CDC §3.4 ; spec avis | M | Avant production |
| **Q16** Après sanction ou suppression | Suppression, anonymisation, fin de sanction : notions distinctes. Sanction = objet distinct conservé. Identifiant anti-abus pseudonymisé. Avis légitime conservé « Ancien utilisateur Connecte+ ». | `Review.user` en `CASCADE` (avis effacés avec le compte) ; `Sanction.user` en `CASCADE` ; aucun identifiant anti-retour. | **Contradiction.** | `reviews/models.py`, `moderation/models.py`, purge T9-3 ; ADR 0006 §20 | L | Avant production |
| **Q17** Organisation orpheline | État « sans administrateur principal / administration à régulariser », cumulable avec une suspension. Aucune promotion automatique. Récupération formelle. Sanctions de la personne et de l'organisation distinctes. Restreinte puis archivée si rien n'est rétabli. | Orpheline calculée (`count_effective_owners`), non affichée, sans état ; `last_effective_owner` permet l'orphelinat sans offre active ; secours L1-01j non livré ; pas d'auto-promotion. | **Ajustement.** | `identity` ; spec L1-01j ; ADR 0008 §9 | M | Bloque L1-01 (à déplacer, voir §3) |
| **Q18** Table legacy | Outil temporaire. Durée : migration → réconciliation → support → clôture formelle. Accès restreint et journalisé. Suppression planifiée. | `LegacyAccountMapping` conservé jusqu'à la réinitialisation de fin de projet. | **Ajustement.** | `identity.LegacyAccountMapping`, commande de purge | S | Avant production (sans objet s'il n'existe aucun compte réel, §5) |
| **Q19** Support | Vraie architecture Aide et Support. Ticket structuré. Canal externe sans authentification obligatoire. Coordonnées configurables. Au moins un canal fonctionnel avant lancement. | Texte « contactez le support » sans lien (messages `name_locked_by_verification`, organisation suspendue). | **Contradiction** (textes livrés). | nouveau module `support` ; `fr.ts` ; CDC §3.17 | S (minimum de lancement) ; L (gestion de dossiers) | Avant production |
| **Q20** Prévenir les anciens comptes | Oui : parcours d'information, récupération, régularisation. E-mail et/ou SMS, séquence limitée, notification in-app. | Message unique envoyé hors application par le personnel. | **Contradiction** avec l'hypothèse ; tension avec CDC §3.15 (« SMS réservés à l'OTP et à la sécurité »). | `notifications`, `identity.sms`, envoi d'e-mail (inexistant) | M | Avant production (si comptes réels) |
| **Q21** Rôles | Rôle → Permissions → Périmètre. « Administrateur principal ». Branches, sites, départements non exclus du modèle technique. Pas de « plusieurs propriétaires », mais un ou plusieurs Administrateurs principaux dûment autorisés. Actions sensibles : authentification renforcée, double contrôle. Rôles personnalisés possibles plus tard. | 4 rôles en constantes ; `OWNER` ; aucun périmètre ; plusieurs `OWNER` par simple promotion (ressaisie du mot de passe). | **Contradiction** (modèle). | `capabilities.py`, `Membership`, `organizations.py`, vues d'équipe ; ADR 0006 §5, ADR 0008 ; CDC §3.1 | L | Bloque L1-01 (ADR + champ périmètre) |
| **Q22** Nombre d'organisations | Pas de plafond global bas. Anti-abus : rate limits, signaux de risque, revue humaine. Ne pas afficher un seuil de sécurité comme limite. | `max_organizations_per_account = 10` ; `409 organization_limit_reached` à la création et à l'acceptation ; exposé par `GET organizations/limits/` ; message front explicite. | **Contradiction.** | `IdentitySettings`, `organization_reads.get_organization_limits`, `fr.ts` ; ADR 0006 D5 ; ADR 0009 §6 | M | Bloque L1-01 |
| **Q23** Rôle par invitation | Invitation possible comme simple membre, Éditeur, Analyste ou Administrateur, selon ce que l'émetteur peut déléguer. Jamais Administrateur principal. Aperçu : émetteur, organisation, rôle, périmètre, accès. | `INVITABLE_ROLES = (EDITOR, ANALYST)` ; aperçu sans périmètre ni accès. | **Contradiction.** | `identity/models.py` (`INVITABLE_ROLES`), `invitations.py`, contrat L1-01 §2.6, front F2 ; ADR 0008 §3.2 | M | Bloque L1-01 |
| **Q24** Suppression de compte | Oui en V1, par un processus contrôlé : « fermeture en cours », accès minimal, dernier Administrateur principal averti puis organisation orpheline, sanction et preuves conservées mais l'utilisateur peut partir. | Aucune suppression exposée ; garde `409` (dernier propriétaire, sanction bloquante, signalement grave) ; B4 liste les blocages. | **Contradiction.** | `identity.assert_account_removable`, B4, F3, `reviews`, `moderation`, `payments` ; ADR 0006 §20 T9-3 ; ADR 0008 §3.9 ; CDC (absent) | L | Avant production ; **F3 en pause** |
| **Q25** Noms réservés | Liste ciblée, configurable. Nom protégé ≠ interdit : vérification renforcée avant représentation publique. Variantes = signaux de revue. Étudier les registres RDC. | L1-01l : refus `400 name_reserved`. | **Contradiction** (spec ; rien de livré). | spec L1-01l ; ADR 0006 §17.5.3 | M | Avant production |
| **Q26** Qui décide | Équipe de vérification ; escalade et second contrôle pour les cas ambigus. Le modérateur ne décide pas. Niveaux : standard (grâce de 90 jours configurable), renforcé, pré-vérification (banques, Mobile Money, télécoms, ministères). L'équipe commerciale ne valide jamais. | Permission dédiée prévue (Q-L1-12) ; quatre yeux seulement si contesté ; pas de niveaux ; publication indépendante de la vérification. | **Ajustement.** | spec L1-01j, BL L1-02 ; `setup_roles` ; ADR 0006 | L | Avant production |
| **Q27** Pièces par type | Matrice progressive : acteur, forme juridique, activité, niveau, secteur. Parcours ONG distinct. La pièce du représentant ne prouve pas l'autorité. Pas de domicile publié. | `OrganizationDocumentRequirement` par `org_type` seulement, valeurs provisoires. | **Ajustement.** | `identity`, BL L1-02 | M | Avant production |
| **Q28** Particulier | Free : acheter, devis, réserver, postuler, événements, favoris, messagerie. Vente Marketplace personnelle : Marketplace Selling Pass (inclus dans Premium). Recruitment, Event, Property Rental Pass. Free : 10 activations de pass sur 12 mois glissants. Premium ≈ 50 USD/an (non final). « + Publier » contextuel. | Le contexte personnel publie sans restriction (Q-CLI3) ; ADR 0009 D7 : aucun pass livré ; offres Free « illimitées, provisoires ». | **Contradiction** (ADR 0009, CDC §3.1 et §7, code `marketplace`). | ADR 0009 D7, §6, §7 ; spec L1-11 ; `marketplace` (publication) ; front `PostEditor` ; CDC §3.1, §3.5, §7 | L | Avant production (mise en vente) ; amender ADR 0009 avant le développement de L1-11 |
| **Q29** Prestataires | Vérification progressive selon le risque. Identité quand la capacité pro publique est activée. Qualification ou licence pour l'activité réglementée. Badges factuels. Anti-contournement par catégorie. Questionnaire privé après interaction. Matrice configurable. | Aucune vérification d'identité du prestataire ; aucune catégorie sensible. | **Contradiction** (hypothèse). | `identity.ProviderProfile`, `catalog` (risque par catégorie), KYC, `reviews` ; BL L1-04 | L | Avant production |
| **Q30** Contact d'organisation | L'organisation décide qui gère ; Connecte+ le traduit en permission + périmètre. La coordonnée appartient à l'organisation. Texte fourni. Modifications sensibles : authentification renforcée, motif, preuve, double contrôle (maker-checker), notification. | `contact.manage_channels` = OWNER, ADMIN ; `org_phone_channels_enabled` fermé ; changement immédiat. | **Ajustement.** | `capabilities.py`, `ContactConsent` (organisation), `IdentitySettings` ; ADR 0006 §19.6 | M | Avant production |
| **Q31** Auteur d'un avis | « Prénom + initiale » + image publique actuelle ou avatar. Indicateur factuel d'interaction. Pas de pseudonyme. Jamais un selfie ou une pièce KYC. « Ancien utilisateur Connecte+ » après suppression. | `public_display_name` (« Marie K. ») ; pas d'avatar ; libellé « Avis après contact » ; avis effacé avec le compte. | **Ajustement.** | `reviews/serializers.py`, front (carte d'avis) | S | Avant production |
| **Q32** Moins de 3 avis | Masquer seulement la moyenne. « 1 avis », « 2 avis ». Mention facultative « La note moyenne est affichée à partir de 3 avis ». Pas de « —/5 ». Seuil sur les avis éligibles. | `min_reviews_to_display = 3` ; moyenne nulle ; texte « Pas encore assez d'avis » + compteur ; avis masqués exclus. | **Aucun** (ajustement de texte). | `fr.ts` (`rating.notEnough`) | S | Plus tard |
| **Q33** Motif de suspension | Montrer catégorie, motif compréhensible, périmètre, depuis, action requise, recours. 7 catégories configurables. Suspension totale ou restriction ciblée. Un échec de paiement ne suspend pas. | `suspension_reason` : 4 codes (`moderation`, `verification`, `legal`, `other`), non affiché ; suspension totale seulement. | **Contradiction.** | `identity.Organization`, `moderation.Sanction`, écran L0-09 « organisation suspendue », notifications | L | Avant production |
| **Q34** Restaurer une archivée | Cycle Active → Inactive/dormante → Fermeture en cours → Archivée → Supprimée/anonymisée. Restauration exceptionnelle, contrôlée, auditée, du même objet. Sanctions séparées du cycle de vie. | Statut unique `ACTIVE`/`SUSPENDED`/`ARCHIVED` ; archivage « irréversible par l'API » ; réactivation d'une archivée refusée. | **Contradiction.** | `Organization.status`, `archive_organization`, `reactivate_organization` ; ADR 0006 | L | Avant production |
| **Q35** Nom après validation | Verrou contre l'édition ordinaire, pas immuable. Procédure « Demander une modification du nom ». Dénomination légale, nom d'affichage, historique. Nouvelle entité = nouvel objet. | Verrou `name_locked_by_verification` (pièce en attente ou validée) ; message « contactez le support » ; un seul champ `name`. | **Ajustement** (procédure à ajouter ; le verrou reste). | `Organization`, `update_organization`, nouvel objet de demande ; ADR 0006 A13 | M | Avant production |
| **Q36** Troc | Décision en attente d'une proposition de l'équipe. Pas activé en V1. | `exchange_enabled` éteint ; `is_exchangeable` et `ExchangeProposal` masqués (L0-14). | **Aucun** (conforme). Livrable attendu : une proposition (§7). | doc ; BL nouvelle ligne TROC-01 | M (proposition) | Plus tard (le client attend la proposition) |

**Bilan :** 15 contradictions (Q2, Q3, Q15, Q16, Q19, Q20, Q21, Q22, Q23, Q24, Q25, Q28, Q29, Q33, Q34), dont 10 touchent du code livré (Q3, Q15, Q16, Q19, Q21, Q22, Q23, Q24, Q33, Q34) et 5 des specs, ADR ou hypothèses non codés ; 18 ajustements ; 3 sans écart (Q9, Q32, Q36).

---

## 2. Contradictions avec le code livré et recommandations

Classées par impact sur L1-01 (B1, B2a, B2b, B4 faits ; F1 fait ; F2 en cours ; F3 à faire).

### K1 — Libellé « Propriétaire » (L0-09, B1, F1, F2) — Q3, Q21

- **Constat :** `ROLE_CHOICES` (`capabilities.py`) libelle `OWNER` « Propriétaire ». Le front l'affiche partout (≈ 33 entrées dans `fr.ts`, dialogues de transfert, messages `last_owner`). Le client exige « Administrateur principal » et refuse le concept de propriétaire.
- **Options :** (a) garder le code technique `OWNER` en base et dans l'API, changer seulement les libellés ; (b) renommer la valeur en `PRIMARY_ADMIN` (migration de données sur `Membership.role`, contrainte `orginv_role_not_owner`, fixtures, contrat front).
- **Recommandation :** (a). Le code technique n'est pas visible du client ; (b) coûte une migration et un changement de contrat sans gain fonctionnel. L'ADR de gouvernance (ADR 0010, §3) consigne la correspondance. Messages backend (`organizations.py`, notifications) et `fr.ts` à réécrire. Effort S.

### K2 — Plusieurs `OWNER` par simple promotion (B1 : `change_role` vers `OWNER`, `transfer_ownership_to`) — Q21, Q23, Q30

- **Constat :** un propriétaire en nomme un autre avec la seule ressaisie de son mot de passe. Le client autorise plusieurs Administrateurs principaux « dûment autorisés lorsque la gouvernance le permet » et demande une procédure renforcée (Q23), avec maker-checker : « l'initiateur ne doit pas être l'unique approbateur de sa propre demande sensible » (Q30).
- **Options :**
  - (a) Garder le libre-service, ajouter l'**acceptation explicite par la cible**, la notification de tous les Administrateurs principaux, l'audit ; pour une organisation vérifiée, l'autorité du nouvel Administrateur principal reste « non vérifiée » jusqu'à une revue par l'équipe de vérification.
  - (b) Toute attribution d'Administrateur principal passe par l'équipe de vérification (preuve d'autorité).
  - (c) Bloquer la promotion vers `OWNER` en attendant la matrice des modifications sensibles.
- **Recommandation :** (a) en V1, et (b) pour les organisations de niveau « renforcé » ou « pré-vérification » (Q26). L'acceptation par la cible fournit le second acteur du maker-checker. **Décision utilisateur.** Effort M.

### K3 — Aucun périmètre sur l'appartenance (L0-09 T1, B1) — Q21, Q23

- **Constat :** `Membership` porte un rôle, sans périmètre. Le client exige que le modèle permette « agence, site, branche, département, module, objet ».
- **Recommandation :** ADR 0010 : ajouter un périmètre **additif** (`scope_type` défaut `ORGANIZATION`, `scope_id` nul), seule valeur `ORGANIZATION` active en V1, sans écran avancé. `can`/`authorize_on` reçoivent le périmètre de l'objet visé (offre → ville, plus tard branche). Migration additive, réversible. Évite une refonte après la production. Effort M (modèle) ; L si les capacités par module sont refondues.

### K4 — Invitations limitées à éditeur et analyste ; aperçu sans périmètre (B2a, B2b, F2) — Q23

- **Constat :** `INVITABLE_ROLES = (EDITOR, ANALYST)` ; l'aperçu renvoie `organization_name, org_type, role, expires_at, invited_by_display_name`.
- **Risque nouveau :** l'invitation est un **lien porteur** (LEG-PRV-invit-3). Un lien `ADMIN` transmis à un tiers donne un accès d'administration. L'ADR 0008 §12 n'acceptait ce risque que parce que les rôles étaient limités.
- **Recommandation :**
  1. Terminer F2 sur le contrat actuel (cohérent et sûr) ; ne pas élargir en cours de route.
  2. Lot additif B7/F2-bis après ADR 0010 : `ADMIN` invitable si `can_manage_role_of(rôle de l'émetteur, ADMIN)` ; ressaisie du mot de passe de l'émetteur pour une invitation `ADMIN` ; aperçu enrichi de `scope` et `capabilities` (champs additifs) ; pour `ADMIN`, **une** des parades suivantes : rattacher l'invitation à un téléphone vérifié (option B de l'ADR 0008), ou activation après confirmation de l'émetteur. Revue `auditeur-securite` obligatoire.
  3. « Simple membre » : aucun rôle de ce nom n'existe (question §5, QO-6).
- Effort M.

### K5 — Plafond de 10 organisations affiché (L0-09, B2b, front) — Q22

- **Constat :** refus `409 organization_limit_reached` à la création et à l'acceptation ; valeur exposée par `GET organizations/limits/` ; message front « nombre maximal d'organisations ». Validateur : 1 à 100.
- **Options :** (a) seuil technique élevé et caché, refus neutre au-delà ; (b) au-delà d'un seuil, la création est permise mais **mise en revue** (signal de risque) ; (c) supprimer toute limite.
- **Recommandation :** (b), plus une limite de débit de création par compte (throttle), sans valeur affichée. Retirer `max_organizations_per_account` de la réponse `limits/` (changement de contrat : le front ne doit plus l'afficher). Les valeurs sont à proposer par l'équipe (le client le demande) et à valider par l'utilisateur ; aucune valeur n'est fixée ici. ADR 0009 §6 à corriger (« 10 organisations par compte : anti-abus »). Effort M.

### K6 — Garde de suppression de compte et blocages (T9-3, B4 ; F3 à faire) — Q16, Q17, Q24

- **Constat :** `assert_account_removable` refuse (409) si le compte est seul propriétaire, sous sanction bloquante ou sous signalement grave. B4 expose ces blocages. Le client veut l'inverse sur deux points : l'utilisateur **peut partir** sous sanction (les preuves restent) ; le dernier Administrateur principal est **averti**, puis l'organisation devient orpheline.
- **Recommandation :**
  - Garder la garde comme règle de **suppression des données**, pas comme règle de **départ**. Introduire un état de compte « fermeture en cours » : connexion fermée, profil masqué, données supprimées ou dissociées par catégorie une fois les obligations résolues (ADR 0012 à produire).
  - **Mettre F3 en pause** et la re-spécifier en « préalables et conséquences de la fermeture » (designer-ux), après la story L1-18.
  - Prérequis techniques déjà connus : TOCTOU de la garde (ADR 0006 §20 T9-3 n° 6 a) ; `payments.has_open_payments` (ADR 0009 §4).
- Effort L (story complète).

### K7 — Règle `last_effective_owner` (B1, ADR 0008 §9)

- **Constat :** le départ ou la rétrogradation qui laisse zéro propriétaire effectif est refusé si l'organisation a des offres actives. Le client (Q24) demande d'« avertir et demander régularisation lorsque possible ».
- **Recommandation :** **compatible**, à garder pour les départs volontaires. Changer seulement les libellés (K1). La fermeture de compte (K6) suit sa propre règle : avertir, puis orpheline.

### K8 — Archivage irréversible et réactivation refusée (L0-09 T9-2) — Q34

- **Constat :** `archive_organization` est « irréversible par l'API » ; `reactivate_organization` refuse une organisation archivée.
- **Recommandation :** ADR 0011 (cycle de vie) : service de **restauration exceptionnelle** par le personnel (motif codé, contrôle de conflit d'intérêts comme la réactivation, revérification des administrateurs, contacts et pièces, audit, même objet). L'archivage par l'Administrateur principal reste. Effort M.

### K9 — Statut d'organisation unique qui mêle sanction et cycle de vie (L0-09, B-SUSP, F-SUSP) — Q17, Q33, Q34

- **Constat :** `Organization.status` porte à la fois `SUSPENDED` (sanction) et `ARCHIVED` (cycle de vie). `suspension_reason` a 4 codes, jamais montrés. L'écran « organisation suspendue » n'affiche aucun motif. Il n'existe ni restriction ciblée, ni état dormant, ni « fermeture en cours ».
- **Recommandation :** ADR 0011 : séparer `lifecycle_status` (Active, Inactive, Fermeture en cours, Archivée) et des **restrictions d'organisation** (objet : catégorie configurable, motif communiqué, périmètre affecté, depuis, action requise, recours, preuves internes). Migration de données : `SUSPENDED` → restriction « organisation entière ». Toutes les gardes `_authorize_member` et la visibilité publique sont touchées : chantier transversal. Effort L.

### K10 — Verrou du nom et renvoi au support (L0-09 T4) — Q19, Q35

- **Constat :** le verrou est conforme. Le message renvoie à un support qui n'existe pas.
- **Recommandation :** garder le verrou. Ajouter la demande de modification du nom (story L1-20). Remplacer le texte par un lien vers l'Aide et Support (L1-21).

### K11 — Avis verrouillés et effacés (L0-10, L0-20, T9-3) — Q15, Q16, Q31

- **Constat :** `update_review` et `delete_review` refusent après réponse du vendeur ; modification limitée à 48 h ; suppression refusée sous signalement grave ; `Review.user` en `CASCADE`.
- **Recommandation :** story L1-22 :
  - suppression par l'auteur toujours possible ; elle retire l'avis et sa réponse de la vue publique ; une copie restreinte est conservée tant qu'un signalement, un recours ou une obligation le justifie (durée configurable) ;
  - « Mettre à jour » après la fenêtre crée une version marquée « actualisé » (la fenêtre de 48 h du CDC §3.4 devient la fenêtre de correction simple) ;
  - `Review.user` en `SET_NULL` (ou dissociation) avec affichage « Ancien utilisateur Connecte+ » et avatar générique ;
  - avatar public actuel ;
  - motif de suppression facultatif, en liste fermée.
- Effort M.

### K12 — Sanctions effacées avec le compte (moderation) — Q16

- **Constat :** `Sanction.user` en `CASCADE`.
- **Recommandation :** dissocier la sanction du compte supprimé et conserver un identifiant anti-abus dérivé (pas la pièce d'identité), durée configurable. Avec L1-18 et L1-24. Effort M.

### K13 — Contact partagé entre contexte personnel et prestataire (L0-10a, T7) — Q5

- **Constat :** un seul `ContactPoint` par compte.
- **Recommandation :** un contact professionnel propre au contexte prestataire (même mécanisme que l'organisation), avec horaires plus tard. Story L1-23. Effort M.

### K14 — Une révélation vaut preuve de contact (option C, L0-25) — Q14, Q31

- **Constat :** voir un numéro ouvre le droit d'avis avec le libellé « Avis après contact ».
- **Recommandation :** pas de contradiction stricte : le client n'interdit pas l'avis. Mais l'indicateur doit être factuel. Distinguer le libellé selon la preuve (« Numéro obtenu via Connecte+ » / « Message échangé via Connecte+ »). Story L1-22. Effort S.

### K15 — Consentement du contact d'organisation par OWNER ou ADMIN (T7) — Q30

- **Recommandation :** capacité dédiée attribuable par l'organisation (via le périmètre de K3), texte du client, maker-checker pour la création ou le changement du contact principal. Story L1-23. Effort M.

### K16 — Specs non codées à réécrire

- **L1-01i** (revendication générique) : contredit Q2.
- **L1-01j** (H8, quatre yeux seulement si contesté) : à compléter par Q26 (escalade, second contrôle, niveaux) et Q17 (état « à régulariser »).
- **L1-01l** (refus `name_reserved`) : contredit Q25.
- **ADR 0009 D7** (aucun pass, Free illimité) : contredit Q28. L'ADR est au statut « proposé » : l'amender avant tout développement de L1-11.

---

## 3. Proposition de re-découpage du backlog

### 3.1. Lignes modifiées

| ID | Modification proposée | Raison |
|---|---|---|
| **L1-01** | Périmètre réduit à : équipe (b, e, f, g, h), invitations (c, d), blocages (k, partie lecture), **plus** les ajustements Q21 à Q23 (B5 à B9 ci-dessous). Sortir i, j, l vers L1-02. | Q2 : la revendication relève de la vérification d'autorité, pas de l'équipe. Permet de clore L1-01. |
| **L1-01-F2** | Terminer sur le contrat actuel. Puis F2-bis (additif). | Éviter un contrat mouvant en cours de tâche. |
| **L1-01-F3** | Statut `Bloqué` (en attente de L1-18). Re-spécifier en « préalables et conséquences de la fermeture du compte ». | Q24. |
| **L1-02** | Devient une ligne parent : « Vérification et autorité des organisations », découpée en L1-02a à L1-02g. | Q3, Q4, Q25, Q26, Q27, Q30. |
| **L1-04** | Ajouter L1-04b (vérification progressive du prestataire). | Q29. |
| **L1-07** | Ajouter les favoris de **profils** (privés, unilatéraux), distincts du suivi et sans consentement marketing. | Q10, Q12. |
| **L1-11** | Ajouter : passes du particulier (Marketplace Selling, Event, Recruitment, Property Rental), Particulier Premium, plafond Free de 10 activations de pass sur 12 mois glissants, « + Publier » contextuel ; amender ADR 0009 D7, §6, §7. | Q28. |
| **L2-09** | Ajouter : canal de communication externe générique ; messagerie contextuelle réutilisable (support compris). | Q13, Q19. |
| **F-02** | Ajouter : pas d'accès illimité des techniciens aux données de production (comptes d'administration nominatifs, accès journalisé). | Q14. |

### 3.2. Nouvelles lignes

| ID | Tâche | Agents | Lot | Réf. client | Priorité |
|---|---|---|---|---|---|
| **L1-01-R** | Analyse et **ADR 0010 gouvernance d'organisation** : Administrateur principal (libellé, nombre, attribution renforcée), rôle → permissions → périmètre, délégation datée et révocable, anti-abus de création, invitations v2 | analyste-fonctionnel, architecte-technique | 1 | Q3, Q21, Q22, Q23, Q30 | Bloque L1-01 |
| **L1-01-B5** | Libellés « Administrateur principal » (messages backend, notifications) + front (F1-bis) | dev-backend, dev-frontend | 1 | Q3, Q21 | Bloque L1-01 |
| **L1-01-B6** | Périmètre additif sur l'appartenance (`ORGANIZATION` seul actif en V1) ; contrôle d'autorisation par objet | dev-backend, auditeur-securite | 1 | Q21 | Bloque L1-01 |
| **L1-01-B7** | Invitations v2 : `ADMIN` invitable selon délégation, ressaisie de l'émetteur, aperçu avec périmètre et accès, parade contre le lien porteur (+ F2-bis) | dev-backend, dev-frontend, auditeur-securite | 1 | Q23 | Bloque L1-01 |
| **L1-01-B8** | Anti-abus de création d'organisations : fin du plafond affiché, throttle de création, signal de risque, file de revue | dev-backend, dev-frontend | 1 | Q22 | Bloque L1-01 |
| **L1-01-B9** | Attribution et transfert d'Administrateur principal : acceptation de la cible, notification des Administrateurs principaux, revue selon le niveau (décision K2) | dev-backend, dev-frontend, auditeur-securite | 1 | Q21, Q23, Q30 | Bloque L1-01 |
| **L1-02a** | Niveaux de vérification d'organisation (standard avec grâce configurable de 90 jours, renforcé, pré-vérification) et niveau de risque de l'organisation | analyste, architecte, dev-backend | 1 | Q26 | Avant production |
| **L1-02b** | Matrice documentaire configurable (acteur, forme, activité, secteur, niveau) ; parcours ONG/ASBL | dev-backend, dev-frontend | 1 | Q27 | Avant production |
| **L1-02c** | Indicateur public « Organisation vérifiée » avec détail factuel des contrôles | designer-ux, dev-backend, dev-frontend | 1 | Q3, règle 3 | Avant production |
| **L1-02d** | Autorité du représentant : dates de début et de fin, statut, expiration, revérification | dev-backend | 1 | Q3, Q4 | Avant production |
| **L1-02e** (ex-L1-01i) | Récupération d'autorité et conflits d'autorité (dont récupération d'anciens comptes) ; aucune fiche précréée | analyste, dev-backend, dev-frontend, auditeur-securite | 1 | Q2, Q3, Q26 | Avant production |
| **L1-02f** (ex-L1-01j) | Organisation « sans administrateur principal / à régulariser » : état visible, récupération formelle, décision par l'équipe de vérification, escalade, second contrôle | dev-backend, dev-frontend, auditeur-securite | 1 | Q17, Q26 | Avant production |
| **L1-02g** (ex-L1-01l) | Noms protégés : liste configurable, vérification renforcée avant représentation publique, variantes comme signaux (aucun refus) | dev-backend | 1 | Q1, Q25 | Avant production |
| **L1-04b** | Vérification progressive du prestataire : matrice de risque par catégorie, identité, qualification, licence ; badges factuels ; anti-contournement ; questionnaire privé de conformité | analyste, architecte, dev-backend, dev-frontend, auditeur-securite | 1 | Q3, Q29 | Avant production |
| **L1-17** | Cycle de vie de l'organisation (Active, Inactive, Fermeture en cours, Archivée, Supprimée) et restauration exceptionnelle ; **ADR 0011** | architecte, dev-backend, dev-frontend | 1 | Q34 | Avant production |
| **L1-18** | Fermeture de compte en libre-service (états, obligations, dissociation, orpheline) ; **ADR 0012** | analyste, architecte, dev-backend, dev-frontend, auditeur-securite | 1 | Q16, Q24 | Avant production |
| **L1-19** | Restrictions et sanctions d'organisation : catégories configurables, motif communiqué, périmètre, action requise, recours ; restriction ciblée | dev-backend, dev-frontend | 1 | Q17, Q33 | Avant production |
| **L1-20** | Changement de nom contrôlé : dénomination légale, nom d'affichage, historique, demande et revérification | dev-backend, dev-frontend | 1 | Q1, Q35 | Avant production |
| **L1-21** | Aide et Support minimal de lancement : canal externe sans authentification, formulaire ou ticket, coordonnées configurables, liens depuis les messages d'erreur | analyste, designer-ux, dev-backend, dev-frontend | 1 | Q19 | Avant production |
| **L1-22** | Avis : modifier, actualiser, supprimer avec motif ; copie restreinte ; dissociation « Ancien utilisateur Connecte+ » ; avatar ; indicateur d'interaction factuel ; texte sous 3 avis | dev-backend, dev-frontend | 1 | Q14, Q15, Q16, Q31, Q32 | Avant production |
| **L1-23** | Contact : contact pro du prestataire, consentement contextuel et historisé, information avant accès, rappel anti-démarchage, écran WhatsApp, réponse progressive anti-scraping, accès exceptionnel du personnel, gestion du contact d'organisation | dev-backend, dev-frontend, auditeur-securite | 1 | Q5, Q6, Q8, Q11 à Q14, Q30 | Avant production |
| **L1-24** | Politique de conservation configurable par catégorie, legal hold, purges planifiées (pièces, traces d'accès, avis, sanctions, table legacy) | architecte, dev-backend, auditeur-securite | 1 | Q4, Q8, Q15, Q16, Q18 | Avant production |
| **L1-25** | Migration des anciens comptes entreprise : séquence de notifications (e-mail, SMS, in-app), parcours de récupération | analyste, dev-backend, dev-frontend | 1 | Q18, Q20 | Avant production (si comptes réels, QO-1) |
| **L2-12** | Gestion de dossiers de support complète (centre d'aide, diagnostic, routage, escalade, recours, métriques) | analyste, architecte, dev-backend, dev-frontend | 2 | Q19, §3 du client | Plus tard |
| **DOC-01** | Matrice Sanctions, Modération et Enforcement (dont remédiation organisationnelle) | analyste-fonctionnel | — | §3 du client, Q16, Q17, Q33 | Avant production |
| **DOC-02** | Matrice des modifications organisationnelles sensibles | analyste-fonctionnel, auditeur-securite | — | §3, Q30, Q35 | Avant production |
| **DOC-03** | Architecture Help, Support et Case Management (cible) | analyste, architecte | — | §3, Q19 | Avant production |
| **DOC-04** | Économie informelle, formalisation et fiscalité RDC (recherche) | analyste (avec conseil juridique du client) | — | §3 | Plus tard |
| **DOC-05** | Étude des appels vocaux (WebRTC vs PSTN masqué) | architecte-technique | — | §3 | Plus tard |
| **DOC-06** | Favoris et Partenariats professionnels (définitions, états) | analyste | — | §3, Q12 | Plus tard (favoris : avec L1-07) |
| **DOC-07** | Taxonomie V1 (catégories, synonymes FR/EN/lingala) et matrices de vérification | analyste | — | §3, Q27, Q29 | Avant production |
| **DOC-08** | Stratégie de lancement et onboarding institutionnel (séparation commercial / vérification) | analyste | — | §3, Q26 | Avant production |
| **TROC-01** | Proposition structurée sur le troc (plan au §7) | analyste, architecte, designer-ux | — | Q36 | Plus tard (attendu par le client) |

### 3.3. Ordre conseillé

1. **Maintenant :** terminer et valider F2 (contrat actuel). Mettre F3 en pause. Mettre à jour `questions.md` (journal des réponses) et le backlog.
2. **Décisions utilisateur** (une séance) : K2 (attribution d'Administrateur principal), K4 (parade du lien porteur pour `ADMIN`), K5 (forme de l'anti-abus), extension du périmètre V1 (Q24, Q28, Q19, périmètre Q21), sortie de i/j/l de L1-01.
3. **L1-01-R** (analyste puis architecte, ADR 0010). En parallèle : **amendement de l'ADR 0009** pour Q28 (avant tout code de L1-11).
4. **L1-01-B5** (libellés, rapide) dès F2 fusionnée ; puis **B6 → B7 ‖ B8 → B9** ; recette L1-01 ; clôture de L1-01.
5. **ADR 0011** (cycle de vie + restrictions) puis **L1-17, L1-19, L1-20** ; en parallèle **L1-02a à L1-02g** (vérification et autorité).
6. **ADR 0012** (fermeture de compte et conservation) puis **L1-18, L1-22, L1-24** (ils partagent la dissociation et les durées) ; reprendre F3 re-spécifiée.
7. **L1-23** (contact) et **L1-21** (support minimal) avant la recette du lot 1 (L1-16).
8. **DOC-01, DOC-02, DOC-07, DOC-08** au fil de l'eau (ils alimentent L1-02, L1-19, L1-04b). **TROC-01** dès qu'un analyste est disponible : le client attend la proposition.

---

## 4. Propositions de modification du CDC (diff texte, non appliquées)

**§0.4 Glossaire — ajouter**
- Nouveau : `Administrateur principal | Rôle le plus élevé d'une organisation sur Connecte+. Il ne désigne ni la propriété juridique ni la représentation légale.`
- Nouveau : `Périmètre | Où et sur quoi un rôle s'applique : organisation entière, puis ville, site, branche, département, module ou objet.`

**§3.1 — tableau des contextes, ligne Personnel**
- Ancien : `Noter, suivre, acheter un billet, s'abonner, donner, postuler, publier une offre personnelle`
- Nouveau : `Noter, suivre, acheter un billet, s'abonner, donner, postuler ; publier une vente personnelle, un recrutement privé, un événement ou une location de son propre bien avec le pass correspondant ou le plan Particulier Premium`

**§3.1 — ligne Organisation**
- Ancien : `Création, revendication ou invitation`
- Nouveau : `Création par une personne autorisée, invitation, ou récupération d'un ancien compte après vérification d'autorité`

**§3.1 — Organisations, puce « Vérification KYB »**
- Ancien : `Vérification KYB : RCCM ou arrêté d'enregistrement (ONG), identification nationale, pièce du représentant. Le badge affiche précisément ce qui a été vérifié (par exemple « RCCM vérifié »).`
- Nouveau : `Vérification progressive selon le niveau de risque (standard, renforcé, pré-vérification obligatoire pour banques, Mobile Money, télécoms, ministères et grandes entités publiques) et selon une matrice documentaire configurable. L'indicateur public « Organisation vérifiée » détaille les contrôles faits (par exemple « RCCM vérifié ») ; il n'est ni une recommandation ni une garantie. Authentification, identité, organisation, autorité et qualification sont vérifiées séparément.`

**§3.1 — Organisations, puce « Rôles »**
- Ancien : `Rôles dans l'organisation : propriétaire, administrateur, éditeur, analyste. Le départ d'un membre retire son accès sans supprimer son compte personnel.`
- Nouveau : `Rôles dans l'organisation : administrateur principal, administrateur, éditeur, analyste ; chaque rôle s'exerce dans un périmètre. Une invitation peut proposer tout rôle que l'émetteur peut déléguer, sauf administrateur principal. Le départ d'un membre retire son accès sans supprimer son compte personnel. Aucun membre n'est promu automatiquement.`

**§3.1 — Organisations, puce « revendication »**
- Ancien : `Une revendication d'organisation existante ne donne aucun droit avant validation.`
- Nouveau : `Connecte+ ne crée aucune fiche d'organisation à l'avance. Une demande de récupération (ancien compte) ou un conflit d'autorité ne donne aucun droit avant la décision de l'équipe de vérification, avec escalade et second contrôle pour les cas ambigus. Une organisation qui perd son dernier administrateur principal passe à l'état « administration à régulariser ».`

**§3.1 — ajouter une puce « Cycle de vie et suspension »**
- Nouveau : `Cycle de vie : active, inactive, fermeture en cours, archivée, supprimée. Les restrictions et suspensions sont séparées du cycle de vie ; les administrateurs voient la catégorie, le motif, le périmètre affecté, la date, l'action requise et le recours. Une organisation archivée peut être restaurée à titre exceptionnel par le personnel, avec audit. Le nom vérifié ne se modifie que par une demande contrôlée.`

**§3.1 — ajouter une puce « Fermeture de compte »**
- Nouveau : `L'utilisateur peut demander la fermeture de son compte. La fermeture est différée tant qu'une obligation reste ouverte (paiement, remboursement, litige). Les sanctions et preuves nécessaires sont conservées ; les avis légitimes restent sous la mention « Ancien utilisateur Connecte+ ».`

**§3.4 — tableau, ligne « Un avis par interaction »**
- Ancien : `Modifiable pendant 48 heures`
- Nouveau : `Corrigeable pendant 48 heures ; ensuite l'auteur peut le mettre à jour (mention « actualisé ») ou le supprimer à tout moment, avec un motif facultatif`

**§3.4 — tableau, ligne « Affichage »**
- Ancien : `Moyenne, nombre d'avis et ancienneté affichés ensemble ; « Pas encore d'avis » en dessous de 3 avis`
- Nouveau : `« Pas encore d'avis » à 0 avis ; à 1 ou 2 avis éligibles, les avis et leurs notes sont visibles, sans moyenne ; à partir de 3, moyenne, nombre d'avis et ancienneté. Auteur affiché en « Prénom + initiale » avec son image publique actuelle.`

**§3.5 — paragraphe Plans**
- Ancien : `Les plans Particulier Premium, Professionnel, Business et Business Pro (document 05 du client) donnent des quotas : […] le gratuit reste utile (publication et découverte).`
- Nouveau : `Les plans Particulier Premium, Professionnel, Business et Business Pro donnent des quotas : […]. Le particulier gratuit peut activer des passes (vente Marketplace personnelle, recrutement privé, événement, location de son bien), dans la limite configurable de 10 activations sur 12 mois glissants ; le Particulier Premium les inclut. Une activité commerciale récurrente passe par le contexte prestataire. Le gratuit reste utile (découverte, achat, candidature, messagerie).`

**§3.15 — Lot 1, Contact (ajout)**
- Nouveau : `Le titulaire voit l'historique des accès à ses coordonnées. Avant l'accès, le visiteur est informé que son accès est visible du titulaire et que la coordonnée ne doit pas servir au démarchage. Une information précède toute sortie vers WhatsApp.`

**§3.15 — Notifications**
- Ancien : `SMS réservés à l'OTP et à la sécurité`
- Nouveau : `SMS réservés à l'OTP, à la sécurité et aux notifications de migration et de récupération des anciens comptes`

**§3.17 — ajouter une ligne « Aide et Support »**
- Nouveau : `Aide et Support | Centre d'aide, tickets structurés, canal externe sans authentification, coordonnées configurables | 1 (minimum de lancement), 2 (gestion de dossiers)`

**§7 — tableau du modèle économique, ligne Particulier Premium**
- Ancien : `Particulier Premium | Particulier | 2 $ / mois | 1`
- Nouveau : `Particulier Premium | Particulier | environ 50 $ / an (hypothèse du client, non finale) | 1` — **à confirmer** : écart avec le modèle financier du document 04 (QO-3).

**§7 — ajouter une ligne**
- Nouveau : `Passes du particulier (vente, recrutement privé, événement, location) | Particulier | prix à fixer | 1 (vente), 2 (recrutement, événement)`

**§11.1 — ligne `identity`** : ajouter les objets retenus par les ADR 0010 à 0012 (périmètre, restriction d'organisation, demande de changement de nom, autorité datée).

---

## 5. Questions encore ouvertes et contradictions internes

### 5.1. Contradictions internes ou avec le CDC

| # | Constat | Options | Recommandation |
|---|---|---|---|
| **CI-1** | Q21 refuse « plusieurs propriétaires » mais admet « un ou plusieurs Administrateurs principaux ». | (a) Nombre libre ; (b) nombre plafonné par réglage ; (c) un seul en V1. | (a) avec la procédure renforcée de K2 ; la différence porte sur la manière d'être nommé, pas sur le nombre. |
| **CI-2** | Q28 : Premium ≈ 50 $/an. CDC §7 (modèle financier, doc 04) : 2 $/mois (24 $/an). | — | Prix en back-office (règle 11) ; demander au client lequel fait foi. |
| **CI-3** | Q28 : la vente personnelle exige un pass. CDC §3.1 et §7 : « le gratuit reste utile : publier des offres en quantité limitée ». | — | Q28 prime (source 1). Mettre le CDC à jour (§4). Prévoir la transition des offres personnelles déjà publiées (QO-4). |
| **CI-4** | Q3 recommande « Organisation vérifiée ». CDC §3.1 et règle 3 : « un badge dit précisément ce qui a été vérifié ». | (a) Libellé générique seul ; (b) libellé générique + détail factuel. | (b) : conforme aux deux (L1-02c). |
| **CI-5** | Q5, Q9, Q13, Q28, Q36 évoquent commande, livraison, devis, réservation, restaurants, location immobilière. CDC §1.4 et CLAUDE.md §3.2 : vente en ligne, restaurants, livraison hors V1. | — | Lire ces mentions comme la vision cible. Ne rien développer hors V1 sans accord écrit. Demander si « Property Rental Pass » crée une catégorie d'offre en V1 (QO-5). |
| **CI-6** | Q15 : modifier ou actualiser à tout moment. CDC §3.4 : « Modifiable pendant 48 heures ». | — | Q15 prime ; diff CDC au §4. |
| **CI-7** | Q20 : SMS pour la migration. CDC §3.15 : SMS réservés à l'OTP et à la sécurité. | — | Q20 prime ; coût SMS à budgéter (CDC §9.3). |
| **CI-8** | Q23 cite « simple membre ». Q21 ne liste que quatre rôles (Administrateur principal, Administrateur, Éditeur/Gestionnaire, Analyste). | (a) « Simple membre » = Analyste ; (b) nouveau rôle de lecture minimale. | Question au client (QO-6). |

### 5.2. Questions encore ouvertes

| # | Question | Destinataire | Pourquoi |
|---|---|---|---|
| **QO-1** | Existe-t-il de **vrais** anciens comptes entreprise à migrer ? L'ADR 0002 dit qu'aucune donnée de production n'existe. | Client | Q18 et Q20 (L1-25) sont sans objet sinon. |
| **QO-2** | Q2 (Q-L1-6) n'est pas répondu sur deux points : l'administrateur en place est-il prévenu d'une contestation d'autorité, avec ou sans l'identité du demandeur ? Peut-il répondre dans l'application ? | Client | L1-02e. |
| **QO-3** | Prix de référence du Particulier Premium : 50 $/an (Q28) ou 2 $/mois (doc 04) ? | Client | Mise en vente. |
| **QO-4** | Que deviennent les offres personnelles déjà publiées sans pass quand le pass devient obligatoire ? Une « activation de pass » = un achat, ou une publication ? Durée d'un pass ? | Client | L1-11 ; aucun chiffre ne doit être inventé. |
| **QO-5** | « Property Rental Pass » : la location immobilière entre-t-elle en V1 comme catégorie d'offre ? | Client, utilisateur | Périmètre V1. |
| **QO-6** | « Simple membre » : rôle distinct ou analyste ? | Client | L1-01-B7. |
| **QO-7** | Grâce de 90 jours (Q26) : que se passe-t-il à l'échéance sans vérification (masquage, restriction de publication, rappel seulement) ? | Client | L1-02a. |
| **QO-8** | Seuils d'inactivité (dormante) et délai avant restriction puis archivage d'une organisation orpheline (Q17, Q34) : l'équipe propose, qui valide ? | Client | L1-17, L1-02f ; aucune valeur inventée. |
| **QO-9** | Délai de traitement annoncé pour une vérification ou une récupération (ancienne Q-L1-8, non répondue). | Client | L1-02e. |
| **QO-10** | Historique d'accès d'une organisation : quels rôles le voient ? | Client | L1-23. |
| **QO-11** | CAPTCHA (Q11) : service externe acceptable ? Lequel ? | Utilisateur | Dépendance externe, CLAUDE.md §1. |
| **QO-12** | Encore ouvertes, non couvertes par Q1 à Q36 : LEG-PRV-invit-1 à 3 (conservation des invitations, étiquette libre, lien porteur), Q-L1-1, 2, 4, 5, 7, 9 (questions du CP), Q-CLI9 à Q-CLI23 (plans et paiements, sauf ce que Q28 tranche), L2-06 (dons), L2-10 (Meta). | Client, utilisateur | Restent dans `questions.md`. |
| **QO-13** | Toutes les durées (Q4, Q8, Q11, Q15, Q16, Q18) sont « à proposer par l'équipe, à valider juridiquement ». Qui, chez le client, valide la grille proposée ? | Client | L1-24 ; avant production. |

### 5.3. Décisions à demander à l'utilisateur (CLAUDE.md §1)

1. **Extension du périmètre V1** : fermeture de compte libre-service (Q24), passes du particulier (Q28), module Aide et Support (Q19), modèle de périmètre (Q21), vérification progressive du prestataire (Q29). Impact planning et budget.
2. **K2** : procédure d'attribution d'Administrateur principal.
3. **K4** : parade du lien porteur pour une invitation `ADMIN`.
4. **K5** : forme de l'anti-abus de création d'organisations.
5. **K9** : séparation du statut d'organisation (migration de données, changement de contrat `status`, `unavailable`).
6. Sortie de L1-01i, j, l de L1-01 vers L1-02.

---

## 6. Points qui touchent une règle verrouillée (CLAUDE.md §4)

| Règle | Décision du client | Verdict | Vigilance |
|---|---|---|---|
| 1. Compte unique, contextes | Q21, Q22, Q28 (« un même compte humain agit dans plusieurs contextes »). | **Renforcée.** | Q28 cite « Premium » et « Employeur particulier » parmi les contextes. Premium est un **plan**, jamais un contexte ni un type de compte. L'employeur particulier est le contexte personnel avec un pass. |
| 2. Permissions ≠ droits commerciaux | Q28 (pass ouvre la publication), Q29 (vérification avant activation publique). | **Compatible.** | Un pass ouvre une capacité (`DENY_ENTITLEMENT`), jamais un rôle. Ordre du client « éligibilité → permission → entitlement » ; ADR 0009 §7 : « permission → éligibilité → entitlement ». Les deux ordres refusent avant le droit commercial ; garder l'ordre de l'ADR (un refus de permission ne révèle pas l'état du plan). La vérification d'identité du prestataire est une condition d'éligibilité, jamais achetable. |
| 3. Vérification non achetable | Q3, Q26 (l'équipe commerciale ne valide jamais), Q29 (badges factuels). | **Renforcée.** | « Organisation vérifiée » doit détailler les contrôles (CI-4). Un nom protégé n'est pas une vérification (Q25). Onboarding assisté : séparer les permissions commerciales et de vérification dans `setup_roles`. |
| 4. Aucun score de confiance universel | Q29 (questionnaire privé « le service correspondait-il ? »), Q22 et Q11 (signaux de risque internes). | **Compatible sous condition.** | Le questionnaire et les signaux de risque ne doivent produire **aucune** note publique ni agrégat transversal, ni entrer dans le classement organique. Usage : signal de modération seulement. À inscrire dans L1-04b et DOC-01. |
| 5. « Sponsorisé » | Non touchée. | — | — |
| 6. Aucune commission en % | Q28 (prix de pass fixes). | **Compatible.** | Prix en montant, configurables. |
| 7. Paiement confirmé par signature | Non touchée. | — | Achat de pass : même chaîne que L1-12. |
| 8. États indépendants | Q24 (fermeture), Q33, Q34 (cycle de vie ≠ sanction). | **Renforcée.** | Le statut unique d'organisation actuel (K9) est en tension avec l'esprit de la règle. |
| 9. Ni portefeuille ni séquestre | Q5 (destination de paiement distincte), Q36 (troc avec argent). | **Vigilance.** | Un troc « objet + argent » imposerait un paiement de bien (hors V1) ; jamais de séquestre pour garantir une remise. |
| 10. Données par finalité | Q5 à Q14, Q31 (jamais de selfie KYC comme avatar). | **Renforcée.** | Q7 permet un numéro **professionnel** public : conforme (la règle vise adresse exacte, pièces, GPS ; le numéro personnel du particulier reste privé). Q8 révèle au titulaire l'identité publique du visiteur : information préalable obligatoire. |
| 11. Configurable | Toutes les durées, catégories de suspension, noms protégés, matrice documentaire, grâce de 90 jours, 10 activations, coordonnées du support. | **Renforcée.** | Aucune de ces valeurs ne doit être codée en dur. |
| 12. Audit | Q14 (accès exceptionnels), Q18, Q21, Q26, Q30, Q34, Q35. | **Renforcée.** | Nouveaux codes d'audit à prévoir dans ADR 0010 à 0012. |

---

## 7. Plan de la proposition « troc » (Q36)

Livrable futur : `docs/specs/TROC-01-proposition.md`, rédigé par `analyste-fonctionnel`, chiffré par `architecte-technique`, parcours par `designer-ux`. Il répond point par point aux attentes de Q36.

1. **Besoin et cas d'usage** : utilisateurs concernés (particuliers, petits commerçants informels), exemples à Kinshasa, fréquence attendue ; valeur par rapport à la vente et au don ; sources (aucune dans le dossier client avant Q36).
2. **Modèles d'échange** : objet ↔ objet ; plusieurs objets ↔ un objet ; objet + argent ↔ objet ; offre et contre-proposition ; remise en main propre ou livraison. Pour chacun : faisabilité V1. Hypothèse à instruire : exclure « objet + argent » et la livraison (paiement de bien et logistique hors V1 ; règle 9).
3. **Parcours et états** : publication → proposition → contre-proposition → acceptation bilatérale → accord enregistré → remise → confirmations → terminé ou litige. États propres au troc, indépendants des autres objets (règle 8). Cas limites : annulation, remise unilatérale, absence de confirmation, délai d'expiration.
4. **Biens autorisés et interdits** : réutilisation de `ForbiddenItem` et des catégories ; anti-contournement (troc utilisé pour masquer une vente interdite).
5. **Risques et contrôles** : fraude, contrefaçon, fausse description, bien défectueux, non-remise, non-conformité ; signalement, preuves (photos, messages), articulation avec la modération et les sanctions (DOC-01). Principe : l'absence d'argent ne crée pas une zone moins contrôlée.
6. **Rôle de Connecte+ en litige** : enregistrer, constater, faciliter, modérer, sanctionner, orienter. Aucune garantie, aucun séquestre, aucun arbitrage de valeur.
7. **Avis après troc** : preuve d'interaction requise (confirmations des deux parties) ; libellé factuel ; aucune note universelle (règle 4).
8. **Intégration technique et effort** : existant masqué (`Offer.is_exchangeable`, `ExchangeProposal`, `MarketplaceSettings.exchange_enabled`, L0-14) ; dépendances (messagerie L2-09, modération, notifications) ; estimation par option.
9. **Options et recommandation** : A) V1 ; B) architecture prévue, activation reportée ; C) ne pas intégrer ; D) autre (par exemple « ouvert à l'échange » comme simple mention sur une offre, sans parcours transactionnel). Hypothèse de départ à vérifier : B ou D, parce que la V1 n'a pas de notion de transaction de bien.
10. **Questions au client** et critères d'acceptation de la recommandation retenue.

Effort de la proposition : M. Prérequis : DOC-01 (matrice des sanctions) aide pour le point 5, sans le bloquer.

---

## 8. Fichiers à mettre à jour ensuite (par le CP, pas par ce document)

- `questions.md` : remplir le « Journal des réponses » (Q1 à Q36 ↔ identifiants), marquer les questions répondues, ajouter QO-1 à QO-13.
- `docs/suivi/BACKLOG.md` : lignes du §3.
- `docs/suivi/JOURNAL.md` : entrée « réponses du client reçues, analyse d'impact ».
- ADR 0006 (amendé par 0010 et 0011), ADR 0008 (§3.2, §8.2, §12, §15), ADR 0009 (D7, §6, §7), ADR 0005 (C2, C12, §9).
- Specs : `L1-01-organisations.md` (i, j, l retirés ou renvoyés), `L1-01-contrat-api.md` (aperçu additif, `limits/`), `L1-11-L1-12-plans-paiements.md` (passes, Premium), `avis-classement-contact.md` (Q15, Q16, Q31, Q32).
