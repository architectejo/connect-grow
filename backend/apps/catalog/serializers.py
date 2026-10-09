from rest_framework import serializers

from .models import Category, City, Commune, ForbiddenItem


class CommuneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commune
        fields = ['id', 'name', 'city']  # On inclut la ville pour pouvoir filtrer côté frontend


class CitySerializer(serializers.ModelSerializer):
    # On inclut les communes à l'intérieur de la ville pour un chargement efficace
    communes = CommuneSerializer(many=True, read_only=True)

    class Meta:
        model = City
        fields = ['id', 'name', 'communes']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'icon', 'slug']


class ForbiddenItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ForbiddenItem
        fields = ['id', 'keyword', 'category', 'created_at']
        read_only_fields = ['created_at']
