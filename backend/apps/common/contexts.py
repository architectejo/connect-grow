"""Types de contexte d'un compte (règle 1 : un compte unique, plusieurs contextes).

Aucun modèle : de simples constantes partagées par les domaines. Un contexte vendeur est désigné
par (`type`, `id`) : `USER` (identifiant du compte), `PROVIDER` (identifiant du `ProviderProfile`)
ou `ORGANIZATION` (identifiant de l'organisation). ADR 0006, section 4.1.
"""
import uuid
from dataclasses import dataclass
from typing import Optional

from rest_framework import status

from .exception_handler import CodedAPIException

CONTEXT_USER = 'USER'
CONTEXT_PROVIDER = 'PROVIDER'
CONTEXT_ORGANIZATION = 'ORGANIZATION'

# Choix historiques (deux entrées) : encore utilisés par `Review.seller_context_type`, dont le
# changement de `choices` est porté par la migration de T5 (ADR 0006, section 10.2). T5 fera pointer
# `CONTEXT_CHOICES` vers `ALL_CONTEXT_CHOICES` et supprimera cette distinction.
CONTEXT_CHOICES = (
    (CONTEXT_USER, "Compte personnel"),
    (CONTEXT_ORGANIZATION, "Organisation"),
)
ALL_CONTEXT_CHOICES = (
    (CONTEXT_USER, "Compte personnel"),
    (CONTEXT_PROVIDER, "Prestataire individuel"),
    (CONTEXT_ORGANIZATION, "Organisation"),
)

# Codes de refus d'autorisation (ADR 0006, A14) : tous en 403, en majuscules.
DENY_CONTEXT = 'DENY_CONTEXT'
DENY_RELATION = 'DENY_RELATION'
DENY_PERMISSION = 'DENY_PERMISSION'
DENY_SECURITY = 'DENY_SECURITY'
DENY_OBJECT_STATE = 'DENY_OBJECT_STATE'

DENY_CODES = (DENY_CONTEXT, DENY_RELATION, DENY_PERMISSION, DENY_SECURITY, DENY_OBJECT_STATE)


@dataclass(frozen=True)
class ActingContext:
    """Contexte sous lequel une action est tentée. Ne confère aucune permission par lui-même (R4)."""

    user_id: uuid.UUID
    type: str
    id: uuid.UUID
    role: Optional[str] = None


class ContextDenied(CodedAPIException):
    """Refus d'autorisation lié au contexte (403). Le message ne contient jamais le nom d'une
    organisation ni d'information sur d'autres membres."""

    def __init__(self, code, detail=None):
        if code not in DENY_CODES:
            raise ValueError(f"Code de refus inconnu : {code}")
        super().__init__(detail or "Action non autorisée dans ce contexte.", code, status.HTTP_403_FORBIDDEN)


def audit_context_args(ctx):
    """(type, id) à passer à `AuditLog` pour une action exécutée sous le contexte `ctx`."""
    if ctx is None:
        return None, None
    return ctx.type, ctx.id
