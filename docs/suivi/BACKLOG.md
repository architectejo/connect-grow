# Backlog — Connecte+

Tenu par le chef de projet (Claude Code). Statuts : `À faire`, `En cours`, `En relecture`, `En test`, `Fait`, `Bloqué`.
Référence : CDC v1.2 (`docs/CDC_Connecte+_v1.2.md`). État initial au 06/10/2026.

## Lot 0 — Mise en conformité de l'existant (à faire en premier)

Le code existant a été écrit sur la base du CDC v1.0. Ces tâches l'alignent sur la v1.2 avant d'ajouter de nouvelles fonctions. Ordre conseillé : L0-01 → L0-02 → L0-03 → L0-04 → L0-05, puis le reste.

| ID | Tâche | Agents | Statut | Réf. CDC |
|---|---|---|---|---|
| L0-01 | Dépôt Git unique à la racine (historique des deux dépôts conservé), puis CI GitHub Actions (tests backend SQLite, lint/test/build front), `.gitignore` vérifié | devops | Fait sauf `npm run test` du front (aucun test / config Vitest : à corriger par dev-frontend) ; branches `main`, `backend`, `frontend` créées, rien poussé (remote à désigner) | §5.11 |
| L0-02 | SQLite seul : sortir `mysqlclient` de `requirements.txt` vers `requirements-mysql.txt`, retirer les dépendances système MySQL du Dockerfile, archiver `docker-compose.mysql.yml` | devops | Fait (relu, fusionné dans `backend`, branche `chore/L0-02-sqlite-seul`) | §2.5, ADR 0001 |
| L0-03 | Supprimer Redis : `CHANNEL_LAYERS` en `InMemoryChannelLayer`, retirer `channels_redis`, le service Redis des compose et les variables `REDIS_*` | dev-temps-reel, devops | Fait (code et compose ; 98 tests verts, relu) | §5.5 |
| L0-04 | Supprimer le code mort : apps non installées `users`, `offers`, `exchanges`, `chat`, `notifications`, dossier `backend/scratch/`, ancien front `connecte-plus-hub/` (après vérification qu'aucun import n'y renvoie) | architecte-technique (vérif), dev-backend | À faire | — |
| L0-05 | Décider par ADR de la réinitialisation des migrations (aucune donnée de production) pour passer aux clés UUID et à la structure cible des modules | architecte-technique | Fait (ADR 0002 accepté ; exécution du reset : voir R1-R3 ci-dessous) | §5.4, §11.1 |
| L0-05-R1 | Reset R1 : `common`, `identity` (ex-`accounts`), `catalog`, `AUTH_USER_MODEL`, UUID (inclut L0-06). Un seul agent, une seule branche `chore/L0-05-reset-migrations` | dev-backend | À faire (après L0-01) | ADR 0002 |
| L0-05-R2 | Reset R2 : `marketplace` (`Offer`, `is_deleted`, inclut L0-12 et L0-15), `visibility`, `reviews`, `notifications`, `messaging` | dev-backend | À faire (après R1) | ADR 0002 |
| L0-05-R3 | Reset R3 : `moderation`, `payments`, cron, `setup_roles`, import-linter, régénération des `0001`, `migrate` sur base vierge | dev-backend | À faire (après R2) | ADR 0002 |
| L0-05-F1 | Front : ids en `string` (UUID), en parallèle de R1 à R3 | dev-frontend | À faire | ADR 0002 |
| L0-06 | Créer le module `catalog` (City, Commune, Category, ForbiddenItem) et supprimer les clés étrangères entre domaines (ex. `accounts.User` → `marketplace.City`) | architecte-technique, dev-backend | À faire | §5.3, §5.4 |
| L0-07 | Retirer le Trust Score : `User.trust_score`, `TrustScoreSettings`, facteur de confiance de `ranking`, `TrustScore.tsx` et `lib/trust.ts` ; remplacer par note d'offre et note vendeur affichées (moyenne, nombre, ancienneté) | analyste-fonctionnel, architecte-technique, dev-backend, dev-frontend | À faire | §3.4, règle 4 |
| L0-08 | Remplacer le classement par le score organique P × E × R × D, sans note ; pondérations en base | dev-backend | À faire | §3.5 |
| L0-09 | Compte unique et contextes : remplacer `user_type` PARTICULIER/BUSINESS et `BusinessProfile` par `Organization`, `Membership`, rôles d'organisation et contexte actif | analyste-fonctionnel, architecte-technique, dev-backend, dev-frontend | À faire | §3.1, règle 1 |
| L0-10 | Avis : ouvrir le droit d'avis après prise de contact enregistrée (au lieu de l'« affaire conclue »), double note offre + vendeur, libellé « Avis après contact » | dev-backend, dev-frontend | À faire | §3.4 |
| L0-11 | Versionner l'API sous `/api/v1/` (backend + `VITE_API_URL` et client front) | dev-backend, dev-frontend | À faire | §5.9 |
| L0-12 | Renommer `is_delete` en `is_deleted` ; renommer `Post` en `Offer` si validé par l'ADR L0-05 | dev-backend | À faire | §3.16 |
| L0-13 | Paiements : geler `payments.Transaction` (vente d'annonce, hors V1) derrière un interrupteur ; le module sera refondu en L1-12 | dev-paiements | À faire | §3.14 |
| L0-14 | Troc (`is_exchangeable`, `ExchangeProposal`) : masquer derrière un interrupteur en attendant la confirmation du client | dev-backend, dev-frontend | À faire | §8.3 |
| L0-15 | Fusionner les doublons `Conversation`/`Message` dans un futur module `messaging` (préparation du lot 2) | architecte-technique | À faire | §3.15 |
| L0-16 | Table outbox et commande de diffusion des événements de domaine | architecte-technique, dev-backend | À faire | §5.4 |
| L0-17 | Rattrapage du front (phases 0 à 4, livrées hors circuit) : lint à 0 erreur, audit sécurité, relecture | dev-frontend, auditeur-securite, relecteur-code | Fait (lint 0 erreur, 15 tests, build vert, audit corrigé, relu ; reste : test du cache PWA en navigateur en recette ; react-router 7 et Tailwind 4 à valider) | §2.4 (DoD) |
| L0-18 | Passe finale i18n : sortir les textes en dur des pages du front (à faire après L0-07, L0-09 et L0-14, qui réécrivent plusieurs écrans) | dev-frontend | À faire | §4.6 |

## Lot 1 — Visibilité

| ID | Tâche | Agents | Statut | Réf. CDC / client |
|---|---|---|---|---|
| L1-01 | Organisations : création, revendication, invitation, membres et rôles | dev-backend, dev-frontend | À faire | §3.1 — IAM-005/006 |
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
