from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import IdentifierTokenObtainPairSerializer
from .throttles import LoginIdentifierThrottle, LoginIpThrottle, LoginPhoneThrottle
from .views import (
    BusinessListView,
    ChangePasswordView,
    LogoutAllView,
    LogoutView,
    KycDecisionView,
    KycDocumentDeleteView,
    KycDocumentDownloadView,
    KycDocumentListCreateView,
    KycReviewQueueView,
    OtpRequestView,
    PasswordResetConfirmView,
    RegisterView,
    UserDetailView,
)


class LoginView(TokenObtainPairView):
    # Connexion par e-mail ou par téléphone (CDC 3.1), limitée par IP et par identifiant.
    serializer_class = IdentifierTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_classes = [LoginIpThrottle, LoginIdentifierThrottle, LoginPhoneThrottle]


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]


urlpatterns = [
    # Inscription
    path('register/', RegisterView.as_view(), name='register'),

    # Connexion (Obtenir le Token)
    path('login/', LoginView.as_view(), name='token_obtain_pair'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('logout-all/', LogoutAllView.as_view(), name='logout_all'),
    path('token/refresh/', RefreshView.as_view(), name='token_refresh'),

    # OTP et mot de passe
    path('otp/request/', OtpRequestView.as_view(), name='otp_request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    # Profil actuel
    path('me/', UserDetailView.as_view(), name='user_me'),

    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('businesses/', BusinessListView.as_view(), name='business_list'),

    # KYC Business (CDC 3.1, 3.11)
    path('kyc/documents/', KycDocumentListCreateView.as_view(), name='kyc_documents'),
    path('kyc/review-queue/', KycReviewQueueView.as_view(), name='kyc_review_queue'),
    path('kyc/documents/<uuid:pk>/', KycDocumentDeleteView.as_view(), name='kyc_document_delete'),
    path('kyc/documents/<uuid:pk>/decision/', KycDecisionView.as_view(), name='kyc_decision'),
    path('kyc/documents/<uuid:pk>/download/', KycDocumentDownloadView.as_view(), name='kyc_download'),
]
