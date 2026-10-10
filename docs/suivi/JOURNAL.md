# Journal — Connecte+

Une entrée par tâche terminée ou décision prise, la plus récente en haut.

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

## 2026-10-10 — L0-13 : gel de `payments.Transaction` (dev-paiements)
- Constat : sur la branche `backend`, le module `payments` est déjà inerte par construction (R3, ADR 0002) : `urlpatterns = []`, aucune vue, aucun webhook, aucune commande cron, aucun admin. Le `FeatureFlag` annoncé n'existe pas (aucune occurrence dans le code).
- Décision : aucun interrupteur créé, car il ne garderait aucun code (code mort, et un réglage « activable » sans implémentation serait trompeur en matière financière). Le gel est garanti par l'absence de code et verrouillé par des tests (`FrozenModuleTests`). L1-12 livrera le module et son interrupteur (désactivé par défaut) en s'appuyant sur `FeatureFlag` (L0-16), avec journalisation AuditLog.
