"""Anti-abus de création d'organisation (L1-01-B8 ; ADR 0010 D8, §4.5, §4.7, §10 ; décision client Q22).

- `IdentitySettings.max_organizations_per_account` (plafond affiché de 10) est RENOMMÉ `max_memberships_hard_limit` :
  plafond technique caché, défaut 200, bornes 50 à 1 000. La valeur existante est portée à `max(valeur, 200)`.
- Nouveaux réglages internes `org_creation_review_window_days` (30) et `org_creation_review_threshold` (5).
- `Organization.creation_review_status` (`NONE` par défaut : aucune revue rétroactive), index `org_creation_review`,
  permission `review_organization_creation`.

Retour arrière : la garde de données (dernière opération, donc exécutée en premier à l'inverse) refuse de revenir en
0020 tant qu'une organisation est retenue en revue (`PENDING`) : sans la colonne, elle redeviendrait publique sans
décision du personnel. Puis retrait des colonnes ; le plafond renommé reprend son ancien nom, ramené dans ses anciennes
bornes (au plus 100 : la valeur d'avant n'est pas connue, on garde la plus permissive des valeurs autrefois admises).
"""
import django.core.validators
from django.db import migrations, models

HARD_LIMIT_DEFAULT = 200
OLD_LIMIT_MAX = 100


def raise_hard_limit(apps, schema_editor):
    IdentitySettings = apps.get_model('identity', 'IdentitySettings')
    for row in IdentitySettings.objects.all():
        if row.max_memberships_hard_limit < HARD_LIMIT_DEFAULT:
            row.max_memberships_hard_limit = HARD_LIMIT_DEFAULT
            row.save(update_fields=['max_memberships_hard_limit'])


def clamp_to_old_bounds(apps, schema_editor):
    IdentitySettings = apps.get_model('identity', 'IdentitySettings')
    IdentitySettings.objects.filter(max_memberships_hard_limit__gt=OLD_LIMIT_MAX).update(
        max_memberships_hard_limit=OLD_LIMIT_MAX,
    )


def forwards_noop(apps, schema_editor):
    """Rien à écrire : `NONE` par défaut, aucune revue rétroactive (ADR 0010 §10)."""


def refuse_rollback_with_pending_reviews(apps, schema_editor):
    Organization = apps.get_model('identity', 'Organization')
    blocking = Organization.objects.filter(creation_review_status='PENDING').count()
    if blocking:
        raise RuntimeError(
            "Retour arrière de identity.0021 impossible : "
            f"{blocking} organisation(s) sont retenues en revue de création ; sans cette colonne elles redeviendraient "
            "publiques sans décision du personnel. Levez la revue ou suspendez-les, puis relancez la migration inverse."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0020_invitation_confirmation_code'),
    ]

    operations = [
        migrations.RenameField(
            model_name='identitysettings',
            old_name='max_organizations_per_account',
            new_name='max_memberships_hard_limit',
        ),
        migrations.AlterField(
            model_name='identitysettings',
            name='max_memberships_hard_limit',
            field=models.PositiveIntegerField(
                default=200,
                help_text="Seuil de sécurité interne : ne jamais le communiquer comme une limite. Plafond technique "
                          "d'appartenances actives par compte (50 à 1 000) ; au-delà, refus neutre "
                          "« examen du compte ».",
                validators=[
                    django.core.validators.MinValueValidator(50), django.core.validators.MaxValueValidator(1000),
                ],
            ),
        ),
        migrations.RunPython(raise_hard_limit, clamp_to_old_bounds),
        migrations.AddField(
            model_name='identitysettings',
            name='org_creation_review_window_days',
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text="Seuil de sécurité interne : ne jamais le communiquer comme une limite. "
                          "Fenêtre glissante, en jours, du comptage des organisations créées par un même compte (1 à 365).",
                validators=[
                    django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(365),
                ],
            ),
        ),
        migrations.AddField(
            model_name='identitysettings',
            name='org_creation_review_threshold',
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="Seuil de sécurité interne : ne jamais le communiquer comme une limite. "
                          "Rang de création dans la fenêtre à partir duquel une nouvelle organisation est retenue en revue par l'équipe "
                          "(2 à 100).",
                validators=[
                    django.core.validators.MinValueValidator(2), django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AddField(
            model_name='organization',
            name='creation_review_status',
            field=models.CharField(
                choices=[('NONE', 'Aucune'), ('PENDING', 'En revue'), ('CLEARED', 'Levée')],
                default='NONE', max_length=10,
            ),
        ),
        migrations.AddIndex(
            model_name='organization',
            index=models.Index(fields=['creation_review_status'], name='org_creation_review'),
        ),
        migrations.AlterModelOptions(
            name='organization',
            options={'permissions': [
                ('suspend_organization', 'Peut suspendre et réactiver une organisation'),
                ('review_organization_creation', "Peut lever la revue de création d'une organisation"),
            ]},
        ),
        migrations.RunPython(forwards_noop, refuse_rollback_with_pending_reviews),
    ]
