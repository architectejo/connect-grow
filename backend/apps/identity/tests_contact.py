"""Modèles ContactPoint et ContactConsent (ADR 0005, T1)."""
from django.contrib.admin.sites import site as admin_site
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from .models import CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint

User = get_user_model()


class ContactModelsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='v@example.com', password='x')

    def test_text_version_constant(self):
        # Garde-fou : changer la version est un acte juridique (texte de consentement). Ce test oblige
        # à le faire en connaissance de cause (texte affiché au front, ADR 0005 §8, dette LEG-PRV-03).
        self.assertEqual(CONTACT_CONSENT_TEXT_VERSION, '2026-10-v1')

    def test_one_contact_point_per_account(self):
        ContactPoint.objects.create(user=self.user, phone='+243812345678')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContactPoint.objects.create(user=self.user, phone='+243812345679')

    def test_phone_format_is_validated_and_not_unique(self):
        other = User.objects.create_user(email='o@example.com', password='x')
        ContactPoint.objects.create(user=self.user, phone='+243812345678')
        ContactPoint(user=other, phone='+243812345678').full_clean()  # numéro d'entreprise partageable
        with self.assertRaises(ValidationError):
            ContactPoint(user=other, phone='0812345678').full_clean()

    def test_defaults_and_unique_user_channel(self):
        point = ContactPoint.objects.create(user=self.user, phone='+243812345678')
        self.assertFalse(point.is_verified)
        consent = ContactConsent.objects.create(user=self.user, channel='CALL')
        self.assertFalse(consent.is_granted)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContactConsent.objects.create(user=self.user, channel='CALL')
        ContactConsent.objects.create(user=self.user, channel='WHATSAPP')

    def test_representations_never_contain_the_number(self):
        point = ContactPoint.objects.create(user=self.user, phone='+243812345678')
        self.assertNotIn('812345678', str(point))
        self.assertNotIn('812345678', repr(point))

    def test_consent_admin_is_read_only_and_contact_point_not_in_admin(self):
        model_admin = admin_site._registry[ContactConsent]
        request = RequestFactory().get('/')
        request.user = User.objects.create_superuser(email='a@example.com', password='x')
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertNotIn(ContactPoint, admin_site._registry)
        self.assertNotIn('phone', model_admin.list_display)

    def test_deleting_the_account_removes_contact_data(self):
        ContactPoint.objects.create(user=self.user, phone='+243812345678')
        ContactConsent.objects.create(user=self.user, channel='CALL')
        self.user.delete()
        self.assertEqual((ContactPoint.objects.count(), ContactConsent.objects.count()), (0, 0))
