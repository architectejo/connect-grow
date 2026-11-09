# L0-09 T9 (L0-09h) — Conversion des comptes entreprise puis contraction du modèle

- **Statut :** T9-1 (conversion) et T9-2 (contraction) livrées le 09/11/2026 (voir ADR 0006 §20, « Livraison de T9-2 ») ; T9-3 et F-T9 restent à faire. Plan proposé par architecte-technique ; les points de la section 9 ont été validés par le chef de projet (délégation du client).
- **Date :** 24/10/2026. **Base de départ :** `main` a85a453 (1568 tests backend verts).
- **Références :** ADR 0006 §2 (D1, D2), §3 (A3, A11), §10 (migrations), §11.4, §15, §17.3, §19.2 à 19.6 ; ADR 0001 (SQLite seul), ADR 0002 (réinitialisation d'octobre), ADR 0003 (outbox) ; CLAUDE.md §4 (règles 1, 3, 10, 12) et §5, §9 (migrations).
- **Résumé :** la conversion est une **migration de données** (une par domaine, un seul `migrate`), précédée d'un contrôle de pré-vol en lecture seule et suivie d'une **contraction** livrée à part, après accord. Aucune réinitialisation de migrations maintenant (recommandée une seule fois, en fin de projet, avec le passage à MySQL).

---

## 0. Écarts entre l'ADR 0006 et l'état réel du dépôt (à connaître avant de lire la suite)

L'ADR §10.2 prévoyait `identity 0008`/`0009`, `marketplace 0003`/`0004`, `visibility 0003`/`0004`, `reviews 0004`. Ces numéros sont **périmés** : les tâches T1 à T8 ont consommé d'autres numéros. Numérotation réelle, relevée sur `main` :

| Domaine | Dernière migration | Contenu utile pour T9 |
|---|---|---|
| identity | `0010_identitysettings_kyb_file_retention_days` | `0006` schéma des contextes, `0008` CHECK contact, `0009` `KycDocument.business_profile` nullable |
| marketplace | `0009_fill_offer_seller_context` | remplissage **déjà fait** : toute offre = `USER` + `created_by` = ancien vendeur ; `seller_is_public` posé |
| visibility | `0005_fill_counter_seller_context` | idem pour les compteurs |
| reviews | `0005_provider_context_choice` | `Review.seller_context_*` existe déjà (NOT NULL, défaut `USER`) : **les avis d'un compte entreprise pointent encore le compte** |
| messaging | `0003_message_sender_set_null` | colonnes de contexte nulles (nul = ancien régime) |
| notifications | `0002_notification_context` | idem |
| moderation | `0004_auditlog_context` | `AuditLog.context_*` disponible |

Autres constats qui corrigent l'énoncé ou l'ADR :
1. **`SellerSummary.user_type` n'existe plus** (la dataclass de `identity/sellers.py` n'a plus ce champ ; le test `tests_contexts.py` garde les clés). Rien à retirer ; la dette de l'ADR §19.2 est soldée. Les seuls restes de `user_type` en code non test sont `User.user_type` (modèle), `UserAdmin` (`list_display`, `list_filter`).
2. **Routes KYC historiques encore montées** : `identity/urls.py` expose `kyc/documents/` (liste et dépôt), `kyc/documents/<id>/` (suppression), toutes fondées sur `request.user.business_profile`. Le front ne les appelle plus (il utilise `organizations/<id>/kyc/documents/`). À retirer en T9b. Restent `kyc/review-queue/`, `kyc/documents/<id>/decision/` et `…/download/` (personnel de vérification).
3. **`setup_roles` n'a jamais reçu les permissions d'organisation** prévues par l'ADR §11.4 (seulement `identity.businessprofile: view` pour l'administrateur). À corriger en T9b ; sans `suspend_organization` pour l'administrateur, personne ne peut réactiver une organisation convertie en état suspendu (section 2.5).
4. Les dossiers `backend/apps/accounts/`, `apps/reputation/`, `apps/interactions/` ne contiennent que `__pycache__` / `management/` vides, **non suivis par git** : résidus locaux, sans effet. Ne pas les supprimer sans accord (aucune suppression de dossier sans l'utilisateur) ; simple signalement.
5. `payments.Transaction.seller` (FK vers `User`) **n'est pas un vestige** : module gelé, hors V1 (ADR §11.4, refonte L1-12). Ne pas y toucher.
6. `get_allowed_channels(seller_ids)` et `get_contact_endpoint(seller_id, …)` de `identity/services.py` sont des assistants **par compte** encore utilisés par `identity/sellers.py` (contextes `USER` et `PROVIDER`). Ce ne sont pas des vestiges.

---

## 1. Inventaire exhaustif des vestiges (relevé du 24/10/2026)

Recherche : `user_type|BusinessProfile|business_profile` (hors migrations) et rattachement `seller` (FK) dans `backend/` et `connect-grow/src/`.

### 1.1 Code applicatif backend

| Vestige | Fichier : lignes | Traitement |
|---|---|---|
| `User.user_type`, `USER_TYPE_CHOICES` | `identity/models.py` 72-75, 95 | retiré en `identity 0014` |
| `BusinessProfile` (+ `set_category_ids`, `category_ids`) | `identity/models.py` 137-175 | supprimé en `identity 0013` |
| `BusinessProfileCategory` | `identity/models.py` 177-186 | supprimé en `identity 0013` |
| `KycDocument.business_profile` (FK nulle) et `__str__` qui la lit | `identity/models.py` 290-292, 316 | FK retirée en `identity 0012` ; `__str__` réécrit |
| `KycDocument.organization` nullable | `identity/models.py` 295-297 | NOT NULL en `identity 0012` |
| `KycDocument.REQUIRED_TYPES` | `identity/models.py` 278 ; lu par `services.recompute_verification` et `tests_verification.py` 477 | supprimé avec `recompute_verification` ; le test passe par `OrganizationDocumentRequirement` |
| `recompute_verification` | `identity/services.py` 101-121 | supprimé |
| branche « ancien profil » de `get_document_for_download` | `identity/services.py` 148-162 | supprimée (`select_related('business_profile')` retiré) |
| branche « ancien profil » de `decide_kyc_document` (`recompute_verification`, `Cette pièce n'est rattachée à aucun profil…`) | `identity/services.py` 188-241 | supprimée ; `organization` toujours renseignée |
| `KycDocumentListCreateView`, `KycDocumentDeleteView` | `identity/views.py` 314-360 ; routes `kyc_documents`, `kyc_document_delete` dans `identity/urls.py` 76-78 | supprimés (404 ensuite) |
| `KycReviewQueueView.select_related('business_profile', …)` | `identity/views.py` 368-370 | `select_related('organization')` seul |
| `KycDocumentSerializer.validate` (lit `user.business_profile`, `KYC_MAX_DOCUMENTS_PER_PROFILE`) et import `BusinessProfile` | `identity/serializers.py` 11, 253-301 | `validate` retiré ; le sérialiseur ne sert plus qu'à la lecture (file de vérification, décision) : `file` en écriture seule disparaît |
| docstring de `RegisterSerializer.create` (« compatibilité transitoire `user_type` ») | `identity/serializers.py` 186-190 | reformulée ; **le comportement reste** : DRF ignore les champs inconnus, test `tests_l021` conservé |
| `UserAdmin` (`user_type` en colonne et filtre), `BusinessProfileAdmin`, `BusinessProfileCategoryInline`, `KycDocumentAdmin` (colonnes, recherche, `select_related`, `readonly_fields` sur `business_profile`) | `identity/admin.py` 24, 31-32, 104-133 | retirés / réécrits |
| `identity.businessprofile: view` | `moderation/management/commands/setup_roles.py` 29 | retiré ; permissions d'organisation ajoutées (section 5.4) |
| `Organization.legacy_business_profile_id` | `identity/models.py` 520 ; lu par `identity/acting.py` 299 et `identity/views_organizations.py` 99 (`migrated_from_business`) | **conservé** (voir 2.9 et section 9, question Q3) |
| `LegacyAccountMapping` | `identity/models.py` 639-645 | **conservée** (idem) |
| `Offer.seller` (FK `User`, CASCADE, nulle) | `marketplace/models.py` 124-126 | retirée en `marketplace 0011` |
| index `offer_seller_deleted` | `marketplace/models.py` 201 | retiré en `marketplace 0011` |
| passerelle `Offer.save()` (`seller` → contexte `USER`, `created_by`) | `marketplace/models.py` 209-216 (`TODO(T9)`) | retirée |
| `Offer.seller_context_type/id` nullables | `marketplace/models.py` 112-113 | NOT NULL en `marketplace 0012` |
| écriture de `offer.seller = actor` | `marketplace/services.py` ~358 (`create_offer`) | retirée |
| `readonly_fields` contenant `seller` | `marketplace/admin.py` 25 | retiré |
| `DailyVisibilityCounter.seller` (FK nulle, CASCADE) et index `visib_counter_seller_date` | `visibility/models.py` 102-105, 119 | retirés en `visibility 0007` |
| passerelle `DailyVisibilityCounter.save()` | `visibility/models.py` 123-129 (`TODO(T9)`) | retirée |
| `seller_context_*` nullables | `visibility/models.py` 100-101 | NOT NULL en `visibility 0008` |
| Review : contexte des avis des anciens comptes entreprise | `reviews` (données) | converti en `reviews 0006` (section 3) |

Aucune autre référence à `.seller` (FK) en code non test : `OfferSerializer.seller` est un `SerializerMethodField` déclaré (marketplace/serializers.py 83, 198), donc sans dépendance à la colonne ; `moderation`, `messaging`, `notifications`, `reviews`, `visibility` n'écrivent plus `seller`.

### 1.2 Scripts, configuration et documentation

| Élément | Détail | Traitement |
|---|---|---|
| `backend/scripts/recette_contrat_http.py` | 15 occurrences : schéma `me` avec `user_type`/`business_profile` (153-160), inscription avec ces champs pour vérifier qu'ils sont ignorés (241-250), **création d'un `BusinessProfile` en base pour exercer les routes KYC historiques** (252-255 ; casse à la contraction), `PATCH me` (303-309) | réécrire : KYC par `organizations/<id>/kyc/documents/` ; garder les contrôles « champ ignoré » ; plus aucun import de `BusinessProfile` |
| `backend/README.md` | lignes 61-62 (décrivent le retrait côté API : exactes, à compléter par la conversion et le retrait des routes `kyc/documents/`) ; section cron inchangée | mise à jour |
| `backend/backend/settings.py` 330, `settings_test.py` 32 | `KYC_MAX_DOCUMENTS_PER_PROFILE` encore lu par `identity/verification.py` 207 | **conservé** (réglage utilisé par le chemin organisation) ; renommer en dette L1 |
| Docs | `docs/adr/0002`, `0004`, `0006`, `docs/specs/L0-09-compte-contextes.md`, `L0-09-ecrans-contextes.md`, `docs/suivi/*` | citations historiques : **ne pas réécrire** ; ajouter la section 20 à l'ADR 0006 (pointeur vers ce document) et mettre à jour BACKLOG/JOURNAL |
| `cron/crontab` | `sync_seller_visibility` déjà planifiée | rien (à lancer une fois à la main après conversion, voir 2.8) |

### 1.3 Tests backend (à migrer, pas à supprimer)

Occurrences de `user_type|BusinessProfile|business_profile` : `common/tests_recette_lot0.py` (23), `identity/tests_organizations_api.py` (19), `identity/tests.py` (11), `identity/tests_admin.py` (8), `identity/tests_verification.py` (6), `common/tests_l021.py` (6), `common/tests_privacy.py` (4), `identity/tests_throttling.py` (3), `marketplace/tests_seller_profile.py` (3), `identity/tests_organizations.py` (2), `common/tests_images.py` (2), `identity/tests_acting_context.py` (1).

Occurrences du rattachement `seller=` / `.seller` / `Offer(...)` / `Offer.objects.create(` : environ **450 lignes dans 35 fichiers** (les plus chargés : `marketplace/tests.py` 64, `marketplace/tests_contexts.py` 63, `common/tests_recette_contact.py` 50, `marketplace/tests_seller_profile.py` 34, `moderation/tests.py` 32, `marketplace/tests_reveal.py` 25, `reviews/tests.py` 24, `common/tests_recette_lot0.py` 21, `reviews/tests_eligibility.py` 18, `moderation/tests_corrections.py` 16, `visibility/tests.py` 15, `messaging/tests.py` 14, …).

Règle : **le nombre de tests ne baisse pas** (ADR §12). Un test des routes KYC historiques est réécrit contre la route d'organisation équivalente ou remplacé par un test de conversion ; il n'est jamais simplement supprimé. Un test qui garantit qu'un champ retiré n'a aucun effet (`tests_l021`, `tests_recette_lot0` 405-412) est **conservé** (il garde la non-régression d'API), seul son jeu de données change.

### 1.4 Front (`connect-grow/src`) : déjà quasi propre

| Élément | Constat | Traitement |
|---|---|---|
| `user_type`, `business_profile` en code | **aucun** hors tests de garde : `api/backend-contract.test.ts` 90 et 129-130, `api/backend-identity-contract.test.ts` 302-303 (vérifient l'absence), `i18n/client-rules.test.ts` 74 (regex d'interdiction), `lib/validation.test.ts` 20 (fixture d'erreur imbriquée `business_profile.logo`) | conserver les gardes ; réécrire la fixture de `validation.test.ts` avec un champ réel (`organization.logo` n'existe pas : prendre `logo`) |
| `is_verified` dans `api/types.ts` 304 | concerne le **numéro de contact** (`phone.is_verified`), pas l'entreprise | aucun |
| `migrated_from_business` (`types.ts` 383, 428 ; `lib/legacy-notice.ts` ; `LegacyOrgNotice.tsx` ; `AuthContext.tsx` ; fixtures `contexts.json` 24 `true`, `backend-identity.json`) | contrat figé ADR 17.1 Q-F2 | **conservé** tant que `legacy_business_profile_id` existe (Q3) |
| `kyc/documents/` | uniquement les routes d'organisation (`use-organizations.ts` 120-155) ; `cache-rules.test.ts` 48 et 130 citent `/api/accounts/kyc/documents/` et `businesses/3/` comme chemins non cachables | remplacer par les chemins réels (`organizations/…/kyc/documents/`), garder une assertion « jamais caché » |
| Route et page `/businesses` (`App.tsx` 126, `Navbar.tsx` 28, `FooterSection.tsx` 13, `SellCtaSection.tsx` 29, `fr.ts` 12) | libellé « Organisations », appelle déjà `organizations/` | renommage de l'URL en `/organisations` : **hors périmètre T9** (cosmétique, demande d'accord) |
| Fixtures `src/api/__fixtures__/*.json` | `backend-identity.json`, `backend-lot0.json`, `contexts.json` ; elles reflètent le contrat, pas la base | à régénérer **seulement si** un champ de contrat change (section 6 : aucun champ ne change en T9a ; en T9b, aucun non plus) ; revérifier contre le backend final |

---

## 2. Règle de conversion d'un compte entreprise en organisation

### 2.1 Décision : migration de données, pas commande de gestion

| Critère | Migration de données (retenue) | Commande de gestion |
|---|---|---|
| Garantie d'ordre avec la contraction | oui : `migrate` ne peut pas atteindre la contraction sans avoir passé la conversion (dépendances de migrations) | non : un oubli laisse des comptes non convertis, la contraction détruirait leurs données |
| Frontières de modules | permet la lecture d'`identity` par les autres domaines **via la table de correspondance** et le modèle historique (exception A11, lecture seule) | une commande qui touche offres, compteurs et avis doit importer les services de quatre domaines ; elle n'a pas à écrire dans leurs tables sans leurs services |
| Idempotence | par table de correspondance et par colonne `legacy_business_profile_id` | idem |
| Réversibilité | partielle (section 4) | possible mais sans garantie d'ordre |
| Simulation avant exécution | **à compenser** par la commande de pré-vol (2.2) | native |
| Base vierge (CI, nouveaux développeurs) | no-op automatique | à ne pas lancer |

**Décision : migration de données (ADR 0006 A11 et D1 confirmés), complétée par une commande de pré-vol en lecture seule `check_legacy_conversion`** (dans `identity`, ne lit que `identity` et les services de `moderation` déjà importés par `identity`). Elle ne modifie rien, ne s'exécute pas dans la CI de production, et sert à décider « on migre » (section 4). Les comptes du côté des autres domaines sont comptés par les migrations elles-mêmes (journalisation du nombre de lignes déplacées, affirmations de post-condition).

Pourquoi pas une commande idempotente et réversible : l'idempotence et la réversibilité de la commande ne protègent pas du vrai risque, qui est une contraction exécutée sur une base non convertie. La migration lie les deux étapes par le graphe de dépendances.

### 2.2 Commande de pré-vol `check_legacy_conversion` (lecture seule)

Sortie : identifiants et comptages, **jamais de nom, de NIF, d'e-mail ni de téléphone** (règle 10 ; les journaux de console sont copiés dans des tickets). Contenu :
- nombre de `BusinessProfile`, de comptes `user_type='ENTREPRISE'` sans profil, de profils déjà dans `LegacyAccountMapping` ;
- profils dont le nom, une fois nettoyé (2.4), est vide, a moins de 2 caractères, dépasse 255 caractères ou mélange latin, cyrillique et grec ;
- noms en collision (casse et accents ignorés) entre profils, et avec des organisations existantes : liste de paires d'identifiants ;
- NIF non vides en doublon entre profils (identifiants seulement) ;
- bios de plus de 2000 caractères ; profils avec plus de 5 catégories ;
- profils dont `is_verified` diffère du calcul « trois types `RCCM`, `ID_NATIONALE`, `PIECE_GERANT` validés » (avec `OrganizationDocumentRequirement` de `ENTREPRISE`) ;
- propriétaires `is_active=False` ou sous sanction bloquante (`moderation.services.get_restricted_user_ids`) ;
- pièces dont le fichier est absent du stockage privé ;
- pièces déjà rattachées à une organisation ET à un profil (incohérence).
Code de sortie 0 s'il n'y a pas d'anomalie bloquante (aucune n'est bloquante : tout est corrigeable par la règle ci-dessous ou signalé au personnel), 1 si une table attendue manque. Testée.

### 2.3 Table de correspondance (champ par champ), exécutée par `identity 0011_convert_business_profiles`

Pour chaque `BusinessProfile` sans ligne dans `LegacyAccountMapping` (et sans `Organization.legacy_business_profile_id` égal à son identifiant, pour reprendre une correspondance perdue). **Le critère est l'existence du profil, pas la valeur de `user_type`** (un compte `ENTREPRISE` sans profil et tout compte `PARTICULIER` sans profil ne reçoivent rien ; un `PARTICULIER` qui aurait un profil serait converti).

| Source | Destination | Remarque |
|---|---|---|
| `BusinessProfile` | `Organization` créée directement par le modèle historique (pas par `create_organization` : ni plafond, ni `phone_verified`, ni audit synchrone, ni événement) | voir 2.9 pour la traçabilité |
| `business_name` | `name` | nettoyage 2.4 ; **aucune unicité** (A12) |
| (aucune source) | `org_type = 'ENTREPRISE'` | le profil n'avait pas de type ; correction par le personnel en admin (le type est immuable par l'API) ; signalé dans le pré-vol |
| `bio` | `description` | tronquée à 2000 caractères ; l'original reste dans `BusinessProfile` jusqu'à la contraction |
| `logo` | `logo` | **même nom de fichier**, aucun déplacement ni copie de fichier (le dossier reste `business_logos/`) ; le prochain remplacement du logo écrit dans `organization_logos/` ; les anciens fichiers deviennent orphelins : purge **non faite** sans accord (section 9, Q5) |
| `nif` | `nif` | non public (règle 10) |
| (aucune source) | `city_id`, `commune_id` = `NULL` | l'ancien profil n'avait pas d'adresse propre ; celles du compte (donnée personnelle) ne sont PAS reprises (décision du 09/11/2026, LEG-PRV) ; l'organisation les renseigne elle-même |
| catégories (`BusinessProfileCategory`) | `OrganizationCategory` | toutes, même au-delà de 5 (les données ne sont pas rognées) |
| `user.is_active` | `status` | actif → `ACTIVE` ; **inactif → `SUSPENDED`**, `suspension_reason = 'other'` (voir 2.5) |
| `profile.created_at` | `Organization.created_at` et `Membership.joined_at` | conserve l'ancienneté (`member_since`) ; `updated_at` = date de conversion |
| `profile.user` | `Membership(role=OWNER, status=ACTIVE, added_by=NULL)` | seul membre ; aucun autre compte n'obtient de rôle |
| `profile.user` | `Organization.created_by` | |
| `profile.pk` | `Organization.legacy_business_profile_id` | alimente `migrated_from_business = true` (ADR 17.1) |
| `KycDocument` du profil | `organization` posée, `uploaded_by = propriétaire` | statut, motif, décideur, dates et **fichier inchangés** (le champ `file` garde le même chemin ; aucun fichier déplacé) |
| `is_verified` | **rien** | la vérification est dérivée (règle 3, A6). Équivalence vérifiée par le pré-vol et par un test (2.6) |
| (aucune) | `LegacyAccountMapping(user_id, organization_id)` | une seule ligne par profil |

Ne sont **pas** transférés (ADR 10.3, confirmé) : `ContactPoint` et `ContactConsent` du propriétaire (le consentement personnel ne vaut pas pour l'organisation ; l'organisation n'offre que `MESSAGE`, `org_phone_channels_enabled` étant fermé), photo du compte, conversations, messages, notifications (2.7).

### 2.4 Nettoyage du nom (migration, sans appeler les services)

Le nom d'une donnée existante n'est pas rejeté (on ne perd pas une entreprise parce que son nom est inhabituel) mais ne doit pas casser l'écran d'édition : le nettoyage applique ce qui est sans risque, le reste est signalé.
1. retrait des caractères Unicode de catégories `Cc`, `Cf`, `Zl`, `Zp`, repli des espaces multiples, retrait des espaces de bord (même règle que l'ADR §17.5.3, sans NFKC pour ne pas modifier une marque) ;
2. troncature à 255 caractères ;
3. nom vide ou de moins de 2 caractères après nettoyage : nom neutre `Organisation <8 premiers caractères de l'identifiant du profil>` (jamais le nom ou l'e-mail du compte : règle 10) ;
4. mélange latin/cyrillique/grec : **conservé**, listé au pré-vol (le contrôle d'homoglyphes ne s'applique qu'aux saisies de l'API).
Collisions de noms : **aucun suffixe, aucune fusion** (A12). Listées au pré-vol pour examen du personnel.

### 2.5 Cas limites

| Cas | Règle |
|---|---|
| Profil sans offre | converti ; organisation `ACTIVE` (elle apparaît dans l'annuaire, comme l'ancien profil dans `businesses/`) |
| « Plusieurs profils » | impossible par compte (`OneToOneField`). Plusieurs comptes pour la même entreprise (même NIF ou même nom) : **une organisation par profil**, jamais de fusion automatique ; doublons de NIF listés au pré-vol ; la fusion passera par l'équipe (L1-01) |
| Propriétaire `is_active=False` (désactivé ; `Sanction.apply` passe par `set_account_active`) | organisation **`SUSPENDED`** (`suspension_reason='other'`), offres non publiques (`seller_is_public=false`). Raison : avant T9 `seller__is_active` masquait les offres ; sans cela la conversion **republierait** les offres d'un compte banni (régression de sécurité). Conséquence assumée : la levée d'une sanction ne réactive pas l'organisation, le personnel utilise l'action admin « Réactiver » (section 5.4, permission) |
| Propriétaire actif mais sous sanction bloquante en cours (`SUSPENSION_TEMPORAIRE`/`BANNISSEMENT`, `is_active` vrai, `ends_at` nul ou futur) | **`SUSPENDED`** comme un compte désactivé (décision du 09/11/2026) : `identity 0011` lit `moderation.Sanction` en lecture seule par `apps.get_model` (une requête avant la boucle ; exception A11, dépendance `identity 0011` -> `moderation 0004` autorisée dans `common/tests.py`). Sanction échue, levée ou avertissement : `ACTIVE`. Le pré-vol applique la même règle (« sera SUSPENDED ») |
| Nom vide, trop long, mixte, en collision | 2.4 |
| Description de plus de 2000 caractères | tronquée, comptée au pré-vol |
| Logo absent du disque | l'organisation garde le nom de fichier ; l'affichage tombe sur l'absence de logo (comportement actuel) ; compté au pré-vol |
| Profil dont `is_verified` est vrai sans pièces suffisantes (positionné à la main) | **non reproduit** (règle 3) ; liste au pré-vol ; le personnel revérifie |
| Pièce rattachée à la fois à un profil et à une organisation | conservée telle quelle, signalée ; aucune réaffectation |
| Propriétaire personnel du personnel de vérification (`is_staff` ou permission `review_kycdocument`) | converti ; la règle de conflit d'intérêts (ADR §18.3) lui interdit ensuite de décider ses propres pièces (il a un `Membership`) : comportement voulu |
| Propriétaire qui a déjà créé des organisations avec le nouveau flux | la conversion **n'applique pas** le plafond (ADR 10.3, D5) ; au-delà de 10 appartenances, il ne peut plus en créer, pas de perte |
| Double exécution / reprise après erreur | idempotent (2.3, clé de correspondance) ; la migration entière est dans une transaction (SQLite exécute le DDL en transaction) : échec = rien n'est écrit |

### 2.6 Rattachement des autres données (migrations d'autres domaines, une par domaine)

Chacune dépend de `identity 0011` (autorisé par `test_no_migration_depends_on_another_domain_except_identity`) et lit **uniquement** `identity.LegacyAccountMapping` (et `Organization.status` pour la visibilité) via `apps.get_model` : exception A11 déjà documentée (lecture seule dans une migration), à reconduire dans `common/boundaries` si le contrôle statique la signale.

| Migration | Opération (par ligne de correspondance, `UPDATE … WHERE`) |
|---|---|
| `marketplace 0010_convert_offer_contexts` | `Offer` où `seller_context_type='USER'` et `seller_context_id=<user_id>` → `('ORGANIZATION', <organization_id>)` ; `created_by` **inchangé** (trace de l'auteur, Q-CP7) ; `seller_is_public = (organisation ACTIVE)` ; `seller` (FK) **laissé tel quel** pour le retour arrière |
| `visibility 0006_convert_counter_contexts` | `DailyVisibilityCounter` idem ; `views`, `shares`, `contacts` inchangés |
| `reviews 0006_convert_review_contexts` | `Review` où `seller_context_type='USER'` et `seller_context_id=<user_id>` → `('ORGANIZATION', <organization_id>)` : **les avis suivent l'organisation** (la note de l'ancien compte entreprise devient celle de l'organisation ; règle 4 : toujours par contexte). Recalcul des `counts_for_seller` inutile (la règle « dernier avis par acheteur » s'applique au contexte, tous les avis d'un même acheteur sur ce contexte sont déplacés ensemble) |
| `moderation 0005_audit_legacy_conversion` | une ligne `AuditLog` par correspondance : action `ORG_CONVERTED`, contexte `(ORGANIZATION, organization_id)`, cible l'organisation, `details = 'legacy_business_profile=<uuid>; status=<ACTIVE|SUSPENDED>'` (identifiants seulement), acteur nul (règle 12) ; idempotente (ne recrée pas une ligne existante) |

Post-conditions affirmées **dans** chaque migration (échec = retour arrière de la transaction) : plus aucune ligne `USER` dont l'identifiant figure dans la table de correspondance ; le nombre de lignes déplacées est journalisé (`logging`, pas de donnée personnelle).

Piège d'ordre : `marketplace 0010` n'a pas besoin que `identity 0012` (contraction) soit absent ; mais `identity 0012+` ne doit jamais précéder `identity 0011` (dépendance de chaîne) ; l'ordre entre `identity 0012` et `marketplace 0010` n'est pas imposé par le graphe et n'a pas d'importance (la table de correspondance n'est pas retirée par T9).

### 2.7 Conversations, messages, notifications (décision)

Aucun remplissage (ADR 10.3 confirmé) :
- **Conversations existantes** : restent en accès par participants. Le propriétaire converti y reste participant et les lit comme avant ; l'équipe n'y a pas accès (il n'y a que le propriétaire). Les nouvelles conversations sur une offre convertie suivent le régime « organisation » : si un acheteur avait déjà une conversation ancienne sur la même offre, une seconde conversation naît (doublon d'affichage, sans perte). Un remplissage de `Conversation.seller_context_*` exigerait de relire `marketplace` depuis `messaging` : refusé (frontière). Risque accepté, section 9.
- **Messages** : `sender_context` nul = personnel (norme unique).
- **Notifications** : `context` nul = personnel ; celles du propriétaire convertissent en « personnelles ». Les nouvelles suivent les contextes (T6).

### 2.8 Après la conversion

Lancer une fois `python manage.py sync_seller_visibility` (filet : la migration pose déjà `seller_is_public`, la commande confirme) et `dispatch_outbox --stats` (aucun événement n'est émis par la conversion ; contrôle de routine).

### 2.9 Traçabilité de la conversion (règle 12) sans événement

Pas de `publish_event` : aucun abonné n'a besoin d'être informé (les visibilités sont posées par la migration), et émettre depuis une migration créerait des événements dont les charges ne seraient pas déclarées dans le catalogue à ce moment. La trace est l'`AuditLog` de `moderation 0005`. Le message d'information côté utilisateur est déjà couvert par `migrated_from_business` (front, `LegacyOrgNotice`). Aucune notification n'est envoyée à la conversion.

---

## 3. Migrations (« une par changement logique »), ordre et retour arrière

### 3.1 Phase A : conversion (T9-1). Aucun champ retiré.

| # | Migration | Dépend de | Contenu | Retour arrière |
|---|---|---|---|---|
| A1 | `identity 0011_convert_business_profiles` | `identity 0010` | `RunPython` 2.3 + post-conditions | **`noop` documenté** : les organisations créées restent (inoffensives tant que `BusinessProfile` existe) ; une nouvelle application est idempotente. Aucune suppression automatique de ligne |
| A2 | `marketplace 0010_convert_offer_contexts` | `identity 0011`, `marketplace 0009` | 2.6 | **réel** : replace les offres des organisations à correspondance dans `('USER', <propriétaire>)` (via `Membership` propriétaire de l'organisation `legacy_business_profile_id` non nul), `seller_is_public` recalculé depuis le compte. Vrai tant que `Offer.seller` existe, et seulement s'il n'y a pas eu de publication par d'autres membres entre-temps (hypothèse de développement ; sinon restauration de la copie de base) |
| A3 | `visibility 0006_convert_counter_contexts` | `identity 0011`, `visibility 0005` | 2.6 | réel, même logique |
| A4 | `reviews 0006_convert_review_contexts` | `identity 0011`, `reviews 0005` | 2.6 | réel, même logique |
| A5 | `moderation 0005_audit_legacy_conversion` | `identity 0011`, `moderation 0004` | 2.6 | `noop` (le journal d'audit n'est jamais supprimé) |

Les migrations A2 à A5 sont indépendantes entre elles : l'ordre d'application sera A1 → (A2, A3, A4, A5 dans l'ordre alphabétique des applications) ; aucune dépendance croisée entre ces quatre.

### 3.2 Phase B : contraction (T9-2), **après accord explicite** (section 9, Q1)

Chaque migration de contraction commence par une **garde** (`RunPython` en tête de la même migration, avant toute opération de schéma) qui lève une erreur claire si la conversion n'a pas eu lieu. Les gardes ne lisent que les tables de leur propre domaine plus la table de correspondance.

| # | Migration | Dépend de | Opérations | Garde | Retour arrière (schéma seulement) |
|---|---|---|---|---|---|
| B1 | `identity 0012_kycdocument_organization_required` | `identity 0011` | `KycDocument.organization` NOT NULL ; retrait de `KycDocument.business_profile` | échoue si une pièce a `organization` NULL, ou si un `BusinessProfile` n'a pas de ligne de correspondance | recrée la colonne `business_profile` (nulle) ; `organization` redevient nullable. Les données du lien (quelle pièce appartenait à quel profil) **ne sont pas restituées** |
| B2 | `identity 0013_remove_business_profile` | `identity 0012` | `DeleteModel BusinessProfileCategory`, puis `DeleteModel BusinessProfile` | même garde | recrée des **tables vides** ; la donnée n'est pas restituée |
| B3 | `identity 0014_remove_user_user_type` | `identity 0013` | `RemoveField User.user_type` | aucune | recrée la colonne avec le défaut `PARTICULIER` ; la valeur d'origine n'est pas restituée |
| B4 | `marketplace 0011_remove_offer_seller` | `marketplace 0010`, `identity 0011` | `RemoveIndex offer_seller_deleted` ; `RemoveField Offer.seller` | échoue s'il reste une offre dont le contexte est `USER` avec un identifiant présent dans la table de correspondance (conversion non faite) ou une offre à contexte nul | recrée `seller` (nulle) ; non remplie |
| B5 | `marketplace 0012_offer_seller_context_required` | `marketplace 0011` | `seller_context_type`, `seller_context_id` NOT NULL | échoue si une ligne a un contexte nul | redevient nullable |
| B6 | `visibility 0007_remove_counter_seller` | `visibility 0006`, `identity 0011` | `RemoveIndex visib_counter_seller_date` ; `RemoveField seller` | idem B4 pour les compteurs | recrée la colonne nulle |
| B7 | `visibility 0008_counter_seller_context_required` | `visibility 0007` | NOT NULL | échoue si contexte nul | redevient nullable |

Remarques :
- B1 retire `business_profile` **avant** B2 (sinon la FK bloquerait la suppression de table). B2 doit précéder B3 sans dépendance technique (séparés pour qu'un changement logique = une migration).
- SQLite reconstruit la table à chaque `AlterField`/`RemoveField` : prévoir le temps sur une copie de la base (taille réelle) ; portable MySQL (aucun SQL brut, aucune contrainte conditionnelle).
- Le **code** qui retire les champs (modèles, services, tests, admin, routes) est livré **dans le même commit** que B1 à B7 : l'état du dépôt reste cohérent à chaque commit (`makemigrations --check` vert).
- `Organization.legacy_business_profile_id` et `LegacyAccountMapping` ne sont **pas** retirés en T9 (voir section 9, Q3).

### 3.3 Recommandation sur la réinitialisation des migrations (ADR 0002 : possible par ADR tant que pas de production)

**Ne pas réinitialiser maintenant.** Raisons : (1) la conversion est la preuve que les pièces, avis et compteurs ont suivi (D1) et doit pouvoir se rejouer sur chaque base de développement ; (2) deux développeurs au moins ont une base locale : une réinitialisation les oblige à repartir de zéro et supprime leur jeu d'essai ; (3) les migrations des tâches T1 à T9 sont toutes réversibles ou documentées. **Réinitialiser une seule fois, à la fin du projet, au passage à MySQL** (ADR 0001) : la base de production sera de toute façon recréée, et la chaîne `0001..00NN` avec ses migrations de données se réduira alors à un état initial propre (nouvel ADR 0002bis, retrait de `LegacyAccountMapping`, de `legacy_business_profile_id` et des migrations de conversion). Cela évite aussi d'embarquer la lecture croisée `identity` dans des migrations vouées à disparaître.

---

## 4. Précautions (obligatoires avant la phase A, et avant la phase B)

À exécuter par le chef de projet (et la copie par l'utilisateur pour sa propre base) avant toute délégation de T9-1 puis de T9-2. Aucune suppression sans accord.

1. **Étiquette git locale** : `git tag pre-L0-09-conversion` sur le commit de départ de T9-1 ; seconde étiquette `pre-L0-09-contraction` avant T9-2. Le `git push` d'une étiquette suit la règle habituelle (accord ou autorisation permanente existante).
2. **Copie de la base de développement hors dépôt**, avec horodatage, par exemple `D:\Projects\cp-backups\L0-09\db.sqlite3.avant-conversion-AAAAMMJJ` (jamais dans `backend/`, jamais commitée ; `db.sqlite3` est déjà ignoré). Copier aussi `backend/media/` et **`backend/private_media/kyc/`** (pièces KYC : les fichiers ne sont pas en base). La copie contient des données personnelles : accès limité au poste de développement, suppression à décider avec LEG-PRV, jamais diffusée par un canal de discussion.
3. **Répétition sur la copie** : lancer les migrations contre une **copie jetable** (variable `DB_NAME` pointant sur un chemin absolu ; `BASE_DIR / DB_NAME` accepte un chemin absolu), pas sur la base de travail. Sauvegarder la sortie de `check_legacy_conversion` avant et après (identifiants et comptages uniquement).
4. **Contrôles avant** : `python manage.py test apps` vert ; `makemigrations --check --dry-run` vert ; `dispatch_outbox --stats` sans événement `dead` ni en attente (les abonnés doivent avoir rattrapé).
5. **Contrôles après la conversion (avant d'ouvrir la phase B)** : zéro `USER` mappé dans `Offer`, `DailyVisibilityCounter`, `Review` ; autant d'organisations converties que de profils ; pour chaque profil `ancien is_verified == synthèse complète` (sauf exceptions listées) ; `sync_seller_visibility` ne change rien ; pas de `KycDocument` sans organisation ; la liste publique `organizations/` et un profil `sellers/organization/<id>/` répondent ; `migrate` de retour arrière jusqu'à `identity 0010` puis de nouveau en avant fonctionne sur la copie.
6. **Aucune suppression automatique** : T9-1 ne supprime ni ligne, ni fichier, ni dossier ; le retour arrière des migrations de contexte déplace des lignes, il n'en détruit pas ; la phase B est la seule étape destructive (tables `BusinessProfile*`, colonnes) et exige l'accord de la section 9.
7. **Réglage après contraction** : la restauration de la copie de base (et des dossiers `media/`, `private_media/`) est le **seul** retour arrière complet des données ; les migrations inverses ne recréent que le schéma.

---

## 5. Impacts sur l'API, le front, l'administration et les scripts

### 5.1 Contrat JSON

| Moment | Changement observable |
|---|---|
| T9-1 (conversion) | **Aucun champ ne change.** Les offres, avis et vendeurs convertis exposent déjà `seller.context_type = ORGANIZATION` (contrat 9.6). Visibles : `GET contexts/` affiche l'organisation (`migrated_from_business: true`), `GET organizations/` la liste, `sellers/organization/<id>/` répond. Les offres d'un compte entreprise cessent d'être « personnelles » : l'ancien `?seller=<user_id>` ne les trouve plus, `?seller=<organization_id>` oui (contrat 9.6 déjà en vigueur) |
| T9-2 (contraction) | **Aucun champ de réponse ne change** (`user_type` et `business_profile` ont disparu de l'API depuis T8 ; `seller` des offres est déjà l'objet de contexte). **Routes retirées (404)** : `GET/POST /api/accounts/kyc/documents/` et `DELETE /api/accounts/kyc/documents/<uuid>/`. Inchangées : `kyc/review-queue/`, `kyc/documents/<uuid>/decision/`, `kyc/documents/<uuid>/download/`. Les corps envoyés avec `user_type`/`business_profile` restent sans effet (test conservé) |
| T9-3 (purge par contexte) | Nouvel événement de domaine (sans effet JSON) |

### 5.2 Front

Aucune adaptation fonctionnelle obligatoire (voir 1.4). Tâche courte (F-T9) : nettoyer les tests qui citent des chemins retirés, rejouer `npm run lint && npm run test && npm run build`, confirmer qu'aucune requête n'appelle `kyc/documents/` hors organisation, et vérifier le comportement d'un compte converti (organisation suspendue : état `DENY_SECURITY` déjà géré par F1/F2). Les fixtures sont régénérées uniquement si le contrat change (il ne change pas) : sinon les revérifier contre le backend final.

### 5.3 Administration Django

- `BusinessProfileAdmin` et son inline retirés (B2) ; `KycDocumentAdmin` : colonnes `organization`, `document_type`, `status`, `reviewed_by`, `created_at`, recherche par `organization__name` ; consultation journalisée conservée ; **Organization** : l'action « Réactiver » existe déjà ; elle doit servir aux organisations converties en `SUSPENDED` (2.5).
- `UserAdmin` : retirer `user_type` de `list_display` et `list_filter`.

### 5.4 `setup_roles`

Retirer `identity.businessprofile`. Ajouter (ADR §11.4, jamais appliqué) : administrateur : `identity.organization` (`view`, `suspend_organization`), `identity.organizationdocumentrequirement` (`view`, `add`, `change`, `delete`), `identity.identitysettings` (`view`, `change`) ; modérateur : `identity.organization` (`view`) si la liste des pièces à vérifier l'exige ; `identity.membership` en `view` seulement pour l'administrateur (le personnel ne voit ni téléphone ni e-mail de membre). Une permission inconnue continue de faire échouer la commande (test existant). **À valider par le chef de projet avec l'analyste** : la matrice exacte relève des droits de back-office, pas de la conversion ; le minimum exigé par T9 est `suspend_organization` pour l'administrateur.

### 5.5 `scripts/recette_contrat_http.py`

Retirer l'import de `BusinessProfile` et la création d'un profil en base ; exercer le KYC par `organizations/<id>/kyc/documents/` (création d'organisation par l'API, dépôt, file de vérification, décision, claims) ; garder les vérifications « `user_type` et `business_profile` ignorés » (lignes 241-250, 303-309) ; schéma `me` sans ces deux clés. Non exécuté en CI : le dev-backend l'exécute une fois contre un serveur local et joint la sortie.

---

## 6. Découpage en sous-tâches (une tâche = un agent)

Règle de sérialisation (ADR 10.1) : pendant T9-1 et T9-2, **personne d'autre ne touche** les migrations de `identity`, `marketplace`, `visibility`, `reviews`, `moderation`, `messaging`, `notifications`.

Ordre : **T9-0 → T9-1 → (relecture + audit) → contrôles de la section 4 → ACCORD → T9-2 → T9-3 ‖ F-T9 → T10**.

### T9-0 — Préparer les tests et le code à ne plus dépendre des vestiges (dev-backend, refactor sans changement de comportement)

Objectif : réduire le diff de la contraction. Se fait **avant** la conversion, tests verts à chaque pas.
- Ajouter dans `apps/common/factories.py` un assistant sans import de modèle (ex. `owner_kwargs(user)` → `{'seller_context_type': 'USER', 'seller_context_id': user.pk, 'created_by': user}`) et l'utiliser à la place de `seller=` dans les ~35 fichiers de tests ; remplacer les créations de `BusinessProfile` par la création d'une organisation par les services ou `Organization.objects.create` + `Membership` ; réécrire les tests des routes `kyc/documents/` historiques vers les routes d'organisation (le test ne disparaît pas).
- Retirer de `tests_verification.py` l'usage de `KycDocument.REQUIRED_TYPES` (utiliser `OrganizationDocumentRequirement`).
Critères d'acceptation : `python manage.py test apps` vert avec **au moins 1568 tests** ; `grep -rnE "seller=" backend/apps --include=tests*.py` ne trouve plus que des cas qui testent explicitement un champ interdit (`seller_not_settable`) ; aucun test ne crée `BusinessProfile` hors du test de migration (T9-1) ; aucun changement de code applicatif sauf imports.

### T9-1 — Conversion (dev-backend ; relecteur-code ; **auditeur-securite obligatoire**)

Livrables : migrations A1 à A5 (section 3.1), commande `check_legacy_conversion` (2.2), tests.
Tests exigés (`MigrationExecutor`, état historique avant `identity 0011`, jeu fabriqué) :
- profil complet (bio, logo, NIF, catégories, ville) converti champ par champ (2.3) ; `created_at` et `joined_at` conservés ; une seule `Membership` `OWNER` `ACTIVE` ;
- pièces : `organization` et `uploaded_by` posés, statut, motif, décideur, fichier inchangés ; **équivalence** `ancien is_verified == résumé complet` pour trois profils (complet, deux pièces, une pièce refusée) ; `migrated_from_business` vrai (via `contexts/`) ;
- offres, compteurs et avis déplacés ; `created_by` inchangé ; offres d'un compte **sans** profil inchangées (reste `USER`) ; compte `PARTICULIER` inchangé ;
- profil sans offre ; propriétaire inactif → `SUSPENDED`, `seller_is_public=false` ; nom vide, trop long, avec caractères de contrôle, doublons de noms (deux organisations, pas d'erreur) ; plus de 5 catégories conservées ;
- **idempotence** : double exécution (migrer en avant, revenir à `0010`, ré-avancer ; et exécution de la fonction deux fois) sans doublon d'organisation, de membre ni de correspondance ;
- retour arrière A2 à A4 : offres, compteurs, avis retrouvent le contexte `USER` ; aucune ligne n'est supprimée ;
- `AuditLog` `ORG_CONVERTED` : une ligne par correspondance, sans nom ni e-mail ni NIF (valeurs sentinelles) ;
- base vierge : toutes les migrations passent, la conversion est un no-op ;
- non-fuite : le téléphone et le consentement du propriétaire ne sont pas copiés ; `allowed_channels` d'une offre convertie vaut `['MESSAGE']` ; l'API publique `organizations/` et `sellers/organization/<id>/` n'exposent ni NIF, ni `created_by`, ni compte ; un ancien propriétaire révoqué ne décide pas de la vérification (conflit d'intérêts) ;
- `check_legacy_conversion` : sortie sans donnée personnelle (valeurs sentinelles), lecture seule (aucune ligne modifiée).
Critères généraux : suites `identity`, `marketplace`, `visibility`, `reviews`, `moderation`, `platform_core`, `common.DomainBoundariesTests` vertes ; `makemigrations --check --dry-run` vert ; migrations sur base SQLite vierge et sur une **copie** de la base de développement ; `grep -rn "business_profile" backend/apps` ne change pas encore (la contraction est T9-2).
Hors périmètre : tout retrait de champ ou de modèle ; événements ; remplissage de `messaging`/`notifications`.

### T9-2 — Contraction et retrait du code (dev-backend ; relecteur-code ; auditeur-securite pour les gardes, routes retirées, `setup_roles`)

Livrables : migrations B1 à B7 avec gardes (3.2) ; retrait du code, des routes, de l'admin, des tests devenus sans objet (inventaire 1.1) ; `setup_roles` (5.4) ; `recette_contrat_http.py` (5.5) ; README.
Tests exigés : chaque garde échoue sur une base non convertie (jeu fabriqué : profil sans correspondance, offre `USER` mappée, pièce sans organisation) et passe sur une base convertie ; retour arrière schéma de B7 à B1 sur une copie ; routes `kyc/documents/` (liste, dépôt, suppression) répondent 404 et les routes de décision et de téléchargement fonctionnent pour une pièce d'organisation ; `register/`, `me/` ignorent toujours `user_type`/`business_profile` ; `setup_roles` s'exécute sur une base vierge ; création d'offre sans passerelle (le contexte est obligatoire) ; `Offer.objects.create` sans contexte lève une erreur d'intégrité ; suppression d'un compte par l'admin ne laisse pas de tables orphelines liées à `BusinessProfile`.
Critères généraux : **`grep -rnE "user_type|BusinessProfile|business_profile" backend/apps backend/scripts` ne renvoie plus rien hors migrations historiques, et hors les gardes de non-régression listées (tests qui vérifient l'ignorance du champ)** ; `grep -rn "TODO(T9)" backend` vide ; 0 test en moins ; `python manage.py test apps` et `makemigrations --check --dry-run` verts ; migrations sur base vierge et sur copie convertie.

### T9-3 — Purge par contexte à la suppression d'un compte (dev-backend ; relecteur-code ; auditeur-securite)

Contexte : la cascade `Offer.seller` / `DailyVisibilityCounter.seller` disparaît en T9-2 ; la suppression d'un `User` par l'admin laisserait des offres, compteurs et avis rattachés à un identifiant inexistant (donnée personnelle conservée sans finalité, règle 10). Il n'y a pas de suppression de compte exposée en V1 : cette tâche couvre la suppression par l'admin et prépare L1.
Conception : nouvel événement `identity.seller_context_removed` (v1, charge `context_type`, `context_id`, `reason` = `account_deleted` | `provider_deleted`, aucune donnée personnelle) émis par `identity.services` (appelé par `UserAdmin.delete_model/delete_queryset` à côté de `announce_account_status`, et par la suppression d'un `ProviderProfile`) ; abonnés : `marketplace` (supprime les offres du contexte et leurs photos, via ORM pour que les signaux de fichiers jouent), `visibility` (supprime les compteurs du contexte), `reviews` (supprime les avis **reçus** du contexte ; les avis rédigés par le compte disparaissent déjà par la FK `Review.user`). Le contexte `ORGANIZATION` n'est **jamais** purgé par cet événement (une organisation n'est pas supprimée, seulement archivée ; ses offres restent, `created_by` passe à nul). Abonnés idempotents, `deliver_now` non requis (l'identifiant disparu n'a plus d'état à relire). Déclarer l'événement et ses abonnés dans `platform_core/catalog.py` (contrôle `E001`).
Critères : suppression d'un compte avec offres, photos, compteurs et avis reçus → plus aucune ligne de contexte `USER` de ce compte après livraison de l'outbox ; les offres d'une organisation dont il était membre restent ; double livraison sans erreur ; aucun nom ni e-mail dans la charge utile ni dans `AuditLog` ; test de non-régression `last_owner_account` (la suppression du seul propriétaire reste refusée).
Dépendance : T9-2 (suppression des cascades). Parallélisable avec F-T9.

### F-T9 — Front : nettoyage et vérification (dev-frontend)

Après T9-2. Livrables : tests `cache-rules.test.ts` et `validation.test.ts` réécrits avec des chemins et champs réels ; vérification par recherche qu'aucun appel ne vise `kyc/documents/` hors `organizations/…` ; contrôle des fixtures contre le backend final (aucun écart attendu) ; test d'une organisation `migrated_from_business: true` suspendue (message `DENY_SECURITY` du sélecteur de contexte). Critères : `npm run lint && npm run test && npm run build` verts ; aucun nouveau texte en dur (i18n). Hors périmètre : renommer l'URL `/businesses`, retirer `migrated_from_business`.

### T10 — Recette (qa-testeur)

Ajouter à la recette de L0-09 : conversion sur une copie de la base de développement (comptes avec offres, avis, pièces validées/refusées, compte désactivé), vérification de l'affichage de l'organisation convertie (nom, claims, note), `allowed_channels`, message d'information, réactivation d'une organisation suspendue par le personnel, retour arrière sur copie.

---

## 7. Sécurité (audit obligatoire : T9-1, T9-2, T9-3)

Points à fournir à `auditeur-securite` :
1. **Création de privilèges par migration** : seule la ligne `OWNER` du titulaire du profil est créée ; aucun autre compte n'obtient de rôle ; pas de membre « fantôme ». Un test fabrique un compte `is_staff` et vérifie qu'il n'obtient rien.
2. **Pas de fuite par la conversion** (règle 10) : le NIF reste non public ; le téléphone et le consentement du propriétaire ne deviennent pas ceux de l'organisation ; la liste publique et le profil vendeur gardent leurs clés exactes ; la sortie du pré-vol et les journaux de migration ne contiennent que des identifiants et des comptages.
3. **Visibilité d'un vendeur sanctionné** : propriétaire désactivé → organisation `SUSPENDED` ; couverture de test et procédure de réactivation par le personnel (permission dédiée, journalisée `ORG_REACTIVATED`).
4. **Vérification (règle 3)** : aucune organisation ne devient « vérifiée » par la conversion ; un `is_verified` posé à la main n'est pas reproduit ; la synthèse reste dérivée des pièces `VALIDE` exigées.
5. **Conflit d'intérêts** : le propriétaire converti ne peut ni décider, ni télécharger ses propres pièces (il a un `Membership`) ; vérifier le cas d'un compte du personnel propriétaire d'un ancien profil.
6. **Pièces KYC** : fichiers jamais déplacés ni exposés ; `download` réservé à `review_kycdocument` ; copie de sauvegarde du dossier privé hors dépôt et hors `MEDIA_ROOT` (données de pièces d'identité).
7. **Routes retirées** : 404 net, pas de redirection vers un autre périmètre ; aucune autre route n'utilise `request.user.business_profile` (recherche).
8. **Gardes de contraction** : impossible d'atteindre B1 à B7 sans conversion ; message d'erreur sans donnée personnelle.
9. **Purge par contexte** : elle ne supprime jamais les données d'une organisation, ne s'exécute que sur `USER` et `PROVIDER` d'un compte effectivement supprimé, est idempotente.
10. **Journalisation (règle 12)** : `ORG_CONVERTED` pour chaque conversion ; actions admin de réactivation journalisées.

---

## 8. Risques

| # | Risque | Parade |
|---|---|---|
| R1 | Contraction sur une base non convertie (perte de données) | gardes B1 à B7, ordre des étapes, copie de base, accord explicite |
| R2 | Republication des offres d'un propriétaire banni | organisation `SUSPENDED` à la conversion (2.5) |
| R3 | Suspension durable après levée d'une sanction (l'organisation n'est pas réactivée automatiquement) | action admin « Réactiver », permission dans `setup_roles`, listée au pré-vol ; limite assumée |
| R4 | Conversations anciennes en accès par participants, doublon à la reprise de contact | accepté (ADR 10.3), sans perte |
| R5 | Perte du canal « appel / WhatsApp » des anciennes entreprises (consentement non transféré) | voulu (ADR 10.3, Q-CLI5) ; message d'information déjà présent côté front |
| R6 | Type d'organisation fixé à `ENTREPRISE` pour toutes (ONG, boutiques) : pièces exigées inadaptées | correction par le personnel (le type est immuable par l'API) ; comptés au pré-vol |
| R7 | Logos orphelins dans `business_logos/` après remplacement | purge non faite (pas de suppression sans accord) ; liste à produire plus tard |
| R8 | Volume de réécriture des tests (~450 lignes, 35 fichiers) | T9-0 séparé, mécanique, avant la contraction |
| R9 | Temps de reconstruction de table sous SQLite sur une grosse base | répétition sur copie ; prévoir fenêtre |
| R10 | Migration lisant `identity` depuis d'autres domaines (exception A11) | lecture seule de deux UUID ; à effacer par la réinitialisation de fin de projet (3.3) |
| R11 | Données personnelles dans les copies de sauvegarde | hors dépôt, accès limité, suppression à décider (LEG-PRV) |
| R12 | Un événement outbox en attente référence encore `seller_id` (v1) | les abonnés tolèrent la v1 (ADR 19.6.5) ; contrôle `dispatch_outbox --stats` avant la phase A |

---

## 9. Points exigeant l'accord de l'utilisateur

- **Q1 (obligatoire avant T9-2) : accord pour la phase destructive** : suppression des tables `BusinessProfile` et `BusinessProfileCategory`, retrait de `User.user_type`, `KycDocument.business_profile`, `Offer.seller`, `DailyVisibilityCounter.seller` (migrations B1 à B7, non restituables sans la copie de base). Condition : contrôles de la section 4.5 verts, copie de base et dossiers de médias sauvegardés.
- **Q2 : réinitialisation des migrations** : recommandation, ne pas réinitialiser maintenant, le faire une fois au passage à MySQL (section 3.3). Un « oui » pour réinitialiser dès maintenant exigerait un ADR d'amendement de l'ADR 0002 et l'abandon des bases de développement existantes.
- **Q3 : conservation de `LegacyAccountMapping` et `Organization.legacy_business_profile_id`** après T9 (recommandé : oui, jusqu'à ce que toutes les bases de développement soient converties et que le message d'information ait servi ; retrait par la réinitialisation de fin de projet ou une tâche de nettoyage L0-09k).
- **Q4 : organisations des propriétaires désactivés** : `SUSPENDED` à la conversion (recommandé, sécurité) plutôt que `ACTIVE`. Un « ACTIVE » republierait des offres de comptes bannis.
- **Q5 : fichiers orphelins** (`business_logos/`) et copies de sauvegarde : aucune purge sans accord ; durée de conservation des sauvegardes à fixer.
- **Q6 : type d'organisation des anciens profils** : tous `ENTREPRISE` par défaut (le profil n'avait pas de type) ; si le client veut une règle (par exemple tous `BOUTIQUE` pour les vendeurs de la marketplace), changer la constante en T9-1 avant exécution ; sinon correction manuelle par le personnel.
- **Q7 : suppression de l'URL `/businesses`** (cosmétique) et de `KYC_MAX_DOCUMENTS_PER_PROFILE` (renommage) : hors T9, à planifier.
- **Q8 : étiquette et sauvegarde** : le chef de projet crée l'étiquette `pre-L0-09-conversion` et fait faire la copie de la base ; l'utilisateur fait la copie de **sa** base de développement avant d'appliquer les migrations.

Aucune règle verrouillée n'est contredite : la conversion ne donne aucune vérification (règle 3), ne crée aucun score (règle 4), n'expose aucune donnée privée (règle 10), journalise (règle 12) et ne configure rien en dur hors le type `ENTREPRISE` par défaut, à valider (Q6, règle 11).

---

## 10. Livraison de T9-2 (09/11/2026) : écarts avec le plan

- Numérotation conforme (B1 à B7 : `identity 0012` à `0014`, `marketplace 0011` et `0012`, `visibility 0007` et `0008`). Les gardes comptent les lignes à contexte nul avec une seule requête (`Q`), et celle de `identity 0013` refait le contrôle de `0012`.
- `check_legacy_conversion` : **retirée** plutôt que réécrite (les modèles qu'elle lit n'existent plus). Ses 6 tests sont remplacés par les tests de gardes et de retour arrière de `identity/tests_contraction.py` (14 tests).
- Tests migrés : `tests_admin` (admin d'organisation en lecture seule à la place de celui du profil, matrice de `setup_roles`), `tests_organizations` (disparition du modèle, conservation des traces de conversion), `tests_l021`, `tests_recette_lot0`, `tests_organizations_api` (champs hérités ignorés, vérifiés sur le nouveau modèle), `tests_verification` et `tests_verification_hardening` (une pièce sans organisation est refusée par la base), `marketplace/tests_contexts` (une offre ne porte que son contexte et son auteur).
- `KYC_MAX_DOCUMENTS_PER_PROFILE` conservé (Q7). `Offer.save()` n'a plus de passerelle : une offre sans contexte lève `IntegrityError`.
