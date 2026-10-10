from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Notification(BaseModel):
    """Notification interne adressée à un utilisateur (CDC 3.6). Créée par les autres
    domaines via `apps.notifications.services.notify`."""

    class NotificationType(models.TextChoices):
        COMMENT = 'COMMENT', "Nouveau commentaire"
        CONTACT = 'CONTACT', "Demande de contact"
        EXCHANGE = 'EXCHANGE', "Proposition d'échange"
        MESSAGE = 'MESSAGE', "Nouveau message"
        EXPIRATION = 'EXPIRATION', "Annonce bientôt expirée"
        SYSTEM = 'SYSTEM', "Système"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NotificationType.choices)
    title = models.CharField(max_length=255)
    content = models.TextField()
    link = models.CharField(max_length=255, null=True, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'is_read'], name='notif_user_read')]

    def __str__(self):
        return f"Notification pour {self.user_id} : {self.title}"
