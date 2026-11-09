"""Avis par contexte vendeur (ADR 0006, T6 / L0-09f1) : réponse par capacité `review.reply`, calcul par lot de
`is_post_owner` (requêtes constantes), `review_posted` v3 (destinataires résolus à la livraison), journal d'audit,
non-fuite."""
import json

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from apps.identity import services as identity_services
from apps.identity.models import Membership, Organization, ProviderProfile, User
from apps.moderation.models import AuditLog, Sanction
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now

from . import services
from .models import Review
from .tests import GOOD, REVIEWS_URL, ReviewsTestBase

OWNER, ADMIN, EDITOR, ANALYST = 'OWNER', 'ADMIN', 'EDITOR', 'ANALYST'
SENTINEL_NAME = 'Sentinelle Membre'
SENTINEL_EMAIL = 'sentinelle.membre@example.com'


class ContextReviewBase(ReviewsTestBase):
    def setUp(self):
        super().setUp()
        self.org = Organization.objects.create(name='Atelier X', org_type='ENTREPRISE')
        self.members = {}
        for role in (OWNER, ADMIN, EDITOR, ANALYST):
            user = User.objects.create_user(email=f'{role.lower()}@example.com', password='x', full_name=f'Membre {role}')
            Membership.objects.create(organization=self.org, user=user, role=role)
            self.members[role] = user

    def org_offer(self, org=None, title='Offre de l\'atelier'):
        org = org or self.org
        return self.make_offer(
            None, title=title, seller_context_type='ORGANIZATION', seller_context_id=org.pk,
            created_by=self.members[OWNER],
        )

    def org_review(self, offer=None, user=None, org=None):
        offer = offer or self.org_offer(org)
        return self.make_review(
            offer=offer, user=user, seller_context_type='ORGANIZATION', seller_context_id=(org or self.org).pk,
        )

    def reply(self, user, review, text='Merci pour votre avis !'):
        self.client.force_authenticate(user)
        return self.client.post(f'{REVIEWS_URL}{review.id}/reply/', {'reply_content': text})


class ReplyByRoleTests(ContextReviewBase):
    def test_owner_admin_and_editor_reply_the_analyst_does_not(self):
        for role, allowed in ((OWNER, True), (ADMIN, True), (EDITOR, True), (ANALYST, False)):
            with self.subTest(role=role):
                review = self.org_review(user=User.objects.create_user(
                    email=f'buyer-{role}@example.com', password='x', full_name='Acheteur',
                ))
                response = self.reply(self.members[role], review)
                if allowed:
                    self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                    self.assertTrue(response.data['is_post_owner'])
                else:
                    self.assertEqual((response.status_code, response.data['code']), (403, 'DENY_PERMISSION'))
                    review.refresh_from_db()
                    self.assertFalse(review.reply_content)

    def test_former_member_stranger_and_author_are_refused_as_not_seller(self):
        review = self.org_review()
        Membership.objects.filter(user=self.members[EDITOR]).update(status='REVOKED')
        for user in (self.members[EDITOR], self.other, self.buyer, self.seller):
            with self.subTest(user=user.email):
                response = self.reply(user, review)
                self.assertEqual((response.status_code, response.data['code']), (403, 'not_seller'))
        review.refresh_from_db()
        self.assertFalse(review.reply_content)

    def test_sanctioned_member_cannot_reply(self):
        review = self.org_review()
        Sanction.objects.create(user=self.members[ADMIN], sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        response = self.reply(self.members[ADMIN], review)
        self.assertEqual((response.status_code, response.data['code']), (403, 'DENY_SECURITY'))
        self.assertFalse(services.can_reply(review, self.members[ADMIN]))
        self.assertTrue(services.can_reply(review, self.members[OWNER]))

    def test_deactivated_account_cannot_reply(self):
        review = self.org_review()
        User.objects.filter(pk=self.members[EDITOR].pk).update(is_active=False)
        self.assertFalse(services.can_reply(review, self.members[EDITOR]))
        self.assertEqual(self.reply(self.members[EDITOR], review).status_code, 403)

    def test_suspended_and_archived_organizations_refuse_the_reply(self):
        review = self.org_review()
        for org_status, code in (('SUSPENDED', 'DENY_SECURITY'), ('ARCHIVED', 'DENY_OBJECT_STATE')):
            Organization.objects.filter(pk=self.org.pk).update(status=org_status)
            with self.subTest(status=org_status):
                response = self.reply(self.members[OWNER], review)
                self.assertEqual((response.status_code, response.data['code']), (403, code))

    def test_the_header_is_ignored_authorization_follows_the_review_owner(self):
        """Un éditeur de A et analyste de B n'agit pas sur un avis de B en présentant l'en-tête de A (IDOR)."""
        other_org = Organization.objects.create(name='Atelier B', org_type='BOUTIQUE')
        Membership.objects.create(organization=other_org, user=self.members[EDITOR], role=ANALYST)
        review = self.org_review(org=other_org)
        self.client.force_authenticate(self.members[EDITOR])
        response = self.client.post(
            f'{REVIEWS_URL}{review.id}/reply/', {'reply_content': 'Réponse'},
            HTTP_X_CONTEXT=f'ORGANIZATION:{self.org.pk}',
        )
        self.assertEqual((response.status_code, response.data['code']), (403, 'DENY_PERMISSION'))

    def test_provider_owner_replies_and_an_archived_profile_does_not(self):
        profile = ProviderProfile.objects.create(user=self.seller, display_name='Marie couture')
        offer = self.make_offer(
            None, seller_context_type='PROVIDER', seller_context_id=profile.pk, created_by=self.seller,
        )
        review = self.make_review(offer=offer, seller_context_type='PROVIDER', seller_context_id=profile.pk)
        self.assertEqual(self.reply(self.seller, review).status_code, 200)
        other = self.make_review(
            offer=offer, user=self.other, seller_context_type='PROVIDER', seller_context_id=profile.pk,
        )
        ProviderProfile.objects.filter(pk=profile.pk).update(status='ARCHIVED')
        response = self.reply(self.seller, other)
        self.assertEqual((response.status_code, response.data['code']), (403, 'DENY_OBJECT_STATE'))

    def test_reply_is_audited_under_the_seller_context_without_personal_data(self):
        review = self.org_review()
        self.assertEqual(self.reply(self.members[EDITOR], review).status_code, 200)
        entry = AuditLog.objects.get(action='REVIEW_REPLIED')
        self.assertEqual(entry.actor, self.members[EDITOR])
        self.assertEqual((entry.context_type, entry.context_id), ('ORGANIZATION', self.org.pk))
        self.assertNotIn('@', entry.details)
        self.assertNotIn('Membre', entry.details)

    def test_a_refused_reply_is_not_audited_and_publishes_nothing(self):
        review = self.org_review()
        self.assertEqual(self.reply(self.members[ANALYST], review).status_code, 403)
        self.assertFalse(AuditLog.objects.filter(action='REVIEW_REPLIED').exists())
        self.assertFalse(OutboxEvent.objects.filter(event_type='reviews.review_replied').exists())

    def test_service_rechecks_authorization_in_the_write_transaction(self):
        """Révocation survenue entre le contrôle de la vue et l'écriture : le service refuse."""
        review = self.org_review()
        Membership.objects.filter(user=self.members[EDITOR]).update(status='REVOKED')
        with self.assertRaises(services.ReviewError) as caught:
            services.reply_to_review(review, self.members[EDITOR], 'Trop tard')
        self.assertEqual(caught.exception.code, 'not_seller')
        review.refresh_from_db()
        self.assertFalse(review.reply_content)

    def test_the_reply_never_shows_the_member_but_the_organization_is_named_to_the_buyer(self):
        review = self.org_review()
        self.members[EDITOR].full_name = SENTINEL_NAME
        self.members[EDITOR].save()
        response = self.reply(self.members[EDITOR], review)
        self.assertNotIn(SENTINEL_NAME, json.dumps(response.data, default=str))
        event = OutboxEvent.objects.get(event_type='reviews.review_replied')
        self.assertNotIn(SENTINEL_NAME, json.dumps(event.payload))
        dispatch_outbox_now()
        notification = Notification.objects.get(user=review.user)
        self.assertIn('Atelier X', notification.content)
        self.assertNotIn(SENTINEL_NAME, notification.title + notification.content)
        self.assertIsNone(notification.context_type)  # l'acheteur est en contexte personnel


class IsPostOwnerBatchTests(ContextReviewBase):
    def listing_queries(self, user):
        self.client.force_authenticate(user)
        self.client.get(REVIEWS_URL)  # échauffement (réglages en cache, etc.)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(REVIEWS_URL)
        self.assertEqual(response.status_code, 200)
        return len(captured), response.data

    def make_reviews(self, count, org=None):
        for index in range(count):
            buyer = User.objects.create_user(email=f'b{index}-{User.objects.count()}@example.com', password='x', full_name='B')
            self.org_review(user=buyer, org=org)

    def test_is_post_owner_by_role(self):
        self.make_reviews(2)
        expected = {OWNER: True, ADMIN: True, EDITOR: True, ANALYST: False}
        for role, allowed in expected.items():
            with self.subTest(role=role):
                _, data = self.listing_queries(self.members[role])
                self.assertEqual({item['is_post_owner'] for item in data}, {allowed})
        self.client.force_authenticate(None)
        self.assertEqual({item['is_post_owner'] for item in self.client.get(REVIEWS_URL).data}, {False})

    def test_query_count_does_not_depend_on_the_number_of_reviews(self):
        self.make_reviews(2)
        few, _ = self.listing_queries(self.members[EDITOR])
        self.make_reviews(10)
        # Avis de plusieurs organisations : le nombre de contextes distincts non plus ne coûte rien.
        for index in range(3):
            self.make_reviews(1, org=Organization.objects.create(name=f'Autre {index}', org_type='ONG'))
        many, data = self.listing_queries(self.members[EDITOR])
        self.assertEqual(len(data), 15)
        self.assertEqual(few, many)

    def test_only_the_contexts_where_the_user_may_reply_are_flagged(self):
        other_org = Organization.objects.create(name='Atelier B', org_type='BOUTIQUE')
        Membership.objects.create(organization=other_org, user=self.members[EDITOR], role=ANALYST)
        mine = self.org_review()
        foreign = self.org_review(org=other_org, user=self.other)
        _, data = self.listing_queries(self.members[EDITOR])
        flags = {item['id']: item['is_post_owner'] for item in data}
        self.assertEqual(flags, {str(mine.id): True, str(foreign.id): False})

    def test_batch_matches_the_single_decision(self):
        self.org_review()
        for user in list(self.members.values()) + [self.seller, self.buyer, self.other]:
            for review in Review.objects.all():
                with self.subTest(user=user.email):
                    batch = (review.seller_context_type, review.seller_context_id) in services.get_reply_contexts(user)
                    self.assertEqual(batch, services.can_reply(review, user))

    def test_detail_and_batch_exclude_a_sanctioned_member(self):
        review = self.org_review()
        Sanction.objects.create(user=self.members[OWNER], sanction_type='BANNISSEMENT', reason='x')
        self.assertEqual(services.get_reply_contexts(self.members[OWNER]), set())
        self.client.force_authenticate(self.members[OWNER])
        self.assertFalse(self.client.get(f'{REVIEWS_URL}{review.id}/').data['is_post_owner'])


class ReviewPostedRecipientsTests(ContextReviewBase):
    def post_review(self, offer, buyer=None):
        buyer = buyer or self.buyer
        self.make_contact(offer=offer, user=buyer)
        self.client.force_authenticate(buyer)
        response = self.client.post(REVIEWS_URL, {'post': str(offer.id), **GOOD})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response

    def notified(self):
        return {n.user_id: n for n in Notification.objects.filter(notification_type='COMMENT')}

    def test_organization_notifies_the_members_who_can_reply_with_the_context(self):
        offer = self.org_offer()
        self.post_review(offer)
        self.assertFalse(Notification.objects.exists())  # rien avant la livraison
        dispatch_outbox_now()
        notified = self.notified()
        self.assertEqual(set(notified), {self.members[OWNER].pk, self.members[ADMIN].pk, self.members[EDITOR].pk})
        for notification in notified.values():
            self.assertEqual((notification.context_type, notification.context_id), ('ORGANIZATION', self.org.pk))
            self.assertEqual(notification.link, f'/post/{offer.id}')

    def test_recipients_are_resolved_at_delivery_not_at_publication(self):
        offer = self.org_offer()
        self.post_review(offer)
        Membership.objects.filter(user=self.members[EDITOR]).update(status='REVOKED')  # parti entre-temps
        late = User.objects.create_user(email='late@example.com', password='x', full_name='Tardif')
        Membership.objects.create(organization=self.org, user=late, role=EDITOR)  # arrivé entre-temps
        dispatch_outbox_now()
        self.assertEqual(
            set(self.notified()), {self.members[OWNER].pk, self.members[ADMIN].pk, late.pk},
        )

    def test_organization_without_any_eligible_member_notifies_nobody_without_failing(self):
        offer = self.org_offer()
        self.post_review(offer)
        User.objects.filter(pk__in=[self.members[OWNER].pk, self.members[ADMIN].pk, self.members[EDITOR].pk]).update(
            is_active=False,
        )
        dispatch_outbox_now()
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(OutboxEvent.objects.get(event_type='reviews.review_posted').status, 'done')

    def test_organization_with_only_an_analyst_notifies_nobody(self):
        Membership.objects.filter(user__in=[
            self.members[OWNER], self.members[ADMIN], self.members[EDITOR],
        ]).update(status='REVOKED')
        self.post_review(self.org_offer())
        dispatch_outbox_now()
        self.assertFalse(Notification.objects.exists())

    def test_suspended_organization_does_not_notify(self):
        self.post_review(self.org_offer())
        Organization.objects.filter(pk=self.org.pk).update(status='SUSPENDED')
        dispatch_outbox_now()
        self.assertFalse(Notification.objects.exists())

    def test_provider_context_notifies_the_holder_with_the_provider_context(self):
        profile = ProviderProfile.objects.create(user=self.seller, display_name='Marie couture')
        offer = self.make_offer(None, seller_context_type='PROVIDER', seller_context_id=profile.pk, created_by=self.seller)
        self.post_review(offer)
        dispatch_outbox_now()
        notification = Notification.objects.get()
        self.assertEqual(notification.user, self.seller)
        self.assertEqual((notification.context_type, notification.context_id), ('PROVIDER', profile.pk))

    def test_personal_context_notification_has_a_null_context(self):
        self.post_review(self.offer)
        dispatch_outbox_now()
        notification = Notification.objects.get()
        self.assertEqual(notification.user, self.seller)
        self.assertEqual((notification.context_type, notification.context_id), (None, None))

    def test_payload_names_the_context_and_carries_no_recipient_nor_personal_data(self):
        offer = self.org_offer()
        self.buyer.full_name = SENTINEL_NAME
        self.buyer.email = SENTINEL_EMAIL
        self.buyer.save()
        response = self.post_review(offer)
        event = OutboxEvent.objects.get(event_type='reviews.review_posted')
        self.assertEqual(event.version, 3)
        self.assertEqual(event.payload, {
            'review_id': response.data['id'], 'author_id': str(self.buyer.pk), 'offer_id': str(offer.id),
            'offer_title': offer.title, 'seller_context_type': 'ORGANIZATION', 'seller_context_id': str(self.org.pk),
        })
        serialized = json.dumps(event.payload)
        for secret in (SENTINEL_NAME, SENTINEL_EMAIL, 'Membre'):
            self.assertNotIn(secret, serialized)

    def test_notification_shows_the_public_name_of_the_author_only(self):
        self.buyer.full_name = 'Marie Kabongo'
        self.buyer.email = SENTINEL_EMAIL
        self.buyer.save()
        self.post_review(self.org_offer())
        dispatch_outbox_now()
        for notification in Notification.objects.all():
            self.assertIn('Marie K.', notification.content)
            self.assertNotIn('Kabongo', notification.content)
            self.assertNotIn(SENTINEL_EMAIL, notification.content + notification.title)

    def test_former_member_gets_nothing_and_a_revoked_member_loses_the_old_notification(self):
        offer = self.org_offer()
        self.post_review(offer)
        dispatch_outbox_now()
        editor = self.members[EDITOR]
        self.assertEqual(Notification.objects.filter(user=editor, context_type='ORGANIZATION').count(), 1)
        identity_services.revoke_member(self.members[OWNER], self.org.pk, editor.pk)
        dispatch_outbox_now()
        self.assertFalse(Notification.objects.filter(user=editor, context_type='ORGANIZATION').exists())
        self.client.force_authenticate(editor)
        for item in self.client.get('/api/v1/interactions/notifications/').data:
            self.assertIsNone(item['context'])
