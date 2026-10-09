from rest_framework import serializers

from .models import Category, City, Commune, ForbiddenItem, normalize_key


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

    def validate_keyword(self, value):
        duplicates = ForbiddenItem.objects.filter(keyword_key=normalize_key(value))
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("Ce mot-clé existe déjà (la casse n'est pas prise en compte).")
        return value
