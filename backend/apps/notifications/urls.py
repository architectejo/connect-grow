"""Routes montées sous `api/interactions/` : URL historiques conservées jusqu'à L0-11."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import NotificationViewSet

router = SimpleRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]
