"""Remplissage de l'identité affichée des messages existants (ADR 0006, 4.5, étape T5b).

Séparée de la migration de schéma (0002). Tout message existant a été écrit à titre personnel : son identité
affichée est le contexte `USER` de l'expéditeur. Les conversations existantes restent SANS contexte vendeur
(ADR 0006, 10.3 : accès par participants ; leur vendeur se déduirait de l'offre, table d'un autre domaine que
cette migration ne lit pas). Idempotente : ne touche que les messages sans contexte. Aucun comportement ne
change : rien ne lit ces colonnes avant T7. Retour arrière : sans effet sur les données (les colonnes sont
retirées par la migration 0002 inversée).
"""
from django.db import migrations
from django.db.models import F


def fill_sender_contexts(apps, schema_editor):
    Message = apps.get_model('messaging', 'Message')
    Message.objects.filter(sender_context_type__isnull=True, sender_context_id__isnull=True).update(
        sender_context_type='USER', sender_context_id=F('sender_id'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('messaging', '0002_conversation_message_contexts'),
    ]

    operations = [
        migrations.RunPython(fill_sender_contexts, migrations.RunPython.noop),
    ]
