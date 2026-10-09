"""CDC 3.7 / 3.8 : le Trust Score d'un utilisateur est recalculé à chaque avis créé, modifié
ou retiré, puis répercuté sur le score de visibilité de ses offres actives (facteur T).
Signaux sur un modèle du même domaine ; les effets sur les autres domaines passent par leurs
`services.py` (transitoire : retiré par L0-07)."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import services
from .models import Review


@receiver(post_save, sender=Review)
def on_review_saved(sender, instance, created, **kwargs):
    if instance.reviewed_user_id:
        services.recompute_trust_score(instance.reviewed_user_id)
    if created:
        services.check_crossed_reviews(instance)


@receiver(post_delete, sender=Review)
def on_review_deleted(sender, instance, **kwargs):
    if instance.reviewed_user_id:
        services.recompute_trust_score(instance.reviewed_user_id)
