"""Signaux de `identity` : point unique de purge des contextes à la suppression (ADR 0006, section 20, T9-3).

Toute suppression d'un compte (admin, action en masse, shell, futur « supprimer mon compte ») ou d'un profil
prestataire passe par le collecteur de Django, donc par ces récepteurs, dans la transaction de la suppression :
aucun chemin ne peut oublier la purge. La suppression d'un compte supprime aussi son profil prestataire (cascade) :
les deux contextes sont annoncés. Une organisation n'est jamais supprimée par ce biais (archivage seulement)."""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.common.contexts import CONTEXT_PROVIDER, CONTEXT_USER

from . import services
from .models import ProviderProfile, User


@receiver(post_delete, sender=User, dispatch_uid='identity.announce_user_context_removed')
def announce_user_removed(sender, instance, raw=False, **kwargs):
    if raw:  # chargement de fixtures : aucune purge
        return
    services.announce_seller_context_removed(CONTEXT_USER, instance.pk)


@receiver(post_delete, sender=ProviderProfile, dispatch_uid='identity.announce_provider_context_removed')
def announce_provider_removed(sender, instance, raw=False, **kwargs):
    if raw:
        return
    services.announce_seller_context_removed(CONTEXT_PROVIDER, instance.pk)
