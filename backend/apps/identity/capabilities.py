"""Rôles et capacités des organisations (ADR 0006, section 5, matrice figée).

Constantes pures : aucun import de modèle. La fonction de décision ne reçoit ni plan, ni prix, ni
droit commercial (règle 2) ; `is_staff` n'ouvre rien. Une capacité inconnue est une erreur de
programmation (`UnknownCapability`), pas un refus.
"""
from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER

ROLE_OWNER = 'OWNER'
ROLE_ADMIN = 'ADMIN'
ROLE_EDITOR = 'EDITOR'
ROLE_ANALYST = 'ANALYST'
ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR, ROLE_ANALYST)
ROLE_CHOICES = (
    (ROLE_OWNER, "Administrateur principal"),
    (ROLE_ADMIN, "Administrateur"),
    (ROLE_EDITOR, "Éditeur"),
    (ROLE_ANALYST, "Analyste"),
)

# Rang d'autorité : un acteur n'attribue jamais un rôle supérieur au sien (R10).
ROLE_RANK = {ROLE_OWNER: 4, ROLE_ADMIN: 3, ROLE_EDITOR: 2, ROLE_ANALYST: 1}

_ALL = frozenset(ROLES)
_OWNER_ADMIN = frozenset({ROLE_OWNER, ROLE_ADMIN})
_NOT_ANALYST = frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR})
_OWNER = frozenset({ROLE_OWNER})

# Capacité détenue par tous les rôles (seule ouverte sur une organisation suspendue ou archivée) ; sert aussi à joindre
# toute l'équipe (notifications).
CAP_ORG_LEAVE = 'org.leave'

CAPABILITIES = {
    'org.view_internal': _ALL,
    CAP_ORG_LEAVE: _ALL,
    'org.edit_profile': _OWNER_ADMIN,
    'org.manage_members': _OWNER_ADMIN,
    'org.manage_roles': _OWNER_ADMIN,
    'org.archive': _OWNER,
    'org.verification_submit': _OWNER_ADMIN,
    'offer.view_internal': _ALL,
    'offer.publish': _NOT_ANALYST,
    'offer.edit': _NOT_ANALYST,
    'offer.delete': _NOT_ANALYST,
    'review.reply': _NOT_ANALYST,
    'contact.view_requesters': _NOT_ANALYST,
    'contact.manage_channels': _OWNER_ADMIN,
    'message.reply': _OWNER_ADMIN,
    'stats.view': _ALL,
}

# Contextes USER et PROVIDER : toutes les capacités « de contenu », aucune capacité `org.*`.
PERSONAL_CAPABILITIES = frozenset(name for name in CAPABILITIES if not name.startswith('org.'))


class UnknownCapability(LookupError):
    """Capacité absente de la matrice : erreur de programmation."""


def _check_capability(capability):
    if capability not in CAPABILITIES:
        raise UnknownCapability(capability)


def role_has_capability(role, capability) -> bool:
    _check_capability(capability)
    return role in CAPABILITIES[capability]


def capabilities_for_role(role) -> list:
    return sorted(name for name, roles in CAPABILITIES.items() if role in roles)


def capabilities_for_context(context_type, role=None) -> list:
    """Capacités d'un contexte : le titulaire d'un contexte personnel ou prestataire a toutes les
    capacités de contenu ; une organisation se règle par le rôle du membre."""
    if context_type in (CONTEXT_USER, CONTEXT_PROVIDER):
        return sorted(PERSONAL_CAPABILITIES)
    if context_type == CONTEXT_ORGANIZATION:
        return capabilities_for_role(role)
    raise ValueError(f"Type de contexte inconnu : {context_type}")


def context_has_capability(context_type, role, capability) -> bool:
    _check_capability(capability)
    if context_type in (CONTEXT_USER, CONTEXT_PROVIDER):
        return capability in PERSONAL_CAPABILITIES
    if context_type == CONTEXT_ORGANIZATION:
        return role in CAPABILITIES[capability]
    raise ValueError(f"Type de contexte inconnu : {context_type}")


def can_manage_role_of(actor_role, target_role) -> bool:
    """Un administrateur ne manipule que ADMIN, EDITOR, ANALYST ; seul un administrateur principal agit sur OWNER (R9)."""
    if actor_role == ROLE_OWNER:
        return True
    if actor_role == ROLE_ADMIN:
        return target_role != ROLE_OWNER
    return False
