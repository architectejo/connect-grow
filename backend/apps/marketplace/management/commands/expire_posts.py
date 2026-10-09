"""CDC 3.2 / 3.6 / 5.6 : expiration des offres après N jours sans renouvellement (tâche
quotidienne), et notification « bientôt expirée » quelques jours avant l'échéance.
Le nom de la commande est conservé (crontab) jusqu'à L0-11."""
from django.core.management.base import BaseCommand

from apps.marketplace import services


class Command(BaseCommand):
    help = "Expire les annonces actives dépassant leur date d'expiration et notifie les échéances proches (CDC 3.2, 3.6)."

    def handle(self, *args, **options):
        expired_count, notified_count = services.expire_offers()
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(
                f"{expired_count} annonce(s) expirée(s), {notified_count} notification(s) d'échéance envoyée(s)."
            ))
