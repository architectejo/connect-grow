"""Réconciliation de la visibilité publique des vendeurs (ADR 0006, A7), tâche horaire.

`Offer.seller_is_public` est dénormalisé depuis `identity` et tenu à jour par l'abonné de
`identity.seller_context_status_changed`. Cette commande recalcule TOUS les contextes vendeur ayant des offres
et corrige tout écart (événement perdu ou mort, modification directe en base). Idempotente.
"""
from django.core.management.base import BaseCommand

from apps.marketplace import services


class Command(BaseCommand):
    help = "Recalcule la visibilité publique des offres depuis l'état des vendeurs (idempotent)."

    def handle(self, *args, **options):
        changed = services.sync_all_seller_visibility()
        if options['verbosity'] > 0:
            self.stdout.write(self.style.SUCCESS(f"{changed} offre(s) mise(s) à jour."))
