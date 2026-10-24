import uuid

from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from apps.common.contexts import CONTEXT_ORGANIZATION
from apps.common.serializers import PreloadingListSerializer
from apps.identity import services as identity_services
from apps.marketplace import services as marketplace_services

from . import services
from .models import Conversation, Message

MESSAGE_MAX_LENGTH = 2000
CONVERSATION_NOT_FOUND = "Conversation introuvable."
DELETED_SENDER_NAME = "Utilisateur supprimé"

_DATETIME_FIELD = serializers.DateTimeField()


def _api_datetime(value):
    """Date au format du reste de l'API (ISO 8601, fuseau local avec décalage, jamais `Z`)."""
    return _DATETIME_FIELD.to_representation(value) if value is not None else None


def _api_uuid(value):
    """UUID canonique (avec tirets), y compris quand la base renvoie sa forme hexadécimale."""
    return str(uuid.UUID(str(value))) if value is not None else None


class ConversationField(serializers.PrimaryKeyRelatedField):
    """Identifiant de conversation : un UUID mal formé donne la même réponse qu'une conversation inconnue."""

    def to_internal_value(self, data):
        try:
            return super().to_internal_value(data)
        except DjangoValidationError:
            self.fail('does_not_exist', pk_value=data)


class MessageListSerializer(PreloadingListSerializer):
    pass


class MessageSerializer(serializers.ModelSerializer):
    """Message d'une conversation. Un message écrit « en tant que » l'organisation (`sender_context`) expose le nom
    de l'organisation et son identifiant à la place de ceux du membre : jamais le nom, l'identifiant de compte,
    le numéro ni l'e-mail du membre qui a écrit (ADR 0006, 9.8 ; règle 10)."""

    # Message d'erreur identique pour une conversation inexistante, mal formée ou interdite : aucun oracle d'existence.
    conversation = ConversationField(
        queryset=Conversation.objects.all(),
        error_messages={
            'does_not_exist': CONVERSATION_NOT_FOUND, 'incorrect_type': CONVERSATION_NOT_FOUND,
            'required': "Ce champ est obligatoire.", 'null': "Ce champ est obligatoire.",
        },
    )
    sender = serializers.SerializerMethodField()
    sender_name = serializers.SerializerMethodField()
    sender_context = serializers.SerializerMethodField()
    is_me = serializers.SerializerMethodField()
    content = serializers.CharField(max_length=MESSAGE_MAX_LENGTH)

    NAMES_KEY = 'messaging_context_names'
    REPLY_ORGS_KEY = 'messaging_reply_organizations'

    class Meta:
        model = Message
        fields = [
            'id', 'conversation', 'sender', 'sender_name', 'sender_context', 'content', 'is_read', 'created_at', 'is_me',
        ]
        read_only_fields = ['is_read']
        list_serializer_class = MessageListSerializer

    @classmethod
    def preload(cls, messages, context):
        """Noms des organisations expéditrices (une requête) et organisations où le lecteur répond (pour `is_me`)."""
        names = context.setdefault(cls.NAMES_KEY, {})
        wanted = {
            (m.sender_context_type, m.sender_context_id) for m in messages if m.sender_context_type
        } - names.keys()
        if wanted:
            names.update(services.get_context_names(wanted))
            for key in wanted:
                names.setdefault(key, None)
        if cls.REPLY_ORGS_KEY not in context:
            request = context.get('request')
            user = getattr(request, 'user', None)
            context[cls.REPLY_ORGS_KEY] = (
                identity_services.get_accessible_organization_ids(user.pk, services.REPLY_CAPABILITY)
                if user is not None and user.is_authenticated and any(m.sender_context_type for m in messages)
                else set()
            )

    def _ready(self, obj):
        key = (obj.sender_context_type, obj.sender_context_id)
        if self.NAMES_KEY not in self.context or key not in self.context[self.NAMES_KEY]:
            self.preload([obj], self.context)

    def validate_conversation(self, conversation):
        # Seul un participant, ou un membre habilité de l'organisation de la conversation, écrit dedans.
        request = self.context['request']
        if not services.can_write(conversation, request.user):
            raise serializers.ValidationError(CONVERSATION_NOT_FOUND)
        return conversation

    def get_sender(self, obj):
        # Côté organisation : l'identifiant de l'organisation, jamais celui du compte du membre.
        return obj.sender_context_id if obj.sender_context_type else obj.sender_id

    def get_sender_name(self, obj):
        if obj.sender_context_type:
            self._ready(obj)
            return self.context[self.NAMES_KEY].get((obj.sender_context_type, obj.sender_context_id)) or "Organisation"
        if obj.sender is None:
            return DELETED_SENDER_NAME
        request = self.context.get('request')
        viewer = getattr(request, 'user', None)
        if obj.conversation.seller_context_type == CONTEXT_ORGANIZATION and viewer is not None and obj.sender_id != viewer.pk:
            # L'équipe d'une organisation voit l'acheteur sous une forme abrégée (« Marie K. », règle 10).
            return identity_services.requester_display_name(obj.sender.full_name)
        return obj.sender.full_name

    def get_sender_context(self, obj):
        if not obj.sender_context_type:
            return None
        return {'type': obj.sender_context_type, 'id': obj.sender_context_id}

    def get_is_me(self, obj):
        request = self.context.get('request')
        if not (request and request.user and request.user.is_authenticated):
            return False
        if obj.sender_context_type == CONTEXT_ORGANIZATION:
            # « de mon côté » : tout membre habilité de l'organisation expéditrice, pas seulement l'auteur.
            self._ready(obj)
            return obj.sender_context_id in self.context[self.REPLY_ORGS_KEY]
        return obj.sender_id == request.user.id


class ConversationListSerializer(PreloadingListSerializer):
    pass


class ConversationSerializer(serializers.ModelSerializer):
    # Clé JSON `post` conservée jusqu'à L0-11 : UUID de l'offre, ou null si elle a été purgée.
    post = serializers.SerializerMethodField()
    post_title = serializers.SerializerMethodField()
    post_image = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    seller_context = serializers.SerializerMethodField()

    OFFERS_KEY = 'messaging_offers'
    SELLERS_KEY = 'messaging_sellers'

    class Meta:
        model = Conversation
        fields = [
            'id', 'post', 'post_title', 'post_image', 'other_participant', 'last_message', 'seller_context',
            'updated_at',
        ]
        list_serializer_class = ConversationListSerializer

    @classmethod
    def preload(cls, conversations, context):
        """Charge en une requête les offres citées par les conversations de la liste."""
        cache = context.setdefault(cls.OFFERS_KEY, {})
        missing = {c.offer_id for c in conversations if c.offer_id} - cache.keys()
        cache.update(marketplace_services.get_offers_by_ids(missing))
        for offer_id in missing:
            cache.setdefault(offer_id, None)
        # Organisations vendeuses (une requête) : l'acheteur voit l'organisation en face de lui, pas un membre.
        sellers = context.setdefault(cls.SELLERS_KEY, {})
        wanted = {
            (c.seller_context_type, c.seller_context_id) for c in conversations
            if c.seller_context_type == CONTEXT_ORGANIZATION
        } - sellers.keys()
        if wanted:
            sellers.update(identity_services.get_seller_summaries(wanted))
            for key in wanted:
                sellers.setdefault(key, None)

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
            # Message écrit côté organisation : l'identifiant de l'organisation, jamais celui du membre.
            sender = getattr(obj, 'last_message_sender_context_id', None) or obj.last_message_sender_id
            return {
                'content': obj.last_message_content,
                'created_at': _api_datetime(obj.last_message_at),
                'is_read': obj.last_message_is_read,
                'sender_id': _api_uuid(sender),
            }
        last_msg = obj.messages.order_by('-created_at').first()
        if last_msg:
            return {
                'content': last_msg.content,
                'created_at': _api_datetime(last_msg.created_at),
                'is_read': last_msg.is_read,
                'sender_id': _api_uuid(last_msg.sender_context_id or last_msg.sender_id),
            }
        return None

    def get_seller_context(self, obj):
        if not obj.seller_context_type:
            return None
        return {'type': obj.seller_context_type, 'id': obj.seller_context_id}

    def get_other_participant(self, obj):
        request = self.context.get('request')
        if request and request.user:
            # `participants` est préchargé par la vue : pas de requête par conversation.
            other = next((p for p in obj.participants.all() if p.pk != request.user.pk), None)
            if other:
                if obj.seller_context_type == CONTEXT_ORGANIZATION:
                    # L'équipe d'une organisation voit l'acheteur sous une forme abrégée, sans photo (règle 10).
                    return {
                        'id': other.id, 'full_name': identity_services.requester_display_name(other.full_name),
                        'photo': None,
                    }
                return {
                    'id': other.id,
                    'full_name': other.full_name,
                    'photo': other.photo.url if other.photo else None,
                }
            if obj.seller_context_type == CONTEXT_ORGANIZATION:
                # L'acheteur d'une conversation d'organisation : l'interlocuteur est l'organisation.
                key = (obj.seller_context_type, obj.seller_context_id)
                if key not in self.context.get(self.SELLERS_KEY, {}):
                    self.preload([obj], self.context)
                summary = self.context[self.SELLERS_KEY].get(key)
                if summary is not None:
                    return {'id': summary.context_id, 'full_name': summary.display_name, 'photo': summary.photo}
        return None
