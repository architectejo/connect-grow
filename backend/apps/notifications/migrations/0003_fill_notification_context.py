"""Remplissage du contexte des notifications existantes (ADR 0006, 4.5, étape T5b).

Séparée de la migration de schéma (0002). Toute notification existante a été adressée à un compte à titre
personnel : son contexte est `USER` de ce compte (nul ET `USER` signifient « personnel » ; le remplissage rend
le filtre par contexte de T6 uniforme pour l'existant). Idempotente : ne touche que les notifications sans
contexte. Aucun comportement ne change : rien ne lit ces colonnes avant T6. Retour arrière : sans effet sur
les données (les colonnes sont retirées par la migration 0002 inversée).
"""
from django.db import migrations
from django.db.models import F


def fill_contexts(apps, schema_editor):
    Notification = apps.get_model('notifications', 'Notification')
    Notification.objects.filter(context_type__isnull=True, context_id__isnull=True).update(
        context_type='USER', context_id=F('user_id'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_notification_context'),
    ]

    operations = [
        migrations.RunPython(fill_contexts, migrations.RunPython.noop),
    ]
