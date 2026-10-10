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


def recompute_verification(business_profile):
    """Recalcule `is_verified` : vrai seulement si chaque type de pièce requis a une
    pièce validée. Révoque la vérification si ce n'est plus le cas. La vérification
    ne vient que de décisions de la modération, jamais d'un achat (règle 3).

    À appeler DANS un `transaction.atomic()` : le `select_for_update` ci-dessous n'a d'effet
    (et n'est autorisé hors autocommit) que dans une transaction."""
    from .models import BusinessProfile, KycDocument

    # Verrou de ligne sur le profil (à appeler dans une transaction) : deux décisions
    # simultanées sur des pièces du même profil se recalculent l'une après l'autre.
    locked = BusinessProfile.objects.select_for_update().get(pk=business_profile.pk)
    validated_types = set(
        locked.kyc_documents.filter(status=KycDocument.STATUS_VALIDE).values_list('document_type', flat=True)
    )
    verified = set(KycDocument.REQUIRED_TYPES).issubset(validated_types)
    if locked.is_verified != verified:
        locked.is_verified = verified
        locked.save(update_fields=['is_verified', 'updated_at'])
    business_profile.is_verified = verified
    return verified


def decide_kyc_document(document_id, reviewer, decision, reason=''):
    """Décision (VALIDE ou REFUSE) sur une pièce KYC, atomique avec son journal d'audit."""
    from django.db import transaction
    from .models import KycDocument

    if decision not in (KycDocument.STATUS_VALIDE, KycDocument.STATUS_REFUSE):
        raise KycError("decision doit être VALIDE ou REFUSE.")
    if len(reason) > KycDocument.REASON_MAX_LENGTH:
        raise KycError(f"Le motif ne doit pas dépasser {KycDocument.REASON_MAX_LENGTH} caractères.")

    with transaction.atomic():
        try:
            doc = KycDocument.objects.select_related('business_profile').get(pk=document_id)
        except KycDocument.DoesNotExist:
            raise KycError("Document introuvable.", 404)

        if doc.business_profile.user_id == reviewer.pk:
            raise KycError("Vous ne pouvez pas décider sur votre propre pièce.", 403)

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

        recompute_verification(doc.business_profile)

        action = 'KYC_REVOKED' if revoking else f'KYC_{decision}'
        record_audit(
            reviewer, action, target=doc,
            details=doc.rejection_reason or f"Document {doc.get_document_type_display()} validé.",
        )
    return doc


@dataclass(frozen=True)
class SellerBusiness:
    business_name: str
    bio: str
    logo: Optional[str]  # URL relative du média, ou None
    is_verified: bool


@dataclass(frozen=True)
class SellerSummary:
    """Fiche publique d'un vendeur affichée sur ses offres. Ni téléphone ni e-mail
    (règle 10) : le numéro ne sort que par l'action de contact (L0-10a-c)."""

    id: uuid.UUID
    full_name: str
    photo: Optional[str]
    user_type: str
    business: Optional[SellerBusiness]
    date_joined: object


def get_seller_summaries(ids: Iterable) -> dict:
    """Fiches vendeur indexées par UUID, en une requête (profil business compris)."""
    from apps.common.utils import parse_uuid

    from .models import User

    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    if not wanted:
        return {}
    summaries = {}
    for user in User.objects.filter(id__in=wanted).select_related('business_profile'):
        profile = getattr(user, 'business_profile', None)
        business = None
        if profile is not None:
            business = SellerBusiness(
                business_name=profile.business_name, bio=profile.bio,
                logo=profile.logo.url if profile.logo else None, is_verified=profile.is_verified,
            )
        summaries[user.id] = SellerSummary(
            id=user.id, full_name=user.full_name, photo=user.photo.url if user.photo else None,
            user_type=user.user_type, business=business, date_joined=user.date_joined,
        )
    return summaries


def get_full_names(ids: Iterable) -> dict:
    """Noms complets indexés par UUID (une requête) ; un compte absent n'apparaît pas."""
    from apps.common.utils import parse_uuid

    from .models import User

    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return dict(User.objects.filter(id__in=wanted).values_list('id', 'full_name'))


def acts_for_context(user_id, context_type, context_id) -> bool:
    """Vrai si ce compte agit pour le contexte désigné (couture L0-09). Aujourd'hui, seul le
    contexte personnel existe : le compte agit pour lui-même. L0-09 étendra la règle aux membres
    d'une organisation sans changer les appelants."""
    from apps.common.contexts import CONTEXT_USER

    return (
        context_type == CONTEXT_USER and user_id is not None and context_id is not None
        and str(user_id) == str(context_id)
    )


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


# --- Contact vendeur : numéro de contact et consentement par canal (ADR 0005) ---------------------

CHANNEL_ORDER = ('MESSAGE', 'CALL', 'WHATSAPP')
NUMBER_CHANNELS = ('CALL', 'WHATSAPP')  # canaux qui révèlent le numéro


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


def get_contact_settings(user) -> dict:
    """État complet de l'écran « Contact » (ADR 0005, 5.1). Numéros toujours masqués."""
    from .models import CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint

    point = ContactPoint.objects.filter(user=user).first()
    consents = {c.channel: c for c in ContactConsent.objects.filter(user=user)}
    login_masked = mask_phone(user.phone)
    can_use_login = bool(user.phone) and user.phone_verified
    phone = None
    if point is not None:
        phone = {
            'masked': mask_phone(point.phone), 'is_verified': point.is_verified,
            'login_phone_masked': login_masked, 'can_use_login_phone': can_use_login,
        }
    return {
        'phone': phone,
        # Au niveau racine aussi : `phone` vaut null tant qu'aucun numéro de contact n'existe.
        'login_phone_masked': login_masked,
        'can_use_login_phone': can_use_login,
        'channels': {ch: _channel_state(consents.get(ch), ch) for ch in CHANNEL_ORDER},
        'current_text_version': CONTACT_CONSENT_TEXT_VERSION,
    }


def _revoke_number_channels(user, reason) -> list:
    from .models import ContactConsent

    revoked = []
    now = timezone.now()
    for consent in ContactConsent.objects.filter(user=user, channel__in=NUMBER_CHANNELS, is_granted=True):
        consent.is_granted = False
        consent.revoked_at = now
        consent.revoked_reason = reason
        consent.save(update_fields=['is_granted', 'revoked_at', 'revoked_reason', 'updated_at'])
        record_audit(
            user, 'contact.consent_revoked', target=user,
            details=f"Canal {consent.channel} retiré (motif : {reason}).",
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


def _lock_or_create_point(user, number, verified, now):
    """Renvoie `(point, created)`. Verrouille la ligne existante ; une création concurrente
    (unicité du compte) est rattrapée par une relecture au lieu d'une erreur 500."""
    from .models import ContactPoint

    point = ContactPoint.objects.select_for_update().filter(user=user).first()
    if point is not None:
        return point, False
    try:
        with transaction.atomic():
            point = ContactPoint.objects.create(
                user=user, phone=number, is_verified=verified, verified_at=now if verified else None,
            )
        return point, True
    except IntegrityError:
        return ContactPoint.objects.select_for_update().get(user=user), False


def set_contact_phone(user, *, phone=None, use_login_phone=False) -> None:
    """Crée ou remplace le numéro de contact. Seul un geste explicite copie le numéro de connexion.
    Changer de numéro révoque CALL et WHATSAPP ; un numéro non vérifié reçoit un code SMS."""
    from django.core.exceptions import ValidationError as DjangoValidationError

    from .models import phone_validator

    if bool(use_login_phone) == bool(phone):
        raise ContactSettingsError(
            "Indiquez un numéro, ou demandez à utiliser votre numéro de connexion.", 'phone_invalid',
        )
    verified_at_once = False
    if use_login_phone:
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
        now = timezone.now()
        point, created = _lock_or_create_point(user, number, verified_at_once, now)
        if not created and point.phone == number:
            # Même numéro : aucun canal n'est révoqué ; un numéro non vérifié reçoit un nouveau code.
            if not point.is_verified:
                if verified_at_once:
                    point.is_verified, point.verified_at = True, now
                    point.save(update_fields=['is_verified', 'verified_at', 'updated_at'])
                    record_audit(user, 'contact.phone_verified', target=user, details="Numéro de contact vérifié (numéro de connexion déjà vérifié).")
                else:
                    send_code = True
        else:
            if not created:
                point.phone = number
                point.is_verified = verified_at_once
                point.verified_at = now if verified_at_once else None
                point.save(update_fields=['phone', 'is_verified', 'verified_at', 'updated_at'])
            _revoke_number_channels(user, 'phone_changed')
            record_audit(
                user, 'contact.phone_changed', target=user,
                details="Numéro de contact modifié ; CALL et WHATSAPP désactivés.",
            )
            if verified_at_once:
                record_audit(user, 'contact.phone_verified', target=user, details="Numéro de contact vérifié (numéro de connexion déjà vérifié).")
            else:
                send_code = True
    if send_code:
        _send_contact_code(number)


def verify_contact_phone(user, code) -> None:
    """Valide le numéro de contact par le code SMS. Ne réactive aucun canal."""
    from .models import ContactPoint, OtpCode

    point = ContactPoint.objects.filter(user=user).first()
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
        # Mise à jour conditionnelle : le code ne vaut que pour le numéro auquel il a été envoyé.
        # Si le numéro a changé entre la lecture et l'écriture, rien n'est marqué vérifié.
        updated = ContactPoint.objects.filter(
            pk=point.pk, phone=otp.phone, is_verified=False,
        ).update(is_verified=True, verified_at=timezone.now())
        if not updated:
            raise ContactSettingsError("Code invalide. Demandez un nouveau code.", 'otp_invalid')
        # Le code a servi : on ne garde pas de trace du numéro dans la table des OTP (LEG-PRV-12).
        OtpCode.objects.filter(phone=otp.phone, purpose=OtpCode.PURPOSE_CONTACT_VERIFY).delete()
        record_audit(user, 'contact.phone_verified', target=user, details="Numéro de contact vérifié par code SMS.")


def set_channel_consent(user, channel, *, enabled, text_version=None) -> None:
    """Active ou retire un canal (ADR 0005, C2 et C4). Retirer est toujours permis et idempotent."""
    from .models import CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint

    if channel not in CHANNEL_ORDER:
        raise ContactSettingsError("Canal inconnu.", 'channel_unknown', 404)
    now = timezone.now()
    with transaction.atomic():
        consent, created = ContactConsent.objects.get_or_create(
            user=user, channel=channel, defaults={'is_granted': channel == 'MESSAGE'},
        )
        if not enabled:
            if consent.is_granted:
                consent.is_granted = False
                consent.revoked_at = now
                consent.revoked_reason = ContactConsent.REVOKED_USER
                consent.save(update_fields=['is_granted', 'revoked_at', 'revoked_reason', 'updated_at'])
                record_audit(user, 'contact.consent_revoked', target=user, details=f"Canal {channel} retiré (motif : user).")
            return
        if channel == 'MESSAGE':
            if not consent.is_granted:
                consent.is_granted, consent.granted_at = True, now
                consent.revoked_at, consent.revoked_reason = None, ''
                consent.save(update_fields=['is_granted', 'granted_at', 'revoked_at', 'revoked_reason', 'updated_at'])
                record_audit(user, 'contact.consent_granted', target=user, details="Canal MESSAGE activé.")
            return
        if not text_version:
            raise ContactSettingsError("Acceptez le texte de consentement pour activer ce moyen.", 'consent_text_required')
        if text_version != CONTACT_CONSENT_TEXT_VERSION:
            raise ContactSettingsError(
                "Le texte a changé, relisez-le avant d'accepter.", 'consent_version_mismatch',
            )
        point = ContactPoint.objects.select_for_update().filter(user=user).first()
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
        consent.save(update_fields=[
            'is_granted', 'text_version', 'granted_at', 'revoked_at', 'revoked_reason', 'phone_last4', 'updated_at',
        ])
        record_audit(
            user, 'contact.consent_granted', target=user,
            details=f"Canal {channel} activé ; texte {text_version} ; numéro se terminant par {last4}.",
        )


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
