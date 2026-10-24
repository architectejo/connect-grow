"""Signalement d'une offre par contexte vendeur (ADR 0006, 19.3 n°7, dette de T5a) : un membre actif ne signale pas
l'offre de son organisation, un ancien membre ou un tiers le peut ; un seul résolveur d'auteurs, par lot."""
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.common.contexts import CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER
from apps.identity import services as identity_services
from apps.identity.models import Membership, Organization, ProviderProfile, User
from apps.marketplace import services as marketplace_services
from apps.marketplace.models import Offer
from apps.marketplace.tests import make_test_image

from . import services
from .models import Report
from .tests import ModerationTestBase

REPORTS = '/api/moderation/reports/'
ROLES = ('OWNER', 'ADMIN', 'EDITOR', 'ANALYST')


class OrganizationReportTests(ModerationTestBase):
    def setUp(self):
        super().setUp()
        self.org = Organization.objects.create(name='Atelier X', org_type='ENTREPRISE')
        self.members = {}
        for role in ROLES:
            user = User.objects.create_user(email=f'm-{role.lower()}@example.com', password='x', full_name=role)
            Membership.objects.create(organization=self.org, user=user, role=role)
            self.members[role] = user
        self.offer = self.offer_of('ORGANIZATION', self.org.pk)

    def offer_of(self, context_type, context_id):
        return Offer.objects.create(
            seller=None, seller_context_type=context_type, seller_context_id=context_id,
            created_by=self.seller, category_id=self.category.id, commune_id=self.commune.id,
            title='Offre de test', description='Description suffisamment longue pour le CDC.',
            price=100, main_image=make_test_image(),
        )

    def report(self, user, offer=None):
        self.client.force_authenticate(user)
        return self.client.post(REPORTS, {
            'target_type': 'POST', 'object_id': str(offer.id if offer else self.offer.id), 'reason': 'ARNAQUE',
        })

    def test_every_active_member_is_refused_whatever_the_role(self):
        for role, user in self.members.items():
            with self.subTest(role=role):
                response = self.report(user)
                self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Report.objects.count(), 0)

    def test_authors_of_an_organization_offer_are_its_active_members(self):
        authors = marketplace_services.get_report_authors([self.offer.id])
        self.assertEqual(authors[self.offer.id], frozenset(user.pk for user in self.members.values()))
        self.assertEqual(
            services.resolve_target_authors('offer', self.offer.id), frozenset(u.pk for u in self.members.values()),
        )
        self.assertIsNone(services.resolve_target_author('offer', self.offer.id))  # plusieurs auteurs : pas d'auteur unique

    def test_suspended_organization_does_not_allow_reporting_its_own_offer(self):
        Organization.objects.filter(pk=self.org.pk).update(status='SUSPENDED')
        self.assertEqual(self.report(self.members['EDITOR']).status_code, 400)
        self.assertEqual(self.report(self.reporter).status_code, 201)

    def test_single_member_organization_offer_has_no_unique_author(self):
        solo = Organization.objects.create(name='Solo', org_type='ONG')
        Membership.objects.create(organization=solo, user=self.members['OWNER'], role='OWNER')
        offer = self.offer_of('ORGANIZATION', solo.pk)
        self.assertEqual(services.resolve_target_authors('offer', offer.id), frozenset({self.members['OWNER'].pk}))
        self.assertIsNone(services.resolve_target_author('offer', offer.id))
        self.assertEqual(services.resolve_target_author('user', self.seller.pk), self.seller.pk)

    def test_former_member_stranger_and_buyer_can_report(self):
        Membership.objects.filter(user=self.members['EDITOR']).update(status='REVOKED')
        for user in (self.members['EDITOR'], self.reporter, self.seller):
            with self.subTest(user=user.email):
                self.assertEqual(self.report(user).status_code, 201)
        self.assertEqual(Report.objects.count(), 3)

    def test_a_member_of_another_organization_can_report(self):
        other = Organization.objects.create(name='Atelier B', org_type='BOUTIQUE')
        offer = self.offer_of('ORGANIZATION', other.pk)  # le propriétaire de l'atelier X n'est pas membre de B
        self.assertEqual(self.report(self.members['OWNER'], offer).status_code, 201)

    def test_provider_and_personal_contexts_still_refuse_their_holder(self):
        profile = ProviderProfile.objects.create(user=self.seller, display_name='Marie couture')
        provider_offer = self.offer_of('PROVIDER', profile.pk)
        personal_offer = self.offer_of('USER', self.seller.pk)
        for offer in (provider_offer, personal_offer):
            self.assertEqual(self.report(self.seller, offer).status_code, 400)
            self.assertEqual(self.report(self.reporter, offer).status_code, 201)

    def test_authors_resolver_is_batched_and_constant(self):
        orgs = [Organization.objects.create(name=f'O{i}', org_type='ONG') for i in range(6)]
        offers = [self.offer_of('ORGANIZATION', org.pk) for org in orgs]
        offers.append(self.offer_of('USER', self.seller.pk))
        with CaptureQueriesContext(connection) as many:
            marketplace_services.get_report_authors([o.id for o in offers])
        with CaptureQueriesContext(connection) as few:
            marketplace_services.get_report_authors([offers[0].id])
        self.assertEqual(len(many), len(few))


class AuthorsEquivalenceTests(ModerationTestBase):
    """`get_context_member_accounts` (par lot) doit rester identique à `acts_for_context` (par appel)."""

    def test_batch_definition_matches_acts_for_context_for_every_context_and_user(self):
        active = Organization.objects.create(name='Active', org_type='ENTREPRISE')
        suspended = Organization.objects.create(name='Suspendue', org_type='ENTREPRISE', status='SUSPENDED')
        archived = Organization.objects.create(name='Archivée', org_type='ENTREPRISE', status='ARCHIVED')
        users = {role: User.objects.create_user(email=f'q-{role}@example.com', password='x', full_name=role) for role in ROLES}
        former = User.objects.create_user(email='former@example.com', password='x', full_name='Ancien')
        for org in (active, suspended, archived):
            for role, user in users.items():
                Membership.objects.create(organization=org, user=user, role=role)
            Membership.objects.create(organization=org, user=former, role='EDITOR', status='REVOKED')
        profile = ProviderProfile.objects.create(user=self.seller, display_name='Marie couture')
        archived_profile_owner = User.objects.create_user(email='pa@example.com', password='x', full_name='PA')
        archived_profile = ProviderProfile.objects.create(
            user=archived_profile_owner, display_name='Archivé', status='ARCHIVED',
        )
        contexts = [
            (CONTEXT_USER, self.seller.pk), (CONTEXT_PROVIDER, profile.pk), (CONTEXT_PROVIDER, archived_profile.pk),
            (CONTEXT_ORGANIZATION, active.pk), (CONTEXT_ORGANIZATION, suspended.pk),
            (CONTEXT_ORGANIZATION, archived.pk),
        ]
        everyone = list(users.values()) + [former, self.seller, self.reporter, archived_profile_owner]
        batch = identity_services.get_context_member_accounts(contexts)
        for context_type, context_id in contexts:
            for user in everyone:
                with self.subTest(context=(context_type, str(context_id)[:8]), user=user.email):
                    expected = identity_services.acts_for_context(user.pk, context_type, context_id)
                    if context_id == suspended.pk:
                        # Écart voulu : la suspension n'autorise pas à signaler sa propre offre.
                        expected = Membership.objects.filter(
                            organization_id=suspended.pk, user=user, status='ACTIVE',
                        ).exists()
                    self.assertEqual(user.pk in batch[(context_type, context_id)], expected)
