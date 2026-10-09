from rest_framework import permissions as drf_permissions
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import OptionalPagination
from apps.common.throttles import ActionScopedThrottleMixin
from apps.identity import services as identity_services
from apps.marketplace import services as marketplace_services
from apps.notifications import services as notification_services

from . import permissions, services
from .models import AuditLog, Report, ReportClosedError, Sanction
from .serializers import ReportSerializer, SanctionSerializer

NOTES_MAX_LENGTH = 1000


def _notes(request):
    """Notes de décision (texte libre, sans donnée personnelle) bornées en longueur."""
    notes = request.data.get('notes', '')
    if not isinstance(notes, str):
        raise ValidationError({'notes': "Les notes doivent être un texte."})
    if len(notes) > NOTES_MAX_LENGTH:
        raise ValidationError({'notes': f"Les notes ne peuvent pas dépasser {NOTES_MAX_LENGTH} caractères."})
    return notes


class ReportViewSet(ActionScopedThrottleMixin, viewsets.ModelViewSet):
    """CDC 3.11 : file unique de signalements, prise en charge, décision."""

    serializer_class = ReportSerializer
    http_method_names = ['get', 'post', 'head', 'options']
    pagination_class = OptionalPagination
    throttle_scopes = {'create': 'report'}
    required_permissions = {
        'list': permissions.VIEW_REPORT, 'retrieve': permissions.VIEW_REPORT,
        'claim': permissions.CHANGE_REPORT, 'resolve': permissions.CHANGE_REPORT,
        'reject': permissions.CHANGE_REPORT,
    }

    def get_permissions(self):
        if self.action == 'create':
            return [drf_permissions.IsAuthenticated()]
        return [permissions.HasModerationPermission()]

    def get_queryset(self):
        queryset = Report.objects.select_related('reporter', 'assigned_to')
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        reports = list(page if page is not None else queryset)
        serializer = self.get_serializer(
            reports, many=True, context={**self.get_serializer_context(),
                                         'target_labels': services.resolve_labels_for_reports(reports)},
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)

    def _decide(self, request, transition, audit_action, notes=None):
        report = self.get_object()
        try:
            transition(report)
        except ReportClosedError as error:
            return Response({"error": str(error)}, status=status.HTTP_409_CONFLICT)
        AuditLog.record(request.user, audit_action, target=report, details=notes or '')
        return Response(ReportSerializer(report, context=self.get_serializer_context()).data)

    @action(detail=True, methods=['post'])
    def claim(self, request, pk=None):
        return self._decide(request, lambda report: report.claim(request.user), 'REPORT_CLAIMED')

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        notes = _notes(request)
        return self._decide(request, lambda report: report.resolve(notes=notes), 'REPORT_RESOLVED', notes)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        notes = _notes(request)
        return self._decide(request, lambda report: report.reject(notes=notes), 'REPORT_REJECTED', notes)


HEAVY_SANCTION_MESSAGE = "Seul un administrateur peut prononcer ou lever une suspension ou un bannissement."


class SanctionViewSet(viewsets.ModelViewSet):
    """CDC 3.11 : avertissement, masquage d'annonce, suspension, bannissement."""

    serializer_class = SanctionSerializer
    http_method_names = ['get', 'post', 'head', 'options']
    pagination_class = OptionalPagination
    queryset = Sanction.objects.select_related('user', 'issued_by')
    permission_classes = [permissions.HasModerationPermission]
    required_permissions = {
        'list': permissions.VIEW_SANCTION, 'retrieve': permissions.VIEW_SANCTION,
        'create': permissions.ADD_SANCTION, 'lift': permissions.ADD_SANCTION,
    }

    def perform_create(self, serializer):
        sanction_type = serializer.validated_data.get('sanction_type')
        user = self.request.user
        if sanction_type not in Sanction.MODERATOR_ALLOWED_TYPES and not permissions.is_administrator(user):
            raise PermissionDenied(HEAVY_SANCTION_MESSAGE)
        sanction = serializer.save(issued_by=user)
        sanction.apply()

        notification_services.notify(
            user_id=sanction.user_id,
            notification_type=notification_services.SYSTEM,
            title="Sanction appliquée à votre compte",
            content=f"{sanction.get_sanction_type_display()} : {sanction.reason[:100]}",
        )

        AuditLog.record(user, f'SANCTION_{sanction_type}', target=sanction, details=sanction.reason)

    @action(detail=True, methods=['post'])
    def lift(self, request, pk=None):
        sanction = self.get_object()
        if sanction.sanction_type not in Sanction.MODERATOR_ALLOWED_TYPES and not permissions.is_administrator(request.user):
            raise PermissionDenied(HEAVY_SANCTION_MESSAGE)
        if not sanction.is_active:
            return Response({"error": "Cette sanction n'est plus active."}, status=status.HTTP_400_BAD_REQUEST)
        sanction.lift()
        AuditLog.record(request.user, 'SANCTION_LIFTED', target=sanction)
        return Response(SanctionSerializer(sanction, context=self.get_serializer_context()).data)


class ModerationDashboardView(APIView):
    """CDC 3.11 : tableau de bord (utilisateurs, annonces, signalements en
    attente). Les revenus (P3) ne sont pas encore pertinents."""

    permission_classes = [drf_permissions.IsAuthenticated]

    def get(self, request):
        if not permissions.can_moderate(request.user):
            raise PermissionDenied()
        return Response({
            'users_count': identity_services.count_users(),
            'active_posts_count': marketplace_services.count_active_offers(),
            'pending_reports_count': Report.objects.filter(status=Report.STATUS_EN_ATTENTE).count(),
            'pending_kyc_count': identity_services.count_pending_kyc_documents(),
        })
