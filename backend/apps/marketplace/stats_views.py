from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.visibility import services as visibility_services

from . import services
from .models import Offer


def _history(points):
    return [{"day": p.date.strftime('%d/%m'), "views": p.views} for p in points]


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stats = visibility_services.get_seller_stats(request.user.id)
        active_offers = services.count_active_offers(request.user.id)

        # CDC 3.9 : contacts reçus et taux de contact par annonce (agrégat CDC 5.6,
        # commande refresh_dashboard_aggregates).
        contact_rate = round(stats.contacts_count / active_offers, 2) if active_offers else 0.0

        # CDC 3.7 : Trust Score bayésien, déjà mis en cache sur l'utilisateur par le module
        # `reviews`, jamais recalculé ici. Le nom de champ avg_rating est conservé (déjà
        # consommé par le front). Transitoire : retiré par L0-07.
        return Response({
            "history": _history(stats.history),
            "summary": {
                "total_views": stats.total_views,
                "today_views": stats.today_views,
                "active_posts": active_offers,
                "contacts_count": stats.contacts_count,
                "contact_rate": contact_rate,
                "avg_rating": request.user.trust_score,
                "review_count": request.user.reviews_count,
            },
        })


class OfferStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not Offer.objects.filter(pk=pk, seller=request.user).exists():
            return Response({"error": "Annonce introuvable ou accès refusé."}, status=404)
        return Response({"history": _history(visibility_services.get_offer_history(pk))})
