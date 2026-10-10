"""Contacts et propositions d'échange, montés sous `api/interactions/` : URL historiques
conservées jusqu'à L0-11."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import ContactEventViewSet, ExchangeProposalViewSet

router = SimpleRouter()
router.register(r'contacts', ContactEventViewSet, basename='contact')
router.register(r'exchanges', ExchangeProposalViewSet, basename='exchange')

urlpatterns = [
    path('', include(router.urls)),
]
