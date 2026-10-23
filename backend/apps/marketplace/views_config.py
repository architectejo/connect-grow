from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.throttles import AnonymousScopedThrottle

from . import services

FEATURES_CACHE_SECONDS = 60


class FeaturesView(APIView):
    """GET public : fonctionnalités activables par le back-office (aucune donnée personnelle).
    Cache court côté navigateur/proxy ; le front masque l'interface des fonctions éteintes."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [AnonymousScopedThrottle]
    throttle_scope = 'features'

    def get(self, request):
        response = Response({'features': services.get_public_features()})
        response['Cache-Control'] = f'public, max-age={FEATURES_CACHE_SECONDS}'
        return response
