"""Contexte actif : résolution de l'en-tête `X-Context`, autorisation par capacité, liste des contextes
(ADR 0006, section 6 ; décision D3).

Principes :
- l'en-tête est revalidé en base à CHAQUE requête qui en a besoin ; aucun cache de rôle ni d'appartenance
  (ni `lru_cache`, ni cache Django, ni claim JWT) : une révocation est effective à la requête suivante.
  Le résultat n'est mémorisé que sur l'objet `request`, pour la durée de la requête ;
- en-tête absent = contexte personnel ; présent mais vide, mal formé ou de type inconnu = refus
  `DENY_CONTEXT`, jamais de repli silencieux ;
- pas d'oracle d'existence : une organisation inexistante et une organisation dont on n'est pas membre
  produisent exactement la même réponse (`DENY_RELATION`) ;
- `is_staff` et `is_superuser` ne contournent rien ; aucun plan ni droit commercial n'entre ici (règle 2).

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
import uuid
from dataclasses import dataclass
from typing import Optional

from django.db.models.functions import Lower
from rest_framework import permissions

from apps.common.contexts import (
    CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER, DENY_CONTEXT, DENY_OBJECT_STATE, DENY_PERMISSION,
    DENY_RELATION, DENY_SECURITY, ActingContext, ContextDenied,
)

from . import capabilities
from .models import Membership, Organization, ProviderProfile

CONTEXT_HEADER = 'X-Context'
CONTEXT_HEADER_META_KEY = 'HTTP_X_CONTEXT'
_REQUEST_CACHE_ATTR = '_acting_context'

_VALID_TYPES = (CONTEXT_USER, CONTEXT_PROVIDER, CONTEXT_ORGANIZATION)

# Messages uniformes : jamais de nom d'organisation ni d'information sur d'autres membres.
MSG_MALFORMED = "Le contexte demandé est invalide."
MSG_NOT_MEMBER = "Vous n'agissez pas pour ce contexte."
MSG_SUSPENDED = "Cette organisation est suspendue."
MSG_ARCHIVED = "Cette organisation est archivée."
MSG_PROVIDER_ARCHIVED = "Ce profil de prestataire est archivé."
MSG_FORBIDDEN = "Votre rôle ne permet pas cette action dans ce contexte."


def _parse_header(raw):
    """(type, id) ou lève `DENY_CONTEXT`. `USER` seul désigne le compte (id = None). L'UUID doit être au
    format canonique minuscule : pas de normalisation permissive (casse, accolades, espaces)."""
    if not isinstance(raw, str):
        raise ContextDenied(DENY_CONTEXT, MSG_MALFORMED)
    if raw == CONTEXT_USER:
        return CONTEXT_USER, None
    context_type, sep, raw_id = raw.partition(':')
    if not sep or context_type not in _VALID_TYPES:
        raise ContextDenied(DENY_CONTEXT, MSG_MALFORMED)
    try:
        parsed = uuid.UUID(raw_id)
    except (ValueError, AttributeError, TypeError):
        raise ContextDenied(DENY_CONTEXT, MSG_MALFORMED)
    if str(parsed) != raw_id:
        raise ContextDenied(DENY_CONTEXT, MSG_MALFORMED)
    return context_type, parsed


def _provider_state(user_id, provider_id):
    """Statut du profil prestataire si c'est bien celui de `user_id`, sinon None (même résultat pour
    un profil inexistant et pour celui d'un autre compte). Une requête."""
    row = ProviderProfile.objects.filter(pk=provider_id).values_list('user_id', 'status').first()
    if row is None or row[0] != user_id:
        return None
    return row[1]


def _membership_state(user_id, organization_id):
    """(rôle, statut de l'organisation) pour une appartenance ACTIVE, sinon None. Une requête (jointure)."""
    return Membership.objects.filter(
        user_id=user_id, organization_id=organization_id, status=Membership.STATUS_ACTIVE,
    ).values_list('role', 'organization__status').first()


def _check_organization_status(org_status):
    if org_status == Organization.STATUS_SUSPENDED:
        raise ContextDenied(DENY_SECURITY, MSG_SUSPENDED)
    if org_status == Organization.STATUS_ARCHIVED:
        raise ContextDenied(DENY_OBJECT_STATE, MSG_ARCHIVED)


def resolve_acting_context(user, raw_header=None) -> ActingContext:
    """Contexte sous lequel `user` agit. `raw_header` : valeur brute de `X-Context`, ou None si l'en-tête
    est absent (contexte personnel). Au plus une requête SQL (ADR 0006, 6.2)."""
    if raw_header is None:
        return ActingContext(user.pk, CONTEXT_USER, user.pk)
    context_type, context_id = _parse_header(raw_header)

    if context_type == CONTEXT_USER:
        if context_id is not None and context_id != user.pk:
            raise ContextDenied(DENY_CONTEXT, MSG_MALFORMED)
        return ActingContext(user.pk, CONTEXT_USER, user.pk)

    if context_type == CONTEXT_PROVIDER:
        provider_status = _provider_state(user.pk, context_id)
        if provider_status is None:
            raise ContextDenied(DENY_CONTEXT, MSG_MALFORMED)
        if provider_status != ProviderProfile.STATUS_ACTIVE:
            raise ContextDenied(DENY_OBJECT_STATE, MSG_PROVIDER_ARCHIVED)
        return ActingContext(user.pk, CONTEXT_PROVIDER, context_id)

    state = _membership_state(user.pk, context_id)
    if state is None:
        raise ContextDenied(DENY_RELATION, MSG_NOT_MEMBER)
    role, org_status = state
    _check_organization_status(org_status)
    return ActingContext(user.pk, CONTEXT_ORGANIZATION, context_id, role)


def get_acting_context(request) -> ActingContext:
    """Contexte actif de la requête DRF, résolu une seule fois (mémorisation sur `request` seulement).
    Lève `ContextDenied`. Utilisateur non authentifié : `DENY_CONTEXT` (les vues exigent aussi
    `IsAuthenticated`, ce qui donne le 401 natif avant d'arriver ici)."""
    cached = getattr(request, _REQUEST_CACHE_ATTR, None)
    if cached is not None:
        return cached
    user = request.user
    if user is None or not user.is_authenticated:
        raise ContextDenied(DENY_CONTEXT, MSG_MALFORMED)
    raw = request._request.META.get(CONTEXT_HEADER_META_KEY)
    ctx = resolve_acting_context(user, raw)
    setattr(request, _REQUEST_CACHE_ATTR, ctx)
    return ctx


def authorize(ctx: ActingContext, capability) -> ActingContext:
    """Refus `DENY_PERMISSION` si le rôle du contexte n'a pas la capacité. Capacité inconnue : erreur de
    programmation (`UnknownCapability`), pas un refus."""
    if not capabilities.context_has_capability(ctx.type, ctx.role, capability):
        raise ContextDenied(DENY_PERMISSION, MSG_FORBIDDEN)
    return ctx


def authorize_on(user, context_type, context_id, capability) -> ActingContext:
    """Autorisation PAR OBJET : d'après le contexte propriétaire de l'objet et le rôle réel de `user`,
    jamais d'après l'en-tête (ADR 0006, 6.4). Codes : DENY_RELATION, DENY_SECURITY, DENY_OBJECT_STATE,
    DENY_PERMISSION."""
    parsed = context_id if isinstance(context_id, uuid.UUID) else _safe_uuid(context_id)
    if context_type == CONTEXT_USER:
        if parsed is None or parsed != user.pk:
            raise ContextDenied(DENY_RELATION, MSG_NOT_MEMBER)
        ctx = ActingContext(user.pk, CONTEXT_USER, user.pk)
    elif context_type == CONTEXT_PROVIDER:
        provider_status = _provider_state(user.pk, parsed) if parsed is not None else None
        if provider_status is None:
            raise ContextDenied(DENY_RELATION, MSG_NOT_MEMBER)
        if provider_status != ProviderProfile.STATUS_ACTIVE:
            raise ContextDenied(DENY_OBJECT_STATE, MSG_PROVIDER_ARCHIVED)
        ctx = ActingContext(user.pk, CONTEXT_PROVIDER, parsed)
    elif context_type == CONTEXT_ORGANIZATION:
        state = _membership_state(user.pk, parsed) if parsed is not None else None
        if state is None:
            raise ContextDenied(DENY_RELATION, MSG_NOT_MEMBER)
        _check_organization_status(state[1])
        ctx = ActingContext(user.pk, CONTEXT_ORGANIZATION, parsed, state[0])
    else:
        raise ContextDenied(DENY_CONTEXT, MSG_MALFORMED)
    return authorize(ctx, capability)


def can(user_id, context_type, context_id, capability) -> bool:
    """Variante sans exception d'`authorize_on` pour les autres domaines et les sérialiseurs."""
    from .models import User

    if user_id is None:
        return False
    # `authorize_on` n'utilise que `user.pk` : un objet léger évite une requête.
    stub = User(pk=_safe_uuid(user_id))
    if stub.pk is None:
        return False
    try:
        authorize_on(stub, context_type, context_id, capability)
    except ContextDenied:
        return False
    return True


def _safe_uuid(value) -> Optional[uuid.UUID]:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


# --- Brique DRF ------------------------------------------------------------------------------

class ActingContextMixin:
    """Pour les vues « sensibles au contexte » : `self.acting_context` résout l'en-tête (une fois) et
    `self.authorize_capability('offer.publish')` contrôle la capacité."""

    @property
    def acting_context(self) -> ActingContext:
        return get_acting_context(self.request)

    def authorize_capability(self, capability) -> ActingContext:
        return authorize(self.acting_context, capability)


def capability_permission(capability):
    """Fabrique une classe de permission DRF : authentifié, contexte résolu, capacité détenue.
    Les refus sont des 403 portant un code `DENY_*`."""

    class HasContextCapability(permissions.BasePermission):
        def has_permission(self, request, view):
            if not (request.user and request.user.is_authenticated):
                return False
            authorize(get_acting_context(request), capability)
            return True

    HasContextCapability.__name__ = f"HasContextCapability[{capability}]"
    return HasContextCapability


# --- Liste des contextes disponibles -----------------------------------------------------------

@dataclass(frozen=True)
class AvailableContext:
    type: str
    id: uuid.UUID
    name: str
    role: Optional[str]
    org_type: Optional[str]
    photo: Optional[str]  # URL relative du média, ou None
    capabilities: tuple
    migrated_from_business: bool


def get_contexts_for_user(user) -> list:
    """Contextes que `user` peut activer : personnel, prestataire s'il est actif, organisations ACTIVE dont
    il est membre actif (par nom). Deux requêtes, quel que soit le nombre d'organisations."""
    result = [AvailableContext(
        type=CONTEXT_USER, id=user.pk, name=user.full_name, role=None, org_type=None,
        photo=user.photo.url if user.photo else None,
        capabilities=tuple(capabilities.capabilities_for_context(CONTEXT_USER)), migrated_from_business=False,
    )]
    provider = ProviderProfile.objects.filter(user_id=user.pk, status=ProviderProfile.STATUS_ACTIVE).first()
    if provider is not None:
        result.append(AvailableContext(
            type=CONTEXT_PROVIDER, id=provider.pk, name=provider.display_name, role=None, org_type=None,
            photo=user.photo.url if user.photo else None,
            capabilities=tuple(capabilities.capabilities_for_context(CONTEXT_PROVIDER)),
            migrated_from_business=False,
        ))
    memberships = (
        Membership.objects.filter(
            user_id=user.pk, status=Membership.STATUS_ACTIVE, organization__status=Organization.STATUS_ACTIVE,
        ).select_related('organization').order_by(Lower('organization__name'), 'organization_id')
    )
    for membership in memberships:
        org = membership.organization
        result.append(AvailableContext(
            type=CONTEXT_ORGANIZATION, id=org.pk, name=org.name, role=membership.role, org_type=org.org_type,
            photo=org.logo.url if org.logo else None,
            capabilities=tuple(capabilities.capabilities_for_context(CONTEXT_ORGANIZATION, membership.role)),
            migrated_from_business=org.legacy_business_profile_id is not None,
        ))
    return result
