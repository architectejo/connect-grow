from django.db import models
from django.db.models import OuterRef, Subquery
from rest_framework import permissions, serializers, viewsets

from apps.common.contexts import CONTEXT_ORGANIZATION
from apps.common.pagination import OptionalPagination
from apps.common.throttles import ActionScopedThrottleMixin
from apps.common.utils import parse_uuid
from apps.identity.services import ActingContextMixin

from . import services
from .models import Conversation, Message
from .serializers import ConversationSerializer, MessageSerializer


class ConversationViewSet(ActingContextMixin, viewsets.ReadOnlyModelViewSet):
    """Boîte de messages (ADR 0006, 9.8).

    Liste : sans en-tête `X-Context` (ou en contexte personnel ou prestataire), les conversations où le compte est
    participant ; avec `X-Context: ORGANIZATION:<id>`, celles dont le contexte vendeur est cette organisation (capacité
    `message.reply`, sinon 403 `DENY_PERMISSION`). Détail : accès PAR OBJET (participant, ou membre habilité de
    l'organisation de la conversation), l'en-tête est ignoré. Jamais celles des autres."""

    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OptionalPagination

    def _scope(self):
        user = self.request.user
        if self.action != 'list':
            return Conversation.objects.filter(services.accessible_conversations_filter(user))
        if self.request.META.get('HTTP_X_CONTEXT') is None:  # contexte personnel : comportement historique
            return Conversation.objects.filter(services.personal_conversations_filter(user))
        ctx = self.acting_context
        self.authorize_capability(services.REPLY_CAPABILITY)
        if ctx.type == CONTEXT_ORGANIZATION:
            return Conversation.objects.filter(seller_context_type=CONTEXT_ORGANIZATION, seller_context_id=ctx.id)
        return Conversation.objects.filter(services.personal_conversations_filter(user))

    def get_queryset(self):
        last = Message.objects.filter(conversation=OuterRef('pk')).order_by('-created_at')
        return (
            self._scope()
            .prefetch_related('participants')
            .annotate(
                last_message_content=Subquery(last.values('content')[:1]),
                last_message_at=Subquery(last.values('created_at')[:1], output_field=models.DateTimeField()),
                last_message_is_read=Subquery(last.values('is_read')[:1]),
                last_message_sender_id=Subquery(last.values('sender_id')[:1], output_field=models.UUIDField()),
                last_message_sender_context_id=Subquery(
                    last.values('sender_context_id')[:1], output_field=models.UUIDField(),
                ),
            )
            .order_by('-updated_at')
        )


class MessageViewSet(ActingContextMixin, ActionScopedThrottleMixin, viewsets.ModelViewSet):
    """Messages des conversations accessibles à l'utilisateur ; envoi réservé aux participants et aux membres habilités
    de l'organisation de la conversation (accès par objet, l'en-tête `X-Context` est ignoré ; ADR 0006, 6.4).
    Un message n'est ni modifiable ni supprimable (traçabilité pour la modération)."""

    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OptionalPagination
    http_method_names = ['get', 'post', 'head', 'options']
    throttle_scopes = {'create': 'message'}

    def get_queryset(self):
        queryset = Message.objects.filter(
            services.accessible_conversations_filter(self.request.user, 'conversation__'),
        ).select_related('sender')
        conversation_id = self.request.query_params.get('conversation')
        if conversation_id:
            conversation_uuid = parse_uuid(conversation_id)
            queryset = queryset.filter(conversation_id=conversation_uuid) if conversation_uuid else queryset.none()
        return queryset.order_by('created_at')

    def perform_create(self, serializer):
        try:
            message = services.send_message(
                conversation=serializer.validated_data['conversation'],
                sender=self.request.user,
                content=serializer.validated_data['content'],
            )
        except services.ConversationAccessDenied:  # accès retiré entre la validation et l'écriture
            raise serializers.ValidationError({'conversation': ["Conversation introuvable."]})
        serializer.instance = message
