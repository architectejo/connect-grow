"""Format d'erreur de l'API : {detail, code} hors champs, format DRF pour les champs (ADR 0004, 7) ;
retrait du Trust Score : routes et rôles."""
from django.core.management import call_command
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.identity.models import User
from apps.moderation.models import Report


class ErrorFormatTests(APITestCase):
    def test_not_authenticated_has_a_code(self):
        response = self.client.get('/api/v1/interactions/notifications/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'not_authenticated')
        self.assertIn('detail', response.data)

    def test_permission_denied_and_not_found_have_codes(self):
        user = User.objects.create_user(email='e@example.com', password='x', full_name='E')
        self.client.force_authenticate(user)
        denied = self.client.get('/api/v1/moderation/dashboard/')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(denied.data['code'], 'permission_denied')
        missing = self.client.get('/api/v1/interactions/reviews/00000000-0000-0000-0000-000000000001/')
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(missing.data['code'], 'not_found')

    def test_field_validation_errors_keep_the_drf_shape(self):
        user = User.objects.create_user(email='f@example.com', password='x', full_name='F')
        self.client.force_authenticate(user)
        response = self.client.post('/api/v1/interactions/reviews/', {'post': 'x'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('code', response.data)
        self.assertIsInstance(response.data['post'], list)


class RetiredTrustScoreTests(TestCase):
    def test_setup_roles_grants_review_settings_not_trust_score_settings(self):
        call_command('setup_roles', verbosity=0)
        admin = Group.objects.get(name='Administrateur')
        codenames = set(admin.permissions.values_list('codename', flat=True))
        self.assertIn('change_reviewsettings', codenames)
        self.assertFalse({c for c in codenames if 'trustscore' in c})
        moderator = Group.objects.get(name='Modérateur')
        self.assertNotIn('change_reviewsettings', set(moderator.permissions.values_list('codename', flat=True)))
        self.assertFalse(Permission.objects.filter(codename__contains='deal').exists())

    def test_contact_fictif_is_a_report_reason_with_a_french_label(self):
        labels = dict(Report.REASON_CHOICES)
        self.assertEqual(labels['CONTACT_FICTIF'], 'Contact fictif')
        self.assertLessEqual(len('CONTACT_FICTIF'), Report._meta.get_field('reason').max_length)
