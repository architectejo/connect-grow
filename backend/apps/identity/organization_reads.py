"""Lectures des organisations : état de vérification dérivé, liste publique, limites (ADR 0006, 9.2 et 17.2).

Aucune écriture. Les « claims » et la synthèse sont dérivés par `identity.verification` (T4, source unique,
règle 3 / A6) ; ce module ne fait que les présenter dans les formes documentées (ADR 9.2). Seuls les filtres
`claim` et `fully_verified` de la liste publique sont exprimés en sous-requêtes ORM (pagination côté base) ; un
test vérifie qu'ils restent cohérents avec `verification.get_verification_summaries`.

Ce module est exposé par `identity.services` ; les autres domaines n'importent jamais ce sous-module.
"""
from collections import defaultdict

from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Lower
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from apps.moderation import services as moderation_services

from . import capabilities, organizations, verification
from .models import KycDocument, Membership, Organization, OrganizationCategory, OrganizationDocumentRequirement

SEARCH_MAX_LENGTH = 100
STATE_NONE = 'NONE'
STATE_MISSING_T4 = verification.STATUS_MISSING


def get_verification_data(organizations_list) -> dict:
    """Claims et synthèse par lot, pour la liste publique : `{organization_id: {'verified_claims': [...],
    'summary': {...}}}`. Dérivation unique de `identity.verification` (T4) : rien n'est recalculé ici."""
    return verification.get_verification_summaries([o.pk for o in organizations_list])


def get_internal_verification(organization) -> dict:
    """Bloc `verification` de `OrganizationInternal` (ADR 9.2) : `required[{document_type,label,state}]`,
    `verified_claims`, `summary`. Construit depuis `verification.get_verification_state` (T4).
    `state` : `VALIDE` si le type est prouvé (présent dans les claims), sinon le statut de la pièce la plus
    récente (`EN_ATTENTE`, `REFUSE`), `NONE` si aucune pièce n'a été déposée (MANQUANTE côté T4)."""
    data = verification.get_verification_state(organization)
    proven = {c['code'] for c in data['verified_claims']}
    required = []
    for item in data['requirements']:
        if item['claim_code'] in proven:
            state = KycDocument.STATUS_VALIDE
        elif item['status'] == STATE_MISSING_T4:
            state = STATE_NONE
        else:
            state = item['status']
        required.append({
            'document_type': item['document_type'], 'label': item['document_type_label'], 'state': state,
        })
    return {'required': required, 'verified_claims': data['verified_claims'], 'summary': data['summary']}


def get_category_ids_by_organization(organizations_list) -> dict:
    """UUID de catégories triés, par organisation (une requête)."""
    ids = [o.pk for o in organizations_list]
    result = defaultdict(list)
    for organization_id, category_id in OrganizationCategory.objects.filter(
        organization_id__in=ids,
    ).values_list('organization_id', 'category_id'):
        result[organization_id].append(category_id)
    return {key: sorted(values, key=str) for key, values in result.items()}


# État d'administration exposé tant que B10 (ADR 0010 D9) n'a pas livré `primary_admin_state` : contrat §7.6, « vaut
# `OK` avant B10 ».
PRIMARY_ADMIN_STATE_OK = 'OK'


def governance_block(under_review) -> dict:
    """Clé `governance` de `OrganizationInternal` et des éléments ORGANIZATION de `contexts/` (contrat §7.6). Réservée
    aux membres : jamais `assurance_level`, jamais de seuil ni de cause de la revue."""
    return {'primary_admin_state': PRIMARY_ADMIN_STATE_OK, 'under_review': bool(under_review)}


def get_organization_governance(organization) -> dict:
    return governance_block(organization.creation_review_status == Organization.CREATION_REVIEW_PENDING)


def get_organization_limits() -> dict:
    """Limites informatives pour le front (il ne code aucune limite). Rien de propre à l'utilisateur ;
    le serveur valide toujours. Aucun seuil anti-abus n'y figure (plafond technique, revue de création : ADR 0010 D8,
    Q22) : un seuil de sécurité ne se publie pas."""
    settings_row = organizations.get_identity_settings()
    return {
        'max_categories_per_context': settings_row.max_categories_per_context,
        'name_min_length': organizations.NAME_MIN_LENGTH,
        'name_max_length': organizations.NAME_MAX_LENGTH,
        'description_max_length': organizations.DESCRIPTION_MAX_LENGTH,
        'invitation_ttl_days': settings_row.invitation_ttl_days,
        'max_pending_invitations': settings_row.max_pending_invitations,
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
    # Même règle que `is_seller_context_public` (A7) : au moins un propriétaire actif, compte actif et sans sanction
    # bloquante ; sinon l'organisation n'est pas listée (ses offres sont masquées et sa fiche répond 404). Une
    # organisation retenue en revue de création n'est pas listée non plus (ADR 0010 D8).
    led = Membership.objects.filter(
        organization_id=OuterRef('pk'), role=capabilities.ROLE_OWNER, status=Membership.STATUS_ACTIVE,
        user__is_active=True,
    ).filter(~Exists(moderation_services.blocking_sanctions_for(OuterRef('user_id'))))
    queryset = Organization.objects.filter(status=Organization.STATUS_ACTIVE).exclude(
        creation_review_status=Organization.CREATION_REVIEW_PENDING,
    ).filter(Exists(led))

    search = params.get('search')
    if search and len(search.strip()) > SEARCH_MAX_LENGTH:
        raise serializers.ValidationError({'search': [ErrorDetail(
            f"La recherche ne doit pas dépasser {SEARCH_MAX_LENGTH} caractères.", 'search_too_long',
        )]})
    if search and search.strip():
        queryset = queryset.filter(Q(name__icontains=search.strip()) | Q(description__icontains=search.strip()))

    org_type = params.get('org_type')
    if org_type:
        if org_type not in dict(Organization._meta.get_field('org_type').choices):
            raise serializers.ValidationError({'org_type': [ErrorDetail("Type d'organisation inconnu.", 'invalid_org_type')]})
        queryset = queryset.filter(org_type=org_type)

    claim = params.get('claim')
    if claim:
        document_type = _document_for_claim(claim)
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


def _document_for_claim(code):
    """Type de pièce correspondant à un code de claim (table de présentation de `identity.verification`)."""
    for document_type, (claim_code, _) in verification.CLAIMS.items():
        if claim_code == code:
            return document_type
    return None
