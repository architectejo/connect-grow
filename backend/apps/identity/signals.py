"""Signaux de `identity` : point unique de garde et de purge des contextes à la suppression (ADR 0006, section 20, T9-3).

Toute suppression d'un compte (admin, action en masse, shell, futur « supprimer mon compte ») ou d'un profil
prestataire passe par le collecteur de Django, donc par ces récepteurs, dans la transaction de la suppression :
- `pre_delete` : garde (`assert_account_removable`, `assert_provider_removable`) ; un refus annule toute la suppression ;
- `post_delete` : annonce `identity.seller_context_removed`, dont les abonnés effacent ce qui était rattaché.
La suppression d'un compte supprime aussi son profil prestataire (cascade) : les deux contextes sont annoncés. Une
organisation n'est jamais supprimée par ce biais (archivage seulement)."""
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from apps.common.contexts import CONTEXT_PROVIDER, CONTEXT_USER

from . import services
from .models import ProviderProfile, User


@receiver(pre_delete, sender=User, dispatch_uid='identity.guard_user_removal')
def guard_user_removal(sender, instance, **kwargs):
    services.assert_account_removable(instance)


@receiver(pre_delete, sender=ProviderProfile, dispatch_uid='identity.guard_provider_removal')
def guard_provider_removal(sender, instance, **kwargs):
    services.assert_provider_removable(instance)


@receiver(post_delete, sender=User, dispatch_uid='identity.announce_user_context_removed')
def announce_user_removed(sender, instance, **kwargs):
    services.announce_seller_context_removed(CONTEXT_USER, instance.pk)


@receiver(post_delete, sender=ProviderProfile, dispatch_uid='identity.announce_provider_context_removed')
def announce_provider_removed(sender, instance, **kwargs):
    services.announce_seller_context_removed(CONTEXT_PROVIDER, instance.pk)
