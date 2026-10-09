"""Notes affichées (moyennes calculées à la lecture) et drapeau « dernière note vendeur » (ADR 0004, 3.2 et 7.1)."""
from datetime import timedelta

from django.utils import timezone
from rest_framework import status

from apps.identity.models import User
from apps.marketplace.models import ContactEvent, Offer
from apps.moderation.models import AuditLog

from . import services
from .models import Review, ReviewSettings
from .tests import ReviewsTestBase

POSTS_URL = '/api/marketplace/posts/'

FORBIDDEN_KEYS = {
    'trust_score', 'reviews_count', 'is_new_seller', 'is_trusted_seller', 'comments_count', 'rating', 'deal',
}


class RatingAveragesTests(ReviewsTestBase):
    def reviewers(self, count):
        return [
            User.objects.create_user(email=f'r{i}@example.com', password='x', full_name=f'R{i}')
            for i in range(count)
        ]

    def rate(self, offer, ratings, key='offer_rating'):
        for user, value in zip(self.reviewers(len(ratings)), ratings):
            self.make_review(offer=offer, user=user, **{key: value})

    def detail(self, offer=None):
        return self.client.get(f'{POSTS_URL}{(offer or self.offer).id}/').data

    def test_no_review_gives_null_average_and_zero_count(self):
        data = self.detail()
        self.assertEqual(data['offer_rating'], {'average': None, 'count': 0})
        self.assertEqual(data['seller_rating'], {'average': None, 'count': 0})

    def test_average_is_null_below_the_threshold_but_count_is_exact(self):
        self.rate(self.offer, [5, 5])
        data = self.detail()
        self.assertEqual(data['offer_rating'], {'average': None, 'count': 2})
        self.assertEqual(data['seller_rating'], {'average': None, 'count': 2})

    def test_average_is_shown_from_the_threshold_and_rounded_half_up(self):
        self.rate(self.offer, [5, 4, 4, 4])  # 17 / 4 = 4,25 -> 4,3 (et non 4,2 comme round())
        self.assertEqual(self.detail()['offer_rating'], {'average': 4.3, 'count': 4})

    def test_rounding_to_one_decimal(self):
        self.rate(self.offer, [5, 5, 4])  # 4,666... -> 4,7
        self.assertEqual(self.detail()['offer_rating'], {'average': 4.7, 'count': 3})

    def test_threshold_comes_from_the_settings(self):
        self.rate(self.offer, [4, 4])
        ReviewSettings.objects.update_or_create(
            pk=ReviewSettings.SINGLETON_ID, defaults={'min_reviews_to_display': 2},
        )
        self.assertEqual(self.detail()['offer_rating'], {'average': 4.0, 'count': 2})
        ReviewSettings.objects.update(min_reviews_to_display=3)
        self.assertEqual(self.detail()['offer_rating'], {'average': None, 'count': 2})

    def test_hidden_reviews_are_excluded_from_average_and_count(self):
        self.rate(self.offer, [5, 5, 5])
        extra = self.make_review(user=self.other, offer_rating=1, seller_rating=1)
        self.assertEqual(self.detail()['offer_rating'], {'average': 4.0, 'count': 4})
        services.set_review_hidden(extra, True, self.seller)
        self.assertEqual(self.detail()['offer_rating'], {'average': 5.0, 'count': 3})
        self.assertEqual(self.detail()['seller_rating'], {'average': 5.0, 'count': 3})

    def test_offer_and_seller_ratings_are_independent_and_per_context(self):
        other_offer = self.make_offer(self.seller, 'Une seconde annonce du vendeur')
        for user, (offer_a, seller_a, offer_b, seller_b) in zip(
            self.reviewers(3), [(5, 1, 1, 1), (5, 1, 1, 1), (5, 1, 1, 1)],
        ):
            self.make_review(offer=self.offer, user=user, offer_rating=offer_a, seller_rating=seller_a)
            self.make_review(offer=other_offer, user=user, offer_rating=offer_b, seller_rating=seller_b)
        first, second = self.detail(self.offer), self.detail(other_offer)
        self.assertEqual(first['offer_rating']['average'], 5.0)
        self.assertEqual(second['offer_rating']['average'], 1.0)
        # La note vendeur est celle du vendeur (une seule dernière note par auteur), commune aux deux offres.
        self.assertEqual(first['seller_rating'], second['seller_rating'])
        self.assertEqual(first['seller_rating']['count'], 3)

    def test_ratings_are_attached_to_each_offer_of_a_list(self):
        self.rate(self.offer, [4, 4, 4])
        quiet = self.make_offer(self.other, 'Une annonce sans aucun avis')
        results = {row['id']: row for row in self.client.get(POSTS_URL).data}
        self.assertEqual(results[str(self.offer.id)]['offer_rating'], {'average': 4.0, 'count': 3})
        self.assertEqual(results[str(quiet.id)]['offer_rating'], {'average': None, 'count': 0})

    def test_old_trust_keys_are_gone_from_offers_and_sellers(self):
        self.rate(self.offer, [4, 4, 4])
        data = self.detail()
        self.assertFalse(FORBIDDEN_KEYS & set(data))
        self.assertFalse(FORBIDDEN_KEYS & set(data['seller']))
        self.assertEqual(set(data['seller']), {'id', 'full_name', 'user_type', 'date_joined', 'photo', 'business_profile'})
        self.assertIn('is_sponsored', data)

    def test_ratings_do_not_change_the_organic_score(self):
        self.rate(self.offer, [5, 5, 5])
        twin = self.make_offer(self.other, 'Une annonce jumelle sans avis')
        Offer.objects.filter(pk=twin.pk).update(created_at=self.offer.created_at)
        # Mêmes contacts (ils entrent dans l'engagement), mais aucun avis sur la jumelle.
        for sender in {c.sender for c in ContactEvent.objects.filter(offer=self.offer)}:
            self.make_contact(twin, sender)
        services.marketplace_services.refresh_all_scores()
        self.offer.refresh_from_db()
        twin.refresh_from_db()
        self.assertGreater(self.offer.visibility_score, 0)
        self.assertAlmostEqual(self.offer.visibility_score, twin.visibility_score, places=4)


class SellerFlagTests(ReviewsTestBase):
    def second_offer(self, title='Une seconde annonce du vendeur'):
        return self.make_offer(self.seller, title)

    def flags(self):
        return {r.offer_id: r.counts_for_seller for r in Review.objects.all()}

    def test_only_the_latest_seller_rating_of_an_author_counts(self):
        offer2 = self.second_offer()
        first = self.make_review(seller_rating=1)
        second = self.make_review(offer=offer2, seller_rating=5)
        Review.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=1))
        services.reconcile_seller_flag(self.buyer.pk, 'USER', self.seller.pk)
        self.assertEqual(self.flags(), {self.offer.id: False, offer2.id: True})
        summary = services.get_seller_ratings('USER', [self.seller.id])[self.seller.id]
        self.assertEqual(summary.count, 1)
        second.refresh_from_db()
        self.assertTrue(second.counts_for_seller)

    def test_each_author_counts_once_for_the_seller_average(self):
        offer2 = self.second_offer()
        self.make_review(seller_rating=1)
        self.make_review(offer=offer2, seller_rating=3)
        self.make_review(user=self.other, seller_rating=5)
        ReviewSettings.objects.update_or_create(
            pk=ReviewSettings.SINGLETON_ID, defaults={'min_reviews_to_display': 2},
        )
        summary = services.get_seller_ratings('USER', [self.seller.id])[self.seller.id]
        self.assertEqual((summary.count, summary.average), (2, 4.0))  # (3 + 5) / 2

    def test_api_creation_moves_the_flag_to_the_new_review(self):
        offer2 = self.second_offer()
        self.make_contact()
        self.make_contact(offer2)
        self.client.force_authenticate(self.buyer)
        body = {'offer_rating': 4, 'seller_rating': 2, 'content': 'Un avis tout à fait correct.'}
        first = self.client.post('/api/interactions/reviews/', {'post': str(self.offer.id), **body})
        Review.objects.filter(pk=first.data['id']).update(created_at=timezone.now() - timedelta(minutes=5))
        second = self.client.post('/api/interactions/reviews/', {'post': str(offer2.id), **body})
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertEqual(self.flags(), {self.offer.id: False, offer2.id: True})

    def test_hiding_the_latest_restores_the_previous_one_and_unhiding_reverts(self):
        offer2 = self.second_offer()
        first = self.make_review()
        second = self.make_review(offer=offer2)
        Review.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=1))
        services.reconcile_seller_flag(self.buyer.pk, 'USER', self.seller.pk)
        services.set_review_hidden(second, True, self.seller)
        self.assertEqual(self.flags(), {self.offer.id: True, offer2.id: False})
        services.set_review_hidden(second, False, self.seller)
        self.assertEqual(self.flags(), {self.offer.id: False, offer2.id: True})
        self.assertTrue(AuditLog.objects.filter(action='REVIEW_HIDDEN', target_id=second.id).exists())

    def test_deleting_the_latest_restores_the_previous_one(self):
        offer2 = self.second_offer()
        first = self.make_review()
        second = self.make_review(offer=offer2)
        Review.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=1))
        services.reconcile_seller_flag(self.buyer.pk, 'USER', self.seller.pk)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.delete(f'/api/interactions/reviews/{second.id}/').status_code, 204)
        self.assertEqual(self.flags(), {self.offer.id: True})

    def test_reconcile_is_idempotent_and_hidden_only_leaves_no_flag(self):
        review = self.make_review(is_hidden=True)
        for _ in range(2):
            services.reconcile_seller_flag(self.buyer.pk, 'USER', self.seller.pk)
        review.refresh_from_db()
        self.assertFalse(review.counts_for_seller)

    def test_editing_an_older_review_does_not_change_the_seller_average(self):
        offer2 = self.second_offer()
        first = self.make_review(seller_rating=1)
        self.make_review(offer=offer2, seller_rating=5)
        Review.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=1))
        services.reconcile_seller_flag(self.buyer.pk, 'USER', self.seller.pk)
        self.client.force_authenticate(self.buyer)
        self.client.patch(f'/api/interactions/reviews/{first.id}/', {'seller_rating': 3})
        summary = services.get_seller_ratings('USER', [self.seller.id])[self.seller.id]
        self.assertEqual(summary.count, 1)
        self.assertEqual(Review.objects.get(pk=first.pk).seller_rating, 3)
        self.assertFalse(Review.objects.get(pk=first.pk).counts_for_seller)


class DashboardRatingTests(ReviewsTestBase):
    url = '/api/marketplace/stats/dashboard/'

    def test_without_review_the_average_is_null(self):
        self.client.force_authenticate(self.seller)
        summary = self.client.get(self.url).data['summary']
        self.assertIsNone(summary['avg_rating'])
        self.assertEqual(summary['review_count'], 0)

    def test_average_has_no_display_threshold_and_ignores_hidden_reviews(self):
        self.make_review(seller_rating=5)
        hidden = self.make_review(user=self.other, seller_rating=1)
        self.client.force_authenticate(self.seller)
        summary = self.client.get(self.url).data['summary']
        self.assertEqual((summary['avg_rating'], summary['review_count']), (3.0, 2))
        services.set_review_hidden(hidden, True, self.seller)
        summary = self.client.get(self.url).data['summary']
        self.assertEqual((summary['avg_rating'], summary['review_count']), (5.0, 1))
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)
