"""Endpoints des invitations d'équipe (ADR 0008, contrat d'API L1-01 §2 ; invitations v2 : ADR 0010 D4, contrat
§7.4). Vues fines : la logique est dans `invitations.py`, exposé par `identity.services`.

Le jeton voyage dans le CORPS des POST d'aperçu, d'acceptation et de refus, jamais dans l'URL ni dans une clé de
cache ; `sensitive_post_parameters('token')` le masque des rapports d'erreur (et `password` pour la confirmation).
Toute réponse est `Cache-Control: private, no-store` (celle de création porte `link_token`, relisible nulle part
ailleurs). L'en-tête `X-Context` est ignoré (organisation désignée par le chemin ou invitation désignée par le jeton
ou par la personne qui l'a acceptée).
"""
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination

from . import capabilities
from .models import INVITABLE_ROLES, OrganizationInvitation
from .services import (
    ACCEPTANCE_ACTIVE, accept_invitation, confirm_invitation, create_invitation, decline_invitation, effective_status,
    list_invitations, list_my_awaiting_invitations, phone_hint, preview_invitation, public_display_name,
    reject_invitation, requires_confirmation, revoke_invitation, sole_effective_owner_id, withdraw_awaiting_invitation,
)
from .throttles import (
    InvitationCreateOrgThrottle, InvitationCreateThrottle, InvitationRedeemIpThrottle, InvitationRedeemUserThrottle,
    OrganizationSensitiveThrottle, OrganizationWriteThrottle,
)
from .views_organizations import (
    EXEMPT_REASON, MEMBER_SCHEMA, ScopeSchemaSerializer, _body, _iso, _private, serialize_member, serialize_scope,
)

_STATUSES = [value for value, _ in OrganizationInvitation.STATUS_CHOICES]
_AWAITING_STATUSES = [OrganizationInvitation.STATUS_AWAITING_CONFIRMATION, OrganizationInvitation.STATUS_EXPIRED]


def _invitation_schema(**kwargs):
    return inline_serializer('Invitation', {
        'invitation_id': serializers.UUIDField(),
        'role': serializers.ChoiceField(choices=INVITABLE_ROLES),
        'status': serializers.ChoiceField(choices=_STATUSES),
        'label': serializers.CharField(allow_blank=True),
        'created_at': serializers.DateTimeField(),
        'expires_at': serializers.DateTimeField(),
        'created_by_display_name': serializers.CharField(allow_null=True),
        'is_mine': serializers.BooleanField(),
        'scope': ScopeSchemaSerializer(),
        'requires_confirmation': serializers.BooleanField(),
        'accepted_at': serializers.DateTimeField(allow_null=True),
        'confirmation_expires_at': serializers.DateTimeField(allow_null=True),
        'accepted_by_display_name': serializers.CharField(allow_null=True),
        'accepted_by_phone_hint': serializers.CharField(allow_null=True),
        'can_confirm': serializers.BooleanField(),
    }, **kwargs)


INVITATION_PAGE_SCHEMA = inline_serializer('InvitationPage', {
    'count': serializers.IntegerField(),
    'next': serializers.URLField(allow_null=True),
    'previous': serializers.URLField(allow_null=True),
    'results': _invitation_schema(many=True),
})
INVITATION_CREATE_SCHEMA = inline_serializer('InvitationCreate', {
    'role': serializers.ChoiceField(choices=INVITABLE_ROLES),
    'label': serializers.CharField(required=False, allow_blank=True, max_length=60),
    'scope': ScopeSchemaSerializer(required=False, allow_null=True),
})
INVITATION_CREATED_SCHEMA = inline_serializer('InvitationCreated', {
    'invitation_id': serializers.UUIDField(),
    'role': serializers.ChoiceField(choices=INVITABLE_ROLES),
    'status': serializers.ChoiceField(choices=_STATUSES),
    'label': serializers.CharField(allow_blank=True),
    'created_at': serializers.DateTimeField(),
    'expires_at': serializers.DateTimeField(),
    'link_token': serializers.CharField(),
    'scope': ScopeSchemaSerializer(),
    'requires_confirmation': serializers.BooleanField(),
})
TOKEN_SCHEMA = inline_serializer('InvitationToken', {'token': serializers.CharField(write_only=True)})
PREVIEW_SCHEMA = inline_serializer('InvitationPreview', {
    'organization_name': serializers.CharField(),
    'org_type': serializers.CharField(),
    'role': serializers.ChoiceField(choices=capabilities.ROLES),
    'expires_at': serializers.DateTimeField(),
    'invited_by_display_name': serializers.CharField(),
    'scope': ScopeSchemaSerializer(),
    'capabilities': serializers.ListField(child=serializers.CharField()),
    'requires_confirmation': serializers.BooleanField(),
})
ACCEPTED_SCHEMA = inline_serializer('InvitationAccepted', {
    'status': serializers.ChoiceField(choices=[ACCEPTANCE_ACTIVE]),
    'organization_id': serializers.UUIDField(),
    'organization_name': serializers.CharField(),
    'role': serializers.ChoiceField(choices=capabilities.ROLES),
    'membership_id': serializers.UUIDField(),
})
AWAITING_ACCEPTED_SCHEMA = inline_serializer('InvitationAwaitingConfirmation', {
    'status': serializers.ChoiceField(choices=[OrganizationInvitation.STATUS_AWAITING_CONFIRMATION]),
    'invitation_id': serializers.UUIDField(),
    'organization_name': serializers.CharField(),
    'role': serializers.ChoiceField(choices=capabilities.ROLES),
    'confirmation_expires_at': serializers.DateTimeField(),
})
CONFIRM_SCHEMA = inline_serializer('InvitationConfirm', {
    'confirm': serializers.BooleanField(),
    'password': serializers.CharField(write_only=True),
})
MY_AWAITING_PAGE_SCHEMA = inline_serializer('MyAwaitingInvitationPage', {
    'count': serializers.IntegerField(),
    'next': serializers.URLField(allow_null=True),
    'previous': serializers.URLField(allow_null=True),
    'results': inline_serializer('MyAwaitingInvitation', {
        'invitation_id': serializers.UUIDField(),
        'organization_name': serializers.CharField(),
        'org_type': serializers.CharField(),
        'role': serializers.ChoiceField(choices=INVITABLE_ROLES),
        'scope': ScopeSchemaSerializer(),
        'accepted_at': serializers.DateTimeField(),
        'confirmation_expires_at': serializers.DateTimeField(),
        'status': serializers.ChoiceField(choices=_AWAITING_STATUSES),
    }, many=True),
})


def serialize_invitation(invitation, actor, now, listing=None):
    """`Invitation` (contrat §0 et §7.4) : statut EFFECTIF, étiquette vide hors `PENDING`, jamais le jeton ni son
    empreinte. Nom abrégé et indice de téléphone de la personne qui a accepté : SEULEMENT si l'invitation attend une
    confirmation que l'appelant peut donner (`can_confirm`) ; `null` sinon."""
    current = effective_status(invitation, now)
    author = invitation.created_by
    can_confirm = listing.can_confirm(invitation, now) if listing is not None else False
    accepted = invitation.accepted_by if can_confirm else None
    return {
        'invitation_id': str(invitation.pk),
        'role': invitation.role,
        'status': current,
        'label': invitation.label if current == OrganizationInvitation.STATUS_PENDING else '',
        'created_at': _iso(invitation.created_at),
        'expires_at': _iso(invitation.expires_at),
        'created_by_display_name': public_display_name(author.full_name) if author is not None else None,
        'is_mine': invitation.created_by_id == actor.pk,
        'scope': serialize_scope(invitation),
        'requires_confirmation': requires_confirmation(invitation.role),
        'accepted_at': _iso(invitation.accepted_at) if invitation.accepted_at else None,
        'confirmation_expires_at': (
            _iso(invitation.confirmation_expires_at) if invitation.confirmation_expires_at else None
        ),
        'accepted_by_display_name': public_display_name(accepted.full_name) if accepted is not None else None,
        'accepted_by_phone_hint': phone_hint(accepted) if accepted is not None else None,
        'can_confirm': can_confirm,
    }


def _token(request):
    """Jeton du corps. Champ absent : 400 `{"token": [...]}` ; toute autre valeur est jugée par le service (404
    uniforme, pour ne rien révéler sur la forme attendue)."""
    token = _body(request).get('token')
    if token is None:
        raise serializers.ValidationError({'token': ["Ce champ est obligatoire."]})
    return token


class OrganizationInvitationsView(APIView):
    """`GET` (liste paginée, `?status=`) et `POST` (création) des invitations d'une organisation
    (`org.manage_members`). Le jeton n'est renvoyé que par le `POST`."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [InvitationCreateThrottle]  # le quota par organisation est compté après l'autorisation
    http_method_names = ['get', 'post', 'head', 'options']

    @extend_schema(
        operation_id='organizations_invitations_list', responses=INVITATION_PAGE_SCHEMA,
        parameters=[
            OpenApiParameter('status', str, required=False, enum=_STATUSES),
            OpenApiParameter('page', int, required=False), OpenApiParameter('page_size', int, required=False),
        ],
    )
    def get(self, request, pk):
        listing = list_invitations(request.user, pk, request.query_params.get('status'))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(listing.queryset, request, view=self)
        now = timezone.now()
        return _private(paginator.get_paginated_response(
            [serialize_invitation(invitation, request.user, now, listing) for invitation in page],
        ))

    @extend_schema(
        operation_id='organizations_invitations_create', request=INVITATION_CREATE_SCHEMA,
        responses={201: INVITATION_CREATED_SCHEMA},
    )
    def post(self, request, pk):
        data = _body(request)
        org_quota = InvitationCreateOrgThrottle()
        invitation, token = create_invitation(
            request.user, pk, data.get('role'), data.get('label', ''), scope=data.get('scope'),
            after_authorization=lambda: org_quota.enforce(request, self),
        )
        return _private(Response({
            'invitation_id': str(invitation.pk), 'role': invitation.role, 'status': invitation.status,
            'label': invitation.label, 'created_at': _iso(invitation.created_at),
            'expires_at': _iso(invitation.expires_at), 'link_token': token,
            'scope': serialize_scope(invitation), 'requires_confirmation': requires_confirmation(invitation.role),
        }, status=status.HTTP_201_CREATED))


class OrganizationInvitationDetailView(APIView):
    """`DELETE organizations/<uuid>/invitations/<uuid>/` : révocation (`org.manage_members`), `PENDING` seulement."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationWriteThrottle]
    http_method_names = ['delete', 'options']

    @extend_schema(operation_id='organizations_invitations_revoke', request=None, responses={204: None})
    def delete(self, request, pk, invitation_id):
        revoke_invitation(request.user, pk, invitation_id)
        return _private(Response(status=status.HTTP_204_NO_CONTENT))


@method_decorator(sensitive_post_parameters('password'), name='dispatch')
class OrganizationInvitationConfirmView(APIView):
    """`POST organizations/<uuid>/invitations/<uuid>/confirm/` : confirmation d'une invitation Administrateur en
    attente, par l'émetteur habilité ou un administrateur principal effectif, avec ressaisie du mot de passe
    (contrat §7.4.6). Réponse : `Member` de la personne entrée."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationSensitiveThrottle]
    http_method_names = ['post', 'options']

    @extend_schema(operation_id='organizations_invitations_confirm', request=CONFIRM_SCHEMA, responses=MEMBER_SCHEMA)
    def post(self, request, pk, invitation_id):
        data = _body(request)
        membership = confirm_invitation(
            request.user, pk, invitation_id, confirm=data.get('confirm') is True, password=data.get('password'),
        )
        # L'appelant a `org.manage_members` (sinon refusé) : `is_last_effective_owner` lui est révélé.
        return _private(Response(serialize_member(membership, request.user, True, sole_effective_owner_id(pk))))


class OrganizationInvitationRejectView(APIView):
    """`POST organizations/<uuid>/invitations/<uuid>/reject/` : rejet d'une invitation en attente de confirmation
    (mêmes acteurs que la confirmation, sans ressaisie)."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationWriteThrottle]
    http_method_names = ['post', 'options']

    @extend_schema(operation_id='organizations_invitations_reject', request=None, responses={204: None})
    def post(self, request, pk, invitation_id):
        reject_invitation(request.user, pk, invitation_id)
        return _private(Response(status=status.HTTP_204_NO_CONTENT))


class _RedeemView(APIView):
    """Socle des trois routes d'échange : compte connecté, aucune capacité, jeton dans le corps, throttles par IP et
    par compte (jamais par jeton)."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [InvitationRedeemIpThrottle, InvitationRedeemUserThrottle]
    http_method_names = ['post', 'options']


@method_decorator(sensitive_post_parameters('token'), name='dispatch')
class InvitationPreviewView(_RedeemView):
    """`POST organization-invitations/preview/` : aperçu sans effet de bord."""

    @extend_schema(operation_id='organization_invitations_preview', request=TOKEN_SCHEMA, responses=PREVIEW_SCHEMA)
    def post(self, request):
        preview = preview_invitation(request.user, _token(request))
        scope = preview['scope']
        return _private(Response({
            **preview, 'expires_at': _iso(preview['expires_at']),
            'scope': {'type': scope.type, 'id': str(scope.id) if scope.id else None},
        }))


@method_decorator(sensitive_post_parameters('token'), name='dispatch')
class InvitationAcceptView(_RedeemView):
    """`POST organization-invitations/accept/` : acceptation. Rôle sans confirmation : 200, appartenance créée ou
    réactivée. Rôle Administrateur : 202, attente de confirmation, aucune appartenance (contrat §7.4.5)."""

    @extend_schema(
        operation_id='organization_invitations_accept', request=TOKEN_SCHEMA,
        responses={
            200: ACCEPTED_SCHEMA,
            202: OpenApiResponse(AWAITING_ACCEPTED_SCHEMA, description="En attente de confirmation : aucun accès."),
        },
    )
    def post(self, request):
        result = accept_invitation(request.user, _token(request))
        if result.status == ACCEPTANCE_ACTIVE:
            membership = result.membership
            return _private(Response({
                'status': ACCEPTANCE_ACTIVE, 'organization_id': str(membership.organization_id),
                'organization_name': result.organization.name, 'role': membership.role,
                'membership_id': str(membership.pk),
            }))
        return _private(Response({
            'status': result.status, 'invitation_id': str(result.invitation.pk),
            'organization_name': result.organization.name, 'role': result.role,
            'confirmation_expires_at': _iso(result.confirmation_expires_at),
        }, status=status.HTTP_202_ACCEPTED))


@method_decorator(sensitive_post_parameters('token'), name='dispatch')
class InvitationDeclineView(_RedeemView):
    """`POST organization-invitations/decline/` : refus (l'inviteur est notifié sans nom)."""

    @extend_schema(operation_id='organization_invitations_decline', request=TOKEN_SCHEMA, responses={204: None})
    def post(self, request):
        decline_invitation(request.user, _token(request))
        return _private(Response(status=status.HTTP_204_NO_CONTENT))


def serialize_my_awaiting(invitation, now):
    """Élément de « mes adhésions en attente » (contrat §7.4.7, clés exactes)."""
    organization = invitation.organization
    return {
        'invitation_id': str(invitation.pk),
        'organization_name': organization.name,
        'org_type': organization.org_type,
        'role': invitation.role,
        'scope': serialize_scope(invitation),
        'accepted_at': _iso(invitation.accepted_at),
        'confirmation_expires_at': _iso(invitation.confirmation_expires_at),
        'status': effective_status(invitation, now),
    }


class MyAwaitingInvitationsView(APIView):
    """`GET organization-invitations/awaiting/` : invitations acceptées par l'appelant et en attente de confirmation
    (et échues depuis peu, pour information). Paginé ; strictement le compte appelant."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'head', 'options']

    @extend_schema(
        operation_id='organization_invitations_awaiting', responses=MY_AWAITING_PAGE_SCHEMA,
        parameters=[OpenApiParameter('page', int, required=False), OpenApiParameter('page_size', int, required=False)],
    )
    def get(self, request):
        paginator = StandardPagination()
        page = paginator.paginate_queryset(list_my_awaiting_invitations(request.user), request, view=self)
        now = timezone.now()
        return _private(paginator.get_paginated_response([serialize_my_awaiting(row, now) for row in page]))


class InvitationWithdrawView(APIView):
    """`POST organization-invitations/<uuid>/withdraw/` : la personne qui a accepté retire sa demande en attente."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationWriteThrottle]
    http_method_names = ['post', 'options']

    @extend_schema(operation_id='organization_invitations_withdraw', request=None, responses={204: None})
    def post(self, request, invitation_id):
        withdraw_awaiting_invitation(request.user, invitation_id)
        return _private(Response(status=status.HTTP_204_NO_CONTENT))
