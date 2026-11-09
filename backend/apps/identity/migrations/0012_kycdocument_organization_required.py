"""Contraction (L0-09 T9-2, phase B1) : `KycDocument.organization` devient obligatoire, `business_profile` disparaît.

GARDE : échoue, avant toute opération de schéma, si la conversion des comptes entreprise n'a pas eu lieu (une pièce
sans organisation, ou un profil sans ligne de correspondance). Le message ne contient que des comptages.

RETOUR ARRIÈRE (schéma seulement) : recrée la colonne `business_profile` (nulle) et rend `organization` nulle ; le
lien d'origine entre une pièce et son profil N'EST PAS restitué. Seule la restauration de la copie de base le fait.
"""
from django.db import migrations, models
import django.db.models.deletion


def guard_conversion_done(apps, schema_editor):
    KycDocument = apps.get_model('identity', 'KycDocument')
    Profile = apps.get_model('identity', 'BusinessProfile')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    orphans = KycDocument.objects.filter(organization__isnull=True).count()
    unconverted = Profile.objects.exclude(user_id__in=Mapping.objects.values('user_id')).count()
    if orphans or unconverted:
        raise RuntimeError(
            f"Contraction refusée : conversion des comptes entreprise incomplète ({orphans} pièce(s) sans "
            f"organisation, {unconverted} profil(s) sans correspondance). Appliquer d'abord identity 0011 ; "
            "ne jamais contracter une base non convertie."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_convert_business_profiles'),
    ]

    operations = [
        migrations.RunPython(guard_conversion_done, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='kycdocument',
            name='organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='kyc_documents', to='identity.organization'),
        ),
        migrations.RemoveField(
            model_name='kycdocument',
            name='business_profile',
        ),
    ]
