from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Conversation(BaseModel):
    """Fil de discussion entre utilisateurs, éventuellement rattaché à une offre.

    `offer_id` désigne l'offre par UUID (pas de clé étrangère entre domaines, CDC §5.4) :
    si l'offre est purgée, la conversation survit. Les participants sont des utilisateurs
    (relation autorisée). `updated_at` (BaseModel) sert de tri : dernière activité."""

    offer_id = models.UUIDField(null=True, blank=True, db_index=True)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='conversations')

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation {self.pk}"


class Message(BaseModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['conversation', 'created_at'], name='msg_conv_created')]

    def __str__(self):
        return f"Message de {self.sender_id} à {self.created_at}"
