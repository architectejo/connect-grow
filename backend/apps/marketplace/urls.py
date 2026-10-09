from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .stats_views import DashboardStatsView, OfferStatsView
from .views import FavoriteViewSet, OfferViewSet

router = DefaultRouter()
router.register(r'posts', OfferViewSet, basename='offer')
router.register(r'favorites', FavoriteViewSet, basename='favorite')

urlpatterns = [
    path('stats/dashboard/', DashboardStatsView.as_view(), name='dashboard_stats'),
    path('stats/post/<uuid:pk>/', OfferStatsView.as_view(), name='offer_stats'),
    path('', include(router.urls)),
]
