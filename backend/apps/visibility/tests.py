import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.identity.models import User

from . import services
from .models import DailyVisibilityCounter, OfferUniqueView, RankingSettings


class VisibilityTestBase(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.offer_id = uuid.uuid4()
        self.today = timezone.now().date()

    def counter(self, days_ago, views, offer_id=None, contacts=0):
        return DailyVisibilityCounter.objects.create(
            offer_id=offer_id or self.offer_id, seller=self.seller, views=views, contacts=contacts,
            date=self.today - timedelta(days=days_ago),
        )


class RecordViewTests(VisibilityTestBase):
    def test_a_viewer_counts_once_per_day(self):
        key = services.build_viewer_key(None, 'abc')
        self.assertTrue(services.record_view(offer_id=self.offer_id, seller_id=self.seller.id, viewer_key=key))
        self.assertFalse(services.record_view(offer_id=self.offer_id, seller_id=self.seller.id, viewer_key=key))
        self.assertEqual(DailyVisibilityCounter.objects.get(offer_id=self.offer_id).views, 1)

    def test_same_viewer_counts_again_the_next_day(self):
        key = services.build_viewer_key(None, 'abc')
        services.record_view(
            offer_id=self.offer_id, seller_id=self.seller.id, viewer_key=key, day=self.today - timedelta(days=1),
        )
        self.assertTrue(services.record_view(offer_id=self.offer_id, seller_id=self.seller.id, viewer_key=key))
        self.assertEqual(DailyVisibilityCounter.objects.filter(offer_id=self.offer_id).count(), 2)

    def test_viewer_keys(self):
        self.assertEqual(services.build_viewer_key(self.seller, 'x'), f'user:{self.seller.pk}')
        anon = services.build_viewer_key(None, 'y' * 1000)
        self.assertTrue(anon.startswith('anon:'))
        self.assertLessEqual(len(anon), 64)
        self.assertNotEqual(anon, services.build_viewer_key(None, 'z'))

    def test_unique_constraints_exist_in_database(self):
        OfferUniqueView.objects.create(offer_id=self.offer_id, date=self.today, viewer_key='k')
        with self.assertRaises(IntegrityError), transaction.atomic():
            OfferUniqueView.objects.create(offer_id=self.offer_id, date=self.today, viewer_key='k')
        self.counter(0, 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.counter(0, 1)


class ComputeScoreTests(VisibilityTestBase):
    def test_score_grows_with_engagement_and_decays_with_age(self):
        now = timezone.now()
        base = dict(likes=0, comments=0, shares=0, trust_score=3.5, now=now)
        fresh = services.compute_score(views=0, created_at=now, **base)
        engaged = services.compute_score(views=50, created_at=now, **base)
        old = services.compute_score(views=0, created_at=now - timedelta(hours=72), **base)
        self.assertGreater(engaged, fresh)
        self.assertAlmostEqual(old, fresh / 2, places=6)  # demi-vie de 72 h par défaut

    def test_trust_factor_is_bounded_by_settings(self):
        now = timezone.now()
        row = RankingSettings.get_solo()
        score = services.compute_score(views=0, likes=0, comments=0, shares=0, created_at=now, trust_score=0, now=now)
        self.assertAlmostEqual(score, row.trust_factor_min)
        row.trust_factor_max = 1.0
        row.save()
        score = services.compute_score(views=0, likes=0, comments=0, shares=0, created_at=now, trust_score=5, now=now)
        self.assertAlmostEqual(score, 1.0)

    def test_settings_row_is_a_single_configurable_row(self):
        first = RankingSettings.get_solo()
        self.assertEqual(RankingSettings.get_solo().pk, first.pk)
        self.assertEqual(RankingSettings.objects.count(), 1)


class TrendingTests(VisibilityTestBase):
    def test_not_trending_without_history(self):
        self.counter(0, 50)
        self.assertEqual(services.trending_offer_ids([self.offer_id]), set())

    def test_trending_on_spike_and_threshold(self):
        for days in range(1, 6):
            self.counter(days, 1)
        self.counter(0, 10)
        self.assertEqual(services.trending_offer_ids([self.offer_id, None]), {self.offer_id})

    def test_not_trending_below_five_views_or_below_double_the_average(self):
        calm, small = uuid.uuid4(), uuid.uuid4()
        for days in range(1, 4):
            self.counter(days, 10, offer_id=calm)
            self.counter(days, 1, offer_id=small)
        self.counter(0, 15, offer_id=calm)   # moins du double de la moyenne
        self.counter(0, 4, offer_id=small)   # fort mais sous le plancher de 5 vues
        self.assertEqual(services.trending_offer_ids([calm, small]), set())

    def test_batch_uses_one_query(self):
        with self.assertNumQueries(1):
            services.trending_offer_ids([uuid.uuid4() for _ in range(20)])


class SellerStatsTests(VisibilityTestBase):
    def test_totals_history_and_isolation(self):
        self.counter(0, 4, contacts=2)
        self.counter(2, 6)
        self.counter(40, 100)  # hors fenêtre de 30 jours : compté au total, pas dans l'historique
        stranger = User.objects.create_user(email='x@example.com', password='x', full_name='X')
        DailyVisibilityCounter.objects.create(offer_id=uuid.uuid4(), seller=stranger, date=self.today, views=77)

        stats = services.get_seller_stats(self.seller.id)
        self.assertEqual((stats.total_views, stats.today_views, stats.contacts_count), (110, 4, 2))
        self.assertEqual([p.views for p in stats.history], [6, 4])

    def test_offer_history_and_contacts_aggregate(self):
        self.counter(1, 3)
        self.assertEqual([p.views for p in services.get_offer_history(self.offer_id)], [3])
        services.set_daily_contacts(self.today, [(self.offer_id, self.seller.id, 5)])
        services.set_daily_contacts(self.today, [(self.offer_id, self.seller.id, 6)])
        self.assertEqual(DailyVisibilityCounter.objects.get(offer_id=self.offer_id, date=self.today).contacts, 6)

    def test_delete_offer_data(self):
        self.counter(0, 1)
        OfferUniqueView.objects.create(offer_id=self.offer_id, date=self.today, viewer_key='k')
        services.delete_offer_data([self.offer_id])
        self.assertFalse(DailyVisibilityCounter.objects.exists() or OfferUniqueView.objects.exists())
