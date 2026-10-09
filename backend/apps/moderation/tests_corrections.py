import uuid

from django.contrib import admin
from django.core.cache import cache
from django.test import RequestFactory, override_settings
from rest_framework import status

from apps.identity.models import User
from apps.marketplace.models import Offer
from apps.reviews.admin import ReviewAdmin
from apps.reviews.models import Review

from .tests import make_review

from . import services
from .models import Report, Sanction
from .tests import ModerationTestBase

REPORTS = '/api/moderation/reports/'
SANCTIONS = '/api/moderation/sanctions/'
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'moderation-throttles'}}


def make_user(email, **extra):
    return User.objects.create_user(email=email, password='x', full_name=extra.pop('full_name', 'Nom'), **extra)


class ReporterPrivacyTests(ModerationTestBase):
    def test_a_regular_reporter_gets_only_the_minimum_back(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post(REPORTS, {'target_type': 'USER', 'object_id': str(self.seller.id), 'reason': 'SPAM'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(response.data), {'id', 'status', 'created_at'})
        body = response.content.decode()
        self.assertNotIn(self.seller.email, body)
        self.assertNotIn('Vendeur', body)

    def test_a_hidden_offer_title_is_not_returned_to_a_regular_reporter(self):
        Offer.objects.filter(pk=self.post.pk).update(is_active=False, is_deleted=True)
        self.client.force_authenticate(self.reporter)
        response = self.client.post(REPORTS, {'target_type': 'POST', 'object_id': str(self.post.id), 'reason': 'SPAM'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn(self.post.title, response.content.decode())

    def test_staff_labels_of_accounts_never_contain_email_or_phone(self):
        self.seller.phone = '+243990000001'
        self.seller.save()
        nameless = make_user('anonyme@example.com', full_name='')
        Report.objects.create(target_type='user', target_id=self.seller.id, reporter=self.reporter, reason='SPAM')
        Report.objects.create(target_type='user', target_id=nameless.id, reporter=self.reporter, reason='SPAM')
        self.client.force_authenticate(self.moderator)
        response = self.client.get(REPORTS)
        body = response.content.decode()
        for secret in (self.seller.email, '+243990000001', 'anonyme@example.com'):
            self.assertNotIn(secret, body)
        labels = {row['target_display'] for row in response.data}
        self.assertEqual(labels, {'Vendeur', f'Utilisateur {str(nameless.id)[:8]}'})


class ReportAbuseTests(ModerationTestBase):
    def post_report(self, target_type='USER', target=None, **extra):
        return self.client.post(REPORTS, {
            'target_type': target_type, 'object_id': str((target or self.seller).pk), 'reason': 'SPAM', **extra,
        })

    def test_duplicate_open_report_is_refused_until_the_first_is_closed(self):
        self.client.force_authenticate(self.reporter)
        self.assertEqual(self.post_report().status_code, 201)
        self.assertEqual(self.post_report().status_code, 409)
        Report.objects.update(status=Report.STATUS_REJETE)
        self.assertEqual(self.post_report().status_code, 201)

    def test_another_reporter_can_report_the_same_target(self):
        self.client.force_authenticate(self.reporter)
        self.assertEqual(self.post_report().status_code, 201)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.post_report().status_code, 201)

    def test_own_account_and_own_offer_cannot_be_reported(self):
        self.client.force_authenticate(self.seller)
        for response in (self.post_report(), self.post_report('POST', self.post)):
            self.assertEqual(response.status_code, 400)
            self.assertIn('object_id', response.data)

    def test_own_review_cannot_be_reported(self):
        review = make_review(self.reporter, self.seller)
        self.client.force_authenticate(self.reporter)
        self.assertEqual(self.post_report('REVIEW', review).status_code, 400)

    def test_description_length_is_limited(self):
        self.client.force_authenticate(self.reporter)
        self.assertEqual(self.post_report(description='x' * 1001).status_code, 400)
        self.assertEqual(self.post_report(description='x' * 1000).status_code, 201)

    @override_settings(CACHES=LOCMEM)
    def test_reports_are_throttled_per_user(self):
        cache.clear()
        targets = [make_user(f'cible{i}@example.com') for i in range(11)]
        self.client.force_authenticate(self.reporter)
        codes = [self.post_report(target=t).status_code for t in targets]
        self.assertEqual(codes[:10], [201] * 10)
        self.assertEqual(codes[10], 429)
        cache.clear()


class ModerationPermissionTests(ModerationTestBase):
    def setUp(self):
        super().setUp()
        self.bare_staff = make_user('staff@example.com', is_staff=True)  # is_staff sans groupe
        self.report = Report.objects.create(
            target_type='user', target_id=self.seller.id, reporter=self.reporter, reason='SPAM',
        )

    def test_staff_without_group_has_no_access_anywhere(self):
        self.client.force_authenticate(self.bare_staff)
        for method, url in (
            ('get', REPORTS), ('get', f'{REPORTS}{self.report.id}/'), ('post', f'{REPORTS}{self.report.id}/claim/'),
            ('get', SANCTIONS), ('get', '/api/moderation/dashboard/'), ('post', SANCTIONS),
        ):
            self.assertEqual(getattr(self.client, method)(url).status_code, 403, url)

    def test_anonymous_is_refused(self):
        self.assertEqual(self.client.get('/api/moderation/dashboard/').status_code, 401)
        self.assertEqual(self.client.get(SANCTIONS).status_code, 401)

    def test_moderator_works_the_queue_and_sees_the_dashboard(self):
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.client.get(REPORTS).status_code, 200)
        self.assertEqual(self.client.post(f'{REPORTS}{self.report.id}/claim/').status_code, 200)
        self.assertEqual(self.client.get(SANCTIONS).status_code, 200)
        self.assertEqual(self.client.get('/api/moderation/dashboard/').status_code, 200)

    def test_only_administrators_lift_a_ban(self):
        ban = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='x', issued_by=self.admin,
        )
        ban.apply()
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.client.post(f'{SANCTIONS}{ban.id}/lift/').status_code, 403)
        self.seller.refresh_from_db()
        self.assertFalse(self.seller.is_active)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f'{SANCTIONS}{ban.id}/lift/').status_code, 200)

    def test_moderator_lifts_a_warning(self):
        warning = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_AVERTISSEMENT, reason='x', issued_by=self.admin,
        )
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.client.post(f'{SANCTIONS}{warning.id}/lift/').status_code, 200)

    def test_group_permissions_cover_what_the_api_requires(self):
        for user in (self.moderator, self.admin):
            fresh = User.objects.get(pk=user.pk)
            for perm in ('moderation.view_report', 'moderation.change_report',
                         'moderation.view_sanction', 'moderation.add_sanction'):
                self.assertTrue(fresh.has_perm(perm), (user.email, perm))


class ReportStateMachineTests(ModerationTestBase):
    def make_report(self):
        return Report.objects.create(target_type='user', target_id=self.seller.id, reporter=self.reporter, reason='SPAM')

    def test_closed_reports_refuse_every_transition_and_keep_resolved_at(self):
        report = self.make_report()
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.client.post(f'{REPORTS}{report.id}/resolve/', {'notes': 'ok'}).status_code, 200)
        report.refresh_from_db()
        resolved_at = report.resolved_at
        for action_name in ('claim', 'resolve', 'reject'):
            response = self.client.post(f'{REPORTS}{report.id}/{action_name}/', {'notes': 'autre'})
            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, action_name)
        report.refresh_from_db()
        self.assertEqual(
            (report.status, report.resolved_at, report.decision_notes), (Report.STATUS_TRAITE, resolved_at, 'ok'),
        )

    def test_rejected_report_cannot_be_resolved(self):
        report = self.make_report()
        self.client.force_authenticate(self.moderator)
        self.client.post(f'{REPORTS}{report.id}/reject/')
        self.assertEqual(self.client.post(f'{REPORTS}{report.id}/resolve/').status_code, 409)

    def test_decision_notes_are_bounded(self):
        report = self.make_report()
        self.client.force_authenticate(self.moderator)
        self.assertEqual(self.client.post(f'{REPORTS}{report.id}/resolve/', {'notes': 'x' * 1001}).status_code, 400)


class SanctionTargetTests(ModerationTestBase):
    def test_hiding_an_offer_requires_it_to_belong_to_the_sanctioned_user(self):
        other = make_user('autre@example.com')
        self.client.force_authenticate(self.moderator)
        response = self.client.post(SANCTIONS, {
            'user': str(other.id), 'sanction_type': 'MASQUAGE_ANNONCE',
            'related_post': str(self.post.id), 'reason': 'Interdit.',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('related_post', response.data)
        self.post.refresh_from_db()
        self.assertTrue(self.post.is_active)

    def test_staff_and_self_cannot_be_sanctioned(self):
        self.client.force_authenticate(self.admin)
        for victim in (self.moderator, self.admin):
            response = self.client.post(SANCTIONS, {'user': str(victim.id), 'sanction_type': 'AVERTISSEMENT', 'reason': 'x'})
            self.assertEqual(response.status_code, 400, victim.email)
            self.assertIn('user', response.data)
        superuser = make_user('root@example.com', is_superuser=True)
        response = self.client.post(SANCTIONS, {'user': str(superuser.id), 'sanction_type': 'BANNISSEMENT', 'reason': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Sanction.objects.exists())


class ReviewAdminTests(ModerationTestBase):
    def test_moderator_can_only_toggle_is_hidden_in_the_admin(self):
        request = RequestFactory().get('/')
        request.user = self.moderator
        readonly = set(ReviewAdmin(Review, admin.site).get_readonly_fields(request))
        self.assertNotIn('is_hidden', readonly)
        self.assertTrue({'content', 'offer_rating', 'seller_rating', 'reply_content', 'user'} <= readonly)
        request.user = make_user('root@example.com', is_superuser=True, is_staff=True)
        # Le super-administrateur réécrit tout sauf la preuve de contact et le drapeau calculé.
        self.assertEqual(
            set(ReviewAdmin(Review, admin.site).get_readonly_fields(request)),
            {'contact_event_id', 'contact_channel', 'contact_recorded_at', 'counts_for_seller', 'edited_at'},
        )


class AutomaticReportTypesTests(ModerationTestBase):
    def test_every_automatic_target_type_has_a_resolver(self):
        self.assertTrue(services.AUTOMATIC_TARGET_TYPES)
        self.assertEqual(set(services.AUTOMATIC_TARGET_TYPES) - set(services.TARGET_RESOLVERS), set())

    def test_automatic_report_refuses_a_type_without_resolver(self):
        with self.assertRaises(ValueError):
            services.file_automatic_report('group', uuid.uuid4(), services.REASON_CROSSED_REVIEWS)

    def test_automatic_report_on_a_review_is_resolvable(self):
        review = make_review(self.reporter, self.seller)
        report = services.file_automatic_report('review', review.pk, services.REASON_CROSSED_REVIEWS, 'x')
        self.assertIn(report.target_type, services.TARGET_RESOLVERS)
        self.assertIsNotNone(services.resolve_target(report.target_type, report.target_id))
