"""Endpoints du prestataire individuel (ADR 0006, 9.3). Vues fines : la logique est dans `providers.py`.
Ces routes concernent le compte lui-même (l'en-tête `X-Context` est ignoré, ADR 6.4). Authentification
requise ; seul le titulaire voit et agit sur son profil (aucun identifiant dans le chemin)."""
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    activate_provider, archive_provider, get_provider_category_ids, get_provider_profile, update_provider,
)
from .throttles import ProviderWriteThrottle

EXEMPT_REASON = "profil prestataire du compte : ignore X-Context (ADR 0006 §6.4)"
WRITABLE_FIELDS = ('display_name', 'bio', 'category_ids')


def serialize_provider(profile):
    return {
        'id': str(profile.pk), 'display_name': profile.display_name, 'bio': profile.bio,
        'category_ids': [str(c) for c in get_provider_category_ids(profile)],
        'status': profile.status, 'created_at': profile.created_at,
    }


def _private(response):
    response['Cache-Control'] = 'private, no-store'
    return response


def _body(request):
    data = request.data
    if not hasattr(data, 'keys'):
        raise serializers.ValidationError({'non_field_errors': ["Corps de requête invalide."]})
    return {key: data[key] for key in WRITABLE_FIELDS if key in data}


class ProviderDetailView(APIView):
    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ProviderWriteThrottle]

    def get(self, request):
        return _private(Response(serialize_provider(get_provider_profile(request.user))))

    def patch(self, request):
        profile = update_provider(request.user, **_body(request))
        return _private(Response(serialize_provider(profile)))


class ProviderActivateView(APIView):
    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ProviderWriteThrottle]

    def post(self, request):
        body = _body(request)
        profile, created = activate_provider(
            request.user, body.get('display_name'), body.get('bio'), body.get('category_ids'), fields=body.keys(),
        )
        return _private(Response(
            serialize_provider(profile), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        ))


class ProviderArchiveView(APIView):
    acting_context_exempt = EXEMPT_REASON
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ProviderWriteThrottle]

    def post(self, request):
        return _private(Response(serialize_provider(archive_provider(request.user))))
