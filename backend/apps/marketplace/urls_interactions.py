"""Contacts et propositions d'échange, montés sous `api/v1/interactions/` : URL historiques
conservées."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import ContactEventViewSet, ExchangeProposalViewSet

router = SimpleRouter()
router.register(r'contacts', ContactEventViewSet, basename='contact')
router.register(r'exchanges', ExchangeProposalViewSet, basename='exchange')

urlpatterns = [
    path('', include(router.urls)),
]
