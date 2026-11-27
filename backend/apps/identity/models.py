import logging
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.files.storage import FileSystemStorage
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.db.models import F
from django.conf import settings
from django.utils import timezone

from apps.common.images import sanitize_uploaded_field, validate_image_pixels, validate_image_upload_size
from apps.common.models import BaseModel, SingletonSettingsModel

from .capabilities import (
    ROLE_ADMIN, ROLE_ANALYST, ROLE_CHOICES, ROLE_EDITOR, ROLE_MEMBER, ROLE_OWNER, SCOPE_CHOICES, SCOPE_ORGANIZATION,
)
from .kyc_files import kyc_upload_to

logger = logging.getLogger(__name__)

# CDC 2.3 : numéros togolais... congolais au format +243 suivi de 9 chiffres.
phone_validator = RegexValidator(
    regex=r'^\+243[0-9]{9}\Z',  # \Z et [0-9] : ni saut de ligne final ni chiffres Unicode
    message="Le numéro doit être au format +243 suivi de 9 chiffres.",
)

# CDC 4.2 / 5.8 : les pièces KYC sont stockées dans un espace privé, jamais servi
# par le MEDIA_URL public. Ce dossier est en dehors de MEDIA_ROOT.
#
# Sous-classe (plutôt qu'une instance FileSystemStorage(location=...) directe) pour
# que la migration ne fige pas un chemin absolu propre à une machine : deconstruct()
# ne sérialise que "KycPrivateStorage()", et location est recalculé à chaque exécution
# depuis settings.KYC_PRIVATE_ROOT (donc correct en dev Windows comme dans le conteneur).
class KycPrivateStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', str(settings.KYC_PRIVATE_ROOT))
        kwargs.setdefault('base_url', None)
        super().__init__(*args, **kwargs)


kyc_storage = KycPrivateStorage()


def normalize_email(value):
    """Forme canonique d'un e-mail : espaces retirés et minuscules (partie locale comprise).
    Garantit qu'un e-mail est unique sans tenir compte de la casse, sur SQLite comme sur MySQL."""
    if not value:
        return None
    return value.strip().lower() or None


class UserManager(BaseUserManager):
    def create_user(self, email=None, phone=None, password=None, **extra_fields):
        email = normalize_email(email)
        if not email and not phone:
            raise ValueError("Un email ou un numéro de téléphone est obligatoire")
        user = self.model(email=email, phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email=email, password=password, **extra_fields)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    # CDC 3.1 : inscription par téléphone OU par e-mail. Les deux sont donc
    # facultatifs individuellement (contrainte "au moins un des deux" gérée par
    # UserManager.create_user), mais chacun reste unique quand il est renseigné.
    # unique=True + null=True est portable SQLite/MySQL (2.6) : NULL n'est jamais
    # comparé égal à NULL par un index unique, donc plusieurs comptes sans email
    # ou sans téléphone cohabitent sans conflit.
    email = models.EmailField(unique=True, null=True, blank=True, default=None)
    phone = models.CharField(
        max_length=20, unique=True, null=True, blank=True, default=None,
        validators=[phone_validator],
    )
    phone_verified = models.BooleanField(default=False)

    photo = models.ImageField(
        upload_to='profile_photos/', null=True, blank=True,
        validators=[validate_image_upload_size, validate_image_pixels],
    )
    full_name = models.CharField(max_length=255)

    # Localisation : références par UUID vers le domaine `catalog` (CDC §5.4, pas de
    # clé étrangère entre domaines). L'existence est vérifiée par apps.catalog.services
    # (voir UserSerializer) ; null permet la création avant d'avoir configuré les villes.
    city_id = models.UUIDField(null=True, blank=True, db_index=True)
    commune_id = models.UUIDField(null=True, blank=True, db_index=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_groups', # Nom unique
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_permissions', # Nom unique
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        # Photo ré-encodée (sans EXIF/GPS, taille plafonnée) avant stockage.
        self.photo = sanitize_uploaded_field(self.photo)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email or self.phone or f"Utilisateur #{self.pk}"


class OtpCode(BaseModel):
    """CDC 3.1 : OTP SMS à 6 chiffres, valable 10 minutes, 3 tentatives maximum."""

    PURPOSE_REGISTER = 'REGISTER'
    PURPOSE_LOGIN = 'LOGIN'
    PURPOSE_PASSWORD_RESET = 'PASSWORD_RESET'
    PURPOSE_CONTACT_VERIFY = 'CONTACT_VERIFY'
    PURPOSE_CHOICES = (
        (PURPOSE_REGISTER, "Inscription"),
        (PURPOSE_LOGIN, "Connexion"),
        (PURPOSE_PASSWORD_RESET, "Réinitialisation du mot de passe"),
        (PURPOSE_CONTACT_VERIFY, "Vérification du numéro de contact"),
    )

    VALIDITY_MINUTES = 10
    MAX_ATTEMPTS = 3
    CODE_LENGTH = 6

    phone = models.CharField(max_length=20, validators=[phone_validator])
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    code_hash = models.CharField(max_length=128)
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=['phone', 'purpose', 'is_used'])]
        ordering = ['-created_at']

    @classmethod
    def issue(cls, phone, purpose):
        """Génère un nouveau code, invalide les codes précédents non utilisés
        pour ce couple (phone, purpose), et retourne (instance, code_en_clair)."""
        cls.objects.filter(phone=phone, purpose=purpose, is_used=False).update(is_used=True)
        code = ''.join(secrets.choice('0123456789') for _ in range(cls.CODE_LENGTH))
        instance = cls.objects.create(
            phone=phone,
            purpose=purpose,
            code_hash=make_password(code),
            expires_at=timezone.now() + timedelta(minutes=cls.VALIDITY_MINUTES),
        )
        return instance, code

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def verify(self, raw_code):
        """Vérifie le code fourni. Retourne True seulement si le code est valide, non
        expiré, non utilisé et sous la limite de tentatives.

        Le décompte des tentatives et l'usage unique sont atomiques (UPDATE conditionnel
        en base) : deux requêtes simultanées ne peuvent ni dépasser la limite de
        tentatives ni consommer deux fois le même code."""
        if self.is_used or self.is_expired():
            return False
        claimed = OtpCode.objects.filter(
            pk=self.pk, is_used=False, attempts__lt=self.MAX_ATTEMPTS,
        ).update(attempts=F('attempts') + 1)
        if not claimed:
            self.refresh_from_db(fields=['attempts', 'is_used'])
            return False
        self.refresh_from_db(fields=['attempts'])
        if not check_password(raw_code, self.code_hash):
            return False
        used = OtpCode.objects.filter(pk=self.pk, is_used=False).update(is_used=True)
        if used:
            self.is_used = True
        return bool(used)

    def __str__(self):
        return f"OTP {self.purpose} pour {self.phone}"


class KycDocument(BaseModel):
    """CDC 3.1 / 3.11 : pièces justificatives KYC d'une organisation,
    en file d'attente de validation par la modération."""

    DOC_RCCM = 'RCCM'
    DOC_ID_NATIONALE = 'ID_NATIONALE'
    DOC_PIECE_GERANT = 'PIECE_GERANT'
    DOC_ARRETE_ONG = 'ARRETE_ONG'
    DOC_TYPE_CHOICES = (
        (DOC_RCCM, "RCCM"),
        (DOC_ID_NATIONALE, "Identification nationale"),
        (DOC_PIECE_GERANT, "Pièce d'identité du gérant"),
        (DOC_ARRETE_ONG, "Arrêté d'enregistrement de l'ONG"),
    )

    REASON_MAX_LENGTH = 500

    STATUS_EN_ATTENTE = 'EN_ATTENTE'
    STATUS_VALIDE = 'VALIDE'
    STATUS_REFUSE = 'REFUSE'
    STATUS_CHOICES = (
        (STATUS_EN_ATTENTE, "En attente"),
        (STATUS_VALIDE, "Validé"),
        (STATUS_REFUSE, "Refusé"),
    )

    # ADR 0006, section 4.4 : pièce rattachée à une organisation. `uploaded_by` : trace de l'auteur du dépôt.
    organization = models.ForeignKey('Organization', on_delete=models.CASCADE, related_name='kyc_documents')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='kyc_uploads',
    )
    document_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES)
    file = models.FileField(upload_to=kyc_upload_to, storage=kyc_storage)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_EN_ATTENTE)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kyc_reviews',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        permissions = [('review_kycdocument', "Peut examiner, décider et télécharger les pièces KYC")]

    def __str__(self):
        return f"{self.get_document_type_display()} — organisation {self.organization_id} ({self.status})"


@receiver(post_delete, sender=KycDocument)
def delete_kyc_file_with_row(sender, instance, **kwargs):
    """Le fichier privé disparaît avec sa ligne (suppression directe ou en cascade), une fois la transaction
    validée : un retour arrière ne perd jamais de fichier. Un échec disque est journalisé, jamais remonté."""
    stored_file = instance.file
    if not stored_file or not stored_file.name:
        return

    def remove():
        try:
            stored_file.delete(save=False)
        except OSError:
            logger.exception("Suppression du fichier de la pièce %s impossible.", instance.pk)

    transaction.on_commit(remove)


# Version courante du texte de consentement au contact (ADR 0005, C4). Provisoire (LEG-PRV-03).
CONTACT_CONSENT_TEXT_VERSION = '2026-10-v1'


class ContactPoint(BaseModel):
    """Numéro de contact d'un compte, distinct du numéro de connexion (ADR 0005, C1 et C3).

    Donnée personnelle : jamais exposée par l'API de liste ni par les événements ; seul
    `identity.services.get_contact_endpoint` le lit, pour un canal consenti. Pas d'unicité sur le
    numéro (un numéro d'entreprise peut être partagé entre comptes)."""

    # Exactement un des deux est renseigné (garanti par le service, ADR 0006 §4.4) : un numéro
    # d'organisation n'est jamais le numéro d'un membre.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contact_point', null=True, blank=True,
    )
    organization = models.OneToOneField(
        'Organization', on_delete=models.CASCADE, related_name='contact_point', null=True, blank=True,
    )
    phone = models.CharField(max_length=20, validators=[phone_validator])
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # Exactement un propriétaire : un compte ou une organisation (ADR 0006 §4.4).
            models.CheckConstraint(
                check=(models.Q(user__isnull=False, organization__isnull=True)
                       | models.Q(user__isnull=True, organization__isnull=False)),
                name='contact_point_exactly_one_owner',
            ),
        ]

    def __str__(self):
        # Jamais le numéro dans les représentations (logs, admin).
        return f"Numéro de contact de {self.user_id or self.organization_id}"


class ContactConsent(BaseModel):
    """Accord d'un compte pour un canal de contact (ADR 0005, C2 et C4). Unique par compte et canal ;
    l'unicité est inconditionnelle (portable MySQL). Les lignes manquantes valent « désactivé »
    (sauf MESSAGE), créées à la demande par le service."""

    CHANNEL_MESSAGE = 'MESSAGE'
    CHANNEL_CALL = 'CALL'
    CHANNEL_WHATSAPP = 'WHATSAPP'
    CHANNEL_CHOICES = (
        (CHANNEL_MESSAGE, "Message"),
        (CHANNEL_CALL, "Appel"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
    )
    REVOKED_USER = 'user'
    REVOKED_PHONE_CHANGED = 'phone_changed'
    REVOKED_MODERATION = 'moderation'
    REVOKED_REASON_CHOICES = (
        (REVOKED_USER, "Retrait par l'utilisateur"),
        (REVOKED_PHONE_CHANGED, "Numéro modifié"),
        (REVOKED_MODERATION, "Modération"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contact_consents', null=True, blank=True,
    )
    organization = models.ForeignKey(
        'Organization', on_delete=models.CASCADE, related_name='contact_consents', null=True, blank=True,
    )
    # Pour une organisation : le propriétaire ou l'administrateur qui a consenti (ADR 0006 §4.4).
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    is_granted = models.BooleanField(default=False)
    text_version = models.CharField(max_length=20, blank=True, default='')
    granted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # Preuve d'accord : 4 derniers chiffres du numéro couvert (le numéro complet reste dans ContactPoint).
    phone_last4 = models.CharField(max_length=4, blank=True, default='')
    revoked_reason = models.CharField(max_length=20, blank=True, default='', choices=REVOKED_REASON_CHOICES)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'channel'], name='contact_consent_user_channel_uniq'),
            # Les valeurs nulles ne se comparent pas : portable SQLite et MySQL, inconditionnelle.
            models.UniqueConstraint(fields=['organization', 'channel'], name='contact_consent_org_channel_uniq'),
            models.CheckConstraint(
                check=(models.Q(user__isnull=False, organization__isnull=True)
                       | models.Q(user__isnull=True, organization__isnull=False)),
                name='contact_consent_exactly_one_owner',
            ),
        ]

    def __str__(self):
        return f"Consentement {self.channel} de {self.user_id or self.organization_id}"


# --- Organisations, appartenances, prestataire, réglages (ADR 0006, sections 4.2 et 4.3) -------------

ORG_TYPE_ENTREPRISE = 'ENTREPRISE'
ORG_TYPE_BOUTIQUE = 'BOUTIQUE'
ORG_TYPE_ONG = 'ONG'
ORG_TYPE_EVENEMENTS = 'ORGANISATEUR_EVENEMENTS'
ORG_TYPE_CHOICES = (
    (ORG_TYPE_ENTREPRISE, "Entreprise"),
    (ORG_TYPE_BOUTIQUE, "Boutique"),
    (ORG_TYPE_ONG, "ONG"),
    (ORG_TYPE_EVENEMENTS, "Organisateur d'événements"),
)
ORG_TYPES = tuple(value for value, _ in ORG_TYPE_CHOICES)


class IdentitySettings(SingletonSettingsModel):
    """Réglages d'identité modifiables dans le back-office (règle 11). Ligne unique."""

    # Anti-abus de création (ADR 0010 D8, Q22) : seuils INTERNES, jamais renvoyés par l'API ni affichés. Valeurs
    # provisoires, à confirmer (QG-1).
    max_memberships_hard_limit = models.PositiveIntegerField(
        default=200, validators=[MinValueValidator(50), MaxValueValidator(1000)],
        help_text="Seuil de sécurité interne : ne jamais le communiquer comme une limite. Plafond technique "
                  "d'appartenances actives par compte (50 à 1 000) ; au-delà, refus neutre « examen du compte ».",
    )
    org_creation_review_window_days = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Seuil de sécurité interne : ne jamais le communiquer comme une limite. Fenêtre glissante, en "
                  "jours, du comptage des organisations créées par un même compte (1 à 365).",
    )
    org_creation_review_threshold = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(2), MaxValueValidator(100)],
        help_text="Seuil de sécurité interne : ne jamais le communiquer comme une limite. Rang de création dans la "
                  "fenêtre à partir duquel une nouvelle organisation est retenue en revue par l'équipe (2 à 100).",
    )
    org_creation_review_max_pending = models.PositiveSmallIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Seuil de sécurité interne : ne jamais le communiquer comme une limite. Nombre d'organisations "
                  "d'un même créateur pouvant être en revue en même temps (1 à 50) ; au-delà, refus neutre.",
    )
    max_categories_per_context = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Nombre maximal de catégories d'une organisation ou d'un prestataire (1 à 20).",
    )
    org_phone_channels_enabled = models.BooleanField(
        default=False,
        help_text="Autorise les canaux Appel et WhatsApp pour une organisation (fermé tant que le client n'a pas "
                  "validé le consentement des organisations).",
    )

    kyb_file_retention_days = models.PositiveIntegerField(
        default=0, validators=[MaxValueValidator(3650)],
        help_text="Jours de conservation du FICHIER d'une pièce d'organisation après sa décision ; 0 = illimité "
                  "(durée à fixer par le client, LEG-PRV). La ligne et le résultat de la décision sont conservés.",
    )

    # Invitations d'équipe (ADR 0008, 4.2). Valeurs provisoires, à confirmer par le client.
    invitation_ttl_days = models.PositiveSmallIntegerField(
        default=7, validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Durée de validité d'un lien d'invitation, en jours (1 à 30). Valeur provisoire, à confirmer.",
    )
    max_pending_invitations = models.PositiveSmallIntegerField(
        default=20, validators=[MinValueValidator(1), MaxValueValidator(200)],
        help_text="Nombre maximal d'invitations en attente par organisation (1 à 200). Valeur provisoire, à confirmer.",
    )
    invitation_history_days = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Jours de conservation d'une invitation close (acceptée, refusée, révoquée, expirée) avant purge "
                  "(1 à 365). Valeur provisoire, à confirmer.",
    )
    # Invitations v2 (ADR 0010 §4.7). Délai laissé à l'émetteur ou à un administrateur principal pour confirmer une
    # invitation Administrateur acceptée ; l'échéance est renvoyée, jamais la règle.
    admin_invitation_confirmation_hours = models.PositiveSmallIntegerField(
        default=72, validators=[MinValueValidator(1), MaxValueValidator(336)],
        help_text="Délai de confirmation d'une invitation Administrateur acceptée, en heures (1 à 336). Valeur "
                  "provisoire, à confirmer.",
    )

    class Meta:
        verbose_name = "Paramètres d'identité"
        verbose_name_plural = "Paramètres d'identité"

    def save(self, *args, **kwargs):
        # Fermer l'interrupteur des canaux numéro des organisations retire leurs consentements (ADR 0006, 19.6).
        with transaction.atomic():
            was_open = type(self).objects.filter(pk=self.pk, org_phone_channels_enabled=True).exists()
            super().save(*args, **kwargs)
            if was_open and not self.org_phone_channels_enabled:
                from .services import revoke_organization_phone_consents

                revoke_organization_phone_consents()

    def __str__(self):
        return "Paramètres d'identité"


class Organization(BaseModel):
    """Entreprise, boutique, ONG ou organisateur d'événements (ADR 0006, 4.2). Le nom n'est pas
    unique (A12). Aucune logique métier ici : elle vit dans les services."""

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_SUSPENDED = 'SUSPENDED'
    STATUS_ARCHIVED = 'ARCHIVED'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspendue"),
        (STATUS_ARCHIVED, "Archivée"),
    )
    CREATION_REVIEW_NONE = 'NONE'
    CREATION_REVIEW_PENDING = 'PENDING'
    CREATION_REVIEW_CLEARED = 'CLEARED'
    CREATION_REVIEW_CHOICES = (
        (CREATION_REVIEW_NONE, "Aucune"),
        (CREATION_REVIEW_PENDING, "En revue"),
        (CREATION_REVIEW_CLEARED, "Levée"),
    )

    name = models.CharField(max_length=255)
    org_type = models.CharField(max_length=30, choices=ORG_TYPE_CHOICES)
    description = models.TextField(blank=True, validators=[MaxLengthValidator(2000)])
    logo = models.ImageField(
        upload_to='organization_logos/', null=True, blank=True,
        validators=[validate_image_upload_size, validate_image_pixels],
    )
    # Non public (règle 10).
    nif = models.CharField(max_length=50, blank=True)
    # Adresse générale seulement : références par UUID vers `catalog`.
    city_id = models.UUIDField(null=True, blank=True, db_index=True)
    commune_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    # Revue de création (ADR 0010 D8) : état propre, indépendant du statut (règle 8) ; PENDING = absente de l'annuaire
    # et des pages publiques jusqu'à la levée par le personnel. Jamais exposé avec sa cause (seuil caché, Q22).
    creation_review_status = models.CharField(
        max_length=10, choices=CREATION_REVIEW_CHOICES, default=CREATION_REVIEW_NONE,
    )
    # Motif normalisé, jamais de texte libre.
    suspension_reason = models.CharField(max_length=30, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    # Idempotence de la migration de données (T9) ; retiré avec la table de correspondance. Identifiant de l'ancien
    # profil : pseudonymisé, conservation à fixer (LEG-PRV).
    legacy_business_profile_id = models.UUIDField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'org_type'], name='org_status_type'),
            models.Index(fields=['name'], name='org_name'),
            models.Index(fields=['creation_review_status'], name='org_creation_review'),
        ]
        permissions = [
            ('suspend_organization', "Peut suspendre et réactiver une organisation"),
            ('review_organization_creation', "Peut lever la revue de création d'une organisation"),
        ]

    def save(self, *args, **kwargs):
        # Logo ré-encodé (sans EXIF/GPS, taille plafonnée) avant stockage.
        self.logo = sanitize_uploaded_field(self.logo)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OrganizationCategory(BaseModel):
    """Table de liaison interne : catégories d'une organisation, par UUID (domaine `catalog`)."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='category_links')
    category_id = models.UUIDField(db_index=True)

    class Meta:
        unique_together = ('organization', 'category_id')


class Membership(BaseModel):
    """Appartenance d'un compte à une organisation, avec un rôle dans un périmètre (ADR 0010 D3). Une seule ligne
    par couple (organisation, compte) : un retour réactive la même ligne (R12). La règle « au moins un
    administrateur principal » n'est pas en base : elle est garantie par le service, sous verrou. En base : un
    administrateur principal couvre toujours toute l'organisation, et `scope_id` est nul si et seulement si le
    périmètre est l'organisation entière."""

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_REVOKED = 'REVOKED'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Actif"),
        (STATUS_REVOKED, "Révoqué"),
    )
    END_REMOVED = 'removed'
    END_LEFT = 'left'
    END_REASON_CHOICES = (
        (END_REMOVED, "Retiré"),
        (END_LEFT, "Parti"),
    )

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    # Périmètre (ADR 0010 §4.2) : `ORGANIZATION` seul accepté par les services en V1 ; `scope_id` désigne une ville
    # (`catalog`, par UUID, sans clé étrangère) ou une future unité. Non indexé : jamais filtré en V1.
    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_ORGANIZATION)
    scope_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    end_reason = models.CharField(max_length=12, choices=END_REASON_CHOICES, blank=True, default='')
    joined_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    ended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['organization', 'user'], name='membership_org_user_uniq'),
            models.CheckConstraint(
                check=~(models.Q(role=ROLE_OWNER) & ~models.Q(scope_type=SCOPE_ORGANIZATION)),
                name='membership_owner_org_scope',
            ),
            models.CheckConstraint(
                check=(
                    models.Q(scope_type=SCOPE_ORGANIZATION, scope_id__isnull=True)
                    | (~models.Q(scope_type=SCOPE_ORGANIZATION) & models.Q(scope_id__isnull=False))
                ),
                name='membership_scope_consistent',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'status'], name='membership_user_status'),
            models.Index(fields=['organization', 'role', 'status'], name='membership_org_role_status'),
        ]

    def __str__(self):
        return f"Appartenance {self.role} ({self.status})"


# Rôles qu'une invitation peut porter (ADR 0010 D4, amende ADR 0008 §3.2), chacun seulement si l'émetteur peut le
# déléguer (`can_delegate`). `OWNER` jamais : refusé en service et interdit en base (`orginv_role_not_owner`).
# Modifier ces listes ne demande aucune migration.
INVITABLE_ROLES = (ROLE_ADMIN, ROLE_EDITOR, ROLE_ANALYST, ROLE_MEMBER)
# Rôles dont l'acceptation attend la confirmation de l'émetteur ou d'un administrateur principal (ADR 0010 D4, U2) :
# aucune appartenance, donc aucun droit, avant cette confirmation.
CONFIRMATION_REQUIRED_ROLES = (ROLE_ADMIN,)


class OrganizationInvitation(BaseModel):
    """Invitation à rejoindre une organisation, par lien à usage unique (ADR 0008, 4.1). Le jeton n'est jamais
    stocké : seule son empreinte SHA-256. Aucune unicité conditionnelle : le plafond d'invitations en attente est
    garanti en service, sous verrou. L'étiquette est vidée dès que l'invitation quitte `PENDING` (règle 10)."""

    STATUS_PENDING = 'PENDING'
    STATUS_AWAITING_CONFIRMATION = 'AWAITING_CONFIRMATION'
    STATUS_ACCEPTED = 'ACCEPTED'
    STATUS_DECLINED = 'DECLINED'
    STATUS_REVOKED = 'REVOKED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_EXPIRED = 'EXPIRED'
    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente"),
        (STATUS_AWAITING_CONFIRMATION, "En attente de confirmation"),
        (STATUS_ACCEPTED, "Acceptée"),
        (STATUS_DECLINED, "Refusée"),
        (STATUS_REVOKED, "Révoquée"),
        (STATUS_REJECTED, "Rejetée"),
        (STATUS_EXPIRED, "Expirée"),
    )
    # États non terminaux (ADR 0010 §5.1) : tous les autres sont définitifs.
    OPEN_STATUSES = (STATUS_PENDING, STATUS_AWAITING_CONFIRMATION)

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    # Périmètre proposé (ADR 0010 §4.3), mêmes règles que `Membership`.
    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_ORGANIZATION)
    scope_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING)
    token_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=60, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    expires_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    # Confirmation d'une invitation Administrateur (ADR 0010 §4.3) : personne qui a accepté (aucune appartenance tant
    # que la confirmation n'est pas donnée), échéance de la confirmation, et confirmateur ou auteur du rejet.
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    confirmation_expires_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    # Code de rattachement (ADR 0010 QG-2, décision S3) : six chiffres montrés à la seule personne qui a accepté,
    # ressaisis par le confirmateur. Seule l'empreinte HMAC est stockée (comme le jeton) ; compteur des codes faux.
    confirmation_code_hash = models.CharField(max_length=64, blank=True, default='')
    confirmation_code_failures = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(check=~models.Q(role=ROLE_OWNER), name='orginv_role_not_owner'),
            models.CheckConstraint(
                check=(
                    models.Q(scope_type=SCOPE_ORGANIZATION, scope_id__isnull=True)
                    | (~models.Q(scope_type=SCOPE_ORGANIZATION) & models.Q(scope_id__isnull=False))
                ),
                name='orginv_scope_consistent',
            ),
        ]
        indexes = [
            models.Index(fields=['organization', 'status'], name='orginv_org_status'),
            models.Index(fields=['status', 'expires_at'], name='orginv_status_expires'),
            models.Index(fields=['created_by', 'status'], name='orginv_created_by'),
            models.Index(fields=['accepted_by', 'status'], name='orginv_accepted_by'),
        ]

    def __str__(self):
        return f"Invitation {self.role} ({self.status})"


class ProviderProfile(BaseModel):
    """Contexte prestataire individuel : un seul par compte (ADR 0006, 4.3). Photo publique : celle du compte."""

    STATUS_ACTIVE = 'ACTIVE'
    STATUS_ARCHIVED = 'ARCHIVED'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Actif"),
        (STATUS_ARCHIVED, "Archivé"),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='provider_profile')
    display_name = models.CharField(max_length=255)
    bio = models.TextField(blank=True, validators=[MaxLengthValidator(2000)])
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    archived_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.display_name


class ProviderProfileCategory(BaseModel):
    """Table de liaison interne : catégories d'un prestataire, par UUID (domaine `catalog`)."""

    provider = models.ForeignKey(ProviderProfile, on_delete=models.CASCADE, related_name='category_links')
    category_id = models.UUIDField(db_index=True)

    class Meta:
        unique_together = ('provider', 'category_id')


class OrganizationDocumentRequirement(BaseModel):
    """Pièces exigées par type d'organisation (règle 11, éditées dans l'admin). Valeurs initiales
    provisoires posées par la migration 0007 (Q-CLI2)."""

    org_type = models.CharField(max_length=30, choices=ORG_TYPE_CHOICES)
    document_type = models.CharField(max_length=20, choices=KycDocument.DOC_TYPE_CHOICES)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['org_type', 'position']
        constraints = [
            models.UniqueConstraint(fields=['org_type', 'document_type'], name='org_doc_requirement_uniq'),
        ]

    def __str__(self):
        return f"{self.org_type} : {self.document_type}"


class LegacyAccountMapping(BaseModel):
    """Table de correspondance ancien compte -> organisation (migration T9, ADR 0006 A11). Deux UUID : donnée
    PSEUDONYMISÉE (elle relie un compte à une organisation), pas anonyme ; durée de conservation à fixer (LEG-PRV).
    À retirer après la mise à jour des bases de développement."""

    user_id = models.UUIDField(unique=True)
    organization_id = models.UUIDField()
