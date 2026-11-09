"""Visibilité des offres : compteurs journaliers (vues, contacts) et réglages du classement.

Le module ne référence aucune table d'un autre domaine : l'offre est désignée par son
UUID (`offer_id`) et son vendeur par son contexte (type et UUID), sans clé étrangère.
"""
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import BaseModel, SingletonSettingsModel


MAX_WEIGHT = 1000.0
MAX_HALF_LIFE_HOURS = 8760.0
MAX_PROXIMITY = 5.0


class RankingSettings(SingletonSettingsModel):
    """CDC 3.5 : réglages du classement organique, modifiables dans le back-office (règle 11).
    Ligne unique. Score organique = P x E x R x D, sans terme de note (règle 4) :

    - E, engagement : 1 + ln(1 + w_vues.vues + w_favoris.favoris + w_contacts.contacts + w_partages.partages) ;
    - R, récence : 0,5 ** (âge_heures / demi-vie) ;
    - D, proximité : coefficients par commune / ville / défaut, appliqués à la lecture ;
    - P : filtre strict de la recherche (pas de réglage)."""

    weight_views = models.FloatField(default=1.0, validators=[MinValueValidator(0), MaxValueValidator(MAX_WEIGHT)])
    weight_favorites = models.FloatField(default=3.0, validators=[MinValueValidator(0), MaxValueValidator(MAX_WEIGHT)])
    weight_contacts = models.FloatField(default=5.0, validators=[MinValueValidator(0), MaxValueValidator(MAX_WEIGHT)])
    weight_shares = models.FloatField(default=8.0, validators=[MinValueValidator(0), MaxValueValidator(MAX_WEIGHT)])

    # Demi-vie de la récence, en heures (> 0).
    recency_half_life_hours = models.FloatField(default=72.0, validators=[MaxValueValidator(MAX_HALF_LIFE_HOURS)])

    # Proximité D : même commune >= même ville >= défaut, chacun >= 1.
    proximity_same_commune = models.FloatField(
        default=1.2, validators=[MinValueValidator(1), MaxValueValidator(MAX_PROXIMITY)])
    proximity_same_city = models.FloatField(
        default=1.1, validators=[MinValueValidator(1), MaxValueValidator(MAX_PROXIMITY)])
    proximity_default = models.FloatField(
        default=1.0, validators=[MinValueValidator(1), MaxValueValidator(MAX_PROXIMITY)])

    class Meta:
        verbose_name = "Paramètres de classement"
        verbose_name_plural = "Paramètres de classement"

    def clean(self):
        errors = {}
        for name in ('weight_views', 'weight_favorites', 'weight_contacts', 'weight_shares'):
            value = getattr(self, name)
            if value is None or not 0 <= value <= MAX_WEIGHT:
                errors[name] = f"Le poids doit être compris entre 0 et {MAX_WEIGHT:g}."
        if self.recency_half_life_hours is None or not 0 < self.recency_half_life_hours <= MAX_HALF_LIFE_HOURS:
            errors['recency_half_life_hours'] = f"La demi-vie doit être comprise entre 0 (exclu) et {MAX_HALF_LIFE_HOURS:g} heures."
        for name in ('proximity_same_commune', 'proximity_same_city', 'proximity_default'):
            value = getattr(self, name)
            if value is None or not 1 <= value <= MAX_PROXIMITY:
                errors[name] = f"Le coefficient de proximité doit être compris entre 1 et {MAX_PROXIMITY:g}."
        if not errors and not (
            self.proximity_same_commune >= self.proximity_same_city >= self.proximity_default
        ):
            errors['proximity_same_commune'] = (
                "Les coefficients doivent respecter : même commune >= même ville >= défaut."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return "Paramètres de classement"


class VisibilitySettings(SingletonSettingsModel):
    """Conservation des vues uniques (données de navigation : durée à fixer avec LEG-PRV,
    donc réglable dans le back-office, jamais codée en dur). Ligne unique."""

    # Minimum 1 jour : l'unicité d'une vue (et d'un partage) se vérifie sur la journée courante.
    unique_view_retention_days = models.PositiveIntegerField(
        default=2, validators=[MinValueValidator(1)],
        help_text="Jours de conservation des vues uniques avant purge (commande purge_offer_views).",
    )

    class Meta:
        verbose_name = "Paramètres de visibilité"
        verbose_name_plural = "Paramètres de visibilité"

    def __str__(self):
        return "Paramètres de visibilité"


class DailyVisibilityCounter(BaseModel):
    """CDC 3.9 / 5.6 : vues, partages et contacts reçus par offre et par jour (graphiques du
    tableau de bord). Vues et partages sont tenus à jour en temps réel ; les contacts le sont par
    la tâche planifiée `refresh_daily_contacts`. Ces compteurs, jamais purgés, sont la source
    des totaux `views_count` / `shares_count` de l'offre (recalculés par événement, ADR 0003)."""

    offer_id = models.UUIDField()
    # Contexte vendeur de l'offre (ADR 0006, A3) : facilite les requêtes du tableau de bord d'un contexte.
    seller_context_type = models.CharField(max_length=20)
    seller_context_id = models.UUIDField()
    date = models.DateField()
    views = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    contacts = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Compteur de visibilité"
        verbose_name_plural = "Compteurs de visibilité"
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['offer_id', 'date'], name='uniq_visibility_counter_offer_date'),
        ]
        indexes = [
            models.Index(fields=['seller_context_type', 'seller_context_id', 'date'], name='visib_counter_ctx_date'),
        ]

    def __str__(self):
        return f"{self.offer_id} - {self.date} ({self.views} vues, {self.contacts} contacts)"


class OfferUniqueView(BaseModel):
    """CDC 3.8 : « une vue unique = une offre vue par un utilisateur connecté (ou une
    empreinte anonyme) une fois par jour, garantie par une contrainte d'unicité en base. »

    `viewer_key` vaut « user:<uuid> » ou « anon:<empreinte hachée> » : une seule colonne
    texte, jamais nulle, pour une contrainte d'unicité portable SQLite/MySQL (pas de
    contrainte conditionnelle sur deux colonnes nullables)."""

    offer_id = models.UUIDField()
    viewer_key = models.CharField(max_length=64)
    date = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['offer_id', 'date', 'viewer_key'], name='uniq_unique_view_offer_day_viewer'),
        ]
        # Purge des vues d'un compte supprimé (T9-3) : recherche par visiteur, sans parcourir toute la table.
        indexes = [models.Index(fields=['viewer_key'], name='visib_uview_viewer_key')]
