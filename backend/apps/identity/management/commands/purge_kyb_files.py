"""Purge des FICHIERS des pièces d'organisation après la durée de conservation (règle 11, règle 12).

La durée vient de `IdentitySettings.kyb_file_retention_days` (0 = illimité, valeur par défaut tant que le client
n'a pas répondu, LEG-PRV). Seul le fichier est supprimé : la ligne et la décision restent, donc les claims
de vérification sont inchangés. Chaque purge est journalisée. À lancer par cron (quotidien)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.common.contexts import CONTEXT_ORGANIZATION
from apps.identity.models import IdentitySettings, KycDocument
from apps.moderation.services import record_audit


class Command(BaseCommand):
    help = "Supprime les fichiers des pièces d'organisation décidées depuis plus longtemps que la durée de conservation."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Compte sans supprimer.")

    def handle(self, *args, **options):
        days = IdentitySettings.get_solo().kyb_file_retention_days
        if days <= 0:
            if options['verbosity'] > 0:
                self.stdout.write("Conservation illimitée (0 jour) : rien à purger.")
            return
        limit = timezone.now() - timedelta(days=days)
        queryset = KycDocument.objects.filter(
            organization__isnull=False, reviewed_at__lt=limit,
            status__in=[KycDocument.STATUS_VALIDE, KycDocument.STATUS_REFUSE],
        ).exclude(Q(file='') | Q(file__isnull=True))
        purged = 0
        for document in queryset.iterator():
            if options['dry_run']:
                purged += 1
                continue
            name = document.file.name
            try:
                document.file.storage.delete(name)
            except OSError as exc:
                self.stderr.write(f"Pièce {document.pk} : suppression impossible ({exc}).")
                continue
            KycDocument.objects.filter(pk=document.pk).update(file='')
            record_audit(
                None, 'KYC_FILE_PURGED', target=document,
                details=f"organization={document.organization_id}; document_type={document.document_type}; "
                        f"retention_days={days}",
                context=(CONTEXT_ORGANIZATION, document.organization_id),
            )
            purged += 1
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"{purged} fichier(s) de pièce purgé(s)."))
