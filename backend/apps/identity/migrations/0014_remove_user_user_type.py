"""Contraction (L0-09 T9-2, phase B3) : retrait de `User.user_type` (un compte est unique, ADR 0006, règle 1).

Aucune garde : le type n'a plus aucune lecture ; la conversion a été décidée par l'existence du profil, jamais par
cette valeur (spec T9, 2.3).

RETOUR ARRIÈRE (schéma seulement) : recrée la colonne avec le défaut `PARTICULIER` ; la valeur d'origine n'est pas restituée.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0013_remove_business_profile'),
    ]

    operations = [
        migrations.RemoveField(model_name='user', name='user_type'),
    ]
