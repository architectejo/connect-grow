"""L0-20 : champs du recours exposés à l'auteur, `can_delete`, lien des notifications, débit du recours
et admin des signalements."""
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from rest_framework.throttling import ScopedRateThrottle

from apps.identity.models import User
from apps.moderation.admin import ReportAdmin
from apps.moderation.models import Report, ReportClosedError
from apps.notifications.models import Notification

from .models import Review
from .tests_eligibility import REVIEWS_URL
from .tests_recours import RecoursBase


class ContestFieldsTests(RecoursBase):
    def detail(self, review=None):
        return f'{REVIEWS_URL}{(review or self.review).id}/'

    def test_author_sees_the_open_report_id_and_whether_he_answered(self):
        self.file_report()
        report = Report.objects.get()
        self.client.force_authenticate(self.buyer)
        data = self.client.get(self.detail()).data
        self.assertEqual((data['contest_report_id'], data['contest_responded']), (str(report.id), False))
        self.assertTrue(data['can_edit'])
        self.assertFalse(data['can_delete'])
        self.assertEqual(self.respond(self.buyer).status_code, 200)
        data = self.client.get(self.detail()).data
        self.assertEqual((data['contest_report_id'], data['contest_responded']), (str(report.id), True))

    def test_no_contest_without_open_fictitious_report(self):
        self.client.force_authenticate(self.buyer)
        data = self.client.get(self.detail()).data
        self.assertEqual((data['contest_report_id'], data['contest_responded']), (None, False))
        self.assertTrue(data['can_delete'])
        self.file_report()
        self.decide('reject')
        self.client.force_authenticate(self.buyer)
        data = self.client.get(self.detail()).data
        self.assertEqual((data['contest_report_id'], data['can_delete']), (None, True))

    def test_other_viewers_get_nothing_about_the_report(self):
        self.file_report()
        for viewer in (self.seller, self.other, None):
            self.client.force_authenticate(viewer)
            data = self.client.get(self.detail()).data
            self.assertEqual((data['contest_report_id'], data['contest_responded']), (None, False))
            self.assertFalse(data['can_delete'])
        self.client.force_authenticate(self.buyer)
        body = self.client.get(self.detail()).content.decode()
        for secret in ("jamais contact", str(self.seller.pk), 'seller@example.com', 'reporter'):
            self.assertNotIn(secret, body)

    def test_can_delete_is_false_when_hidden_or_replied_and_minor_report_does_not_lock(self):
        self.client.force_authenticate(self.buyer)
        Report.objects.create(target_type='review', target_id=self.review.id, reporter=self.other, reason='SPAM')
        self.assertTrue(self.client.get(self.detail()).data['can_delete'])
        Review.objects.filter(pk=self.review.pk).update(reply_content='Merci.')
        self.assertFalse(self.client.get(self.detail()).data['can_delete'])
        Review.objects.filter(pk=self.review.pk).update(reply_content='', is_hidden=True)
        self.assertFalse(self.client.get(self.detail()).data['can_delete'])

    def test_list_loads_the_states_in_a_constant_number_of_queries(self):
        self.file_report()
        self.client.force_authenticate(self.buyer)

        def count():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(f'{REVIEWS_URL}?post={self.offer.id}')
                self.assertEqual(response.status_code, 200)
            return len(ctx)

        base = count()
        for i in range(3):
            user = User.objects.create_user(email=f'x{i}@example.com', password='x', full_name=f'X{i}')
            self.make_review(user=user)
        self.assertEqual(count(), base)


class NotificationLinkAndThrottleTests(RecoursBase):
    def test_notifications_to_the_author_link_to_the_offer(self):
        self.file_report()
        self.decide('resolve')
        links = set(Notification.objects.filter(user=self.buyer).values_list('link', flat=True))
        self.assertEqual(links, {f'/post/{self.review.offer_id}'})

    def test_author_response_has_its_own_throttle_scope(self):
        cache.clear()
        self.file_report()
        self.assertEqual(ScopedRateThrottle.THROTTLE_RATES['report_response'], '30/hour')
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'report': '1/hour', 'report_response': '5/hour'}):
            self.assertEqual(self.respond(self.buyer).status_code, 200)  # pas compté dans « report »
            self.assertEqual(self.respond(self.buyer).status_code, 409)


class ReportAdminHardeningTests(RecoursBase):
    def setUp(self):
        super().setUp()
        self.file_report()
        self.report = Report.objects.get()
        self.admin = ReportAdmin(Report, admin_site)
        self.request = RequestFactory().get('/admin/')
        self.request.user = self.moderator

    def test_no_delete_and_notes_frozen_once_closed(self):
        self.assertFalse(self.admin.has_delete_permission(self.request, self.report))
        self.assertNotIn('decision_notes', self.admin.get_readonly_fields(self.request, self.report))
        self.report.resolve(notes='fait')
        self.assertIn('decision_notes', self.admin.get_readonly_fields(self.request, Report.objects.get()))

    def test_closed_in_the_meantime_shows_an_error_and_no_success_message(self):
        root = User.objects.create_superuser(email='root@example.com', password='x', full_name='Root')
        client = Client()
        client.force_login(root)
        with mock.patch.object(Report, 'resolve', side_effect=ReportClosedError):
            response = client.post(
                f'/admin/moderation/report/{self.report.id}/change/',
                {'status': Report.STATUS_TRAITE, 'assigned_to': '', 'decision_notes': 'Vérifié.'},
            )
        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual([m.level_tag for m in messages], ['error'])
        self.assertIn('clos entre-temps', str(messages[0]))
        self.assertEqual(Report.objects.get().status, Report.STATUS_EN_ATTENTE)
