# Journal — Connecte+

Une entrée par tâche terminée ou décision prise, la plus récente en haut.

## 09/10/2026 — L0-07, L0-08, L0-10 fusionnés (Trust Score retiré, avis après contact, classement organique)

- **Livré (dev-backend, dev-frontend ; ADR 0004) :** `Review` réécrit (note d'offre + note de vendeur, preuve de contact, un avis par couple auteur-offre) ; `Deal`, `TrustScore`, badge « Vendeur fiable » supprimés ; éligibilité authentifiée, délai contact→avis (≥ 1 h, défaut 24 h), compte ≥ 24 h ; signalement « contact fictif » réservé au vendeur avec recours de l'auteur (notifications, réponse, verrou sur la seule suppression, délai de traitement 72 h) ; score organique E×R stocké, proximité D à la lecture (`near`), recalcul horaire ; réglages en base bornés (règle 11) avec audit. 678 tests backend, 155 front.
- **Décisions du chef de projet :** migrations `0002` à `0004` au lieu de réécrire les `0001` (CLAUDE.md §9) ; deux tables de réglages ; limite quotidienne d'avis en 429 et format d'erreur `{detail, code}` ; événements d'avis en version 2 ; nom d'auteur « prénom + initiale » par défaut (D11, en attente du client) ; verrou de suppression seul pour les motifs graves.
- **Intégration :** T1 corrigé, T2 et T3 fusionnés dans `integ/L0-07-08-10` puis dans `backend` ; conflits résolus par dev-backend en gardant les verrous de T1 et l'éligibilité de T3.
- **Questions LEG-PRV ajoutées :** droit d'information et de contestation de l'auteur d'un avis masqué ; durée de conservation des signalements, de leur description et de la réponse de l'auteur ; consentement pour afficher « prénom + initiale » ; anonymisation des avis à la fermeture d'un compte (`Review.user` en CASCADE).
- **Dettes :** alerte sur les pics d'avis à 5 étoiles ; message réellement échangé comme preuve (L0-10a) ; plafond de signalements non atomique ; tri par pertinence non indexé (à mesurer au passage MySQL) ; badge « Vérifié » sans libellé précis (L1-02).
- **Opération :** `NUM_PROXIES=1` obligatoire derrière Nginx (`.env.example` à 0 pour le développement).

## 09/10/2026 — L0-19 et L0-10a-a fusionnés (fuite du téléphone colmatée)

- **L0-19 :** `logout/` sans access valide, `Retry-After` exposé en CORS, offres non actives lisibles par leur vendeur, filtre `is_verified` ; 516 tests.
- **L0-10a-a (backend + front, 2 allers-retours chacun) :** `phone` retiré de tous les sérialiseurs publics ; test de non-fuite exhaustif (`common/tests_privacy.py`, 6 profils dont modérateur et administrateur, recherche, écritures) ; boutons Appeler/WhatsApp supprimés du front ; `Vary: Authorization` et `Cache-Control: private` sur `/api/` ; cache PWA renommé `api-annonces-v2` ; oracle d'existence du téléphone à l'inscription supprimé (unicité contrôlée après un OTP valide). 539 tests backend, 85 front.
- **Dette tracée :** oracle d'existence d'e-mail à l'inscription (à lever avec une vérification d'e-mail) ; accès des modérateurs aux e-mails/téléphones dans l'admin (LEG-PRV) ; WebSocket non couverts par le test de non-fuite.
- **Écart de contrat front :** plus d'erreur `phone` « déjà utilisé » à l'étape 1 (remplacée par `otp_code` neutre) ; 429 possibles sur `register` et `PATCH me/`.

## 09/10/2026 — F1 et L0-16 fusionnés

- **F1 (dev-frontend, 2 allers-retours) :** ids UUID, erreurs 429 avec `Retry-After`, déconnexion serveur et « tous les appareils », purge des caches PWA et multi-onglets, entreprises paginées, dates Africa/Kinshasa, messagerie en `useQuery` ; 78 tests, lint 0 erreur. Fusionné dans `frontend`.
- **L0-16 (dev-backend, 2 allers-retours) :** outbox `platform_core` (ADR 0003) ; contact, échange, vues, partages, avis, réponse, avis croisés et expiration passent par l'outbox ; 504 tests ; concurrence SQLite vérifiée par script manuel (`scripts/check_outbox_concurrency.py`). Décisions : nom `platform_core` (pas `platform`), diffusion immédiate après commit en plus du cron, compteurs journaliers de `visibility` seule source des totaux, `reputation_changed` non migré (L0-07), rétention 7 jours (traités) et 30 jours (échecs). Audit : plus de données personnelles dans les journaux.
- **Décisions avis/classement/contact :** voir `docs/specs/avis-classement-contact.md` section 6 (suppression de `Deal`, consentement de contact par canal désactivé par défaut, etc.).
- **En cours :** L0-19 (correctifs backend issus de F1). **Ensuite :** L0-10a-a (retrait de `phone`), L0-07/L0-08, L0-10.

## 09/10/2026 — R2 et R3 du reset fusionnés dans `backend`

- **R2 (dev-backend, 2 allers-retours) :** `marketplace` (Offer, `is_deleted`), `visibility`, `reviews` (Deal/TrustScore transitoires), `notifications`, `messaging` ; anciennes apps `interactions`, `reputation`, `ranking` supprimées ; 381 tests. Failles de l'ancien code corrigées : modification d'une offre par n'importe quel connecté, conversation unique partagée par offre, écriture dans toute conversation, réponse d'avis écrite par son auteur. Ajouts : limites de débit sur les écritures, masquage de modération explicite (`is_hidden_by_moderation`), cookie anonyme signé, purge des vues (`VisibilitySettings`), journalisation règle 12, fuseau `Africa/Kinshasa` avec `USE_TZ`.
- **R3 (dev-backend, 2 allers-retours) :** `moderation` par `target_type`/`target_id` sans clé générique ; `payments` aligné structurellement ; cron renommé (`purge_offer_trash`, `expire_offers`, `purge_otp_codes`, `refresh_daily_contacts`) ; `setup_roles` au moindre privilège ; frontières de modules vérifiées par analyse `ast` sur les 9 domaines ; import-linter non ajouté (redondant) ; migrations 0001 finales. 425 tests, `migrate` sur base vierge OK. Audit : fuite d'e-mail/téléphone par la réponse de création d'un signalement corrigée ; permissions de modération par droits et groupes ; machine d'états des signalements ; sanctions liées à la bonne cible.
- **Décision du chef de projet :** fuseau `Africa/Kinshasa`.
- **Contrat front (F1 en cours) :** voir la liste dans le brief F1 ; en plus : réponse de création de signalement minimale pour un non-staff, 409 sur signalement clos ou doublon, 400 sur sanction invalide.
- **Questions LEG-PRV ajoutées :** durée de conservation des messages, contacts, avis, signalements, journal d'audit et vues anonymes ; consentement du cookie anonyme ; finalité de l'accès du Modérateur aux e-mails/téléphones.
- **Points ouverts :** téléphone vendeur (L0-10a) ; affaire déclarable après `mark_sold` (à arbitrer avec L0-10) ; cache de production partagé ; taux de limitation en `settings` (pas administrables) ; Trust Score transitoire (L0-07). Prochaine étape : L0-16 (outbox), L0-07, après fusion de F1.

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

## 2026-10-09 — Recette QA du lot 0 et corrections (L0-21, L0-22)
- qa-testeur : recette refusée (4 majeures : prix négatif, stock négatif/500, e-mail sensible à la casse, levée de suspension qui réactive un banni). Règles 3, 4, 10 OK ; règle 12 OK sauf soft_delete (réversible, voulu).
- dev-backend (L0-21) : toutes corrigées + 429 avec Retry-After, messages en français, LOGGING OTP en DEBUG, offres des comptes inactifs masquées, user_type en lecture seule. 753 tests verts. Migrations marketplace 0004 et identity 0003 (e-mails en minuscules).
- dev-frontend (L0-22) : types alignés, null géré, typecheck au build. 183 tests verts.
- Décisions : prix 0 accepté (« sur devis », à confirmer client) ; stock max 1 000 000 (garde-fou technique) ; pagination plafonnée reportée à L0-11.
- Points ouverts : stats/agrégats comptent encore les offres de comptes suspendus ; profils vendeurs publics de comptes suspendus ; ENTREPRISE sans business_profile ; fichier parasite D:\Projects	sc.out et dossier cp-wt-QAf à supprimer à la main.


## 2026-10-10 — Contact vendeur et consentement (L0-10a-b à d), audit et corrections (L0-23, L0-24)
- **ADR 0005** (architecte) : compte de contact distinct du numéro de connexion, consentement par canal (MESSAGE actif, appel et WhatsApp désactivés par défaut), révélation du numéro uniquement par POST authentifié, limitée, journalisée.
- **T1, T2, T5 fusionnés** (modèles, réglages de contact côté serveur et côté front). **L0-23** : tests au jour local (Africa/Kinshasa), corrige 4 échecs entre 00 h et 01 h.
- **Relecture + audit de T1/T2** : aucun critique. Majeur : course entre vérification et changement de numéro (numéro d'un tiers pouvant être « vérifié ») ; ContactPoint concurrent (500). **L0-24** (dev-backend) corrige : vérification conditionnelle, création concurrente, contrôle de phone_last4 à la révélation, garde SMS « compte neuf » (réglage `CONTACT_SMS_MIN_ACCOUNT_AGE_HOURS`, 24 h), SMS qui nomme son but, codes de contact masqués dans l'admin et purgés après usage. 836 tests.
- **T3 fusionné** (révélation, quotas 15/24 h par compte, 3/24 h compte neuf, 30/h par IP, liste « qui a demandé », signalement automatique après 3 jours de dépassement, réglages configurables). Relecture + audit : aucune fuite du numéro. Corrigés : verrou par visiteur (course), signalement automatique redevient actif après clôture, audit dédoublonné, Retry-After exact, IPv6 sur /64. **903 tests verts** (relancés par le chef de projet), migration marketplace 0006.
- **Décisions du chef de projet** : « compte neuf » = téléphone non vérifié OU inscrit depuis moins de 24 h ; anti-doublon de contact par canal ; fenêtre de 24 h en constante (dette règle 11).
- **Dettes / points ouverts** : consentement valable après changement de version du texte (LEG-PRV-03) ; migration marketplace 0005 mixte ; courses sous MySQL (REPEATABLE READ) ; limite IP en cache mémoire par processus (mono-processus ou cache partagé en prod), `NUM_PROXIES=1` + `X-Forwarded-For $remote_addr` à donner au devops ; CGNAT ; durée de conservation de l'AuditLog et des ContactEvent (LEG-PRV-05), information du visiteur avant le clic, IP dans le cache (LEG-PRV-07).
- **En cours :** T4 (preuve de message remis pour les avis, dev-backend), T6 (boutons de contact et « Qui a demandé », dev-frontend). Ensuite T7 (non-fuite), puis L0-09, L0-11, L0-13, L0-14, L0-18.

## 2026-10-10 (suite) — Contact vendeur terminé, branches réunies, lancement de L0-09
- **T4, T6 fusionnés, relus et audités** (aucun bloquant). Corrections L0-25 (délai d'avis compté depuis la remise, nom du visiteur nettoyé), L0-26 (fixture et contrat front, regex WhatsApp, texte d'information du visiteur). **Risque accepté** : un numéro révélé vaut preuve de contact pour un avis (surveiller le ratio avis/révélations).
- **Réunion des branches** : `main` = `backend` + `frontend`. Six conflits sur des copies anciennes (CI, requirements avec Redis, .env.example, ADR 0002 à 0004) : version de `backend` retenue.
- **Recette QA L0-10a : acceptée** (59 tests backend et 24 front ajoutés ; 972/283 tests). Corrigés : notification au nom nettoyé (L0-27), audit du consentement sans chiffres du numéro, `account_too_new` et masque serveur côté front (L0-28).
- **L0-13** : le module `payments` n'a aucune route ; tests de gel ajoutés ; interrupteur et `FeatureFlag` à livrer avec L1-12. Texte marketing « Laxpaie » du front à retirer en L0-18. Statut `HELD` (séquestre) contraire à la règle 9 : à écarter dans la refonte L1-12.
- **L0-09** : analyse (10 stories L0-09a à j, docs/specs/L0-09-compte-contextes.md). Décisions du chef de projet : découpage L0-09/L1-01/L1-02 validé ; éditeur sans droit sur l'identité de l'organisation ; téléphone vérifié exigé pour créer une organisation ; offre conservée par l'organisation ; migration de données (pas de reset) ; rôles en constantes (propriétaire, administrateur, éditeur, analyste) ; 10 organisations max par compte (réglage) ; organisation limitée au canal MESSAGE en intérim. ADR 0006 en cours (architecte). **Questions client Q-CLI1 à Q-CLI8** à poser (rôles, pièces KYB par type, contenu du contexte personnel, nombre d'organisations, consentement d'une organisation, conservation KYB, vérification du prestataire, unicité des noms).
- **L0-14** (backend) lancé : réglage `exchange_enabled`, éteint par défaut.
