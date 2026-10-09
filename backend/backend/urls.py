from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # Référentiels du catalogue : URL historiques conservées jusqu'à L0-11.
    path('api/marketplace/', include('apps.catalog.urls')),
    path('api/marketplace/', include('apps.marketplace.urls')),
    path('api/accounts/', include('apps.identity.urls')),
    path('api/payments/', include('apps.payments.urls')),
    path('api/interactions/', include('apps.interactions.urls')),
    path('api/reputation/', include('apps.reputation.urls')),
    path('api/moderation/forbidden-items/', include('apps.catalog.urls_forbidden')),
    path('api/moderation/', include('apps.moderation.urls')),
]

# Une seule fois suffit, et seulement si DEBUG est True
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)