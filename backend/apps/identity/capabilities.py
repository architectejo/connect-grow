"""Rôles, capacités et périmètres des organisations (ADR 0006, section 5, matrice figée ; amendée par ADR 0010
§4.1 : rôle `MEMBER`, périmètre).

Constantes pures : aucun import de modèle. La fonction de décision ne reçoit ni plan, ni prix, ni
droit commercial (règle 2) ; `is_staff` n'ouvre rien. Une capacité inconnue est une erreur de
programmation (`UnknownCapability`), pas un refus.

Modèle Rôle -> Permissions -> Périmètre (réponse du client Q21) : une appartenance porte UN rôle dans UN périmètre
(`Membership.scope_type`, `scope_id`). En V1 seul le périmètre `ORGANIZATION` (organisation entière) est actif ;
`CITY` et `UNIT` sont déclarés et refusés en écriture (ADR 0010, D3).

Points de lecture du rôle à réécrire le jour où une personne aura plusieurs rôles par organisation (table
`RoleAssignment`, ADR 0010 §4.8) : `organizations.get_active_role`, `sellers.get_user_context_roles`,
`organizations.count_active_owners`, `organizations.effective_owner_ids_by_organization` (et
`count_effective_owners`), `context_reads.get_organization_recipients`, `acting._membership_state`.
"""
import uuid
from typing import NamedTuple, Optional

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER

ROLE_OWNER = 'OWNER'
ROLE_ADMIN = 'ADMIN'
ROLE_EDITOR = 'EDITOR'
ROLE_ANALYST = 'ANALYST'
# « Simple membre » (Q22, Q23 ; ADR 0010 D2) : voit l'espace interne et l'équipe, peut partir, rien d'autre.
ROLE_MEMBER = 'MEMBER'
ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR, ROLE_ANALYST, ROLE_MEMBER)
ROLE_CHOICES = (
    (ROLE_OWNER, "Administrateur principal"),
    (ROLE_ADMIN, "Administrateur"),
    (ROLE_EDITOR, "Éditeur"),
    (ROLE_ANALYST, "Analyste"),
    (ROLE_MEMBER, "Membre"),
)

# Rang d'autorité : un acteur n'attribue jamais un rôle supérieur au sien (R10).
ROLE_RANK = {ROLE_OWNER: 4, ROLE_ADMIN: 3, ROLE_EDITOR: 2, ROLE_ANALYST: 1, ROLE_MEMBER: 0}

_ALL = frozenset(ROLES)
# Tous les rôles sauf `MEMBER` (moindre privilège : ni statistiques, ni offres internes ; ADR 0010 §4.1).
_NOT_MEMBER = frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR, ROLE_ANALYST})
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
    'offer.view_internal': _NOT_MEMBER,
    'offer.publish': _NOT_ANALYST,
    'offer.edit': _NOT_ANALYST,
    'offer.delete': _NOT_ANALYST,
    'review.reply': _NOT_ANALYST,
    'contact.view_requesters': _NOT_ANALYST,
    'contact.manage_channels': _OWNER_ADMIN,
    'message.reply': _OWNER_ADMIN,
    'stats.view': _NOT_MEMBER,
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
    """Un administrateur ne manipule que ADMIN, EDITOR, ANALYST, MEMBER ; seul un administrateur principal agit sur
    OWNER (R9)."""
    if actor_role == ROLE_OWNER:
        return True
    if actor_role == ROLE_ADMIN:
        return target_role != ROLE_OWNER
    return False


# --- Périmètre (ADR 0010 D3, §4.1) -----------------------------------------------------------------------------

SCOPE_ORGANIZATION = 'ORGANIZATION'
SCOPE_CITY = 'CITY'
SCOPE_UNIT = 'UNIT'
SCOPE_TYPES = (SCOPE_ORGANIZATION, SCOPE_CITY, SCOPE_UNIT)
SCOPE_CHOICES = (
    (SCOPE_ORGANIZATION, "Toute l'organisation"),
    (SCOPE_CITY, "Ville"),
    (SCOPE_UNIT, "Unité"),
)
# Seuls types acceptés en écriture en V1 ; `CITY` et `UNIT` sont réservés (étendre ce tuple ne demande aucune
# migration de schéma).
ACTIVE_SCOPE_TYPES = (SCOPE_ORGANIZATION,)


class Scope(NamedTuple):
    """Périmètre d'une appartenance ou d'un objet : `ORGANIZATION` (identifiant nul) ou `CITY`/`UNIT` + UUID."""

    type: str
    id: Optional[uuid.UUID] = None

    @classmethod
    def of(cls, scope_type, scope_id=None) -> 'Scope':
        """Périmètre normalisé (identifiant en `uuid.UUID`), pour que deux périmètres égaux soient comparés
        égaux quel que soit le format d'origine de l'identifiant (chaîne, UUID)."""
        if scope_id is not None and not isinstance(scope_id, uuid.UUID):
            scope_id = uuid.UUID(str(scope_id))
        return cls(scope_type, scope_id)


ORGANIZATION_SCOPE = Scope(SCOPE_ORGANIZATION, None)


def _normalize_scope(scope) -> Scope:
    """Périmètre bien formé, ou `ValueError` : `None` = organisation entière ; sinon couple (type connu, identifiant),
    identifiant nul si et seulement si le type est `ORGANIZATION` (même règle que la contrainte en base)."""
    if scope is None:
        return ORGANIZATION_SCOPE
    if not isinstance(scope, tuple) or len(scope) != 2 or scope[0] not in SCOPE_TYPES:
        raise ValueError(f"Périmètre mal formé : {scope!r}")
    normalized = Scope.of(*scope)
    if (normalized.type == SCOPE_ORGANIZATION) != (normalized.id is None):
        raise ValueError(f"Périmètre mal formé : {scope!r}")
    return normalized


def scope_covers(holder_scope, target_scope) -> bool:
    """Vrai si le périmètre détenu couvre le périmètre visé. `ORGANIZATION` couvre tout ; sinon il faut l'égalité
    (aucune hiérarchie d'unités en V1). `None` vaut organisation entière, des deux côtés. Un périmètre mal formé lève
    `ValueError` (les appelants d'autorisation passent par `scope_allows`, qui en fait un refus)."""
    holder = _normalize_scope(holder_scope)
    target = _normalize_scope(target_scope)
    if holder.type == SCOPE_ORGANIZATION:
        return True
    return holder == target


def scope_allows(holder_scope, capability, target_scope=None) -> bool:
    """Règle unique « le périmètre détenu permet d'exercer cette capacité sur ce périmètre visé » (ADR 0010 D3,
    fermée par défaut) : sans périmètre visé, la capacité s'exerce sur l'organisation entière, donc un périmètre
    `CITY` ou `UNIT` ne la couvre pas. Seule exception : `org.leave` (quitter sa propre appartenance ne vise aucun
    périmètre). Un périmètre visé mal formé est un refus, jamais une erreur."""
    if capability == CAP_ORG_LEAVE:
        return True
    try:
        return scope_covers(holder_scope, target_scope)
    except (ValueError, TypeError, AttributeError):
        return False


def can_delegate(actor_role, actor_scope, target_role, target_scope) -> bool:
    """Un acteur attribue (ou gère) `target_role` sur `target_scope` s'il peut gérer ce rôle (`can_manage_role_of`)
    ET si son périmètre couvre le périmètre visé : un administrateur limité à une branche ne crée pas un
    administrateur global (Q23). Ne reçoit ni plan ni droit commercial (règle 2)."""
    return can_manage_role_of(actor_role, target_role) and scope_covers(actor_scope, target_scope)
