"""Module `payments` : gelé en l'état (hors V1, voir L0-13) ; refonte prévue en L1-12.

Alignement structurel uniquement (ADR 0002) : clé UUID, `offer_id` par UUID sans clé étrangère,
seules clés étrangères autorisées vers l'utilisateur.
"""
from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Transaction(BaseModel):
    STATUS_CHOICES = (
        ('PENDING', 'En attente de paiement'),
        ('HELD', 'Fonds bloqués (Séquestre)'),
        ('SHIPPED', 'Article expédié'),
        ('COMPLETED', 'Transaction terminée'),
        ('CANCELLED', 'Annulée / Remboursée'),
        ('DISPUTE', 'En litige'),
    )

    # Références
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchases')
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sales')
    # Offre achetée : référence par UUID (pas de clé étrangère entre domaines, ADR 0002).
    offer_id = models.UUIDField(db_index=True)

    # Détails financiers
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    laxpaie_reference = models.CharField(max_length=100, unique=True, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    def __str__(self):
        return f"Transaction {self.id} - {self.status}"
