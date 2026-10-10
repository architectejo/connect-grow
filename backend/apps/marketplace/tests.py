import io
import uuid
from datetime import timedelta

from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Category, City, Commune
from apps.common.factories import make_test_image  # noqa: F401  (réexporté pour les tests des autres domaines)
from apps.identity.models import User
from apps.messaging.models import Conversation, Message
from apps.notifications.models import Notification
from apps.platform_core.testing import dispatch_outbox_now
from apps.visibility.models import DailyVisibilityCounter, OfferUniqueView, RankingSettings

from . import services
from .models import ContactEvent, Favorite, Offer, OfferImage


class MarketplaceTestBase(APITestCase):
    def setUp(self):
        self.city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=self.city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')

    def make_offer(self, **kwargs):
        defaults = dict(
            seller=self.seller,
            category_id=self.category.id,
            commune_id=self.commune.id,
            title='Un joli canapé à vendre',
            description='Description suffisamment longue pour passer la validation du CDC.',
            price=100,
            main_image=make_test_image(),
        )
        defaults.update(kwargs)
        return Offer.objects.create(**defaults)

    def offer_payload(self, **overrides):
        payload = {
            'title': 'Un titre correct', 'description': 'Description suffisamment longue pour valider.',
            'price': 10, 'category': str(self.category.id), 'commune': str(self.commune.id),
            'main_image': make_test_image(),
        }
        payload.update(overrides)
        return payload


class ImageReencodingTests(MarketplaceTestBase):
    def test_main_image_is_reencoded_to_webp_on_save(self):
        offer = self.make_offer()
        self.assertTrue(offer.main_image.name.lower().endswith('.webp'))
        # Le fichier doit être un WebP valide, pas juste renommé.
        offer.main_image.open()
        self.assertEqual(Image.open(offer.main_image).format, 'WEBP')

    def test_gallery_image_is_reencoded_to_webp_on_save(self):
        offer = self.make_offer()
        image = OfferImage.objects.create(offer=offer, image=make_test_image('extra.png', fmt='PNG'))
        self.assertTrue(image.image.name.lower().endswith('.webp'))

    def test_webp_upload_is_reencoded_too_and_loses_its_exif(self):
        """Un fichier déjà .webp n'échappe pas au ré-encodage : EXIF (GPS) retiré, nom régénéré."""
        exif = Image.Exif()
        exif[0x010F] = 'AppareilTest'
        buffer = io.BytesIO()
        Image.new('RGB', (30, 30), (10, 20, 30)).save(buffer, format='WEBP', exif=exif)
        self.assertIn(b'AppareilTest', buffer.getvalue())

        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile('mon-fichier.webp', buffer.getvalue(), content_type='image/webp')
        offer = self.make_offer(main_image=upload)
        offer.main_image.open()
        raw = offer.main_image.read()
        self.assertNotIn(b'AppareilTest', raw)
        self.assertNotIn('mon-fichier', offer.main_image.name)

    def test_gallery_endpoint_rejects_an_invalid_file_with_400(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        response = self.client.post(
            reverse('offer-images', args=[offer.id]),
            {'image': SimpleUploadedFile('faux.jpg', b'MZ pas une image', content_type='image/jpeg')},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(offer.images.count(), 0)

    def test_create_endpoint_rejects_an_invalid_file_with_400(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('offer-list'), self.offer_payload(
            main_image=SimpleUploadedFile('faux.jpg', b'MZ pas une image', content_type='image/jpeg'),
        ))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('main_image', response.data)


class OfferValidationTests(MarketplaceTestBase):
    def test_title_shorter_than_ten_chars_is_rejected(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('offer-list'), self.offer_payload(title='Court'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title', response.data)

    def test_description_shorter_than_twenty_chars_is_rejected(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('offer-list'), self.offer_payload(description='Trop court'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_main_image_is_required_on_creation(self):
        self.client.force_authenticate(self.seller)
        payload = self.offer_payload()
        del payload['main_image']
        response = self.client.post(reverse('offer-list'), payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('main_image', response.data)

    def test_valid_creation_sets_seller_and_expiration(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('offer-list'), self.offer_payload(post_type='SERVICE'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        offer = Offer.objects.get(pk=response.data['id'])
        self.assertEqual(offer.seller, self.seller)
        self.assertEqual(offer.offer_type, 'SERVICE')
        self.assertEqual(response.data['post_type'], 'SERVICE')
        self.assertIsNotNone(offer.expires_at)

    def test_anonymous_cannot_create(self):
        response = self.client.post(reverse('offer-list'), self.offer_payload())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class OfferOwnershipTests(MarketplaceTestBase):
    """Seul le vendeur modifie, supprime ou gère le cycle de vie de son offre."""

    def test_owner_can_update(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        response = self.client.patch(reverse('offer-detail', args=[offer.id]), {'price': 250})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        offer.refresh_from_db()
        self.assertEqual(offer.price, 250)

    def test_other_user_cannot_update_or_delete(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        url = reverse('offer-detail', args=[offer.id])
        self.assertEqual(self.client.patch(url, {'price': 1}).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.put(url, {}).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        offer.refresh_from_db()
        self.assertEqual(offer.price, 100)

    def test_other_user_cannot_use_owner_actions(self):
        offer = self.make_offer()
        Offer.objects.filter(pk=offer.pk).update(is_deleted=True)
        self.client.force_authenticate(self.buyer)
        for name in ('restore', 'soft-delete', 'pause', 'unpause', 'mark-sold', 'renew'):
            response = self.client.post(reverse(f'offer-{name}', args=[offer.id]))
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, name)
        response = self.client.delete(reverse('offer-hard-delete', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Offer.objects.filter(pk=offer.pk).exists())

    def test_unknown_offer_gives_404_not_500(self):
        self.client.force_authenticate(self.seller)
        ghost = uuid.uuid4()
        self.assertEqual(self.client.post(reverse('offer-restore', args=[ghost])).status_code, 404)
        self.assertEqual(self.client.delete(reverse('offer-hard-delete', args=[ghost])).status_code, 404)

    def test_owner_destroy_removes_offer_and_visibility_data(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        self.client.get(reverse('offer-detail', args=[offer.id]))
        self.assertTrue(DailyVisibilityCounter.objects.filter(offer_id=offer.id).exists())

        self.client.force_authenticate(self.seller)
        response = self.client.delete(reverse('offer-detail', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Offer.objects.filter(pk=offer.pk).exists())
        self.assertFalse(DailyVisibilityCounter.objects.filter(offer_id=offer.id).exists())
        self.assertFalse(OfferUniqueView.objects.filter(offer_id=offer.id).exists())

    def test_recalculate_all_scores_is_admin_only(self):
        self.make_offer()
        url = reverse('offer-recalculate-all-scores')
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.post(url).status_code, status.HTTP_403_FORBIDDEN)
        admin = User.objects.create_user(email='admin@example.com', password='x', full_name='Admin', is_staff=True)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.post(url).status_code, status.HTTP_200_OK)


class OfferGalleryTests(MarketplaceTestBase):
    def test_owner_cannot_exceed_the_image_limit(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        # main_image compte pour 1 : il reste 7 places.
        for _ in range(7):
            OfferImage.objects.create(offer=offer, image=make_test_image())
        response = self.client.post(
            reverse('offer-images', args=[offer.id]),
            {'image': make_test_image('one_too_many.jpg')},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_add_an_image(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        response = self.client.post(
            reverse('offer-images', args=[offer.id]), {'image': make_test_image()}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(offer.images.count(), 1)

    def test_non_owner_cannot_add_images(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(
            reverse('offer-images', args=[offer.id]), {'image': make_test_image()}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_delete_a_gallery_image(self):
        offer = self.make_offer()
        image = OfferImage.objects.create(offer=offer, image=make_test_image())
        self.client.force_authenticate(self.seller)
        response = self.client.delete(f"{reverse('offer-images', args=[offer.id])}?image_id={image.id}")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(OfferImage.objects.filter(id=image.id).exists())

    def test_deleting_an_unknown_image_gives_404(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        for image_id in (str(uuid.uuid4()), 'pas-un-uuid', ''):
            response = self.client.delete(f"{reverse('offer-images', args=[offer.id])}?image_id={image_id}")
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, image_id)


class FavoriteTests(MarketplaceTestBase):
    def test_toggle_favorite_adds_then_removes(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('offer-favorite', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['favorited'])
        self.assertTrue(Favorite.objects.filter(user=self.buyer, offer=offer).exists())

        response = self.client.post(reverse('offer-favorite', args=[offer.id]))
        self.assertFalse(response.data['favorited'])
        self.assertFalse(Favorite.objects.filter(user=self.buyer, offer=offer).exists())

    def test_favorites_list_only_shows_own_favorites(self):
        offer = self.make_offer()
        Favorite.objects.create(user=self.buyer, offer=offer)
        self.client.force_authenticate(self.seller)
        response = self.client.get(reverse('favorite-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

        self.client.force_authenticate(self.buyer)
        response = self.client.get(reverse('favorite-list'))
        self.assertEqual(len(response.data), 1)
        item = response.data[0]
        self.assertEqual(set(item), {'id', 'post', 'created_at'})
        self.assertEqual(item['post']['id'], str(offer.id))
        self.assertTrue(item['post']['is_favorited'])
        self.assertEqual(item['post']['favorites_count'], 1)

    def test_create_favorite_through_the_collection_endpoint(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('favorite-list'), {'post_id': str(offer.id)})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        # Un second ajout est refusé proprement (400), pas une erreur 500.
        response = self.client.post(reverse('favorite-list'), {'post_id': str(offer.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_favorite_a_deleted_offer_through_the_collection_endpoint(self):
        offer = self.make_offer()
        Offer.objects.filter(pk=offer.pk).update(is_deleted=True)
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('favorite-list'), {'post_id': str(offer.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_is_favorited_flag_on_offer_detail(self):
        offer = self.make_offer()
        Favorite.objects.create(user=self.buyer, offer=offer)
        self.client.force_authenticate(self.buyer)
        response = self.client.get(reverse('offer-detail', args=[offer.id]))
        self.assertTrue(response.data['is_favorited'])
        self.client.force_authenticate(None)
        self.assertFalse(self.client.get(reverse('offer-detail', args=[offer.id])).data['is_favorited'])


class OfferFilterTests(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        self.cheap_usd = self.make_offer(title='Chaise en bois massif', price=20, currency='USD')
        self.expensive_cdf = self.make_offer(
            title='Téléviseur grand écran 4K', price=500000, currency='CDF', is_exchangeable=False,
        )

    def ids(self, **params):
        response = self.client.get(reverse('offer-list'), params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {p['id'] for p in response.data}

    def test_filter_by_currency(self):
        ids = self.ids(currency='CDF')
        self.assertIn(str(self.expensive_cdf.id), ids)
        self.assertNotIn(str(self.cheap_usd.id), ids)

    def test_filter_by_price_range(self):
        ids = self.ids(price_min=10, price_max=100)
        self.assertIn(str(self.cheap_usd.id), ids)
        self.assertNotIn(str(self.expensive_cdf.id), ids)

    def test_invalid_price_filter_does_not_fail(self):
        self.assertEqual(self.ids(price_min='abc'), set())
        self.assertEqual(self.ids(price_max='NaN'), set())
        # Valeur hors plage : bornée, sans erreur.
        self.assertEqual(self.ids(price_max='1' * 60), {str(self.cheap_usd.id), str(self.expensive_cdf.id)})

    def test_filter_by_exchangeable(self):
        ids = self.ids(is_exchangeable='false')
        self.assertIn(str(self.expensive_cdf.id), ids)
        self.assertNotIn(str(self.cheap_usd.id), ids)

    def test_search_by_title(self):
        self.assertEqual(self.ids(search='chaise'), {str(self.cheap_usd.id)})

    def test_inactive_and_trashed_offers_are_not_public(self):
        Offer.objects.filter(pk=self.cheap_usd.pk).update(is_active=False)
        Offer.objects.filter(pk=self.expensive_cdf.pk).update(is_deleted=True)
        self.assertEqual(self.ids(), set())
        detail = self.client.get(reverse('offer-detail', args=[self.cheap_usd.id]))
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_my_offers_filter_lists_own_inactive_offers_but_not_trashed_ones(self):
        Offer.objects.filter(pk=self.cheap_usd.pk).update(is_active=False)
        Offer.objects.filter(pk=self.expensive_cdf.pk).update(is_deleted=True)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.ids(my_posts='true'), {str(self.cheap_usd.id)})

    def test_pagination_is_optional(self):
        response = self.client.get(reverse('offer-list'))
        self.assertIsInstance(response.data, list)
        response = self.client.get(reverse('offer-list'), {'page_size': 1})
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['results']), 1)


class OfferTrashTests(MarketplaceTestBase):
    def test_soft_delete_sets_deleted_at(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('offer-soft-delete', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        offer.refresh_from_db()
        self.assertTrue(offer.is_deleted)
        self.assertIsNotNone(offer.deleted_at)

    def test_restore_clears_deleted_at(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        self.client.post(reverse('offer-soft-delete', args=[offer.id]))
        self.client.post(reverse('offer-restore', args=[offer.id]))
        offer.refresh_from_db()
        self.assertFalse(offer.is_deleted)
        self.assertIsNone(offer.deleted_at)

    def test_trash_lists_only_own_deleted_offers(self):
        mine = self.make_offer(title='Mon annonce supprimée ici')
        other = self.make_offer(title='Annonce supprimée d un autre', seller=self.buyer)
        Offer.objects.filter(pk__in=[mine.pk, other.pk]).update(is_deleted=True)
        self.make_offer(title='Une annonce encore en ligne')
        self.client.force_authenticate(self.seller)
        response = self.client.get(reverse('offer-trash'))
        self.assertEqual([o['id'] for o in response.data], [str(mine.id)])

    def test_hard_delete_removes_the_offer(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        response = self.client.delete(reverse('offer-hard-delete', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Offer.objects.filter(pk=offer.pk).exists())


class VisibilityScoreFormulaTests(MarketplaceTestBase):
    def test_formula_is_engagement_times_recency(self):
        """Score stocké = E x R (ADR 0004) : vues, favoris, contacts, partages ; aucune note."""
        import math

        row = RankingSettings.get_solo()
        offer = self.make_offer()
        offer.views_count, offer.likes_count, offer.contacts_count, offer.shares_count = 10, 2, 1, 3
        offer.save(update_fields=['views_count', 'likes_count', 'contacts_count', 'shares_count'])

        services.refresh_visibility_score(offer)
        offer.refresh_from_db()

        raw = row.weight_views * 10 + row.weight_favorites * 2 + row.weight_contacts * 1 + row.weight_shares * 3
        expected_e = 1 + math.log(1 + raw)
        age_hours = (offer.last_score_update - offer.created_at).total_seconds() / 3600
        expected_r = 0.5 ** (age_hours / row.recency_half_life_hours)
        self.assertAlmostEqual(offer.visibility_score, expected_e * expected_r, places=6)

    def test_score_without_interaction_is_pure_recency(self):
        offer = self.make_offer()
        services.refresh_visibility_score(offer)
        offer.refresh_from_db()
        # E = 1 sans interaction : le score ne dépasse jamais R <= 1.
        self.assertLessEqual(offer.visibility_score, 1.0)
        self.assertGreater(offer.visibility_score, 0.99)

    def test_refresh_all_scores_only_touches_active_offers(self):
        mine = self.make_offer()
        hidden = self.make_offer(title='Une annonce masquée ici', is_active=False)
        other = self.make_offer(title='Annonce d un autre vendeur', seller=self.buyer)
        self.assertEqual(services.refresh_all_scores(), 2)
        for offer in (mine, hidden, other):
            offer.refresh_from_db()
        self.assertGreater(mine.visibility_score, 0)
        self.assertGreater(other.visibility_score, 0)
        self.assertEqual(hidden.visibility_score, 0)


class UniqueViewTests(MarketplaceTestBase):
    def test_first_anonymous_visit_gets_a_signed_cookie_and_is_not_counted(self):
        offer = self.make_offer()
        response = self.client.get(reverse('offer-detail', args=[offer.id]))
        self.assertIn('anon_id', response.cookies)
        offer.refresh_from_db()
        self.assertEqual(offer.views_count, 0)
        self.assertFalse(OfferUniqueView.objects.exists())

    def test_same_anonymous_visitor_counted_once_per_day(self):
        offer = self.make_offer()
        url = reverse('offer-detail', args=[offer.id])

        self.client.get(url)  # émet le cookie signé
        self.client.get(url)  # compté
        self.client.get(url)  # même visiteur, même jour : pas recompté

        dispatch_outbox_now()
        offer.refresh_from_db()
        self.assertEqual(offer.views_count, 1)
        self.assertEqual(OfferUniqueView.objects.filter(offer_id=offer.id).count(), 1)
        counter = DailyVisibilityCounter.objects.get(offer_id=offer.id)
        self.assertEqual((counter.views, counter.seller_id), (1, self.seller.id))

    def test_two_different_users_both_count(self):
        offer = self.make_offer()
        url = reverse('offer-detail', args=[offer.id])

        self.client.force_authenticate(self.buyer)
        self.client.get(url)
        other = User.objects.create_user(email='other@example.com', password='x', full_name='Autre')
        self.client.force_authenticate(other)
        self.client.get(url)

        dispatch_outbox_now()
        offer.refresh_from_db()
        self.assertEqual(offer.views_count, 2)
        self.assertEqual(DailyVisibilityCounter.objects.get(offer_id=offer.id).views, 2)

    def test_forged_or_unsigned_cookies_are_never_counted(self):
        offer = self.make_offer()
        url = reverse('offer-detail', args=[offer.id])
        for forged in ('x' * 500, uuid.uuid4().hex, 'abc:def:ghi'):
            self.client.cookies['anon_id'] = forged
            response = self.client.get(url)
            self.assertIn('anon_id', response.cookies)  # remplacé par un cookie signé valide
        offer.refresh_from_db()
        self.assertEqual(offer.views_count, 0)
        self.assertFalse(OfferUniqueView.objects.exists())

    def test_cookie_signed_by_the_server_is_hashed_in_the_database(self):
        offer = self.make_offer()
        url = reverse('offer-detail', args=[offer.id])
        self.client.get(url)
        self.client.get(url)
        key = OfferUniqueView.objects.get(offer_id=offer.id).viewer_key
        self.assertTrue(key.startswith('anon:'))
        self.assertLessEqual(len(key), 64)


class TrendingBadgeTests(MarketplaceTestBase):
    def counter(self, offer, days_ago, views):
        return DailyVisibilityCounter.objects.create(
            offer_id=offer.id, seller=self.seller, views=views, date=timezone.localdate() - timedelta(days=days_ago),
        )

    def test_not_trending_without_history(self):
        offer = self.make_offer()
        response = self.client.get(reverse('offer-detail', args=[offer.id]))
        self.assertFalse(response.data['is_trending'])

    def test_trending_when_views_spike(self):
        offer = self.make_offer()
        for i in range(1, 6):
            self.counter(offer, i, 1)
        self.counter(offer, 0, 10)
        response = self.client.get(reverse('offer-list'))
        flags = {o['id']: o['is_trending'] for o in response.data}
        self.assertTrue(flags[str(offer.id)])


class ShareActionTests(MarketplaceTestBase):
    def test_share_increments_counter_and_requires_auth(self):
        offer = self.make_offer()
        response = self.client.post(reverse('offer-share', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('offer-share', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dispatch_outbox_now()  # le total de l'offre est recalculé par l'outbox
        offer.refresh_from_db()
        self.assertEqual(offer.shares_count, 1)


class OfferLifecycleActionTests(MarketplaceTestBase):
    def test_owner_can_pause_and_unpause(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)

        response = self.client.post(reverse('offer-pause', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.STATUS_PAUSED)
        self.assertFalse(offer.is_active)

        response = self.client.post(reverse('offer-unpause', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.STATUS_ACTIVE)
        self.assertTrue(offer.is_active)

    def test_non_owner_cannot_pause(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('offer-pause', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_mark_sold(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('offer-mark-sold', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.STATUS_SOLD)
        self.assertFalse(offer.is_active)

    def test_unpause_an_expired_offer_requires_renewal(self):
        offer = self.make_offer()
        Offer.objects.filter(pk=offer.pk).update(status=Offer.STATUS_PAUSED, expires_at=timezone.now() - timedelta(days=1))
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('offer-unpause', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.STATUS_EXPIRED)

    def test_renew_resets_expiration_and_reactivates(self):
        offer = self.make_offer()
        Offer.objects.filter(pk=offer.pk).update(
            status=Offer.STATUS_EXPIRED, is_active=False, expires_at=timezone.now() - timedelta(days=1),
        )
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('offer-renew', args=[offer.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.STATUS_ACTIVE)
        self.assertTrue(offer.is_active)
        self.assertGreater(offer.expires_at, timezone.now())


class ScheduledTasksTests(MarketplaceTestBase):
    def test_purge_offer_trash_deletes_only_old_soft_deleted_offers(self):
        old_deleted = self.make_offer(title='Une annonce ancienne à purger')
        Offer.objects.filter(pk=old_deleted.pk).update(is_deleted=True, deleted_at=timezone.now() - timedelta(days=31))
        recent_deleted = self.make_offer(title='Une annonce récente supprimée')
        Offer.objects.filter(pk=recent_deleted.pk).update(is_deleted=True, deleted_at=timezone.now() - timedelta(days=1))

        call_command('purge_offer_trash', verbosity=0)

        self.assertFalse(Offer.objects.filter(pk=old_deleted.pk).exists())
        self.assertTrue(Offer.objects.filter(pk=recent_deleted.pk).exists())

    def test_purge_offer_trash_also_clears_visibility_data(self):
        offer = self.make_offer()
        DailyVisibilityCounter.objects.create(offer_id=offer.id, seller=self.seller, date=timezone.localdate(), views=3)
        Offer.objects.filter(pk=offer.pk).update(is_deleted=True, deleted_at=timezone.now() - timedelta(days=31))
        call_command('purge_offer_trash', verbosity=0)
        self.assertFalse(DailyVisibilityCounter.objects.filter(offer_id=offer.id).exists())

    def test_expire_offers_transitions_status(self):
        offer = self.make_offer()
        Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() - timedelta(days=1))

        call_command('expire_offers', verbosity=0)

        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.STATUS_EXPIRED)
        self.assertFalse(offer.is_active)

    def test_expire_offers_notifies_upcoming_expiration_once(self):
        offer = self.make_offer()
        Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() + timedelta(days=1))

        call_command('expire_offers', verbosity=0)
        call_command('expire_offers', verbosity=0)  # ne doit pas renotifier
        dispatch_outbox_now()

        self.assertEqual(Notification.objects.filter(user=self.seller, notification_type='EXPIRATION').count(), 1)

    def test_refresh_daily_contacts_counts_todays_contacts(self):
        offer = self.make_offer()
        ContactEvent.objects.create(offer=offer, sender=self.buyer, message='Bonjour')
        ContactEvent.objects.create(offer=offer, sender=self.buyer, message='Toujours disponible ?')

        call_command('refresh_daily_contacts', verbosity=0)
        call_command('refresh_daily_contacts', verbosity=0)  # idempotent

        counter = DailyVisibilityCounter.objects.get(offer_id=offer.id)
        self.assertEqual(counter.contacts, 2)
        self.assertEqual(counter.seller_id, self.seller.id)


class DashboardStatsTests(MarketplaceTestBase):
    def test_dashboard_summary_and_history(self):
        offer = self.make_offer()
        today = timezone.localdate()
        DailyVisibilityCounter.objects.create(offer_id=offer.id, seller=self.seller, date=today, views=4, contacts=2)
        DailyVisibilityCounter.objects.create(
            offer_id=offer.id, seller=self.seller, date=today - timedelta(days=2), views=6,
        )
        # Le compteur d'un autre vendeur n'est jamais compté.
        DailyVisibilityCounter.objects.create(offer_id=uuid.uuid4(), seller=self.buyer, date=today, views=99)

        self.client.force_authenticate(self.seller)
        response = self.client.get(reverse('dashboard_stats'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data['summary']
        self.assertEqual(
            (summary['total_views'], summary['today_views'], summary['active_posts'], summary['contacts_count']),
            (10, 4, 1, 2),
        )
        self.assertEqual(summary['contact_rate'], 2.0)
        self.assertEqual([p['views'] for p in response.data['history']], [6, 4])
        self.assertEqual(set(summary), {
            'total_views', 'today_views', 'active_posts', 'contacts_count', 'contact_rate', 'avg_rating', 'review_count',
        })

    def test_offer_stats_only_for_the_seller(self):
        offer = self.make_offer()
        DailyVisibilityCounter.objects.create(offer_id=offer.id, seller=self.seller, date=timezone.localdate(), views=3)
        url = reverse('offer_stats', args=[offer.id])
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.get(url).data['history'][0]['views'], 3)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)


class ContactTests(MarketplaceTestBase):
    def contact(self, offer, message='Bonjour, toujours disponible ?'):
        return self.client.post(reverse('contact-list'), {'post': str(offer.id), 'message': message})

    def test_contact_creates_event_conversation_message_and_notification(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        response = self.contact(offer)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(str(response.data['post']), str(offer.id))
        dispatch_outbox_now()  # conversation et notification sont créées par l'outbox (ADR 0003)

        self.assertEqual(ContactEvent.objects.filter(offer=offer, sender=self.buyer).count(), 1)
        conversation = Conversation.objects.get(offer_id=offer.id)
        self.assertEqual({p.id for p in conversation.participants.all()}, {self.buyer.id, self.seller.id})
        self.assertEqual(Message.objects.get(conversation=conversation).sender, self.buyer)
        notification = Notification.objects.get(user=self.seller)
        self.assertEqual(notification.notification_type, 'CONTACT')

    def test_each_buyer_gets_a_private_conversation(self):
        offer = self.make_offer()
        other = User.objects.create_user(email='other@example.com', password='x', full_name='Autre')
        for user in (self.buyer, other):
            self.client.force_authenticate(user)
            self.assertEqual(self.contact(offer).status_code, status.HTTP_201_CREATED)
        dispatch_outbox_now()
        self.assertEqual(Conversation.objects.filter(offer_id=offer.id).count(), 2)
        buyer_conversation = Conversation.objects.filter(offer_id=offer.id, participants=self.buyer).get()
        self.assertEqual(buyer_conversation.messages.count(), 1)
        self.assertFalse(buyer_conversation.participants.filter(pk=other.pk).exists())

    def test_cannot_contact_own_offer(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        response = self.contact(offer)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ContactEvent.objects.exists())

    def test_cannot_contact_a_deleted_offer_or_an_unknown_one(self):
        offer = self.make_offer()
        Offer.objects.filter(pk=offer.pk).update(is_deleted=True)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.contact(offer).status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(reverse('contact-list'), {'post': str(uuid.uuid4()), 'message': 'Bonjour'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_message_is_required_and_bounded(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.contact(offer, message='').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.contact(offer, message='x' * 2001).status_code, status.HTTP_400_BAD_REQUEST)

    def test_requires_authentication(self):
        offer = self.make_offer()
        self.assertEqual(self.contact(offer).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_contacts_are_private_to_their_sender_and_immutable(self):
        offer = self.make_offer()
        event = ContactEvent.objects.create(offer=offer, sender=self.buyer, message='Bonjour')
        self.client.force_authenticate(self.seller)
        self.assertEqual(len(self.client.get(reverse('contact-list')).data), 0)
        self.assertEqual(self.client.get(reverse('contact-detail', args=[event.id])).status_code, 404)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.client.patch(reverse('contact-detail', args=[event.id]), {'message': 'X'}).status_code, 405)
        self.assertEqual(self.client.delete(reverse('contact-detail', args=[event.id])).status_code, 405)

    def test_exchange_proposal_flow(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('exchange-list'), {'post': str(offer.id), 'message': 'Je propose un troc.'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        dispatch_outbox_now()
        message = Message.objects.get(conversation__offer_id=offer.id)
        self.assertTrue(message.content.startswith("[PROPOSITION D'ÉCHANGE]"))
        self.assertEqual(Notification.objects.get(user=self.seller).notification_type, 'EXCHANGE')


class CatalogDecouplingTests(MarketplaceTestBase):
    """ADR 0002 : catégories et communes référencées par UUID, résolues via catalog.services."""

    def test_list_has_a_constant_number_of_queries(self):
        other_commune = Commune.objects.create(city=self.city, name='Limete')
        for i in range(3):
            self.make_offer(title=f'Annonce numéro {i} à vendre', commune_id=other_commune.id if i else self.commune.id)

        def run():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(reverse('offer-list'))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return len(ctx.captured_queries), len([q for q in ctx.captured_queries if 'catalog_' in q['sql']]), response

        run()  # amorce les réglages (lignes uniques créées à la première lecture)
        few_total, few_catalog, response = run()
        names = {(p['category_name'], p['commune_name']) for p in response.data}
        self.assertEqual(names, {('Électronique', 'Gombe'), ('Électronique', 'Limete')})
        self.assertEqual(str(self.category.id), response.data[0]['category'])
        for i in range(3, 9):
            self.make_offer(title=f'Autre annonce numéro {i} ici')
        many_total, many_catalog, _ = run()
        # Une requête pour les catégories, une pour les communes, quel que soit le nombre d'offres.
        self.assertEqual((few_catalog, many_catalog), (2, 2))
        self.assertEqual(few_total, many_total)

    def test_authenticated_list_query_count_is_constant_too(self):
        self.client.force_authenticate(self.buyer)
        self.make_offer()
        self.client.get(reverse('offer-list'))  # amorce les réglages
        with CaptureQueriesContext(connection) as few:
            self.client.get(reverse('offer-list'))
        for i in range(6):
            self.make_offer(title=f'Autre annonce numéro {i} ici')
        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse('offer-list'))
        self.assertEqual(len(few.captured_queries), len(many.captured_queries))

    def test_filters_by_category_city_commune_and_location(self):
        other_city = City.objects.create(name='Lubumbashi')
        other_commune = Commune.objects.create(city=other_city, name='Kenya')
        other_category = Category.objects.create(name='Mode', slug='mode')
        kept = self.make_offer()
        far = self.make_offer(title='Annonce à Lubumbashi ici', commune_id=other_commune.id, category_id=other_category.id)

        def ids(**params):
            response = self.client.get(reverse('offer-list'), params)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return {p['id'] for p in response.data}

        self.assertEqual(ids(category=str(self.category.id)), {str(kept.id)})
        self.assertEqual(ids(city=str(other_city.id)), {str(far.id)})
        self.assertEqual(ids(commune=str(self.commune.id)), {str(kept.id)})
        self.assertEqual(ids(location='lubum'), {str(far.id)})
        self.assertEqual(ids(location='gombe'), {str(kept.id)})

    def test_malformed_filter_ids_return_nothing_instead_of_failing(self):
        self.make_offer()
        for param in ('category', 'commune', 'city', 'seller'):
            response = self.client.get(reverse('offer-list'), {param: 'pas-un-uuid'})
            self.assertEqual(response.status_code, status.HTTP_200_OK, param)
            self.assertEqual(len(response.data), 0, param)

    def test_create_rejects_unknown_category_and_commune(self):
        self.client.force_authenticate(self.seller)
        response = self.client.post(reverse('offer-list'), self.offer_payload(category=str(uuid.uuid4())))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('category', response.data)
        response = self.client.post(reverse('offer-list'), self.offer_payload(commune='abc'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('commune', response.data)


class ContractTests(MarketplaceTestBase):
    """Contrat JSON historique (jusqu'à L0-11) : clés de l'offre et du vendeur, ids en chaînes."""

    def test_offer_and_seller_json_keys(self):
        offer = self.make_offer()
        data = self.client.get(reverse('offer-detail', args=[offer.id])).data
        self.assertEqual(set(data), {
            'id', 'seller', 'seller_name', 'category', 'category_name', 'commune', 'commune_name', 'post_type',
            'title', 'description', 'price', 'currency', 'condition', 'stock', 'is_price_negotiable',
            'is_exchangeable', 'main_image', 'images', 'views_count', 'likes_count',
            'shares_count', 'created_at', 'status', 'expires_at', 'visibility_score', 'visibility_rank',
            'offer_rating', 'seller_rating', 'is_favorited', 'favorites_count', 'is_trending', 'is_sponsored', 'allowed_channels',
        })
        self.assertEqual(set(data['seller']), {
            'id', 'full_name', 'photo', 'user_type', 'business_profile', 'date_joined',
        })
        self.assertNotIn('phone', data['seller'])
        self.assertNotIn('email', data['seller'])
        self.assertEqual(data['id'], str(offer.id))
        self.assertEqual(data['seller']['id'], str(self.seller.id))
        self.assertIsNone(data['seller']['business_profile'])
        self.assertEqual(data['offer_rating'], {'average': None, 'count': 0})
        self.assertEqual(data['seller_rating'], {'average': None, 'count': 0})

    def test_seller_business_profile_is_embedded(self):
        from apps.identity.models import BusinessProfile

        BusinessProfile.objects.create(user=self.seller, business_name='Boutique Test', bio='Bio', is_verified=True)
        offer = self.make_offer()
        seller = self.client.get(reverse('offer-detail', args=[offer.id])).data['seller']
        self.assertEqual(set(seller['business_profile']), {'business_name', 'bio', 'logo', 'is_verified'})
        self.assertEqual(seller['business_profile']['business_name'], 'Boutique Test')
        self.assertTrue(seller['business_profile']['is_verified'])

    def test_offers_are_not_exposed_through_a_deleted_flag_name(self):
        offer = self.make_offer()
        data = self.client.get(reverse('offer-detail', args=[offer.id])).data
        self.assertNotIn('is_delete', data)
        self.assertNotIn('is_deleted', data)


class ServiceTests(MarketplaceTestBase):
    def test_get_offers_by_ids_ignores_malformed_ids(self):
        offer = self.make_offer()
        found = services.get_offers_by_ids([offer.id, 'nope', None, uuid.uuid4()])
        self.assertEqual(set(found), {offer.id})
        info = found[offer.id]
        self.assertEqual((info.seller_id, info.title), (self.seller.id, offer.title))
        self.assertTrue(info.main_image_url.endswith('.webp'))

    def test_offer_has_no_foreign_key_to_another_domain(self):
        for model in (Offer, OfferImage, Favorite, ContactEvent):
            for field in model._meta.get_fields():
                if field.is_relation and field.concrete:
                    self.assertIn(
                        field.related_model._meta.app_label, ('marketplace', 'identity'), f'{model.__name__}.{field.name}',
                    )


class OwnerRetrieveInactiveOfferTests(MarketplaceTestBase):
    """L0-19 : le vendeur retrouve ses offres non actives ; le public et les tiers non."""

    def states(self):
        return {
            'pause': dict(status=Offer.STATUS_PAUSED, is_active=False),
            'vendue': dict(status=Offer.STATUS_SOLD, is_active=False),
            'expiree': dict(status=Offer.STATUS_EXPIRED, is_active=False),
            'masquee': dict(is_active=False, is_hidden_by_moderation=True),
            'corbeille': dict(is_deleted=True, is_active=False),
        }

    def test_owner_sees_every_state_others_get_404(self):
        for label, fields in self.states().items():
            offer = self.make_offer(**fields)
            url = reverse('offer-detail', args=[offer.id])
            self.client.force_authenticate(self.seller)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, label)
            self.assertEqual(response.data['status'], offer.status, label)
            self.assertEqual(response.data['is_hidden_by_moderation'], label == 'masquee', label)
            self.client.force_authenticate(self.buyer)
            self.assertEqual(self.client.get(url).status_code, 404, label)
            self.client.force_authenticate(None)
            self.assertEqual(self.client.get(url).status_code, 404, label)

    def test_hidden_offer_cannot_be_put_back_online(self):
        offer = self.make_offer(is_active=False, is_hidden_by_moderation=True)
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.post(reverse('offer-unpause', args=[offer.id])).status_code, 403)
        offer.refresh_from_db()
        self.assertFalse(offer.is_active)

    def test_hidden_flag_is_read_only(self):
        offer = self.make_offer()
        self.client.force_authenticate(self.seller)
        self.client.patch(reverse('offer-detail', args=[offer.id]), {'is_hidden_by_moderation': True}, format='json')
        offer.refresh_from_db()
        self.assertFalse(offer.is_hidden_by_moderation)

    def test_owner_views_are_not_counted(self):
        offer = self.make_offer()
        paused = self.make_offer(status=Offer.STATUS_PAUSED, is_active=False)
        self.client.force_authenticate(self.seller)
        for o in (offer, paused):
            self.client.get(reverse('offer-detail', args=[o.id]))
        dispatch_outbox_now()
        self.assertFalse(OfferUniqueView.objects.exists())

    def test_query_count_is_unchanged_for_inactive_offer(self):
        active = self.make_offer()
        paused = self.make_offer(status=Offer.STATUS_PAUSED, is_active=False)
        self.client.force_authenticate(self.seller)
        counts = []
        self.client.get(reverse('offer-detail', args=[active.id]))  # réchauffe les caches
        for o in (active, paused):
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(reverse('offer-detail', args=[o.id])).status_code, 200)
            counts.append(len(ctx))
        self.assertEqual(counts[0], counts[1])


class OfferPrivacyTests(MarketplaceTestBase):
    """L0-10a-a / L0-19 : pas de téléphone du vendeur, masquage connu du seul vendeur, cache privé."""

    def test_seller_phone_and_email_never_in_offer_responses(self):
        self.seller.phone = '+243970000009'
        self.seller.save()
        offer = self.make_offer()
        for user in (None, self.buyer, self.seller):
            self.client.force_authenticate(user)
            for url in (reverse('offer-detail', args=[offer.id]), reverse('offer-list')):
                body = self.client.get(url).content.decode()
                self.assertNotIn('+243970000009', body)
                self.assertNotIn('seller@example.com', body)
                self.assertNotIn('"phone"', body)

    def test_hidden_flag_is_exposed_to_the_seller_only(self):
        offer = self.make_offer(is_hidden_by_moderation=True)
        url = reverse('offer-detail', args=[offer.id])
        self.client.force_authenticate(self.seller)
        self.assertTrue(self.client.get(url).data['is_hidden_by_moderation'])
        visible = self.make_offer(title='Une autre annonce visible')
        for user in (None, self.buyer):
            self.client.force_authenticate(user)
            self.assertNotIn('is_hidden_by_moderation', self.client.get(reverse('offer-detail', args=[visible.id])).data)

    def test_authenticated_api_responses_are_private_and_vary_on_authorization(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        offer = self.make_offer()
        url = reverse('offer-detail', args=[offer.id])
        token = str(RefreshToken.for_user(self.buyer).access_token)
        for target in (url, reverse('offer-list')):
            response = self.client.get(target, HTTP_AUTHORIZATION=f'Bearer {token}')
            self.assertIn('private', response['Cache-Control'])
            self.assertIn('Authorization', response['Vary'])
            self.assertIn('Authorization', self.client.get(target)['Vary'])

    def test_response_setting_the_anonymous_cookie_is_not_shared_cacheable(self):
        offer = self.make_offer()
        response = self.client.get(reverse('offer-detail', args=[offer.id]))
        self.assertIn('anon_id', response.cookies)
        self.assertIn('private', response['Cache-Control'])

    def test_cors_vary_is_preserved(self):
        response = self.client.get(reverse('offer-list'), HTTP_ORIGIN='http://localhost:8080')
        vary = response.get('Vary', '')
        self.assertIn('Authorization', vary)
        self.assertIn('origin', vary.lower())

    def test_mine_list_shows_hidden_flag_to_the_seller_only(self):
        self.make_offer(is_hidden_by_moderation=True, is_active=False)
        self.client.force_authenticate(self.seller)
        rows = self.client.get(reverse('offer-list'), {'my_posts': 'true'}).data
        rows = rows['results'] if isinstance(rows, dict) else rows
        self.assertTrue(rows)
        self.assertTrue(all('is_hidden_by_moderation' in row for row in rows))
        self.make_offer(title='Une annonce visible de tous')
        self.client.force_authenticate(self.buyer)
        rows = self.client.get(reverse('offer-list')).data
        rows = rows['results'] if isinstance(rows, dict) else rows
        self.assertTrue(rows)
        self.assertTrue(all('is_hidden_by_moderation' not in row for row in rows))


class DayBoundaryDashboardTests(MarketplaceTestBase):
    """L0-23 : le tableau de bord compte « aujourd'hui » dans le fuseau de l'application."""

    def run_at(self, *args):
        from datetime import datetime, timezone as dt_timezone
        from unittest import mock
        offer = self.make_offer()
        with mock.patch('django.utils.timezone.now', return_value=datetime(*args, tzinfo=dt_timezone.utc)):
            today = timezone.localdate()
            DailyVisibilityCounter.objects.create(offer_id=offer.id, seller=self.seller, date=today, views=4)
            DailyVisibilityCounter.objects.create(
                offer_id=offer.id, seller=self.seller, date=today - timedelta(days=2), views=6,
            )
            self.client.force_authenticate(self.seller)
            response = self.client.get(reverse('dashboard_stats'))
        self.assertEqual(response.data['summary']['today_views'], 4)
        self.assertEqual([p['views'] for p in response.data['history']], [6, 4])
        return today

    def test_23h30_utc_counts_as_next_local_day(self):
        self.assertEqual(self.run_at(2026, 10, 10, 23, 30).isoformat(), '2026-10-11')

    def test_midday_utc(self):
        self.assertEqual(self.run_at(2026, 10, 10, 12, 0).isoformat(), '2026-10-10')
