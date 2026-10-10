"""ADR 0003 : purge les événements traités (7 jours) et en échec définitif (30 jours). Cron quotidien."""
from django.core.management.base import BaseCommand

from apps.platform_core import services


class Command(BaseCommand):
    help = "Supprime les anciens événements de domaine (durées : OUTBOX_RETENTION_DAYS, OUTBOX_DEAD_RETENTION_DAYS)."

    def handle(self, *args, **options):
        removed = services.purge()
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(
                f"{removed['done']} événement(s) traité(s) et {removed['dead']} en échec supprimé(s)."
            ))
