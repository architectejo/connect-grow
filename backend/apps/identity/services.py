"""Interface publique du domaine `identity` (sessions, jetons, fiches publiques de vendeurs)."""
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

from django.db import transaction
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


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
    from django.utils import timezone

    from apps.moderation.services import record_audit

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
    """Fiche publique d'un vendeur affichée sur ses offres. Le téléphone y figure
    encore (contact par appel / WhatsApp) : à retirer par L0-10a (règle 10)."""

    id: uuid.UUID
    full_name: str
    photo: Optional[str]
    phone: Optional[str]
    user_type: str
    business: Optional[SellerBusiness]
    date_joined: object
    trust_score: float
    reviews_count: int


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
            phone=user.phone, user_type=user.user_type, business=business, date_joined=user.date_joined,
            trust_score=user.trust_score, reviews_count=user.reviews_count,
        )
    return summaries


def get_full_names(ids: Iterable) -> dict:
    """Noms complets indexés par UUID (une requête) ; un compte absent n'apparaît pas."""
    from apps.common.utils import parse_uuid

    from .models import User

    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return dict(User.objects.filter(id__in=wanted).values_list('id', 'full_name'))


def set_reputation(user_id, trust_score: float, reviews_count: int) -> None:
    """Met en cache le Trust Score et le nombre d'avis reçus (calculés par `reviews`).
    Mise à jour par requête : sans effet (et sans erreur) si le compte vient d'être supprimé.
    Transitoire : supprimé avec le Trust Score par L0-07."""
    from .models import User

    User.objects.filter(pk=user_id).update(trust_score=trust_score, reviews_count=reviews_count)


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
