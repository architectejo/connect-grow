"""Contraction (L0-09 T9-2, phase B4) : retrait de `Offer.seller` et de son index `offer_seller_deleted`.

GARDE : échoue, avant toute opération de schéma, s'il reste une offre sans contexte vendeur ou une offre encore au
contexte personnel d'un compte entreprise converti (conversion `marketplace 0010` non faite). Comptages seulement.

RETOUR ARRIÈRE (schéma seulement) : recrée la colonne `seller` (nulle, NON remplie) et l'index ; l'ancien lien
offre -> compte n'est pas restitué (les offres gardent leur contexte). Restaurer la copie de base pour le récupérer.
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
    Offer = apps.get_model('marketplace', 'Offer')
    no_context = Offer.objects.filter(Q(seller_context_type__isnull=True) | Q(seller_context_id__isnull=True)).count()
    leftover = Offer.objects.filter(
        seller_context_type='USER', seller_context_id__in=converted_user_ids(apps),
    ).count()
    if no_context or leftover:
        raise RuntimeError(
            f"Contraction refusée : {no_context} offre(s) sans contexte vendeur, {leftover} offre(s) encore au "
            "contexte personnel d'un compte entreprise converti. Appliquer d'abord marketplace 0009 et 0010."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_convert_business_profiles'),
        ('identity', '0012_kycdocument_organization_required'),
        ('marketplace', '0010_convert_offer_contexts'),
    ]

    operations = [
        migrations.RunPython(guard_conversion_done, migrations.RunPython.noop),
        migrations.RemoveIndex(model_name='offer', name='offer_seller_deleted'),
        migrations.RemoveField(model_name='offer', name='seller'),
    ]
