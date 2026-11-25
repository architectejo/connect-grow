"""Schéma `identity` du compte unique (L0-09a / T1) : capacités, organisations, équipes, invariants,
audit, événements, non-fuite et données de référence. ADR 0006, sections 4, 5, 7, 8 et 12."""
import inspect
import json
import uuid
from unittest import mock

from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Category, City, Commune
from apps.common.contexts import (
    ALL_CONTEXT_CHOICES, CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER, DENY_CODES, ActingContext,
    ContextDenied, audit_context_args,
)
from apps.moderation.models import AuditLog, Sanction
from apps.platform_core.models import OutboxEvent

from . import capabilities, services
from .models import (
    ContactConsent, IdentitySettings, Membership, Organization, OrganizationDocumentRequirement, ProviderProfile, User,
)

OWNER, ADMIN, EDITOR, ANALYST = capabilities.ROLE_OWNER, capabilities.ROLE_ADMIN, capabilities.ROLE_EDITOR, capabilities.ROLE_ANALYST
MEMBER = 'MEMBER'

# Matrice de l'ADR 0006 section 5, amendée par l'ADR 0010 §4.1 (rôle MEMBER), recopiée telle quelle (indépendante du
# code testé). MEMBER : `org.view_internal` et `org.leave` seulement.
EXPECTED_MATRIX = {
    'org.view_internal': {OWNER, ADMIN, EDITOR, ANALYST, MEMBER},
    'org.leave': {OWNER, ADMIN, EDITOR, ANALYST, MEMBER},
    'org.edit_profile': {OWNER, ADMIN},
    'org.manage_members': {OWNER, ADMIN},
    'org.manage_roles': {OWNER, ADMIN},
    'org.archive': {OWNER},
    'org.verification_submit': {OWNER, ADMIN},
    'offer.view_internal': {OWNER, ADMIN, EDITOR, ANALYST},
    'offer.publish': {OWNER, ADMIN, EDITOR},
    'offer.edit': {OWNER, ADMIN, EDITOR},
    'offer.delete': {OWNER, ADMIN, EDITOR},
    'review.reply': {OWNER, ADMIN, EDITOR},
    'contact.view_requesters': {OWNER, ADMIN, EDITOR},
    'contact.manage_channels': {OWNER, ADMIN},
    'message.reply': {OWNER, ADMIN},
    'stats.view': {OWNER, ADMIN, EDITOR, ANALYST},
}

SENTINEL_NAME = 'Sentinelle-Orga-ZZ'
SENTINEL_EMAIL = 'sentinelle.secret@example.com'
SENTINEL_PHONE = '+243999000111'


def make_user(label, **extra):
    extra.setdefault('phone_verified', True)
    return User.objects.create_user(email=f'{label}@example.com', password='x', full_name=f'Nom {label}', **extra)


def code_of(test, exc_context):
    return exc_context.exception.get_codes()


class CapabilityMatrixTests(SimpleTestCase):
    def test_matrix_is_exactly_the_adr_table(self):
        self.assertEqual({k: set(v) for k, v in capabilities.CAPABILITIES.items()}, EXPECTED_MATRIX)

    def test_every_role_and_capability_pair(self):
        self.assertEqual(capabilities.ROLES, (OWNER, ADMIN, EDITOR, ANALYST, MEMBER))  # 5 rôles x 16 capacités
        for capability, allowed in EXPECTED_MATRIX.items():
            for role in capabilities.ROLES:
                with self.subTest(capability=capability, role=role):
                    self.assertEqual(capabilities.role_has_capability(role, capability), role in allowed)
                    self.assertEqual(
                        capabilities.context_has_capability(CONTEXT_ORGANIZATION, role, capability), role in allowed,
                    )

    def test_capabilities_for_role_lists_match_the_matrix(self):
        for role in capabilities.ROLES:
            expected = sorted(c for c, allowed in EXPECTED_MATRIX.items() if role in allowed)
            self.assertEqual(capabilities.capabilities_for_role(role), expected)

    def test_personal_and_provider_contexts_have_content_capabilities_and_no_org_capability(self):
        for context_type in (CONTEXT_USER, CONTEXT_PROVIDER):
            granted = capabilities.capabilities_for_context(context_type)
            self.assertFalse([c for c in granted if c.startswith('org.')])
            self.assertEqual(set(granted), {c for c in EXPECTED_MATRIX if not c.startswith('org.')})
            self.assertTrue(capabilities.context_has_capability(context_type, None, 'offer.publish'))
            self.assertFalse(capabilities.context_has_capability(context_type, None, 'org.archive'))

    def test_an_unknown_capability_is_a_programming_error_not_a_refusal(self):
        with self.assertRaises(capabilities.UnknownCapability):
            capabilities.role_has_capability(OWNER, 'org.inexistante')
        with self.assertRaises(capabilities.UnknownCapability):
            capabilities.context_has_capability(CONTEXT_USER, None, 'org.inexistante')

    def test_role_authority_rules(self):
        self.assertTrue(capabilities.can_manage_role_of(OWNER, OWNER))
        self.assertTrue(capabilities.can_manage_role_of(ADMIN, ADMIN))
        self.assertFalse(capabilities.can_manage_role_of(ADMIN, OWNER))
        self.assertFalse(capabilities.can_manage_role_of(EDITOR, ANALYST))
        self.assertFalse(capabilities.can_manage_role_of(ANALYST, ANALYST))

    def test_no_commercial_parameter_in_decision_or_team_functions(self):
        """Règle 2 : ni plan, ni prix, ni entitlement dans une fonction de rôle ou de permission."""
        forbidden = {'plan', 'price', 'entitlement', 'subscription', 'tier'}
        functions = [
            capabilities.role_has_capability, capabilities.context_has_capability, capabilities.capabilities_for_role,
            capabilities.capabilities_for_context, capabilities.can_manage_role_of,
            services.create_organization, services.add_member, services.change_member_role, services.revoke_member,
            services.leave_organization, services.transfer_ownership, services.archive_organization,
            services.suspend_organization, services.reactivate_organization, services.get_active_role,
        ]
        for func in functions:
            with self.subTest(func=func.__name__):
                self.assertFalse(forbidden & set(inspect.signature(func).parameters))


class ContextConstantsTests(SimpleTestCase):
    def test_three_contexts_and_deny_codes(self):
        self.assertEqual([c for c, _ in ALL_CONTEXT_CHOICES], ['USER', 'PROVIDER', 'ORGANIZATION'])
        self.assertEqual(
            set(DENY_CODES),
            {'DENY_CONTEXT', 'DENY_RELATION', 'DENY_PERMISSION', 'DENY_SECURITY', 'DENY_OBJECT_STATE'},
        )

    def test_context_denied_is_a_403_with_a_code_and_rejects_unknown_codes(self):
        exc = ContextDenied('DENY_RELATION')
        self.assertEqual(exc.status_code, 403)
        self.assertEqual(exc.get_codes(), 'DENY_RELATION')
        with self.assertRaises(ValueError):
            ContextDenied('last_owner')

    def test_audit_context_args(self):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        self.assertEqual(audit_context_args(ActingContext(user_id, CONTEXT_ORGANIZATION, org_id, OWNER)),
                         (CONTEXT_ORGANIZATION, org_id))
        self.assertEqual(audit_context_args(None), (None, None))


class TeamTestBase(TestCase):
    def setUp(self):
        self.owner = make_user('owner')
        self.admin = make_user('admin')
        self.editor = make_user('editor')
        self.analyst = make_user('analyst')
        self.outsider = make_user('outsider')
        self.org = services.create_organization(self.owner, 'Atelier Test', 'ENTREPRISE')
        services.add_member(self.owner, self.org.pk, self.admin.pk, ADMIN)
        services.add_member(self.owner, self.org.pk, self.editor.pk, EDITOR)
        services.add_member(self.owner, self.org.pk, self.analyst.pk, ANALYST)

    def staff_user(self):
        staff = make_user('staffer', is_staff=True)
        staff.user_permissions.add(
            *Permission.objects.filter(codename__in=['suspend_organization', 'view_organization']),
        )
        return User.objects.get(pk=staff.pk)  # recharge le cache de permissions

    def role_of(self, user):
        return services.get_active_role(user.pk, self.org.pk)

    def assertDenied(self, code, func, *args, **kwargs):
        with self.assertRaises(ContextDenied) as caught:
            func(*args, **kwargs)
        self.assertEqual(caught.exception.get_codes(), code)

    def assertBusiness(self, code, func, *args, **kwargs):
        with self.assertRaises(services.OrganizationError) as caught:
            func(*args, **kwargs)
        self.assertEqual(caught.exception.get_codes(), code)


class CreateOrganizationTests(TestCase):
    def setUp(self):
        self.user = make_user('creator')

    def test_creation_makes_organization_and_owner_membership_with_audit_and_event(self):
        city = City.objects.create(name='Kinshasa')
        commune = Commune.objects.create(name='Gombe', city=city)
        category = Category.objects.create(name='Mode')
        org = services.create_organization(
            self.user, '  Atelier X  ', 'BOUTIQUE', description='Texte', nif='N1',
            category_ids=[category.pk, category.pk], city_id=city.pk, commune_id=commune.pk,
        )
        self.assertEqual((org.name, org.org_type, org.status), ('Atelier X', 'BOUTIQUE', 'ACTIVE'))
        self.assertEqual(org.created_by, self.user)
        self.assertEqual(list(org.category_links.values_list('category_id', flat=True)), [category.pk])
        membership = Membership.objects.get(organization=org, user=self.user)
        self.assertEqual((membership.role, membership.status), (OWNER, 'ACTIVE'))
        entry = AuditLog.objects.get(action='ORG_CREATED')
        self.assertEqual((entry.actor, entry.target_type, entry.target_id), (self.user, 'organization', org.pk))
        self.assertEqual((entry.context_type, entry.context_id), (CONTEXT_ORGANIZATION, org.pk))
        event = OutboxEvent.objects.get(event_type='identity.membership_changed')
        self.assertEqual(event.payload['change'], 'added')
        self.assertEqual(event.payload['new_role'], OWNER)

    def test_every_org_type_is_accepted(self):
        for org_type in ('ENTREPRISE', 'BOUTIQUE', 'ONG', 'ORGANISATEUR_EVENEMENTS'):
            with self.subTest(org_type=org_type):
                self.assertEqual(services.create_organization(self.user, 'Nom', org_type).org_type, org_type)

    def test_invalid_input_is_refused_and_nothing_is_written(self):
        cases = [
            ({'name': '', 'org_type': 'ONG'}, 'name'),
            ({'name': 'A', 'org_type': 'ONG'}, 'name'),
            ({'name': 'x' * 256, 'org_type': 'ONG'}, 'name'),
            ({'name': None, 'org_type': 'ONG'}, 'name'),
            ({'name': 'Valide', 'org_type': 'RESTAURANT'}, 'org_type'),
            ({'name': 'Valide', 'org_type': 'ONG', 'description': 'd' * 2001}, 'description'),
            ({'name': 'Valide', 'org_type': 'ONG', 'category_ids': [uuid.uuid4()]}, 'category_ids'),
            ({'name': 'Valide', 'org_type': 'ONG', 'city_id': uuid.uuid4()}, 'city_id'),
            ({'name': 'Valide', 'org_type': 'ONG', 'commune_id': uuid.uuid4()}, 'commune_id'),
        ]
        for kwargs, field in cases:
            with self.subTest(field=field, kwargs=kwargs):
                with self.assertRaises(ValidationError) as caught:
                    services.create_organization(self.user, **kwargs)
                self.assertIn(field, caught.exception.detail)
        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(AuditLog.objects.filter(action='ORG_CREATED').count(), 0)

    def test_category_count_is_capped_by_the_setting(self):
        categories = [Category.objects.create(name=f'Cat {i}') for i in range(6)]
        self.assertEqual(IdentitySettings.get_solo().max_categories_per_context, 5)
        with self.assertRaises(ValidationError) as caught:
            services.create_organization(self.user, 'Valide', 'ONG', category_ids=[c.pk for c in categories])
        self.assertIn('category_ids', caught.exception.detail)
        self.assertEqual(Organization.objects.count(), 0)
        org = services.create_organization(self.user, 'Valide', 'ONG', category_ids=[c.pk for c in categories[:5]])
        self.assertEqual(org.category_links.count(), 5)
        self.assertEqual(services.create_organization(self.user, 'Vide', 'ONG').category_links.count(), 0)

    def test_commune_must_belong_to_the_city(self):
        city, other = City.objects.create(name='Kinshasa'), City.objects.create(name='Lubumbashi')
        commune = Commune.objects.create(name='Gombe', city=other)
        with self.assertRaises(ValidationError) as caught:
            services.create_organization(self.user, 'Valide', 'ONG', city_id=city.pk, commune_id=commune.pk)
        self.assertIn('commune_id', caught.exception.detail)

    def test_unverified_login_phone_is_refused(self):
        user = make_user('unverified', phone_verified=False)
        with self.assertRaises(services.OrganizationError) as caught:
            services.create_organization(user, 'Valide', 'ONG')
        self.assertEqual(caught.exception.get_codes(), 'phone_verification_required')
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(Organization.objects.count(), 0)

    def test_restricted_or_inactive_account_is_refused(self):
        Sanction.objects.create(user=self.user, sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        with self.assertRaises(ContextDenied) as caught:
            services.create_organization(self.user, 'Valide', 'ONG')
        self.assertEqual(caught.exception.get_codes(), 'DENY_SECURITY')
        inactive = make_user('inactive', is_active=False)
        with self.assertRaises(ContextDenied):
            services.create_organization(inactive, 'Valide', 'ONG')
        self.assertEqual(Organization.objects.count(), 0)

    def test_limit_comes_from_the_setting_and_counts_active_memberships(self):
        self.assertEqual(IdentitySettings.get_solo().max_organizations_per_account, 10)
        settings_row = IdentitySettings.get_solo()
        settings_row.max_organizations_per_account = 2
        settings_row.save()
        first = services.create_organization(self.user, 'Une', 'ONG')
        services.create_organization(self.user, 'Deux', 'ONG')
        with self.assertRaises(services.OrganizationError) as caught:
            services.create_organization(self.user, 'Trois', 'ONG')
        self.assertEqual(caught.exception.get_codes(), 'organization_limit_reached')
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(Organization.objects.count(), 2)
        # Une organisation quittée libère une place (seules les appartenances ACTIVE comptent).
        other = make_user('coowner')
        services.add_member(self.user, first.pk, other.pk, OWNER)
        services.leave_organization(self.user, first.pk)
        self.assertEqual(services.create_organization(self.user, 'Trois', 'ONG').name, 'Trois')

    def test_a_failure_while_creating_the_membership_leaves_no_organization(self):
        with mock.patch('apps.identity.organizations.Membership.objects.create', side_effect=IntegrityError('boom')):
            with self.assertRaises(IntegrityError):
                services.create_organization(self.user, 'Valide', 'ONG')
        self.assertEqual(Organization.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.filter(event_type='identity.membership_changed').count(), 0)
        self.assertEqual(AuditLog.objects.filter(action='ORG_CREATED').count(), 0)

    def test_names_are_not_unique(self):
        services.create_organization(self.user, 'Homonyme', 'ONG')
        self.assertEqual(services.create_organization(make_user('other'), 'Homonyme', 'ONG').name, 'Homonyme')


class MembershipRulesTests(TeamTestBase):
    def test_non_member_gets_deny_relation_even_if_staff_or_superuser(self):
        staff = make_user('staff', is_staff=True, is_superuser=True)
        for actor in (self.outsider, staff):
            with self.subTest(actor=actor.email):
                self.assertDenied('DENY_RELATION', services.add_member, actor, self.org.pk, make_user(f'n{actor.pk.hex[:6]}').pk, EDITOR)
                self.assertDenied('DENY_RELATION', services.archive_organization, actor, self.org.pk)

    def test_unknown_or_malformed_organization_gives_the_same_refusal_as_non_member(self):
        self.assertDenied('DENY_RELATION', services.leave_organization, self.owner, uuid.uuid4())
        self.assertDenied('DENY_RELATION', services.leave_organization, self.owner, 'pas-un-uuid')

    def test_only_roles_with_manage_members_can_add(self):
        newcomer = make_user('newcomer')
        for actor in (self.editor, self.analyst):
            self.assertDenied('DENY_PERMISSION', services.add_member, actor, self.org.pk, newcomer.pk, ANALYST)
        self.assertIsNone(self.role_of(newcomer))
        membership = services.add_member(self.admin, self.org.pk, newcomer.pk, EDITOR)
        self.assertEqual((membership.role, membership.added_by), (EDITOR, self.admin))

    def test_admin_never_grants_or_touches_owner(self):
        newcomer = make_user('newcomer')
        self.assertDenied('DENY_PERMISSION', services.add_member, self.admin, self.org.pk, newcomer.pk, OWNER)
        self.assertDenied('DENY_PERMISSION', services.change_member_role, self.admin, self.org.pk, self.editor.pk, OWNER)
        self.assertDenied('DENY_PERMISSION', services.change_member_role, self.admin, self.org.pk, self.owner.pk, EDITOR)
        self.assertDenied('DENY_PERMISSION', services.revoke_member, self.admin, self.org.pk, self.owner.pk)
        self.assertDenied('DENY_PERMISSION', services.change_member_role, self.admin, self.org.pk, self.admin.pk, OWNER)
        self.assertEqual(self.role_of(self.owner), OWNER)
        self.assertEqual(self.role_of(self.editor), EDITOR)

    def test_admin_manages_lower_roles_and_peers(self):
        services.change_member_role(self.admin, self.org.pk, self.editor.pk, ANALYST)
        self.assertEqual(self.role_of(self.editor), ANALYST)
        services.revoke_member(self.admin, self.org.pk, self.analyst.pk)
        self.assertIsNone(self.role_of(self.analyst))

    def test_editor_and_analyst_cannot_manage_roles_or_revoke(self):
        for actor in (self.editor, self.analyst):
            self.assertDenied('DENY_PERMISSION', services.change_member_role, actor, self.org.pk, self.analyst.pk, EDITOR)
            self.assertDenied('DENY_PERMISSION', services.revoke_member, actor, self.org.pk, self.admin.pk)
            self.assertDenied('DENY_PERMISSION', services.archive_organization, actor, self.org.pk)

    def test_only_owner_can_archive(self):
        self.assertDenied('DENY_PERMISSION', services.archive_organization, self.admin, self.org.pk)

    def test_unknown_role_is_a_validation_error(self):
        with self.assertRaises(ValidationError):
            services.change_member_role(self.owner, self.org.pk, self.editor.pk, 'CHEF')
        with self.assertRaises(ValidationError):
            services.add_member(self.owner, self.org.pk, self.outsider.pk, 'CHEF')

    def test_adding_an_active_member_twice_or_an_unknown_or_restricted_account_is_refused(self):
        self.assertBusiness('already_member', services.add_member, self.owner, self.org.pk, self.editor.pk, EDITOR)
        restricted = make_user('restricted')
        Sanction.objects.create(user=restricted, sanction_type='BANNISSEMENT', reason='x')
        inactive = make_user('inactive2', is_active=False)
        responses = set()
        for target in (uuid.uuid4(), restricted.pk, inactive.pk):
            with self.assertRaises(services.OrganizationError) as caught:
                services.add_member(self.owner, self.org.pk, target, EDITOR)
            responses.add((caught.exception.get_codes(), caught.exception.status_code, str(caught.exception.detail)))
        # Une seule réponse neutre : l'existence et l'état du compte ne sont pas révélés.
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses.pop()[0], 'user_unavailable')

    def test_added_member_is_subject_to_the_organization_limit(self):
        services.create_organization(self.outsider, 'Sienne', 'ONG')
        row = IdentitySettings.get_solo()
        row.max_organizations_per_account = 1
        row.save()
        self.assertBusiness('user_unavailable', services.add_member, self.owner, self.org.pk, self.outsider.pk, EDITOR)
        # Le propriétaire déjà au plafond (1) ne peut plus rien créer.
        self.assertBusiness('organization_limit_reached', services.create_organization, self.owner, 'Autre', 'ONG')

    def test_returning_member_reactivates_the_same_row(self):
        row_id = Membership.objects.get(organization=self.org, user=self.editor).pk
        services.revoke_member(self.owner, self.org.pk, self.editor.pk)
        self.assertIsNone(self.role_of(self.editor))
        again = services.add_member(self.owner, self.org.pk, self.editor.pk, ANALYST)
        self.assertEqual(again.pk, row_id)
        self.assertEqual(Membership.objects.filter(organization=self.org, user=self.editor).count(), 1)
        self.assertEqual((again.role, again.status, again.end_reason, again.ended_at), (ANALYST, 'ACTIVE', '', None))
        event = OutboxEvent.objects.filter(event_type='identity.membership_changed').order_by('-created_at').first()
        self.assertEqual(event.payload['change'], 'reactivated')

    def test_membership_is_unique_per_organization_and_user(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(organization=self.org, user=self.editor, role=ANALYST)

    def test_suspended_and_archived_organizations_refuse_team_actions(self):
        staff = self.staff_user()
        services.suspend_organization(staff, self.org.pk, 'moderation')
        self.assertDenied('DENY_SECURITY', services.add_member, self.owner, self.org.pk, self.outsider.pk, EDITOR)
        self.assertDenied('DENY_SECURITY', services.change_member_role, self.owner, self.org.pk, self.editor.pk, ANALYST)
        self.assertDenied('DENY_SECURITY', services.archive_organization, self.owner, self.org.pk)
        services.reactivate_organization(staff, self.org.pk)
        services.archive_organization(self.owner, self.org.pk)
        self.assertDenied('DENY_OBJECT_STATE', services.add_member, self.owner, self.org.pk, self.outsider.pk, EDITOR)
        # Quitter n'est jamais bloqué (amendement 1, Q-F4).
        services.leave_organization(self.editor, self.org.pk)
        self.assertIsNone(self.role_of(self.editor))


class LastOwnerTests(TeamTestBase):
    def assertOwnerState(self, expected_owners):
        self.assertEqual(services.count_active_owners(self.org.pk), expected_owners)

    def test_sole_owner_cannot_leave_be_demoted_or_revoked(self):
        self.assertBusiness('last_owner', services.leave_organization, self.owner, self.org.pk)
        self.assertBusiness('last_owner', services.change_member_role, self.owner, self.org.pk, self.owner.pk, ADMIN)
        self.assertOwnerState(1)
        self.assertEqual(self.role_of(self.owner), OWNER)
        membership = Membership.objects.get(organization=self.org, user=self.owner)
        self.assertEqual((membership.status, membership.end_reason, membership.ended_at), ('ACTIVE', '', None))

    def test_refusal_writes_no_audit_and_no_event(self):
        audits, events = AuditLog.objects.count(), OutboxEvent.objects.count()
        self.assertBusiness('last_owner', services.leave_organization, self.owner, self.org.pk)
        self.assertEqual((AuditLog.objects.count(), OutboxEvent.objects.count()), (audits, events))

    def test_two_owners_one_leaves_the_other_becomes_last(self):
        services.change_member_role(self.owner, self.org.pk, self.admin.pk, OWNER)
        self.assertOwnerState(2)
        services.leave_organization(self.owner, self.org.pk)
        self.assertOwnerState(1)
        self.assertBusiness('last_owner', services.leave_organization, self.admin, self.org.pk)
        self.assertBusiness('last_owner', services.change_member_role, self.admin, self.org.pk, self.admin.pk, EDITOR)

    def test_an_owner_can_revoke_another_owner_but_never_the_last_one(self):
        services.change_member_role(self.owner, self.org.pk, self.admin.pk, OWNER)
        services.revoke_member(self.owner, self.org.pk, self.admin.pk)
        self.assertOwnerState(1)
        self.assertEqual(self.role_of(self.owner), OWNER)

    def test_revoking_oneself_goes_through_leave(self):
        self.assertBusiness('use_leave', services.revoke_member, self.owner, self.org.pk, self.owner.pk)

    def test_a_non_owner_leaves_freely_and_loses_access_at_once(self):
        services.leave_organization(self.editor, self.org.pk)
        membership = Membership.objects.get(organization=self.org, user=self.editor)
        self.assertEqual((membership.status, membership.end_reason, membership.ended_by), ('REVOKED', 'left', self.editor))
        self.assertIsNone(self.role_of(self.editor))
        # Plus aucune capacité : relation absente.
        self.assertDenied('DENY_RELATION', services.leave_organization, self.editor, self.org.pk)
        self.assertDenied('DENY_RELATION', services.add_member, self.editor, self.org.pk, self.outsider.pk, EDITOR)
        # Le compte personnel est intact.
        self.editor.refresh_from_db()
        self.assertTrue(self.editor.is_active)

    def test_leaving_is_allowed_from_a_suspended_organization(self):
        staff = self.staff_user()
        services.suspend_organization(staff, self.org.pk, 'moderation')
        services.leave_organization(self.editor, self.org.pk)
        self.assertIsNone(self.role_of(self.editor))

    def test_transfer_ownership_is_two_role_changes_in_one_transaction(self):
        target = services.transfer_ownership(self.owner, self.org.pk, self.admin.pk)
        self.assertEqual(target.role, OWNER)
        self.assertEqual(self.role_of(self.admin), OWNER)
        self.assertEqual(self.role_of(self.owner), ADMIN)
        self.assertOwnerState(1)
        entry = AuditLog.objects.get(action='ORG_OWNERSHIP_TRANSFERRED')
        self.assertEqual(entry.details, f'from_user={self.owner.pk}; to_user={self.admin.pk}')
        self.assertEqual(entry.context_id, self.org.pk)
        self.assertEqual(AuditLog.objects.filter(action='MEMBERSHIP_ROLE_CHANGED').count(), 2)

    def test_transfer_rules(self):
        self.assertDenied('DENY_PERMISSION', services.transfer_ownership, self.admin, self.org.pk, self.editor.pk)
        self.assertBusiness('member_not_found', services.transfer_ownership, self.owner, self.org.pk, self.outsider.pk)
        self.assertBusiness('invalid_transfer', services.transfer_ownership, self.owner, self.org.pk, self.owner.pk)
        with self.assertRaises(ValidationError):
            services.transfer_ownership(self.owner, self.org.pk, self.admin.pk, actor_new_role=OWNER)
        self.assertEqual(self.role_of(self.owner), OWNER)
        self.assertEqual(self.role_of(self.admin), ADMIN)

    def test_a_failed_last_owner_check_rolls_the_whole_change_back(self):
        """Mise à jour puis contrôle : si le contrôle échoue, l'écriture est annulée avec la transaction."""
        with self.assertRaises(services.OrganizationError):
            services.leave_organization(self.owner, self.org.pk)
        self.assertEqual(Membership.objects.get(organization=self.org, user=self.owner).status, 'ACTIVE')


class AuditAndEventTests(TeamTestBase):
    def test_each_team_action_writes_an_audit_entry_with_context_and_a_matching_event(self):
        newcomer = make_user('newcomer')
        services.add_member(self.admin, self.org.pk, newcomer.pk, EDITOR)
        services.change_member_role(self.admin, self.org.pk, newcomer.pk, ANALYST)
        services.revoke_member(self.admin, self.org.pk, newcomer.pk)
        services.leave_organization(self.editor, self.org.pk)
        services.archive_organization(self.owner, self.org.pk)
        actions = list(AuditLog.objects.filter(context_id=self.org.pk).order_by('created_at').values_list('action', flat=True))
        for expected in ('ORG_CREATED', 'MEMBERSHIP_ADDED', 'MEMBERSHIP_ROLE_CHANGED', 'MEMBERSHIP_REVOKED', 'ORG_ARCHIVED'):
            self.assertIn(expected, actions)
        entry = AuditLog.objects.filter(action='MEMBERSHIP_ROLE_CHANGED').latest('created_at')
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target_type, 'membership')
        self.assertEqual(entry.context_type, CONTEXT_ORGANIZATION)
        self.assertEqual(
            entry.details,
            f'organization={self.org.pk}; user={newcomer.pk}; old_role=EDITOR; new_role=ANALYST',
        )
        changes = [e.payload['change'] for e in OutboxEvent.objects.filter(event_type='identity.membership_changed').order_by('created_at')]
        self.assertEqual(changes[-4:], ['added', 'role_changed', 'revoked', 'revoked'])

    def test_membership_event_payload_has_exactly_the_documented_keys(self):
        services.change_member_role(self.owner, self.org.pk, self.editor.pk, ANALYST)
        event = OutboxEvent.objects.filter(event_type='identity.membership_changed').latest('created_at')
        self.assertEqual(event.version, 1)
        self.assertEqual(event.aggregate_type, 'organization')
        self.assertEqual(event.aggregate_id, self.org.pk)
        self.assertEqual(
            event.payload,
            {
                'organization_id': str(self.org.pk), 'user_id': str(self.editor.pk), 'change': 'role_changed',
                'old_role': EDITOR, 'new_role': ANALYST, 'actor_id': str(self.owner.pk),
            },
        )

    def test_status_events_for_suspend_reactivate_archive(self):
        staff = self.staff_user()
        services.suspend_organization(staff, self.org.pk, 'verification')
        services.reactivate_organization(staff, self.org.pk)
        services.archive_organization(self.owner, self.org.pk)
        events = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').order_by('created_at')
        self.assertEqual([e.payload['reason'] for e in events], ['suspended', 'reactivated', 'archived'])
        self.assertEqual(
            set(events[0].payload), {'context_type', 'context_id', 'reason', 'actor_id'},
        )
        self.assertEqual(events[0].payload['context_type'], CONTEXT_ORGANIZATION)
        suspended = AuditLog.objects.get(action='ORG_SUSPENDED')
        self.assertEqual(suspended.details, 'reason=verification')
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'ARCHIVED')
        self.assertEqual(self.org.suspension_reason, '')

    def test_suspension_needs_the_dedicated_permission_and_a_known_reason(self):
        self.assertDenied('DENY_PERMISSION', services.suspend_organization, self.owner, self.org.pk, 'moderation')
        plain_staff = make_user('plainstaff', is_staff=True)
        self.assertDenied('DENY_PERMISSION', services.suspend_organization, plain_staff, self.org.pk, 'moderation')
        self.assertDenied('DENY_PERMISSION', services.reactivate_organization, self.owner, self.org.pk)
        staff = self.staff_user()
        with self.assertRaises(ValidationError):
            services.suspend_organization(staff, self.org.pk, 'parce que')
        self.assertBusiness('invalid_status', services.reactivate_organization, staff, self.org.pk)
        services.suspend_organization(staff, self.org.pk, 'legal')
        self.assertBusiness('invalid_status', services.suspend_organization, staff, self.org.pk, 'legal')

    def test_staff_never_reactivates_an_archived_organization(self):
        staff = self.staff_user()
        services.archive_organization(self.owner, self.org.pk)
        self.assertBusiness('invalid_status', services.reactivate_organization, staff, self.org.pk)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'ARCHIVED')
        # Même refus par l'action d'administration (compte en échec, statut inchangé).
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        from .models import Organization
        request = RequestFactory().post('/')
        request.user, request._messages = staff, mock.Mock()
        site._registry[Organization].reactivate_selected(request, Organization.objects.filter(pk=self.org.pk))
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'ARCHIVED')
        self.assertFalse(AuditLog.objects.filter(action='ORG_REACTIVATED').exists())

    def test_staff_who_is_or_was_a_member_or_the_creator_cannot_reactivate(self):
        other = make_user('autre-staff', is_staff=True)
        other.user_permissions.add(Permission.objects.get(codename='suspend_organization'))
        other = User.objects.get(pk=other.pk)
        for who in ('member', 'former', 'creator'):
            staff = make_user(f'conflit-{who}', is_staff=True)
            staff.user_permissions.add(Permission.objects.get(codename='suspend_organization'))
            staff = User.objects.get(pk=staff.pk)
            if who == 'creator':
                self.org.created_by = staff
                self.org.save(update_fields=['created_by'])
            else:
                Membership.objects.create(
                    organization=self.org, user=staff, role=ANALYST,
                    status=Membership.STATUS_ACTIVE if who == 'member' else Membership.STATUS_REVOKED,
                )
            services.suspend_organization(other, self.org.pk, 'moderation')
            with self.assertRaises(services.OrganizationError) as caught:
                services.reactivate_organization(staff, self.org.pk)
            self.assertEqual((caught.exception.get_codes(), caught.exception.status_code), ('interest_conflict', 403))
            self.org.refresh_from_db()
            self.assertEqual(self.org.status, 'SUSPENDED', who)
            denied = AuditLog.objects.filter(action='ORG_REACTIVATION_DENIED', actor=staff).get()
            self.assertIn('old_status=SUSPENDED', denied.details)
            self.assertEqual((denied.context_type, denied.context_id), ('ORGANIZATION', self.org.pk))
            services.reactivate_organization(other, self.org.pk)  # un autre membre du personnel le peut
            self.org.created_by = None
            self.org.save(update_fields=['created_by'])
        self.assertEqual(AuditLog.objects.filter(action='ORG_REACTIVATED', actor=other).count(), 3)

    def test_no_personal_data_in_audit_details_or_event_payloads(self):
        """Valeurs sentinelles : ni nom d'organisation, ni e-mail, ni téléphone ne sortent dans le journal ni l'outbox."""
        owner = make_user('sentinel-owner', phone='+243999000222')
        member = User.objects.create_user(
            email=SENTINEL_EMAIL, phone=SENTINEL_PHONE, password='x', full_name='Nom Secret Sentinelle', phone_verified=True,
        )
        org = services.create_organization(owner, SENTINEL_NAME, 'ONG', description='Description sentinelle', nif='NIF-SENTINELLE')
        services.add_member(owner, org.pk, member.pk, EDITOR)
        services.change_member_role(owner, org.pk, member.pk, ANALYST)
        services.revoke_member(owner, org.pk, member.pk)
        staff = self.staff_user()
        services.suspend_organization(staff, org.pk, 'other')
        services.reactivate_organization(staff, org.pk)
        services.archive_organization(owner, org.pk)
        forbidden = [SENTINEL_NAME, SENTINEL_EMAIL, SENTINEL_PHONE, '+243999000222', 'Nom Secret', 'NIF-SENTINELLE',
                     'Description sentinelle', 'sentinel-owner@example.com']
        blobs = [e.details for e in AuditLog.objects.filter(context_id=org.pk)]
        blobs += [json.dumps(e.payload) for e in OutboxEvent.objects.filter(aggregate_id=org.pk)]
        self.assertTrue(blobs)
        for blob in blobs:
            for secret in forbidden:
                self.assertNotIn(secret, blob)


class SchemaTests(TestCase):
    def test_default_settings_are_closed_and_configurable(self):
        row = IdentitySettings.get_solo()
        self.assertEqual(row.max_organizations_per_account, 10)
        self.assertFalse(row.org_phone_channels_enabled)
        self.assertEqual(row.max_categories_per_context, 5)
        self.assertEqual(IdentitySettings.get_solo().pk, row.pk)
        row.max_organizations_per_account = 0
        with self.assertRaises(Exception):
            row.full_clean()
        row.max_organizations_per_account = 101
        with self.assertRaises(Exception):
            row.full_clean()

    def test_document_requirements_seed(self):
        def types(org_type):
            return list(OrganizationDocumentRequirement.objects.filter(org_type=org_type).values_list('document_type', flat=True))

        self.assertEqual(types('ENTREPRISE'), ['RCCM', 'ID_NATIONALE', 'PIECE_GERANT'])
        self.assertEqual(types('ORGANISATEUR_EVENEMENTS'), ['RCCM', 'ID_NATIONALE', 'PIECE_GERANT'])
        self.assertEqual(types('BOUTIQUE'), ['ID_NATIONALE', 'PIECE_GERANT'])
        self.assertEqual(types('ONG'), ['ARRETE_ONG', 'ID_NATIONALE', 'PIECE_GERANT'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationDocumentRequirement.objects.create(org_type='ONG', document_type='ARRETE_ONG')

    def test_one_provider_profile_per_account(self):
        user = make_user('prestataire')
        ProviderProfile.objects.create(user=user, display_name='Marie couture')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderProfile.objects.create(user=user, display_name='Doublon')

    def test_consent_is_unique_per_organization_and_channel_but_nulls_do_not_collide(self):
        owner = make_user('proprio')
        org = services.create_organization(owner, 'Orga consentement', 'ONG')
        ContactConsent.objects.create(organization=org, channel='MESSAGE', granted_by=owner)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContactConsent.objects.create(organization=org, channel='MESSAGE')
        ContactConsent.objects.create(organization=org, channel='CALL')
        # Deux consentements de compte pour des canaux différents n'entrent pas en collision avec l'organisation.
        ContactConsent.objects.create(user=owner, channel='MESSAGE')
        ContactConsent.objects.create(user=make_user('autre'), channel='MESSAGE')

    def test_legacy_company_model_is_gone_but_the_conversion_traces_remain(self):
        # T9-2 (contraction) : plus de type de compte ni de profil entreprise ; seules les traces de la conversion
        # (table de correspondance, colonne `legacy_business_profile_id`) sont conservées jusqu'à la réinitialisation.
        from django.apps import apps
        self.assertNotIn('user_type', {f.name for f in User._meta.get_fields()})
        self.assertRaises(LookupError, apps.get_model, 'identity', 'BusinessProfile')
        self.assertRaises(LookupError, apps.get_model, 'identity', 'BusinessProfileCategory')
        self.assertIn('legacy_business_profile_id', {f.name for f in Organization._meta.get_fields()})
        self.assertTrue(apps.get_model('identity', 'LegacyAccountMapping'))

    def test_audit_log_context_is_optional(self):
        entry = AuditLog.record(None, 'SOMETHING')
        self.assertEqual((entry.context_type, entry.context_id), (None, None))
        org_id = uuid.uuid4()
        entry = AuditLog.record(None, 'SOMETHING', context=(CONTEXT_ORGANIZATION, org_id))
        self.assertEqual((entry.context_type, entry.context_id), (CONTEXT_ORGANIZATION, org_id))
        entry = AuditLog.record(None, 'SOMETHING', context=ActingContext(uuid.uuid4(), CONTEXT_PROVIDER, org_id))
        self.assertEqual((entry.context_type, entry.context_id), (CONTEXT_PROVIDER, org_id))


class AdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(email='root@example.com', password='x', full_name='Root')
        self.client.force_login(self.superuser)
        self.owner = make_user('adminowner')
        self.org = services.create_organization(self.owner, 'Orga admin', 'ONG')

    def test_organization_and_membership_admin_are_read_only_and_hide_member_data(self):
        for model in ('organization', 'membership', 'providerprofile'):
            response = self.client.get(f'/admin/identity/{model}/add/')
            self.assertEqual(response.status_code, 403, model)
        membership = Membership.objects.get(organization=self.org)
        response = self.client.get(f'/admin/identity/membership/{membership.pk}/change/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(self.owner.email, content)
        self.assertEqual(self.client.post(f'/admin/identity/organization/{self.org.pk}/delete/', {'post': 'yes'}).status_code, 403)

    def test_suspend_action_goes_through_the_service(self):
        response = self.client.post('/admin/identity/organization/', {
            'action': 'suspend_selected', '_selected_action': [str(self.org.pk)], 'apply': '1', 'reason': 'moderation',
        })
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'SUSPENDED')
        self.assertTrue(AuditLog.objects.filter(action='ORG_SUSPENDED', context_id=self.org.pk).exists())
