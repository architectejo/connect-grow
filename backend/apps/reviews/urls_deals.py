"""Affaires conclues (transitoire, L0-07), montées sous `api/reputation/`."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import DealViewSet

router = SimpleRouter()
router.register(r'deals', DealViewSet, basename='deal')

urlpatterns = [
    path('', include(router.urls)),
]
