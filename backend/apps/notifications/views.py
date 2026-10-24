from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.pagination import OptionalPagination

from . import services
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    """Notifications de l'utilisateur connecté : lecture, marquage « lu », suppression.
    La création est réservée au système (`services.notify`)."""

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    # Notifications du compte, tous contextes confondus (ADR 0006, 9.8) : l'en-tête X-Context est ignoré.
    acting_context_exempt = "toujours personnel : les notifications appartiennent au compte (ADR 0006, 9.8)"
    pagination_class = OptionalPagination
    http_method_names = ['get', 'patch', 'delete', 'post', 'head', 'options']

    def get_queryset(self):
        return services.visible_notifications(self.request.user.id).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        return Response(
            {"error": "Les notifications sont créées par le système."}, status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        services.mark_all_read(request.user.id)
        return Response({'status': 'notifications marked as read'})
