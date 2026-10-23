"""Vues et partages : compteurs de `visibility`, totaux de l'offre recalculés par événements (ADR 0003, L0-16)."""
from datetime import timedelta

from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.platform_core.models import OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now
from apps.visibility import services as visibility_services
from apps.visibility.models import DailyVisibilityCounter, OfferUniqueView

from . import services
from .models import Offer
from .tests import MarketplaceTestBase, make_test_image


class ViewEventTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        self.offer = self.make_offer()

    def view(self, key):
        return services.register_view(self.offer, key)

    def totals(self):
        self.offer.refresh_from_db()
        return self.offer.views_count, self.offer.shares_count

    def test_a_new_view_publishes_an_event_and_a_repeat_does_not(self):
        self.assertTrue(self.view('user:a'))
        self.assertFalse(self.view('user:a'))
        events = OutboxEvent.objects.filter(event_type='visibility.offer_viewed')
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().payload, {'offer_id': str(self.offer.id), 'date': timezone.localdate().isoformat()})
        self.assertEqual(self.totals(), (0, 0))  # le total attend la diffusion

    def test_dispatch_recomputes_totals_and_score_from_the_daily_counters(self):
        for key in ('user:a', 'user:b', 'user:c'):
            self.view(key)
        dispatch_outbox_now()
        self.assertEqual(self.totals(), (3, 0))
        self.offer.refresh_from_db()
        self.assertGreater(self.offer.visibility_score, 0)
        self.assertEqual(visibility_services.total_views(self.offer.id), 3)

    def test_replaying_the_synchronisation_is_idempotent(self):
        self.view('user:a')
        dispatch_outbox_now()
        services.sync_offer_engagement(self.offer.id)
        services.sync_offer_engagement(self.offer.id)
        self.assertEqual(self.totals(), (1, 0))

    def test_synchronisation_of_a_deleted_offer_is_harmless(self):
        self.view('user:a')
        services.delete_offers(Offer.objects.filter(pk=self.offer.pk))
        dispatch_outbox_now()
        self.assertFalse(services.sync_offer_engagement(self.offer.id))

    def test_shares_counted_once_per_user_and_day_and_survive_the_purge_of_unique_views(self):
        actor = f'user:{self.buyer.pk}'
        self.assertTrue(visibility_services.record_share(offer_id=self.offer.id, seller_context_type='USER', seller_context_id=self.seller.id, actor_key=actor))
        self.assertFalse(visibility_services.record_share(offer_id=self.offer.id, seller_context_type='USER', seller_context_id=self.seller.id, actor_key=actor))
        dispatch_outbox_now()
        OfferUniqueView.objects.update(date=timezone.localdate() - timedelta(days=30))
        visibility_services.purge_unique_views()
        self.assertFalse(OfferUniqueView.objects.exists())
        services.sync_offer_engagement(self.offer.id)  # le recalcul à la source ne perd rien
        self.assertEqual(self.totals(), (0, 1))
        self.assertEqual(DailyVisibilityCounter.objects.get().shares, 1)

    def test_the_daily_counters_are_the_only_source_of_the_totals(self):
        # Une valeur divergente (ancien incrément, saisie manuelle) est écrasée : pas de max() hybride.
        self.view('user:a')
        self.view('user:b')
        Offer.objects.filter(pk=self.offer.pk).update(views_count=50, shares_count=7)
        services.sync_offer_engagement(self.offer.id)
        self.assertEqual(self.totals(), (2, 0))
        DailyVisibilityCounter.objects.all().delete()
        services.sync_offer_engagement(self.offer.id)
        self.assertEqual(self.totals(), (0, 0))

    @override_settings(OUTBOX_INLINE_DISPATCH=True)
    def test_share_value_with_immediate_diffusion_inside_a_test_transaction(self):
        self.client.force_authenticate(self.buyer)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.post(reverse('offer-share', args=[self.offer.id]))
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(response.data, {'shares_count': 0})  # « au mieux » : la diffusion suit la réponse
        self.assertEqual(self.totals(), (0, 1))  # puis le total est exact
        self.assertEqual(OutboxEvent.objects.get().status, 'done')

    def test_share_endpoint_keeps_its_json_contract_and_is_best_effort_before_diffusion(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('offer-share', args=[self.offer.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.data), ['shares_count'])
        self.assertEqual(response.data['shares_count'], 0)  # sans diffusion immédiate : total précédent
        dispatch_outbox_now()
        other_day = timezone.localdate() - timedelta(days=1)
        OfferUniqueView.objects.update(date=other_day)
        self.assertEqual(self.client.post(reverse('offer-share', args=[self.offer.id])).data['shares_count'], 1)


class InlineDispatchContractTests(TransactionTestCase):
    """Vraies validations de transaction : la diffusion immédiate rend le total à jour."""

    def setUp(self):
        from apps.catalog.models import Category, City, Commune
        from apps.identity.models import User

        city = City.objects.create(name='Kinshasa')
        commune = Commune.objects.create(city=city, name='Gombe')
        category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')
        self.offer = Offer.objects.create(
            seller=self.seller, category_id=category.id, commune_id=commune.id, title='Un joli canapé à vendre',
            description='Description suffisamment longue pour le CDC.', price=100, main_image=make_test_image(),
        )

    @override_settings(OUTBOX_INLINE_DISPATCH=True)
    def test_share_response_carries_the_updated_total_when_diffusion_is_immediate(self):
        client = APIClient()
        client.force_authenticate(self.buyer)
        url = reverse('offer-share', args=[self.offer.id])
        self.assertEqual(client.post(url).data, {'shares_count': 1})
        self.assertEqual(client.post(url).data, {'shares_count': 1})
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.shares_count, 1)

    @override_settings(OUTBOX_INLINE_DISPATCH=True)
    def test_detail_view_response_counts_the_visit_when_diffusion_is_immediate(self):
        client = APIClient()
        client.force_authenticate(self.buyer)
        response = client.get(reverse('offer-detail', args=[self.offer.id]))
        self.assertEqual(response.data['views_count'], 1)

    def test_repeated_and_replayed_views_are_counted_exactly(self):
        keys = [f'user:{n}' for n in range(8)]
        for key in keys + keys[:3]:  # trois visiteurs reviennent le même jour
            visibility_services.record_view(offer_id=self.offer.id, seller_context_type='USER', seller_context_id=self.seller.id, viewer_key=key)
        dispatch_outbox_now()
        dispatch_outbox_now()  # rejeu
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.views_count, 8)
        self.assertEqual(visibility_services.total_views(self.offer.id), 8)
