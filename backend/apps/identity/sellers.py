"""Contextes vendeur vus par les autres domaines : fiches publiques, visibilité, destinataires, canaux de
contact, état du compte (ADR 0006, 7.1 et A7, A9).

Un contexte vendeur est désigné par le couple (`type`, `id`) : `USER` (identifiant du compte), `PROVIDER`
(identifiant du profil prestataire), `ORGANIZATION` (identifiant de l'organisation). Toutes les lectures sont
PAR LOT : le nombre de requêtes ne dépend pas du nombre de vendeurs. Aucune fonction ne renvoie de téléphone,
d'e-mail, de liste de membres ni d'adresse exacte (règle 10).

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

from django.db import transaction

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER
from apps.common.utils import parse_uuid
from apps.moderation.services import get_restricted_user_ids
from apps.platform_core.services import publish_event

from . import capabilities, verification
from .models import Membership, Organization, ProviderProfile, User

NO_CLAIMS_SUMMARY = {'complete': False, 'label': None}

STATUS_REASON_ACCOUNT_DEACTIVATED = 'account_deactivated'
STATUS_REASON_ACCOUNT_REACTIVATED = 'account_reactivated'

_CONTEXT_TYPES = (CONTEXT_USER, CONTEXT_PROVIDER, CONTEXT_ORGANIZATION)


def _pairs(contexts) -> dict:
    """`{type: {uuid, ...}}` à partir de couples (type, id) ; les couples invalides sont ignorés."""
    grouped = {context_type: set() for context_type in _CONTEXT_TYPES}
    for context_type, context_id in contexts:
        parsed = parse_uuid(context_id)
        if context_type in grouped and parsed is not None:
            grouped[context_type].add(parsed)
    return grouped


# --- Fiches publiques -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class SellerSummary:
    """Fiche publique d'un contexte vendeur (ADR 0006, 7.1). Ni téléphone, ni e-mail, ni liste de membres,
    ni NIF, ni adresse exacte. `verified_claims` et `verification_summary` sont DÉRIVÉS des pièces validées
    (règle 3) : un plan payant n'y change rien."""

    context_type: str
    context_id: uuid.UUID
    display_name: str
    photo: Optional[str]  # URL relative du média, ou None
    org_type: Optional[str]
    description: Optional[str]
    verified_claims: list
    verification_summary: dict
    member_since: object


def get_seller_summaries(contexts: Iterable) -> dict:
    """Fiches indexées par (type, id), par lot : une requête par type de contexte, plus trois pour les claims
    des organisations. Un contexte inconnu n'apparaît pas dans le résultat."""
    grouped = _pairs(contexts)
    summaries = {}

    if grouped[CONTEXT_USER]:
        for user in User.objects.filter(pk__in=grouped[CONTEXT_USER]):
            summaries[(CONTEXT_USER, user.pk)] = SellerSummary(
                context_type=CONTEXT_USER, context_id=user.pk, display_name=_public_name(user.full_name),
                photo=user.photo.url if user.photo else None, org_type=None, description=None,
                verified_claims=[], verification_summary=dict(NO_CLAIMS_SUMMARY), member_since=user.date_joined,
            )

    if grouped[CONTEXT_PROVIDER]:
        for profile in ProviderProfile.objects.filter(pk__in=grouped[CONTEXT_PROVIDER]).select_related('user'):
            # Le profil prestataire n'a pas de photo propre : la photo personnelle du compte n'est pas exposée
            # (règle 10). Dette : photo propre du profil prestataire (ADR 0006, 19.4).
            summaries[(CONTEXT_PROVIDER, profile.pk)] = SellerSummary(
                context_type=CONTEXT_PROVIDER, context_id=profile.pk, display_name=profile.display_name,
                photo=None, org_type=None, description=profile.bio,
                verified_claims=[], verification_summary=dict(NO_CLAIMS_SUMMARY), member_since=profile.created_at,
            )

    if grouped[CONTEXT_ORGANIZATION]:
        organizations = list(Organization.objects.filter(pk__in=grouped[CONTEXT_ORGANIZATION]))
        proofs = verification.get_verification_summaries([org.pk for org in organizations])
        for org in organizations:
            proof = proofs.get(org.pk) or {'verified_claims': [], 'summary': dict(NO_CLAIMS_SUMMARY)}
            summaries[(CONTEXT_ORGANIZATION, org.pk)] = SellerSummary(
                context_type=CONTEXT_ORGANIZATION, context_id=org.pk, display_name=org.name,
                photo=org.logo.url if org.logo else None, org_type=org.org_type, description=org.description,
                verified_claims=proof['verified_claims'], verification_summary=proof['summary'],
                member_since=org.created_at,
            )
    return summaries


def _public_name(full_name) -> str:
    from .services import public_display_name

    return public_display_name(full_name)


# --- Visibilité publique (A7) ------------------------------------------------------------------------------

def get_seller_context_public_flags(contexts: Iterable) -> dict:
    """`{(type, id): bool}` : le vendeur est-il public ? Source du recalcul de `Offer.seller_is_public`.
    `USER` : compte actif et sans sanction bloquante ; `PROVIDER` : profil ACTIVE et compte titulaire public ;
    `ORGANIZATION` : organisation ACTIVE. Un contexte inconnu est non public. Par lot."""
    grouped = _pairs(contexts)
    flags = {}

    profiles = {}
    if grouped[CONTEXT_PROVIDER]:
        profiles = dict(
            ProviderProfile.objects.filter(
                pk__in=grouped[CONTEXT_PROVIDER], status=ProviderProfile.STATUS_ACTIVE,
            ).values_list('pk', 'user_id')
        )
    account_ids = grouped[CONTEXT_USER] | set(profiles.values())
    public_accounts = set()
    if account_ids:
        active = set(User.objects.filter(pk__in=account_ids, is_active=True).values_list('pk', flat=True))
        public_accounts = active - get_restricted_user_ids(active)

    for user_id in grouped[CONTEXT_USER]:
        flags[(CONTEXT_USER, user_id)] = user_id in public_accounts
    for provider_id in grouped[CONTEXT_PROVIDER]:
        flags[(CONTEXT_PROVIDER, provider_id)] = profiles.get(provider_id) in public_accounts
    if grouped[CONTEXT_ORGANIZATION]:
        active_orgs = set(
            Organization.objects.filter(
                pk__in=grouped[CONTEXT_ORGANIZATION], status=Organization.STATUS_ACTIVE,
            ).values_list('pk', flat=True)
        )
        for org_id in grouped[CONTEXT_ORGANIZATION]:
            flags[(CONTEXT_ORGANIZATION, org_id)] = org_id in active_orgs
    return flags


def is_seller_context_public(context_type, context_id) -> bool:
    """Vrai si le contexte vendeur est public (ADR 0006, 7.1). Faux pour un contexte inconnu ou mal formé."""
    parsed = parse_uuid(context_id)
    if parsed is None:
        return False
    return get_seller_context_public_flags([(context_type, parsed)]).get((context_type, parsed), False)


# --- Contextes de l'utilisateur ---------------------------------------------------------------------------

def get_user_context_roles(user_id) -> dict:
    """Contextes dans lesquels le compte peut agir, avec son rôle : `{(type, id): rôle ou None}`. `USER` (rôle
    nul), `PROVIDER` s'il est actif (rôle nul), organisations ACTIVE dont il est membre actif. Deux requêtes,
    sans cache. Sert à calculer « le demandeur peut modifier cette offre » pour toute une page sans N+1."""
    parsed = parse_uuid(user_id)
    if parsed is None:
        return {}
    roles = {(CONTEXT_USER, parsed): None}
    provider_id = ProviderProfile.objects.filter(
        user_id=parsed, status=ProviderProfile.STATUS_ACTIVE,
    ).values_list('pk', flat=True).first()
    if provider_id is not None:
        roles[(CONTEXT_PROVIDER, provider_id)] = None
    for organization_id, role in Membership.objects.filter(
        user_id=parsed, status=Membership.STATUS_ACTIVE, organization__status=Organization.STATUS_ACTIVE,
    ).values_list('organization_id', 'role'):
        roles[(CONTEXT_ORGANIZATION, organization_id)] = role
    return roles


def context_has_capability(context_type, role, capability) -> bool:
    """Le rôle (nul pour `USER`/`PROVIDER`) a-t-il cette capacité dans ce type de contexte ? Pure (aucune requête)."""
    return capabilities.context_has_capability(context_type, role, capability)


def get_context_recipients(context_type, context_id, capability) -> list:
    """Comptes à notifier pour un contexte (ADR 0006, 7.1) : `USER` = le compte, `PROVIDER` = son titulaire,
    `ORGANIZATION` = membres actifs dont le rôle a la capacité. Comptes désactivés ou sous sanction bloquante exclus. Deux requêtes au plus."""
    parsed = parse_uuid(context_id)
    if parsed is None:
        return []
    if context_type == CONTEXT_USER:
        accounts = list(User.objects.filter(pk=parsed, is_active=True).values_list('pk', flat=True))
    elif context_type == CONTEXT_PROVIDER:
        accounts = list(
            ProviderProfile.objects.filter(pk=parsed, user__is_active=True).values_list('user_id', flat=True)
        )
    elif context_type == CONTEXT_ORGANIZATION:
        roles = [role for role in capabilities.ROLES if capabilities.role_has_capability(role, capability)]
        accounts = sorted(
            Membership.objects.filter(
                organization_id=parsed, status=Membership.STATUS_ACTIVE, role__in=roles,
                organization__status=Organization.STATUS_ACTIVE, user__is_active=True,
            ).values_list('user_id', flat=True),
            key=str,
        )
    else:
        return []
    # Un compte sous sanction bloquante ne reçoit plus rien au titre d'un contexte vendeur.
    restricted = get_restricted_user_ids(accounts)
    return [account for account in accounts if account not in restricted]


# --- Contact par contexte vendeur (interim T5a, étendu par T7) -------------------------------------------------

def get_contact_accounts(contexts: Iterable) -> dict:
    """Compte dont les réglages de contact valent pour chaque contexte : `USER` = lui-même, `PROVIDER` = son
    titulaire (mêmes `ContactPoint`/`ContactConsent`, ADR 0006 11.2), `ORGANIZATION` = None (le numéro d'une
    organisation n'est jamais celui d'un membre ; la prise en charge arrive avec T7). `{(type, id): user_id|None}`."""
    grouped = _pairs(contexts)
    accounts = {(CONTEXT_USER, user_id): user_id for user_id in grouped[CONTEXT_USER]}
    owners = {}
    if grouped[CONTEXT_PROVIDER]:
        owners = dict(
            ProviderProfile.objects.filter(
                pk__in=grouped[CONTEXT_PROVIDER], status=ProviderProfile.STATUS_ACTIVE,
            ).values_list('pk', 'user_id')
        )
    for provider_id in grouped[CONTEXT_PROVIDER]:
        accounts[(CONTEXT_PROVIDER, provider_id)] = owners.get(provider_id)
    for org_id in grouped[CONTEXT_ORGANIZATION]:
        accounts[(CONTEXT_ORGANIZATION, org_id)] = None
    return accounts


def get_context_allowed_channels(contexts: Iterable) -> dict:
    """Canaux ouverts par contexte vendeur, `{(type, id): ['MESSAGE', ...]}` (ordre fixe, aucun numéro).
    `USER`/`PROVIDER` : ceux du compte titulaire ; `ORGANIZATION` : aucun tant que le contact d'équipe
    (T7, intérim D6) n'est pas livré. Tout contexte demandé figure dans le résultat."""
    from .services import get_allowed_channels

    contexts = list(contexts)
    accounts = get_contact_accounts(contexts)
    by_account = get_allowed_channels([account for account in accounts.values() if account is not None])
    result = {}
    for context_type, context_id in contexts:
        parsed = parse_uuid(context_id)
        account = accounts.get((context_type, parsed))
        result[(context_type, parsed if parsed is not None else context_id)] = (
            list(by_account.get(account, [])) if account is not None else []
        )
    return result


# --- État du compte (A9) ------------------------------------------------------------------------------------

def set_account_active(user_id, active: bool, actor=None) -> bool:
    """Point unique de changement de `User.is_active` (ADR 0006, 7.1) : écrit le drapeau puis publie
    `identity.seller_context_status_changed` pour le contexte personnel et, s'il existe, pour le profil
    prestataire (les offres suivent par `marketplace.sync_seller_visibility`). Idempotent : sans changement,
    aucun événement. Renvoie vrai si l'état a changé. Les sanctions (modération) passent par ici."""
    parsed = parse_uuid(user_id)
    if parsed is None:
        return False
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=parsed).first()
        if user is None or user.is_active == bool(active):
            return False
        user.is_active = bool(active)
        user.save(update_fields=['is_active'])
        announce_account_status(parsed, bool(active), actor)
    return True


def announce_account_status(user_id, active: bool, actor=None) -> None:
    """Publie le changement de statut des contextes vendeur d'un compte (personnel et prestataire) et le
    diffuse immédiatement aux abonnés, dans la transaction. À appeler dans `transaction.atomic()`. Sert aussi
    à l'administration Django, qui peut modifier `is_active` directement."""
    reason = STATUS_REASON_ACCOUNT_REACTIVATED if active else STATUS_REASON_ACCOUNT_DEACTIVATED
    contexts = [(CONTEXT_USER, 'user', user_id)]
    provider_id = ProviderProfile.objects.filter(user_id=user_id).values_list('pk', flat=True).first()
    if provider_id is not None:
        contexts.append((CONTEXT_PROVIDER, 'provider', provider_id))
    for context_type, aggregate_type, context_id in contexts:
        publish_event(
            'identity.seller_context_status_changed', aggregate_type=aggregate_type, aggregate_id=context_id,
            payload={
                'context_type': context_type, 'context_id': str(context_id), 'reason': reason,
                'actor_id': str(actor.pk) if actor is not None else None,
            },
            deliver_now=True,
        )
