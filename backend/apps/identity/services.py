"""Interface publique du domaine `identity` (sessions et jetons)."""
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken


def revoke_all_sessions(user) -> int:
    """Révoque tous les refresh tokens en cours de `user` (déconnexion de tous les
    appareils, changement ou réinitialisation de mot de passe). Renvoie le nombre
    de jetons révoqués. Les jetons d'accès déjà émis expirent d'eux-mêmes (15 min)."""
    revoked = 0
    for token in OutstandingToken.objects.filter(user=user).exclude(blacklistedtoken__isnull=False):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        revoked += created
    return revoked


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
    ne vient que de décisions de la modération, jamais d'un achat (règle 3)."""
    from .models import KycDocument

    validated_types = set(
        business_profile.kyc_documents.filter(status=KycDocument.STATUS_VALIDE)
        .values_list('document_type', flat=True)
    )
    verified = set(KycDocument.REQUIRED_TYPES).issubset(validated_types)
    if business_profile.is_verified != verified:
        business_profile.is_verified = verified
        business_profile.save(update_fields=['is_verified', 'updated_at'])
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
