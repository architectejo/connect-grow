"""Exigences de pièces provisoires par type d'organisation (ADR 0006, 4.3 ; Q-CLI2, à valider par le client).

Données seules (aucun schéma). Modifiables ensuite dans le back-office : le retour arrière ne supprime que
les lignes encore identiques à la graine, jamais une exigence que l'administrateur a créée."""
from django.db import migrations

REQUIREMENTS = {
    'ENTREPRISE': ('RCCM', 'ID_NATIONALE', 'PIECE_GERANT'),
    'ORGANISATEUR_EVENEMENTS': ('RCCM', 'ID_NATIONALE', 'PIECE_GERANT'),
    'BOUTIQUE': ('ID_NATIONALE', 'PIECE_GERANT'),
    'ONG': ('ARRETE_ONG', 'ID_NATIONALE', 'PIECE_GERANT'),
}


def seed(apps, schema_editor):
    Requirement = apps.get_model('identity', 'OrganizationDocumentRequirement')
    for org_type, documents in REQUIREMENTS.items():
        for position, document_type in enumerate(documents):
            Requirement.objects.get_or_create(
                org_type=org_type, document_type=document_type, defaults={'position': position},
            )


def unseed(apps, schema_editor):
    Requirement = apps.get_model('identity', 'OrganizationDocumentRequirement')
    for org_type, documents in REQUIREMENTS.items():
        for position, document_type in enumerate(documents):
            Requirement.objects.filter(org_type=org_type, document_type=document_type, position=position).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0006_contexts_schema'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
