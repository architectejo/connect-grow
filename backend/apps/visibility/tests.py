import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.common.factories import owner_kwargs, counter_owner_kwargs
from apps.identity.models import User

from . import services
from .models import DailyVisibilityCounter, OfferUniqueView, RankingSettings


class VisibilityTestBase(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.offer_id = uuid.uuid4()
        self.today = timezone.localdate()

    def counter(self, days_ago, views, offer_id=None, contacts=0):
        return DailyVisibilityCounter.objects.create(
            offer_id=offer_id or self.offer_id, **counter_owner_kwargs(self.seller), views=views, contacts=contacts,
            date=self.today - timedelta(days=days_ago),
        )


class RecordViewTests(VisibilityTestBase):
    def test_a_viewer_counts_once_per_day(self):
        key = services.build_viewer_key(None, 'abc')
        self.assertTrue(services.record_view(offer_id=self.offer_id, seller_context_type='USER', seller_context_id=self.seller.id, viewer_key=key))
        self.assertFalse(services.record_view(offer_id=self.offer_id, seller_context_type='USER', seller_context_id=self.seller.id, viewer_key=key))
        self.assertEqual(DailyVisibilityCounter.objects.get(offer_id=self.offer_id).views, 1)

    def test_same_viewer_counts_again_the_next_day(self):
        key = services.build_viewer_key(None, 'abc')
        services.record_view(
            offer_id=self.offer_id, seller_context_type='USER', seller_context_id=self.seller.id, viewer_key=key, day=self.today - timedelta(days=1),
        )
        self.assertTrue(services.record_view(offer_id=self.offer_id, seller_context_type='USER', seller_context_id=self.seller.id, viewer_key=key))
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
    def score(self, **overrides):
        now = overrides.pop('now', timezone.now())
        values = dict(views=0, favorites=0, contacts=0, shares=0, created_at=now, now=now)
        values.update(overrides)
        return services.compute_score(**values)

    def test_score_grows_with_engagement_and_decays_with_age(self):
        now = timezone.now()
        fresh = self.score(now=now)
        engaged = self.score(now=now, views=50)
        old = self.score(now=now, created_at=now - timedelta(hours=72))
        self.assertGreater(engaged, fresh)
        self.assertAlmostEqual(old, fresh / 2, places=6)  # demi-vie de 72 h par défaut

    def test_engagement_is_one_without_interaction_and_recency_is_half_at_the_half_life(self):
        now = timezone.now()
        self.assertAlmostEqual(self.score(now=now), 1.0)
        self.assertAlmostEqual(self.score(now=now, created_at=now - timedelta(hours=72)), 0.5)
        row = RankingSettings.get_solo()
        row.recency_half_life_hours = 24
        row.save()
        self.assertAlmostEqual(self.score(now=now, created_at=now - timedelta(hours=72)), 0.125)

    def test_weights_come_from_the_settings(self):
        import math

        now = timezone.now()
        row = RankingSettings.get_solo()
        self.assertEqual(
            (row.weight_views, row.weight_favorites, row.weight_contacts, row.weight_shares), (1, 3, 5, 8),
        )
        self.assertAlmostEqual(self.score(now=now, views=1), 1 + math.log(2))
        self.assertAlmostEqual(self.score(now=now, favorites=1), 1 + math.log(4))
        self.assertAlmostEqual(self.score(now=now, contacts=1), 1 + math.log(6))
        self.assertAlmostEqual(self.score(now=now, shares=1), 1 + math.log(9))
        row.weight_contacts = 10
        row.save()
        self.assertAlmostEqual(self.score(now=now, contacts=1), 1 + math.log(11))

    def test_the_score_has_no_trust_input(self):
        import inspect

        parameters = set(inspect.signature(services.compute_score).parameters)
        self.assertEqual(parameters, {'views', 'favorites', 'contacts', 'shares', 'created_at', 'settings_row', 'now'})

    def test_settings_row_is_a_single_configurable_row(self):
        first = RankingSettings.get_solo()
        self.assertEqual(RankingSettings.get_solo().pk, first.pk)
        self.assertEqual(RankingSettings.objects.count(), 1)

    def test_proximity_weights_come_from_the_settings(self):
        self.assertEqual(services.get_proximity_weights(), (1.2, 1.1, 1.0))
        row = RankingSettings.get_solo()
        row.proximity_same_commune = 1.5
        row.save()
        self.assertEqual(services.get_proximity_weights(), (1.5, 1.1, 1.0))


class RankingSettingsValidationTests(VisibilityTestBase):
    def test_defaults_are_valid(self):
        RankingSettings().full_clean()

    def test_invalid_values_are_refused(self):
        from django.core.exceptions import ValidationError

        cases = [
            ({'weight_views': -1}, 'weight_views'), ({'weight_favorites': -0.5}, 'weight_favorites'),
            ({'weight_contacts': -2}, 'weight_contacts'), ({'weight_shares': -1}, 'weight_shares'),
            ({'recency_half_life_hours': 0}, 'recency_half_life_hours'),
            ({'recency_half_life_hours': -5}, 'recency_half_life_hours'),
            ({'proximity_default': 0.9}, 'proximity_default'), ({'proximity_same_city': 0.5}, 'proximity_same_city'),
            ({'proximity_same_commune': 1.05, 'proximity_same_city': 1.1}, 'proximity_same_commune'),
            ({'proximity_same_city': 1.0, 'proximity_default': 1.05, 'proximity_same_commune': 1.2},
             'proximity_same_commune'),
        ]
        for values, field in cases:
            with self.assertRaises(ValidationError, msg=values) as caught:
                RankingSettings(**values).full_clean()
            self.assertIn(field, caught.exception.message_dict, values)

    def test_zero_weights_are_allowed(self):
        RankingSettings(weight_views=0, weight_favorites=0, weight_contacts=0, weight_shares=0).full_clean()


class RankingSettingsAdminTests(VisibilityTestBase):
    def save_through_admin(self, **changes):
        from unittest import mock

        from django.contrib.admin.sites import site as admin_site
        from django.db import transaction
        from django.test import RequestFactory

        from apps.identity.models import User

        from .admin import RankingSettingsAdmin

        admin = User.objects.create_user(
            email='ranking-admin@example.com', password='x', full_name='Admin', is_staff=True,
        )
        request = RequestFactory().post('/admin/')
        request.user = admin
        row = RankingSettings.get_solo()
        initial = {name: getattr(row, name) for name in changes}
        for name, value in changes.items():
            setattr(row, name, value)
        form = mock.Mock(changed_data=list(changes), initial=initial)
        with transaction.atomic():
            RankingSettingsAdmin(RankingSettings, admin_site).save_model(request, row, form, True)
        return admin, row

    def test_change_is_audited_and_publishes_an_event(self):
        from apps.moderation.models import AuditLog
        from apps.platform_core.models import OutboxEvent

        admin, row = self.save_through_admin(weight_contacts=7.0)
        entry = AuditLog.objects.get(action='SETTINGS_CHANGED', actor=admin)
        self.assertEqual(entry.target_id, row.pk)
        self.assertIn('weight_contacts : 5.0 -> 7.0', entry.details)
        event = OutboxEvent.objects.get(event_type='visibility.ranking_settings_changed')
        self.assertEqual(event.payload, {'changed': ['weight_contacts']})

    def test_the_event_triggers_a_recalculation_of_the_scores(self):
        from apps.catalog.models import Category, City, Commune
        from apps.identity.models import User
        from apps.marketplace.models import ContactEvent, Offer
        from apps.marketplace.tests import make_test_image
        from apps.platform_core.testing import dispatch_outbox_now

        city = City.objects.create(name='Kinshasa')
        commune = Commune.objects.create(city=city, name='Gombe')
        category = Category.objects.create(name='Électronique', slug='electronique')
        seller = User.objects.create_user(email='ranking-seller@example.com', password='x', full_name='V')
        offer = Offer.objects.create(
            **owner_kwargs(seller), category_id=category.id, commune_id=commune.id, title='Un joli canapé à vendre',
            description='Description suffisamment longue pour le CDC.', price=100, main_image=make_test_image(),
        )
        for index in range(2):
            sender = User.objects.create_user(email=f'ranking-buyer{index}@example.com', password='x', full_name='A')
            ContactEvent.objects.create(offer=offer, sender=sender, message='Bonjour')
        self.assertEqual(offer.visibility_score, 0)
        self.save_through_admin(weight_contacts=7.0)
        dispatch_outbox_now()
        offer.refresh_from_db()
        self.assertGreater(offer.visibility_score, 1.0)  # E > 1 avec 2 contacts

    def test_admin_does_not_allow_a_second_row_or_deletion(self):
        from django.contrib.admin.sites import site as admin_site

        from .admin import RankingSettingsAdmin

        model_admin = RankingSettingsAdmin(RankingSettings, admin_site)
        RankingSettings.get_solo()
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None))


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
        DailyVisibilityCounter.objects.create(offer_id=uuid.uuid4(), **counter_owner_kwargs(stranger), date=self.today, views=77)

        stats = services.get_seller_stats('USER', self.seller.id)
        self.assertEqual((stats.total_views, stats.today_views, stats.contacts_count), (110, 4, 2))
        self.assertEqual([p.views for p in stats.history], [6, 4])

    def test_offer_history_and_contacts_aggregate(self):
        self.counter(1, 3)
        self.assertEqual([p.views for p in services.get_offer_history(self.offer_id)], [3])
        services.set_daily_contacts(self.today, [(self.offer_id, 'USER', self.seller.id, 5)])
        services.set_daily_contacts(self.today, [(self.offer_id, 'USER', self.seller.id, 6)])
        self.assertEqual(DailyVisibilityCounter.objects.get(offer_id=self.offer_id, date=self.today).contacts, 6)

    def test_delete_offer_data(self):
        self.counter(0, 1)
        OfferUniqueView.objects.create(offer_id=self.offer_id, date=self.today, viewer_key='k')
        services.delete_offer_data([self.offer_id])
        self.assertFalse(DailyVisibilityCounter.objects.exists() or OfferUniqueView.objects.exists())


class DayBoundaryTests(TestCase):
    """L0-23 : « aujourd'hui » est le jour du fuseau de l'application (Africa/Kinshasa, UTC+1), pas le jour UTC."""

    def freeze(self, *args):
        from datetime import datetime, timezone as dt_timezone
        from unittest import mock
        return mock.patch('django.utils.timezone.now', return_value=datetime(*args, tzinfo=dt_timezone.utc))

    def check(self, frozen):
        seller = User.objects.create_user(email='s@example.com', password='x', full_name='V')
        offer_id = uuid.uuid4()
        with frozen:
            today = timezone.localdate()
            DailyVisibilityCounter.objects.create(offer_id=offer_id, **counter_owner_kwargs(seller), date=today, views=10)
            for days in range(1, 6):
                DailyVisibilityCounter.objects.create(
                    offer_id=offer_id, **counter_owner_kwargs(seller), date=today - timedelta(days=days), views=1,
                )
            stats = services.get_seller_stats('USER', seller.id)
            self.assertEqual(stats.today_views, 10)
            self.assertEqual(services.trending_offer_ids([offer_id]), {offer_id})
            return today

    def test_23h30_utc_is_already_next_day_in_kinshasa(self):
        # 10/10 23:30 UTC = 11/10 00:30 à Kinshasa
        today = self.check(self.freeze(2026, 10, 10, 23, 30))
        self.assertEqual(today.isoformat(), '2026-10-11')

    def test_midday_utc_same_day(self):
        today = self.check(self.freeze(2026, 10, 10, 12, 0))
        self.assertEqual(today.isoformat(), '2026-10-10')
