from rest_framework import permissions, viewsets

from apps.moderation.services import record_audit

from .models import Category, City, Commune, ForbiddenItem
from .serializers import CategorySerializer, CitySerializer, CommuneSerializer, ForbiddenItemSerializer


class CityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = City.objects.all().prefetch_related('communes')
    serializer_class = CitySerializer
    permission_classes = [permissions.AllowAny]  # Tout le monde peut voir les villes


class CommuneViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Commune.objects.all()
    serializer_class = CommuneSerializer
    permission_classes = [permissions.AllowAny]  # Tout le monde peut voir les communes


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]  # Tout le monde peut voir les catégories


class ForbiddenItemViewSet(viewsets.ModelViewSet):
    """CDC 2.1 / 3.11 : référentiel des produits et services interdits.
    Lecture publique, écriture réservée à l'administration."""

    serializer_class = ForbiddenItemSerializer
    queryset = ForbiddenItem.objects.all()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]

    def perform_create(self, serializer):
        item = serializer.save(added_by=self.request.user)
        record_audit(self.request.user, 'FORBIDDEN_ITEM_CREATED', target=item, details=item.keyword)

    def perform_update(self, serializer):
        before = serializer.instance.keyword
        item = serializer.save()
        record_audit(
            self.request.user, 'FORBIDDEN_ITEM_UPDATED', target=item, details=f"{before} -> {item.keyword}",
        )

    def perform_destroy(self, instance):
        record_audit(self.request.user, 'FORBIDDEN_ITEM_DELETED', target=instance, details=instance.keyword)
        instance.delete()
