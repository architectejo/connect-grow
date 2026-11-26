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
from django.db.models import Q

from apps.common.contexts import (
    CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER, DENY_OBJECT_STATE, DENY_SECURITY, ContextDenied,
)
from apps.common.utils import parse_uuid
from apps.moderation.services import get_restricted_user_ids
from apps.platform_core.services import publish_event

from . import capabilities, verification
from .models import Membership, Organization, ProviderProfile, User
from .organizations import effective_owner_ids_by_organization, reject_awaiting_invitations_of_account

NO_CLAIMS_SUMMARY = {'complete': False, 'label': None}

STATUS_REASON_ACCOUNT_DEACTIVATED = 'account_deactivated'
STATUS_REASON_ACCOUNT_REACTIVATED = 'account_reactivated'
STATUS_REASON_CONTEXT_REMOVED = 'context_removed'

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
    `ORGANIZATION` : organisation ACTIVE, hors revue de création (`creation_review_status != PENDING`, ADR 0010 D8),
    avec au moins un propriétaire actif, compte actif et sans sanction bloquante. Un contexte inconnu est non public.
    Par lot."""
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
            ).exclude(creation_review_status=Organization.CREATION_REVIEW_PENDING).values_list('pk', flat=True)
        )
        # Une organisation dont tous les propriétaires actifs sont désactivés ou sous sanction bloquante n'est pas
        # publique (T9-1, audit M3) : le statut stocké de l'organisation n'est pas modifié.
        # Définition unique du « propriétaire effectif » (partagée avec la règle `last_effective_owner`, ADR 0008 §9).
        led_orgs = set(effective_owner_ids_by_organization(active_orgs)) if active_orgs else set()
        for org_id in grouped[CONTEXT_ORGANIZATION]:
            flags[(CONTEXT_ORGANIZATION, org_id)] = org_id in led_orgs
    return flags


def is_seller_context_public(context_type, context_id) -> bool:
    """Vrai si le contexte vendeur est public (ADR 0006, 7.1). Faux pour un contexte inconnu ou mal formé."""
    parsed = parse_uuid(context_id)
    if parsed is None:
        return False
    return get_seller_context_public_flags([(context_type, parsed)]).get((context_type, parsed), False)


# --- Contextes de l'utilisateur ---------------------------------------------------------------------------

def org_capability_scope_q(capability):
    """Filtre ORM des appartenances dont le périmètre permet d'exercer `capability` au niveau de l'organisation
    (ADR 0010 D3, fermé par défaut, même règle que `capabilities.scope_allows` sans périmètre visé) : organisation
    entière seulement, sauf `org.leave` (tous périmètres)."""
    if capability == capabilities.CAP_ORG_LEAVE:
        return Q()
    return Q(scope_type=capabilities.SCOPE_ORGANIZATION)


def get_user_context_roles(user_id) -> dict:
    """Contextes dans lesquels le compte peut agir, avec son rôle : `{(type, id): rôle ou None}`. `USER` (rôle
    nul), `PROVIDER` s'il est actif (rôle nul), organisations ACTIVE dont il est membre actif. Deux requêtes,
    sans cache. Sert à calculer « le demandeur peut modifier cette offre » pour toute une page sans N+1.
    Une appartenance limitée à une ville ou une unité (ADR 0010 D3) figure avec un rôle NUL : la personne reste
    membre (clé présente), mais aucune capacité de niveau organisation ne lui est reconnue (fermé par défaut)."""
    parsed = parse_uuid(user_id)
    if parsed is None:
        return {}
    roles = {(CONTEXT_USER, parsed): None}
    provider_id = ProviderProfile.objects.filter(
        user_id=parsed, status=ProviderProfile.STATUS_ACTIVE,
    ).values_list('pk', flat=True).first()
    if provider_id is not None:
        roles[(CONTEXT_PROVIDER, provider_id)] = None
    for organization_id, role, scope_type in Membership.objects.filter(
        user_id=parsed, status=Membership.STATUS_ACTIVE, organization__status=Organization.STATUS_ACTIVE,
    ).values_list('organization_id', 'role', 'scope_type'):
        roles[(CONTEXT_ORGANIZATION, organization_id)] = (
            role if scope_type == capabilities.SCOPE_ORGANIZATION else None
        )
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
                org_capability_scope_q(capability),
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


# --- Contact par contexte vendeur (ADR 0006, 4.4 et 11.2) ---------------------------------------------------

def get_contact_accounts(contexts: Iterable) -> dict:
    """Compte dont les réglages de contact valent pour chaque contexte : `USER` = lui-même, `PROVIDER` = son
    titulaire (mêmes `ContactPoint`/`ContactConsent`, ADR 0006 11.2), `ORGANIZATION` = None : le numéro d'une
    organisation lui appartient et n'est jamais celui d'un membre ; ses contacts sont reçus par l'équipe
    (`get_context_recipients`), pas par un compte. `{(type, id): user_id|None}`."""
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


def _organizations_with_team(org_ids) -> set:
    """Organisations ACTIVE dont l'équipe a au moins un destinataire de messages (propriétaire ou administrateur
    actif, compte actif). Une requête, quel que soit le nombre d'organisations."""
    if not org_ids:
        return set()
    roles = [role for role in capabilities.ROLES if capabilities.role_has_capability(role, 'message.reply')]
    return set(
        Membership.objects.filter(
            org_capability_scope_q('message.reply'),
            organization_id__in=org_ids, status=Membership.STATUS_ACTIVE, role__in=roles,
            organization__status=Organization.STATUS_ACTIVE, user__is_active=True,
        ).values_list('organization_id', flat=True)
    )


def _valid_organization_phone_channels(org_ids) -> dict:
    """`{organisation: {'CALL', 'WHATSAPP'}}` : canaux numéro dont l'organisation peut user maintenant (l'interrupteur
    est vérifié par l'appelant) : numéro de contact VÉRIFIÉ de l'organisation, consentement actif, version courante
    du texte et preuve d'accord (4 derniers chiffres) conforme au numéro actuel. Deux requêtes, jamais de numéro."""
    from .models import CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint

    if not org_ids:
        return {}
    points = dict(
        ContactPoint.objects.filter(organization_id__in=org_ids, is_verified=True).values_list('organization_id', 'phone')
    )
    result = {}
    for org_id, channel, last4 in ContactConsent.objects.filter(
        organization_id__in=list(points), channel__in=('CALL', 'WHATSAPP'), is_granted=True,
        text_version=CONTACT_CONSENT_TEXT_VERSION,
    ).values_list('organization_id', 'channel', 'phone_last4'):
        if last4 and points[org_id][-4:] == last4:
            result.setdefault(org_id, set()).add(channel)
    return result


def get_context_allowed_channels(contexts: Iterable) -> dict:
    """Canaux ouverts par contexte vendeur, `{(type, id): ['MESSAGE', ...]}` (ordre fixe, aucun numéro). Tout
    contexte demandé figure dans le résultat ; le nombre de requêtes ne dépend pas du nombre de contextes.

    - `USER`/`PROVIDER` : ceux du compte titulaire (inchangé).
    - `ORGANIZATION` : `MESSAGE` (routé vers l'équipe) tant que l'organisation est active et a au moins un
      destinataire ; `CALL`/`WHATSAPP` seulement si `org_phone_channels_enabled` est vrai ET l'organisation a son
      propre numéro vérifié ET un consentement valide. Le téléphone d'un membre n'entre jamais ici."""
    from .services import CHANNEL_ORDER, get_allowed_channels, get_available_channels

    contexts = list(contexts)
    accounts = get_contact_accounts(contexts)
    by_account = get_allowed_channels([account for account in accounts.values() if account is not None])
    org_ids = {parse_uuid(cid) for ctype, cid in contexts if ctype == CONTEXT_ORGANIZATION} - {None}
    team = _organizations_with_team(org_ids)
    phone = {}
    if team and 'CALL' in get_available_channels(CONTEXT_ORGANIZATION):
        phone = _valid_organization_phone_channels(team)
    result = {}
    for context_type, context_id in contexts:
        parsed = parse_uuid(context_id)
        key = (context_type, parsed if parsed is not None else context_id)
        if context_type == CONTEXT_ORGANIZATION:
            if parsed in team:
                opened = {'MESSAGE'} | phone.get(parsed, set())
                result[key] = [channel for channel in CHANNEL_ORDER if channel in opened]
            else:
                result[key] = []
            continue
        account = accounts.get((context_type, parsed))
        result[key] = list(by_account.get(account, [])) if account is not None else []
    return result


def get_context_contact_endpoint(context_type, context_id, channel):
    """Numéro à remettre pour un canal numéro (`CALL`/`WHATSAPP`) du contexte vendeur. `USER`/`PROVIDER` : numéro du
    compte titulaire. `ORGANIZATION` : numéro de CONTACT de l'organisation, jamais le téléphone d'un membre, et
    seulement si l'interrupteur est ouvert, l'organisation active, le numéro vérifié et le consentement valide.
    Lève `ChannelNotConsented` sinon. À appeler uniquement par la révélation de `marketplace` ; le résultat
    ne se journalise ni ne se publie."""
    from .models import ContactPoint
    from .services import ChannelNotConsented, ContactEndpoint, get_available_channels, get_contact_endpoint

    parsed = parse_uuid(context_id)
    if parsed is None or channel not in ('CALL', 'WHATSAPP'):
        raise ChannelNotConsented()
    if context_type != CONTEXT_ORGANIZATION:
        account = get_contact_accounts([(context_type, parsed)]).get((context_type, parsed))
        if account is None:
            raise ChannelNotConsented()
        return get_contact_endpoint(account, channel)
    if channel not in get_available_channels(CONTEXT_ORGANIZATION):
        raise ChannelNotConsented()
    if channel not in _valid_organization_phone_channels(_organizations_with_team({parsed})).get(parsed, ()):
        raise ChannelNotConsented()
    point = ContactPoint.objects.filter(organization_id=parsed, is_verified=True).first()
    if point is None:
        raise ChannelNotConsented()
    return ContactEndpoint(phone_e164=point.phone)


def ensure_seller_context_accepts_contact(context_type, context_id) -> None:
    """Refuse les écritures d'un acheteur vers une organisation suspendue (`DENY_SECURITY`) ou archivée
    (`DENY_OBJECT_STATE`) : contact, échange, révélation, message. Sans effet pour un compte ou un prestataire (leur
    visibilité passe par `seller_is_public`). Une requête."""
    parsed = parse_uuid(context_id)
    if context_type != CONTEXT_ORGANIZATION or parsed is None:
        return
    state = Organization.objects.filter(pk=parsed).values_list('status', flat=True).first()
    if state == Organization.STATUS_SUSPENDED:
        raise ContextDenied(DENY_SECURITY, "Cette organisation est suspendue.")
    if state == Organization.STATUS_ARCHIVED:
        raise ContextDenied(DENY_OBJECT_STATE, "Cette organisation est archivée.")


def get_accessible_organization_ids(user_id, capability) -> set:
    """Organisations ACTIVE dont le compte est membre actif avec cette capacité, pour un compte utilisable (actif,
    sans sanction bloquante). Sert à l'accès par capacité des autres domaines (messagerie) sans N+1 : deux à trois
    requêtes. Aucun cache : une révocation est effective à l'appel suivant (ADR 0006, 6.2)."""
    from apps.common.contexts import ContextDenied

    from .acting import _ensure_actor_usable

    parsed = parse_uuid(user_id)
    if parsed is None:
        return set()
    try:
        _ensure_actor_usable(User(pk=parsed))
    except ContextDenied:
        return set()
    roles = [role for role in capabilities.ROLES if capabilities.role_has_capability(role, capability)]
    return set(
        Membership.objects.filter(
            org_capability_scope_q(capability),
            user_id=parsed, status=Membership.STATUS_ACTIVE, role__in=roles,
            organization__status=Organization.STATUS_ACTIVE,
        ).values_list('organization_id', flat=True)
    )


# --- État du compte (A9) ------------------------------------------------------------------------------------

def set_account_active(user_id, active: bool, actor=None) -> bool:
    """Point unique de changement de `User.is_active` (ADR 0006, 7.1) : écrit le drapeau puis publie
    `identity.seller_context_status_changed` pour le contexte personnel et, s'il existe, pour le profil
    prestataire (les offres suivent par `marketplace.sync_seller_visibility`). Idempotent : sans changement,
    aucun événement. Renvoie vrai si l'état a changé. Les sanctions (modération) passent par ici.

    Désactivation (sanction bloquante comprise) : les attentes de confirmation d'invitation créées par ce compte sont
    ensuite rejetées (décision S3, L1-01-B7), organisation par organisation, hors de cette transaction (ordre de
    verrouillage : organisation d'abord)."""
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
    if not active:
        reject_awaiting_invitations_of_account(parsed, actor=actor)
    return True


def seller_context_exists(context_type, context_id) -> bool:
    """Le compte, le profil prestataire ou l'organisation désigné existe-t-il encore ? Sert aux abonnés de purge
    (défense en profondeur : on ne purge jamais un contexte vivant)."""
    parsed = parse_uuid(context_id)
    if parsed is None:
        return False
    model = {CONTEXT_USER: User, CONTEXT_PROVIDER: ProviderProfile, CONTEXT_ORGANIZATION: Organization}.get(context_type)
    return model is not None and model.objects.filter(pk=parsed).exists()


def announce_seller_context_removed(context_type, context_id) -> None:
    """Un contexte personnel (`USER`) ou prestataire (`PROVIDER`) vient d'être supprimé (T9-3, règle 10) : publie
    d'abord le changement de statut (les offres cessent aussitôt d'être publiques, même si la purge échoue), puis
    `identity.seller_context_removed` dont les abonnés (marketplace, visibility, reviews) effacent ce qui était
    rattaché au contexte. Les deux sont diffusés dans la transaction de la suppression ; un abonné en échec est repris
    par le cron. `ORGANIZATION` n'est JAMAIS purgée par cet événement (refus). Charge utile : type et identifiant
    seulement. À appeler dans `transaction.atomic()` (récepteurs `post_delete` de `identity.signals`)."""
    if context_type not in (CONTEXT_USER, CONTEXT_PROVIDER):
        raise ValueError("Seuls les contextes personnel et prestataire peuvent être purgés.")
    aggregate_type = 'user' if context_type == CONTEXT_USER else 'provider'
    publish_event(
        'identity.seller_context_status_changed', aggregate_type=aggregate_type, aggregate_id=context_id,
        payload={
            'context_type': context_type, 'context_id': str(context_id), 'reason': STATUS_REASON_CONTEXT_REMOVED,
            'actor_id': None,
        },
        deliver_now=True,
    )
    publish_event(
        'identity.seller_context_removed', aggregate_type=aggregate_type, aggregate_id=context_id,
        payload={'context_type': context_type, 'context_id': str(context_id)},
        deliver_now=True,
    )


def announce_account_status(user_id, active: bool, actor=None) -> None:
    """Publie le changement de statut des contextes vendeur d'un compte (personnel, prestataire et organisations dont il est propriétaire) et le
    diffuse immédiatement aux abonnés, dans la transaction. À appeler dans `transaction.atomic()`. Sert aussi
    à l'administration Django, qui peut modifier `is_active` directement."""
    reason = STATUS_REASON_ACCOUNT_REACTIVATED if active else STATUS_REASON_ACCOUNT_DEACTIVATED
    contexts = [(CONTEXT_USER, 'user', user_id)]
    # Organisations dont ce compte est propriétaire actif : leur visibilité dépend de leurs propriétaires.
    for org_id in Membership.objects.filter(
        user_id=user_id, role=capabilities.ROLE_OWNER, status=Membership.STATUS_ACTIVE,
    ).values_list('organization_id', flat=True):
        contexts.append((CONTEXT_ORGANIZATION, 'organization', org_id))
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
