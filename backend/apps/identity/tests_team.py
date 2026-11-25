"""Équipe d'organisation par `membership_id` (L1-01-B1, ADR 0008 §5.2, §8, §9 ; contrat d'API §1) : liste des
membres, changement de rôle, retrait, transfert de propriété, ressaisie du mot de passe, événement de visibilité.

Les cas qui dépendent des offres actives (`last_effective_owner` avec offres) sont dans
`apps.marketplace.tests_team_offers` : `identity` n'importe jamais les modèles de `marketplace`."""
import json
import uuid
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.common.contexts import DENY_OBJECT_STATE, DENY_PERMISSION, DENY_RELATION, DENY_SECURITY
from apps.moderation.models import AuditLog, Sanction
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxEvent

from . import capabilities, organizations, services
from .models import Membership, Organization, User
from .tests_route_guard import collect_unguarded_write_routes

OWNER, ADMIN, EDITOR, ANALYST = capabilities.ROLE_OWNER, capabilities.ROLE_ADMIN, capabilities.ROLE_EDITOR, capabilities.ROLE_ANALYST
ORGS = '/api/v1/accounts/organizations/'
MEMBER_KEYS = {'membership_id', 'display_name', 'role', 'joined_at', 'is_self', 'is_last_effective_owner', 'scope'}
PASSWORD = 'x'
SECRET_PHONE = '+243999000777'
SECRET_EMAIL_PART = 'secret-team'
SECRET_NAME = 'Zacharie Sentinelle-Equipe'

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'team-throttle'}}


def make_user(label, **extra):
    extra.setdefault('phone_verified', True)
    extra.setdefault('full_name', f'Nom {label}')
    return User.objects.create_user(email=f'{label}@example.com', password=PASSWORD, **extra)


def url_members(org):
    return f'{ORGS}{org.pk}/members/'


def url_member(org, membership):
    return f'{ORGS}{org.pk}/members/{membership.pk}/'


def url_transfer(org):
    return f'{ORGS}{org.pk}/transfer-ownership/'


def login(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@override_settings(CACHES=LOCMEM_CACHE)
class TeamBase(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name='Atelier Équipe', org_type='ENTREPRISE')
        self.users, self.memberships = {}, {}
        for index, role in enumerate((OWNER, ADMIN, EDITOR, ANALYST)):
            self.add(role.lower(), role, joined_offset=index)
        self.owner = self.users[OWNER]

    def add(self, label, role, org=None, **extra):
        offset = extra.pop('joined_offset', 0)
        user = make_user(f'{label}-{uuid.uuid4().hex[:6]}', **extra)
        membership = Membership.objects.create(organization=org or self.org, user=user, role=role)
        if org is None:
            self.users.setdefault(role, user)
            self.memberships.setdefault(role, membership)
        return user, membership

    def as_role(self, role):
        return login(User.objects.get(pk=self.users[role].pk))

    def assertDenied(self, response, code, status=403):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()['code'], code)

    def role_of(self, membership):
        return Membership.objects.get(pk=membership.pk).role

    def status_of(self, membership):
        return Membership.objects.get(pk=membership.pk).status


# --- Liste ----------------------------------------------------------------------------------------------------

class MemberListTests(TeamBase):
    def get(self, role=OWNER, org=None, **params):
        return self.as_role(role).get(url_members(org or self.org), params)

    def test_every_role_reads_the_list_with_exact_keys_and_pagination_envelope(self):
        for role in (OWNER, ADMIN, EDITOR, ANALYST):  # rôles de l'équipe de base ; MEMBER : tests_member_scope
            with self.subTest(role=role):
                response = self.get(role)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(set(body), {'count', 'next', 'previous', 'results'})
                self.assertEqual(body['count'], 4)
                for row in body['results']:
                    self.assertEqual(set(row), MEMBER_KEYS)
                self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_order_is_role_then_joined_at_then_id(self):
        extra_editor, extra_membership = self.add('editor2', EDITOR, org=self.org)
        extra_admin, _ = self.add('admin2', ADMIN, org=self.org)
        rows = self.get().json()['results']
        self.assertEqual([r['role'] for r in rows], [OWNER, ADMIN, ADMIN, EDITOR, EDITOR, ANALYST])
        same_role = [r for r in rows if r['role'] == EDITOR]
        self.assertEqual(same_role[0]['membership_id'], str(self.memberships[EDITOR].pk))
        self.assertEqual(same_role[1]['membership_id'], str(extra_membership.pk))

    def test_only_active_members_are_listed(self):
        gone, membership = self.add('gone', EDITOR, org=self.org)
        Membership.objects.filter(pk=membership.pk).update(status=Membership.STATUS_REVOKED)
        ids = {row['membership_id'] for row in self.get().json()['results']}
        self.assertNotIn(str(membership.pk), ids)

    def test_page_size_is_honoured(self):
        body = self.get(page_size=2).json()
        self.assertEqual((body['count'], len(body['results'])), (4, 2))
        self.assertIsNotNone(body['next'])

    def test_is_self_and_last_effective_owner_flags_for_a_manager(self):
        rows = {r['membership_id']: r for r in self.get(ADMIN).json()['results']}
        self.assertTrue(rows[str(self.memberships[ADMIN].pk)]['is_self'])
        self.assertFalse(rows[str(self.memberships[OWNER].pk)]['is_self'])
        self.assertIs(rows[str(self.memberships[OWNER].pk)]['is_last_effective_owner'], True)
        for role in (ADMIN, EDITOR, ANALYST):
            self.assertIs(rows[str(self.memberships[role].pk)]['is_last_effective_owner'], False)

    def test_flag_is_null_for_non_managers(self):
        for role in (EDITOR, ANALYST):
            with self.subTest(role=role):
                for row in self.get(role).json()['results']:
                    self.assertIsNone(row['is_last_effective_owner'])

    def test_flag_is_false_everywhere_with_two_effective_owners(self):
        self.add('owner2', OWNER, org=self.org)
        for row in self.get().json()['results']:
            self.assertIs(row['is_last_effective_owner'], False)

    def test_sole_effective_owner_is_the_one_not_sanctioned(self):
        _, second = self.add('owner2', OWNER, org=self.org)
        Sanction.objects.create(
            user=self.owner, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.users[ADMIN],
        ).apply()
        rows = {r['membership_id']: r for r in self.get(ADMIN).json()['results']}
        self.assertIs(rows[str(second.pk)]['is_last_effective_owner'], True)
        self.assertIs(rows[str(self.memberships[OWNER].pk)]['is_last_effective_owner'], False)

    def test_display_name_is_abbreviated_and_no_personal_data_is_returned(self):
        user, _ = self.add('named', EDITOR, org=self.org, full_name=SECRET_NAME, phone='+243999000777')
        text = json.dumps(self.get().json())
        self.assertIn('Zacharie S.', text)
        for secret in (SECRET_NAME, SECRET_PHONE, user.email, str(user.pk), 'Sentinelle-Equipe'):
            self.assertNotIn(secret, text)

    def test_non_member_unknown_and_revoked_get_the_same_refusal(self):
        stranger = login(make_user('stranger'))
        first = stranger.get(url_members(self.org))
        self.assertDenied(first, DENY_RELATION)
        class Unknown:
            pk = uuid.uuid4()
        second = stranger.get(url_members(Unknown))
        self.assertEqual((second.status_code, second.json()), (first.status_code, first.json()))
        Membership.objects.filter(pk=self.memberships[EDITOR].pk).update(status=Membership.STATUS_REVOKED)
        self.assertDenied(self.get(EDITOR), DENY_RELATION)

    def test_staff_without_membership_gets_nothing(self):
        staff = make_user('staff', is_staff=True, is_superuser=True)
        self.assertDenied(login(staff).get(url_members(self.org)), DENY_RELATION)

    def test_anonymous_is_refused(self):
        self.assertEqual(APIClient().get(url_members(self.org)).status_code, 401)

    def test_suspended_archived_and_restricted(self):
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertDenied(self.get(), DENY_SECURITY)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ARCHIVED)
        self.assertDenied(self.get(), DENY_OBJECT_STATE)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ACTIVE)
        User.objects.filter(pk=self.users[EDITOR].pk).update(is_active=False)
        self.assertDenied(self.as_role(EDITOR).get(url_members(self.org)), DENY_SECURITY)

    def test_x_context_header_is_ignored(self):
        other = Organization.objects.create(name='Autre', org_type='ENTREPRISE')
        client = self.as_role(OWNER)
        response = client.get(url_members(self.org), HTTP_X_CONTEXT=f'ORGANIZATION:{other.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 4)

    def test_query_count_does_not_depend_on_the_page_size(self):
        client = self.as_role(OWNER)
        with self.assertNumQueries(self._count_queries(client)):
            client.get(url_members(self.org))
        for index in range(8):
            self.add(f'more{index}', ANALYST, org=self.org)
        with self.assertNumQueries(self._count_queries(client)):
            client.get(url_members(self.org))
        self.assertEqual(client.get(url_members(self.org)).json()['count'], 12)

    def _count_queries(self, client):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as captured:
            client.get(url_members(self.org), {'page_size': 1})
        return len(captured)

    def test_post_on_members_is_not_routed(self):
        self.assertEqual(self.as_role(OWNER).post(url_members(self.org), {'identifier': 'x'}, format='json').status_code, 405)


# --- Changement de rôle -------------------------------------------------------------------------------------

class ChangeRoleTests(TeamBase):
    def patch(self, actor_role, target_role, new_role, **extra):
        body = {'role': new_role, **extra}
        return self.as_role(actor_role).patch(url_member(self.org, self.memberships[target_role]), body, format='json')

    def test_admin_changes_editor_and_analyst_without_password(self):
        response = self.patch(ADMIN, EDITOR, ANALYST)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(set(response.json()), MEMBER_KEYS)
        self.assertEqual(response.json()['role'], ANALYST)
        self.assertEqual(self.role_of(self.memberships[EDITOR]), ANALYST)
        self.assertEqual(self.patch(ADMIN, ANALYST, ADMIN).status_code, 200)

    def test_matrix_role_by_target_by_new_role(self):
        # (acteur, cible, nouveau rôle) -> statut attendu, sans mot de passe : les cas 400 sont ceux d'un siège OWNER.
        expectations = {
            (OWNER, ADMIN, EDITOR): 200, (OWNER, EDITOR, ADMIN): 200, (OWNER, ANALYST, EDITOR): 200,
            (OWNER, EDITOR, OWNER): 400, (OWNER, OWNER, ADMIN): 400,
            (ADMIN, EDITOR, ANALYST): 200, (ADMIN, ANALYST, ADMIN): 200,
            (ADMIN, OWNER, ADMIN): 403, (ADMIN, EDITOR, OWNER): 403, (ADMIN, OWNER, OWNER): 403,
            (EDITOR, ANALYST, EDITOR): 403, (EDITOR, EDITOR, ANALYST): 403, (EDITOR, OWNER, ADMIN): 403,
            (ANALYST, EDITOR, ANALYST): 403, (ANALYST, ANALYST, EDITOR): 403,
        }
        for (actor, target, new_role), expected in expectations.items():
            with self.subTest(actor=actor, target=target, new_role=new_role):
                response = self.patch(actor, target, new_role)
                self.assertEqual(response.status_code, expected, response.content)
                if expected == 403:
                    self.assertEqual(response.json()['code'], DENY_PERMISSION)
                # Remet la matrice à zéro pour le cas suivant.
                for role, membership in self.memberships.items():
                    Membership.objects.filter(pk=membership.pk).update(role=role)

    def test_the_new_role_is_effective_on_the_next_request(self):
        self.assertEqual(self.patch(OWNER, EDITOR, ANALYST).status_code, 200)
        response = self.as_role(EDITOR).patch(
            url_member(self.org, self.memberships[ANALYST]), {'role': EDITOR}, format='json',
        )
        self.assertDenied(response, DENY_PERMISSION)

    def test_same_role_is_a_noop_without_trace_or_event(self):
        audits, events = AuditLog.objects.count(), OutboxEvent.objects.count()
        response = self.patch(ADMIN, EDITOR, EDITOR)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((AuditLog.objects.count(), OutboxEvent.objects.count()), (audits, events))

    def test_invalid_or_missing_role_is_a_field_error(self):
        for body in ({}, {'role': 'GOD'}, {'role': ''}, {'role': None}, {'role': ['OWNER']}):
            with self.subTest(body=body):
                response = self.as_role(OWNER).patch(url_member(self.org, self.memberships[EDITOR]), body, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('role', response.json())

    def test_promotion_to_owner_needs_confirmation_then_password(self):
        target = self.memberships[ADMIN]
        client = self.as_role(OWNER)
        response = client.patch(url_member(self.org, target), {'role': OWNER}, format='json')
        self.assertDenied(response, 'confirmation_required', 400)
        response = client.patch(url_member(self.org, target), {'role': OWNER, 'confirm': True}, format='json')
        self.assertDenied(response, 'password_required', 400)
        response = client.patch(url_member(self.org, target), {'role': OWNER, 'confirm': 'true', 'password': PASSWORD}, format='json')
        self.assertDenied(response, 'confirmation_required', 400)
        self.assertEqual(self.role_of(target), ADMIN)
        response = client.patch(
            url_member(self.org, target), {'role': OWNER, 'confirm': True, 'password': PASSWORD}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.role_of(target), OWNER)
        details = AuditLog.objects.filter(action='MEMBERSHIP_ROLE_CHANGED').latest('created_at').details
        self.assertIn('reauth=true', details)

    def test_demotion_of_an_owner_needs_password(self):
        _, second = self.add('owner2', OWNER, org=self.org)
        client = self.as_role(OWNER)
        response = client.patch(url_member(self.org, second), {'role': ADMIN}, format='json')
        self.assertDenied(response, 'confirmation_required', 400)
        response = client.patch(
            url_member(self.org, second), {'role': ADMIN, 'confirm': True, 'password': PASSWORD}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.role_of(second), ADMIN)

    def test_password_is_ignored_when_not_needed(self):
        response = self.patch(OWNER, EDITOR, ANALYST, password='faux', confirm=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AuditLog.objects.filter(action='ORG_SENSITIVE_REAUTH_FAILED').exists())

    def test_wrong_password_is_refused_audited_and_changes_nothing(self):
        target = self.memberships[ADMIN]
        events = OutboxEvent.objects.count()
        response = self.as_role(OWNER).patch(
            url_member(self.org, target), {'role': OWNER, 'confirm': True, 'password': 'mauvais'}, format='json',
        )
        self.assertDenied(response, 'reauthentication_failed')
        self.assertEqual(self.role_of(target), ADMIN)
        self.assertEqual(OutboxEvent.objects.count(), events)
        entry = AuditLog.objects.get(action='ORG_SENSITIVE_REAUTH_FAILED')
        self.assertEqual(entry.actor_id, self.owner.pk)
        self.assertIn(f'organization={self.org.pk}', entry.details)
        self.assertIn('action=promote_owner', entry.details)
        self.assertNotIn('mauvais', entry.details)

    def test_failed_reauth_is_limited_then_a_success_resets_the_counter(self):
        target = self.memberships[ADMIN]
        client = self.as_role(OWNER)
        wrong = {'role': OWNER, 'confirm': True, 'password': 'mauvais'}
        for _ in range(5):
            self.assertDenied(client.patch(url_member(self.org, target), wrong, format='json'), 'reauthentication_failed')
        response = client.patch(url_member(self.org, target), {**wrong, 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.role_of(target), ADMIN)

    def test_a_success_clears_earlier_failures(self):
        target = self.memberships[ADMIN]
        client = self.as_role(OWNER)
        for _ in range(4):
            client.patch(url_member(self.org, target), {'role': OWNER, 'confirm': True, 'password': 'm'}, format='json')
        ok = client.patch(url_member(self.org, target), {'role': OWNER, 'confirm': True, 'password': PASSWORD}, format='json')
        self.assertEqual(ok.status_code, 200)
        self.assertIsNone(cache.get('fail:org_reauth:' + str(self.owner.pk)))

    def test_admin_cannot_reach_an_owner_even_with_the_password(self):
        response = self.patch(ADMIN, OWNER, ADMIN, confirm=True, password=PASSWORD)
        self.assertDenied(response, DENY_PERMISSION)
        self.assertFalse(AuditLog.objects.filter(action='ORG_SENSITIVE_REAUTH_FAILED').exists())

    def test_member_of_another_organization_revoked_or_unknown_is_404(self):
        other = Organization.objects.create(name='Autre', org_type='ENTREPRISE')
        _, foreign = self.add('foreign', EDITOR, org=other)
        client = self.as_role(OWNER)
        for target in (foreign.pk, uuid.uuid4()):
            response = client.patch(f'{ORGS}{self.org.pk}/members/{target}/', {'role': ADMIN}, format='json')
            self.assertDenied(response, 'member_not_found', 404)
        self.assertEqual(self.role_of(foreign), EDITOR)
        Membership.objects.filter(pk=self.memberships[EDITOR].pk).update(status=Membership.STATUS_REVOKED)
        self.assertDenied(self.patch(OWNER, EDITOR, ADMIN), 'member_not_found', 404)

    def test_other_organization_member_id_gives_the_same_answer_as_unknown(self):
        other = Organization.objects.create(name='Autre', org_type='ENTREPRISE')
        _, foreign = self.add('foreign', EDITOR, org=other)
        client = self.as_role(OWNER)
        a = client.patch(f'{ORGS}{self.org.pk}/members/{foreign.pk}/', {'role': ADMIN}, format='json')
        b = client.patch(f'{ORGS}{self.org.pk}/members/{uuid.uuid4()}/', {'role': ADMIN}, format='json')
        self.assertEqual((a.status_code, a.json()), (b.status_code, b.json()))

    def test_unavailable_target_is_a_neutral_400(self):
        User.objects.filter(pk=self.users[EDITOR].pk).update(is_active=False)
        self.assertDenied(self.patch(OWNER, EDITOR, ANALYST), 'user_unavailable', 400)

    def test_last_owner_is_protected_even_with_the_password(self):
        response = self.as_role(OWNER).patch(
            url_member(self.org, self.memberships[OWNER]),
            {'role': ADMIN, 'confirm': True, 'password': PASSWORD}, format='json',
        )
        self.assertDenied(response, 'last_owner', 409)
        self.assertEqual(self.role_of(self.memberships[OWNER]), OWNER)

    def test_an_owner_can_step_down_when_another_owner_exists(self):
        self.add('owner2', OWNER, org=self.org)
        response = self.as_role(OWNER).patch(
            url_member(self.org, self.memberships[OWNER]),
            {'role': ADMIN, 'confirm': True, 'password': PASSWORD}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['is_self'])

    def test_orphaning_without_active_offers_is_allowed_and_traced(self):
        # Le second propriétaire est sous sanction : le seul propriétaire effectif se rétrograde, sans offre active.
        other, _ = self.add('owner2', OWNER, org=self.org)
        Sanction.objects.create(
            user=other, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.users[ADMIN],
        ).apply()
        response = self.as_role(OWNER).patch(
            url_member(self.org, self.memberships[OWNER]),
            {'role': ADMIN, 'confirm': True, 'password': PASSWORD}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        details = AuditLog.objects.filter(action='MEMBERSHIP_ROLE_CHANGED').latest('created_at').details
        self.assertIn('orphaned=true', details)

    def test_owner_promotion_publishes_the_visibility_event_delivered_now(self):
        before = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count()
        self.assertEqual(self.patch(
            OWNER, ADMIN, OWNER, confirm=True, password=PASSWORD,
        ).status_code, 200)
        events = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed')
        self.assertEqual(events.count(), before + 1)
        event = events.latest('created_at')
        self.assertEqual(event.payload['reason'], 'owners_changed')
        self.assertEqual(event.payload['context_type'], 'ORGANIZATION')
        self.assertEqual(event.payload['context_id'], str(self.org.pk))

    def test_non_owner_role_change_publishes_no_visibility_event(self):
        before = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count()
        self.patch(ADMIN, EDITOR, ANALYST)
        self.assertEqual(
            OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count(), before,
        )

    def test_suspended_archived_and_restricted_actor(self):
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertDenied(self.patch(OWNER, EDITOR, ANALYST), DENY_SECURITY)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ARCHIVED)
        self.assertDenied(self.patch(OWNER, EDITOR, ANALYST), DENY_OBJECT_STATE)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ACTIVE)
        Sanction.objects.create(
            user=self.users[ADMIN], sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.owner,
        ).apply()
        self.assertEqual(self.patch(ADMIN, EDITOR, ANALYST).status_code in (401, 403), True)

    def test_non_member_is_refused_before_any_body_check(self):
        stranger = login(make_user('stranger'))
        response = stranger.patch(url_member(self.org, self.memberships[ADMIN]), {'role': OWNER}, format='json')
        self.assertDenied(response, DENY_RELATION)

    def test_anonymous_is_refused_and_unsupported_methods_are_405(self):
        self.assertEqual(APIClient().patch(url_member(self.org, self.memberships[EDITOR]), {'role': ADMIN}, format='json').status_code, 401)
        self.assertEqual(self.as_role(OWNER).get(url_member(self.org, self.memberships[EDITOR])).status_code, 405)
        self.assertEqual(self.as_role(OWNER).put(url_member(self.org, self.memberships[EDITOR]), {}, format='json').status_code, 405)

    def test_role_changed_after_the_check_but_before_the_lock_demands_the_password(self):
        """Concurrence : la cible devient propriétaire après la première lecture, avant le verrou ; sans
        ressaisie effectuée, l'opération est refusée et rien n'est écrit."""
        target = self.memberships[EDITOR]
        real_resolve = organizations._resolve_role_change
        calls = []

        def promote_after_first_read(*args, **kwargs):
            result = real_resolve(*args, **kwargs)
            if not calls:
                Membership.objects.filter(pk=target.pk).update(role=OWNER)
            calls.append(1)
            return result

        with mock.patch('apps.identity.organizations._resolve_role_change', side_effect=promote_after_first_read):
            response = self.patch(OWNER, EDITOR, ANALYST)
        self.assertDenied(response, 'reauthentication_failed')
        self.assertEqual(self.role_of(target), OWNER)

    def test_target_revoked_between_check_and_write_is_not_resurrected(self):
        """Mise à jour conditionnelle : une ligne déjà révoquée n'est jamais modifiée."""
        target = self.memberships[EDITOR]
        stale = Membership.objects.get(pk=target.pk)
        Membership.objects.filter(pk=target.pk).update(status=Membership.STATUS_REVOKED)
        org = Organization.objects.get(pk=self.org.pk)
        organizations._apply_role_change(self.owner, org, stale, ANALYST)
        self.assertEqual(self.role_of(target), EDITOR)
        self.assertEqual(self.status_of(target), Membership.STATUS_REVOKED)

    def test_sensitive_throttle_counts_only_sensitive_patches(self):
        from rest_framework.throttling import SimpleRateThrottle
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', {**SimpleRateThrottle.THROTTLE_RATES, 'org_sensitive': '2/hour'}):
            with override_settings(CACHES=LOCMEM_CACHE):
                cache.clear()
                client = self.as_role(OWNER)
                target = url_member(self.org, self.memberships[EDITOR])
                for _ in range(4):
                    self.assertEqual(client.patch(target, {'role': ANALYST}, format='json').status_code, 200)
                wrong = {'role': OWNER, 'confirm': True, 'password': 'm'}
                self.assertEqual(client.patch(target, wrong, format='json').status_code, 403)
                self.assertEqual(client.patch(target, wrong, format='json').status_code, 403)
                self.assertEqual(client.patch(target, wrong, format='json').status_code, 429)
                cache.clear()

    def test_rate_is_configured(self):
        from django.conf import settings
        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['org_sensitive'], '10/hour')


# --- Retrait ------------------------------------------------------------------------------------------------

class RemoveMemberTests(TeamBase):
    def delete(self, actor_role, target_role):
        return self.as_role(actor_role).delete(url_member(self.org, self.memberships[target_role]))

    def test_owner_and_admin_remove_lower_roles(self):
        self.assertEqual(self.delete(OWNER, EDITOR).status_code, 204)
        self.assertEqual(self.status_of(self.memberships[EDITOR]), Membership.STATUS_REVOKED)
        self.assertEqual(Membership.objects.get(pk=self.memberships[EDITOR].pk).end_reason, Membership.END_REMOVED)
        self.assertEqual(self.delete(ADMIN, ANALYST).status_code, 204)
        self.assertEqual(self.delete(OWNER, ADMIN).status_code, 204)

    def test_matrix_refusals(self):
        self.assertDenied(self.delete(ADMIN, OWNER), DENY_PERMISSION)
        self.assertDenied(self.delete(EDITOR, ANALYST), DENY_PERMISSION)
        self.assertDenied(self.delete(ANALYST, EDITOR), DENY_PERMISSION)
        self.assertDenied(self.delete(EDITOR, OWNER), DENY_PERMISSION)
        for role in (EDITOR, ANALYST, OWNER, ADMIN):
            self.assertEqual(self.status_of(self.memberships[role]), Membership.STATUS_ACTIVE)

    def test_removing_oneself_is_refused(self):
        self.assertDenied(self.delete(ADMIN, ADMIN), 'use_leave', 400)
        self.assertDenied(self.delete(OWNER, OWNER), 'use_leave', 400)

    def test_an_owner_cannot_be_removed_directly(self):
        _, second = self.add('owner2', OWNER, org=self.org)
        response = self.as_role(OWNER).delete(url_member(self.org, second))
        self.assertDenied(response, 'owner_must_be_demoted', 409)
        self.assertEqual(self.status_of(second), Membership.STATUS_ACTIVE)

    def test_removal_is_immediate_for_the_removed_person(self):
        admin = self.as_role(ADMIN)
        header = {'HTTP_X_CONTEXT': f'ORGANIZATION:{self.org.pk}'}
        self.assertEqual(admin.get('/api/v1/interactions/conversations/', **header).status_code, 200)
        self.delete(OWNER, ADMIN)
        response = admin.get('/api/v1/interactions/conversations/', **header)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], DENY_RELATION)
        self.assertEqual(admin.get('/api/v1/interactions/conversations/').status_code, 200)

    def test_unknown_foreign_and_revoked_member_are_404(self):
        other = Organization.objects.create(name='Autre', org_type='ENTREPRISE')
        _, foreign = self.add('foreign', EDITOR, org=other)
        client = self.as_role(OWNER)
        for target in (foreign.pk, uuid.uuid4()):
            self.assertDenied(client.delete(f'{ORGS}{self.org.pk}/members/{target}/'), 'member_not_found', 404)
        self.assertEqual(self.status_of(foreign), Membership.STATUS_ACTIVE)
        self.delete(OWNER, EDITOR)
        self.assertDenied(self.delete(OWNER, EDITOR), 'member_not_found', 404)

    def test_audit_event_and_no_personal_data(self):
        self.delete(OWNER, EDITOR)
        entry = AuditLog.objects.get(action='MEMBERSHIP_REVOKED')
        self.assertEqual(entry.actor_id, self.owner.pk)
        event = OutboxEvent.objects.filter(event_type='identity.membership_changed').latest('created_at')
        self.assertEqual(event.payload['change'], 'revoked')
        blob = entry.details + json.dumps(event.payload)
        for secret in (self.users[EDITOR].email, self.users[EDITOR].full_name):
            self.assertNotIn(secret, blob)

    def test_removing_a_non_owner_publishes_no_visibility_event(self):
        before = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count()
        self.delete(OWNER, EDITOR)
        self.assertEqual(
            OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count(), before,
        )

    def test_suspended_archived_and_non_member(self):
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertDenied(self.delete(OWNER, EDITOR), DENY_SECURITY)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ARCHIVED)
        self.assertDenied(self.delete(OWNER, EDITOR), DENY_OBJECT_STATE)
        stranger = login(make_user('stranger'))
        self.assertDenied(stranger.delete(url_member(self.org, self.memberships[EDITOR])), DENY_RELATION)
        self.assertEqual(APIClient().delete(url_member(self.org, self.memberships[EDITOR])).status_code, 401)

    def test_removed_member_can_rejoin_through_the_same_row_later(self):
        self.delete(OWNER, EDITOR)
        self.assertEqual(Membership.objects.filter(organization=self.org, user=self.users[EDITOR]).count(), 1)

    def test_stale_row_revoked_concurrently_gives_404_and_no_second_trace(self):
        stale = Membership.objects.get(pk=self.memberships[EDITOR].pk)
        Membership.objects.filter(pk=stale.pk).update(status=Membership.STATUS_REVOKED)
        audits = AuditLog.objects.count()
        with self.assertRaises(organizations.OrganizationError) as caught:
            organizations._end_membership(
                self.owner, self.org, stale, Membership.END_REMOVED, 'MEMBERSHIP_REVOKED',
            )
        self.assertEqual(caught.exception.get_codes(), 'member_not_found')
        self.assertEqual(AuditLog.objects.count(), audits)


# --- Départ (règle last_effective_owner sur leave/) ---------------------------------------------------------

class LeaveEffectiveOwnerTests(TeamBase):
    def test_sole_effective_owner_may_leave_when_the_organization_has_no_active_offer(self):
        other, _ = self.add('owner2', OWNER, org=self.org)
        Sanction.objects.create(
            user=other, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.users[ADMIN],
        ).apply()
        response = self.as_role(OWNER).post(f'{ORGS}{self.org.pk}/leave/')
        self.assertEqual(response.status_code, 204, response.content)
        details = AuditLog.objects.filter(action='MEMBERSHIP_REVOKED').latest('created_at').details
        self.assertIn('orphaned=true', details)
        event = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').latest('created_at')
        self.assertEqual(event.payload['reason'], 'owners_changed')

    def test_owner_leaving_with_another_effective_owner_is_not_orphaning(self):
        self.add('owner2', OWNER, org=self.org)
        self.assertEqual(self.as_role(OWNER).post(f'{ORGS}{self.org.pk}/leave/').status_code, 204)
        details = AuditLog.objects.filter(action='MEMBERSHIP_REVOKED').latest('created_at').details
        self.assertNotIn('orphaned', details)

    def test_last_owner_still_wins(self):
        response = self.as_role(OWNER).post(f'{ORGS}{self.org.pk}/leave/')
        self.assertDenied(response, 'last_owner', 409)

    def test_a_non_owner_leaving_publishes_no_visibility_event(self):
        before = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count()
        self.assertEqual(self.as_role(EDITOR).post(f'{ORGS}{self.org.pk}/leave/').status_code, 204)
        self.assertEqual(
            OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count(), before,
        )

    def test_the_rule_is_not_applied_to_a_suspended_organization(self):
        other, _ = self.add('owner2', OWNER, org=self.org)
        Sanction.objects.create(
            user=other, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.users[ADMIN],
        ).apply()
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertEqual(self.as_role(OWNER).post(f'{ORGS}{self.org.pk}/leave/').status_code, 204)
        self.assertNotIn(
            'orphaned', AuditLog.objects.filter(action='MEMBERSHIP_REVOKED').latest('created_at').details,
        )


# --- Transfert de propriété ---------------------------------------------------------------------------------

class TransferOwnershipTests(TeamBase):
    def post(self, actor_role='OWNER', target_role=ADMIN, org=None, **body):
        payload = {
            'membership_id': str(self.memberships[target_role].pk), 'confirm': True, 'password': PASSWORD, **body,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        return self.as_role(actor_role).post(url_transfer(org or self.org), payload, format='json')

    def test_nominal_transfer_is_atomic_and_returns_both_members(self):
        response = self.post(target_role=EDITOR)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(set(body), {'new_owner', 'me'})
        self.assertEqual(set(body['new_owner']), MEMBER_KEYS)
        self.assertEqual(set(body['me']), MEMBER_KEYS)
        self.assertEqual((body['new_owner']['role'], body['me']['role']), (OWNER, ADMIN))
        self.assertTrue(body['me']['is_self'])
        self.assertIs(body['new_owner']['is_last_effective_owner'], True)
        self.assertIs(body['me']['is_last_effective_owner'], False)
        self.assertEqual(self.role_of(self.memberships[EDITOR]), OWNER)
        self.assertEqual(self.role_of(self.memberships[OWNER]), ADMIN)
        actions = list(AuditLog.objects.filter(action__in=(
            'MEMBERSHIP_ROLE_CHANGED', 'ORG_OWNERSHIP_TRANSFERRED',
        )).values_list('action', flat=True))
        self.assertEqual(sorted(actions), ['MEMBERSHIP_ROLE_CHANGED', 'MEMBERSHIP_ROLE_CHANGED', 'ORG_OWNERSHIP_TRANSFERRED'])
        self.assertIn('reauth=true', AuditLog.objects.get(action='ORG_OWNERSHIP_TRANSFERRED').details)
        self.assertTrue(OutboxEvent.objects.filter(
            event_type='identity.seller_context_status_changed', payload__reason='owners_changed',
        ).exists())

    def test_my_new_role_choices(self):
        for role in (EDITOR, ANALYST, ADMIN):
            with self.subTest(role=role):
                for r, membership in self.memberships.items():
                    Membership.objects.filter(pk=membership.pk).update(role=r)
                response = self.post(target_role=ADMIN, my_new_role=role)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()['me']['role'], role)
                self.assertIsNone(response.json()['me']['is_last_effective_owner'] if role != ADMIN else None)

    def test_invalid_my_new_role_is_a_field_error(self):
        for value in (OWNER, 'GOD', '', 3, ['ADMIN']):
            with self.subTest(value=value):
                response = self.post(my_new_role=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn('my_new_role', response.json())
        self.assertEqual(self.role_of(self.memberships[OWNER]), OWNER)

    def test_confirmation_and_password_are_required(self):
        self.assertDenied(self.post(confirm=None), 'confirmation_required', 400)
        self.assertDenied(self.post(confirm=False), 'confirmation_required', 400)
        self.assertDenied(self.post(confirm='yes'), 'confirmation_required', 400)
        self.assertDenied(self.post(password=None), 'password_required', 400)
        self.assertDenied(self.post(password=''), 'password_required', 400)
        self.assertEqual(self.role_of(self.memberships[OWNER]), OWNER)

    def test_wrong_password_is_refused_audited_and_changes_nothing(self):
        response = self.post(password='mauvais')
        self.assertDenied(response, 'reauthentication_failed')
        entry = AuditLog.objects.get(action='ORG_SENSITIVE_REAUTH_FAILED')
        self.assertIn('action=transfer', entry.details)
        self.assertNotIn('mauvais', entry.details)
        self.assertEqual(self.role_of(self.memberships[OWNER]), OWNER)
        self.assertEqual(self.role_of(self.memberships[ADMIN]), ADMIN)
        self.assertFalse(AuditLog.objects.filter(action='ORG_OWNERSHIP_TRANSFERRED').exists())

    def test_repeated_wrong_passwords_are_limited(self):
        for _ in range(5):
            self.assertDenied(self.post(password='mauvais'), 'reauthentication_failed')
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(self.role_of(self.memberships[OWNER]), OWNER)

    def test_only_an_owner_may_transfer(self):
        for role in (ADMIN, EDITOR, ANALYST):
            with self.subTest(role=role):
                response = self.post(actor_role=role, target_role=EDITOR if role != EDITOR else ANALYST)
                self.assertDenied(response, DENY_PERMISSION)
                self.assertFalse(AuditLog.objects.filter(action='ORG_SENSITIVE_REAUTH_FAILED').exists())
        self.assertEqual(self.role_of(self.memberships[OWNER]), OWNER)

    def test_transfer_to_oneself_is_invalid(self):
        self.assertDenied(self.post(target_role=OWNER), 'invalid_transfer', 400)

    def test_unknown_foreign_revoked_and_malformed_targets(self):
        other = Organization.objects.create(name='Autre', org_type='ENTREPRISE')
        _, foreign = self.add('foreign', EDITOR, org=other)
        for target in (foreign.pk, uuid.uuid4()):
            response = self.as_role(OWNER).post(
                url_transfer(self.org), {'membership_id': str(target), 'confirm': True, 'password': PASSWORD},
                format='json',
            )
            self.assertDenied(response, 'member_not_found', 404)
        Membership.objects.filter(pk=self.memberships[ADMIN].pk).update(status=Membership.STATUS_REVOKED)
        self.assertDenied(self.post(), 'member_not_found', 404)
        for bad in (None, '', 'pas-un-uuid', 12):
            response = self.as_role(OWNER).post(
                url_transfer(self.org), {'membership_id': bad, 'confirm': True, 'password': PASSWORD}, format='json',
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn('membership_id', response.json())

    def test_unavailable_target_is_a_neutral_400(self):
        User.objects.filter(pk=self.users[ADMIN].pk).update(is_active=False)
        self.assertDenied(self.post(), 'user_unavailable', 400)
        self.assertEqual(self.role_of(self.memberships[OWNER]), OWNER)

    def test_restricted_target_is_refused(self):
        Sanction.objects.create(
            user=self.users[ADMIN], sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.owner,
        ).apply()
        self.assertDenied(self.post(), 'user_unavailable', 400)

    def test_failure_of_the_second_step_leaves_everything_unchanged(self):
        real = organizations._apply_role_change
        calls = []

        def fail_on_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('boom')
            return real(*args, **kwargs)

        audits, events = AuditLog.objects.count(), OutboxEvent.objects.count()
        client = self.as_role(OWNER)
        client.raise_request_exception = False
        with mock.patch('apps.identity.organizations._apply_role_change', side_effect=fail_on_second):
            response = client.post(url_transfer(self.org), {
                'membership_id': str(self.memberships[ADMIN].pk), 'confirm': True, 'password': PASSWORD,
            }, format='json')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.role_of(self.memberships[ADMIN]), ADMIN)
        self.assertEqual(self.role_of(self.memberships[OWNER]), OWNER)
        self.assertEqual((AuditLog.objects.count(), OutboxEvent.objects.count()), (audits, events))

    def test_allowed_on_an_archived_organization_and_refused_on_a_suspended_one(self):
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertDenied(self.post(), DENY_SECURITY)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ARCHIVED)
        self.assertEqual(self.post().status_code, 200)

    def test_non_member_unknown_organization_and_anonymous(self):
        stranger = login(make_user('stranger'))
        body = {'membership_id': str(self.memberships[ADMIN].pk), 'confirm': True, 'password': PASSWORD}
        self.assertDenied(stranger.post(url_transfer(self.org), body, format='json'), DENY_RELATION)
        self.assertDenied(
            self.as_role(OWNER).post(f'{ORGS}{uuid.uuid4()}/transfer-ownership/', body, format='json'), DENY_RELATION,
        )
        self.assertEqual(APIClient().post(url_transfer(self.org), body, format='json').status_code, 401)

    def test_old_owner_loses_the_owner_rights_immediately(self):
        self.post()
        response = self.as_role(OWNER).post(
            url_transfer(self.org), {
                'membership_id': str(self.memberships[ADMIN].pk), 'confirm': True, 'password': PASSWORD,
            }, format='json',
        )
        self.assertDenied(response, DENY_PERMISSION)

    def test_transfer_to_an_existing_co_owner_steps_the_actor_down(self):
        _, second = self.add('owner2', OWNER, org=self.org)
        response = self.as_role(OWNER).post(
            url_transfer(self.org), {'membership_id': str(second.pk), 'confirm': True, 'password': PASSWORD},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.role_of(second), OWNER)
        self.assertEqual(self.role_of(self.memberships[OWNER]), ADMIN)

    def test_no_plan_or_payment_parameter_is_read(self):
        response = self.post(plan='PREMIUM', paid=True, price=10)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(word in json.dumps(response.json()) for word in ('plan', 'price', 'paid')))

    def test_service_transfer_by_user_id_still_works(self):
        services.transfer_ownership(self.owner, self.org.pk, self.users[ADMIN].pk)
        self.assertEqual(self.role_of(self.memberships[ADMIN]), OWNER)
        self.assertNotIn('reauth', AuditLog.objects.get(action='ORG_OWNERSHIP_TRANSFERRED').details)


# --- Données personnelles, notifications, garde de routes ----------------------------------------------------

class TeamPrivacyAndGuardTests(TeamBase):
    def test_no_personal_data_in_audit_outbox_or_notifications(self):
        user, membership = self.add(
            'sentinel', EDITOR, org=self.org, full_name=SECRET_NAME, phone='+243999000777',
        )
        client = self.as_role(OWNER)
        client.patch(url_member(self.org, membership), {'role': ANALYST}, format='json')
        client.patch(
            url_member(self.org, self.memberships[ADMIN]), {'role': OWNER, 'confirm': True, 'password': 'faux'},
            format='json',
        )
        client.post(url_transfer(self.org), {
            'membership_id': str(self.memberships[ADMIN].pk), 'confirm': True, 'password': PASSWORD,
        }, format='json')
        self.as_role(ADMIN).delete(url_member(self.org, membership))
        blobs = [a.details for a in AuditLog.objects.all()]
        blobs += [json.dumps(e.payload) for e in OutboxEvent.objects.all()]
        blobs += [f'{n.title} {n.content} {n.link}' for n in Notification.objects.all()]
        text = ' '.join(blobs)
        for secret in (SECRET_NAME, 'Sentinelle', SECRET_PHONE, user.email, PASSWORD + PASSWORD, 'faux'):
            self.assertNotIn(secret, text)

    def test_new_team_routes_declare_the_exemption_and_post_members_is_absent(self):
        self.assertEqual([r for r in collect_unguarded_write_routes() if 'organizations' in r], [])
        self.assertNotIn('add_member', open(
            __import__('apps.identity.views_organizations', fromlist=['x']).__file__, encoding='utf-8',
        ).read())

    def test_every_team_view_ignores_x_context(self):
        from . import views_organizations as v
        for view in (v.OrganizationMembersView, v.OrganizationMemberDetailView, v.OrganizationTransferOwnershipView):
            self.assertTrue(view.acting_context_exempt)


class SharedEffectiveOwnerDefinitionTests(TeamBase):
    def test_visibility_and_the_team_rule_use_the_same_definition(self):
        other, _ = self.add('owner2', OWNER, org=self.org)
        for restricted in (False, True):
            if restricted:
                Sanction.objects.create(
                    user=other, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.users[ADMIN],
                ).apply()
            expected = organizations.count_effective_owners(self.org.pk)
            public = services.get_seller_context_public_flags([('ORGANIZATION', self.org.pk)])
            self.assertEqual(public[('ORGANIZATION', self.org.pk)], expected > 0)
            self.assertEqual(expected, 1 if restricted else 2)

    def test_no_effective_owner_means_not_public(self):
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assertEqual(organizations.count_effective_owners(self.org.pk), 0)
        self.assertFalse(services.get_seller_context_public_flags([('ORGANIZATION', self.org.pk)])[('ORGANIZATION', self.org.pk)])
        self.assertIsNone(services.sole_effective_owner_id(self.org.pk))


class TeamOpenApiTests(TestCase):
    def test_team_routes_are_documented_with_their_methods(self):
        from drf_spectacular.generators import SchemaGenerator
        paths = SchemaGenerator().get_schema(request=None, public=True)['paths']
        found = {p: sorted(m for m in ops if m in ('get', 'post', 'patch', 'delete')) for p, ops in paths.items() if p.startswith('/api/v1/accounts/organizations/') and ('members' in p or 'transfer' in p)}
        self.assertEqual(sorted(found.values()), [['delete', 'patch'], ['get'], ['post']], found)


class ReviewFixesTests(TeamBase):
    def test_delete_never_consumes_the_org_sensitive_quota(self):
        from rest_framework.throttling import SimpleRateThrottle
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'org_sensitive': '2/hour', 'org_write': '1000/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            client = self.as_role(OWNER)
            for index in range(6):
                _, membership = self.add(f'del{index}', ANALYST, org=self.org)
                self.assertEqual(client.delete(url_member(self.org, membership)).status_code, 204)

    def test_transfer_post_still_consumes_the_org_sensitive_quota(self):
        from rest_framework.throttling import SimpleRateThrottle
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'org_sensitive': '1/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            client = self.as_role(OWNER)
            body = {'membership_id': str(self.memberships[ADMIN].pk), 'confirm': True, 'password': 'faux'}
            self.assertEqual(client.post(url_transfer(self.org), body, format='json').status_code, 403)
            self.assertEqual(client.post(url_transfer(self.org), body, format='json').status_code, 429)

    def test_failure_limiter_acquire_counts_before_verification(self):
        from .throttles import FailureLimiter
        from rest_framework.exceptions import Throttled
        limiter = FailureLimiter('t-acquire', threshold=3)
        for _ in range(3):
            limiter.acquire('k')  # trois tentatives en vol, aucune n'a encore « échoué » ni réussi
        with self.assertRaises(Throttled):
            limiter.acquire('k')
        with self.assertRaises(Throttled):
            limiter.acquire('k')
        self.assertEqual(cache.get('fail:t-acquire:k'), 3)  # les tentatives refusées ne gonflent pas le compteur
        limiter.success('k')
        limiter.acquire('k')

    def test_same_role_on_an_owner_seat_needs_no_password_and_uses_no_quota(self):
        response = self.as_role(OWNER).patch(
            url_member(self.org, self.memberships[OWNER]), {'role': OWNER}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(AuditLog.objects.filter(action='ORG_SENSITIVE_REAUTH_FAILED').exists())
        self.assertFalse(AuditLog.objects.filter(action='MEMBERSHIP_ROLE_CHANGED').exists())
        self.assertIsNone(cache.get('fail:org_reauth:' + str(self.owner.pk)))

    def test_same_role_still_requires_the_permission(self):
        response = self.as_role(ADMIN).patch(
            url_member(self.org, self.memberships[OWNER]), {'role': OWNER}, format='json',
        )
        self.assertDenied(response, DENY_PERMISSION)

    def test_transfer_publishes_owners_changed_once(self):
        before = OutboxEvent.objects.filter(payload__reason='owners_changed').count()
        body = {'membership_id': str(self.memberships[ADMIN].pk), 'confirm': True, 'password': PASSWORD}
        self.assertEqual(self.as_role(OWNER).post(url_transfer(self.org), body, format='json').status_code, 200)
        self.assertEqual(OutboxEvent.objects.filter(payload__reason='owners_changed').count(), before + 1)

    def test_transfer_response_flag_follows_the_effective_role_after_transfer(self):
        body = {
            'membership_id': str(self.memberships[ADMIN].pk), 'confirm': True, 'password': PASSWORD,
            'my_new_role': ANALYST,
        }
        data = self.as_role(OWNER).post(url_transfer(self.org), body, format='json').json()
        self.assertIsNone(data['me']['is_last_effective_owner'])
        self.assertIsNone(data['new_owner']['is_last_effective_owner'])
        for key in ('me', 'new_owner'):
            self.assertEqual(set(data[key]), MEMBER_KEYS)

