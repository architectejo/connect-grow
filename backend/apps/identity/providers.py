"""Profil de prestataire individuel (contexte PROVIDER, ADR 0006 sections 4.3, 7 et 9.3).

Un seul profil par compte (unicité inconditionnelle sur `user`). Aucun plan, aucun prix, aucun entitlement
(règle 2) ; le prestataire n'est pas une organisation (pas de membres ni de rôles) : seul le titulaire
agit sur son profil, donc l'autorisation est la propriété du profil, pas une capacité `org.*`. Toute
écriture est atomique, journalisée (`AuditLog`, contexte = le profil) et publie
`identity.seller_context_status_changed` quand le profil devient public ou cesse de l'être. Les `details`
d'audit et les charges utiles d'événements ne contiennent que des UUID et des codes : jamais de nom
affiché, de bio, de téléphone ni d'e-mail (règle 10).

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.common.contexts import CONTEXT_PROVIDER, DENY_OBJECT_STATE, DENY_SECURITY, ContextDenied
from apps.common.exception_handler import CodedAPIException
from apps.moderation.services import is_user_restricted, record_audit
from apps.platform_core.services import publish_event

from .models import ProviderProfile, ProviderProfileCategory, User
from .organizations import (
    STATUS_REASON_ARCHIVED, _error, normalize_name, validate_category_ids,
)

DISPLAY_NAME_MIN_LENGTH = 2
DISPLAY_NAME_MAX_LENGTH = 255
BIO_MAX_LENGTH = 2000

STATUS_REASON_ACTIVATED = 'activated'


class ProviderError(CodedAPIException):
    """Refus métier du prestataire : code en minuscules (ADR 0006, A14)."""


def _not_found():
    return ProviderError("Vous n'avez pas de profil de prestataire.", 'provider_not_found', 404)


# --- Lectures ---------------------------------------------------------------------------------

def get_provider_profile(user) -> ProviderProfile:
    """Profil du compte (actif ou archivé), ou `provider_not_found` (404)."""
    profile = ProviderProfile.objects.filter(user_id=user.pk).first()
    if profile is None:
        raise _not_found()
    return profile


def get_provider_category_ids(provider) -> list:
    """UUID des catégories, triés pour une réponse stable."""
    return sorted(
        ProviderProfileCategory.objects.filter(provider=provider).values_list('category_id', flat=True),
        key=str,
    )


# --- Validation -------------------------------------------------------------------------------

def _validate_display_name(value):
    normalized = normalize_name(value)
    if normalized is None:
        raise serializers.ValidationError({'display_name': _error(
            "Le nom contient un caractère non autorisé.", 'invalid_name',
        )})
    if not DISPLAY_NAME_MIN_LENGTH <= len(normalized) <= DISPLAY_NAME_MAX_LENGTH:
        raise serializers.ValidationError({'display_name': _error(
            f"Le nom doit contenir de {DISPLAY_NAME_MIN_LENGTH} à {DISPLAY_NAME_MAX_LENGTH} caractères.",
            'invalid_name',
        )})
    return normalized


def _validate_bio(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise serializers.ValidationError({'bio': _error("La présentation doit être un texte.", 'invalid_bio')})
    if len(value) > BIO_MAX_LENGTH:
        raise serializers.ValidationError({'bio': _error(
            f"La présentation ne doit pas dépasser {BIO_MAX_LENGTH} caractères.", 'invalid_bio',
        )})
    return value.strip()


def _ensure_account_allowed(user):
    if not user.is_active:
        raise ContextDenied(DENY_SECURITY, "Votre compte est désactivé.")
    if is_user_restricted(user.pk):
        raise ContextDenied(DENY_SECURITY, "Votre compte fait l'objet d'une restriction.")


def _default_display_name(user):
    """Forme publique du nom du compte (« Marie K. »), jamais le nom complet (règle 10) ; repli
    « Utilisateur » si elle est invalide ou trop courte."""
    from .services import public_display_name

    candidate = normalize_name(public_display_name(user.full_name))
    if not candidate or len(candidate) < DISPLAY_NAME_MIN_LENGTH:
        return "Utilisateur"
    return candidate[:DISPLAY_NAME_MAX_LENGTH]


def _set_categories(profile, wanted):
    ProviderProfileCategory.objects.filter(provider=profile).exclude(category_id__in=wanted).delete()
    existing = set(ProviderProfileCategory.objects.filter(provider=profile).values_list('category_id', flat=True))
    ProviderProfileCategory.objects.bulk_create([
        ProviderProfileCategory(provider=profile, category_id=cid) for cid in wanted if cid not in existing
    ])


def _publish_status_change(profile, reason, actor):
    publish_event(
        'identity.seller_context_status_changed', aggregate_type='provider', aggregate_id=profile.pk,
        payload={
            'context_type': CONTEXT_PROVIDER, 'context_id': str(profile.pk), 'reason': reason,
            'actor_id': str(actor.pk) if actor is not None else None,
        },
    )


def _lock_profile(user) -> ProviderProfile:
    profile = ProviderProfile.objects.select_for_update().filter(user_id=user.pk).first()
    if profile is None:
        raise _not_found()
    return profile


# --- Cycle de vie -----------------------------------------------------------------------------

def activate_provider(user, display_name=None, bio=None, category_ids=None, fields=None):
    """Active (ou réactive) le profil prestataire du compte. Retourne `(profil, created)`.

    - aucun profil : création `ACTIVE` (`created=True`), audit `PROVIDER_ACTIVATED` ;
    - profil déjà actif : idempotent, rien n'est modifié ni journalisé ;
    - profil archivé : réactivé, les champs fournis sont appliqués, audit `PROVIDER_ACTIVATED`.
    `fields` : ensemble des clés réellement envoyées (distingue « absent » de « vide »). Nom par défaut :
    la forme publique du nom du compte (« Marie K. »), jamais le nom complet (règle 10).
    Exigences : compte actif et sans restriction. Le téléphone vérifié n'est pas exigé (ADR 0006 : réservé
    à la création d'organisation, Q-CP5)."""
    fields = set(fields) if fields is not None else {
        key for key, value in (('display_name', display_name), ('bio', bio), ('category_ids', category_ids))
        if value is not None
    }
    existing = ProviderProfile.objects.filter(user_id=user.pk).first()
    if existing is not None and existing.status == ProviderProfile.STATUS_ACTIVE:
        _ensure_account_allowed(user)
        return existing, False
    _ensure_account_allowed(user)

    if 'display_name' in fields and display_name is not None:
        name = _validate_display_name(display_name)
    elif 'display_name' in fields:
        raise serializers.ValidationError({'display_name': _error("Le nom est obligatoire.", 'invalid_name')})
    else:
        name = None
    new_bio = _validate_bio(bio) if 'bio' in fields else None
    wanted = validate_category_ids(category_ids) if 'category_ids' in fields else None

    with transaction.atomic():
        locked_user = User.objects.select_for_update().filter(pk=user.pk).first()  # sérialise les activations
        _ensure_account_allowed(locked_user or user)  # état du compte relu après verrou (ADR 6.4)
        profile = ProviderProfile.objects.select_for_update().filter(user_id=user.pk).first()
        if profile is not None and profile.status == ProviderProfile.STATUS_ACTIVE:
            return profile, False  # une requête concurrente a déjà activé
        created = profile is None
        if created:
            profile = ProviderProfile(
                user=user, display_name=name or _default_display_name(user),
                bio=new_bio or '', status=ProviderProfile.STATUS_ACTIVE,
            )
            try:
                with transaction.atomic():
                    profile.save()
            except IntegrityError:  # unicité inconditionnelle sur le compte : doublon concurrent
                profile = ProviderProfile.objects.get(user_id=user.pk)
                return profile, False
        else:
            if name is not None:
                profile.display_name = name
            if new_bio is not None:
                profile.bio = new_bio
            profile.status = ProviderProfile.STATUS_ACTIVE
            profile.archived_at = None
            profile.save(update_fields=['display_name', 'bio', 'status', 'archived_at', 'updated_at'])
        if wanted is not None:
            _set_categories(profile, wanted)
        record_audit(
            user, 'PROVIDER_ACTIVATED', target=profile,
            details=f"provider={profile.pk}; reactivated={'no' if created else 'yes'}",
            context=(CONTEXT_PROVIDER, profile.pk),
        )
        _publish_status_change(profile, STATUS_REASON_ACTIVATED, user)
    return profile, created


def update_provider(user, **changes) -> ProviderProfile:
    """Modifie `display_name`, `bio` et/ou `category_ids` (seules les clés présentes). Refus si le profil
    est archivé (`DENY_OBJECT_STATE`), le compte désactivé ou restreint (`DENY_SECURITY`). L'audit ne
    note que les noms des champs modifiés, jamais leur valeur."""
    unknown = set(changes) - {'display_name', 'bio', 'category_ids'}
    if unknown:
        raise serializers.ValidationError({k: _error("Champ non modifiable.", 'read_only') for k in unknown})
    profile = get_provider_profile(user)
    if profile.status != ProviderProfile.STATUS_ACTIVE:
        raise ContextDenied(DENY_OBJECT_STATE, "Ce profil de prestataire est archivé.")
    _ensure_account_allowed(user)

    name = _validate_display_name(changes['display_name']) if 'display_name' in changes else None
    new_bio = _validate_bio(changes['bio']) if 'bio' in changes else None
    wanted = validate_category_ids(changes['category_ids']) if 'category_ids' in changes else None

    with transaction.atomic():
        locked_user = User.objects.select_for_update().filter(pk=user.pk).first()
        _ensure_account_allowed(locked_user or user)
        profile = _lock_profile(user)
        if profile.status != ProviderProfile.STATUS_ACTIVE:
            raise ContextDenied(DENY_OBJECT_STATE, "Ce profil de prestataire est archivé.")
        touched = []
        if name is not None:
            profile.display_name = name
            touched.append('display_name')
        if new_bio is not None:
            profile.bio = new_bio
            touched.append('bio')
        if touched:
            profile.save(update_fields=touched + ['updated_at'])
        if wanted is not None:
            _set_categories(profile, wanted)
            touched.append('category_ids')
        if touched:
            record_audit(
                user, 'PROVIDER_UPDATED', target=profile,
                details=f"provider={profile.pk}; fields={','.join(touched)}",
                context=(CONTEXT_PROVIDER, profile.pk),
            )
    return profile


def archive_provider(user) -> ProviderProfile:
    """Archive le profil (données et avis conservés ; les offres cessent d'être publiques via l'abonné
    de `identity.seller_context_status_changed`). Idempotent. Permis même à un compte restreint : se
    retirer n'est jamais un risque."""
    get_provider_profile(user)
    with transaction.atomic():
        profile = _lock_profile(user)
        if profile.status == ProviderProfile.STATUS_ARCHIVED:
            return profile
        profile.status = ProviderProfile.STATUS_ARCHIVED
        profile.archived_at = timezone.now()
        profile.save(update_fields=['status', 'archived_at', 'updated_at'])
        record_audit(
            user, 'PROVIDER_ARCHIVED', target=profile, details=f"provider={profile.pk}",
            context=(CONTEXT_PROVIDER, profile.pk),
        )
        _publish_status_change(profile, STATUS_REASON_ARCHIVED, user)
    return profile
