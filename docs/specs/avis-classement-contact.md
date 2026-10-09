# Spécification : avis, classement organique et contact (L0-07, L0-08, L0-10, L0-10a)

Auteur : analyste-fonctionnel. Date : 09/10/2026. Statut : proposition, en attente d'arbitrage (section 2).

Sources : CLAUDE.md §4 (règles 3, 4, 5, 10, 11, 12) ; CDC v1.2 §3.4, §3.5, §3.9, §3.15 ; dossier client doc07 (§8 « Avis, notes et preuve d'interaction », §17 « Protection des données sensibles », TRU-AC-05/06) ; doc12 (LEG-PRV) ; doc13 (`ContactPoint`, `ContactAction`) ; code lu dans `cp-wt-backend/backend/apps` (`reviews`, `visibility`, `marketplace`, `identity`) et `connect-grow/src`.

Remarque de numérotation : les commentaires du code citent encore « CDC 3.7 / 3.8 » (v1.0). Dans la v1.2 ce sont §3.4 (avis) et §3.5 (classement). À corriger au passage.

---

## 0. Analyse de conformité

| Élément de l'existant | Source du problème | Verdict |
|---|---|---|
| `User.trust_score`, `TrustScoreSettings`, `recompute_trust_score`, signaux `reviews/signals.py` | Règle 4 ; CDC §3.4 (« aucun score de confiance universel ») | Non conforme : à retirer |
| Facteur T de `compute_score`, champs `trust_factor_min/max` de `RankingSettings` | Règle 4 ; CDC §3.5 (« la note n'entre pas dans ce score ») | Non conforme : à retirer |
| Badge « Vendeur fiable » (`is_trusted_seller` : score >= 4,5 et 10 avis ; `TRUSTED_SELLER_MIN_*` dans `marketplace/serializers.py`, `StatusBadge kind="reliable"`) | Règles 3 et 4 : un badge dérivé de la note est un score de confiance déguisé et un badge qui ne dit pas ce qui est vérifié | Non conforme : à retirer (non listé dans le backlog, à ajouter à L0-07) |
| `comments_count` dans l'engagement E | Le CDC définit E avec vues uniques, favoris, contacts, partages. Selon sa source (à vérifier), `comments_count` peut refléter le nombre d'avis | Écart : retirer `comments`, ajouter `contacts` |
| `avg_rating = request.user.trust_score` dans `marketplace/stats_views.py` | Règle 4 | Non conforme : à remplacer par la moyenne des avis reçus (note vendeur) |
| `Deal` (« affaire conclue ») comme seule condition d'avis | CDC §3.4 : droit d'avis après prise de contact enregistrée | Écart à corriger (L0-10) |
| Avis noté une seule fois (1 note) et avis dans les deux sens (acheteur et vendeur s'évaluent) | CDC §3.4 : double note offre + vendeur, par le visiteur | Écart (L0-10) |
| `SellerSerializer.phone` public, boutons `tel:` / `wa.me` dans `ContactActions.tsx` | Règle 10 ; doc07 §17 (téléphone : « seulement si utilisateur choisit et policy autorise ») | Fuite de donnée personnelle : à corriger avant toute recette ouverte |
| Textes front : « Avis après une affaire conclue » (`HeroSection.tsx`), « Trust Score » (`FeaturesSection.tsx`, `HowItWorksSection.tsx`), « Trust & Engage » (`Index.tsx`, `FeaturesSection.tsx`) | CDC §3.4 : libellé « Avis après contact » | À réécrire (avec L0-18) |
| Constantes en dur : `DAILY_REVIEW_LIMIT`, `CROSSED_REVIEWS_*`, `TRUSTED_SELLER_MIN_*`, `DUPLICATE_CONTACT_WINDOW`, `REVIEW_EDIT_WINDOW_HOURS`, `TRENDING_*` | Règle 11 (règles de marché configurables) | Écart : rendre configurables ce qui relève du marché (voir D8) |

Aucune des quatre tâches ne contredit une règle verrouillée, à condition de retirer le badge « Vendeur fiable ». Un point du CDC est fragile (voir C1 ci-dessous).

### Contradictions et risques à signaler

- C1. Le droit d'avis après simple « prise de contact » est facile à fabriquer : un compte peut envoyer un message, puis noter. Le doc07 (§8) parle d'« interaction terminée/éligible » ; le CDC §3.4 retient « contact enregistré ». Pas de contradiction formelle, mais l'anti-abus du CDC (5 avis/jour, avis réciproques) est mince. Options en D5.
- C2. Pour un appel ou un message WhatsApp, la plateforme ne sait pas si la conversation a eu lieu : elle sait seulement que le numéro a été révélé. Le libellé « Avis après contact » reste honnête s'il est défini ainsi : « contact initié depuis Connecte+ ». À écrire dans les conditions d'usage.
- C3. « Note vendeur non fusionnée avec d'autres rôles » (CDC §3.4) dépend de L0-09 (contextes, `Organization`). Tant que L0-09 n'est pas faite, le « vendeur » est un `User`. Le modèle d'avis doit pointer vers le contexte vendeur, pas vers la personne. Voir D7.
- C4. Le PWA peut mettre en cache les réponses : la réponse de révélation du numéro ne doit jamais être mise en cache (rappel du point ouvert de L0-17).
- C5. `Review.user` / `reviewed_user` actuels autorisent un avis du vendeur sur l'acheteur. Le CDC ne le prévoit pas (« le visiteur connecté note une offre et son vendeur »). La réponse du vendeur reste le seul retour.

---

## 1. User stories

### L0-07 — Retrait du Trust Score, remplacé par deux notes affichées

#### L0-07-a — Supprimer tout score de confiance universel
En tant que staff (équipe produit), je veux qu'aucun score de confiance agrégé n'existe dans le système, afin de respecter la règle 4.
Réf. : CDC §3.4 ; règle 4 ; dossier client doc07 §8 (« Pas de score universel ») ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné la base migrée à vide, quand on liste les champs du modèle utilisateur, alors `trust_score` (et le compteur `reviews_count` stocké sur l'utilisateur) n'existent plus.
- [ ] Étant donné le code, quand on cherche `TrustScoreSettings`, `recompute_trust_score`, `set_reputation`, `trust_factor_min`, `trust_factor_max`, `is_trusted_seller`, alors aucune occurrence hors historique Git.
- [ ] Étant donné une réponse API de liste ou de fiche d'offre et de profil vendeur, quand on lit le JSON, alors aucune clé `trust_score`, `is_trusted_seller`, `is_new_seller` n'est présente.
- [ ] Étant donné l'écran du front, quand on cherche `TrustScore.tsx`, `lib/trust.ts`, `StatusBadge kind="reliable"` et les chaînes « Trust Score », « Vendeur fiable », « Trust & Engage », alors il n'en reste aucune dans le code ni dans les textes i18n.
- [ ] Étant donné la page d'accueil, quand elle s'affiche, alors aucun texte ne promet un score de confiance ou une « affaire conclue ».
- [ ] Étant donné l'administration Django, quand on ouvre la fiche d'un utilisateur, alors aucun champ de score n'apparaît.
- [ ] Étant donné `python manage.py makemigrations --check --dry-run` sur la base vierge, alors aucune migration n'est en attente et `migrate` passe sur SQLite vierge.
Règles métier : suppression nette, sans compatibilité ascendante (aucune donnée de production, voir section 5). Le badge « Vérifié » n'est pas touché : il vient de la vérification (L1-02), jamais d'une note.
Hors périmètre : refonte des badges de vérification (L1-02).
Questions ouvertes : aucune.

#### L0-07-b — Afficher la note de l'offre et la note du vendeur côte à côte
En tant que visiteur, je veux voir la note de l'offre et la note du vendeur séparément, avec leur nombre d'avis et l'ancienneté, afin de juger sans score unique.
Réf. : CDC §3.4 (« Affichage », « Séparation ») ; règle 4 ; doc07 §8 (« contexte, volume et récence ») ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné une offre qui a 5 avis (moyenne 4,2 sur la note d'offre) et un vendeur qui a 8 avis (moyenne 3,9 sur la note vendeur), quand j'ouvre la fiche de l'offre, alors je vois deux blocs distincts : « Note de l'offre 4,2 (5 avis) » et « Note du vendeur 3,9 (8 avis) », chacun avec son nombre d'avis.
- [ ] Étant donné la même fiche, quand je lis l'API, alors les deux moyennes sont des champs séparés (`offer_rating`, `seller_rating`, chacun avec `average`, `count`) et aucun champ ne fusionne les deux.
- [ ] Étant donné un vendeur ou une offre avec moins de N avis (N = réglage, 3 par défaut), quand la fiche s'affiche, alors la moyenne n'est pas affichée et le texte « Pas encore d'avis » apparaît à sa place ; l'API renvoie `average: null`.
- [ ] Étant donné un vendeur avec N avis ou plus, quand la fiche s'affiche, alors la moyenne est arrondie à une décimale (règle d'arrondi : demi supérieur) et suivie du nombre d'avis.
- [ ] Étant donné un avis masqué par la modération, quand les moyennes sont calculées, alors cet avis n'est compté ni dans la moyenne ni dans le nombre.
- [ ] Étant donné un avis ajouté, modifié ou masqué, quand je recharge la fiche, alors les moyennes reflètent l'état à jour (calcul à la lecture ou compteur mis à jour dans la même opération).
- [ ] Étant donné le vendeur, quand sa note s'affiche, alors l'ancienneté s'affiche à côté (voir D4) et le texte de l'ancienneté provient d'une seule source de données.
- [ ] Étant donné une carte d'offre dans une liste, quand elle s'affiche, alors elle montre au plus la note de l'offre (ou « Pas encore d'avis »), jamais une note fusionnée.
- [ ] Étant donné les lecteurs d'écran, quand la note s'affiche, alors le libellé accessible dit « Note de l'offre : 4,2 sur 5, 5 avis ».
Règles métier : la note vendeur ne reprend que les avis marketplace (CDC §3.4 « Séparation ») ; aucune moyenne bayésienne, aucune note « neutre » injectée : la moyenne est arithmétique ; le seuil N est un réglage de back-office (règle 11).
Hors périmètre : avis « après achat » (billets, abonnements : lot 2) ; tri et filtre par note (L1-06).
Questions ouvertes : D3 (affichage sous le seuil), D4 (ancienneté).

#### L0-07-c — Statistiques du vendeur sans score
En tant que prestataire, je veux voir dans mon tableau de bord la moyenne de mes avis reçus et leur nombre, afin de suivre mes retours sans score de confiance.
Réf. : CDC §3.4 ; `marketplace/stats_views.py` ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné un vendeur avec 4 avis visibles de notes vendeur 5, 4, 4, 3, quand il ouvre son tableau de bord, alors `avg_rating` vaut 4,0 et `review_count` vaut 4.
- [ ] Étant donné un vendeur sans avis, quand il ouvre son tableau de bord, alors `avg_rating` est `null` (pas 3,5) et `review_count` vaut 0.
Règles métier : le vendeur voit sa moyenne même sous le seuil d'affichage public (information privée au propriétaire).
Hors périmètre : graphiques de visibilité (L1-xx).
Questions ouvertes : aucune.

---

### L0-08 — Classement organique P × E × R × D

#### L0-08-a — Calculer le score organique sans note
En tant que visiteur, je veux que l'ordre du fil dépende de la pertinence, de l'engagement, de la récence et de la proximité, afin de voir ce qui m'intéresse sans que la note ne décide.
Réf. : CDC §3.5 (formule et tableau P, E, R, D) ; règles 4, 5, 11 ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné deux offres identiques en vues, favoris, contacts, partages, âge et lieu, dont l'une a un vendeur noté 5/5 et l'autre 1/5, quand on calcule leur score, alors les deux scores sont égaux.
- [ ] Étant donné une offre sans interaction, quand on calcule E, alors E = 1.
- [ ] Étant donné une offre avec v vues uniques, f favoris, c contacts et s partages, quand on calcule E, alors E = 1 + ln(1 + a·v + b·f + c·contacts + d·s) où a, b, c, d sont lus dans la base (valeurs initiales 1, 3, 5, 8).
- [ ] Étant donné une offre âgée de 72 heures et une demi-vie réglée à 72, quand on calcule R, alors R = 0,5 (tolérance 1e-6) ; avec une demi-vie réglée à 24, R = 0,125.
- [ ] Étant donné un visiteur de la commune X, quand l'offre est dans la commune X alors D = 1,2 ; dans la même ville mais une autre commune, D = 1,1 ; ailleurs ou position inconnue, D = 1,0 (valeurs lues dans la base).
- [ ] Étant donné le fil sans recherche ni catégorie, quand le score est calculé, alors P = 1.
- [ ] Étant donné un administrateur qui modifie une pondération dans le back-office, quand un nouveau score est calculé, alors la nouvelle valeur est utilisée sans redéploiement ; aucune pondération n'est codée en dur dans le code de calcul.
- [ ] Étant donné la réponse du fil, quand on lit l'API, alors aucune note ni aucun badge de note n'entre dans le champ de tri, et le tri par défaut reste le score organique.
- [ ] Étant donné une valeur de réglage invalide (négative, demi-vie <= 0, proximité < 1), quand l'administrateur l'enregistre, alors le formulaire la refuse avec un message en français.
- [ ] Étant donné un changement de réglage, quand il est enregistré, alors une entrée `AuditLog` est écrite (règle 12) avec l'ancienne et la nouvelle valeur.
Règles métier : formule du CDC, sans terme de promotion (le Sponsorisé reste séparé, règle 5, et est traité en L1-xx). Seuls les indicateurs « uniques » comptent (une vue unique par visiteur et par jour ; un partage par utilisateur, offre, jour). Les contacts comptent une fois par couple (expéditeur, offre) et par jour, tous canaux confondus, pour éviter qu'un contact répété gonfle E.
Hors périmètre : emplacements sponsorisés ; filtre de recherche sur le texte (P > 1 pour la recherche : voir Questions ouvertes) ; tri par distance en kilomètres.
Questions ouvertes : D6 (lecture des pondérations), D9 (formule de P lors d'une recherche), D10 (stockage du score et proximité).

#### L0-08-b — Retirer les anciens termes (confiance, likes, commentaires)
En tant que staff, je veux que les anciens facteurs disparaissent des réglages, afin que le back-office ne propose que les paramètres du CDC.
Réf. : CDC §3.5 ; règle 4 ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné le formulaire « Paramètres de classement » du back-office, quand je l'ouvre, alors je vois : poids des vues uniques, des favoris, des contacts et des partages ; demi-vie de récence ; coefficients de proximité (même commune, même ville, ailleurs). Je ne vois ni facteur de confiance, ni poids des commentaires, ni poids des « likes ».
- [ ] Étant donné les tests de `visibility` et `marketplace`, quand on les exécute, alors aucun ne référence `trust_score` ni `trust_factor_*` et les tests de formule vérifient les quatre facteurs.
- [ ] Étant donné la commande d'actualisation des scores, quand l'administrateur la lance, alors toutes les offres actives sont recalculées avec les nouveaux paramètres et le nombre d'offres mises à jour est affiché.
Règles métier : renommage fonctionnel : « Trust & Engage » devient « Classement organique » (admin, textes, commentaires).
Hors périmètre : A/B test d'algorithme.
Questions ouvertes : aucune.

---

### L0-10 — Avis après contact, double note

#### L0-10-a — Ouvrir le droit d'avis après une prise de contact enregistrée
En tant que visiteur connecté, je veux pouvoir noter l'offre et son vendeur après avoir pris contact avec lui via Connecte+, afin de partager mon expérience.
Réf. : CDC §3.4 (« Droit d'évaluer », « Un avis par interaction ») ; doc07 §8 ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné un visiteur connecté qui n'a jamais contacté le vendeur pour cette offre, quand il tente de créer un avis pour cette offre, alors l'API répond 403 avec le message « Vous pourrez donner votre avis après avoir contacté le vendeur. » et aucun avis n'est créé.
- [ ] Étant donné un visiteur qui a une prise de contact enregistrée (message, appel ou WhatsApp, voir L0-10a) pour cette offre depuis au moins D heures (réglage ; voir D5), quand il crée un avis, alors l'avis est créé avec le libellé « Avis après contact ».
- [ ] Étant donné la fiche de l'offre, quand le visiteur éligible la consulte, alors un bouton « Donner mon avis » est visible ; quand le visiteur non éligible ou non connecté la consulte, alors le bouton est absent.
- [ ] Étant donné le vendeur de l'offre, quand il essaie de noter sa propre offre, alors l'API répond 403.
- [ ] Étant donné un avis déjà posté pour la même interaction (voir D2 : un avis par couple auteur-offre), quand l'auteur en crée un second, alors l'API répond 409 « Vous avez déjà donné votre avis pour cette offre. »
- [ ] Étant donné un auteur qui a déjà écrit 5 avis aujourd'hui (réglage), quand il en crée un sixième, alors l'API répond 429 et le compteur du jour ne diminue pas si un avis est supprimé.
- [ ] Étant donné un compte suspendu ou une offre masquée par la modération, quand son visiteur éligible veut noter, alors l'avis reste possible sur une offre expirée, vendue ou en pause, et impossible pour un compte suspendu (règle de sanction).
- [ ] Étant donné une offre purgée définitivement, quand on consulte les avis, alors ils restent attachés à l'identifiant d'offre et au vendeur, et continuent de compter dans la note du vendeur (CDC §3.16 : avis conservés).
- [ ] Étant donné l'API de création d'avis, quand la requête contient un identifiant d'« affaire » (`deal`), alors le champ est ignoré ou rejeté (400) ; l'endpoint `/api/reputation/deals/` n'existe plus (404).
Règles métier : la preuve d'éligibilité est la prise de contact enregistrée (L0-10a) ; la plateforme ne garantit pas que l'échange a abouti : le libellé dit « Avis après contact » et rien d'autre (règle 3, CDC §3.4 « sans garantir la qualité »). Seul le visiteur qui a contacté peut noter ; le vendeur répond mais ne note pas l'acheteur.
Hors périmètre : « Avis après achat » (billet, abonnement : lot 2) ; avis sur un employeur ou un organisateur.
Questions ouvertes : D1 (devenir de `Deal`), D2 (unité « une interaction »), D5 (garde-fous).

#### L0-10-b — Double note (offre et vendeur) et commentaire
En tant que visiteur éligible, je veux donner une note à l'offre et une note au vendeur avec un commentaire, afin de distinguer le produit de la personne.
Réf. : CDC §3.4 (« Contenu ») ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné le formulaire d'avis, quand je le soumets sans note d'offre ou sans note de vendeur, alors l'API répond 400 avec une erreur sur le champ manquant.
- [ ] Étant donné une note d'offre ou de vendeur hors de 1 à 5 (0, 6, 3,5), quand je soumets, alors l'API répond 400.
- [ ] Étant donné un commentaire de 9 caractères, quand je soumets, alors 400 ; de 10 caractères, alors accepté ; de 500 accepté ; de 501, 400 (espaces de début et de fin retirés avant comptage).
- [ ] Étant donné un avis publié, quand je consulte la fiche, alors je vois les deux notes en étoiles, le commentaire, le libellé « Avis après contact », la date et le prénom/nom d'affichage de l'auteur selon sa règle de confidentialité.
- [ ] Étant donné un avis publié, quand son auteur le modifie moins de 48 h après sa création, alors la modification est acceptée et une mention « modifié » apparaît ; après 48 h, l'API répond 403.
- [ ] Étant donné un avis, quand le vendeur répond, alors une seule réponse publique de 500 caractères au plus est acceptée, l'auteur est notifié ; une seconde réponse est refusée (409).
- [ ] Étant donné un avis négatif non conforme à aucune règle de modération, quand le vendeur demande son retrait parce qu'il est défavorable, alors l'avis reste (doc07 TRU-AC-06 ; CDC §3.4 « Modération »).
- [ ] Étant donné un avis qui contient un numéro de téléphone ou une adresse (donnée privée), quand il est signalé et jugé non conforme, alors un modérateur peut le masquer, l'action est écrite dans `AuditLog` et les moyennes sont recalculées sans lui.
Règles métier : la note d'offre porte sur l'offre ; la note vendeur sur le vendeur (contexte marketplace). Suppression par l'auteur : tant que l'avis n'est ni masqué ni signalé (existant, conservé).
Hors périmètre : photos dans les avis ; vote « utile ».
Questions ouvertes : affichage du nom de l'auteur (prénom + initiale ?), à confirmer (D11).

#### L0-10-c — Anti-abus des avis
En tant que modérateur, je veux que les avis réciproques répétés et les avis en rafale soient détectés, afin de limiter les faux avis.
Réf. : CDC §3.4 (« Anti-abus ») ; doc07 §8 (« Spam / manipulation ») ; règle 11 ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné l'ancienne règle des « 3 affaires distinctes en 30 jours », quand la nouvelle règle est en place, alors elle compte des interactions (couples auteur-offre) et non plus des `Deal` ; le seuil et la fenêtre sont des réglages de back-office.
- [ ] Étant donné deux comptes A et B qui se sont notés mutuellement au moins 3 fois sur 30 jours (réglages par défaut), quand le troisième avis est créé, alors il est publié et un signalement automatique est ouvert pour la modération (comportement actuel conservé).
- [ ] Étant donné le réglage « avis par jour et par compte » (5 par défaut), quand l'administrateur le change, alors la nouvelle valeur s'applique au prochain avis.
Règles métier : la détection signale, elle ne bloque pas (un faux positif ne doit pas empêcher un vrai avis).
Hors périmètre : détection de multi-comptes par appareil.
Questions ouvertes : D8.

---

### L0-10a — Contact authentifié, consenti, journalisé

#### L0-10a-a — Retirer le téléphone de toutes les réponses publiques
En tant que prestataire, je veux que mon numéro n'apparaisse jamais dans une réponse publique, afin de protéger ma vie privée (règle 10).
Réf. : CDC §3.15 ; règle 10 ; doc07 §17 ; lot 0 (prérequis de toute recette ouverte)
Critères d'acceptation (testables) :
- [ ] Étant donné un visiteur anonyme, quand il appelle la liste des offres, la fiche d'une offre, le profil d'un vendeur, la liste des conversations ou toute autre route publique, alors aucune clé `phone` ni aucune valeur ressemblant à un numéro du vendeur n'est présente (test automatique sur toutes les routes publiques de `SellerSerializer`).
- [ ] Étant donné un visiteur connecté, quand il appelle les mêmes routes, alors le résultat est identique (le numéro ne sort que par l'action de contact).
- [ ] Étant donné le HTML et le JS du front, quand on lit le code source de la page de fiche avant tout clic sur « Contacter », alors le numéro n'est présent ni dans le DOM, ni dans le stockage local, ni dans le cache du service worker.
- [ ] Étant donné la dataclass `SellerSummary` et le test de contrat des champs du vendeur, quand on les lit, alors `phone` n'y figure plus.
- [ ] Étant donné les fichiers de test existants qui attendent `seller.phone`, quand ils sont mis à jour, alors ils vérifient l'absence du champ.
Règles métier : le numéro de connexion du compte n'est pas, par défaut, un numéro de contact public.
Hors périmètre : masquage de l'e-mail (déjà privé).
Questions ouvertes : aucune.

#### L0-10a-b — Réglages de contact du vendeur et consentement
En tant que prestataire, je veux choisir quels moyens de contact j'autorise (message interne, appel, WhatsApp) et quel numéro est utilisé, afin de ne révéler mon numéro que si je le décide.
Réf. : CDC §3.15 (« au choix un appel, une conversation WhatsApp ou un message interne ») ; doc07 §17 (« seulement si utilisateur choisit ») ; doc13 (`ContactPoint`, `ContactAction`) ; règle 10 ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné un nouveau compte, quand on lit ses réglages de contact, alors seul « message interne » est activé ; « appel » et « WhatsApp » sont désactivés (consentement explicite, désactivé par défaut).
- [ ] Étant donné un vendeur qui active « appel » ou « WhatsApp », quand il confirme, alors un écran lui dit en français : quel numéro sera montré, à qui (tout utilisateur connecté qui clique sur Contacter), et comment retirer son accord ; l'acceptation est enregistrée avec la date, la version du texte et le numéro concerné.
- [ ] Étant donné un vendeur qui désactive « appel » ou « WhatsApp », quand un visiteur ouvre sa fiche, alors le bouton correspondant disparaît dès le prochain chargement et l'API de contact refuse ce canal (403).
- [ ] Étant donné un vendeur sans numéro vérifié (`phone_verified` faux), quand il veut activer « appel » ou « WhatsApp », alors l'activation est refusée avec le message « Vérifiez d'abord votre numéro ».
- [ ] Étant donné un vendeur qui change de numéro de contact, quand le nouveau numéro n'est pas vérifié par code SMS, alors les canaux « appel » et « WhatsApp » restent désactivés jusqu'à la vérification.
- [ ] Étant donné une activation, un retrait ou un changement de numéro de contact, quand l'action est faite, alors une entrée `AuditLog` est écrite (acteur, action, date, sans écrire le numéro en clair).
Règles métier : consentement par canal, révocable à tout moment, effet immédiat sur les révélations futures (pas sur celles déjà faites). L'accord est par vendeur (compte), pas par offre.
Hors périmètre : horaires de joignabilité ; numéro différent par offre.
Questions ouvertes : D12 (numéro de contact distinct du numéro de connexion), LEG-PRV (section 3).

#### L0-10a-c — Action « Contacter » authentifiée qui enregistre la prise de contact
En tant que visiteur connecté, je veux contacter un vendeur par message, appel ou WhatsApp en un geste, afin de lui parler tout en ouvrant mon droit d'avis.
Réf. : CDC §3.15 (« Chaque prise de contact est enregistrée : elle alimente les statistiques et ouvre le droit d'avis ») ; règle 10, règle 12 ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné un visiteur anonyme, quand il clique sur « Contacter », alors on lui demande de se connecter ; aucune prise de contact n'est enregistrée et aucun numéro n'est renvoyé (401 côté API).
- [ ] Étant donné un visiteur connecté, quand il choisit « Message » et saisit un texte de 1 à 2000 caractères, alors une prise de contact (canal MESSAGE) est enregistrée, une conversation s'ouvre (ou est alimentée) et le vendeur reçoit une notification (comportement actuel conservé).
- [ ] Étant donné un vendeur qui autorise « appel », quand le visiteur connecté choisit « Appeler », alors l'API enregistre une prise de contact (canal CALL), répond avec le numéro au format international, et le front ouvre le lien `tel:` à partir de cette réponse.
- [ ] Étant donné un vendeur qui autorise « WhatsApp », quand le visiteur choisit « WhatsApp », alors l'API enregistre une prise de contact (canal WHATSAPP), répond avec le lien `wa.me` prérempli, et le front l'ouvre.
- [ ] Étant donné un vendeur qui n'autorise pas le canal demandé, quand le visiteur l'appelle, alors l'API répond 403 « Ce vendeur n'accepte pas ce moyen de contact. » sans numéro.
- [ ] Étant donné la réponse qui contient un numéro, quand on lit ses en-têtes, alors elle porte `Cache-Control: no-store` et le service worker ne la met pas en cache.
- [ ] Étant donné un visiteur qui demande le même canal pour la même offre dans les 24 h, quand il redemande, alors l'API renvoie à nouveau le contact sans créer de seconde prise de contact (idempotent) et les statistiques du vendeur ne comptent qu'une prise de contact.
- [ ] Étant donné un visiteur qui est le vendeur de l'offre, quand il demande un contact, alors 403 ; étant donné une offre non disponible (corbeille, masquée, expirée), alors 404 ou 409 selon la règle actuelle, sans numéro.
- [ ] Étant donné un utilisateur bloqué par le vendeur ou sanctionné, quand il demande un contact, alors l'accès est refusé sans révéler le numéro (le blocage est un lot 2 ; le critère s'applique à la sanction dès le lot 0).
- [ ] Étant donné le décompte `ContactEvent` utilisé par l'agrégat quotidien (`count_contacts_by_offer`), quand un contact CALL ou WHATSAPP est enregistré, alors il est compté comme un MESSAGE dans « contacts » du tableau de bord et de l'engagement E (une fois par expéditeur, offre et jour).
- [ ] Étant donné chaque prise de contact et chaque révélation de numéro, quand elle a lieu, alors une entrée `AuditLog` est écrite avec : acteur (visiteur), cible (offre et vendeur), canal, date ; le numéro n'est pas écrit dans le journal.
- [ ] Étant donné le vendeur, quand un visiteur a révélé son numéro, alors il reçoit une notification « [Nom] a demandé votre numéro pour [Offre] » sans que le numéro du visiteur lui soit communiqué.
Règles métier : la révélation et l'enregistrement sont une seule opération (pas de numéro sans trace). Les blocs de contact du front sont construits à partir de la réponse de l'API, jamais d'un champ de la fiche. Aucun contact ne peut être enregistré sans compte (donc le droit d'avis est toujours rattaché à un compte).
Hors périmètre : messagerie temps réel (lot 2) ; appel via la plateforme (VoIP) ; numéro masqué/relais.
Questions ouvertes : D13 (prérequis pour demander un numéro), D14 (quel contact compte comme éligible à l'avis pour CALL/WHATSAPP).

#### L0-10a-d — Limites de débit et anti-scraping
En tant que staff, je veux limiter le nombre de numéros qu'un compte peut obtenir, afin d'empêcher la collecte en masse.
Réf. : règle 10 ; CDC §3.15 ; doc07 §8 (« Rate limit ») ; règle 11 ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné un compte, quand il demande plus de K révélations de numéro (CALL/WHATSAPP) différentes en 24 h (K réglable, valeur initiale proposée : 15), alors l'API répond 429 avec un délai de nouvel essai, sans numéro.
- [ ] Étant donné une adresse IP, quand elle dépasse M révélations par heure tous comptes confondus (M réglable, proposé : 30), alors 429.
- [ ] Étant donné un compte nouvellement créé (< 24 h) ou sans numéro vérifié, quand il demande un numéro, alors la limite appliquée est celle du palier « nouveau compte » (réglable, proposé : 3 par 24 h) (voir D13).
- [ ] Étant donné un compte qui dépasse trois fois la limite en 7 jours, quand le seuil est atteint, alors un signalement automatique est ouvert pour la modération.
- [ ] Étant donné les routes de liste et de détail, quand on les parcourt page par page, alors aucun numéro n'en sort (vérifié par le test de L0-10a-a), et aucune route n'accepte une liste d'identifiants d'offres pour renvoyer plusieurs numéros d'un coup.
- [ ] Étant donné la limite atteinte, quand le visiteur voit le message, alors le texte dit en français ce qui se passe et propose le message interne comme repli (qui n'expose aucun numéro).
- [ ] Étant donné les journaux, quand on les inspecte, alors ils contiennent les dépassements de limite (compte, adresse IP hachée, date) conservés selon la durée fixée par LEG-PRV (point ouvert).
Règles métier : les limites sont des réglages de back-office (règle 11) ; les valeurs proposées sont à valider.
Hors périmètre : CAPTCHA (option à étudier si le scraping est observé).
Questions ouvertes : D13.

#### L0-10a-e — Boutons du front
En tant que visiteur, je veux des boutons de contact clairs qui ne montrent un moyen de contact que si le vendeur l'autorise, afin de savoir comment joindre le vendeur.
Réf. : CDC §3.3 (fiche offre) et §3.15 ; `ContactActions.tsx`, `lib/contact.ts` ; lot 0
Critères d'acceptation (testables) :
- [ ] Étant donné la fiche d'une offre dont le vendeur autorise seulement le message, quand elle s'affiche, alors seul le bouton « Envoyer un message » est visible.
- [ ] Étant donné la fiche dont le vendeur autorise appel et WhatsApp, quand elle s'affiche, alors les trois boutons sont visibles ; la fiche dispose d'un indicateur `allowed_channels` (liste de canaux, sans numéro).
- [ ] Étant donné un clic sur « Appeler » ou « WhatsApp », quand la requête est en cours, alors le bouton est désactivé et affiche un état de chargement ; en cas d'erreur 401, 403, 429, un message en français explique la cause.
- [ ] Étant donné un visiteur anonyme, quand il clique, alors il est redirigé vers la connexion puis revient à la fiche.
- [ ] Étant donné une fois la prise de contact enregistrée, quand le visiteur revient sur la fiche, alors il voit le bouton « Donner mon avis » (après le délai éventuel de D5) ; le numéro n'est pas réaffiché sans nouveau clic.
- [ ] Étant donné les textes, quand ils s'affichent, alors ils passent par l'i18n et sont en français.
Règles métier : la barre mobile (`layout="bar"`) et le panneau (`layout="stack"`) ont le même comportement.
Hors périmètre : refonte graphique (designer-ux si nécessaire).
Questions ouvertes : aucune.

---

## 2. Décisions à arbitrer

Légende : U = à arbitrer par l'utilisateur (Anicet/Jonathan) ; CP = le chef de projet peut trancher ; CL = à poser au client.

| # | Question | Recommandation | Qui |
|---|---|---|---|
| D1 | Que devient `Deal` (« affaire conclue ») ? | Le supprimer entièrement : modèle, `urls_deals.py`, endpoints `/api/reputation/deals/`, tests, écrans. Le CDC §3.4 remplace la condition. Une confirmation bilatérale est une preuve plus forte, mais elle est lourde et absente de la v1.2. Si on la veut plus tard, on la rajoutera comme condition « avis renforcé » sans réutiliser l'ancien code. | U (touche une règle d'avis du CDC, mais le CDC tranche déjà : validation rapide) |
| D2 | Qu'est-ce que « une interaction » pour « un avis par interaction » ? Un couple (auteur, offre), ou chaque prise de contact ? | Un avis par couple (auteur, offre) pour la note d'offre. La note vendeur compte aussi une seule fois par couple : un acheteur ne peut pas gonfler la note d'un vendeur en contactant dix offres ? À trancher : option A, une seule note vendeur par auteur et par vendeur (la dernière compte) ; option B, une par couple (auteur, offre). Je recommande A pour la note vendeur, B pour la note d'offre, avec l'avis unique par couple (auteur, offre) comme règle simple de départ. | U |
| D3 | Que montre-t-on d'un vendeur sans avis, ou avec moins de 3 avis ? | Libellé « Pas encore d'avis » (CDC), pas d'étoiles vides, pas de note neutre. Sous le seuil, la liste des avis déjà publiés reste lisible (seule la moyenne est masquée) avec la mention « 2 avis ». Le CDC dit « Pas encore d'avis en dessous de 3 avis » : litéralement, il masquerait aussi les avis. À confirmer avec le client. | CL (précision du texte du CDC) puis CP |
| D4 | Que veut dire « ancienneté » ? | Ancienneté du vendeur : « Sur Connecte+ depuis octobre 2026 » (date d'inscription du compte, ou de création de l'organisation après L0-09). Ce n'est pas l'âge des avis. Affichée dans les deux blocs. | CP |
| D5 | Garde-fous contre les avis « post-contact » fabriqués (C1) ? | Minimum viable : (a) délai réglable entre le contact et l'avis (proposé : 24 h) ; (b) un avis par couple (auteur, offre) ; (c) 5 avis/jour ; (d) le vendeur peut signaler un avis comme « contact fictif » ; (e) la modération voit la date et le canal du contact. Ne pas ajouter de preuve d'achat (hors V1). | U |
| D6 | Quelles pondérations configurables pour P × E × R × D, et comment les lire ? | `RankingSettings` (une ligne unique) : `weight_views` (1), `weight_favorites` (3), `weight_contacts` (5), `weight_shares` (8) ; `recency_half_life_hours` (72) ; `proximity_same_commune` (1,2), `proximity_same_city` (1,1), `proximity_default` (1,0). Retirer : `trust_factor_min/max`, `weight_likes`, `weight_comments`. Lecture : à chaque recalcul via `visibility.services.get_ranking_settings()` (une lecture par lot, comme aujourd'hui), jamais de constante. Validation : poids >= 0 ; demi-vie > 0 ; proximité >= 1 et commune >= ville. Journaliser les changements (règle 12). Le champ P n'a pas de pondération : voir D9. | CP |
| D7 | Sur qui porte la « note vendeur » avant L0-09 ? | Sur le `User` vendeur aujourd'hui, mais le modèle d'avis doit stocker un identifiant de « contexte vendeur » (utilisateur maintenant, `Organization` ou contexte prestataire après L0-09) pour respecter « pas de fusion des rôles » (CDC §3.4). Sans donnée à migrer, on peut le faire directement. À coordonner avec L0-09 ; architecte-technique tranche la forme. | CP + architecte |
| D8 | Quels seuils de l'anti-abus des avis et des contacts deviennent des réglages ? | Oui, en back-office : avis par jour (5), fenêtre et seuil des avis réciproques (30 j, 3), délai avant avis (24 h, D5), fenêtre de modification (48 h), durée de doublon de contact (24 h), limites de révélation (D13), seuil d'affichage de la moyenne (3). Une seule table de réglages « Avis et contact ». | CP |
| D9 | Comment calculer P lors d'une recherche ? | Hors fil : P = 1 sans recherche ni catégorie (CDC). Avec recherche ou catégorie : le CDC dit « correspondance avec la recherche et la catégorie » sans valeurs. Proposition : filtre strict dans la V1 (une offre qui ne correspond pas est exclue), P = 1 pour les offres retenues, pondération textuelle plus fine après la V1. À valider. | U |
| D10 | Où calculer D (proximité) puisqu'il dépend du visiteur ? | Le score stocké sur l'offre contient E × R (recalculé par cron), D et P sont appliqués à la lecture. À figer par l'architecte (impact sur le tri et la pagination). L'ordre par défaut aujourd'hui est `-visibility_score`. | CP + architecte |
| D11 | Affichage du nom de l'auteur d'un avis | Prénom et initiale du nom (« Marie K. »), sans photo ni téléphone. À confirmer avec le client (LEG-PRV : nom réel). | CL |
| D12 | Numéro de contact distinct du numéro de connexion ? | Oui : numéro de contact séparé (`ContactPoint` du doc13 : privé par défaut, vérifié, avec visibilité), pré-rempli avec le numéro de connexion mais soumis au consentement. Évite qu'un login soit publié sans le savoir. | U (modèle de données) |
| D13 | Prérequis et plafonds pour obtenir un numéro | Compte connecté ; téléphone ou e-mail vérifié ; palier « nouveau compte » (< 24 h) plus strict. Plafonds proposés : 15 numéros/24 h/compte, 30/h/IP, 3/24 h pour un compte neuf. Valeurs réglables. | U (valeurs) |
| D14 | Un contact CALL/WHATSAPP ouvre-t-il le droit d'avis ? | Oui (CDC §3.15), avec le libellé « Avis après contact » défini comme « contact initié depuis Connecte+ » (C2). Alternative plus stricte : ouvrir l'avis seulement après un message ou après un délai. | U |
| D15 | Retirer ou non le badge « Vendeur fiable » ? | Retirer (règles 3 et 4). À ajouter dans L0-07. | CP (conforme aux règles verrouillées) |
| D16 | Les vendeurs reçoivent-ils l'identité de ceux qui ont révélé leur numéro ? | Oui : nom d'affichage et offre concernée, pas de numéro. Journalisé. | CP |

Décisions que le chef de projet peut trancher seul (conformes aux règles verrouillées et au CDC) : D4, D6, D7 (avec l'architecte), D8, D10 (avec l'architecte), D15, D16.
Décisions pour l'utilisateur : D1, D2, D5, D9, D12, D13, D14.
Décisions pour le client : D3, D11, et les questions LEG-PRV ci-dessous.

---

## 3. Questions juridiques LEG-PRV à poser au client (téléphone du vendeur)

Rattachées à doc12 : LEG-PRV-01 (bases légales), -03 (consentements), -04 (droits), -05 (durées), -09 (journalisation), -11 (marketing), -12 (identifiants).

1. LEG-PRV-01 : Quelle base légale couvre la communication du numéro d'un vendeur à un utilisateur connecté (consentement du vendeur, exécution d'un service, intérêt légitime) ? Un consentement par canal, révocable, suffit-il ?
2. LEG-PRV-03 : Le consentement est-il valable s'il est donné dans un écran des réglages avec un texte versionné ? Quelle formulation exacte en français (et en lingala/swahili plus tard) faut-il montrer ?
3. LEG-PRV-03 : Le vendeur peut-il rendre son numéro visible à tous les visiteurs, y compris non connectés, s'il le demande expressément ? (Ce n'est pas prévu en V1 ; nous voulons savoir si c'est permis.)
4. LEG-PRV-05 : Durée de conservation de la trace « X a obtenu le numéro de Y pour l'offre Z, le [date] » (contacts et journal d'audit) ? Durée de conservation après la clôture d'un compte ? Que devient cette trace si le visiteur demande l'effacement de son compte alors que l'avis qu'il a écrit reste (CDC §3.16) ?
5. LEG-PRV-04 : Quand le vendeur retire son accord, doit-on informer ceux qui ont déjà reçu le numéro ? Le numéro déjà révélé reste-t-il utilisable par eux ?
6. LEG-PRV-04 : Le vendeur peut-il demander la liste des personnes qui ont obtenu son numéro ? Le visiteur peut-il obtenir la liste des numéros qu'il a demandés ?
7. LEG-PRV-09 : La plateforme peut-elle conserver l'adresse IP (ou une empreinte hachée) des demandes de numéro pour limiter le scraping, et pour combien de temps ?
8. LEG-PRV-11 : Un visiteur qui obtient un numéro peut-il l'utiliser pour de la prospection commerciale ? Quelle mention faut-il afficher (usage limité à l'objet de l'offre) ?
9. LEG-PRV-12 : WhatsApp (Meta) reçoit le numéro lors de l'ouverture du lien `wa.me` : faut-il informer le vendeur et le visiteur ? Transfert hors RDC (LEG-PRV-06) ?
10. LEG-PRV-01 : L'avis publié affiche le nom d'affichage de l'auteur : quelle forme est acceptable (nom complet, prénom + initiale, pseudo) ?
11. LEG-PRV-05 : Durée de conservation des avis et des réponses (y compris masqués) et conséquence d'une demande de suppression par leur auteur ?
12. LEG-PRV-01 : Le modérateur peut-il voir le numéro d'un vendeur et le canal utilisé lors d'un litige sur un avis « contact fictif » ? (lien avec la question déjà notée sur l'accès du Modérateur aux e-mails/téléphones.)

---

## 4. Ordre de livraison conseillé et dépendances

Il n'y a pas de donnée à migrer : on peut modifier les migrations initiales en suivant la procédure de l'ADR 0002, ou ajouter des migrations de suppression ; l'architecte choisit.

| Étape | Contenu | Agent | Dépend de | Parallélisable avec |
|---|---|---|---|---|
| 0 | Arbitrage D1, D2, D5, D9, D12, D13, D14 ; contrat d'API figé (champs `offer_rating`, `seller_rating`, `allowed_channels`, endpoint d'action de contact, codes d'erreur) | analyste + architecte-technique + utilisateur | — | — |
| 1 | **L0-10a-a** : retrait de `phone` des sérialiseurs publics (correctif immédiat, peu de lignes) + test de non-fuite sur toutes les routes publiques | dev-backend | — | 2 |
| 2 | Plan de données : `Review` (deux notes, lien vers la prise de contact par UUID, contexte vendeur), `ContactEvent` + canal, réglages de contact du vendeur, table de réglages « Avis et contact » | architecte-technique | 0 | 1 |
| 3 | **L0-10a-b/c/d** (backend) : consentement, action de contact, journalisation, limites | dev-backend | 2 | 4 |
| 4 | **L0-07** et **L0-08** (backend) : retrait du Trust Score, nouveau `compute_score`, `RankingSettings` ; ils sont indépendants des avis sauf pour le retrait de `recompute_trust_score` | dev-backend | 2 | 3 |
| 5 | **L0-10** (backend) : nouvelle condition d'avis, suppression de `Deal`, double note, anti-abus reconfiguré | dev-backend | 3 (le contact enregistré est la preuve), 4 (plus de Trust Score) | — |
| 6 | Front : contrat figé à l'étape 0 ; boutons de contact (L0-10a-e), blocs de notes (L0-07-b), formulaire d'avis (L0-10), suppression de `TrustScore.tsx`/`lib/trust.ts` ; en parallèle de 3 à 5 avec des mocks | dev-frontend | 0 (contrat) ; intégration réelle après 5 | 3 à 5 |
| 7 | Revue sécurité (révélation du numéro, cache, throttles, `AuditLog`) | auditeur-securite | 3, 6 | — |
| 8 | Relecture, recette des critères d'acceptation, passe i18n (L0-18) | relecteur-code, qa-testeur, dev-frontend | 5, 6, 7 | — |

Dépendances externes : L0-09 (contextes) influence D7 mais ne bloque pas : on stocke un identifiant de contexte vendeur dès maintenant. L0-11 (`/api/v1/`) : les nouveaux endpoints doivent être créés directement sous `/api/v1/` si L0-11 est faite avant, sinon renommés avec L0-11. L0-16 (outbox) : la notification et l'agrégat de contacts passeront par des événements ; en attendant, les écritures indépendantes actuelles sont conservées. L0-18 (i18n) après L0-07, L0-09, L0-14.

Mise à jour backlog proposée : ajouter à L0-07 « retrait du badge Vendeur fiable et de `avg_rating` issu du Trust Score » ; ajouter à L0-10 « suppression de `Deal` ». Découper si besoin L0-10a en -a (retrait du champ, correctif immédiat) et -b..e.

Propositions de modification du CDC (diff texte, à valider ; le CDC n'est pas modifié) :

- §3.4, ligne « Affichage » — ancien : « Moyenne, nombre d'avis et ancienneté affichés ensemble ; « Pas encore d'avis » en dessous de 3 avis ». Nouveau : « Moyenne, nombre d'avis et ancienneté du vendeur (« Sur Connecte+ depuis <mois année> ») affichés ensemble, pour l'offre et pour le vendeur séparément ; en dessous de 3 avis (réglable), la moyenne est remplacée par « Pas encore d'avis » et les avis déjà publiés restent lisibles ».
- §3.4, ligne « Droit d'évaluer » — ajouter : « La prise de contact est enregistrée par une action authentifiée (message, appel, WhatsApp) ; un délai réglable sépare le contact de l'avis ».
- §3.4, ligne « Anti-abus » — ajouter : « Les seuils sont des réglages du back-office ».
- §3.15, paragraphe Lot 1 — ajouter : « Le numéro du vendeur n'apparaît jamais dans les pages ni les listes publiques. Il n'est communiqué qu'à un utilisateur connecté qui clique sur « Appeler » ou « WhatsApp », si le vendeur a accepté ce canal ; chaque communication est limitée en nombre et journalisée ».

---

## 5. Données de développement

Confirmation : aucune donnée de production n'existe (CLAUDE.md §8 ; ADR 0002 : migrations réinitialisées, UUID). Aucune migration de données n'est nécessaire pour L0-07, L0-08, L0-10 ni L0-10a :
- les avis, `Deal` et `Trust Score` de développement sont jetables ;
- les colonnes supprimées (`User.trust_score`, `User.reviews_count`, `Review.deal`, `Review.reviewed_user` au profit du contexte vendeur) n'ont pas besoin de conversion ;
- les bases locales SQLite se recréent avec `migrate` et le jeu de données de départ ;
- seules les migrations de schéma sont requises (ou la réécriture des `0001` de `identity`, `reviews`, `visibility`, `marketplace` si l'ADR 0002 l'autorise encore : décision de l'architecte, à demander à l'utilisateur s'il faut modifier des migrations déjà partagées, CLAUDE.md §9).

---

## 6. Décisions du chef de projet (09/10/2026)

Prises sur la délégation donnée par l'utilisateur (« choisis la meilleure option à chaque question »). L'utilisateur peut les corriger ; rien n'est irréversible avant la production.

| Décision | Choix retenu |
|---|---|
| D1 | Supprimer `Deal` entièrement (livré avec L0-10, migrations 0001 réécrites) |
| D2 | Un avis par couple auteur-offre ; une note vendeur par auteur et par vendeur |
| D4 | Ancienneté du vendeur : « Sur Connecte+ depuis <mois année> » |
| D5 | Garde-fous : délai réglable entre contact et avis, un avis par couple auteur-offre, signalement « contact fictif » |
| D6 | Pondérations proposées (vues 1, favoris 3, contacts 5, partages 8 ; demi-vie 72 h ; proximité 1,2 / 1,1 / 1,0), lues en base |
| D8 | Réglages anti-abus dans une table « Avis et contact » (règle 11) |
| D9 | Recherche : filtre strict en V1, P = 1 |
| D12 | Numéro de contact distinct du numéro de connexion, consentement désactivé par défaut, par canal, révocable |
| D13 | 15 révélations par 24 h et par compte, 30 par heure et par IP, 3 par 24 h pour un compte de moins de 24 h (valeurs en réglages) |
| D14 | Un contact CALL ou WHATSAPP ouvre le droit d'avis ; libellé défini comme « contact initié depuis Connecte+ » |
| D15 | Retirer le badge « Vendeur fiable » et `avg_rating` issu du Trust Score (ajouté à L0-07) |
| D16 | Le vendeur voit qui a demandé son numéro, sans le numéro du visiteur |

**À poser au client :** D3 (affichage sous le seuil de 3 avis : masquer la moyenne seulement), D11 (forme du nom d'auteur : prénom + initiale proposé), les 12 questions LEG-PRV de la section 3.

**Ordre d'exécution :** L0-16 (outbox) d'abord, car il touche les mêmes `services.py` ; puis L0-10a-a (retrait de `phone` + test de non-fuite, avec adaptation du front) ; puis L0-07/L0-08 et L0-10a-b à e en parallèle (branches distinctes, fichiers disjoints à vérifier) ; puis L0-10.
