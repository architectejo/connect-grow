"""Invitations d'équipe par lien à usage unique (L1-01c et d ; ADR 0008 §3 à §7, §11 ; contrat d'API §2), version 2
(L1-01-B7 ; ADR 0010 D4, §5.1, §6.2 ; contrat d'API §7.4).

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
  inconnu n'est jamais journalisé ;
- invitations v2 : rôles `ADMIN`, `EDITOR`, `ANALYST`, `MEMBER`, chacun seulement si l'émetteur peut le déléguer
  (`can_delegate`, rôle ET périmètre) ; jamais `OWNER`. Une invitation `ADMIN` acceptée passe en
  `AWAITING_CONFIRMATION` SANS appartenance (donc sans aucun droit) jusqu'à la confirmation, avec ressaisie du mot de
  passe, par l'émetteur s'il peut toujours déléguer ce rôle ou par un administrateur principal effectif (parade au
  lien porteur, décision U2). Le confirmateur voit le nom abrégé et les deux derniers chiffres du téléphone vérifié
  de la personne (`phone_hint`), annoncés à celle-ci avant qu'elle accepte, ET ressaisit le code de rattachement à
  six chiffres que seule cette personne a reçu (décision S3, ADR 0010 QG-2) ; ces données ne vont jamais dans
  l'audit, l'outbox, les notifications ni les journaux.

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
import hashlib
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.db.models import F, Q
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils import timezone
from rest_framework import serializers, status

from apps.common.contexts import CONTEXT_ORGANIZATION, DENY_PERMISSION, DENY_SECURITY, ContextDenied
from apps.common.utils import parse_uuid
from apps.moderation import services as moderation_services
from apps.moderation.services import record_audit

from . import capabilities
from .models import (
    CONFIRMATION_REQUIRED_ROLES, INVITABLE_ROLES, Membership, Organization, OrganizationInvitation, User,
)
from .organizations import (
    ACCOUNT_REVIEW_HARD_LIMIT, INVITATION_CHANGE_REJECTED, OrganizationError, _activate_membership, _audit_invitation,
    _authorize_member, _effective_owner_ids, _ensure_under_hard_limit, _get_organization, _lock_organization,
    _require_reauthentication, is_under_creation_review, record_account_review_refusal,
    _unavailable_user_error, _validate_scope, get_identity_settings, membership_scope, publish_invitation_change,
)
from .throttles import FailureLimiter

LABEL_MAX_LENGTH = 60
TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,128}$')

# Types de changement portés par `identity.organization_invitation_changed`.
CHANGE_CREATED = 'created'
CHANGE_ACCEPTED = 'accepted'
CHANGE_DECLINED = 'declined'
CHANGE_REVOKED = 'revoked'
# ADR 0010 §7 : valeurs additives (charge utile enrichie de `accepted_by_id`).
CHANGE_AWAITING_CONFIRMATION = 'awaiting_confirmation'
CHANGE_CONFIRMED = 'confirmed'
CHANGE_REJECTED = INVITATION_CHANGE_REJECTED

# Code de rattachement (décision S3, ADR 0010 QG-2) : six chiffres tirés par `secrets`, empreinte HMAC (clé du
# projet, sel propre, identifiant de l'invitation) seule stockée ; au-delà de 5 codes faux sur une invitation, elle
# est rejetée. Seuil de sécurité (comme les limiteurs d'échecs), pas une règle de marché.
CONFIRMATION_CODE_LENGTH = 6
CONFIRMATION_CODE_MAX_FAILURES = 5
_CODE_SALT = 'identity.organization_invitation.confirmation_code'
REJECT_REASON_CODE_FAILED = 'code_failed'

# Ressaisie du mot de passe (ADR 0010 §8, action de `ORG_SENSITIVE_REAUTH_FAILED`).
REAUTH_CONFIRM_ADMIN_INVITATION = 'confirm_admin_invitation'
# Fondement de l'autorité du confirmateur, tracé dans `INVITATION_CONFIRMED`.
CONFIRMER_BASIS_INVITER = 'inviter'
CONFIRMER_BASIS_PRIMARY_ADMIN = 'primary_admin'
# Fenêtre d'information de « mes adhésions en attente » sur les demandes expirées (contrat §7.4.7 : 7 jours).
AWAITING_EXPIRED_VISIBLE_DAYS = 7

# Compteur d'échecs de l'échange (aperçu, acceptation, refus), PAR COMPTE : la clé ne contient jamais le jeton.
INVITATION_FAILURES = FailureLimiter('invitation_redeem', threshold=5)

LIST_STATUSES = tuple(value for value, _ in OrganizationInvitation.STATUS_CHOICES)


def invitation_invalid_error():
    """Réponse UNIQUE de toute invitation inutilisable : même statut, même message, même code."""
    return OrganizationError(
        "Cette invitation n'est pas valide.", 'invitation_invalid', status.HTTP_404_NOT_FOUND,
    )


def hash_token(token) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _not_awaiting_error():
    return OrganizationError(
        "Cette demande n'est plus en attente de confirmation.", 'invitation_not_awaiting_confirmation',
    )


def _not_found_error():
    return OrganizationError("Cette invitation est introuvable.", 'invitation_not_found', status.HTTP_404_NOT_FOUND)


def requires_confirmation(role) -> bool:
    """Le rôle attend-il la confirmation de l'émetteur ou d'un administrateur principal (ADR 0010 D4) ?"""
    return role in CONFIRMATION_REQUIRED_ROLES


def effective_status(invitation, now=None) -> str:
    """Statut présenté : une `PENDING` échue (pas encore balayée par le cron) est `EXPIRED`, de même qu'une
    `AWAITING_CONFIRMATION` dont l'échéance de confirmation est passée (contrat §7.4)."""
    now = now or timezone.now()
    if invitation.status == OrganizationInvitation.STATUS_PENDING and invitation.expires_at <= now:
        return OrganizationInvitation.STATUS_EXPIRED
    if invitation.status == OrganizationInvitation.STATUS_AWAITING_CONFIRMATION and (
        invitation.confirmation_expires_at is None or invitation.confirmation_expires_at <= now
    ):
        return OrganizationInvitation.STATUS_EXPIRED
    return invitation.status


def _live_awaiting_q(now):
    """Filtre des invitations en attente de confirmation NON échues."""
    return Q(status=OrganizationInvitation.STATUS_AWAITING_CONFIRMATION, confirmation_expires_at__gt=now)


def phone_hint(user) -> Optional[str]:
    """Indice de téléphone (ADR 0010 §6.2, règle 10) : « •• » suivi des deux derniers chiffres du téléphone de
    connexion VÉRIFIÉ ; `None` sinon. Servi SEULEMENT dans la liste des invitations en attente de confirmation, à qui
    peut confirmer CETTE invitation ; jamais dans l'audit, l'outbox, une notification ni un journal.

    L'indice est RELU EN DIRECT sur le compte au moment de la liste (jamais figé à l'acceptation) : si la personne
    change de numéro entre-temps, le confirmateur voit le nouveau. Ce n'est qu'un indice d'identification ; la preuve
    que la personne entrée est bien celle avec qui le confirmateur communique est le code de rattachement
    (décision S3), qu'elle seule a reçu."""
    if user is None or not user.phone_verified:
        return None
    digits = [ch for ch in (user.phone or '') if ch.isdigit()]
    if len(digits) < 2:
        return None
    return '••' + ''.join(digits[-2:])


# Émission partagée avec `organizations` (rejets automatiques) : UUID et codes seulement.
_publish_invitation_change = publish_invitation_change


def _new_confirmation_code() -> str:
    return f"{secrets.randbelow(10 ** CONFIRMATION_CODE_LENGTH):0{CONFIRMATION_CODE_LENGTH}d}"


def _code_hash(invitation_id, code) -> str:
    """Empreinte HMAC-SHA256 du code, liée à l'invitation : sans la clé du projet, la table ne permet pas de
    retrouver un code par essais hors ligne (un million de valeurs seulement)."""
    return salted_hmac(_CODE_SALT, f"{invitation_id}:{code}", algorithm='sha256').hexdigest()


_CODE_PATTERN = re.compile(r'^[0-9]{%d}\Z' % CONFIRMATION_CODE_LENGTH)


def _code_is_missing(code) -> bool:
    """Code absent : `None`, chaîne vide ou blanche. Toute autre valeur (nombre, chaîne mal formée) est un ESSAI,
    jugé par `_code_matches` (décision de la relecture : un code mal formé compte comme un code faux)."""
    return code is None or (isinstance(code, str) and not code.strip())


def _code_matches(invitation, code) -> bool:
    """Exactement six chiffres, puis comparaison à temps constant ; une invitation sans empreinte (antérieure au code)
    ne se confirme pas."""
    if not invitation.confirmation_code_hash or not isinstance(code, str) or not _CODE_PATTERN.match(code):
        return False
    return constant_time_compare(_code_hash(invitation.pk, code), invitation.confirmation_code_hash)


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

def create_invitation(actor, organization_id, role, label='', scope=None, after_authorization=None):
    """Crée une invitation `PENDING` et renvoie `(invitation, jeton)`. Le jeton clair n'existe qu'ici.
    `org.manage_members` ; rôle parmi `INVITABLE_ROLES` (`ADMIN`, `EDITOR`, `ANALYST`, `MEMBER`) ET déléguable par
    l'acteur sur le périmètre visé (`can_delegate`), sinon 400 `invitation_role_not_allowed` (`OWNER` toujours) ;
    `scope` : `None` = organisation entière, seule valeur acceptée en V1 (sinon 400 `{"scope": [...]}`). Pas de
    ressaisie : aucun droit n'est ouvert à ce stade (ADR 0010 §6.2). Plafond d'invitations en attente non échues par
    organisation (réglage), compté sous verrou. L'autorisation précède la validation du corps.
    `after_authorization` : crochet appelé juste après l'autorisation réussie (quota par organisation de la vue :
    un non-membre ne le consomme jamais)."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_members')
        if is_under_creation_review(organization):
            # Organisation retenue en revue de création (ADR 0010 D8, correction S5) : pas d'invitation tant que le
            # personnel n'a pas levé la revue. Après l'autorisation (un non-membre reçoit DENY_RELATION : aucun
            # oracle ; le membre connaît déjà `governance.under_review`), avant le quota par organisation.
            raise OrganizationError(
                "Cette organisation est en cours d'examen par l'équipe Connecte+ ; les invitations seront possibles "
                "ensuite.",
                'organization_under_review',
            )
        if after_authorization is not None:
            after_authorization()
        if not isinstance(role, str) or role not in capabilities.ROLES:
            raise serializers.ValidationError({'role': ["Rôle inconnu ou manquant."]})
        target_scope = _validate_scope(scope) or capabilities.ORGANIZATION_SCOPE
        if role not in INVITABLE_ROLES or not capabilities.can_delegate(
            actor_membership.role, membership_scope(actor_membership), role, target_scope,
        ):
            raise OrganizationError(
                "Ce rôle ne peut pas être attribué par invitation.", 'invitation_role_not_allowed',
                status.HTTP_400_BAD_REQUEST,
            )
        label = _clean_label(label)
        settings_row = get_identity_settings()
        now = timezone.now()
        # Invitations OUVERTES non échues (décision S3) : en attente d'acceptation ou de confirmation.
        pending = OrganizationInvitation.objects.filter(
            Q(status=OrganizationInvitation.STATUS_PENDING, expires_at__gt=now) | _live_awaiting_q(now),
            organization=organization,
        ).count()
        if pending >= settings_row.max_pending_invitations:
            raise OrganizationError(
                "Le nombre maximal d'invitations en attente est atteint pour cette organisation.",
                'invitation_limit_reached',
            )
        token = secrets.token_urlsafe(32)
        invitation = OrganizationInvitation.objects.create(
            organization=organization, role=role, token_hash=hash_token(token), label=label, created_by=actor,
            scope_type=target_scope.type, scope_id=target_scope.id,
            expires_at=now + timedelta(days=settings_row.invitation_ttl_days),
        )
        _audit_invitation(
            actor, 'INVITATION_CREATED', organization, invitation, ttl_days=settings_row.invitation_ttl_days,
            scope_type=target_scope.type, scope_id=target_scope.id or '-',
        )
        _publish_invitation_change(organization, invitation, CHANGE_CREATED, actor)
    return invitation, token


@dataclass(frozen=True)
class InvitationList:
    """Invitations d'une organisation et ce qu'il faut pour calculer `can_confirm` sans requête par ligne."""

    queryset: object
    actor_id: object
    actor_role: str
    actor_scope: capabilities.Scope
    organization_id: object = None

    def inviter_authority(self, invitations) -> dict:
        """`{invitation_id: bool}` : l'émetteur peut-il toujours déléguer le rôle et le périmètre de l'invitation
        (même règle que `_inviter_has_authority`) ? Calcul PAR LOT pour une page : au plus 3 requêtes, quel que
        soit le nombre de lignes. Sert à l'avertissement du front sur une attente dont l'émetteur a perdu
        l'autorité (un administrateur principal peut encore confirmer)."""
        invitations = list(invitations)
        inviter_ids = {row.created_by_id for row in invitations if row.created_by_id is not None}
        if not inviter_ids:
            return {row.pk: False for row in invitations}
        memberships = {
            user_id: (role, capabilities.Scope.of(scope_type, scope_id))
            for user_id, role, scope_type, scope_id in Membership.objects.filter(
                organization_id=self.organization_id, user_id__in=inviter_ids, status=Membership.STATUS_ACTIVE,
            ).values_list('user_id', 'role', 'scope_type', 'scope_id')
        }
        usable = set()
        if memberships:
            usable = set(
                User.objects.filter(pk__in=list(memberships), is_active=True).values_list('pk', flat=True)
            ) - moderation_services.get_restricted_user_ids(set(memberships))
        result = {}
        for row in invitations:
            held = memberships.get(row.created_by_id)
            result[row.pk] = bool(
                held is not None and row.created_by_id in usable
                and capabilities.role_has_capability(held[0], 'org.manage_members')
                and capabilities.scope_allows(held[1], 'org.manage_members')
                and capabilities.can_delegate(held[0], held[1], row.role, membership_scope(row))
            )
        return result

    def can_confirm(self, invitation, now=None) -> bool:
        """Contrat §7.4 : l'invitation est `AWAITING_CONFIRMATION` non échue ET l'appelant est l'émetteur qui peut
        toujours déléguer ce rôle sur ce périmètre, ou un administrateur principal (effectif : l'appelant a passé la
        garde de compte de `_authorize_member`)."""
        if effective_status(invitation, now) != OrganizationInvitation.STATUS_AWAITING_CONFIRMATION:
            return False
        return _confirmer_basis(self.actor_id, self.actor_role, self.actor_scope, invitation) is not None


def _confirmer_basis(actor_id, actor_role, actor_scope, invitation) -> Optional[str]:
    """Fondement de l'autorité de confirmer (ou rejeter) une invitation en attente, pour un acteur DÉJÀ autorisé
    `org.manage_members` sur l'organisation (membre actif, compte actif et non restreint, périmètre organisation) :
    `inviter` si c'est l'émetteur et qu'il peut toujours déléguer le rôle et le périmètre de l'invitation ; sinon
    `primary_admin` s'il est administrateur principal ; sinon `None`. Pur (aucune requête)."""
    if invitation.created_by_id is not None and invitation.created_by_id == actor_id and capabilities.can_delegate(
        actor_role, actor_scope, invitation.role, membership_scope(invitation),
    ):
        return CONFIRMER_BASIS_INVITER
    if actor_role == capabilities.ROLE_OWNER and actor_scope == capabilities.ORGANIZATION_SCOPE:
        return CONFIRMER_BASIS_PRIMARY_ADMIN
    return None


def list_invitations(actor, organization_id, status_filter=None) -> InvitationList:
    """Invitations de l'organisation (`org.manage_members`), du plus récent au plus ancien, filtrées par statut
    EFFECTIF (défaut `PENDING` ; une `PENDING` ou une `AWAITING_CONFIRMATION` échue compte comme `EXPIRED`). Ni jeton
    ni empreinte ne sont lus. Les comptes de l'émetteur et de la personne qui a accepté sont joints (nom ; téléphone
    pour l'indice, servi seulement à qui peut confirmer) : nombre de requêtes indépendant de la page."""
    organization = _get_organization(organization_id)
    actor_membership = _authorize_member(actor, organization, 'org.manage_members')
    status_filter = status_filter or OrganizationInvitation.STATUS_PENDING
    if status_filter not in LIST_STATUSES:
        raise serializers.ValidationError({'status': ["Statut inconnu."]})
    now = timezone.now()
    rows = OrganizationInvitation.objects.filter(organization=organization)
    pending, expired = OrganizationInvitation.STATUS_PENDING, OrganizationInvitation.STATUS_EXPIRED
    awaiting = OrganizationInvitation.STATUS_AWAITING_CONFIRMATION
    if status_filter == pending:
        rows = rows.filter(status=pending, expires_at__gt=now)
    elif status_filter == awaiting:
        rows = rows.filter(_live_awaiting_q(now))
    elif status_filter == expired:
        rows = rows.filter(
            Q(status=expired) | Q(status=pending, expires_at__lte=now)
            | (Q(status=awaiting) & (Q(confirmation_expires_at__lte=now) | Q(confirmation_expires_at__isnull=True)))
        )
    else:
        rows = rows.filter(status=status_filter)
    queryset = rows.select_related('created_by', 'accepted_by').only(
        'id', 'organization', 'role', 'scope_type', 'scope_id', 'status', 'label', 'created_at', 'expires_at',
        'created_by', 'accepted_by', 'accepted_at', 'confirmation_expires_at', 'created_by__full_name',
        'accepted_by__full_name', 'accepted_by__phone', 'accepted_by__phone_verified',
    ).order_by('-created_at', '-id')
    return InvitationList(
        queryset, actor.pk, actor_membership.role, membership_scope(actor_membership), organization.pk,
    )


def revoke_invitation(actor, organization_id, invitation_id):
    """Révoque une invitation (`org.manage_members`, tout membre habilité peut révoquer toute invitation de
    l'organisation). Mise à jour conditionnelle `PENDING -> REVOKED` : inexistante ou d'une autre organisation, 404
    `invitation_not_found` ; déjà close, échue ou en attente de confirmation (celle-ci se REJETTE :
    `reject_invitation`), 409 `invitation_not_pending`."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        _authorize_member(actor, organization, 'org.manage_members')
        invitation = OrganizationInvitation.objects.filter(pk=invitation_id, organization=organization).first()
        if invitation is None:
            raise _not_found_error()
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
    ceux propres à la cible. Toute invalidité : 404 `invitation_invalid`. Aperçu enrichi (ADR 0010 D4, contrat §7.4.4) :
    périmètre, capacités du rôle proposé (liste triée, celles que le périmètre permet d'exercer) et
    `requires_confirmation` (le front annonce alors ce que verra le confirmateur : nom abrégé et deux derniers chiffres
    du téléphone)."""
    from .services import public_display_name  # import tardif : `services` importe ce module

    invitation = _find_invitation(user, token)
    now = timezone.now()
    organization = Organization.objects.filter(pk=invitation.organization_id).first()
    if (
        invitation.status != OrganizationInvitation.STATUS_PENDING or invitation.expires_at <= now
        or organization is None or organization.status != Organization.STATUS_ACTIVE
        or is_under_creation_review(organization)
        or invitation.role not in INVITABLE_ROLES or not _inviter_has_authority(invitation, organization)
    ):
        raise invitation_invalid_error()
    inviter = User.objects.filter(pk=invitation.created_by_id).only('full_name').first()
    scope = membership_scope(invitation)
    return {
        'organization_name': organization.name, 'org_type': organization.org_type, 'role': invitation.role,
        'expires_at': invitation.expires_at, 'invited_by_display_name': public_display_name(inviter.full_name),
        'scope': scope,
        'capabilities': [
            name for name in capabilities.capabilities_for_role(invitation.role)
            if capabilities.scope_allows(scope, name)
        ],
        'requires_confirmation': requires_confirmation(invitation.role),
    }


# Résultat d'une acceptation (contrat §7.4.5) : appartenance active, ou attente de confirmation sans appartenance.
ACCEPTANCE_ACTIVE = 'ACTIVE'
ACCEPTANCE_AWAITING_CONFIRMATION = OrganizationInvitation.STATUS_AWAITING_CONFIRMATION


@dataclass(frozen=True)
class InvitationAcceptance:
    """`status` = `ACTIVE` (appartenance créée ou réactivée : `membership`) ou `AWAITING_CONFIRMATION` (aucune
    appartenance : `invitation`, `confirmation_expires_at`)."""

    status: str
    organization: Organization
    role: str
    membership: Optional[Membership] = None
    invitation: Optional[OrganizationInvitation] = None
    confirmation_expires_at: Optional[object] = None
    # Code de rattachement en clair : renvoyé UNE fois, à la seule personne qui a accepté (réponse 202).
    confirmation_code: Optional[str] = None


def _already_member_error():
    return OrganizationError("Ce compte est déjà membre de l'organisation.", 'already_member')


def _already_awaiting_error():
    return OrganizationError(
        "Vous attendez déjà la confirmation d'une demande pour rejoindre cette organisation.",
        'already_awaiting_confirmation',
    )


def _accept_locked(user, invitation) -> InvitationAcceptance:
    """Corps transactionnel de l'acceptation, dans l'ordre exact de l'ADR 0008 §5.1 (3), amendé par l'ADR 0010 §6.2.
    Toute levée de `_Refusal` annule la transaction, donc la prise de l'invitation : elle reste `PENDING`.

    Rôle sans confirmation : `PENDING -> ACCEPTED` et appartenance active. Rôle `ADMIN` : `PENDING ->
    AWAITING_CONFIRMATION` (personne, date, échéance de confirmation) et AUCUNE appartenance, donc aucun droit."""
    try:
        organization = _lock_organization(invitation.organization_id)
    except ContextDenied:
        raise _Refusal('org_inactive', invitation_invalid_error())
    now = timezone.now()
    awaiting = requires_confirmation(invitation.role)
    confirmation_expires_at = code = None
    if awaiting:
        hours = get_identity_settings().admin_invitation_confirmation_hours
        confirmation_expires_at = now + timedelta(hours=hours)
        code = _new_confirmation_code()
        changes = {
            'status': OrganizationInvitation.STATUS_AWAITING_CONFIRMATION, 'accepted_by': user, 'accepted_at': now,
            'confirmation_expires_at': confirmation_expires_at,
            'confirmation_code_hash': _code_hash(invitation.pk, code), 'confirmation_code_failures': 0,
        }
    else:
        changes = {'status': OrganizationInvitation.STATUS_ACCEPTED, 'closed_at': now, 'closed_by': user}
    taken = OrganizationInvitation.objects.filter(
        pk=invitation.pk, status=OrganizationInvitation.STATUS_PENDING, expires_at__gt=now,
    ).update(label='', updated_at=now, **changes)
    if not taken:
        raise _Refusal(_dead_reason(invitation.pk, now), invitation_invalid_error())
    if organization.status != Organization.STATUS_ACTIVE:
        raise _Refusal('org_inactive', invitation_invalid_error())
    if is_under_creation_review(organization):  # invitation antérieure à la mise en revue : non prise (S5)
        raise _Refusal('org_under_review', invitation_invalid_error())
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
        _ensure_under_hard_limit(user.pk)
    except OrganizationError as error:
        raise _Refusal(ACCOUNT_REVIEW_HARD_LIMIT, error)
    if Membership.objects.filter(organization=organization, user=user, status=Membership.STATUS_ACTIVE).exists():
        raise _Refusal('already_member', _already_member_error())
    # Une seule attente de confirmation par personne et par organisation (ADR 0010 §6.2), garantie sous le verrou de
    # l'organisation (aucune unicité conditionnelle en base). Vaut aussi pour un rôle sans confirmation : la personne
    # attend déjà une décision de l'organisation.
    if OrganizationInvitation.objects.filter(
        _live_awaiting_q(now), organization=organization, accepted_by=user,
    ).exclude(pk=invitation.pk).exists():
        raise _Refusal('already_awaiting', _already_awaiting_error())

    if awaiting:
        _audit_invitation(
            user, 'INVITATION_ACCEPTED_AWAITING_CONFIRMATION', organization, invitation,
            invited_by=invitation.created_by_id,
        )
        _publish_invitation_change(
            organization, invitation, CHANGE_AWAITING_CONFIRMATION, user, accepted_by_id=user.pk,
        )
        return InvitationAcceptance(
            ACCEPTANCE_AWAITING_CONFIRMATION, organization, invitation.role, invitation=invitation,
            confirmation_expires_at=confirmation_expires_at, confirmation_code=code,
        )

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
    return InvitationAcceptance(ACCEPTANCE_ACTIVE, organization, membership.role, membership=membership)


def accept_invitation(user, token) -> InvitationAcceptance:
    """Accepte l'invitation. Rôle sans confirmation : crée (ou réactive) l'appartenance `ACTIVE` au rôle invité.
    Rôle `ADMIN` : l'invitation passe en attente de confirmation, sans appartenance (contrat §7.4.5, réponse 202).
    Jamais de changement de rôle d'un membre existant (409 `already_member`, l'invitation reste `PENDING`). Voir
    `_accept_locked` pour l'ordre des contrôles. Les refus identifiés sont journalisés hors transaction
    (`INVITATION_REFUSED`)."""
    invitation = _find_invitation(user, token)
    try:
        with transaction.atomic():
            result = _accept_locked(user, invitation)
    except _Refusal as refusal:
        record_audit(
            user, 'INVITATION_REFUSED', target=invitation, details=(
                f"organization={invitation.organization_id}; reason={refusal.reason}"
            ), context=(CONTEXT_ORGANIZATION, invitation.organization_id),
        )
        if refusal.reason == ACCOUNT_REVIEW_HARD_LIMIT:
            record_account_review_refusal(user, ACCOUNT_REVIEW_HARD_LIMIT)  # file du personnel (S5)
        raise refusal.error
    INVITATION_FAILURES.success(_failure_key(user))
    return result


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


# --- Confirmation d'une invitation Administrateur (ADR 0010 D4, §5.1, §6.2 ; contrat §7.4.6) ---------------------

def _resolve_awaiting(actor, organization, invitation_id, now):
    """Acteur autorisé et invitation à confirmer ou rejeter, dans l'ordre du contrat (section 0) : non-membre, état de
    l'organisation, état du compte, capacité `org.manage_members` (`DENY_*`) ; invitation de CETTE organisation
    (404 `invitation_not_found`, aussi pour un identifiant d'une autre organisation : IDOR) ; autorité de confirmer
    (`DENY_PERMISSION` : ni l'émetteur qui peut toujours déléguer ce rôle, ni un administrateur principal) ; état
    (409 `invitation_not_awaiting_confirmation` : autre statut ou échéance passée).
    Renvoie `(invitation, fondement)`."""
    actor_membership = _authorize_member(actor, organization, 'org.manage_members')
    parsed = parse_uuid(invitation_id)
    invitation = (
        OrganizationInvitation.objects.filter(pk=parsed, organization=organization).first()
        if parsed is not None else None
    )
    if invitation is None:
        raise _not_found_error()
    basis = _confirmer_basis(actor.pk, actor_membership.role, membership_scope(actor_membership), invitation)
    if basis is None:
        raise ContextDenied(DENY_PERMISSION, "Vous ne pouvez pas confirmer ni rejeter cette demande.")
    if effective_status(invitation, now) != OrganizationInvitation.STATUS_AWAITING_CONFIRMATION:
        raise _not_awaiting_error()
    return invitation, basis


def _eligible_accepted_person(organization, invitation) -> User:
    """La personne qui a accepté, revérifiée au moment de confirmer (ADR 0010 §6.2) : compte existant, actif, non
    restreint, téléphone vérifié, sous le plafond d'appartenances (compte verrouillé), sinon 400 `user_unavailable`
    (réponse NEUTRE : elle ne dit pas laquelle de ces conditions manque) ; pas déjà membre actif, sinon 409
    `already_member`. Appelée APRÈS la prise conditionnelle de l'invitation (ordre de verrouillage : organisation,
    invitation, appartenances, comptes) : une levée annule la transaction, l'invitation reste en attente."""
    target_id = invitation.accepted_by_id
    target = User.objects.filter(pk=target_id, is_active=True).first() if target_id is not None else None
    if target is None or moderation_services.is_user_restricted(target_id) or not target.phone_verified:
        raise _unavailable_user_error()
    try:
        _ensure_under_hard_limit(target_id)
    except OrganizationError:
        raise _unavailable_user_error()
    if Membership.objects.filter(
        organization=organization, user_id=target_id, status=Membership.STATUS_ACTIVE,
    ).exists():
        raise _already_member_error()
    return target


def _code_required_error():
    return OrganizationError(
        "Saisissez le code de confirmation communiqué par la personne.", 'confirmation_code_required',
        status.HTTP_400_BAD_REQUEST,
    )


def _code_invalid_error():
    return OrganizationError(
        "Le code de confirmation est incorrect.", 'confirmation_code_invalid', status.HTTP_400_BAD_REQUEST,
    )


def _code_exhausted_error():
    return OrganizationError(
        "Trop de codes incorrects : la demande a été rejetée. Une nouvelle invitation est nécessaire.",
        'confirmation_code_exhausted',
    )


def _record_code_failure(actor, organization, invitation, now) -> bool:
    """Code faux (sous verrou) : compteur incrémenté par mise à jour conditionnelle ; trace
    `INVITATION_CONFIRMATION_CODE_FAILED` (jamais le code). Au seuil, l'invitation est REJETÉE (`reason=code_failed`,
    événement `rejected` : la personne est prévenue sans nom). Renvoie vrai si l'invitation vient d'être rejetée."""
    OrganizationInvitation.objects.filter(_live_awaiting_q(now), pk=invitation.pk).update(
        confirmation_code_failures=F('confirmation_code_failures') + 1, updated_at=now,
    )
    failures = OrganizationInvitation.objects.filter(pk=invitation.pk).values_list(
        'confirmation_code_failures', flat=True,
    ).first() or 0
    _audit_invitation(actor, 'INVITATION_CONFIRMATION_CODE_FAILED', organization, invitation, failures=failures)
    if failures < CONFIRMATION_CODE_MAX_FAILURES:
        return False
    done = OrganizationInvitation.objects.filter(_live_awaiting_q(now), pk=invitation.pk).update(
        status=OrganizationInvitation.STATUS_REJECTED, confirmed_by=actor, closed_at=now, closed_by=actor,
        confirmation_code_hash='', updated_at=now,
    )
    if done:
        _audit_invitation(
            actor, 'INVITATION_REJECTED', organization, invitation, accepted_by=invitation.accepted_by_id,
            reason=REJECT_REASON_CODE_FAILED,
        )
        _publish_invitation_change(
            organization, invitation, CHANGE_REJECTED, actor, accepted_by_id=invitation.accepted_by_id,
        )
    return True


def confirm_invitation(
    actor, organization_id, invitation_id, confirm=False, password=None, code=None,
) -> Membership:
    """Confirme une invitation `AWAITING_CONFIRMATION` : l'appartenance active est créée (ou réactivée) au rôle et au
    périmètre de l'invitation. Acteur : l'émetteur s'il peut toujours déléguer ce rôle, ou un administrateur principal
    effectif ; ressaisie du mot de passe (`confirm` vrai et `password`) AVANT le verrou, même limiteur d'échecs que
    les autres opérations sensibles (`org_reauth`, atomique). Sous verrou, TOUT est revérifié (organisation active,
    autorité du confirmateur, état et échéance de l'invitation, éligibilité de la personne). Mise à jour
    conditionnelle `AWAITING_CONFIRMATION -> ACCEPTED` : une seule confirmation (ou un seul rejet, ou un seul retrait)
    gagne. Audit `INVITATION_CONFIRMED` (confirmateur) et `MEMBERSHIP_ADDED` ; événements `confirmed` et
    `membership_changed` (`actor_id` = émetteur, `via = invitation`, `confirmed`). Renvoie l'appartenance, compte
    chargé.

    Code de rattachement (décision S3) : `code` obligatoire (400 `confirmation_code_required` s'il manque, avant la
    ressaisie), comparé à temps constant APRÈS la ressaisie et sous verrou. Faux ou mal formé (pas exactement six
    chiffres) : 400 `confirmation_code_invalid`,
    compteur de l'invitation incrémenté (la trace et le compteur sont conservés : l'erreur est levée après la
    transaction) ; au 5e code faux, l'invitation est rejetée et la réponse est 409 `confirmation_code_exhausted`."""
    organization = _get_organization(organization_id)
    _resolve_awaiting(actor, organization, invitation_id, timezone.now())
    if _code_is_missing(code):
        raise _code_required_error()
    _require_reauthentication(actor, organization, confirm, password, REAUTH_CONFIRM_ADMIN_INVITATION)
    code_error = None
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        now = timezone.now()
        invitation, basis = _resolve_awaiting(actor, organization, invitation_id, now)
        if not _code_matches(invitation, code):
            # Le compteur et la trace doivent survivre au refus : l'erreur est levée APRÈS la transaction.
            exhausted = _record_code_failure(actor, organization, invitation, now)
            code_error = _code_exhausted_error() if exhausted else _code_invalid_error()
        else:
            membership, target = _confirm_locked(actor, organization, invitation, basis, now)
    if code_error is not None:
        raise code_error
    membership.user = target
    return membership


def _confirm_locked(actor, organization, invitation, basis, now):
    """Corps de la confirmation, code vérifié, sous verrou : prise conditionnelle, éligibilité de la personne,
    appartenance, audit, événement. Renvoie `(appartenance, compte entré)`."""
    done = OrganizationInvitation.objects.filter(_live_awaiting_q(now), pk=invitation.pk).update(
        status=OrganizationInvitation.STATUS_ACCEPTED, confirmed_by=actor, closed_at=now, closed_by=actor,
        confirmation_code_hash='', updated_at=now,
    )
    if not done:
        raise _not_awaiting_error()
    target = _eligible_accepted_person(organization, invitation)
    inviter = User.objects.filter(pk=invitation.created_by_id).first() if invitation.created_by_id else None
    membership = _activate_membership(
        actor, organization, target, invitation.role, added_by=inviter or actor, via='invitation',
        invited_by=invitation.created_by_id, scope=membership_scope(invitation), confirmed=True,
    )
    _audit_invitation(
        actor, 'INVITATION_CONFIRMED', organization, invitation, accepted_by=target.pk,
        invited_by=invitation.created_by_id, confirmer_basis=basis, reauth='true',
    )
    _publish_invitation_change(organization, invitation, CHANGE_CONFIRMED, actor, accepted_by_id=target.pk)
    return membership, target


def reject_invitation(actor, organization_id, invitation_id):
    """Rejette une invitation `AWAITING_CONFIRMATION` (mêmes acteurs que la confirmation, sans ressaisie : rejeter
    n'ouvre aucun droit). `AWAITING_CONFIRMATION -> REJECTED`, conditionnel ; audit `INVITATION_REJECTED` ; événement
    `rejected` (la personne est prévenue sans le nom du confirmateur)."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        now = timezone.now()
        invitation, _ = _resolve_awaiting(actor, organization, invitation_id, now)
        done = OrganizationInvitation.objects.filter(_live_awaiting_q(now), pk=invitation.pk).update(
            status=OrganizationInvitation.STATUS_REJECTED, confirmed_by=actor, closed_at=now, closed_by=actor,
            confirmation_code_hash='', updated_at=now,
        )
        if not done:
            raise _not_awaiting_error()
        _audit_invitation(actor, 'INVITATION_REJECTED', organization, invitation, accepted_by=invitation.accepted_by_id)
        _publish_invitation_change(
            organization, invitation, CHANGE_REJECTED, actor, accepted_by_id=invitation.accepted_by_id,
        )


# --- Côté personne qui a accepté (contrat §7.4.7) ------------------------------------------------------------------

def list_my_awaiting_invitations(user):
    """Invitations acceptées par `user` et en attente de confirmation, plus celles échues depuis moins de
    `AWAITING_EXPIRED_VISIBLE_DAYS` jours (pour information), de la plus récente à la plus ancienne. Statut à
    présenter par `effective_status` (`AWAITING_CONFIRMATION` ou `EXPIRED`). Organisation jointe : une requête."""
    now = timezone.now()
    return OrganizationInvitation.objects.filter(
        accepted_by_id=user.pk,
        status__in=(OrganizationInvitation.STATUS_AWAITING_CONFIRMATION, OrganizationInvitation.STATUS_EXPIRED),
        confirmation_expires_at__gt=now - timedelta(days=AWAITING_EXPIRED_VISIBLE_DAYS),
    ).select_related('organization').only(
        'id', 'organization', 'role', 'scope_type', 'scope_id', 'status', 'accepted_at', 'confirmation_expires_at',
        'organization__name', 'organization__org_type',
    ).order_by('-accepted_at', '-id')


def withdraw_awaiting_invitation(user, invitation_id):
    """La personne qui a accepté retire sa demande : `AWAITING_CONFIRMATION -> DECLINED` (conditionnel). Toute autre
    invitation, y compris celle d'autrui : 404 `invitation_not_found` (réponse identique) ; plus en attente ou échue :
    409 `invitation_not_awaiting_confirmation`. Permis quel que soit l'état de l'organisation (c'est un retrait).
    Audit `INVITATION_WITHDRAWN` ; événement `declined`."""
    parsed = parse_uuid(invitation_id)
    invitation = (
        OrganizationInvitation.objects.filter(pk=parsed, accepted_by_id=user.pk).first() if parsed is not None else None
    )
    if invitation is None:
        raise _not_found_error()
    with transaction.atomic():
        try:
            organization = _lock_organization(invitation.organization_id)
        except ContextDenied:
            raise _not_found_error()
        now = timezone.now()
        done = OrganizationInvitation.objects.filter(
            _live_awaiting_q(now), pk=invitation.pk, accepted_by_id=user.pk,
        ).update(
            status=OrganizationInvitation.STATUS_DECLINED, closed_at=now, closed_by=user, confirmation_code_hash='',
            updated_at=now,
        )
        if not done:
            raise _not_awaiting_error()
        _audit_invitation(user, 'INVITATION_WITHDRAWN', organization, invitation)
        _publish_invitation_change(organization, invitation, CHANGE_DECLINED, user)


def regenerate_confirmation_code(user, invitation_id):
    """La personne qui a accepté obtient un NOUVEAU code de rattachement (l'ancien cesse de valoir) : code perdu,
    ou montré à un tiers. Même périmètre que le retrait : sa propre attente non échue, sinon 404
    `invitation_not_found` (y compris l'attente d'autrui) ou 409 `invitation_not_awaiting_confirmation`. Le compteur
    de codes faux n'est PAS remis à zéro. Trace `INVITATION_CONFIRMATION_CODE_REGENERATED` (jamais le code), aucun
    événement. Renvoie `(invitation, code en clair)`."""
    parsed = parse_uuid(invitation_id)
    invitation = (
        OrganizationInvitation.objects.filter(pk=parsed, accepted_by_id=user.pk).first() if parsed is not None else None
    )
    if invitation is None:
        raise _not_found_error()
    with transaction.atomic():
        try:
            organization = _lock_organization(invitation.organization_id)
        except ContextDenied:
            raise _not_found_error()
        now = timezone.now()
        code = _new_confirmation_code()
        done = OrganizationInvitation.objects.filter(
            _live_awaiting_q(now), pk=invitation.pk, accepted_by_id=user.pk,
        ).update(confirmation_code_hash=_code_hash(invitation.pk, code), updated_at=now)
        if not done:
            raise _not_awaiting_error()
        _audit_invitation(user, 'INVITATION_CONFIRMATION_CODE_REGENERATED', organization, invitation)
    return invitation, code


# --- Lecture pour les notifications ------------------------------------------------------------------------------

def get_invitation_confirmer_ids(organization_id, invitation_id) -> list:
    """Comptes qui peuvent confirmer cette invitation, relus au moment de l'appel (destinataires des notifications
    `awaiting_confirmation` et `confirmed`, ADR 0010 §7) : l'émetteur s'il en a toujours l'autorité
    (`_inviter_has_authority` : membre actif, capacité, délégation du rôle et du périmètre, compte actif et non
    restreint) et les administrateurs principaux effectifs. Ne lit pas le statut. Identifiants seulement, triés."""
    organization_id, invitation_id = parse_uuid(organization_id), parse_uuid(invitation_id)
    if organization_id is None or invitation_id is None:
        return []
    invitation = OrganizationInvitation.objects.filter(pk=invitation_id, organization_id=organization_id).only(
        'id', 'organization', 'role', 'scope_type', 'scope_id', 'created_by',
    ).first()
    if invitation is None:
        return []
    recipients = set(_effective_owner_ids(organization_id))
    organization = Organization(pk=organization_id)
    if invitation.created_by_id is not None and _inviter_has_authority(invitation, organization):
        recipients.add(invitation.created_by_id)
    return sorted(recipients, key=str)
