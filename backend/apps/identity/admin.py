"""Back-office Django de `identity`.

Principes (règles 2, 3, 10, 12) :
- aucune élévation de privilège par l'admin : `is_superuser`, `is_staff`, groupes et
  permissions directes ne sont modifiables que par un super-administrateur, et le mot de
  passe (empreinte) ne l'est jamais ici ;
- la vérification (`is_verified`) et les décisions KYC ne se saisissent pas à la main :
  elles ne naissent que de `decide_kyc_document` (journalisée) ;
- les pièces d'identité ne sont ni affichées ni téléchargeables depuis l'admin.
"""
from django.contrib import admin

from apps.moderation.services import record_audit

from .models import BusinessProfile, BusinessProfileCategory, ContactConsent, KycDocument, OtpCode, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'phone', 'phone_verified', 'full_name', 'user_type', 'is_staff')
    list_filter = ('user_type', 'is_staff', 'phone_verified')
    search_fields = ('email', 'phone', 'full_name')

    ALWAYS_READONLY = (
        'password', 'last_login', 'date_joined', 'created_at', 'updated_at',
        'phone_verified',
    )
    SUPERUSER_ONLY = ('is_superuser', 'is_staff', 'groups', 'user_permissions')

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return self.ALWAYS_READONLY
        return self.ALWAYS_READONLY + self.SUPERUSER_ONLY

    def has_add_permission(self, request):
        # Les comptes naissent de l'inscription (mot de passe haché, OTP) ; un compte créé ici
        # n'aurait pas de mot de passe valide.
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and form.changed_data:
            record_audit(
                request.user, 'USER_ADMIN_CHANGED', target=obj,
                details="Champs modifiés : " + ', '.join(sorted(form.changed_data)),
            )

    def delete_model(self, request, obj):
        record_audit(request.user, 'USER_ADMIN_DELETED', target=obj, details=f"Compte supprimé ({obj.pk}).")
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # Suppression en masse (action « supprimer la sélection ») : une trace par compte.
        for obj in queryset:
            record_audit(request.user, 'USER_ADMIN_DELETED', target=obj, details=f"Compte supprimé ({obj.pk}).")
        super().delete_queryset(request, queryset)


class BusinessProfileCategoryInline(admin.TabularInline):
    model = BusinessProfileCategory
    extra = 0


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'is_verified')
    list_filter = ('is_verified',)
    inlines = [BusinessProfileCategoryInline]
    # La vérification ne s'achète ni ne se saisit : elle résulte des décisions KYC (règle 3).
    readonly_fields = ('is_verified', 'user', 'created_at', 'updated_at')


@admin.register(KycDocument)
class KycDocumentAdmin(admin.ModelAdmin):
    """Consultation seule : ni fichier, ni saisie des décisions (voir KycDecisionView)."""

    list_display = ('business_profile', 'document_type', 'status', 'reviewed_by', 'created_at')
    list_filter = ('status', 'document_type')
    search_fields = ('business_profile__business_name',)
    exclude = ('file',)
    readonly_fields = (
        'business_profile', 'document_type', 'status', 'rejection_reason', 'reviewed_by', 'reviewed_at',
        'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OtpCode)
class OtpCodeAdmin(admin.ModelAdmin):
    list_display = ('phone', 'purpose', 'is_used', 'attempts', 'created_at', 'expires_at')
    list_filter = ('purpose', 'is_used')
    search_fields = ('phone',)
    exclude = ('code_hash',)

    def get_queryset(self, request):
        # Les codes de vérification du numéro de contact portent un numéro à ne pas exposer (LEG-PRV-12).
        return super().get_queryset(request).exclude(purpose=OtpCode.PURPOSE_CONTACT_VERIFY)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ContactConsent)
class ContactConsentAdmin(admin.ModelAdmin):
    """Consultation seule (ADR 0005, C12) : jamais le numéro, seulement les 4 derniers chiffres de preuve.
    `ContactPoint` n'est volontairement pas enregistré dans l'admin (LEG-PRV-12)."""

    list_display = ('user', 'channel', 'is_granted', 'text_version', 'granted_at', 'revoked_at', 'revoked_reason')
    list_filter = ('channel', 'is_granted', 'revoked_reason')
    readonly_fields = (
        'user', 'channel', 'is_granted', 'text_version', 'granted_at', 'revoked_at', 'phone_last4',
        'revoked_reason', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
