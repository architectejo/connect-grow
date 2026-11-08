"""Visibilité d'une organisation selon l'état de ses propriétaires (L0-09 T9-1, audit M3, ADR 0006 section 20).

Une organisation dont TOUS les propriétaires actifs sont désactivés ou sous sanction bloquante n'est pas publique ;
le statut stocké de l'organisation ne change pas. Un second propriétaire actif la garde publique ; la levée de la
sanction la rend de nouveau publique."""
from apps.identity import services as identity_services
from apps.identity.models import Membership, Organization, User
from apps.moderation.models import Sanction

from .models import Offer
from .tests_contexts import ADMIN, OWNER, ContextBase


class OwnerVisibilityTests(ContextBase):
    def setUp(self):
        super().setUp()
        self.join(self.member, role=OWNER)
        self.offer = self.org_offer()

    def public(self):
        return Offer.objects.get(pk=self.offer.pk).seller_is_public

    def second_owner(self):
        other = User.objects.create_user(email='second@example.com', password='x', full_name='Second Proprietaire')
        self.join(other, role=OWNER)
        return other

    def test_sole_owner_deactivated_hides_the_offers_without_changing_the_status(self):
        self.assertTrue(self.public())
        identity_services.set_account_active(self.member.pk, False)
        self.assertFalse(self.public())
        self.assertEqual(Organization.objects.get(pk=self.org.pk).status, Organization.STATUS_ACTIVE)

    def test_reactivation_makes_the_offers_public_again(self):
        identity_services.set_account_active(self.member.pk, False)
        identity_services.set_account_active(self.member.pk, True)
        self.assertTrue(self.public())

    def test_second_active_owner_keeps_the_organization_public(self):
        self.second_owner()
        identity_services.set_account_active(self.member.pk, False)
        self.assertTrue(self.public())

    def test_all_owners_deactivated_hides_the_offers(self):
        other = self.second_owner()
        identity_services.set_account_active(self.member.pk, False)
        identity_services.set_account_active(other.pk, False)
        self.assertFalse(self.public())

    def test_blocking_sanction_then_lift(self):
        sanction = Sanction.objects.create(
            user=self.member, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.seller,
        )
        sanction.apply()
        self.assertFalse(self.public())
        sanction.lift()
        self.assertTrue(self.public())

    def test_a_demoted_owner_leaves_no_active_owner(self):
        Membership.objects.filter(organization=self.org, user=self.member).update(role=ADMIN)
        identity_services.set_account_active(self.second_owner().pk, False)  # n'est pas un propriétaire actif non plus
        # Aucun propriétaire actif et en règle : non publique (le compte administrateur ne suffit pas).
        self.assertFalse(self.public())

    def test_revoked_owner_does_not_count(self):
        other = self.second_owner()
        Membership.objects.filter(organization=self.org, user=other).update(status=Membership.STATUS_REVOKED)
        identity_services.set_account_active(self.member.pk, False)
        self.assertFalse(self.public())

    def test_reconciliation_command_agrees(self):
        flags = identity_services.get_seller_context_public_flags([('ORGANIZATION', self.org.pk)])
        self.assertTrue(flags[('ORGANIZATION', self.org.pk)])
        User.objects.filter(pk=self.member.pk).update(is_active=False)  # modification directe, sans événement
        self.assertEqual(Offer.objects.get(pk=self.offer.pk).seller_is_public, True)
        from apps.marketplace import services

        self.assertEqual(services.sync_all_seller_visibility(), 1)
        self.assertFalse(self.public())
