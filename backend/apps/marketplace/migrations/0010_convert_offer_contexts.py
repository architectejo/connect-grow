"""Déplace les offres des anciens comptes entreprise vers leur organisation (L0-09 T9-1, ADR 0006 §20).

Lit `identity.LegacyAccountMapping` (deux UUID) et `Organization.status` via `apps.get_model`, en lecture seule
(exception A11). Pour chaque correspondance : les offres du contexte `USER` de l'ancien compte passent au contexte
`ORGANIZATION` de l'organisation ; `created_by` reste inchangé (trace de l'auteur) ; `seller_is_public` vaut
« organisation active » (une organisation suspendue à la conversion ne republie rien). `seller` (FK) n'est pas touché.

Idempotente (une offre déjà déplacée n'est plus `USER`). Post-condition : plus aucune offre `USER` d'un compte
converti. Retour arrière réel : replace les offres de chaque organisation convertie dans `USER` du propriétaire
d'origine, `seller_is_public` repris de l'état du compte ; aucune ligne n'est supprimée. Hypothèse de développement :
aucune offre publiée par un autre membre entre-temps (sinon, restaurer la copie de la base).
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def to_organizations(apps, schema_editor):
    Offer = apps.get_model('marketplace', 'Offer')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    Organization = apps.get_model('identity', 'Organization')
    statuses = dict(Organization.objects.filter(
        pk__in=Mapping.objects.values('organization_id')).values_list('pk', 'status'))
    moved = 0
    for user_id, org_id in Mapping.objects.values_list('user_id', 'organization_id'):
        moved += Offer.objects.filter(seller_context_type='USER', seller_context_id=user_id).update(
            seller_context_type='ORGANIZATION', seller_context_id=org_id,
            seller_is_public=statuses.get(org_id) == 'ACTIVE',
        )
    leftover = Offer.objects.filter(
        seller_context_type='USER', seller_context_id__in=Mapping.objects.values('user_id'),
    ).count()
    if leftover:
        raise RuntimeError(f"Conversion des offres incomplète : {leftover} offre(s) restée(s) personnelle(s).")
    logger.info("Offres déplacées vers leur organisation : %d.", moved)


def back_to_users(apps, schema_editor):
    Offer = apps.get_model('marketplace', 'Offer')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    User = apps.get_model('identity', 'User')
    active = dict(User.objects.filter(pk__in=Mapping.objects.values('user_id')).values_list('pk', 'is_active'))
    restored = 0
    for user_id, org_id in Mapping.objects.values_list('user_id', 'organization_id'):
        restored += Offer.objects.filter(seller_context_type='ORGANIZATION', seller_context_id=org_id).update(
            seller_context_type='USER', seller_context_id=user_id, seller_is_public=bool(active.get(user_id)),
        )
    logger.info("Offres replacées dans le contexte personnel : %d.", restored)


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_convert_business_profiles'),
        ('marketplace', '0009_fill_offer_seller_context'),
    ]

    operations = [
        migrations.RunPython(to_organizations, back_to_users),
    ]
