"""Recette du lot 0 (L0-05 à L0-20) : tests d'intégration de bout en bout, par l'API.

Trois familles :
- contrat front <-> backend : clés, nullabilité et formats attendus par `connect-grow/src/api/types.ts` ;
- règles verrouillées du client (CLAUDE.md §4) : 4 (notes hors classement), 10 (données privées),
  12 (journal d'audit) ;
- outbox (ADR 0003) : diffusion, idempotence, panne d'un abonné, relance, purge.

Les anomalies « R0-xx » du rapport de recette ont été corrigées en L0-21 : leurs tests sont désormais
des tests ordinaires, qui verrouillent la correction.
"""
import io
import json
import re
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.common.factories import make_test_image
from apps.identity.models import BusinessProfile, KycDocument, Membership, Organization, OtpCode, User
from apps.marketplace import services as marketplace_services
from apps.marketplace.models import ContactEvent, Offer
from apps.messaging.models import Conversation, Message
from apps.moderation.models import AuditLog, Report, Sanction
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxDelivery, OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now
from apps.reviews.models import Review, ReviewSettings
from apps.reviews.tests import GOOD, REVIEWS_URL, ReviewsTestBase

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
# Date ISO 8601 avec décalage horaire (jamais de date « naïve »).
DATE_RE = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$')
PASSWORD = 'Recette-mdp-2026!'
POSTS_URL = '/api/marketplace/posts/'
REPORTS_URL = '/api/moderation/reports/'
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'recette-lot0'}}

# --- Miroir de connect-grow/src/api/types.ts : {clé: types acceptés} ; `?` = optionnelle côté TS ---
SPEC_RATING = {'average': 'num|null', 'count': 'num'}
SPEC_SELLER = {
    'id': 'uuid', 'full_name': 'str', 'photo?': 'str|null', 'user_type': 'str', 'business_profile?': 'obj|null',
    'date_joined?': 'date',
}
SPEC_POST = {
    'id': 'uuid', 'seller': 'obj', 'seller_name?': 'str', 'category': 'uuid', 'category_name?': 'str|null',
    'commune': 'uuid', 'commune_name?': 'str|null', 'post_type': 'str', 'title': 'str', 'description': 'str',
    'price': 'str', 'currency?': 'str', 'condition?': 'str|null', 'stock?': 'num', 'is_price_negotiable?': 'bool',
    'is_exchangeable?': 'bool', 'main_image?': 'str|null', 'images?': 'list', 'is_favorited?': 'bool',
    'favorites_count?': 'num', 'views_count': 'num', 'likes_count': 'num', 'created_at': 'date', 'status?': 'str',
    'expires_at?': 'date|null', 'visibility_score?': 'num', 'visibility_rank?': 'str', 'is_trending?': 'bool',
    'is_sponsored?': 'bool', 'offer_rating': 'obj', 'seller_rating': 'obj', 'shares_count?': 'num',
}
SPEC_REVIEW = {
    'id': 'uuid', 'post': 'uuid|null', 'is_mine': 'bool', 'user_name': 'str', 'offer_rating': 'num',
    'seller_rating': 'num', 'content': 'str', 'source': 'str', 'reply_content?': 'str|null', 'reply_at?': 'date|null',
    'created_at': 'date', 'edited_at?': 'date|null', 'is_post_owner?': 'bool', 'can_edit?': 'bool',
    'contest_report_id?': 'uuid|null', 'contest_responded?': 'bool',
}
SPEC_ELIGIBILITY = {'can_review': 'bool', 'reason': 'str|null', 'available_at': 'date|null', 'review_id': 'uuid|null'}
SPEC_NOTIFICATION = {
    'id': 'uuid', 'notification_type': 'str', 'title': 'str', 'content': 'str', 'link?': 'str|null', 'is_read': 'bool',
    'created_at': 'date',
}
SPEC_KYC = {
    'id': 'uuid', 'document_type': 'str', 'download_url?': 'str|null', 'status': 'str', 'rejection_reason?': 'str',
    'created_at': 'date', 'reviewed_at?': 'date|null',
}
# Liste publique des organisations (ADR 0006, 9.2) : remplace l'ancienne liste `businesses/`.
SPEC_ORGANIZATION = {
    'id': 'uuid', 'name': 'str', 'org_type': 'str', 'description': 'str', 'logo': 'str|null',
    'city_id': 'uuid|null', 'commune_id': 'uuid|null', 'category_ids': 'list', 'verified_claims': 'list',
    'verification_summary': 'obj', 'member_since': 'date',
}
SPEC_PAGE = {'count': 'num', 'next': 'str|null', 'previous': 'str|null', 'results': 'list'}
SPEC_AUTHOR_RESPONSE = {'id': 'uuid', 'status': 'str', 'author_responded_at': 'date'}
SPEC_FAVORITE = {'id': 'uuid', 'post': 'obj', 'created_at': 'date'}


def _kind_ok(value, kind):
    return {
        'null': lambda v: v is None,
        'str': lambda v: isinstance(v, str),
        'uuid': lambda v: isinstance(v, str) and bool(UUID_RE.match(v)),
        'date': lambda v: isinstance(v, str) and bool(DATE_RE.match(v)),
        'num': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        'bool': lambda v: isinstance(v, bool),
        'list': lambda v: isinstance(v, list),
        'obj': lambda v: isinstance(v, dict),
    }[kind](value)


class ContractMixin:
    def assertShape(self, data, spec, label=''):
        """`data` respecte `spec` : clés requises présentes, types et nullabilité conformes à types.ts."""
        self.assertIsInstance(data, dict, label)
        for raw_key, kinds in spec.items():
            key = raw_key.rstrip('?')
            if key not in data:
                self.assertTrue(raw_key.endswith('?'), f'{label} : clé requise absente `{key}`')
                continue
            self.assertTrue(
                any(_kind_ok(data[key], kind) for kind in kinds.split('|')),
                f'{label} : `{key}` = {data[key]!r} incompatible avec TS `{kinds}`',
            )

    @staticmethod
    def rows(response):
        data = response.json()
        return data['results'] if isinstance(data, dict) else data


class RecetteBase(ContractMixin, ReviewsTestBase):
    """Vendeur, trois acheteurs, offre, personnel de modération et d'administration."""

    def setUp(self):
        super().setUp()
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(min_reviews_to_display=1)
        self.buyer2 = User.objects.create_user(email='buyer2@example.com', password=PASSWORD, full_name='Acheteuse Deux')
        self.moderator = User.objects.create_user(email='modo@example.com', password=PASSWORD, full_name='Modo Test')
        self.moderator.groups.add(self.group('Modérateur'))
        self.admin = User.objects.create_user(email='admin@example.com', password=PASSWORD, full_name='Admin Test')
        self.admin.groups.add(self.group('Administrateur'))

    def group(self, name):
        if not Group.objects.filter(name=name).exists():
            call_command('setup_roles', verbosity=0)
        return Group.objects.get(name=name)

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def contact_via_api(self, user, offer=None, message='Bonjour, est-ce toujours disponible ?'):
        return self.as_user(user).post(
            '/api/interactions/contacts/', {'post': str((offer or self.offer).id), 'message': message}, format='json',
        )


# =========================================================================================
# Contrat front <-> backend
# =========================================================================================

class ContractTests(RecetteBase):
    def test_post_list_and_detail_match_types_ts(self):
        self.make_review()
        for client in (APIClient(), self.as_user(self.buyer)):
            listing = client.get(POSTS_URL)
            self.assertEqual(listing.status_code, 200)
            self.assertShape(self.rows(listing)[0], SPEC_POST, 'Post (liste)')
            detail = client.get(f'{POSTS_URL}{self.offer.id}/')
            self.assertShape(detail.json(), SPEC_POST, 'Post (détail)')
            self.assertShape(detail.json()['seller'], SPEC_SELLER, 'Post.seller')
            self.assertShape(detail.json()['offer_rating'], SPEC_RATING, 'offer_rating')
            self.assertShape(detail.json()['seller_rating'], SPEC_RATING, 'seller_rating')

    def test_post_ratings_are_always_present_with_null_average_below_threshold(self):
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(min_reviews_to_display=3)
        self.make_review()
        body = APIClient().get(f'{POSTS_URL}{self.offer.id}/').json()
        self.assertEqual(body['offer_rating'], {'average': None, 'count': 1})
        self.assertEqual(body['seller_rating'], {'average': None, 'count': 1})

    def test_paginated_lists_follow_the_django_rest_envelope(self):
        for i in range(3):
            self.make_offer(self.seller, title=f'Offre numéro {i} de la liste')
        page = APIClient().get(POSTS_URL, {'page': 1, 'page_size': 2}).json()
        self.assertShape(page, SPEC_PAGE, 'Paginated<Post>')
        self.assertEqual((page['count'], len(page['results'])), (4, 2))
        self.assertIsNotNone(page['next'])
        self.assertEqual(APIClient().get(POSTS_URL, {'page': 99}).status_code, 404)

    def test_review_payloads_match_types_ts_and_never_expose_the_author(self):
        review = self.make_review()
        mine = self.as_user(self.buyer).get(REVIEWS_URL, {'post': str(self.offer.id)})
        self.assertShape(self.rows(mine)[0], SPEC_REVIEW, 'Review (auteur)')
        self.assertTrue(self.rows(mine)[0]['is_mine'])
        for client in (APIClient(), self.as_user(self.other), self.as_user(self.seller)):
            item = self.rows(client.get(REVIEWS_URL, {'post': str(self.offer.id)}))[0]
            self.assertShape(item, SPEC_REVIEW, 'Review (tiers)')
            self.assertFalse(item['is_mine'])
            self.assertIsNone(item['contest_report_id'])
            for forbidden in ('user', 'user_id', 'author', 'contact_channel', 'contact_event_id',
                              'contact_recorded_at', 'seller_context_id', 'is_hidden', 'counts_for_seller'):
                self.assertNotIn(forbidden, item)
        self.assertEqual(review.pk and str(review.pk), self.rows(mine)[0]['id'])

    def test_eligibility_payload_for_every_reason(self):
        client = self.as_user(self.buyer)
        url = REVIEWS_URL + 'eligibility/'
        result = client.get(url, {'post': str(self.offer.id)}).json()
        self.assertShape(result, SPEC_ELIGIBILITY, 'éligibilité')
        self.assertEqual((result['can_review'], result['reason']), (False, 'no_contact'))
        contact = self.make_contact()
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(delay_after_contact_hours=24)
        too_early = client.get(url, {'post': str(self.offer.id)}).json()
        self.assertShape(too_early, SPEC_ELIGIBILITY, 'éligibilité')
        self.assertEqual(too_early['reason'], 'too_early')
        self.assertIsNotNone(too_early['available_at'])
        ContactEvent.objects.filter(pk=contact.pk).update(
            created_at=timezone.now() - timedelta(hours=48), delivered_at=timezone.now() - timedelta(hours=48),
        )
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(min_account_age_hours=72)
        too_new = client.get(url, {'post': str(self.offer.id)}).json()
        self.assertEqual(too_new['reason'], 'account_too_new')
        self.assertShape(too_new, SPEC_ELIGIBILITY, 'éligibilité')
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(min_account_age_hours=0)
        self.assertEqual(client.get(url, {'post': str(self.offer.id)}).json()['can_review'], True)
        self.assertEqual(self.as_user(self.seller).get(url, {'post': str(self.offer.id)}).json()['reason'], 'own_offer')

    def test_error_bodies_carry_detail_and_code(self):
        anonymous = APIClient().get('/api/accounts/me/')
        self.assertEqual((anonymous.status_code, anonymous.json()['code']), (401, 'not_authenticated'))
        unknown = self.as_user(self.buyer).get(REVIEWS_URL + 'eligibility/', {'post': str(uuid.uuid4())})
        self.assertEqual((unknown.status_code, unknown.json()['code']), (404, 'offer_not_found'))
        no_contact = self.as_user(self.buyer).post(
            REVIEWS_URL, {'post': str(self.offer.id), **GOOD}, format='json',
        )
        self.assertEqual((no_contact.status_code, no_contact.json()['code']), (403, 'not_eligible'))
        self.assertIn('detail', no_contact.json())

    def test_dates_carry_the_kinshasa_offset(self):
        self.make_review()
        body = APIClient().get(f'{POSTS_URL}{self.offer.id}/').json()
        self.assertTrue(DATE_RE.match(body['created_at']), body['created_at'])
        self.assertTrue(body['created_at'].endswith('+01:00'), body['created_at'])
        self.assertTrue(body['seller']['date_joined'].endswith('+01:00'), body['seller']['date_joined'])

    def test_organizations_are_paginated_by_20_and_filter_on_fully_verified(self):
        for i in range(24):
            organization = Organization.objects.create(name=f'Zbiz {i:02d}', org_type='ENTREPRISE')
            if i % 3 == 0:  # les trois pièces exigées du type ENTREPRISE, toutes validées
                holder = User.objects.create_user(email=f'ent{i}@example.com', password=PASSWORD, full_name=f'Gérant {i}')
                profile = BusinessProfile.objects.create(user=holder, business_name=f'Support {i}')
                for document_type in ('RCCM', 'ID_NATIONALE', 'PIECE_GERANT'):
                    KycDocument.objects.create(
                        business_profile=profile, organization=organization, document_type=document_type,
                        status=KycDocument.STATUS_VALIDE, reviewed_at=timezone.now(),
                    )
        client = APIClient()
        first = client.get('/api/accounts/organizations/', {'search': 'Zbiz'}).json()
        self.assertShape(first, SPEC_PAGE, 'Paginated<PublicOrganization>')
        self.assertEqual((first['count'], len(first['results'])), (24, 20))
        self.assertShape(first['results'][0], SPEC_ORGANIZATION, 'PublicOrganization')
        second = client.get('/api/accounts/organizations/', {'search': 'Zbiz', 'page': 2}).json()
        self.assertEqual((len(second['results']), second['next']), (4, None))
        verified = client.get('/api/accounts/organizations/', {'search': 'Zbiz', 'fully_verified': 'true'}).json()
        self.assertEqual(verified['count'], 8)
        self.assertTrue(all(o['verification_summary']['complete'] for o in verified['results']))
        self.assertEqual(client.get('/api/accounts/organizations/', {'fully_verified': 'False'}).json()['count'], 16)
        self.assertEqual(client.get('/api/accounts/organizations/', {'fully_verified': 'peut-etre'}).status_code, 400)
        self.assertEqual(client.get('/api/accounts/businesses/').status_code, 404)  # ancienne liste supprimée

    def test_favorite_toggle_and_list_contract(self):
        client = self.as_user(self.buyer)
        self.assertEqual(client.post(f'{POSTS_URL}{self.offer.id}/favorite/').json(), {'favorited': True})
        detail = client.get(f'{POSTS_URL}{self.offer.id}/').json()
        self.assertEqual((detail['is_favorited'], detail['favorites_count']), (True, 1))
        favorites = client.get('/api/marketplace/favorites/')
        self.assertShape(self.rows(favorites)[0], SPEC_FAVORITE, 'Favorite')
        self.assertEqual(client.post(f'{POSTS_URL}{self.offer.id}/favorite/').json(), {'favorited': False})
        self.assertEqual(APIClient().post(f'{POSTS_URL}{self.offer.id}/favorite/').status_code, 401)

    def test_user_payload_allows_null_email_phone_and_catalog_names(self):
        """types.ts déclare `email: string`, `phone?: string`, `ville_name?: string` : l'API renvoie null
        pour un compte créé par téléphone (sans e-mail) ou sans localisation (anomalie R0-02, mineure).
        Ce test fige le comportement réel pour que le front ne l'ignore pas."""
        phone_user = User.objects.create_user(phone='+243812345678', password=PASSWORD, full_name='Par Téléphone')
        body = self.as_user(phone_user).get('/api/accounts/me/').json()
        self.assertIsNone(body['email'])
        self.assertIsNone(body['ville_name'])
        self.assertIsNone(body['commune_name'])
        email_user = self.as_user(self.buyer).get('/api/accounts/me/').json()
        self.assertIsNone(email_user['phone'])

    def test_profile_patch_cannot_grant_verification(self):
        """Règle 3 : la vérification ne s'achète ni ne s'auto-déclare. `me/` ne porte plus de profil entreprise
        et une organisation ne peut pas recevoir de claim par son propre PATCH."""
        owner = User.objects.create_user(email='bizz@example.com', password=PASSWORD, full_name='Gérant', phone_verified=True)
        client = self.as_user(owner)
        response = client.patch(
            '/api/accounts/me/', {'business_profile': {'business_name': 'Ma boîte', 'is_verified': True}}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BusinessProfile.objects.filter(user=owner).exists())
        created = client.post('/api/accounts/organizations/', {'name': 'Ma boîte', 'org_type': 'ENTREPRISE'}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        patched = client.patch(
            f"/api/accounts/organizations/{created.json()['id']}/",
            {'description': 'Ok', 'is_verified': True, 'verified_claims': [{'code': 'RCCM_VERIFIED'}]}, format='json',
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual(patched.json()['verification']['verified_claims'], [])
        self.assertFalse(patched.json()['verification']['summary']['complete'])

    def test_otp_throttle_returns_429_with_retry_after_and_code(self):
        with override_settings(CACHES=LOCMEM):
            from django.core.cache import cache
            cache.clear()
            client = APIClient()
            statuses = []
            with mock.patch('apps.identity.views.send_otp_sms'):
                for i in range(6):
                    response = client.post(
                        '/api/accounts/otp/request/', {'phone': f'+24381000000{i}', 'purpose': 'REGISTER'},
                        format='json', REMOTE_ADDR='10.99.0.1',
                    )
                    statuses.append(response.status_code)
            self.assertEqual(statuses, [200] * 5 + [429])
            self.assertTrue(response['Retry-After'].isdigit())
            self.assertEqual(response.json()['code'], 'throttled')
            cache.clear()

    def test_R0_01_negative_price_is_refused(self):
        """ANOMALIE R0-01 (majeure) : `Offer.price` n'a aucun validateur de minimum ; un prix négatif est
        accepté (201) et publié. Attendu : 400 sur `price`."""
        response = self.as_user(self.seller).post(POSTS_URL, {
            'post_type': 'PRODUIT', 'category': str(self.category.id), 'commune': str(self.commune.id),
            'title': 'Perceuse à prix négatif', 'description': 'Description suffisamment longue pour le CDC.',
            'price': '-5', 'currency': 'USD', 'condition': 'NEUF', 'stock': '1',
            'main_image': make_test_image(),
        }, format='multipart')
        self.assertEqual(response.status_code, 400, response.content[:200])

    def test_R0_04_negative_stock_is_refused_not_a_server_error(self):
        """ANOMALIE R0-04 (majeure) : `stock` négatif (création ou modification d'offre) déclenche
        `IntegrityError: CHECK constraint failed: stock` donc un HTTP 500. Attendu : 400 sur `stock`."""
        client = self.as_user(self.seller)
        client.raise_request_exception = False
        patched = client.patch(f'{POSTS_URL}{self.offer.id}/', {'stock': '-3'}, format='json')
        self.assertEqual(patched.status_code, 400, patched.status_code)

    def test_R0_05_login_accepts_the_email_exactly_as_registered(self):
        """ANOMALIE R0-05 (majeure) : l'inscription normalise le domaine de l'e-mail en minuscules
        (`normalize_email`) mais la connexion compare la saisie telle quelle ; le front n'abaisse pas la
        casse. Un utilisateur qui s'inscrit avec `Jean.Dupont@Example.com` ne peut plus se connecter avec ce
        même texte (401), et `jean.dupont@example.com` crée un second compte (201). Attendu : e-mail
        insensible à la casse (CLAUDE.md §5)."""
        client = APIClient()
        typed = 'Jean.Dupont@Example.com'
        self.assertEqual(client.post('/api/accounts/register/', {
            'full_name': 'Casse Test', 'password': PASSWORD, 'email': typed}, format='json').status_code, 201)
        login = client.post('/api/accounts/login/', {'email': typed, 'password': PASSWORD}, format='json')
        self.assertEqual(login.status_code, 200)

    def test_R0_05b_same_email_in_another_case_is_a_duplicate(self):
        """ANOMALIE R0-05 (suite) : `BUYER@example.com` est accepté alors que `buyer@example.com` existe."""
        response = APIClient().post('/api/accounts/register/', {
            'full_name': 'Doublon Casse', 'password': PASSWORD, 'email': 'BUYER@example.com'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_R0_06_daily_review_limit_429_carries_retry_after(self):
        """ANOMALIE R0-06 (mineure) : le 429 `daily_limit` (et `report_daily_limit`) n'a pas d'en-tête
        Retry-After alors que le front (`review-errors.ts`) prévoit un message avec délai ; la branche
        « réessayez dans N heures » est inatteignable."""
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(daily_review_limit=1)
        second = self.make_offer(self.seller, title='Deuxième offre pour la limite')
        self.contact_via_api(self.buyer)
        self.contact_via_api(self.buyer, second)
        dispatch_outbox_now()
        dispatch_outbox_now()  # remise du message = preuve de contact pour l'avis
        client = self.as_user(self.buyer)
        self.assertEqual(client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD}, format='json').status_code, 201)
        limited = client.post(REVIEWS_URL, {'post': str(second.id), **GOOD}, format='json')
        self.assertEqual((limited.status_code, limited.json()['code']), (429, 'daily_limit'))
        self.assertTrue(limited.get('Retry-After', '').isdigit())
        self.assertTrue(0 < int(limited['Retry-After']) <= 24 * 3600)

    def test_R0_07_conversation_last_message_uses_canonical_uuid_and_offset_dates(self):
        """ANOMALIE R0-07 (cosmétique) : `last_message.sender_id` est un UUID hexadécimal sans tirets et
        `last_message.created_at` est en UTC (`Z`), alors que partout ailleurs les UUID ont des tirets et les
        dates le décalage +01:00."""
        self.contact_via_api(self.buyer)
        dispatch_outbox_now()
        last = self.rows(self.as_user(self.seller).get('/api/interactions/conversations/'))[0]['last_message']
        self.assertTrue(UUID_RE.match(last['sender_id']), last['sender_id'])
        self.assertTrue(last['created_at'].endswith('+01:00'), last['created_at'])


# =========================================================================================
# Parcours complet par l'API (inscription -> avis -> recours -> décision)
# =========================================================================================

class JourneyTests(RecetteBase):
    def register_by_phone(self, phone, name='Nouvel Utilisateur', **extra):
        client = APIClient()
        with mock.patch('apps.identity.views.send_otp_sms') as sms:
            requested = client.post('/api/accounts/otp/request/', {'phone': phone, 'purpose': 'REGISTER'}, format='json')
        self.assertEqual(requested.status_code, 200)
        self.assertShape(requested.json(), {'message': 'str', 'expires_in_minutes': 'num'}, 'OTP')
        code = sms.call_args[0][1]
        body = {'full_name': name, 'password': PASSWORD, 'phone': phone, 'otp_code': code, **extra}
        return client.post('/api/accounts/register/', body, format='json'), code

    def test_register_by_otp_then_login_refresh_logout(self):
        phone = '+243811112233'
        response, code = self.register_by_phone(phone, user_type='ENTREPRISE', business_profile={'business_name': 'Atelier'})
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        # Compte unique (règle 1) : l'ancien type de compte et le profil entreprise ne sont ni lus ni renvoyés.
        self.assertNotIn('user_type', body)
        self.assertNotIn('business_profile', body)
        self.assertFalse(Organization.objects.exists())
        self.assertFalse(BusinessProfile.objects.exists())
        self.assertNotIn('password', body)
        self.assertNotIn('otp_code', body)
        self.assertTrue(body['phone_verified'])
        # Un code OTP ne sert qu'une fois.
        again = APIClient().post('/api/accounts/register/', {
            'full_name': 'Rejeu', 'password': PASSWORD, 'phone': phone, 'otp_code': code}, format='json')
        self.assertEqual(again.status_code, 400)

        client = APIClient()
        tokens = client.post('/api/accounts/login/', {'phone': phone, 'password': PASSWORD}, format='json').json()
        self.assertEqual(set(tokens), {'access', 'refresh'})
        me = client.get('/api/accounts/me/', HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(me.status_code, 200)
        self.assertIsNone(me.json()['email'])

        rotated = client.post('/api/accounts/token/refresh/', {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(set(rotated.json()), {'access', 'refresh'})
        self.assertEqual(
            client.post('/api/accounts/token/refresh/', {'refresh': tokens['refresh']}, format='json').status_code, 401,
        )
        self.assertEqual(client.post('/api/accounts/logout/', {'refresh': rotated.json()['refresh']}, format='json').status_code, 200)
        self.assertEqual(
            client.post('/api/accounts/token/refresh/', {'refresh': rotated.json()['refresh']}, format='json').status_code, 401,
        )
        self.assertEqual(client.post('/api/accounts/logout/', {}, format='json').status_code, 400)

    def test_logout_all_revokes_every_session(self):
        user = User.objects.create_user(email='multi@example.com', password=PASSWORD, full_name='Multi Appareils')
        client = APIClient()
        sessions = [client.post('/api/accounts/login/', {'email': 'multi@example.com', 'password': PASSWORD}, format='json').json()
                    for _ in range(3)]
        response = client.post(
            '/api/accounts/logout-all/', {'refresh': sessions[0]['refresh']}, format='json',
            HTTP_AUTHORIZATION=f"Bearer {sessions[0]['access']}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertShape(response.json(), {'message': 'str', 'revoked': 'num'}, 'logout-all')
        for session in sessions:
            self.assertEqual(
                client.post('/api/accounts/token/refresh/', {'refresh': session['refresh']}, format='json').status_code, 401,
            )
        self.assertEqual(user.pk, User.objects.get(email='multi@example.com').pk)

    def test_offer_creation_with_image_and_gallery(self):
        client = self.as_user(self.seller)
        response = client.post(POSTS_URL, {
            'post_type': 'PRODUIT', 'category': str(self.category.id), 'commune': str(self.commune.id),
            'title': 'Perceuse sans fil', 'description': 'Description suffisamment longue pour le CDC.',
            'price': '25.50', 'currency': 'USD', 'condition': 'NEUF', 'stock': '3',
            'is_price_negotiable': 'false', 'is_exchangeable': 'true', 'main_image': make_test_image(),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertShape(response.json(), SPEC_POST, 'Post (création)')
        offer_id = response.json()['id']
        # Sans image : refusé ; image corrompue : 400 et non 500.
        base = {'post_type': 'PRODUIT', 'category': str(self.category.id), 'commune': str(self.commune.id),
                'title': 'Sans photo', 'description': 'Description suffisamment longue pour le CDC.',
                'price': '5', 'currency': 'USD', 'condition': 'NEUF', 'stock': '1'}
        self.assertEqual(client.post(POSTS_URL, base, format='multipart').status_code, 400)
        from django.core.files.uploadedfile import SimpleUploadedFile
        broken = SimpleUploadedFile('a.jpg', b'pas une image', content_type='image/jpeg')
        self.assertEqual(client.post(POSTS_URL, {**base, 'main_image': broken}, format='multipart').status_code, 400)
        gallery = client.post(f'{POSTS_URL}{offer_id}/images/', {'image': make_test_image()}, format='multipart')
        self.assertEqual(gallery.status_code, 201)
        self.assertShape(gallery.json()[0], {'id': 'uuid', 'image': 'str', 'order?': 'num'}, 'PostImage')
        # Un tiers ne peut pas ajouter de photo : 404, comme une offre inconnue.
        intruder = self.as_user(self.buyer).post(f'{POSTS_URL}{offer_id}/images/', {'image': make_test_image()}, format='multipart')
        self.assertEqual(intruder.status_code, 404)
        self.assertEqual(client.delete(f'{POSTS_URL}{offer_id}/images/', {}, QUERY_STRING=f"image_id={gallery.json()[0]['id']}").status_code, 204)

    def test_contact_review_reply_report_recourse_and_decision(self):
        # Contact -> diffusion -> notification et conversation du vendeur.
        for buyer in (self.buyer, self.buyer2, self.other):
            self.assertEqual(self.contact_via_api(buyer).status_code, 201)
        dispatch_outbox_now()
        dispatch_outbox_now()  # 2e passe : `messaging.contact_message_delivered` (preuve de remise, ADR 0005)
        seller = self.as_user(self.seller)
        notifications = self.rows(seller.get('/api/interactions/notifications/'))
        self.assertEqual(len(notifications), 3)
        self.assertShape(notifications[0], SPEC_NOTIFICATION, 'AppNotification')
        self.assertEqual(len(self.rows(seller.get('/api/interactions/conversations/'))), 3)

        # Avis, modification, suppression, ré-écriture bloquée.
        buyer_client = self.as_user(self.buyer)
        created = buyer_client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        self.assertShape(created.json(), SPEC_REVIEW, 'Review (création)')
        first = created.json()
        edited = buyer_client.patch(f"{REVIEWS_URL}{first['id']}/", {'offer_rating': 5}, format='json')
        self.assertEqual(edited.status_code, 200)
        self.assertIsNotNone(edited.json()['edited_at'])
        self.assertEqual(self.as_user(self.buyer2).patch(
            f"{REVIEWS_URL}{first['id']}/", {'content': 'Piratage du contenu de quelqu un'}, format='json').json()['code'], 'not_author')
        self.assertEqual(buyer_client.delete(f"{REVIEWS_URL}{first['id']}/").status_code, 204)
        rewrite = buyer_client.post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD}, format='json')
        self.assertEqual((rewrite.status_code, rewrite.json()['code']), (409, 'review_recently_deleted'))
        eligibility = buyer_client.get(REVIEWS_URL + 'eligibility/', {'post': str(self.offer.id)}).json()
        self.assertEqual(eligibility['reason'], 'recently_deleted')

        # buyer2 publie ; le vendeur répond à l'avis de other (verrouille sa modification).
        second = self.as_user(self.buyer2).post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD}, format='json').json()
        third = self.as_user(self.other).post(
            REVIEWS_URL, {'post': str(self.offer.id), 'offer_rating': 1, 'seller_rating': 1,
                          'content': 'Article jamais reçu, vendeur absent.'}, format='json').json()
        replied = seller.post(f"{REVIEWS_URL}{third['id']}/reply/", {'reply_content': 'Je conteste cet avis.'}, format='json')
        self.assertEqual(replied.status_code, 200)
        self.assertTrue(replied.json()['is_post_owner'])
        self.assertEqual(seller.post(f"{REVIEWS_URL}{third['id']}/reply/", {'reply_content': 'bis'}, format='json').json()['code'], 'already_replied')
        locked = self.as_user(self.other).patch(f"{REVIEWS_URL}{third['id']}/", {'content': 'Réécriture après coup ici'}, format='json')
        self.assertEqual(locked.json()['code'], 'review_locked_after_reply')

        # Signalement « contact fictif » : réservé au vendeur concerné.
        body = {'target_type': 'REVIEW', 'object_id': second['id'], 'reason': 'CONTACT_FICTIF', 'description': 'Inconnu.'}
        self.assertEqual(self.as_user(self.buyer).post(REPORTS_URL, body, format='json').json()['code'], 'not_seller')
        filed = seller.post(REPORTS_URL, body, format='json')
        self.assertEqual(filed.status_code, 201, filed.content)
        self.assertEqual(set(filed.json()), {'id', 'status', 'created_at'})  # ni signaleur ni notes pour un non-modérateur
        self.assertEqual(seller.post(REPORTS_URL, body, format='json').status_code, 409)

        # Recours de l'auteur : seul l'auteur le voit et peut répondre.
        author = self.as_user(self.buyer2)
        mine = [r for r in self.rows(author.get(REVIEWS_URL, {'post': str(self.offer.id)})) if r['is_mine']][0]
        self.assertShape(mine, SPEC_REVIEW, 'Review (contestée)')
        report_id = mine['contest_report_id']
        self.assertIsNotNone(report_id)
        self.assertFalse(mine['contest_responded'])
        seen_by_seller = [r for r in self.rows(seller.get(REVIEWS_URL, {'post': str(self.offer.id)})) if r['id'] == second['id']][0]
        self.assertIsNone(seen_by_seller['contest_report_id'])
        url = f'{REPORTS_URL}{report_id}/author-response/'
        self.assertEqual(self.as_user(self.buyer).post(url, {'author_response': 'Pas mon avis'}, format='json').status_code, 404)
        self.assertEqual(seller.post(url, {'author_response': 'Je suis le vendeur'}, format='json').status_code, 404)
        self.assertEqual(author.post(url, {'author_response': ''}, format='json').status_code, 400)
        answered = author.post(url, {'author_response': 'Voici ma preuve : capture de la conversation.'}, format='json')
        self.assertEqual(answered.status_code, 200)
        self.assertShape(answered.json(), SPEC_AUTHOR_RESPONSE, 'AuthorResponseResult')
        self.assertEqual(author.post(url, {'author_response': 'Encore'}, format='json').json()['code'], 'already_responded')
        self.assertEqual(author.delete(f"{REVIEWS_URL}{second['id']}/").json()['code'], 'review_locked')

        # Décision du modérateur : l'avis est masqué, les moyennes l'ignorent, l'auteur est bloqué.
        moderator = self.as_user(self.moderator)
        self.assertEqual(self.as_user(self.buyer).get(REPORTS_URL).status_code, 403)
        self.assertEqual(moderator.post(f'{REPORTS_URL}{report_id}/claim/').status_code, 200)
        self.assertEqual(moderator.post(f'{REPORTS_URL}{report_id}/resolve/', {'notes': 'Contact non établi.'}, format='json').status_code, 200)
        self.assertEqual(moderator.post(f'{REPORTS_URL}{report_id}/resolve/', {}, format='json').status_code, 409)
        detail = APIClient().get(f'{POSTS_URL}{self.offer.id}/').json()
        self.assertEqual(detail['offer_rating']['count'], 1)  # seul l'avis de `other` reste
        self.assertEqual(author.get(REVIEWS_URL + 'eligibility/', {'post': str(self.offer.id)}).json()['reason'], 'contact_rejected')
        self.assertNotIn(second['id'], [r['id'] for r in self.rows(APIClient().get(REVIEWS_URL, {'post': str(self.offer.id)}))])
        self.assertEqual(author.patch(f"{REVIEWS_URL}{second['id']}/", {'content': 'Modification après masquage'}, format='json').json()['code'], 'review_locked')
        self.assertTrue(AuditLog.objects.filter(action='REVIEW_HIDDEN', actor=self.moderator).exists())
        self.assertTrue(Notification.objects.filter(user=self.buyer2, title='Votre avis a été masqué').exists())

    def test_kyc_upload_delete_decision_and_verification(self):
        owner = User.objects.create_user(email='kyc@example.com', password=PASSWORD, full_name='Gérant', user_type='ENTREPRISE')
        BusinessProfile.objects.create(user=owner, business_name='Boîte KYC')
        client = self.as_user(owner)
        pdf = lambda: io.BytesIO(b'%PDF-1.4\n% test\n')  # noqa: E731

        def upload(kind):
            from django.core.files.uploadedfile import SimpleUploadedFile
            return client.post('/api/accounts/kyc/documents/', {
                'document_type': kind, 'file': SimpleUploadedFile('p.pdf', pdf().read(), content_type='application/pdf'),
            }, format='multipart')

        first = upload('RCCM')
        self.assertEqual(first.status_code, 201, first.content)
        self.assertShape(first.json(), SPEC_KYC, 'KycDocument')
        self.assertIsNone(first.json()['download_url'])
        self.assertNotIn('file', first.json())
        self.assertEqual(upload('RCCM').status_code, 400)  # une pièce par type en attente
        self.assertEqual(self.as_user(self.buyer).delete(f"/api/accounts/kyc/documents/{first.json()['id']}/").status_code, 404)
        self.assertEqual(client.delete(f"/api/accounts/kyc/documents/{first.json()['id']}/").status_code, 204)
        self.assertTrue(AuditLog.objects.filter(action='KYC_DELETED').exists())

        moderator = self.as_user(self.moderator)
        ids = {}
        for kind in ('RCCM', 'ID_NATIONALE', 'PIECE_GERANT'):
            ids[kind] = upload(kind).json()['id']
        self.assertEqual(client.get('/api/accounts/kyc/review-queue/').status_code, 403)
        queue = self.rows(moderator.get('/api/accounts/kyc/review-queue/'))
        self.assertEqual(len(queue), 3)
        self.assertTrue(queue[0]['download_url'])
        profile = owner.business_profile
        for kind, doc_id in ids.items():
            self.assertFalse(BusinessProfile.objects.get(pk=profile.pk).is_verified)  # pas vérifié avant les trois pièces
            decision = moderator.post(f'/api/accounts/kyc/documents/{doc_id}/decision/', {'decision': 'VALIDE'}, format='json')
            self.assertEqual(decision.status_code, 200)
        self.assertTrue(BusinessProfile.objects.get(pk=profile.pk).is_verified)
        self.assertEqual(client.delete(f"/api/accounts/kyc/documents/{ids['RCCM']}/").status_code, 400)
        self.assertEqual(AuditLog.objects.filter(action='KYC_VALIDE').count(), 3)
        seller_card = APIClient().get(POSTS_URL, {'seller': str(owner.id)})
        self.assertEqual(self.rows(seller_card), [])  # aucune offre : liste vide, pas d'erreur


# =========================================================================================
# Règle 4 : aucune note n'influe sur le classement organique
# =========================================================================================

class RatingsDoNotRankTests(RecetteBase):
    def snapshot(self, near=None):
        listing = APIClient().get(POSTS_URL, {'near': near} if near else {}).json()
        # La récence R décroît avec l'horloge : tolérance à 3 décimales, ordre exact.
        return [(row['id'], round(row['visibility_score'], 3)) for row in listing]

    def test_rule4_ratings_never_change_order_nor_scores(self):
        other_seller = User.objects.create_user(email='seller2@example.com', password=PASSWORD, full_name='Vendeur Deux')
        offer_b = self.make_offer(other_seller, title='Une offre concurrente identique')
        raters = [User.objects.create_user(email=f'rater{i}@example.com', password=PASSWORD, full_name=f'Noteur {i}') for i in range(4)]
        for rater in raters:  # mêmes contacts (engagement) sur les deux offres : seules les notes diffèreront
            self.make_contact(self.offer, rater)
            self.make_contact(offer_b, rater)
        marketplace_services.refresh_all_scores()
        before = self.snapshot()
        self.assertEqual(len(before), 2)
        for rater in raters:
            self.make_review(offer=self.offer, user=rater, offer_rating=5, seller_rating=5)
            self.make_review(offer=offer_b, user=rater, offer_rating=1, seller_rating=1)
        marketplace_services.refresh_all_scores()
        self.assertEqual(self.snapshot(), before)  # même ordre, mêmes scores, avis 5 étoiles contre 1 étoile

        # Les notes sont bien lues par ailleurs (le test ne passe pas à vide).
        top = APIClient().get(f'{POSTS_URL}{self.offer.id}/').json()
        self.assertEqual(top['offer_rating'], {'average': 5.0, 'count': 4})
        low = APIClient().get(f'{POSTS_URL}{offer_b.id}/').json()
        self.assertEqual(low['offer_rating'], {'average': 1.0, 'count': 4})

        # Inverser les notes ne change rien non plus.
        Review.objects.filter(offer_id=self.offer.id).update(offer_rating=1, seller_rating=1)
        Review.objects.filter(offer_id=offer_b.id).update(offer_rating=5, seller_rating=5)
        marketplace_services.refresh_all_scores()
        self.assertEqual(self.snapshot(), before)

    def test_rule4_no_rating_based_ordering_is_honoured(self):
        other_seller = User.objects.create_user(email='seller3@example.com', password=PASSWORD, full_name='Vendeur Trois')
        offer_b = self.make_offer(other_seller, title='Autre offre pour le tri')
        self.make_review(offer=offer_b, offer_rating=5, seller_rating=5)
        marketplace_services.refresh_all_scores()
        default = [r['id'] for r in APIClient().get(POSTS_URL).json()]
        for ordering in ('-offer_rating', 'offer_rating', '-seller_rating', '-rating', '-average', '-reviews'):
            ordered = [r['id'] for r in APIClient().get(POSTS_URL, {'ordering': ordering}).json()]
            self.assertEqual(ordered, default, ordering)

    def test_rule5_no_offer_is_flagged_sponsored(self):
        """Pas de promotion en V1 (lot 1) : aucune offre ne porte `is_sponsored` vrai ni de badge payant."""
        body = APIClient().get(f'{POSTS_URL}{self.offer.id}/').json()
        self.assertIs(body['is_sponsored'], False)
        self.assertNotIn('sponsored', body.get('badges', []))

    def test_rule4_no_trust_score_field_anywhere(self):
        self.make_review()
        payloads = [
            APIClient().get(f'{POSTS_URL}{self.offer.id}/').content.decode(),
            APIClient().get(REVIEWS_URL, {'post': str(self.offer.id)}).content.decode(),
            self.as_user(self.seller).get('/api/accounts/me/').content.decode(),
            self.as_user(self.seller).get('/api/marketplace/stats/dashboard/').content.decode(),
            APIClient().get('/api/accounts/organizations/').content.decode(),
        ]
        for text in payloads:
            self.assertNotRegex(text.lower(), r'trust|confiance|reputation')


# =========================================================================================
# Règle 10 : aucune donnée privée dans la réponse d'un tiers
# =========================================================================================

class PrivacyThirdPartyTests(RecetteBase):
    def test_rule10_no_private_data_leaks_to_third_parties(self):
        seller_phone, seller_email, nif = '+243899998877', 'prive.vendeur@example.com', 'NIF-SECRET-4242'
        owner = User.objects.create_user(
            email=seller_email, phone=seller_phone, password=PASSWORD, full_name='Gérant Privé', user_type='ENTREPRISE',
        )
        BusinessProfile.objects.create(user=owner, business_name='Boîte Privée', nif=nif)
        organization = Organization.objects.create(name='Boîte Privée', org_type='ENTREPRISE', nif=nif)
        Membership.objects.create(organization=organization, user=owner, role='OWNER')
        offer = self.make_offer(owner, title='Offre du gérant privé')
        from django.core.files.uploadedfile import SimpleUploadedFile
        KycDocument.objects.create(
            business_profile=owner.business_profile, document_type='RCCM',
            file=SimpleUploadedFile('x.pdf', b'%PDF-1.4 secret-kyc', content_type='application/pdf'),
        )
        self.contact_via_api(self.buyer, offer)
        dispatch_outbox_now()
        review = self.make_review(offer=offer)
        Report.objects.create(target_type='review', target_id=review.pk, reporter=owner, reason='CONTACT_FICTIF')

        secrets = [seller_phone, '243899998877', '899998877', seller_email, nif, 'secret-kyc']
        urls = [
            POSTS_URL, f'{POSTS_URL}{offer.id}/', f'{POSTS_URL}?seller={owner.id}', '/api/accounts/organizations/',
            f'{REVIEWS_URL}?post={offer.id}', f'{REVIEWS_URL}?seller={owner.id}',
            '/api/interactions/conversations/', '/api/interactions/notifications/', '/api/marketplace/favorites/',
            '/api/accounts/kyc/documents/', '/api/accounts/me/', '/api/moderation/dashboard/',
        ]
        for viewer in (None, self.buyer, self.other, self.buyer2):
            client = APIClient() if viewer is None else self.as_user(viewer)
            for url in urls:
                text = client.get(url).content.decode()
                for secret in secrets:
                    self.assertNotIn(secret, text, f'{secret!r} exposé à {viewer} sur {url}')
        # L'auteur de l'avis ne reçoit ni le signaleur ni la description du signalement.
        mine = self.rows(self.as_user(self.buyer).get(f'{REVIEWS_URL}?post={offer.id}'))[0]
        self.assertNotIn('reporter', json.dumps(mine))
        # L'e-mail et le téléphone du propriétaire ne sortent que dans son propre espace.
        own = self.as_user(owner).get('/api/accounts/me/').json()
        self.assertEqual((own['email'], own['phone']), (seller_email, seller_phone))

    def test_rule10_download_url_is_reserved_to_reviewers(self):
        owner = User.objects.create_user(email='own@example.com', password=PASSWORD, full_name='Gérant', user_type='ENTREPRISE')
        profile = BusinessProfile.objects.create(user=owner, business_name='B')
        from django.core.files.uploadedfile import SimpleUploadedFile
        doc = KycDocument.objects.create(
            business_profile=profile, document_type='RCCM',
            file=SimpleUploadedFile('x.pdf', b'%PDF-1.4 a', content_type='application/pdf'),
        )
        for viewer in (self.buyer, owner):
            self.assertEqual(self.as_user(viewer).get(f'/api/accounts/kyc/documents/{doc.pk}/download/').status_code, 403)
        self.assertEqual(APIClient().get(f'/api/accounts/kyc/documents/{doc.pk}/download/').status_code, 401)
        self.assertEqual(self.as_user(self.moderator).get(f'/api/accounts/kyc/documents/{doc.pk}/download/').status_code, 200)


# =========================================================================================
# Règle 12 : les actions sensibles écrivent un AuditLog
# =========================================================================================

class AuditTrailTests(RecetteBase):
    def test_rule12_suspension_ban_lift_and_login_effect(self):
        target = User.objects.create_user(email='cible@example.com', password=PASSWORD, full_name='Cible')
        admin = self.as_user(self.admin)
        issued = APIClient().post('/api/accounts/login/', {'email': 'cible@example.com', 'password': PASSWORD}, format='json').json()
        created = admin.post('/api/moderation/sanctions/', {
            'user': str(target.id), 'sanction_type': 'SUSPENSION_TEMPORAIRE', 'reason': 'Faux avis répétés',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        entry = AuditLog.objects.get(action='SANCTION_SUSPENSION_TEMPORAIRE')
        self.assertEqual((entry.actor, entry.details), (self.admin, 'Faux avis répétés'))
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        login = APIClient().post('/api/accounts/login/', {'email': 'cible@example.com', 'password': PASSWORD}, format='json')
        self.assertEqual(login.status_code, 401)
        # Un jeton émis avant la suspension ne vaut plus rien.
        self.assertEqual(APIClient().get('/api/accounts/me/', HTTP_AUTHORIZATION=f"Bearer {issued['access']}").status_code, 401)
        self.assertEqual(APIClient().post('/api/accounts/token/refresh/', {'refresh': issued['refresh']}, format='json').status_code, 401)
        # Un modérateur ne peut pas suspendre.
        refused = self.as_user(self.moderator).post('/api/moderation/sanctions/', {
            'user': str(target.id), 'sanction_type': 'BANNISSEMENT', 'reason': 'Tentative'}, format='json')
        self.assertEqual(refused.status_code, 403)
        self.assertFalse(AuditLog.objects.filter(action='SANCTION_BANNISSEMENT').exists())
        lifted = admin.post(f"/api/moderation/sanctions/{created.json()['id']}/lift/")
        self.assertEqual(lifted.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='SANCTION_LIFTED', actor=self.admin).exists())
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_R0_03_lifting_one_sanction_keeps_a_user_with_another_active_sanction_blocked(self):
        """ANOMALIE R0-03 (majeure) : `Sanction.lift()` réactive le compte sans regarder les autres sanctions
        actives. Un utilisateur banni puis suspendu, dont on lève la suspension, redevient actif alors que
        le bannissement court toujours (idem `lift_expired_sanctions` à l'échéance de la suspension)."""
        target = User.objects.create_user(email='double@example.com', password=PASSWORD, full_name='Double')
        admin = self.as_user(self.admin)
        ban = admin.post('/api/moderation/sanctions/', {'user': str(target.id), 'sanction_type': 'BANNISSEMENT', 'reason': 'Fraude'}, format='json')
        suspension = admin.post('/api/moderation/sanctions/', {'user': str(target.id), 'sanction_type': 'SUSPENSION_TEMPORAIRE', 'reason': 'Doublon'}, format='json')
        self.assertEqual((ban.status_code, suspension.status_code), (201, 201))
        admin.post(f"/api/moderation/sanctions/{suspension.json()['id']}/lift/")
        target.refresh_from_db()
        self.assertTrue(Sanction.objects.get(pk=ban.json()['id']).is_active)
        self.assertFalse(target.is_active, "compte réactivé alors que le bannissement est toujours actif")

    def test_rule12_review_hiding_and_unhiding_are_audited(self):
        review = self.make_review()
        from apps.reviews import services as reviews_services
        reviews_services.set_review_hidden(review, True, self.moderator)
        reviews_services.set_review_hidden(review, False, self.moderator)
        self.assertEqual(
            list(AuditLog.objects.filter(target_id=review.pk, actor=self.moderator).order_by('created_at').values_list('action', flat=True)),
            ['REVIEW_HIDDEN', 'REVIEW_UNHIDDEN'],
        )

    def test_rule12_kyc_decisions_and_refusal_reason(self):
        owner = User.objects.create_user(email='k@example.com', password=PASSWORD, full_name='K', user_type='ENTREPRISE')
        profile = BusinessProfile.objects.create(user=owner, business_name='K')
        from django.core.files.uploadedfile import SimpleUploadedFile
        doc = KycDocument.objects.create(
            business_profile=profile, document_type='RCCM',
            file=SimpleUploadedFile('x.pdf', b'%PDF-1.4 a', content_type='application/pdf'),
        )
        moderator = self.as_user(self.moderator)
        url = f'/api/accounts/kyc/documents/{doc.pk}/decision/'
        self.assertEqual(moderator.post(url, {'decision': 'REFUSE'}, format='json').status_code, 400)  # motif requis
        self.assertEqual(moderator.post(url, {'decision': 'REFUSE', 'reason': 'Illisible'}, format='json').status_code, 200)
        entry = AuditLog.objects.get(action='KYC_REFUSE')
        self.assertEqual((entry.actor, entry.target_id, entry.details), (self.moderator, doc.pk, 'Illisible'))
        self.assertEqual(moderator.post(url, {'decision': 'VALIDE'}, format='json').status_code, 409)  # refus définitif
        self.assertEqual(self.as_user(self.buyer).post(url, {'decision': 'VALIDE'}, format='json').status_code, 403)

    def test_rule12_offer_deletion_routes_are_audited(self):
        first = self.make_offer(self.seller, title='Offre supprimée par DELETE')
        second = self.make_offer(self.seller, title='Offre supprimée par hard_delete')
        client = self.as_user(self.seller)
        self.assertEqual(client.delete(f'{POSTS_URL}{first.id}/').status_code, 204)
        self.assertEqual(client.delete(f'{POSTS_URL}{second.id}/hard_delete/').status_code, 200)
        actions = AuditLog.objects.filter(action='OFFER_DELETED', actor=self.seller)
        self.assertEqual({a.target_id for a in actions}, {first.id, second.id})
        self.assertFalse(Offer.objects.filter(pk__in=[first.id, second.id]).exists())
        # Un tiers ne supprime pas l'offre d'autrui et rien n'est journalisé.
        before = AuditLog.objects.count()
        self.assertEqual(self.as_user(self.buyer).delete(f'{POSTS_URL}{self.offer.id}/').status_code, 404)
        self.assertEqual(AuditLog.objects.count(), before)

    def test_rule12_settings_change_through_the_admin_form(self):
        superuser = User.objects.create_superuser(email='root@example.com', password=PASSWORD, full_name='Root')
        client = self.client_class()
        client.force_login(superuser)
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(delay_after_contact_hours=24)  # setUp met 0
        row = ReviewSettings.get_solo()
        url = f'/admin/reviews/reviewsettings/{row.pk}/change/'
        page = client.get(url)
        self.assertEqual(page.status_code, 200)
        initial = {k: v for k, v in page.context['adminform'].form.initial.items() if v is not None}
        initial['edit_window_hours'] = 72
        response = client.post(url, initial)
        if response.status_code == 200:
            self.fail(response.context['adminform'].form.errors.as_json())
        self.assertIn(response.status_code, (200, 302), response.content[:300])
        self.assertEqual(ReviewSettings.get_solo().edit_window_hours, 72)
        entry = AuditLog.objects.filter(action='SETTINGS_CHANGED', target_id=row.pk).latest('created_at')
        self.assertEqual(entry.actor, superuser)
        self.assertIn('edit_window_hours : 48 -> 72', entry.details)

    def test_rule12_outbox_requeue_is_audited(self):
        self.contact_via_api(self.buyer)
        OutboxDelivery.objects.update(status=OutboxDelivery.DEAD, attempts=8, last_error='RuntimeError')
        call_command('dispatch_outbox', '--requeue', 'dead', verbosity=0)
        self.assertEqual(AuditLog.objects.filter(action='OUTBOX_REQUEUED').count(), OutboxDelivery.objects.count())
        self.assertFalse(OutboxDelivery.objects.filter(status=OutboxDelivery.DEAD).exists())
        entry = AuditLog.objects.filter(action='OUTBOX_REQUEUED').first()
        self.assertNotIn('Bonjour', entry.details)  # jamais la charge utile (message de contact)


# =========================================================================================
# Outbox : diffusion, idempotence, panne d'abonné, relance, purge
# =========================================================================================

@override_settings(OUTBOX_MAX_ATTEMPTS=2)
class OutboxScenarioTests(RecetteBase):
    def make_contacts(self, count=5):
        buyers = [User.objects.create_user(email=f'ob{i}@example.com', password=PASSWORD, full_name=f'Client {i}') for i in range(count)]
        for buyer in buyers:
            self.assertEqual(self.contact_via_api(buyer).status_code, 201)
        return buyers

    def test_nothing_is_visible_before_dispatch_then_everything_exactly_once(self):
        self.make_contacts(5)
        self.assertEqual((Conversation.objects.count(), Notification.objects.count()), (0, 0))
        self.assertEqual(OutboxEvent.objects.filter(status='pending').count(), 5)
        call_command('dispatch_outbox', verbosity=0)
        self.assertEqual(Conversation.objects.count(), 5)
        self.assertEqual(Message.objects.count(), 5)
        self.assertEqual(Notification.objects.filter(user=self.seller, notification_type='CONTACT').count(), 5)
        self.assertEqual(OutboxEvent.objects.filter(status='done').count(), 5)
        # Idempotence : relancer ne duplique rien.
        call_command('dispatch_outbox', verbosity=0)
        call_command('dispatch_outbox', verbosity=0)
        self.assertEqual((Conversation.objects.count(), Message.objects.count(), Notification.objects.count()), (5, 5, 5))

    def test_a_failing_subscriber_goes_dead_without_blocking_the_others_then_requeue_recovers(self):
        self.make_contacts(2)
        with mock.patch('apps.notifications.services.notify', side_effect=RuntimeError('panne notifications')):
            call_command('dispatch_outbox', verbosity=0)  # tentative 1 : échec, reprogrammée
            OutboxDelivery.objects.filter(status='pending').update(next_attempt_at=timezone.now() - timedelta(seconds=1))
            call_command('dispatch_outbox', verbosity=0)  # tentative 2 = max : échec définitif
        dead = OutboxDelivery.objects.filter(status=OutboxDelivery.DEAD)
        self.assertEqual(dead.count(), 2)
        self.assertEqual({d.handler for d in dead}, {'notifications.notify_contact'})
        self.assertNotIn('panne notifications', ''.join(d.last_error for d in dead))  # classe et origine seulement
        # Les conversations (autre abonné) sont bien créées malgré la panne.
        self.assertEqual(Conversation.objects.count(), 2)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.filter(status='dead').count(), 2)
        with self.assertRaises(CommandError):
            call_command('dispatch_outbox', '--stats', verbosity=0)

        call_command('dispatch_outbox', '--requeue', 'dead', verbosity=0)
        call_command('dispatch_outbox', verbosity=0)
        self.assertEqual(Notification.objects.filter(notification_type='CONTACT').count(), 2)
        self.assertEqual(Conversation.objects.count(), 2)  # l'abonné déjà réussi n'est pas rejoué
        self.assertEqual(Message.objects.count(), 2)
        # 2 `contact_recorded` + 2 `contact_message_delivered` (émis par la conversation ouverte, sans abonné en panne).
        self.assertEqual(OutboxEvent.objects.filter(status='done').count(), 4)
        call_command('dispatch_outbox', '--stats', verbosity=0)  # plus aucune livraison morte

    def test_unknown_event_version_is_a_permanent_failure(self):
        self.contact_via_api(self.buyer)
        OutboxEvent.objects.update(version=9)
        call_command('dispatch_outbox', verbosity=0)
        self.assertEqual(OutboxDelivery.objects.filter(status=OutboxDelivery.DEAD).count(), OutboxDelivery.objects.count())
        self.assertEqual(Notification.objects.count(), 0)

    def test_purge_removes_old_done_and_dead_events_only(self):
        self.make_contacts(3)
        call_command('dispatch_outbox', verbosity=0)
        call_command('dispatch_outbox', verbosity=0)  # 2e passe : remise des messages de contact
        # Après deux passes, tous les contacts sont remis.
        self.assertFalse(ContactEvent.objects.filter(delivered_at__isnull=True).exists())
        delivered = list(OutboxEvent.objects.filter(event_type='messaging.contact_message_delivered'))
        self.assertEqual(len(delivered), 3)
        events = list(OutboxEvent.objects.filter(event_type='marketplace.contact_recorded').order_by('created_at'))
        old, recent, dead = events
        old_delivered, kept_delivered = delivered[0], delivered[1]
        OutboxEvent.objects.filter(pk=old.pk).update(completed_at=timezone.now() - timedelta(days=8))
        OutboxEvent.objects.filter(pk=old_delivered.pk).update(completed_at=timezone.now() - timedelta(days=8))
        OutboxEvent.objects.filter(pk=dead.pk).update(status='dead', completed_at=timezone.now() - timedelta(days=10))
        OutboxEvent.objects.exclude(pk__in=[old.pk, recent.pk, dead.pk, old_delivered.pk, kept_delivered.pk]).delete()
        call_command('purge_outbox', verbosity=0)
        remaining = set(OutboxEvent.objects.values_list('pk', flat=True))
        self.assertEqual(remaining, {recent.pk, dead.pk, kept_delivered.pk})  # le mort attend 30 jours, le récent 7
        self.assertFalse(OutboxEvent.objects.filter(pk=old_delivered.pk).exists())
        self.assertFalse(OutboxDelivery.objects.filter(event_id=old.pk).exists())  # cascade

    def test_review_events_reach_the_right_people(self):
        self.contact_via_api(self.buyer)
        call_command('dispatch_outbox', verbosity=0)
        call_command('dispatch_outbox', verbosity=0)  # 2e passe : remise du message de contact
        Notification.objects.all().delete()
        created = self.as_user(self.buyer).post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD}, format='json').json()
        self.as_user(self.seller).post(f"{REVIEWS_URL}{created['id']}/reply/", {'reply_content': 'Merci !'}, format='json')
        call_command('dispatch_outbox', verbosity=0)
        self.assertEqual(Notification.objects.filter(user=self.seller, notification_type='COMMENT').count(), 1)
        reply = Notification.objects.filter(user=self.buyer).get()
        self.assertEqual(reply.link, f'/post/{self.offer.id}')
        self.assertFalse(Notification.objects.filter(user=self.other).exists())
