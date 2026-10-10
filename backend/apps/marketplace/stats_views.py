from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.throttles import PublicIpThrottle
from apps.identity import services as identity_services
from apps.reviews import services as reviews_services
from apps.visibility import services as visibility_services

from . import services
from .models import Offer
from .serializers import PublicSellerProfileSerializer


def _history(points):
    return [{"day": p.date.strftime('%d/%m'), "views": p.views} for p in points]


class DashboardStatsView(identity_services.ActingContextMixin, APIView):
    """Agrégats du CONTEXTE ACTIF (en-tête `X-Context`, capacité `stats.view` : tous les rôles, ADR 0006, 9.8)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        ctx = self.authorize_capability('stats.view')
        stats = visibility_services.get_seller_stats(ctx.type, ctx.id)
        active_offers = services.count_active_offers(ctx.type, ctx.id)

        # CDC 3.9 : contacts reçus et taux de contact par annonce (agrégat CDC 5.6,
        # commande refresh_daily_contacts).
        contact_rate = round(stats.contacts_count / active_offers, 2) if active_offers else 0.0

        # ADR 0004, 7.3 : moyenne des notes vendeur visibles (sans seuil d'affichage : le vendeur
        # voit ses propres chiffres), calculée à la lecture par `reviews`. Le nom de champ
        # avg_rating est conservé (déjà consommé par le front) ; il vaut null sans avis.
        rating = reviews_services.get_seller_dashboard_rating(ctx.type, ctx.id)
        return Response({
            "history": _history(stats.history),
            "summary": {
                "total_views": stats.total_views,
                "today_views": stats.today_views,
                "active_posts": active_offers,
                "contacts_count": stats.contacts_count,
                "contact_rate": contact_rate,
                "avg_rating": rating.average,
                "review_count": rating.review_count,
            },
        })


class OfferStatsView(identity_services.ActingContextMixin, APIView):
    """Statistiques d'une offre : autorisées d'après le contexte PROPRIÉTAIRE de l'offre (`stats.view`), jamais
    d'après l'en-tête. Un tiers reçoit 403 `DENY_RELATION`."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        offer = Offer.objects.filter(pk=pk).first()
        if offer is None:
            return Response({"error": "Annonce introuvable ou accès refusé."}, status=404)
        services.authorize_offer(request.user, offer, 'stats.view')  # 404 uniforme pour un étranger si non publique
        return Response({"history": _history(visibility_services.get_offer_history(pk))})


class SellerProfileThrottle(PublicIpThrottle):
    """Lecture publique du profil d'un vendeur : par adresse IP, anonymes compris."""

    scope = 'seller_profile'


class PublicSellerProfileView(APIView):
    """Profil public minimal d'un contexte vendeur (ADR 0006, 9.7) : `GET sellers/<user|provider|organization>/<id>/`.

    Public, lecture seule, indépendant du demandeur : aucune authentification n'est lue (un jeton périmé ne casse
    pas la page) et l'en-tête `X-Context` est ignoré. Un contexte inexistant, mal formé, non public (compte
    désactivé ou sanctionné, profil archivé, organisation suspendue ou archivée) répond le MÊME 404 : aucun oracle
    d'existence. La réponse est mise en cache publiquement quelques secondes, sauf si la requête porte un jeton ou
    `X-Context` (le middleware d'API la rend alors privée)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [SellerProfileThrottle]
    CACHE_SECONDS = 60
    PATH_TYPES = {'user': 'USER', 'provider': 'PROVIDER', 'organization': 'ORGANIZATION'}

    def get(self, request, context_type, context_id):
        profile = services.get_public_seller_profile(self.PATH_TYPES.get(context_type), context_id)
        if profile is None:
            raise NotFound("Vendeur introuvable.")
        summary = profile.summary
        # Assemblage dans la vue : la fiche et le nombre d'offres viennent de `marketplace`/`identity`, la note de
        # `reviews` (qui importe déjà `marketplace.services` : l'import inverse ferait un cycle). Pour chaque
        # identifiant demandé, `get_seller_ratings` renvoie toujours une entrée (zéro avis compris).
        rating = reviews_services.get_seller_ratings(summary.context_type, [summary.context_id])[summary.context_id]
        if rating.average is None:
            # Sous le seuil d'affichage, le nombre d'avis n'est pas public non plus (il révélerait « 1 avis »).
            rating = reviews_services.RatingSummary(None, 0)
        data = PublicSellerProfileSerializer(
            {'summary': summary, 'rating': rating, 'active_offers_count': profile.active_offers_count},
            context={'request': request},
        ).data
        response = Response(data)
        if not request.META.get('HTTP_X_CONTEXT') and not request.META.get('HTTP_AUTHORIZATION'):
            response['Cache-Control'] = f'public, max-age={self.CACHE_SECONDS}'
        return response
