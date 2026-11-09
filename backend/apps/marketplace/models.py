"""Offres de la marketplace (CDC 3.2) : produits et services, galerie, favoris, contacts.

Règles de portage (ADR 0002) : clés UUID (`BaseModel`), `Post` devient `Offer`,
`is_delete` devient `is_deleted`. Les référentiels (catégorie, commune) sont désignés par
UUID (`category_id`, `commune_id`) et lus via `apps.catalog.services` ; seul le vendeur
est une clé étrangère (vers l'utilisateur). La logique métier (cycle de vie, score) est
dans `services.py`.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinLengthValidator, MinValueValidator
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.common.contexts import ALL_CONTEXT_CHOICES
from apps.common.images import sanitize_uploaded_field, validate_image_pixels, validate_image_upload_size
from apps.common.models import BaseModel, SingletonSettingsModel


logger = logging.getLogger(__name__)

# Garde-fou contre les valeurs absurdes (saisie erronée) ; pas une règle commerciale.
MAX_STOCK = 1_000_000


class MarketplaceSettings(SingletonSettingsModel):
    """CDC 3.2 : durée d'expiration d'une offre sans renouvellement, « valeur paramétrable »
    dans le back-office (règle 11). Ligne unique."""

    expiration_days = models.PositiveIntegerField(default=60)
    trash_retention_days = models.PositiveIntegerField(default=30)
    expiring_soon_warning_days = models.PositiveIntegerField(default=3)
    # Fenêtre pendant laquelle un second contact du même expéditeur sur la même offre est refusé
    # (et, côté classement, ne compte pas deux fois dans l'engagement). Minimum 1 heure.
    duplicate_contact_window_hours = models.PositiveIntegerField(
        default=24, validators=[MinValueValidator(1), MaxValueValidator(8760)],
        help_text="Heures (8760 au plus) pendant lesquelles un même expéditeur ne peut contacter deux fois la même annonce.",
    )

    # Révélation du numéro de contact (ADR 0005, C9) : plafonds sur 24 h glissantes, par compte.
    reveal_daily_limit_account = models.PositiveIntegerField(
        default=15, validators=[MinValueValidator(1), MaxValueValidator(1000)],
        help_text="Nombre de numéros qu'un compte peut obtenir en 24 h (1 à 1000).",
    )
    reveal_daily_limit_new_account = models.PositiveIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(1000)],
        help_text="Même plafond pour un compte neuf (1 à 1000).",
    )
    new_account_hours = models.PositiveIntegerField(
        default=24, validators=[MaxValueValidator(720)],
        help_text="Ancienneté (en heures, 0 à 720) en dessous de laquelle un compte est considéré comme neuf.",
    )
    # Abus : un compte qui dépasse son plafond N fois sur D jours est signalé à la modération.
    reveal_abuse_threshold = models.PositiveIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Nombre de JOURS avec dépassement de plafond (1 à 100) qui déclenche un signalement automatique.",
    )
    reveal_abuse_window_days = models.PositiveIntegerField(
        default=7, validators=[MinValueValidator(1), MaxValueValidator(90)],
        help_text="Période (en jours, 1 à 90) sur laquelle les dépassements de plafond sont comptés.",
    )

    # Troc (CDC §8.3, périmètre V1 non confirmé par le client) : désactivé par défaut. Éteint, les
    # propositions d'échange sont refusées et `is_exchangeable` n'est plus ni lu, ni écrit, ni filtré.
    exchange_enabled = models.BooleanField(
        default=False, verbose_name="Troc activé",
        help_text="Active les propositions d'échange (troc) et l'indicateur « échangeable » des annonces.",
    )

    class Meta:
        verbose_name = "Paramètres de la marketplace"
        verbose_name_plural = "Paramètres de la marketplace"

    def __str__(self):
        return "Paramètres de la marketplace"


class Offer(BaseModel):
    OFFER_TYPE_CHOICES = (
        ('PRODUIT', 'Produit Physique'),
        ('SERVICE', 'Prestation de Service'),
    )

    CONDITION_CHOICES = (
        ('NEUF', 'Neuf'),
        ('OCCASION', 'Occasion / Très bon état'),
        ('RECONDITIONNE', 'Reconditionné'),
    )

    CURRENCY_CHOICES = (
        ('USD', 'USD'),
        ('CDF', 'CDF'),
    )

    # CDC 3.2 : cycle de vie. is_active reste le seul indicateur de visibilité effective sur la
    # marketplace (offre masquée par le vendeur, par expiration ou par la modération) ; status
    # ne fait qu'expliquer POURQUOI, côté tableau de bord vendeur.
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_PAUSED = 'PAUSED'
    STATUS_SOLD = 'SOLD'
    STATUS_EXPIRED = 'EXPIRED'
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "En pause"),
        (STATUS_SOLD, "Vendue"),
        (STATUS_EXPIRED, "Expirée"),
    )

    # Contexte vendeur (ADR 0006, A3) : à qui appartient l'offre. `USER` (compte), `PROVIDER` (profil
    # prestataire) ou `ORGANIZATION`. Pas de clé étrangère entre domaines : l'identifiant désigne une ligne
    # d'`identity` lue par ses services. Obligatoire : une offre sans propriétaire est refusée en base.
    seller_context_type = models.CharField(max_length=20, choices=ALL_CONTEXT_CHOICES)
    seller_context_id = models.UUIDField()
    # Trace de l'auteur : l'offre reste à son propriétaire quand l'auteur part (Q-CP7).
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='offers_created',
    )
    # Le vendeur est-il public ? Dénormalisé depuis `identity` (compte actif et sans sanction, profil
    # prestataire actif, organisation active) : recalculé par l'abonné de
    # `identity.seller_context_status_changed` et par la commande `sync_seller_visibility` (ADR 0006, A7).
    seller_is_public = models.BooleanField(default=True, db_index=True)
    # Références par UUID vers le domaine `catalog` (CDC §5.4, pas de clé étrangère entre
    # domaines) ; l'existence est vérifiée par apps.catalog.services.
    category_id = models.UUIDField(db_index=True)
    commune_id = models.UUIDField(db_index=True)

    offer_type = models.CharField(max_length=10, choices=OFFER_TYPE_CHOICES, default='PRODUIT')

    # CDC 3.2 : titre 10-100 caractères, description 20-3000 caractères.
    title = models.CharField(
        max_length=100, validators=[MinLengthValidator(10), MaxLengthValidator(100)],
    )
    description = models.TextField(
        validators=[MinLengthValidator(20), MaxLengthValidator(3000)],
    )
    # Le prix ne peut pas être négatif. 0 reste accepté : le CDC prévoit « Sur devis » (§3.2) sans
    # champ dédié à ce jour ; l'interdire bloquerait ce cas (arbitrage à confirmer avec le client).
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0, message="Le prix ne peut pas être négatif.")],
    )
    # CDC 2.3 : prix en USD ou en CDF, au choix du vendeur.
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')

    # Champs spécifiques aux produits
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, null=True, blank=True)
    stock = models.PositiveIntegerField(
        default=1, help_text="Quantité disponible (si produit)",
        validators=[
            MinValueValidator(0, message="Le stock ne peut pas être négatif."),
            MaxValueValidator(MAX_STOCK, message=f"Le stock ne peut pas dépasser {MAX_STOCK} unités."),
        ],
    )

    is_price_negotiable = models.BooleanField(default=True, verbose_name="Prix discutable")
    is_exchangeable = models.BooleanField(default=True, verbose_name="Echangeable")

    # Corbeille (CDC 3.10)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Les images sont ré-encodées sans métadonnées (EXIF/GPS) à l'enregistrement, même
    # si le fichier envoyé est déjà au format WebP (apps/common/images.py).
    main_image = models.ImageField(
        upload_to='offers/', validators=[validate_image_upload_size, validate_image_pixels],
    )

    # Compteurs d'engagement (CDC 3.8). Les vues uniques et leurs agrégats journaliers
    # sont dans le domaine `visibility` ; ces totaux servent au tri et à la formule.
    views_count = models.PositiveIntegerField(default=0)
    # `likes_count` = nombre de favoris (renommage renvoyé à L0-11).
    likes_count = models.PositiveIntegerField(default=0)
    # Nombre de contacts comptés (`ContactEvent.is_counted`), recalculé depuis la source (ADR 0004, 6.3).
    contacts_count = models.PositiveIntegerField(default=0)
    shares_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # Masquage prononcé par la modération (sanction MASQUAGE_ANNONCE). État explicite, distinct
    # de `is_active` et de `status` : le vendeur ne peut ni reprendre ni renouveler l'offre
    # (seule la levée de la sanction l'efface).
    is_hidden_by_moderation = models.BooleanField(default=False)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    # CDC 3.2 : expiration après N jours sans renouvellement (cf. MarketplaceSettings).
    expires_at = models.DateTimeField(null=True, blank=True)
    # Évite de renotifier chaque jour la même échéance (CDC 3.6 : « Annonce bientôt expirée »).
    expiring_soon_notified = models.BooleanField(default=False)

    # Score organique stocké = E x R (engagement x récence) ; la proximité D est appliquée à la
    # lecture et P vaut 1 (filtre strict). Aucun terme de note ni de promotion (règles 4 et 5).
    visibility_score = models.FloatField(default=0.0)
    last_score_update = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'is_deleted', '-visibility_score'], name='offer_public_ranking'),
            models.Index(
                fields=['seller_context_type', 'seller_context_id', 'is_deleted'], name='offer_seller_ctx_deleted',
            ),
        ]

    def save(self, *args, **kwargs):
        self.main_image = sanitize_uploaded_field(self.main_image)
        if self.expires_at is None:
            expiration_days = MarketplaceSettings.get_solo().expiration_days
            self.expires_at = timezone.now() + timedelta(days=expiration_days)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.offer_type}] {self.title}"


class OfferImage(BaseModel):
    """CDC 3.2 : une offre porte de 1 à 8 photos (main_image compte pour la première ; ce
    modèle porte les photos supplémentaires de la galerie)."""

    MAX_IMAGES_PER_OFFER = 8

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(
        upload_to='offers/gallery/', validators=[validate_image_upload_size, validate_image_pixels],
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'created_at']

    def save(self, *args, **kwargs):
        self.image = sanitize_uploaded_field(self.image)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Photo de {self.offer_id} (#{self.order})"


def _delete_file_after_commit(stored_file, label):
    """Le fichier disparaît avec sa ligne (suppression directe, en cascade ou purge de contexte, T9-3), une fois la
    transaction validée : un retour arrière ne perd jamais de fichier. Un échec disque est journalisé, jamais remonté."""
    if not stored_file or not stored_file.name:
        return

    def remove():
        try:
            stored_file.delete(save=False)
        except OSError:
            logger.exception("Suppression du fichier de %s impossible.", label)

    transaction.on_commit(remove)


@receiver(post_delete, sender=Offer, dispatch_uid='marketplace.delete_offer_main_image')
def delete_offer_main_image(sender, instance, **kwargs):
    _delete_file_after_commit(instance.main_image, f"l'offre {instance.pk}")


@receiver(post_delete, sender=OfferImage, dispatch_uid='marketplace.delete_offer_gallery_image')
def delete_offer_gallery_image(sender, instance, **kwargs):
    _delete_file_after_commit(instance.image, f"la photo {instance.pk}")


class Favorite(BaseModel):
    """CDC 3.2 : liste personnelle des offres favorites d'un utilisateur."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='favorited_by')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'offer'], name='uniq_favorite_user_offer')]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user_id} ♥ {self.offer_id}"


class ContactEvent(BaseModel):
    """Prise de contact d'un utilisateur à propos d'une offre (CDC §11.1 ; ex-ContactRequest).
    Sert l'historique des contacts, la preuve qui ouvre le droit d'avis (CDC 3.4, lue par
    `get_review_contact`) et l'agrégat de contacts du tableau de bord."""

    CHANNEL_MESSAGE = 'MESSAGE'
    CHANNEL_CALL = 'CALL'
    CHANNEL_WHATSAPP = 'WHATSAPP'
    CHANNEL_CHOICES = (
        (CHANNEL_MESSAGE, "Message"),
        (CHANNEL_CALL, "Appel"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
    )

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='contact_events')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_contacts')
    # Obligatoire pour MESSAGE (contrôlé au serializer) ; vide pour CALL et WHATSAPP (ADR 0005, 3.3).
    message = models.TextField(blank=True, default='', validators=[MaxLengthValidator(2000)])
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default=CHANNEL_MESSAGE)
    # Ce contact entre dans l'engagement (une fois par expéditeur, offre et fenêtre, tous canaux
    # confondus) ; la logique de marquage est portée par le classement (ADR 0004, 6.3).
    is_counted = models.BooleanField(default=True)
    # Preuve que le contact a réellement abouti (ADR 0005, C10) : message posé dans la conversation,
    # ou numéro remis pour CALL/WHATSAPP. Nul tant que la preuve manque.
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['offer', 'created_at'], name='contact_offer_created'),
            models.Index(fields=['sender', 'channel', 'created_at'], name='contact_sender_channel_created'),
        ]

    def __str__(self):
        return f"Contact de {self.sender_id} pour {self.offer_id}"


class ExchangeProposal(BaseModel):
    """Proposition d'échange. Reste derrière l'interrupteur de L0-14."""

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='exchange_proposals')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_exchanges')
    message = models.TextField(validators=[MaxLengthValidator(2000)])

    def __str__(self):
        return f"Proposition d'échange de {self.sender_id} pour {self.offer_id}"
