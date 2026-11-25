"""Endpoints des organisations (ADR 0006, 9.2 et 17.2). Vues fines : la logique est dans `organizations.py` et
`organization_reads.py`, exposés par `identity.services`.

L'en-tête `X-Context` est IGNORÉ ici (ADR 6.4) :
- la création est toujours faite par le compte (le créateur devient administrateur principal) ;
- les routes `organizations/<id>/…` désignent l'organisation par leur chemin ; l'autorisation se fait par objet,
  d'après le rôle réel du compte dans CETTE organisation (jamais d'après l'en-tête), dans le service, sous verrou
  pour les écritures ;
- la liste publique et `limits/` n'ont pas de contexte.

Données personnelles (règle 10) : jamais de téléphone, d'e-mail ni de nom complet de membre ; le NIF n'est dans
aucune réponse publique (seulement dans le détail interne, réservé aux membres).
"""
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_serializer, inline_serializer
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.fields import DateTimeField
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination
from apps.common.utils import parse_uuid

from . import capabilities
from .services import (
    archive_organization, change_role, create_organization, get_active_role, get_category_ids_by_organization,
    get_internal_verification, get_organization_for_member, get_organization_limits, get_verification_data,
    leave_organization, list_members, public_display_name, public_organizations_queryset, remove_member,
    sole_effective_owner_id, transfer_ownership_to, update_organization,
)
from .throttles import (
    OrganizationCreateThrottle, OrganizationListThrottle, OrganizationSensitiveThrottle, OrganizationWriteThrottle,
)

EXEMPT_REASON = (
    "organisation : création par le compte et autorisation par objet dans le service ; "
    "ignore X-Context (ADR 0006 §6.4)"
)
_ISO = DateTimeField()

CREATE_FIELDS = ('name', 'org_type', 'description', 'nif', 'category_ids', 'city_id', 'commune_id', 'logo')
# `org_type` est lu pour être refusé explicitement (400 `org_type_immutable`).
UPDATE_FIELDS = ('name', 'org_type', 'description', 'nif', 'category_ids', 'city_id', 'commune_id', 'logo')


def _iso(value):
    return _ISO.to_representation(value) if value else None


def _private(response):
    response['Cache-Control'] = 'private, no-store'
    return response


def _logo_url(request, organization):
    return request.build_absolute_uri(organization.logo.url) if organization.logo else None


def _uuid_or_raw(value):
    """Vide -> None ; UUID valide -> UUID ; autre valeur conservée telle quelle pour que la validation du
    service la refuse (`unknown_city`, `unknown_commune`)."""
    if value is None or value == '':
        return None
    return parse_uuid(value) or value


def _extract(request, fields):
    """Champs présents du corps, JSON ou multipart ; les champs inconnus (`id`, `status`, `my_role`…) sont
    ignorés. Un `logo` vide (multipart) équivaut à `null` (retrait)."""
    data = request.data
    if not hasattr(data, 'keys'):
        raise serializers.ValidationError({'non_field_errors': ["Corps de requête invalide."]})
    values = {}
    for key in fields:
        if key not in data:
            continue
        if key == 'category_ids' and hasattr(data, 'getlist'):
            value = [item for item in data.getlist(key) if item != '']
        else:
            value = data[key]
        if key in ('city_id', 'commune_id'):
            value = _uuid_or_raw(value)
        elif key == 'logo' and value == '':
            value = None
        values[key] = value
    return values


def serialize_internal(request, organization, role):
    """`OrganizationInternal` (ADR 9.2) : détail réservé aux membres actifs."""
    verification = get_internal_verification(organization)
    category_ids = get_category_ids_by_organization([organization]).get(organization.pk, [])
    return {
        'id': str(organization.pk), 'name': organization.name, 'org_type': organization.org_type,
        'description': organization.description, 'logo': _logo_url(request, organization),
        # Minimisation (règle 10) : le NIF n'est lu que par les rôles qui peuvent le modifier.
        'nif': organization.nif if 'org.edit_profile' in capabilities.capabilities_for_role(role) else None,
        'city_id': str(organization.city_id) if organization.city_id else None,
        'commune_id': str(organization.commune_id) if organization.commune_id else None,
        'category_ids': [str(c) for c in category_ids],
        'status': organization.status, 'created_at': _iso(organization.created_at),
        'my_role': role, 'capabilities': capabilities.capabilities_for_role(role),
        'migrated_from_business': organization.legacy_business_profile_id is not None,
        'verification': {
            'required': verification['required'],
            'verified_claims': [_claim(c) for c in verification['verified_claims']],
            'summary': verification['summary'],
        },
    }


def _claim(claim):
    return {'code': claim['code'], 'label': claim['label'], 'verified_at': _iso(claim['verified_at'])}


def serialize_public(request, organization, category_ids, verification):
    """Élément de la liste publique : liste blanche stricte (règle 10). Jamais `nif`, `status`, `is_verified`,
    téléphone, e-mail, adresse exacte, membres ni créateur."""
    return {
        'id': str(organization.pk), 'name': organization.name, 'org_type': organization.org_type,
        'description': organization.description, 'logo': _logo_url(request, organization),
        'city_id': str(organization.city_id) if organization.city_id else None,
        'commune_id': str(organization.commune_id) if organization.commune_id else None,
        'category_ids': [str(c) for c in category_ids],
        'verified_claims': [_claim(c) for c in verification['verified_claims']],
        'verification_summary': verification['summary'],
        'member_since': _iso(organization.created_at),
    }


class OrganizationViewSet(viewsets.ViewSet):
    """`GET organizations/` (public, paginé) et `POST organizations/` (création, authentifié)."""

    acting_context_exempt = EXEMPT_REASON

    def get_throttles(self):
        """Défauts du projet (anonyme/utilisateur) + un throttle propre à l'action : lecture publique par IP
        pour `list`, plafond de création par compte pour `create`."""
        specific = OrganizationListThrottle if self.action == 'list' else OrganizationCreateThrottle
        return [throttle() for throttle in api_settings.DEFAULT_THROTTLE_CLASSES] + [specific()]

    def get_permissions(self):
        if self.action == 'list':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def list(self, request):
        paginator = StandardPagination()
        page = paginator.paginate_queryset(public_organizations_queryset(request.query_params), request, view=self)
        categories = get_category_ids_by_organization(page)
        verification = get_verification_data(page)
        results = [
            serialize_public(request, org, categories.get(org.pk, []), verification[org.pk]) for org in page
        ]
        return paginator.get_paginated_response(results)

    def create(self, request):
        # Un champ absent vaut `None` : le service le refuse par un 400 (jamais une erreur 500 sur un corps vide).
        values = {'name': None, 'org_type': None, **_extract(request, CREATE_FIELDS)}
        organization = create_organization(request.user, **values)
        return _private(Response(
            serialize_internal(request, organization, capabilities.ROLE_OWNER), status=status.HTTP_201_CREATED,
        ))


class OrganizationLimitsView(APIView):
    """`GET organizations/limits/` : limites lues dans les réglages (le front ne code aucune limite)."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return _private(Response(get_organization_limits()))


class OrganizationDetailView(APIView):
    """`PATCH organizations/<uuid>/` : identité de l'organisation (`org.edit_profile`)."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationWriteThrottle]
    http_method_names = ['patch', 'options']

    def patch(self, request, pk):
        organization = update_organization(request.user, pk, **_extract(request, UPDATE_FIELDS))
        return _private(Response(serialize_internal(request, organization, get_active_role(request.user.pk, organization.pk))))


class OrganizationInternalView(APIView):
    """`GET organizations/<uuid>/internal/` : détail interne (membre actif, `org.view_internal`). Non-membre :
    `DENY_RELATION` ; suspendue : `DENY_SECURITY` ; archivée : `DENY_OBJECT_STATE`."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        organization, role = get_organization_for_member(request.user, pk)
        return _private(Response(serialize_internal(request, organization, role)))


class OrganizationArchiveView(APIView):
    """`POST organizations/<uuid>/archive/` : archivage (`org.archive`, administrateur principal). Irréversible
    par l'API."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationWriteThrottle]

    def post(self, request, pk):
        organization = archive_organization(request.user, pk)
        return _private(Response(serialize_internal(request, organization, get_active_role(request.user.pk, organization.pk))))


class OrganizationLeaveView(APIView):
    """`POST organizations/<uuid>/leave/` : sortie volontaire (tout membre actif). Permise aussi sur une
    organisation suspendue ou archivée ; refusée au dernier administrateur principal (409 `last_owner`)."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationWriteThrottle]

    def post(self, request, pk):
        leave_organization(request.user, pk)
        return _private(Response(status=status.HTTP_204_NO_CONTENT))


# --- Équipe (ADR 0008, contrat L1-01 §1) ----------------------------------------------------------------------

# Composants OpenAPI définis UNE fois (une seule classe par nom de composant : aucune collision `Member`/`Scope`).
@extend_schema_serializer(component_name='Scope')
class ScopeSchemaSerializer(serializers.Serializer):
    """Objet `Scope` (contrat §7.1, clés exactes) : V1, seule valeur `{"type": "ORGANIZATION", "id": null}`."""

    type = serializers.ChoiceField(choices=capabilities.SCOPE_TYPES)
    id = serializers.UUIDField(allow_null=True)


@extend_schema_serializer(component_name='Member')
class MemberSchemaSerializer(serializers.Serializer):
    """Objet `Member` (contrat §0 et §7.1, clés exactes)."""

    membership_id = serializers.UUIDField()
    display_name = serializers.CharField()
    role = serializers.ChoiceField(choices=capabilities.ROLES)
    joined_at = serializers.DateTimeField()
    is_self = serializers.BooleanField()
    is_last_effective_owner = serializers.BooleanField(allow_null=True)
    scope = ScopeSchemaSerializer()


def _member_schema(**kwargs):
    return MemberSchemaSerializer(**kwargs)


MEMBER_SCHEMA = _member_schema()
MEMBER_PAGE_SCHEMA = inline_serializer('MemberPage', {
    'count': serializers.IntegerField(),
    'next': serializers.URLField(allow_null=True),
    'previous': serializers.URLField(allow_null=True),
    'results': _member_schema(many=True),
})
ROLE_CHANGE_SCHEMA = inline_serializer('MemberRoleChange', {
    'role': serializers.ChoiceField(choices=capabilities.ROLES),
    'scope': ScopeSchemaSerializer(required=False, allow_null=True),
    'confirm': serializers.BooleanField(required=False),
    'password': serializers.CharField(required=False, write_only=True),
})
TRANSFER_SCHEMA = inline_serializer('OwnershipTransfer', {
    'membership_id': serializers.UUIDField(),
    'my_new_role': serializers.ChoiceField(
        choices=('ADMIN', 'EDITOR', 'ANALYST'), required=False, default='ADMIN',
    ),
    'confirm': serializers.BooleanField(),
    'password': serializers.CharField(write_only=True),
})
TRANSFER_RESULT_SCHEMA = inline_serializer('OwnershipTransferResult', {
    'new_owner': _member_schema(), 'me': _member_schema(),
})


def serialize_scope(holder):
    """`Scope` d'une appartenance ou d'une invitation (contrat §7.1)."""
    return {'type': holder.scope_type, 'id': str(holder.scope_id) if holder.scope_id else None}


def serialize_member(membership, actor, can_manage, sole_owner_id):
    """`Member` (contrat §0 et §7.1, clés exactes). Jamais de téléphone, e-mail, nom complet, photo ni identifiant de
    compte. `is_last_effective_owner` n'est révélé qu'aux appelants `org.manage_members` (sinon `null`)."""
    return {
        'membership_id': str(membership.pk),
        'display_name': public_display_name(membership.user.full_name),
        'role': membership.role,
        'joined_at': _iso(membership.joined_at),
        'is_self': membership.user_id == actor.pk,
        'is_last_effective_owner': (membership.user_id == sole_owner_id) if can_manage else None,
        'scope': serialize_scope(membership),
    }


def _body(request):
    data = request.data
    if not hasattr(data, 'get'):
        raise serializers.ValidationError({'non_field_errors': ["Corps de requête invalide."]})
    return data


class OrganizationMembersView(APIView):
    """`GET organizations/<uuid>/members/` : membres actifs, paginé (`org.view_internal`, tout rôle).
    `POST` n'existe pas (405) : l'ajout direct est remplacé par les invitations (ADR 0008)."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'head', 'options']

    @extend_schema(
        operation_id='organizations_members_list', responses=MEMBER_PAGE_SCHEMA,
        parameters=[OpenApiParameter('page', int, required=False), OpenApiParameter('page_size', int, required=False)],
    )
    def get(self, request, pk):
        team = list_members(request.user, pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(team.queryset, request, view=self)
        results = [
            serialize_member(member, request.user, team.can_manage, team.sole_effective_owner_id) for member in page
        ]
        return _private(paginator.get_paginated_response(results))


@method_decorator(sensitive_post_parameters('password'), name='dispatch')
class OrganizationMemberDetailView(APIView):
    """`PATCH` (rôle) et `DELETE` (retrait) d'un membre, par `membership_id`. Le mot de passe n'est exigé que pour
    un siège d'administrateur principal (ADR 0008 §8.2)."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationWriteThrottle, OrganizationSensitiveThrottle]
    http_method_names = ['patch', 'delete', 'options']

    @extend_schema(operation_id='organizations_members_change_role', request=ROLE_CHANGE_SCHEMA, responses=MEMBER_SCHEMA)
    def patch(self, request, pk, membership_id):
        data = _body(request)
        membership = change_role(
            request.user, pk, membership_id, data.get('role'),
            confirm=data.get('confirm') is True, password=data.get('password'), scope=data.get('scope'),
        )
        sole = sole_effective_owner_id(pk)
        return _private(Response(serialize_member(membership, request.user, True, sole)))

    @extend_schema(operation_id='organizations_members_remove', request=None, responses={204: None})
    def delete(self, request, pk, membership_id):
        remove_member(request.user, pk, membership_id)
        return _private(Response(status=status.HTTP_204_NO_CONTENT))


@method_decorator(sensitive_post_parameters('password'), name='dispatch')
class OrganizationTransferOwnershipView(APIView):
    """`POST organizations/<uuid>/transfer-ownership/` : transfert atomique du rôle d'administrateur
    principal (`confirm` et ressaisie du mot de passe obligatoires)."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationSensitiveThrottle]

    @extend_schema(operation_id='organizations_transfer_ownership', request=TRANSFER_SCHEMA, responses=TRANSFER_RESULT_SCHEMA)
    def post(self, request, pk):
        data = _body(request)
        membership_id = parse_uuid(data.get('membership_id'))
        if membership_id is None:
            raise serializers.ValidationError({'membership_id': ["Identifiant de membre invalide ou manquant."]})
        extra = {'my_new_role': data['my_new_role']} if 'my_new_role' in data else {}
        target, me = transfer_ownership_to(
            request.user, pk, membership_id, confirm=data.get('confirm') is True, password=data.get('password'),
            **extra,
        )
        sole = sole_effective_owner_id(pk)
        can_manage = capabilities.role_has_capability(me.role, 'org.manage_members')
        return _private(Response({
            'new_owner': serialize_member(target, request.user, can_manage, sole),
            'me': serialize_member(me, request.user, can_manage, sole),
        }))
