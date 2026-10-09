"""Durcissement R2 : avis protégés, quota quotidien, réponse unique, audit, limites de débit, requêtes."""
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle

from apps.identity.models import User
from apps.marketplace.models import ContactEvent, Offer
from apps.moderation.models import AuditLog, Report

from . import services
from .admin import ReviewAdmin
from .models import Deal, Review, ReviewDailyCount
from .tests import ReviewsTestBase

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'reviews-throttles'}}


class ReviewProtectionTests(ReviewsTestBase):
    url = '/api/interactions/reviews/'

    def test_reported_review_cannot_be_edited_or_deleted_by_its_author(self):
        review = self.make_review()
        detail = f'{self.url}{review.id}/'
        self.client.force_authenticate(self.buyer)
        Report.objects.create(
            content_type=ContentType.objects.get_for_model(Review), object_id=str(review.id),
            reporter=self.other, reason=Report.REASON_AUTRE,
        )
        self.assertEqual(self.client.patch(detail, {'content': 'Je réécris mon avis signalé.'}).status_code, 403)
        self.assertEqual(self.client.delete(detail).status_code, 403)
        # Un signalement clos libère l'avis.
        Report.objects.update(status=Report.STATUS_TRAITE)
        response = self.client.patch(detail, {'content': 'Je précise mon avis après traitement.'})
        self.assertEqual(response.status_code, 200)

    def test_hidden_review_cannot_be_edited_or_deleted_by_its_author(self):
        review = self.make_review(is_hidden=True)
        detail = f'{self.url}{review.id}/'
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.patch(detail, {'content': 'Je réécris mon avis masqué.'}).status_code, 403)
        self.assertEqual(self.client.delete(detail).status_code, 403)
        self.assertTrue(Review.objects.filter(pk=review.pk).exists())

    def test_seller_reply_is_written_only_once(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        url = f'{self.url}{review.id}/reply/'
        self.assertEqual(self.client.post(url, {'reply_content': 'Merci beaucoup !'}).status_code, 200)
        again = self.client.post(url, {'reply_content': 'Autre réponse'})
        self.assertEqual(again.status_code, 409)
        review.refresh_from_db()
        self.assertEqual(review.reply_content, 'Merci beaucoup !')


class ReviewQuotaTests(ReviewsTestBase):
    url = '/api/interactions/reviews/'

    def new_deal(self, i):
        seller = User.objects.create_user(email=f'v{i}@example.com', password='x', full_name=f'V{i}')
        return self.make_confirmed_deal(offer=self.make_offer(seller, f'Annonce numéro {i} ici'), counterparty=seller)

    def test_deleted_reviews_still_count_in_the_daily_limit(self):
        self.client.force_authenticate(self.buyer)
        for i in range(5):
            created = self.client.post(
                self.url, {'deal': str(self.new_deal(i).id), 'content': f'Avis numéro {i} assez long.', 'rating': 5},
            )
            self.assertEqual(created.status_code, 201, created.data)
            self.client.delete(f"{self.url}{created.data['id']}/")
        self.assertEqual(Review.objects.count(), 0)
        self.assertEqual(ReviewDailyCount.objects.get(user=self.buyer).count, 5)
        response = self.client.post(
            self.url, {'deal': str(self.new_deal(9).id), 'content': 'Un sixième avis du jour.', 'rating': 5},
        )
        self.assertEqual(response.status_code, 400)

    def test_failed_creation_does_not_consume_the_quota(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        self.client.post(self.url, {'deal': str(deal.id), 'content': 'Court', 'rating': 5})
        self.assertFalse(ReviewDailyCount.objects.filter(user=self.buyer, count__gt=0).exists())

    def test_duplicate_review_race_gives_a_clean_400_and_keeps_the_quota(self):
        deal = self.make_confirmed_deal()
        self.make_review(deal=deal)
        self.client.force_authenticate(self.buyer)
        # La vérification préalable est contournée (deux requêtes simultanées) : la contrainte répond.
        with mock.patch.object(services, 'validate_new_review', return_value=self.seller):
            response = self.client.post(
                self.url, {'deal': str(deal.id), 'content': 'Deuxième avis simultané.', 'rating': 4},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.filter(deal=deal).count(), 1)
        self.assertFalse(ReviewDailyCount.objects.filter(user=self.buyer, count__gt=0).exists())


class TrustRecomputeTests(ReviewsTestBase):
    def test_trust_score_is_recomputed_only_when_rating_or_visibility_changes(self):
        review = self.make_review(rating=4)
        with mock.patch.object(services, 'recompute_trust_score') as recompute:
            review.content = 'Texte retouché mais note identique.'
            review.save()
            self.assertEqual(recompute.call_count, 0)
            review.rating = 2
            review.save()
            self.assertEqual(recompute.call_count, 1)
            review.is_hidden = True
            review.save()
            self.assertEqual(recompute.call_count, 2)
            review.save(update_fields=['reply_content'])
            self.assertEqual(recompute.call_count, 2)

    def test_a_reply_does_not_recompute(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        with mock.patch.object(services, 'recompute_trust_score') as recompute:
            self.client.post(f'/api/interactions/reviews/{review.id}/reply/', {'reply_content': 'Merci !'})
        self.assertEqual(recompute.call_count, 0)


class ReviewAuditTests(ReviewsTestBase):
    def make_admin(self):
        return User.objects.create_user(email='admin@example.com', password='x', full_name='Admin', is_staff=True)

    def test_hiding_through_the_service_is_audited_and_recomputes_the_score(self):
        review = self.make_review(rating=1)
        admin = self.make_admin()
        services.set_review_hidden(review, True, admin)
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.reviews_count, 0)
        hidden = AuditLog.objects.filter(action='REVIEW_HIDDEN', actor=admin, object_id=str(review.id))
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
        other = self.make_review(deal=self.make_confirmed_deal(initiator=self.other), user=self.other)

        review.is_hidden = True
        model_admin.save_model(request, review, mock.Mock(changed_data=['is_hidden']), True)
        actions = list(AuditLog.objects.filter(actor=admin).values_list('action', flat=True))
        self.assertEqual(sorted(actions), ['REVIEW_ADMIN_UPDATED', 'REVIEW_HIDDEN'])

        model_admin.delete_model(request, review)
        model_admin.delete_queryset(request, Review.objects.filter(pk=other.pk))
        self.assertEqual(AuditLog.objects.filter(action='REVIEW_ADMIN_DELETED').count(), 2)
        self.assertEqual(Review.objects.count(), 0)

    def test_deal_confirmation_and_refusal_are_audited(self):
        deal = Deal.objects.create(offer_id=self.offer.id, initiator=self.buyer, counterparty=self.seller)
        refused = Deal.objects.create(offer_id=self.offer.id, initiator=self.other, counterparty=self.seller)
        self.client.force_authenticate(self.seller)
        self.client.post(f'/api/reputation/deals/{deal.id}/confirm/')
        self.client.post(f'/api/reputation/deals/{refused.id}/decline/')
        confirmed = AuditLog.objects.filter(action='DEAL_CONFIRMED', actor=self.seller, object_id=str(deal.id))
        self.assertTrue(confirmed.exists())
        self.assertTrue(AuditLog.objects.filter(action='DEAL_DECLINED', object_id=str(refused.id)).exists())


class DealAvailabilityTests(ReviewsTestBase):
    def test_deal_refused_on_unavailable_offers(self):
        self.client.force_authenticate(self.buyer)
        ContactEvent.objects.create(offer=self.offer, sender=self.buyer, message='Bonjour')
        payload = {'post': str(self.offer.id), 'counterparty': str(self.seller.id)}
        for changes in ({'is_active': False}, {'is_deleted': True}, {'status': Offer.STATUS_SOLD, 'is_active': False}):
            Offer.objects.filter(pk=self.offer.pk).update(**changes)
            response = self.client.post('/api/reputation/deals/', payload)
            self.assertEqual(response.status_code, 400, changes)
            self.assertIn('post', response.data)
            Offer.objects.filter(pk=self.offer.pk).update(is_active=True, is_deleted=False, status=Offer.STATUS_ACTIVE)
        self.assertFalse(Deal.objects.exists())


@override_settings(CACHES=LOCMEM)
class ReviewThrottleTests(ReviewsTestBase):
    def test_review_and_deal_creation_are_limited(self):
        cache.clear()
        ContactEvent.objects.create(offer=self.offer, sender=self.buyer, message='Bonjour')
        self.client.force_authenticate(self.buyer)
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'deal': '1/hour', 'review': '1/hour'}):
            payload = {'post': str(self.offer.id), 'counterparty': str(self.seller.id)}
            first = self.client.post('/api/reputation/deals/', payload)
            second = self.client.post('/api/reputation/deals/', payload)
            self.assertEqual(first.status_code, 201)
            self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            self.assertIn('Retry-After', second)
            deal = self.make_confirmed_deal()
            body = {'deal': str(deal.id), 'content': 'Très bon vendeur, je recommande.', 'rating': 5}
            self.assertEqual(self.client.post('/api/interactions/reviews/', body).status_code, 201)
            self.assertEqual(self.client.post('/api/interactions/reviews/', body).status_code, 429)


class ReviewQueryCountTests(ReviewsTestBase):
    def measure(self, url):
        self.client.get(url)  # amorce les réglages à ligne unique
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def grow(self, url, i):
        seller = User.objects.create_user(email=f'q{i}{abs(hash(url))}@example.com', password='x', full_name=f'S{i}')
        offer = self.make_offer(seller, f'Annonce numéro {i} à vendre')
        deal = self.make_confirmed_deal(offer=offer, initiator=self.buyer, counterparty=seller)
        if 'reviews' in url:
            self.make_review(deal=deal)

    def test_review_and_deal_lists_have_a_constant_query_count(self):
        self.client.force_authenticate(self.buyer)
        for url in ('/api/interactions/reviews/', '/api/reputation/deals/'):
            self.grow(url, 0)
            few = self.measure(url)
            for i in range(1, 6):
                self.grow(url, i)
            self.assertEqual(few, self.measure(url), url)
