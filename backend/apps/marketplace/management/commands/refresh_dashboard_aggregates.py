"""CDC 5.6 : agrégats du tableau de bord (contacts reçus par offre), tâche horaire. Les
contacts sont comptés ici (domaine marketplace) puis écrits dans les compteurs de
`visibility`, qui tient déjà les vues à jour en temps réel."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.marketplace import services
from apps.visibility import services as visibility_services


class Command(BaseCommand):
    help = "Recalcule l'agrégat quotidien des contacts reçus par annonce (CDC 3.9, 5.6)."

    def handle(self, *args, **options):
        today = timezone.now().date()
        rows = services.count_contacts_by_offer(today)
        count = visibility_services.set_daily_contacts(today, rows)
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"Agrégat de contacts recalculé pour {count} annonce(s)."))
