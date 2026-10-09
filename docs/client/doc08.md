**MANUEL PAIEMENTS, COMMANDES, REMBOURSEMENTS & LITIGES**

**Plateforme Écosystème RDC**

*Document 08 - Règles opérationnelles et états commerce V1*

Version de référence V1 / Post-V1 - Septembre 2026

# 1. Objet et invariant financier

Ce manuel définit le comportement de référence des commandes, paiements, stocks, fulfillment, livraisons, billets, remboursements, réconciliations et litiges. Il s'applique aux flux Marketplace, restaurants/food ordering, event ticketing et Platform Billing lorsque les mêmes principes sont pertinents.

Invariant central: toute modification d'un état monétaire doit être traçable à une confirmation autoritative du fournisseur de paiement, une confirmation autorisée de réception cash, une confirmation de remboursement du fournisseur ou une action administrative autorisée et auditée.

# 2. Séparation obligatoire des états

| **Objet**         | **Ce qu'il représente**                             | **Ne doit jamais être confondu avec**   |
|-------------------|-----------------------------------------------------|-----------------------------------------|
| Commercial Object | Commande Marketplace, Food Order, Ticket Order      | Paiement ou livraison                   |
| Payment           | Tentative/transaction financière                    | Commande elle-même                      |
| Fulfillment       | Préparation/retrait/remise de l'article             | Paiement                                |
| Delivery Request  | Mission du partenaire livraison                     | Food/Marketplace Order                  |
| Ticket            | Droit d'accès unique après commande/paiement valide | Ticket Order                            |
| Refund            | Retour de fonds lié à un paiement original          | Annulation simple                       |
| Case / Dispute    | Problème, contestation ou investigation             | État commercial                         |
| Platform Billing  | Abonnements, passes, promotion                      | Paiement d'un vendeur/service ordinaire |

Une transition dans un objet peut déclencher une transition dans un autre, mais elle ne l'écrase jamais. Exemple: une commande annulée ne signifie pas automatiquement que le paiement est remboursé; un Refund Record doit exister.

# 3. Identifiants et idempotency

| **Élément**             | **Règle**                                                                    |
|-------------------------|------------------------------------------------------------------------------|
| order_id                | Identifiant unique de commande; stable.                                      |
| payment_id              | Une tentative/transaction financière distincte.                              |
| provider_transaction_id | Référence externe unique si fournie.                                         |
| idempotency_key         | Obligatoire pour créations/actions financières susceptibles d'être rejouées. |
| refund_id               | Identifiant distinct lié au payment_id original.                             |
| delivery_request_id     | Distinct de order_id.                                                        |
| ticket_id / token       | Unique, non prédictible, scannable une seule fois selon règle.               |
| case_id                 | Relie litige, parties, objets et preuves.                                    |
| event_id / webhook_id   | Dédupliqué avant traitement.                                                 |

# 4. Machine d'état Payment

| **État**               | **Signification**                                  | **Transitions principales**                                               |
|------------------------|----------------------------------------------------|---------------------------------------------------------------------------|
| Initiated              | Tentative créée localement                         | Pending, Cancelled, Failed                                                |
| Pending                | Provider n'a pas encore confirmé résultat final    | Successful, Failed, Expired, Cancelled, ReconciliationRequired            |
| Successful             | Provider confirme paiement réussi                  | Refund Requested/partiel via objet Refund; pas de retour direct à Pending |
| Failed                 | Provider confirme échec                            | Nouvelle tentative = nouveau Payment                                      |
| Expired                | Fenêtre de paiement expirée                        | Nouvelle tentative possible                                               |
| Cancelled              | Tentative annulée avant succès                     | Nouvelle tentative possible                                               |
| ReconciliationRequired | État local/provider incohérent ou inconnu          | Résolution via provider/reconciliation                                    |
| Unknown                | Utilisé seulement si statut ne peut être déterminé | ReconciliationRequired                                                    |

Le retour de l'application cliente n'est jamais une preuve suffisante de succès. La confirmation autoritative vient du provider selon l'intégration approuvée.

# 5. Mobile Money / fournisseur de paiement

| **Étape**             | **Comportement attendu**                                                           |
|-----------------------|------------------------------------------------------------------------------------|
| 1\. Création          | Créer Payment Initiated avec idempotency key et montant attendu.                   |
| 2\. Provider call     | Envoyer demande; enregistrer référence provider sans données sensibles inutiles.   |
| 3\. Pending           | Afficher « paiement en cours de confirmation »; ne pas marquer Paid.               |
| 4\. Callback/webhook  | Vérifier authenticité/signature/source selon provider; dédupliquer event.          |
| 5\. Successful        | Comparer montant/devise/référence; marquer Successful une seule fois.              |
| 6\. Failed/Expired    | Libérer réservations selon règles; permettre nouvelle tentative.                   |
| 7\. Timeout           | Ne pas supposer échec; passer par vérification/reconciliation.                     |
| 8\. Duplicate webhook | Répondre idempotemment sans doubler paiement, stock, ticket ou notification.       |
| 9\. Reconciliation    | Interroger/rapprocher provider; toute correction est auditée.                      |
| 10\. Notification     | Envoyer message utilisateur seulement sur transition significative et dédupliquée. |

# 6. Paiement cash

| **Règle**        | **Application**                                                                   |
|------------------|-----------------------------------------------------------------------------------|
| Statut initial   | Cash = Unpaid jusqu'à réception confirmée.                                        |
| Collecteur       | Seller, restaurant, delivery company ou arrangement autorisé doit être explicite. |
| Confirmation     | Seul acteur autorisé confirme cash received.                                      |
| Montants séparés | Montant food/item et montant delivery restent distincts.                          |
| Désaccord        | Créer Case « cash disagreement »; ne pas modifier silencieusement l'historique.   |
| Annulation       | Si cash non reçu, pas de refund financier; traiter fulfillment/case.              |
| Audit            | Conserver qui a confirmé, quand, montant et contexte.                             |
| Pas de faux Paid | Une livraison « Delivered » ne marque jamais automatiquement le cash Paid.        |

# 7. Marketplace Order - machine d'état

| **État**            | **Description**                            | **Effet stock / paiement**                               |
|---------------------|--------------------------------------------|----------------------------------------------------------|
| Draft/Checkout      | Panier/checkout non finalisé               | Pas de vente; réservation éventuelle courte selon design |
| Placed              | Commande créée                             | Réservation stock active si applicable                   |
| Payment Pending     | Attente provider                           | Stock réservé selon TTL                                  |
| Confirmed           | Paiement réussi ou cash accepté comme mode | Préparation/fulfillment peut commencer                   |
| Preparing           | Vendeur prépare                            | Stock réservé/décrément selon politique                  |
| Ready               | Prêt retrait/remise/livraison              | Fulfillment actif                                        |
| Fulfilled/Completed | Remis/retiré/livré et finalisé             | Interaction éligible avis                                |
| Cancelled           | Commande annulée                           | Libérer stock non consommé; traiter paiement séparément  |
| Failed              | Commande ne peut être exécutée             | Case/refund selon paiement                               |
| Return Requested    | Retour demandé si policy applicable        | Case/return workflow                                     |
| Returned            | Retour accepté/achevé                      | Refund séparé si dû                                      |

# 8. Stock et articles uniques

| **Cas**                      | **Règle**                                                                                     |
|------------------------------|-----------------------------------------------------------------------------------------------|
| Produit avec quantité        | Réserver quantité à commande/paiement pending selon politique; décrémenter à étape autorisée. |
| Paiement échoué/expiré       | Libérer réservation de façon idempotente.                                                     |
| Annulation avant fulfillment | Libérer stock non engagé.                                                                     |
| Article unique               | Available → Reserved → Sold; retour/annulation peut restaurer selon inspection/policy.        |
| Deux acheteurs               | Transaction/locking empêche quantité négative ou double vente.                                |
| Stock modifié vendeur        | Ne doit pas invalider silencieusement une commande déjà confirmée.                            |
| Oversell détecté             | Case + résolution client; refund si paiement réussi et non-fulfillment.                       |

# 9. Annulations Marketplace

| **Qui**        | **Moment**                                          | **Conséquence**                                                                      |
|----------------|-----------------------------------------------------|--------------------------------------------------------------------------------------|
| Acheteur       | Avant seuil de préparation/fulfillment configurable | Cancel; libération stock; refund si paiement déjà Successful                         |
| Vendeur        | Avant fulfillment                                   | Reason obligatoire; refund si payé; impact opérationnel/suspicious flag si répétitif |
| Système        | Payment expired / policy condition                  | Cancel/expire idempotent; libération stock                                           |
| Staff autorisé | Exception documentée                                | Action auditée; jamais suppression de l'historique                                   |

Toute annulation conserve cancelled_by, reason_code, timestamp, état précédent et conséquence financière.

# 10. Food Order - machine d'état

| **État**  | **Responsable principal**           | **Notes**                                      |
|-----------|-------------------------------------|------------------------------------------------|
| Received  | Système/restaurant                  | Commande reçue                                 |
| Accepted  | Restaurant                          | Engagement à préparer                          |
| Preparing | Restaurant                          | Préparation commencée                          |
| Ready     | Restaurant                          | Prêt pickup/driver                             |
| Picked Up | Client/driver selon fulfillment     | Séparé du Delivery Request                     |
| Delivered | Fulfillment                         | Livraison effectuée                            |
| Collected | Restaurant/client                   | Retrait effectué                               |
| Completed | Système/règle                       | Clôture normale                                |
| Declined  | Restaurant                          | Avant acceptation; payment consequence séparée |
| Cancelled | Client/restaurant/staff selon règle | Reason + payment consequence                   |
| Failed    | Exception opérationnelle            | Case/refund possible                           |

# 11. Annulation restaurant et préparation

| **Moment**                         | **Politique V1**                                                                                         |
|------------------------------------|----------------------------------------------------------------------------------------------------------|
| Avant Acceptation                  | Annulation généralement possible; refund si paiement déjà capturé selon provider/policy.                 |
| Après Acceptation, avant Preparing | Règle configurable; restaurant peut déjà engager des coûts.                                              |
| Après Preparing                    | Annulation/remboursement dépend de raison, responsabilité et droit applicable.                           |
| Restaurant decline                 | Client ne doit pas supporter un paiement final pour une commande non exécutée; lancer résolution/refund. |
| Rupture ingrédient/article         | Proposer résolution autorisée ou annuler; pas de substitution silencieuse.                               |
| No-show pickup                     | Politique configurable et clairement affichée.                                                           |
| Incident sécurité/alimentaire      | Case Safety/Support séparé du simple refund.                                                             |

# 12. Delivery Request - état séparé

| **État**         | **Description**                            |
|------------------|--------------------------------------------|
| Requested        | Mission créée pour partenaire livraison    |
| Offered/Assigned | Partenaire/équipe ciblé selon architecture |
| Accepted         | Partenaire accepte                         |
| HeadingToPickup  | En route vers point de retrait             |
| AtPickup         | Arrivé pickup si utilisé                   |
| PickedUp         | Colis/commande pris en charge              |
| InDelivery       | Acheminement                               |
| Delivered        | Remise confirmée                           |
| Declined         | Partenaire refuse                          |
| Cancelled        | Mission annulée                            |
| Failed           | Échec livraison                            |
| ReturnRequired   | Retour nécessaire                          |
| Returned         | Retour achevé                              |

# 13. Règles livraison partenaire

| **Règle**         | **Application**                                                                     |
|-------------------|-------------------------------------------------------------------------------------|
| Objet séparé      | Delivery Request référence Food/Marketplace Order sans fusionner les états.         |
| Données minimales | Le partenaire reçoit pickup/dropoff/contact uniquement quand nécessaire.            |
| Prix séparé       | Delivery amount distinct du food/item amount.                                       |
| Cash              | Responsabilité de collecte explicitement attribuée.                                 |
| Échec pickup      | Order peut rester valide pendant résolution; ne pas marquer Failed automatiquement. |
| Échec delivery    | Créer exception/case; définir return/refund selon responsabilité.                   |
| Proof of delivery | Méthode configurable: confirmation, code, signature/photo si légal et proportionné. |
| GPS               | Driver-level live GPS/routing avancé n'est pas requis en V1.                        |
| Réseau            | V1 orchestre des sociétés de livraison existantes; pas de flotte propriétaire.      |

# 14. Event Ticketing - flux financier

| **Étape**          | **État attendu**                                                     |
|--------------------|----------------------------------------------------------------------|
| Ticket Order créé  | Quantité/catégorie de billet réservée selon capacité/TTL.            |
| Payment Pending    | Aucun ticket valide tant que paiement non confirmé.                  |
| Payment Successful | Créer/activer Ticket(s) uniques.                                     |
| Ticket Valid       | QR/token utilisable selon événement.                                 |
| Check-in           | Valid → CheckedIn; duplicate scan détecté.                           |
| Ticket Cancelled   | Invalidé; ne peut plus check-in.                                     |
| Refund             | Refund Record distinct; ticket invalidé selon politique.             |
| Event Cancelled    | Déclencher workflow de notification et refund pour tickets affectés. |
| Event Postponed    | Préserver ticket ou offrir options configurables selon policy.       |

# 15. QR / contrôle d'accès

| **Contrôle**        | **Règle**                                                                                                        |
|---------------------|------------------------------------------------------------------------------------------------------------------|
| Token               | Unique, non prédictible et lié à ticket/event.                                                                   |
| Premier scan valide | Enregistrer event, scanner, timestamp; marquer CheckedIn.                                                        |
| Double scan         | Refuser ou alerter; afficher premier check-in au staff autorisé.                                                 |
| Offline             | Si mode offline prévu, stratégie de synchronisation et conflits doit éviter doubles entrées autant que possible. |
| Annulé/refunded     | Scan invalide.                                                                                                   |
| Staff scope         | Scanner uniquement événements assignés/autorisés.                                                                |
| Journal             | Conserver historique de scans et corrections autorisées.                                                         |

# 16. Refund - objet immuable distinct

| **État Refund** | **Signification**                               |
|-----------------|-------------------------------------------------|
| Requested       | Demande créée                                   |
| UnderReview     | Vérification/approbation si nécessaire          |
| Approved        | Montant/motif autorisés                         |
| Submitted       | Demande envoyée au provider                     |
| Processing      | Provider traite                                 |
| Refunded        | Provider confirme succès                        |
| Failed          | Provider confirme échec                         |
| Cancelled       | Demande retirée avant soumission lorsque permis |
| Rejected        | Demande non approuvée avec reason code          |

# 17. Règles remboursement

| **Règle**          | **Application**                                                       |
|--------------------|-----------------------------------------------------------------------|
| Lien obligatoire   | Chaque refund référence Payment original et objet commercial.         |
| Montant            | Full ou partial seulement si provider/policy le permet.               |
| Pas de faux succès | Approved ≠ Refunded; confirmation provider requise.                   |
| Idempotency        | Même refund ne peut être soumis deux fois par retry.                  |
| Limite cumulée     | Somme refunds confirmés ne dépasse pas montant remboursable original. |
| Devise             | Conserver devise transaction originale sauf règle provider explicite. |
| Motif              | Reason code + notes structurées.                                      |
| Autorisation       | Seuils staff/four-eye configurables.                                  |
| Notification       | Informer parties sur transitions significatives.                      |
| Échec              | Rester traçable; permettre retry contrôlé ou traitement manuel.       |

# 18. Retours Marketplace V1

| **Motif signalable**             | **Traitement**                                                                       |
|----------------------------------|--------------------------------------------------------------------------------------|
| Article matériellement différent | Case + preuves proportionnées; résolution/refund selon policy                        |
| Mauvais article                  | Case; retour/remplacement/refund selon vendeur/policy                                |
| Article endommagé                | Case; déterminer transport/vendeur et résolution                                     |
| Non reçu                         | Vérifier fulfillment/delivery; case                                                  |
| Contrefaçon alléguée             | Case Trust/Moderation + commerce; restriction possible                               |
| Article interdit                 | Moderation/Safety + résolution transaction                                           |
| Changement d'avis                | Selon politique vendeur/droit applicable; pas automatiquement garanti par plateforme |

Les délais de retour et obligations exactes restent configurables et doivent être validés juridiquement en RDC.

# 19. Catalogue des litiges commerce

| **Code**          | **Catégorie**                      |
|-------------------|------------------------------------|
| CASE-PAY-UNCONF   | Chargé mais paiement non confirmé  |
| CASE-PAY-DUP      | Paiement dupliqué                  |
| CASE-PAY-UNAUTH   | Transaction non autorisée alléguée |
| CASE-MKT-NOTREC   | Article non reçu                   |
| CASE-MKT-WRONG    | Mauvais article                    |
| CASE-MKT-DAMAGE   | Article endommagé                  |
| CASE-MKT-NONFUL   | Vendeur n'exécute pas              |
| CASE-MKT-PROHIB   | Contrefaçon/article interdit       |
| CASE-DLV-FAIL     | Échec livraison                    |
| CASE-CASH-DISPUTE | Désaccord cash                     |
| CASE-FOOD-ISSUE   | Problème restaurant/commande       |
| CASE-TKT-PAY      | Billet/paiement                    |
| CASE-EVT-CANCEL   | Annulation événement/refund        |
| CASE-REFUND-FAIL  | Refund provider échoué             |

# 20. Cycle d'un litige

| **Étape**           | **Règle**                                                           |
|---------------------|---------------------------------------------------------------------|
| Open                | Case créé avec catégorie, objets liés, parties, priorité.           |
| Evidence Collection | Collecter seulement preuves nécessaires; protéger données privées.  |
| Temporary Action    | Restriction proportionnée si risque.                                |
| Review              | Support/commerce/finance/trust selon catégorie.                     |
| Resolution Proposed | Refund, replacement, retry delivery, no action, seller action, etc. |
| Financial Action    | Toujours via Payment/Refund records, jamais simple édition du Case. |
| Closed              | Résultat, reason, actor, timestamps et communications conservés.    |
| Appeal/Reopen       | Selon policy et nouvelles preuves; historique intact.               |

# 21. Réconciliation

| **Situation**                            | **Procédure**                                                                      |
|------------------------------------------|------------------------------------------------------------------------------------|
| Local Pending, provider Successful       | Vérifier montant/référence; appliquer succès idempotent.                           |
| Local Successful, provider Failed/absent | Bloquer correction automatique risquée; finance review.                            |
| Webhook manquant                         | Provider query/batch reconciliation.                                               |
| Montant différent                        | ReconciliationRequired + case; pas d'auto-confirmation.                            |
| Doublon provider                         | Identifier paiements distincts vs duplicate event; refund si double charge réelle. |
| Cash disagreement                        | Preuves/actors; ne pas modifier rétroactivement sans audit.                        |
| Refund pending trop long                 | Provider query; notifier utilisateur; escalation si nécessaire.                    |
| Daily close                              | Rapport provider vs ledger interne; exceptions en queue.                           |

# 22. Ledger / journal financier V1

| **Entrée**            | **Contenu minimal**                                                                        |
|-----------------------|--------------------------------------------------------------------------------------------|
| Payment event         | payment_id, order_id, provider ref, montant, devise, ancien/nouvel état, source, timestamp |
| Cash confirmation     | order, collector, montant, confirmation actor/time                                         |
| Refund event          | refund_id, payment_id, montant, status, provider ref                                       |
| Admin adjustment      | actor, permission, before/after, reason, case_id                                           |
| Reconciliation action | source evidence, actor/system, result                                                      |
| Platform Billing      | subscription/pass/promotion transaction séparée                                            |

Le journal doit être append-only ou protégé contre la modification ordinaire. Une correction crée une nouvelle entrée plutôt que d'effacer l'historique.

# 23. Reçu de paiement vs facture commerciale/fiscale

| **Document**                         | **Rôle**                                                                              |
|--------------------------------------|---------------------------------------------------------------------------------------|
| Payment receipt / transaction record | Confirme la transaction technique: montant, date, référence, méthode/statut.          |
| Order confirmation                   | Confirme l'objet commercial commandé.                                                 |
| Seller invoice / tax invoice         | Document commercial/fiscal émis selon obligations du vendeur/organisateur/plateforme. |
| Platform subscription invoice        | Document lié aux plans/passes/promotion selon obligations.                            |
| Refund confirmation                  | Confirme le retour de fonds, distinct de l'annulation.                                |

La plateforme ne doit pas présenter automatiquement un simple reçu technique comme une facture fiscale. Les exigences exactes doivent être validées en RDC.

# 24. Notifications transactionnelles

| **Événement**                         | **Notification**                       |
|---------------------------------------|----------------------------------------|
| Order placed                          | Confirmation commande                  |
| Payment pending                       | Paiement en cours; éviter langage Paid |
| Payment successful                    | Paiement confirmé                      |
| Payment failed/expired                | Échec/expiration + action suivante     |
| Order accepted/preparing/ready        | Transitions utiles                     |
| Delivery assigned/picked up/delivered | Transitions utiles                     |
| Refund submitted/refunded/failed      | État réel                              |
| Event cancelled/postponed             | Impact billet/refund et options        |
| Case update                           | Demande d'information/résolution       |
| Cash received                         | Confirmation de réception              |

Les notifications doivent être dédupliquées. Un retry webhook ne doit jamais produire plusieurs messages identiques.

# 25. Safeguards et anti-abus

| **Contrôle**               | **Objectif**                                                   |
|----------------------------|----------------------------------------------------------------|
| Provider verification      | Ne jamais accepter un statut financier du client comme vérité. |
| Idempotency                | Éviter doubles charges, commandes, refunds, tickets.           |
| Rate limits                | Limiter spam de checkout/payment/refund.                       |
| Seller/payment eligibility | Bloquer acteurs/catégories non éligibles.                      |
| Suspicious flags           | Détecter patterns anormaux sans verdict autonome irréversible. |
| Immutable audit            | Traçabilité financière.                                        |
| Restricted admin           | Séparer support, finance et approbation.                       |
| Four-eye                   | Refunds/overrides importants selon seuil.                      |
| Manual review              | Cas ambigus ou à fort impact.                                  |
| Data minimization          | Ne pas exposer détails paiement inutiles.                      |

# 26. Défaillances techniques et reprise

| **Défaillance**                           | **Comportement attendu**                                           |
|-------------------------------------------|--------------------------------------------------------------------|
| App fermée après paiement                 | Au retour, recharger état serveur/provider; ne pas recréer charge. |
| Timeout API création order                | Retry avec même idempotency key.                                   |
| Webhook reçu avant réponse client         | Backend applique événement; client lit état final.                 |
| Queue indisponible                        | Outbox/retry; état transactionnel préservé.                        |
| Notification échoue                       | Retry notification sans rejouer transaction.                       |
| Stock service temporairement indisponible | Ne pas confirmer oversell; retry/compensation contrôlée.           |
| Provider indisponible                     | Payment Pending/Unavailable; ne pas simuler succès.                |
| Double clic utilisateur                   | Même idempotency key/action lock.                                  |
| Crash après stock reserve                 | Recovery job/TTL libère réservation orpheline.                     |

# 27. Permissions financières

| **Action**             | **Permission / acteur**                       |
|------------------------|-----------------------------------------------|
| Voir statut own        | Acheteur/client propriétaire ou org autorisée |
| Confirmer cash reçu    | Collecteur explicitement autorisé             |
| Gérer order vendeur    | Seller/org permission                         |
| Soumettre refund       | Finance/support selon workflow                |
| Approuver refund       | Finance role + seuil; four-eye si requis      |
| Override transaction   | Staff très restreint + case + audit           |
| Réconciliation         | Finance Ops / système autorisé                |
| Modifier règles refund | Policy/Admin autorisé; versionné              |

# 28. Critères d'acceptation V1

| **Test**  | **Critère**                                                                                         |
|-----------|-----------------------------------------------------------------------------------------------------|
| COM-AC-01 | Un double clic checkout ne crée pas deux commandes/charges.                                         |
| COM-AC-02 | Deux webhooks Successful identiques ne doublent ni stock, ni ticket, ni notification.               |
| COM-AC-03 | Un timeout provider laisse Payment Pending/ReconciliationRequired, jamais Paid supposé.             |
| COM-AC-04 | Un cash order reste Unpaid jusqu'à confirmation du collecteur autorisé.                             |
| COM-AC-05 | Delivered ne force pas automatiquement cash Paid.                                                   |
| COM-AC-06 | Un paiement échoué/expiré libère la réservation stock une seule fois.                               |
| COM-AC-07 | Deux acheteurs ne peuvent pas acheter le même article unique.                                       |
| COM-AC-08 | Une annulation payée crée un Refund Record au lieu de modifier Payment en Refunded arbitrairement.  |
| COM-AC-09 | Approved refund n'est pas affiché comme Refunded avant confirmation provider.                       |
| COM-AC-10 | La somme des partial refunds ne dépasse pas le montant remboursable.                                |
| COM-AC-11 | Food Order et Delivery Request peuvent avoir des états différents sans incohérence.                 |
| COM-AC-12 | Un delivery provider non assigné ne voit pas l'adresse exacte.                                      |
| COM-AC-13 | Un QR ticket ne peut pas être check-in deux fois sans alerte/refus.                                 |
| COM-AC-14 | Un ticket refunded/annulé est invalide au scan.                                                     |
| COM-AC-15 | L'annulation d'un événement identifie tous les tickets affectés et lance le workflow de résolution. |
| COM-AC-16 | Un refund échoué reste visible et peut être repris sans double refund.                              |
| COM-AC-17 | Une correction admin financière exige permission, reason et audit.                                  |
| COM-AC-18 | Une notification transactionnelle n'est pas dupliquée par retry webhook.                            |
| COM-AC-19 | Le reçu technique n'est pas libellé automatiquement facture fiscale.                                |
| COM-AC-20 | Un Case fermé conserve toutes les transitions financières liées.                                    |

# 29. V1 vs Post-V1

| **V1**                                         | **Post-V1 / hors V1**                                 |
|------------------------------------------------|-------------------------------------------------------|
| Mobile Money via providers approuvés + cash    | Wallet propriétaire / stored balance                  |
| Commandes Marketplace simples                  | Multi-seller checkout sophistiqué                     |
| Food orders + partner delivery                 | Flotte propriétaire, routing/surge/telematics avancés |
| Event ticketing + QR                           | Settlement complexe multi-parties                     |
| Refunds complets/partiels si provider supporte | Escrow général                                        |
| Réconciliation et manual review                | Fraud engine avancé                                   |
| Basic pickup/seller delivery                   | Réseau logistique propriétaire                        |
| Platform Billing plans/passes/promotion        | Lending/crédit                                        |
| Paiements ciblés commerce/ticketing            | Orchestration universelle de tous services            |

# 30. Paramètres à valider / configurer

| **Paramètre**                            | **Statut**                          |
|------------------------------------------|-------------------------------------|
| Fenêtres d'annulation Marketplace        | TBD + validation juridique          |
| Délais/conditions de retour              | TBD + validation juridique RDC      |
| Règles refund restaurant après Preparing | TBD + droit applicable              |
| TTL réservation stock/ticket             | TBD technique/business              |
| Seuils four-eye refunds                  | TBD finance/risk                    |
| Frais Mobile Money/provider              | TBD après intégration/négociation   |
| Settlement marchand/organisateur         | TBD provider/comptabilité           |
| Documents fiscaux requis                 | À VALIDER JURIDIQUEMENT/FISCALEMENT |
| Cash collection par partenaires          | À contractualiser/configurer        |
| Proof of delivery                        | TBD par marché/provider             |
| Politique event postponement/refund      | TBD + droit applicable              |

# 31. Liens avec la suite documentaire

| **Document**                                   | **Relation**                                                          |
|------------------------------------------------|-----------------------------------------------------------------------|
| Document 01 - Référentiel Fonctionnel          | COM, MKT, FOD, DLV, EVT, ENT définissent les capacités.               |
| Document 02 - User Flows                       | UF-06 à UF-08, UF-11/12, UF-19 à UF-21 et UF-27 utilisent ces règles. |
| Document 05 - Plans & Entitlements             | Platform Billing reste séparé des paiements transactionnels.          |
| Document 06 - Accès                            | Permissions financières et scopes protègent les actions.              |
| Document 07 - Trust/Safety                     | Disputes, fraude et safety cases utilisent Case Management.           |
| Document 09 à venir - Back-office & Opérations | Transformera ces règles en queues et procédures staff.                |
| Document 10 à venir - Tests & Recette          | Reprendra COM-AC-01 à COM-AC-20 en scénarios QA.                      |
