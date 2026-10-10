"""Vérification des organisations (KYB) : pièces et libellés précis (ADR 0006, A6, 4.3, 4.4 et 9.4).

Principes :
- AUCUN champ « vérifié » n'est stocké : les `verified_claims` et la synthèse sont calculés à la lecture
  depuis les pièces `VALIDE` et le tableau `OrganizationDocumentRequirement` (règle 11). Aucun plan, prix,
  rôle ou ajout de membre n'entre dans ce calcul (règles 2 et 3) : ce module ne reçoit aucun paramètre
  commercial.
- Seule la décision du personnel (`services.decide_kyc_document`) fait passer une pièce à `VALIDE`.
- Les fichiers restent dans le stockage privé ; aucune réponse de ce module ne contient d'URL de fichier.
- Les `details` d'audit ne contiennent que des UUID et des codes (jamais de nom, d'e-mail ni de téléphone).

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
import uuid
from collections import defaultdict
from typing import Iterable

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import ErrorDetail

from apps.common.contexts import CONTEXT_ORGANIZATION, DENY_RELATION, ContextDenied
from apps.moderation.services import record_audit

from .kyc_files import validate_kyc_file
from .models import KycDocument, Organization, OrganizationDocumentRequirement
from .organizations import OrganizationError, _authorize_member, _lock_organization

# Libellés précis (CDC §3.1, doc 07 §3) : chacun dit exactement ce qui a été vérifié, ni « sûre », ni
# « solvable », ni « recommandée ». Présentation seulement : les pièces EXIGÉES viennent de la base.
CLAIMS = {
    KycDocument.DOC_RCCM: ('RCCM_VERIFIED', "RCCM vérifié"),
    KycDocument.DOC_ID_NATIONALE: ('ID_NATIONALE_VERIFIED', "Identification nationale vérifiée"),
    KycDocument.DOC_PIECE_GERANT: ('REPRESENTATIVE_VERIFIED', "Représentant vérifié"),
    KycDocument.DOC_ARRETE_ONG: ('ONG_DECREE_VERIFIED', "Arrêté d'enregistrement de l'ONG vérifié"),
}
SUMMARY_LABEL = "Organisation vérifiée"

# État d'une pièce exigée qui n'a pas encore été déposée.
STATUS_MISSING = 'MANQUANTE'

DOC_TYPE_LABELS = dict(KycDocument.DOC_TYPE_CHOICES)


def _claim(document_type, verified_at):
    code, label = CLAIMS.get(document_type, (f'{document_type}_VERIFIED', f'{document_type} vérifié'))
    return {'code': code, 'label': label, 'verified_at': verified_at}


def _required_types_by_org_type(org_types) -> dict:
    required = defaultdict(list)
    rows = OrganizationDocumentRequirement.objects.filter(org_type__in=set(org_types)).order_by(
        'org_type', 'position', 'document_type',
    ).values_list('org_type', 'document_type')
    for org_type, document_type in rows:
        required[org_type].append(document_type)
    return required


def get_verification_summaries(org_ids: Iterable) -> dict:
    """Pour chaque organisation : `{'verified_claims': [...], 'summary': {'complete', 'label'}}`.

    Calculé à la lecture, par lot : une requête pour les organisations, une pour les exigences, une pour les
    pièces validées. Le libellé global n'existe que si TOUTES les pièces exigées sont validées ; il se lit
    toujours avec la liste `verified_claims` de la même réponse."""
    ids = list(dict.fromkeys(org_ids))
    if not ids:
        return {}
    org_types = dict(Organization.objects.filter(pk__in=ids).values_list('pk', 'org_type'))
    required = _required_types_by_org_type(org_types.values())
    validated = defaultdict(dict)  # org -> type -> date de vérification la plus récente
    rows = KycDocument.objects.filter(organization_id__in=ids, status=KycDocument.STATUS_VALIDE).values_list(
        'organization_id', 'document_type', 'reviewed_at',
    )
    for org_id, document_type, reviewed_at in rows:
        known = validated[org_id].get(document_type)
        if known is None or (reviewed_at is not None and reviewed_at > known):
            validated[org_id][document_type] = reviewed_at

    result = {}
    for org_id in ids:
        if org_id not in org_types:
            result[org_id] = {'verified_claims': [], 'summary': {'complete': False, 'label': None}}
            continue
        needed = required.get(org_types[org_id], [])
        proven = validated.get(org_id, {})
        ordered = [t for t in needed if t in proven] + sorted(t for t in proven if t not in needed)
        complete = bool(needed) and all(t in proven for t in needed)
        result[org_id] = {
            'verified_claims': [_claim(t, proven[t]) for t in ordered],
            'summary': {'complete': complete, 'label': SUMMARY_LABEL if complete else None},
        }
    return result


def get_verified_claims(org_ids: Iterable) -> dict:
    """`{org_id: [claims]}` : un claim par type de pièce validée (`code`, `label`, `verified_at`)."""
    return {org_id: data['verified_claims'] for org_id, data in get_verification_summaries(org_ids).items()}


def get_verification_state(organization) -> dict:
    """Bloc `verification` interne : claims, synthèse et état de chaque pièce exigée (jamais d'URL de fichier)."""
    data = get_verification_summaries([organization.pk])[organization.pk]
    latest = {}
    for doc in organization.kyc_documents.order_by('-created_at'):
        latest.setdefault(doc.document_type, doc)
    requirements = []
    for document_type in _required_types_by_org_type([organization.org_type]).get(organization.org_type, []):
        doc = latest.get(document_type)
        requirements.append({
            'document_type': document_type,
            'document_type_label': DOC_TYPE_LABELS.get(document_type, document_type),
            'claim_code': _claim(document_type, None)['code'],
            'claim_label': _claim(document_type, None)['label'],
            'status': doc.status if doc else STATUS_MISSING,
            'rejection_reason': doc.rejection_reason if doc and doc.status == KycDocument.STATUS_REFUSE else '',
        })
    return {**data, 'requirements': requirements}


# --- Pièces d'une organisation -----------------------------------------------------------------

def _field_error(field, message, code):
    return serializers.ValidationError({field: [ErrorDetail(message, code=code)]})


def _validate_input(document_type, file):
    if not isinstance(document_type, str) or document_type not in DOC_TYPE_LABELS:
        raise _field_error('document_type', "Type de pièce inconnu.", 'invalid_choice')
    if file is None or not hasattr(file, 'size'):
        raise _field_error('file', "Aucun fichier n'a été envoyé.", 'required')
    try:
        validate_kyc_file(file)
    except DjangoValidationError as exc:
        raise _field_error('file', exc.messages[0], exc.code or 'invalid')


def _audit(actor, action, document, organization, details):
    record_audit(
        actor, action, target=document, details=f"organization={organization.pk}; {details}",
        context=(CONTEXT_ORGANIZATION, organization.pk),
    )


def list_kyb_documents(actor, organization_id):
    """Pièces de l'organisation (capacité `org.view_internal`), de la plus récente à la plus ancienne."""
    organization = _load_for_read(actor, organization_id)
    return organization.kyc_documents.order_by('-created_at', 'pk')


def _load_for_read(actor, organization_id) -> Organization:
    try:
        organization = Organization.objects.get(pk=organization_id)
    except (Organization.DoesNotExist, ValueError, TypeError, DjangoValidationError):
        # Même refus qu'un non-membre : aucun oracle d'existence.
        raise ContextDenied(DENY_RELATION, "Vous n'êtes pas membre de cette organisation.")
    _authorize_member(actor, organization, 'org.view_internal')
    return organization


def _is_uuid(value):
    if isinstance(value, uuid.UUID):
        return True
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def get_organization_verification(actor, organization_id) -> dict:
    """Lecture de l'état de vérification (capacité `org.view_internal`)."""
    return get_verification_state(_load_for_read(actor, organization_id))


def submit_kyb_document(actor, organization_id, document_type, file) -> KycDocument:
    """Dépôt (ou remplacement) d'une pièce par un propriétaire ou un administrateur (`org.verification_submit`).

    Une pièce du même type en attente ou refusée est remplacée (fichier supprimé, trace d'audit) ; une pièce
    déjà validée ne se remplace pas (409)."""
    _validate_input(document_type, file)
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        _authorize_member(actor, organization, 'org.verification_submit')
        required = OrganizationDocumentRequirement.objects.filter(org_type=organization.org_type)
        if not required.filter(document_type=document_type).exists():
            raise _field_error(
                'document_type', "Cette pièce n'est pas exigée pour ce type d'organisation.",
                'document_type_not_required',
            )
        existing = list(organization.kyc_documents.select_for_update())
        same_type = [d for d in existing if d.document_type == document_type]
        if any(d.status == KycDocument.STATUS_VALIDE for d in same_type):
            raise OrganizationError("Cette pièce est déjà validée.", 'document_already_validated')
        if len(existing) - len(same_type) >= settings.KYC_MAX_DOCUMENTS_PER_PROFILE:
            raise OrganizationError("Nombre maximal de pièces atteint.", 'document_limit_reached', status.HTTP_400_BAD_REQUEST)

        document = KycDocument(organization=organization, uploaded_by=actor, document_type=document_type, file=file)
        document.save()
        replaced_files = []
        for old in same_type:
            _audit(actor, 'KYC_REPLACED', old, organization, f"document_type={old.document_type}; old_status={old.status}")
            replaced_files.append(old.file)
            old.delete()
        _audit(actor, 'KYC_SUBMITTED', document, organization, f"document_type={document_type}")
    for stored_file in replaced_files:
        stored_file.delete(save=False)
    return document


def delete_kyb_document(actor, organization_id, document_id) -> None:
    """Suppression d'une pièce en attente ou refusée (`org.verification_submit`) ; 409 si validée."""
    with transaction.atomic():
        organization = _lock_organization(organization_id)
        _authorize_member(actor, organization, 'org.verification_submit')
        document = organization.kyc_documents.select_for_update().filter(pk=document_id).first() \
            if _is_uuid(document_id) else None
        if document is None:
            raise OrganizationError("Pièce introuvable.", 'document_not_found', status.HTTP_404_NOT_FOUND)
        if document.status == KycDocument.STATUS_VALIDE:
            raise OrganizationError("Une pièce validée ne peut pas être supprimée.", 'document_validated')
        _audit(actor, 'KYC_DELETED', document, organization,
               f"document_type={document.document_type}; status={document.status}")
        stored_file = document.file
        document.delete()
    stored_file.delete(save=False)
