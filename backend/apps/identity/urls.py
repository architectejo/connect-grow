from django.urls import path

from .views import (
    BusinessListView,
    ChangePasswordView,
    ContactChannelView,
    ContactPhoneVerifyView,
    ContactPhoneView,
    ContactSettingsView,
    ContextListView,
    KycDecisionView,
    KycDocumentDeleteView,
    KycDocumentDownloadView,
    KycDocumentListCreateView,
    KycReviewQueueView,
    LoginView,
    LogoutAllView,
    LogoutView,
    OtpRequestView,
    PasswordResetConfirmView,
    RefreshView,
    RegisterView,
    UserDetailView,
)


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

    # Contextes disponibles pour le compte (ADR 0006, 9.1)
    path('contexts/', ContextListView.as_view(), name='contexts'),

    # Réglages de contact vendeur (ADR 0005)
    path('contact-settings/', ContactSettingsView.as_view(), name='contact_settings'),
    path('contact-settings/phone/', ContactPhoneView.as_view(), name='contact_settings_phone'),
    path('contact-settings/phone/verify/', ContactPhoneVerifyView.as_view(), name='contact_settings_phone_verify'),
    path('contact-settings/channels/<str:channel>/', ContactChannelView.as_view(), name='contact_settings_channel'),

    # KYC Business (CDC 3.1, 3.11)
    path('kyc/documents/', KycDocumentListCreateView.as_view(), name='kyc_documents'),
    path('kyc/review-queue/', KycReviewQueueView.as_view(), name='kyc_review_queue'),
    path('kyc/documents/<uuid:pk>/', KycDocumentDeleteView.as_view(), name='kyc_document_delete'),
    path('kyc/documents/<uuid:pk>/decision/', KycDecisionView.as_view(), name='kyc_decision'),
    path('kyc/documents/<uuid:pk>/download/', KycDocumentDownloadView.as_view(), name='kyc_download'),
]
