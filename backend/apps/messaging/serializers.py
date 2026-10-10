import uuid

from rest_framework import serializers

from apps.common.serializers import PreloadingListSerializer
from apps.marketplace import services as marketplace_services

from .models import Conversation, Message

MESSAGE_MAX_LENGTH = 2000

_DATETIME_FIELD = serializers.DateTimeField()


def _api_datetime(value):
    """Date au format du reste de l'API (ISO 8601, fuseau local avec décalage, jamais `Z`)."""
    return _DATETIME_FIELD.to_representation(value) if value is not None else None


def _api_uuid(value):
    """UUID canonique (avec tirets), y compris quand la base renvoie sa forme hexadécimale."""
    return str(uuid.UUID(str(value))) if value is not None else None


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.ReadOnlyField(source='sender.full_name')
    is_me = serializers.SerializerMethodField()
    content = serializers.CharField(max_length=MESSAGE_MAX_LENGTH)

    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'sender_name', 'content', 'is_read', 'created_at', 'is_me']
        read_only_fields = ['sender', 'is_read']

    def validate_conversation(self, conversation):
        # Seul un participant écrit dans une conversation.
        request = self.context['request']
        if not conversation.participants.filter(pk=request.user.pk).exists():
            raise serializers.ValidationError("Conversation introuvable.")
        return conversation

    def get_is_me(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.sender_id == request.user.id
        return False


class ConversationListSerializer(PreloadingListSerializer):
    pass


class ConversationSerializer(serializers.ModelSerializer):
    # Clé JSON `post` conservée jusqu'à L0-11 : UUID de l'offre, ou null si elle a été purgée.
    post = serializers.SerializerMethodField()
    post_title = serializers.SerializerMethodField()
    post_image = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    OFFERS_KEY = 'messaging_offers'

    class Meta:
        model = Conversation
        fields = ['id', 'post', 'post_title', 'post_image', 'other_participant', 'last_message', 'updated_at']
        list_serializer_class = ConversationListSerializer

    @classmethod
    def preload(cls, conversations, context):
        """Charge en une requête les offres citées par les conversations de la liste."""
        cache = context.setdefault(cls.OFFERS_KEY, {})
        missing = {c.offer_id for c in conversations if c.offer_id} - cache.keys()
        cache.update(marketplace_services.get_offers_by_ids(missing))
        for offer_id in missing:
            cache.setdefault(offer_id, None)

    def _offer(self, obj):
        if not obj.offer_id:
            return None
        cache = self.context.get(self.OFFERS_KEY)
        if cache is None or obj.offer_id not in cache:
            self.preload([obj], self.context)
            cache = self.context[self.OFFERS_KEY]
        return cache[obj.offer_id]

    def get_post(self, obj):
        return str(obj.offer_id) if self._offer(obj) else None

    def get_post_title(self, obj):
        offer = self._offer(obj)
        return offer.title if offer else None

    def get_post_image(self, obj):
        offer = self._offer(obj)
        return offer.main_image_url if offer else None

    def get_last_message(self, obj):
        # Annotations posées par la vue (une requête pour toute la liste) ; repli ciblé sinon.
        if hasattr(obj, 'last_message_at'):
            if obj.last_message_at is None:
                return None
            return {
                'content': obj.last_message_content,
                'created_at': _api_datetime(obj.last_message_at),
                'is_read': obj.last_message_is_read,
                'sender_id': _api_uuid(obj.last_message_sender_id),
            }
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'content': last_msg.content,
                'created_at': _api_datetime(last_msg.created_at),
                'is_read': last_msg.is_read,
                'sender_id': _api_uuid(last_msg.sender_id),
            }
        return None

    def get_other_participant(self, obj):
        request = self.context.get('request')
        if request and request.user:
            # `participants` est préchargé par la vue : pas de requête par conversation.
            other = next((p for p in obj.participants.all() if p.pk != request.user.pk), None)
            if other:
                return {
                    'id': other.id,
                    'full_name': other.full_name,
                    'photo': other.photo.url if other.photo else None,
                }
        return None
