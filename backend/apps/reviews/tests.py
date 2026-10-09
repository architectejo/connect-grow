"""Avis après contact (ADR 0004, T1) : création, modification, réponse, visibilité, réglages,
avis croisés et découplage. Moyennes et drapeau vendeur : voir `tests_ratings.py`."""
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Category, City, Commune
from apps.identity.models import User
from apps.marketplace.models import ContactEvent, Offer
from apps.marketplace.tests import make_test_image
from apps.moderation.models import Report
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now

from . import services
from .models import Review, ReviewSettings

REVIEWS_URL = '/api/interactions/reviews/'
GOOD = {'offer_rating': 4, 'seller_rating': 5, 'content': 'Très bon vendeur, je recommande.'}


class ReviewsTestBase(APITestCase):
    def setUp(self):
        # Les tests de création ne portent pas sur le délai contact -> avis (tests_eligibility.py).
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(
            delay_after_contact_hours=0, min_account_age_hours=0,  # update() contourne le minimum de 1 h (tests seulement)
        )
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')
        self.other = User.objects.create_user(email='other@example.com', password='x', full_name='Tiers')
        self.offer = self.make_offer(self.seller)

    def make_offer(self, seller, title='Un joli canapé à vendre', **extra):
        return Offer.objects.create(
            seller=seller, category_id=self.category.id, commune_id=self.commune.id,
            title=title, description='Description suffisamment longue pour le CDC.',
            price=100, main_image=make_test_image(), **extra,
        )

    def make_contact(self, offer=None, user=None, channel=ContactEvent.CHANNEL_MESSAGE):
        return ContactEvent.objects.create(
            offer=offer or self.offer, sender=user or self.buyer, message='Bonjour, toujours disponible ?',
            channel=channel,
        )

    def make_review(self, offer=None, user=None, **kwargs):
        """Avis créé directement (sans passer par l'API), avec son contact si nécessaire."""
        offer = offer or self.offer
        user = user or self.buyer
        contact = ContactEvent.objects.filter(offer=offer, sender=user).order_by('created_at').first() \
            or self.make_contact(offer, user)
        defaults = dict(
            offer_id=offer.id, user=user, seller_context_type='USER', seller_context_id=offer.seller_id,
            contact_event_id=contact.id, contact_channel=contact.channel, contact_recorded_at=contact.created_at,
            offer_rating=4, seller_rating=5, content='Avis suffisamment long pour être valide.',
        )
        defaults.update(kwargs)
        review = Review.objects.create(**defaults)
        services.reconcile_seller_flag(user.pk, review.seller_context_type, review.seller_context_id)
        review.refresh_from_db()
        return review


class ReviewCreationTests(ReviewsTestBase):
    def post_review(self, post_id=None, **extra):
        payload = {'post': str(post_id or self.offer.id), **GOOD}
        payload.update(extra)
        return self.client.post(REVIEWS_URL, payload, format='json')

    def test_contact_opens_the_right_to_review(self):
        contact = self.make_contact()
        self.client.force_authenticate(self.buyer)
        response = self.post_review()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(set(response.data), {
            'id', 'post', 'user_name', 'offer_rating', 'seller_rating', 'content', 'source',
            'reply_content', 'reply_at', 'created_at', 'edited_at', 'is_post_owner', 'is_mine', 'can_edit',
            'can_delete', 'contest_report_id', 'contest_responded',
        })
        self.assertTrue(response.data['is_mine'])
        self.assertNotIn('user_id', response.data)
        self.assertEqual(response.data['post'], str(self.offer.id))
        self.assertEqual((response.data['offer_rating'], response.data['seller_rating']), (4, 5))
        self.assertEqual(response.data['source'], 'CONTACT')
        self.assertEqual(response.data['user_name'], 'Acheteur')
        self.assertIsNone(response.data['edited_at'])
        self.assertTrue(response.data['can_edit'])
        review = Review.objects.get()
        # Instantané de la preuve de contact et contexte vendeur ; jamais exposés publiquement.
        self.assertEqual(review.contact_event_id, contact.id)
        self.assertEqual((review.contact_channel, review.contact_recorded_at), ('MESSAGE', contact.created_at))
        self.assertEqual((review.seller_context_type, review.seller_context_id), ('USER', self.seller.id))
        self.assertNotIn('contact_channel', response.data)
        self.assertTrue(review.counts_for_seller)

    def test_without_contact_the_review_is_refused(self):
        self.client.force_authenticate(self.buyer)
        response = self.post_review()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'not_eligible')
        self.assertEqual(response.data['detail'], 'Vous pourrez donner votre avis après avoir contacté le vendeur.')
        self.assertFalse(Review.objects.exists())

    def test_contact_of_someone_else_does_not_count(self):
        self.make_contact(user=self.other)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post_review().data['code'], 'not_eligible')

    def test_any_contact_channel_opens_the_right_and_the_oldest_contact_is_the_proof(self):
        newer = self.make_contact(channel=ContactEvent.CHANNEL_CALL)
        older = self.make_contact(channel=ContactEvent.CHANNEL_WHATSAPP)
        ContactEvent.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=2))
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post_review().status_code, status.HTTP_201_CREATED)
        review = Review.objects.get()
        self.assertEqual((review.contact_event_id, review.contact_channel), (older.id, 'WHATSAPP'))
        self.assertNotEqual(review.contact_event_id, newer.id)

    def test_own_offer_cannot_be_reviewed(self):
        self.make_contact(user=self.seller)
        self.client.force_authenticate(self.seller)
        response = self.post_review()
        self.assertEqual((response.status_code, response.data['code']), (403, 'own_offer'))

    def test_unknown_offer_gives_the_uniform_refusal(self):
        self.client.force_authenticate(self.buyer)
        response = self.post_review(post_id=uuid.uuid4())
        self.assertEqual((response.status_code, response.data['code']), (404, 'offer_not_found'))
        self.assertEqual(response.data['detail'], 'Annonce introuvable.')

    def test_second_review_for_the_same_offer_is_409(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post_review().status_code, status.HTTP_201_CREATED)
        response = self.post_review(content='Deuxième avis sur la même annonce.')
        self.assertEqual((response.status_code, response.data['code']), (409, 'already_reviewed'))
        self.assertEqual(Review.objects.count(), 1)

    def test_database_enforces_one_review_per_author_and_offer(self):
        self.make_review()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_review()

    def test_offer_in_the_trash_or_hidden_by_moderation_is_unavailable_for_who_contacted_it(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        for changes in ({'is_deleted': True}, {'is_hidden_by_moderation': True, 'is_active': False}):
            Offer.objects.filter(pk=self.offer.pk).update(**changes)
            response = self.post_review()
            self.assertEqual((response.status_code, response.data['code']), (409, 'offer_unavailable'), changes)
            Offer.objects.filter(pk=self.offer.pk).update(
                is_deleted=False, is_hidden_by_moderation=False, is_active=True,
            )
        self.assertFalse(Review.objects.exists())

    def test_sold_offer_stays_reviewable(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        for state in ({'status': Offer.STATUS_SOLD}, {'status': Offer.STATUS_EXPIRED}, {'status': Offer.STATUS_PAUSED}):
            Review.objects.all().delete()
            Offer.objects.filter(pk=self.offer.pk).update(is_active=False, **state)
            self.assertEqual(self.post_review().status_code, status.HTTP_201_CREATED, state)

    def test_review_of_a_purged_offer_is_a_404(self):
        self.make_contact()
        offer_id = self.offer.id
        self.offer.delete()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post_review(post_id=offer_id).data['code'], 'offer_not_found')

    def test_invalid_bodies_are_rejected_with_field_errors(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        cases = [
            ({'offer_rating': 0}, 'offer_rating'), ({'offer_rating': 6}, 'offer_rating'),
            ({'seller_rating': 'abc'}, 'seller_rating'), ({'seller_rating': 4.5}, 'seller_rating'),
            ({'seller_rating': None}, 'seller_rating'),
            ({'content': 'Court'}, 'content'), ({'content': '  neuf car  '}, 'content'),
            ({'content': 'x' * 501}, 'content'), ({'content': ''}, 'content'),
            ({'post': 'pas-un-uuid'}, 'post'),
        ]
        for extra, field in cases:
            response = self.post_review(**extra)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, extra)
            self.assertIn(field, response.data, extra)
        for field in ('offer_rating', 'seller_rating', 'content', 'post'):
            payload = {'post': str(self.offer.id), **GOOD}
            del payload[field]
            response = self.client.post(REVIEWS_URL, payload, format='json')
            self.assertEqual(response.status_code, 400, field)
            self.assertIn(field, response.data)
        self.assertFalse(Review.objects.exists())

    def test_content_bounds_are_inclusive_after_strip(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post_review(content='  ' + 'a' * 10 + '  ').status_code, 201)
        Review.objects.all().delete()
        self.assertEqual(self.post_review(content='a' * 500).status_code, 201)

    def test_legacy_keys_are_ignored(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        response = self.post_review(deal=str(self.offer.id), rating=1, reviewed_user=str(self.other.id))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Review.objects.get().seller_context_id, self.seller.id)

    def test_anonymous_cannot_create_but_can_list(self):
        response = self.post_review()
        self.assertEqual((response.status_code, response.data['code']), (401, 'not_authenticated'))
        self.assertEqual(self.client.get(REVIEWS_URL).status_code, status.HTTP_200_OK)

    def test_seller_is_notified_after_the_diffusion(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        self.post_review()
        dispatch_outbox_now()
        notification = Notification.objects.get(user=self.seller)
        self.assertEqual(notification.notification_type, 'COMMENT')

    def test_put_is_not_routed(self):
        review = self.make_review()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.put(f'{REVIEWS_URL}{review.id}/', GOOD).status_code, 405)


class ReviewEditTests(ReviewsTestBase):
    def detail(self, review):
        return f'{REVIEWS_URL}{review.id}/'

    def test_author_edits_a_subset_and_edited_at_is_set(self):
        review = self.make_review()
        self.client.force_authenticate(self.buyer)
        response = self.client.patch(self.detail(review), {'seller_rating': 2, 'post': str(self.other.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data['seller_rating'], response.data['offer_rating']), (2, 4))
        self.assertIsNotNone(response.data['edited_at'])
        review.refresh_from_db()
        self.assertEqual(review.offer_id, self.offer.id)  # `post` ignoré

    def test_edit_validates_values_and_requires_a_change(self):
        review = self.make_review()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.patch(self.detail(review), {'content': 'Court'}).status_code, 400)
        self.assertEqual(self.client.patch(self.detail(review), {'offer_rating': 9}).status_code, 400)
        self.assertEqual(self.client.patch(self.detail(review), {}).status_code, 400)

    def test_edit_window_comes_from_the_settings(self):
        review = self.make_review()
        Review.objects.filter(pk=review.pk).update(created_at=timezone.now() - timedelta(hours=49))
        self.client.force_authenticate(self.buyer)
        response = self.client.patch(self.detail(review), {'content': 'Trop tard pour modifier.'})
        self.assertEqual((response.status_code, response.data['code']), (403, 'edit_window_closed'))
        self.assertFalse(self.client.get(self.detail(review)).data['can_edit'])
        ReviewSettings.objects.update_or_create(pk=ReviewSettings.SINGLETON_ID, defaults={'edit_window_hours': 72})
        self.assertEqual(self.client.patch(self.detail(review), {'content': 'Encore dans les temps.'}).status_code, 200)

    def test_only_the_author_edits_or_deletes(self):
        review = self.make_review()
        self.client.force_authenticate(self.other)
        for response in (
            self.client.patch(self.detail(review), {'content': 'Avis détourné par un tiers.'}),
            self.client.delete(self.detail(review)),
        ):
            self.assertEqual((response.status_code, response.data['code']), (403, 'not_author'))
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.delete(self.detail(review)).data['code'], 'not_author')
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.delete(self.detail(review)).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Review.objects.exists())

    def test_author_cannot_write_a_reply_on_their_own_review(self):
        review = self.make_review()
        self.client.force_authenticate(self.buyer)
        self.client.patch(self.detail(review), {'reply_content': 'Fausse réponse', 'offer_rating': 3})
        review.refresh_from_db()
        self.assertIsNone(review.reply_content)

    def test_anonymous_cannot_edit(self):
        review = self.make_review()
        self.assertEqual(self.client.patch(self.detail(review), {'offer_rating': 1}).status_code, 401)


class ReviewReplyTests(ReviewsTestBase):
    def url(self, review):
        return f'{REVIEWS_URL}{review.id}/reply/'

    def test_seller_can_reply(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        response = self.client.post(self.url(review), {'reply_content': 'Merci pour votre confiance !'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['reply_content'], 'Merci pour votre confiance !')
        self.assertTrue(response.data['is_post_owner'])
        dispatch_outbox_now()
        self.assertEqual(Notification.objects.get(user=self.buyer).notification_type, 'SYSTEM')

    def test_author_and_strangers_cannot_reply(self):
        review = self.make_review()
        for user in (self.buyer, self.other):
            self.client.force_authenticate(user)
            response = self.client.post(self.url(review), {'reply_content': 'Je réponds à cet avis.'})
            self.assertEqual((response.status_code, response.data['code']), (403, 'not_seller'))
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url(review), {'reply_content': 'Anonyme'}).status_code, 401)

    def test_reply_is_required_and_bounded(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        for body in ({'reply_content': '  '}, {}, {'reply_content': 'x' * 501}):
            response = self.client.post(self.url(review), body)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, body)
            self.assertIn('reply_content', response.data)

    def test_reply_to_a_review_of_a_purged_offer(self):
        review = self.make_review()
        self.offer.delete()
        self.client.force_authenticate(self.seller)
        response = self.client.post(self.url(review), {'reply_content': 'Merci !'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_second_reply_is_409(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        self.client.post(self.url(review), {'reply_content': 'Merci !'})
        response = self.client.post(self.url(review), {'reply_content': 'Encore merci !'})
        self.assertEqual((response.status_code, response.data['code']), (409, 'already_replied'))


class ReviewVisibilityTests(ReviewsTestBase):
    def test_list_filters_by_offer_and_seller_and_hides_moderated_reviews(self):
        shown = self.make_review()
        hidden = self.make_review(user=self.other, is_hidden=True)
        other_offer = self.make_offer(self.buyer, 'Une autre annonce à vendre')
        elsewhere = self.make_review(offer=other_offer, user=self.seller)

        by_offer = self.client.get(REVIEWS_URL, {'post': str(self.offer.id)})
        self.assertEqual([r['id'] for r in by_offer.data], [str(shown.id)])
        self.assertEqual({r['id'] for r in self.client.get(REVIEWS_URL).data}, {str(shown.id), str(elsewhere.id)})
        by_seller = self.client.get(REVIEWS_URL, {'seller': str(self.seller.id)})
        self.assertEqual([r['id'] for r in by_seller.data], [str(shown.id)])
        self.assertEqual(self.client.get(REVIEWS_URL, {'post': 'pas-un-uuid'}).data, [])
        self.assertEqual(self.client.get(REVIEWS_URL, {'seller': 'pas-un-uuid'}).data, [])

        # Un avis masqué n'est pas public par son identifiant ; son auteur le voit encore.
        detail = f'{REVIEWS_URL}{hidden.id}/'
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_200_OK)

    def test_list_is_newest_first_and_paginates_on_demand(self):
        first = self.make_review()
        second = self.make_review(user=self.other)
        Review.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(days=1))
        ids = [r['id'] for r in self.client.get(REVIEWS_URL).data]
        self.assertEqual(ids, [str(second.id), str(first.id)])
        page = self.client.get(REVIEWS_URL, {'page_size': 1}).data
        self.assertEqual((page['count'], len(page['results'])), (2, 1))

    def test_list_flags_for_the_connected_user(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        item = self.client.get(REVIEWS_URL).data[0]
        self.assertTrue(item['is_post_owner'])
        self.assertFalse(item['can_edit'])
        self.client.force_authenticate(self.buyer)
        item = self.client.get(REVIEWS_URL).data[0]
        self.assertFalse(item['is_post_owner'])
        self.assertTrue(item['can_edit'])
        self.assertEqual(item['id'], str(review.id))

    def test_author_name_is_first_name_and_initial(self):
        self.buyer.full_name = 'Marie Kabongo'
        self.buyer.save()
        self.make_review()
        self.assertEqual(self.client.get(REVIEWS_URL).data[0]['user_name'], 'Marie K.')

    def test_review_of_a_purged_offer_stays_listed_without_link(self):
        review = self.make_review()
        self.offer.delete()
        item = self.client.get(REVIEWS_URL).data[0]
        self.assertEqual(item['id'], str(review.id))
        self.assertIsNone(item['post'])
        self.assertFalse(item['is_post_owner'])


class ReviewSettingsTests(ReviewsTestBase):
    def test_defaults_match_the_adr(self):
        ReviewSettings.objects.all().delete()  # revient aux valeurs par défaut (la base de test les met à 0 h)
        row = ReviewSettings.get_solo()
        self.assertEqual(
            (row.min_reviews_to_display, row.daily_review_limit, row.edit_window_hours,
             row.delay_after_contact_hours, row.crossed_reviews_window_days, row.crossed_reviews_threshold),
            (3, 5, 48, 24, 30, 3),
        )

    def test_bounds_are_validated(self):
        for field, bad in (
            ('min_reviews_to_display', 0), ('daily_review_limit', 0), ('edit_window_hours', 0),
            ('crossed_reviews_window_days', 0), ('crossed_reviews_threshold', 1),
            ('delay_after_contact_hours', 0), ('min_account_age_hours', 721),
        ):
            row = ReviewSettings(**{field: bad})
            with self.assertRaises(ValidationError, msg=field) as caught:
                row.full_clean()
            self.assertIn(field, caught.exception.message_dict)
        ReviewSettings(delay_after_contact_hours=1, min_account_age_hours=0).full_clean()  # bornes incluses
        ReviewSettings(delay_after_contact_hours=168, min_account_age_hours=720).full_clean()


class DecouplingTests(ReviewsTestBase):
    def test_offers_are_referenced_by_uuid_only(self):
        for field in Review._meta.get_fields():
            if field.is_relation and field.concrete:
                self.assertEqual(field.related_model._meta.app_label, 'identity', field.name)
        for name in ('offer_id', 'contact_event_id', 'seller_context_id'):
            self.assertEqual(Review._meta.get_field(name).get_internal_type(), 'UUIDField')

    def test_purging_the_offer_keeps_the_reviews(self):
        review = self.make_review()
        Offer.objects.filter(pk=self.offer.pk).update(is_deleted=True, deleted_at=timezone.now() - timedelta(days=31))
        call_command('purge_offer_trash', verbosity=0)
        self.assertFalse(Offer.objects.filter(pk=self.offer.pk).exists())
        review.refresh_from_db()
        self.assertEqual(review.offer_id, self.offer.id)  # CDC 3.10 : l'avis garde l'UUID de l'offre disparue

    def test_old_deals_endpoint_is_gone(self):
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get('/api/reputation/deals/').status_code, status.HTTP_404_NOT_FOUND)


class CrossedReviewsDetectionTests(ReviewsTestBase):
    def post_as(self, user, offer):
        self.client.force_authenticate(user)
        self.make_contact(offer, user)
        return self.client.post(REVIEWS_URL, {'post': str(offer.id), **GOOD})

    def reports(self):
        return Report.objects.filter(target_type='review', reason=Report.REASON_AVIS_CROISES)

    def test_threshold_reached_through_the_api_publishes_v2_event_and_files_a_report(self):
        offers = [self.make_offer(self.seller, f'Annonce vendeur numéro {i}') for i in range(2)]
        mine = self.make_offer(self.buyer, 'Annonce de l’acheteur')
        self.assertEqual(self.post_as(self.buyer, offers[0]).status_code, 201)
        self.assertEqual(self.post_as(self.buyer, offers[1]).status_code, 201)
        self.assertFalse(OutboxEvent.objects.filter(event_type='reviews.crossed_reviews_detected').exists())
        response = self.post_as(self.seller, mine)  # troisième avis entre les deux comptes
        self.assertEqual(response.status_code, 201, response.data)
        event = OutboxEvent.objects.get(event_type='reviews.crossed_reviews_detected')
        self.assertEqual(event.version, 2)
        self.assertEqual(
            (event.payload['review_id'], event.payload['reviews_count'], event.payload['window_days']),
            (response.data['id'], 3, 30),
        )
        dispatch_outbox_now()
        report = self.reports().get()
        self.assertEqual((str(report.target_id), report.reporter), (response.data['id'], None))
        self.assertIn('3 avis distincts sur 30 jours', report.description)

    def test_below_the_threshold_nothing_is_published(self):
        offers = [self.make_offer(self.seller, f'Annonce vendeur numéro {i}') for i in range(2)]
        last = None
        for offer in offers:
            last = self.make_review(offer=offer, user=self.buyer)
        with transaction.atomic():
            services.check_crossed_reviews(last)
        self.assertFalse(OutboxEvent.objects.filter(event_type='reviews.crossed_reviews_detected').exists())

    def test_threshold_and_window_come_from_the_settings(self):
        offers = [self.make_offer(self.seller, f'Annonce vendeur numéro {i}') for i in range(2)]
        last = None
        for offer in offers:
            last = self.make_review(offer=offer, user=self.buyer)
        ReviewSettings.objects.update_or_create(
            pk=ReviewSettings.SINGLETON_ID, defaults={'crossed_reviews_threshold': 2},
        )
        with transaction.atomic():
            services.check_crossed_reviews(last)
        self.assertEqual(OutboxEvent.objects.filter(event_type='reviews.crossed_reviews_detected').count(), 1)
        ReviewSettings.objects.update(crossed_reviews_window_days=1)
        Review.objects.update(created_at=timezone.now() - timedelta(days=3))
        before = OutboxEvent.objects.count()
        with transaction.atomic():
            services.check_crossed_reviews(last)
        self.assertEqual(OutboxEvent.objects.count(), before)  # hors fenêtre

    def test_replaying_detection_does_not_duplicate_the_report(self):
        for i in range(3):
            last = self.make_review(offer=self.make_offer(self.seller, f'Annonce vendeur numéro {i}'), user=self.buyer)
            with transaction.atomic():
                services.check_crossed_reviews(last)
        dispatch_outbox_now()
        with transaction.atomic():
            services.check_crossed_reviews(last)
        dispatch_outbox_now()
        self.assertEqual(self.reports().filter(target_id=last.id).count(), 1)
