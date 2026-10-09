"""Durcissement : avis protégés, quota quotidien, réponse unique, audit, limites de débit, requêtes."""
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle

from apps.identity.models import User
from apps.moderation.models import AuditLog, Report

from . import services
from .admin import ReviewAdmin, ReviewSettingsAdmin
from .models import Review, ReviewDailyCount, ReviewSettings
from .tests import GOOD, REVIEWS_URL, ReviewsTestBase

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'reviews-throttles'}}


class ReviewProtectionTests(ReviewsTestBase):
    def test_reported_review_cannot_be_edited_or_deleted_by_its_author(self):
        review = self.make_review()
        detail = f'{REVIEWS_URL}{review.id}/'
        self.client.force_authenticate(self.buyer)
        Report.objects.create(
            target_type='review', target_id=review.id, reporter=self.other, reason=Report.REASON_AUTRE,
        )
        for response in (
            self.client.patch(detail, {'content': 'Je réécris mon avis signalé.'}), self.client.delete(detail),
        ):
            self.assertEqual((response.status_code, response.data['code']), (403, 'review_locked'))
        # Un signalement clos libère l'avis.
        Report.objects.update(status=Report.STATUS_TRAITE)
        response = self.client.patch(detail, {'content': 'Je précise mon avis après traitement.'})
        self.assertEqual(response.status_code, 200)

    def test_hidden_review_cannot_be_edited_or_deleted_by_its_author(self):
        review = self.make_review(is_hidden=True)
        detail = f'{REVIEWS_URL}{review.id}/'
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.patch(detail, {'content': 'Je réécris mon avis masqué.'}).status_code, 403)
        self.assertEqual(self.client.delete(detail).data['code'], 'review_locked')
        self.assertTrue(Review.objects.filter(pk=review.pk).exists())
        self.assertFalse(self.client.get(detail).data['can_edit'])


class ReviewQuotaTests(ReviewsTestBase):
    def new_offer(self, i):
        seller = User.objects.create_user(email=f'v{i}@example.com', password='x', full_name=f'V{i}')
        offer = self.make_offer(seller, f'Annonce numéro {i} ici')
        self.make_contact(offer)
        return offer

    def post(self, offer):
        return self.client.post(REVIEWS_URL, {'post': str(offer.id), **GOOD})

    def test_deleted_reviews_still_count_in_the_daily_limit(self):
        self.client.force_authenticate(self.buyer)
        for i in range(5):
            created = self.post(self.new_offer(i))
            self.assertEqual(created.status_code, 201, created.data)
            self.client.delete(f"{REVIEWS_URL}{created.data['id']}/")
        self.assertEqual(Review.objects.count(), 0)
        self.assertEqual(ReviewDailyCount.objects.get(user=self.buyer).count, 5)
        response = self.post(self.new_offer(9))
        self.assertEqual((response.status_code, response.data['code']), (429, 'daily_limit'))
        self.assertEqual(response.data['detail'], 'Vous avez atteint la limite de 5 avis par jour.')

    def test_daily_limit_comes_from_the_settings(self):
        ReviewSettings.objects.update_or_create(pk=ReviewSettings.SINGLETON_ID, defaults={'daily_review_limit': 2})
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post(self.new_offer(1)).status_code, 201)
        self.assertEqual(self.post(self.new_offer(2)).status_code, 201)
        response = self.post(self.new_offer(3))
        self.assertEqual((response.status_code, response.data['code']), (429, 'daily_limit'))
        self.assertIn('limite de 2 avis', response.data['detail'])

    def test_failed_creation_does_not_consume_the_quota(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD, 'content': 'Court'})
        self.assertFalse(ReviewDailyCount.objects.filter(user=self.buyer, count__gt=0).exists())

    def test_duplicate_review_race_gives_a_clean_409_and_keeps_the_quota(self):
        self.make_review()
        self.client.force_authenticate(self.buyer)
        offer_info = services.marketplace_services.get_offer(self.offer.id)
        contact = services.marketplace_services.get_review_contact(self.offer.id, self.buyer.id)
        # La vérification préalable est contournée (deux requêtes simultanées) : la contrainte répond.
        with mock.patch.object(services, 'ensure_can_review', return_value=(offer_info, contact)):
            response = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD})
        self.assertEqual((response.status_code, response.data['code']), (409, 'already_reviewed'))
        self.assertEqual(Review.objects.count(), 1)
        self.assertFalse(ReviewDailyCount.objects.filter(user=self.buyer, count__gt=0).exists())


class ReviewAuditTests(ReviewsTestBase):
    def make_admin(self):
        return User.objects.create_user(email='admin@example.com', password='x', full_name='Admin', is_staff=True)

    def test_hiding_through_the_service_is_audited(self):
        review = self.make_review()
        admin = self.make_admin()
        services.set_review_hidden(review, True, admin)
        hidden = AuditLog.objects.filter(action='REVIEW_HIDDEN', actor=admin, target_id=review.id)
        self.assertEqual(hidden.count(), 1)
        services.set_review_hidden(review, True, admin)  # sans changement : pas de doublon
        self.assertEqual(hidden.count(), 1)
        services.set_review_hidden(review, False, admin)
        self.assertTrue(AuditLog.objects.filter(action='REVIEW_UNHIDDEN', actor=admin).exists())

    def test_admin_save_and_delete_are_audited(self):
        admin = self.make_admin()
        request = RequestFactory().post('/admin/')
        request.user = admin
        model_admin = ReviewAdmin(Review, admin_site)
        review = self.make_review()
        other = self.make_review(user=self.other)

        review.is_hidden = True
        model_admin.save_model(request, review, mock.Mock(changed_data=['is_hidden']), True)
        actions = list(AuditLog.objects.filter(actor=admin).values_list('action', flat=True))
        self.assertEqual(sorted(actions), ['REVIEW_ADMIN_UPDATED', 'REVIEW_HIDDEN'])
        review.refresh_from_db()
        self.assertFalse(review.counts_for_seller)  # drapeau recalculé par l'admin

        model_admin.delete_model(request, review)
        model_admin.delete_queryset(request, Review.objects.filter(pk=other.pk))
        self.assertEqual(AuditLog.objects.filter(action='REVIEW_ADMIN_DELETED').count(), 2)
        self.assertEqual(Review.objects.count(), 0)

    def test_admin_has_no_add_and_shows_contact_proof_read_only(self):
        request = RequestFactory().get('/admin/')
        request.user = self.make_admin()
        request.user.is_superuser = True
        model_admin = ReviewAdmin(Review, admin_site)
        review = self.make_review()
        self.assertFalse(model_admin.has_add_permission(request))
        for name in ('contact_channel', 'contact_recorded_at', 'counts_for_seller'):
            self.assertIn(name, model_admin.get_readonly_fields(request, review))

    def test_settings_change_is_audited_with_old_and_new_values(self):
        admin = self.make_admin()
        request = RequestFactory().post('/admin/')
        request.user = admin
        row = ReviewSettings.get_solo()
        row.daily_review_limit = 8
        form = mock.Mock(changed_data=['daily_review_limit'], initial={'daily_review_limit': 5})
        ReviewSettingsAdmin(ReviewSettings, admin_site).save_model(request, row, form, True)
        entry = AuditLog.objects.get(action='SETTINGS_CHANGED', actor=admin)
        self.assertEqual(entry.target_id, row.pk)
        self.assertIn('daily_review_limit : 5 -> 8', entry.details)
        self.assertEqual(ReviewSettings.get_solo().daily_review_limit, 8)


@override_settings(CACHES=LOCMEM)
class ReviewThrottleTests(ReviewsTestBase):
    def test_review_creation_is_limited_and_answers_429_throttled(self):
        cache.clear()
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        body = {'post': str(self.offer.id), **GOOD}
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'review': '1/hour'}):
            self.assertEqual(self.client.post(REVIEWS_URL, body).status_code, 201)
            second = self.client.post(REVIEWS_URL, body)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(second.data['code'], 'throttled')
        self.assertIn('Retry-After', second)


class ReviewQueryCountTests(ReviewsTestBase):
    def measure(self, url):
        self.client.get(url)  # amorce les réglages à ligne unique
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_review_list_has_a_constant_query_count(self):
        self.client.force_authenticate(self.buyer)
        self.make_review()
        few = self.measure(REVIEWS_URL)
        for i in range(1, 6):
            seller = User.objects.create_user(email=f'q{i}@example.com', password='x', full_name=f'S{i}')
            self.make_review(offer=self.make_offer(seller, f'Annonce numéro {i} à vendre'))
        self.assertEqual(few, self.measure(REVIEWS_URL))

    def test_offer_list_with_ratings_has_a_constant_query_count(self):
        for i in range(1, 6):
            self.make_review(offer=self.make_offer(self.seller, f'Annonce notée numéro {i}'), user=self.buyer)
        url = '/api/marketplace/posts/'
        few = self.measure(url)
        for i in range(6, 12):
            offer = self.make_offer(self.seller, f'Annonce notée numéro {i}')
            self.make_review(offer=offer, user=self.other)
        self.assertEqual(few, self.measure(url))
