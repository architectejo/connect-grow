"""Référentiels publics. Montés sous `api/v1/marketplace/` pour conserver les URL
(`/api/v1/marketplace/cities/`...)."""
from rest_framework.routers import SimpleRouter

from .views import CategoryViewSet, CityViewSet, CommuneViewSet

router = SimpleRouter()
router.register(r'cities', CityViewSet, basename='city')
router.register(r'communes', CommuneViewSet, basename='commune')
router.register(r'categories', CategoryViewSet, basename='category')

urlpatterns = router.urls
