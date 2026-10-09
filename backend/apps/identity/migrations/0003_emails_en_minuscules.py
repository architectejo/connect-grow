"""Données : e-mails ramenés à leur forme canonique (espaces retirés, minuscules).

Un e-mail dont la forme canonique est déjà portée par un autre compte est laissé tel quel
(collision à traiter à la main : fusion ou changement d'adresse) ; la connexion le retrouve quand
même, car elle compare sans tenir compte de la casse.
"""
from django.db import migrations


def lowercase_emails(apps, schema_editor):
    User = apps.get_model('identity', 'User')
    taken = {e for e in User.objects.exclude(email__isnull=True).values_list('email', flat=True)}
    for user in User.objects.exclude(email__isnull=True).order_by('date_joined'):
        canonical = (user.email or '').strip().lower() or None
        if canonical == user.email:
            continue
        if canonical is not None and canonical in taken:
            continue
        taken.discard(user.email)
        if canonical is not None:
            taken.add(canonical)
        User.objects.filter(pk=user.pk).update(email=canonical)


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0002_retrait_trust_score_schema_final'),
    ]

    operations = [
        migrations.RunPython(lowercase_emails, migrations.RunPython.noop),
    ]
