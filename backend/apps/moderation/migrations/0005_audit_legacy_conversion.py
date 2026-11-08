"""Journal d'audit de la conversion des comptes entreprise (L0-09 T9-1, règle 12, ADR 0006 §20).

Une ligne `ORG_CONVERTED` par correspondance `identity.LegacyAccountMapping` (lecture seule, exception A11) :
cible l'organisation, contexte `(ORGANIZATION, id)`, acteur nul (opération système). `details` ne contient que des
identifiants et le statut (jamais de nom, de NIF, d'e-mail ni de téléphone). Idempotente : une conversion déjà
journalisée n'est pas réécrite. Retour arrière : `noop` (un journal d'audit n'est jamais supprimé).
"""
from django.db import migrations

ACTION = 'ORG_CONVERTED'


def audit(apps, schema_editor):
    AuditLog = apps.get_model('moderation', 'AuditLog')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')
    Organization = apps.get_model('identity', 'Organization')
    done = set(AuditLog.objects.filter(action=ACTION).values_list('target_id', flat=True))
    orgs = {o.pk: o for o in Organization.objects.filter(
        pk__in=Mapping.objects.values('organization_id')).only('pk', 'legacy_business_profile_id', 'status')}
    rows = []
    for org_id in Mapping.objects.values_list('organization_id', flat=True):
        org = orgs.get(org_id)
        if org is None or org_id in done:
            continue
        rows.append(AuditLog(
            actor=None, action=ACTION, target_type='organization', target_id=org_id,
            context_type='ORGANIZATION', context_id=org_id,
            details=f'legacy_business_profile={org.legacy_business_profile_id}; status={org.status}',
        ))
        done.add(org_id)
    AuditLog.objects.bulk_create(rows)


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0011_convert_business_profiles'),
        ('moderation', '0004_auditlog_context'),
    ]

    operations = [
        migrations.RunPython(audit, migrations.RunPython.noop),
    ]
