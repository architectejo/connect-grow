"""L0-21 : non-régression des corrections de la recette du lot 0 (R0-01 à R0-12 et arbitrages)."""
import logging
from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import Throttled
from rest_framework.test import APIClient

from apps.common.exception_handler import CodedAPIException, exception_handler, throttled_message
from apps.common.factories import make_test_image
from apps.common.tests_recette_lot0 import PASSWORD, POSTS_URL, UUID_RE, RecetteBase
from apps.common.utils import seconds_until_next_day
from apps.identity.models import User, normalize_email
from apps.identity.sms import send_otp_sms
from apps.marketplace.models import Offer
from apps.moderation.models import Sanction
from apps.platform_core.testing import dispatch_outbox_now


class OfferNumbersTests(RecetteBase):
    def payload(self, **extra):
        return {
            'post_type': 'PRODUIT', 'category': str(self.category.id), 'commune': str(self.commune.id),
            'title': 'Perceuse de test solide', 'description': 'Description suffisamment longue pour le CDC.',
            'price': '10', 'currency': 'USD', 'condition': 'NEUF', 'stock': '1',
            'main_image': make_test_image(), **extra,
        }

    def create(self, **extra):
        return self.as_user(self.seller).post(POSTS_URL, self.payload(**extra), format='multipart')

    def test_negative_price_is_refused_on_create_and_update(self):
        refused = self.create(price='-0.01')
        self.assertEqual(refused.status_code, 400)
        self.assertIn('price', refused.json())
        patched = self.as_user(self.seller).patch(f'{POSTS_URL}{self.offer.id}/', {'price': '-5'}, format='json')
        self.assertEqual(patched.status_code, 400)
        self.assertEqual(Offer.objects.get(pk=self.offer.pk).price, 100)

    def test_zero_price_is_accepted_for_quote_only_offers(self):
        """Décision documentée : 0 reste permis (« Sur devis », CDC 3.2, sans champ dédié)."""
        self.assertEqual(self.create(price='0').status_code, 201)

    def test_negative_or_absurd_stock_is_a_400_never_a_500(self):
        client = self.as_user(self.seller)
        client.raise_request_exception = False
        for value in ('-1', '1000001'):
            response = client.post(POSTS_URL, self.payload(stock=value), format='multipart')
            self.assertEqual(response.status_code, 400, value)
            self.assertIn('stock', response.json())
        self.assertEqual(client.patch(f'{POSTS_URL}{self.offer.id}/', {'stock': '-3'}, format='json').status_code, 400)
        self.assertEqual(self.create(stock='1000000').status_code, 201)
        self.assertEqual(self.create(stock='0').status_code, 201)


class EmailCaseTests(RecetteBase):
    def register(self, email):
        return APIClient().post('/api/accounts/register/', {
            'full_name': 'Test Casse', 'password': PASSWORD, 'email': email}, format='json')

    def test_normalize_email(self):
        self.assertEqual(normalize_email('  Jean.Dupont@Example.COM '), 'jean.dupont@example.com')
        self.assertIsNone(normalize_email('   '))
        self.assertIsNone(normalize_email(None))

    def test_registration_stores_the_canonical_email_and_login_ignores_case(self):
        response = self.register('Marie.Curie@Example.com')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['email'], 'marie.curie@example.com')
        self.assertEqual(User.objects.get(full_name='Test Casse').email, 'marie.curie@example.com')
        for typed in ('MARIE.CURIE@EXAMPLE.COM', 'marie.curie@example.com'):
            login = APIClient().post('/api/accounts/login/', {'email': typed, 'password': PASSWORD}, format='json')
            self.assertEqual(login.status_code, 200, typed)

    def test_duplicate_in_another_case_is_refused(self):
        for typed in ('BUYER@example.com', 'Buyer@EXAMPLE.com'):
            self.assertEqual(self.register(typed).status_code, 400, typed)
        self.assertEqual(User.objects.filter(email__iexact='buyer@example.com').count(), 1)

    def test_legacy_mixed_case_account_can_still_log_in(self):
        User.objects.filter(pk=self.buyer.pk).update(email='Buyer@Example.com')  # donnée antérieure à L0-21
        login = APIClient().post(
            '/api/accounts/login/', {'email': 'buyer@example.com', 'password': 'x'}, format='json')
        self.assertEqual(login.status_code, 200)

    def test_profile_update_refuses_another_users_email_in_any_case_but_keeps_own(self):
        client = self.as_user(self.buyer)
        refused = client.patch('/api/accounts/me/', {'email': 'SELLER@example.com'}, format='json')
        self.assertEqual(refused.status_code, 400)
        own = client.patch('/api/accounts/me/', {'email': 'Buyer@Example.com'}, format='json')
        self.assertEqual(own.status_code, 200, own.content)
        self.assertEqual(own.json()['email'], 'buyer@example.com')

    def test_manager_normalizes_too(self):
        user = User.objects.create_user(email='  Admin2@Example.COM ', password=PASSWORD, full_name='A2')
        self.assertEqual(user.email, 'admin2@example.com')


class AccountTypeReadOnlyTests(RecetteBase):
    """ADR 0006, règle 1 : le compte est unique ; il n'a plus de type. `user_type` n'est ni exposé ni accepté
    (compatibilité transitoire : un ancien client qui l'envoie encore n'a aucun effet)."""

    def test_user_type_is_neither_exposed_nor_changed_through_me(self):
        client = self.as_user(self.buyer)
        self.assertNotIn('user_type', client.get('/api/accounts/me/').json())
        response = client.patch('/api/accounts/me/', {'user_type': 'ENTREPRISE'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('user_type', response.json())
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.user_type, 'PARTICULIER')


class SanctionLiftTests(RecetteBase):
    def setUp(self):
        super().setUp()
        self.target = User.objects.create_user(email='cible@example.com', password=PASSWORD, full_name='Cible')

    def sanction(self, kind, **extra):
        sanction = Sanction.objects.create(
            user=self.target, sanction_type=kind, reason='Test', issued_by=self.admin, **extra)
        sanction.apply()
        return sanction

    def test_account_stays_blocked_while_another_blocking_sanction_is_active(self):
        ban = self.sanction(Sanction.TYPE_BANNISSEMENT)
        suspension = self.sanction(Sanction.TYPE_SUSPENSION_TEMPORAIRE)
        suspension.lift()
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        ban.lift()
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_a_warning_does_not_keep_the_account_blocked(self):
        warning = self.sanction(Sanction.TYPE_AVERTISSEMENT)
        suspension = self.sanction(Sanction.TYPE_SUSPENSION_TEMPORAIRE)
        suspension.lift()
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertTrue(Sanction.objects.get(pk=warning.pk).is_active)

    def test_expiry_command_does_not_reactivate_a_banned_account(self):
        self.sanction(Sanction.TYPE_BANNISSEMENT)
        self.sanction(Sanction.TYPE_SUSPENSION_TEMPORAIRE, ends_at=timezone.now() - timedelta(hours=1))
        call_command('lift_expired_sanctions', verbosity=0)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(Sanction.objects.filter(user=self.target, is_active=True).count(), 1)


class SuspendedSellerVisibilityTests(RecetteBase):
    def suspend_seller(self):
        # Point unique de changement d'état du compte ; la visibilité des offres suit par l'événement (A7).
        from apps.identity import services as identity_services

        identity_services.set_account_active(self.seller.pk, False)
        dispatch_outbox_now()

    def ids(self, response):
        return [row['id'] for row in self.rows(response)]

    def test_offers_of_a_suspended_seller_leave_public_lists_search_and_detail(self):
        self.suspend_seller()
        anonymous = APIClient()
        self.assertNotIn(str(self.offer.id), self.ids(anonymous.get(POSTS_URL)))
        self.assertNotIn(str(self.offer.id), self.ids(anonymous.get(POSTS_URL, {'search': 'canapé'})))
        self.assertEqual(anonymous.get(f'{POSTS_URL}{self.offer.id}/').status_code, 404)
        self.assertEqual(self.as_user(self.buyer).get(f'{POSTS_URL}{self.offer.id}/').status_code, 404)

    def test_other_users_cannot_contact_or_favorite_such_an_offer(self):
        self.suspend_seller()
        self.assertEqual(self.contact_via_api(self.buyer).status_code, 400)
        favorite = self.as_user(self.buyer).post(
            '/api/marketplace/favorites/', {'post_id': str(self.offer.id)}, format='json')
        self.assertEqual(favorite.status_code, 400)

    def test_author_and_moderators_still_see_the_offer(self):
        self.suspend_seller()
        self.assertEqual(self.as_user(self.moderator).get(f'{POSTS_URL}{self.offer.id}/').status_code, 200)
        # L'auteur suspendu ne peut plus s'authentifier : on simule l'accès avec une session forcée.
        self.assertEqual(self.as_user(self.seller).get(f'{POSTS_URL}{self.offer.id}/').status_code, 200)
        # Les listes « de mon contexte » exigent un compte utilisable (garde du contexte actif, ADR 0006 6.2).
        mine = self.as_user(self.seller).get(POSTS_URL, {'my_posts': 'true'})
        self.assertEqual((mine.status_code, mine.json()['code']), (403, 'DENY_SECURITY'))

    def test_offer_is_public_again_once_the_account_is_reactivated(self):
        self.suspend_seller()
        from apps.identity import services as identity_services

        identity_services.set_account_active(self.seller.pk, True)
        dispatch_outbox_now()
        self.assertEqual(APIClient().get(f'{POSTS_URL}{self.offer.id}/').status_code, 200)


class ThrottleMessageTests(SimpleTestCase):
    def test_message_is_in_french_and_keeps_a_parsable_delay(self):
        self.assertEqual(throttled_message(42), "Requête ralentie. Réessayez dans 42 secondes.")
        self.assertEqual(throttled_message(1), "Requête ralentie. Réessayez dans 1 seconde.")
        self.assertIn('quelques instants', throttled_message(None))

    def test_handler_translates_throttled_and_keeps_retry_after(self):
        response = exception_handler(Throttled(wait=17), {})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data['detail'], "Requête ralentie. Réessayez dans 17 secondes.")
        self.assertEqual(response.data['code'], 'throttled')
        self.assertEqual(response['Retry-After'], '17')

    def test_coded_exception_with_wait_sets_retry_after(self):
        response = exception_handler(CodedAPIException("Limite atteinte.", 'daily_limit', 429, wait=3600), {})
        self.assertEqual((response.status_code, response['Retry-After']), (429, '3600'))

    def test_seconds_until_next_day_is_within_a_day(self):
        self.assertTrue(1 <= seconds_until_next_day() <= 24 * 3600)


class ConversationLastMessageFormatTests(RecetteBase):
    def test_last_message_matches_the_api_formats_in_both_code_paths(self):
        from apps.messaging.models import Conversation
        from apps.messaging.serializers import ConversationSerializer

        self.contact_via_api(self.buyer)
        dispatch_outbox_now()
        last = self.rows(self.as_user(self.seller).get('/api/interactions/conversations/'))[0]['last_message']
        self.assertTrue(UUID_RE.match(last['sender_id']), last['sender_id'])
        self.assertEqual(last['sender_id'], str(self.buyer.id))
        self.assertTrue(last['created_at'].endswith('+01:00'), last['created_at'])
        # Chemin de repli (sans annotation), utilisé hors liste.
        data = ConversationSerializer(
            Conversation.objects.get(), context={'request': mock.Mock(user=self.seller)}).data
        self.assertEqual(data['last_message']['sender_id'], str(self.buyer.id))
        self.assertTrue(data['last_message']['created_at'].endswith('+01:00'))


class OtpLoggingTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_code_is_logged_in_development(self):
        with self.assertLogs('apps.identity.sms', level=logging.INFO) as captured:
            send_otp_sms('+243810000000', '123456', 'REGISTER')
        self.assertIn('123456', captured.output[0])

    @override_settings(DEBUG=False)
    def test_code_is_never_logged_in_production(self):
        with self.assertNoLogs('apps.identity.sms', level=logging.DEBUG):
            with self.assertRaises(NotImplementedError) as raised:
                send_otp_sms('+243810000000', '654321', 'REGISTER')
        self.assertNotIn('654321', str(raised.exception))
