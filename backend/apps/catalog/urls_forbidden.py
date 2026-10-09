"""Produits interdits. Monté sous `api/moderation/forbidden-items/` pour
conserver l'URL existante jusqu'à L0-11."""
from rest_framework.routers import SimpleRouter

from .views import ForbiddenItemViewSet

router = SimpleRouter()
router.register(r'', ForbiddenItemViewSet, basename='forbidden-item')

urlpatterns = router.urls
