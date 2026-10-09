from django.db.models import OuterRef, Subquery
from rest_framework import permissions, viewsets

from apps.common.pagination import OptionalPagination

from . import services
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer


class ConversationViewSet(viewsets.ReadOnlyModelViewSet):
    """Conversations de l'utilisateur connecté (jamais celles des autres)."""

    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OptionalPagination

    def get_queryset(self):
        last = Message.objects.filter(conversation=OuterRef('pk')).order_by('-created_at')
        return (
            Conversation.objects.filter(participants=self.request.user)
            .prefetch_related('participants')
            .annotate(
                last_message_content=Subquery(last.values('content')[:1]),
                last_message_at=Subquery(last.values('created_at')[:1]),
                last_message_is_read=Subquery(last.values('is_read')[:1]),
                last_message_sender_id=Subquery(last.values('sender_id')[:1]),
            )
            .order_by('-updated_at')
        )


class MessageViewSet(viewsets.ModelViewSet):
    """Messages des conversations de l'utilisateur ; envoi réservé aux participants.
    Un message n'est ni modifiable ni supprimable (traçabilité pour la modération)."""

    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OptionalPagination
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        queryset = Message.objects.filter(conversation__participants=self.request.user).select_related('sender')
        conversation_id = self.request.query_params.get('conversation')
        if conversation_id:
            from apps.common.utils import parse_uuid

            conversation_uuid = parse_uuid(conversation_id)
            queryset = queryset.filter(conversation_id=conversation_uuid) if conversation_uuid else queryset.none()
        return queryset.order_by('created_at')

    def perform_create(self, serializer):
        message = services.send_message(
            conversation=serializer.validated_data['conversation'],
            sender=self.request.user,
            content=serializer.validated_data['content'],
        )
        serializer.instance = message
