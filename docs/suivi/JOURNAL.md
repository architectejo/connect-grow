# Journal — Connecte+

Une entrée par tâche terminée ou décision prise, la plus récente en haut.

## 09/10/2026 — R1 du reset fusionné dans `backend` (L0-04, L0-06)

- **Livré (dev-backend, 3 allers-retours) :** `common`, `identity`, `catalog`, UUID, migrations régénérées ; 235 tests verts sans `.env` ni `DEBUG` (relancés par le chef de projet), `migrate` sur base vierge et `makemigrations --check` OK. Relecture et ré-audit sécurité : OK, aucun bloquant.
- **Décisions :** limite de connexion par couple identifiant+IP avec délai croissant (pas de plafond par identifiant seul, pour éviter le verrouillage d'un tiers) ; OTP 3/h par numéro+IP et 10/jour par numéro ; `NUM_PROXIES` obligatoire hors DEBUG (`common.E001`) : à fixer à 1 derrière Nginx ; `backend/scratch/` supprimé.
- **Contrat pour le front (F1) :** réponses 429 avec `Retry-After`, endpoints logout/logout-all, KYC `download_url`, liste d'entreprises paginée à clés restreintes, commune cohérente avec la ville.
- **Points ouverts :** téléphone vendeur public (L0-10a, avec R2), ré-encodage des images d'annonces `.webp` (R2), vérification e-mail, cache partagé de production (DatabaseCache), alerte de bourrage distribué, `NUM_PROXIES` à mentionner à devops, 46 dossiers temporaires de tests anciens à purger. Prochaine étape : R2.

## 09/10/2026 — Vague 1 : ADR 0002 et audit du front

- **Décision (chef de projet, sur délégation de l'utilisateur) :** réinitialisation des migrations (L0-05). ADR 0002 rédigé par architecte-technique et accepté. Choix retenus : noms d'API conservés jusqu'à L0-11 ; `Deal` et Trust Score portés transitoirement dans `reviews` jusqu'à L0-07 ; app `platform` (vérifier la collision de nom dès R1) ; UUID v4 (à revoir en F-01) ; les fichiers `db.sqlite3` et `media/` de dev sont renommés, jamais supprimés.
- **Constat :** les apps mortes `users`, `offers`, `exchanges`, `chat` ne sont plus dans `backend/apps/` ; il reste `backend/scratch/` (L0-04) et `docker-compose.mysql.yml` + `mysql-init` (L0-02).
- **Audit sécurité du front (L0-17) :** aucun point bloquant ; 3 majeurs (jetons JWT dans localStorage, cache PWA de données privées, 21 vulnérabilités npm), 7 mineurs. Correctifs à confier à dev-frontend après le lint. Décision d'architecture sur le stockage des jetons (cookie HttpOnly + CSP) à prendre avec l'utilisateur. Questions juridiques LEG-PRV : téléphone vendeur public, consentement KYC, conservation des pièces.
- **En cours :** L0-01 (devops), L0-03 (dev-temps-reel), lint front (dev-frontend).

## 09/10/2026 — L0-01, L0-02, L0-03 livrés ; R1 et correctifs front en relecture

- **L0-01 (devops) :** dépôt Git unique à la racine, historiques des deux anciens dépôts fusionnés (sauvegardes dans `D:\Projects\cp-git-backup`), branches `main`, `backend`, `frontend`, CI GitHub Actions séparée par dossier. Rien n'est poussé ; remote à désigner. **Autorisation de push :** l'utilisateur autorise les `git push` sans redemander (09/10/2026) ; déploiements et services externes restent soumis à son accord.
- **L0-02 et L0-03 :** SQLite seul, MySQL archivé dans `docs/archive/mysql/`, Redis retiré (code et compose), 98 tests verts (relancés par le chef de projet). Relu (OK sous réserve) ; corrigé : volume `backend_private` pour les pièces KYC, `depends_on` du cron, timeout SQLite à 20 s, README backend. Reste à décider avant déploiement : mode WAL de SQLite.
- **L0-17 front :** lint à 0 erreur, tests réels, build vert, correctifs de l'audit (cache PWA des données privées, purge à la déconnexion, `withCredentials`, dépendances : 21 → 10 vulnérabilités). **Décision :** on accepte que les utilisateurs connectés n'aient plus de cache hors ligne sur les listes d'annonces et d'entreprises (la sécurité prime) ; un cache séparé par utilisateur pourra être étudié plus tard. **Risque accepté :** 5 vulnérabilités hautes restantes dans la chaîne de build Tailwind 3 (`braces`), sans effet à l'exécution ; corrigées par un futur passage à Tailwind 4. **À valider par l'utilisateur :** react-router-dom 7 (avis de redirection ouverte, saut de version majeure).
- **R1 du reset (dev-backend) :** `common`, `identity`, `catalog`, UUID, migrations régénérées, 126 tests verts (relancés par le chef de projet avec `DEBUG=True`). Audit sécurité d'`identity` : 3 bloquantes préexistantes (endpoint public des entreprises qui expose téléphone et e-mail, mot de passe en clair via `PATCH /me/`, liste noire JWT absente), plusieurs majeures (jeton d'accès à 1 h, politique de mot de passe, OTP, pièces KYC, décision KYC, réglages de production). Corrections en cours avant fusion. **Questions juridiques LEG-PRV à poser au client :** téléphone/e-mail vendeur public, consentement et conservation des pièces KYC, rôles habilités à ouvrir une pièce d'identité, contenu de l'AuditLog, sous-traitance SMS.
- **CI backend :** les tests exigent `DEBUG=True` (sinon `SECURE_SSL_REDIRECT` renvoie 301) alors que le workflow fixe `DEBUG=False` : à corriger avec des réglages de test dédiés et un hasheur rapide.

## 06/10/2026 — Décisions de l'utilisateur et lancement de la vague 1

- **Git :** un dépôt unique à la racine pour GitHub (au lieu de `backend` et `connect-grow` séparés), avec deux branches : `feat/front-phases-0-4` (travail front non commité) et `chore/L0-01-ci`. Aucun `git push` sans accord ; le dépôt GitHub cible reste à désigner.
- **Front phases 0 à 4** (design system, accueil, marketplace, fiche, authentification OTP, espace vendeur, PWA, découpage du code) : livrées directement par le chef de projet, hors circuit. Aucune relecture ni audit sécurité à ce jour ; `npm run lint` échoue (6 erreurs : `command.tsx`, `textarea.tsx`, `Messages.tsx`) ; textes des pages en dur. Rattrapage créé : L0-17 (puis L0-18 pour l'i18n).
- **Accord de l'utilisateur** pour L0-17 et pour la suppression du code mort de L0-04 (après vérification par l'architecte).
- **Lancés :** L0-01 (devops), L0-05 (architecte-technique, ADR proposé), L0-17 (audit sécurité du front ; correction du lint à suivre sur la branche front).

## 06/10/2026 — Mise en place de l'organisation par agents

- CDC passé en v1.2 : périmètre V1 aligné sur le brief du client, SQLite seul jusqu'à la fin du projet, lot 0 de mise en conformité.
- Création de `CLAUDE.md`, des 11 agents de `.claude/agents/`, du backlog et de l'ADR 0001.
- État constaté : 98 tests backend verts sur SQLite ; écarts avec la v1.2 listés dans le lot 0.
- Prochaine étape : L0-01 (CI) et L0-02 / L0-03 (SQLite seul, retrait de Redis).
