"""CDC 3.10 / 5.6 : purge automatique de la corbeille (offres supprimées depuis plus de N
jours), tâche quotidienne. Les avis, affaires et conversations liés restent en base : ils ne
portent que l'UUID de l'offre."""
from django.core.management.base import BaseCommand

from apps.marketplace import services


class Command(BaseCommand):
    help = "Supprime définitivement les annonces en corbeille depuis plus de N jours (CDC 3.10)."

    def handle(self, *args, **options):
        count = services.purge_expired_trash()
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"{count} annonce(s) purgée(s) définitivement."))
