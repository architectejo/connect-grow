"""Classement organique P x E x R x D (CDC 3.5, ADR 0004, L0-08) : marquage des contacts, score
stocké E x R, proximité D appliquée à la lecture, recalcul idempotent et commande horaire."""
import io
import math
import os
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import City, Commune
from apps.identity.models import User
from apps.reviews.models import Review
from apps.visibility.models import RankingSettings

from . import services
from .models import ContactEvent, Favorite, MarketplaceSettings, Offer
from .tests import MarketplaceTestBase

LIST_URL = '/api/marketplace/posts/'


def ids(response):
    data = response.data['results'] if isinstance(response.data, dict) else response.data
    return [row['id'] for row in data]


class ContactCountingTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        self.offer = self.make_offer()

    def test_a_contact_is_counted_and_updates_the_counter_and_the_score_together(self):
        self.assertEqual(self.offer.contacts_count, 0)
        event = services.create_contact_event(offer=self.offer, sender=self.buyer, message='Bonjour')
        self.assertTrue(event.is_counted)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.contacts_count, 1)
        self.assertAlmostEqual(self.offer.visibility_score, 1 + math.log(6), places=3)  # w_contacts = 5

    def test_a_contact_inside_the_window_is_not_counted_again_whatever_the_channel(self):
        services.create_contact_event(offer=self.offer, sender=self.buyer, message='Bonjour')
        self.assertTrue(services.is_countable_contact(self.offer, self.seller, 24))  # autre expéditeur
        self.assertFalse(services.is_countable_contact(self.offer, self.buyer, 24))
        ContactEvent.objects.update(created_at=timezone.now() - timedelta(hours=25))
        self.assertTrue(services.is_countable_contact(self.offer, self.buyer, 24))

    def test_uncounted_contacts_are_excluded_from_the_counter_and_the_dashboard_aggregate(self):
        ContactEvent.objects.create(offer=self.offer, sender=self.buyer, message='Un', is_counted=True)
        ContactEvent.objects.create(
            offer=self.offer, sender=self.buyer, message='Deux', is_counted=False, channel=ContactEvent.CHANNEL_CALL,
        )
        self.assertEqual(services.recount_contacts(self.offer.id), 1)
        rows = services.count_contacts_by_offer(timezone.localdate())
        self.assertEqual(rows, [(self.offer.id, self.seller.id, 1)])

    def test_the_window_comes_from_the_settings(self):
        row = MarketplaceSettings.get_solo()
        row.duplicate_contact_window_hours = 2
        row.save()
        services.create_contact_event(offer=self.offer, sender=self.buyer, message='Bonjour')
        ContactEvent.objects.update(created_at=timezone.now() - timedelta(hours=3))
        event = services.create_contact_event(offer=self.offer, sender=self.buyer, message='Encore')
        self.assertTrue(event.is_counted)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.contacts_count, 2)


class StoredScoreTests(MarketplaceTestBase):
    def test_refresh_recounts_the_sources_and_is_idempotent(self):
        offer = self.make_offer()
        Favorite.objects.create(user=self.buyer, offer=offer)
        ContactEvent.objects.create(offer=offer, sender=self.buyer, message='Bonjour')
        # Compteurs dérivés volontairement faux : la source fait foi.
        Offer.objects.filter(pk=offer.pk).update(likes_count=9, contacts_count=7)
        self.assertEqual(services.refresh_all_scores(), 1)
        offer.refresh_from_db()
        self.assertEqual((offer.likes_count, offer.contacts_count), (1, 1))
        first = offer.visibility_score
        self.assertAlmostEqual(first, 1 + math.log(1 + 3 + 5), places=3)
        services.refresh_all_scores()
        offer.refresh_from_db()
        self.assertAlmostEqual(offer.visibility_score, first, places=4)

    def test_favorites_trigger_a_recalculation(self):
        offer = self.make_offer()
        services.add_favorite(self.buyer, offer)
        offer.refresh_from_db()
        self.assertAlmostEqual(offer.visibility_score, 1 + math.log(4), places=3)
        services.toggle_favorite(self.buyer, offer)
        offer.refresh_from_db()
        self.assertAlmostEqual(offer.visibility_score, 1.0, places=3)

    def test_recency_decays_the_stored_score_through_the_refresh(self):
        offer = self.make_offer()
        Offer.objects.filter(pk=offer.pk).update(created_at=timezone.now() - timedelta(hours=72))
        services.refresh_all_scores()
        offer.refresh_from_db()
        self.assertAlmostEqual(offer.visibility_score, 0.5, places=3)

    def test_ratings_and_reviews_do_not_change_the_score(self):
        offer = self.make_offer()
        twin = self.make_offer(title='Une annonce jumelle du canapé')
        Offer.objects.filter(pk=twin.pk).update(created_at=offer.created_at)
        contact = ContactEvent.objects.create(offer=offer, sender=self.buyer, message='Bonjour')
        ContactEvent.objects.create(offer=twin, sender=self.buyer, message='Bonjour')
        services.refresh_all_scores()
        offer.refresh_from_db()
        before = offer.visibility_score
        Review.objects.create(
            offer_id=offer.id, user=self.buyer, seller_context_type='USER', seller_context_id=self.seller.id,
            contact_event_id=contact.id, contact_channel=contact.channel, contact_recorded_at=contact.created_at,
            offer_rating=5, seller_rating=5, content='Excellent vendeur, très réactif.',
        )
        services.refresh_all_scores()
        Review.objects.filter(offer_id=offer.id).update(offer_rating=1, seller_rating=1)
        services.refresh_all_scores()
        offer.refresh_from_db()
        twin.refresh_from_db()
        self.assertAlmostEqual(offer.visibility_score, before, places=3)
        self.assertAlmostEqual(offer.visibility_score, twin.visibility_score, places=3)

    def test_inactive_offers_are_not_recalculated(self):
        offer = self.make_offer(is_active=False)
        self.assertEqual(services.refresh_all_scores(), 0)
        offer.refresh_from_db()
        self.assertEqual(offer.visibility_score, 0)


class RefreshCommandTests(MarketplaceTestBase):
    def test_command_reports_the_number_of_offers_and_is_replayable(self):
        self.make_offer()
        self.make_offer(title='Une seconde annonce valide')
        for _ in range(2):
            out = io.StringIO()
            call_command('refresh_visibility_scores', stdout=out)
            self.assertIn('2 offres mises à jour.', out.getvalue())
        self.assertTrue(all(score > 0.99 for score in Offer.objects.values_list('visibility_score', flat=True)))

    def test_the_command_is_scheduled_hourly(self):
        path = os.path.join(settings.BASE_DIR, 'cron', 'crontab')
        with open(path, encoding='utf-8') as handle:
            lines = [line for line in handle if 'refresh_visibility_scores' in line]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('15 * * * * '))


class ProximityOrderingTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        self.other_city = City.objects.create(name='Lubumbashi')
        self.same_city_commune = Commune.objects.create(city=self.city, name='Limete')
        self.far_commune = Commune.objects.create(city=self.other_city, name='Kamalondo')
        # Trois offres au score stocké identique : seule la proximité D les départage.
        self.far = self.make_offer(title='Offre lointaine', commune_id=self.far_commune.id)
        self.city_offer = self.make_offer(title='Offre de la ville', commune_id=self.same_city_commune.id)
        self.local = self.make_offer(title='Offre de la commune', commune_id=self.commune.id)
        Offer.objects.update(visibility_score=10.0)

    def listing(self, **params):
        return self.client.get(LIST_URL, params)

    def test_without_reference_the_stored_score_decides_then_date_then_id(self):
        Offer.objects.filter(pk=self.far.pk).update(visibility_score=11.0)
        self.assertEqual(ids(self.listing())[0], str(self.far.id))
        Offer.objects.update(visibility_score=10.0)
        newest_first = [str(o.id) for o in Offer.objects.order_by('-created_at', 'id')]
        self.assertEqual(ids(self.listing()), newest_first)

    def test_near_applies_the_proximity_weights_in_the_sort(self):
        response = self.listing(near=str(self.commune.id))
        self.assertEqual(ids(response), [str(self.local.id), str(self.city_offer.id), str(self.far.id)])

    def test_a_better_distant_offer_can_still_win(self):
        Offer.objects.filter(pk=self.far.pk).update(visibility_score=13.0)  # 13 > 10 x 1,2
        self.assertEqual(ids(self.listing(near=str(self.commune.id)))[0], str(self.far.id))
        Offer.objects.filter(pk=self.far.pk).update(visibility_score=11.5)  # 10 x 1,1 < 11,5 < 10 x 1,2
        order = ids(self.listing(near=str(self.commune.id)))
        self.assertEqual(order, [str(self.local.id), str(self.far.id), str(self.city_offer.id)])

    def test_the_weights_come_from_the_settings(self):
        row = RankingSettings.get_solo()
        row.proximity_same_commune = 1.5
        row.proximity_same_city = 1.5
        row.save()
        Offer.objects.filter(pk=self.far.pk).update(visibility_score=14.0)  # 14 < 10 x 1,5
        self.assertEqual(ids(self.listing(near=str(self.commune.id)))[-1], str(self.far.id))

    def test_the_profile_commune_is_the_fallback_and_near_wins(self):
        User.objects.filter(pk=self.buyer.pk).update(commune_id=self.same_city_commune.id)
        self.client.force_authenticate(User.objects.get(pk=self.buyer.pk))
        self.assertEqual(ids(self.listing())[0], str(self.city_offer.id))
        self.assertEqual(ids(self.listing(near=str(self.commune.id)))[0], str(self.local.id))

    def test_an_invalid_near_is_ignored(self):
        response = self.listing(near='pas-un-uuid')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(ids(response)), 3)

    def test_an_unknown_commune_gives_the_default_weight_to_everyone(self):
        import uuid

        newest_first = [str(o.id) for o in Offer.objects.order_by('-created_at', 'id')]
        self.assertEqual(ids(self.listing(near=str(uuid.uuid4()))), newest_first)

    def test_other_orderings_are_unchanged_by_near(self):
        Offer.objects.filter(pk=self.far.pk).update(price=1)
        self.assertEqual(ids(self.listing(ordering='price', near=str(self.commune.id)))[0], str(self.far.id))

    def test_the_response_does_not_expose_the_proximity(self):
        row = self.listing(near=str(self.commune.id)).data[0]
        self.assertFalse([key for key in row if 'proximity' in key or 'distance' in key])

    def test_pagination_is_exact_with_near(self):
        for index in range(5):
            self.make_offer(title=f'Offre supplémentaire {index}', commune_id=self.far_commune.id)
        Offer.objects.update(visibility_score=10.0)
        Offer.objects.filter(pk=self.local.pk).update(visibility_score=10.5)
        full = ids(self.listing(near=str(self.commune.id)))
        seen = []
        for page in (1, 2, 3):
            response = self.listing(near=str(self.commune.id), page=page, page_size=3)
            self.assertEqual(response.data['count'], len(full))
            seen += ids(response)
        self.assertEqual(seen, full)
        self.assertEqual(len(set(seen)), len(full))

    def test_the_listing_does_not_run_a_query_per_offer(self):
        self.listing(near=str(self.commune.id))  # amorçage des caches
        with CaptureQueriesContext(connection) as small:
            self.listing(near=str(self.commune.id))
        for index in range(6):
            self.make_offer(title=f'Offre en plus {index}', commune_id=self.far_commune.id)
        with CaptureQueriesContext(connection) as big:
            self.listing(near=str(self.commune.id))
        self.assertEqual(len(big), len(small))
