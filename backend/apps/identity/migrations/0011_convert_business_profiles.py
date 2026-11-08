"""Conversion des comptes entreprise (`BusinessProfile`) en organisations (L0-09 T9-1, ADR 0006 §20, spec T9 §2.3).

Phase additive : rien n'est supprimé, ni ligne, ni fichier. Le critère est l'existence du profil (pas `user_type`).
Une organisation `ENTREPRISE` par profil, jamais de fusion ni de suffixe en cas de collision de noms.

- Le propriétaire du profil devient l'unique membre `OWNER`. Aucun autre compte ne reçoit de rôle.
- La vérification n'est JAMAIS recopiée (règle 3) : elle se dérive des pièces `VALIDE` (`is_verified` ignoré).
- Contact, consentements, conversations, messages et notifications ne sont pas transférés (règle 10).
- Propriétaire désactivé OU sous sanction bloquante en cours (`moderation.Sanction`, lue en lecture seule par
  `apps.get_model`, exception A11) : organisation `SUSPENDED`, pour ne pas republier ses offres. Réactivation par
  le personnel.
- Adresse : l'ancien `BusinessProfile` n'avait pas de ville ni de commune propres ; celles du compte (donnée personnelle)
  ne sont PAS reprises (`NULL`), l'organisation les renseignera elle-même (LEG-PRV).
- Le logo garde le même nom de fichier ; les pièces KYC gardent leur fichier (aucun déplacement).
- Idempotente : un profil déjà dans `LegacyAccountMapping` (ou déjà lié par `legacy_business_profile_id`) n'est pas
  recréé. La transaction de la migration couvre tout : un échec n'écrit rien.
- Retour arrière : `noop` documenté. Les organisations créées restent (inoffensives tant que `BusinessProfile`
  existe) ; une nouvelle application est idempotente. Aucune suppression automatique.
- Les journaux ne contiennent que des comptages, jamais de nom, de NIF, d'e-mail ni de téléphone.

Lecture des modèles historiques par `apps.get_model` (exception A11 de l'ADR 0006).
"""
import logging

from django.db import migrations
from django.utils import timezone

from apps.identity import legacy_conversion as rules

logger = logging.getLogger(__name__)


def convert_profiles(apps, schema_editor):
    BusinessProfile = apps.get_model('identity', 'BusinessProfile')
    BusinessProfileCategory = apps.get_model('identity', 'BusinessProfileCategory')
    Organization = apps.get_model('identity', 'Organization')
    OrganizationCategory = apps.get_model('identity', 'OrganizationCategory')
    Membership = apps.get_model('identity', 'Membership')
    KycDocument = apps.get_model('identity', 'KycDocument')
    Mapping = apps.get_model('identity', 'LegacyAccountMapping')

    Sanction = apps.get_model('moderation', 'Sanction')
    now = timezone.now()
    # Une seule requête avant la boucle : propriétaires de profils sous sanction bloquante en cours.
    sanctioned = {
        user_id for user_id, kind, active, ends_at in Sanction.objects.filter(
            user_id__in=BusinessProfile.objects.values('user_id'), is_active=True,
            sanction_type__in=rules.BLOCKING_SANCTION_TYPES,
        ).values_list('user_id', 'sanction_type', 'is_active', 'ends_at')
        if rules.is_blocking(kind, active, ends_at, now)
    }
    mapped_users = set(Mapping.objects.values_list('user_id', flat=True))
    org_by_legacy = dict(
        Organization.objects.filter(legacy_business_profile_id__isnull=False)
        .values_list('legacy_business_profile_id', 'pk')
    )
    created = reused = skipped = 0

    for profile in BusinessProfile.objects.select_related('user').order_by('created_at', 'pk').iterator():
        if profile.user_id in mapped_users:
            skipped += 1
            continue
        user = profile.user
        org_id = org_by_legacy.get(profile.pk)
        if org_id is None:
            suspended = rules.owner_is_suspended(user.is_active, user.pk in sanctioned)
            org = Organization.objects.create(
                name=rules.converted_name(profile.business_name, profile.pk),
                org_type=rules.ORG_TYPE,
                description=(profile.bio or '')[:rules.DESCRIPTION_MAX_LENGTH],
                logo=profile.logo.name if profile.logo else None,
                nif=profile.nif or '',
                status='SUSPENDED' if suspended else 'ACTIVE',
                suspension_reason=rules.SUSPENSION_REASON if suspended else '',
                created_by_id=user.pk,
                legacy_business_profile_id=profile.pk,
            )
            # `created_at` conserve l'ancienneté du profil (`auto_now_add` l'a écrasée à la création).
            Organization.objects.filter(pk=org.pk).update(created_at=profile.created_at)
            org_id = org.pk
            created += 1
        else:
            reused += 1

        wanted = list(BusinessProfileCategory.objects.filter(business_profile_id=profile.pk)
                      .order_by('created_at', 'pk').values_list('category_id', flat=True))
        known = set(OrganizationCategory.objects.filter(organization_id=org_id).values_list('category_id', flat=True))
        OrganizationCategory.objects.bulk_create([
            OrganizationCategory(organization_id=org_id, category_id=cid) for cid in dict.fromkeys(wanted) if cid not in known
        ])

        if not Membership.objects.filter(organization_id=org_id, user_id=user.pk).exists():
            Membership.objects.create(
                organization_id=org_id, user_id=user.pk, role='OWNER', status='ACTIVE', joined_at=profile.created_at,
            )

        # Pièces : rattachement seulement (statut, motif, décideur, dates et fichier inchangés). Une pièce déjà
        # rattachée à une organisation reste telle quelle (signalée par le pré-vol).
        KycDocument.objects.filter(business_profile_id=profile.pk, organization__isnull=True).update(
            organization_id=org_id, uploaded_by_id=user.pk,
        )

        Mapping.objects.create(user_id=user.pk, organization_id=org_id)
        mapped_users.add(user.pk)

    leftover = BusinessProfile.objects.exclude(user_id__in=Mapping.objects.values('user_id')).count()
    if leftover:
        raise RuntimeError(f"Conversion incomplète : {leftover} profil(s) sans correspondance.")
    logger.info(
        "Conversion des profils : %d organisation(s) créée(s), %d reprise(s), %d déjà convertie(s).",
        created, reused, skipped,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0010_identitysettings_kyb_file_retention_days'),
        ('moderation', '0004_auditlog_context'),
    ]

    operations = [
        migrations.RunPython(convert_profiles, migrations.RunPython.noop),
    ]
