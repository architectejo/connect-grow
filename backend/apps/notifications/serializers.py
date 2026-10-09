from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Seul `is_read` est modifiable : une notification est produite par le système."""

    class Meta:
        model = Notification
        fields = ['id', 'user', 'notification_type', 'title', 'content', 'link', 'is_read', 'created_at']
        read_only_fields = ['user', 'notification_type', 'title', 'content', 'link', 'created_at']
