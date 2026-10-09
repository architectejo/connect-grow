"""Avis après contact (CDC 3.4, ADR 0004).

Un avis note **une offre** (note d'offre) et **son vendeur** (note vendeur) ; la preuve qui ouvre
le droit d'avis est une prise de contact (`contact_event_id`). Aucun score agrégé n'est stocké :
les moyennes sont calculées à la lecture (règle 4, pas de score de confiance).

L'offre et le contact sont désignés par leur UUID, sans clé étrangère (CDC §5.4) : un avis survit
à la purge de l'offre. Seul l'auteur est une clé étrangère (vers l'utilisateur).
"""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinLengthValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.contexts import CONTEXT_CHOICES, CONTEXT_USER
from apps.common.models import BaseModel, SingletonSettingsModel

CONTENT_MIN_LENGTH = 10
CONTENT_MAX_LENGTH = 500


class ReviewSettings(SingletonSettingsModel):
    """Règles des avis, modifiables dans le back-office (règle 11). Ligne unique.
    Les limites de révélation de numéro relèvent du domaine `marketplace` (L0-10a)."""

    min_reviews_to_display = models.PositiveIntegerField(
        default=3, validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Nombre d'avis à partir duquel une moyenne est affichée.",
    )
    daily_review_limit = models.PositiveIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Avis maximum par utilisateur et par jour.",
    )
    edit_window_hours = models.PositiveIntegerField(
        default=48, validators=[MinValueValidator(1), MaxValueValidator(8760)],
        help_text="Heures pendant lesquelles un avis reste modifiable (8760 au plus).",
    )
    delay_after_contact_hours = models.PositiveIntegerField(
        default=24, validators=[MaxValueValidator(168)],
        help_text="Heures à attendre entre le contact et l'avis (0 : aucun délai, 168 au plus).",
    )
    crossed_reviews_window_days = models.PositiveIntegerField(
        default=30, validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Fenêtre de détection des avis croisés, en jours (365 au plus).",
    )
    crossed_reviews_threshold = models.PositiveIntegerField(
        default=3, validators=[MinValueValidator(2), MaxValueValidator(50)],
        help_text="Nombre d'avis entre les deux mêmes comptes qui déclenche un signalement automatique.",
    )

    class Meta:
        verbose_name = "Paramètres des avis"
        verbose_name_plural = "Paramètres des avis"

    def __str__(self):
        return "Paramètres des avis"


def _validate_content_length(value):
    """10 à 500 caractères après suppression des espaces de bord."""
    length = len((value or '').strip())
    if length < CONTENT_MIN_LENGTH or length > CONTENT_MAX_LENGTH:
        raise ValidationError(
            f"L'avis doit contenir entre {CONTENT_MIN_LENGTH} et {CONTENT_MAX_LENGTH} caractères."
        )


class Review(BaseModel):
    # L'auteur de l'avis (le visiteur qui a contacté le vendeur).
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews_written')
    # Référence sans clé étrangère : l'avis survit à la purge de l'offre (CDC 3.10).
    offer_id = models.UUIDField(db_index=True)
    # Contexte vendeur noté (CDC 3.4 : jamais fusionné avec un autre rôle). Un `User.id` tant que
    # les organisations n'existent pas (L0-09).
    seller_context_type = models.CharField(max_length=20, choices=CONTEXT_CHOICES, default=CONTEXT_USER)
    seller_context_id = models.UUIDField()

    # Preuve de contact (instantané, pour la modération) ; pas de clé étrangère vers `marketplace`.
    contact_event_id = models.UUIDField()
    contact_channel = models.CharField(max_length=10)
    contact_recorded_at = models.DateTimeField()

    offer_rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    seller_rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    content = models.TextField(validators=[_validate_content_length])

    # Réponse publique du vendeur concerné.
    reply_content = models.TextField(null=True, blank=True, validators=[MaxLengthValidator(CONTENT_MAX_LENGTH)])
    reply_at = models.DateTimeField(null=True, blank=True)

    # Avis masqué par la modération : exclu de toutes les moyennes et listes publiques.
    is_hidden = models.BooleanField(default=False)
    # Vrai pour la dernière note vendeur non masquée du couple (auteur, contexte vendeur) ;
    # recalculé par `services.reconcile_seller_flag` (règle en couche service, pas en base).
    counts_for_seller = models.BooleanField(default=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['user', 'offer_id'], name='uniq_review_author_offer')]
        indexes = [
            models.Index(
                fields=['seller_context_type', 'seller_context_id', 'is_hidden', 'counts_for_seller'],
                name='review_seller_avg',
            ),
            models.Index(fields=['offer_id', 'is_hidden'], name='review_offer_avg'),
            models.Index(fields=['user', 'seller_context_id', 'created_at'], name='review_author_seller'),
        ]

    def can_still_be_edited(self, window_hours=None):
        if window_hours is None:
            window_hours = ReviewSettings.get_solo().edit_window_hours
        return timezone.now() < self.created_at + timedelta(hours=window_hours)

    def __str__(self):
        return f"Avis de {self.user_id} sur {self.offer_id}"


class DeletedReviewMark(BaseModel):
    """Trace légère de la suppression d'un avis par son auteur : empêche de réécrire un avis pour la
    même offre pendant `ReviewSettings.edit_window_hours` (supprimer puis recréer contournerait la
    fenêtre de modification). Une ligne par (auteur, offre), mise à jour à chaque suppression."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='deleted_review_marks')
    offer_id = models.UUIDField()
    deleted_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'offer_id'], name='uniq_deleted_review_user_offer')]


class ReviewDailyCount(BaseModel):
    """Avis écrits par un utilisateur un jour donné (limite quotidienne, `ReviewSettings`). Compteur
    dédié : la suppression d'un avis ne libère pas de place, sinon écrire puis supprimer
    contournerait la limite."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='review_daily_counts')
    date = models.DateField()
    count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'date'], name='uniq_review_daily_user_date')]
