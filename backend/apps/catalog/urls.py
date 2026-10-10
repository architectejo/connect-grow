"""Référentiels publics. Montés sous `api/marketplace/` pour conserver les URL
existantes (`/api/marketplace/cities/`...) jusqu'à L0-11."""
from rest_framework.routers import SimpleRouter

from .views import CategoryViewSet, CityViewSet, CommuneViewSet

router = SimpleRouter()
router.register(r'cities', CityViewSet, basename='city')
router.register(r'communes', CommuneViewSet, basename='commune')
router.register(r'categories', CategoryViewSet, basename='category')

urlpatterns = router.urls
