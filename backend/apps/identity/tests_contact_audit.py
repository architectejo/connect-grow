"""Corrections de l'audit sécurité et de la relecture de L0-10a T1/T2 (L0-24)."""
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.db import IntegrityError
from django.test import RequestFactory, override_settings
from django.utils import timezone

from . import services, sms
from .models import ContactConsent, ContactPoint, OtpCode, User
from .tests_contact_settings import CONTACT, Base

OTHER = '+243822222222'


class VerifyRaceTests(Base):
    def test_number_changed_between_read_and_write_is_not_marked_verified(self):
        self.put_phone(phone=CONTACT)
        code = self.last_code()
        real_verify = OtpCode.verify

        def verify_then_change_number(otp, raw):
            ok = real_verify(otp, raw)
            ContactPoint.objects.filter(user=self.user).update(phone=OTHER)  # course avec set_contact_phone
            return ok

        with mock.patch.object(OtpCode, 'verify', verify_then_change_number):
            response = self.verify(code)
        self.assert_code(response, 400, 'otp_invalid')
        point = ContactPoint.objects.get(user=self.user)
        self.assertEqual(point.phone, OTHER)
        self.assertFalse(point.is_verified)

    def test_consumed_code_is_purged(self):
        self.put_phone(phone=CONTACT)
        self.assertTrue(OtpCode.objects.filter(purpose=OtpCode.PURPOSE_CONTACT_VERIFY).exists())
        self.assertEqual(self.verify(self.last_code()).status_code, 200)
        self.assertFalse(OtpCode.objects.filter(purpose=OtpCode.PURPOSE_CONTACT_VERIFY).exists())

    def test_wrong_code_keeps_the_otp(self):
        self.put_phone(phone=CONTACT)
        self.assertEqual(self.verify('000000' if self.last_code() != '000000' else '111111').status_code, 400)
        self.assertTrue(OtpCode.objects.filter(purpose=OtpCode.PURPOSE_CONTACT_VERIFY).exists())

    def test_admin_hides_contact_verification_codes(self):
        self.put_phone(phone=CONTACT)
        OtpCode.issue('+243970000009', OtpCode.PURPOSE_LOGIN)
        request = RequestFactory().get('/admin/')
        request.user = User.objects.create_superuser(email='a@example.com', password='x', full_name='Admin')
        purposes = set(admin_site._registry[OtpCode].get_queryset(request).values_list('purpose', flat=True))
        self.assertEqual(purposes, {OtpCode.PURPOSE_LOGIN})


class ConcurrentCreationTests(Base):
    def test_concurrent_contact_point_creation_is_recovered(self):
        # Une autre requête a créé le numéro entre notre lecture (vide) et notre insertion.
        ContactPoint.objects.create(user=self.user, phone=CONTACT, is_verified=True, verified_at=timezone.now())
        original = ContactPoint.objects.select_for_update
        calls = []

        def first_read_sees_nothing(*args, **kwargs):
            calls.append(1)
            return ContactPoint.objects.none() if len(calls) == 1 else original(*args, **kwargs)

        with mock.patch.object(ContactPoint.objects, 'select_for_update', first_read_sees_nothing):
            response = self.put_phone(phone=OTHER)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ContactPoint.objects.filter(user=self.user).count(), 1)
        point = ContactPoint.objects.get(user=self.user)
        self.assertEqual(point.phone, OTHER)
        self.assertFalse(point.is_verified)
        self.sms.assert_called_once()

    def test_concurrent_creation_of_the_same_number_does_not_revoke_or_resend_blindly(self):
        ContactPoint.objects.create(user=self.user, phone=CONTACT, is_verified=True, verified_at=timezone.now())
        original = ContactPoint.objects.select_for_update
        calls = []

        def first_read_sees_nothing(*args, **kwargs):
            calls.append(1)
            return ContactPoint.objects.none() if len(calls) == 1 else original(*args, **kwargs)

        with mock.patch.object(ContactPoint.objects, 'select_for_update', first_read_sees_nothing):
            response = self.put_phone(phone=CONTACT)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(ContactPoint.objects.get(user=self.user).is_verified)
        self.sms.assert_not_called()


class ConsentDefenceTests(Base):
    def test_endpoint_refused_when_the_proof_does_not_match_the_current_number(self):
        self.verified_phone()
        self.assertEqual(self.enable('CALL').status_code, 200)
        self.assertEqual(services.get_contact_endpoint(self.user.id, 'CALL').phone_e164, CONTACT)
        ContactPoint.objects.filter(user=self.user).update(phone=OTHER)  # changement hors service
        with self.assertRaises(services.ChannelNotConsented):
            services.get_contact_endpoint(self.user.id, 'CALL')

    def test_consent_is_not_written_when_the_number_changed_meanwhile(self):
        self.verified_phone()
        stale = ContactPoint.objects.get(user=self.user)

        class Stub:
            def filter(self_inner, **kwargs):
                # Renvoie l'ancienne lecture, puis le numéro change avant l'écriture du consentement.
                ContactPoint.objects.filter(user=self.user).update(phone=OTHER)
                return mock.Mock(first=lambda: stale)

        with mock.patch.object(ContactPoint.objects, 'select_for_update', lambda: Stub()):
            response = self.enable('CALL')
        self.assert_code(response, 409, 'contact_phone_unverified')
        self.assertFalse(ContactConsent.objects.filter(user=self.user, channel='CALL', is_granted=True).exists())

    def test_changing_to_another_number_then_accepting_again_records_the_new_last4(self):
        self.verified_phone()
        self.enable('CALL')
        self.assertEqual(ContactConsent.objects.get(user=self.user, channel='CALL').phone_last4, CONTACT[-4:])
        self.verified_phone(OTHER)
        consent = ContactConsent.objects.get(user=self.user, channel='CALL')
        self.assertFalse(consent.is_granted)
        self.assertEqual(self.enable('CALL').status_code, 200)
        consent.refresh_from_db()
        self.assertTrue(consent.is_granted)
        self.assertEqual(consent.phone_last4, OTHER[-4:])
        self.assertEqual(services.get_contact_endpoint(self.user.id, 'CALL').phone_e164, OTHER)

    def test_consent_stays_valid_when_the_text_version_constant_moves(self):
        # Décision CP : un accord reste valable après un changement de version (dette LEG-PRV-03).
        self.verified_phone()
        self.enable('CALL')
        ContactConsent.objects.filter(user=self.user, channel='CALL').update(text_version='2026-01-old')
        self.assertEqual(services.get_contact_endpoint(self.user.id, 'CALL').phone_e164, CONTACT)


class AllowedChannelsActivityTests(Base):
    def test_inactive_account_has_no_channel_not_even_message(self):
        self.verified_phone()
        self.enable('CALL')
        silent = User.objects.create_user(email='s@example.com', password='x', full_name='Muet')
        User.objects.filter(pk__in=[self.user.pk, silent.pk]).update(is_active=False)
        result = services.get_allowed_channels([self.user.id, silent.id])
        self.assertEqual(result, {self.user.id: [], silent.id: []})

    def test_unknown_account_has_no_channel(self):
        import uuid

        ghost = uuid.uuid4()
        self.assertEqual(services.get_allowed_channels([ghost]), {ghost: []})


class ArbitrarySmsTests(Base):
    def setUp(self):
        super().setUp()
        # Compte neuf, sans identifiant vérifié.
        User.objects.filter(pk=self.user.pk).update(phone_verified=False)
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)

    def test_new_account_without_verified_identifier_cannot_trigger_a_sms(self):
        response = self.put_phone(phone=CONTACT)
        self.assert_code(response, 403, 'account_too_new')
        self.assertIn('trop récent', response.content.decode())
        self.sms.assert_not_called()
        self.assertFalse(ContactPoint.objects.filter(user=self.user).exists())
        self.assertFalse(OtpCode.objects.exists())

    def test_old_enough_account_can(self):
        User.objects.filter(pk=self.user.pk).update(date_joined=timezone.now() - timedelta(hours=25))
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.put_phone(phone=CONTACT).status_code, 200)
        self.sms.assert_called_once()

    def test_account_with_a_verified_identifier_can(self):
        User.objects.filter(pk=self.user.pk).update(phone_verified=True)
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)
        self.assertEqual(self.put_phone(phone=CONTACT).status_code, 200)

    def test_threshold_is_a_setting(self):
        User.objects.filter(pk=self.user.pk).update(date_joined=timezone.now() - timedelta(hours=2))
        self.user.refresh_from_db()
        self.client.force_authenticate(self.user)
        with override_settings(CONTACT_SMS_MIN_ACCOUNT_AGE_HOURS=1):
            self.assertEqual(self.put_phone(phone=CONTACT).status_code, 200)
        ContactPoint.objects.all().delete()
        with override_settings(CONTACT_SMS_MIN_ACCOUNT_AGE_HOURS=48):
            self.assert_code(self.put_phone(phone=CONTACT), 403, 'account_too_new')

    def test_login_phone_path_sends_no_sms_and_is_not_blocked_by_age(self):
        # use_login_phone exige un numéro de connexion vérifié : refusé tant qu'il ne l'est pas, sans SMS.
        self.assert_code(self.put_phone(use_login_phone=True), 409, 'login_phone_unverified')
        self.sms.assert_not_called()

    def test_default_threshold_is_24_hours(self):
        from django.conf import settings

        self.assertEqual(settings.CONTACT_SMS_MIN_ACCOUNT_AGE_HOURS, 24)

    def test_sms_text_names_its_purpose(self):
        text = sms.build_otp_message('123456', OtpCode.PURPOSE_CONTACT_VERIFY)
        self.assertIn('123456', text)
        self.assertIn('publier ce numéro comme contact Connecte+', text)
        self.assertIn('Ne le communiquez à personne', text)
        self.assertNotIn('publier ce numéro', sms.build_otp_message('123456', OtpCode.PURPOSE_LOGIN))
