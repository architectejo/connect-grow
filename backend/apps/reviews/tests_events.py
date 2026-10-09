"""Avis et réponses publiés comme événements de domaine, versions 2 (ADR 0003, ADR 0004)."""
from unittest import mock

from django.utils import timezone
from rest_framework import status

from apps.moderation.models import Report
from apps.notifications.models import Notification
from apps.platform_core import registry
from apps.platform_core.models import OutboxDelivery, OutboxEvent
from apps.platform_core.services import publish_event
from apps.platform_core.testing import dispatch_outbox_now

from . import services
from .models import Review
from .tests import GOOD, REVIEWS_URL, ReviewsTestBase


class ReviewEventTests(ReviewsTestBase):
    def post_review(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        return self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD})

    def test_review_is_saved_with_its_v2_event_and_the_notification_follows_the_diffusion(self):
        response = self.post_review()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        event = OutboxEvent.objects.get(event_type='reviews.review_posted')
        self.assertEqual(event.version, 2)
        self.assertEqual(event.payload, {
            'review_id': response.data['id'], 'recipient_id': str(self.seller.pk),
            'author_id': str(self.buyer.pk), 'offer_id': str(self.offer.id), 'offer_title': self.offer.title,
            'seller_context_type': 'USER', 'seller_context_id': str(self.seller.pk),
        })
        self.assertNotIn('Acheteur', str(event.payload))  # ni nom ni extrait dans l'outbox
        self.assertNotIn('recommande', str(event.payload))
        self.assertFalse(Notification.objects.exists())  # rien n'est écrit chez notifications avant la diffusion
        dispatch_outbox_now()
        dispatch_outbox_now()
        notification = Notification.objects.get()
        self.assertEqual((notification.user, notification.notification_type), (self.seller, 'COMMENT'))
        self.assertEqual(notification.link, f'/post/{self.offer.id}')
        self.assertEqual(
            notification.content, 'Acheteur a laissé un avis : Très bon vendeur, je recommande....',
        )

    def test_a_refused_review_publishes_nothing(self):
        self.make_review()  # déjà un avis de l'acheteur pour cette annonce
        OutboxEvent.objects.all().delete()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD})
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_failing_notification_keeps_the_review_and_is_retried(self):
        original = registry.get_subscriber('notifications.notify_review_posted')
        failing = registry.Subscriber(
            original.event_type, original.name, mock.Mock(side_effect=ValueError('x')), original.versions,
        )
        with mock.patch.dict(registry._BY_NAME, {original.name: failing}):
            self.assertEqual(self.post_review().status_code, status.HTTP_201_CREATED)
            dispatch_outbox_now()
        self.assertEqual((Review.objects.count(), Notification.objects.count()), (1, 0))
        OutboxDelivery.objects.update(next_attempt_at=timezone.now())
        dispatch_outbox_now()
        self.assertEqual(Notification.objects.count(), 1)

    def test_subscriber_refuses_version_1_payloads(self):
        subscriber = registry.get_subscriber('notifications.notify_review_posted')
        self.assertEqual(subscriber.versions, (2,))
        crossed = registry.get_subscriber('moderation.file_crossed_reviews_report')
        self.assertEqual(crossed.versions, (2,))

    def test_reply_event_is_published_in_the_reply_transaction(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        url = f'{REVIEWS_URL}{review.id}/reply/'
        self.assertEqual(self.client.post(url, {'reply_content': 'Merci !'}).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(url, {'reply_content': 'Encore'}).status_code, status.HTTP_409_CONFLICT)
        replied = OutboxEvent.objects.filter(event_type='reviews.review_replied')
        self.assertEqual(replied.count(), 1)  # pas de doublon
        self.assertEqual(replied.get().version, 1)
        self.assertEqual(replied.get().payload['replier_id'], str(self.seller.pk))
        self.assertNotIn('Vendeur', str(replied.get().payload))
        dispatch_outbox_now()
        notification = Notification.objects.get()
        self.assertEqual((notification.user, notification.notification_type), (self.buyer, 'SYSTEM'))
        self.assertEqual(notification.content, f'Vendeur a répondu à votre avis sur {self.offer.title}')

    def test_review_deleted_before_the_diffusion_sends_no_notification(self):
        self.assertEqual(self.post_review().status_code, status.HTTP_201_CREATED)
        Review.objects.all().delete()
        dispatch_outbox_now()
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(OutboxEvent.objects.get(event_type='reviews.review_posted').status, 'done')

    def test_notification_for_a_review_on_a_deleted_offer_has_no_link(self):
        review = self.make_review()
        OutboxEvent.objects.all().delete()
        from django.db import transaction

        offer_id = self.offer.id
        self.offer.delete()
        with transaction.atomic():
            services.publish_review_posted(review, self.buyer)
        dispatch_outbox_now()
        notification = Notification.objects.get()
        self.assertEqual(notification.title, 'Nouvel avis sur une annonce supprimée')
        self.assertFalse(notification.link)
        self.assertEqual(review.offer_id, offer_id)


class CrossedReviewsEventTests(ReviewsTestBase):
    def exchange(self, count):
        last = None
        for i in range(count):
            last = self.make_review(offer=self.make_offer(self.seller, f'Une annonce quelconque numéro {i}'))
            from django.db import transaction

            with transaction.atomic():
                services.check_crossed_reviews(last)
        return last

    def test_detection_publishes_a_v2_event_and_moderation_files_one_report(self):
        last = self.exchange(3)
        events = OutboxEvent.objects.filter(event_type='reviews.crossed_reviews_detected')
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.payload['review_id'], str(last.pk))
        self.assertEqual((event.payload['reviews_count'], event.payload['window_days']), (3, 30))
        self.assertNotIn('deals_count', event.payload)
        self.assertFalse(Report.objects.exists())
        dispatch_outbox_now()
        report = Report.objects.get()
        self.assertEqual((report.target_type, report.target_id, report.reporter), ('review', last.pk, None))
        self.assertIn('3 avis distincts sur 30 jours', report.description)

    def test_version_1_event_is_dead_lettered(self):
        from django.db import transaction

        with transaction.atomic():
            publish_event(
                'reviews.crossed_reviews_detected', aggregate_type='review', aggregate_id=self.seller.pk,
                payload={'review_id': str(self.seller.pk)},
            )
        OutboxEvent.objects.update(version=1)
        dispatch_outbox_now()
        self.assertEqual(OutboxDelivery.objects.get().status, 'dead')
        self.assertFalse(Report.objects.exists())
