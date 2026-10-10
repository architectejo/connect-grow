"""Contacts et propositions d'échange publiés comme événements de domaine (ADR 0003, L0-16)."""
from unittest import mock

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.messaging.models import Conversation, Message
from apps.notifications.models import Notification
from apps.platform_core import registry
from apps.platform_core.models import OutboxDelivery, OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now

from . import services
from .models import ContactEvent, ExchangeProposal, Offer
from .tests import MarketplaceTestBase


class ContactEventTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        self.offer = self.make_offer()

    def contact(self, message='Mon numéro est secret, appelez-moi.'):
        return services.create_contact_event(offer=self.offer, sender=self.buyer, message=message)

    def test_contact_and_event_are_written_together_without_touching_other_domains(self):
        event = self.contact()
        outbox = OutboxEvent.objects.get(event_type='marketplace.contact_recorded')
        self.assertEqual(outbox.aggregate_id, self.offer.id)
        self.assertEqual(
            sorted(outbox.deliveries.values_list('handler', flat=True)),
            ['messaging.open_contact_conversation', 'notifications.notify_contact'],
        )
        # Rien n'est écrit chez messaging ni notifications avant la diffusion.
        self.assertEqual((Conversation.objects.count(), Message.objects.count(), Notification.objects.count()), (0, 0, 0))
        self.assertEqual(ContactEvent.objects.get(), event)

    def test_payload_holds_identifiers_and_the_public_title_only(self):
        event = self.contact(message='Texte confidentiel')
        payload = OutboxEvent.objects.get().payload
        self.assertEqual(payload, {
            'contact_event_id': str(event.pk), 'offer_id': str(self.offer.id), 'offer_title': self.offer.title,
            'seller_id': str(self.seller.pk), 'sender_id': str(self.buyer.pk), 'channel': 'MESSAGE',
        })
        self.assertNotIn('Texte confidentiel', str(payload))
        self.assertNotIn('Acheteur', str(payload))

    def test_dispatch_creates_conversation_message_and_notification_once(self):
        self.contact(message='Bonjour')
        dispatch_outbox_now()
        dispatch_outbox_now()
        message = Message.objects.get()
        self.assertEqual((message.content, message.sender), ('Bonjour', self.buyer))
        notification = Notification.objects.get()
        self.assertEqual((notification.user, notification.notification_type), (self.seller, 'CONTACT'))
        self.assertEqual(notification.content, f'Acheteur vous a contacté pour {self.offer.title}')
        self.assertEqual(OutboxEvent.objects.get(event_type='marketplace.contact_recorded').status, 'done')

    def test_validation_errors_publish_nothing(self):
        with self.assertRaises(services.MarketplaceError):
            services.create_contact_event(offer=self.offer, sender=self.seller, message='x')
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_rollback_of_the_emitter_leaves_neither_contact_nor_event(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.contact()
                raise RuntimeError('échec ultérieur')
        self.assertEqual((ContactEvent.objects.count(), OutboxEvent.objects.count()), (0, 0))

    def test_failing_subscriber_keeps_the_contact_and_is_recovered_by_a_retry(self):
        original = registry.get_subscriber('notifications.notify_contact')
        failing = registry.Subscriber(original.event_type, original.name, mock.Mock(side_effect=ValueError('x')), (1,))
        with mock.patch.dict(registry._BY_NAME, {original.name: failing}):
            self.contact(message='Bonjour')
            with self.assertLogs('apps.platform_core.services', level='ERROR'):
                dispatch_outbox_now()
        # Le contact existe et le message de la conversation aussi ; seule la notification attend.
        self.assertEqual((ContactEvent.objects.count(), Message.objects.count(), Notification.objects.count()), (1, 1, 0))
        self.assertEqual(OutboxEvent.objects.get(event_type='marketplace.contact_recorded').status, 'pending')
        OutboxDelivery.objects.filter(status='pending').update(next_attempt_at=self.offer.created_at)
        dispatch_outbox_now()
        self.assertEqual((Message.objects.count(), Notification.objects.count()), (1, 1))
        self.assertEqual(OutboxEvent.objects.get(event_type='marketplace.contact_recorded').status, 'done')

    def test_contact_deleted_with_its_offer_before_delivery_opens_nothing(self):
        self.contact()
        services.delete_offers(type(self.offer).objects.filter(pk=self.offer.pk))
        dispatch_outbox_now()
        self.assertEqual((Conversation.objects.count(), Message.objects.count()), (0, 0))
        self.assertEqual(OutboxEvent.objects.get().status, 'done')

    def test_exchange_proposal_goes_through_the_outbox_too(self):
        proposal = services.create_exchange_proposal(offer=self.offer, sender=self.buyer, message='Troc ?')
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.get().payload['proposal_id'], str(proposal.pk))
        dispatch_outbox_now()
        self.assertEqual(Message.objects.get().content, "[PROPOSITION D'ÉCHANGE] Troc ?")
        notification = Notification.objects.get()
        self.assertEqual(notification.notification_type, 'EXCHANGE')
        self.assertEqual(ExchangeProposal.objects.count(), 1)

    def test_http_contact_returns_the_same_contract_before_diffusion(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('contact-list'), {'post': str(self.offer.id), 'message': 'Bonjour'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(response.data['post']), str(self.offer.id))
        self.assertEqual(response.data['message'], 'Bonjour')

    def test_marketplace_no_longer_calls_messaging_directly(self):
        self.assertFalse(hasattr(services, 'messaging_services'))


class ExpirationEventTests(MarketplaceTestBase):
    def expiring_offer(self, days=1):
        from datetime import timedelta

        offer = self.make_offer()
        Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() + timedelta(days=days))
        offer.refresh_from_db()
        return offer

    def test_expiring_offer_publishes_one_event_and_the_notification_follows_the_diffusion(self):
        offer = self.expiring_offer()
        self.assertEqual(services.expire_offers(), (0, 1))
        self.assertEqual(services.expire_offers(), (0, 0))  # déjà signalée
        self.assertEqual(Notification.objects.count(), 0)
        event = OutboxEvent.objects.get(event_type='marketplace.offer_expiring_soon')
        self.assertEqual(event.payload, {
            'offer_id': str(offer.id), 'offer_title': offer.title, 'seller_id': str(self.seller.pk),
            'expires_at': offer.expires_at.isoformat(),
        })
        dispatch_outbox_now()
        notification = Notification.objects.get()
        self.assertEqual((notification.user, notification.notification_type), (self.seller, 'EXPIRATION'))
        self.assertEqual(notification.title, 'Votre annonce expire bientôt')
        self.assertEqual(
            notification.content,
            f'« {offer.title} » expire le {offer.expires_at:%d/%m/%Y}. Renouvelez-la pour rester visible.',
        )
        self.assertEqual(notification.link, f'/post/{offer.id}')

    def test_a_failing_notification_does_not_prevent_the_offer_from_being_marked(self):
        offer = self.expiring_offer()
        original = registry.get_subscriber('notifications.notify_offer_expiration')
        failing = registry.Subscriber(original.event_type, original.name, mock.Mock(side_effect=ValueError('x')), (1,))
        with mock.patch.dict(registry._BY_NAME, {original.name: failing}):
            services.expire_offers()
            dispatch_outbox_now()
        offer.refresh_from_db()
        self.assertTrue(offer.expiring_soon_notified)
        self.assertEqual(Notification.objects.count(), 0)
        OutboxDelivery.objects.update(next_attempt_at=timezone.now())
        dispatch_outbox_now()
        self.assertEqual(Notification.objects.count(), 1)

    def test_marketplace_no_longer_depends_on_notifications(self):
        self.assertFalse(hasattr(services, 'notification_services'))
