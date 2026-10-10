"""Couture des contextes (L0-09) et nom public : `acts_for_context`, `public_display_name`, absence du Trust Score."""
import uuid

from django.test import SimpleTestCase, TestCase

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_USER

from . import services
from .models import User


class ActsForContextTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='ctx@example.com', password='x', full_name='Contexte')

    def test_a_user_acts_for_its_own_personal_context_only(self):
        self.assertTrue(services.acts_for_context(self.user.id, CONTEXT_USER, self.user.id))
        self.assertTrue(services.acts_for_context(self.user.id, CONTEXT_USER, str(self.user.id)))
        self.assertFalse(services.acts_for_context(self.user.id, CONTEXT_USER, uuid.uuid4()))
        self.assertFalse(services.acts_for_context(uuid.uuid4(), CONTEXT_USER, self.user.id))

    def test_organization_context_is_not_resolved_before_l0_09(self):
        self.assertFalse(services.acts_for_context(self.user.id, CONTEXT_ORGANIZATION, self.user.id))

    def test_missing_values_never_match(self):
        self.assertFalse(services.acts_for_context(None, CONTEXT_USER, None))
        self.assertFalse(services.acts_for_context(self.user.id, CONTEXT_USER, None))


class PublicDisplayNameTests(SimpleTestCase):
    def test_first_name_and_initial_of_the_last_name(self):
        self.assertEqual(services.public_display_name('Marie Kabongo'), 'Marie K.')
        self.assertEqual(services.public_display_name('  jean  claude  mbuyi  '), 'jean M.')
        self.assertEqual(services.public_display_name('Marie'), 'Marie')

    def test_empty_name_has_a_neutral_fallback(self):
        self.assertEqual(services.public_display_name(''), 'Utilisateur')
        self.assertEqual(services.public_display_name(None), 'Utilisateur')


class NoReputationOnUserTests(TestCase):
    def test_the_user_carries_no_trust_data(self):
        names = {field.name for field in User._meta.get_fields()}
        self.assertFalse({'trust_score', 'reviews_count'} & names)
        self.assertFalse(hasattr(services, 'set_reputation'))
        summary_fields = set(services.SellerSummary.__dataclass_fields__)
        self.assertFalse({'trust_score', 'reviews_count'} & summary_fields)
