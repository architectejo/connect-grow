"""Visibilité des offres : compteurs journaliers (vues, contacts) et réglages du classement.

Le module ne référence aucune table d'un autre domaine : l'offre est désignée par son
UUID (`offer_id`) ; seul le vendeur est une clé étrangère vers l'utilisateur (autorisée).
"""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import BaseModel, SingletonSettingsModel


class RankingSettings(SingletonSettingsModel):
    """CDC 3.8 : pondérations, demi-vie et bornes de l'algorithme « Trust & Engage »,
    paramétrables dans le back-office. Ligne unique.

    Le facteur de confiance est retiré par L0-07 / L0-08 (règle 4), pas pendant le portage."""

    # Engagement E = 1 + ln(1 + w_views*vues + w_likes*likes + w_comments*commentaires + w_shares*partages)
    weight_views = models.FloatField(default=1.0)
    weight_likes = models.FloatField(default=3.0)
    weight_comments = models.FloatField(default=5.0)
    weight_shares = models.FloatField(default=8.0)

    # Confiance T = 0.8 + 0.4 * (TrustScore / 5), bornée à [trust_factor_min, trust_factor_max]
    trust_factor_min = models.FloatField(default=0.8)
    trust_factor_max = models.FloatField(default=1.2)

    # Récence R = e^(-λ * âge_heures), demi-vie en heures
    recency_half_life_hours = models.FloatField(default=72.0)

    class Meta:
        verbose_name = "Paramètres de classement"
        verbose_name_plural = "Paramètres de classement"

    def __str__(self):
        return "Paramètres de l'algorithme Trust & Engage"


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
    """CDC 3.9 / 5.6 : vues et contacts reçus par offre et par jour (graphiques du tableau
    de bord). Les vues sont tenues à jour en temps réel, les contacts par la tâche
    planifiée `refresh_daily_contacts`."""

    offer_id = models.UUIDField()
    # Le vendeur facilite les requêtes du tableau de bord (clé étrangère vers l'utilisateur : autorisée).
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='visibility_counters',
    )
    date = models.DateField()
    views = models.PositiveIntegerField(default=0)
    contacts = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Compteur de visibilité"
        verbose_name_plural = "Compteurs de visibilité"
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['offer_id', 'date'], name='uniq_visibility_counter_offer_date'),
        ]
        indexes = [models.Index(fields=['seller', 'date'], name='visib_counter_seller_date')]

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
