"""Avis (CDC 3.7). `Deal` et `TrustScoreSettings` sont des portages transitoires de l'ancien
module `reputation`, supprimés par L0-07 (retrait du Trust Score, règle 4) ; `Review.deal_id`
disparaît alors avec eux au profit de l'avis après contact (L0-10).

L'offre est désignée par son UUID (`offer_id`) : pas de clé étrangère vers `marketplace`
(CDC §5.4). Un avis survit à la purge de l'offre (CDC 3.10) ; les clés vers l'utilisateur
sont autorisées.
"""
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinLengthValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel, SingletonSettingsModel

REVIEW_EDIT_WINDOW_HOURS = 48


class TrustScoreSettings(SingletonSettingsModel):
    """CDC 3.7 : paramètres de la moyenne bayésienne du Trust Score, modifiables dans le
    back-office. Transitoire (L0-07)."""

    neutral_rating = models.FloatField(default=3.5, help_text="m : note neutre")
    neutral_weight = models.FloatField(default=5.0, help_text="C : poids de la note neutre")
    min_reviews_to_display = models.PositiveIntegerField(default=3)

    class Meta:
        verbose_name = "Paramètres du Trust Score"
        verbose_name_plural = "Paramètres du Trust Score"

    def __str__(self):
        return "Paramètres du Trust Score"


class Deal(BaseModel):
    """CDC 3.7 : « affaire conclue » — interaction déclarée par l'une des parties et
    confirmée par l'autre, seule condition d'accès au droit d'avis. Transitoire (L0-07)."""

    STATUS_PENDING = 'PENDING'
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_DECLINED = 'DECLINED'
    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente de confirmation"),
        (STATUS_CONFIRMED, "Confirmée"),
        (STATUS_DECLINED, "Refusée"),
    )

    # CDC 3.10 : si l'offre est purgée, l'affaire (et les avis qui en dépendent) survit.
    offer_id = models.UUIDField(null=True, blank=True, db_index=True)
    initiator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='deals_initiated',
    )
    counterparty = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='deals_to_confirm',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def other_party(self, user):
        if self.initiator_id == user.id:
            return self.counterparty
        if self.counterparty_id == user.id:
            return self.initiator
        return None

    def confirm(self):
        self.status = self.STATUS_CONFIRMED
        self.confirmed_at = timezone.now()
        self.save(update_fields=['status', 'confirmed_at', 'updated_at'])

    def decline(self):
        self.status = self.STATUS_DECLINED
        self.save(update_fields=['status', 'updated_at'])

    def __str__(self):
        return f"Affaire {self.offer_id} ({self.get_status_display()})"


class Review(BaseModel):
    offer_id = models.UUIDField(null=True, blank=True, db_index=True)
    # L'auteur de l'avis
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews_written')
    # La personne évaluée (CDC 3.7 : l'une des deux parties de l'affaire conclue).
    reviewed_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, related_name='reviews_received',
    )
    # CDC 3.7 : un avis n'est possible qu'après une affaire conclue (transitoire, L0-07 / L0-10).
    deal = models.ForeignKey(Deal, on_delete=models.CASCADE, null=True, blank=True, related_name='reviews')

    # CDC 3.7 : commentaire de 10 à 500 caractères.
    content = models.TextField(validators=[MinLengthValidator(10), MaxLengthValidator(500)])
    rating = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(5)],
    )  # De 1 à 5 étoiles

    # Réponse publique de la personne évaluée
    reply_content = models.TextField(null=True, blank=True, validators=[MaxLengthValidator(500)])
    reply_at = models.DateTimeField(null=True, blank=True)

    # CDC 3.7 : un avis retiré par la modération sort du calcul du Trust Score.
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        # Un seul avis par partie et par affaire (CDC 3.7).
        constraints = [models.UniqueConstraint(fields=['deal', 'user'], name='uniq_review_deal_user')]

    def can_still_be_edited(self):
        # CDC 3.7 : l'avis est modifiable pendant 48 heures.
        return timezone.now() < self.created_at + timedelta(hours=REVIEW_EDIT_WINDOW_HOURS)

    def __str__(self):
        return f"Avis de {self.user_id} sur {self.offer_id or 'une annonce supprimée'}"
