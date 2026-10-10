"""Outils DRF communs : chargement par lot des données d'un autre domaine."""
from django.db.models.manager import BaseManager
from rest_framework import serializers


class PreloadingListSerializer(serializers.ListSerializer):
    """ListSerializer qui laisse le sérialiseur enfant charger, en une fois pour
    toute la liste, les données d'un autre domaine (remplace une jointure ORM
    supprimée par le découplage, sans requête N+1).

    Le sérialiseur enfant expose `preload(items, context)` : il lit les
    identifiants des objets de la liste, appelle le `services.py` du domaine
    propriétaire et range le résultat dans `context`.
    """

    def to_representation(self, data):
        items = list(data.all() if isinstance(data, BaseManager) else data)
        self.child.preload(items, self.context)
        return super().to_representation(items)
