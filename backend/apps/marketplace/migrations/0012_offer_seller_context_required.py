"""Contraction (L0-09 T9-2, phase B5) : le contexte vendeur d'une offre devient obligatoire (NOT NULL).

GARDE : échoue si une offre a encore un contexte nul. RETOUR ARRIÈRE : les colonnes redeviennent nulles.
"""
from django.db import migrations, models
from django.db.models import Q


def guard_contexts_filled(apps, schema_editor):
    Offer = apps.get_model('marketplace', 'Offer')
    missing = Offer.objects.filter(Q(seller_context_type__isnull=True) | Q(seller_context_id__isnull=True)).count()
    if missing:
        raise RuntimeError(f"Contraction refusée : {missing} valeur(s) de contexte vendeur nulle(s) parmi les offres.")


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0011_remove_offer_seller'),
    ]

    operations = [
        migrations.RunPython(guard_contexts_filled, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='offer',
            name='seller_context_type',
            field=models.CharField(
                choices=[('USER', 'Compte personnel'), ('PROVIDER', 'Prestataire individuel'), ('ORGANIZATION', 'Organisation')],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='offer',
            name='seller_context_id',
            field=models.UUIDField(),
        ),
    ]
