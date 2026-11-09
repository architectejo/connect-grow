"""Contraction (L0-09 T9-2, phase B6) : retrait de `DailyVisibilityCounter.seller` et de l'index `visib_counter_seller_date`.

GARDE : échoue, avant toute opération de schéma, s'il reste un compteur sans contexte vendeur ou encore au contexte
personnel d'un compte entreprise converti. Comptages seulement.

RETOUR ARRIÈRE (schéma seulement) : recrée la colonne `seller` (nulle, NON remplie) et l'index.
"""
from django.db import migrations
from django.db.models import Q


def converted_user_ids(apps):
    """Comptes dont le contexte `USER` ne doit plus porter de données : ceux de la table de correspondance, et, sans
    elle (vidée à la main), les créateurs et propriétaires des organisations issues d'un profil entreprise."""
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    Organization = apps.get_model('identity', 'Organization')
    Membership = apps.get_model('identity', 'Membership')
    legacy = Organization.objects.filter(legacy_business_profile_id__isnull=False).values('pk')
    ids = set(Mapping.objects.values_list('user_id', flat=True))
    ids |= set(Organization.objects.filter(pk__in=legacy, created_by__isnull=False).values_list('created_by_id', flat=True))
    ids |= set(Membership.objects.filter(organization_id__in=legacy, role='OWNER').values_list('user_id', flat=True))
    return ids


def guard_conversion_done(apps, schema_editor):
    Counter = apps.get_model('visibility', 'DailyVisibilityCounter')
    no_context = Counter.objects.filter(Q(seller_context_type__isnull=True) | Q(seller_context_id__isnull=True)).count()
    leftover = Counter.objects.filter(
        seller_context_type='USER', seller_context_id__in=converted_user_ids(apps),
    ).count()
    if no_context or leftover:
        raise RuntimeError(
            f"Contraction refusée : {no_context} compteur(s) sans contexte vendeur, {leftover} compteur(s) encore "
            "au contexte personnel d'un compte entreprise converti. Appliquer d'abord visibility 0005 et 0006."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_convert_business_profiles'),
        ('identity', '0012_kycdocument_organization_required'),
        ('visibility', '0006_convert_counter_contexts'),
    ]

    operations = [
        migrations.RunPython(guard_conversion_done, migrations.RunPython.noop),
        migrations.RemoveIndex(model_name='dailyvisibilitycounter', name='visib_counter_seller_date'),
        migrations.RemoveField(model_name='dailyvisibilitycounter', name='seller'),
    ]
