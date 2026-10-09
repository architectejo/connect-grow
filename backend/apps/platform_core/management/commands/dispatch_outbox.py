"""ADR 0003 : diffuse les événements de domaine en attente aux abonnés. Cron : chaque minute."""
from django.core.management.base import BaseCommand, CommandError

from apps.platform_core import services
from apps.platform_core.models import OutboxDelivery
from apps.platform_core.operations import requeue_and_audit


class Command(BaseCommand):
    help = "Diffuse les événements de domaine (outbox) aux abonnés."

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=200, help="Livraisons traitées par exécution.")
        parser.add_argument('--max-seconds', type=float, default=50, help="Durée maximale d'une exécution.")
        parser.add_argument('--stats', action='store_true',
                            help="Affiche les décomptes ; code de sortie 1 si une livraison est en échec définitif.")
        parser.add_argument('--requeue', metavar='ID|dead',
                            help="Relance une livraison (identifiant) ou toutes celles en échec définitif (« dead »).")

    def handle(self, *args, **options):
        if options['stats']:
            return self.print_stats()
        if options['requeue']:
            return self.requeue(options['requeue'])
        result = services.dispatch_due(limit=options['limit'], max_seconds=options['max_seconds'])
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(
                f"{result['done']} livraison(s) traitée(s), {result['failed']} en échec, "
                f"{result['skipped']} ignorée(s)."
            ))

    def print_stats(self):
        stats = services.get_stats()
        for status, label in OutboxDelivery.STATUS_CHOICES:
            self.stdout.write(f"{label} : {stats['counts'][status]}")
        oldest = stats['oldest_pending_at']
        self.stdout.write(f"Plus ancienne en attente : {oldest:%d/%m/%Y %H:%M:%S}" if oldest else
                          "Plus ancienne en attente : aucune")
        if stats['counts'][OutboxDelivery.DEAD]:
            raise CommandError(f"{stats['counts'][OutboxDelivery.DEAD]} livraison(s) en échec définitif.")

    def requeue(self, target):
        queryset = OutboxDelivery.objects.select_related('event')
        if target == 'dead':
            deliveries = queryset.filter(status=OutboxDelivery.DEAD)
        else:
            deliveries = queryset.filter(pk=target) if _is_uuid(target) else queryset.none()
            if not deliveries:
                raise CommandError("Livraison introuvable.")
        count = requeue_and_audit(None, deliveries, via='ligne de commande')
        self.stdout.write(self.style.SUCCESS(f"{count} livraison(s) relancée(s)."))


def _is_uuid(value):
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
