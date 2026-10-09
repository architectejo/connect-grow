"""Outbox des événements de domaine (ADR 0003).

Tables techniques partagées par construction (patron « transactional outbox ») : aucune clé
étrangère vers un autre domaine, aucune référence à l'utilisateur. Un événement désigne ses
objets par UUID (en chaîne) dans son `payload`.
"""
from django.db import models

from apps.common.models import BaseModel


class OutboxEvent(BaseModel):
    """Fait métier survenu, écrit dans la transaction de l'émetteur."""

    PENDING = 'pending'
    DONE = 'done'
    DEAD = 'dead'
    STATUS_CHOICES = ((PENDING, "En attente"), (DONE, "Traité"), (DEAD, "En échec définitif"))

    event_type = models.CharField(max_length=100)
    version = models.PositiveSmallIntegerField(default=1)
    aggregate_type = models.CharField(max_length=50)
    aggregate_id = models.UUIDField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    # Date de passage à un état terminal (traité ou en échec définitif) : sert à la purge.
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Événement de domaine"
        verbose_name_plural = "Événements de domaine"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='outbox_event_status_created'),
            models.Index(fields=['completed_at'], name='outbox_event_completed'),
            models.Index(fields=['event_type'], name='outbox_event_type'),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.get_status_display()})"


class OutboxDelivery(BaseModel):
    """Livraison d'un événement à un abonné : une ligne par (événement, abonné), créée à la
    publication. La reprise d'un abonné en échec ne rejoue pas les abonnés déjà réussis."""

    PENDING = 'pending'
    PROCESSING = 'processing'
    DONE = 'done'
    DEAD = 'dead'
    STATUS_CHOICES = (
        (PENDING, "En attente"), (PROCESSING, "En cours"), (DONE, "Traitée"), (DEAD, "En échec définitif"),
    )

    event = models.ForeignKey(OutboxEvent, on_delete=models.CASCADE, related_name='deliveries')
    handler = models.CharField(max_length=150)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True, default='')
    last_error = models.TextField(blank=True, default='')
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Livraison d'événement"
        verbose_name_plural = "Livraisons d'événements"
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['event', 'handler'], name='uniq_outbox_delivery_event_handler'),
        ]
        indexes = [models.Index(fields=['status', 'next_attempt_at'], name='outbox_delivery_due')]

    def __str__(self):
        return f"{self.handler} ({self.get_status_display()})"
