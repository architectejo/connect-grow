"""Rôle « Membre » et périmètre des appartenances (L1-01-B6 ; ADR 0010 D2, D3, §4.1, §4.2, §6.1, §10 ; contrat d'API
L1-01 §7.1 et §7.2).

- `MEMBER` : capacités `org.view_internal` et `org.leave` seulement (matrice case par case dans `tests_organizations`) ;
- `scope_covers` et `can_delegate` : tests purs sur des périmètres fictifs `CITY` (inactifs en V1) ;
- contraintes `CHECK` en base ; `authorize_on(target_scope=...)` et `can(target_scope=...)` ;
- API : `Member.scope`, `PATCH` avec `scope` (seule valeur acceptée : organisation entière), rôle `MEMBER` dans
  `members/`, `internal/` et `contexts/` ;
- garde de la migration inverse `identity 0018`."""
import uuid

from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_USER, DENY_PERMISSION, ContextDenied
from apps.moderation.models import AuditLog

from . import capabilities, organizations, services
from .capabilities import (
    ORGANIZATION_SCOPE, ROLE_ADMIN as ADMIN, ROLE_ANALYST as ANALYST, ROLE_EDITOR as EDITOR, ROLE_MEMBER as MEMBER,
    ROLE_OWNER as OWNER, SCOPE_CITY, SCOPE_ORGANIZATION, SCOPE_UNIT, Scope, can_delegate, scope_covers,
)
from .models import Membership, Organization, OrganizationInvitation, User

ORGS = '/api/v1/accounts/organizations/'
CONTEXTS = '/api/v1/accounts/contexts/'
PASSWORD = 'x'
ORG_SCOPE_JSON = {'type': 'ORGANIZATION', 'id': None}
SCOPE_MESSAGE = "Ce périmètre n'est pas encore disponible."
MEMBER_CAPABILITIES = ['org.leave', 'org.view_internal']
LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'b6-scope'}}

KINSHASA = Scope(SCOPE_CITY, uuid.UUID('11111111-1111-4111-8111-111111111111'))
LUBUMBASHI = Scope(SCOPE_CITY, uuid.UUID('22222222-2222-4222-8222-222222222222'))


def make_user(label):
    return User.objects.create_user(
        email=f'{label}-{uuid.uuid4().hex[:6]}@example.com', password=PASSWORD, full_name=f'Nom {label}',
        phone_verified=True,
    )


def login(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def force_scope(membership, scope):
    """Périmètre fictif posé directement en base (inatteignable par l'API en V1)."""
    Membership.objects.filter(pk=membership.pk).update(scope_type=scope.type, scope_id=scope.id)
    membership.refresh_from_db()
    return membership


# --- Rôle MEMBER : constantes et matrice ------------------------------------------------------------------------

class MemberRoleConstantsTests(SimpleTestCase):
    def test_member_role_is_declared_with_rank_zero_and_french_label(self):
        self.assertEqual(MEMBER, 'MEMBER')
        self.assertEqual(capabilities.ROLES, (OWNER, ADMIN, EDITOR, ANALYST, MEMBER))
        self.assertEqual(dict(capabilities.ROLE_CHOICES)[MEMBER], 'Membre')
        self.assertEqual(capabilities.ROLE_RANK[MEMBER], 0)
        self.assertEqual(services.get_role_label(MEMBER), 'Membre')

    def test_member_has_only_view_internal_and_leave(self):
        self.assertEqual(capabilities.capabilities_for_role(MEMBER), MEMBER_CAPABILITIES)
        self.assertEqual(capabilities.capabilities_for_context(CONTEXT_ORGANIZATION, MEMBER), MEMBER_CAPABILITIES)
        for capability in ('stats.view', 'offer.view_internal', 'offer.publish', 'org.manage_members', 'message.reply'):
            with self.subTest(capability=capability):
                self.assertFalse(capabilities.role_has_capability(MEMBER, capability))

    def test_member_is_managed_like_analyst_and_manages_nobody(self):
        self.assertTrue(capabilities.can_manage_role_of(OWNER, MEMBER))
        self.assertTrue(capabilities.can_manage_role_of(ADMIN, MEMBER))
        self.assertFalse(capabilities.can_manage_role_of(EDITOR, MEMBER))
        self.assertFalse(capabilities.can_manage_role_of(ANALYST, MEMBER))
        for role in capabilities.ROLES:
            with self.subTest(role=role):
                self.assertFalse(capabilities.can_manage_role_of(MEMBER, role))

    def test_scope_types_declared_and_only_organization_active(self):
        self.assertEqual(capabilities.SCOPE_TYPES, (SCOPE_ORGANIZATION, SCOPE_CITY, SCOPE_UNIT))
        self.assertEqual(capabilities.ACTIVE_SCOPE_TYPES, (SCOPE_ORGANIZATION,))
        self.assertEqual(ORGANIZATION_SCOPE, Scope('ORGANIZATION', None))


# --- scope_covers et can_delegate : tests purs (périmètres fictifs CITY) ------------------------------------------

class ScopeCoversTests(SimpleTestCase):
    def test_organization_covers_everything(self):
        for target in (ORGANIZATION_SCOPE, KINSHASA, LUBUMBASHI, Scope(SCOPE_UNIT, uuid.uuid4()), None):
            with self.subTest(target=target):
                self.assertTrue(scope_covers(ORGANIZATION_SCOPE, target))

    def test_none_means_whole_organization_on_both_sides(self):
        self.assertTrue(scope_covers(None, KINSHASA))
        self.assertFalse(scope_covers(KINSHASA, None))

    def test_a_city_covers_itself_only(self):
        self.assertTrue(scope_covers(KINSHASA, KINSHASA))
        self.assertTrue(scope_covers(KINSHASA, Scope(SCOPE_CITY, str(KINSHASA.id))))  # identifiant en chaîne
        self.assertFalse(scope_covers(KINSHASA, LUBUMBASHI))
        self.assertFalse(scope_covers(KINSHASA, ORGANIZATION_SCOPE))
        self.assertFalse(scope_covers(KINSHASA, Scope(SCOPE_UNIT, KINSHASA.id)))  # même UUID, autre type


class CanDelegateTests(SimpleTestCase):
    def test_a_branch_administrator_does_not_create_a_global_administrator(self):
        """Q23 : « un administrateur limité à une branche ne crée pas un administrateur global »."""
        self.assertFalse(can_delegate(ADMIN, KINSHASA, ADMIN, ORGANIZATION_SCOPE))
        self.assertFalse(can_delegate(ADMIN, KINSHASA, EDITOR, ORGANIZATION_SCOPE))
        self.assertFalse(can_delegate(ADMIN, KINSHASA, MEMBER, LUBUMBASHI))

    def test_a_branch_administrator_delegates_inside_his_branch(self):
        for role in (ADMIN, EDITOR, ANALYST, MEMBER):
            with self.subTest(role=role):
                self.assertTrue(can_delegate(ADMIN, KINSHASA, role, KINSHASA))

    def test_an_organization_wide_actor_delegates_any_scope_within_his_role_authority(self):
        for role in (ADMIN, EDITOR, ANALYST, MEMBER):
            for scope in (ORGANIZATION_SCOPE, KINSHASA):
                with self.subTest(role=role, scope=scope):
                    self.assertTrue(can_delegate(OWNER, ORGANIZATION_SCOPE, role, scope))
                    self.assertTrue(can_delegate(ADMIN, ORGANIZATION_SCOPE, role, scope))

    def test_role_authority_still_applies(self):
        self.assertFalse(can_delegate(ADMIN, ORGANIZATION_SCOPE, OWNER, ORGANIZATION_SCOPE))
        for actor in (EDITOR, ANALYST, MEMBER):
            for role in capabilities.ROLES:
                with self.subTest(actor=actor, role=role):
                    self.assertFalse(can_delegate(actor, ORGANIZATION_SCOPE, role, ORGANIZATION_SCOPE))


# --- Contraintes en base ------------------------------------------------------------------------------------------

class ScopeDatabaseConstraintTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Atelier Périmètre', org_type='ENTREPRISE')

    def create(self, role, scope_type, scope_id):
        return Membership.objects.create(
            organization=self.org, user=make_user('contrainte'), role=role, scope_type=scope_type, scope_id=scope_id,
        )

    def assertRefused(self, role, scope_type, scope_id):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create(role, scope_type, scope_id)

    def test_defaults_are_whole_organization(self):
        membership = Membership.objects.create(organization=self.org, user=make_user('defaut'), role=EDITOR)
        membership.refresh_from_db()
        self.assertEqual((membership.scope_type, membership.scope_id), (SCOPE_ORGANIZATION, None))

    def test_primary_administrator_always_covers_the_whole_organization(self):
        self.assertRefused(OWNER, SCOPE_CITY, KINSHASA.id)
        self.assertRefused(OWNER, SCOPE_UNIT, uuid.uuid4())
        self.create(OWNER, SCOPE_ORGANIZATION, None)

    def test_scope_identifier_is_null_iff_whole_organization(self):
        self.assertRefused(EDITOR, SCOPE_ORGANIZATION, uuid.uuid4())
        self.assertRefused(EDITOR, SCOPE_CITY, None)
        self.create(ADMIN, SCOPE_CITY, KINSHASA.id)  # valeur réservée, acceptée par la base (refusée par les services)

    def test_invitation_scope_is_consistent_too(self):
        def invite(scope_type, scope_id):
            return OrganizationInvitation.objects.create(
                organization=self.org, role=EDITOR, token_hash=uuid.uuid4().hex, expires_at='2030-01-01T00:00:00Z',
                scope_type=scope_type, scope_id=scope_id,
            )
        invitation = invite(SCOPE_ORGANIZATION, None)
        self.assertEqual(invitation.scope_type, SCOPE_ORGANIZATION)
        for scope_type, scope_id in ((SCOPE_ORGANIZATION, uuid.uuid4()), (SCOPE_CITY, None)):
            with self.subTest(scope_type=scope_type), self.assertRaises(IntegrityError), transaction.atomic():
                invite(scope_type, scope_id)


# --- authorize_on / can avec target_scope ------------------------------------------------------------------------

class TargetScopeAuthorizationTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Atelier Autorisation', org_type='ENTREPRISE')
        self.user = make_user('editeur')
        self.membership = Membership.objects.create(organization=self.org, user=self.user, role=EDITOR)

    def test_default_target_is_the_whole_organization_and_unchanged_for_callers(self):
        ctx = services.authorize_on(self.user, CONTEXT_ORGANIZATION, self.org.pk, 'offer.edit')
        self.assertEqual(ctx.role, EDITOR)
        self.assertTrue(services.can(self.user.pk, CONTEXT_ORGANIZATION, self.org.pk, 'offer.edit'))

    def test_organization_wide_membership_covers_any_target_scope(self):
        for target in (ORGANIZATION_SCOPE, KINSHASA):
            with self.subTest(target=target):
                services.authorize_on(self.user, CONTEXT_ORGANIZATION, self.org.pk, 'offer.edit', target_scope=target)
                self.assertTrue(services.can(
                    self.user.pk, CONTEXT_ORGANIZATION, self.org.pk, 'offer.edit', target_scope=target,
                ))

    def test_city_membership_is_refused_outside_its_city(self):
        force_scope(self.membership, KINSHASA)
        services.authorize_on(self.user, CONTEXT_ORGANIZATION, self.org.pk, 'offer.edit', target_scope=KINSHASA)
        for target in (None, ORGANIZATION_SCOPE, LUBUMBASHI):
            with self.subTest(target=target):
                with self.assertRaises(ContextDenied) as ctx:
                    services.authorize_on(
                        self.user, CONTEXT_ORGANIZATION, self.org.pk, 'offer.edit', target_scope=target,
                    )
                self.assertEqual(ctx.exception.detail.code, DENY_PERMISSION)
                self.assertFalse(services.can(
                    self.user.pk, CONTEXT_ORGANIZATION, self.org.pk, 'offer.edit', target_scope=target,
                ))

    def test_capability_is_checked_before_scope(self):
        """Un rôle sans la capacité est refusé même sur un périmètre couvert."""
        Membership.objects.filter(pk=self.membership.pk).update(role=MEMBER)
        with self.assertRaises(ContextDenied) as ctx:
            services.authorize_on(self.user, CONTEXT_ORGANIZATION, self.org.pk, 'stats.view', target_scope=None)
        self.assertEqual(ctx.exception.detail.code, DENY_PERMISSION)
        services.authorize_on(self.user, CONTEXT_ORGANIZATION, self.org.pk, 'org.view_internal')

    def test_personal_context_ignores_target_scope(self):
        services.authorize_on(self.user, CONTEXT_USER, self.user.pk, 'offer.edit', target_scope=KINSHASA)


# --- Services : validation du périmètre, délégation, audit -------------------------------------------------------

class ScopeServiceTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Atelier Services', org_type='ENTREPRISE')
        self.owner = make_user('owner')
        self.admin = make_user('admin')
        self.editor = make_user('editor')
        Membership.objects.create(organization=self.org, user=self.owner, role=OWNER)
        self.admin_membership = Membership.objects.create(organization=self.org, user=self.admin, role=ADMIN)
        self.editor_membership = Membership.objects.create(organization=self.org, user=self.editor, role=EDITOR)

    def test_validate_scope_accepts_only_the_whole_organization(self):
        self.assertEqual(organizations._validate_scope(None), ORGANIZATION_SCOPE)
        self.assertEqual(organizations._validate_scope({'type': 'ORGANIZATION', 'id': None}), ORGANIZATION_SCOPE)
        self.assertEqual(organizations._validate_scope({'type': 'ORGANIZATION'}), ORGANIZATION_SCOPE)
        for bad in (
            {'type': 'CITY', 'id': str(KINSHASA.id)}, {'type': 'UNIT', 'id': str(uuid.uuid4())},
            {'type': 'ORGANIZATION', 'id': str(uuid.uuid4())}, {'type': 'PLANETE', 'id': None}, {},
            {'type': 'ORGANIZATION', 'id': None, 'extra': 1}, 'ORGANIZATION', ['ORGANIZATION'], 42,
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError) as ctx:
                organizations._validate_scope(bad)
            self.assertEqual(ctx.exception.detail, {'scope': [SCOPE_MESSAGE]})

    def test_change_role_to_member_is_audited_without_scope_when_whole_organization(self):
        membership = services.change_role(self.owner, self.org.pk, self.editor_membership.pk, MEMBER)
        self.assertEqual((membership.role, membership.scope_type, membership.scope_id), (MEMBER, SCOPE_ORGANIZATION, None))
        log = AuditLog.objects.get(action='MEMBERSHIP_ROLE_CHANGED')
        self.assertIn('new_role=MEMBER', log.details)
        self.assertNotIn('scope_type', log.details)

    def test_reserved_scope_is_traced_when_written_internally(self):
        """Un périmètre autre qu'`ORGANIZATION` (écrit par le noyau, jamais par l'API en V1) est tracé."""
        organization = Organization.objects.select_for_update().get(pk=self.org.pk)
        organizations._apply_role_change(self.owner, organization, self.editor_membership, ANALYST, new_scope=KINSHASA)
        self.editor_membership.refresh_from_db()
        self.assertEqual((self.editor_membership.scope_type, self.editor_membership.scope_id), KINSHASA)
        log = AuditLog.objects.get(action='MEMBERSHIP_ROLE_CHANGED')
        self.assertIn(f'scope_type=CITY; scope_id={KINSHASA.id}', log.details)

    def test_primary_administrator_scope_is_forced_to_whole_organization(self):
        force_scope(self.editor_membership, KINSHASA)
        organization = Organization.objects.select_for_update().get(pk=self.org.pk)
        organizations._apply_role_change(self.owner, organization, self.editor_membership, OWNER, new_scope=KINSHASA)
        self.editor_membership.refresh_from_db()
        self.assertEqual((self.editor_membership.role, self.editor_membership.scope_type), (OWNER, SCOPE_ORGANIZATION))
        self.assertIsNone(self.editor_membership.scope_id)

    def test_branch_administrator_cannot_manage_organization_wide_members(self):
        force_scope(self.admin_membership, KINSHASA)
        for call in (
            lambda: services.change_role(self.admin, self.org.pk, self.editor_membership.pk, ANALYST),
            lambda: services.remove_member(self.admin, self.org.pk, self.editor_membership.pk),
            lambda: services.change_member_role(self.admin, self.org.pk, self.editor.pk, ANALYST),
            lambda: services.revoke_member(self.admin, self.org.pk, self.editor.pk),
            lambda: services.add_member(self.admin, self.org.pk, make_user('ajout').pk, MEMBER),
        ):
            with self.assertRaises(ContextDenied) as ctx:
                call()
            self.assertEqual(ctx.exception.detail.code, DENY_PERMISSION)
        self.editor_membership.refresh_from_db()
        self.assertEqual((self.editor_membership.role, self.editor_membership.status), (EDITOR, Membership.STATUS_ACTIVE))

    def test_branch_administrator_manages_a_member_of_his_branch(self):
        force_scope(self.admin_membership, KINSHASA)
        force_scope(self.editor_membership, KINSHASA)
        # Le PATCH n'accepte que l'organisation entière en V1 : le noyau (périmètre inchangé) est exercé directement.
        membership = services.change_member_role(self.admin, self.org.pk, self.editor.pk, MEMBER)
        self.assertEqual((membership.role, membership.scope_type), (MEMBER, SCOPE_CITY))
        # Le PATCH avec le périmètre par défaut (organisation entière) reste refusé : il élargirait le périmètre.
        with self.assertRaises(ContextDenied):
            services.change_role(self.admin, self.org.pk, self.editor_membership.pk, ANALYST)

    def test_reactivation_resets_the_scope(self):
        force_scope(self.editor_membership, KINSHASA)
        services.revoke_member(self.owner, self.org.pk, self.editor.pk)
        membership = services.add_member(self.owner, self.org.pk, self.editor.pk, MEMBER)
        self.assertEqual((membership.pk, membership.role), (self.editor_membership.pk, MEMBER))
        self.assertEqual((membership.scope_type, membership.scope_id), (SCOPE_ORGANIZATION, None))

    def test_member_is_not_yet_invitable(self):
        """Invitations v2 (B7) hors périmètre : `MEMBER` reste hors `INVITABLE_ROLES` jusque-là."""
        with self.assertRaises(services.OrganizationError) as ctx:
            services.create_invitation(self.owner, self.org.pk, MEMBER)
        self.assertEqual(ctx.exception.detail.code, 'invitation_role_not_allowed')


# --- API ----------------------------------------------------------------------------------------------------------

@override_settings(CACHES=LOCMEM_CACHE)
class MemberScopeApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name='Atelier API Membre', org_type='ENTREPRISE')
        self.owner, self.admin, self.editor, self.member = (
            make_user('owner'), make_user('admin'), make_user('editor'), make_user('member'),
        )
        Membership.objects.create(organization=self.org, user=self.owner, role=OWNER)
        self.admin_m = Membership.objects.create(organization=self.org, user=self.admin, role=ADMIN)
        self.editor_m = Membership.objects.create(organization=self.org, user=self.editor, role=EDITOR)
        self.member_m = Membership.objects.create(organization=self.org, user=self.member, role=MEMBER)

    def url_member(self, membership):
        return f'{ORGS}{self.org.pk}/members/{membership.pk}/'

    def patch(self, actor, membership, body):
        return login(actor).patch(self.url_member(membership), body, format='json')

    def test_members_list_exposes_scope_and_orders_members_last(self):
        response = login(self.member).get(f'{ORGS}{self.org.pk}/members/')
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()['results']
        self.assertEqual([row['role'] for row in rows], [OWNER, ADMIN, EDITOR, MEMBER])
        for row in rows:
            self.assertEqual(row['scope'], ORG_SCOPE_JSON)
            self.assertIsNone(row['is_last_effective_owner'])  # MEMBER n'a pas `org.manage_members`

    def test_patch_to_member_returns_member_with_scope(self):
        for body in ({'role': MEMBER}, {'role': MEMBER, 'scope': ORG_SCOPE_JSON}, {'role': MEMBER, 'scope': None}):
            with self.subTest(body=body):
                Membership.objects.filter(pk=self.editor_m.pk).update(role=EDITOR)
                response = self.patch(self.admin, self.editor_m, body)
                self.assertEqual(response.status_code, 200, response.content)
                body_json = response.json()
                self.assertEqual(body_json['role'], MEMBER)
                self.assertEqual(body_json['scope'], ORG_SCOPE_JSON)
                self.assertEqual(set(body_json), {
                    'membership_id', 'display_name', 'role', 'joined_at', 'is_self', 'is_last_effective_owner', 'scope',
                })

    def test_patch_member_back_to_editor(self):
        response = self.patch(self.owner, self.member_m, {'role': EDITOR})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Membership.objects.get(pk=self.member_m.pk).role, EDITOR)

    def test_patch_with_reserved_or_invalid_scope_is_a_field_error(self):
        for scope in (
            {'type': 'CITY', 'id': str(KINSHASA.id)}, {'type': 'UNIT', 'id': str(uuid.uuid4())},
            {'type': 'ORGANIZATION', 'id': str(uuid.uuid4())}, 'ORGANIZATION', {'type': 'X'},
        ):
            with self.subTest(scope=scope):
                response = self.patch(self.owner, self.editor_m, {'role': ANALYST, 'scope': scope})
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json(), {'scope': [SCOPE_MESSAGE]})
        self.assertEqual(Membership.objects.get(pk=self.editor_m.pk).role, EDITOR)
        self.assertFalse(AuditLog.objects.filter(action='MEMBERSHIP_ROLE_CHANGED').exists())

    def test_patch_unknown_role_is_still_a_role_field_error(self):
        response = self.patch(self.owner, self.editor_m, {'role': 'SIMPLE_MEMBRE'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('role', response.json())

    def test_member_and_editor_cannot_change_roles(self):
        for actor in (self.member, self.editor):
            with self.subTest(actor=actor.full_name):
                response = self.patch(actor, self.admin_m, {'role': MEMBER})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()['code'], DENY_PERMISSION)

    def test_member_cannot_remove_anyone_but_can_leave(self):
        response = login(self.member).delete(self.url_member(self.editor_m))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], DENY_PERMISSION)
        response = login(self.member).post(f'{ORGS}{self.org.pk}/leave/')
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(Membership.objects.get(pk=self.member_m.pk).status, Membership.STATUS_REVOKED)

    def test_internal_view_and_contexts_expose_member_capabilities(self):
        response = login(self.member).get(f'{ORGS}{self.org.pk}/internal/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['my_role'], MEMBER)
        self.assertEqual(response.json()['capabilities'], MEMBER_CAPABILITIES)
        response = login(self.member).get(CONTEXTS)
        self.assertEqual(response.status_code, 200)
        org_items = [item for item in response.json()['results'] if item['type'] == CONTEXT_ORGANIZATION]
        self.assertEqual(len(org_items), 1)
        self.assertEqual(org_items[0]['role'], MEMBER)
        self.assertEqual(org_items[0]['capabilities'], MEMBER_CAPABILITIES)

    def test_member_has_no_stats_nor_internal_offers(self):
        for capability in ('stats.view', 'offer.view_internal'):
            with self.subTest(capability=capability):
                self.assertFalse(services.can(self.member.pk, CONTEXT_ORGANIZATION, self.org.pk, capability))
                self.assertTrue(services.can(self.editor.pk, CONTEXT_ORGANIZATION, self.org.pk, capability))
        self.assertTrue(services.can(self.member.pk, CONTEXT_ORGANIZATION, self.org.pk, 'org.view_internal'))

    def test_member_is_an_organization_recipient_only_for_its_capabilities(self):
        everyone = services.get_organization_recipients(self.org.pk, capabilities.CAP_ORG_LEAVE)
        self.assertIn(self.member.pk, everyone)
        self.assertNotIn(self.member.pk, services.get_organization_recipients(self.org.pk, 'stats.view'))


# --- Migration inverse : garde de données -----------------------------------------------------------------------

IDENTITY_0017 = ('identity', '0017_role_labels')
IDENTITY_0018 = ('identity', '0018_membership_scope_member_role')


def _migrate(targets):
    MigrationExecutor(connection).migrate(targets)


def _applied():
    return MigrationExecutor(connection).loader.applied_migrations


class MigrationRollbackGuardTests(TransactionTestCase):
    def tearDown(self):
        call_command('migrate', verbosity=0)

    def test_rollback_is_refused_while_member_or_reserved_scope_exists_then_allowed(self):
        org = Organization.objects.create(name='Atelier Migration', org_type='ENTREPRISE')
        member = Membership.objects.create(organization=org, user=make_user('migration'), role=MEMBER)
        with self.assertRaises(RuntimeError) as ctx:
            _migrate([IDENTITY_0017])
        self.assertIn('1 appartenance(s)', str(ctx.exception))
        self.assertNotIn('Atelier', str(ctx.exception))  # comptages seulement
        self.assertIn(IDENTITY_0018, _applied())

        Membership.objects.filter(pk=member.pk).update(role=ANALYST, scope_type=SCOPE_CITY, scope_id=KINSHASA.id)
        with self.assertRaises(RuntimeError):
            _migrate([IDENTITY_0017])
        self.assertIn(IDENTITY_0018, _applied())

        Membership.objects.filter(pk=member.pk).update(scope_type=SCOPE_ORGANIZATION, scope_id=None)
        _migrate([IDENTITY_0017])
        self.assertNotIn(IDENTITY_0018, _applied())
        with connection.cursor() as cursor:
            columns = {c.name for c in connection.introspection.get_table_description(cursor, 'identity_membership')}
        self.assertNotIn('scope_type', columns)
        _migrate([IDENTITY_0018])
        self.assertIn(IDENTITY_0018, _applied())
