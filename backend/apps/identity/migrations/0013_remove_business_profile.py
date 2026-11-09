"""Contraction (L0-09 T9-2, phase B2) : suppression des modèles `BusinessProfileCategory` et `BusinessProfile`.

GARDE : même contrôle que `identity 0012` (aucun profil sans correspondance, aucune pièce sans organisation),
refait ici car cette migration peut être appliquée seule après un retour arrière partiel.

RETOUR ARRIÈRE (schéma seulement) : recrée deux tables VIDES ; les profils et leurs catégories ne sont pas restitués
(restaurer la copie de base). Les organisations converties restent intactes dans les deux sens.
"""
from django.db import migrations


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
        ('identity', '0012_kycdocument_organization_required'),
    ]

    operations = [
        migrations.RunPython(guard_conversion_done, migrations.RunPython.noop),
        migrations.DeleteModel(name='BusinessProfileCategory'),
        migrations.DeleteModel(name='BusinessProfile'),
    ]
