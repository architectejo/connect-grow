import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0015_organizationinvitation'),
    ]

    operations = [
        migrations.AddField(
            model_name='identitysettings',
            name='invitation_history_days',
            field=models.PositiveSmallIntegerField(default=30, help_text="Jours de conservation d'une invitation close (acceptée, refusée, révoquée, expirée) avant purge (1 à 365). Valeur provisoire, à confirmer.", validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(365)]),
        ),
        migrations.AddField(
            model_name='identitysettings',
            name='invitation_ttl_days',
            field=models.PositiveSmallIntegerField(default=7, help_text="Durée de validité d'un lien d'invitation, en jours (1 à 30). Valeur provisoire, à confirmer.", validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(30)]),
        ),
        migrations.AddField(
            model_name='identitysettings',
            name='max_pending_invitations',
            field=models.PositiveSmallIntegerField(default=20, help_text="Nombre maximal d'invitations en attente par organisation (1 à 200). Valeur provisoire, à confirmer.", validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(200)]),
        ),
    ]
