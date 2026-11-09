# Registre de recette MySQL — Connecte+

Tenu par le chef de projet. Ce registre liste les comportements que SQLite ne peut pas prouver (verrous de ligne, concurrence réelle, DDL non transactionnel, casse, emojis) et qui doivent être rejoués sur MySQL **avant la production** (tâche F-01 du backlog).

Sous SQLite, `select_for_update` est sans effet et les écritures sont sérialisées : les tests de concurrence actuels sont des tests de « concurrence logique » (entrelacement simulé), honnêtes sur leur portée mais insuffisants pour valider MySQL.

| ID | Origine | Cas à rejouer sur MySQL | Résultat attendu | Statut |
|---|---|---|---|---|
| MYSQL-01 | ADR 0008 §11 (L1-01 B2b) | Deux acceptations simultanées du même jeton d'invitation, par deux comptes différents | Une seule gagne ; la seconde reçoit `404 invitation_invalid` ; un seul membre créé | À faire |
| MYSQL-02 | ADR 0008 §11 (L1-01 B2b) | Acceptation contre révocation de la même invitation | Une seule issue ; état final cohérent (ACCEPTED ou REVOKED, jamais les deux) | À faire |
| MYSQL-03 | ADR 0008 §11 (L1-01 B2b) | Refus contre acceptation de la même invitation | Une seule issue ; pas de membre créé si le refus gagne | À faire |
| MYSQL-04 | ADR 0008 (L1-01 B1) | Deux retraits ou rétrogradations simultanés des deux derniers propriétaires effectifs d'une organisation à offres actives | `409 last_effective_owner` pour l'un des deux ; l'organisation garde au moins un propriétaire effectif | À faire |
| MYSQL-05 | ADR 0008 (L1-01 B1) | Transfert de propriété concurrent à un changement de rôle de la cible | Transaction cohérente, aucun état intermédiaire visible ; verrou `_lock_organization` effectif | À faire |
| MYSQL-06 | ADR 0008 (L1-01 B2b) | Acceptation concurrente à la rétrogradation ou au retrait de l'inviteur | L'acceptation échoue (404 uniforme) si l'autorité est perdue ; sinon l'invitation est acceptée avant le balayage | À faire |
| MYSQL-07 | ADR 0006 §15 (L0-09) | Verrous de ligne de `last_owner` et conversion des anciens comptes entreprise (DDL non transactionnel) | Voir l'ADR 0006 §15 et journal du 09/11/2026 | À faire |
| MYSQL-08 | ADR 0001 | Casse (collation), unicité des noms normalisés, emojis (utf8mb4) sur les champs indexés | Mêmes résultats que sur SQLite | À faire |

Prérequis de production liés (voir ADR 0006 §18-19 et ADR 0008) : cache partagé entre processus pour les limiteurs, `NUM_PROXIES` et en-tête `X-Forwarded-For` réécrit par Nginx.
