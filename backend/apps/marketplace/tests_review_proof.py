"""Schéma posé par ADR 0004 côté marketplace : canal de contact, preuve d'avis, fenêtre de doublon, couture du contexte vendeur."""
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.moderation.models import AuditLog
from apps.platform_core.models import OutboxEvent

from . import services
from .admin import MarketplaceSettingsAdmin
from .models import ContactEvent, MarketplaceSettings, Offer
from .tests import MarketplaceTestBase


class ContactProofTests(MarketplaceTestBase):
    def test_api_contact_is_recorded_as_a_message_and_counted_by_default(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('contact-list'), {'post': str(offer.id), 'message': 'Bonjour, dispo ?'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        event = ContactEvent.objects.get()
        self.assertEqual((event.channel, event.is_counted), ('MESSAGE', True))
        self.assertEqual(OutboxEvent.objects.get(event_type='marketplace.contact_recorded').payload['channel'], 'MESSAGE')

    def test_service_records_other_channels(self):
        offer = self.make_offer()
        event = services.create_contact_event(offer=offer, sender=self.buyer, message='', channel=ContactEvent.CHANNEL_CALL)
        self.assertEqual(event.channel, 'CALL')
        self.assertEqual(OutboxEvent.objects.get().payload['channel'], 'CALL')

    def test_get_review_contact_returns_the_oldest_contact_of_the_author(self):
        offer = self.make_offer()
        self.assertIsNone(services.get_review_contact(offer.id, self.buyer.id))
        now = timezone.now()
        newer = ContactEvent.objects.create(offer=offer, sender=self.buyer, message='b', channel='CALL', delivered_at=now)
        older = ContactEvent.objects.create(offer=offer, sender=self.buyer, message='a', channel='WHATSAPP', delivered_at=now)
        ContactEvent.objects.filter(pk=older.pk).update(created_at=now - timedelta(days=3))
        ContactEvent.objects.create(offer=offer, sender=self.seller, message='c')
        proof = services.get_review_contact(offer.id, self.buyer.id)
        self.assertEqual((proof.contact_event_id, proof.channel), (older.id, 'WHATSAPP'))
        self.assertNotEqual(proof.contact_event_id, newer.id)

    def test_offer_info_exposes_the_seller_context_and_moderation_state(self):
        offer = self.make_offer()
        info = services.get_offer(offer.id)
        self.assertEqual((info.seller_context_type, info.seller_context_id), ('USER', self.seller.id))
        self.assertFalse(info.is_hidden_by_moderation)
        services.hide_by_moderation(offer.id)
        self.assertTrue(services.get_offer(offer.id).is_hidden_by_moderation)
        self.assertEqual((offer.seller_context_type, offer.seller_context_id), ('USER', self.seller.id))

    def test_comments_count_is_gone_and_contacts_count_exists(self):
        names = {field.name for field in Offer._meta.get_fields()}
        self.assertNotIn('comments_count', names)
        self.assertIn('contacts_count', names)
        self.assertEqual(self.make_offer().contacts_count, 0)


class DuplicateContactWindowTests(MarketplaceTestBase):
    def test_default_window_is_24_hours_and_comes_from_the_settings(self):
        self.assertEqual(MarketplaceSettings.get_solo().duplicate_contact_window_hours, 24)
        offer = self.make_offer()
        services.create_contact_event(offer=offer, sender=self.buyer, message='Bonjour')
        with self.assertRaises(services.MarketplaceError) as caught:
            services.create_contact_event(offer=offer, sender=self.buyer, message='Encore')
        self.assertIn('24 heures', str(caught.exception))

    def test_a_shorter_window_allows_a_new_contact_sooner(self):
        offer = self.make_offer()
        first = services.create_contact_event(offer=offer, sender=self.buyer, message='Bonjour')
        ContactEvent.objects.filter(pk=first.pk).update(created_at=timezone.now() - timedelta(hours=3))
        with self.assertRaises(services.MarketplaceError):
            services.create_contact_event(offer=offer, sender=self.buyer, message='Encore')
        MarketplaceSettings.objects.update_or_create(
            pk=MarketplaceSettings.SINGLETON_ID, defaults={'duplicate_contact_window_hours': 2},
        )
        services.create_contact_event(offer=offer, sender=self.buyer, message='Encore')
        self.assertEqual(ContactEvent.objects.count(), 2)

    def test_window_must_be_at_least_one_hour(self):
        with self.assertRaises(ValidationError) as caught:
            MarketplaceSettings(duplicate_contact_window_hours=0).full_clean()
        self.assertIn('duplicate_contact_window_hours', caught.exception.message_dict)


class MarketplaceSettingsAuditTests(MarketplaceTestBase):
    def test_a_settings_change_is_audited(self):
        row = MarketplaceSettings.get_solo()
        row.duplicate_contact_window_hours = 12
        request = RequestFactory().post('/admin/')
        request.user = self.seller
        form = mock.Mock(changed_data=['duplicate_contact_window_hours'], initial={'duplicate_contact_window_hours': 24})
        MarketplaceSettingsAdmin(MarketplaceSettings, admin_site).save_model(request, row, form, True)
        entry = AuditLog.objects.get(action='SETTINGS_CHANGED')
        self.assertEqual((entry.actor, entry.target_id), (self.seller, row.pk))
        self.assertIn('duplicate_contact_window_hours : 24 -> 12', entry.details)
