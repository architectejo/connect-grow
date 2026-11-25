from django.urls import path

from .views import (
    ChangePasswordView,
    ContactChannelView,
    ContactPhoneVerifyView,
    ContactPhoneView,
    ContactSettingsView,
    ContextListView,
    KycDecisionView,
    KycDocumentDownloadView,
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
from .views_account_blockers import AccountDeletionBlockersView
from .views_organizations import (
    OrganizationArchiveView, OrganizationDetailView, OrganizationInternalView, OrganizationLeaveView,
    OrganizationLimitsView, OrganizationMemberDetailView, OrganizationMembersView,
    OrganizationTransferOwnershipView, OrganizationViewSet,
)
from .views_invitations import (
    InvitationAcceptView, InvitationDeclineView, InvitationPreviewView, InvitationWithdrawView,
    MyAwaitingInvitationsView, OrganizationInvitationConfirmView, OrganizationInvitationDetailView,
    OrganizationInvitationRejectView, OrganizationInvitationsView,
)
from .views_verification import (
    OrganizationKycDocumentDeleteView, OrganizationKycDocumentListCreateView, OrganizationVerificationView,
)
from .views_provider import ProviderActivateView, ProviderArchiveView, ProviderDetailView


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

    # Contextes disponibles pour le compte (ADR 0006, 9.1)
    path('contexts/', ContextListView.as_view(), name='contexts'),
    path('me/account-deletion-blockers/', AccountDeletionBlockersView.as_view(), name='account_deletion_blockers'),

    # Organisations (ADR 0006, 9.2 et 17.2) ; remplace `businesses/`
    path('organizations/', OrganizationViewSet.as_view({'get': 'list', 'post': 'create'}), name='organizations'),
    path('organizations/limits/', OrganizationLimitsView.as_view(), name='organization_limits'),
    path('organizations/<uuid:pk>/', OrganizationDetailView.as_view(), name='organization_detail'),
    path('organizations/<uuid:pk>/internal/', OrganizationInternalView.as_view(), name='organization_internal'),
    path('organizations/<uuid:pk>/archive/', OrganizationArchiveView.as_view(), name='organization_archive'),
    path('organizations/<uuid:pk>/leave/', OrganizationLeaveView.as_view(), name='organization_leave'),
    path('organizations/<uuid:pk>/members/', OrganizationMembersView.as_view(), name='organization_members'),
    path('organizations/<uuid:pk>/members/<uuid:membership_id>/', OrganizationMemberDetailView.as_view(),
         name='organization_member_detail'),
    path('organizations/<uuid:pk>/transfer-ownership/', OrganizationTransferOwnershipView.as_view(),
         name='organization_transfer_ownership'),
    # Invitations d'équipe (ADR 0008, contrat L1-01 §2) : le jeton voyage dans le corps, jamais dans l'URL
    path('organizations/<uuid:pk>/invitations/', OrganizationInvitationsView.as_view(),
         name='organization_invitations'),
    path('organizations/<uuid:pk>/invitations/<uuid:invitation_id>/', OrganizationInvitationDetailView.as_view(),
         name='organization_invitation_detail'),
    path('organization-invitations/preview/', InvitationPreviewView.as_view(), name='organization_invitation_preview'),
    path('organization-invitations/accept/', InvitationAcceptView.as_view(), name='organization_invitation_accept'),
    path('organization-invitations/decline/', InvitationDeclineView.as_view(), name='organization_invitation_decline'),
    # Invitations v2 (ADR 0010 D4, contrat L1-01 §7.4.6 et §7.4.7) : confirmation d'une invitation Administrateur
    path('organizations/<uuid:pk>/invitations/<uuid:invitation_id>/confirm/',
         OrganizationInvitationConfirmView.as_view(), name='organization_invitation_confirm'),
    path('organizations/<uuid:pk>/invitations/<uuid:invitation_id>/reject/',
         OrganizationInvitationRejectView.as_view(), name='organization_invitation_reject'),
    path('organization-invitations/awaiting/', MyAwaitingInvitationsView.as_view(),
         name='organization_invitations_awaiting'),
    path('organization-invitations/<uuid:invitation_id>/withdraw/', InvitationWithdrawView.as_view(),
         name='organization_invitation_withdraw'),

    # Prestataire individuel (ADR 0006, 9.3)
    path('provider/', ProviderDetailView.as_view(), name='provider_detail'),
    path('provider/activate/', ProviderActivateView.as_view(), name='provider_activate'),
    path('provider/archive/', ProviderArchiveView.as_view(), name='provider_archive'),

    # Réglages de contact vendeur (ADR 0005)
    path('contact-settings/', ContactSettingsView.as_view(), name='contact_settings'),
    path('contact-settings/phone/', ContactPhoneView.as_view(), name='contact_settings_phone'),
    path('contact-settings/phone/verify/', ContactPhoneVerifyView.as_view(), name='contact_settings_phone_verify'),
    path('contact-settings/channels/<str:channel>/', ContactChannelView.as_view(), name='contact_settings_channel'),

    # KYC Business (CDC 3.1, 3.11)
    path('kyc/review-queue/', KycReviewQueueView.as_view(), name='kyc_review_queue'),
    path('kyc/documents/<uuid:pk>/decision/', KycDecisionView.as_view(), name='kyc_decision'),
    path('kyc/documents/<uuid:pk>/download/', KycDocumentDownloadView.as_view(), name='kyc_download'),

    # Vérification des organisations (ADR 0006, 9.4)
    path('organizations/<uuid:org_id>/kyc/documents/', OrganizationKycDocumentListCreateView.as_view(),
         name='organization_kyc_documents'),
    path('organizations/<uuid:org_id>/kyc/documents/<uuid:pk>/', OrganizationKycDocumentDeleteView.as_view(),
         name='organization_kyc_document_delete'),
    path('organizations/<uuid:org_id>/verification/', OrganizationVerificationView.as_view(),
         name='organization_verification'),
]
