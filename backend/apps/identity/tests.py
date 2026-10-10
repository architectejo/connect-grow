import os
from datetime import timedelta

from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

import uuid

from rest_framework_simplejwt.tokens import RefreshToken

from apps.catalog.models import Category, City, Commune

from .models import BusinessProfile, KycDocument, OtpCode, User


class OtpCodeModelTests(TestCase):
    """CDC 3.1 : OTP à 6 chiffres, valable 10 minutes, 3 tentatives maximum."""

    def test_issue_returns_six_digit_code(self):
        _, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_correct_code_verifies_once(self):
        otp, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        self.assertTrue(otp.verify(code))
        # Usage unique : une deuxième vérification du même code échoue.
        self.assertFalse(otp.verify(code))

    def test_wrong_code_is_rejected_and_counts_as_attempt(self):
        otp, _ = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        self.assertFalse(otp.verify('000000'))
        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 1)

    def test_max_three_attempts(self):
        otp, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        for _ in range(OtpCode.MAX_ATTEMPTS):
            otp.verify('000000')
        # Même le bon code est refusé au-delà de la limite de tentatives.
        self.assertFalse(otp.verify(code))

    def test_expired_code_is_rejected(self):
        otp, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        otp.expires_at = timezone.now() - timedelta(seconds=1)
        otp.save(update_fields=['expires_at'])
        self.assertFalse(otp.verify(code))

    def test_issuing_new_code_invalidates_previous_one(self):
        otp1, code1 = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        otp1.refresh_from_db()
        self.assertTrue(otp1.is_used)
        self.assertFalse(otp1.verify(code1))


class RegistrationApiTests(APITestCase):
    def test_register_by_email_does_not_require_otp(self):
        response = self.client.post(reverse('register'), {
            'email': 'alice@example.com',
            'password': 'un-mot-de-passe-solide',
            'full_name': 'Alice',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(User.objects.filter(email='alice@example.com').exists())

    def test_register_by_phone_without_otp_is_rejected(self):
        response = self.client.post(reverse('register'), {
            'phone': '+243822222222',
            'password': 'un-mot-de-passe-solide',
            'full_name': 'Bob',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(phone='+243822222222').exists())

    def test_register_by_phone_with_valid_otp_succeeds(self):
        phone = '+243822222223'
        _, code = OtpCode.issue(phone, OtpCode.PURPOSE_REGISTER)
        response = self.client.post(reverse('register'), {
            'phone': phone,
            'otp_code': code,
            'password': 'un-mot-de-passe-solide',
            'full_name': 'Carole',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(phone=phone)
        self.assertTrue(user.phone_verified)

    def test_register_by_phone_with_wrong_otp_is_rejected(self):
        phone = '+243822222224'
        OtpCode.issue(phone, OtpCode.PURPOSE_REGISTER)
        response = self.client.post(reverse('register'), {
            'phone': phone,
            'otp_code': '000000',
            'password': 'un-mot-de-passe-solide',
            'full_name': 'David',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(phone=phone).exists())


class LoginApiTests(APITestCase):
    def setUp(self):
        self.password = 'un-mot-de-passe-solide'
        self.email_user = User.objects.create_user(email='eve@example.com', password=self.password, full_name='Eve')
        self.phone_user = User.objects.create_user(
            phone='+243833333333', password=self.password, full_name='Farid',
        )

    def test_login_with_email(self):
        response = self.client.post(reverse('token_obtain_pair'), {
            'email': 'eve@example.com', 'password': self.password,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('access', response.data)

    def test_login_with_phone(self):
        response = self.client.post(reverse('token_obtain_pair'), {
            'phone': '+243833333333', 'password': self.password,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn('access', response.data)

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post(reverse('token_obtain_pair'), {
            'email': 'eve@example.com', 'password': 'mauvais-mot-de-passe',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone='+243844444444', password='ancien-mot-de-passe', full_name='Grace',
        )

    def test_reset_with_valid_otp(self):
        _, code = OtpCode.issue(self.user.phone, OtpCode.PURPOSE_PASSWORD_RESET)
        response = self.client.post(reverse('password_reset_confirm'), {
            'phone': self.user.phone, 'code': code, 'new_password': 'nouveau-mot-de-passe',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('nouveau-mot-de-passe'))

    def test_reset_with_invalid_otp_is_rejected(self):
        OtpCode.issue(self.user.phone, OtpCode.PURPOSE_PASSWORD_RESET)
        response = self.client.post(reverse('password_reset_confirm'), {
            'phone': self.user.phone, 'code': '000000', 'new_password': 'nouveau-mot-de-passe',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('ancien-mot-de-passe'))


def _make_image_bytes(fmt):
    import io
    from PIL import Image

    buffer = io.BytesIO()
    Image.new('RGB', (8, 8), (10, 20, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


PNG_BYTES = _make_image_bytes('PNG')
PDF_BYTES = b'%PDF-1.4\n' + b'0' * 64
JPEG_BYTES = _make_image_bytes('JPEG')


def kyc_upload(content=PNG_BYTES, name='piece.png', content_type='image/png'):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content, content_type=content_type)


def make_kyc_reviewer(email, staff=True):
    """Compte avec la permission dédiée identity.review_kycdocument."""
    from django.contrib.auth.models import Permission

    user = User.objects.create_user(email=email, password='x', full_name='Examinateur', is_staff=staff)
    user.user_permissions.add(Permission.objects.get(codename='review_kycdocument'))
    return user


class KycDocumentApiTests(APITestCase):
    def setUp(self):
        self.business_user = User.objects.create_user(
            email='biz@example.com', password='x', full_name='Boutique', user_type='ENTREPRISE',
        )
        self.business_profile = BusinessProfile.objects.create(
            user=self.business_user, business_name='Ma Boutique',
        )
        self.admin = make_kyc_reviewer('admin@example.com')

    def test_non_business_user_cannot_submit_kyc(self):
        user = User.objects.create_user(email='particulier@example.com', password='x', full_name='Particulier')
        self.client.force_authenticate(user)
        response = self.client.post(reverse('kyc_documents'), {'document_type': KycDocument.DOC_RCCM})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_validate_kyc_document(self):
        doc = KycDocument.objects.create(
            business_profile=self.business_profile, document_type=KycDocument.DOC_RCCM,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse('kyc_decision', args=[doc.pk]), {'decision': KycDocument.STATUS_VALIDE},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        doc.refresh_from_db()
        self.assertEqual(doc.status, KycDocument.STATUS_VALIDE)

    def test_kyc_decision_writes_an_audit_log(self):
        from apps.moderation.models import AuditLog

        doc = KycDocument.objects.create(
            business_profile=self.business_profile, document_type=KycDocument.DOC_RCCM,
        )
        self.client.force_authenticate(self.admin)
        self.client.post(reverse('kyc_decision', args=[doc.pk]), {'decision': KycDocument.STATUS_VALIDE})
        self.assertTrue(AuditLog.objects.filter(action='KYC_VALIDE', actor=self.admin).exists())

    def test_non_admin_cannot_access_review_queue(self):
        self.client.force_authenticate(self.business_user)
        response = self.client.get(reverse('kyc_review_queue'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_self_declare_business_verified(self):
        self.client.force_authenticate(self.business_user)
        response = self.client.patch(reverse('user_me'), {
            'business_profile': {'business_name': 'Ma Boutique', 'is_verified': True},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.business_profile.refresh_from_db()
        self.assertFalse(self.business_profile.is_verified)

    def test_business_verified_once_all_required_documents_validated(self):
        for doc_type in (KycDocument.DOC_RCCM, KycDocument.DOC_ID_NATIONALE, KycDocument.DOC_PIECE_GERANT):
            doc = KycDocument.objects.create(business_profile=self.business_profile, document_type=doc_type)
            self.client.force_authenticate(self.admin)
            self.client.post(reverse('kyc_decision', args=[doc.pk]), {'decision': KycDocument.STATUS_VALIDE})
        self.business_profile.refresh_from_db()
        self.assertTrue(self.business_profile.is_verified)


class OtpCleanupCommandTests(TestCase):
    def test_only_expired_codes_are_deleted(self):
        from django.core.management import call_command

        expired, _ = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        expired.expires_at = timezone.now() - timedelta(minutes=1)
        expired.save(update_fields=['expires_at'])
        valid, _ = OtpCode.issue('+243822222222', OtpCode.PURPOSE_REGISTER)

        call_command('purge_otp_codes', verbosity=0)

        self.assertFalse(OtpCode.objects.filter(pk=expired.pk).exists())
        self.assertTrue(OtpCode.objects.filter(pk=valid.pk).exists())


class UuidAndCatalogReferenceTests(APITestCase):
    """ADR 0002 : clés UUID, localisation et catégories référencées par UUID."""

    def setUp(self):
        self.city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=self.city, name='Gombe')
        self.category = Category.objects.create(name='Mode', slug='mode')

    def register(self, **extra):
        data = {'email': 'alice@example.com', 'password': 'un-mot-de-passe-solide', 'full_name': 'Alice'}
        data.update(extra)
        return self.client.post(reverse('register'), data, format='json')

    def test_user_id_is_uuid_string_in_api(self):
        response = self.register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsInstance(uuid.UUID(response.data['id']), uuid.UUID)

    def test_register_with_city_and_commune_returns_names(self):
        response = self.register(ville=str(self.city.id), commune=str(self.commune.id))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['ville'], str(self.city.id))
        self.assertEqual(response.data['ville_name'], 'Kinshasa')
        self.assertEqual(response.data['commune_name'], 'Gombe')
        self.assertEqual(User.objects.get(email='alice@example.com').city_id, self.city.id)

    def test_register_rejects_unknown_or_malformed_city(self):
        self.assertEqual(self.register(ville=str(uuid.uuid4())).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.register(ville='12').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.register(commune=str(uuid.uuid4())).status_code, status.HTTP_400_BAD_REQUEST)

    def test_business_categories_stored_as_uuid_and_validated(self):
        response = self.register(
            user_type='ENTREPRISE',
            business_profile={'business_name': 'Chez Alice', 'categories': [str(self.category.id)]},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['business_profile']['categories'], [str(self.category.id)])
        profile = BusinessProfile.objects.get(business_name='Chez Alice')
        self.assertEqual(profile.category_ids, [self.category.id])

        bad = self.register(
            email='bob@example.com', user_type='ENTREPRISE',
            business_profile={'business_name': 'Chez Bob', 'categories': [str(uuid.uuid4())]},
        )
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_business_list_has_no_query_per_user_for_catalog(self):
        for i in range(3):
            user = User.objects.create_user(
                email=f'b{i}@example.com', password='x', full_name=f'B{i}', user_type='ENTREPRISE',
                city_id=self.city.id, commune_id=self.commune.id,
            )
            profile = BusinessProfile.objects.create(user=user, business_name=f'Boutique {i}')
            profile.set_category_ids([self.category.id])
        with self.assertNumQueries(5):  # total, utilisateurs, catégories, villes, communes : indépendant du nombre de profils
            response = self.client.get(reverse('business_list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['ville_name'], 'Kinshasa')

    def test_kyc_urls_use_uuid(self):
        admin = make_kyc_reviewer('admin@example.com')
        self.client.force_authenticate(admin)
        response = self.client.post(
            reverse('kyc_decision', args=[uuid.uuid4()]), {'decision': 'VALIDE'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        # Un identifiant entier ne correspond plus à aucune route.
        self.assertEqual(
            self.client.post('/api/accounts/kyc/documents/1/decision/', {'decision': 'VALIDE'}).status_code,
            status.HTTP_404_NOT_FOUND,
        )


class PublicBusinessListTests(APITestCase):
    """Règle 10 : la liste publique des entreprises n'expose aucune donnée personnelle."""

    FORBIDDEN_KEYS = {
        'email', 'phone', 'phone_verified', 'date_joined', 'nif', 'full_name', 'password',
        'ville', 'commune', 'business_profile', 'user_type', 'photo',
    }

    def make_business(self, n, **extra):
        user = User.objects.create_user(
            email=f'biz{n}@example.com', phone=f'+24381000000{n}', password='x',
            full_name=f'Personne Privée {n}', user_type='ENTREPRISE', **extra,
        )
        BusinessProfile.objects.create(user=user, business_name=f'Boutique {n}', bio='Vente de pagnes', nif='A123456')
        return user

    def test_only_whitelisted_keys_are_exposed(self):
        self.make_business(1)
        response = self.client.get(reverse('business_list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data['results'][0]
        self.assertEqual(
            set(item),
            {'id', 'business_name', 'logo', 'bio', 'categories', 'ville_name', 'commune_name', 'is_verified'},
        )
        self.assertFalse(self.FORBIDDEN_KEYS & set(item))
        raw = response.content.decode()
        for secret in ('biz1@example.com', '+243810000001', 'A123456', 'Personne Privée'):
            self.assertNotIn(secret, raw)

    def test_inactive_users_and_profileless_users_are_hidden(self):
        banned = self.make_business(1)
        banned.is_active = False
        banned.save(update_fields=['is_active'])
        User.objects.create_user(email='noprofile@example.com', password='x', full_name='X', user_type='ENTREPRISE')
        self.make_business(2)
        names = [i['business_name'] for i in self.client.get(reverse('business_list')).data['results']]
        self.assertEqual(names, ['Boutique 2'])

    def test_list_is_paginated_and_search_ignores_personal_name(self):
        for n in range(1, 4):
            self.make_business(n)
        data = self.client.get(reverse('business_list'), {'page_size': 2}).data
        self.assertEqual((data['count'], len(data['results'])), (3, 2))
        self.assertIsNotNone(data['next'])
        self.assertEqual(self.client.get(reverse('business_list'), {'search': 'Boutique 2'}).data['count'], 1)
        # Le nom de la personne n'est pas indexé par la recherche publique.
        self.assertEqual(self.client.get(reverse('business_list'), {'search': 'Privée'}).data['count'], 0)


class BusinessVerifiedFilterTests(APITestCase):
    def make_business(self, n):
        user = User.objects.create_user(
            email=f'biz{n}@example.com', phone=f'+24381000000{n}', password='x',
            full_name=f'Personne {n}', user_type='ENTREPRISE',
        )
        BusinessProfile.objects.create(user=user, business_name=f'Boutique {n}', bio='Vente')
        return user

    def setUp(self):
        self.verified = self.make_business(1)
        self.plain = self.make_business(2)
        BusinessProfile.objects.filter(user=self.verified).update(is_verified=True)

    def names(self, value):
        response = self.client.get(reverse('business_list'), {'is_verified': value})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return [i['business_name'] for i in response.data['results']]

    def test_filter_true_and_false(self):
        self.assertEqual(self.names('true'), ['Boutique 1'])
        self.assertEqual(self.names('FALSE'), ['Boutique 2'])
        self.assertEqual(len(self.client.get(reverse('business_list')).data['results']), 2)

    def test_invalid_value_is_rejected(self):
        for value in ('1', 'yes', 'oui', ''):
            response = self.client.get(reverse('business_list'), {'is_verified': value})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, value)
            self.assertIn('is_verified', response.data)

    def test_keys_and_pagination_unchanged(self):
        response = self.client.get(reverse('business_list'), {'is_verified': 'true', 'page_size': 1})
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(
            set(response.data['results'][0]),
            {'id', 'business_name', 'logo', 'bio', 'categories', 'ville_name', 'commune_name', 'is_verified'},
        )


class ProfileUpdateSecurityTests(APITestCase):
    def test_patch_me_cannot_set_password(self):
        user = User.objects.create_user(email='a@example.com', password='ancien-mot-de-passe-1', full_name='A')
        self.client.force_authenticate(user)
        for method in (self.client.patch, self.client.put):
            response = method(reverse('user_me'), {'password': 'nouveau', 'full_name': 'A', 'email': 'a@example.com'})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('password', response.data)
        user.refresh_from_db()
        self.assertTrue(user.check_password('ancien-mot-de-passe-1'))

    def test_patch_me_still_updates_profile(self):
        user = User.objects.create_user(email='a@example.com', password='x', full_name='A')
        self.client.force_authenticate(user)
        response = self.client.patch(reverse('user_me'), {'full_name': 'Alice'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.full_name, 'Alice')


class SessionRevocationTests(APITestCase):
    PASSWORD = 'mot-de-passe-solide-42'

    def setUp(self):
        self.user = User.objects.create_user(email='s@example.com', password=self.PASSWORD, full_name='S')

    def login(self):
        response = self.client.post(reverse('token_obtain_pair'), {'email': 's@example.com', 'password': self.PASSWORD})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def refresh_status(self, refresh):
        return self.client.post(reverse('token_refresh'), {'refresh': refresh}).status_code

    def test_logout_blacklists_the_refresh_token(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.post(reverse('logout'), {'refresh': tokens['refresh']})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.refresh_status(tokens['refresh']), status.HTTP_401_UNAUTHORIZED)

    def test_logout_works_without_access_token(self):
        tokens = self.login()
        response = self.client.post(reverse('logout'), {'refresh': tokens['refresh']})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.refresh_status(tokens['refresh']), status.HTTP_401_UNAUTHORIZED)

    def test_logout_works_with_expired_access_token(self):
        from rest_framework_simplejwt.tokens import AccessToken
        tokens = self.login()
        expired = AccessToken(tokens['access'])
        expired.set_exp(from_time=timezone.now() - timedelta(hours=1), lifetime=timedelta(minutes=1))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {expired}')
        response = self.client.post(reverse('logout'), {'refresh': tokens['refresh']})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.refresh_status(tokens['refresh']), status.HTTP_401_UNAUTHORIZED)

    def test_logout_is_uniform_for_bad_tokens_and_400_when_missing(self):
        tokens = self.login()
        self.assertEqual(self.client.post(reverse('logout'), {}).status_code, 400)
        self.assertEqual(self.client.post(reverse('logout'), {'refresh': ''}).status_code, 400)
        self.assertEqual(self.client.post(reverse('logout'), {'refresh': ['x']}, format='json').status_code, 400)
        forged = self.client.post(reverse('logout'), {'refresh': 'abc'})
        self.assertEqual((forged.status_code, forged.data), (200, {'message': "Déconnecté."}))
        self.client.post(reverse('logout'), {'refresh': tokens['refresh']})
        again = self.client.post(reverse('logout'), {'refresh': tokens['refresh']})  # déjà révoqué
        self.assertEqual((again.status_code, again.data), (200, {'message': "Déconnecté."}))

    @override_settings(CACHES={'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'logout-throttle'}})
    def test_logout_is_throttled_per_ip(self):
        cache.clear()
        codes = [self.client.post(reverse('logout'), {'refresh': 'abc'}).status_code for _ in range(61)]
        self.assertEqual(set(codes[:60]), {200})
        self.assertEqual(codes[60], status.HTTP_429_TOO_MANY_REQUESTS)
        cache.clear()

    def test_logout_all_revokes_every_session(self):
        first, second = self.login(), self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {first['access']}")
        response = self.client.post(reverse('logout_all'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['revoked'], 2)
        self.assertEqual(self.refresh_status(first['refresh']), status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.refresh_status(second['refresh']), status.HTTP_401_UNAUTHORIZED)

    def test_logout_all_requires_authentication(self):
        self.assertEqual(self.client.post(reverse('logout_all')).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_revokes_sessions(self):
        tokens = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.post(reverse('change_password'), {
            'old_password': self.PASSWORD, 'new_password': 'un-autre-mot-de-passe-91',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.refresh_status(tokens['refresh']), status.HTTP_401_UNAUTHORIZED)

    def test_password_reset_revokes_sessions(self):
        phone = '+243811111111'
        User.objects.filter(pk=self.user.pk).update(phone=phone)
        tokens = self.login()
        _, code = OtpCode.issue(phone, OtpCode.PURPOSE_PASSWORD_RESET)
        self.client.credentials()
        response = self.client.post(reverse('password_reset_confirm'), {
            'phone': phone, 'code': code, 'new_password': 'reinitialise-solide-77',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.refresh_status(tokens['refresh']), status.HTTP_401_UNAUTHORIZED)


class TokenLifetimeTests(APITestCase):
    def test_access_15_minutes_refresh_7_days(self):
        user = User.objects.create_user(email='t@example.com', password='x', full_name='T')
        token = RefreshToken.for_user(user)
        self.assertEqual(token.access_token['exp'] - token.access_token['iat'], 15 * 60)
        self.assertEqual(token['exp'] - token['iat'], 7 * 24 * 3600)


class PasswordPolicyTests(APITestCase):
    def register(self, password, **extra):
        data = {'email': 'alice@example.com', 'password': password, 'full_name': 'Alice Martin'}
        data.update(extra)
        return self.client.post(reverse('register'), data)

    def test_registration_rejects_weak_passwords(self):
        for weak in ('court1', 'motdepasse', '1234567890123', 'alice@example.com'):
            response = self.register(weak)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, weak)
            self.assertIn('password', response.data, weak)
        self.assertFalse(User.objects.filter(email='alice@example.com').exists())

    def test_registration_rejects_blank_password(self):
        response = self.register('   ')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_registration_accepts_strong_password(self):
        self.assertEqual(self.register('cheval-agrafe-pile-47').status_code, status.HTTP_201_CREATED)

    def test_change_password_applies_validators(self):
        user = User.objects.create_user(email='c@example.com', password='ancien-solide-4242', full_name='C')
        self.client.force_authenticate(user)
        for weak in (None, '', 'abc', '12345678901'):
            response = self.client.post(
                reverse('change_password'), {'old_password': 'ancien-solide-4242', 'new_password': weak},
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, weak)
            self.assertIn('error', response.data)
        user.refresh_from_db()
        self.assertTrue(user.check_password('ancien-solide-4242'))

    def test_reset_applies_validators_and_keeps_the_otp(self):
        user = User.objects.create_user(
            phone='+243822222222', password='ancien-solide-4242', full_name='R',
        )
        otp, code = OtpCode.issue(user.phone, OtpCode.PURPOSE_PASSWORD_RESET)
        for weak in ('abc', '12345678901', ''):
            response = self.client.post(reverse('password_reset_confirm'), {
                'phone': user.phone, 'code': code, 'new_password': weak,
            })
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, weak)
        otp.refresh_from_db()
        self.assertFalse(otp.is_used)
        ok = self.client.post(reverse('password_reset_confirm'), {
            'phone': user.phone, 'code': code, 'new_password': 'cheval-agrafe-pile-47',
        })
        self.assertEqual(ok.status_code, status.HTTP_200_OK)


LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'otp-tests'}}


class OtpGenerationAndAtomicityTests(TestCase):
    def test_code_is_generated_with_secrets(self):
        with mock.patch('apps.identity.models.secrets') as fake_secrets:
            fake_secrets.choice.return_value = '7'
            _, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        self.assertEqual(code, '777777')
        self.assertEqual(fake_secrets.choice.call_count, OtpCode.CODE_LENGTH)

    def test_attempt_counter_is_atomic_across_stale_instances(self):
        otp, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        first, second = OtpCode.objects.get(pk=otp.pk), OtpCode.objects.get(pk=otp.pk)
        for _ in range(2):
            self.assertFalse(first.verify('000000'))
            self.assertFalse(second.verify('000000'))
        otp.refresh_from_db()
        # 4 essais depuis deux copies périmées : la base n'en décompte jamais plus de 3.
        self.assertEqual(otp.attempts, OtpCode.MAX_ATTEMPTS)
        self.assertFalse(second.verify(code))

    def test_code_is_single_use_across_stale_instances(self):
        otp, code = OtpCode.issue('+243811111111', OtpCode.PURPOSE_REGISTER)
        first, second = OtpCode.objects.get(pk=otp.pk), OtpCode.objects.get(pk=otp.pk)
        self.assertTrue(first.verify(code))
        self.assertFalse(second.verify(code))


@override_settings(CACHES=LOCMEM_CACHE)
class OtpRequestApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.existing = User.objects.create_user(phone='+243811111111', password='x', full_name='E')

    def request_code(self, phone, purpose, **extra):
        return self.client.post(reverse('otp_request'), {'phone': phone, 'purpose': purpose}, **extra)

    def test_responses_are_identical_whether_or_not_the_account_exists(self):
        with mock.patch('apps.identity.views.send_otp_sms') as sms:
            for purpose in ('LOGIN', 'PASSWORD_RESET', 'REGISTER'):
                known = self.request_code('+243811111111', purpose, REMOTE_ADDR='10.0.0.1')
                unknown = self.request_code('+243899999999', purpose, REMOTE_ADDR='10.0.0.2')
                self.assertEqual(known.status_code, status.HTTP_200_OK, purpose)
                self.assertEqual(known.status_code, unknown.status_code, purpose)
                self.assertEqual(known.data, unknown.data, purpose)
        # Seules les demandes cohérentes déclenchent un SMS : LOGIN et RESET (compte connu) + REGISTER (inconnu).
        self.assertEqual(sms.call_count, 3)

    def test_invalid_input_is_still_rejected(self):
        self.assertEqual(self.request_code('12345', 'LOGIN').status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.request_code('+243811111111', 'AUTRE').status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(reverse('otp_request'), {'phone': 12345, 'purpose': 'LOGIN'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_phone_throttle_is_per_number_and_ip_with_a_wider_daily_cap_per_number(self):
        with mock.patch('apps.identity.views.send_otp_sms'):
            for _ in range(3):
                self.assertEqual(self.request_code('+243811111111', 'LOGIN', REMOTE_ADDR='10.0.1.1').status_code, 200)
            blocked = self.request_code('+243811111111', 'LOGIN', REMOTE_ADDR='10.0.1.1')
            self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            # Un tiers, depuis une autre IP, n'a pas épuisé le quota horaire de la victime.
            self.assertEqual(self.request_code('+243811111111', 'LOGIN', REMOTE_ADDR='10.0.1.2').status_code, 200)
            # Un autre numéro n'est pas affecté.
            self.assertEqual(self.request_code('+243822222222', 'LOGIN', REMOTE_ADDR='10.0.1.1').status_code, 200)

    def test_daily_cap_per_number_counts_all_addresses(self):
        with mock.patch('apps.identity.views.send_otp_sms'):
            codes = [
                self.request_code('+243833333333', 'LOGIN', REMOTE_ADDR=f'10.0.3.{i}').status_code for i in range(11)
            ]
        self.assertEqual(codes[:10], [200] * 10)
        self.assertEqual(codes[10], status.HTTP_429_TOO_MANY_REQUESTS)

    def test_number_spelling_variants_share_the_otp_throttles(self):
        with mock.patch('apps.identity.views.send_otp_sms'):
            for variant in ('+243811111111', '243811111111', '+243 811 111 111'):
                self.request_code(variant, 'LOGIN', REMOTE_ADDR='10.0.4.1')
            blocked = self.request_code('+243811111111', 'LOGIN', REMOTE_ADDR='10.0.4.1')
        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class CityCommuneConsistencyAndRegistrationTests(APITestCase):
    def setUp(self):
        self.kin = City.objects.create(name='Kinshasa')
        self.gombe = Commune.objects.create(city=self.kin, name='Gombe')
        self.other_city = City.objects.create(name='Matadi')

    def register(self, **extra):
        data = {'email': 'alice@example.com', 'password': 'cheval-agrafe-pile-47', 'full_name': 'Alice'}
        data.update(extra)
        return self.client.post(reverse('register'), data, format='json')

    def test_commune_must_belong_to_the_city(self):
        ok = self.register(ville=str(self.kin.id), commune=str(self.gombe.id))
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED, ok.data)
        bad = self.register(email='b@example.com', ville=str(self.other_city.id), commune=str(self.gombe.id))
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('commune', bad.data)

    def test_commune_requires_a_city(self):
        response = self.register(commune=str(self.gombe.id))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('ville', response.data)

    def test_patch_checks_against_current_values(self):
        user = User.objects.create_user(
            email='p@example.com', password='x', full_name='P', city_id=self.kin.id, commune_id=self.gombe.id,
        )
        self.client.force_authenticate(user)
        response = self.client.patch(reverse('user_me'), {'ville': str(self.other_city.id)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.patch(reverse('user_me'), {'ville': None, 'commune': None}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_registration_without_email_or_phone_is_400_not_500(self):
        response = self.client.post(reverse('register'), {'password': 'cheval-agrafe-pile-47', 'full_name': 'X'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(
            reverse('register'), {'email': '', 'password': 'cheval-agrafe-pile-47', 'full_name': 'X'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_me_with_unchanged_phone_does_not_ask_for_otp(self):
        user = User.objects.create_user(phone='+243811111111', password='x', full_name='P')
        self.client.force_authenticate(user)
        response = self.client.patch(
            reverse('user_me'), {'phone': '+243811111111', 'full_name': 'Nouveau'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # Un numéro différent exige toujours un code.
        response = self.client.patch(reverse('user_me'), {'phone': '+243822222222'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('otp_code', response.data)

    def test_sms_gateway_failure_keeps_a_uniform_200(self):
        User.objects.create_user(phone='+243811111111', password='x', full_name='E')
        with mock.patch('apps.identity.views.send_otp_sms', side_effect=NotImplementedError('pas de passerelle')), \
                self.assertLogs('apps.identity.views', level='ERROR'):
            known = self.client.post(reverse('otp_request'), {'phone': '+243811111111', 'purpose': 'LOGIN'})
            unknown = self.client.post(reverse('otp_request'), {'phone': '+243899999999', 'purpose': 'LOGIN'})
        self.assertEqual((known.status_code, unknown.status_code), (200, 200))
        self.assertEqual(known.data, unknown.data)


class RevokeAllSessionsTests(TestCase):
    def test_revocation_is_idempotent_and_tolerates_already_blacklisted_tokens(self):
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

        user = User.objects.create_user(email='s@example.com', password='x', full_name='S')
        refreshes = [RefreshToken.for_user(user) for _ in range(3)]
        refreshes[0].blacklist()  # déjà révoqué par une autre requête
        from .services import revoke_all_sessions

        self.assertEqual(revoke_all_sessions(user), 2)
        self.assertEqual(revoke_all_sessions(user), 0)
        self.assertEqual(
            BlacklistedToken.objects.filter(token__user=user).count(), OutstandingToken.objects.filter(user=user).count(),
        )


class PhoneValidatorTests(TestCase):
    def test_trailing_newline_and_unicode_digits_are_rejected(self):
        from django.core.exceptions import ValidationError

        from .models import phone_validator

        phone_validator('+243811111111')
        for bad in ('+243811111111\n', '+243811111111 ', '+243\u0661\u0662\u0663456789', '+24381111111'):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                phone_validator(bad)

    def test_otp_request_rejects_a_phone_with_trailing_newline(self):
        response = self.client.post(reverse('otp_request'), {'phone': '+243811111111\n', 'purpose': 'LOGIN'})
        self.assertEqual(response.status_code, 400)


class CorsExposeHeadersTests(TestCase):
    def test_retry_after_is_exposed_without_widening_origins(self):
        from django.conf import settings
        self.assertEqual(settings.CORS_EXPOSE_HEADERS, ['Retry-After'])
        self.assertNotIn('*', settings.CORS_ALLOWED_ORIGINS)


class PhoneExistenceOracleTests(APITestCase):
    """Un numéro déjà inscrit ne se distingue pas d'un numéro libre (pas d'oracle d'existence)."""

    TAKEN = '+243830000001'
    FREE = '+243830000002'

    def setUp(self):
        self.owner = User.objects.create_user(phone=self.TAKEN, password='x', full_name='Titulaire')

    def register(self, phone, **extra):
        payload = {'phone': phone, 'password': 'un-mot-de-passe-solide', 'full_name': 'Zoé'}
        payload.update(extra)
        return self.client.post(reverse('register'), payload)

    def test_taken_and_free_phone_without_otp_give_the_same_answer(self):
        taken, free = self.register(self.TAKEN), self.register(self.FREE)
        self.assertEqual(taken.status_code, 400)
        self.assertEqual(taken.data, free.data)
        self.assertNotIn('phone', taken.data)

    def test_taken_and_free_phone_with_wrong_otp_give_the_same_answer(self):
        OtpCode.issue(self.FREE, OtpCode.PURPOSE_REGISTER)
        taken, free = self.register(self.TAKEN, otp_code='000000'), self.register(self.FREE, otp_code='000000')
        self.assertEqual(taken.status_code, 400)
        self.assertEqual(taken.data, free.data)

    def test_taken_phone_with_a_valid_otp_is_refused_neutrally(self):
        # Cas limite (course) : un code valide existe pour un numéro déjà pris.
        _, code = OtpCode.issue(self.TAKEN, OtpCode.PURPOSE_REGISTER)
        response = self.register(self.TAKEN, otp_code=code)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {'otp_code': ["Code invalide ou expiré."]})
        self.assertEqual(User.objects.filter(phone=self.TAKEN).count(), 1)

    def test_invalid_phone_format_is_still_rejected(self):
        self.assertIn('phone', self.register('abc').data)

    def test_changing_to_a_third_party_number_looks_like_a_free_number(self):
        me = User.objects.create_user(email='moi@example.com', password='x', full_name='Moi')
        self.client.force_authenticate(me)
        taken = self.client.patch(reverse('user_me'), {'phone': self.TAKEN, 'otp_code': '000000'})
        free = self.client.patch(reverse('user_me'), {'phone': self.FREE, 'otp_code': '000000'})
        self.assertEqual(taken.status_code, 400)
        self.assertEqual(taken.data, free.data)
        me.refresh_from_db()
        self.assertIsNone(me.phone)


class RequesterDisplayNameTests(TestCase):
    def test_normal_names(self):
        from . import services
        self.assertEqual(services.requester_display_name('Marie Kabila'), 'Marie K.')
        self.assertEqual(services.requester_display_name("Jean-Luc N'Dour"), "Jean-Luc N.")
        self.assertEqual(services.requester_display_name('Marie'), 'Marie')

    def test_digits_urls_and_symbols_are_removed(self):
        from . import services
        self.assertEqual(services.requester_display_name('Appelez 0812345678 Marie'), 'Appelez M.')
        self.assertEqual(services.requester_display_name('http://x.cd/a Paul'), 'httpxcda P.')
        self.assertEqual(services.requester_display_name('0812345678'), 'Un visiteur')
        self.assertEqual(services.requester_display_name('+243 81 23 45'), 'Un visiteur')

    def test_first_word_is_capped_and_empty_falls_back(self):
        from . import services
        self.assertEqual(services.requester_display_name('A' * 50 + ' Zola'), 'A' * 20 + ' Z.')
        for empty in (None, '', '   ', '123 456', '--'):
            self.assertEqual(services.requester_display_name(empty), 'Un visiteur')
