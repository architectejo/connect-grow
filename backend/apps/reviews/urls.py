"""Avis, montés sous `api/interactions/` : URL historique conservée jusqu'à L0-11."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import ReviewViewSet

router = SimpleRouter()
router.register(r'reviews', ReviewViewSet, basename='review')

urlpatterns = [
    path('', include(router.urls)),
]
