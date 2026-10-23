"""Remplissage des contextes vendeur des offres existantes (ADR 0006, 10.2, étape T5).

Séparée de la migration de schéma (0008). Toute offre existante appartient à son ancien vendeur, donc au
contexte personnel `USER` de ce compte. La conversion des comptes entreprise en organisations est la tâche T9a
(migrations de conversion), pas celle-ci. Idempotente : ne touche que les offres sans contexte. Les offres
des comptes déjà désactivés ne sont pas publiques (`seller_is_public`), comme avant (`seller__is_active`).
Retour arrière : sans effet sur les données (les colonnes sont retirées par la migration 0008 inversée).
"""
from django.db import migrations
from django.db.models import F


def fill_contexts(apps, schema_editor):
    Offer = apps.get_model('marketplace', 'Offer')
    Offer.objects.filter(seller_context_type__isnull=True, seller__isnull=False).update(
        seller_context_type='USER', seller_context_id=F('seller_id'), created_by_id=F('seller_id'),
    )
    Offer.objects.filter(seller_context_type='USER', seller__is_active=False).update(seller_is_public=False)


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0008_offer_seller_context'),
    ]

    operations = [
        migrations.RunPython(fill_contexts, migrations.RunPython.noop),
    ]
