from django.conf import settings
from django.db import models

from apps.common.contexts import ALL_CONTEXT_CHOICES
from apps.common.models import BaseModel


class Conversation(BaseModel):
    """Fil de discussion entre utilisateurs, éventuellement rattaché à une offre.

    `offer_id` désigne l'offre par UUID (pas de clé étrangère entre domaines, CDC §5.4) :
    si l'offre est purgée, la conversation survit. Les participants sont des utilisateurs
    (relation autorisée). `updated_at` (BaseModel) sert de tri : dernière activité."""

    offer_id = models.UUIDField(null=True, blank=True, db_index=True)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='conversations')
    # Contexte vendeur de la conversation (ADR 0006, A8 et 4.5). SCHÉMA SEULEMENT en T5b : aucun code ne les lit
    # ni ne les écrit avant T7. Nul = ancienne conversation, accès par `participants` (norme unique : aucun remplissage).
    seller_context_type = models.CharField(max_length=20, choices=ALL_CONTEXT_CHOICES, null=True, blank=True)
    seller_context_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['seller_context_type', 'seller_context_id'], name='conv_seller_ctx'),
        ]

    def __str__(self):
        return f"Conversation {self.pk}"


class Message(BaseModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    # SET_NULL : la suppression d'un compte ne supprime pas ses messages (la conversation de l'organisation et de
    # l'acheteur reste lisible) ; un message sans expéditeur s'affiche « Utilisateur supprimé » (ADR 0006, 19.6).
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_messages',
    )
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    # Identité affichée de l'expéditeur (personne ou organisation), ADR 0006, 4.5. Schéma seulement (T7 les
    # utilisera) ; nul = l'expéditeur lui-même, à titre personnel (norme unique : aucun remplissage).
    sender_context_type = models.CharField(max_length=20, choices=ALL_CONTEXT_CHOICES, null=True, blank=True)
    sender_context_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['conversation', 'created_at'], name='msg_conv_created')]

    def __str__(self):
        return f"Message de {self.sender_id} à {self.created_at}"
