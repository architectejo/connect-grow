"""Preuve de remise du contact pour l'avis (ADR 0005, C10) : `delivered_at` non nul exigé."""
from datetime import timedelta

from django.utils import timezone
from rest_framework import status

from apps.marketplace.models import ContactEvent
from apps.messaging.models import Message
from apps.platform_core.models import OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now

from .tests_eligibility import EligibilityBase


class DeliveredContactProofTests(EligibilityBase):
    def setUp(self):
        super().setUp()
        self.set_settings(delay_after_contact_hours=24)
        self.client.force_authenticate(self.buyer)

    def test_undelivered_message_contact_opens_no_review(self):
        contact = self.make_contact(delivered=False)
        self.age_contact(contact, hours=48)
        result = self.eligibility().data
        self.assertEqual((result['can_review'], result['reason']), (False, 'no_contact'))
        response = self.post_review()
        self.assertEqual((response.status_code, response.data['code']), (403, 'not_eligible'))

    def test_delivered_contact_opens_the_review_after_the_delay(self):
        contact = self.make_contact(delivered=False)
        self.age_contact(contact, hours=1)
        dispatch_outbox_now()  # aucune remise : rien ne change
        self.assertFalse(self.eligibility().data['can_review'])
        ContactEvent.objects.filter(pk=contact.pk).update(delivered_at=contact.created_at)
        self.assertEqual(self.eligibility().data['reason'], 'too_early')  # délai D5 inchangé
        self.age_contact(contact, hours=25)
        self.assertTrue(self.eligibility().data['can_review'])
        self.assertEqual(self.post_review().status_code, status.HTTP_201_CREATED)

    def test_uncounted_but_delivered_contact_is_not_a_proof(self):
        contact = self.make_contact()
        ContactEvent.objects.filter(pk=contact.pk).update(is_counted=False)
        self.age_contact(contact, hours=48)
        self.assertEqual(self.eligibility().data['reason'], 'no_contact')

    def test_message_contact_through_the_outbox_becomes_a_proof_once_delivered(self):
        from apps.marketplace import services as marketplace_services

        contact = marketplace_services.create_contact_event(offer=self.offer, sender=self.buyer, message='Bonjour')
        self.assertIsNone(ContactEvent.objects.get(pk=contact.pk).delivered_at)
        self.assertEqual(self.eligibility().data['reason'], 'no_contact')
        dispatch_outbox_now()   # ouvre la conversation et publie la remise
        dispatch_outbox_now()   # abonné marketplace : pose delivered_at
        contact.refresh_from_db()
        self.assertIsNotNone(contact.delivered_at)
        self.assertEqual(Message.objects.count(), 1)
        delivered = OutboxEvent.objects.get(event_type='messaging.contact_message_delivered')
        self.assertEqual(delivered.status, 'done')
        self.assertEqual(delivered.payload['contact_event_id'], str(contact.pk))
        # Le payload ne contient ni le texte du message ni de numéro.
        self.assertNotIn('Bonjour', str(delivered.payload))
        self.assertEqual(
            set(delivered.payload), {'contact_event_id', 'offer_id', 'conversation_id', 'message_id'},
        )
        stamp = contact.delivered_at
        marketplace_services.mark_contact_delivered(contact.pk)  # idempotent
        contact.refresh_from_db()
        self.assertEqual(contact.delivered_at, stamp)
        self.age_contact(contact, hours=25)
        self.assertTrue(self.eligibility().data['can_review'])

    def test_late_delivery_delays_the_review_from_the_delivery(self):
        contact = self.make_contact(delivered=False)
        self.age_contact(contact, hours=30)  # contact vieux de 30 h, délai de 24 h
        delivered_at = timezone.now() - timedelta(hours=2)
        ContactEvent.objects.filter(pk=contact.pk).update(delivered_at=delivered_at)
        result = self.eligibility().data
        self.assertEqual(result['reason'], 'too_early')  # compté depuis la remise, pas la création
        self.assertEqual(result['available_at'], delivered_at + timedelta(hours=24))

    def test_exchange_proposal_publishes_its_own_event_but_no_delivery_event(self):
        from apps.marketplace import services as marketplace_services

        marketplace_services.create_exchange_proposal(offer=self.offer, sender=self.buyer, message='Échange ?')
        self.assertTrue(OutboxEvent.objects.filter(event_type='marketplace.exchange_proposed').exists())
        dispatch_outbox_now()
        dispatch_outbox_now()
        self.assertTrue(Message.objects.exists())
        self.assertFalse(OutboxEvent.objects.filter(event_type='messaging.contact_message_delivered').exists())
