"""Interface publique du domaine `identity` (sessions, jetons, fiches publiques de vendeurs)."""
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable, Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.moderation.services import record_audit

# Contexte actif (ADR 0006, section 6) : façade publique.
from .acting import (  # noqa: F401
    ActingContextMixin, AvailableContext, authorize, authorize_on, can, capability_permission, get_acting_context,
    get_contexts_for_user, get_unavailable_organizations, resolve_acting_context,
)

# Organisations et équipes (ADR 0006) : façade publique, les autres domaines n'importent jamais le sous-module.
from .organizations import (  # noqa: F401
    OrganizationError, SUSPENSION_REASONS, add_member, assert_account_removable, assert_provider_removable,
    archive_organization, change_member_role, change_role, count_effective_owners, list_members, remove_member,
    sole_effective_owner_id, transfer_ownership_to, TeamList,
    count_active_owners, create_organization, get_active_role, get_identity_settings, get_organization_for_member,
    leave_organization, reactivate_organization, revoke_member, suspend_organization, transfer_ownership,
    update_organization,
)

# Invitations d'équipe (ADR 0008) : façade publique.
from .invitations import (  # noqa: F401
    accept_invitation, create_invitation, decline_invitation, effective_status, list_invitations, preview_invitation,
    revoke_invitation,
)

# Lectures des organisations : état de vérification dérivé, liste publique, limites (ADR 0006, 9.2 et 17.2).
from .organization_reads import (  # noqa: F401
    get_category_ids_by_organization, get_internal_verification, get_organization_limits, get_verification_data,
    public_organizations_queryset,
)

# Vérification des organisations (ADR 0006, A6, 9.4) : façade publique.
from .verification import (  # noqa: F401
    delete_kyb_document, get_organization_verification, get_verification_summaries, get_verified_claims,
    list_kyb_documents, submit_kyb_document,
)

from .capabilities import CAP_ORG_LEAVE  # noqa: F401

# Contextes vendeur : fiches publiques, visibilité, destinataires, canaux, état du compte (ADR 0006, 7.1).
from .sellers import (  # noqa: F401
    SellerSummary, context_has_capability, ensure_seller_context_accepts_contact, get_accessible_organization_ids,
    get_contact_accounts,
    get_context_allowed_channels, get_context_contact_endpoint, get_context_recipients,
    get_seller_context_public_flags, get_seller_summaries, get_user_context_roles, is_seller_context_public,
    set_account_active, announce_account_status, announce_seller_context_removed,
    seller_context_exists,
)

# Lectures par lot des contextes (droits, comptes agissant, destinataires d'équipe, noms) : ADR 0006, 9.8 et 19.3.
from .context_reads import (  # noqa: F401
    get_active_organization_ids, get_capable_contexts, get_context_member_accounts, get_context_names,
    get_document_type_label, get_organization_recipients, get_role_label,
)

# Prestataire individuel (ADR 0006, 9.3) : façade publique.
from .providers import (  # noqa: F401
    ProviderError, activate_provider, archive_provider, get_provider_category_ids, get_provider_profile,
    update_provider,
)


def revoke_all_sessions(user) -> int:
    """Révoque tous les refresh tokens en cours de `user` (déconnexion de tous les
    appareils, changement ou réinitialisation de mot de passe). Renvoie le nombre
    de jetons ciblés (approximatif : une révocation concurrente du même jeton est ignorée par
    `ignore_conflicts` mais reste comptée). Les jetons d'accès déjà émis expirent d'eux-mêmes (15 min).

    Atomique et sans course : une révocation simultanée du même jeton (autre requête,
    autre processus) est ignorée par `ignore_conflicts` au lieu de lever une erreur."""
    with transaction.atomic():
        tokens = list(OutstandingToken.objects.filter(user=user).exclude(blacklistedtoken__isnull=False))
        BlacklistedToken.objects.bulk_create([BlacklistedToken(token=t) for t in tokens], ignore_conflicts=True)
    return len(tokens)


def validate_new_password(password, user=None) -> None:
    """Applique les validateurs de mot de passe de Django (AUTH_PASSWORD_VALIDATORS).
    Lève rest_framework.serializers.ValidationError (liste de messages en français).
    Refuse aussi un mot de passe absent ou vide."""
    from django.contrib.auth import password_validation
    from django.core.exceptions import ValidationError as DjangoValidationError
    from rest_framework import serializers

    if not isinstance(password, str) or not password.strip():
        raise serializers.ValidationError(["Le mot de passe est requis."])
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))


class KycError(Exception):
    """Refus métier d'une décision KYC (message en français + code HTTP)."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


INTEREST_CONFLICT_MESSAGE = (
    "Vous ne pouvez pas traiter une pièce d'une organisation dont vous êtes ou avez été membre, ni une pièce que "
    "vous avez déposée."
)


def has_interest_conflict(doc, organization, reviewer) -> bool:
    """Conflit d'intérêts du personnel sur une pièce d'organisation (ADR 0006, 7.2) : déposant, créateur de
    l'organisation, ou toute ligne d'appartenance de tout statut (actif ou ancien membre, sans limite de durée)."""
    from .models import Membership

    return bool(
        doc.uploaded_by_id == reviewer.pk or organization.created_by_id == reviewer.pk
        or Membership.objects.filter(organization=organization, user_id=reviewer.pk).exists()
    )


def get_document_for_download(document_id, reviewer):
    """Pièce que `reviewer` peut télécharger. Même règle de conflit d'intérêts que la décision : le refus est
    journalisé (`KYC_DOWNLOAD_DENIED`) puis renvoyé en 403."""
    from apps.common.contexts import CONTEXT_ORGANIZATION
    from .models import KycDocument

    try:
        doc = KycDocument.objects.select_related('organization').get(pk=document_id)
    except KycDocument.DoesNotExist:
        raise KycError("Document introuvable.", 404)
    organization = doc.organization
    if has_interest_conflict(doc, organization, reviewer):
        record_audit(
            reviewer, 'KYC_DOWNLOAD_DENIED', target=doc,
            details=f"organization={organization.pk}; reason=interest_conflict",
            context=(CONTEXT_ORGANIZATION, organization.pk),
        )
        raise KycError(INTEREST_CONFLICT_MESSAGE, 403)
    return doc


def decide_kyc_document(document_id, reviewer, decision, reason=''):
    """Décision (VALIDE ou REFUSE) sur une pièce KYC ou KYB, atomique avec son journal d'audit.

    Pièce d'organisation (ADR 0006, 7.2) : refus (403) si le décideur a une ligne d'appartenance à
    l'organisation (actif ou ancien membre, sans limite de durée), s'il a déposé la pièce ou s'il a créé
    l'organisation. Les claims ne sont jamais écrits : ils sont calculés à la lecture. Un événement
    `identity.organization_verification_changed` est publié dans la même transaction.

    `reason` (500 caractères au plus) est visible du déposant : il ne doit contenir AUCUNE donnée personnelle
    (nom, numéro, adresse). Une liste codée de motifs est une dette suivie pour L1-xx (ADR 0006, amendement T4)."""
    from django.db import transaction
    from apps.common.contexts import CONTEXT_ORGANIZATION
    from apps.platform_core.services import publish_event
    from .models import KycDocument, Organization

    if decision not in (KycDocument.STATUS_VALIDE, KycDocument.STATUS_REFUSE):
        raise KycError("decision doit être VALIDE ou REFUSE.")
    if len(reason) > KycDocument.REASON_MAX_LENGTH:
        raise KycError(f"Le motif ne doit pas dépasser {KycDocument.REASON_MAX_LENGTH} caractères.")

    with transaction.atomic():
        try:
            doc = KycDocument.objects.get(pk=document_id)
        except KycDocument.DoesNotExist:
            raise KycError("Document introuvable.", 404)

        # Verrou de l'organisation : deux décisions sur ses pièces se suivent l'une après l'autre.
        organization = Organization.objects.select_for_update().get(pk=doc.organization_id)
        if has_interest_conflict(doc, organization, reviewer):
            raise KycError(INTEREST_CONFLICT_MESSAGE, 403)
        if organization.status != Organization.STATUS_ACTIVE:
            # Une vérification ne s'accorde pas à une organisation suspendue ou archivée (règle 3).
            raise KycError("Cette organisation n'est pas active : la pièce ne peut pas être décidée.", 409)

        previous = doc.status
        revoking = previous == KycDocument.STATUS_VALIDE and decision == KycDocument.STATUS_REFUSE
        if previous != KycDocument.STATUS_EN_ATTENTE and not revoking:
            raise KycError("Cette pièce a déjà fait l'objet d'une décision.", 409)
        if decision == KycDocument.STATUS_REFUSE and not reason:
            raise KycError("Un motif est requis pour refuser ou révoquer une pièce.")

        # Mise à jour conditionnelle : deux décisions simultanées ne passent pas toutes les deux.
        now = timezone.now()
        updated = KycDocument.objects.filter(pk=doc.pk, status=previous).update(
            status=decision,
            rejection_reason=reason if decision == KycDocument.STATUS_REFUSE else '',
            reviewed_by=reviewer, reviewed_at=now, updated_at=now,
        )
        if not updated:
            raise KycError("Cette pièce a déjà fait l'objet d'une décision.", 409)
        doc.refresh_from_db()

        action = 'KYC_REVOKED' if revoking else f'KYC_{decision}'
        record_audit(
            reviewer, action, target=doc,
            details=f"organization={organization.pk}; document_type={doc.document_type}; decision={decision}",
            context=(CONTEXT_ORGANIZATION, organization.pk),
        )
        publish_event(
            'identity.organization_verification_changed', aggregate_type='organization',
            aggregate_id=organization.pk,
            payload={
                'organization_id': str(organization.pk), 'document_type': doc.document_type,
                'decision': 'REVOKED' if revoking else decision,
            },
        )
    return doc


def get_full_names(ids: Iterable) -> dict:
    """Noms complets indexés par UUID (une requête) ; un compte absent n'apparaît pas."""
    from apps.common.utils import parse_uuid

    from .models import User

    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return dict(User.objects.filter(id__in=wanted).values_list('id', 'full_name'))


def acts_for_context(user_id, context_type, context_id) -> bool:
    """Vrai si ce compte agit pour le contexte désigné (ADR 0006, 7.1) : `USER` = soi-même ; `PROVIDER` =
    titulaire du profil (même archivé) ; `ORGANIZATION` = membre ACTIF, de tout rôle, d'une organisation non
    suspendue. Faux sinon (dont membre révoqué). Sert au refus « je ne note pas et ne contacte pas ma
    propre offre ». Aucun cache : relu en base à chaque appel.

    NE PAS L'UTILISER POUR AUTORISER UNE ÉCRITURE : elle ignore le rôle, l'état du compte et, contrairement
    à la résolution du contexte actif, tolère une organisation archivée et un profil prestataire archivé.
    Pour autoriser, utiliser `can` / `authorize_on` (capacité du rôle réel)."""
    from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER
    from apps.common.utils import parse_uuid

    from .models import Membership, Organization, ProviderProfile

    user_uuid, context_uuid = parse_uuid(user_id), parse_uuid(context_id)
    if user_uuid is None or context_uuid is None or user_id is None or context_id is None:
        return False
    if context_type == CONTEXT_USER:
        return user_uuid == context_uuid
    if context_type == CONTEXT_PROVIDER:
        return ProviderProfile.objects.filter(pk=context_uuid, user_id=user_uuid).exists()
    if context_type == CONTEXT_ORGANIZATION:
        return Membership.objects.filter(
            user_id=user_uuid, organization_id=context_uuid, status=Membership.STATUS_ACTIVE,
        ).exclude(organization__status=Organization.STATUS_SUSPENDED).exists()
    return False


def public_display_name(full_name) -> str:
    """Nom affiché publiquement pour un auteur : prénom et initiale du nom (« Marie K. »).
    Valeur par défaut en attendant la décision du client (D11) ; fonction unique pour que le
    changement de règle ne touche qu'ici. Un nom d'un seul mot est conservé tel quel."""
    parts = (full_name or '').split()
    if not parts:
        return "Utilisateur"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0].upper()}."


REQUESTER_NAME_MAX_LENGTH = 20
REQUESTER_NAME_FALLBACK = "Un visiteur"


def requester_display_name(full_name) -> str:
    """Nom du demandeur montré au vendeur dans « mes révélations » (ADR 0005). Le nom est saisi
    librement : on borne le premier mot et on ne garde que lettres, tiret et apostrophe, pour
    qu'il ne serve pas à glisser un numéro, une URL ou un message. Repli : « Un visiteur »."""
    def clean(word):
        return ''.join(c for c in word if c.isalpha() or c in "-'’").strip("-'’")

    parts = [clean(word) for word in (full_name or '').split()]
    parts = [word for word in parts if word]
    if not parts:
        return REQUESTER_NAME_FALLBACK
    first = parts[0][:REQUESTER_NAME_MAX_LENGTH]
    if len(parts) == 1:
        return first
    return f"{first} {parts[-1][0].upper()}."


def get_report_labels(ids: Iterable) -> dict:
    """Libellés de comptes signalables, indexés par UUID (une requête) : sert à la modération.
    Un compte absent n'apparaît pas dans le résultat."""
    from apps.common.utils import parse_uuid

    from .models import User

    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    # Jamais d'e-mail ni de téléphone dans un libellé (données personnelles par finalité).
    return {
        user.id: (user.full_name or '').strip() or f"Utilisateur {str(user.id)[:8]}"
        for user in User.objects.filter(id__in=wanted)
    }


def count_users() -> int:
    """Nombre de comptes (tableau de bord de modération)."""
    from .models import User

    return User.objects.count()


def count_pending_kyc_documents() -> int:
    """Nombre de pièces KYC en attente de décision (tableau de bord de modération)."""
    from .models import KycDocument

    return KycDocument.objects.filter(status=KycDocument.STATUS_EN_ATTENTE).count()


def get_report_authors(ids: Iterable) -> dict:
    """Un compte est son propre auteur : `{compte: compte}` pour les comptes existants."""
    return {user_id: user_id for user_id in get_report_labels(ids)}


# --- Contact vendeur : numéro de contact et consentement par canal (ADR 0005, ADR 0006 4.4 et 11.2) --------

CHANNEL_ORDER = ('MESSAGE', 'CALL', 'WHATSAPP')
NUMBER_CHANNELS = ('CALL', 'WHATSAPP')  # canaux qui révèlent le numéro

CAP_MANAGE_CHANNELS = 'contact.manage_channels'


class ContactSettingsError(Exception):
    """Refus métier des réglages de contact : message français + code machine + statut HTTP."""

    def __init__(self, message, code, status_code=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ChannelNotConsented(Exception):
    """Le vendeur n'a pas activé ce canal, ou son numéro n'est pas vérifié (ADR 0005, C5)."""


@dataclass(frozen=True)
class ContactEndpoint:
    """Numéro à remettre au visiteur. Ne jamais journaliser ni publier dans un événement."""

    phone_e164: str

    def __repr__(self):
        return "ContactEndpoint(phone_e164=<masqué>)"


def mask_phone(phone) -> Optional[str]:
    """Numéro masqué pour l'écran de réglages : « +243 81 *** ** 45 ». Hors indicatif +243, seuls
    4 chiffres restent visibles (jamais le numéro complet, même pour son titulaire)."""
    if not phone or not isinstance(phone, str) or len(phone) != 13 or not phone.startswith('+243'):
        return None
    digits = phone[4:]
    return f"+243 {digits[:2]} *** ** {digits[-2:]}"


def get_available_channels(context_type) -> list:
    """Canaux que ce type de contexte a le droit de configurer (ADR 0006, Q-F3), indépendamment de l'état actuel
    (numéro, consentement). `USER` et `PROVIDER` : les trois. `ORGANIZATION` : `MESSAGE` seulement tant que
    `IdentitySettings.org_phone_channels_enabled` est faux (Q-CLI5), les trois sinon. Source unique, partagée avec
    `get_context_allowed_channels`."""
    from apps.common.contexts import CONTEXT_ORGANIZATION

    if context_type == CONTEXT_ORGANIZATION and not get_identity_settings().org_phone_channels_enabled:
        return ['MESSAGE']
    return list(CHANNEL_ORDER)


class _Owner:
    """Titulaire des réglages de contact pour une opération : le compte de l'acteur (contexte personnel ou
    prestataire, mêmes `ContactPoint`/`ContactConsent`) ou l'organisation du contexte actif. Le numéro d'une
    organisation n'est JAMAIS celui d'un membre (règle 10)."""

    def __init__(self, actor, context=None):
        from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_USER

        self.actor = actor
        self.context = context
        self.organization_id = context.id if context is not None and context.type == CONTEXT_ORGANIZATION else None
        self.context_type = context.type if context is not None else CONTEXT_USER
        self.context_id = context.id if context is not None else actor.pk

    @property
    def is_organization(self) -> bool:
        return self.organization_id is not None

    @property
    def lookup(self) -> dict:
        return {'organization_id': self.organization_id} if self.is_organization else {'user': self.actor}

    def authorize_write(self, allow_restricted=False) -> None:
        """Écriture sur le contact d'une organisation : capacité revérifiée en base, sous la transaction,
        juste avant d'écrire (révocation ou suspension survenue entre-temps, ADR 0006, 6.4). `allow_restricted` :
        le retrait d'un consentement reste permis à un compte restreint (ADR 0005, C4)."""
        if self.is_organization:
            from apps.common.contexts import CONTEXT_ORGANIZATION

            authorize_on(
                self.actor, CONTEXT_ORGANIZATION, self.organization_id, CAP_MANAGE_CHANNELS,
                allow_restricted=allow_restricted,
            )

    def lock_organization(self) -> None:
        if self.is_organization:
            from .models import Organization

            Organization.objects.select_for_update().filter(pk=self.organization_id).first()

    def audit(self, user_action, organization_action, details) -> None:
        """Compte : actions `contact.*` historiques, cible = le compte. Organisation : `CONTACT_*`, cible =
        l'organisation, avec le contexte (ADR 0006, A10). Jamais de numéro ni de nom dans `details`."""
        if self.is_organization:
            from apps.common.contexts import CONTEXT_ORGANIZATION

            from .models import Organization

            record_audit(
                self.actor, organization_action, target=Organization(pk=self.organization_id), details=details,
                context=(CONTEXT_ORGANIZATION, self.organization_id),
            )
        else:
            record_audit(self.actor, user_action, target=self.actor, details=details)

    def describe(self) -> dict:
        return {'type': self.context_type, 'id': str(self.context_id)}


def _channel_state(consent, channel):
    if channel == 'MESSAGE':
        return {'enabled': True if consent is None else consent.is_granted}
    if consent is None:
        return {'enabled': False, 'granted_at': None, 'text_version': ''}
    return {
        'enabled': consent.is_granted,
        'granted_at': consent.granted_at if consent.is_granted else None,
        'text_version': consent.text_version if consent.is_granted else '',
    }


def get_contact_settings(user, context=None) -> dict:
    """État complet de l'écran « Contact » (ADR 0005, 5.1) du contexte actif (`context` : `ActingContext`, ou
    None pour le compte). Numéros toujours masqués. Ajoute `context` et `available_channels` (ADR 0006, 17.1).
    Organisation : jamais le numéro de connexion de l'acteur (`login_phone_masked` nul), et `MESSAGE` toujours actif."""
    from .models import CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint

    owner = _Owner(user, context)
    point = ContactPoint.objects.filter(**owner.lookup).first()
    consents = {c.channel: c for c in ContactConsent.objects.filter(**owner.lookup)}
    if owner.is_organization:
        login_masked, can_use_login = None, False
    else:
        login_masked = mask_phone(user.phone)
        can_use_login = bool(user.phone) and user.phone_verified
    phone = None
    if point is not None:
        phone = {
            'masked': mask_phone(point.phone), 'is_verified': point.is_verified,
            'login_phone_masked': login_masked, 'can_use_login_phone': can_use_login,
        }
    channels = {ch: _channel_state(consents.get(ch), ch) for ch in CHANNEL_ORDER}
    if owner.is_organization:
        channels['MESSAGE'] = {'enabled': True}
    return {
        'phone': phone,
        # Au niveau racine aussi : `phone` vaut null tant qu'aucun numéro de contact n'existe.
        'login_phone_masked': login_masked,
        'can_use_login_phone': can_use_login,
        'channels': channels,
        'current_text_version': CONTACT_CONSENT_TEXT_VERSION,
        'context': owner.describe(),
        'available_channels': get_available_channels(owner.context_type),
    }


def _revoke_number_channels(owner, reason) -> list:
    from .models import ContactConsent

    revoked = []
    now = timezone.now()
    for consent in ContactConsent.objects.filter(**owner.lookup, channel__in=NUMBER_CHANNELS, is_granted=True):
        consent.is_granted = False
        consent.revoked_at = now
        consent.revoked_reason = reason
        consent.save(update_fields=['is_granted', 'revoked_at', 'revoked_reason', 'updated_at'])
        owner.audit(
            'contact.consent_revoked', 'CONTACT_CHANNEL_CHANGED',
            f"Canal {consent.channel} retiré (motif : {reason}).",
        )
        revoked.append(consent.channel)
    return revoked


def _send_contact_code(phone) -> None:
    import logging

    from .models import OtpCode
    from .sms import send_otp_sms

    _, code = OtpCode.issue(phone, OtpCode.PURPOSE_CONTACT_VERIFY)
    try:
        send_otp_sms(phone, code, OtpCode.PURPOSE_CONTACT_VERIFY)
    except Exception:  # passerelle SMS absente ou en panne : le code reste redemandable
        logging.getLogger(__name__).exception("Échec d'envoi du SMS de vérification du numéro de contact.")


def _can_send_contact_sms(user) -> bool:
    """Un SMS vers un numéro saisi n'est envoyé qu'à un compte assez ancien ou déjà doté d'un
    identifiant vérifié (anti-SMS arbitraire, audit M2). Ancienneté : `CONTACT_SMS_MIN_ACCOUNT_AGE_HOURS`."""
    if user.phone_verified:
        return True
    min_age = timedelta(hours=settings.CONTACT_SMS_MIN_ACCOUNT_AGE_HOURS)
    return timezone.now() - user.date_joined >= min_age


def _lock_or_create_point(owner, number, verified, now):
    """Renvoie `(point, created)`. Verrouille la ligne existante ; une création concurrente
    (unicité du titulaire) est rattrapée par une relecture au lieu d'une erreur 500."""
    from .models import ContactPoint

    point = ContactPoint.objects.select_for_update().filter(**owner.lookup).first()
    if point is not None:
        return point, False
    try:
        with transaction.atomic():
            point = ContactPoint.objects.create(
                **owner.lookup, phone=number, is_verified=verified, verified_at=now if verified else None,
            )
        return point, True
    except IntegrityError:
        return ContactPoint.objects.select_for_update().get(**owner.lookup), False


def set_contact_phone(user, *, phone=None, use_login_phone=False, context=None) -> None:
    """Crée ou remplace le numéro de contact du contexte actif. Seul un geste explicite copie le numéro de
    connexion (jamais pour une organisation : le numéro d'un membre n'est pas celui de l'organisation). Changer
    de numéro révoque CALL et WHATSAPP ; un numéro non vérifié reçoit un code SMS."""
    from django.core.exceptions import ValidationError as DjangoValidationError

    from .models import phone_validator

    owner = _Owner(user, context)
    if bool(use_login_phone) == bool(phone):
        raise ContactSettingsError(
            "Indiquez un numéro, ou demandez à utiliser votre numéro de connexion.", 'phone_invalid',
        )
    verified_at_once = False
    if use_login_phone:
        if owner.is_organization:
            raise ContactSettingsError(
                "Le numéro de connexion d'un membre ne peut pas servir de numéro d'organisation.",
                'login_phone_not_allowed',
            )
        if not user.phone or not user.phone_verified:
            raise ContactSettingsError(
                "Vérifiez d'abord votre numéro de connexion.", 'login_phone_unverified', 409,
            )
        number = user.phone
        verified_at_once = True
    else:
        number = phone.strip() if isinstance(phone, str) else None
        try:
            if not number:
                raise DjangoValidationError("invalide")
            phone_validator(number)
        except DjangoValidationError:
            raise ContactSettingsError(
                "Numéro invalide. Format attendu : +243XXXXXXXXX.", 'phone_invalid',
            )
        if not _can_send_contact_sms(user):
            raise ContactSettingsError(
                "Votre compte est trop récent pour recevoir un code par SMS. Réessayez plus tard, "
                "ou vérifiez d'abord votre numéro de connexion.", 'account_too_new', 403,
            )

    send_code = False
    with transaction.atomic():
        owner.lock_organization()
        owner.authorize_write()
        now = timezone.now()
        point, created = _lock_or_create_point(owner, number, verified_at_once, now)
        if not created and point.phone == number:
            # Même numéro : aucun canal n'est révoqué ; un numéro non vérifié reçoit un nouveau code.
            if not point.is_verified:
                if verified_at_once:
                    point.is_verified, point.verified_at = True, now
                    point.save(update_fields=['is_verified', 'verified_at', 'updated_at'])
                    owner.audit(
                        'contact.phone_verified', 'CONTACT_PHONE_VERIFIED',
                        "Numéro de contact vérifié (numéro de connexion déjà vérifié).",
                    )
                else:
                    send_code = True
        else:
            if not created:
                point.phone = number
                point.is_verified = verified_at_once
                point.verified_at = now if verified_at_once else None
                point.save(update_fields=['phone', 'is_verified', 'verified_at', 'updated_at'])
            _revoke_number_channels(owner, 'phone_changed')
            owner.audit(
                'contact.phone_changed', 'CONTACT_PHONE_CHANGED',
                "Numéro de contact modifié ; CALL et WHATSAPP désactivés.",
            )
            if verified_at_once:
                owner.audit(
                    'contact.phone_verified', 'CONTACT_PHONE_VERIFIED',
                    "Numéro de contact vérifié (numéro de connexion déjà vérifié).",
                )
            else:
                send_code = True
    if send_code:
        _send_contact_code(number)


def verify_contact_phone(user, code, context=None) -> None:
    """Valide le numéro de contact par le code SMS. Ne réactive aucun canal."""
    from .models import ContactPoint, OtpCode

    owner = _Owner(user, context)
    point = ContactPoint.objects.filter(**owner.lookup).first()
    if point is None:
        raise ContactSettingsError("Aucun numéro de contact à vérifier.", 'contact_phone_missing', 404)
    if point.is_verified:
        return
    otp = (
        OtpCode.objects.filter(phone=point.phone, purpose=OtpCode.PURPOSE_CONTACT_VERIFY, is_used=False)
        .order_by('-created_at').first()
    )
    if otp is None:
        raise ContactSettingsError("Code invalide. Demandez un nouveau code.", 'otp_invalid')
    if otp.is_expired():
        raise ContactSettingsError("Ce code a expiré. Demandez un nouveau code.", 'otp_expired')
    if otp.attempts >= OtpCode.MAX_ATTEMPTS:
        raise ContactSettingsError(
            "Trop de tentatives. Demandez un nouveau code.", 'otp_attempts_exceeded', 429,
        )
    if not isinstance(code, str) or not otp.verify(code.strip()):
        raise ContactSettingsError("Code invalide.", 'otp_invalid')
    with transaction.atomic():
        owner.lock_organization()
        owner.authorize_write()
        # Mise à jour conditionnelle : le code ne vaut que pour le numéro auquel il a été envoyé.
        # Si le numéro a changé entre la lecture et l'écriture, rien n'est marqué vérifié.
        updated = ContactPoint.objects.filter(
            pk=point.pk, phone=otp.phone, is_verified=False,
        ).update(is_verified=True, verified_at=timezone.now())
        if not updated:
            raise ContactSettingsError("Code invalide. Demandez un nouveau code.", 'otp_invalid')
        # Le code a servi : on ne garde pas de trace du numéro dans la table des OTP (LEG-PRV-12).
        OtpCode.objects.filter(phone=otp.phone, purpose=OtpCode.PURPOSE_CONTACT_VERIFY).delete()
        owner.audit('contact.phone_verified', 'CONTACT_PHONE_VERIFIED', "Numéro de contact vérifié par code SMS.")


def set_channel_consent(user, channel, *, enabled, text_version=None, context=None) -> None:
    """Active ou retire un canal (ADR 0005, C2 et C4). Retirer est toujours permis et idempotent.

    Organisation (ADR 0006, 11.2) : réservé à qui a `contact.manage_channels` (propriétaire, administrateur),
    `granted_by` conserve l'auteur du consentement ; un canal absent de `get_available_channels` est refusé
    (`channel_not_available`) ; `MESSAGE` est toujours proposé et ne se désactive pas."""
    from .models import CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint

    if channel not in CHANNEL_ORDER:
        raise ContactSettingsError("Canal inconnu.", 'channel_unknown', 404)
    owner = _Owner(user, context)
    if enabled and channel not in get_available_channels(owner.context_type):
        raise ContactSettingsError(
            "Ce moyen de contact n'est pas disponible pour ce contexte.", 'channel_not_available',
        )
    if owner.is_organization and channel == 'MESSAGE':
        if not enabled:
            raise ContactSettingsError(
                "Le message à l'équipe reste toujours proposé pour une organisation.", 'message_channel_required',
            )
        return
    now = timezone.now()
    with transaction.atomic():
        owner.lock_organization()
        owner.authorize_write(allow_restricted=not enabled)
        consent, created = ContactConsent.objects.get_or_create(
            **owner.lookup, channel=channel, defaults={'is_granted': channel == 'MESSAGE'},
        )
        if not enabled:
            if consent.is_granted:
                consent.is_granted = False
                consent.revoked_at = now
                consent.revoked_reason = ContactConsent.REVOKED_USER
                consent.save(update_fields=['is_granted', 'revoked_at', 'revoked_reason', 'updated_at'])
                owner.audit(
                    'contact.consent_revoked', 'CONTACT_CHANNEL_CHANGED', f"Canal {channel} retiré (motif : user).",
                )
            return
        if channel == 'MESSAGE':
            if not consent.is_granted:
                consent.is_granted, consent.granted_at = True, now
                consent.revoked_at, consent.revoked_reason = None, ''
                consent.save(update_fields=['is_granted', 'granted_at', 'revoked_at', 'revoked_reason', 'updated_at'])
                owner.audit('contact.consent_granted', 'CONTACT_CHANNEL_CHANGED', "Canal MESSAGE activé.")
            return
        if not text_version:
            raise ContactSettingsError(
                "Acceptez le texte de consentement pour activer ce moyen.", 'consent_text_required',
            )
        if text_version != CONTACT_CONSENT_TEXT_VERSION:
            raise ContactSettingsError(
                "Le texte a changé, relisez-le avant d'accepter.", 'consent_version_mismatch',
            )
        point = ContactPoint.objects.select_for_update().filter(**owner.lookup).first()
        if point is None or not point.is_verified:
            raise ContactSettingsError("Vérifiez d'abord votre numéro.", 'contact_phone_unverified', 409)
        last4 = point.phone[-4:]
        if consent.is_granted and consent.text_version == text_version and consent.phone_last4 == last4:
            return
        # Le numéro doit être resté celui que l'on vient de lire (un changement concurrent
        # a déjà révoqué les accords : on n'en écrit pas un nouveau pour l'ancien numéro).
        if not ContactPoint.objects.filter(pk=point.pk, phone=point.phone, is_verified=True).exists():
            raise ContactSettingsError("Le numéro a changé. Vérifiez-le à nouveau.", 'contact_phone_unverified', 409)
        consent.is_granted = True
        consent.text_version = text_version
        consent.granted_at = now
        consent.revoked_at = None
        consent.revoked_reason = ''
        consent.phone_last4 = last4
        fields = [
            'is_granted', 'text_version', 'granted_at', 'revoked_at', 'revoked_reason', 'phone_last4', 'updated_at',
        ]
        if owner.is_organization:
            consent.granted_by = user  # qui a consenti pour l'organisation (ADR 0006, 4.4)
            fields.append('granted_by')
        consent.save(update_fields=fields)
        owner.audit(
            'contact.consent_granted', 'CONTACT_CHANNEL_CHANGED', f"Canal {channel} activé ; texte {text_version}.",
        )


def revoke_organization_phone_consents() -> int:
    """Retire les consentements CALL et WHATSAPP de toutes les organisations (motif `moderation`), un audit par
    consentement avec le contexte, sans numéro. Appelée quand `org_phone_channels_enabled` se ferme : un
    consentement donné sous l'ancien régime ne se réactive pas tout seul à la réouverture. Renvoie le nombre retiré."""
    from apps.common.contexts import CONTEXT_ORGANIZATION

    from .models import ContactConsent, Organization

    now = timezone.now()
    count = 0
    with transaction.atomic():
        for consent in ContactConsent.objects.filter(
            organization__isnull=False, channel__in=NUMBER_CHANNELS, is_granted=True,
        ):
            consent.is_granted = False
            consent.revoked_at = now
            consent.revoked_reason = ContactConsent.REVOKED_MODERATION
            consent.save(update_fields=['is_granted', 'revoked_at', 'revoked_reason', 'updated_at'])
            record_audit(
                None, 'CONTACT_CHANNEL_CHANGED', target=Organization(pk=consent.organization_id),
                details=f"Canal {consent.channel} retiré (motif : moderation ; canaux numéro fermés).",
                context=(CONTEXT_ORGANIZATION, consent.organization_id),
            )
            count += 1
    return count


def get_allowed_channels(seller_ids: Iterable) -> dict:
    """Canaux ouverts par vendeur, en une requête : `{vendeur: ['MESSAGE', 'CALL', ...]}` (ordre fixe).
    Un compte inactif n'a aucun canal. CALL/WHATSAPP exigent un consentement actif ET un numéro de
    contact vérifié ; MESSAGE est actif sauf refus explicite. Tout vendeur demandé figure dans le
    résultat (un compte inconnu n'a aucun canal). Aucun numéro ici (ADR 0005, C11)."""
    from apps.common.utils import parse_uuid

    from .models import User

    wanted = {parsed for parsed in (parse_uuid(i) for i in seller_ids) if parsed is not None}
    if not wanted:
        return {}
    active = set()
    message_off = set()
    number_ok = {}
    rows = User.objects.filter(pk__in=wanted).values_list(
        'pk', 'is_active', 'contact_point__is_verified', 'contact_consents__channel', 'contact_consents__is_granted',
    )
    for user_id, is_active, verified, channel, granted in rows:
        if is_active:
            active.add(user_id)
        if channel == 'MESSAGE' and not granted:
            message_off.add(user_id)
        elif channel in NUMBER_CHANNELS and granted and verified:
            number_ok.setdefault(user_id, set()).add(channel)
    result = {}
    for user_id in wanted:
        if user_id not in active:
            result[user_id] = []
            continue
        channels = [] if user_id in message_off else ['MESSAGE']
        channels += [ch for ch in NUMBER_CHANNELS if ch in number_ok.get(user_id, ())]
        result[user_id] = channels
    return result


def get_contact_endpoint(seller_id, channel) -> ContactEndpoint:
    """Numéro du vendeur pour un canal consenti (lecture seule, ADR 0005, C5). Lève
    `ChannelNotConsented` si le canal n'est pas actif, si le numéro n'est pas vérifié, si le compte
    est inactif ou si la preuve d'accord (4 derniers chiffres) ne correspond pas au numéro actuel.
    À appeler uniquement par l'action de révélation de `marketplace`."""
    from apps.common.utils import parse_uuid

    from .models import ContactConsent, ContactPoint

    seller_uuid = parse_uuid(seller_id)
    if channel not in NUMBER_CHANNELS or seller_uuid is None:
        raise ChannelNotConsented()
    consent = ContactConsent.objects.filter(
        user_id=seller_uuid, channel=channel, is_granted=True, user__is_active=True,
    ).first()
    point = ContactPoint.objects.filter(user_id=seller_uuid, is_verified=True).first() if consent else None
    if point is None or consent.phone_last4 != point.phone[-4:]:
        raise ChannelNotConsented()
    return ContactEndpoint(phone_e164=point.phone)
