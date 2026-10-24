"""Abonnés de `notifications` aux événements de domaine (ADR 0003). N'appellent que des `services.py`."""
from datetime import datetime

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER
from apps.common.utils import parse_uuid
from apps.identity import services as identity_services
from apps.platform_core.registry import PermanentEventError, subscribe
from apps.reviews import services as reviews_services

from . import services

UNKNOWN_USER = "Un utilisateur"


def _require(payload, *keys):
    """Valeurs obligatoires de la charge utile ; une clé absente ou un UUID mal formé est une
    erreur définitive (rejouer ne changera rien)."""
    try:
        return [payload[key] for key in keys]
    except (KeyError, TypeError) as exc:
        raise PermanentEventError("charge utile invalide") from exc


def _user_id(value):
    parsed = parse_uuid(value)
    if parsed is None:
        raise PermanentEventError("charge utile invalide")
    return parsed


def _name(user_id_value):
    user_id = _user_id(user_id_value)
    return identity_services.get_full_names([user_id]).get(user_id) or UNKNOWN_USER


REPLY_CAPABILITY = 'message.reply'  # équipe qui reçoit les messages d'une organisation (ADR 0006, D6)
REQUESTERS_CAPABILITY = 'contact.view_requesters'  # équipe qui voit « qui a demandé » (l'analyste n'y a pas droit)


def _seller_context(event):
    """(type, id) du contexte vendeur d'une charge utile de contact ou d'échange. Version 1 encore en file : le
    vendeur était un compte (`seller_id`), lu comme son contexte `USER`. Type inconnu : erreur définitive."""
    payload = event.payload
    if event.version == 1:
        return CONTEXT_USER, _user_id(_require(payload, 'seller_id')[0])
    context_type, context_id = _require(payload, 'seller_context_type', 'seller_context_id')
    if context_type not in (CONTEXT_USER, CONTEXT_PROVIDER, CONTEXT_ORGANIZATION):
        raise PermanentEventError("charge utile invalide")
    return context_type, _user_id(context_id)


def _buyer_name(user_id_value):
    """Nom de l'acheteur vu par l'équipe du vendeur : forme abrégée (« Marie K. »), jamais le nom complet."""
    user_id = _user_id(user_id_value)
    return identity_services.requester_display_name(identity_services.get_full_names([user_id]).get(user_id))


def _notify_context(event, capability, **notification):
    """Une notification par destinataire du contexte vendeur, résolu À LA LIVRAISON (équipe du moment : un membre
    révoqué entre-temps n'est pas notifié). Une organisation : la notification est rattachée à l'organisation.
    Aucune donnée de membre dans la charge utile ni dans les journaux."""
    context_type, context_id = _seller_context(event)
    for recipient_id in identity_services.get_context_recipients(context_type, context_id, capability):
        services.notify(
            user_id=recipient_id,
            context=(context_type, context_id) if context_type == CONTEXT_ORGANIZATION else None,
            **notification,
        )


@subscribe('marketplace.contact_recorded', name='notifications.notify_contact', versions=(1, 2))
def notify_contact(event):
    sender_id, title = _require(event.payload, 'sender_id', 'offer_title')
    _notify_context(
        event, REPLY_CAPABILITY, notification_type=services.CONTACT,
        title="Nouvelle demande de contact",
        content=f"{_buyer_name(sender_id)} vous a contacté pour {title}",
        link='/messages',
    )


@subscribe('marketplace.contact_revealed', name='notifications.notify_contact_revealed', versions=(1, 2))
def notify_contact_revealed(event):
    """Le vendeur apprend qu'un utilisateur a obtenu son numéro (ADR 0005, C7) : nom d'affichage
    « Marie K. » (`requester_display_name`, nettoyé comme la liste), jamais de numéro. Organisation : les membres
    qui ont `contact.view_requesters` (comme la liste « qui a demandé »)."""
    sender_id, title = _require(event.payload, 'sender_id', 'offer_title')
    sender = _user_id(sender_id)
    name = identity_services.requester_display_name(identity_services.get_full_names([sender]).get(sender))
    _notify_context(
        event, REQUESTERS_CAPABILITY, notification_type=services.CONTACT,
        title="Votre numéro a été demandé",
        content=f"{name} a demandé votre numéro pour {title}",
        link='/dashboard',
    )


@subscribe('marketplace.exchange_proposed', name='notifications.notify_exchange', versions=(1, 2))
def notify_exchange(event):
    sender_id, title = _require(event.payload, 'sender_id', 'offer_title')
    _notify_context(
        event, REPLY_CAPABILITY, notification_type=services.EXCHANGE,
        title="Nouvelle proposition d'échange",
        content=f"{_buyer_name(sender_id)} propose un échange pour {title}",
        link='/messages',
    )


def _post_link(payload):
    return f"/post/{payload['offer_id']}" if payload.get('offer_id') else ''


@subscribe('reviews.review_posted', name='notifications.notify_review_posted', versions=(2,))
def notify_review_posted(event):
    """Version 2 (ADR 0004) : `recipient_id` est l'utilisateur à notifier ; la version 1
    est refusée par le registre (`PermanentEventError`)."""
    payload = event.payload
    review_id, recipient_id, author_id, title = _require(
        payload, 'review_id', 'recipient_id', 'author_id', 'offer_title',
    )
    excerpt = reviews_services.get_review_excerpt(_user_id(review_id))
    if excerpt is None:  # avis supprimé avant la diffusion : plus rien à annoncer
        return
    services.notify(
        user_id=_user_id(recipient_id), notification_type=services.COMMENT,
        title=f"Nouvel avis sur {title}",
        content=f"{_name(author_id)} a laissé un avis : {excerpt}...",
        link=_post_link(payload),
    )


@subscribe('reviews.review_replied', name='notifications.notify_review_reply')
def notify_review_reply(event):
    payload = event.payload
    author_id, replier_id, title = _require(payload, 'review_author_id', 'replier_id', 'offer_title')
    services.notify(
        user_id=_user_id(author_id), notification_type=services.SYSTEM,
        title="Réponse à votre avis",
        content=f"{_name(replier_id)} a répondu à votre avis sur {title}",
        link=_post_link(payload),
    )


@subscribe('marketplace.offer_expiring_soon', name='notifications.notify_offer_expiration')
def notify_offer_expiration(event):
    payload = event.payload
    seller_id, title, offer_id, raw_date = _require(payload, 'seller_id', 'offer_title', 'offer_id', 'expires_at')
    try:
        expires_at = datetime.fromisoformat(raw_date)
    except (ValueError, TypeError) as exc:
        raise PermanentEventError("charge utile invalide") from exc
    services.notify(
        user_id=_user_id(seller_id), notification_type=services.EXPIRATION,
        title="Votre annonce expire bientôt",
        content=f"« {title} » expire le {expires_at:%d/%m/%Y}. Renouvelez-la pour rester visible.",
        link=f"/post/{offer_id}",
    )
