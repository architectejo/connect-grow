"""Endpoints des invitations d'équipe (ADR 0008, contrat d'API L1-01 §2). Vues fines : la logique est dans
`invitations.py`, exposé par `identity.services`.

Le jeton voyage dans le CORPS des POST d'aperçu, d'acceptation et de refus, jamais dans l'URL ni dans une clé de
cache ; `sensitive_post_parameters('token')` le masque des rapports d'erreur. Toute réponse est `Cache-Control:
private, no-store` (celle de création porte `link_token`, relisible nulle part ailleurs). L'en-tête `X-Context` est
ignoré (organisation désignée par le chemin ou invitation désignée par le jeton).
"""
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination

from . import capabilities
from .models import INVITABLE_ROLES, OrganizationInvitation
from .services import (
    accept_invitation, create_invitation, decline_invitation, effective_status, list_invitations, preview_invitation,
    public_display_name, revoke_invitation,
)
from .throttles import (
    InvitationCreateOrgThrottle, InvitationCreateThrottle, InvitationRedeemIpThrottle, InvitationRedeemUserThrottle,
    OrganizationWriteThrottle,
)
from .views_organizations import EXEMPT_REASON, _body, _iso, _private

_STATUSES = [value for value, _ in OrganizationInvitation.STATUS_CHOICES]

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
})
INVITATION_CREATED_SCHEMA = inline_serializer('InvitationCreated', {
    'invitation_id': serializers.UUIDField(),
    'role': serializers.ChoiceField(choices=INVITABLE_ROLES),
    'status': serializers.ChoiceField(choices=_STATUSES),
    'label': serializers.CharField(allow_blank=True),
    'created_at': serializers.DateTimeField(),
    'expires_at': serializers.DateTimeField(),
    'link_token': serializers.CharField(),
})
TOKEN_SCHEMA = inline_serializer('InvitationToken', {'token': serializers.CharField(write_only=True)})
PREVIEW_SCHEMA = inline_serializer('InvitationPreview', {
    'organization_name': serializers.CharField(),
    'org_type': serializers.CharField(),
    'role': serializers.ChoiceField(choices=capabilities.ROLES),
    'expires_at': serializers.DateTimeField(),
    'invited_by_display_name': serializers.CharField(),
})
ACCEPTED_SCHEMA = inline_serializer('InvitationAccepted', {
    'organization_id': serializers.UUIDField(),
    'organization_name': serializers.CharField(),
    'role': serializers.ChoiceField(choices=capabilities.ROLES),
    'membership_id': serializers.UUIDField(),
})


def serialize_invitation(invitation, actor, now):
    """`Invitation` (contrat §0) : statut EFFECTIF, étiquette vide hors `PENDING`, jamais le jeton ni son empreinte."""
    current = effective_status(invitation, now)
    author = invitation.created_by
    return {
        'invitation_id': str(invitation.pk),
        'role': invitation.role,
        'status': current,
        'label': invitation.label if current == OrganizationInvitation.STATUS_PENDING else '',
        'created_at': _iso(invitation.created_at),
        'expires_at': _iso(invitation.expires_at),
        'created_by_display_name': public_display_name(author.full_name) if author is not None else None,
        'is_mine': invitation.created_by_id == actor.pk,
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
    throttle_classes = [InvitationCreateThrottle, InvitationCreateOrgThrottle]
    http_method_names = ['get', 'post', 'head', 'options']

    @extend_schema(
        operation_id='organizations_invitations_list', responses=INVITATION_PAGE_SCHEMA,
        parameters=[
            OpenApiParameter('status', str, required=False, enum=_STATUSES),
            OpenApiParameter('page', int, required=False), OpenApiParameter('page_size', int, required=False),
        ],
    )
    def get(self, request, pk):
        rows = list_invitations(request.user, pk, request.query_params.get('status'))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        now = timezone.now()
        return _private(paginator.get_paginated_response(
            [serialize_invitation(invitation, request.user, now) for invitation in page],
        ))

    @extend_schema(
        operation_id='organizations_invitations_create', request=INVITATION_CREATE_SCHEMA,
        responses={201: INVITATION_CREATED_SCHEMA},
    )
    def post(self, request, pk):
        data = _body(request)
        invitation, token = create_invitation(request.user, pk, data.get('role'), data.get('label', ''))
        return _private(Response({
            'invitation_id': str(invitation.pk), 'role': invitation.role, 'status': invitation.status,
            'label': invitation.label, 'created_at': _iso(invitation.created_at),
            'expires_at': _iso(invitation.expires_at), 'link_token': token,
        }, status=status.HTTP_201_CREATED))


class OrganizationInvitationDetailView(APIView):
    """`DELETE organizations/<uuid>/invitations/<uuid>/` : révocation (`org.manage_members`)."""

    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [OrganizationWriteThrottle]
    http_method_names = ['delete', 'options']

    @extend_schema(operation_id='organizations_invitations_revoke', request=None, responses={204: None})
    def delete(self, request, pk, invitation_id):
        revoke_invitation(request.user, pk, invitation_id)
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
        return _private(Response({**preview, 'expires_at': _iso(preview['expires_at'])}))


@method_decorator(sensitive_post_parameters('token'), name='dispatch')
class InvitationAcceptView(_RedeemView):
    """`POST organization-invitations/accept/` : acceptation (appartenance créée ou réactivée au rôle invité)."""

    @extend_schema(operation_id='organization_invitations_accept', request=TOKEN_SCHEMA, responses=ACCEPTED_SCHEMA)
    def post(self, request):
        membership = accept_invitation(request.user, _token(request))
        return _private(Response({
            'organization_id': str(membership.organization_id), 'organization_name': membership.organization.name,
            'role': membership.role, 'membership_id': str(membership.pk),
        }))


@method_decorator(sensitive_post_parameters('token'), name='dispatch')
class InvitationDeclineView(_RedeemView):
    """`POST organization-invitations/decline/` : refus (l'inviteur est notifié sans nom)."""

    @extend_schema(operation_id='organization_invitations_decline', request=TOKEN_SCHEMA, responses={204: None})
    def post(self, request):
        decline_invitation(request.user, _token(request))
        return _private(Response(status=status.HTTP_204_NO_CONTENT))
