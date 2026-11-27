"""Corrections de relecture et d'audit sur T1 (L0-09a) : compte supprimable, cible neutre, normalisation des noms,
types d'entrée, quota, organisations archivées, contraintes de contact, admin."""
import uuid
from unittest import mock

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Category
from apps.common.factories import make_test_image
from apps.moderation.models import AuditLog, Sanction

from . import services
from .models import (
    ContactConsent, ContactPoint, IdentitySettings, Organization, OrganizationDocumentRequirement, User,
)
from .tests_organizations import ADMIN, ANALYST, EDITOR, OWNER, TeamTestBase, make_user


class AccountRemovalTests(TeamTestBase):
    def test_sole_owner_of_an_active_organization_is_not_removable(self):
        self.assertBusiness('last_owner_account', services.assert_account_removable, self.owner)
        services.assert_account_removable(self.admin)  # simple membre : libre
        services.assert_account_removable(self.outsider)

    def test_deactivation_by_sanction_is_not_blocked(self):
        Sanction.objects.create(user=self.owner, sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        self.owner.is_active = False
        self.owner.save()  # aucune garde sur is_active

    def test_removable_with_a_second_owner_or_an_archived_organization(self):
        services.change_member_role(self.owner, self.org.pk, self.admin.pk, OWNER)
        services.assert_account_removable(self.owner)
        services.leave_organization(self.owner, self.org.pk)
        self.assertBusiness('last_owner_account', services.assert_account_removable, self.admin)
        services.archive_organization(self.admin, self.org.pk)
        services.assert_account_removable(self.admin)

    def test_user_admin_blocks_single_and_bulk_deletion_of_a_sole_owner(self):
        root = User.objects.create_superuser(email='root2@example.com', password='x', full_name='Root')
        self.client.force_login(root)
        response = self.client.post(f'/admin/identity/user/{self.owner.pk}/delete/', {'post': 'yes'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        # Suppression en masse (méthode appelée par l'action) : le propriétaire unique est ignoré et signalé.
        from django.contrib import admin as django_admin
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        request = RequestFactory().post('/admin/identity/user/')
        request.user = root
        request.session = {}
        request._messages = FallbackStorage(request)
        model_admin = django_admin.site._registry[User]
        model_admin.delete_queryset(request, User.objects.filter(pk__in=[self.owner.pk, self.outsider.pk]))
        self.assertTrue(User.objects.filter(pk=self.owner.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.outsider.pk).exists())
        self.assertIn('non supprimé', ' '.join(str(m) for m in request._messages))
        spare = make_user('spare')
        self.client.post(f'/admin/identity/user/{spare.pk}/delete/', {'post': 'yes'})
        self.assertFalse(User.objects.filter(pk=spare.pk).exists())


class AdminTests(TeamTestBase):
    def test_requirement_bulk_delete_is_audited_per_row(self):
        root = User.objects.create_superuser(email='root3@example.com', password='x', full_name='Root')
        self.client.force_login(root)
        ids = [str(p) for p in OrganizationDocumentRequirement.objects.filter(org_type='BOUTIQUE').values_list('pk', flat=True)]
        self.assertEqual(len(ids), 2)
        self.client.post('/admin/identity/organizationdocumentrequirement/', {
            'action': 'delete_selected', '_selected_action': ids, 'post': 'yes',
        })
        self.assertEqual(OrganizationDocumentRequirement.objects.filter(org_type='BOUTIQUE').count(), 0)
        self.assertEqual(AuditLog.objects.filter(action='DOC_REQUIREMENT_DELETED', actor=root).count(), 2)

    def test_suspension_reason_is_chosen_in_an_intermediate_form(self):
        staff = self.staff_user()
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        url = '/admin/identity/organization/'
        data = {'action': 'suspend_selected', '_selected_action': [str(self.org.pk)]}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'ACTIVE')
        self.assertEqual(self.client.post(url, {**data, 'apply': '1', 'reason': 'caprice'}).status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'ACTIVE')
        self.client.post(url, {**data, 'apply': '1', 'reason': 'legal'})
        self.org.refresh_from_db()
        self.assertEqual((self.org.status, self.org.suspension_reason), ('SUSPENDED', 'legal'))

    def test_failures_are_reported_as_a_warning(self):
        staff = self.staff_user()
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        response = self.client.post(
            '/admin/identity/organization/',
            {'action': 'reactivate_selected', '_selected_action': [str(self.org.pk)]}, follow=True,
        )
        self.assertContains(response, "1 organisation(s) non modifiée(s)")


class NameAndInputTests(TeamTestBase):
    def test_name_is_normalized(self):
        org = services.create_organization(make_user('namer'), '  ＡＢＣ   Atelier  Kin  ', 'ONG')
        self.assertEqual(org.name, 'ABC Atelier Kin')

    def test_control_direction_and_zero_width_characters_are_refused(self):
        user = make_user('namer2')
        for bad in ('Atelier​X', 'Atelier‮X', 'Atelier\x00X', 'Atelier\nX', 'Atelier X', 'A‍B'):
            with self.subTest(name=bad), self.assertRaises(ValidationError) as caught:
                services.create_organization(user, bad, 'ONG')
            self.assertEqual(caught.exception.get_codes()['name'], ['invalid_name'])
        with self.assertRaises(ValidationError):
            services.create_organization(user, ' A  ', 'ONG')

    def test_wrong_input_types_give_validation_errors(self):
        user = make_user('typer')
        cases = [
            ({'description': 123}, 'description'), ({'description': ['x']}, 'description'),
            ({'nif': 5}, 'nif'), ({'nif': 'n' * 51}, 'nif'), ({'org_type': ['ONG']}, 'org_type'),
            ({'org_type': None}, 'org_type'), ({'category_ids': 'abc'}, 'category_ids'),
            ({'category_ids': ['pas-un-uuid']}, 'category_ids'), ({'logo': 'chaine'}, 'logo'),
        ]
        for extra, field in cases:
            with self.subTest(extra=extra), self.assertRaises(ValidationError) as caught:
                services.create_organization(user, **{'name': 'Valide', 'org_type': 'ONG', **extra})
            self.assertIn(field, caught.exception.detail)
        self.assertEqual(Organization.objects.count(), 1)  # celle de setUp

    def test_nif_is_never_truncated_silently(self):
        org = services.create_organization(make_user('nifer'), 'Avec NIF', 'ONG', nif='  ' + 'n' * 50 + '  ')
        self.assertEqual(org.nif, 'n' * 50)

    def test_category_error_codes(self):
        user = make_user('cater')
        categories = [Category.objects.create(name=f'C{i}') for i in range(6)]
        with self.assertRaises(ValidationError) as caught:
            services.create_organization(user, 'Valide', 'ONG', category_ids=[c.pk for c in categories])
        self.assertEqual(caught.exception.get_codes()['category_ids'], ['too_many_categories'])
        with self.assertRaises(ValidationError) as caught:
            services.create_organization(user, 'Valide', 'ONG', category_ids=[uuid.uuid4()])
        self.assertEqual(caught.exception.get_codes()['category_ids'], ['unknown_category'])

    def test_logo_is_validated_and_no_orphan_file_remains_after_a_failure(self):
        user = make_user('logoer')
        with self.assertRaises(ValidationError) as caught:
            services.create_organization(user, 'Valide', 'ONG', logo=SimpleUploadedFile('x.png', b'pas une image'))
        self.assertIn('logo', caught.exception.detail)

        def stored():
            try:
                return set(default_storage.listdir('organization_logos')[1])
            except FileNotFoundError:
                return set()

        before = stored()
        with mock.patch('apps.identity.organizations.Membership.objects.create', side_effect=IntegrityError('boom')):
            with self.assertRaises(IntegrityError):
                services.create_organization(user, 'Valide', 'ONG', logo=make_test_image())
        self.assertEqual(stored(), before)
        org = services.create_organization(user, 'Avec logo', 'ONG', logo=make_test_image())
        self.assertTrue(default_storage.exists(org.logo.name))
        default_storage.delete(org.logo.name)


class ActorAndTargetTests(TeamTestBase):
    def test_restricted_actor_is_refused_except_to_leave(self):
        Sanction.objects.create(user=self.admin, sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        self.assertDenied('DENY_SECURITY', services.add_member, self.admin, self.org.pk, self.outsider.pk, EDITOR)
        self.assertDenied('DENY_SECURITY', services.change_member_role, self.admin, self.org.pk, self.editor.pk, ANALYST)
        services.leave_organization(self.admin, self.org.pk)
        self.assertIsNone(self.role_of(self.admin))

    def test_inactive_actor_is_refused(self):
        self.admin.is_active = False
        self.admin.save()
        self.assertDenied('DENY_SECURITY', services.revoke_member, self.admin, self.org.pk, self.analyst.pk)

    def test_role_change_and_transfer_refuse_an_inactive_or_restricted_target(self):
        Sanction.objects.create(user=self.editor, sanction_type='BANNISSEMENT', reason='x')
        self.assertBusiness('user_unavailable', services.change_member_role, self.owner, self.org.pk, self.editor.pk, ANALYST)
        self.assertBusiness('user_unavailable', services.transfer_ownership, self.owner, self.org.pk, self.editor.pk)
        self.analyst.is_active = False
        self.analyst.save()
        self.assertBusiness('user_unavailable', services.change_member_role, self.owner, self.org.pk, self.analyst.pk, EDITOR)
        self.assertEqual(self.role_of(self.owner), OWNER)

    def test_hard_limit_counts_memberships_of_archived_organizations_until_the_member_leaves(self):
        """Correction S5 (ADR 0010 D8) : archiver ne libère pas de place ; quitter l'organisation archivée, si."""
        row = IdentitySettings.get_solo()
        row.max_memberships_hard_limit = 1
        row.save()
        user = make_user('quota')
        first = services.create_organization(user, 'Une', 'ONG')
        self.assertBusiness('account_review_required', services.create_organization, user, 'Deux', 'ONG')
        services.archive_organization(user, first.pk)
        self.assertBusiness('account_review_required', services.create_organization, user, 'Deux', 'ONG')
        services.leave_organization(user, first.pk)
        self.assertEqual(services.create_organization(user, 'Deux', 'ONG').name, 'Deux')

    def test_last_owner_can_transfer_then_leave_an_archived_organization(self):
        services.archive_organization(self.owner, self.org.pk)
        services.transfer_ownership(self.owner, self.org.pk, self.admin.pk)
        self.assertEqual(self.role_of(self.admin), OWNER)
        services.leave_organization(self.admin, self.org.pk)  # dernier propriétaire d'une organisation archivée
        self.assertIsNone(self.role_of(self.admin))
        entry = AuditLog.objects.filter(action='MEMBERSHIP_REVOKED', actor=self.admin).latest('created_at')
        self.assertIn('old_role=OWNER', entry.details)
        self.assertEqual(entry.context_id, self.org.pk)

    def test_last_owner_still_cannot_leave_an_active_organization(self):
        self.assertBusiness('last_owner', services.leave_organization, self.owner, self.org.pk)

    def test_reactivation_audit_keeps_the_previous_state(self):
        staff = self.staff_user()
        services.suspend_organization(staff, self.org.pk, 'verification')
        services.reactivate_organization(staff, self.org.pk)
        self.assertEqual(
            AuditLog.objects.get(action='ORG_REACTIVATED').details, 'old_status=SUSPENDED; old_reason=verification',
        )

    def test_contact_rows_need_exactly_one_owner(self):
        for kwargs in (
            {}, {'user': self.owner, 'organization': self.org},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    ContactPoint.objects.create(phone='+243900000001', **kwargs)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    ContactConsent.objects.create(channel='MESSAGE', **kwargs)
        ContactPoint.objects.create(phone='+243900000001', organization=self.org)
        ContactPoint.objects.create(phone='+243900000002', user=self.owner)
        ContactConsent.objects.create(channel='MESSAGE', organization=self.org)
