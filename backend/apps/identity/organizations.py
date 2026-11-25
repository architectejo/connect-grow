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
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files import File
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.db.models.functions import Lower
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import ErrorDetail

from apps.common.contexts import (
    CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER, DENY_OBJECT_STATE, DENY_PERMISSION, DENY_RELATION,
    DENY_SECURITY, ContextDenied,
)
from apps.common.exception_handler import CodedAPIException
from apps.common.images import reencode_image, validate_image_pixels, validate_image_upload_size
from apps.common.utils import parse_uuid
from apps.moderation import services as moderation_services
from apps.moderation.services import record_audit
from apps.platform_core.services import publish_event

from . import capabilities
from .capabilities import ROLE_OWNER, ROLES
from .models import (
    IdentitySettings, KycDocument, Membership, Organization, OrganizationCategory, OrganizationInvitation, ORG_TYPES,
    ProviderProfile, User,
)
from .throttles import FailureLimiter

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
STATUS_REASON_OWNERS_CHANGED = 'owners_changed'

# Opérations qui touchent un siège de propriétaire : ressaisie du mot de passe (ADR 0008 §8.2).
REAUTH_TRANSFER = 'transfer'
REAUTH_PROMOTE_OWNER = 'promote_owner'
REAUTH_DEMOTE_OWNER = 'demote_owner'
# Compteur d'échecs de ressaisie, par compte appelant (le compteur est celui de l'attaquant, pas d'une victime).
REAUTH_FAILURES = FailureLimiter('org_reauth', threshold=5)

# Rôles que le propriétaire sortant peut prendre lors d'un transfert (jamais OWNER).
TRANSFER_SELF_ROLES = (capabilities.ROLE_ADMIN, capabilities.ROLE_EDITOR, capabilities.ROLE_ANALYST)


class OrganizationError(CodedAPIException):
    """Refus métier d'équipe ou d'organisation : code en minuscules (ADR 0006, A14)."""

    def __init__(self, detail, code, status_code=status.HTTP_409_CONFLICT):
        super().__init__(detail, code, status_code)


def _last_owner_error(organization=None):
    """Refus `last_owner`. Pour une organisation SUSPENDED (le seul administrateur principal ne peut ni partir ni
    changer de rôle), le message explique l'issue : attendre la levée de la suspension ou contacter le support."""
    if organization is not None and organization.status == Organization.STATUS_SUSPENDED:
        return OrganizationError(
            "Cette organisation est suspendue et vous en êtes le seul administrateur principal : vous ne pouvez pas "
            "la quitter ni changer votre rôle tant que la suspension n'est pas levée. Attendez la levée de la "
            "suspension ou contactez le support.",
            'last_owner',
        )
    return OrganizationError("Une organisation doit garder au moins un administrateur principal.", 'last_owner')


def _last_effective_owner_error():
    return OrganizationError(
        "Cette opération laisserait l'organisation sans administrateur principal actif alors qu'elle a des offres "
        "actives. Désignez d'abord un autre administrateur principal.",
        'last_effective_owner',
    )


# --- Réglages ---------------------------------------------------------------------

def get_identity_settings() -> IdentitySettings:
    return IdentitySettings.get_solo()


# --- Lectures sans effet de bord ------------------------------------------------------

def count_active_owners(organization_id) -> int:
    return Membership.objects.filter(
        organization_id=organization_id, role=ROLE_OWNER, status=Membership.STATUS_ACTIVE,
    ).count()


def effective_owner_ids_by_organization(organization_ids) -> dict:
    """`{organisation: {comptes}}` : propriétaires EFFECTIFS (ADR 0008 §9, R-L8) = appartenance `OWNER` `ACTIVE`
    dont le compte est actif et sans sanction bloquante. Définition UNIQUE, partagée avec la visibilité publique
    (`sellers.get_seller_context_public_flags`). Deux requêtes, quel que soit le nombre d'organisations ; une
    organisation sans propriétaire effectif est absente du résultat."""
    owners = {}
    for organization_id, user_id in Membership.objects.filter(
        organization_id__in=list(organization_ids), role=ROLE_OWNER, status=Membership.STATUS_ACTIVE,
        user__is_active=True,
    ).values_list('organization_id', 'user_id'):
        owners.setdefault(organization_id, set()).add(user_id)
    everyone = set().union(*owners.values()) if owners else set()
    restricted = moderation_services.get_restricted_user_ids(everyone) if everyone else set()
    result = {}
    for organization_id, users in owners.items():
        effective = users - restricted
        if effective:
            result[organization_id] = effective
    return result


def _effective_owner_ids(organization_id) -> set:
    return effective_owner_ids_by_organization([organization_id]).get(organization_id, set())


def count_effective_owners(organization_id) -> int:
    return len(_effective_owner_ids(organization_id))


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
    (`org.leave`). `is_staff` et `is_superuser` n'ouvrent rien (ADR 0006, A5). Périmètre (ADR 0010 D3, fermé par
    défaut) : une appartenance limitée à une ville ou une unité n'exerce aucune capacité de niveau organisation
    (`DENY_PERMISSION`), sauf `org.leave`."""
    membership = Membership.objects.filter(
        organization=organization, user_id=actor.pk, status=Membership.STATUS_ACTIVE,
    ).first()
    if membership is None:
        raise ContextDenied(DENY_RELATION, "Vous n'êtes pas membre de cette organisation.")
    _ensure_organization_usable(organization, allow_archived=allow_archived, allow_inactive=allow_inactive)
    if capability != 'org.leave' and (not actor.is_active or moderation_services.is_user_restricted(actor.pk)):
        raise ContextDenied(DENY_SECURITY, "Votre compte ne permet pas cette action.")
    if not capabilities.role_has_capability(membership.role, capability):
        raise ContextDenied(DENY_PERMISSION, "Votre rôle ne permet pas cette action.")
    if not capabilities.scope_allows(membership_scope(membership), capability):
        raise ContextDenied(DENY_PERMISSION, "Votre périmètre ne permet pas cette action.")
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
    if not User.objects.filter(pk=user_id, is_active=True).exists() or moderation_services.is_user_restricted(user_id):
        raise _unavailable_user_error()


def _validate_role(role):
    if role not in ROLES:
        raise serializers.ValidationError({'role': ["Rôle inconnu."]})


SCOPE_NOT_AVAILABLE_MESSAGE = "Ce périmètre n'est pas encore disponible."


def _validate_scope(scope) -> capabilities.Scope:
    """Périmètre fourni en entrée d'API (contrat L1-01 §7.1 et §7.2). `None` (absent ou nul) : renvoie `None`, à
    l'appelant de choisir le défaut. Seule valeur acceptée en V1 : exactement `{"type": "ORGANIZATION", "id": null}`
    (les deux clés, rien d'autre) ; toute autre valeur (type réservé `CITY` ou `UNIT`, identifiant non nul, clé
    manquante ou en trop, forme invalide) : erreur de champ 400 `{"scope": [...]}` (ADR 0010 §6.1)."""
    if scope is None:
        return None
    if (
        isinstance(scope, dict) and set(scope) == {'type', 'id'}
        and scope['type'] in capabilities.ACTIVE_SCOPE_TYPES and scope['id'] is None
    ):
        return capabilities.Scope(scope['type'], None)
    raise serializers.ValidationError({'scope': [SCOPE_NOT_AVAILABLE_MESSAGE]})


def membership_scope(membership) -> capabilities.Scope:
    """Périmètre d'une appartenance (ou d'une invitation : mêmes champs)."""
    return capabilities.Scope.of(membership.scope_type, membership.scope_id)


def _can_manage_member(actor_membership, membership) -> bool:
    """L'acteur peut agir sur ce membre : il peut gérer son rôle ET son périmètre couvre celui du membre."""
    return capabilities.can_delegate(
        actor_membership.role, membership_scope(actor_membership), membership.role, membership_scope(membership),
    )


def _get_membership(organization, user_id) -> Membership:
    membership = Membership.objects.filter(organization=organization, user_id=user_id).first()
    if membership is None:
        raise OrganizationError("Ce compte n'est pas membre de l'organisation.", 'member_not_found', 404)
    return membership


def _event_payload(organization, membership, change, old_role, new_role, actor, via=None):
    """Charge utile de `identity.membership_changed` (v1). `via` (clé additive, ADR 0008 §6) n'est présente que
    pour une appartenance obtenue par invitation."""
    payload = {
        'organization_id': str(organization.pk), 'user_id': str(membership.user_id), 'change': change,
        'old_role': old_role or None, 'new_role': new_role or None,
        'actor_id': str(actor.pk) if actor is not None else None,
    }
    if via:
        payload['via'] = via
    return payload


def _publish_membership_change(organization, membership, change, old_role, new_role, actor, via=None):
    publish_event(
        'identity.membership_changed', aggregate_type='organization', aggregate_id=organization.pk,
        payload=_event_payload(organization, membership, change, old_role, new_role, actor, via=via),
    )


def _scope_code(scope) -> str:
    """`TYPE:uuid` ou `ORGANIZATION:-` pour l'audit (codes et UUID seulement)."""
    return f"{scope.type}:{scope.id or '-'}"


def _audit_membership(
    actor, action, organization, membership, old_role, new_role, reauth=False, orphaned=False, extra='',
    old_scope=None,
):
    details = (
        f"organization={organization.pk}; user={membership.user_id}; "
        f"old_role={old_role or '-'}; new_role={new_role or '-'}"
    )
    scope_type = getattr(membership, 'scope_type', capabilities.SCOPE_ORGANIZATION)
    if new_role and scope_type != capabilities.SCOPE_ORGANIZATION:
        # ADR 0010 §8 : le périmètre n'est tracé que s'il n'est pas l'organisation entière (codes et UUID seulement).
        details += f"; scope_type={scope_type}; scope_id={membership.scope_id}"
    if old_scope is not None and old_scope != membership_scope(membership):
        # Changement de périmètre : ancien et nouveau toujours tracés (ADR 0010 §8).
        details += f"; old_scope={_scope_code(old_scope)}; new_scope={_scope_code(membership_scope(membership))}"
    if reauth:
        details += "; reauth=true"
    if orphaned:
        details += "; orphaned=true"
    if extra:
        details += f"; {extra}"
    record_audit(
        actor, action, target=membership, details=details, context=(CONTEXT_ORGANIZATION, organization.pk),
    )


def _ensure_under_limit(user_id):
    """Plafond d'appartenances actives par compte (réglage, règle 11). Le compte est verrouillé pour que
    deux créations simultanées ne dépassent pas la limite."""
    User.objects.select_for_update().filter(pk=user_id).first()
    limit = get_identity_settings().max_organizations_per_account
    if count_active_memberships(user_id) >= limit:
        raise OrganizationError("Vous avez atteint le nombre maximal d'organisations.", 'organization_limit_reached')


_FORBIDDEN_NAME_CATEGORIES = ('Cc', 'Cf', 'Zl', 'Zp')


_CONFUSABLE_SCRIPTS = ('LATIN', 'CYRILLIC', 'GREEK')


def _mixes_scripts(name):
    """Vrai si le nom mêle plusieurs écritures aisément confondables (latin, cyrillique, grec) : « Rawbаnk »
    avec un « а » cyrillique imite « Rawbank » (homoglyphes). Ne détecte pas les collisions entre noms
    d'écritures homogènes (dette : modération, L1-01)."""
    scripts = set()
    for ch in name:
        if ch.isalpha():
            word = unicodedata.name(ch, '').split(' ', 1)[0]
            if word in _CONFUSABLE_SCRIPTS:
                scripts.add(word)
    return len(scripts) > 1


def normalize_name(name):
    """Forme canonique d'un nom d'organisation : NFKC, espaces multiples repliés, bords retirés. Retourne
    None si le nom contient un caractère de contrôle, de direction ou de largeur nulle (catégories
    Unicode Cc, Cf, Zl, Zp), ou qui mêle latin, cyrillique et grec (homoglyphes), qui permettraient d'usurper
    un nom visuellement."""
    if not isinstance(name, str):
        return None
    name = unicodedata.normalize('NFKC', name)
    if any(unicodedata.category(ch) in _FORBIDDEN_NAME_CATEGORIES for ch in name):
        return None
    if _mixes_scripts(name):
        return None
    return re.sub(r'\s+', ' ', name).strip()


def _error(message, code):
    return [ErrorDetail(message, code=code)]


def validate_category_ids(category_ids):
    """Catégories d'un contexte (organisation ou prestataire, ADR 0006 Q-F5) : liste facultative, vide
    permise, doublons ignorés, plafond réglable (`max_categories_per_context`). Retourne la liste d'UUID
    dédoublonnée ; lève `ValidationError({'category_ids': [...]})` code `unknown_category` ou
    `too_many_categories`."""
    from apps.catalog import services as catalog

    def fail(message, code):
        raise serializers.ValidationError({'category_ids': _error(message, code)})

    if category_ids is None:
        return []
    if not isinstance(category_ids, (list, tuple, set)):
        fail("Les catégories doivent former une liste.", 'unknown_category')
    parsed = [parse_uuid(c) for c in category_ids]
    if any(p is None for p in parsed):
        fail("Une catégorie est inconnue.", 'unknown_category')
    wanted = list(dict.fromkeys(parsed))
    if len(wanted) > get_identity_settings().max_categories_per_context:
        fail("Trop de catégories.", 'too_many_categories')
    if wanted and len(catalog.existing_category_ids(wanted)) != len(wanted):
        fail("Une catégorie est inconnue.", 'unknown_category')
    return wanted


def _check_description(description, errors):
    if description is None:
        description = ''
    if not isinstance(description, str):
        errors['description'] = _error("La description doit être un texte.", 'invalid_description')
    elif len(description) > DESCRIPTION_MAX_LENGTH:
        errors['description'] = _error(
            f"La description ne doit pas dépasser {DESCRIPTION_MAX_LENGTH} caractères.", 'invalid_description',
        )
    return description


def _check_nif(nif, errors):
    if nif is None:
        nif = ''
    if not isinstance(nif, str):
        errors['nif'] = _error("Le NIF doit être un texte.", 'invalid_nif')
    else:
        nif = nif.strip()
        if len(nif) > NIF_MAX_LENGTH:
            errors['nif'] = _error(f"Le NIF ne doit pas dépasser {NIF_MAX_LENGTH} caractères.", 'invalid_nif')
    return nif


def _check_name(name, errors):
    normalized = normalize_name(name)
    if normalized is None:
        errors['name'] = _error("Le nom contient un caractère non autorisé.", 'invalid_name')
        return ''
    if not NAME_MIN_LENGTH <= len(normalized) <= NAME_MAX_LENGTH:
        errors['name'] = _error(
            f"Le nom doit contenir de {NAME_MIN_LENGTH} à {NAME_MAX_LENGTH} caractères.", 'invalid_name',
        )
    return normalized


def _check_categories(category_ids, errors):
    try:
        return validate_category_ids(category_ids)
    except serializers.ValidationError as exc:
        errors['category_ids'] = exc.detail['category_ids']
        return []


def _check_location(city_id, commune_id, errors):
    """Ville et commune (références `catalog`) : existence, et la commune appartient à la ville."""
    from apps.catalog import services as catalog

    if city_id is not None and not catalog.city_exists(city_id):
        errors['city_id'] = _error("Ville inconnue.", 'unknown_city')
    if commune_id is not None:
        if not catalog.commune_exists(commune_id):
            errors['commune_id'] = _error("Commune inconnue.", 'unknown_commune')
        elif city_id is not None and not catalog.commune_belongs_to_city(commune_id, city_id):
            errors['commune_id'] = _error("Cette commune n'appartient pas à la ville choisie.", 'unknown_commune')


def _check_logo(logo, errors):
    if logo is None:
        return
    if not isinstance(logo, File):
        errors['logo'] = _error("Le logo doit être un fichier image.", 'invalid_logo')
        return
    try:
        validate_image_upload_size(logo)
        validate_image_pixels(logo)
        # Décodage réel (une image tronquée ou corrompue passe les contrôles d'en-tête) : refus ici en 400,
        # jamais une erreur au moment de l'écriture.
        reencode_image(logo)
    except DjangoValidationError as exc:
        errors['logo'] = [ErrorDetail(m, code='invalid_logo') for m in exc.messages]
    finally:
        if hasattr(logo, 'seek'):
            logo.seek(0)


def _validate_creation_input(name, org_type, description, nif, category_ids, city_id, commune_id, logo):
    errors = {}
    normalized = _check_name(name, errors)
    if not isinstance(org_type, str) or org_type not in ORG_TYPES:
        errors['org_type'] = _error("Type d'organisation inconnu.", 'invalid_org_type')
    description = _check_description(description, errors)
    nif = _check_nif(nif, errors)
    wanted = _check_categories(category_ids, errors)
    _check_location(city_id, commune_id, errors)
    _check_logo(logo, errors)
    if errors:
        raise serializers.ValidationError(errors)
    return normalized, description, nif, wanted


# --- Cycle de vie -------------------------------------------------------------------------

# Protection contre le double clic (L009-02) : même créateur, même nom (casse ignorée) et même type dans cette
# fenêtre => la création est idempotente (l'organisation existante est renvoyée, aucune autre n'est créée). Des
# homonymes espacés dans le temps restent autorisés (ADR 0006, A12). Limite : sans verrou, deux requêtes
# strictement simultanées peuvent encore passer ensemble (SQLite sérialise les écritures).
DUPLICATE_SUBMISSION_WINDOW_SECONDS = 10


def _recent_duplicate(creator, name, org_type):
    since = timezone.now() - timedelta(seconds=DUPLICATE_SUBMISSION_WINDOW_SECONDS)
    return Organization.objects.filter(
        created_by=creator, name__iexact=name, org_type=org_type, status=Organization.STATUS_ACTIVE,
        created_at__gte=since,
    ).order_by('created_at').first()


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
    if moderation_services.is_user_restricted(creator.pk):
        raise ContextDenied(DENY_SECURITY, "Votre compte fait l'objet d'une restriction.")
    name, description, nif, wanted_categories = _validate_creation_input(
        name, org_type, description, nif, category_ids, city_id, commune_id, logo,
    )

    organization = None
    try:
        with transaction.atomic():
            duplicate = _recent_duplicate(creator, name, org_type)
            if duplicate is not None:
                return duplicate  # double soumission : réponse idempotente, rien n'est recréé
            _ensure_under_limit(creator.pk)
            organization = Organization(
                name=name, org_type=org_type, description=description, nif=nif,
                city_id=city_id, commune_id=commune_id, status=Organization.STATUS_ACTIVE, created_by=creator,
            )
            if logo:
                organization.logo = logo
            _save_with_logo_check(organization)
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


def _save_with_logo_check(organization, **kwargs):
    """`save()` ré-encode le logo ; une image illisible qui aurait échappé à la validation devient un 400
    `invalid_logo` et non une erreur serveur. Le ré-encodage précède l'écriture : aucun fichier orphelin."""
    try:
        organization.save(**kwargs)
    except DjangoValidationError:
        raise serializers.ValidationError({'logo': _error("Fichier image invalide.", 'invalid_logo')})


def _discard_logo(organization):
    if organization is not None and organization.logo and organization.logo.name:
        try:
            organization.logo.storage.delete(organization.logo.name)
        except Exception:  # nettoyage au mieux, ne masque jamais l'erreur d'origine
            pass


# Champs d'identité modifiables par l'API (`org.edit_profile`). `org_type` est immuable (A13).
UPDATABLE_FIELDS = ('name', 'description', 'logo', 'category_ids', 'city_id', 'commune_id', 'nif')


def _discard_stored_file(name, storage):
    if name:
        try:
            storage.delete(name)
        except Exception:  # nettoyage au mieux, ne masque jamais l'erreur d'origine
            pass


def _set_categories(organization, wanted):
    OrganizationCategory.objects.filter(organization=organization).exclude(category_id__in=wanted).delete()
    existing = set(
        OrganizationCategory.objects.filter(organization=organization).values_list('category_id', flat=True)
    )
    OrganizationCategory.objects.bulk_create([
        OrganizationCategory(organization=organization, category_id=cid) for cid in wanted if cid not in existing
    ])


def update_organization(actor, organization_id, **changes) -> Organization:
    """Modifie l'identité de l'organisation (`org.edit_profile` : propriétaire et administrateur seulement,
    jamais un éditeur ni un analyste, Q-CP3). Seules les clés présentes sont lues ; `logo=None` retire le logo.

    - `org_type` : refusé (400 `org_type_immutable`), le type ne change pas par l'API ;
    - le nom ne peut plus changer dès qu'une pièce de l'organisation est validée ou en attente d'examen (409
      `name_locked_by_verification`, ADR 0006 A13 et §18) et le NIF dès qu'une pièce est validée (409
      `nif_locked_by_verification`) : un compte vérifié ne se renomme pas sans nouvelle
      vérification (règle 3) ; un nom inchangé après normalisation n'est pas un renommage ;
    - l'autorisation est (re)faite sous verrou, juste avant l'écriture (révocation ou suspension entre-temps) ;
    - audit synchrone `ORG_UPDATED` (noms de champs seulement, jamais les valeurs) et événement
      `identity.organization_updated` dans la même transaction ; rien n'est écrit si rien ne change."""
    if 'org_type' in changes:
        raise serializers.ValidationError({'org_type': _error(
            "Le type d'une organisation ne peut pas être modifié.", 'org_type_immutable',
        )})
    unknown = set(changes) - set(UPDATABLE_FIELDS)
    if unknown:
        raise serializers.ValidationError({key: _error("Champ non modifiable.", 'read_only') for key in unknown})

    stored_new_logo = None
    try:
        with transaction.atomic():
            organization = _lock_organization(organization_id)
            _authorize_member(actor, organization, 'org.edit_profile')

            errors = {}
            values = {}
            if 'name' in changes:
                values['name'] = _check_name(changes['name'], errors)
            if 'description' in changes:
                values['description'] = _check_description(changes['description'], errors)
            if 'nif' in changes:
                values['nif'] = _check_nif(changes['nif'], errors)
            if 'category_ids' in changes:
                values['category_ids'] = _check_categories(changes['category_ids'], errors)
            if 'city_id' in changes or 'commune_id' in changes:
                city_id = changes['city_id'] if 'city_id' in changes else organization.city_id
                commune_id = changes['commune_id'] if 'commune_id' in changes else organization.commune_id
                if city_id is None and 'commune_id' not in changes:
                    commune_id = None  # retirer la ville retire aussi la commune (cohérence)
                _check_location(city_id, commune_id, errors)
                values['city_id'], values['commune_id'] = city_id, commune_id
            if changes.get('logo') is not None:
                _check_logo(changes['logo'], errors)
            if errors:
                raise serializers.ValidationError(errors)

            pieces = KycDocument.objects.filter(organization=organization)
            if values.get('name') is not None and values['name'] != organization.name and pieces.filter(
                    status__in=(KycDocument.STATUS_VALIDE, KycDocument.STATUS_EN_ATTENTE)).exists():
                raise OrganizationError(
                    "Le nom ne peut plus être modifié : une pièce de l'organisation est validée ou en cours "
                    "d'examen. Contactez le support pour un changement de nom.",
                    'name_locked_by_verification',
                )
            if values.get('nif') is not None and values['nif'] != organization.nif and pieces.filter(
                    status=KycDocument.STATUS_VALIDE).exists():
                raise OrganizationError(
                    "Le NIF ne peut plus être modifié : une pièce de l'organisation est validée. "
                    "Contactez le support pour un changement.",
                    'nif_locked_by_verification',
                )

            touched = []
            for field in ('name', 'description', 'nif', 'city_id', 'commune_id'):
                if field in values and values[field] != getattr(organization, field):
                    setattr(organization, field, values[field])
                    touched.append(field)
            old_logo_name = organization.logo.name if organization.logo else None
            if 'logo' in changes and (changes['logo'] is not None or old_logo_name):
                organization.logo = changes['logo']
                touched.append('logo')
            if touched:
                _save_with_logo_check(organization, update_fields=touched + ['updated_at'])
                if 'logo' in touched and organization.logo:
                    stored_new_logo = organization.logo.name
            if 'category_ids' in values:
                current = set(OrganizationCategory.objects.filter(
                    organization=organization).values_list('category_id', flat=True))
                if current != set(values['category_ids']):
                    _set_categories(organization, values['category_ids'])
                    touched.append('category_ids')
            if not touched:
                return organization
            record_audit(
                actor, 'ORG_UPDATED', target=organization,
                details=f"organization={organization.pk}; fields={','.join(touched)}",
                context=(CONTEXT_ORGANIZATION, organization.pk),
            )
            publish_event(
                'identity.organization_updated', aggregate_type='organization', aggregate_id=organization.pk,
                payload={
                    'organization_id': str(organization.pk), 'fields': list(touched), 'actor_id': str(actor.pk),
                },
            )
            if 'logo' in touched and old_logo_name:
                storage = organization.logo.storage
                transaction.on_commit(lambda: _discard_stored_file(old_logo_name, storage))
    except BaseException:
        if stored_new_logo:
            _discard_stored_file(stored_new_logo, Organization._meta.get_field('logo').storage)
        raise
    return organization


def get_organization_for_member(actor, organization_id, capability='org.view_internal'):
    """Lecture réservée aux membres : `(organisation, rôle)`. Ordre des contrôles : non-membre
    (`DENY_RELATION`, aussi pour une organisation inexistante : pas d'oracle), état de l'organisation
    (suspendue `DENY_SECURITY`, archivée `DENY_OBJECT_STATE`), état du compte, puis capacité."""
    try:
        organization = Organization.objects.get(pk=organization_id)
    except (Organization.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ContextDenied(DENY_RELATION, "Vous n'êtes pas membre de cette organisation.")
    membership = _authorize_member(actor, organization, capability)
    return organization, membership.role


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
    """Réactivation par le personnel d'une organisation SUSPENDUE. Une organisation archivée est un choix de ses
    membres : le personnel ne la réactive jamais. Conflit d'intérêts : un acteur qui est ou a été membre de
    l'organisation, ou qui l'a créée, ne la réactive pas (refus journalisé avec l'acteur et l'ancien statut)."""
    _ensure_staff_permission(actor)
    # Refus d'abord, hors transaction : la trace du refus ne doit pas être annulée avec lui.
    known = Organization.objects.filter(pk=organization_id).first()
    if known is not None and known.status == Organization.STATUS_SUSPENDED and (
        known.created_by_id == actor.pk or Membership.objects.filter(organization=known, user_id=actor.pk).exists()
    ):
        record_audit(
            actor, 'ORG_REACTIVATION_DENIED', target=known,
            details=f"old_status={known.status}; reason=interest_conflict",
            context=(CONTEXT_ORGANIZATION, known.pk),
        )
        raise OrganizationError(
            "Vous ne pouvez pas réactiver une organisation dont vous êtes ou avez été membre, "
            "ou que vous avez créée.",
            'interest_conflict', status.HTTP_403_FORBIDDEN,
        )
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        if organization.status == Organization.STATUS_ACTIVE:
            raise OrganizationError("Cette organisation est déjà active.", 'invalid_status')
        if organization.status == Organization.STATUS_ARCHIVED:
            raise OrganizationError(
                "Une organisation archivée ne peut pas être réactivée par le personnel.", 'invalid_status',
            )
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
        deliver_now=True,  # visibilité des offres du vendeur à jour dès la fin de l'action (ADR 0006, A7)
    )


# --- Équipe -------------------------------------------------------------------------------

def _activate_membership(
    actor, organization, target, role, added_by=None, via=None, invited_by=None, scope=None,
):
    """Noyau interne, JAMAIS exposé : crée l'appartenance `ACTIVE` ou réactive la même ligne (R12), puis audit
    `MEMBERSHIP_ADDED` (acteur = `actor`) et événement `identity.membership_changed` (acteur = `added_by`, par défaut
    `actor`). Aucune autorisation ici : l'appelant l'a faite sous verrou. Déjà membre actif : 409 `already_member`.
    `via='invitation'` et `invited_by` tracent l'origine dans l'audit et l'événement (ADR 0008 §5.1, §6). `scope` :
    périmètre de l'appartenance (défaut : organisation entière ; une réactivation repart du périmètre donné)."""
    added_by = added_by or actor
    scope = scope or capabilities.ORGANIZATION_SCOPE
    membership = Membership.objects.filter(organization=organization, user=target).first()
    if membership is not None and membership.status == Membership.STATUS_ACTIVE:
        raise OrganizationError("Ce compte est déjà membre de l'organisation.", 'already_member')
    now = timezone.now()
    if membership is None:
        membership = Membership.objects.create(
            organization=organization, user=target, role=role, status=Membership.STATUS_ACTIVE,
            scope_type=scope.type, scope_id=scope.id, added_by=added_by, joined_at=now,
        )
        change = CHANGE_ADDED
    else:
        membership.role, membership.status = role, Membership.STATUS_ACTIVE
        membership.scope_type, membership.scope_id = scope.type, scope.id
        membership.end_reason, membership.ended_at, membership.ended_by = '', None, None
        membership.added_by, membership.joined_at = added_by, now
        membership.save()
        change = CHANGE_REACTIVATED
    extra = f"via={via}; invited_by={invited_by}" if via else ''
    _audit_membership(actor, 'MEMBERSHIP_ADDED', organization, membership, None, role, extra=extra)
    _publish_membership_change(organization, membership, change, None, role, added_by, via=via)
    return membership


def add_member(actor, organization_id, user_id, role) -> Membership:
    """Ajoute (ou réactive) un membre actif. `org.manage_members` ; un administrateur n'attribue jamais
    OWNER (R9) ni un rôle supérieur au sien (R10). Réactive la même ligne pour un ancien membre (R12).

    NON EXPOSABLE : cet ajout direct se fait sans le consentement de la cible. Aucun endpoint n'appelle cette
    fonction (ADR 0008 : l'entrée dans une équipe passe par une invitation acceptée par la cible, voir
    `invitations.accept_invitation`) ; un test de garde de routes vérifie qu'aucune vue ne l'importe. Elle ne
    subsiste que pour les tests et les usages internes. Les refus portant sur la cible (inconnue, inactive,
    restreinte, au plafond) partagent une réponse unique et neutre."""
    _validate_role(role)
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_members')
        if not capabilities.can_delegate(
            actor_membership.role, membership_scope(actor_membership), role, capabilities.ORGANIZATION_SCOPE,
        ):
            raise ContextDenied(DENY_PERMISSION, "Vous ne pouvez pas attribuer ce rôle.")
        # La cible est verrouillée et son plafond vérifié avant toute lecture de ses appartenances.
        target = User.objects.select_for_update().filter(pk=user_id, is_active=True).first()
        if target is None or moderation_services.is_user_restricted(target.pk):
            raise _unavailable_user_error()
        try:
            _ensure_under_limit(target.pk)
        except OrganizationError:
            raise _unavailable_user_error()
        return _activate_membership(actor, organization, target, role)


# --- Invitations : trace et balayage (le cycle de vie complet est dans `invitations.py`) ------------------------

def _audit_invitation(actor, action, organization, invitation, **extra):
    """Trace d'une invitation : UUID et codes seulement (jamais jeton, étiquette, nom, téléphone, e-mail)."""
    details = f"organization={organization.pk}; role={invitation.role}"
    for key, value in extra.items():
        details += f"; {key}={value}"
    record_audit(
        actor, action, target=invitation, details=details, context=(CONTEXT_ORGANIZATION, organization.pk),
    )


def sweep_invitations_of_inviter(actor, organization, inviter_id, new_role=None, new_scope=None):
    """Révoque (`authority_lost`) les invitations `PENDING` d'un inviteur qui perd son autorité : retiré ou parti
    (`new_role=None` : toutes), ou rétrogradé ou déplacé (`new_role`, `new_scope` : seules celles qu'il ne peut plus
    déléguer, `can_delegate` sur le rôle et le périmètre de l'invitation ; `new_scope=None` = organisation entière ;
    un périmètre partiel n'a plus `org.manage_members` au niveau de l'organisation). Dans la
    transaction de l'appelant ; mise à jour conditionnelle `PENDING -> REVOKED`, étiquette vidée, une trace par
    invitation, aucun événement. C'est du nettoyage : la garantie de sécurité reste la revérification de l'autorité
    à l'acceptation (ADR 0008 §5.1). Renvoie le nombre d'invitations révoquées."""
    now = timezone.now()
    revoked = 0
    inviter_scope = new_scope or capabilities.ORGANIZATION_SCOPE
    for invitation in OrganizationInvitation.objects.filter(
        organization=organization, created_by_id=inviter_id, status=OrganizationInvitation.STATUS_PENDING,
    ).only('id', 'role', 'scope_type', 'scope_id'):
        if (
            new_role is not None and capabilities.role_has_capability(new_role, 'org.manage_members')
            and capabilities.scope_allows(inviter_scope, 'org.manage_members')
            and capabilities.can_delegate(new_role, inviter_scope, invitation.role, membership_scope(invitation))
        ):
            continue
        done = OrganizationInvitation.objects.filter(
            pk=invitation.pk, status=OrganizationInvitation.STATUS_PENDING,
        ).update(
            status=OrganizationInvitation.STATUS_REVOKED, closed_at=now, closed_by=actor, label='', updated_at=now,
        )
        if done:
            revoked += 1
            _audit_invitation(actor, 'INVITATION_REVOKED', organization, invitation, reason='authority_lost')
    return revoked


def _publish_owners_changed(organization, actor):
    """Un siège de propriétaire a bougé : la visibilité publique dépend des propriétaires EFFECTIFS (ADR 0008 §6)."""
    _publish_status_change(organization, STATUS_REASON_OWNERS_CHANGED, actor)


def _effective_owners_before(organization, old_role):
    """Nombre de propriétaires effectifs AVANT une opération qui retire un siège de propriétaire. Sans objet
    (0) si l'organisation n'est pas active : la règle `last_effective_owner` ne la concerne pas."""
    if old_role != ROLE_OWNER or organization.status != Organization.STATUS_ACTIVE:
        return 0
    return count_effective_owners(organization.pk)


def _ensure_not_orphaned(organization, effective_before) -> bool:
    """Règle `last_effective_owner` (ADR 0008 §9), appelée APRÈS l'écriture et sous verrou. Refuse (409) si
    l'organisation active n'a plus aucun propriétaire effectif à cause de l'opération (il y en avait un avant)
    ET a au moins une offre active. Sans offre active, l'opération est permise : renvoie vrai (organisation
    devenue orpheline, tracé `orphaned=true`). Lecture des offres par `marketplace.services` (import local :
    `marketplace` importe `identity.services`)."""
    if organization.status != Organization.STATUS_ACTIVE or effective_before < 1:
        return False
    if count_effective_owners(organization.pk) > 0:
        return False
    from apps.marketplace import services as marketplace_services
    if marketplace_services.seller_has_active_offers(CONTEXT_ORGANIZATION, organization.pk):
        raise _last_effective_owner_error()
    return True


def _apply_role_change(
    actor, organization, membership, new_role, audit_action='MEMBERSHIP_ROLE_CHANGED', reauth=False,
    publish_owners=True, new_scope=None,
):
    """Écrit un changement de rôle (verrou déjà posé, autorisation déjà faite) et vérifie les invariants
    après l'écriture : `last_owner` (zéro propriétaire) puis `last_effective_owner` (ADR 0008 §9) ; une
    transition qui les viole annule la transaction. Un mouvement de propriétaire publie `owners_changed`.
    `new_scope` : nouveau périmètre (None : inchangé) ; un administrateur principal couvre toujours toute
    l'organisation (forcé ici, et garanti en base par `membership_owner_org_scope`)."""
    old_role = membership.role
    old_scope = membership_scope(membership)
    scope = _target_scope(membership, new_role, new_scope)
    if old_role == new_role and scope == old_scope:
        return membership
    effective_before = _effective_owners_before(organization, old_role)
    Membership.objects.filter(pk=membership.pk, status=Membership.STATUS_ACTIVE).update(
        role=new_role, scope_type=scope.type, scope_id=scope.id, updated_at=timezone.now(),
    )
    membership.role = new_role
    membership.scope_type, membership.scope_id = scope.type, scope.id
    orphaned = False
    if old_role == ROLE_OWNER:
        if count_active_owners(organization.pk) < 1:
            raise _last_owner_error(organization)
        orphaned = _ensure_not_orphaned(organization, effective_before)
    _audit_membership(
        actor, audit_action, organization, membership, old_role, new_role, reauth, orphaned, old_scope=old_scope,
    )
    _publish_membership_change(organization, membership, CHANGE_ROLE_CHANGED, old_role, new_role, actor)
    if capabilities.role_has_capability(old_role, 'org.manage_members'):
        # Il a pu inviter : ses invitations en attente sont revues dans la même transaction (ADR 0008 §5.1).
        sweep_invitations_of_inviter(actor, organization, membership.user_id, new_role=new_role, new_scope=scope)
    if publish_owners and ROLE_OWNER in (old_role, new_role):
        _publish_owners_changed(organization, actor)
    return membership


def change_member_role(actor, organization_id, user_id, new_role) -> Membership:
    """Change le rôle d'un membre actif (périmètre inchangé). `org.manage_roles` ; l'administrateur ne manipule que
    ADMIN, EDITOR, ANALYST et MEMBER (R9, R10) ; seul un administrateur principal attribue ou retire OWNER ; jamais
    zéro administrateur principal (R8). Délégation vérifiée sur le rôle et le périmètre (`can_delegate`)."""
    _validate_role(new_role)
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_roles')
        membership = _get_membership(organization, user_id)
        if membership.status != Membership.STATUS_ACTIVE:
            raise OrganizationError("Ce compte n'est pas membre de l'organisation.", 'member_not_found', 404)
        if not (_can_manage_member(actor_membership, membership) and capabilities.can_delegate(
            actor_membership.role, membership_scope(actor_membership), new_role, membership_scope(membership),
        )):
            raise ContextDenied(DENY_PERMISSION, "Vous ne pouvez pas modifier ce rôle.")
        _ensure_target_available(membership.user_id)
        return _apply_role_change(actor, organization, membership, new_role)


def transfer_ownership(actor, organization_id, new_owner_user_id, actor_new_role=capabilities.ROLE_ADMIN) -> Membership:
    """Transfert de propriété = deux changements de rôle (promotion du nouveau propriétaire puis
    rétrogradation de l'acteur), faits par la voie `org.manage_roles` réservée aux propriétaires pour OWNER.
    Une seule transaction, deux événements, une trace `ORG_OWNERSHIP_TRANSFERRED`."""
    _validate_role(actor_new_role)
    if actor_new_role == ROLE_OWNER:
        raise serializers.ValidationError(
            {'role': ["L'administrateur principal sortant doit prendre un autre rôle."]},
        )
    if str(new_owner_user_id) == str(actor.pk):
        raise OrganizationError(
            "Vous êtes déjà administrateur principal.", 'invalid_transfer', status.HTTP_400_BAD_REQUEST,
        )
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_roles', allow_archived=True)
        if actor_membership.role != ROLE_OWNER:
            raise ContextDenied(
                DENY_PERMISSION, "Seul un administrateur principal peut transférer l'administration principale.",
            )
        target = _get_membership(organization, new_owner_user_id)
        if target.status != Membership.STATUS_ACTIVE:
            raise OrganizationError("Ce compte n'est pas membre de l'organisation.", 'member_not_found', 404)
        _ensure_target_available(target.user_id)
        _transfer_core(actor, organization, actor_membership, target, actor_new_role)
    return target


def _transfer_core(actor, organization, actor_membership, target, actor_new_role, reauth=False):
    """Deux changements de rôle et la trace `ORG_OWNERSHIP_TRANSFERRED` (verrou et autorisation déjà faits)."""
    # `owners_changed` n'est publié qu'une fois, après les deux écritures (le transfert est un seul mouvement).
    _apply_role_change(actor, organization, target, ROLE_OWNER, reauth=reauth, publish_owners=False)
    _apply_role_change(actor, organization, actor_membership, actor_new_role, reauth=reauth, publish_owners=False)
    _publish_owners_changed(organization, actor)
    record_audit(
        actor, 'ORG_OWNERSHIP_TRANSFERRED', target=organization,
        details=f"from_user={actor.pk}; to_user={target.user_id}" + ("; reauth=true" if reauth else ""),
        context=(CONTEXT_ORGANIZATION, organization.pk),
    )


def _end_membership(actor, organization, membership, end_reason, audit_action):
    """Passe l'appartenance à REVOKED (mise à jour conditionnelle) et vérifie après coup `last_owner` puis
    `last_effective_owner` (ADR 0008 §9)."""
    old_role = membership.role
    effective_before = _effective_owners_before(organization, old_role)
    now = timezone.now()
    done = Membership.objects.filter(pk=membership.pk, status=Membership.STATUS_ACTIVE).update(
        status=Membership.STATUS_REVOKED, end_reason=end_reason, ended_at=now, ended_by=actor, updated_at=now,
    )
    if not done:
        raise OrganizationError("Ce compte n'est pas membre de l'organisation.", 'member_not_found', 404)
    orphaned = False
    if old_role == ROLE_OWNER:
        # Une organisation archivée n'a plus de vie active : son dernier propriétaire peut la quitter (tracé).
        if organization.status != Organization.STATUS_ARCHIVED and count_active_owners(organization.pk) < 1:
            raise _last_owner_error(organization)
        orphaned = _ensure_not_orphaned(organization, effective_before)
    membership.status, membership.end_reason, membership.ended_at = Membership.STATUS_REVOKED, end_reason, now
    _audit_membership(actor, audit_action, organization, membership, old_role, None, orphaned=orphaned)
    _publish_membership_change(organization, membership, CHANGE_REVOKED, old_role, None, actor)
    if capabilities.role_has_capability(old_role, 'org.manage_members'):
        # Retiré ou parti : ses invitations en attente sont révoquées dans la même transaction (ADR 0008 §5.1).
        sweep_invitations_of_inviter(actor, organization, membership.user_id)
    if old_role == ROLE_OWNER:
        _publish_owners_changed(organization, actor)
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
        if not _can_manage_member(actor_membership, membership):
            raise ContextDenied(DENY_PERMISSION, "Vous ne pouvez pas retirer ce membre.")
        return _end_membership(actor, organization, membership, Membership.END_REMOVED, 'MEMBERSHIP_REVOKED')


def leave_organization(user, organization_id) -> Membership:
    """Sortie volontaire d'un membre (`org.leave`), refusée pour le dernier propriétaire. Autorisée aussi
    pour une organisation suspendue ou archivée (ADR 0006, amendement 1, Q-F4) : jamais bloquée."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        membership = _authorize_member(user, organization, 'org.leave', allow_inactive=True)
        return _end_membership(user, organization, membership, Membership.END_LEFT, 'MEMBERSHIP_REVOKED')


# --- Équipe : opérations par `membership_id` (ADR 0008 §5.2, contrat d'API 1.x) ---------------------------------
# Elles résolvent le membre DANS l'organisation du chemin (autre organisation ou inexistant : 404 identique) et
# réutilisent les mêmes noyaux privés que les fonctions par `user_id` ci-dessus.

_ROLE_ORDER = Case(
    *[When(role=role, then=Value(rank)) for rank, role in enumerate(ROLES)], default=Value(len(ROLES)),
    output_field=IntegerField(),
)


@dataclass(frozen=True)
class TeamList:
    """Liste des membres actifs et ce qu'il faut pour la présenter sans requête par ligne."""

    queryset: object
    can_manage: bool  # l'appelant a `org.manage_members` : `is_last_effective_owner` lui est révélé
    sole_effective_owner_id: Optional[object]  # compte du seul propriétaire effectif (None si zéro, ou plusieurs)


def sole_effective_owner_id(organization_id):
    """Compte du seul propriétaire effectif de l'organisation, sinon None."""
    owners = _effective_owner_ids(organization_id)
    return next(iter(owners)) if len(owners) == 1 else None


def list_members(actor, organization_id) -> TeamList:
    """Membres ACTIFS (`org.view_internal`, tout rôle). Ordre : administrateurs principaux, administrateurs,
    éditeurs, analystes, membres, puis `joined_at`, puis identifiant. Seul `full_name` du compte est lu (abrégé à
    l'affichage)."""
    organization, role = get_organization_for_member(actor, organization_id, 'org.view_internal')
    queryset = Membership.objects.filter(
        organization=organization, status=Membership.STATUS_ACTIVE,
    ).select_related('user').only(
        'id', 'organization', 'user', 'role', 'scope_type', 'scope_id', 'status', 'joined_at', 'user__full_name',
    ).annotate(role_rank=_ROLE_ORDER).order_by('role_rank', 'joined_at', 'id')
    can_manage = capabilities.role_has_capability(role, 'org.manage_members')
    return TeamList(queryset, can_manage, sole_effective_owner_id(organization.pk) if can_manage else None)


def _get_organization(organization_id) -> Organization:
    """Organisation sans verrou ; inexistante = même refus qu'un non-membre."""
    try:
        return Organization.objects.get(pk=organization_id)
    except (Organization.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        raise ContextDenied(DENY_RELATION, "Vous n'êtes pas membre de cette organisation.")


def _get_member(organization, membership_id) -> Membership:
    """Appartenance ACTIVE de CETTE organisation (IDOR : une autre organisation répond comme l'inexistant)."""
    membership = Membership.objects.filter(
        pk=membership_id, organization=organization, status=Membership.STATUS_ACTIVE,
    ).select_related('user').first()
    if membership is None:
        raise OrganizationError("Ce membre est introuvable.", 'member_not_found', status.HTTP_404_NOT_FOUND)
    return membership


def _require_reauthentication(actor, organization, confirm, password, action):
    """Ressaisie du mot de passe (ADR 0008 §8.2) : `confirm` vrai ET `password` (400), puis vérification AVANT
    le verrou (le hachage est lent). Échec : 403 `reauthentication_failed`, compteur d'échecs par compte (429
    au-delà du seuil) et trace `ORG_SENSITIVE_REAUTH_FAILED` hors transaction. Le mot de passe n'est jamais
    journalisé. Pas de fenêtre de confiance."""
    if confirm is not True:
        raise OrganizationError(
            "Confirmez l'opération pour continuer.", 'confirmation_required', status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(password, str) or not password:
        raise OrganizationError(
            "Saisissez votre mot de passe pour confirmer.", 'password_required', status.HTTP_400_BAD_REQUEST,
        )
    key = str(actor.pk)
    REAUTH_FAILURES.acquire(key)  # atomique : la tentative est comptée avant la vérification
    if not actor.check_password(password):
        record_audit(
            actor, 'ORG_SENSITIVE_REAUTH_FAILED', target=organization,
            details=f"organization={organization.pk}; action={action}",
            context=(CONTEXT_ORGANIZATION, organization.pk),
        )
        raise OrganizationError(
            "Mot de passe incorrect.", 'reauthentication_failed', status.HTTP_403_FORBIDDEN,
        )
    REAUTH_FAILURES.success(key)


def _target_scope(membership, new_role, new_scope) -> capabilities.Scope:
    """Périmètre résultant d'un changement de rôle : organisation entière pour OWNER ; sinon celui demandé ; sinon
    (champ absent) le périmètre actuel, inchangé (décision L1-01-B6, contrat §7.2)."""
    if new_role == ROLE_OWNER:
        return capabilities.ORGANIZATION_SCOPE
    return new_scope or membership_scope(membership)


def _resolve_role_change(actor, organization, membership_id, new_role, new_scope):
    """Acteur autorisé (`org.manage_roles`), cible de CETTE organisation, délégation permise sur le rôle et le
    périmètre actuels de la cible comme sur le rôle et le périmètre résultants (`can_delegate`, ADR 0010 §9.1)."""
    actor_membership = _authorize_member(actor, organization, 'org.manage_roles')
    membership = _get_member(organization, membership_id)
    actor_scope = membership_scope(actor_membership)
    target_scope = _target_scope(membership, new_role, new_scope)
    if not (_can_manage_member(actor_membership, membership)
            and capabilities.can_delegate(actor_membership.role, actor_scope, new_role, target_scope)):
        raise ContextDenied(DENY_PERMISSION, "Vous ne pouvez pas modifier ce rôle.")
    _ensure_target_available(membership.user_id)
    return membership


def _role_change_needs_reauth(membership, new_role) -> bool:
    return new_role == ROLE_OWNER or membership.role == ROLE_OWNER


def change_role(
    actor, organization_id, membership_id, new_role, confirm=False, password=None, scope=None,
) -> Membership:
    """Change le rôle d'un membre actif de l'organisation (`org.manage_roles`). L'administrateur ne touche jamais
    un administrateur principal et n'attribue jamais OWNER. Promotion vers OWNER ou rétrogradation d'un OWNER :
    `confirm` et ressaisie du mot de passe. Invariants `last_owner` et `last_effective_owner` vérifiés sous verrou. Même
    rôle et même périmètre : aucun effet, aucune trace. `scope` (contrat §7.2) : périmètre visé ; absent ou nul, le
    périmètre actuel est conservé ; seul `ORGANIZATION` est accepté en V1 (sinon 400 `{"scope": [...]}`)."""
    _validate_role(new_role)
    new_scope = _validate_scope(scope)
    organization = _get_organization(organization_id)
    membership = _resolve_role_change(actor, organization, membership_id, new_role, new_scope)
    if membership.role == new_role and membership_scope(membership) == _target_scope(membership, new_role, new_scope):
        return membership  # même rôle : ni ressaisie, ni quota, ni trace (l'autorisation a déjà été vérifiée)
    reauth = _role_change_needs_reauth(membership, new_role)
    if reauth:
        _require_reauthentication(
            actor, organization, confirm, password,
            REAUTH_PROMOTE_OWNER if new_role == ROLE_OWNER else REAUTH_DEMOTE_OWNER,
        )
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        membership = _resolve_role_change(actor, organization, membership_id, new_role, new_scope)
        if _role_change_needs_reauth(membership, new_role) and not reauth:
            # Le rôle de la cible a changé entre la lecture et le verrou : la ressaisie n'a pas eu lieu.
            raise OrganizationError(
                "Mot de passe incorrect.", 'reauthentication_failed', status.HTTP_403_FORBIDDEN,
            )
        _apply_role_change(actor, organization, membership, new_role, reauth=reauth, new_scope=new_scope)
    return membership


def remove_member(actor, organization_id, membership_id) -> Membership:
    """Retire un membre (`org.manage_members`). Soi-même : 400 `use_leave`. Un administrateur principal ne se retire
    jamais directement (409 `owner_must_be_demoted` : le rétrograder d'abord, ce qui exige la ressaisie du mot de
    passe). Effet immédiat ; les invitations en attente créées par la personne retirée sont révoquées dans la même
    transaction (`sweep_invitations_of_inviter`)."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership = _authorize_member(actor, organization, 'org.manage_members')
        membership = _get_member(organization, membership_id)
        if membership.user_id == actor.pk:
            raise OrganizationError("Utilisez « quitter l'organisation ».", 'use_leave', status.HTTP_400_BAD_REQUEST)
        if not _can_manage_member(actor_membership, membership):
            raise ContextDenied(DENY_PERMISSION, "Vous ne pouvez pas retirer ce membre.")
        if membership.role == ROLE_OWNER:
            raise OrganizationError(
                "Un administrateur principal ne peut pas être retiré directement : rétrogradez-le d'abord.",
                'owner_must_be_demoted',
            )
        return _end_membership(actor, organization, membership, Membership.END_REMOVED, 'MEMBERSHIP_REVOKED')


def _resolve_transfer(actor, organization, membership_id):
    actor_membership = _authorize_member(actor, organization, 'org.manage_roles', allow_archived=True)
    if actor_membership.role != ROLE_OWNER:
        raise ContextDenied(
            DENY_PERMISSION, "Seul un administrateur principal peut transférer l'administration principale.",
        )
    target = _get_member(organization, membership_id)
    if target.user_id == actor.pk:
        raise OrganizationError(
            "Vous êtes déjà administrateur principal.", 'invalid_transfer', status.HTTP_400_BAD_REQUEST,
        )
    _ensure_target_available(target.user_id)
    return actor_membership, target


def transfer_ownership_to(
    actor, organization_id, membership_id, my_new_role=capabilities.ROLE_ADMIN, confirm=False, password=None,
):
    """Transfert de propriété vers un membre actif, par `membership_id` (acteur `OWNER`). `confirm` vrai et
    ressaisie du mot de passe obligatoires. Une transaction : la cible devient OWNER, l'acteur prend
    `my_new_role` (jamais OWNER). Autorisé sur une organisation archivée, refusé sur une suspendue. Renvoie
    `(appartenance de la cible, appartenance de l'acteur)`, rôles à jour."""
    if my_new_role not in TRANSFER_SELF_ROLES:
        raise serializers.ValidationError(
            {'my_new_role': ["Rôle inconnu ou non permis pour l'administrateur principal sortant."]},
        )
    organization = _get_organization(organization_id)
    _resolve_transfer(actor, organization, membership_id)
    _require_reauthentication(actor, organization, confirm, password, REAUTH_TRANSFER)
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        actor_membership, target = _resolve_transfer(actor, organization, membership_id)
        _transfer_core(actor, organization, actor_membership, target, my_new_role, reauth=True)
    actor_membership.user = actor
    return target, actor_membership


def assert_account_removable(user):
    """Refuse la suppression définitive d'un compte (point unique : `UserAdmin`, récepteur `pre_delete`) :
    - 409 `last_owner_account` : seul propriétaire ACTIF d'une organisation active OU suspendue (elle deviendrait
      orpheline) ;
    - 409 `blocking_sanction` : sanction bloquante en cours (on désactive le compte, l'historique de sanction ne
      doit pas disparaître) ;
    - 409 `open_grave_report` : signalement ouvert pour motif grave visant le compte, une de ses offres, un avis qu'il
      a reçu OU écrit, un message qu'il a envoyé, ou ceux de son profil prestataire (preuves à conserver jusqu'à la
      clôture).
    Ne bloque PAS la désactivation (`is_active`). Dette (ADR 0006, section 15) : chemin de secours audité du
    personnel et sort des organisations orphelines, à livrer avec L1-01 / la suppression de compte. Garde sans
    verrou (TOCTOU possible entre le contrôle et la suppression, voir ADR §20)."""
    blockers = account_removal_blockers(user)
    if blockers.organizations:
        raise OrganizationError(
            "Ce compte est le seul administrateur principal d'une organisation active ou suspendue : désignez "
            "d'abord un autre administrateur principal.",
            'last_owner_account',
        )
    if blockers.other_code == 'blocking_sanction':
        raise OrganizationError(
            "Ce compte fait l'objet d'une sanction en cours : désactivez-le plutôt que de le supprimer.",
            'blocking_sanction',
        )
    if blockers.other_code == 'open_grave_report':
        raise _open_report_error()


# `suggested_action` d'un blocage d'organisation (contrat d'API L1-01, section 3).
ACTION_TRANSFER_OWNERSHIP = 'transfer_ownership'
ACTION_ARCHIVE = 'archive'
ACTION_WAIT_FOR_UNSUSPENSION = 'wait_for_unsuspension'


@dataclass(frozen=True)
class OrganizationBlocker:
    organization_id: UUID
    name: str
    status: str
    other_members_count: int
    suggested_action: str


@dataclass(frozen=True)
class AccountRemovalBlockers:
    organizations: tuple
    other_code: Optional[str]  # None, 'blocking_sanction' ou 'open_grave_report' : jamais détaillé


def account_removal_blockers(user, limit=None) -> AccountRemovalBlockers:
    """Décision UNIQUE de suppression d'un compte (lue par `assert_account_removable` et par
    `GET me/account-deletion-blockers/`) : organisations dont le compte est le seul propriétaire actif (active ou
    suspendue), puis premier blocage « autre » (sanction bloquante, puis signalement grave). `limit` ne borne que
    la liste renvoyée (affichage), jamais la décision. Comptage seulement des autres membres, aucune identité."""
    owned = Membership.objects.filter(
        user_id=user.pk, role=ROLE_OWNER, status=Membership.STATUS_ACTIVE,
    ).values('organization_id')
    sole = Organization.objects.filter(
        status__in=(Organization.STATUS_ACTIVE, Organization.STATUS_SUSPENDED), pk__in=owned,
    ).annotate(
        owners=Count(
            'memberships', filter=Q(memberships__role=ROLE_OWNER, memberships__status=Membership.STATUS_ACTIVE),
        ),
        active_members=Count('memberships', filter=Q(memberships__status=Membership.STATUS_ACTIVE)),
    ).order_by(Lower('name'), 'pk')
    rows = []
    for organization in sole:
        if organization.owners > 1:
            continue
        others = max(organization.active_members - 1, 0)
        if organization.status == Organization.STATUS_SUSPENDED:
            action = ACTION_WAIT_FOR_UNSUSPENSION
        elif others > 0:
            action = ACTION_TRANSFER_OWNERSHIP
        else:
            action = ACTION_ARCHIVE
        rows.append(OrganizationBlocker(organization.pk, organization.name, organization.status, others, action))
    other = None
    if moderation_services.is_user_restricted(user.pk):
        other = 'blocking_sanction'
    else:
        provider_id = ProviderProfile.objects.filter(user_id=user.pk).values_list('pk', flat=True).first()
        if (
            moderation_services.has_open_grave_report('user', [user.pk])
            or _context_has_grave_evidence(CONTEXT_USER, user.pk)
            or (provider_id is not None and _context_has_grave_evidence(CONTEXT_PROVIDER, provider_id))
            or _author_has_grave_evidence(user.pk)
        ):
            other = 'open_grave_report'
    return AccountRemovalBlockers(tuple(rows[:limit] if limit is not None else rows), other)


def assert_provider_removable(profile):
    """Refuse la suppression définitive d'un profil prestataire tant qu'un signalement ouvert pour motif grave vise
    une de ses offres ou un de ses avis reçus (409 `open_grave_report`). Il n'existe pas de signalement du profil
    lui-même : la cible « utilisateur » est contrôlée avec le compte."""
    if _context_has_grave_evidence(CONTEXT_PROVIDER, profile.pk):
        raise _open_report_error()


def _open_report_error():
    return OrganizationError(
        "Un signalement grave est en cours : la suppression est impossible tant qu'il n'est pas clos.",
        'open_grave_report',
    )


def _context_has_grave_evidence(context_type, context_id) -> bool:
    """Offres et avis reçus d'un contexte sous signalement grave ouvert. Imports locaux : `marketplace` et `reviews`
    importent `identity.services` (cycle) ; l'appel reste par leurs `services.py`."""
    from apps.marketplace import services as marketplace_services
    from apps.reviews import services as reviews_services
    return (
        marketplace_services.has_open_grave_report_on_seller(context_type, context_id)
        or reviews_services.has_open_grave_report_on_seller(context_type, context_id)
    )


def _author_has_grave_evidence(user_id) -> bool:
    """Avis écrits et messages envoyés par le compte sous signalement grave ouvert (ils partent avec lui par cascade
    de clé étrangère : preuves à conserver)."""
    from apps.messaging import services as messaging_services
    from apps.reviews import services as reviews_services
    return (
        reviews_services.has_open_grave_report_on_author(user_id)
        or messaging_services.has_open_grave_report_on_sender(user_id)
    )
