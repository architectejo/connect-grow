"""Double soumission de la création d'une organisation (L009-02) : idempotente dans une fenêtre courte, homonymes
espacés dans le temps autorisés (ADR 0006, A12)."""
from datetime import timedelta

from django.utils import timezone

from . import organizations
from .models import Membership, Organization
from .tests_organizations_api import ApiBase


class DoubleSubmissionTests(ApiBase):
    def test_second_identical_submission_returns_the_same_organization(self):
        first = self.create_via_api(name='Atelier Double')
        second = self.create_via_api(name='  atelier   DOUBLE ')
        self.assertEqual((first.status_code, second.status_code), (201, 201))
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(Organization.objects.filter(name__iexact='Atelier Double').count(), 1)
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 1)

    def test_same_name_after_the_window_creates_a_homonym(self):
        first = self.create_via_api(name='Atelier Double').json()
        Organization.objects.filter(pk=first['id']).update(
            created_at=timezone.now() - timedelta(seconds=organizations.DUPLICATE_SUBMISSION_WINDOW_SECONDS + 5),
        )
        second = self.create_via_api(name='Atelier Double')
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first['id'], second.json()['id'])

    def test_other_type_or_other_name_is_not_a_duplicate(self):
        first = self.create_via_api(name='Atelier Double', org_type='ENTREPRISE').json()
        other_type = self.create_via_api(name='Atelier Double', org_type='ONG').json()
        other_name = self.create_via_api(name='Atelier Triple', org_type='ENTREPRISE').json()
        self.assertEqual(len({first['id'], other_type['id'], other_name['id']}), 3)
