"""`GET accounts/contexts/` : organisations indisponibles (L0-09 B-SUSP ; ADR 0006, 9.1, amendement 2).
`status` sur chaque profil, clé `unavailable` toujours présente, aucune fuite de motif ni de membre."""
import json
import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.moderation.models import Sanction

from .models import Membership, Organization
from .tests_acting_context import ADMIN, ANALYST, CONTEXTS_URL, EDITOR, OWNER, join, make_org, make_user

UNAVAILABLE_KEYS = {
    'type', 'id', 'name', 'role', 'org_type', 'photo', 'capabilities', 'migrated_from_business', 'status',
}
SUSPENDED, ARCHIVED = Organization.STATUS_SUSPENDED, Organization.STATUS_ARCHIVED


class UnavailableBase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('indispo')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def body(self):
        response = self.client.get(CONTEXTS_URL)
        self.assertEqual(response.status_code, 200)
        return response.json()


class UnavailableContractTests(UnavailableBase):
    def test_key_is_always_present_and_empty_by_default(self):
        body = self.body()
        self.assertEqual(body['unavailable'], [])
        self.assertEqual(set(body), {'count', 'next', 'previous', 'results', 'unavailable'})
        self.assertEqual([r['status'] for r in body['results']], ['ACTIVE'])

    def test_all_results_are_active_and_carry_status(self):
        join(make_org(name='Active'), self.user, EDITOR)
        join(make_org(name='Suspendue', status=SUSPENDED), self.user, EDITOR)
        body = self.body()
        self.assertEqual([r['name'] for r in body['results'] if r['type'] == 'ORGANIZATION'], ['Active'])
        self.assertEqual({r['status'] for r in body['results']}, {'ACTIVE'})
        self.assertEqual([r['name'] for r in body['unavailable']], ['Suspendue'])

    def test_role_by_status_matrix(self):
        for role in (OWNER, ADMIN, EDITOR, ANALYST):
            for org_status in (SUSPENDED, ARCHIVED):
                with self.subTest(role=role, status=org_status):
                    Membership.objects.all().delete()
                    Organization.objects.all().delete()
                    org = make_org(name='Atelier X', org_type='ONG', status=org_status)
                    join(org, self.user, role)
                    body = self.body()
                    self.assertEqual(body['count'], 1)  # absente de `results`
                    self.assertEqual([r['type'] for r in body['results']], ['USER'])
                    self.assertEqual(len(body['unavailable']), 1)
                    item = body['unavailable'][0]
                    self.assertEqual(set(item), UNAVAILABLE_KEYS)
                    self.assertEqual(item, {
                        'type': 'ORGANIZATION', 'id': str(org.pk), 'name': 'Atelier X', 'role': role,
                        'org_type': 'ONG', 'photo': None, 'capabilities': ['org.leave'],
                        'migrated_from_business': False, 'status': org_status,
                    })

    def test_order_is_case_insensitive_by_name(self):
        for name in ('zeta', 'Alpha', 'beta'):
            join(make_org(name=name, status=SUSPENDED), self.user, OWNER)
        self.assertEqual([r['name'] for r in self.body()['unavailable']], ['Alpha', 'beta', 'zeta'])

    def test_converted_organization_is_flagged_migrated(self):
        join(make_org(status=SUSPENDED, legacy_business_profile_id=uuid.uuid4()), self.user, OWNER)
        self.assertIs(self.body()['unavailable'][0]['migrated_from_business'], True)

    def test_revoked_member_other_account_and_active_orgs_are_absent(self):
        join(make_org(name='Revoquee', status=SUSPENDED), self.user, OWNER, status=Membership.STATUS_REVOKED)
        make_org(name='Etrangere', status=ARCHIVED)
        other = make_user('autre')
        join(make_org(name='Autre compte', status=SUSPENDED), other, OWNER)
        join(make_org(name='Active'), self.user, OWNER)
        self.assertEqual(self.body()['unavailable'], [])

    def test_member_who_left_no_longer_sees_it(self):
        org = make_org(status=SUSPENDED)
        join(org, self.user, ANALYST)
        self.assertEqual(len(self.body()['unavailable']), 1)
        Membership.objects.filter(organization=org).update(status=Membership.STATUS_REVOKED)
        self.assertEqual(self.body()['unavailable'], [])

    def test_restricted_account_gets_200_with_unavailable(self):
        join(make_org(status=SUSPENDED), self.user, OWNER)
        Sanction.objects.create(user=self.user, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='x')
        self.assertEqual(len(self.body()['unavailable']), 1)

    def test_reactivated_organization_moves_back_to_results(self):
        org = make_org(status=SUSPENDED)
        join(org, self.user, EDITOR)
        Organization.objects.filter(pk=org.pk).update(status=Organization.STATUS_ACTIVE)
        body = self.body()
        self.assertEqual(body['unavailable'], [])
        self.assertEqual(len(body['results']), 2)

    def test_no_reason_date_author_member_or_nif_leaks(self):
        org = make_org(name='Sentinelle', status=SUSPENDED, nif='NIF-SECRET-987', suspension_reason='legal')
        join(org, self.user, OWNER)
        join(org, make_user('collegue'), ADMIN)
        response = self.client.get(CONTEXTS_URL)
        text = response.content.decode()
        for forbidden in ('NIF-SECRET-987', 'collegue', 'legal', 'reason', self.user.email, 'suspended_at', 'created'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(set(json.loads(text)['unavailable'][0]), UNAVAILABLE_KEYS)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_query_count_is_bounded(self):
        for i in range(2):
            join(make_org(name=f'S{i}', status=SUSPENDED), self.user, OWNER)
        with self.assertNumQueries(3):  # prestataire, organisations actives, organisations indisponibles
            self.client.get(CONTEXTS_URL)
        for i in range(8):
            join(make_org(name=f'T{i}', status=ARCHIVED if i % 2 else SUSPENDED), self.user, EDITOR)
        with self.assertNumQueries(3):
            self.client.get(CONTEXTS_URL)

    def test_a_reader_ignoring_unavailable_still_gets_the_same_results(self):
        join(make_org(name='Active'), self.user, OWNER)
        body = self.body()
        self.assertEqual([r['type'] for r in body['results']], ['USER', 'ORGANIZATION'])
        self.assertEqual(body['count'], 2)


class LeaveUnavailableTests(UnavailableBase):
    def leave(self, org):
        return self.client.post(f'/api/accounts/organizations/{org.pk}/leave/')

    def test_leave_is_204_for_every_role_and_status_and_clears_the_entry(self):
        for role in (OWNER, ADMIN, EDITOR, ANALYST):
            for org_status in (SUSPENDED, ARCHIVED):
                with self.subTest(role=role, status=org_status):
                    org = make_org(status=org_status)
                    join(org, self.user, role)
                    join(org, make_user(f'second{role}{org_status}'), OWNER)  # un autre propriétaire reste
                    self.assertEqual(self.leave(org).status_code, 204)
                    self.assertNotIn(str(org.pk), [u['id'] for u in self.body()['unavailable']])

    def test_last_owner_of_an_archived_organization_can_leave(self):
        org = make_org(status=ARCHIVED)
        join(org, self.user, OWNER)
        self.assertEqual(self.leave(org).status_code, 204)
        self.assertEqual(self.body()['unavailable'], [])

    def test_last_owner_of_a_suspended_organization_is_refused(self):
        org = make_org(status=SUSPENDED)
        join(org, self.user, OWNER)
        response = self.leave(org)
        self.assertEqual((response.status_code, response.json()['code']), (409, 'last_owner'))
        self.assertEqual(len(self.body()['unavailable']), 1)

    def test_restricted_account_can_leave_a_suspended_organization(self):
        org = make_org(status=SUSPENDED)
        join(org, self.user, EDITOR)
        Sanction.objects.create(user=self.user, sanction_type='BANNISSEMENT', reason='x')
        self.assertEqual(self.leave(org).status_code, 204)

    def test_internal_is_unchanged(self):
        for org_status, code in ((SUSPENDED, 'DENY_SECURITY'), (ARCHIVED, 'DENY_OBJECT_STATE')):
            org = make_org(status=org_status)
            join(org, self.user, OWNER)
            response = self.client.get(f'/api/accounts/organizations/{org.pk}/internal/')
            self.assertEqual((response.status_code, response.json()['code']), (403, code))
