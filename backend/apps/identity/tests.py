from datetime import timedelta

from django.test import TestCase
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


class KycDocumentApiTests(APITestCase):
    def setUp(self):
        self.business_user = User.objects.create_user(
            email='biz@example.com', password='x', full_name='Boutique', user_type='ENTREPRISE',
        )
        self.business_profile = BusinessProfile.objects.create(
            user=self.business_user, business_name='Ma Boutique',
        )
        self.admin = User.objects.create_user(
            email='admin@example.com', password='x', full_name='Admin', is_staff=True,
        )

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

        call_command('cleanup_otp_codes', verbosity=0)

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
        admin = User.objects.create_user(email='admin@example.com', password='x', full_name='Admin', is_staff=True)
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
        'ville', 'commune', 'business_profile', 'user_type', 'photo', 'trust_score',
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

    def test_logout_requires_auth_and_valid_own_token(self):
        tokens = self.login()
        self.assertEqual(self.client.post(reverse('logout'), {'refresh': tokens['refresh']}).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.post(reverse('logout'), {}).status_code, 400)
        self.assertEqual(self.client.post(reverse('logout'), {'refresh': 'abc'}).status_code, 400)
        other = User.objects.create_user(email='o@example.com', password='x', full_name='O')
        other_refresh = str(RefreshToken.for_user(other))
        self.assertEqual(self.client.post(reverse('logout'), {'refresh': other_refresh}).status_code, 400)
        self.assertEqual(self.refresh_status(other_refresh), status.HTTP_200_OK)

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
