"""Invitations d'équipe par lien à usage unique (L1-01c et d ; ADR 0008 §3 à §7, §11 ; contrat d'API §2).

Règles clés :
- le jeton (`secrets.token_urlsafe(32)`, 256 bits) n'est renvoyé qu'à la création et jamais stocké : seule son empreinte
  SHA-256 l'est. Il ne figure ni dans l'audit, ni dans l'outbox, ni dans une notification, ni dans un journal, ni dans
  une clé de cache (le compteur d'échecs est par compte) ;
- aucun plan, prix ni entitlement dans une signature (règle 2) : l'invitation ne donne aucun droit commercial ;
- toute mutation se fait sous `_lock_organization` ; les passages d'état sont des mises à jour conditionnelles
  `PENDING -> …` (une seule des deux requêtes concurrentes gagne) ;
- aucun oracle : jeton de forme incorrecte, inconnu, expiré, révoqué, utilisé, organisation inactive ou autorité de
  l'inviteur perdue donnent la MÊME réponse `404 invitation_invalid` ; l'aperçu exige un compte connecté ;
- les refus après identification de l'invitation sont journalisés HORS transaction (`INVITATION_REFUSED`) ; un jeton
  inconnu n'est jamais journalisé.

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
import hashlib
import re
import secrets
import unicodedata
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status

from apps.common.contexts import CONTEXT_ORGANIZATION, DENY_SECURITY, ContextDenied
from apps.moderation import services as moderation_services
from apps.moderation.services import record_audit
from apps.platform_core.services import publish_event

from . import capabilities
from .models import INVITABLE_ROLES, Membership, Organization, OrganizationInvitation, User
from .organizations import (
    OrganizationError, _activate_membership, _audit_invitation, _authorize_member, _ensure_under_limit,
    _lock_organization, get_identity_settings, get_organization_for_member, membership_scope,
)
from .throttles import FailureLimiter

LABEL_MAX_LENGTH = 60
TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,128}$')

# Types de changement portés par `identity.organization_invitation_changed`.
CHANGE_CREATED = 'created'
CHANGE_ACCEPTED = 'accepted'
CHANGE_DECLINED = 'declined'
CHANGE_REVOKED = 'revoked'

# Compteur d'échecs de l'échange (aperçu, acceptation, refus), PAR COMPTE : la clé ne contient jamais le jeton.
INVITATION_FAILURES = FailureLimiter('invitation_redeem', threshold=5)

LIST_STATUSES = (
    OrganizationInvitation.STATUS_PENDING, OrganizationInvitation.STATUS_ACCEPTED,
    OrganizationInvitation.STATUS_DECLINED, OrganizationInvitation.STATUS_REVOKED,
    OrganizationInvitation.STATUS_EXPIRED,
)


def invitation_invalid_error():
    """Réponse UNIQUE de toute invitation inutilisable : même statut, même message, même code."""
    return OrganizationError(
        "Cette invitation n'est pas valide.", 'invitation_invalid', status.HTTP_404_NOT_FOUND,
    )


def hash_token(token) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def effective_status(invitation, now=None) -> str:
    """Statut présenté : une `PENDING` échue (pas encore balayée par le cron) est `EXPIRED`."""
    now = now or timezone.now()
    if invitation.status == OrganizationInvitation.STATUS_PENDING and invitation.expires_at <= now:
        return OrganizationInvitation.STATUS_EXPIRED
    return invitation.status


def _publish_invitation_change(organization, invitation, change, actor):
    publish_event(
        'identity.organization_invitation_changed', aggregate_type='organization', aggregate_id=organization.pk,
        payload={
            'organization_id': str(organization.pk), 'invitation_id': str(invitation.pk), 'change': change,
            'role': invitation.role, 'actor_id': str(actor.pk) if actor is not None else None,
            'inviter_id': str(invitation.created_by_id) if invitation.created_by_id else None,
        },
    )


# Caractères de format refusés (contrôle de direction et BOM : usurpation visuelle) ; ZWJ et ZWNJ restent permis
# (emoji composés).
_FORBIDDEN_LABEL_CHARS = frozenset(
    ['‎', '‏', '﻿'] + [chr(c) for c in range(0x202a, 0x202f)] + [chr(c) for c in range(0x2066, 0x206a)]
)


def _clean_label(label) -> str:
    if label is None:
        return ''
    if not isinstance(label, str):
        raise serializers.ValidationError({'label': ["L'étiquette doit être un texte."]})
    label = label.strip()
    if len(label) > LABEL_MAX_LENGTH:
        raise serializers.ValidationError(
            {'label': [f"L'étiquette ne doit pas dépasser {LABEL_MAX_LENGTH} caractères."]},
        )
    if any(unicodedata.category(ch) in ('Cc', 'Zl', 'Zp') or ch in _FORBIDDEN_LABEL_CHARS for ch in label):
        raise serializers.ValidationError({'label': ["L'étiquette contient un caractère non autorisé."]})
    return label


# --- Côté membre habilité : créer, lister, révoquer ---------------------------------------------------------------

def create_invitation(actor, organization_id, role, label='', after_authorization=None):
    """Crée une invitation `PENDING` et renvoie `(invitation, jeton)`. Le jeton clair n'existe qu'ici.
    `org.manage_members` ; rôle `EDITOR` ou `ANALYST` seulement (`INVITABLE_ROLES`) ; plafond d'invitations en attente
    non échues par organisation (réglage), compté sous verrou. L'autorisation précède la validation du corps.
    `after_authorization` : crochet appelé juste après l'autorisation réussie (quota par organisation de la vue :
    un non-membre ne le consomme jamais)."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_members')
        if after_authorization is not None:
            after_authorization()
        if not isinstance(role, str) or role not in capabilities.ROLES:
            raise serializers.ValidationError({'role': ["Rôle inconnu ou manquant."]})
        # Périmètre de l'invitation : organisation entière en V1 (le champ `scope` d'entrée arrive avec B7).
        if role not in INVITABLE_ROLES or not capabilities.can_delegate(
            actor_membership.role, membership_scope(actor_membership), role, capabilities.ORGANIZATION_SCOPE,
        ):
            raise OrganizationError(
                "Ce rôle ne peut pas être attribué par invitation.", 'invitation_role_not_allowed',
                status.HTTP_400_BAD_REQUEST,
            )
        label = _clean_label(label)
        settings_row = get_identity_settings()
        now = timezone.now()
        pending = OrganizationInvitation.objects.filter(
            organization=organization, status=OrganizationInvitation.STATUS_PENDING, expires_at__gt=now,
        ).count()
        if pending >= settings_row.max_pending_invitations:
            raise OrganizationError(
                "Le nombre maximal d'invitations en attente est atteint pour cette organisation.",
                'invitation_limit_reached',
            )
        token = secrets.token_urlsafe(32)
        invitation = OrganizationInvitation.objects.create(
            organization=organization, role=role, token_hash=hash_token(token), label=label, created_by=actor,
            expires_at=now + timedelta(days=settings_row.invitation_ttl_days),
        )
        _audit_invitation(
            actor, 'INVITATION_CREATED', organization, invitation, ttl_days=settings_row.invitation_ttl_days,
        )
        _publish_invitation_change(organization, invitation, CHANGE_CREATED, actor)
    return invitation, token


def list_invitations(actor, organization_id, status_filter=None):
    """Invitations de l'organisation (`org.manage_members`), du plus récent au plus ancien, filtrées par statut
    EFFECTIF (défaut `PENDING` ; une `PENDING` échue compte comme `EXPIRED`). Ni jeton ni empreinte ne sont lus."""
    organization, _ = get_organization_for_member(actor, organization_id, 'org.manage_members')
    status_filter = status_filter or OrganizationInvitation.STATUS_PENDING
    if status_filter not in LIST_STATUSES:
        raise serializers.ValidationError({'status': ["Statut inconnu."]})
    now = timezone.now()
    rows = OrganizationInvitation.objects.filter(organization=organization)
    pending, expired = OrganizationInvitation.STATUS_PENDING, OrganizationInvitation.STATUS_EXPIRED
    if status_filter == pending:
        rows = rows.filter(status=pending, expires_at__gt=now)
    elif status_filter == expired:
        rows = rows.filter(Q(status=expired) | Q(status=pending, expires_at__lte=now))
    else:
        rows = rows.filter(status=status_filter)
    return rows.select_related('created_by').only(
        'id', 'organization', 'role', 'status', 'label', 'created_at', 'expires_at', 'created_by__full_name',
    ).order_by('-created_at', '-id')


def revoke_invitation(actor, organization_id, invitation_id):
    """Révoque une invitation (`org.manage_members`, tout membre habilité peut révoquer toute invitation de
    l'organisation). Mise à jour conditionnelle `PENDING -> REVOKED` : inexistante ou d'une autre organisation, 404
    `invitation_not_found` ; déjà close ou échue, 409 `invitation_not_pending`."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        _authorize_member(actor, organization, 'org.manage_members')
        invitation = OrganizationInvitation.objects.filter(pk=invitation_id, organization=organization).first()
        if invitation is None:
            raise OrganizationError(
                "Cette invitation est introuvable.", 'invitation_not_found', status.HTTP_404_NOT_FOUND,
            )
        now = timezone.now()
        done = OrganizationInvitation.objects.filter(
            pk=invitation.pk, status=OrganizationInvitation.STATUS_PENDING, expires_at__gt=now,
        ).update(
            status=OrganizationInvitation.STATUS_REVOKED, closed_at=now, closed_by=actor, label='', updated_at=now,
        )
        if not done:
            raise OrganizationError("Cette invitation n'est plus en attente.", 'invitation_not_pending')
        _audit_invitation(actor, 'INVITATION_REVOKED', organization, invitation, reason='manual')
        _publish_invitation_change(organization, invitation, CHANGE_REVOKED, actor)


# --- Côté cible : aperçu, acceptation, refus ----------------------------------------------------------------------

class _Refusal(Exception):
    """Refus d'une invitation identifiée : porte la raison journalisée et l'erreur d'API à renvoyer. Levée dans le
    `atomic` pour annuler la prise de l'invitation (elle reste `PENDING`), journalisée et relevée à l'extérieur."""

    def __init__(self, reason, error):
        super().__init__(reason)
        self.reason, self.error = reason, error


def _failure_key(user):
    return str(user.pk)


def _reject_unknown(user):
    """Jeton mal formé ou inconnu (aucune ligne ne correspond à l'empreinte) : seul cas compté comme échec. Une
    invitation connue mais morte suppose la détention d'un vrai jeton de 256 bits : aucun oracle de devinette, et
    un utilisateur qui rouvre un lien expiré ne doit pas se verrouiller. Les réponses restent identiques."""
    INVITATION_FAILURES.failure(_failure_key(user))
    raise invitation_invalid_error()


def _find_invitation(user, token):
    """Vérifie le délai d'échecs du compte, la forme du jeton puis cherche l'invitation par empreinte. Forme
    incorrecte ou inconnu : même 404 uniforme, non journalisé (rien à rattacher), échec compté."""
    INVITATION_FAILURES.check(_failure_key(user))
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        _reject_unknown(user)
    invitation = OrganizationInvitation.objects.filter(token_hash=hash_token(token)).first()
    if invitation is None:
        _reject_unknown(user)
    return invitation


def _inviter_has_authority(invitation, organization) -> bool:
    """L'inviteur est toujours membre actif avec `org.manage_members` au niveau de l'organisation (périmètre entier,
    ADR 0010 D3), peut déléguer le rôle ET le périmètre de l'invitation (`can_delegate`), et son compte est actif et
    non restreint. Relu à chaque aperçu et acceptation (la garantie de sécurité, ADR 0008 §3.3)."""
    inviter_id = invitation.created_by_id
    if inviter_id is None:
        return False
    membership = Membership.objects.filter(
        organization=organization, user_id=inviter_id, status=Membership.STATUS_ACTIVE,
    ).first()
    if membership is None:
        return False
    inviter_scope = membership_scope(membership)
    if not (
        capabilities.role_has_capability(membership.role, 'org.manage_members')
        and capabilities.scope_allows(inviter_scope, 'org.manage_members')
        and capabilities.can_delegate(membership.role, inviter_scope, invitation.role, membership_scope(invitation))
    ):
        return False
    return (
        User.objects.filter(pk=inviter_id, is_active=True).exists()
        and not moderation_services.is_user_restricted(inviter_id)
    )


def _dead_reason(invitation_id, now) -> str:
    """Raison pour laquelle une prise conditionnelle n'a rien modifié (relue ; journal seulement)."""
    current = OrganizationInvitation.objects.filter(pk=invitation_id).first()
    if current is None:
        return 'used'
    if current.status == OrganizationInvitation.STATUS_REVOKED:
        return 'revoked'
    if current.status == OrganizationInvitation.STATUS_EXPIRED or (
        current.status == OrganizationInvitation.STATUS_PENDING and current.expires_at <= now
    ):
        return 'expired'
    return 'used'


def preview_invitation(user, token) -> dict:
    """Aperçu sans effet de bord (n'écrit ni statut ni audit) : mêmes contrôles de validité que l'acceptation, sans
    ceux propres à la cible. Toute invalidité : 404 `invitation_invalid`."""
    from .services import public_display_name  # import tardif : `services` importe ce module

    invitation = _find_invitation(user, token)
    now = timezone.now()
    organization = Organization.objects.filter(pk=invitation.organization_id).first()
    if (
        invitation.status != OrganizationInvitation.STATUS_PENDING or invitation.expires_at <= now
        or organization is None or organization.status != Organization.STATUS_ACTIVE
        or invitation.role not in INVITABLE_ROLES or not _inviter_has_authority(invitation, organization)
    ):
        raise invitation_invalid_error()
    inviter = User.objects.filter(pk=invitation.created_by_id).only('full_name').first()
    return {
        'organization_name': organization.name, 'org_type': organization.org_type, 'role': invitation.role,
        'expires_at': invitation.expires_at, 'invited_by_display_name': public_display_name(inviter.full_name),
    }


def _accept_locked(user, invitation):
    """Corps transactionnel de l'acceptation, dans l'ordre exact de l'ADR 0008 §5.1 (3). Toute levée de `_Refusal`
    annule la transaction, donc la prise de l'invitation : elle reste `PENDING`."""
    try:
        organization = _lock_organization(invitation.organization_id)
    except ContextDenied:
        raise _Refusal('org_inactive', invitation_invalid_error())
    now = timezone.now()
    taken = OrganizationInvitation.objects.filter(
        pk=invitation.pk, status=OrganizationInvitation.STATUS_PENDING, expires_at__gt=now,
    ).update(
        status=OrganizationInvitation.STATUS_ACCEPTED, closed_at=now, closed_by=user, label='', updated_at=now,
    )
    if not taken:
        raise _Refusal(_dead_reason(invitation.pk, now), invitation_invalid_error())
    if organization.status != Organization.STATUS_ACTIVE:
        raise _Refusal('org_inactive', invitation_invalid_error())
    if not _inviter_has_authority(invitation, organization):
        raise _Refusal('authority_lost', invitation_invalid_error())
    if invitation.role not in INVITABLE_ROLES:  # la base n'interdit que OWNER
        raise _Refusal('role_not_invitable', invitation_invalid_error())

    # Contrôles propres à la cible : seulement après validité de l'invitation, et sans effet sur le compteur d'échecs.
    if moderation_services.is_user_restricted(user.pk):
        raise _Refusal(
            'account_restricted', ContextDenied(DENY_SECURITY, "Votre compte ne permet pas cette action."),
        )
    if not user.phone_verified:
        raise _Refusal('phone_unverified', OrganizationError(
            "Vérifiez votre numéro de téléphone avant de rejoindre une organisation.",
            'phone_verification_required', status.HTTP_403_FORBIDDEN,
        ))
    try:
        _ensure_under_limit(user.pk)
    except OrganizationError as error:
        raise _Refusal('limit', error)
    inviter = User.objects.get(pk=invitation.created_by_id)
    try:
        membership = _activate_membership(
            user, organization, user, invitation.role, added_by=inviter, via='invitation',
            invited_by=invitation.created_by_id, scope=membership_scope(invitation),
        )
    except OrganizationError as error:
        raise _Refusal('already_member', error)
    _audit_invitation(
        user, 'INVITATION_ACCEPTED', organization, invitation, invited_by=invitation.created_by_id,
    )
    _publish_invitation_change(organization, invitation, CHANGE_ACCEPTED, user)
    membership.organization = organization
    return membership


def accept_invitation(user, token) -> Membership:
    """Accepte l'invitation : crée (ou réactive) l'appartenance `ACTIVE` au rôle invité. Jamais de changement de
    rôle d'un membre existant (409 `already_member`, l'invitation reste `PENDING`). Voir `_accept_locked` pour
    l'ordre des contrôles. Les refus identifiés sont journalisés hors transaction (`INVITATION_REFUSED`)."""
    invitation = _find_invitation(user, token)
    try:
        with transaction.atomic():
            membership = _accept_locked(user, invitation)
    except _Refusal as refusal:
        record_audit(
            user, 'INVITATION_REFUSED', target=invitation, details=(
                f"organization={invitation.organization_id}; reason={refusal.reason}"
            ), context=(CONTEXT_ORGANIZATION, invitation.organization_id),
        )
        raise refusal.error
    INVITATION_FAILURES.success(_failure_key(user))
    return membership


def decline_invitation(user, token):
    """Refuse l'invitation (toujours possible tant qu'elle est vivante) : aucun contrôle de plafond, de téléphone
    ni d'autorité. Mise à jour conditionnelle `PENDING -> DECLINED` ; sinon 404 uniforme."""
    invitation = _find_invitation(user, token)
    with transaction.atomic():
        try:
            organization = _lock_organization(invitation.organization_id)
        except ContextDenied:
            organization = None
        now = timezone.now()
        # Organisation non active : invitation « non prise » (contrat §2.7), ni écriture, ni audit, ni événement.
        done = organization is not None and organization.status == Organization.STATUS_ACTIVE and OrganizationInvitation.objects.filter(
            pk=invitation.pk, status=OrganizationInvitation.STATUS_PENDING, expires_at__gt=now,
        ).update(
            status=OrganizationInvitation.STATUS_DECLINED, closed_at=now, closed_by=user, label='', updated_at=now,
        )
        if done:
            _audit_invitation(user, 'INVITATION_DECLINED', organization, invitation)
            _publish_invitation_change(organization, invitation, CHANGE_DECLINED, user)
    if not done:
        raise invitation_invalid_error()
    INVITATION_FAILURES.success(_failure_key(user))
