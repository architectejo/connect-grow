from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.throttling import SimpleRateThrottle

from . import views
from .models import BusinessProfile, KycDocument, OtpCode, User
from .throttles import LoginIpThrottle

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'throttle-tests'}}
PASSWORD = 'bon-mot-de-passe-12'


@override_settings(CACHES=LOCMEM_CACHE)
class LoginFailureLimiterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.victim = User.objects.create_user(email='victime@example.com', password=PASSWORD, full_name='V')

    def login(self, password='mauvais', ip='10.1.0.1', email='victime@example.com'):
        return APIClient().post(
            '/api/accounts/login/', {'email': email, 'password': password}, format='json', REMOTE_ADDR=ip,
        )

    def test_pair_is_locked_after_five_failures_but_other_ips_are_not(self):
        for _ in range(5):
            self.assertEqual(self.login().status_code, 401)
        locked = self.login()
        self.assertEqual(locked.status_code, 429)
        self.assertIn('Retry-After', locked)
        # Même IP, même identifiant : le bon mot de passe est aussi refusé tant que la fenêtre court.
        self.assertEqual(self.login(PASSWORD).status_code, 429)
        # La victime, depuis son adresse, se connecte normalement.
        self.assertEqual(self.login(PASSWORD, ip='10.1.0.99').status_code, 200)

    def test_third_party_cannot_block_victim_with_ten_requests_from_other_ips(self):
        for i in range(10):
            self.assertEqual(self.login(ip=f'10.2.0.{i}').status_code, 401)
        self.assertEqual(self.login(PASSWORD, ip='10.2.1.1').status_code, 200)

    def test_wide_identifier_ceiling_is_daily_and_still_exists(self):
        limits = [('pair', 5, 900), ('identifier', 12, 86400)]
        with mock.patch.object(views.LOGIN_FAILURES, 'limits', limits):
            for i in range(12):
                self.assertEqual(self.login(ip=f'10.3.0.{i}').status_code, 401)
            blocked = self.login(PASSWORD, ip='10.3.1.1')
        self.assertEqual(blocked.status_code, 429)
        self.assertLessEqual(int(blocked['Retry-After']), 86400)

    def test_only_failures_count_and_success_resets(self):
        for _ in range(4):
            self.login()
        self.assertEqual(self.login(PASSWORD).status_code, 200)
        for _ in range(4):
            self.assertEqual(self.login().status_code, 401)
        # 8 échecs au total mais jamais 5 de suite : pas de blocage.
        self.assertEqual(self.login(PASSWORD).status_code, 200)

    def test_successes_alone_never_trigger_the_failure_limit(self):
        for _ in range(8):
            self.assertEqual(self.login(PASSWORD).status_code, 200)

    def test_ip_throttle_counts_all_requests_whatever_the_identifier(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'login': '4/hour'}):
            codes = [self.login(email=f'u{i}@example.com', ip='10.4.0.1').status_code for i in range(5)]
        self.assertEqual(codes, [401, 401, 401, 401, 429])


@override_settings(CACHES=LOCMEM_CACHE)
class IpThrottleScopeTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_ip_limit_also_applies_to_authenticated_requests(self):
        user = User.objects.create_user(email='a@example.com', password='x', full_name='A')
        client = APIClient()
        client.force_authenticate(user)
        with mock.patch('apps.identity.views.send_otp_sms'):
            codes = [
                client.post('/api/accounts/otp/request/', {'phone': f'+24381000000{i}', 'purpose': 'REGISTER'},
                            REMOTE_ADDR='10.5.0.1').status_code
                for i in range(6)
            ]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5], 429)

    def test_num_proxies_controls_the_ip_seen_by_throttles(self):
        request = Request(APIRequestFactory().get('/', HTTP_X_FORWARDED_FOR='6.6.6.6, 1.2.3.4', REMOTE_ADDR='10.0.0.9'))
        throttle = LoginIpThrottle()
        with self.settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'NUM_PROXIES': 0}):
            self.assertEqual(throttle.get_ident(request), '10.0.0.9')  # en-tête ignoré : non falsifiable
        with self.settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}):
            self.assertEqual(throttle.get_ident(request), '1.2.3.4')  # ajouté par le proxy de confiance

    def test_refresh_has_its_own_scope(self):
        user = User.objects.create_user(email='r@example.com', password=PASSWORD, full_name='R')
        login = APIClient().post('/api/accounts/login/', {'email': 'r@example.com', 'password': PASSWORD},
                                 format='json', REMOTE_ADDR='10.6.0.1')
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'refresh': '2/hour'}):
            codes = [
                APIClient().post('/api/accounts/token/refresh/', {'refresh': 'invalide'}, format='json',
                                 REMOTE_ADDR='10.6.0.1').status_code
                for _ in range(3)
            ]
        self.assertEqual(codes, [401, 401, 429])
        # La connexion (autre scope) n'est pas touchée.
        again = APIClient().post('/api/accounts/login/', {'email': 'r@example.com', 'password': PASSWORD},
                                 format='json', REMOTE_ADDR='10.6.0.1')
        self.assertEqual(again.status_code, 200)

    def test_anonymous_browsing_ceiling_is_high_enough_for_shared_ips(self):
        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        self.assertGreaterEqual(int(rates['anon'].split('/')[0]), 1000)

    def test_change_password_is_throttled_per_user(self):
        user = User.objects.create_user(email='c@example.com', password=PASSWORD, full_name='C')
        client = APIClient()
        client.force_authenticate(user)
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'change_password': '2/hour'}):
            codes = [
                client.post('/api/accounts/change-password/', {'old_password': 'faux', 'new_password': 'x'},
                            format='json').status_code
                for _ in range(3)
            ]
        self.assertEqual(codes, [400, 400, 429])


@override_settings(CACHES=LOCMEM_CACHE)
class ResetConfirmFailureTests(TestCase):
    PHONE = '+243811111111'

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(phone=self.PHONE, password='ancien-solide-4242', full_name='R')

    def confirm(self, code='000000', ip='10.7.0.1', **extra):
        payload = {'phone': self.PHONE, 'code': code, 'new_password': 'cheval-agrafe-pile-47'}
        payload.update(extra)
        return APIClient().post('/api/accounts/password-reset/confirm/', payload, format='json', REMOTE_ADDR=ip)

    def test_five_wrong_codes_lock_the_pair_only(self):
        OtpCode.issue(self.PHONE, OtpCode.PURPOSE_PASSWORD_RESET)
        for _ in range(5):
            self.assertEqual(self.confirm().status_code, 400)
        self.assertEqual(self.confirm().status_code, 429)
        self.assertNotEqual(self.confirm(ip='10.7.0.2').status_code, 429)

    def test_success_resets_and_requests_are_not_counted_when_valid(self):
        for i in range(8):
            _, code = OtpCode.issue(self.PHONE, OtpCode.PURPOSE_PASSWORD_RESET)
            self.assertEqual(self.confirm(code).status_code, 200, i)

    def test_invalid_types_are_400_and_do_not_consume_attempts(self):
        otp, code = OtpCode.issue(self.PHONE, OtpCode.PURPOSE_PASSWORD_RESET)
        for bad in ({'code': ['1']}, {'code': {'a': 1}}, {'code': True}, {'phone': ['x']}, {'phone': None}):
            self.assertEqual(self.confirm(**bad).status_code, 400, bad)
        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 0)
        self.assertEqual(self.confirm(code).status_code, 200)

    def test_integer_code_is_accepted_as_text(self):
        _, code = OtpCode.issue(self.PHONE, OtpCode.PURPOSE_PASSWORD_RESET)
        self.assertEqual(self.confirm(int(code) if not code.startswith('0') else code).status_code, 200)

    def test_similarity_validator_uses_the_account_without_burning_the_otp(self):
        User.objects.filter(pk=self.user.pk).update(email='jean.dupont@example.com', full_name='Jean Dupont')
        otp, code = OtpCode.issue(self.PHONE, OtpCode.PURPOSE_PASSWORD_RESET)
        response = self.confirm(code, new_password='jean.dupont@example.com')
        self.assertEqual(response.status_code, 400)
        otp.refresh_from_db()
        self.assertFalse(otp.is_used)
        self.assertEqual(otp.attempts, 0)


@override_settings(CACHES=LOCMEM_CACHE)
class KycWriteThrottleTests(TestCase):
    def test_deposit_and_delete_are_throttled_per_user(self):
        from .tests import PNG_BYTES, kyc_upload

        user = User.objects.create_user(email='k@example.com', password='x', full_name='K', user_type='ENTREPRISE')
        BusinessProfile.objects.create(user=user, business_name='B')
        client = APIClient()
        client.force_authenticate(user)
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'kyc_write': '2/hour'}):
            first = client.post('/api/accounts/kyc/documents/', {'document_type': 'RCCM', 'file': kyc_upload(PNG_BYTES)}, format='multipart')
            doc = KycDocument.objects.get(pk=first.data['id'])
            deleted = client.delete(f'/api/accounts/kyc/documents/{doc.pk}/')
            blocked = client.post('/api/accounts/kyc/documents/', {'document_type': 'RCCM', 'file': kyc_upload(PNG_BYTES)}, format='multipart')
            listing = client.get('/api/accounts/kyc/documents/')
        self.assertEqual((first.status_code, deleted.status_code, blocked.status_code), (201, 204, 429))
        self.assertEqual(listing.status_code, 200)  # la lecture n'est pas limitée
