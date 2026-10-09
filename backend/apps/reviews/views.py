from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.common.pagination import OptionalPagination
from apps.common.utils import parse_uuid

from . import services
from .models import Deal, Review
from .serializers import DealSerializer, ReviewSerializer

REPLY_MAX_LENGTH = 500


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    pagination_class = OptionalPagination

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = Review.objects.select_related('user')
        user = self.request.user
        is_staff = user.is_authenticated and user.is_staff
        # CDC 3.7 : un avis retiré par la modération n'apparaît plus dans les listes publiques ;
        # son auteur et l'administration peuvent encore le consulter par son identifiant.
        if not is_staff:
            if self.action == 'list' or not user.is_authenticated:
                queryset = queryset.filter(is_hidden=False)
            else:
                queryset = queryset.filter(Q(is_hidden=False) | Q(user=user))
        offer_id = self.request.query_params.get('post')
        if offer_id:
            offer_uuid = parse_uuid(offer_id)
            queryset = queryset.filter(offer_id=offer_uuid) if offer_uuid else queryset.none()
        return queryset.order_by('-created_at')

    def perform_create(self, serializer):
        review = serializer.save(user=self.request.user)
        services.notify_review_created(review, self.request.user)

    def perform_destroy(self, instance):
        if instance.user_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez pas supprimer l'avis d'un autre utilisateur.")
        instance.delete()

    def perform_update(self, serializer):
        if serializer.instance.user_id != self.request.user.id:
            raise PermissionDenied("Vous ne pouvez pas modifier l'avis d'un autre utilisateur.")
        serializer.save()

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        review = self.get_object()
        if review.reviewed_user_id != request.user.id:
            return Response(
                {"error": "Seule la personne évaluée peut répondre à cet avis."},
                status=status.HTTP_403_FORBIDDEN,
            )

        reply_content = request.data.get('reply_content')
        if not isinstance(reply_content, str) or not reply_content.strip():
            return Response({"error": "Le contenu de la réponse est requis."}, status=status.HTTP_400_BAD_REQUEST)
        reply_content = reply_content.strip()
        if len(reply_content) > REPLY_MAX_LENGTH:
            return Response(
                {"error": f"La réponse ne doit pas dépasser {REPLY_MAX_LENGTH} caractères."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        services.reply_to_review(review, request.user, reply_content)
        return Response(self.get_serializer(review).data)


class DealViewSet(viewsets.ModelViewSet):
    """CDC 3.7 : déclaration et confirmation d'une affaire conclue."""

    serializer_class = DealSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OptionalPagination
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        return Deal.objects.filter(Q(initiator=user) | Q(counterparty=user)).select_related('initiator', 'counterparty')

    def perform_create(self, serializer):
        serializer.save(initiator=self.request.user)

    def _answer(self, request, verb, apply):
        deal = self.get_object()
        if deal.counterparty_id != request.user.id:
            return Response(
                {"error": f"Seule la contrepartie peut {verb} cette affaire."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if deal.status != Deal.STATUS_PENDING:
            return Response({"error": "Cette affaire n'est plus en attente."}, status=status.HTTP_400_BAD_REQUEST)
        apply(deal)
        return Response(self.get_serializer(deal).data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        return self._answer(request, 'confirmer', Deal.confirm)

    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        return self._answer(request, 'refuser', Deal.decline)
