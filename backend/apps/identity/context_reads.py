"""Lectures par lot des contextes pour les autres domaines : droits d'un compte sur ses contextes, comptes
agissant pour un contexte, destinataires d'une organisation, noms (ADR 0006, 7.1, 9.8 et 19.3).

Toutes les lectures ont un nombre de requêtes INDÉPENDANT du nombre d'objets (règle d'or contre le N+1).
Aucune ne renvoie de téléphone, d'e-mail ni de nom de membre (règle 10). Aucun cache : tout est relu en base.

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
from typing import Iterable

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER
from apps.common.utils import parse_uuid
from apps.moderation.services import is_user_restricted

from . import capabilities
from .models import KycDocument, Membership, Organization, ProviderProfile, User
from .sellers import get_user_context_roles, org_capability_scope_q

_ROLE_LABELS = dict(capabilities.ROLE_CHOICES)
_DOCUMENT_LABELS = dict(KycDocument.DOC_TYPE_CHOICES)


def get_capable_contexts(user_id, capability) -> set:
    """Contextes `(type, id)` pour lesquels ce compte détient la capacité, comme `can(...)` mais PAR LOT : au plus
    4 requêtes (état du compte : 2 ; profil prestataire : 1 ; appartenances : 1), quel que soit le nombre d'objets
    à tester. Le compte désactivé ou sous sanction bloquante n'a aucun droit (même garde que `authorize_on`).
    Un contexte absent du résultat est refusé : organisation suspendue ou archivée, ancien membre, profil
    prestataire archivé, rôle sans la capacité (ex. analyste pour `review.reply`).

    Périmètre (ADR 0010 D3, fermé par défaut) : une appartenance limitée à une ville ou une unité figure avec un rôle
    NUL (`get_user_context_roles`), donc sans AUCUNE capacité ici, pas même `org.leave` (contrairement à
    `capabilities.scope_allows`, qui la laisse passer) : cette lecture par lot sert aux capacités de contenu ; la
    sortie volontaire, elle, passe par `leave_organization`, qui l'autorise pour tout périmètre."""
    parsed = parse_uuid(user_id)
    if parsed is None:
        return set()
    capabilities.role_has_capability(capabilities.ROLE_OWNER, capability)  # capacité inconnue : erreur de programmation
    if not User.objects.filter(pk=parsed, is_active=True).exists() or is_user_restricted(parsed):
        return set()
    return {
        (context_type, context_id)
        for (context_type, context_id), role in get_user_context_roles(parsed).items()
        if capabilities.context_has_capability(context_type, role, capability)
    }


def get_context_member_accounts(contexts: Iterable) -> dict:
    """Comptes qui agissent pour chaque contexte, `{(type, id): frozenset[user_id]}` (ADR 0006, 19.3 n°7) : `USER` =
    le compte ; `PROVIDER` = son titulaire ; `ORGANIZATION` = membres actifs de tout rôle d'une organisation, QUEL QUE
    SOIT son état. Comme `acts_for_context` (testée case par case), sauf l'organisation suspendue, qui reste couverte
    ici. Par lot : au plus 2 requêtes.
    Sert au contrôle « pas de signalement de sa propre offre »."""
    wanted = {CONTEXT_USER: set(), CONTEXT_PROVIDER: set(), CONTEXT_ORGANIZATION: set()}
    for context_type, context_id in contexts:
        parsed = parse_uuid(context_id)
        if context_type in wanted and parsed is not None:
            wanted[context_type].add(parsed)
    result = {(CONTEXT_USER, user_id): frozenset({user_id}) for user_id in wanted[CONTEXT_USER]}
    if wanted[CONTEXT_PROVIDER]:
        owners = dict(ProviderProfile.objects.filter(pk__in=wanted[CONTEXT_PROVIDER]).values_list('pk', 'user_id'))
        for provider_id, owner_id in owners.items():
            result[(CONTEXT_PROVIDER, provider_id)] = frozenset({owner_id})
    if wanted[CONTEXT_ORGANIZATION]:
        members = {}
        # Quel que soit l'état de l'organisation : la suspension n'autorise pas à signaler sa propre offre.
        for organization_id, user_id in Membership.objects.filter(
            organization_id__in=wanted[CONTEXT_ORGANIZATION], status=Membership.STATUS_ACTIVE,
        ).values_list('organization_id', 'user_id'):
            members.setdefault(organization_id, set()).add(user_id)
        for organization_id in wanted[CONTEXT_ORGANIZATION]:
            result[(CONTEXT_ORGANIZATION, organization_id)] = frozenset(members.get(organization_id, ()))
    return result


def get_organization_recipients(organization_id, capability) -> list:
    """Comptes actifs, membres actifs de l'organisation dont le rôle a la capacité, QUEL QUE SOIT l'état de
    l'organisation (une suspension ou une décision de vérification doit pouvoir être annoncée à l'équipe d'une
    organisation suspendue ou archivée). Une requête. Liste vide si aucun membre éligible (comportement
    documenté : rien n'est envoyé, l'événement est traité sans erreur)."""
    parsed = parse_uuid(organization_id)
    if parsed is None:
        return []
    roles = [role for role in capabilities.ROLES if capabilities.role_has_capability(role, capability)]
    return sorted(
        Membership.objects.filter(
            org_capability_scope_q(capability),
            organization_id=parsed, status=Membership.STATUS_ACTIVE, role__in=roles, user__is_active=True,
        ).values_list('user_id', flat=True),
        key=str,
    )


def get_active_organization_ids(user_id) -> set:
    """Organisations dont ce compte est membre ACTIF, quel que soit leur état (une suspension reste visible de
    l'équipe). Une requête. Sert à masquer les notifications d'une organisation quittée (défense en profondeur
    en plus de la purge à la révocation)."""
    parsed = parse_uuid(user_id)
    if parsed is None:
        return set()
    return set(
        Membership.objects.filter(user_id=parsed, status=Membership.STATUS_ACTIVE).values_list('organization_id', flat=True)
    )


def get_context_names(contexts: Iterable) -> dict:
    """Nom public de chaque contexte vendeur, `{(type, id): nom}` : nom de l'organisation, nom d'affichage du
    profil prestataire. Le contexte personnel n'est pas résolu (aucune notification ne le désigne : nul = personnel).
    Un contexte inconnu n'apparaît pas. Au plus 2 requêtes."""
    organizations, providers = set(), set()
    for context_type, context_id in contexts:
        parsed = parse_uuid(context_id)
        if parsed is None:
            continue
        if context_type == CONTEXT_ORGANIZATION:
            organizations.add(parsed)
        elif context_type == CONTEXT_PROVIDER:
            providers.add(parsed)
    names = {}
    if organizations:
        for pk, name in Organization.objects.filter(pk__in=organizations).values_list('pk', 'name'):
            names[(CONTEXT_ORGANIZATION, pk)] = name
    if providers:
        for pk, name in ProviderProfile.objects.filter(pk__in=providers).values_list('pk', 'display_name'):
            names[(CONTEXT_PROVIDER, pk)] = name
    return names


def get_role_label(role) -> str:
    """Libellé français d'un rôle d'organisation (« Éditeur »), ou le code lui-même s'il est inconnu."""
    return _ROLE_LABELS.get(role, role or '')


def get_document_type_label(document_type) -> str:
    """Libellé français d'un type de pièce (« RCCM »), ou le code lui-même s'il est inconnu."""
    return _DOCUMENT_LABELS.get(document_type, document_type or '')
