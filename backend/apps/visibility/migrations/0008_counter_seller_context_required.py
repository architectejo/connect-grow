"""Contraction (L0-09 T9-2, phase B7) : le contexte vendeur d'un compteur devient obligatoire (NOT NULL).

GARDE : échoue si un compteur a encore un contexte nul. RETOUR ARRIÈRE : les colonnes redeviennent nulles.
"""
from django.db import migrations, models
from django.db.models import Q


def guard_contexts_filled(apps, schema_editor):
    Counter = apps.get_model('visibility', 'DailyVisibilityCounter')
    missing = Counter.objects.filter(Q(seller_context_type__isnull=True) | Q(seller_context_id__isnull=True)).count()
    if missing:
        raise RuntimeError(
            f"Contraction refusée : {missing} valeur(s) de contexte vendeur nulle(s) parmi les compteurs.")


class Migration(migrations.Migration):

    dependencies = [
        ('visibility', '0007_remove_counter_seller'),
    ]

    operations = [
        migrations.RunPython(guard_contexts_filled, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='dailyvisibilitycounter',
            name='seller_context_type',
            field=models.CharField(max_length=20),
        ),
        migrations.AlterField(
            model_name='dailyvisibilitycounter',
            name='seller_context_id',
            field=models.UUIDField(),
        ),
    ]
