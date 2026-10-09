"""CDC 3.5, ADR 0004 6.3 : la récence R baisse avec le temps, donc le score organique stocké (E x R)
est recalculé chaque heure depuis les compteurs sources (favoris et contacts recomptés).
Idempotent : une seconde exécution donne le même résultat, à la dérive de R près."""
from django.core.management.base import BaseCommand

from apps.marketplace import services


class Command(BaseCommand):
    help = "Recalcule le score de visibilité organique (E x R) des offres actives (CDC 3.5)."

    def handle(self, *args, **options):
        count = services.refresh_all_scores()
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"{count} offres mises à jour."))
