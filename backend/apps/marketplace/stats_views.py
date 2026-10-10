from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity import services as identity_services
from apps.reviews import services as reviews_services
from apps.visibility import services as visibility_services

from . import services
from .models import Offer


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
        rating = reviews_services.get_seller_dashboard_rating(ctx.id, ctx.type)
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
        offer = Offer.objects.filter(pk=pk).only('seller_context_type', 'seller_context_id').first()
        if offer is None:
            return Response({"error": "Annonce introuvable ou accès refusé."}, status=404)
        self.authorize_object(offer.seller_context_type, offer.seller_context_id, 'stats.view')
        return Response({"history": _history(visibility_services.get_offer_history(pk))})
