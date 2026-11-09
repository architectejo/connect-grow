"""L0-14 : le troc est masqué derrière le réglage `MarketplaceSettings.exchange_enabled` (éteint par défaut)."""
from django.contrib.admin.sites import site as admin_site
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status

from apps.identity.models import User
from apps.moderation.models import AuditLog
from apps.platform_core.models import OutboxEvent

from .models import ExchangeProposal, MarketplaceSettings, Offer
from .tests import MarketplaceTestBase


def set_exchange(enabled):
    row = MarketplaceSettings.get_solo()
    row.exchange_enabled = enabled
    row.save()


class ExchangeDisabledTests(MarketplaceTestBase):
    def test_default_is_off(self):
        self.assertFalse(MarketplaceSettings.get_solo().exchange_enabled)

    def test_proposal_refused_with_feature_disabled_and_no_side_effect(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('exchange-list'), {'post': str(offer.id), 'message': 'Je propose un troc.'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['code'], 'feature_disabled')
        self.assertIn('disponible', response.data['detail'])
        self.assertEqual(ExchangeProposal.objects.count(), 0)
        self.assertFalse(OutboxEvent.objects.filter(event_type='marketplace.exchange_proposed').exists())

    def test_proposal_list_is_refused_too_and_anonymous_stays_401(self):
        self.assertEqual(self.client.get(reverse('exchange-list')).status_code, status.HTTP_401_UNAUTHORIZED)
        self.client.force_authenticate(self.buyer)
        response = self.client.get(reverse('exchange-list'))
        self.assertEqual((response.status_code, response.data['code']), (403, 'feature_disabled'))

    def test_field_absent_from_list_and_detail(self):
        offer = self.make_offer()
        self.assertNotIn('is_exchangeable', self.client.get(reverse('offer-detail', args=[offer.id])).data)
        rows = self.client.get(reverse('offer-list')).data
        self.assertTrue(rows)
        self.assertTrue(all('is_exchangeable' not in row for row in rows))

    def test_filter_is_ignored(self):
        yes = self.make_offer(title='Chaise en bois massif', is_exchangeable=True)
        no = self.make_offer(title='Téléviseur grand écran 4K', is_exchangeable=False)
        response = self.client.get(reverse('offer-list'), {'is_exchangeable': 'true'})
        self.assertEqual({row['id'] for row in response.data}, {str(yes.id), str(no.id)})

    def test_field_not_writable_and_existing_value_kept(self):
        offer = self.make_offer(is_exchangeable=True)
        self.client.force_authenticate(self.seller)
        response = self.client.patch(reverse('offer-detail', args=[offer.id]), {'is_exchangeable': False})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        offer.refresh_from_db()
        self.assertTrue(offer.is_exchangeable)
        created = self.client.post(reverse('offer-list'), self.offer_payload(is_exchangeable='false'), format='multipart')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertNotIn('is_exchangeable', created.data)


class ExchangeEnabledTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        set_exchange(True)

    def test_proposal_works_as_before(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('exchange-list'), {'post': str(offer.id), 'message': 'Je propose un troc.'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(ExchangeProposal.objects.count(), 1)

    def test_field_filter_and_write_work_as_before(self):
        yes = self.make_offer(title='Chaise en bois massif', is_exchangeable=True)
        no = self.make_offer(title='Téléviseur grand écran 4K', is_exchangeable=False)
        self.assertIn('is_exchangeable', self.client.get(reverse('offer-detail', args=[yes.id])).data)
        response = self.client.get(reverse('offer-list'), {'is_exchangeable': 'false'})
        self.assertEqual({row['id'] for row in response.data}, {str(no.id)})
        self.client.force_authenticate(self.seller)
        self.client.patch(reverse('offer-detail', args=[yes.id]), {'is_exchangeable': False})
        yes.refresh_from_db()
        self.assertFalse(yes.is_exchangeable)


class FeaturesEndpointTests(MarketplaceTestBase):
    def test_public_contract_and_cache(self):
        response = self.client.get('/api/v1/config/features/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {'features': {'exchange_enabled': False}})
        self.assertEqual(response['Cache-Control'], 'public, max-age=60')

    def test_reflects_the_setting(self):
        set_exchange(True)
        self.assertEqual(self.client.get('/api/v1/config/features/').json(), {'features': {'exchange_enabled': True}})

    def test_read_only(self):
        self.assertEqual(self.client.post('/api/v1/config/features/', {}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ExchangeSettingAuditTests(MarketplaceTestBase):
    def test_change_in_admin_is_audited(self):
        from unittest import mock
        admin = User.objects.create_user(email='adm@example.com', password='x', full_name='A', is_staff=True)
        request = RequestFactory().post('/admin/')
        request.user = admin
        row = MarketplaceSettings.get_solo()
        row.exchange_enabled = True
        form = mock.Mock(changed_data=['exchange_enabled'], initial={'exchange_enabled': False})
        admin_site._registry[MarketplaceSettings].save_model(request, row, form, True)
        entry = AuditLog.objects.filter(action='SETTINGS_CHANGED', target_id=row.pk).latest('created_at')
        self.assertIn('exchange_enabled : False -> True', entry.details)
        self.assertTrue(MarketplaceSettings.get_solo().exchange_enabled)
