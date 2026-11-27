"""Nombre maximal d'organisations d'un même créateur en revue de création simultanément (L1-01-B8, correction de la
revue S5 ; ADR 0010 D8). Réglage interne, jamais exposé, défaut 3 (bornes 1 à 50). Ajout pur ; retour arrière : retrait
de la colonne (sans effet sur les données)."""
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0021_creation_antiabuse'),
    ]

    operations = [
        migrations.AddField(
            model_name='identitysettings',
            name='org_creation_review_max_pending',
            field=models.PositiveSmallIntegerField(
                default=3,
                help_text="Seuil de sécurité interne : ne jamais le communiquer comme une limite. Nombre "
                          "d'organisations d'un même créateur pouvant être en revue en même temps (1 à 50) ; "
                          "au-delà, refus neutre.",
                validators=[
                    django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(50),
                ],
            ),
        ),
    ]
