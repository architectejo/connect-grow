"""Corrections après relecture : bornes des réglages, verrouillage des écritures, suppression et
modification encadrées, réponse uniforme, auteur non identifiable, journal de l'admin."""
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import RequestFactory
from django.utils import timezone
from rest_framework import status

from apps.identity.models import User
from apps.marketplace import services as marketplace_services
from apps.marketplace.models import MarketplaceSettings
from apps.moderation.models import AuditLog, Report
from apps.visibility.models import RankingSettings

from . import services
from .admin import ReviewAdmin
from .models import DeletedReviewMark, Review, ReviewSettings
from .tests import GOOD, REVIEWS_URL, ReviewsTestBase


class SettingsBoundsTests(ReviewsTestBase):
    def assert_bound(self, model, field, ok, too_high, **extra):
        model(**{field: ok}, **extra).full_clean()
        with self.assertRaises(ValidationError, msg=f'{field}={too_high}') as caught:
            model(**{field: too_high}, **extra).full_clean()
        self.assertIn(field, caught.exception.message_dict)

    def test_review_settings_have_a_ceiling(self):
        for field, ceiling in (
            ('min_reviews_to_display', 100), ('daily_review_limit', 100), ('edit_window_hours', 8760),
            ('delay_after_contact_hours', 168), ('crossed_reviews_window_days', 365),
            ('crossed_reviews_threshold', 50),
        ):
            self.assert_bound(ReviewSettings, field, ceiling, ceiling + 1)

    def test_marketplace_duplicate_window_has_a_ceiling(self):
        self.assert_bound(MarketplaceSettings, 'duplicate_contact_window_hours', 8760, 8761)

    def test_ranking_settings_have_ceilings_in_validators_and_clean(self):
        for field in ('weight_views', 'weight_favorites', 'weight_contacts', 'weight_shares'):
            self.assert_bound(RankingSettings, field, 1000.0, 1000.1)
        self.assert_bound(RankingSettings, 'recency_half_life_hours', 8760.0, 8761.0)
        for field in ('proximity_same_commune', 'proximity_same_city', 'proximity_default'):
            self.assert_bound(RankingSettings, field, 5.0, 5.1,
                              **{k: 5.0 for k in ('proximity_same_commune', 'proximity_same_city', 'proximity_default')
                                 if k != field})
        # `clean()` seul (sans les validateurs de champ) refuse aussi un plafond dépassé.
        with self.assertRaises(ValidationError) as caught:
            RankingSettings(weight_contacts=5000).clean()
        self.assertIn('weight_contacts', caught.exception.message_dict)
        with self.assertRaises(ValidationError):
            RankingSettings(recency_half_life_hours=10 ** 9).clean()
        with self.assertRaises(ValidationError):
            RankingSettings(proximity_same_commune=50).clean()

    def test_review_and_contact_still_work_at_every_ceiling(self):
        ReviewSettings.objects.update_or_create(pk=ReviewSettings.SINGLETON_ID, defaults=dict(
            min_reviews_to_display=100, daily_review_limit=100, edit_window_hours=8760,
            delay_after_contact_hours=168, crossed_reviews_window_days=365, crossed_reviews_threshold=50,
        ))
        MarketplaceSettings.objects.update_or_create(
            pk=MarketplaceSettings.SINGLETON_ID, defaults={'duplicate_contact_window_hours': 8760},
        )
        RankingSettings.objects.update_or_create(pk=RankingSettings.SINGLETON_ID, defaults=dict(
            weight_views=1000, weight_favorites=1000, weight_contacts=1000, weight_shares=1000,
            recency_half_life_hours=8760, proximity_same_commune=5, proximity_same_city=5, proximity_default=5,
        ))
        contact = marketplace_services.create_contact_event(offer=self.offer, sender=self.buyer, message='Bonjour')
        type(contact).objects.filter(pk=contact.pk).update(created_at=timezone.now() - timedelta(hours=200))
        self.assertEqual(marketplace_services.refresh_all_scores(), 1)
        self.client.force_authenticate(self.buyer)
        response = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        review = Review.objects.get()
        self.assertTrue(review.can_still_be_edited())
        patched = self.client.patch(f'{REVIEWS_URL}{review.id}/', {'offer_rating': 2})
        self.assertEqual(patched.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.delete(f'{REVIEWS_URL}{review.id}/').status_code, 204)
        again = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD})
        self.assertEqual(again.data['code'], 'review_recently_deleted')  # sans OverflowError


class StaleStateTests(ReviewsTestBase):
    """Les contrôles portent sur la ligne relue sous verrou, pas sur la copie obtenue plus tôt."""

    def test_update_with_a_stale_copy_is_refused_after_hiding(self):
        stale = self.make_review()
        Review.objects.filter(pk=stale.pk).update(is_hidden=True)
        with self.assertRaises(services.ReviewError) as caught:
            services.update_review(stale, {'content': 'Modification sur une copie périmée.'})
        self.assertEqual(caught.exception.code, 'review_locked')
        self.assertNotEqual(Review.objects.get(pk=stale.pk).content, 'Modification sur une copie périmée.')

    def test_delete_with_a_stale_copy_is_refused_after_a_report(self):
        stale = self.make_review()
        Report.objects.create(target_type='review', target_id=stale.id, reporter=self.other, reason=Report.REASON_AUTRE)
        with self.assertRaises(services.ReviewError) as caught:
            services.delete_review(stale, self.buyer)
        self.assertEqual(caught.exception.code, 'review_locked')
        self.assertTrue(Review.objects.filter(pk=stale.pk).exists())

    def test_update_and_delete_with_a_stale_copy_are_refused_after_the_reply(self):
        stale = self.make_review()
        Review.objects.filter(pk=stale.pk).update(reply_content='Merci !', reply_at=timezone.now())
        for call in (
            lambda: services.update_review(stale, {'content': 'Modification après la réponse.'}),
            lambda: services.delete_review(stale, self.buyer),
        ):
            with self.assertRaises(services.ReviewError) as caught:
                call()
            self.assertEqual(caught.exception.code, 'review_locked_after_reply')

    def test_a_vanished_review_gives_not_found(self):
        stale = self.make_review()
        Review.objects.filter(pk=stale.pk).delete()
        with self.assertRaises(services.ReviewError) as caught:
            services.update_review(stale, {'content': 'Avis déjà supprimé ailleurs.'})
        self.assertEqual((caught.exception.code, caught.exception.status_code), ('not_found', 404))

    def test_writes_lock_the_row_inside_a_transaction(self):
        review = self.make_review()
        with mock.patch.object(Review.objects.__class__, 'select_for_update', autospec=True,
                               side_effect=Review.objects.__class__.select_for_update) as locked:
            services.update_review(review, {'offer_rating': 1})
            services.delete_review(review, self.buyer)
        self.assertGreaterEqual(locked.call_count, 2)  # mise à jour et suppression (puis rapprochement du drapeau)

    def test_reconcile_works_standalone_and_inside_a_transaction(self):
        review = self.make_review()
        services.reconcile_seller_flag(self.buyer.pk, 'USER', self.seller.pk)
        with transaction.atomic():
            services.reconcile_seller_flag(self.buyer.pk, 'USER', self.seller.pk)
        review.refresh_from_db()
        self.assertTrue(review.counts_for_seller)


class DeletionAndLockTests(ReviewsTestBase):
    def detail(self, review):
        return f'{REVIEWS_URL}{review.id}/'

    def test_deletion_is_audited(self):
        review = self.make_review()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.delete(self.detail(review)).status_code, 204)
        entry = AuditLog.objects.get(action='REVIEW_DELETED')
        self.assertEqual((entry.actor, entry.target_id, entry.target_type), (self.buyer, review.id, 'review'))
        self.assertIn(str(self.offer.id), entry.details)

    def test_recreating_after_deletion_is_blocked_for_the_edit_window_only(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        first = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD})
        self.client.delete(f"{REVIEWS_URL}{first.data['id']}/")
        blocked = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD})
        self.assertEqual((blocked.status_code, blocked.data['code']), (409, 'review_recently_deleted'))
        self.assertFalse(Review.objects.exists())
        DeletedReviewMark.objects.update(deleted_at=timezone.now() - timedelta(hours=49))
        self.assertEqual(self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD}).status_code, 201)

    def test_deleting_twice_keeps_a_single_mark_per_author_and_offer(self):
        self.make_contact()
        self.client.force_authenticate(self.buyer)
        for _ in range(2):
            DeletedReviewMark.objects.update(deleted_at=timezone.now() - timedelta(hours=100))
            created = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD})
            self.assertEqual(created.status_code, 201)
            self.client.delete(f"{REVIEWS_URL}{created.data['id']}/")
        self.assertEqual(DeletedReviewMark.objects.count(), 1)

    def test_replied_review_cannot_be_deleted_or_edited_by_its_author(self):
        review = self.make_review()
        self.client.force_authenticate(self.seller)
        self.client.post(f'{self.detail(review)}reply/', {'reply_content': 'Merci pour votre avis.'})
        self.client.force_authenticate(self.buyer)
        for response in (
            self.client.patch(self.detail(review), {'content': 'Je change mon avis après la réponse.'}),
            self.client.delete(self.detail(review)),
        ):
            self.assertEqual((response.status_code, response.data['code']), (403, 'review_locked_after_reply'))
        self.assertTrue(Review.objects.filter(pk=review.pk).exists())
        self.assertFalse(self.client.get(self.detail(review)).data['can_edit'])


class AuthorPrivacyTests(ReviewsTestBase):
    def test_author_id_is_never_public_and_is_mine_is_for_the_author_only(self):
        self.make_review()
        for viewer in (None, self.seller, self.other, self.buyer):
            self.client.force_authenticate(viewer)
            item = self.client.get(REVIEWS_URL).data[0]
            self.assertNotIn('user_id', item)
            self.assertNotIn(str(self.buyer.id), str(item))
            self.assertEqual(item['is_mine'], viewer == self.buyer)

    def test_uniform_refusal_does_not_tell_offers_apart(self):
        self.client.force_authenticate(self.other)
        hidden = self.make_offer(self.seller, 'Une annonce masquée par la modération')
        marketplace_services.hide_by_moderation(hidden.id)
        trashed = self.make_offer(self.seller, 'Une annonce en corbeille ici')
        trashed.is_deleted = True
        trashed.save()
        bodies = set()
        for offer_id in (hidden.id, trashed.id, '00000000-0000-0000-0000-000000000009'):
            response = self.client.post(REVIEWS_URL, {'post': str(offer_id), **GOOD})
            bodies.add((response.status_code, response.data['code'], response.data['detail']))
        self.assertEqual(bodies, {(404, 'offer_not_found', 'Annonce introuvable.')})
        public = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD})  # offre publique : visible de tous
        self.assertEqual((public.status_code, public.data['code']), (403, 'not_eligible'))


class AdminCorrectionsTests(ReviewsTestBase):
    def make_admin(self):
        return User.objects.create_user(
            email='admin2@example.com', password='x', full_name='Admin', is_staff=True, is_superuser=True,
        )

    def test_identity_fields_are_read_only_even_for_a_superuser(self):
        request = RequestFactory().get('/admin/')
        request.user = self.make_admin()
        readonly = set(ReviewAdmin(Review, admin_site).get_readonly_fields(request, self.make_review()))
        self.assertTrue({'user', 'offer_id', 'seller_context_id', 'contact_event_id'} <= readonly)

    def test_update_is_audited_with_old_and_new_values_and_no_created_label(self):
        admin = self.make_admin()
        request = RequestFactory().post('/admin/')
        request.user = admin
        review = self.make_review()
        review.offer_rating = 1
        form = mock.Mock(changed_data=['offer_rating'], initial={'offer_rating': 4})
        ReviewAdmin(Review, admin_site).save_model(request, review, form, True)
        entry = AuditLog.objects.get(action='REVIEW_ADMIN_UPDATED')
        self.assertIn('offer_rating : 4 -> 1', entry.details)
        self.assertFalse(AuditLog.objects.filter(action='REVIEW_ADMIN_CREATED').exists())

    def test_admin_writes_run_in_a_transaction(self):
        request = RequestFactory().post('/admin/')
        request.user = self.make_admin()
        review = self.make_review()
        model_admin = ReviewAdmin(Review, admin_site)
        with mock.patch.object(services, 'reconcile_seller_flag', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                model_admin.delete_queryset(request, Review.objects.filter(pk=review.pk))
        # La suppression et son audit sont annulés ensemble.
        self.assertTrue(Review.objects.filter(pk=review.pk).exists())
        self.assertFalse(AuditLog.objects.filter(action='REVIEW_ADMIN_DELETED').exists())
