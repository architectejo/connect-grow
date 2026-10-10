"""Lectures des organisations : état de vérification dérivé, liste publique, limites (ADR 0006, 9.2 et 17.2).

Aucune écriture. Les « claims » (ce qui a été vérifié) sont DÉRIVÉS à la lecture des pièces `VALIDE` et du
tableau `OrganizationDocumentRequirement` (règle 11) : il n'existe aucun champ qu'un plan, un rôle ou un
autre code puisse écrire (règle 3, A6). Le libellé de synthèse n'est donné que si TOUTES les pièces exigées du
type sont validées ET la liste d'exigences n'est pas vide.

NOTE T4 : cette dérivation est le strict minimum nécessaire à `OrganizationInternal` et à la liste publique ;
T4 (pièces et claims d'organisation) la reprendra/consolidera sans changer ces formes de sortie.

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
from collections import defaultdict

from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Lower
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from . import organizations
from .models import KycDocument, Organization, OrganizationCategory, OrganizationDocumentRequirement

# Codes de claim et libellés (en base de code ; le front traduit par la clé `code`).
CLAIM_BY_DOCUMENT = {
    KycDocument.DOC_RCCM: 'RCCM_VERIFIED',
    KycDocument.DOC_ID_NATIONALE: 'NATIONAL_ID_VERIFIED',
    KycDocument.DOC_PIECE_GERANT: 'REPRESENTATIVE_VERIFIED',
    KycDocument.DOC_ARRETE_ONG: 'NGO_DECREE_VERIFIED',
}
DOCUMENT_BY_CLAIM = {code: document for document, code in CLAIM_BY_DOCUMENT.items()}
CLAIM_LABELS = {
    'RCCM_VERIFIED': "RCCM vérifié",
    'NATIONAL_ID_VERIFIED': "Identification nationale vérifiée",
    'REPRESENTATIVE_VERIFIED': "Représentant vérifié",
    'NGO_DECREE_VERIFIED': "Arrêté d'enregistrement vérifié",
}
SUMMARY_LABEL = "Organisation vérifiée"

STATE_NONE = 'NONE'


def _document_label(document_type):
    return dict(KycDocument.DOC_TYPE_CHOICES).get(document_type, document_type)


def get_verification_data(organizations_list) -> dict:
    """État de vérification dérivé, par lot (une requête d'exigences, une requête de pièces) :
    `{organization_id: {'required': [...], 'verified_claims': [...], 'summary': {...}}}`.

    - `required` : une entrée par pièce exigée du type, `state` = `VALIDE` si une pièce de ce type est validée,
      sinon le statut de la pièce la plus récente (`EN_ATTENTE`, `REFUSE`), sinon `NONE` ;
    - `verified_claims` : un par pièce exigée VALIDE (jamais d'une pièce non exigée), avec `verified_at` ;
    - `summary` : `complete` vrai seulement si les exigences existent et sont toutes validées."""
    orgs = list(organizations_list)
    if not orgs:
        return {}
    requirements = defaultdict(list)
    for req in OrganizationDocumentRequirement.objects.filter(
        org_type__in={o.org_type for o in orgs},
    ).order_by('position', 'document_type'):
        requirements[req.org_type].append(req.document_type)

    documents = defaultdict(list)
    rows = KycDocument.objects.filter(organization_id__in=[o.pk for o in orgs]).values(
        'organization_id', 'document_type', 'status', 'reviewed_at', 'created_at',
    ).order_by('-created_at')
    for row in rows:
        documents[row['organization_id']].append(row)

    result = {}
    for org in orgs:
        required, claims = [], []
        required_types = requirements.get(org.org_type, [])
        for document_type in required_types:
            of_type = [d for d in documents.get(org.pk, ()) if d['document_type'] == document_type]
            validated = [d for d in of_type if d['status'] == KycDocument.STATUS_VALIDE]
            if validated:
                state = KycDocument.STATUS_VALIDE
                code = CLAIM_BY_DOCUMENT.get(document_type)
                if code:
                    dates = [d['reviewed_at'] for d in validated if d['reviewed_at']]
                    claims.append({
                        'code': code, 'label': CLAIM_LABELS[code], 'verified_at': max(dates) if dates else None,
                    })
            elif of_type:
                state = of_type[0]['status']
            else:
                state = STATE_NONE
            required.append({
                'document_type': document_type, 'label': _document_label(document_type), 'state': state,
            })
        complete = bool(required_types) and all(r['state'] == KycDocument.STATUS_VALIDE for r in required)
        result[org.pk] = {
            'required': required, 'verified_claims': claims,
            'summary': {'complete': complete, 'label': SUMMARY_LABEL if complete else None},
        }
    return result


def get_category_ids_by_organization(organizations_list) -> dict:
    """UUID de catégories triés, par organisation (une requête)."""
    ids = [o.pk for o in organizations_list]
    result = defaultdict(list)
    for organization_id, category_id in OrganizationCategory.objects.filter(
        organization_id__in=ids,
    ).values_list('organization_id', 'category_id'):
        result[organization_id].append(category_id)
    return {key: sorted(values, key=str) for key, values in result.items()}


def get_organization_limits() -> dict:
    """Limites informatives pour le front (il ne code aucune limite). Rien de propre à l'utilisateur ;
    le serveur valide toujours."""
    settings_row = organizations.get_identity_settings()
    return {
        'max_categories_per_context': settings_row.max_categories_per_context,
        'max_organizations_per_account': settings_row.max_organizations_per_account,
        'name_min_length': organizations.NAME_MIN_LENGTH,
        'name_max_length': organizations.NAME_MAX_LENGTH,
        'description_max_length': organizations.DESCRIPTION_MAX_LENGTH,
    }


def _validated_exists(document_type=None):
    """Sous-requête : l'organisation externe a une pièce VALIDE (du type donné, sinon du type exigé de la
    ligne d'exigence courante)."""
    documents = KycDocument.objects.filter(organization_id=OuterRef('pk'), status=KycDocument.STATUS_VALIDE)
    if document_type is not None:
        documents = documents.filter(document_type=document_type)
    return Exists(documents)


def public_organizations_queryset(params):
    """Organisations ACTIVE, filtrées par `search` (nom et description), `org_type`, `claim` et
    `fully_verified` ; tri par nom (casse ignorée) puis identifiant. Toute valeur de filtre invalide est
    refusée (400) plutôt qu'ignorée : un filtre perdu afficherait des organisations non vérifiées sous
    une étiquette « vérifiée »."""
    queryset = Organization.objects.filter(status=Organization.STATUS_ACTIVE)

    search = params.get('search')
    if search and search.strip():
        queryset = queryset.filter(Q(name__icontains=search.strip()) | Q(description__icontains=search.strip()))

    org_type = params.get('org_type')
    if org_type:
        if org_type not in dict(Organization._meta.get_field('org_type').choices):
            raise serializers.ValidationError({'org_type': [ErrorDetail("Type d'organisation inconnu.", 'invalid_org_type')]})
        queryset = queryset.filter(org_type=org_type)

    claim = params.get('claim')
    if claim:
        document_type = DOCUMENT_BY_CLAIM.get(claim)
        if document_type is None:
            raise serializers.ValidationError({'claim': [ErrorDetail("Claim inconnu.", 'invalid_claim')]})
        # Pièce validée ET exigée pour ce type d'organisation (cohérent avec les claims affichés).
        required = OrganizationDocumentRequirement.objects.filter(
            org_type=OuterRef('org_type'), document_type=document_type,
        )
        queryset = queryset.filter(Exists(required), _validated_exists(document_type))

    fully_verified = params.get('fully_verified')
    if fully_verified is not None:
        value = fully_verified.strip().lower()
        if value not in ('true', 'false'):
            raise serializers.ValidationError({'fully_verified': [
                ErrorDetail("Valeur attendue : true ou false.", 'invalid_filter'),
            ]})
        has_requirements = Exists(OrganizationDocumentRequirement.objects.filter(org_type=OuterRef('org_type')))
        queryset = queryset.annotate(has_requirements=has_requirements, has_missing=_missing_requirement())
        if value == 'true':
            queryset = queryset.filter(has_requirements=True, has_missing=False)
        else:
            queryset = queryset.exclude(has_requirements=True, has_missing=False)

    return queryset.order_by(Lower('name'), 'id')


def _missing_requirement():
    """Sous-requête : au moins une pièce exigée du type de l'organisation n'est pas validée."""
    validated = KycDocument.objects.filter(
        organization_id=OuterRef(OuterRef('pk')), status=KycDocument.STATUS_VALIDE,
        document_type=OuterRef('document_type'),
    )
    return Exists(
        OrganizationDocumentRequirement.objects.filter(org_type=OuterRef('org_type')).filter(~Exists(validated))
    )
