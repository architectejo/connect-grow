from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel, SingletonSettingsModel

# Types de cible d'un signalement ou d'une entrée du journal : nom de modèle en minuscules
# (`offer`, `user`, `review`, `message`...). Aucune clé générique : la cible est désignée par
# (`target_type`, `target_id`) et résolue par les `services.py` des domaines (ADR 0002, décision 5).


class ModerationSettings(SingletonSettingsModel):
    """Règles de la modération modifiables dans le back-office (règle 11). Ligne unique."""

    report_processing_target_hours = models.PositiveIntegerField(
        default=72, validators=[MinValueValidator(1), MaxValueValidator(720)],
        help_text="Délai cible de traitement d'un signalement de contact fictif, en heures (720 au plus).",
    )
    fictitious_contact_daily_limit = models.PositiveIntegerField(
        default=20, validators=[MinValueValidator(1), MaxValueValidator(200)],
        help_text="Signalements « contact fictif » maximum par vendeur et par jour.",
    )

    class Meta:
        verbose_name = "Paramètres de modération"
        verbose_name_plural = "Paramètres de modération"

    def __str__(self):
        return "Paramètres de modération"


class ReportClosedError(Exception):
    """Transition refusée : le signalement est déjà traité ou rejeté."""


class Report(BaseModel):
    """CDC 3.11 : file unique de signalements (annonces, avis, messages,
    utilisateurs). Un seul modèle, cible désignée par `target_type` + `target_id`."""

    REASON_SPAM = 'SPAM'
    REASON_ARNAQUE = 'ARNAQUE'
    REASON_CONTENU_INTERDIT = 'CONTENU_INTERDIT'
    REASON_HARCELEMENT = 'HARCELEMENT'
    REASON_AVIS_CROISES = 'AVIS_CROISES'
    # Réservé au signalement d'un avis par le vendeur concerné (contact jugé fictif, ADR 0004).
    REASON_CONTACT_FICTIF = 'CONTACT_FICTIF'
    REASON_AUTRE = 'AUTRE'
    REASON_CHOICES = (
        (REASON_SPAM, "Spam"),
        (REASON_ARNAQUE, "Arnaque"),
        (REASON_CONTENU_INTERDIT, "Contenu interdit"),
        (REASON_HARCELEMENT, "Harcèlement"),
        (REASON_AVIS_CROISES, "Avis croisés suspects"),
        (REASON_CONTACT_FICTIF, "Contact fictif"),
        (REASON_AUTRE, "Autre"),
    )

    STATUS_EN_ATTENTE = 'EN_ATTENTE'
    STATUS_EN_COURS = 'EN_COURS'
    STATUS_TRAITE = 'TRAITE'
    STATUS_REJETE = 'REJETE'
    STATUS_CHOICES = (
        (STATUS_EN_ATTENTE, "En attente"),
        (STATUS_EN_COURS, "Prise en charge"),
        (STATUS_TRAITE, "Traité"),
        (STATUS_REJETE, "Rejeté"),
    )

    # La cible signalée : une annonce, un avis, un message ou un utilisateur.
    target_type = models.CharField(max_length=50)
    target_id = models.UUIDField()

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='reports_filed',
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    description = models.TextField(blank=True, max_length=1000)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_EN_ATTENTE)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reports_assigned',
    )
    decision_notes = models.TextField(blank=True)

    resolved_at = models.DateTimeField(null=True, blank=True)

    # Recours de l'auteur du contenu visé (une seule réponse, tant que le signalement est ouvert).
    author_response = models.TextField(blank=True, max_length=1000)
    author_responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['target_type', 'target_id'], name='report_target')]

    OPEN_STATUSES = (STATUS_EN_ATTENTE, STATUS_EN_COURS)
    # Motifs « de fond » : un signalement ouvert de l'un d'eux empêche l'auteur de supprimer le
    # contenu visé (la preuve ne s'efface pas). Spam et « autre » ne verrouillent rien.
    GRAVE_REASONS = (
        REASON_ARNAQUE, REASON_CONTENU_INTERDIT, REASON_HARCELEMENT, REASON_AVIS_CROISES, REASON_CONTACT_FICTIF,
    )

    def _transition(self, **changes):
        """Passe le signalement à un nouvel état s'il est encore ouvert. Mise à jour conditionnelle :
        deux décisions simultanées ne s'écrasent pas, et `resolved_at` d'un signalement clos ne
        change jamais."""
        changes['updated_at'] = timezone.now()
        done = Report.objects.filter(pk=self.pk, status__in=self.OPEN_STATUSES).update(**changes)
        if not done:
            raise ReportClosedError("Ce signalement est déjà clos.")
        self.refresh_from_db()

    def claim(self, moderator):
        self._transition(status=self.STATUS_EN_COURS, assigned_to=moderator)

    def resolve(self, notes=''):
        self._transition(status=self.STATUS_TRAITE, decision_notes=notes, resolved_at=timezone.now())

    def reject(self, notes=''):
        self._transition(status=self.STATUS_REJETE, decision_notes=notes, resolved_at=timezone.now())

    def __str__(self):
        return f"Signalement {self.id} ({self.get_reason_display()}) — {self.get_status_display()}"


class Sanction(BaseModel):
    """CDC 3.11 : avertissement, masquage d'une annonce, suspension
    temporaire, bannissement."""

    TYPE_AVERTISSEMENT = 'AVERTISSEMENT'
    TYPE_MASQUAGE_ANNONCE = 'MASQUAGE_ANNONCE'
    TYPE_SUSPENSION_TEMPORAIRE = 'SUSPENSION_TEMPORAIRE'
    TYPE_BANNISSEMENT = 'BANNISSEMENT'
    TYPE_CHOICES = (
        (TYPE_AVERTISSEMENT, "Avertissement"),
        (TYPE_MASQUAGE_ANNONCE, "Masquage d'une annonce"),
        (TYPE_SUSPENSION_TEMPORAIRE, "Suspension temporaire"),
        (TYPE_BANNISSEMENT, "Bannissement"),
    )

    # Rôles autorisés à prononcer chaque type de sanction (CDC 3.11 : « chaque
    # rôle n'accède qu'aux modules qui le concernent »). Un modérateur peut
    # avertir ou masquer une annonce ; seul un administrateur (ou plus) peut
    # suspendre ou bannir.
    MODERATOR_ALLOWED_TYPES = (TYPE_AVERTISSEMENT, TYPE_MASQUAGE_ANNONCE)
    # Sanctions qui désactivent le compte tant qu'elles sont actives.
    ACCOUNT_BLOCKING_TYPES = (TYPE_SUSPENSION_TEMPORAIRE, TYPE_BANNISSEMENT)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sanctions')
    sanction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    reason = models.TextField()
    # Offre masquée par la sanction : référence par UUID (pas de clé étrangère entre domaines,
    # ADR 0002) ; l'existence est vérifiée par apps.marketplace.services.
    related_offer_id = models.UUIDField(null=True, blank=True, db_index=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='sanctions_issued',
    )

    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(auto_now_add=True)
    # CDC 5.6 : la levée automatique à ends_at est une tâche planifiée (Sprint 5) ;
    # d'ici là, seule une levée manuelle (lift()) est possible.
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def apply(self):
        from apps.marketplace import services as marketplace_services

        if self.sanction_type == self.TYPE_MASQUAGE_ANNONCE and self.related_offer_id:
            marketplace_services.hide_by_moderation(self.related_offer_id)
        elif self.sanction_type in self.ACCOUNT_BLOCKING_TYPES:
            self.user.is_active = False
            self.user.save(update_fields=['is_active'])

    def lift(self):
        from apps.marketplace import services as marketplace_services

        if self.sanction_type == self.TYPE_MASQUAGE_ANNONCE and self.related_offer_id:
            marketplace_services.lift_moderation_hiding(self.related_offer_id)
        self.is_active = False
        self.save(update_fields=['is_active'])
        if self.sanction_type in self.ACCOUNT_BLOCKING_TYPES:
            # Le compte n'est réactivé que s'il ne reste aucune autre sanction bloquante en cours.
            still_blocked = Sanction.objects.filter(
                user_id=self.user_id, is_active=True, sanction_type__in=self.ACCOUNT_BLOCKING_TYPES,
            ).exclude(pk=self.pk).exists()
            if not still_blocked:
                self.user.is_active = True
                self.user.save(update_fields=['is_active'])

    def __str__(self):
        return f"{self.get_sanction_type_display()} — {self.user}"


class AuditLog(BaseModel):
    """CDC 3.11, règle 12 : journal horodaté de toutes les actions sensibles (modérateurs,
    administrateurs, système). Cible désignée par `target_type` + `target_id`, sans clé générique."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50)
    target_type = models.CharField(max_length=50, blank=True, default='')
    target_id = models.UUIDField(null=True, blank=True)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['target_type', 'target_id'], name='audit_target')]

    @classmethod
    def record(cls, actor, action, target=None, details=''):
        """`target` : instance d'un modèle à clé UUID (son nom de modèle devient `target_type`)."""
        entry = cls(actor=actor, action=action, details=details)
        if target is not None:
            entry.target_type = target._meta.model_name
            entry.target_id = target.pk
        entry.save()
        return entry

    def __str__(self):
        return f"{self.action} par {self.actor} le {self.created_at:%Y-%m-%d %H:%M}"
