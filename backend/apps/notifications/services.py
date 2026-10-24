"""Interface publique du domaine `notifications` pour les autres domaines.

Contexte d'une notification (ADR 0006, 4.5 et 9.8) : `context_type`/`context_id` désignent le contexte vendeur
(prestataire ou organisation) auquel elle se rattache ; NUL = contexte personnel (norme unique, aussi pour toutes
les notifications antérieures). Une notification du contexte `USER` est donc toujours stockée avec un contexte nul.
"""
from django.db.models import Q

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_USER

from .models import Notification

# Types de notification, exposés sans que l'appelant importe le modèle.
COMMENT = Notification.NotificationType.COMMENT.value
CONTACT = Notification.NotificationType.CONTACT.value
EXCHANGE = Notification.NotificationType.EXCHANGE.value
MESSAGE = Notification.NotificationType.MESSAGE.value
EXPIRATION = Notification.NotificationType.EXPIRATION.value
SYSTEM = Notification.NotificationType.SYSTEM.value

TITLE_MAX_LENGTH = 255
LINK_MAX_LENGTH = 255


def _stored_context(context):
    """`(type, id)` à écrire en base : `None` ou contexte personnel -> `(None, None)` (nul = personnel)."""
    if context is None:
        return None, None
    context_type, context_id = context
    if context_type == CONTEXT_USER or context_id is None:
        return None, None
    return context_type, context_id


def notify(
    *, user_id, notification_type: str, title: str, content: str, link: str = '', context=None,
) -> Notification:
    """Crée une notification pour l'utilisateur `user_id` (titre et lien tronqués à la
    longueur des colonnes : une annonce au titre long ne doit pas faire échouer l'appelant).

    `context` : couple `(type, id)` du contexte vendeur concerné (prestataire ou organisation), ou `None` pour une
    notification personnelle. Ni titre ni contenu ne doivent citer de téléphone, d'e-mail ni de nom de membre."""
    context_type, context_id = _stored_context(context)
    return Notification.objects.create(
        user_id=user_id,
        notification_type=notification_type,
        title=title[:TITLE_MAX_LENGTH],
        content=content,
        link=link[:LINK_MAX_LENGTH] if link else '',
        context_type=context_type,
        context_id=context_id,
    )


def purge_context_notifications(user_id, context_type, context_id) -> int:
    """Supprime les notifications de ce compte rattachées à ce contexte (révocation d'un membre : il ne doit plus
    rien lire de l'organisation, ADR 0006, section 12). Renvoie le nombre de lignes supprimées. Idempotent."""
    if context_type == CONTEXT_USER or context_id is None:
        return 0
    deleted, _ = Notification.objects.filter(
        user_id=user_id, context_type=context_type, context_id=context_id,
    ).delete()
    return deleted


def visible_notifications(user_id):
    """Notifications lisibles par ce compte : les siennes, SAUF celles d'une organisation dont il n'est plus membre
    actif (défense en profondeur : la purge à la révocation passe par l'outbox et peut être différée). Une
    organisation suspendue ou archivée reste visible de ses membres (c'est là qu'on leur annonce la décision)."""
    from apps.identity import services as identity_services  # import tardif : identity -> moderation -> notifications

    allowed = identity_services.get_active_organization_ids(user_id)
    return Notification.objects.filter(user_id=user_id).exclude(
        Q(context_type=CONTEXT_ORGANIZATION) & ~Q(context_id__in=allowed),
    )


def mark_all_read(user_id) -> int:
    """Marque comme lues toutes les notifications visibles de l'utilisateur ; renvoie leur nombre."""
    return visible_notifications(user_id).filter(is_read=False).update(is_read=True)
