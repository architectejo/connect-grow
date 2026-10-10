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

    def test_delay_grows_with_each_tier_of_failures_and_expires(self):
        clock = {'now': 1_000_000.0}
        with mock.patch('apps.identity.throttles.time.time', lambda: clock['now']):
            for _ in range(5):
                self.assertEqual(self.login().status_code, 401)
            first = self.login()
            self.assertEqual(first.status_code, 429)
            self.assertEqual(int(first['Retry-After']), 15 * 60)
            clock['now'] += 15 * 60 + 1          # délai écoulé : une tentative est de nouveau permise
            self.assertEqual(self.login().status_code, 401)   # 6e échec : verrou de nouveau (palier 1)
            self.assertEqual(self.login().status_code, 429)
            clock['now'] += 15 * 60 + 1
            for _ in range(4):                    # échecs 7 à 10, un par délai écoulé
                self.assertEqual(self.login().status_code, 401)
                self.assertEqual(self.login().status_code, 429)
                clock['now'] += 15 * 60 + 1
            # 10 échecs au total : palier suivant. Le délai de 30 min court depuis le dernier échec ;
            # 15 min + 1 s se sont écoulées, il reste donc 15 min - 1 s.
            still_locked = self.login()
            self.assertEqual(still_locked.status_code, 429)
            self.assertEqual(int(still_locked['Retry-After']), 30 * 60 - (15 * 60 + 1))
            clock['now'] += 15 * 60
            self.assertEqual(self.login().status_code, 401)

    def test_second_tier_doubles_the_delay_and_is_capped(self):
        from .throttles import FailureLimiter

        limiter = FailureLimiter('t', threshold=5, base_delay=900, max_delay=3600)
        self.assertEqual([limiter.delay_for(n) for n in (5, 9, 10, 15, 20, 100)], [900, 900, 1800, 3600, 3600, 3600])

    def test_a_third_party_on_other_ips_never_extends_the_victims_delay(self):
        for i in range(30):
            self.login(ip=f'10.9.1.{i}')
        self.assertEqual(self.login(PASSWORD, ip='10.9.2.1').status_code, 200)

    def test_spelling_variants_share_the_same_counter(self):
        for variant in ('victime@example.com', 'Victime@Example.com', ' VICTIME@example.COM '):
            self.assertEqual(self.login(email=variant).status_code, 401)
        self.assertEqual(self.login(email='victime@EXAMPLE.com').status_code, 401)
        self.assertEqual(self.login(email='VICTIME@example.com').status_code, 401)
        self.assertEqual(self.login(email='victime@example.com').status_code, 429)

    def test_phone_spelling_variants_share_the_same_counter(self):
        from .views import failure_key

        request = self.request_for()
        keys = {
            failure_key(request, v)
            for v in ('+243810000000', '243810000000', '+243 81 000 0000', '0024381-000-0000', '(+243) 810.000.000')
        }
        self.assertEqual(len(keys), 1)

    def request_for(self, ip='10.1.0.1'):
        return Request(APIRequestFactory().post('/', REMOTE_ADDR=ip))

    def test_failure_counter_is_atomic_under_concurrency(self):
        from concurrent.futures import ThreadPoolExecutor

        from .throttles import FailureLimiter

        limiter = FailureLimiter('atomic')
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: limiter.failure('k'), range(40)))
        self.assertEqual(cache.get('fail:atomic:k'), 40)

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

    def test_generic_weak_password_does_not_burn_the_otp(self):
        otp, code = OtpCode.issue(self.PHONE, OtpCode.PURPOSE_PASSWORD_RESET)
        response = self.confirm(code, new_password='12345678901')
        self.assertEqual(response.status_code, 400)
        otp.refresh_from_db()
        self.assertFalse(otp.is_used)
        self.assertEqual(otp.attempts, 0)

    def test_similarity_to_the_account_is_checked_only_after_the_otp(self):
        User.objects.filter(pk=self.user.pk).update(email='jean.dupont@example.com', full_name='Jean Dupont')
        _, code = OtpCode.issue(self.PHONE, OtpCode.PURPOSE_PASSWORD_RESET)
        similar = 'jean.dupont@example.com'
        # Sans code valide : « code invalide », jamais le message de similarité (pas d'oracle).
        wrong = self.confirm('000000', new_password=similar)
        self.assertEqual(wrong.data['error'], 'Code invalide ou expiré.')
        # Avec le bon code, le titulaire apprend que son mot de passe ressemble à son compte.
        right = self.confirm(code, new_password=similar)
        self.assertEqual(right.status_code, 400)
        self.assertNotEqual(right.data['error'], 'Code invalide ou expiré.')

    def test_response_is_identical_for_existing_and_unknown_numbers(self):
        User.objects.filter(pk=self.user.pk).update(email='jean.dupont@example.com', full_name='Jean Dupont')
        known = self.confirm('000000', new_password='jean.dupont@example.com')
        unknown = self.confirm('000000', new_password='jean.dupont@example.com', phone='+243899999999', ip='10.7.9.9')
        self.assertEqual((known.status_code, known.data), (unknown.status_code, unknown.data))


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


@override_settings(CACHES=LOCMEM_CACHE)
class RegisterAndProfileThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_register_is_throttled_per_ip(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'register': '2/hour'}):
            codes = [
                APIClient().post('/api/accounts/register/', {'email': f'r{i}@example.com'}, format='json',
                                 REMOTE_ADDR='10.9.0.1').status_code
                for i in range(3)
            ]
            other_ip = APIClient().post('/api/accounts/register/', {'email': 'r9@example.com'}, format='json',
                                        REMOTE_ADDR='10.9.0.2').status_code
        self.assertEqual(codes[2], 429)
        self.assertNotEqual(codes[1], 429)
        self.assertNotEqual(other_ip, 429)

    def test_profile_writes_are_throttled_but_reads_are_not(self):
        user = User.objects.create_user(email='p@example.com', password=PASSWORD, full_name='P')
        client = APIClient()
        client.force_authenticate(user)
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'profile_write': '2/hour'}):
            codes = [client.patch('/api/accounts/me/', {'full_name': f'P{i}'}, format='json').status_code
                     for i in range(3)]
            reads = [client.get('/api/accounts/me/').status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
        self.assertEqual(reads, [200, 200, 200])
