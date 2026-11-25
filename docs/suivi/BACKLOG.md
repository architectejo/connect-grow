# Backlog — Connecte+

Tenu par le chef de projet (Claude Code). Statuts : `À faire`, `En cours`, `En relecture`, `En test`, `Fait`, `Bloqué`.
Référence : CDC v1.2 (`docs/CDC_Connecte+_v1.2.md`). État initial au 06/10/2026.

## Lot 0 — Mise en conformité de l'existant (à faire en premier)

Le code existant a été écrit sur la base du CDC v1.0. Ces tâches l'alignent sur la v1.2 avant d'ajouter de nouvelles fonctions. Ordre conseillé : L0-01 → L0-02 → L0-03 → L0-04 → L0-05, puis le reste.

| ID | Tâche | Agents | Statut | Réf. CDC |
|---|---|---|---|---|
| L0-01 | Dépôt Git unique à la racine (historique des deux dépôts conservé), puis CI GitHub Actions (tests backend SQLite, lint/test/build front), `.gitignore` vérifié | devops | Fait (CI, tests front en place) ; une seule branche `main` depuis le 24/10/2026 ; rien poussé (remote à désigner) | §5.11 |
| L0-02 | SQLite seul : sortir `mysqlclient` de `requirements.txt` vers `requirements-mysql.txt`, retirer les dépendances système MySQL du Dockerfile, archiver `docker-compose.mysql.yml` | devops | Fait (relu, fusionné dans `backend`, branche `chore/L0-02-sqlite-seul`) | §2.5, ADR 0001 |
| L0-03 | Supprimer Redis : `CHANNEL_LAYERS` en `InMemoryChannelLayer`, retirer `channels_redis`, le service Redis des compose et les variables `REDIS_*` | dev-temps-reel, devops | Fait (code et compose ; 98 tests verts, relu) | §5.5 |
| L0-04 | Supprimer le code mort : apps non installées `users`, `offers`, `exchanges`, `chat`, `notifications`, dossier `backend/scratch/`, ancien front `connecte-plus-hub/` (après vérification qu'aucun import n'y renvoie) | architecte-technique (vérif), dev-backend | Fait (apps mortes absentes, `scratch/` supprimé le 09/10/2026) | — |
| L0-05 | Décider par ADR de la réinitialisation des migrations (aucune donnée de production) pour passer aux clés UUID et à la structure cible des modules | architecte-technique | Fait (ADR 0002 accepté ; R1 à R3 exécutés côté backend ; reste F1 front) | §5.4, §11.1 |
| L0-05-R1 | Reset R1 : `common`, `identity` (ex-`accounts`), `catalog`, `AUTH_USER_MODEL`, UUID (inclut L0-06). Un seul agent, une seule branche `chore/L0-05-reset-migrations` | dev-backend | Fait (relu, audité, 235 tests ; fusionné dans `backend`) | ADR 0002 |
| L0-05-R2 | Reset R2 : `marketplace` (`Offer`, `is_deleted`, inclut L0-12 et L0-15), `visibility`, `reviews`, `notifications`, `messaging` | dev-backend | Fait (relu, audité, fusionné dans `backend`) | ADR 0002 |
| L0-05-R3 | Reset R3 : `moderation`, `payments`, cron, `setup_roles`, import-linter, régénération des `0001`, `migrate` sur base vierge | dev-backend | Fait (relu, audité, fusionné dans `backend`) | ADR 0002 |
| L0-05-F1 | Front : ids en `string` (UUID), en parallèle de R1 à R3 | dev-frontend | Fait (relu, audité, 78 tests ; fusionné dans `frontend`) | ADR 0002 |
| L0-06 | Créer le module `catalog` (City, Commune, Category, ForbiddenItem) et supprimer les clés étrangères entre domaines (ex. `accounts.User` → `marketplace.City`) | architecte-technique, dev-backend | Fait (module `catalog` livré avec R1) | §5.3, §5.4 |
| L0-07 | Retirer le Trust Score : `User.trust_score`, `TrustScoreSettings`, facteur de confiance de `ranking`, `TrustScore.tsx` et `lib/trust.ts` ; remplacer par note d'offre et note vendeur affichées (moyenne, nombre, ancienneté) ; retirer aussi le badge « Vendeur fiable » et `avg_rating` issu du Trust Score. Stories : `docs/specs/avis-classement-contact.md` | analyste-fonctionnel, architecte-technique, dev-backend, dev-frontend | Fait (backend + front ; relu, audité ; 678 tests backend, 155 front) | §3.4, règle 4 |
| L0-08 | Remplacer le classement par le score organique P × E × R × D, sans note ; pondérations en base | dev-backend | Fait (score E×R stocké, proximité à la lecture, recalcul horaire) | §3.5 |
| L0-09 | Compte unique et contextes : remplacer `user_type` PARTICULIER/BUSINESS et `BusinessProfile` par `Organization`, `Membership`, rôles d'organisation et contexte actif | analyste-fonctionnel, architecte-technique, dev-backend, dev-frontend | Fait (T1 à T10 : conversion et contraction du modèle comptes entreprise, purge de compte, écran organisation suspendue ; recette T10 validée ; 1739 tests backend, 732 front) | §3.1, §5.4, règle 1 |
| L0-10 | Avis : ouvrir le droit d'avis après prise de contact enregistrée (au lieu de l'« affaire conclue »), double note offre + vendeur, libellé « Avis après contact » ; supprimer `Deal` (D1). Stories : `docs/specs/avis-classement-contact.md` | dev-backend, dev-frontend | Fait (avis après contact, éligibilité, recours de l'auteur, backend et front) ; `Deal` supprimé | §3.4 |
| L0-10a | **Prérequis de toute recette ouverte (fuite règle 10) — étape -a faite (retrait de `phone`, test de non-fuite, oracle d'inscription du téléphone corrigé, 539 tests backend / 85 front) ; restent -b à -e (consentement par canal, action de contact avec révélation, limites, journalisation) :** retirer `phone` du `SellerSerializer` public ; action de contact authentifiée, throttlée et journalisée (appel / WhatsApp / message) qui enregistre la prise de contact et révèle le contact avec le consentement du vendeur ; adapter les boutons du front. À traiter avec L0-10 ; question LEG-PRV associée | dev-backend, dev-frontend, auditeur-securite | Fait (backend 972 tests, front 283 ; recette QA acceptée ; reste dette LEG-PRV et déploiement) | §3.15, règle 10 |
| L0-11 | Versionner l'API sous `/api/v1/` (backend + `VITE_API_URL` et client front) | dev-backend, dev-frontend | Fait (API sous `/api/v1/`, pagination plafonnée, OpenAPI via drf-spectacular ; ADR 0007 ; 1760 tests backend, 739 front) | §5.9 |
| L0-12 | Renommer `is_delete` en `is_deleted` ; renommer `Post` en `Offer` si validé par l'ADR L0-05 | dev-backend | Fait côté backend (R2) ; noms d'API conservés jusqu'à L0-11 | Fait (noms d'API alignés avec L0-11) |
| L0-13 | Paiements : geler `payments.Transaction` (vente d'annonce, hors V1) derrière un interrupteur ; le module sera refondu en L1-12 | dev-paiements | Fait (module déjà inerte : aucune route ; tests de gel ; interrupteur à livrer avec L1-12) | §3.14 |
| L0-14 | Troc (`is_exchangeable`, `ExchangeProposal`) : masquer derrière un interrupteur en attendant la confirmation du client | dev-backend, dev-frontend | Fait (backend réglage exchange_enabled ; front useFeatures ; 984 tests backend, 299 front) | §8.3 |
| L0-15 | Fusionner les doublons `Conversation`/`Message` dans un futur module `messaging` (préparation du lot 2) | architecte-technique | Fait (R2, module `messaging`) | §3.15 |
| L0-16 | Table outbox et commande de diffusion des événements de domaine (app `platform_core`, ADR 0003) | architecte-technique, dev-backend | Fait (relu, audité, 504 tests ; fusionné dans `backend`) | §5.4 |
| L0-17 | Rattrapage du front (phases 0 à 4, livrées hors circuit) : lint à 0 erreur, audit sécurité, relecture | dev-frontend, auditeur-securite, relecteur-code | Fait (lint 0 erreur, 15 tests, build vert, audit corrigé, relu ; reste : test du cache PWA en navigateur en recette ; react-router 7 et Tailwind 4 à valider) | §2.4 (DoD) |
| L0-19 | (Fait, fusionné dans `backend`) Correctifs backend issus de F1 : `logout/` sans access valide (refresh seul, `authentication_classes=[]`, throttlé), `CORS_EXPOSE_HEADERS=["Retry-After"]`, retrieve des offres non actives pour leur propriétaire (`my_posts`), filtre `is_verified` de `businesses/` | dev-backend | Fait | §5.9 |
| L0-20 | Mineurs de l'audit du recours : scope de throttle `report_response` distinct de `report` ; `ReportAdmin` sans suppression et `decision_notes` en lecture seule sur un signalement clos ; vérifier l'audit des changements de `ModerationSettings` et `ReviewSettings` ; documenter la non-atomicité du plafond quotidien | dev-backend | Fait (688 tests ; champs `contest_report_id`, `contest_responded`, `can_delete` ; fusionné dans `backend`) | §3.17 |
| L0-18 | Passe finale i18n : sortir les textes en dur des pages du front (à faire après L0-07, L0-09 et L0-14, qui réécrivent plusieurs écrans) | dev-frontend | Fait (garde-fou i18n renforcé, composants shadcn traduits, relu ; lint 0 erreur, 749 tests, build OK) | §4.6 |
| L0-21 | Corrections recette QA backend (R0-01/03/04/05/06/07/08/12) | dev-backend | Fait | recette QA |
| L0-22 | Corrections recette QA front (R0-02/10/11) | dev-frontend | Fait | recette QA |
| L0-23 | Tests au jour local Africa/Kinshasa (4 échecs entre 00 h et 01 h) | dev-backend | Fait | recette QA |
| L0-24 | Corrections audit et relecture du contact vendeur T1/T2 (course de vérification, ContactPoint concurrent, garde SMS, admin OTP) | dev-backend | Fait (836 tests) | ADR 0005 |
| L0-25 | Corrections T4 (délai depuis la remise, nom visiteur nettoyé) | dev-backend | Fait | ADR 0005 |
| L0-26 | Corrections T6 (fixture et contrat, regex, textes) | dev-frontend | Fait | ADR 0005 |
| L0-27 | Corrections recette contact (notification, audit sans chiffres) | dev-backend | Fait | recette QA |
| L0-28 | Cosmétiques recette contact front | dev-frontend | Fait | recette QA |

## Lot 1 — Visibilité

| ID | Tâche | Agents | Statut | Réf. CDC / client |
|---|---|---|---|---|
| L1-01 | Organisations : création, revendication, invitation, membres et rôles | dev-backend, dev-frontend | En cours : contrat v1 livré et validé (B1, B2a, B2b, B4 : 1998 tests backend ; F1, F2 : 1032 tests front, relus et audités) ; gouvernance ADR 0010 en cours (B5 livrée, B6 à B10 et front à faire) ; F3 en pause ; revendication déplacée en L1-02 | §3.1 — IAM-005/006 |
| L1-01-R | Gouvernance après réponses du client : ADR 0010 (Administrateur principal, rôle Membre, périmètre, invitation Administrateur avec confirmation, nomination, anti-abus, organisation sans administrateur principal) | architecte-technique | Fait (ADR 0010 proposé, contrat v2) | Q2, Q3, Q17, Q21-Q26, Q30 |
| L1-01-B5 | Libellé « Administrateur principal » côté backend | dev-backend | Fait (10e5b00 ; 2025 tests) | ADR 0010 |
| L1-01-D2 | Spécifications d'écran de la gouvernance | designer-ux | Fait (`docs/specs/L1-01-ecrans-gouvernance.md`) | ADR 0010 |
| L1-01-B6 | Rôle Membre et périmètre sur l'appartenance | dev-backend | Fait (relu, audité ; périmètre fermé par défaut ; 2091 tests) | ADR 0010 |
| L1-01-B7 | Invitations v2 (Administrateur avec confirmation, aperçu enrichi) + revue sécurité S3 | dev-backend, auditeur-securite | En cours | ADR 0010, Q23 |
| L1-01-B8 | Anti-abus de création d'organisations (fin du plafond de 10) + S5 | dev-backend, auditeur-securite | À faire | ADR 0010, Q22 |
| L1-01-B9 | Nominations d'Administrateur principal, niveau d'assurance, groupe Vérification + S4 | dev-backend, auditeur-securite | À faire | ADR 0010, Q21, Q26, Q30 |
| L1-01-B10 | État « administration à régulariser » et commande `sync_organization_governance` | dev-backend | À faire | ADR 0010, Q17 |
| L1-01-F1bis / F2bis / F4 / F5 / F6 | Front de la gouvernance (libellés, invitations v2, confirmation, nominations, création sans plafond, bannière) | dev-frontend | F1bis fait (1055 tests) ; FVERIF fait (page Vérification, 1061 tests) ; F2bis à F6 à faire après B7 à B10 | ADR 0010 |
| L1-01-F3 | Blocages de suppression dans Paramètres | dev-frontend | En pause (re-spécification avec la fermeture de compte, ADR 0012) | Q24 |
| L1-17 | Cycle de vie et restrictions d'organisation : ADR 0011 (axes séparés, 8 mesures, catégories configurables, `DENY_RESTRICTION`, fermeture, dormance, restauration à double contrôle, changement de nom contrôlé) ; tâches L1-17-B1, L1-19-B2, L1-17-B3, L1-17-B4, L1-20-B5 en série après L1-01 B8 à B10 ; A-L17, D-L17, F-L17-1 à 4 | architecte, analyste, designer, dev-backend, dev-frontend, auditeur-securite | ADR 0011 proposé (contrat `docs/specs/L1-17-contrat-api.md`) ; A-L17 et D-L17 en cours | Q17, Q33-Q35 |
| L1-17 à L1-24 | Cycle de vie et restrictions d'organisation (ADR 0011), fermeture de compte en V1 (ADR 0012), Aide et Support minimal, contacts (Q5-Q14), avis (Q15, Q16, Q31), vérification L1-02a à g, passes du particulier (amendement ADR 0009) | analyste, architecte, dev-* | À faire (voir `docs/specs/impact-reponses-client-Q1-Q36.md` §3) | réponses du client |
| TROC-01 | Proposition troc demandée par le client (options A, B, C) | analyste-fonctionnel, architecte-technique | À faire | Q36 |
| L1-02 | Vérification KYB des organisations avec badge précis | dev-backend, dev-frontend, auditeur-securite | À faire | §3.1 — TRU-003 |
| L1-03 | Page publique d'organisation façon Facebook (onglets, couverture, abonnés) | designer-ux, dev-backend, dev-frontend | À faire | §3.2 — ORG-001 |
| L1-04 | Profil public prestataire individuel | designer-ux, dev-frontend | À faire | §3.2 — ORG-002 |
| L1-05 | Offres : champs v1.2 (« Sur devis », partage social, type de vendeur visible) | dev-backend, dev-frontend | À faire | §3.3 — MKT-001/002 |
| L1-06 | Recherche : filtre par distance et par note, tri par note | dev-backend, dev-frontend | À faire | §3.3 |
| L1-07 | Suivre un profil + notifications de nouvelles publications + préférences + regroupement anti-spam | dev-backend, dev-frontend | À faire | §3.7 — NTF-001 |
| L1-08 | Notifications web push (PWA) et résumé e-mail quotidien | dev-temps-reel, dev-frontend | À faire | §3.7 |
| L1-09 | Partage social : boutons + balises Open Graph | dev-frontend, dev-backend | À faire | §3.8 |
| L1-10 | Localisation : consentement, stockage commune/ville, tri par distance, statistiques de provenance avec seuil de 10 | dev-backend, dev-frontend, auditeur-securite | À faire | §3.9 |
| L1-11 | Plans et droits commerciaux (entitlements) configurables | architecte-technique, dev-backend | À faire | §3.5 — ENT-001/002 |
| L1-12 | Module `payments` générique : interface fournisseur, faux fournisseur, intentions, webhooks, remboursements, rapprochement | architecte-technique, dev-paiements, auditeur-securite | À faire | §3.14 — COM-001/002/006 |
| L1-13 | Promotions : achat, ciblage, emplacements sponsorisés (1 sur 5), libellé, suspension | dev-backend, dev-paiements, dev-frontend | À faire | §3.5 — PRM-001 |
| L1-14 | Graphiques de visibilité par offre, par profil et par promotion ; export CSV | dev-backend, dev-frontend | À faire | §3.6 |
| L1-15 | Back-office : finance, promotions et plans, interrupteurs, seconde authentification | dev-backend, auditeur-securite | À faire | §3.17 |
| L1-16 | Recette du lot 1 | qa-testeur | À faire | §10.3 |

## Lot 2 — Engagement

| ID | Tâche | Agents | Statut | Réf. CDC / client |
|---|---|---|---|---|
| L2-01 | Événements et calendrier par ville (.ics) | designer-ux, dev-backend, dev-frontend | À faire | §3.10 — EVT-001 |
| L2-02 | Types de billets, achat, émission QR signée | dev-paiements, dev-frontend, auditeur-securite | À faire | §3.10 — EVT-004/005 |
| L2-03 | Check-in par scan, double scan, mode réseau faible | dev-backend, dev-frontend | À faire | §3.10 — EVT-006 |
| L2-04 | Annulation, report et remboursement des billets | dev-paiements | À faire | §3.10 — EVT-007 |
| L2-05 | Abonnements aux services : formules, souscription, rappels de renouvellement | dev-backend, dev-paiements, dev-frontend | À faire | §3.11 — SUB-001 |
| L2-06 | Campagnes ONG et dons (désactivables) | dev-backend, dev-paiements, dev-frontend | Bloqué (validation juridique) | §3.12 — NPO-002 |
| L2-07 | Offres d'emploi et candidatures | dev-backend, dev-frontend, auditeur-securite | À faire | §3.13 — JOB-001/003/004 |
| L2-08 | Appels d'offres et soumissions scellées | architecte-technique, dev-backend, dev-frontend, auditeur-securite | À faire | §3.13 |
| L2-09 | Messagerie temps réel, boîte d'équipe | dev-temps-reel, dev-frontend | À faire | §3.15 — MSG-001/002 |
| L2-10 | Publication automatique sur page Facebook | dev-backend | Bloqué (validation Meta) | §3.8 |
| L2-11 | Recette du lot 2 | qa-testeur | À faire | §10.3 |

## Fin de projet

| ID | Tâche | Agents | Statut |
|---|---|---|---|
| F-01 | Passage à MySQL : `requirements-mysql.txt`, CI sur MySQL, tests de portabilité (casse, unicité, emojis), migration des données | devops, dev-backend, qa-testeur | À faire |
| F-02 | Déploiement AWS Lightsail (Nginx, Daphne, base managée, stockage objet, CDN, sauvegardes) | devops | À faire |
