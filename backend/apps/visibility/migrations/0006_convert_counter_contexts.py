"""Déplace les compteurs de visibilité des anciens comptes entreprise vers leur organisation (L0-09 T9-1).

Même logique que `marketplace 0010` : lecture seule de `identity.LegacyAccountMapping` (exception A11) ; les
compteurs du contexte `USER` de l'ancien compte passent au contexte `ORGANIZATION` ; `views`, `shares`, `contacts`
et `seller` (FK) sont inchangés. Idempotente ; post-condition : aucun compteur `USER` d'un compte converti.
Retour arrière réel ; aucune ligne supprimée. ATTENTION : réservé à une COPIE de base (hypothèse de développement :
aucune donnée rattachée à l'organisation par d'autres membres depuis la conversion) ; sur une base réelle, restaurer la sauvegarde.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def to_organizations(apps, schema_editor):
    Counter = apps.get_model('visibility', 'DailyVisibilityCounter')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    moved = 0
    for user_id, org_id in Mapping.objects.values_list('user_id', 'organization_id'):
        moved += Counter.objects.filter(seller_context_type='USER', seller_context_id=user_id).update(
            seller_context_type='ORGANIZATION', seller_context_id=org_id,
        )
    leftover = Counter.objects.filter(
        seller_context_type='USER', seller_context_id__in=Mapping.objects.values('user_id'),
    ).count()
    if leftover:
        raise RuntimeError(f"Conversion des compteurs incomplète : {leftover} compteur(s) resté(s) personnel(s).")
    logger.info("Compteurs déplacés vers leur organisation : %d.", moved)


def back_to_users(apps, schema_editor):
    logger.warning("Retour arrière des conversions de contexte : réservé à une copie de base, jamais à une base réelle.")
    Counter = apps.get_model('visibility', 'DailyVisibilityCounter')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    restored = 0
    for user_id, org_id in Mapping.objects.values_list('user_id', 'organization_id'):
        restored += Counter.objects.filter(seller_context_type='ORGANIZATION', seller_context_id=org_id).update(
            seller_context_type='USER', seller_context_id=user_id,
        )
    logger.info("Compteurs replacés dans le contexte personnel : %d.", restored)


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_convert_business_profiles'),
        ('visibility', '0005_fill_counter_seller_context'),
    ]

    operations = [
        migrations.RunPython(to_organizations, back_to_users),
    ]
