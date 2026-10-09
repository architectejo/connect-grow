"""Avis, réponses et avis croisés publiés comme événements de domaine (ADR 0003, L0-16)."""
from unittest import mock

from django.utils import timezone
from rest_framework import status

from apps.moderation.models import Report
from apps.notifications.models import Notification
from apps.platform_core import registry
from apps.platform_core.models import OutboxDelivery, OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now

from . import services
from .models import Review
from .tests import ReviewsTestBase


class ReviewEventTests(ReviewsTestBase):
    def post_review(self, deal):
        self.client.force_authenticate(self.buyer)
        return self.client.post('/api/interactions/reviews/', {
            'deal': str(deal.id), 'content': 'Très bon vendeur, je recommande.', 'rating': 5,
        })

    def test_review_is_saved_with_its_event_and_the_notification_follows_the_diffusion(self):
        response = self.post_review(self.make_confirmed_deal())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        event = OutboxEvent.objects.get(event_type='reviews.review_posted')
        self.assertEqual(event.payload, {
            'review_id': response.data['id'], 'reviewed_user_id': str(self.seller.pk),
            'author_id': str(self.buyer.pk), 'offer_id': str(self.offer.id), 'offer_title': self.offer.title,
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
        deal = self.make_confirmed_deal()
        self.make_review(deal=deal)  # déjà un avis de l'acheteur pour cette affaire
        OutboxEvent.objects.all().delete()
        self.assertEqual(self.post_review(deal).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_failing_notification_keeps_the_review_and_is_retried(self):
        original = registry.get_subscriber('notifications.notify_review_posted')
        failing = registry.Subscriber(original.event_type, original.name, mock.Mock(side_effect=ValueError('x')), (1,))
        with mock.patch.dict(registry._BY_NAME, {original.name: failing}):
            self.assertEqual(self.post_review(self.make_confirmed_deal()).status_code, status.HTTP_201_CREATED)
            dispatch_outbox_now()
        self.assertEqual((Review.objects.count(), Notification.objects.count()), (1, 0))
        OutboxDelivery.objects.update(next_attempt_at=timezone.now())
        dispatch_outbox_now()
        self.assertEqual(Notification.objects.count(), 1)

    def test_reply_event_is_published_in_the_reply_transaction(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        url = f'/api/interactions/reviews/{review.id}/reply/'
        self.assertEqual(self.client.post(url, {'reply_content': 'Merci !'}).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(url, {'reply_content': 'Encore'}).status_code, status.HTTP_409_CONFLICT)
        replied = OutboxEvent.objects.filter(event_type='reviews.review_replied')
        self.assertEqual(replied.count(), 1)  # pas de doublon
        self.assertEqual(replied.get().payload['replier_id'], str(self.seller.pk))
        self.assertNotIn('Vendeur', str(replied.get().payload))
        dispatch_outbox_now()
        notification = Notification.objects.get()
        self.assertEqual((notification.user, notification.notification_type), (self.buyer, 'SYSTEM'))
        self.assertEqual(notification.content, f'Vendeur a répondu à votre avis sur {self.offer.title}')

    def test_review_deleted_before_the_diffusion_sends_no_notification(self):
        self.assertEqual(self.post_review(self.make_confirmed_deal()).status_code, status.HTTP_201_CREATED)
        Review.objects.all().delete()
        dispatch_outbox_now()
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(OutboxEvent.objects.get(event_type='reviews.review_posted').status, 'done')

    def test_notification_for_a_review_on_a_deleted_offer_has_no_link(self):
        from apps.marketplace import services as marketplace_services
        from apps.marketplace.models import Offer

        deal = self.make_confirmed_deal()
        marketplace_services.delete_offers(Offer.objects.filter(pk=self.offer.pk))
        self.assertEqual(self.post_review(deal).status_code, status.HTTP_201_CREATED)
        dispatch_outbox_now()
        notification = Notification.objects.get()
        self.assertEqual(notification.title, 'Nouvel avis sur une annonce supprimée')
        self.assertFalse(notification.link)


class CrossedReviewsEventTests(ReviewsTestBase):
    def exchange(self, times):
        last = None
        for i in range(times):
            deal = self.make_confirmed_deal(offer=self.make_offer(self.seller, f'Une annonce quelconque numéro {i}'))
            self.make_review(deal=deal, user=self.buyer, reviewed_user=self.seller)
            last = self.make_review(deal=deal, user=self.seller, reviewed_user=self.buyer)
        return last

    def test_detection_publishes_an_event_and_moderation_files_one_report(self):
        last = self.exchange(3)
        # Le seuil est atteint dès le premier avis de la 3e affaire, puis au second : un événement chacun.
        self.assertEqual(OutboxEvent.objects.filter(event_type='reviews.crossed_reviews_detected').count(), 2)
        event = OutboxEvent.objects.get(event_type='reviews.crossed_reviews_detected', aggregate_id=last.pk)
        self.assertEqual(event.payload['review_id'], str(last.pk))
        self.assertEqual((event.payload['deals_count'], event.payload['window_days']), (3, 30))
        self.assertFalse(Report.objects.exists())
        dispatch_outbox_now()
        self.assertEqual(Report.objects.count(), 2)
        report = Report.objects.get(target_id=last.pk)
        self.assertEqual((report.target_type, report.target_id, report.reporter), ('review', last.pk, None))
        self.assertIn('3 affaires distinctes sur 30 jours', report.description)

    def test_replaying_detection_does_not_duplicate_the_report(self):
        last = self.exchange(3)
        dispatch_outbox_now()
        services.check_crossed_reviews(last)
        dispatch_outbox_now()
        self.assertEqual(Report.objects.filter(target_id=last.pk).count(), 1)

    def test_below_the_threshold_nothing_is_published(self):
        self.exchange(2)
        self.assertFalse(OutboxEvent.objects.filter(event_type='reviews.crossed_reviews_detected').exists())

    def test_reviews_no_longer_imports_notifications(self):
        self.assertFalse(hasattr(services, 'notification_services'))
        self.assertFalse(hasattr(services, 'notify_review_created'))
