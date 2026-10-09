"""CDC 3.7 / 3.8 : le Trust Score d'un utilisateur est recalculé à chaque avis créé, modifié
ou retiré, puis répercuté sur le score de visibilité de ses offres actives (facteur T).
Signaux sur un modèle du même domaine ; le recalcul du Trust Score reste synchrone et passe par
les `services.py` des autres domaines (transitoire : retiré par L0-07). Les autres effets
(notification, signalement automatique) sont des événements de domaine (ADR 0003)."""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from . import services
from .models import Review


@receiver(pre_save, sender=Review)
def on_review_saving(sender, instance, **kwargs):
    """Marque l'avis « à recalculer » seulement si la note, la visibilité ou la personne évaluée
    change (une réponse ou une retouche de texte ne touche pas au Trust Score)."""
    instance._trust_dirty = True
    if instance._state.adding:
        return
    previous = Review.objects.filter(pk=instance.pk).values('rating', 'is_hidden', 'reviewed_user_id').first()
    if previous is not None:
        instance._trust_dirty = (
            previous['rating'] != instance.rating or previous['is_hidden'] != instance.is_hidden
            or previous['reviewed_user_id'] != instance.reviewed_user_id
        )


@receiver(post_save, sender=Review)
def on_review_saved(sender, instance, created, **kwargs):
    if instance.reviewed_user_id and (created or getattr(instance, '_trust_dirty', True)):
        services.recompute_trust_score(instance.reviewed_user_id)
    if created:
        services.check_crossed_reviews(instance)  # publie un événement dans sa propre transaction


@receiver(post_delete, sender=Review)
def on_review_deleted(sender, instance, **kwargs):
    if instance.reviewed_user_id:
        services.recompute_trust_score(instance.reviewed_user_id)
