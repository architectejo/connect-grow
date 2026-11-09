from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # Tout l'API est sous `api/v1/` (ADR 0007) ; l'ancien préfixe `api/` n'est plus servi.
    path('api/v1/marketplace/', include('apps.catalog.urls')),
    path('api/v1/marketplace/', include('apps.marketplace.urls')),
    path('api/v1/config/', include('apps.marketplace.urls_config')),
    path('api/v1/accounts/', include('apps.identity.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    # Interactions : servies par plusieurs domaines.
    path('api/v1/interactions/', include('apps.reviews.urls')),
    path('api/v1/interactions/', include('apps.marketplace.urls_interactions')),
    path('api/v1/interactions/', include('apps.messaging.urls')),
    path('api/v1/interactions/', include('apps.notifications.urls')),
    path('api/v1/moderation/forbidden-items/', include('apps.catalog.urls_forbidden')),
    path('api/v1/moderation/', include('apps.moderation.urls')),
]

# Une seule fois suffit, et seulement si DEBUG est True
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)