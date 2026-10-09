"""Types de contexte d'un compte (règle 1 : un compte unique, plusieurs contextes).

Aucun modèle : de simples constantes partagées par les domaines. Un contexte vendeur est désigné
par (`type`, `id`) ; tant que les organisations n'existent pas (L0-09), seul `USER` est utilisé et
l'identifiant est celui du compte.
"""

CONTEXT_USER = 'USER'
CONTEXT_ORGANIZATION = 'ORGANIZATION'

CONTEXT_CHOICES = (
    (CONTEXT_USER, "Compte personnel"),
    (CONTEXT_ORGANIZATION, "Organisation"),
)
