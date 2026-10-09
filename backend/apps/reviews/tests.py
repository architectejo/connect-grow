import uuid
from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Category, City, Commune
from apps.identity.models import User
from apps.marketplace.models import ContactEvent, Offer
from apps.marketplace.tests import make_test_image
from apps.moderation.models import Report
from apps.notifications.models import Notification

from .models import Deal, Review, TrustScoreSettings


class ReviewsTestBase(APITestCase):
    def setUp(self):
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')
        self.other = User.objects.create_user(email='other@example.com', password='x', full_name='Tiers')
        self.offer = self.make_offer(self.seller)

    def make_offer(self, seller, title='Un joli canapé à vendre'):
        return Offer.objects.create(
            seller=seller, category_id=self.category.id, commune_id=self.commune.id,
            title=title, description='Description suffisamment longue pour le CDC.',
            price=100, main_image=make_test_image(),
        )

    def make_confirmed_deal(self, offer=None, initiator=None, counterparty=None):
        deal = Deal.objects.create(
            offer_id=(offer or self.offer).id, initiator=initiator or self.buyer,
            counterparty=counterparty or self.seller,
        )
        deal.confirm()
        return deal

    def make_review(self, deal=None, user=None, reviewed_user=None, **kwargs):
        deal = deal or self.make_confirmed_deal()
        defaults = dict(
            deal=deal, offer_id=deal.offer_id, user=user or self.buyer, reviewed_user=reviewed_user or self.seller,
            content='Avis suffisamment long pour être valide.', rating=4,
        )
        defaults.update(kwargs)
        return Review.objects.create(**defaults)


class ReviewCreationGateTests(ReviewsTestBase):
    url = '/api/interactions/reviews/'

    def post_review(self, deal, **extra):
        payload = {'deal': str(deal.id), 'content': 'Très bon vendeur, je recommande.', 'rating': 5}
        payload.update(extra)
        return self.client.post(self.url, payload)

    def test_review_requires_a_deal(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post(self.url, {
            'post': str(self.offer.id), 'content': 'Très bon vendeur, je recommande.', 'rating': 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_requires_a_confirmed_deal(self):
        deal = Deal.objects.create(offer_id=self.offer.id, initiator=self.buyer, counterparty=self.seller)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post_review(deal).status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirmed_deal_allows_review(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        response = self.post_review(deal)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(str(response.data['reviewed_user_id']), str(self.seller.id))
        self.assertEqual(str(response.data['post']), str(self.offer.id))
        self.assertEqual(set(response.data), {
            'id', 'post', 'deal', 'user_id', 'user_name', 'reviewed_user_id', 'content', 'rating',
            'reply_content', 'reply_at', 'created_at', 'is_post_owner', 'can_edit',
        })
        # L'évalué est prévenu.
        self.assertEqual(Notification.objects.get(user=self.seller).notification_type, 'COMMENT')

    def test_stranger_to_the_deal_cannot_review(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.post_review(deal).status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_one_review_per_party_per_deal(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        self.post_review(deal)
        response = self.post_review(deal, content='Deuxième avis sur la même affaire.', rating=4)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_both_parties_can_review_the_same_deal(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        r1 = self.post_review(deal)
        self.client.force_authenticate(self.seller)
        r2 = self.post_review(deal, content='Acheteur sérieux et ponctuel.')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(r2.data['reviewed_user_id']), str(self.buyer.id))

    def test_content_too_short_is_rejected(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post_review(deal, content='Court').status_code, status.HTTP_400_BAD_REQUEST)

    def test_rating_out_of_bounds_is_rejected(self):
        deal = self.make_confirmed_deal()
        self.client.force_authenticate(self.buyer)
        response = self.post_review(deal, content='Contenu suffisamment long pour être valide.', rating=7)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_cannot_create_but_can_list(self):
        deal = self.make_confirmed_deal()
        self.assertEqual(self.post_review(deal).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_200_OK)

    def test_review_of_a_purged_offer_does_not_crash(self):
        """L'offre de l'affaire n'existe plus : l'avis reste possible, sans lien ni titre."""
        deal = self.make_confirmed_deal()
        self.offer.delete()
        self.client.force_authenticate(self.buyer)
        response = self.post_review(deal)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNone(response.data['post'])
        self.assertFalse(response.data['is_post_owner'])


class ReviewDailyLimitTests(ReviewsTestBase):
    def test_sixth_review_in_one_day_is_rejected(self):
        self.client.force_authenticate(self.buyer)
        for i in range(5):
            seller = User.objects.create_user(email=f'seller{i}@example.com', password='x', full_name=f'V{i}')
            deal = self.make_confirmed_deal(offer=self.make_offer(seller, f'Annonce numéro {i} à vendre'), counterparty=seller)
            response = self.client.post('/api/interactions/reviews/', {
                'deal': str(deal.id), 'content': f'Avis numéro {i} suffisamment long.', 'rating': 5,
            })
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        seller = User.objects.create_user(email='seller5@example.com', password='x', full_name='V5')
        sixth = self.make_confirmed_deal(offer=self.make_offer(seller, 'Sixième annonce du jour'), counterparty=seller)
        response = self.client.post('/api/interactions/reviews/', {
            'deal': str(sixth.id), 'content': 'Sixième avis, devrait être refusé.', 'rating': 5,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ReviewEditWindowTests(ReviewsTestBase):
    def test_can_edit_within_48_hours(self):
        review = self.make_review()
        self.client.force_authenticate(self.buyer)
        response = self.client.patch(f'/api/interactions/reviews/{review.id}/', {'content': 'Avis modifié à temps.'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_cannot_edit_after_48_hours(self):
        review = self.make_review()
        Review.objects.filter(pk=review.pk).update(created_at=timezone.now() - timedelta(hours=49))
        self.client.force_authenticate(self.buyer)
        response = self.client.patch(f'/api/interactions/reviews/{review.id}/', {'content': 'Trop tard pour modifier.'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_the_author_edits_or_deletes(self):
        review = self.make_review()
        url = f'/api/interactions/reviews/{review.id}/'
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(url, {'content': 'Avis détourné par un tiers.'}).status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_204_NO_CONTENT)

    def test_author_cannot_write_a_reply_on_their_own_review(self):
        review = self.make_review()
        self.client.force_authenticate(self.buyer)
        self.client.patch(f'/api/interactions/reviews/{review.id}/', {'reply_content': 'Fausse réponse'})
        review.refresh_from_db()
        self.assertIsNone(review.reply_content)


class ReviewReplyTests(ReviewsTestBase):
    def test_reviewed_user_can_reply(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        response = self.client.post(f'/api/interactions/reviews/{review.id}/reply/', {
            'reply_content': 'Merci pour votre confiance !',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['reply_content'], 'Merci pour votre confiance !')
        self.assertEqual(Notification.objects.get(user=self.buyer).notification_type, 'SYSTEM')

    def test_stranger_cannot_reply(self):
        review = self.make_review()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(f'/api/interactions/reviews/{review.id}/reply/', {
            'reply_content': 'Je réponds à mon propre avis.',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reply_is_required_and_bounded(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        url = f'/api/interactions/reviews/{review.id}/reply/'
        self.assertEqual(self.client.post(url, {'reply_content': '  '}).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post(url, {}).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.post(url, {'reply_content': 'x' * 501}).status_code, status.HTTP_400_BAD_REQUEST)

    def test_reply_to_a_review_of_a_purged_offer(self):
        review = self.make_review()
        self.offer.delete()
        self.client.force_authenticate(self.seller)
        response = self.client.post(f'/api/interactions/reviews/{review.id}/reply/', {'reply_content': 'Merci !'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class ReviewVisibilityTests(ReviewsTestBase):
    url = '/api/interactions/reviews/'

    def test_list_filters_by_offer_and_hides_moderated_reviews(self):
        shown = self.make_review()
        hidden = self.make_review(
            deal=self.make_confirmed_deal(initiator=self.other), user=self.other, is_hidden=True,
        )
        other_offer = self.make_offer(self.buyer, 'Une autre annonce à vendre')
        elsewhere = self.make_review(deal=self.make_confirmed_deal(offer=other_offer, initiator=self.seller, counterparty=self.buyer),
                                     user=self.seller, reviewed_user=self.buyer)

        response = self.client.get(self.url, {'post': str(self.offer.id)})
        self.assertEqual([r['id'] for r in response.data], [str(shown.id)])
        self.assertEqual(response.data[0]['post'], str(self.offer.id))
        everything = {r['id'] for r in self.client.get(self.url).data}
        self.assertEqual(everything, {str(shown.id), str(elsewhere.id)})
        self.assertEqual(self.client.get(self.url, {'post': 'pas-un-uuid'}).data, [])

        # Un avis masqué n'est pas public par son identifiant ; son auteur le voit encore.
        detail = f'{self.url}{hidden.id}/'
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_200_OK)

    def test_list_flags_for_the_connected_user(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        item = self.client.get(self.url).data[0]
        self.assertTrue(item['is_post_owner'])
        self.assertFalse(item['can_edit'])
        self.client.force_authenticate(self.buyer)
        item = self.client.get(self.url).data[0]
        self.assertTrue(item['can_edit'])
        self.assertEqual(item['id'], str(review.id))

    def test_review_of_a_purged_offer_stays_listed_without_link(self):
        review = self.make_review()
        self.offer.delete()
        item = self.client.get(self.url).data[0]
        self.assertEqual(item['id'], str(review.id))
        self.assertIsNone(item['post'])


class DealCreationTests(ReviewsTestBase):
    url = '/api/reputation/deals/'

    def setUp(self):
        super().setUp()
        ContactEvent.objects.create(offer=self.offer, sender=self.buyer, message='Bonjour, toujours dispo ?')

    def declare(self, user, counterparty, offer=None):
        self.client.force_authenticate(user)
        return self.client.post(self.url, {'post': str((offer or self.offer).id), 'counterparty': str(counterparty.id)})

    def test_buyer_can_declare_deal_with_seller(self):
        response = self.declare(self.buyer, self.seller)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], Deal.STATUS_PENDING)
        self.assertEqual(response.data['post_title'], self.offer.title)
        self.assertEqual(Deal.objects.get().initiator, self.buyer)

    def test_seller_can_declare_deal_with_a_contact(self):
        self.assertEqual(self.declare(self.seller, self.buyer).status_code, status.HTTP_201_CREATED)

    def test_cannot_declare_deal_with_self(self):
        self.assertEqual(self.declare(self.buyer, self.buyer).status_code, status.HTTP_400_BAD_REQUEST)

    def test_buyer_cannot_declare_deal_with_uninvolved_user(self):
        self.assertEqual(self.declare(self.buyer, self.other).status_code, status.HTTP_400_BAD_REQUEST)

    def test_seller_cannot_declare_deal_with_non_contact(self):
        self.assertEqual(self.declare(self.seller, self.other).status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_who_never_contacted_cannot_declare(self):
        self.assertEqual(self.declare(self.other, self.seller).status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_offer_is_rejected(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post(self.url, {'post': str(uuid.uuid4()), 'counterparty': str(self.seller.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('post', response.data)

    def test_deals_are_private_to_their_parties(self):
        self.declare(self.buyer, self.seller)
        self.client.force_authenticate(self.other)
        self.assertEqual(len(self.client.get(self.url).data), 0)
        self.client.force_authenticate(self.seller)
        data = self.client.get(self.url).data
        self.assertEqual(len(data), 1)
        self.assertEqual(set(data[0]), {
            'id', 'post', 'post_title', 'initiator', 'initiator_name', 'counterparty', 'counterparty_name',
            'status', 'created_at', 'confirmed_at',
        })

    def test_anonymous_is_refused(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)


class DealConfirmationTests(ReviewsTestBase):
    def setUp(self):
        super().setUp()
        self.deal = Deal.objects.create(offer_id=self.offer.id, initiator=self.buyer, counterparty=self.seller)

    def test_only_counterparty_can_confirm(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post(f'/api/reputation/deals/{self.deal.id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_counterparty_confirms(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(f'/api/reputation/deals/{self.deal.id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.status, Deal.STATUS_CONFIRMED)
        self.assertIsNotNone(self.deal.confirmed_at)

    def test_counterparty_declines(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(f'/api/reputation/deals/{self.deal.id}/decline/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.status, Deal.STATUS_DECLINED)

    def test_cannot_confirm_twice(self):
        self.deal.confirm()
        self.client.force_authenticate(self.seller)
        response = self.client.post(f'/api/reputation/deals/{self.deal.id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stranger_cannot_see_or_confirm(self):
        self.client.force_authenticate(self.other)
        response = self.client.post(f'/api/reputation/deals/{self.deal.id}/confirm/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TrustScoreTests(ReviewsTestBase):
    def test_review_creation_updates_trust_score(self):
        self.make_review(rating=5)
        self.seller.refresh_from_db()
        row = TrustScoreSettings.get_solo()
        expected = (row.neutral_weight * row.neutral_rating + 5) / (row.neutral_weight + 1)
        self.assertAlmostEqual(self.seller.trust_score, round(expected, 2))
        self.assertEqual(self.seller.reviews_count, 1)

    def test_deleting_review_recomputes_trust_score(self):
        review = self.make_review(rating=1)
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.reviews_count, 1)

        review.delete()
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.reviews_count, 0)
        self.assertEqual(self.seller.trust_score, 3.5)  # retombe à la note neutre

    def test_hidden_review_excluded_from_trust_score(self):
        review = self.make_review(rating=1)
        self.seller.refresh_from_db()
        self.assertLess(self.seller.trust_score, 3.5)

        review.is_hidden = True
        review.save()
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.trust_score, 3.5)
        self.assertEqual(self.seller.reviews_count, 0)

    def test_new_review_refreshes_seller_offers_visibility_score(self):
        before = self.offer.visibility_score
        self.make_review(rating=5)
        self.offer.refresh_from_db()
        self.assertNotEqual(before, self.offer.visibility_score)

    def test_deleting_the_reviewed_account_does_not_fail(self):
        self.make_review(rating=5)
        self.seller.delete()
        self.assertEqual(Review.objects.count(), 0)

    def test_min_reviews_to_display_comes_from_settings(self):
        from . import services

        self.assertEqual(services.get_min_reviews_to_display(), 3)
        row = TrustScoreSettings.get_solo()
        row.min_reviews_to_display = 7
        row.save()
        self.assertEqual(services.get_min_reviews_to_display(), 7)


class CrossedReviewsDetectionTests(ReviewsTestBase):
    def exchange_reviews(self, times):
        last = None
        for i in range(times):
            offer = self.make_offer(self.seller, f'Une annonce quelconque numéro {i}')
            deal = self.make_confirmed_deal(offer=offer)
            self.make_review(deal=deal, user=self.buyer, reviewed_user=self.seller, rating=5)
            last = self.make_review(deal=deal, user=self.seller, reviewed_user=self.buyer, rating=5)
        return last

    def reports(self):
        return Report.objects.filter(
            target_type='review', reason=Report.REASON_AVIS_CROISES,
        )

    def test_three_mutual_deals_trigger_a_report(self):
        last_review = self.exchange_reviews(3)
        self.assertTrue(self.reports().filter(target_id=last_review.id).exists())
        self.assertIsNone(self.reports().first().reporter)

    def test_two_mutual_deals_do_not_trigger_a_report(self):
        self.exchange_reviews(2)
        self.assertFalse(self.reports().exists())

    def test_a_review_is_reported_only_once(self):
        from . import services

        last_review = self.exchange_reviews(3)
        count = self.reports().count()
        services.check_crossed_reviews(last_review)
        self.assertEqual(self.reports().count(), count)


class DecouplingTests(ReviewsTestBase):
    def test_offers_are_referenced_by_uuid_only(self):
        for model in (Review, Deal):
            for field in model._meta.get_fields():
                if field.is_relation and field.concrete:
                    self.assertIn(field.related_model._meta.app_label, ('reviews', 'identity'), field.name)
        self.assertEqual(Review._meta.get_field('offer_id').get_internal_type(), 'UUIDField')

    def test_purging_the_offer_keeps_reviews_and_deals(self):
        review = self.make_review()
        deal = review.deal
        Offer.objects.filter(pk=self.offer.pk).update(is_deleted=True, deleted_at=timezone.now() - timedelta(days=31))

        call_command('purge_offer_trash', verbosity=0)

        self.assertFalse(Offer.objects.filter(pk=self.offer.pk).exists())
        review.refresh_from_db()
        deal.refresh_from_db()
        # Les avis et affaires survivent (CDC 3.10) et gardent l'UUID de l'offre disparue.
        self.assertEqual(review.offer_id, self.offer.id)
        self.assertEqual(deal.offer_id, self.offer.id)
