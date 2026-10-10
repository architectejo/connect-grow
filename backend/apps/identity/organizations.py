"""Organisations et équipes : cycle de vie, appartenances, invariants (ADR 0006, sections 5 et 7).

Aucun service de ce module ne reçoit de plan, de prix ni d'entitlement (règle 2) : les quotas de L1-11
s'ajouteront AVANT l'appel, jamais ici. Toute écriture d'équipe se fait dans `transaction.atomic()`,
sous verrou de ligne sur l'organisation (`select_for_update`, effectif sous MySQL ; SQLite sérialise
déjà les écrivains), avec son `AuditLog` synchrone (contexte = l'organisation) et son événement outbox
dans la même transaction. Les `details` d'audit et les charges utiles d'événements ne contiennent que
des UUID et des codes : jamais de nom, d'e-mail ni de téléphone.

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
import re
import unicodedata

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files import File
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import ErrorDetail

from apps.common.contexts import (
    CONTEXT_ORGANIZATION, DENY_OBJECT_STATE, DENY_PERMISSION, DENY_RELATION, DENY_SECURITY, ContextDenied,
)
from apps.common.exception_handler import CodedAPIException
from apps.common.images import validate_image_pixels, validate_image_upload_size
from apps.common.utils import parse_uuid
from apps.moderation.services import is_user_restricted, record_audit
from apps.platform_core.services import publish_event

from . import capabilities
from .capabilities import ROLE_OWNER, ROLES
from .models import (
    IdentitySettings, Membership, Organization, OrganizationCategory, ORG_TYPES, User,
)

# Motifs de suspension normalisés (jamais de texte libre, ADR 0006 §4.2).
SUSPENSION_REASONS = ('moderation', 'verification', 'legal', 'other')

NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 255
DESCRIPTION_MAX_LENGTH = 2000
NIF_MAX_LENGTH = 50

# Types de changement portés par `identity.membership_changed`.
CHANGE_ADDED = 'added'
CHANGE_ROLE_CHANGED = 'role_changed'
CHANGE_REVOKED = 'revoked'
CHANGE_REACTIVATED = 'reactivated'

# Raisons portées par `identity.seller_context_status_changed`.
STATUS_REASON_SUSPENDED = 'suspended'
STATUS_REASON_REACTIVATED = 'reactivated'
STATUS_REASON_ARCHIVED = 'archived'


class OrganizationError(CodedAPIException):
    """Refus métier d'équipe ou d'organisation : code en minuscules (ADR 0006, A14)."""

    def __init__(self, detail, code, status_code=status.HTTP_409_CONFLICT):
        super().__init__(detail, code, status_code)


def _last_owner_error():
    return OrganizationError("Une organisation doit garder au moins un propriétaire.", 'last_owner')


# --- Réglages ---------------------------------------------------------------------

def get_identity_settings() -> IdentitySettings:
    return IdentitySettings.get_solo()


# --- Lectures sans effet de bord ------------------------------------------------------

def count_active_owners(organization_id) -> int:
    return Membership.objects.filter(
        organization_id=organization_id, role=ROLE_OWNER, status=Membership.STATUS_ACTIVE,
    ).count()


def count_active_memberships(user_id) -> int:
    """Appartenances actives du compte dans des organisations ACTIVE (base du plafond : une organisation
    archivée ou suspendue ne consomme pas de place)."""
    return Membership.objects.filter(
        user_id=user_id, status=Membership.STATUS_ACTIVE, organization__status=Organization.STATUS_ACTIVE,
    ).count()


def get_active_role(user_id, organization_id):
    """Rôle d'un compte dans une organisation, ou None s'il n'a pas d'appartenance active. Aucun cache :
    une révocation est effective à l'appel suivant (R11)."""
    if user_id is None or organization_id is None:
        return None
    return Membership.objects.filter(
        user_id=user_id, organization_id=organization_id, status=Membership.STATUS_ACTIVE,
    ).values_list('role', flat=True).first()


# --- Garde-fous internes ----------------------------------------------------------------

def _lock_organization(organization_id) -> Organization:
    """Charge l'organisation sous verrou. Inexistante = même refus qu'un non-membre (pas d'oracle)."""
    try:
        return Organization.objects.select_for_update().get(pk=organization_id)
    except (Organization.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ContextDenied(DENY_RELATION, "Vous n'êtes pas membre de cette organisation.")


def _ensure_organization_usable(organization, allow_archived=False, allow_inactive=False):
    """`allow_inactive` : suspendue ou archivée tolérées (sortie volontaire) ; `allow_archived` : seule
    l'archivée est tolérée (le dernier propriétaire peut transférer depuis une organisation archivée)."""
    if allow_inactive:
        return
    if organization.status == Organization.STATUS_SUSPENDED:
        raise ContextDenied(DENY_SECURITY, "Cette organisation est suspendue.")
    if organization.status == Organization.STATUS_ARCHIVED and not allow_archived:
        raise ContextDenied(DENY_OBJECT_STATE, "Cette organisation est archivée.")


def _authorize_member(actor, organization, capability, allow_inactive=False, allow_archived=False) -> Membership:
    """Appartenance active de l'acteur, état de l'organisation, état du compte puis capacité, dans cet
    ordre. Un acteur désactivé ou restreint est refusé (`DENY_SECURITY`), sauf pour la sortie volontaire
    (`org.leave`). `is_staff` et `is_superuser` n'ouvrent rien (ADR 0006, A5)."""
    membership = Membership.objects.filter(
        organization=organization, user_id=actor.pk, status=Membership.STATUS_ACTIVE,
    ).first()
    if membership is None:
        raise ContextDenied(DENY_RELATION, "Vous n'êtes pas membre de cette organisation.")
    _ensure_organization_usable(organization, allow_archived=allow_archived, allow_inactive=allow_inactive)
    if capability != 'org.leave' and (not actor.is_active or is_user_restricted(actor.pk)):
        raise ContextDenied(DENY_SECURITY, "Votre compte ne permet pas cette action.")
    if not capabilities.role_has_capability(membership.role, capability):
        raise ContextDenied(DENY_PERMISSION, "Votre rôle ne permet pas cette action.")
    return membership


def _unavailable_user_error():
    """Réponse unique et neutre quand un compte ne peut pas être ciblé : inconnu, inactif, restreint ou
    au plafond. Même code, même statut, même message : elle ne révèle pas l'état du compte."""
    return OrganizationError(
        "Ce compte ne peut pas être ajouté ou modifié dans l'organisation.", 'user_unavailable',
        status.HTTP_400_BAD_REQUEST,
    )


def _ensure_target_available(user_id):
    """Cible active et non restreinte, sinon réponse neutre."""
    if not User.objects.filter(pk=user_id, is_active=True).exists() or is_user_restricted(user_id):
        raise _unavailable_user_error()


def _validate_role(role):
    if role not in ROLES:
        raise serializers.ValidationError({'role': ["Rôle inconnu."]})


def _get_membership(organization, user_id) -> Membership:
    membership = Membership.objects.filter(organization=organization, user_id=user_id).first()
    if membership is None:
        raise OrganizationError("Ce compte n'est pas membre de l'organisation.", 'member_not_found', 404)
    return membership


def _event_payload(organization, membership, change, old_role, new_role, actor):
    return {
        'organization_id': str(organization.pk), 'user_id': str(membership.user_id), 'change': change,
        'old_role': old_role or None, 'new_role': new_role or None,
        'actor_id': str(actor.pk) if actor is not None else None,
    }


def _publish_membership_change(organization, membership, change, old_role, new_role, actor):
    publish_event(
        'identity.membership_changed', aggregate_type='organization', aggregate_id=organization.pk,
        payload=_event_payload(organization, membership, change, old_role, new_role, actor),
    )


def _audit_membership(actor, action, organization, membership, old_role, new_role):
    record_audit(
        actor, action, target=membership,
        details=f"organization={organization.pk}; user={membership.user_id}; "
                f"old_role={old_role or '-'}; new_role={new_role or '-'}",
        context=(CONTEXT_ORGANIZATION, organization.pk),
    )


def _ensure_under_limit(user_id):
    """Plafond d'appartenances actives par compte (réglage, règle 11). Le compte est verrouillé pour que
    deux créations simultanées ne dépassent pas la limite."""
    User.objects.select_for_update().filter(pk=user_id).first()
    limit = get_identity_settings().max_organizations_per_account
    if count_active_memberships(user_id) >= limit:
        raise OrganizationError("Vous avez atteint le nombre maximal d'organisations.", 'organization_limit_reached')


_FORBIDDEN_NAME_CATEGORIES = ('Cc', 'Cf', 'Zl', 'Zp')


def normalize_name(name):
    """Forme canonique d'un nom d'organisation : NFKC, espaces multiples repliés, bords retirés. Retourne
    None si le nom contient un caractère de contrôle, de direction ou de largeur nulle (catégories
    Unicode Cc, Cf, Zl, Zp), qui permettraient d'usurper un nom visuellement."""
    if not isinstance(name, str):
        return None
    name = unicodedata.normalize('NFKC', name)
    if any(unicodedata.category(ch) in _FORBIDDEN_NAME_CATEGORIES for ch in name):
        return None
    return re.sub(r'\s+', ' ', name).strip()


def _error(message, code):
    return [ErrorDetail(message, code=code)]


def _validate_creation_input(name, org_type, description, nif, category_ids, city_id, commune_id, logo):
    from apps.catalog import services as catalog

    errors = {}
    normalized = normalize_name(name)
    if normalized is None:
        errors['name'] = _error("Le nom contient un caractère non autorisé.", 'invalid_name')
        normalized = ''
    elif not NAME_MIN_LENGTH <= len(normalized) <= NAME_MAX_LENGTH:
        errors['name'] = _error(
            f"Le nom doit contenir de {NAME_MIN_LENGTH} à {NAME_MAX_LENGTH} caractères.", 'invalid_name',
        )
    if not isinstance(org_type, str) or org_type not in ORG_TYPES:
        errors['org_type'] = _error("Type d'organisation inconnu.", 'invalid_org_type')
    if description is None:
        description = ''
    if not isinstance(description, str):
        errors['description'] = _error("La description doit être un texte.", 'invalid_description')
    elif len(description) > DESCRIPTION_MAX_LENGTH:
        errors['description'] = _error(
            f"La description ne doit pas dépasser {DESCRIPTION_MAX_LENGTH} caractères.", 'invalid_description',
        )
    if nif is None:
        nif = ''
    if not isinstance(nif, str):
        errors['nif'] = _error("Le NIF doit être un texte.", 'invalid_nif')
    else:
        nif = nif.strip()
        if len(nif) > NIF_MAX_LENGTH:
            errors['nif'] = _error(f"Le NIF ne doit pas dépasser {NIF_MAX_LENGTH} caractères.", 'invalid_nif')

    wanted = []
    if category_ids is None:
        category_ids = ()
    if not isinstance(category_ids, (list, tuple, set)):
        errors['category_ids'] = _error("Les catégories doivent former une liste.", 'unknown_category')
    else:
        parsed = [parse_uuid(c) for c in category_ids]
        if any(p is None for p in parsed):
            errors['category_ids'] = _error("Une catégorie est inconnue.", 'unknown_category')
        else:
            wanted = list(dict.fromkeys(parsed))
            if len(wanted) > get_identity_settings().max_categories_per_context:
                errors['category_ids'] = _error("Trop de catégories.", 'too_many_categories')
            elif wanted and len(catalog.existing_category_ids(wanted)) != len(wanted):
                errors['category_ids'] = _error("Une catégorie est inconnue.", 'unknown_category')
    if city_id is not None and not catalog.city_exists(city_id):
        errors['city_id'] = _error("Ville inconnue.", 'unknown_city')
    if commune_id is not None:
        if not catalog.commune_exists(commune_id):
            errors['commune_id'] = _error("Commune inconnue.", 'unknown_commune')
        elif city_id is not None and not catalog.commune_belongs_to_city(commune_id, city_id):
            errors['commune_id'] = _error("Cette commune n'appartient pas à la ville choisie.", 'unknown_commune')
    if logo is not None:
        if not isinstance(logo, File):
            errors['logo'] = _error("Le logo doit être un fichier image.", 'invalid_logo')
        else:
            try:
                validate_image_upload_size(logo)
                validate_image_pixels(logo)
            except DjangoValidationError as exc:
                errors['logo'] = [ErrorDetail(m, code='invalid_logo') for m in exc.messages]
    if errors:
        raise serializers.ValidationError(errors)
    return normalized, description, nif, wanted


# --- Cycle de vie -------------------------------------------------------------------------

def create_organization(
    creator, name, org_type, description='', nif='', category_ids=(), city_id=None, commune_id=None, logo=None,
) -> Organization:
    """Crée une organisation dont `creator` devient propriétaire, en une seule transaction (R1 de la
    spec : si l'appartenance échoue, aucune organisation n'existe). Conditions : compte actif, téléphone
    de connexion vérifié, absence de restriction, plafond du réglage non atteint."""
    if not creator.is_active:
        raise ContextDenied(DENY_SECURITY, "Votre compte est désactivé.")
    if not creator.phone_verified:
        raise OrganizationError(
            "Vérifiez votre numéro de téléphone avant de créer une organisation.",
            'phone_verification_required', status.HTTP_403_FORBIDDEN,
        )
    if is_user_restricted(creator.pk):
        raise ContextDenied(DENY_SECURITY, "Votre compte fait l'objet d'une restriction.")
    name, description, nif, wanted_categories = _validate_creation_input(
        name, org_type, description, nif, category_ids, city_id, commune_id, logo,
    )

    organization = None
    try:
        with transaction.atomic():
            _ensure_under_limit(creator.pk)
            organization = Organization(
                name=name, org_type=org_type, description=description, nif=nif,
                city_id=city_id, commune_id=commune_id, status=Organization.STATUS_ACTIVE, created_by=creator,
            )
            if logo:
                organization.logo = logo
            organization.save()
            OrganizationCategory.objects.bulk_create([
                OrganizationCategory(organization=organization, category_id=cid) for cid in wanted_categories
            ])
            membership = Membership.objects.create(
                organization=organization, user=creator, role=ROLE_OWNER, status=Membership.STATUS_ACTIVE,
                added_by=creator,
            )
            record_audit(
                creator, 'ORG_CREATED', target=organization, details=f"org_type={org_type}",
                context=(CONTEXT_ORGANIZATION, organization.pk),
            )
            _publish_membership_change(organization, membership, CHANGE_ADDED, None, ROLE_OWNER, creator)
    except BaseException:
        # Le fichier est écrit par `save()` avant la validation de la transaction : pas d'orphelin si elle
        # est annulée (limite : une transaction englobante annulée plus tard n'est pas détectable ici).
        _discard_logo(organization)
        raise
    return organization


def _discard_logo(organization):
    if organization is not None and organization.logo and organization.logo.name:
        try:
            organization.logo.storage.delete(organization.logo.name)
        except Exception:  # nettoyage au mieux, ne masque jamais l'erreur d'origine
            pass


def archive_organization(actor, organization_id) -> Organization:
    """Archive l'organisation (propriétaire seulement, `org.archive`). Irréversible par l'API."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        _authorize_member(actor, organization, 'org.archive')
        organization.status = Organization.STATUS_ARCHIVED
        organization.save(update_fields=['status', 'updated_at'])
        record_audit(
            actor, 'ORG_ARCHIVED', target=organization, details=f"organization={organization.pk}",
            context=(CONTEXT_ORGANIZATION, organization.pk),
        )
        _publish_status_change(organization, STATUS_REASON_ARCHIVED, actor)
    return organization


def _ensure_staff_permission(actor):
    if not actor.is_active or not actor.has_perm('identity.suspend_organization'):
        raise ContextDenied(DENY_PERMISSION, "Vous n'avez pas le droit de suspendre une organisation.")


def suspend_organization(actor, organization_id, reason) -> Organization:
    """Suspension par le personnel (permission `identity.suspend_organization`), motif normalisé."""
    _ensure_staff_permission(actor)
    if reason not in SUSPENSION_REASONS:
        raise serializers.ValidationError({'reason': ["Motif de suspension inconnu."]})
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        if organization.status != Organization.STATUS_ACTIVE:
            raise OrganizationError("Seule une organisation active peut être suspendue.", 'invalid_status')
        organization.status = Organization.STATUS_SUSPENDED
        organization.suspension_reason = reason
        organization.save(update_fields=['status', 'suspension_reason', 'updated_at'])
        record_audit(
            actor, 'ORG_SUSPENDED', target=organization, details=f"reason={reason}",
            context=(CONTEXT_ORGANIZATION, organization.pk),
        )
        _publish_status_change(organization, STATUS_REASON_SUSPENDED, actor)
    return organization


def reactivate_organization(actor, organization_id) -> Organization:
    """Réactivation par le personnel d'une organisation suspendue ou archivée."""
    _ensure_staff_permission(actor)
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        if organization.status == Organization.STATUS_ACTIVE:
            raise OrganizationError("Cette organisation est déjà active.", 'invalid_status')
        old_status, old_reason = organization.status, organization.suspension_reason
        organization.status = Organization.STATUS_ACTIVE
        organization.suspension_reason = ''
        organization.save(update_fields=['status', 'suspension_reason', 'updated_at'])
        record_audit(
            actor, 'ORG_REACTIVATED', target=organization,
            details=f"old_status={old_status}; old_reason={old_reason or '-'}",
            context=(CONTEXT_ORGANIZATION, organization.pk),
        )
        _publish_status_change(organization, STATUS_REASON_REACTIVATED, actor)
    return organization


def _publish_status_change(organization, reason, actor):
    publish_event(
        'identity.seller_context_status_changed', aggregate_type='organization', aggregate_id=organization.pk,
        payload={
            'context_type': CONTEXT_ORGANIZATION, 'context_id': str(organization.pk), 'reason': reason,
            'actor_id': str(actor.pk) if actor is not None else None,
        },
    )


# --- Équipe -------------------------------------------------------------------------------

def add_member(actor, organization_id, user_id, role) -> Membership:
    """Ajoute (ou réactive) un membre actif. `org.manage_members` ; un administrateur n'attribue jamais
    OWNER (R9) ni un rôle supérieur au sien (R10). Réactive la même ligne pour un ancien membre (R12).

    NON EXPOSABLE TEL QUEL : cet ajout direct se fait sans le consentement de la cible. Aucun endpoint ne doit
    l'appeler en l'état ; L1-01 doit implémenter invitation + acceptation par la cible (plafond vérifié à
    l'acceptation), avec revue de `auditeur-securite` (ADR 0006, sections 15 et 17). Les refus portant sur la
    cible (inconnue, inactive, restreinte, au plafond) partagent une réponse unique et neutre."""
    _validate_role(role)
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_members')
        if not capabilities.can_manage_role_of(actor_membership.role, role):
            raise ContextDenied(DENY_PERMISSION, "Vous ne pouvez pas attribuer ce rôle.")
        # La cible est verrouillée et son plafond vérifié avant toute lecture de ses appartenances.
        target = User.objects.select_for_update().filter(pk=user_id, is_active=True).first()
        if target is None or is_user_restricted(target.pk):
            raise _unavailable_user_error()
        try:
            _ensure_under_limit(target.pk)
        except OrganizationError:
            raise _unavailable_user_error()
        membership = Membership.objects.filter(organization=organization, user=target).first()
        if membership is not None and membership.status == Membership.STATUS_ACTIVE:
            raise OrganizationError("Ce compte est déjà membre de l'organisation.", 'already_member')
        now = timezone.now()
        if membership is None:
            membership = Membership.objects.create(
                organization=organization, user=target, role=role, status=Membership.STATUS_ACTIVE,
                added_by=actor, joined_at=now,
            )
            change = CHANGE_ADDED
        else:
            membership.role, membership.status = role, Membership.STATUS_ACTIVE
            membership.end_reason, membership.ended_at, membership.ended_by = '', None, None
            membership.added_by, membership.joined_at = actor, now
            membership.save()
            change = CHANGE_REACTIVATED
        _audit_membership(actor, 'MEMBERSHIP_ADDED', organization, membership, None, role)
        _publish_membership_change(organization, membership, change, None, role, actor)
    return membership


def _apply_role_change(actor, organization, membership, new_role, audit_action='MEMBERSHIP_ROLE_CHANGED'):
    """Écrit un changement de rôle (verrou déjà posé, autorisation déjà faite) et vérifie l'invariant
    LAST_OWNER après l'écriture : une transition qui laisserait zéro propriétaire annule la transaction."""
    old_role = membership.role
    if old_role == new_role:
        return membership
    Membership.objects.filter(pk=membership.pk, status=Membership.STATUS_ACTIVE).update(
        role=new_role, updated_at=timezone.now(),
    )
    membership.role = new_role
    if old_role == ROLE_OWNER and count_active_owners(organization.pk) < 1:
        raise _last_owner_error()
    _audit_membership(actor, audit_action, organization, membership, old_role, new_role)
    _publish_membership_change(organization, membership, CHANGE_ROLE_CHANGED, old_role, new_role, actor)
    return membership


def change_member_role(actor, organization_id, user_id, new_role) -> Membership:
    """Change le rôle d'un membre actif. `org.manage_roles` ; l'administrateur ne manipule que ADMIN, EDITOR
    et ANALYST (R9, R10) ; seul un propriétaire attribue ou retire OWNER ; jamais zéro propriétaire (R8)."""
    _validate_role(new_role)
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_roles')
        membership = _get_membership(organization, user_id)
        if membership.status != Membership.STATUS_ACTIVE:
            raise OrganizationError("Ce compte n'est pas membre de l'organisation.", 'member_not_found', 404)
        if not (capabilities.can_manage_role_of(actor_membership.role, membership.role)
                and capabilities.can_manage_role_of(actor_membership.role, new_role)):
            raise ContextDenied(DENY_PERMISSION, "Vous ne pouvez pas modifier ce rôle.")
        _ensure_target_available(membership.user_id)
        return _apply_role_change(actor, organization, membership, new_role)


def transfer_ownership(actor, organization_id, new_owner_user_id, actor_new_role=capabilities.ROLE_ADMIN) -> Membership:
    """Transfert de propriété = deux changements de rôle (promotion du nouveau propriétaire puis
    rétrogradation de l'acteur), faits par la voie `org.manage_roles` réservée aux propriétaires pour OWNER.
    Une seule transaction, deux événements, une trace `ORG_OWNERSHIP_TRANSFERRED`."""
    _validate_role(actor_new_role)
    if actor_new_role == ROLE_OWNER:
        raise serializers.ValidationError({'role': ["Le propriétaire sortant doit prendre un autre rôle."]})
    if str(new_owner_user_id) == str(actor.pk):
        raise OrganizationError("Vous êtes déjà propriétaire.", 'invalid_transfer', status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_roles', allow_archived=True)
        if actor_membership.role != ROLE_OWNER:
            raise ContextDenied(DENY_PERMISSION, "Seul un propriétaire peut transférer la propriété.")
        target = _get_membership(organization, new_owner_user_id)
        if target.status != Membership.STATUS_ACTIVE:
            raise OrganizationError("Ce compte n'est pas membre de l'organisation.", 'member_not_found', 404)
        _ensure_target_available(target.user_id)
        _apply_role_change(actor, organization, target, ROLE_OWNER)
        _apply_role_change(actor, organization, actor_membership, actor_new_role)
        record_audit(
            actor, 'ORG_OWNERSHIP_TRANSFERRED', target=organization,
            details=f"from_user={actor.pk}; to_user={target.user_id}",
            context=(CONTEXT_ORGANIZATION, organization.pk),
        )
    return target


def _end_membership(actor, organization, membership, end_reason, audit_action):
    """Passe l'appartenance à REVOKED (mise à jour conditionnelle) et vérifie LAST_OWNER après coup."""
    old_role = membership.role
    now = timezone.now()
    done = Membership.objects.filter(pk=membership.pk, status=Membership.STATUS_ACTIVE).update(
        status=Membership.STATUS_REVOKED, end_reason=end_reason, ended_at=now, ended_by=actor, updated_at=now,
    )
    if not done:
        raise OrganizationError("Ce compte n'est pas membre de l'organisation.", 'member_not_found', 404)
    # Une organisation archivée n'a plus de vie active : son dernier propriétaire peut la quitter (tracé).
    if (old_role == ROLE_OWNER and organization.status != Organization.STATUS_ARCHIVED
            and count_active_owners(organization.pk) < 1):
        raise _last_owner_error()
    membership.status, membership.end_reason, membership.ended_at = Membership.STATUS_REVOKED, end_reason, now
    _audit_membership(actor, audit_action, organization, membership, old_role, None)
    _publish_membership_change(organization, membership, CHANGE_REVOKED, old_role, None, actor)
    return membership


def revoke_member(actor, organization_id, user_id) -> Membership:
    """Retire un membre (`org.manage_members`). L'administrateur n'agit jamais sur un propriétaire (R9).
    Pour se retirer soi-même, utiliser `leave_organization`. Effet immédiat (R11)."""
    if str(user_id) == str(actor.pk):
        raise OrganizationError("Utilisez « quitter l'organisation ».", 'use_leave', status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_members')
        membership = _get_membership(organization, user_id)
        if membership.status != Membership.STATUS_ACTIVE:
            raise OrganizationError("Ce compte n'est pas membre de l'organisation.", 'member_not_found', 404)
        if not capabilities.can_manage_role_of(actor_membership.role, membership.role):
            raise ContextDenied(DENY_PERMISSION, "Vous ne pouvez pas retirer ce membre.")
        return _end_membership(actor, organization, membership, Membership.END_REMOVED, 'MEMBERSHIP_REVOKED')


def leave_organization(user, organization_id) -> Membership:
    """Sortie volontaire d'un membre (`org.leave`), refusée pour le dernier propriétaire. Autorisée aussi
    pour une organisation suspendue ou archivée (ADR 0006, amendement 1, Q-F4) : jamais bloquée."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        membership = _authorize_member(user, organization, 'org.leave', allow_inactive=True)
        return _end_membership(user, organization, membership, Membership.END_LEFT, 'MEMBERSHIP_REVOKED')


def assert_account_removable(user):
    """Refuse (409 `last_owner_account`) la suppression d'un compte seul propriétaire ACTIF d'une organisation
    active : l'organisation deviendrait orpheline. Ne bloque PAS la désactivation par sanction (`is_active`).
    Dette (ADR 0006, section 15) : chemin de secours audité du personnel et sort des organisations orphelines,
    à livrer avec L1-01 / la suppression de compte."""
    owned = list(Membership.objects.filter(
        user_id=user.pk, role=ROLE_OWNER, status=Membership.STATUS_ACTIVE,
        organization__status=Organization.STATUS_ACTIVE,
    ).values_list('organization_id', flat=True))
    for organization_id in owned:
        if count_active_owners(organization_id) <= 1:
            raise OrganizationError(
                "Ce compte est le seul propriétaire d'une organisation active : transférez la propriété d'abord.",
                'last_owner_account',
            )
