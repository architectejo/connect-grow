"""Produits interdits. Monté sous `api/v1/moderation/forbidden-items/` pour
conserver l'URL existante."""
from rest_framework.routers import SimpleRouter

from .views import ForbiddenItemViewSet

router = SimpleRouter()
router.register(r'', ForbiddenItemViewSet, basename='forbidden-item')

urlpatterns = router.urls
