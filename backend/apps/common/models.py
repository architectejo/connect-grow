"""Briques communes à tous les domaines (ADR 0002, décision 1).

Ce module ne porte aucun modèle concret : uniquement la classe abstraite dont
héritent les modèles de domaine.
"""
import uuid

from django.db import models


class BaseModel(models.Model):
    """Clé primaire UUID v4 et horodatages de création / modification.

    Les références entre domaines se font par UUID (`<entité>_id`), jamais par
    clé étrangère (CDC v1.2 §5.4, §11.1).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SingletonSettingsModel(BaseModel):
    """Ligne de réglages unique, modifiable dans le back-office (règle 11).

    L'identifiant est constant (`SINGLETON_ID`) : deux créations simultanées de la ligne
    se résolvent en une seule, sans contrainte d'unicité conditionnelle (portable MySQL).
    """

    SINGLETON_ID = uuid.UUID(int=1)

    class Meta:
        abstract = True

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return obj
