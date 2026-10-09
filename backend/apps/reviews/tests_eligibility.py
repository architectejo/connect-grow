"""L0-10 T3 : éligibilité, délai contact -> avis, codes d'erreur, contact fictif et garde-fous (ADR 0004)."""
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle

from apps.identity.models import User
from apps.marketplace.models import ContactEvent, Offer
from apps.moderation.admin import ReportAdmin
from apps.moderation.models import AuditLog, Report
from apps.platform_core.models import OutboxEvent

from . import services
from .models import Review, ReviewSettings
from .tests import GOOD, REVIEWS_URL, ReviewsTestBase

ELIGIBILITY_URL = REVIEWS_URL + 'eligibility/'
REPORTS_URL = '/api/moderation/reports/'
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'reviews-eligibility'}}
UNKNOWN_ID = '8f0f5a52-3c6e-4a49-9d44-0d8a3d5f1c11'


class EligibilityBase(ReviewsTestBase):
    def set_settings(self, **values):
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(**values)

    def age_contact(self, contact, **delta):
        ContactEvent.objects.filter(pk=contact.pk).update(created_at=timezone.now() - timedelta(**delta))
        contact.refresh_from_db()

    def eligibility(self, offer=None):
        return self.client.get(ELIGIBILITY_URL, {'post': str((offer or self.offer).id)})

    def post_review(self, **extra):
        return self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD, **extra}, format='json')


class EligibilityEndpointTests(EligibilityBase):
    def test_requires_authentication(self):
        response = self.eligibility()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'not_authenticated')

    def test_invalid_or_missing_post_is_a_field_error(self):
        self.client.force_authenticate(self.buyer)
        for query in ({}, {'post': 'pas-un-uuid'}):
            response = self.client.get(ELIGIBILITY_URL, query)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('post', response.data)

    def test_no_contact(self):
        self.client.force_authenticate(self.buyer)
        response = self.eligibility()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data, {'can_review': False, 'reason': 'no_contact', 'available_at': None, 'review_id': None},
        )
        refused = self.post_review()
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'not_eligible'))

    def test_own_offer(self):
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.eligibility().data['reason'], 'own_offer')
        refused = self.post_review()
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'own_offer'))

    def test_eligible_with_delay_zero(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(
            self.eligibility().data, {'can_review': True, 'reason': None, 'available_at': None, 'review_id': None},
        )

    def test_too_early_gives_available_at_and_post_refuses(self):
        self.set_settings(delay_after_contact_hours=24)
        contact = self.make_contact()
        self.client.force_authenticate(self.buyer)
        response = self.eligibility()
        self.assertEqual(response.data['reason'], 'too_early')
        self.assertFalse(response.data['can_review'])
        expected = contact.created_at + timedelta(hours=24)
        self.assertEqual(response.json()['available_at'], expected.isoformat().replace('+00:00', 'Z'))
        refused = self.post_review()
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(refused.data['code'], 'review_too_early')
        self.assertTrue(refused.data['detail'].startswith("Vous pourrez donner votre avis dans "))
        self.assertIn("jour", refused.data['detail'])
        self.assertFalse(Review.objects.exists())

    def test_delay_boundary_is_inclusive(self):
        self.set_settings(delay_after_contact_hours=24)
        contact = self.make_contact()
        available_at = contact.created_at + timedelta(hours=24)
        self.client.force_authenticate(self.buyer)
        with mock.patch.object(services.timezone, 'now', return_value=available_at - timedelta(seconds=1)):
            self.assertEqual(self.eligibility().data['reason'], 'too_early')
        with mock.patch.object(services.timezone, 'now', return_value=available_at):
            self.assertTrue(self.eligibility().data['can_review'])

    def test_delay_message_is_in_french_whatever_the_remaining_time(self):
        self.assertEqual(services._format_delay(timedelta(seconds=1)), "1 minute")
        self.assertEqual(services._format_delay(timedelta(minutes=125)), "2 heures et 5 minutes")
        self.assertEqual(services._format_delay(timedelta(hours=24)), "1 jour")
        self.assertEqual(services._format_delay(timedelta(hours=49, minutes=30)), "2 jours et 1 heure")

    def test_delay_is_a_setting(self):
        contact = self.make_contact()
        self.age_contact(contact, hours=25)
        self.set_settings(delay_after_contact_hours=24)
        self.client.force_authenticate(self.buyer)
        self.assertTrue(self.eligibility().data['can_review'])
        self.set_settings(delay_after_contact_hours=48)
        self.assertEqual(self.eligibility().data['reason'], 'too_early')
        self.assertEqual(self.post_review().data['code'], 'review_too_early')
        self.set_settings(delay_after_contact_hours=0)
        self.assertEqual(self.post_review().status_code, status.HTTP_201_CREATED)

    def test_every_channel_opens_the_right_after_the_delay(self):
        self.set_settings(delay_after_contact_hours=24)
        for index, channel in enumerate((ContactEvent.CHANNEL_MESSAGE, 'CALL', 'WHATSAPP')):
            user = User.objects.create_user(email=f'c{index}@example.com', password='x', full_name=f'Visiteur {index}')
            offer = self.make_offer(self.seller, f'Annonce numéro {index} à noter')
            contact = self.make_contact(offer, user, channel=channel)
            self.client.force_authenticate(user)
            self.assertEqual(self.eligibility(offer).data['reason'], 'too_early', channel)
            self.age_contact(contact, hours=30)
            self.assertTrue(self.eligibility(offer).data['can_review'], channel)
            response = self.client.post(REVIEWS_URL, {'post': str(offer.id), **GOOD}, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, channel)
            self.assertEqual(Review.objects.get(pk=response.data['id']).contact_channel, channel)

    def test_delay_counts_from_the_oldest_contact(self):
        self.set_settings(delay_after_contact_hours=24)
        first = self.make_contact()
        self.age_contact(first, hours=30)
        self.make_contact()  # un second contact récent ne repousse pas le droit
        self.client.force_authenticate(self.buyer)
        self.assertTrue(self.eligibility().data['can_review'])

    def test_already_reviewed_returns_the_review_id(self):
        review = self.make_review()
        self.client.force_authenticate(self.buyer)
        response = self.eligibility()
        self.assertEqual(response.data['reason'], 'already_reviewed')
        self.assertEqual(response.json()['review_id'], str(review.id))
        refused = self.post_review()
        self.assertEqual((refused.status_code, refused.data['code']), (409, 'already_reviewed'))

    def test_unavailable_offer_is_known_to_those_who_contacted_it(self):
        self.make_contact()
        Offer.objects.filter(pk=self.offer.pk).update(is_hidden_by_moderation=True, is_active=False)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.eligibility().data['reason'], 'offer_unavailable')
        refused = self.post_review()
        self.assertEqual((refused.status_code, refused.data['code']), (409, 'offer_unavailable'))

    def test_inaccessible_offers_answer_the_same_404_as_unknown_ones(self):
        self.client.force_authenticate(self.other)
        unknown = self.client.get(ELIGIBILITY_URL, {'post': UNKNOWN_ID})
        self.assertEqual((unknown.status_code, unknown.data['code']), (404, 'offer_not_found'))
        for fields in (
            {'is_deleted': True}, {'is_hidden_by_moderation': True, 'is_active': False}, {'is_active': False},
        ):
            Offer.objects.filter(pk=self.offer.pk).update(**fields)
            hidden = self.eligibility()
            self.assertEqual(hidden.status_code, 404, fields)
            self.assertEqual(hidden.data, unknown.data, fields)

    def test_sold_or_paused_offer_stays_reviewable_for_the_one_who_contacted(self):
        self.make_contact()
        Offer.objects.filter(pk=self.offer.pk).update(is_active=False)
        self.client.force_authenticate(self.buyer)
        self.assertTrue(self.eligibility().data['can_review'])
        self.assertEqual(self.post_review().status_code, status.HTTP_201_CREATED)

    def test_daily_limit_is_a_429_at_creation(self):
        self.set_settings(daily_review_limit=1)
        self.client.force_authenticate(self.buyer)
        self.make_contact()
        self.assertEqual(self.post_review().status_code, 201)
        second = self.make_offer(self.seller, 'Une seconde annonce à noter')
        self.make_contact(second)
        refused = self.client.post(REVIEWS_URL, {'post': str(second.id), **GOOD}, format='json')
        self.assertEqual((refused.status_code, refused.data['code']), (429, 'daily_limit'))

    def test_validation_errors_are_reported_before_eligibility(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD, 'offer_rating': 9}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('offer_rating', response.data)

    @override_settings(CACHES=LOCMEM)
    def test_eligibility_is_throttled(self):
        cache.clear()
        self.client.force_authenticate(self.buyer)
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'review_eligibility': '2/hour'}):
            self.assertEqual(self.eligibility().status_code, 200)
            self.assertEqual(self.eligibility().status_code, 200)
            third = self.eligibility()
        self.assertEqual(third.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(third.data['code'], 'throttled')

    def test_query_count_does_not_depend_on_the_data(self):
        self.client.force_authenticate(self.buyer)
        self.eligibility()  # amorce les réglages à ligne unique

        def count(offer):
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.eligibility(offer).status_code, 200)
            return len(ctx.captured_queries)

        no_contact = count(self.offer)
        self.make_contact()
        with_contact = count(self.offer)
        self.make_review()
        reviewed = count(self.offer)
        self.assertLessEqual(max(no_contact, with_contact, reviewed), 8)
        for index in range(3):  # des avis et des contacts de plus ne changent rien
            other = User.objects.create_user(email=f'n{index}@example.com', password='x', full_name=f'N {index}')
            self.make_review(user=other)
        self.assertEqual(count(self.offer), reviewed)


class ContactFictitiousReportTests(EligibilityBase):
    def setUp(self):
        super().setUp()
        call_command('setup_roles', verbosity=0)
        self.review = self.make_review()
        self.moderator = User.objects.create_user(
            email='mod@example.com', password='x', full_name='Modo', is_staff=True,
        )
        self.moderator.groups.add(Group.objects.get(name='Modérateur'))

    def report(self, user, target_id=None, target_type='REVIEW', reason='CONTACT_FICTIF'):
        self.client.force_authenticate(user)
        return self.client.post(REPORTS_URL, {
            'target_type': target_type, 'object_id': str(target_id or self.review.id),
            'reason': reason, 'description': "Cette personne ne m'a jamais contacté.",
        }, format='json')

    def test_seller_reports_a_fictitious_contact(self):
        response = self.report(self.seller)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        report = Report.objects.get()
        self.assertEqual((report.reason, report.status, report.target_type), ('CONTACT_FICTIF', 'EN_ATTENTE', 'review'))
        self.assertEqual((report.reporter, report.target_id), (self.seller, self.review.id))

    def test_report_is_audited_and_waits_in_the_queue_without_hiding(self):
        self.report(self.seller)
        report = Report.objects.get()
        entry = AuditLog.objects.get(action='CONTACT_FICTIF_REPORTED')
        self.assertEqual((entry.actor, entry.target_id, entry.target_type), (self.seller, report.id, 'report'))
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_hidden)
        # La file de modération (et son compteur) montre le signalement.
        self.client.force_authenticate(self.moderator)
        queue = self.client.get(REPORTS_URL, {'status': 'EN_ATTENTE'})
        self.assertEqual([r['reason'] for r in queue.data], ['CONTACT_FICTIF'])
        self.assertEqual(self.client.get('/api/moderation/dashboard/').data['pending_reports_count'], 1)
        # L'avis est gelé pour son auteur le temps de la décision, mais reste visible et compté.
        self.client.force_authenticate(self.buyer)
        gone = self.client.delete(f'{REVIEWS_URL}{self.review.id}/')
        self.assertEqual((gone.status_code, gone.data['code']), (403, 'review_locked'))
        edit = self.client.patch(
            f'{REVIEWS_URL}{self.review.id}/', {'content': 'Un texte modifié assez long.'}, format='json',
        )
        self.assertEqual(edit.status_code, 200)
        listed = self.client.get(REVIEWS_URL, {'post': str(self.offer.id)})
        self.assertEqual([r['id'] for r in listed.data], [str(self.review.id)])

    def test_only_the_concerned_seller_may_use_the_reason(self):
        for user in (self.buyer, self.other, self.moderator):
            response = self.report(user)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, user.email)
            self.assertEqual(response.data['code'], 'not_seller')
        other_seller = User.objects.create_user(email='s2@example.com', password='x', full_name='Autre vendeur')
        self.make_offer(other_seller, 'Une autre annonce à vendre')
        self.assertEqual(self.report(other_seller).data['code'], 'not_seller')
        self.assertFalse(Report.objects.exists())
        self.assertFalse(AuditLog.objects.filter(action='CONTACT_FICTIF_REPORTED').exists())

    def test_reason_is_refused_on_something_else_than_a_review(self):
        response = self.report(self.seller, target_id=self.offer.id, target_type='POST')
        self.assertEqual((response.status_code, response.data['code']), (400, 'invalid_reason'))
        self.assertEqual(self.report(self.buyer, target_id=self.seller.id, target_type='USER').status_code, 400)

    def test_unknown_review_is_a_field_error_and_anonymous_is_refused(self):
        self.assertEqual(self.report(self.seller, target_id=UNKNOWN_ID).status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(REPORTS_URL, {}, format='json').status_code, 401)

    def test_no_second_open_report_for_the_same_review(self):
        self.assertEqual(self.report(self.seller).status_code, 201)
        again = self.report(self.seller)
        self.assertEqual((again.status_code, again.data['code']), (409, 'duplicate_report'))
        self.assertEqual(Report.objects.count(), 1)

    def test_other_reasons_on_a_review_are_unchanged(self):
        self.assertEqual(self.report(self.other, reason='SPAM').status_code, 201)
        self.assertEqual(self.report(self.seller, reason='HARCELEMENT').status_code, 201)

    def decide(self, action):
        report = Report.objects.get(reason='CONTACT_FICTIF')
        self.client.force_authenticate(self.moderator)
        return self.client.post(f'{REPORTS_URL}{report.id}/{action}/', {'notes': 'Vérifié.'}, format='json')

    def test_validated_report_hides_the_review_and_blocks_a_new_one(self):
        other_buyer = User.objects.create_user(email='b2@example.com', password='x', full_name='Acheteur Deux')
        second = self.make_review(user=other_buyer)
        self.report(self.seller)
        self.assertEqual(self.decide('resolve').status_code, 200)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_hidden)
        self.assertTrue(AuditLog.objects.filter(
            action='REVIEW_HIDDEN', target_id=self.review.id, actor=self.moderator).exists())
        self.assertTrue(AuditLog.objects.filter(action='REPORT_RESOLVED').exists())
        self.client.force_authenticate(None)
        listed = self.client.get(REVIEWS_URL, {'post': str(self.offer.id)})
        self.assertEqual([r['id'] for r in listed.data], [str(second.id)])
        # L'auteur ne peut ni redonner son avis, ni effacer celui qui est écarté.
        self.client.force_authenticate(self.buyer)
        verdict = self.eligibility()
        self.assertEqual((verdict.data['reason'], verdict.json()['review_id']), ('contact_rejected', str(self.review.id)))
        refused = self.post_review()
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'contact_rejected'))
        gone = self.client.delete(f'{REVIEWS_URL}{self.review.id}/')
        self.assertEqual((gone.status_code, gone.data['code']), (403, 'review_locked'))

    def test_rejected_report_keeps_the_review(self):
        self.report(self.seller)
        self.assertEqual(self.decide('reject').status_code, 200)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_hidden)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.eligibility().data['reason'], 'already_reviewed')

    def test_resolving_from_the_admin_has_the_same_effect(self):
        self.report(self.seller)
        report = Report.objects.get()
        report.status = Report.STATUS_TRAITE
        request = RequestFactory().post('/admin/')
        request.user = self.moderator
        ReportAdmin(Report, admin_site).save_model(request, report, mock.Mock(changed_data=['status']), True)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_hidden)
        self.assertTrue(AuditLog.objects.filter(action='REPORT_STATUS_CHANGED').exists())


class CrossedReviewsSettingsTests(EligibilityBase):
    def test_threshold_comes_from_the_settings_and_does_not_block(self):
        self.set_settings(crossed_reviews_threshold=2)
        buyer_offer = self.make_offer(self.buyer, 'Offre de acheteur à noter')
        self.make_contact()
        self.make_contact(buyer_offer, self.seller)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.post_review().status_code, 201)
        self.assertFalse(OutboxEvent.objects.filter(event_type='reviews.crossed_reviews_detected').exists())
        self.client.force_authenticate(self.seller)
        response = self.client.post(REVIEWS_URL, {'post': str(buyer_offer.id), **GOOD}, format='json')
        self.assertEqual(response.status_code, 201)
        event = OutboxEvent.objects.get(event_type='reviews.crossed_reviews_detected')
        self.assertEqual((event.payload['reviews_count'], event.version), (2, 2))
        self.assertTrue(Review.objects.filter(pk=response.data['id'], is_hidden=False).exists())
