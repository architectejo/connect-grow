"""Expiration et purge des invitations d'équipe (ADR 0008, 10). À lancer par cron (toutes les heures).

1. Les invitations `PENDING` échues passent à `EXPIRED` (mise à jour de masse, étiquette vidée, idempotente).
2. Les lignes closes depuis plus de `IdentitySettings.invitation_history_days` jours sont supprimées, par lots.
3. Une trace `INVITATION_EXPIRED` (`count=<n>`) par exécution, seulement si n > 0, sans donnée personnelle.
Aucun événement de domaine n'est émis (pas de notification de masse)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.identity.models import IdentitySettings, OrganizationInvitation
from apps.moderation.services import record_audit

PURGE_BATCH_SIZE = 500


def expire_invitations(now=None) -> int:
    """Expire les invitations échues et retourne leur nombre ; trace d'audit si n > 0."""
    now = now or timezone.now()
    with transaction.atomic():
        count = OrganizationInvitation.objects.filter(
            status=OrganizationInvitation.STATUS_PENDING, expires_at__lte=now,
        ).update(
            status=OrganizationInvitation.STATUS_EXPIRED, closed_at=now, closed_by=None, label='',
            updated_at=now,
        )
        if count:
            record_audit(None, 'INVITATION_EXPIRED', details=f"count={count}")
    return count


def purge_closed_invitations(now=None) -> int:
    """Supprime les invitations closes depuis plus longtemps que la durée de conservation (lots de 500)."""
    now = now or timezone.now()
    limit = now - timedelta(days=IdentitySettings.get_solo().invitation_history_days)
    purged = 0
    while True:
        ids = list(
            OrganizationInvitation.objects.exclude(status=OrganizationInvitation.STATUS_PENDING)
            .filter(closed_at__lt=limit).values_list('pk', flat=True)[:PURGE_BATCH_SIZE]
        )
        if not ids:
            return purged
        OrganizationInvitation.objects.filter(pk__in=ids).delete()
        purged += len(ids)


class Command(BaseCommand):
    help = "Expire les invitations d'équipe échues et purge les invitations closes anciennes."

    def handle(self, *args, **options):
        now = timezone.now()
        expired = expire_invitations(now)
        purged = purge_closed_invitations(now)
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"{expired} invitation(s) expirée(s), {purged} purgée(s)."))
