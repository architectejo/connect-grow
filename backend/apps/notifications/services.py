"""Interface publique du domaine `notifications` pour les autres domaines."""
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


def notify(*, user_id, notification_type: str, title: str, content: str, link: str = '') -> Notification:
    """Crée une notification pour l'utilisateur `user_id` (titre et lien tronqués à la
    longueur des colonnes : une annonce au titre long ne doit pas faire échouer l'appelant)."""
    return Notification.objects.create(
        user_id=user_id,
        notification_type=notification_type,
        title=title[:TITLE_MAX_LENGTH],
        content=content,
        link=link[:LINK_MAX_LENGTH] if link else '',
    )


def mark_all_read(user_id) -> int:
    """Marque comme lues toutes les notifications de l'utilisateur ; renvoie leur nombre."""
    return Notification.objects.filter(user_id=user_id, is_read=False).update(is_read=True)
