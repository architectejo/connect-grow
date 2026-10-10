from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.moderation.models import AuditLog

from .admin import BusinessProfileAdmin, KycDocumentAdmin, UserAdmin
from .models import BusinessProfile, KycDocument, User


def make_admin_user(email, *, superuser=False, perms=()):
    user = User.objects.create_user(email=email, password='x', full_name='Admin', is_staff=True, is_superuser=superuser)
    for codename in perms:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


class UserAdminHardeningTests(TestCase):
    def request_for(self, user):
        request = RequestFactory().get('/')
        request.user = user
        return request

    def test_non_superuser_cannot_edit_privilege_fields_or_password(self):
        staff = make_admin_user('adm@example.com', perms=['view_user', 'change_user'])
        readonly = UserAdmin(User, admin.site).get_readonly_fields(self.request_for(staff))
        for field in ('password', 'is_superuser', 'is_staff', 'groups', 'user_permissions'):
            self.assertIn(field, readonly)

    def test_superuser_can_manage_privileges_but_password_stays_readonly(self):
        root = make_admin_user('root@example.com', superuser=True)
        readonly = UserAdmin(User, admin.site).get_readonly_fields(self.request_for(root))
        self.assertIn('password', readonly)
        self.assertNotIn('is_superuser', readonly)

    def test_change_form_does_not_expose_privilege_inputs_to_a_staff_with_change_permission(self):
        staff = make_admin_user('adm@example.com', perms=['view_user', 'change_user'])
        target = User.objects.create_user(email='t@example.com', password='x', full_name='T')
        self.client.force_login(staff)
        response = self.client.get(reverse('admin:identity_user_change', args=[target.pk]))
        self.assertEqual(response.status_code, 200)
        fields = response.context['adminform'].form.fields
        for field in ('password', 'is_superuser', 'is_staff', 'groups', 'user_permissions'):
            self.assertNotIn(field, fields)

    def test_staff_cannot_promote_themselves_by_posting_privilege_fields(self):
        staff = make_admin_user('adm@example.com', perms=['view_user', 'change_user'])
        self.client.force_login(staff)
        self.client.post(reverse('admin:identity_user_change', args=[staff.pk]), {
            'full_name': 'Admin', 'email': 'adm@example.com', 'user_type': 'PARTICULIER',
            'is_active': 'on', 'is_superuser': 'on', 'is_staff': 'on', 'password': 'pbkdf2_sha256$x',
        })
        staff.refresh_from_db()
        self.assertFalse(staff.is_superuser)
        self.assertNotEqual(staff.password, 'pbkdf2_sha256$x')

    def test_admin_change_is_audited_and_add_is_disabled(self):
        staff = make_admin_user('adm@example.com', perms=['view_user', 'change_user'])
        target = User.objects.create_user(email='t@example.com', password='x', full_name='T')
        self.client.force_login(staff)
        self.client.post(reverse('admin:identity_user_change', args=[target.pk]), {
            'full_name': 'Renommé', 'email': 't@example.com', 'user_type': 'PARTICULIER', 'is_active': 'on',
        })
        target.refresh_from_db()
        self.assertEqual(target.full_name, 'Renommé')
        self.assertTrue(AuditLog.objects.filter(action='USER_ADMIN_CHANGED', actor=staff).exists())
        self.assertFalse(UserAdmin(User, admin.site).has_add_permission(self.request_for(staff)))

    def test_bulk_and_single_deletions_are_audited_per_account(self):
        staff = make_admin_user('adm@example.com', perms=['view_user', 'delete_user'])
        victims = [User.objects.create_user(email=f'v{i}@example.com', password='x', full_name='V') for i in range(3)]
        ids = [str(v.pk) for v in victims]
        model_admin = UserAdmin(User, admin.site)
        request = self.request_for(staff)
        model_admin.delete_queryset(request, User.objects.filter(pk__in=[v.pk for v in victims[:2]]))
        model_admin.delete_model(request, victims[2])
        logged = set(AuditLog.objects.filter(action='USER_ADMIN_DELETED', actor=staff).values_list('target_id', flat=True))
        self.assertEqual({str(i) for i in logged}, set(ids))
        self.assertEqual(User.objects.filter(pk__in=ids).count(), 0)

    def test_standard_roles_cannot_change_users_or_edit_kyc(self):
        call_command('setup_roles', verbosity=0)
        for name in ('Modérateur', 'Administrateur'):
            codenames = set(Group.objects.get(name=name).permissions.values_list('codename', flat=True))
            self.assertNotIn('change_user', codenames, name)
            self.assertNotIn('change_kycdocument', codenames, name)
            self.assertNotIn('change_businessprofile', codenames, name)
            self.assertIn('review_kycdocument', codenames, name)


class KycAdminHardeningTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(email='biz@example.com', password='x', full_name='B', user_type='ENTREPRISE')
        self.profile = BusinessProfile.objects.create(user=owner, business_name='Ma Boutique')
        self.doc = KycDocument.objects.create(business_profile=self.profile, document_type='RCCM')
        self.staff = make_admin_user(
            'adm@example.com', perms=['view_kycdocument', 'change_kycdocument', 'delete_kycdocument',
                                      'add_kycdocument', 'view_businessprofile', 'change_businessprofile'],
        )

    def request(self):
        request = RequestFactory().get('/')
        request.user = self.staff
        return request

    def test_kyc_admin_is_read_only_and_never_shows_the_file(self):
        model_admin = KycDocumentAdmin(KycDocument, admin.site)
        request = self.request()
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, self.doc))
        self.assertFalse(model_admin.has_delete_permission(request, self.doc))
        self.assertIn('file', model_admin.exclude)
        for field in ('status', 'reviewed_by', 'reviewed_at', 'rejection_reason'):
            self.assertIn(field, model_admin.readonly_fields)
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin:identity_kycdocument_change', args=[self.doc.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'name="file"', response.content)
        self.assertNotIn(b'private_media', response.content)

    def test_kyc_status_cannot_be_forged_through_the_admin(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('admin:identity_kycdocument_change', args=[self.doc.pk]), {'status': 'VALIDE'})
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, KycDocument.STATUS_EN_ATTENTE)

    def test_is_verified_cannot_be_set_by_hand(self):
        self.assertIn('is_verified', BusinessProfileAdmin(BusinessProfile, admin.site).readonly_fields)
        self.client.force_login(self.staff)
        self.client.post(reverse('admin:identity_businessprofile_change', args=[self.profile.pk]), {
            'business_name': 'Ma Boutique', 'is_verified': 'on', 'bio': '', 'nif': '',
            'category_links-TOTAL_FORMS': '0', 'category_links-INITIAL_FORMS': '0',
        })
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_verified)
