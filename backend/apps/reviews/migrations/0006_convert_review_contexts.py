"""Les avis des anciens comptes entreprise suivent leur organisation (L0-09 T9-1, ADR 0006 §20, règle 4).

Lecture seule de `identity.LegacyAccountMapping` (exception A11). Les avis reçus par le contexte `USER` de l'ancien
compte passent au contexte `ORGANIZATION` : la note reste par contexte, jamais fusionnée. Tous les avis d'un même
acheteur sur ce contexte sont déplacés ensemble : `counts_for_seller` n'a pas à être recalculé. Idempotente ;
post-condition : aucun avis `USER` pour un compte converti. Retour arrière réel (même hypothèse de développement) ;
aucune ligne supprimée.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def to_organizations(apps, schema_editor):
    Review = apps.get_model('reviews', 'Review')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    moved = 0
    for user_id, org_id in Mapping.objects.values_list('user_id', 'organization_id'):
        moved += Review.objects.filter(seller_context_type='USER', seller_context_id=user_id).update(
            seller_context_type='ORGANIZATION', seller_context_id=org_id,
        )
    leftover = Review.objects.filter(
        seller_context_type='USER', seller_context_id__in=Mapping.objects.values('user_id'),
    ).count()
    if leftover:
        raise RuntimeError(f"Conversion des avis incomplète : {leftover} avis resté(s) personnel(s).")
    logger.info("Avis déplacés vers leur organisation : %d.", moved)


def back_to_users(apps, schema_editor):
    Review = apps.get_model('reviews', 'Review')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    restored = 0
    for user_id, org_id in Mapping.objects.values_list('user_id', 'organization_id'):
        restored += Review.objects.filter(seller_context_type='ORGANIZATION', seller_context_id=org_id).update(
            seller_context_type='USER', seller_context_id=user_id,
        )
    logger.info("Avis replacés dans le contexte personnel : %d.", restored)


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_convert_business_profiles'),
        ('reviews', '0005_provider_context_choice'),
    ]

    operations = [
        migrations.RunPython(to_organizations, back_to_users),
    ]
