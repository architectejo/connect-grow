"""Expiration et purge des invitations d'équipe (ADR 0008, 10). À lancer par cron (toutes les heures).

1. Les invitations `PENDING` échues passent à `EXPIRED` (mise à jour de masse, étiquette vidée, idempotente), ainsi
   que les invitations `AWAITING_CONFIRMATION` dont l'échéance de confirmation est passée (ADR 0010 §10 ; réglage
   `admin_invitation_confirmation_hours`) : aucune appartenance n'a été créée, rien d'autre à défaire.
2. Les lignes closes depuis plus de `IdentitySettings.invitation_history_days` jours sont supprimées, par lots.
3. Une trace `INVITATION_EXPIRED` (`count=<n>`, et `awaiting=<m>` si m > 0) par exécution, seulement si n > 0, sans
   donnée personnelle.
Aucun événement de domaine n'est émis (pas de notification de masse)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.identity.models import IdentitySettings, OrganizationInvitation
from apps.moderation.services import record_audit

PURGE_BATCH_SIZE = 500


def expire_invitations(now=None) -> int:
    """Expire les invitations échues et retourne leur nombre ; trace d'audit si n > 0."""
    now = now or timezone.now()
    with transaction.atomic():
        pending = OrganizationInvitation.objects.filter(
            status=OrganizationInvitation.STATUS_PENDING, expires_at__lte=now,
        ).update(
            status=OrganizationInvitation.STATUS_EXPIRED, closed_at=now, closed_by=None, label='',
            updated_at=now,
        )
        # Attente de confirmation échue : conditionnelle sur l'état (une confirmation concurrente gagne ou perd
        # entièrement). Une échéance nulle (donnée incohérente) est expirée aussi : elle n'est jamais confirmable.
        awaiting = OrganizationInvitation.objects.filter(
            Q(confirmation_expires_at__lte=now) | Q(confirmation_expires_at__isnull=True),
            status=OrganizationInvitation.STATUS_AWAITING_CONFIRMATION,
        ).update(
            status=OrganizationInvitation.STATUS_EXPIRED, closed_at=now, closed_by=None, label='',
            confirmation_code_hash='', updated_at=now,
        )
        count = pending + awaiting
        if count:
            details = f"count={count}" + (f"; awaiting={awaiting}" if awaiting else '')
            record_audit(None, 'INVITATION_EXPIRED', details=details)
    return count


def purge_closed_invitations(now=None) -> int:
    """Supprime les invitations closes depuis plus longtemps que la durée de conservation (lots de 500)."""
    now = now or timezone.now()
    limit = now - timedelta(days=IdentitySettings.get_solo().invitation_history_days)
    purged = 0
    while True:
        ids = list(
            OrganizationInvitation.objects.exclude(status__in=OrganizationInvitation.OPEN_STATUSES)
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
