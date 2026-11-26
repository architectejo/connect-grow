"""Back-office Django de `identity`.

Principes (règles 2, 3, 10, 12) :
- aucune élévation de privilège par l'admin : `is_superuser`, `is_staff`, groupes et
  permissions directes ne sont modifiables que par un super-administrateur, et le mot de
  passe (empreinte) ne l'est jamais ici ;
- la vérification (`is_verified`) et les décisions KYC ne se saisissent pas à la main :
  elles ne naissent que de `decide_kyc_document` (journalisée) ;
- les pièces d'identité ne sont ni affichées ni téléchargeables depuis l'admin.
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from apps.common.admin_mixins import SingletonSettingsAdminMixin
from apps.common.contexts import CONTEXT_ORGANIZATION, ContextDenied
from apps.moderation.services import record_audit

from . import services
from .permissions import REVIEW_KYC_PERMISSION
from .models import (
    ContactConsent, IdentitySettings, KycDocument, Membership, OtpCode,
    Organization, OrganizationDocumentRequirement, OrganizationInvitation, ProviderProfile, User,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'phone', 'phone_verified', 'full_name', 'is_staff')
    list_filter = ('is_staff', 'phone_verified')
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

        from . import services

        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if change and 'is_active' in form.changed_data:
                # Modification directe de `is_active` : la visibilité des offres suit (ADR 0006, A7/A9).
                services.announce_account_status(obj.pk, obj.is_active, request.user)
        if change and 'is_active' in form.changed_data and not obj.is_active:
            # Même effet que `set_account_active` (décision S3, L1-01-B7) : les attentes de confirmation créées par ce
            # compte sont rejetées, après la transaction, organisation par organisation.
            services.reject_awaiting_invitations_of_account(obj.pk, actor=request.user)
        if change and form.changed_data:
            record_audit(
                request.user, 'USER_ADMIN_CHANGED', target=obj,
                details="Champs modifiés : " + ', '.join(sorted(form.changed_data)),
            )

    def _audit_refusal(self, request, obj, exc):
        """Refus de suppression journalisé (règle 12) : code stable seulement, aucune donnée personnelle."""
        record_audit(
            request.user, 'USER_ADMIN_DELETE_REFUSED', target=obj, details=f"code={getattr(exc.detail, 'code', '')}",
        )

    def delete_view(self, request, object_id, extra_context=None):
        # Un compte non supprimable (seul administrateur principal, sanction en cours, signalement grave ouvert) est
        # refusé.
        if request.method == 'POST':
            obj = self.get_object(request, unquote(object_id))
            if obj is not None:
                try:
                    services.assert_account_removable(obj)
                except services.OrganizationError as exc:
                    self._audit_refusal(request, obj, exc)
                    self.message_user(request, exc.detail, messages.ERROR)
                    return redirect('admin:identity_user_change', obj.pk)
        return super().delete_view(request, object_id, extra_context)

    def _delete_one(self, request, obj):
        """Garde puis suppression, trace comprise, dans une seule transaction : une suppression qui échoue (refus de
        la garde, y compris par le récepteur `pre_delete`) ne laisse aucune trace de suppression."""
        services.assert_account_removable(obj)
        with transaction.atomic():
            record_audit(request.user, 'USER_ADMIN_DELETED', target=obj, details=f"Compte supprimé ({obj.pk}).")
            obj.delete()

    def delete_model(self, request, obj):
        try:
            self._delete_one(request, obj)
        except services.OrganizationError as exc:
            self._audit_refusal(request, obj, exc)
            self.message_user(request, exc.detail, messages.ERROR)

    def delete_queryset(self, request, queryset):
        # Suppression en masse (action « supprimer la sélection ») : une transaction et une trace par compte ; les
        # comptes non supprimables (seul administrateur principal, sanction en cours, signalement grave ouvert) sont
        # ignorés et signalés.
        blocked = 0
        for obj in queryset:
            try:
                self._delete_one(request, obj)
            except services.OrganizationError as exc:
                self._audit_refusal(request, obj, exc)
                blocked += 1
        if blocked:
            self.message_user(
                request,
                f"{blocked} compte(s) non supprimé(s) : seul administrateur principal d'une organisation, "
                "sanction en cours ou signalement grave ouvert.",
                messages.WARNING,
            )


@admin.register(KycDocument)
class KycDocumentAdmin(admin.ModelAdmin):
    """Consultation seule : ni fichier, ni saisie des décisions (voir KycDecisionView).

    Pièces d'organisation (KYB) : visibles seulement par le personnel qui détient `review_kycdocument`
    (liste et fiche), et chaque consultation d'une fiche est journalisée (règle 12). Aucun contact de membre
    n'est affiché."""

    list_display = ('organization', 'document_type', 'status', 'reviewed_by', 'created_at')
    list_filter = ('status', 'document_type')
    search_fields = ('organization__name',)
    exclude = ('file', 'uploaded_by')
    list_select_related = ('organization', 'reviewed_by')
    readonly_fields = (
        'organization', 'document_type', 'status', 'rejection_reason',
        'reviewed_by', 'reviewed_at', 'created_at', 'updated_at',
    )

    @staticmethod
    def _may_see_organization_documents(request):
        return request.user.has_perm(REVIEW_KYC_PERMISSION)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not self._may_see_organization_documents(request):
            queryset = queryset.none()  # toute pièce est rattachée à une organisation
        return queryset

    def has_view_permission(self, request, obj=None):
        if obj is not None and not self._may_see_organization_documents(request):
            return False
        return super().has_view_permission(request, obj)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)
        if request.method == 'GET' and response.status_code == 200:
            document = KycDocument.objects.filter(pk=object_id).first()
            if document is not None:
                record_audit(
                    request.user, 'KYC_ADMIN_VIEWED', target=document,
                    details=f"organization={document.organization_id}; document_type={document.document_type}",
                    context=(CONTEXT_ORGANIZATION, document.organization_id),
                )
        return response

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

    list_display = ('user', 'organization', 'channel', 'is_granted', 'text_version', 'granted_at', 'revoked_at', 'revoked_reason')
    list_filter = ('channel', 'is_granted', 'revoked_reason')
    readonly_fields = (
        'user', 'organization', 'granted_by', 'channel', 'is_granted', 'text_version', 'granted_at', 'revoked_at',
        'phone_last4',
        'revoked_reason', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(admin.ModelAdmin):
    """Consultation seule : ni ajout, ni modification, ni suppression."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SuspensionReasonForm(forms.Form):
    reason = forms.ChoiceField(
        label="Motif", choices=[
            ('moderation', "Modération"), ('verification', "Vérification"), ('legal', "Obligation légale"),
            ('other', "Autre"),
        ],
    )


@admin.register(Organization)
class OrganizationAdmin(ReadOnlyAdmin):
    """Lecture seule (ADR 0006, 11.4). Le personnel suspend et réactive par les actions ci-dessous, qui
    passent par les services (journal d'audit et événement de statut), réservées à la permission
    `identity.suspend_organization`. Le nom et les coordonnées des membres ne sont pas affichés.

    File de revue de création (ADR 0010 D8) : filtre « Revue de création : En revue » ; levée par l'action dédiée
    (permission `identity.review_organization_creation`, service audité). Le refus d'une organisation douteuse passe
    par la suspension (motif « Modération »). Le nombre de créations du compte n'est pas affiché."""

    list_display = ('name', 'org_type', 'status', 'creation_review_status', 'created_at')
    list_filter = ('status', 'creation_review_status', 'org_type')
    search_fields = ('name',)
    exclude = ('logo', 'nif', 'created_by', 'legacy_business_profile_id')
    actions = ['suspend_selected', 'reactivate_selected', 'clear_creation_review_selected']

    def has_suspend_permission(self, request):
        return request.user.has_perm('identity.suspend_organization')

    def has_review_creation_permission(self, request):
        return request.user.has_perm(services.REVIEW_CREATION_PERMISSION)

    @admin.action(description="Lever la revue de création des organisations sélectionnées",
                  permissions=['review_creation'])
    def clear_creation_review_selected(self, request, queryset):
        self._run(request, queryset, lambda org: services.clear_organization_creation_review(request.user, org.pk))

    @admin.action(description="Suspendre les organisations sélectionnées", permissions=['suspend'])
    def suspend_selected(self, request, queryset):
        """Étape 1 : formulaire du motif normalisé ; étape 2 (`apply`) : suspension par le service."""
        form = SuspensionReasonForm(request.POST if 'apply' in request.POST else None)
        if 'apply' in request.POST and form.is_valid():
            reason = form.cleaned_data['reason']
            self._run(request, queryset, lambda org: services.suspend_organization(request.user, org.pk, reason))
            return None
        return TemplateResponse(request, 'admin/identity/suspend_reason.html', {
            **self.admin_site.each_context(request), 'title': "Suspendre des organisations", 'form': form,
            'organizations': queryset, 'opts': self.model._meta,
            'selected': request.POST.getlist('_selected_action'),
        })

    @admin.action(description="Réactiver les organisations sélectionnées", permissions=['suspend'])
    def reactivate_selected(self, request, queryset):
        self._run(request, queryset, lambda org: services.reactivate_organization(request.user, org.pk))

    def _run(self, request, queryset, func):
        done = failed = 0
        for organization in queryset:
            try:
                func(organization)
                done += 1
            except (ContextDenied, services.OrganizationError):
                failed += 1
        if done:
            self.message_user(request, f"{done} organisation(s) modifiée(s).", messages.SUCCESS)
        if failed:
            self.message_user(request, f"{failed} organisation(s) non modifiée(s) (état incompatible ou droit manquant).", messages.WARNING)


@admin.register(Membership)
class MembershipAdmin(ReadOnlyAdmin):
    """Lecture seule : le personnel n'attribue aucun rôle et ne voit ni téléphone ni e-mail de membre."""

    list_display = ('organization', 'role', 'status', 'end_reason', 'joined_at', 'ended_at')
    list_filter = ('role', 'status')
    exclude = ('user', 'added_by', 'ended_by')


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(ReadOnlyAdmin):
    """Lecture seule (ADR 0008, 13) : ni l'empreinte du jeton, ni l'étiquette, ni les comptes (émetteur, personne qui a
    accepté, confirmateur, auteur de la clôture) ne sont affichés."""

    list_display = ('organization', 'role', 'status', 'expires_at', 'confirmation_expires_at', 'closed_at')
    list_filter = ('status', 'role')
    exclude = (
        'token_hash', 'label', 'created_by', 'closed_by', 'accepted_by', 'confirmed_by', 'confirmation_code_hash',
        'confirmation_code_failures',
    )


@admin.register(ProviderProfile)
class ProviderProfileAdmin(ReadOnlyAdmin):
    list_display = ('display_name', 'status', 'created_at')
    list_filter = ('status',)
    exclude = ('user',)


@admin.register(OrganizationDocumentRequirement)
class OrganizationDocumentRequirementAdmin(admin.ModelAdmin):
    """Pièces exigées par type d'organisation (règle 11) ; chaque modification est journalisée (règle 12)."""

    list_display = ('org_type', 'document_type', 'position')
    list_filter = ('org_type',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        record_audit(
            request.user, 'DOC_REQUIREMENT_CHANGED', target=obj,
            details=f"org_type={obj.org_type}; document_type={obj.document_type}; position={obj.position}",
        )

    def delete_model(self, request, obj):
        record_audit(
            request.user, 'DOC_REQUIREMENT_DELETED', target=obj,
            details=f"org_type={obj.org_type}; document_type={obj.document_type}",
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        # Suppression en masse : une trace par ligne (règle 12).
        for obj in queryset:
            record_audit(
                request.user, 'DOC_REQUIREMENT_DELETED', target=obj,
                details=f"org_type={obj.org_type}; document_type={obj.document_type}",
            )
        super().delete_queryset(request, queryset)


@admin.register(IdentitySettings)
class IdentitySettingsAdmin(SingletonSettingsAdminMixin, admin.ModelAdmin):
    list_display = (
        'max_memberships_hard_limit', 'max_categories_per_context', 'org_phone_channels_enabled',
        'kyb_file_retention_days', 'invitation_ttl_days', 'max_pending_invitations', 'invitation_history_days',
        'admin_invitation_confirmation_hours',
    )
