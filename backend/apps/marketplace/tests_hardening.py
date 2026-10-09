"""Durcissement R2 : limites de débit, masquage de modération, disponibilité, audit, requêtes, dates."""
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle

from apps.identity.models import User
from apps.moderation.models import AuditLog, Sanction
from apps.visibility.models import OfferUniqueView, VisibilitySettings

from . import services
from .admin import OfferAdmin
from .models import ContactEvent, ExchangeProposal, Favorite, Offer
from .tests import MarketplaceTestBase

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'marketplace-throttles'}}


def rate(scope, value):
    return mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {scope: value})


@override_settings(CACHES=LOCMEM)
class WriteThrottleTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client.force_authenticate(self.buyer)

    def assert_limited(self, first, second):
        self.assertNotEqual(first.status_code, status.HTTP_429_TOO_MANY_REQUESTS, first.data)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('Retry-After', second)

    def test_contact_is_limited_per_user(self):
        offers = [self.make_offer(title=f'Annonce numéro {i} à vendre') for i in range(2)]
        with rate('contact', '1/hour'):
            responses = [self.client.post(reverse('contact-list'), {'post': str(o.id), 'message': 'Bonjour'}) for o in offers]
        self.assert_limited(*responses)
        # Un autre utilisateur a son propre quota.
        other = User.objects.create_user(email='other@example.com', password='x', full_name='Autre')
        self.client.force_authenticate(other)
        with rate('contact', '1/hour'):
            ok = self.client.post(reverse('contact-list'), {'post': str(offers[0].id), 'message': 'Bonjour'})
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED)

    def test_exchange_share_favorite_and_upload_are_limited(self):
        offers = [self.make_offer(title=f'Annonce numéro {i} à vendre') for i in range(2)]
        with rate('exchange', '1/hour'):
            self.assert_limited(*[
                self.client.post(reverse('exchange-list'), {'post': str(o.id), 'message': 'Troc ?'}) for o in offers
            ])
        with rate('share', '1/hour'):
            self.assert_limited(*[self.client.post(reverse('offer-share', args=[o.id])) for o in offers])
        with rate('favorite', '1/hour'):
            self.assert_limited(*[self.client.post(reverse('offer-favorite', args=[o.id])) for o in offers])
        self.client.force_authenticate(self.seller)
        with rate('offer_upload', '1/hour'):
            self.assert_limited(*[
                self.client.post(reverse('offer-list'), self.offer_payload(title=f'Un titre correct {i}')) for i in range(2)
            ])

    def test_anonymous_offer_views_are_limited_per_ip_but_not_authenticated_ones(self):
        offer = self.make_offer()
        self.client.force_authenticate(None)
        url = reverse('offer-detail', args=[offer.id])
        with rate('offer_view_anon', '2/hour'):
            codes = [self.client.get(url, REMOTE_ADDR='10.9.0.1').status_code for _ in range(3)]
            other_ip = self.client.get(url, REMOTE_ADDR='10.9.0.2').status_code
            self.client.force_authenticate(self.buyer)
            logged_in = [self.client.get(url, REMOTE_ADDR='10.9.0.1').status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 429])
        self.assertEqual(other_ip, 200)
        self.assertEqual(logged_in, [200] * 4)


class DeduplicationTests(MarketplaceTestBase):
    def test_share_counts_once_per_user_offer_and_day(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        first = self.client.post(reverse('offer-share', args=[offer.id]))
        second = self.client.post(reverse('offer-share', args=[offer.id]))
        self.assertEqual((first.data['shares_count'], second.data['shares_count']), (1, 1))
        other = User.objects.create_user(email='other@example.com', password='x', full_name='Autre')
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(reverse('offer-share', args=[offer.id])).data['shares_count'], 2)
        # Le lendemain, le même utilisateur peut de nouveau partager.
        OfferUniqueView.objects.update(date=timezone.localdate() - timedelta(days=1))
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.post(reverse('offer-share', args=[offer.id])).data['shares_count'], 3)

    def test_one_contact_per_offer_and_sender_per_24_hours(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        payload = {'post': str(offer.id), 'message': 'Bonjour'}
        self.assertEqual(self.client.post(reverse('contact-list'), payload).status_code, 201)
        self.assertEqual(self.client.post(reverse('contact-list'), payload).status_code, 400)
        ContactEvent.objects.update(created_at=timezone.now() - timedelta(hours=25))
        self.assertEqual(self.client.post(reverse('contact-list'), payload).status_code, 201)
        self.assertEqual(ContactEvent.objects.count(), 2)


class ModerationHidingTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(email='admin@example.com', password='x', full_name='Admin', is_staff=True)

    def sanction(self, offer):
        sanction = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_MASQUAGE_ANNONCE, reason='Produit interdit.',
            related_offer_id=offer.id, issued_by=self.admin,
        )
        sanction.apply()
        return sanction

    def test_hidden_offer_is_offline_and_the_seller_cannot_bring_it_back(self):
        offer = self.make_offer()
        self.sanction(offer)
        offer.refresh_from_db()
        self.assertTrue(offer.is_hidden_by_moderation)
        self.assertFalse(offer.is_active)

        self.client.force_authenticate(self.seller)
        for name in ('unpause', 'renew'):
            response = self.client.post(reverse(f'offer-{name}', args=[offer.id]))
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, name)
            self.assertIn('modération', response.data['error'])
        offer.refresh_from_db()
        self.assertFalse(offer.is_active)
        # Même après une pause puis une reprise, l'offre reste hors ligne.
        self.client.post(reverse('offer-pause', args=[offer.id]))
        self.assertEqual(self.client.post(reverse('offer-unpause', args=[offer.id])).status_code, 403)
        # Le vendeur peut encore la marquer vendue ou la mettre à la corbeille.
        self.assertEqual(self.client.post(reverse('offer-mark-sold', args=[offer.id])).status_code, 200)

    def test_lift_reactivates_an_active_offer(self):
        offer = self.make_offer()
        sanction = self.sanction(offer)
        sanction.lift()
        offer.refresh_from_db()
        self.assertFalse(offer.is_hidden_by_moderation)
        self.assertTrue(offer.is_active)

    def test_lift_does_not_reactivate_a_sold_paused_or_expired_offer(self):
        for status_value in (Offer.STATUS_SOLD, Offer.STATUS_PAUSED, Offer.STATUS_EXPIRED):
            offer = self.make_offer(title=f'Annonce {status_value} ici présente')
            sanction = self.sanction(offer)
            Offer.objects.filter(pk=offer.pk).update(status=status_value)
            sanction.lift()
            offer.refresh_from_db()
            self.assertFalse(offer.is_hidden_by_moderation, status_value)
            self.assertFalse(offer.is_active, status_value)

    def test_hidden_offers_are_not_public(self):
        offer = self.make_offer()
        self.sanction(offer)
        self.assertEqual(self.client.get(reverse('offer-list')).data, [])


class AvailabilityTests(MarketplaceTestBase):
    def make_unavailable(self):
        hidden = self.make_offer(title='Annonce masquée présente ici', is_active=False, is_hidden_by_moderation=True)
        paused = self.make_offer(title='Annonce en pause présente', is_active=False, status=Offer.STATUS_PAUSED)
        sold = self.make_offer(title='Annonce vendue présente', is_active=False, status=Offer.STATUS_SOLD)
        trashed = self.make_offer(title='Annonce supprimée présente', is_deleted=True)
        return [hidden, paused, sold, trashed]

    def test_contact_exchange_and_favorite_refuse_unavailable_offers(self):
        self.client.force_authenticate(self.buyer)
        for offer in self.make_unavailable():
            payload = {'post': str(offer.id), 'message': 'Bonjour'}
            self.assertEqual(self.client.post(reverse('contact-list'), payload).status_code, 400, offer.title)
            self.assertEqual(self.client.post(reverse('exchange-list'), payload).status_code, 400, offer.title)
            self.assertEqual(self.client.post(reverse('favorite-list'), {'post_id': str(offer.id)}).status_code, 400)
            self.assertEqual(self.client.post(reverse('offer-favorite', args=[offer.id])).status_code, 404)
        self.assertFalse(ContactEvent.objects.exists() or ExchangeProposal.objects.exists() or Favorite.objects.exists())

    def test_favorites_list_hides_offers_that_went_offline(self):
        offer = self.make_offer()
        Favorite.objects.create(user=self.buyer, offer=offer)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(len(self.client.get(reverse('favorite-list')).data), 1)
        Offer.objects.filter(pk=offer.pk).update(is_active=False)
        self.assertEqual(self.client.get(reverse('favorite-list')).data, [])
        Offer.objects.filter(pk=offer.pk).update(is_active=True, is_deleted=True)
        self.assertEqual(self.client.get(reverse('favorite-list')).data, [])

    def test_favorites_drive_likes_count_and_score(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        self.client.post(reverse('offer-favorite', args=[offer.id]))
        offer.refresh_from_db()
        self.assertEqual(offer.likes_count, 1)
        score = offer.visibility_score
        self.assertGreater(score, 0)
        self.client.post(reverse('offer-favorite', args=[offer.id]))
        offer.refresh_from_db()
        self.assertEqual(offer.likes_count, 0)
        self.assertLess(offer.visibility_score, score)
        # Ajout puis retrait par la collection.
        created = self.client.post(reverse('favorite-list'), {'post_id': str(offer.id)})
        offer.refresh_from_db()
        self.assertEqual(offer.likes_count, 1)
        self.client.delete(reverse('favorite-detail', args=[created.data['id']]))
        offer.refresh_from_db()
        self.assertEqual(offer.likes_count, 0)


class PurgeOfferViewsTests(MarketplaceTestBase):
    def test_purge_uses_the_configurable_retention(self):
        offer = self.make_offer()
        today = timezone.localdate()
        for days in (0, 1, 2, 3, 5):
            OfferUniqueView.objects.create(offer_id=offer.id, date=today - timedelta(days=days), viewer_key=f'k{days}')
        self.assertEqual(VisibilitySettings.get_solo().unique_view_retention_days, 2)
        call_command('purge_offer_views', verbosity=0)
        self.assertEqual(sorted(OfferUniqueView.objects.values_list('viewer_key', flat=True)), ['k0', 'k1', 'k2'])

        row = VisibilitySettings.get_solo()
        row.unique_view_retention_days = 1
        row.save()
        call_command('purge_offer_views', verbosity=0)
        self.assertEqual(sorted(OfferUniqueView.objects.values_list('viewer_key', flat=True)), ['k0', 'k1'])


class AuditTests(MarketplaceTestBase):
    def test_hard_delete_and_destroy_are_audited(self):
        first, second = self.make_offer(), self.make_offer(title='Une deuxième annonce ici')
        self.client.force_authenticate(self.seller)
        self.client.delete(reverse('offer-hard-delete', args=[first.id]))
        self.client.delete(reverse('offer-detail', args=[second.id]))
        entries = AuditLog.objects.filter(action='OFFER_DELETED')
        self.assertEqual(entries.count(), 2)
        self.assertEqual({e.actor_id for e in entries}, {self.seller.id})
        self.assertEqual({e.target_id for e in entries}, {first.id, second.id})

    def test_admin_save_and_delete_are_audited_and_clean_visibility_data(self):
        from apps.visibility.models import DailyVisibilityCounter

        admin = User.objects.create_user(email='admin@example.com', password='x', full_name='Admin', is_staff=True)
        request = RequestFactory().post('/admin/')
        request.user = admin
        model_admin = OfferAdmin(Offer, admin_site)
        offer, other = self.make_offer(), self.make_offer(title='Une autre annonce à retirer')
        for item in (offer, other):
            DailyVisibilityCounter.objects.create(offer_id=item.id, seller=self.seller, date=timezone.localdate(), views=1)

        form = mock.Mock(changed_data=['price'])
        model_admin.save_model(request, offer, form, True)
        self.assertTrue(AuditLog.objects.filter(action='OFFER_ADMIN_UPDATED', target_id=offer.id).exists())

        model_admin.delete_model(request, offer)
        model_admin.delete_queryset(request, Offer.objects.filter(pk=other.pk))
        self.assertEqual(AuditLog.objects.filter(action='OFFER_DELETED', actor=admin).count(), 2)
        self.assertFalse(Offer.objects.exists() or DailyVisibilityCounter.objects.exists())


class QueryCountTests(MarketplaceTestBase):
    """Le nombre de requêtes ne dépend pas du nombre d'éléments listés."""

    def count(self, url_name):
        self.client.get(reverse(url_name))  # amorce les réglages à ligne unique
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def assert_constant(self, url_name, grow):
        self.client.force_authenticate(self.buyer)
        grow(0)
        few = self.count(url_name)
        for i in range(1, 6):
            grow(i)
        self.assertEqual(few, self.count(url_name), url_name)

    def test_favorites(self):
        def grow(i):
            seller = User.objects.create_user(email=f's{i}@example.com', password='x', full_name=f'S{i}')
            Favorite.objects.create(user=self.buyer, offer=self.make_offer(seller=seller, title=f'Annonce favorite {i} ici'))
        self.assert_constant('favorite-list', grow)

    def test_trash(self):
        def grow(i):
            self.make_offer(seller=self.buyer, title=f'Annonce supprimée numéro {i}', is_deleted=True)
        self.assert_constant('offer-trash', grow)

    def test_contacts_and_exchanges(self):
        def grow(i):
            offer = self.make_offer(title=f'Annonce contactée numéro {i}')
            ContactEvent.objects.create(offer=offer, sender=self.buyer, message='Bonjour')
            ExchangeProposal.objects.create(offer=offer, sender=self.buyer, message='Troc')
        self.assert_constant('contact-list', grow)
        self.assert_constant('exchange-list', grow)


class TimezoneTests(MarketplaceTestBase):
    def test_json_dates_carry_the_kinshasa_offset(self):
        offer = self.make_offer()
        data = self.client.get(reverse('offer-detail', args=[offer.id])).data
        self.assertTrue(data['created_at'].endswith('+01:00'), data['created_at'])
        self.assertTrue(data['expires_at'].endswith('+01:00'))

    def test_contacts_are_counted_by_local_day_with_explicit_bounds(self):
        offer = self.make_offer()
        tz = timezone.get_current_timezone()
        day = timezone.localdate()
        late = ContactEvent.objects.create(offer=offer, sender=self.buyer, message='Tard')
        early = ContactEvent.objects.create(offer=offer, sender=self.seller, message='Tôt')
        previous = ContactEvent.objects.create(offer=offer, sender=self.buyer, message='Veille')
        ContactEvent.objects.filter(pk=late.pk).update(created_at=datetime.combine(day, datetime.max.time(), tz))
        ContactEvent.objects.filter(pk=early.pk).update(created_at=datetime.combine(day, datetime.min.time(), tz))
        ContactEvent.objects.filter(pk=previous.pk).update(
            created_at=datetime.combine(day, datetime.min.time(), tz) - timedelta(seconds=1),
        )
        rows = services.count_contacts_by_offer(day)
        self.assertEqual(rows, [(offer.id, self.seller.id, 2)])


class UploadLimitTests(MarketplaceTestBase):
    def test_upload_settings_are_bounded(self):
        from django.conf import settings

        self.assertEqual(settings.PROFILE_IMAGE_MAX_PIXELS, 16_000_000)
        self.assertEqual(settings.TIME_ZONE, 'Africa/Kinshasa')
        self.assertTrue(settings.USE_TZ)
        self.assertLessEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 2 * 1024 * 1024)
        self.assertLessEqual(settings.DATA_UPLOAD_MAX_NUMBER_FILES, 10)

    def test_offer_images_share_the_pixel_ceiling(self):
        self.client.force_authenticate(self.seller)
        with self.settings(PROFILE_IMAGE_MAX_PIXELS=100):
            response = self.client.post(reverse('offer-list'), self.offer_payload())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('main_image', response.data)
