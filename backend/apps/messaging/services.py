"""Interface publique du domaine `messaging` pour les autres domaines.

Messagerie par contexte (ADR 0006, A8, 9.8 et 11.3) :
- `Conversation.seller_context_*` nul = ancienne conversation, accès par `participants` (inchangé) ;
- contexte `USER`/`PROVIDER` : le titulaire du compte est participant (accès par participants) ;
- contexte `ORGANIZATION` : seul l'acheteur est participant ; le côté organisation n'est PAS dans `participants` :
  l'accès se calcule en direct par la capacité `message.reply` (propriétaire, administrateur), donc une révocation
  coupe l'accès à la requête suivante. Lire et répondre exigent la même capacité : il n'existe pas de capacité
  de lecture seule (une boîte d'équipe plus fine arrive avec L2-09), et l'analyste ou l'éditeur ne lisent donc pas
  les messages d'un acheteur ;
- `Message.sender_context_*` : identité affichée de l'expéditeur ; nul = la personne elle-même (acheteur, ou
  titulaire à titre personnel). Un message du côté organisation porte l'organisation, jamais le nom, le numéro
  ni l'e-mail du membre qui l'a écrit.
"""
from django.db import transaction
from django.db.models import Q

from apps.common.contexts import CONTEXT_ORGANIZATION
from apps.identity import services as identity_services
from apps.notifications import services as notification_services
from apps.platform_core.services import publish_event

from .models import Conversation, Message

NOTIFICATION_PREVIEW_LENGTH = 50
REPLY_CAPABILITY = 'message.reply'


class ConversationAccessDenied(Exception):
    """L'utilisateur n'a pas accès à cette conversation (ni participant, ni membre habilité de l'organisation)."""


def get_or_create_offer_conversation(*, offer_id, user_ids, seller_context=None) -> Conversation:
    """Conversation à propos d'une offre entre exactement ces utilisateurs : une conversation
    par acheteur, jamais partagée avec un autre (aucun tiers ne lit les échanges d'autrui).

    `seller_context` : couple `(type, id)` du contexte vendeur de l'offre (ADR 0006, A8). Organisation : `user_ids`
    ne contient que l'acheteur, et la conversation est unique par (offre, organisation, acheteur)."""
    user_ids = list(dict.fromkeys(user_ids))
    queryset = Conversation.objects.filter(offer_id=offer_id)
    if seller_context is not None and seller_context[0] == CONTEXT_ORGANIZATION:
        queryset = queryset.filter(seller_context_type=seller_context[0], seller_context_id=seller_context[1])
    for user_id in user_ids:
        queryset = queryset.filter(participants=user_id)
    for conversation in queryset.prefetch_related('participants'):
        if {p.pk for p in conversation.participants.all()} == set(user_ids):
            return conversation
    context_type, context_id = seller_context if seller_context is not None else (None, None)
    conversation = Conversation.objects.create(
        offer_id=offer_id, seller_context_type=context_type, seller_context_id=context_id,
    )
    conversation.participants.add(*user_ids)
    return conversation


# --- Accès par conversation ---------------------------------------------------------------------------

def _participant_ids(user_id):
    return Conversation.participants.through.objects.filter(user_id=user_id).values('conversation_id')


def personal_conversations_filter(user, prefix='') -> Q:
    """Conversations où le compte est participant (boîte personnelle, ancien comportement)."""
    return Q(**{f'{prefix}pk__in': _participant_ids(user.pk)})


def accessible_conversations_filter(user, prefix='') -> Q:
    """Conversations auxquelles `user` accède PAR OBJET : celles où il est participant, plus celles dont le contexte
    vendeur est une organisation où il est membre actif avec `message.reply` (calculé en base à chaque appel,
    compte actif et sans sanction bloquante exigés). `prefix` : chemin vers la conversation (`conversation__`)."""
    condition = personal_conversations_filter(user, prefix)
    org_ids = identity_services.get_accessible_organization_ids(user.pk, REPLY_CAPABILITY)
    if org_ids:
        condition |= Q(**{
            f'{prefix}seller_context_type': CONTEXT_ORGANIZATION, f'{prefix}seller_context_id__in': org_ids,
        })
    return condition


def get_reply_context(conversation: Conversation, user):
    """`None` si `user` écrit à titre personnel (il est participant), `(ORGANIZATION, id)` s'il répond au nom de
    l'organisation du contexte vendeur. Lève `ConversationAccessDenied` sans accès. Relu en base."""
    if Conversation.participants.through.objects.filter(conversation_id=conversation.pk, user_id=user.pk).exists():
        return None
    if conversation.seller_context_type == CONTEXT_ORGANIZATION and identity_services.can(
        user.pk, CONTEXT_ORGANIZATION, conversation.seller_context_id, REPLY_CAPABILITY,
    ):
        return CONTEXT_ORGANIZATION, conversation.seller_context_id
    raise ConversationAccessDenied()


def can_write(conversation: Conversation, user) -> bool:
    try:
        get_reply_context(conversation, user)
    except ConversationAccessDenied:
        return False
    return True


def get_context_names(contexts) -> dict:
    """Noms publics `{(type, id): nom}` des contextes vendeur cités (une requête par type)."""
    summaries = identity_services.get_seller_summaries(contexts)
    return {key: summary.display_name for key, summary in summaries.items()}


def send_message(*, conversation: Conversation, sender, content: str, notify: bool = True) -> Message:
    """Ajoute un message, fait remonter la conversation (dernière activité) et, si demandé, prévient l'autre côté.

    Un participant écrit à titre personnel ; un membre habilité d'une organisation répond « en tant que » l'organisation
    (`sender_context_*`). L'accès est revérifié en base DANS la transaction, juste avant l'écriture (révocation
    survenue entre la validation et l'écriture). Lève `ConversationAccessDenied`."""
    with transaction.atomic():
        reply_context = get_reply_context(conversation, sender)
        if reply_context is None:
            # Un acheteur n'écrit pas à une organisation suspendue ou archivée (DENY_SECURITY / DENY_OBJECT_STATE).
            identity_services.ensure_seller_context_accepts_contact(
                conversation.seller_context_type, conversation.seller_context_id,
            )
        context_type, context_id = reply_context if reply_context is not None else (None, None)
        message = Message.objects.create(
            conversation=conversation, sender=sender, content=content,
            sender_context_type=context_type, sender_context_id=context_id,
        )
        conversation.save(update_fields=['updated_at'])
        if notify:
            _notify_other_side(conversation, sender, content, reply_context)
    return message


def _notify_other_side(conversation, sender, content, reply_context) -> None:
    preview = content[:NOTIFICATION_PREVIEW_LENGTH]
    if reply_context is not None:
        # L'organisation répond : l'acheteur lit le nom de l'organisation, jamais celui du membre.
        name = get_context_names([reply_context]).get(reply_context) or "l'organisation"
        for other in conversation.participants.exclude(pk=sender.pk)[:1]:
            notification_services.notify(
                user_id=other.pk, notification_type=notification_services.MESSAGE,
                title=f"Nouveau message de {name}", content=preview, link='/messages',
            )
        return
    if conversation.seller_context_type == CONTEXT_ORGANIZATION:
        # L'acheteur écrit à l'organisation : toute l'équipe habilitée est prévenue (résolue maintenant).
        for recipient_id in identity_services.get_context_recipients(
            CONTEXT_ORGANIZATION, conversation.seller_context_id, REPLY_CAPABILITY,
        ):
            notification_services.notify(
                user_id=recipient_id, notification_type=notification_services.MESSAGE,
                title=f"Nouveau message de {identity_services.requester_display_name(sender.full_name)}",
                content=preview, link='/messages', context=(CONTEXT_ORGANIZATION, conversation.seller_context_id),
            )
        return
    for other in conversation.participants.exclude(pk=sender.pk)[:1]:
        notification_services.notify(
            user_id=other.pk, notification_type=notification_services.MESSAGE,
            title=f"Nouveau message de {sender.full_name}", content=preview, link='/messages',
        )


def open_conversation_with_message(
    *, offer_id, sender_id, recipient_id=None, content: str, contact_event_id=None, seller_context=None,
) -> Message:
    """Ouvre (ou retrouve) la conversation d'une offre entre l'expéditeur et le vendeur, puis y dépose le message,
    sans notification (la demande de contact notifie déjà le vendeur).

    `seller_context` : contexte vendeur de l'offre. Organisation : l'acheteur est le seul participant (`recipient_id`
    est ignoré) et l'équipe accède par capacité. Compte ou prestataire : `recipient_id` (le titulaire) est participant.

    Si le message vient d'un contact (`contact_event_id`), publie `messaging.contact_message_delivered`
    dans la même transaction : le message est alors réellement remis au vendeur (ADR 0005, C10).
    La charge utile ne contient que des identifiants, ni le texte ni aucun numéro."""
    is_organization = seller_context is not None and seller_context[0] == CONTEXT_ORGANIZATION
    user_ids = [sender_id] if is_organization else [sender_id, recipient_id]
    with transaction.atomic():
        conversation = get_or_create_offer_conversation(
            offer_id=offer_id, user_ids=user_ids, seller_context=seller_context,
        )
        message = Message.objects.create(conversation=conversation, sender_id=sender_id, content=content)
        conversation.save(update_fields=['updated_at'])
        if contact_event_id is not None:
            publish_event(
                'messaging.contact_message_delivered', aggregate_type='conversation', aggregate_id=conversation.pk,
                payload={
                    'contact_event_id': str(contact_event_id), 'offer_id': str(offer_id),
                    'conversation_id': str(conversation.pk), 'message_id': str(message.pk),
                },
            )
    return message


def get_report_labels(ids) -> dict:
    """Libellés de messages signalables, indexés par UUID (une requête) : sert à la modération.
    Un message absent n'apparaît pas dans le résultat."""
    from apps.common.utils import parse_uuid

    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return {message.id: str(message) for message in Message.objects.filter(id__in=wanted)}


def has_open_grave_report_on_sender(user_id) -> bool:
    """Vrai si un message ENVOYÉ par ce compte fait l'objet d'un signalement ouvert pour motif grave (preuve à ne pas
    effacer : suppression de compte refusée par `identity`)."""
    from apps.moderation import services as moderation_services

    return moderation_services.has_open_grave_report('message', Message.objects.filter(sender_id=user_id).values('id'))


def get_report_authors(ids) -> dict:
    """Expéditeur de chaque message, `{message: expéditeur}` (une requête)."""
    from apps.common.utils import parse_uuid

    wanted = {parsed for parsed in (parse_uuid(i) for i in ids) if parsed is not None}
    return {
        message_id: sender_id for message_id, sender_id in Message.objects.filter(id__in=wanted).values_list('id', 'sender_id')
        if sender_id is not None  # auteur supprimé : plus d'auteur à contrôler
    }
