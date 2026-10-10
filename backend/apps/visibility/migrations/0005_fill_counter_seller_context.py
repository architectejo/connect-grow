"""Remplissage des contextes vendeur des compteurs existants (ADR 0006, 10.2, étape T5).

Séparée de la migration de schéma (0004). Chaque compteur appartient au contexte personnel `USER` de
l'ancien vendeur ; la conversion des comptes entreprise est la tâche T9a. Idempotente : ne touche que les
compteurs sans contexte. Retour arrière : sans effet sur les données.
"""
from django.db import migrations
from django.db.models import F


def fill_contexts(apps, schema_editor):
    Counter = apps.get_model('visibility', 'DailyVisibilityCounter')
    Counter.objects.filter(seller_context_type__isnull=True, seller__isnull=False).update(
        seller_context_type='USER', seller_context_id=F('seller_id'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('visibility', '0004_counter_seller_context'),
    ]

    operations = [
        migrations.RunPython(fill_contexts, migrations.RunPython.noop),
    ]
