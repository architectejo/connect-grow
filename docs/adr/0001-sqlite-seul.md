# ADR 0001 — SQLite comme seul SGBD jusqu'à la fin du projet

- **Statut :** accepté
- **Date :** 06/10/2026
- **Décideurs :** Anicet, Jonathan (IMARA TECH Group)

## Contexte

Le CDC v1.1 prévoyait SQLite en développement et MySQL en recette, en CI et en production. L'équipe veut réduire l'outillage pendant le développement.

## Décision

SQLite est le seul SGBD utilisé dans tous les environnements jusqu'à la fin du projet. MySQL (ou un autre SGBD de production) sera choisi et introduit en fin de projet, avant la mise en production (tâche F-01 du backlog).

## Conséquences

- Pas de service MySQL dans Docker Compose ; le pilote MySQL sort de `requirements.txt`.
- La CI exécute les tests sur SQLite.
- Le code reste portable : ORM uniquement ; `max_length` explicite sur les champs indexés ; pas de contrainte d'unicité conditionnelle (garantie en couche service) ; casse traitée explicitement ; pas de fonction SQL propre à SQLite.
- Risque accepté : des écarts de comportement (casse, emojis, unicité) peuvent apparaître au passage à MySQL. Ils seront traités par une campagne de tests de portabilité dédiée (F-01).
- SQLite gère mal les écritures concurrentes : la recette du lot 2 (messagerie, billetterie) devra en tenir compte (volumes de test modestes, `timeout` de connexion relevé).
