"""Déplace les offres des anciens comptes entreprise vers leur organisation (L0-09 T9-1, ADR 0006 §20).

Lit `identity.LegacyAccountMapping` (deux UUID) et `Organization.status` via `apps.get_model`, en lecture seule
(exception A11). Pour chaque correspondance : les offres du contexte `USER` de l'ancien compte passent au contexte
`ORGANIZATION` de l'organisation ; `created_by` reste inchangé (trace de l'auteur) ; `seller_is_public` devient
faux si l'organisation n'est pas active (une organisation suspendue à la conversion ne republie rien) et n'est jamais
réécrit à vrai (une valeur fausse préexistante est conservée). `seller` (FK) n'est pas touché.

Idempotente (une offre déjà déplacée n'est plus `USER`). Post-condition : plus aucune offre `USER` d'un compte
converti. Retour arrière réel : replace les offres de chaque organisation convertie dans `USER` du propriétaire
d'origine ; `seller_is_public` est conservé, sauf faux si le compte est désactivé ; aucune ligne n'est supprimée.
ATTENTION : ce retour arrière est réservé à une COPIE de base (hypothèse de développement : aucune offre publiée par un
autre membre ni modifiée depuis la conversion). Sur une base réelle, restaurer la sauvegarde.
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
        rows = Offer.objects.filter(seller_context_type='USER', seller_context_id=user_id)
        moved += rows.count()
        rows.update(seller_context_type='ORGANIZATION', seller_context_id=org_id)
        if statuses.get(org_id) != 'ACTIVE':  # un `seller_is_public` faux préexistant n'est jamais réécrit à vrai
            Offer.objects.filter(seller_context_type='ORGANIZATION', seller_context_id=org_id).update(seller_is_public=False)
    leftover = Offer.objects.filter(
        seller_context_type='USER', seller_context_id__in=Mapping.objects.values('user_id'),
    ).count()
    if leftover:
        raise RuntimeError(f"Conversion des offres incomplète : {leftover} offre(s) restée(s) personnelle(s).")
    logger.info("Offres déplacées vers leur organisation : %d.", moved)


def back_to_users(apps, schema_editor):
    logger.warning("Retour arrière des conversions de contexte : réservé à une copie de base, jamais à une base réelle.")
    Offer = apps.get_model('marketplace', 'Offer')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    User = apps.get_model('identity', 'User')
    active = dict(User.objects.filter(pk__in=Mapping.objects.values('user_id')).values_list('pk', 'is_active'))
    restored = 0
    for user_id, org_id in Mapping.objects.values_list('user_id', 'organization_id'):
        rows = Offer.objects.filter(seller_context_type='ORGANIZATION', seller_context_id=org_id)
        restored += rows.count()
        rows.update(seller_context_type='USER', seller_context_id=user_id)
        if not active.get(user_id):  # compte désactivé : offres non publiques ; sinon la valeur actuelle est conservée
            Offer.objects.filter(seller_context_type='USER', seller_context_id=user_id).update(seller_is_public=False)
    logger.info("Offres replacées dans le contexte personnel : %d.", restored)


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_convert_business_profiles'),
        ('marketplace', '0009_fill_offer_seller_context'),
    ]

    operations = [
        migrations.RunPython(to_organizations, back_to_users),
    ]
