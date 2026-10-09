from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.exception_handler import CodedAPIException
from apps.common.pagination import OptionalPagination
from apps.common.throttles import ActionScopedThrottleMixin
from apps.common.utils import parse_uuid

from . import services
from .models import Review
from .serializers import (
    ReviewCreateSerializer, ReviewReplySerializer, ReviewSerializer, ReviewUpdateSerializer,
)


def _api_error(exc):
    return CodedAPIException(exc.message, exc.code, exc.status_code)


class ReviewViewSet(ActionScopedThrottleMixin, viewsets.ModelViewSet):
    """Avis après contact (ADR 0004, 7.2). Création, modification et suppression passent par
    `services.py` ; la vue ne porte que la validation du corps et le format d'erreur."""

    throttle_scopes = {'create': 'review'}
    serializer_class = ReviewSerializer
    pagination_class = OptionalPagination
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = Review.objects.select_related('user')
        user = self.request.user
        is_staff = user.is_authenticated and user.is_staff
        # Un avis masqué par la modération n'apparaît plus dans les listes publiques ; son auteur
        # et l'administration peuvent encore le consulter par son identifiant.
        if not is_staff:
            if self.action == 'list' or not user.is_authenticated:
                queryset = queryset.filter(is_hidden=False)
            else:
                queryset = queryset.filter(Q(is_hidden=False) | Q(user=user))
        params = self.request.query_params
        for param, column in (('post', 'offer_id'), ('seller', 'seller_context_id')):
            raw = params.get(param)
            if raw:
                parsed = parse_uuid(raw)
                queryset = queryset.filter(**{column: parsed}) if parsed else queryset.none()
        return queryset.order_by('-created_at', 'id')

    def create(self, request, *args, **kwargs):
        body = ReviewCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            review = services.create_review(
                request.user, offer_id=data['post'], offer_rating=data['offer_rating'],
                seller_rating=data['seller_rating'], content=data['content'],
            )
        except services.ReviewError as exc:
            raise _api_error(exc)
        return Response(self.get_serializer(review).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        review = self.get_object()
        self._ensure_author(review)
        body = ReviewUpdateSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        try:
            review = services.update_review(review, body.validated_data)
        except services.ReviewError as exc:
            raise _api_error(exc)
        return Response(self.get_serializer(review).data)

    def destroy(self, request, *args, **kwargs):
        review = self.get_object()
        self._ensure_author(review)
        try:
            services.delete_review(review)
        except services.ReviewError as exc:
            raise _api_error(exc)
        return Response(status=204)

    def _ensure_author(self, review):
        if review.user_id != self.request.user.id:
            raise CodedAPIException("Vous ne pouvez pas modifier ni supprimer l'avis d'un autre utilisateur.", 'not_author', 403)

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        review = self.get_object()
        if not services.can_reply(review, request.user):
            raise CodedAPIException("Seul le vendeur concerné peut répondre à cet avis.", 'not_seller', 403)
        body = ReviewReplySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            review = services.reply_to_review(review, request.user, body.validated_data['reply_content'])
        except services.ReviewError as exc:
            raise _api_error(exc)
        return Response(self.get_serializer(review).data)
