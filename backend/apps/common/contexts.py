"""Types de contexte d'un compte (règle 1 : un compte unique, plusieurs contextes).

Aucun modèle : de simples constantes partagées par les domaines. Un contexte vendeur est désigné
par (`type`, `id`) : `USER` (identifiant du compte), `PROVIDER` (identifiant du `ProviderProfile`)
ou `ORGANIZATION` (identifiant de l'organisation). ADR 0006, section 4.1.

Exceptions : ce module importe `CodedAPIException` (Django REST framework) pour définir `ContextDenied` ;
il reste sans modèle et ne dépend d'aucun domaine.
"""
import uuid
from dataclasses import dataclass
from typing import Optional

from rest_framework import status

from .exception_handler import CodedAPIException

CONTEXT_USER = 'USER'
CONTEXT_PROVIDER = 'PROVIDER'
CONTEXT_ORGANIZATION = 'ORGANIZATION'

ALL_CONTEXT_CHOICES = (
    (CONTEXT_USER, "Compte personnel"),
    (CONTEXT_PROVIDER, "Prestataire individuel"),
    (CONTEXT_ORGANIZATION, "Organisation"),
)
# Choix des champs `seller_context_type` (offres, compteurs, avis) : les trois contextes (ADR 0006, T5).
CONTEXT_CHOICES = ALL_CONTEXT_CHOICES

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
    # Périmètre de l'appartenance (organisation seulement ; ADR 0010 D3). Codes et UUID, sans dépendance à `identity`.
    # Fermé par défaut (relecture B6) : un contexte d'organisation construit sans périmètre n'exerce aucune capacité
    # de niveau organisation, sauf `org.leave` ; la résolution (`identity.acting`) le renseigne toujours.
    scope_type: Optional[str] = None
    scope_id: Optional[uuid.UUID] = None


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
