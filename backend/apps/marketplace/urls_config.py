from django.urls import path

from .views_config import FeaturesView

urlpatterns = [
    path('features/', FeaturesView.as_view(), name='config_features'),
]
