from unittest import mock

from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework import status

from apps.identity.models import User
from apps.marketplace.models import Offer

from .management.commands import setup_roles
from .models import Report
from .tests import ModerationTestBase


class TargetResolutionTests(ModerationTestBase):
    """Cibles désignées par `target_type` + `target_id` (UUID), résolues par les services (ADR 0002)."""

    def test_report_stores_type_and_uuid_and_exposes_the_legacy_keys(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post('/api/v1/moderation/reports/', {
            'target_type': 'POST', 'object_id': str(self.post.id), 'reason': 'ARNAQUE',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        report = Report.objects.get(pk=response.data['id'])
        self.assertEqual((report.target_type, report.target_id), ('offer', self.post.id))
        # L'auteur du signalement ne reçoit que le minimum (voir ReporterPrivacyTests).
        self.assertEqual(set(response.data), {'id', 'status', 'created_at'})
        self.client.force_authenticate(self.moderator)
        detail = self.client.get(f'/api/v1/moderation/reports/{report.id}/').data
        self.assertEqual(detail['object_id'], str(self.post.id))
        self.assertEqual(detail['target_type_display'], 'POST')
        self.assertNotIn('target_type', detail)

    def test_unknown_target_type_is_refused(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post('/api/v1/moderation/reports/', {
            'target_type': 'SANCTION', 'object_id': str(self.post.id), 'reason': 'SPAM',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_uuid_of_another_type_is_not_a_valid_target(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post('/api/v1/moderation/reports/', {
            'target_type': 'USER', 'object_id': str(self.post.id), 'reason': 'SPAM',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('object_id', response.data)

    def test_list_resolves_labels_in_batch_and_is_paginated_on_demand(self):
        for _ in range(2):
            Report.objects.create(target_type='offer', target_id=self.post.id, reporter=self.reporter, reason='SPAM')
        Report.objects.create(target_type='user', target_id=self.seller.id, reporter=self.reporter, reason='SPAM')
        self.client.force_authenticate(self.moderator)
        plain = self.client.get('/api/v1/moderation/reports/')
        self.assertEqual(len(plain.data), 3)
        self.assertTrue(all(row['target_display'] for row in plain.data))
        paged = self.client.get('/api/v1/moderation/reports/?page_size=2')
        self.assertEqual(paged.data['count'], 3)
        self.assertEqual(len(paged.data['results']), 2)

    def test_label_lookups_do_not_grow_with_the_number_of_reports(self):
        def count_queries(extra):
            for _ in range(extra):
                Report.objects.create(target_type='offer', target_id=self.post.id, reporter=self.reporter, reason='SPAM')
            from django.db import connection
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection) as queries:
                self.client.get('/api/v1/moderation/reports/')
            return len(queries)

        self.client.force_authenticate(self.moderator)
        self.client.get('/api/v1/moderation/reports/')  # réchauffe le cache de permissions de l'utilisateur
        few = count_queries(2)
        many = count_queries(5)
        self.assertEqual(few, many)

    def test_deleted_target_keeps_the_report_with_an_empty_label(self):
        report = Report.objects.create(
            target_type='offer', target_id=self.post.id, reporter=self.reporter, reason='SPAM',
        )
        Offer.objects.filter(pk=self.post.pk).delete()
        self.client.force_authenticate(self.moderator)
        response = self.client.get(f'/api/v1/moderation/reports/{report.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['target_display'])

    def test_audit_log_records_the_model_name_and_uuid_of_the_target(self):
        from . import services

        entry = services.record_audit(self.admin, 'TEST_ACTION', target=self.post, details='x')
        self.assertEqual((entry.target_type, entry.target_id), ('offer', self.post.id))
        bare = services.record_audit(self.admin, 'TEST_ACTION')
        self.assertEqual((bare.target_type, bare.target_id), ('', None))

    def test_open_report_detection_uses_the_same_keys(self):
        from . import services

        self.assertFalse(services.has_open_report(self.post))
        Report.objects.create(target_type='offer', target_id=self.post.id, reporter=self.reporter, reason='SPAM')
        self.assertTrue(services.has_open_report(self.post))

    def test_dashboard_counts_users_and_pending_kyc_through_identity(self):
        self.client.force_authenticate(self.admin)
        data = self.client.get('/api/v1/moderation/dashboard/').data
        self.assertEqual(data['users_count'], User.objects.count())
        self.assertEqual(data['pending_kyc_count'], 0)


class SetupRolesTests(ModerationTestBase):
    def codenames(self, name):
        return set(Group.objects.get(name=name).permissions.values_list('content_type__app_label', 'codename'))

    def test_command_is_idempotent(self):
        before = (self.codenames('Modérateur'), self.codenames('Administrateur'))
        call_command('setup_roles', verbosity=0)
        call_command('setup_roles', verbosity=0)
        self.assertEqual((self.codenames('Modérateur'), self.codenames('Administrateur')), before)
        self.assertEqual(Group.objects.filter(name__in=['Modérateur', 'Administrateur']).count(), 2)

    def test_stale_permissions_are_removed(self):
        extra = Permission.objects.get(content_type__app_label='moderation', codename='delete_auditlog')
        Group.objects.get(name='Modérateur').permissions.add(extra)
        call_command('setup_roles', verbosity=0)
        self.assertNotIn(('moderation', 'delete_auditlog'), self.codenames('Modérateur'))

    def test_least_privilege_for_moderators(self):
        perms = self.codenames('Modérateur')
        for forbidden in (
            ('moderation', 'delete_sanction'), ('moderation', 'change_sanction'), ('moderation', 'view_auditlog'),
            ('catalog', 'add_forbiddenitem'), ('visibility', 'change_rankingsettings'),
            ('marketplace', 'change_marketplacesettings'), ('identity', 'change_user'),
        ):
            self.assertNotIn(forbidden, perms)
        self.assertIn(('identity', 'review_kycdocument'), perms)

    def test_administrators_read_the_audit_log_but_never_edit_it_nor_touch_private_or_frozen_data(self):
        perms = self.codenames('Administrateur')
        self.assertIn(('moderation', 'view_auditlog'), perms)
        self.assertIn(('visibility', 'change_visibilitysettings'), perms)
        self.assertIn(('marketplace', 'change_marketplacesettings'), perms)
        self.assertFalse({app for app, _ in perms} & {'payments', 'messaging', 'notifications'})
        codenames = {codename for _, codename in perms}
        for codename in ('add_auditlog', 'change_auditlog', 'delete_auditlog', 'view_otpcode', 'change_otpcode'):
            self.assertNotIn(codename, codenames)

    def test_unknown_permission_fails_loudly(self):
        with mock.patch.dict(setup_roles.MODERATOR_PERMISSIONS, {'moderation.nexistepas': ['view']}):
            with self.assertRaises(CommandError):
                call_command('setup_roles', verbosity=0)
