from rest_framework import serializers

from apps.common.serializers import PreloadingListSerializer
from apps.identity import services as identity_services

from .models import Notification


class NotificationListSerializer(PreloadingListSerializer):
    pass


class NotificationSerializer(serializers.ModelSerializer):
    """Seul `is_read` est modifiable : une notification est produite par le système.

    `context` (ADR 0006, 9.8) : `null` = notification personnelle ; sinon `{type, id, name}` du contexte vendeur
    concerné (`name` : nom actuel du prestataire ou de l'organisation, `null` si le contexte n'existe plus)."""

    context = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ['id', 'user', 'notification_type', 'title', 'content', 'link', 'is_read', 'created_at', 'context']
        read_only_fields = ['user', 'notification_type', 'title', 'content', 'link', 'created_at']
        list_serializer_class = NotificationListSerializer

    NAMES_KEY = 'notifications_context_names'

    @classmethod
    def preload(cls, items, context):
        """Noms des contextes de la page, en au plus deux requêtes pour toute la liste."""
        cache = context.setdefault(cls.NAMES_KEY, {})
        wanted = {(i.context_type, i.context_id) for i in items if i.context_type and i.context_id} - cache.keys()
        if wanted:
            found = identity_services.get_context_names(wanted)
            for key in wanted:
                cache[key] = found.get(key)

    def get_context(self, obj):
        if not obj.context_type or not obj.context_id:
            return None
        key = (obj.context_type, obj.context_id)
        if key not in self.context.get(self.NAMES_KEY, {}):
            self.preload([obj], self.context)
        return {'type': obj.context_type, 'id': str(obj.context_id), 'name': self.context[self.NAMES_KEY].get(key)}
