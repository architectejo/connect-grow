"""Routes montées sous `api/v1/interactions/` : URL historiques conservées."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import NotificationViewSet

router = SimpleRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]
