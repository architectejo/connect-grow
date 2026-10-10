"""Réglages de contact du vendeur : numéro, code SMS, consentement par canal (ADR 0005, T2)."""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import Category, City, Commune
from apps.common.factories import make_test_image
from apps.marketplace.models import Offer
from apps.moderation.models import AuditLog

from . import services
from .models import CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint, OtpCode, User

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'contact-settings-tests'}}
BASE = '/api/accounts/contact-settings/'
VERSION = CONTACT_CONSENT_TEXT_VERSION
CONTACT = '+243812345678'
LOGIN = '+243970000001'


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email='v@example.com', phone=LOGIN, password='x', full_name='Vendeur Test', phone_verified=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        sms = mock.patch('apps.identity.sms.send_otp_sms')
        self.sms = sms.start()
        self.addCleanup(sms.stop)

    def last_code(self):
        return self.sms.call_args[0][1]

    def put_phone(self, **body):
        return self.client.put(BASE + 'phone/', body, format='json')

    def verify(self, code):
        return self.client.post(BASE + 'phone/verify/', {'code': code}, format='json')

    def channel(self, channel, **body):
        return self.client.put(f'{BASE}channels/{channel}/', body, format='json')

    def verified_phone(self, phone=CONTACT):
        self.put_phone(phone=phone)
        self.assertEqual(self.verify(self.last_code()).status_code, 200)

    def enable(self, channel):
        return self.channel(channel, enabled=True, text_version=VERSION)

    def assert_code(self, response, status, code):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json().get('code'), code, response.content)


class ReadSettingsTests(Base):
    def test_requires_authentication(self):
        self.assertEqual(APIClient().get(BASE).status_code, 401)
        self.assertEqual(APIClient().put(BASE + 'phone/', {}, format='json').status_code, 401)
        self.assertEqual(APIClient().post(BASE + 'phone/verify/', {}, format='json').status_code, 401)
        self.assertEqual(APIClient().put(BASE + 'channels/CALL/', {}, format='json').status_code, 401)

    def test_new_account_defaults(self):
        response = self.client.get(BASE)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body['phone'])
        self.assertEqual(body['channels'], {
            'MESSAGE': {'enabled': True},
            'CALL': {'enabled': False, 'granted_at': None, 'text_version': ''},
            'WHATSAPP': {'enabled': False, 'granted_at': None, 'text_version': ''},
        })
        self.assertEqual(body['current_text_version'], VERSION)
        # Écart à l'ADR 5.1 demandé par le front : au niveau racine tant qu'aucun numéro de contact n'existe.
        self.assertEqual(body['login_phone_masked'], '+243 97 *** ** 01')
        self.assertTrue(body['can_use_login_phone'])

    def test_login_phone_flags_without_a_verified_login_phone(self):
        self.user.phone_verified = False
        self.user.save()
        body = self.client.get(BASE).json()
        self.assertFalse(body['can_use_login_phone'])
        self.assertEqual(body['login_phone_masked'], '+243 97 *** ** 01')
        self.user.phone = None
        self.user.save()
        body = self.client.get(BASE).json()
        self.assertIsNone(body['login_phone_masked'])
        self.assertFalse(body['can_use_login_phone'])

    def test_responses_are_never_cached_and_numbers_are_masked(self):
        self.put_phone(phone=CONTACT)
        for response in (self.client.get(BASE), self.put_phone(phone=CONTACT), self.channel('CALL', enabled=False)):
            self.assertIn('no-store', response['Cache-Control'])
            text = response.content.decode()
            self.assertNotIn('812345678', text)
            self.assertNotIn('970000001', text)
        body = self.client.get(BASE).json()
        self.assertEqual(body['phone']['masked'], '+243 81 *** ** 78')
        self.assertFalse(body['phone']['is_verified'])

    def test_error_responses_are_not_cached_either(self):
        self.assertIn('no-store', self.channel('NOPE', enabled=True)['Cache-Control'])


class PhoneTests(Base):
    def test_invalid_numbers(self):
        for body in ({'phone': '0812345678'}, {'phone': '+24381234'}, {'phone': ''}, {'phone': 12}, {}, {'phone': [1]},
                     {'phone': CONTACT, 'use_login_phone': True}, {'use_login_phone': 'oui'}):
            self.assert_code(self.put_phone(**body), 400, 'phone_invalid')
        self.assertFalse(ContactPoint.objects.exists())

    def test_login_phone_is_proposed_never_copied_without_a_gesture(self):
        self.client.get(BASE)
        self.assertFalse(ContactPoint.objects.exists())

    def test_use_login_phone_is_verified_at_once_when_login_phone_is_verified(self):
        response = self.put_phone(use_login_phone=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['phone']['is_verified'])
        self.assertEqual(ContactPoint.objects.get(user=self.user).phone, LOGIN)
        self.sms.assert_not_called()

    def test_use_login_phone_refused_when_unverified_or_missing(self):
        self.user.phone_verified = False
        self.user.save()
        self.assert_code(self.put_phone(use_login_phone=True), 409, 'login_phone_unverified')
        self.user.phone = None
        self.user.save()
        self.assert_code(self.put_phone(use_login_phone=True), 409, 'login_phone_unverified')
        self.assertFalse(ContactPoint.objects.exists())

    def test_new_number_sends_a_code_and_is_unverified(self):
        response = self.put_phone(phone=CONTACT)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['phone']['is_verified'])
        self.sms.assert_called_once()
        self.assertEqual(self.sms.call_args[0][0], CONTACT)
        self.assertEqual(self.sms.call_args[0][2], OtpCode.PURPOSE_CONTACT_VERIFY)

    def test_same_unverified_number_resends_a_code_and_invalidates_the_previous(self):
        self.put_phone(phone=CONTACT)
        first = OtpCode.objects.get()
        self.put_phone(phone=CONTACT)
        self.assertEqual(self.sms.call_count, 2)
        first.refresh_from_db()
        self.assertTrue(first.is_used)
        self.assertEqual(ContactPoint.objects.count(), 1)

    def test_sms_failure_does_not_break_the_request(self):
        self.sms.side_effect = RuntimeError('passerelle absente')
        self.assertEqual(self.put_phone(phone=CONTACT).status_code, 200)

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_code_requests_are_throttled(self):
        for _ in range(3):
            self.assertEqual(self.put_phone(phone=CONTACT).status_code, 200)
        throttled = self.put_phone(phone=CONTACT)
        self.assertEqual(throttled.status_code, 429)
        self.assertIn('Retry-After', throttled)

    def test_public_otp_endpoint_refuses_the_contact_purpose(self):
        response = APIClient().post(
            '/api/accounts/otp/request/', {'phone': LOGIN, 'purpose': 'CONTACT_VERIFY'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(OtpCode.objects.exists())

    def test_verify_nominal(self):
        self.put_phone(phone=CONTACT)
        response = self.verify(self.last_code())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['phone']['is_verified'])
        self.assertTrue(AuditLog.objects.filter(action='contact.phone_verified').exists())

    def test_verify_without_contact_phone(self):
        self.assert_code(self.verify('123456'), 404, 'contact_phone_missing')

    def test_verify_wrong_code_then_attempts_exceeded(self):
        self.put_phone(phone=CONTACT)
        good = self.last_code()
        wrong = '000000' if good != '000000' else '111111'
        for _ in range(3):
            self.assert_code(self.verify(wrong), 400, 'otp_invalid')
        self.assert_code(self.verify(good), 429, 'otp_attempts_exceeded')
        self.assertFalse(ContactPoint.objects.get().is_verified)
        # Redemander un code remet l'utilisateur sur pied.
        self.put_phone(phone=CONTACT)
        self.assertEqual(self.verify(self.last_code()).status_code, 200)

    def test_verify_expired_code(self):
        self.put_phone(phone=CONTACT)
        OtpCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assert_code(self.verify(self.last_code()), 400, 'otp_expired')

    def test_verify_without_issued_code_or_with_garbage(self):
        self.put_phone(phone=CONTACT)
        self.assert_code(self.verify(None), 400, 'otp_invalid')
        self.assert_code(self.client.post(BASE + 'phone/verify/', {'code': ['1']}, format='json'), 400, 'otp_invalid')
        OtpCode.objects.update(is_used=True)
        self.assert_code(self.verify('123456'), 400, 'otp_invalid')

    def test_a_code_for_another_purpose_or_number_is_not_accepted(self):
        self.put_phone(phone=CONTACT)
        OtpCode.objects.all().delete()
        _, code = OtpCode.issue(CONTACT, OtpCode.PURPOSE_LOGIN)
        self.assert_code(self.verify(code), 400, 'otp_invalid')

    def test_verify_is_idempotent_once_verified(self):
        self.verified_phone()
        self.assertEqual(self.verify('000000').status_code, 200)


class ChannelTests(Base):
    def test_unknown_channel(self):
        self.assert_code(self.channel('SMS', enabled=True), 404, 'channel_unknown')

    def test_enabled_must_be_boolean(self):
        for body in ({}, {'enabled': 'true'}, {'enabled': 1}):
            response = self.channel('CALL', **body)
            self.assertEqual(response.status_code, 400)
            self.assertIn('enabled', response.json())
        self.assertEqual(self.channel('CALL', enabled=True, text_version=3).status_code, 400)

    def test_activation_requires_a_verified_number(self):
        self.assert_code(self.enable('CALL'), 409, 'contact_phone_unverified')
        self.put_phone(phone=CONTACT)  # non vérifié
        self.assert_code(self.enable('WHATSAPP'), 409, 'contact_phone_unverified')
        self.assertFalse(ContactConsent.objects.filter(is_granted=True).exists())

    def test_activation_requires_the_current_text_version(self):
        self.verified_phone()
        self.assert_code(self.channel('CALL', enabled=True), 400, 'consent_text_required')
        self.assert_code(self.channel('CALL', enabled=True, text_version=''), 400, 'consent_text_required')
        self.assert_code(self.channel('CALL', enabled=True, text_version='2025-01-v0'), 400, 'consent_version_mismatch')
        self.assertFalse(ContactConsent.objects.filter(is_granted=True).exists())

    def test_activation_keeps_proof_and_audit_without_the_number(self):
        self.verified_phone()
        response = self.enable('WHATSAPP')
        self.assertEqual(response.status_code, 200)
        state = response.json()['channels']['WHATSAPP']
        self.assertTrue(state['enabled'])
        self.assertEqual(state['text_version'], VERSION)
        self.assertIsNotNone(state['granted_at'])
        consent = ContactConsent.objects.get(user=self.user, channel='WHATSAPP')
        self.assertEqual((consent.text_version, consent.phone_last4), (VERSION, '5678'))
        self.assertIsNotNone(consent.granted_at)
        entry = AuditLog.objects.get(action='contact.consent_granted')
        self.assertEqual(entry.target_id, self.user.id)
        self.assertIn('WHATSAPP', entry.details)
        self.assertIn(VERSION, entry.details)
        self.assertNotIn('812345678', entry.details)
        self.assertFalse(self.channel('CALL', enabled=False).json()['channels']['CALL']['enabled'])

    def test_enabling_twice_is_idempotent(self):
        self.verified_phone()
        self.enable('CALL')
        count = AuditLog.objects.filter(action='contact.consent_granted').count()
        self.assertEqual(self.enable('CALL').status_code, 200)
        self.assertEqual(AuditLog.objects.filter(action='contact.consent_granted').count(), count)

    def test_revocation_is_immediate_with_reason_and_audit(self):
        self.verified_phone()
        self.enable('CALL')
        response = self.channel('CALL', enabled=False)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['channels']['CALL']['enabled'])
        consent = ContactConsent.objects.get(user=self.user, channel='CALL')
        self.assertEqual(consent.revoked_reason, 'user')
        self.assertIsNotNone(consent.revoked_at)
        self.assertEqual(services.get_allowed_channels([self.user.id])[self.user.id], ['MESSAGE'])
        self.assertTrue(AuditLog.objects.filter(action='contact.consent_revoked').exists())

    def test_disabling_is_always_allowed_and_idempotent(self):
        self.assertEqual(self.channel('CALL', enabled=False).status_code, 200)
        self.assertEqual(self.channel('CALL', enabled=False).status_code, 200)
        self.assertFalse(AuditLog.objects.filter(action='contact.consent_revoked').exists())

    def test_message_can_be_switched_off_and_on_without_text(self):
        self.assertEqual(self.channel('MESSAGE', enabled=False).json()['channels']['MESSAGE'], {'enabled': False})
        self.assertEqual(services.get_allowed_channels([self.user.id])[self.user.id], [])
        self.assertEqual(self.channel('MESSAGE', enabled=True).json()['channels']['MESSAGE'], {'enabled': True})
        self.assertEqual(services.get_allowed_channels([self.user.id])[self.user.id], ['MESSAGE'])

    def test_changing_the_number_revokes_call_and_whatsapp_only(self):
        self.verified_phone()
        self.enable('CALL')
        self.enable('WHATSAPP')
        response = self.put_phone(phone='+243899999999')
        channels = response.json()['channels']
        self.assertFalse(channels['CALL']['enabled'])
        self.assertFalse(channels['WHATSAPP']['enabled'])
        self.assertTrue(channels['MESSAGE']['enabled'])
        self.assertFalse(response.json()['phone']['is_verified'])
        for channel in ('CALL', 'WHATSAPP'):
            self.assertEqual(ContactConsent.objects.get(user=self.user, channel=channel).revoked_reason, 'phone_changed')
        self.assertTrue(AuditLog.objects.filter(action='contact.phone_changed').exists())
        # Réactiver exige de vérifier le nouveau numéro puis d'accepter de nouveau.
        self.assert_code(self.enable('CALL'), 409, 'contact_phone_unverified')
        self.assertEqual(self.verify(self.last_code()).status_code, 200)
        self.assertFalse(self.client.get(BASE).json()['channels']['CALL']['enabled'])
        self.assertEqual(self.enable('CALL').status_code, 200)

    def test_resubmitting_the_same_number_keeps_the_consent(self):
        self.verified_phone()
        self.enable('CALL')
        self.put_phone(phone=CONTACT)
        self.assertTrue(self.client.get(BASE).json()['channels']['CALL']['enabled'])

    def test_login_phone_change_does_not_touch_the_contact_phone(self):
        self.verified_phone()
        self.enable('CALL')
        self.user.phone = '+243970000009'
        self.user.save()
        self.assertEqual(services.get_contact_endpoint(self.user.id, 'CALL').phone_e164, CONTACT)

    def test_switching_to_the_login_phone_revokes_and_is_verified(self):
        self.verified_phone()
        self.enable('CALL')
        body = self.put_phone(use_login_phone=True).json()
        self.assertTrue(body['phone']['is_verified'])
        self.assertFalse(body['channels']['CALL']['enabled'])

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_channel_writes_are_throttled(self):
        for _ in range(20):
            self.channel('CALL', enabled=False)
        self.assertEqual(self.channel('CALL', enabled=False).status_code, 429)

    def test_no_audit_entry_contains_a_phone_number(self):
        self.verified_phone()
        self.enable('CALL')
        self.put_phone(phone='+243899999999')
        self.put_phone(use_login_phone=True)
        self.assertGreaterEqual(AuditLog.objects.count(), 4)
        blob = ' '.join(f'{e.action} {e.target_type} {e.details}' for e in AuditLog.objects.all())
        for digits in ('812345678', '899999999', '970000001', '243'):
            self.assertNotIn(digits, blob)


class ServicesTests(Base):
    def test_get_contact_endpoint(self):
        self.verified_phone()
        for channel in ('CALL', 'WHATSAPP'):
            with self.assertRaises(services.ChannelNotConsented):
                services.get_contact_endpoint(self.user.id, channel)
        self.enable('CALL')
        self.assertEqual(services.get_contact_endpoint(self.user.id, 'CALL').phone_e164, CONTACT)
        self.assertNotIn('812345678', repr(services.get_contact_endpoint(self.user.id, 'CALL')))
        with self.assertRaises(services.ChannelNotConsented):
            services.get_contact_endpoint(self.user.id, 'WHATSAPP')
        with self.assertRaises(services.ChannelNotConsented):
            services.get_contact_endpoint(self.user.id, 'MESSAGE')
        with self.assertRaises(services.ChannelNotConsented):
            services.get_contact_endpoint('pas-un-uuid', 'CALL')
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(services.ChannelNotConsented):
            services.get_contact_endpoint(self.user.id, 'CALL')

    def test_endpoint_refused_when_the_number_is_not_verified(self):
        self.verified_phone()
        self.enable('CALL')
        ContactPoint.objects.update(is_verified=False)
        with self.assertRaises(services.ChannelNotConsented):
            services.get_contact_endpoint(self.user.id, 'CALL')
        self.assertEqual(services.get_allowed_channels([self.user.id])[self.user.id], ['MESSAGE'])

    def test_get_allowed_channels_is_one_query_and_complete(self):
        other = User.objects.create_user(email='o@example.com', password='x', full_name='Autre')
        silent = User.objects.create_user(email='s@example.com', password='x', full_name='Muet')
        self.verified_phone()
        self.enable('CALL')
        self.enable('WHATSAPP')
        ContactConsent.objects.create(user=other, channel='MESSAGE', is_granted=False)
        with CaptureQueriesContext(connection) as queries:
            result = services.get_allowed_channels([self.user.id, str(other.id), silent.id])
        self.assertEqual(len(queries), 1)
        self.assertEqual(result, {self.user.id: ['MESSAGE', 'CALL', 'WHATSAPP'], other.id: [], silent.id: ['MESSAGE']})
        self.assertEqual(services.get_allowed_channels([]), {})


class OfferAllowedChannelsTests(Base):
    def setUp(self):
        super().setUp()
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')

    def offer_for(self, seller):
        return Offer.objects.create(
            seller=seller, category_id=self.category.id, commune_id=self.commune.id, title='Un joli canapé',
            description='Description suffisamment longue pour le CDC.', price=100, main_image=make_test_image(),
        )

    def test_list_and_detail_expose_channels_but_never_a_number(self):
        offer = self.offer_for(self.user)
        anonymous = APIClient()
        detail = anonymous.get(f'/api/marketplace/posts/{offer.id}/')
        self.assertEqual(detail.json()['allowed_channels'], ['MESSAGE'])
        self.verified_phone()
        self.enable('CALL')
        self.enable('WHATSAPP')
        for response in (anonymous.get(f'/api/marketplace/posts/{offer.id}/'), anonymous.get('/api/marketplace/posts/')):
            self.assertEqual(response.status_code, 200)
            text = response.content.decode()
            for digits in ('812345678', '5678', '970000001', '0001'):
                self.assertNotIn(digits, text)
        listing = anonymous.get('/api/marketplace/posts/').json()
        rows = listing['results'] if isinstance(listing, dict) else listing
        self.assertEqual(rows[0]['allowed_channels'], ['MESSAGE', 'CALL', 'WHATSAPP'])
        self.channel('CALL', enabled=False)
        self.assertEqual(
            anonymous.get(f'/api/marketplace/posts/{offer.id}/').json()['allowed_channels'], ['MESSAGE', 'WHATSAPP'],
        )

    def test_message_disabled_hides_the_channel(self):
        offer = self.offer_for(self.user)
        self.channel('MESSAGE', enabled=False)
        self.assertEqual(APIClient().get(f'/api/marketplace/posts/{offer.id}/').json()['allowed_channels'], [])

    def test_no_n_plus_one_on_the_list(self):
        def sellers_queries(count):
            for i in range(count):
                seller = User.objects.create_user(email=f's{count}{i}@example.com', password='x', full_name='V')
                ContactConsent.objects.create(user=seller, channel='MESSAGE', is_granted=True)
                self.offer_for(seller)
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(APIClient().get('/api/marketplace/posts/').status_code, 200)
            return len(queries)

        self.offer_for(self.user)
        APIClient().get('/api/marketplace/posts/')  # échauffement : création des réglages singletons
        few = sellers_queries(2)
        many = sellers_queries(6)
        self.assertEqual(few, many)
