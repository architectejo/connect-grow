"""Interface publique du domaine `messaging` pour les autres domaines."""
from apps.notifications import services as notification_services

from .models import Conversation, Message

NOTIFICATION_PREVIEW_LENGTH = 50


def get_or_create_offer_conversation(*, offer_id, user_ids) -> Conversation:
    """Conversation à propos d'une offre entre exactement ces utilisateurs : une conversation
    par acheteur, jamais partagée avec un autre (aucun tiers ne lit les échanges d'autrui)."""
    user_ids = list(dict.fromkeys(user_ids))
    queryset = Conversation.objects.filter(offer_id=offer_id)
    for user_id in user_ids:
        queryset = queryset.filter(participants=user_id)
    for conversation in queryset.prefetch_related('participants'):
        if {p.pk for p in conversation.participants.all()} == set(user_ids):
            return conversation
    conversation = Conversation.objects.create(offer_id=offer_id)
    conversation.participants.add(*user_ids)
    return conversation


def send_message(*, conversation: Conversation, sender, content: str, notify: bool = True) -> Message:
    """Ajoute un message, fait remonter la conversation (dernière activité) et, si demandé,
    prévient l'autre participant."""
    message = Message.objects.create(conversation=conversation, sender=sender, content=content)
    conversation.save(update_fields=['updated_at'])
    if notify:
        others = conversation.participants.exclude(pk=sender.pk)
        for other in others[:1]:
            notification_services.notify(
                user_id=other.pk,
                notification_type=notification_services.MESSAGE,
                title=f"Nouveau message de {sender.full_name}",
                content=content[:NOTIFICATION_PREVIEW_LENGTH],
                link='/messages',
            )
    return message


def is_participant(conversation_id, user_id) -> bool:
    return Conversation.objects.filter(pk=conversation_id, participants=user_id).exists()
