"""Purge des vues uniques anciennes (données de navigation, LEG-PRV). La durée de conservation
est un réglage du back-office (Paramètres de visibilité), 2 jours par défaut. À planifier
chaque jour (voir backend/cron/crontab)."""
from django.core.management.base import BaseCommand

from apps.visibility import services


class Command(BaseCommand):
    help = "Supprime les vues uniques plus anciennes que la durée de conservation réglée."

    def handle(self, *args, **options):
        count = services.purge_unique_views()
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"{count} vue(s) unique(s) purgée(s)."))
