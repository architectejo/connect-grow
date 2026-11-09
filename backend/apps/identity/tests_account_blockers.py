"""`GET me/account-deletion-blockers/` (L1-01-B4, ADR 0008, contrat d'API §3) : décision unique partagée avec
`assert_account_removable`, aucune fuite, IDOR, borne, throttle, non-régression de la purge de compte."""
import itertools
import uuid

from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.moderation.models import AuditLog, Report, Sanction

from . import organizations, services
from .models import Membership, Organization, User

URL = '/api/v1/accounts/me/account-deletion-blockers/'
PASSWORD = 'x'
SECRET_PHONE = '+24399900'
SECRET_NAME = 'Zacharie Sentinelle-Blocage'
LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'blockers'}}
PHONES = itertools.count(1)
ROW_KEYS = {'organization_id', 'name', 'status', 'other_members_count', 'suggested_action'}


def make_user(label, **extra):
    extra.setdefault('phone_verified', True)
    extra.setdefault('full_name', f'Nom {label}')
    return User.objects.create_user(email=f'{label}-{uuid.uuid4().hex[:6]}@example.com', password=PASSWORD, **extra)


def login(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@override_settings(CACHES=LOCMEM_CACHE)
class BlockersBase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('moi')

    def org(self, name='Boutique Aza', status=Organization.STATUS_ACTIVE, role='OWNER', members=(), user=None):
        organization = Organization.objects.create(name=name, org_type='ENTREPRISE', status=status)
        if role:
            Membership.objects.create(organization=organization, user=user or self.user, role=role)
        for member_role in members:
            Membership.objects.create(organization=organization, user=make_user(
                'm', phone=f'{SECRET_PHONE}{next(PHONES):04d}', full_name=SECRET_NAME),
                                      role=member_role)
        return organization

    def get(self, user=None):
        return login(user or self.user).get(URL)

    def body(self, user=None):
        response = self.get(user)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class BlockerCasesTests(BlockersBase):
    def test_account_without_blocker(self):
        self.org(role='ADMIN', members=('OWNER',))  # simple admin : libre
        body = self.body()
        self.assertEqual(body, {'organizations': [], 'has_other_blocker': False})

    def test_response_headers_and_exact_keys(self):
        organization = self.org(members=('ADMIN',))
        response = self.get()
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        body = response.json()
        self.assertEqual(set(body), {'organizations', 'has_other_blocker'})
        self.assertEqual(set(body['organizations'][0]), ROW_KEYS)
        self.assertEqual(body['organizations'][0]['organization_id'], str(organization.pk))

    def test_sole_owner_with_other_members_suggests_transfer(self):
        self.org(members=('ADMIN', 'EDITOR'))
        row = self.body()['organizations'][0]
        self.assertEqual(row['name'], 'Boutique Aza')
        self.assertEqual(row['status'], 'ACTIVE')
        self.assertEqual(row['other_members_count'], 2)
        self.assertEqual(row['suggested_action'], 'transfer_ownership')

    def test_sole_owner_alone_suggests_archive(self):
        self.org()
        row = self.body()['organizations'][0]
        self.assertEqual((row['other_members_count'], row['suggested_action']), (0, 'archive'))

    def test_suspended_organization_waits_for_unsuspension_even_with_members(self):
        self.org(status=Organization.STATUS_SUSPENDED, members=('ADMIN',))
        row = self.body()['organizations'][0]
        self.assertEqual((row['status'], row['suggested_action']), ('SUSPENDED', 'wait_for_unsuspension'))
        self.assertEqual(row['other_members_count'], 1)

    def test_archived_organization_and_second_owner_do_not_block(self):
        self.org(name='Archivée', status=Organization.STATUS_ARCHIVED)
        self.org(name='Deux', members=('OWNER',))
        self.assertEqual(self.body()['organizations'], [])

    def test_revoked_members_are_not_counted_and_revoked_owner_does_not_make_a_second_owner(self):
        organization = self.org(members=('ADMIN', 'OWNER'))
        Membership.objects.filter(organization=organization, role='OWNER').exclude(user=self.user).update(
            status=Membership.STATUS_REVOKED)
        Membership.objects.filter(organization=organization, role='ADMIN').update(status=Membership.STATUS_REVOKED)
        row = self.body()['organizations'][0]
        self.assertEqual((row['other_members_count'], row['suggested_action']), (0, 'archive'))

    def test_blocking_sanction_and_grave_report_set_the_flag_without_detail(self):
        sanction = Sanction.objects.create(user=self.user, sanction_type='SUSPENSION_TEMPORAIRE', reason='motif secret')
        body = self.body()
        self.assertEqual(body, {'organizations': [], 'has_other_blocker': True})
        self.assertNotIn('motif secret', str(body))
        sanction.delete()
        self.assertFalse(self.body()['has_other_blocker'])
        report = Report.objects.create(target_type='user', target_id=self.user.pk, reporter=make_user('r'),
                                       reason='ARNAQUE')
        self.assertTrue(self.body()['has_other_blocker'])
        report.resolve('ok')
        self.assertFalse(self.body()['has_other_blocker'])

    def test_blocker_disappears_after_ownership_transfer(self):
        organization = self.org(members=('ADMIN',))
        admin_membership = Membership.objects.get(organization=organization, role='ADMIN')
        services.transfer_ownership_to(
            self.user, organization.pk, admin_membership.pk, confirm=True, password=PASSWORD,
        )
        self.assertEqual(self.body()['organizations'], [])


class BlockerPrivacyAndAccessTests(BlockersBase):
    def test_no_member_data_leaks(self):
        self.org(members=('ADMIN', 'EDITOR'))
        content = self.get().content.decode()
        for secret in (SECRET_PHONE, SECRET_NAME, '@example.com'):
            self.assertNotIn(secret, content)

    def test_idor_each_account_sees_only_its_own_blockers(self):
        mine = self.org(name='Mienne')
        other = make_user('autre')
        theirs = self.org(name='Leur', user=other)
        self.assertEqual([r['organization_id'] for r in self.body()['organizations']], [str(mine.pk)])
        self.assertEqual([r['organization_id'] for r in self.body(other)['organizations']], [str(theirs.pk)])
        self.assertEqual(self.body(make_user('tiers'))['organizations'], [])

    def test_anonymous_is_refused_and_unsafe_methods_are_not_allowed(self):
        self.assertIn(APIClient().get(URL).status_code, (401, 403))
        client = login(self.user)
        for method in ('post', 'put', 'patch', 'delete'):
            self.assertEqual(getattr(client, method)(URL).status_code, 405)

    def test_ignores_x_context_header(self):
        self.org()
        response = login(self.user).get(URL, HTTP_X_CONTEXT=f'organization:{uuid.uuid4()}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['organizations']), 1)

    def test_read_writes_nothing_and_no_audit(self):
        self.org()
        before = AuditLog.objects.count()
        self.get()
        self.assertEqual(AuditLog.objects.count(), before)

    def test_list_is_bounded_to_100_and_query_count_is_constant(self):
        self.org(name='Une')
        with CaptureQueriesContext(connection) as small:
            self.get()
        for index in range(104):
            self.org(name=f'Org {index:03d}')
        with CaptureQueriesContext(connection) as big:
            response = self.get()
        self.assertEqual(len(response.json()['organizations']), 100)
        self.assertEqual(len(big), len(small))

    def test_throttle_120_per_hour_per_account(self):
        client = login(self.user)
        for _ in range(120):
            self.assertEqual(client.get(URL).status_code, 200)
        self.assertEqual(client.get(URL).status_code, 429)
        self.assertEqual(login(make_user('autre')).get(URL).status_code, 200)

    def test_list_is_ordered_by_name_case_insensitively(self):
        for name in ('beta', 'Alpha', 'gamma'):
            self.org(name=name)
        self.assertEqual([r['name'] for r in self.body()['organizations']], ['Alpha', 'beta', 'gamma'])


class SharedDecisionTests(BlockersBase):
    """Lecture et garde de suppression partagent la même décision (`account_removal_blockers`)."""

    def assert_consistent(self, user):
        body = self.body(user)
        try:
            services.assert_account_removable(user)
            code = None
        except services.OrganizationError as error:
            code = error.detail.code
        blocked = bool(body['organizations']) or body['has_other_blocker']
        self.assertEqual(blocked, code is not None, (body, code))
        if body['organizations']:
            self.assertEqual(code, 'last_owner_account')
        elif body['has_other_blocker']:
            self.assertIn(code, ('blocking_sanction', 'open_grave_report'))

    def test_consistency_across_scenarios(self):
        self.assert_consistent(self.user)
        organization = self.org(members=('ADMIN',))
        self.assert_consistent(self.user)
        Organization.objects.filter(pk=organization.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assert_consistent(self.user)
        Organization.objects.filter(pk=organization.pk).update(status=Organization.STATUS_ARCHIVED)
        self.assert_consistent(self.user)
        Sanction.objects.create(user=self.user, sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        self.assert_consistent(self.user)
        Sanction.objects.all().delete()
        self.assert_consistent(self.user)
        Report.objects.create(target_type='user', target_id=self.user.pk, reporter=make_user('r'), reason='ARNAQUE')
        self.assert_consistent(self.user)

    def test_guard_codes_are_unchanged(self):
        self.org()
        with self.assertRaises(services.OrganizationError) as caught:
            services.assert_account_removable(self.user)
        self.assertEqual(caught.exception.detail.code, 'last_owner_account')
        other = make_user('sanction')
        Sanction.objects.create(user=other, sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        with self.assertRaises(services.OrganizationError) as caught:
            services.assert_account_removable(other)
        self.assertEqual(caught.exception.detail.code, 'blocking_sanction')
        reported = make_user('signale')
        Report.objects.create(target_type='user', target_id=reported.pk, reporter=other, reason='ARNAQUE')
        with self.assertRaises(services.OrganizationError) as caught:
            services.assert_account_removable(reported)
        self.assertEqual(caught.exception.detail.code, 'open_grave_report')

    def test_decision_is_not_truncated_by_the_display_limit(self):
        self.org()
        blockers = organizations.account_removal_blockers(self.user, limit=1)
        self.assertEqual(len(blockers.organizations), 1)
        for index in range(2):
            self.org(name=f'Autre {index}')
        with self.assertRaises(services.OrganizationError):
            services.assert_account_removable(self.user)
