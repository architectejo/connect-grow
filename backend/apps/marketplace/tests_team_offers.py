"""Règle `last_effective_owner` (L1-01-B1, ADR 0008 §9) avec des offres : `seller_has_active_offers` et refus 409 du
départ, de la rétrogradation et du transfert qui laisseraient une organisation ACTIVE à offres actives sans
propriétaire effectif."""
from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.models import Membership, Organization, User
from apps.moderation.models import AuditLog, Sanction
from apps.platform_core.models import OutboxEvent

from . import services
from .models import Offer
from .tests_contexts import ADMIN, OWNER, ContextBase

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'team-offers'}}
ORGS = '/api/v1/accounts/organizations/'


def client_for(user):
    client = APIClient()
    client.force_authenticate(User.objects.get(pk=user.pk))
    return client


class ActiveOffersServiceTests(ContextBase):
    def has(self, org=None):
        return services.seller_has_active_offers('ORGANIZATION', (org or self.org).pk)

    def test_no_offer(self):
        self.assertFalse(self.has())

    def test_an_active_offer_counts(self):
        self.org_offer()
        self.assertTrue(self.has())

    def test_expired_by_date_or_status_deleted_paused_and_sold_do_not_count(self):
        past = timezone.now() - timedelta(days=1)
        for kwargs in (
            {'expires_at': past}, {'status': Offer.STATUS_EXPIRED}, {'status': Offer.STATUS_PAUSED},
            {'status': Offer.STATUS_SOLD}, {'is_deleted': True},
        ):
            with self.subTest(kwargs=kwargs):
                Offer.objects.all().delete()
                offer = self.org_offer()
                Offer.objects.filter(pk=offer.pk).update(**kwargs)
                self.assertFalse(self.has())

    def test_a_null_or_future_expiry_counts(self):
        offer = self.org_offer()
        Offer.objects.filter(pk=offer.pk).update(expires_at=None)
        self.assertTrue(self.has())
        Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() + timedelta(days=3))
        self.assertTrue(self.has())

    def test_offers_of_another_context_do_not_count(self):
        self.org_offer(org=self.other_org)
        self.make_offer()  # contexte personnel
        self.assertFalse(self.has())

    def test_a_single_query(self):
        with self.assertNumQueries(1):
            self.has()


@override_settings(CACHES=LOCMEM_CACHE)
class LastEffectiveOwnerWithOffersTests(ContextBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.join(self.member, role=OWNER)
        self.other = User.objects.create_user(
            email='second-owner@example.com', password='x', full_name='Second Proprietaire', phone_verified=True,
        )
        self.other_membership = self.join(self.other, role=OWNER)
        self.owner_membership = Membership.objects.get(organization=self.org, user=self.member)
        Sanction.objects.create(
            user=self.other, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.seller,
        ).apply()  # le second propriétaire n'est plus effectif : `self.member` est le seul propriétaire effectif

    def leave(self):
        return client_for(self.member).post(f'{ORGS}{self.org.pk}/leave/')

    def demote(self):
        return client_for(self.member).patch(
            f'{ORGS}{self.org.pk}/members/{self.owner_membership.pk}/',
            {'role': ADMIN, 'confirm': True, 'password': 'x'}, format='json',
        )

    def assert_refused(self, response):
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['code'], 'last_effective_owner')

    def assert_unchanged(self):
        self.assertEqual(Membership.objects.get(pk=self.owner_membership.pk).role, OWNER)
        self.assertEqual(Membership.objects.get(pk=self.owner_membership.pk).status, Membership.STATUS_ACTIVE)

    def test_leave_is_refused_with_an_active_offer_and_changes_nothing(self):
        self.org_offer()
        audits, events = AuditLog.objects.count(), OutboxEvent.objects.count()
        self.assert_refused(self.leave())
        self.assert_unchanged()
        self.assertEqual((AuditLog.objects.count(), OutboxEvent.objects.count()), (audits, events))

    def test_demotion_is_refused_with_an_active_offer(self):
        self.org_offer()
        self.assert_refused(self.demote())
        self.assert_unchanged()

    def test_leave_and_demotion_are_allowed_without_active_offer_and_traced_as_orphaned(self):
        offer = self.org_offer()
        Offer.objects.filter(pk=offer.pk).update(status=Offer.STATUS_PAUSED)
        self.assertEqual(self.demote().status_code, 200)
        self.assertIn('orphaned=true', AuditLog.objects.filter(action='MEMBERSHIP_ROLE_CHANGED').latest('created_at').details)

    def test_expired_offer_does_not_block(self):
        offer = self.org_offer()
        Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(self.leave().status_code, 204)

    def test_a_second_effective_owner_removes_the_obstacle(self):
        self.org_offer()
        Sanction.objects.filter(user=self.other).first().lift()
        self.assertEqual(self.leave().status_code, 204)
        self.assertNotIn('orphaned', AuditLog.objects.filter(action='MEMBERSHIP_REVOKED').latest('created_at').details)

    def test_the_rule_ignores_a_suspended_organization(self):
        self.org_offer()
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertEqual(self.leave().status_code, 204)

    def test_last_owner_guard_takes_precedence(self):
        self.org_offer()
        Membership.objects.filter(pk=self.other_membership.pk).update(status=Membership.STATUS_REVOKED)
        response = self.leave()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'last_owner')

    def test_transfer_to_an_effective_owner_is_never_refused(self):
        self.org_offer()
        successor = User.objects.create_user(
            email='succ@example.com', password='x', full_name='Successeur Test', phone_verified=True,
        )
        membership = self.join(successor, role=ADMIN)
        response = client_for(self.member).post(f'{ORGS}{self.org.pk}/transfer-ownership/', {
            'membership_id': str(membership.pk), 'confirm': True, 'password': 'x',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Membership.objects.get(pk=membership.pk).role, OWNER)

    def test_the_refusal_is_in_french_and_carries_no_personal_data(self):
        self.org_offer()
        body = self.leave().json()
        self.assertIn('administrateur principal', body['detail'])
        self.assertNotIn('propriétaire', body['detail'])
        self.assertNotIn(self.member.email, str(body))
