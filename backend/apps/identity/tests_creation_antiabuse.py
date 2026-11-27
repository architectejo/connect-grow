"""Anti-abus de création d'organisation (L1-01-B8 ; ADR 0010 D8, §6.4, §9.3, §12 ; contrat L1-01 §7.5, §7.6 ; Q22).

Couvre : fin du plafond affiché (`limits/` sans seuil), plafond technique caché et refus neutre
`account_review_required` (création, acceptation, confirmation), revue de création au-delà du seuil interne sur la
fenêtre glissante, invisibilité publique d'une organisation en revue (annuaire, page vendeur, offres), levée par le
personnel (permission dédiée, conflit d'intérêts, audit, événements, admin, `setup_roles`), notifications neutres,
throttle `org_create_burst`, introspection : aucun seuil n'apparaît dans `limits/`, `contexts/`, `internal/`.
"""
import importlib
import json
import re
from datetime import timedelta
from unittest import mock

from django.apps import apps as django_apps
from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.catalog.models import Category, City, Commune
from apps.common.contexts import ContextDenied, DENY_PERMISSION
from apps.common.factories import make_test_image, owner_kwargs
from apps.marketplace.models import Offer
from apps.moderation.models import AuditLog
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now

from . import capabilities, services, throttles
from .admin import OrganizationAdmin
from .models import IdentitySettings, Membership, Organization, OrganizationInvitation, User

ORGS = '/api/v1/accounts/organizations/'
CONTEXTS = '/api/v1/accounts/contexts/'
ACCEPT = '/api/v1/accounts/organization-invitations/accept/'
SELLER_PAGE = '/api/v1/marketplace/sellers/organization/{}/'
LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'b8-throttle'}}
OWNER, ANALYST = capabilities.ROLE_OWNER, capabilities.ROLE_ANALYST
NONE, PENDING, CLEARED = (
    Organization.CREATION_REVIEW_NONE, Organization.CREATION_REVIEW_PENDING, Organization.CREATION_REVIEW_CLEARED,
)
NEUTRAL_DETAIL = (
    "Votre compte doit être examiné par l'équipe Connecte+ avant de créer ou de rejoindre d'autres organisations."
)
# Valeurs sentinelles des seuils internes : aucune ne doit apparaître dans une réponse (introspection, Q22).
SENTINEL_HARD_LIMIT, SENTINEL_WINDOW, SENTINEL_THRESHOLD = 987, 331, 97
HIDDEN_KEY_FRAGMENTS = ('hard_limit', 'max_organizations', 'review_threshold', 'review_window', 'creation_review')


def make_user(label, **extra):
    extra.setdefault('phone_verified', True)
    extra.setdefault('full_name', f'Nom {label}')
    return User.objects.create_user(email=f'{label}@example.com', password='x', **extra)


def set_settings(**values):
    IdentitySettings.objects.filter(pk=IdentitySettings.get_solo().pk).update(**values)


def login(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def staff_with(*codenames, label='staff'):
    user = make_user(label, is_staff=True)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return User.objects.get(pk=user.pk)  # cache des permissions vierge


def all_keys_and_ints(value):
    """Clés et entiers d'une réponse JSON, à toute profondeur."""
    keys, ints = set(), set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            keys.update(item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, int) and not isinstance(item, bool):
            ints.add(item)
    return keys, ints


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.creator = make_user('createur')
        self.client = login(self.creator)

    def create(self, name, user=None):
        return services.create_organization(user or self.creator, name, 'ONG')

    def create_many(self, count, user=None, prefix='Orga'):
        return [self.create(f'{prefix} {i}', user) for i in range(count)]

    def create_held(self, name='Retenue', user=None):
        """Seuil réglé à 2 (sa borne basse) : une création ordinaire, puis `name`, retenue en revue."""
        set_settings(org_creation_review_threshold=2)
        self.create(f'Avant {name}', user)
        held = self.create(name, user)
        assert held.creation_review_status == PENDING
        return held


# --- Revue de création : seuil, fenêtre, comptage -------------------------------------------------------------

class CreationReviewThresholdTests(Base):
    def test_defaults_are_the_proposed_values(self):
        row = IdentitySettings.get_solo()
        self.assertEqual(
            (row.max_memberships_hard_limit, row.org_creation_review_window_days, row.org_creation_review_threshold),
            (200, 30, 5),
        )

    def test_the_fifth_creation_in_the_window_and_the_next_ones_are_held(self):
        organizations = self.create_many(6)
        self.assertEqual([o.creation_review_status for o in organizations], [NONE] * 4 + [PENDING] * 2)
        # Créées, actives, et le créateur en est administrateur principal : la revue n'empêche pas l'usage interne.
        for organization in organizations[4:]:
            self.assertEqual(organization.status, Organization.STATUS_ACTIVE)
            self.assertEqual(services.get_active_role(self.creator.pk, organization.pk), OWNER)

    def test_threshold_and_window_are_settings(self):
        set_settings(org_creation_review_threshold=2)
        first, second = self.create_many(2)
        self.assertEqual((first.creation_review_status, second.creation_review_status), (NONE, PENDING))
        # Hors fenêtre : les créations anciennes ne comptent plus.
        Organization.objects.filter(created_by=self.creator).update(created_at=timezone.now() - timedelta(days=31))
        self.assertEqual(self.create('Plus tard').creation_review_status, NONE)
        set_settings(org_creation_review_window_days=60)
        self.assertEqual(self.create('Fenetre longue').creation_review_status, PENDING)

    def test_every_status_counts_so_archiving_does_not_bypass_the_review(self):
        for organization in self.create_many(4):
            services.archive_organization(self.creator, organization.pk)
        self.assertEqual(self.create('Cinquieme').creation_review_status, PENDING)

    def test_only_the_creations_of_the_same_account_count(self):
        other = make_user('autre')
        self.create_many(4, user=other)
        self.assertEqual(self.create('Premiere').creation_review_status, NONE)

    def test_an_idempotent_double_submission_is_not_counted(self):
        organizations = self.create_many(3)
        self.assertEqual(self.create('Orga 2').pk, organizations[2].pk)  # double clic : même organisation
        self.assertEqual(self.create('Quatrieme').creation_review_status, NONE)
        self.assertEqual(self.create('Cinquieme').creation_review_status, PENDING)
        self.assertEqual(self.create('Cinquieme').pk, Organization.objects.get(name='Cinquieme').pk)
        self.assertEqual(AuditLog.objects.filter(action='ORG_CREATION_HELD_FOR_REVIEW').count(), 1)

    def test_held_creation_is_audited_and_announced_without_count_or_threshold(self):
        self.create_many(4)
        held = self.create('Cinquieme')
        entry = AuditLog.objects.get(action='ORG_CREATION_HELD_FOR_REVIEW')
        self.assertEqual((entry.actor_id, entry.target_id, entry.details), (self.creator.pk, held.pk, 'threshold_reached=true'))
        event = OutboxEvent.objects.get(event_type='identity.organization_governance_changed')
        self.assertEqual(event.payload, {
            'organization_id': str(held.pk), 'change': 'creation_review', 'actor_id': str(self.creator.pk),
        })
        # Une création ordinaire n'émet aucun événement de gouvernance ni trace de revue.
        self.assertEqual(OutboxEvent.objects.filter(event_type='identity.organization_governance_changed').count(), 1)

    def test_converted_and_existing_organizations_are_not_retroactively_held(self):
        organization = Organization.objects.create(name='Existante', org_type='ONG', created_by=self.creator)
        self.assertEqual(organization.creation_review_status, NONE)


class PendingReviewsCapTests(Base):
    def test_beyond_the_pending_cap_creation_is_refused_neutrally_and_journaled(self):
        self.assertEqual(IdentitySettings.get_solo().org_creation_review_max_pending, 3)
        set_settings(org_creation_review_threshold=2)
        organizations = self.create_many(4)
        self.assertEqual([o.creation_review_status for o in organizations], [NONE, PENDING, PENDING, PENDING])
        refused = self.client.post(ORGS, {'name': 'Cinquieme', 'org_type': 'ONG'}, format='json')
        self.assertEqual((refused.status_code, refused.json()['code']), (409, 'account_review_required'))
        self.assertEqual(refused.json()['detail'], NEUTRAL_DETAIL)
        entry = AuditLog.objects.get(action='ORG_CREATION_REFUSED_PENDING_REVIEWS')
        self.assertEqual((entry.actor_id, entry.details), (self.creator.pk, 'pending_reviews=true'))
        self.assertFalse(Organization.objects.filter(name='Cinquieme').exists())
        # Une levée libère une place ; la suivante est de nouveau retenue.
        services.clear_organization_creation_review(staff_with('review_organization_creation'), organizations[1].pk)
        self.assertEqual(self.create('Cinquieme').creation_review_status, PENDING)

    def test_the_cap_is_a_bounded_internal_setting(self):
        row = IdentitySettings.get_solo()
        for value in (0, 51):
            row.org_creation_review_max_pending = value
            with self.assertRaises(Exception):
                row.full_clean()


# --- Plafond technique caché : refus neutre -------------------------------------------------------------------

class HardLimitTests(Base):
    def assertNeutral(self, response, status_code=409):
        self.assertEqual(response.status_code, status_code, response.content)
        body = response.json()
        self.assertEqual((body['code'], body['detail']), ('account_review_required', NEUTRAL_DETAIL))
        self.assertIsNone(re.search(r'\d', body['detail']))
        for word in ('limite', 'maximal', 'plafond', 'quitte'):
            self.assertNotIn(word, body['detail'].lower())

    def test_creation_beyond_the_hard_limit_is_refused_neutrally(self):
        set_settings(max_memberships_hard_limit=2)
        self.create_many(2)
        self.assertNeutral(self.client.post(ORGS, {'name': 'Trois', 'org_type': 'ONG'}, format='json'))
        self.assertEqual(Organization.objects.filter(created_by=self.creator).count(), 2)

    def test_the_hard_limit_counts_every_active_membership_whatever_the_organization_status(self):
        """Créer puis archiver ne contourne pas le plafond (correction S5) ; seul un départ libère une place."""
        set_settings(max_memberships_hard_limit=2)
        first, second = self.create_many(2)
        services.archive_organization(self.creator, first.pk)
        services.suspend_organization(staff_with('suspend_organization'), second.pk, 'moderation')
        with self.assertRaises(services.OrganizationError) as caught:
            self.create('Troisieme')
        self.assertEqual(caught.exception.get_codes(), 'account_review_required')
        services.leave_organization(self.creator, first.pk)  # départ d'une organisation archivée : permis
        self.assertEqual(self.create('Troisieme').status, Organization.STATUS_ACTIVE)
        body = self.client.get(CONTEXTS).json()  # `unavailable` est borné par le même plafond
        self.assertEqual(len(body['results']) - 1 + len(body['unavailable']), 2)

    def test_hard_limit_refusals_feed_the_staff_queue_once_per_account_and_window(self):
        set_settings(max_memberships_hard_limit=1)
        self.create('Une')
        for name in ('Deux', 'Trois'):
            refused = self.client.post(ORGS, {'name': name, 'org_type': 'ONG'}, format='json')
            self.assertNeutral(refused)
        entry = AuditLog.objects.get(action='ORG_CREATION_REFUSED_ACCOUNT_REVIEW')
        self.assertEqual(
            (entry.actor_id, entry.target_id, entry.details), (self.creator.pk, self.creator.pk, 'hard_limit=true'),
        )
        # Une fenêtre plus tard, un nouveau refus est de nouveau journalisé.
        AuditLog.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timedelta(days=31))
        self.assertNeutral(self.client.post(ORGS, {'name': 'Quatre', 'org_type': 'ONG'}, format='json'))
        self.assertEqual(AuditLog.objects.filter(action='ORG_CREATION_REFUSED_ACCOUNT_REVIEW').count(), 2)
        # La file est lisible dans l'admin du journal (filtre par action).
        from apps.moderation.admin import AuditLogAdmin

        self.assertIn('action', AuditLogAdmin.list_filter)

    def test_a_double_submission_at_the_hard_limit_stays_idempotent(self):
        set_settings(max_memberships_hard_limit=1)
        first = self.create('Une')
        self.assertEqual(self.create('Une').pk, first.pk)  # verrou du compte, puis doublon, puis plafond
        self.assertFalse(AuditLog.objects.filter(action='ORG_CREATION_REFUSED_ACCOUNT_REVIEW').exists())

    def test_acceptance_beyond_the_hard_limit_is_refused_neutrally_and_the_invitation_stays_pending(self):
        owner = make_user('proprio-invite')
        organization = services.create_organization(owner, 'Invitante', 'ONG')
        invitation, token = services.create_invitation(owner, organization.pk, ANALYST)
        set_settings(max_memberships_hard_limit=1)
        self.create('Deja une')
        self.assertNeutral(self.client.post(ACCEPT, {'token': token}, format='json'))
        self.assertEqual(OrganizationInvitation.objects.get(pk=invitation.pk).status, 'PENDING')
        refusal = AuditLog.objects.filter(action='INVITATION_REFUSED').latest('created_at')
        self.assertTrue(refusal.details.endswith('reason=hard_limit'))
        queued = AuditLog.objects.get(action='ORG_CREATION_REFUSED_ACCOUNT_REVIEW')
        self.assertEqual((queued.actor_id, queued.details), (self.creator.pk, 'hard_limit=true'))

    def test_add_member_beyond_the_hard_limit_keeps_its_single_neutral_answer(self):
        owner = make_user('proprio-ajout')
        organization = services.create_organization(owner, 'Ajout', 'ONG')
        set_settings(max_memberships_hard_limit=1)
        self.create('Deja une')
        with self.assertRaises(services.OrganizationError) as caught:
            services.add_member(owner, organization.pk, self.creator.pk, ANALYST)
        self.assertEqual(caught.exception.get_codes(), 'user_unavailable')


# --- Aucun seuil exposé (introspection, Q22) -------------------------------------------------------------------

class HiddenThresholdsTests(Base):
    def setUp(self):
        super().setUp()
        set_settings(
            max_memberships_hard_limit=SENTINEL_HARD_LIMIT, org_creation_review_window_days=SENTINEL_WINDOW,
            org_creation_review_threshold=2,
        )
        self.create('Premiere')
        self.held = self.create('Retenue')
        set_settings(org_creation_review_threshold=SENTINEL_THRESHOLD)

    def assertNothingHidden(self, body):
        keys, ints = all_keys_and_ints(body)
        for key in keys:
            for fragment in HIDDEN_KEY_FRAGMENTS:
                self.assertNotIn(fragment, key)
        self.assertFalse(ints & {SENTINEL_HARD_LIMIT, SENTINEL_WINDOW, SENTINEL_THRESHOLD}, body)

    def test_limits_has_exactly_the_contract_keys(self):
        body = self.client.get(f'{ORGS}limits/').json()
        self.assertEqual(set(body), {
            'max_categories_per_context', 'name_min_length', 'name_max_length', 'description_max_length',
            'invitation_ttl_days', 'max_pending_invitations',
        })
        self.assertNothingHidden(body)

    def test_contexts_and_internal_expose_only_the_review_flag(self):
        contexts = self.client.get(CONTEXTS).json()
        self.assertNothingHidden(contexts)
        internal = self.client.get(f'{ORGS}{self.held.pk}/internal/').json()
        self.assertNothingHidden(internal)
        self.assertEqual(internal['governance'], {'primary_admin_state': 'OK', 'under_review': True})

    def test_openapi_schema_publishes_no_threshold(self):
        from drf_spectacular.generators import SchemaGenerator

        schema = json.dumps(SchemaGenerator().get_schema(request=None, public=True))
        for fragment in ('max_organizations_per_account', 'max_memberships_hard_limit', 'org_creation_review',
                         'organization_limit_reached'):
            self.assertNotIn(fragment, schema)
        self.assertIn('account_review_required', schema)
        self.assertIn('org_create_burst', schema)


# --- API : création retenue, gouvernance, usage interne --------------------------------------------------------

class CreationApiTests(Base):
    def test_held_creation_answers_201_like_any_creation_with_the_review_flag(self):
        set_settings(org_creation_review_threshold=2)
        normal = self.client.post(ORGS, {'name': 'Normale', 'org_type': 'ONG'}, format='json')
        held = self.client.post(ORGS, {'name': 'Retenue', 'org_type': 'ONG'}, format='json')
        self.assertEqual((normal.status_code, held.status_code), (201, 201))
        self.assertEqual(set(normal.json()), set(held.json()))
        self.assertEqual(normal.json()['governance'], {'primary_admin_state': 'OK', 'under_review': False})
        self.assertEqual(held.json()['governance'], {'primary_admin_state': 'OK', 'under_review': True})
        self.assertEqual(held.json()['status'], 'ACTIVE')

    def test_contexts_carry_governance_on_organization_results_only(self):
        set_settings(org_creation_review_threshold=2)
        normal, held = self.create('Normale'), self.create('Retenue')
        suspended = self.create('Suspendue')  # retenue elle aussi
        services.suspend_organization(staff_with('suspend_organization'), suspended.pk, 'moderation')
        body = self.client.get(CONTEXTS).json()
        flags = {item['id']: item.get('governance') for item in body['results']}
        self.assertEqual(flags[str(normal.pk)], {'primary_admin_state': 'OK', 'under_review': False})
        self.assertEqual(flags[str(held.pk)], {'primary_admin_state': 'OK', 'under_review': True})
        self.assertIsNone(flags[str(self.creator.pk)])  # contexte personnel : pas de clé
        self.assertEqual(len(body['unavailable']), 1)
        self.assertEqual(len(body['unavailable'][0]), 9)  # `unavailable` garde exactement ses 9 clés
        self.assertNotIn('governance', body['unavailable'][0])

    def test_a_held_organization_stays_editable_by_its_team(self):
        """La revue de création n'est pas une restriction (ADR 0011 D11) : l'équipe complète son organisation."""
        held = self.create_held()
        response = self.client.patch(f'{ORGS}{held.pk}/', {'description': 'Complétée'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get(f'{ORGS}{held.pk}/internal/').status_code, 200)


class InvitationsDuringReviewTests(Base):
    PREVIEW = '/api/v1/accounts/organization-invitations/preview/'

    def setUp(self):
        super().setUp()
        self.invitee = make_user('invitee')
        self.invitee_client = login(self.invitee)

    def test_a_held_organization_cannot_invite(self):
        held = self.create_held()
        response = self.client.post(f'{ORGS}{held.pk}/invitations/', {'role': ANALYST}, format='json')
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual((response.json()['code'], response.json()['detail']), ('account_review_required', NEUTRAL_DETAIL))
        self.assertFalse(OrganizationInvitation.objects.filter(organization=held).exists())
        # Un non-membre reçoit toujours le refus d'appartenance : aucun oracle sur la revue.
        outsider = login(make_user('dehors'))
        self.assertEqual(
            outsider.post(f'{ORGS}{held.pk}/invitations/', {'role': ANALYST}, format='json').json()['code'],
            'DENY_RELATION',
        )

    def test_invitations_created_before_the_review_are_not_redeemable_until_it_is_cleared(self):
        organization = self.create('Normale')
        invitation, token = services.create_invitation(self.creator, organization.pk, ANALYST)
        Organization.objects.filter(pk=organization.pk).update(creation_review_status=PENDING)
        for response in (
            self.invitee_client.post(self.PREVIEW, {'token': token}, format='json'),
            self.invitee_client.post(ACCEPT, {'token': token}, format='json'),
        ):
            self.assertEqual((response.status_code, response.json()['code']), (404, 'invitation_invalid'))
        self.assertEqual(OrganizationInvitation.objects.get(pk=invitation.pk).status, 'PENDING')
        self.assertTrue(AuditLog.objects.filter(
            action='INVITATION_REFUSED', details__endswith='reason=org_under_review').exists())
        services.clear_organization_creation_review(staff_with('review_organization_creation'), organization.pk)
        accepted = self.invitee_client.post(ACCEPT, {'token': token}, format='json')
        self.assertEqual(accepted.status_code, 200, accepted.content)


# --- Invisibilité publique et levée ----------------------------------------------------------------------------

class PublicVisibilityTests(Base):
    def setUp(self):
        super().setUp()
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        set_settings(org_creation_review_threshold=2)
        self.visible = self.create('Visible')
        self.held = self.create('Retenue')
        self.reviewer = staff_with('review_organization_creation', label='revue')

    def offer_of(self, organization):
        from apps.marketplace import services as marketplace_services

        return marketplace_services.create_offer(
            actor=self.creator, context_type='ORGANIZATION', context_id=organization.pk, data=dict(
                category_id=self.category.id, commune_id=self.commune.id, title='Un joli canapé à vendre',
                description='Description suffisamment longue pour passer la validation du CDC.', price=100,
                main_image=make_test_image(), expires_at=timezone.now() + timedelta(days=30),
            ),
        )

    def listed_ids(self):
        return {item['id'] for item in APIClient().get(ORGS).json()['results']}

    def test_held_organization_is_absent_from_every_public_surface(self):
        self.assertEqual(self.listed_ids(), {str(self.visible.pk)})
        self.assertTrue(services.is_seller_context_public('ORGANIZATION', self.visible.pk))
        self.assertFalse(services.is_seller_context_public('ORGANIZATION', self.held.pk))
        self.assertEqual(APIClient().get(SELLER_PAGE.format(self.held.pk)).status_code, 404)
        self.assertEqual(APIClient().get(SELLER_PAGE.format(self.visible.pk)).status_code, 200)
        self.assertFalse(self.offer_of(self.held).seller_is_public)
        self.assertTrue(self.offer_of(self.visible).seller_is_public)
        # Recherche par nom : rien non plus.
        self.assertEqual(APIClient().get(ORGS, {'search': 'Retenue'}).json()['results'], [])

    def test_staff_clears_the_review_and_the_organization_and_its_offers_become_public(self):
        offer = self.offer_of(self.held)
        cleared = services.clear_organization_creation_review(self.reviewer, self.held.pk)
        self.assertEqual(cleared.creation_review_status, CLEARED)
        dispatch_outbox_now()
        self.assertIn(str(self.held.pk), self.listed_ids())
        self.assertTrue(Offer.objects.get(pk=offer.pk).seller_is_public)
        entry = AuditLog.objects.get(action='ORG_CREATION_REVIEW_CLEARED')
        self.assertEqual((entry.actor_id, entry.target_id, entry.details), (self.reviewer.pk, self.held.pk, 'status=ACTIVE'))
        status_event = OutboxEvent.objects.get(event_type='identity.seller_context_status_changed')
        self.assertEqual(status_event.payload['reason'], 'creation_review_cleared')
        changes = list(OutboxEvent.objects.filter(
            event_type='identity.organization_governance_changed').values_list('payload', flat=True))
        self.assertEqual({c['change'] for c in changes}, {'creation_review', 'creation_review_cleared'})

    def test_a_suspended_held_organization_stays_hidden_after_the_review_is_cleared(self):
        services.suspend_organization(staff_with('suspend_organization', label='susp'), self.held.pk, 'moderation')
        services.clear_organization_creation_review(self.reviewer, self.held.pk)
        self.assertFalse(services.is_seller_context_public('ORGANIZATION', self.held.pk))
        self.assertNotIn(str(self.held.pk), self.listed_ids())


class ClearReviewPermissionTests(Base):
    def setUp(self):
        super().setUp()
        self.held = self.create_held()

    def test_permission_is_required_and_is_staff_or_suspension_right_is_not_enough(self):
        for actor in (self.creator, make_user('simple', is_staff=True), staff_with('suspend_organization')):
            with self.assertRaises(ContextDenied) as caught:
                services.clear_organization_creation_review(actor, self.held.pk)
            self.assertEqual(caught.exception.get_codes(), DENY_PERMISSION)
        inactive = staff_with('review_organization_creation', label='inactif')
        User.objects.filter(pk=inactive.pk).update(is_active=False)
        with self.assertRaises(ContextDenied):
            services.clear_organization_creation_review(User.objects.get(pk=inactive.pk), self.held.pk)
        self.assertEqual(Organization.objects.get(pk=self.held.pk).creation_review_status, PENDING)

    def test_a_member_or_the_creator_never_clears_their_own_review(self):
        reviewer = staff_with('review_organization_creation', label='membre-revue')
        Membership.objects.create(organization=self.held, user=reviewer, role=ANALYST)
        with self.assertRaises(services.OrganizationError) as caught:
            services.clear_organization_creation_review(reviewer, self.held.pk)
        self.assertEqual((caught.exception.get_codes(), caught.exception.status_code), ('interest_conflict', 403))
        self.assertEqual(AuditLog.objects.get(action='ORG_CREATION_REVIEW_DENIED').details, 'reason=interest_conflict')
        self.assertEqual(Organization.objects.get(pk=self.held.pk).creation_review_status, PENDING)

    def test_a_person_awaiting_confirmation_on_the_organization_cannot_clear_its_review(self):
        set_settings(org_creation_review_threshold=100)
        organization = self.create('Normale')
        _, token = services.create_invitation(self.creator, organization.pk, capabilities.ROLE_ADMIN)
        reviewer = staff_with('review_organization_creation', label='en-attente')
        self.assertEqual(services.accept_invitation(reviewer, token).status, services.ACCEPTANCE_AWAITING_CONFIRMATION)
        Organization.objects.filter(pk=organization.pk).update(creation_review_status=PENDING)
        with self.assertRaises(services.OrganizationError) as caught:
            services.clear_organization_creation_review(reviewer, organization.pk)
        self.assertEqual(caught.exception.get_codes(), 'interest_conflict')
        self.assertEqual(Organization.objects.get(pk=organization.pk).creation_review_status, PENDING)

    def test_only_a_pending_review_can_be_cleared(self):
        reviewer = staff_with('review_organization_creation', label='revue2')
        services.clear_organization_creation_review(reviewer, self.held.pk)
        with self.assertRaises(services.OrganizationError) as caught:
            services.clear_organization_creation_review(reviewer, self.held.pk)
        self.assertEqual(caught.exception.get_codes(), 'invalid_status')
        self.assertEqual(AuditLog.objects.filter(action='ORG_CREATION_REVIEW_CLEARED').count(), 1)
        with self.assertRaises(ContextDenied):
            services.clear_organization_creation_review(reviewer, 'pas-un-uuid')


class AdminQueueTests(Base):
    def setUp(self):
        super().setUp()
        self.held = self.create_held()
        self.model_admin = OrganizationAdmin(Organization, admin.site)

    def request_for(self, user):
        request = RequestFactory().post('/')
        request.user = user
        request._messages = mock.MagicMock()
        return request

    def test_queue_filter_and_action_are_reserved_to_the_permission(self):
        self.assertIn('creation_review_status', self.model_admin.list_filter)
        self.assertIn('creation_review_status', self.model_admin.list_display)
        allowed = staff_with('view_organization', 'review_organization_creation', label='file')
        denied = staff_with('view_organization', 'suspend_organization', label='sans-revue')
        self.assertIn('clear_creation_review_selected', self.model_admin.get_actions(self.request_for(allowed)))
        self.assertNotIn('clear_creation_review_selected', self.model_admin.get_actions(self.request_for(denied)))

    def test_admin_action_goes_through_the_audited_service(self):
        allowed = staff_with('view_organization', 'review_organization_creation', label='file2')
        queryset = Organization.objects.filter(creation_review_status=PENDING)
        self.model_admin.clear_creation_review_selected(self.request_for(allowed), queryset)
        self.assertEqual(Organization.objects.get(pk=self.held.pk).creation_review_status, CLEARED)
        self.assertTrue(AuditLog.objects.filter(action='ORG_CREATION_REVIEW_CLEARED', actor=allowed).exists())

    def test_setup_roles_grants_the_review_to_the_verification_group_only(self):
        """Séparation des fonctions (ADR 0010 §9.1) : ni l'Administrateur ni le Modérateur ne lèvent une revue."""
        call_command('setup_roles', verbosity=0)
        call_command('setup_roles', verbosity=0)  # idempotent
        codename = 'review_organization_creation'
        verification = Group.objects.get(name='Vérification')
        self.assertEqual(
            set(verification.permissions.values_list('codename', flat=True)),
            {'view_organization', codename},
        )
        for name in ('Administrateur', 'Modérateur'):
            self.assertFalse(Group.objects.get(name=name).permissions.filter(codename=codename).exists(), name)
        member = make_user('verif', is_staff=True)
        member.groups.add(verification)
        member = User.objects.get(pk=member.pk)
        self.assertTrue(member.has_perm(services.REVIEW_CREATION_PERMISSION))
        services.clear_organization_creation_review(member, self.held.pk)
        self.assertEqual(Organization.objects.get(pk=self.held.pk).creation_review_status, CLEARED)


# --- Notifications neutres -----------------------------------------------------------------------------------

class NotificationTests(Base):
    def test_creator_is_told_the_organization_is_under_review_without_any_number(self):
        held = self.create_held()
        dispatch_outbox_now()
        notification = Notification.objects.get(user=self.creator, title="Organisation en cours d'examen")
        self.assertEqual(notification.content, (
            "« Retenue » est en cours d'examen par l'équipe Connecte+. Elle n'apparaît pas encore publiquement."
        ))
        self.assertEqual(notification.link, f'/organizations/{held.pk}')
        self.assertIsNone(re.search(r'\d', notification.title + notification.content))

    def test_clearance_is_announced_to_the_team_but_not_to_the_staff_member(self):
        held = self.create_held()
        analyst = make_user('analyste')
        Membership.objects.create(organization=held, user=analyst, role=ANALYST)
        reviewer = staff_with('review_organization_creation', label='revue-notif')
        services.clear_organization_creation_review(reviewer, held.pk)
        dispatch_outbox_now()
        recipients = set(Notification.objects.filter(title='Examen terminé').values_list('user_id', flat=True))
        self.assertEqual(recipients, {self.creator.pk, analyst.pk})
        self.assertFalse(Notification.objects.filter(user=reviewer).exists())
        # Aucune notification de statut en double (la raison `creation_review_cleared` n'en produit pas).
        self.assertFalse(Notification.objects.filter(title__startswith='Organisation réactivée').exists())

    def test_ordinary_creation_sends_no_review_notification(self):
        self.create('Normale')
        dispatch_outbox_now()
        self.assertFalse(Notification.objects.filter(title="Organisation en cours d'examen").exists())


# --- Throttle `org_create_burst` -------------------------------------------------------------------------------

@override_settings(CACHES=LOCMEM_CACHE)
class BurstThrottleTests(Base):
    def test_third_creation_within_the_hour_is_throttled_with_a_generic_message(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'org_create': '50/day'}):
            codes = [
                self.client.post(ORGS, {'name': f'Rafale {i}', 'org_type': 'ONG'}, format='json')
                for i in range(3)
            ]
        self.assertEqual([r.status_code for r in codes], [201, 201, 429])
        refused = codes[2]
        self.assertTrue(refused.has_header('Retry-After'))
        self.assertEqual(refused.json()['code'], 'throttled')
        # Le quota n'est jamais cité : hors du délai d'attente (« N seconde(s) »), aucun chiffre.
        self.assertIsNone(re.search(r'\d', re.sub(r'\d+ secondes?', '', refused.json()['detail'])))
        # Les lectures ne sont pas comptées.
        self.assertEqual(self.client.get(ORGS).status_code, 200)

    def test_only_effective_creations_count_towards_the_burst(self):
        """Ni une double soumission idempotente ni un refus ne consomment le quota en rafale (`org_create`, lui,
        compte toutes les tentatives)."""
        set_settings(max_memberships_hard_limit=1)

        def post(name):
            return self.client.post(ORGS, {'name': name, 'org_type': 'ONG'}, format='json')

        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'org_create': '50/day'}):
            first = post('Une')
            self.assertEqual(post('Une').json()['id'], first.json()['id'])  # double clic : 201, non compté
            self.assertEqual(post('Deux').status_code, 409)  # refus : non compté
            set_settings(max_memberships_hard_limit=200)
            self.assertEqual(post('Deux').status_code, 201)  # 2e création effective
            self.assertEqual(post('Trois').status_code, 429)
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'org_create': '4/day'}):
            cache.clear()
            codes = [post(f'Essai {i}').status_code for i in range(1)]
            set_settings(max_memberships_hard_limit=1)
            codes += [post(f'Refus {i}').status_code for i in range(3)]
            codes.append(post('Encore').status_code)
        self.assertEqual(codes, [201, 409, 409, 409, 429])  # `org_create` compte les tentatives refusées

    def test_rate_falls_back_to_the_proposed_value_and_a_setting_wins(self):
        rates = dict(SimpleRateThrottle.THROTTLE_RATES)
        rates.pop('org_create_burst', None)
        with mock.patch.object(throttles.OrganizationCreateBurstThrottle, 'THROTTLE_RATES', rates):
            self.assertEqual(throttles.OrganizationCreateBurstThrottle().rate, '2/hour')
        with mock.patch.object(throttles.OrganizationCreateBurstThrottle, 'THROTTLE_RATES', {'org_create_burst': '7/hour'}):
            self.assertEqual(throttles.OrganizationCreateBurstThrottle().rate, '7/hour')


# --- Migration 0021 : fonctions de données ----------------------------------------------------------------------

class MigrationFunctionsTests(TestCase):
    migration = importlib.import_module('apps.identity.migrations.0021_creation_antiabuse')

    def test_hard_limit_is_raised_to_the_new_default_and_clamped_back_on_rollback(self):
        row = IdentitySettings.get_solo()
        set_settings(max_memberships_hard_limit=10)
        self.migration.raise_hard_limit(django_apps, None)
        self.assertEqual(IdentitySettings.objects.get(pk=row.pk).max_memberships_hard_limit, 200)
        set_settings(max_memberships_hard_limit=500)
        self.migration.raise_hard_limit(django_apps, None)
        self.assertEqual(IdentitySettings.objects.get(pk=row.pk).max_memberships_hard_limit, 500)
        self.migration.clamp_to_old_bounds(django_apps, None)
        self.assertEqual(IdentitySettings.objects.get(pk=row.pk).max_memberships_hard_limit, 100)

    def test_rollback_is_refused_while_an_organization_is_held(self):
        self.migration.refuse_rollback_with_pending_reviews(django_apps, None)  # rien en revue : passe
        Organization.objects.create(name='Retenue', org_type='ONG', creation_review_status=PENDING)
        with self.assertRaises(RuntimeError) as caught:
            self.migration.refuse_rollback_with_pending_reviews(django_apps, None)
        self.assertIn('revue de création', str(caught.exception))
