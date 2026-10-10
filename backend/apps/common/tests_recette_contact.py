"""Recette L0-10a : contact vendeur, consentement par canal et révélation du numéro (ADR 0005).

Scénarios de bout en bout par l'API réelle : authentification par jetons JWT obtenus à la connexion
(`/api/accounts/login/`), aucune injection d'état en base pour le consentement, le numéro de contact ou
les révélations. Seuls sont simulés : la passerelle SMS (le code est lu à l'envoi) et l'écoulement du
temps (dates de `ContactEvent`/`AuditLog` reculées, comme le font les autres tests de recette).

Numéros de la recette (distinctifs, pour que la recherche des quatre derniers chiffres n'ait pas de faux positif) :
- contact du vendeur : +243897654321 (derniers chiffres 4321), puis +243893216789 après changement ;
- connexion du vendeur : +243970000001 ;
- contact de l'acheteur : +243898887777.
"""
import json
import logging
import re
import uuid
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.catalog.models import Category, City, Commune
from apps.common.factories import make_test_image
from apps.common.tests_privacy import PARAM_RE, iter_routes
from apps.identity.models import CONTACT_CONSENT_TEXT_VERSION as VERSION
from apps.identity.models import ContactConsent, ContactPoint, OtpCode, User
from apps.marketplace.models import ContactEvent, MarketplaceSettings, Offer
from apps.messaging.models import Conversation, Message
from apps.moderation.models import AuditLog, Report, Sanction
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxDelivery, OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now
from apps.reviews.models import ReviewSettings
from apps.reviews.tests import GOOD, REVIEWS_URL

PASSWORD = 'Recette-contact-2026!'
SETTINGS = '/api/accounts/contact-settings/'
REVEAL = '/api/interactions/contacts/reveal/'
RECEIVED = '/api/interactions/contacts/reveals/received/'
CONTACTS = '/api/interactions/contacts/'
POSTS = '/api/marketplace/posts/'

SELLER_LOGIN = '+243970000001'
SELLER_CONTACT = '+243897654321'
SELLER_CONTACT_2 = '+243893216789'
BUYER_CONTACT = '+243898887777'
UUID_RE = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
DATE_RE = re.compile(r'\d{4}-\d\d-\d\d[T ][\d:.+Z-]+')


def needles(number):
    """Formes sous lesquelles un numéro ne doit pas apparaître : complet, sans « + », sans indicatif,
    forme masquée de l'écran de réglages."""
    national = number[4:]
    return [number, number[1:], national, f'+243 {national[:2]} *** ** {national[-2:]}']


def has_last4(text, number):
    """Les quatre derniers chiffres, isolés (hors UUID et dates, qui contiennent des suites de chiffres)."""
    cleaned = DATE_RE.sub('', UUID_RE.sub('', text))
    return re.search(r'(?<!\d)' + re.escape(number[-4:]) + r'(?!\d)', cleaned) is not None


# Cache mémoire : les limites de débit sont réellement appliquées (le cache de test par défaut est factice).
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'recette-contact'}}


@override_settings(CACHES=LOCMEM)
class RecetteContactBase(APITestCase):
    def setUp(self):
        cache.clear()
        call_command('setup_roles', verbosity=0)
        sms = mock.patch('apps.identity.sms.send_otp_sms')
        self.sms = sms.start()
        self.addCleanup(sms.stop)
        old = timezone.now() - timedelta(days=60)
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = self.user('seller@example.com', 'Jean Mukendi', phone=SELLER_LOGIN, old=old)
        self.buyer = self.user('buyer@example.com', 'Marie Kabongo', phone='+243970000002', old=old)
        self.other = self.user('other@example.com', 'Paul Ilunga', phone='+243970000003', old=old)
        self.admin = self.user('admin@example.com', 'Admin Test', phone='+243970000004', old=old, staff=True)
        self.admin.groups.add(Group.objects.get(name='Administrateur'))
        self.moderator = self.user('modo@example.com', 'Modo Test', phone='+243970000005', old=old, staff=True)
        self.moderator.groups.add(Group.objects.get(name='Modérateur'))
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(
            delay_after_contact_hours=24, min_account_age_hours=0,
        )
        self.offer = self.make_offer()
        self.clients = {}

    # --- fabrique ------------------------------------------------------------------------------

    def user(self, email, name, phone=None, old=None, staff=False, verified=True):
        user = User.objects.create_user(
            email=email, password=PASSWORD, full_name=name, phone=phone, phone_verified=verified and bool(phone),
            is_staff=staff,
        )
        if old is not None:
            User.objects.filter(pk=user.pk).update(date_joined=old)
            user.refresh_from_db()
        return user

    def make_offer(self, seller=None, title='Un joli canapé à vendre'):
        return Offer.objects.create(
            seller=seller or self.seller, category_id=self.category.id, commune_id=self.commune.id, title=title,
            description='Description suffisamment longue pour le CDC.', price=100, main_image=make_test_image(),
        )

    def login(self, user):
        """Client authentifié par un vrai jeton d'accès obtenu à la connexion (pas de force_authenticate)."""
        response = APIClient().post('/api/accounts/login/', {'email': user.email, 'password': PASSWORD}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer ' + response.json()['access'])
        return client

    def c(self, user):
        if user is None:
            return APIClient()
        if user.pk not in self.clients:
            self.clients[user.pk] = self.login(user)
        return self.clients[user.pk]

    # --- parcours vendeur ----------------------------------------------------------------------

    def last_code(self):
        return self.sms.call_args[0][1]

    def set_contact_number(self, number, user=None):
        client = self.c(user or self.seller)
        self.assertEqual(client.put(SETTINGS + 'phone/', {'phone': number}, format='json').status_code, 200)
        response = client.post(SETTINGS + 'phone/verify/', {'code': self.last_code()}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def enable(self, channel, user=None, version=VERSION):
        return self.c(user or self.seller).put(
            f'{SETTINGS}channels/{channel}/', {'enabled': True, 'text_version': version}, format='json',
        )

    def disable(self, channel, user=None):
        return self.c(user or self.seller).put(f'{SETTINGS}channels/{channel}/', {'enabled': False}, format='json')

    def seller_ready(self, number=SELLER_CONTACT):
        self.set_contact_number(number)
        self.assertEqual(self.enable('CALL').status_code, 200)
        self.assertEqual(self.enable('WHATSAPP').status_code, 200)

    def reveal(self, user=None, offer=None, channel='CALL', **extra):
        return self.c(user or self.buyer).post(
            REVEAL, {'offer': str((offer or self.offer).id), 'channel': channel}, format='json', **extra,
        )

    def settings_row(self, **values):
        MarketplaceSettings.objects.filter(pk=MarketplaceSettings.get_solo().pk).update(**values)

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json().get('code'), code, response.content)
        self.assertTrue(response.json().get('detail'))


# =========================================================================================
# Scénario 1 : configuration du vendeur
# =========================================================================================

class Scenario1SellerConfigurationTests(RecetteContactBase):
    def test_new_account_defaults(self):
        response = self.c(self.seller).get(SETTINGS)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body['phone'])
        self.assertEqual(body['channels']['MESSAGE'], {'enabled': True})
        self.assertFalse(body['channels']['CALL']['enabled'])
        self.assertFalse(body['channels']['WHATSAPP']['enabled'])
        self.assertEqual(body['current_text_version'], VERSION)
        self.assertIn('no-store', response['Cache-Control'])

    def test_settings_require_authentication(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.get(SETTINGS).status_code, 401)
        self.assertEqual(anonymous.put(SETTINGS + 'phone/', {'phone': SELLER_CONTACT}, format='json').status_code, 401)
        self.assertEqual(anonymous.put(SETTINGS + 'channels/CALL/', {'enabled': False}, format='json').status_code, 401)

    def test_full_configuration_flow_then_channels_are_public_without_number(self):
        # Activation impossible sans numéro vérifié.
        self.assert_error(self.enable('CALL'), 409, 'contact_phone_unverified')
        # Numéro invalide.
        self.assertEqual(self.c(self.seller).put(SETTINGS + 'phone/', {'phone': '0897654321'}, format='json').status_code, 400)
        self.assertEqual(self.c(self.seller).put(SETTINGS + 'phone/', {}, format='json').status_code, 400)
        # Saisie du numéro : un SMS part, le numéro reste non vérifié et n'est jamais renvoyé en clair.
        put = self.c(self.seller).put(SETTINGS + 'phone/', {'phone': SELLER_CONTACT}, format='json')
        self.assertEqual(put.status_code, 200)
        self.assertFalse(put.json()['phone']['is_verified'])
        self.assertNotIn('897654321', put.content.decode())
        self.sms.assert_called_once()
        self.assertEqual(self.sms.call_args[0][0], SELLER_CONTACT)
        self.assert_error(self.enable('CALL'), 409, 'contact_phone_unverified')
        # Mauvais code, puis bon code.
        wrong = '000000' if self.last_code() != '000000' else '111111'
        self.assert_error(
            self.c(self.seller).post(SETTINGS + 'phone/verify/', {'code': wrong}, format='json'), 400, 'otp_invalid',
        )
        verified = self.c(self.seller).post(SETTINGS + 'phone/verify/', {'code': self.last_code()}, format='json')
        self.assertEqual(verified.status_code, 200)
        self.assertTrue(verified.json()['phone']['is_verified'])
        self.assertEqual(verified.json()['phone']['masked'], '+243 89 *** ** 21')
        used_code = self.last_code()
        self.assertFalse(OtpCode.objects.filter(purpose='CONTACT_VERIFY').exists())  # le code a été détruit
        # Consentement : texte obligatoire, version courante obligatoire.
        self.assert_error(
            self.c(self.seller).put(SETTINGS + 'channels/CALL/', {'enabled': True}, format='json'),
            400, 'consent_text_required',
        )
        self.assert_error(self.enable('CALL', version='1999-v0'), 400, 'consent_version_mismatch')
        self.assert_error(self.c(self.seller).put(SETTINGS + 'channels/FAX/', {'enabled': True}, format='json'), 404, 'channel_unknown')
        self.assertEqual(self.enable('CALL').status_code, 200)
        # Un code déjà utilisé ne vérifie pas un nouveau numéro.
        self.assertEqual(self.c(self.seller).put(SETTINGS + 'phone/', {'phone': SELLER_CONTACT_2}, format='json').status_code, 200)
        self.assert_error(
            self.c(self.seller).post(SETTINGS + 'phone/verify/', {'code': used_code}, format='json'), 400, 'otp_invalid',
        )
        self.assertEqual(self.c(self.seller).put(SETTINGS + 'phone/', {'phone': SELLER_CONTACT}, format='json').status_code, 200)
        self.assertEqual(self.c(self.seller).post(
            SETTINGS + 'phone/verify/', {'code': self.last_code()}, format='json').status_code, 200)
        self.assertEqual(self.enable('CALL').status_code, 200)
        response = self.enable('WHATSAPP')
        channels = response.json()['channels']
        self.assertTrue(channels['CALL']['enabled'] and channels['WHATSAPP']['enabled'])
        self.assertEqual(channels['CALL']['text_version'], VERSION)
        # Fiche publique : canaux sans aucun indice sur le numéro, pour l'anonyme comme pour l'acheteur.
        for client in (self.c(None), self.c(self.buyer)):
            for url in (f'{POSTS}{self.offer.id}/', POSTS):
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                text = response.content.decode()
                self.assertIn('"allowed_channels":["MESSAGE","CALL","WHATSAPP"]', text.replace(' ', ''))
                for needle in needles(SELLER_CONTACT):
                    self.assertNotIn(needle, text)
                self.assertFalse(has_last4(text, SELLER_CONTACT))

    def test_use_login_phone_requires_explicit_gesture_and_a_verified_login_phone(self):
        # Rien n'est copié sans geste.
        self.assertIsNone(self.c(self.seller).get(SETTINGS).json()['phone'])
        response = self.c(self.seller).put(SETTINGS + 'phone/', {'use_login_phone': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['phone']['is_verified'])  # numéro de connexion déjà vérifié : pas de SMS
        self.sms.assert_not_called()
        # Numéro de connexion non vérifié : refus.
        User.objects.filter(pk=self.buyer.pk).update(phone_verified=False)
        self.assert_error(
            self.c(self.buyer).put(SETTINGS + 'phone/', {'use_login_phone': True}, format='json'),
            409, 'login_phone_unverified',
        )

    def test_message_channel_can_be_disabled_and_blocks_messages(self):
        self.assertEqual(self.disable('MESSAGE').status_code, 200)
        self.assertEqual(self.c(None).get(f'{POSTS}{self.offer.id}/').json()['allowed_channels'], [])
        response = self.c(self.buyer).post(CONTACTS, {'post': str(self.offer.id), 'message': 'Bonjour'}, format='json')
        self.assert_error(response, 403, 'channel_not_allowed')
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_settings_writes_are_throttled(self):
        for _ in range(20):
            self.assertEqual(self.disable('CALL').status_code, 200)
        self.assertEqual(self.disable('CALL').status_code, 429)

    def test_an_unverified_new_account_cannot_trigger_a_sms_to_an_arbitrary_number(self):
        newbie = self.user('new@example.com', 'Nouveau Venu', phone='+243970000009', verified=False)
        response = self.c(newbie).put(SETTINGS + 'phone/', {'phone': '+243891112222'}, format='json')
        self.assert_error(response, 403, 'account_too_new')
        self.sms.assert_not_called()
        self.assertFalse(ContactPoint.objects.filter(user=newbie).exists())


# =========================================================================================
# Scénario 2 : aucune fuite du numéro sur les routes de lecture
# =========================================================================================

class Scenario2NoNumberLeakTests(RecetteContactBase):
    def setUp(self):
        super().setUp()
        self.seller_ready()
        self.conversation = Conversation.objects.create(offer_id=self.offer.id)
        self.conversation.participants.add(self.seller, self.buyer)
        Message.objects.create(conversation=self.conversation, sender=self.buyer, content='Bonjour')
        self.pool = [str(x.pk) for x in (self.seller, self.buyer, self.other, self.offer, self.conversation,
                                         self.category, self.commune)]

    def crawl(self, viewer):
        client = self.c(viewer)
        reached = 0
        for route in iter_routes():
            if route.startswith('api/accounts/contact-settings'):
                continue  # espace personnel du titulaire (testé plus bas)
            targets = [route] if not PARAM_RE.search(route) else [PARAM_RE.sub(i, route) for i in self.pool]
            for path in targets:
                response = client.get('/' + path, {'page_size': 100})
                self.assertLess(response.status_code, 500, path)
                reached += response.status_code == 200
                text = response.content.decode('utf-8', errors='ignore')
                for number in (SELLER_CONTACT, SELLER_LOGIN):
                    for needle in needles(number):
                        self.assertNotIn(needle, text, f'{path} ({viewer}) expose {needle}')
                self.assertFalse(has_last4(text, SELLER_CONTACT), f'{path} ({viewer}) expose les 4 derniers chiffres')
        return reached

    def test_get_routes_expose_no_seller_number_to_anyone_who_has_not_revealed_it(self):
        for viewer in (None, self.buyer, self.other, self.moderator, self.admin):
            self.assertGreaterEqual(self.crawl(viewer), 8, viewer)

    def test_the_settings_of_other_accounts_never_show_the_seller_number(self):
        for viewer in (self.buyer, self.moderator, self.admin):
            text = self.c(viewer).get(SETTINGS).content.decode()
            for needle in needles(SELLER_CONTACT):
                self.assertNotIn(needle, text)
            self.assertFalse(has_last4(text, SELLER_CONTACT))

    def test_search_by_any_part_of_the_number_finds_nothing(self):
        for term in (SELLER_CONTACT, SELLER_CONTACT[4:], '7654321', '4321', SELLER_LOGIN, '970000001'):
            for url in (POSTS, '/api/accounts/businesses/'):
                for viewer in (None, self.buyer):
                    response = self.c(viewer).get(url, {'search': term})
                    self.assertEqual(response.status_code, 200)
                    data = response.json()
                    self.assertEqual(data['results'] if isinstance(data, dict) else data, [], f'{url} « {term} »')

    def test_witness_the_crawl_really_reaches_the_offer(self):
        self.assertIn('Un joli canapé', self.c(None).get(POSTS).content.decode())

    def test_admin_api_responses_for_sanctions_and_reports_do_not_carry_the_number(self):
        self.reveal()
        for url in ('/api/moderation/sanctions/', '/api/moderation/reports/', '/api/moderation/dashboard/',
                    '/api/accounts/kyc/review-queue/'):
            for viewer in (self.moderator, self.admin):
                text = self.c(viewer).get(url).content.decode()
                for needle in needles(SELLER_CONTACT):
                    self.assertNotIn(needle, text)


# =========================================================================================
# Scénario 3 : révélation, idempotence, vue du vendeur
# =========================================================================================

class Scenario3RevealTests(RecetteContactBase):
    def setUp(self):
        super().setUp()
        self.seller_ready()

    def test_anonymous_gets_401_and_nothing_is_recorded(self):
        response = APIClient().post(
            REVEAL, {'offer': str(self.offer.id), 'channel': 'CALL'}, format='json',
        )
        self.assert_error(response, 401, 'not_authenticated')
        self.assertNotIn('897654321', response.content.decode())
        self.assertEqual(ContactEvent.objects.count(), 0)
        self.assertFalse(AuditLog.objects.filter(action__startswith='contact.number').exists())

    def test_call_reveal_then_idempotent_replay_then_seller_view(self):
        first = self.reveal(channel='CALL')
        self.assertEqual(first.status_code, 201)
        body = first.json()
        self.assertEqual((body['phone'], body['created'], body['tel_url'], body['whatsapp_url']),
                         (SELLER_CONTACT, True, f'tel:{SELLER_CONTACT}', None))
        self.assertIn('no-store', first['Cache-Control'])
        self.assertEqual(first['Pragma'], 'no-cache')
        second = self.reveal(channel='CALL')
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()['created'])
        self.assertEqual(second.json()['contact_event_id'], body['contact_event_id'])
        self.assertIn('no-store', second['Cache-Control'])
        self.assertEqual(ContactEvent.objects.filter(channel='CALL').count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='contact.number_revealed').count(), 2)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.contacts_count, 1)
        # Le rejeu n'a pas consommé de quota : un seul contact dans le décompte des plafonds.
        self.assertEqual(ContactEvent.objects.filter(sender=self.buyer, channel__in=('CALL', 'WHATSAPP')).count(), 1)

    def test_whatsapp_reveal_link(self):
        offer = self.make_offer(title='Chaussures & sacs à vendre')
        response = self.reveal(offer=offer, channel='WHATSAPP')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIsNone(body['tel_url'])
        self.assertEqual(body['whatsapp_url'], 'https://wa.me/243897654321?text=Chaussures%20%26%20sacs%20%C3%A0%20vendre')

    def test_seller_sees_first_name_and_initial_without_number_or_id(self):
        self.reveal(channel='CALL')
        self.reveal(channel='CALL')
        self.reveal(channel='WHATSAPP')
        response = self.c(self.seller).get(RECEIVED)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        data = response.json()
        self.assertEqual(data['count'], 2)
        self.assertEqual({r['channel'] for r in data['results']}, {'CALL', 'WHATSAPP'})
        for row in data['results']:
            self.assertEqual(set(row), {'id', 'channel', 'created_at', 'requester_display_name', 'offer'})
            self.assertEqual(row['requester_display_name'], 'Marie K.')
            self.assertEqual(row['offer'], {'id': str(self.offer.id), 'title': self.offer.title})
        text = response.content.decode()
        for forbidden in (str(self.buyer.pk), self.buyer.email, '970000002', SELLER_CONTACT, '897654321'):
            self.assertNotIn(forbidden, text)
        filtered = self.c(self.seller).get(RECEIVED, {'channel': 'WHATSAPP'}).json()
        self.assertEqual([r['channel'] for r in filtered['results']], ['WHATSAPP'])
        self.assert_error(self.c(self.seller).get(RECEIVED, {'channel': 'MESSAGE'}), 400, 'channel_invalid')

    def test_received_list_is_private_to_the_seller_and_paginated(self):
        self.assertEqual(self.c(self.seller).get(RECEIVED).json(), {'count': 0, 'next': None, 'previous': None, 'results': []})
        for i in range(23):
            buyer = self.user(f'b{i}@example.com', f'Acheteur{i} Test', phone=f'+2439700001{i:02d}',
                              old=timezone.now() - timedelta(days=90))
            self.assertEqual(self.reveal(user=buyer).status_code, 201)
        page = self.c(self.seller).get(RECEIVED).json()
        self.assertEqual(page['count'], 23)
        self.assertIsNotNone(page['next'])
        self.assertEqual(self.c(self.seller).get(RECEIVED, {'page': 2}).status_code, 200)
        self.assertEqual(self.c(self.seller).get(RECEIVED, {'page': 99}).status_code, 404)
        for viewer in (self.buyer, self.other, self.moderator, self.admin):
            self.assertEqual(self.c(viewer).get(RECEIVED).json()['count'], 0)
        self.assertEqual(APIClient().get(RECEIVED).status_code, 401)

    def test_invalid_inputs(self):
        client = self.c(self.buyer)
        self.assert_error(self.reveal(channel='MESSAGE'), 400, 'channel_invalid')
        self.assert_error(self.reveal(channel='SMS'), 400, 'channel_invalid')
        self.assertEqual(client.post(REVEAL, {}, format='json').status_code, 400)
        self.assertEqual(client.post(REVEAL, {'offer': str(self.offer.id)}, format='json').status_code, 400)
        self.assertEqual(client.get(REVEAL).status_code, 405)
        self.assert_error(self.reveal(user=self.seller), 403, 'own_offer')
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_double_submission_creates_a_single_contact(self):
        responses = [self.reveal(), self.reveal(), self.reveal()]
        self.assertEqual([r.status_code for r in responses], [201, 200, 200])
        self.assertEqual(ContactEvent.objects.count(), 1)

    def test_a_message_and_a_reveal_are_independent_contacts(self):
        message = self.c(self.buyer).post(CONTACTS, {'post': str(self.offer.id), 'message': 'Bonjour'}, format='json')
        self.assertEqual(message.status_code, 201)
        self.assertEqual(self.reveal().status_code, 201)
        # Le doublon d'un message garde son code.
        again = self.c(self.buyer).post(CONTACTS, {'post': str(self.offer.id), 'message': 'Bonjour'}, format='json')
        self.assert_error(again, 400, 'contact_duplicate')


# =========================================================================================
# Scénario 4 : révocation et changement de numéro
# =========================================================================================

class Scenario4RevocationTests(RecetteContactBase):
    def setUp(self):
        super().setUp()
        self.seller_ready()

    def test_revocation_blocks_even_a_visitor_who_already_has_the_number(self):
        self.assertEqual(self.reveal(channel='CALL').status_code, 201)
        self.assertEqual(self.disable('CALL').status_code, 200)
        self.assert_error(self.reveal(channel='CALL'), 403, 'channel_not_allowed')  # même visiteur, même fenêtre de 24 h
        self.assert_error(self.reveal(user=self.other, channel='CALL'), 403, 'channel_not_allowed')
        self.assertEqual(self.c(None).get(f'{POSTS}{self.offer.id}/').json()['allowed_channels'], ['MESSAGE', 'WHATSAPP'])
        self.assertEqual(self.reveal(channel='WHATSAPP').status_code, 201)  # l'autre canal est intact
        self.assertEqual(ContactEvent.objects.filter(channel='CALL').count(), 1)
        self.assertTrue(AuditLog.objects.filter(action='contact.consent_revoked').exists())

    def test_disabling_twice_is_idempotent(self):
        self.assertEqual(self.disable('CALL').status_code, 200)
        self.assertEqual(self.disable('CALL').status_code, 200)

    def test_changing_the_contact_number_revokes_call_and_whatsapp(self):
        self.assertEqual(self.reveal(channel='WHATSAPP').status_code, 201)
        put = self.c(self.seller).put(SETTINGS + 'phone/', {'phone': SELLER_CONTACT_2}, format='json')
        self.assertEqual(put.status_code, 200)
        channels = put.json()['channels']
        self.assertFalse(channels['CALL']['enabled'])
        self.assertFalse(channels['WHATSAPP']['enabled'])
        self.assertTrue(channels['MESSAGE']['enabled'])
        self.assertEqual(
            set(ContactConsent.objects.filter(user=self.seller, is_granted=False).values_list('revoked_reason', flat=True)),
            {'phone_changed'},
        )
        self.assertTrue(AuditLog.objects.filter(action='contact.phone_changed').exists())
        self.assertEqual(self.c(None).get(f'{POSTS}{self.offer.id}/').json()['allowed_channels'], ['MESSAGE'])
        # Ni l'ancien visiteur, ni un nouveau, ne reçoivent un numéro (ancien ou nouveau non vérifié).
        for viewer in (self.buyer, self.other):
            for channel in ('CALL', 'WHATSAPP'):
                response = self.reveal(user=viewer, channel=channel)
                self.assert_error(response, 403, 'channel_not_allowed')
                self.assertNotIn('89', response.content.decode().replace('403', ''))
        # Vérification du nouveau numéro : n'active aucun canal.
        verified = self.c(self.seller).post(SETTINGS + 'phone/verify/', {'code': self.last_code()}, format='json')
        self.assertEqual(verified.status_code, 200)
        self.assert_error(self.reveal(channel='CALL'), 403, 'channel_not_allowed')
        # Nouvelle acceptation : le visiteur reçoit le NOUVEAU numéro, jamais l'ancien.
        self.assertEqual(self.enable('CALL').status_code, 200)
        response = self.reveal(user=self.other, channel='CALL')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['phone'], SELLER_CONTACT_2)
        self.assertNotIn('897654321', response.content.decode())

    def test_resubmitting_the_same_number_does_not_revoke(self):
        self.assertEqual(self.c(self.seller).put(SETTINGS + 'phone/', {'phone': SELLER_CONTACT}, format='json').status_code, 200)
        self.assertEqual(self.reveal().status_code, 201)

    def test_changing_the_login_phone_does_not_change_the_contact_number(self):
        User.objects.filter(pk=self.seller.pk).update(phone='+243970000099')
        self.assertEqual(self.reveal().json()['phone'], SELLER_CONTACT)

    def test_unverified_replacement_number_is_never_revealed_even_if_consent_is_forced(self):
        """Défense en profondeur : un accord ancien ne suffit pas si le numéro actuel n'est pas vérifié."""
        self.c(self.seller).put(SETTINGS + 'phone/', {'phone': SELLER_CONTACT_2}, format='json')
        ContactConsent.objects.filter(user=self.seller, channel='CALL').update(is_granted=True)  # état incohérent simulé
        self.assert_error(self.reveal(channel='CALL'), 403, 'channel_not_allowed')


# =========================================================================================
# Scénario 5 : quotas
# =========================================================================================

class Scenario5QuotaTests(RecetteContactBase):
    def setUp(self):
        super().setUp()
        self.seller_ready()
        self.offers = [self.make_offer(title=f'Annonce numéro {i:02d}') for i in range(18)]

    def assert_retry_after(self, response):
        self.assertIn('Retry-After', response)
        self.assertTrue(0 < int(response['Retry-After']) <= 86400)
        self.assertIn('message', response.json()['detail'].lower())  # repli proposé

    def test_account_quota_is_15_per_24h_with_retry_after(self):
        for offer in self.offers[:15]:
            self.assertEqual(self.reveal(offer=offer).status_code, 201)
        response = self.reveal(offer=self.offers[15])
        self.assert_error(response, 429, 'reveal_quota_account')
        self.assert_retry_after(response)
        self.assertNotIn('897654321', response.content.decode())
        self.assertEqual(ContactEvent.objects.filter(sender=self.buyer).count(), 15)
        # Un rejeu d'un contact déjà obtenu reste possible (aucun quota consommé).
        self.assertEqual(self.reveal(offer=self.offers[0]).status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='contact.reveal_quota_exceeded', actor=self.buyer).exists())

    def test_quota_is_sliding_and_frees_after_24h(self):
        self.settings_row(reveal_daily_limit_account=2)
        for offer in self.offers[:2]:
            self.assertEqual(self.reveal(offer=offer).status_code, 201)
        self.assert_error(self.reveal(offer=self.offers[2]), 429, 'reveal_quota_account')
        ContactEvent.objects.filter(sender=self.buyer).update(created_at=timezone.now() - timedelta(hours=25))
        self.assertEqual(self.reveal(offer=self.offers[2]).status_code, 201)

    def test_new_account_quota_is_3(self):
        fresh = self.user('fresh@example.com', 'Nouvelle Venue', phone='+243970000050')  # inscrit à l'instant
        for offer in self.offers[:3]:
            self.assertEqual(self.reveal(user=fresh, offer=offer).status_code, 201)
        response = self.reveal(user=fresh, offer=self.offers[3])
        self.assert_error(response, 429, 'reveal_quota_new_account')
        self.assert_retry_after(response)

    def test_unverified_phone_account_is_treated_as_new(self):
        old = timezone.now() - timedelta(days=90)
        unverified = self.user('unv@example.com', 'Sans Telephone', old=old)
        for offer in self.offers[:3]:
            self.assertEqual(self.reveal(user=unverified, offer=offer).status_code, 201)
        self.assert_error(self.reveal(user=unverified, offer=self.offers[3]), 429, 'reveal_quota_new_account')

    def test_back_office_values_apply_immediately(self):
        self.settings_row(reveal_daily_limit_account=1)
        self.assertEqual(self.reveal(offer=self.offers[0]).status_code, 201)
        self.assert_error(self.reveal(offer=self.offers[1]), 429, 'reveal_quota_account')
        self.settings_row(reveal_daily_limit_account=5)
        self.assertEqual(self.reveal(offer=self.offers[1]).status_code, 201)
        self.settings_row(new_account_hours=720, reveal_daily_limit_new_account=1)
        User.objects.filter(pk=self.buyer.pk).update(date_joined=timezone.now() - timedelta(hours=1))
        self.assert_error(self.reveal(offer=self.offers[2]), 429, 'reveal_quota_new_account')

    def test_ip_quota_is_30_per_hour_and_not_bypassed_by_forwarded_header_or_other_accounts(self):
        for _ in range(30):
            self.assertIn(self.reveal().status_code, (200, 201))
        response = self.reveal()
        self.assert_error(response, 429, 'reveal_quota_ip')
        self.assertIn('Retry-After', response)
        self.assertGreaterEqual(int(response['Retry-After']), 1)
        # Autre compte, même IP : bloqué.
        self.assert_error(self.reveal(user=self.other), 429, 'reveal_quota_ip')
        # En-tête X-Forwarded-For forgé : ignoré (NUM_PROXIES=0).
        self.assert_error(self.reveal(HTTP_X_FORWARDED_FOR='203.0.113.77'), 429, 'reveal_quota_ip')
        self.assertNotIn('897654321', response.content.decode())

    def test_repeated_excess_on_distinct_days_files_an_automatic_report(self):
        self.settings_row(reveal_daily_limit_account=1)
        self.assertEqual(self.reveal(offer=self.offers[0]).status_code, 201)
        # Même jour : plusieurs dépassements ne font pas un abus.
        for _ in range(4):
            self.assert_error(self.reveal(offer=self.offers[1]), 429, 'reveal_quota_account')
        self.assertEqual(Report.objects.count(), 0)
        # Jours distincts : 2 jours antérieurs + aujourd'hui.
        AuditLog.objects.filter(action='contact.reveal_quota_exceeded').update(created_at=timezone.now() - timedelta(days=2))
        self.assert_error(self.reveal(offer=self.offers[1]), 429, 'reveal_quota_account')
        self.assertEqual(Report.objects.count(), 0)  # deux jours seulement
        AuditLog.objects.filter(action='contact.reveal_quota_exceeded').exclude(
            created_at__gte=timezone.now() - timedelta(hours=1)).update(created_at=timezone.now() - timedelta(days=2))
        latest = AuditLog.objects.filter(action='contact.reveal_quota_exceeded').order_by('-created_at').first()
        AuditLog.objects.filter(pk=latest.pk).update(created_at=timezone.now() - timedelta(days=1))
        self.assert_error(self.reveal(offer=self.offers[1]), 429, 'reveal_quota_account')
        report = Report.objects.get()
        self.assertEqual((report.target_type, report.target_id, report.reporter), ('user', self.buyer.pk, None))
        self.assertEqual(report.reason, Report.REASON_SPAM)
        self.assertNotIn('897654321', report.description)
        # Pas de doublon tant que le signalement est ouvert.
        self.assert_error(self.reveal(offer=self.offers[1]), 429, 'reveal_quota_account')
        self.assertEqual(Report.objects.count(), 1)


# =========================================================================================
# Scénario 6 : comptes et offres indisponibles
# =========================================================================================

class Scenario6UnavailableTests(RecetteContactBase):
    def setUp(self):
        super().setUp()
        self.seller_ready()

    def sanction(self, user, kind, **extra):
        response = self.c(self.admin).post('/api/moderation/sanctions/', {
            'user': str(user.pk), 'sanction_type': kind, 'reason': 'Recette', **extra,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_suspended_seller_gives_the_uniform_404_then_recovers(self):
        sanction = self.sanction(self.seller, 'SUSPENSION_TEMPORAIRE')
        response = self.reveal()
        self.assert_error(response, 404, 'offer_not_found')
        self.assertEqual(self.c(None).get(f'{POSTS}{self.offer.id}/').status_code, 404)
        self.assertEqual(ContactEvent.objects.count(), 0)
        lifted = self.c(self.admin).post(f"/api/moderation/sanctions/{sanction['id']}/lift/")
        self.assertEqual(lifted.status_code, 200)
        self.assertEqual(self.reveal().status_code, 201)

    def test_suspended_visitor_token_is_rejected(self):
        self.c(self.buyer)  # jeton obtenu avant la suspension
        self.sanction(self.buyer, 'BANNISSEMENT')
        response = self.c(self.buyer).post(REVEAL, {'offer': str(self.offer.id), 'channel': 'CALL'}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('897654321', response.content.decode())
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_restricted_visitor_is_refused_with_contact_restricted(self):
        Sanction.objects.create(user=self.buyer, sanction_type='SUSPENSION_TEMPORAIRE', reason='x', issued_by=self.admin)
        self.assert_error(self.reveal(), 403, 'contact_restricted')
        self.assertEqual(ContactEvent.objects.count(), 0)
        # Une sanction échue ne restreint plus.
        Sanction.objects.update(ends_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(self.reveal().status_code, 201)

    def test_warning_does_not_restrict(self):
        self.sanction(self.buyer, 'AVERTISSEMENT')
        self.assertEqual(self.reveal().status_code, 201)

    def test_all_unavailable_offers_give_the_same_404_body(self):
        bodies = {}
        trash = self.make_offer(title='Offre en corbeille ici')
        self.assertEqual(self.c(self.seller).post(f'{POSTS}{trash.id}/soft_delete/').status_code, 200)
        bodies['corbeille'] = self.reveal(offer=trash)
        paused = self.make_offer(title='Offre en pause ici')
        self.assertEqual(self.c(self.seller).post(f'{POSTS}{paused.id}/pause/').status_code, 200)
        bodies['pause'] = self.reveal(offer=paused)
        hidden = self.make_offer(title='Offre masquée par modération')
        self.sanction(self.seller, 'MASQUAGE_ANNONCE', related_post=str(hidden.id))
        bodies['masquée'] = self.reveal(offer=hidden)
        expired = self.make_offer(title='Offre expirée depuis hier')
        Offer.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(days=1))
        call_command('expire_offers', verbosity=0)
        bodies['expirée'] = self.reveal(offer=expired)
        bodies['inconnue'] = self.c(self.buyer).post(REVEAL, {'offer': str(uuid.uuid4()), 'channel': 'CALL'}, format='json')
        bodies['mal formée'] = self.c(self.buyer).post(REVEAL, {'offer': 'pas-un-uuid', 'channel': 'CALL'}, format='json')
        for label, response in bodies.items():
            self.assert_error(response, 404, 'offer_not_found')
        distinct = {json.dumps(r.json(), sort_keys=True) for r in bodies.values()}
        self.assertEqual(len(distinct), 1, f'404 distinguables : {distinct}')
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_restored_offer_is_revealable_again(self):
        offer = self.make_offer(title='Offre à restaurer vite')
        self.c(self.seller).post(f'{POSTS}{offer.id}/soft_delete/')
        self.assertEqual(self.reveal(offer=offer).status_code, 404)
        self.c(self.seller).post(f'{POSTS}{offer.id}/restore/')
        self.assertEqual(self.reveal(offer=offer).status_code, 201)

    def test_hard_deleted_offer_keeps_nothing_leaking(self):
        self.assertEqual(self.reveal().status_code, 201)
        self.assertEqual(self.c(self.seller).delete(f'{POSTS}{self.offer.id}/hard_delete/').status_code, 200)
        self.assert_error(self.reveal(), 404, 'offer_not_found')
        self.assertEqual(self.c(self.seller).get(RECEIVED).status_code, 200)

    def test_quota_is_not_consumed_by_refusals(self):
        self.settings_row(reveal_daily_limit_account=1)
        self.assertEqual(self.disable('WHATSAPP').status_code, 200)
        for _ in range(3):
            self.assert_error(self.reveal(channel='WHATSAPP'), 403, 'channel_not_allowed')
        self.assertEqual(self.reveal(channel='CALL').status_code, 201)
        self.assertEqual(AuditLog.objects.filter(action='contact.reveal_refused').count(), 1)  # dédoublonné par jour


# =========================================================================================
# Scénario 7 : preuve d'avis
# =========================================================================================

class Scenario7ReviewProofTests(RecetteContactBase):
    def eligibility(self, user):
        response = self.c(user).get(REVIEWS_URL + 'eligibility/', {'post': str(self.offer.id)})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def age_contact(self, sender, hours=48):
        past = timezone.now() - timedelta(hours=hours)
        for event in ContactEvent.objects.filter(sender=sender):
            ContactEvent.objects.filter(pk=event.pk).update(
                created_at=past, delivered_at=None if event.delivered_at is None else past,
            )

    def test_delivered_message_opens_the_review_after_the_delay(self):
        sent = self.c(self.buyer).post(CONTACTS, {'post': str(self.offer.id), 'message': 'Bonjour, dispo ?'}, format='json')
        self.assertEqual(sent.status_code, 201)
        self.assertEqual(self.eligibility(self.buyer)['reason'], 'no_contact')  # pas encore remis
        dispatch_outbox_now()
        dispatch_outbox_now()
        self.assertEqual(Message.objects.filter(content='Bonjour, dispo ?').count(), 1)
        self.assertIsNotNone(ContactEvent.objects.get().delivered_at)
        self.assertEqual(self.eligibility(self.buyer)['reason'], 'too_early')
        self.age_contact(self.buyer)
        self.assertTrue(self.eligibility(self.buyer)['can_review'])
        review = self.c(self.buyer).post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD}, format='json')
        self.assertEqual(review.status_code, 201, review.content)

    def test_undelivered_message_never_opens_the_review(self):
        self.c(self.buyer).post(CONTACTS, {'post': str(self.offer.id), 'message': 'Bonjour, dispo ?'}, format='json')
        self.assertIsNone(ContactEvent.objects.get().delivered_at)
        self.age_contact(self.buyer, hours=500)
        self.assertEqual(self.eligibility(self.buyer), {
            'can_review': False, 'reason': 'no_contact', 'available_at': None, 'review_id': None,
        })
        refused = self.c(self.buyer).post(REVIEWS_URL, {'post': str(self.offer.id), **GOOD}, format='json')
        self.assert_error(refused, 403, 'not_eligible')

    def test_a_lost_message_after_permanent_failure_does_not_open_the_review(self):
        self.c(self.buyer).post(CONTACTS, {'post': str(self.offer.id), 'message': 'Bonjour, dispo ?'}, format='json')
        OutboxDelivery.objects.update(status=OutboxDelivery.DEAD)
        dispatch_outbox_now()
        self.age_contact(self.buyer, hours=500)
        self.assertFalse(self.eligibility(self.buyer)['can_review'])

    def test_a_revealed_number_opens_the_review_after_the_delay(self):
        self.seller_ready()
        self.assertEqual(self.reveal(user=self.other, channel='WHATSAPP').status_code, 201)
        self.assertEqual(self.eligibility(self.other)['reason'], 'too_early')
        self.age_contact(self.other)
        self.assertTrue(self.eligibility(self.other)['can_review'])

    def test_the_seller_cannot_review_own_offer_and_a_stranger_cannot_review(self):
        self.assertEqual(self.eligibility(self.seller)['reason'], 'own_offer')
        self.assertEqual(self.eligibility(self.moderator)['reason'], 'no_contact')


# =========================================================================================
# Scénario 8 : aucune fuite dans les traces
# =========================================================================================

class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
            if record.exc_info:
                self.lines.append(logging.Formatter().formatException(record.exc_info))
        except Exception:  # pragma: no cover
            pass


class Scenario8TraceLeakTests(RecetteContactBase):
    def run_full_flow(self):
        self.seller_ready()
        self.assertEqual(self.reveal(channel='CALL').status_code, 201)
        self.reveal(channel='CALL')
        self.assertEqual(self.reveal(channel='WHATSAPP').status_code, 201)
        self.c(self.other).post(CONTACTS, {'post': str(self.offer.id), 'message': 'Bonjour, dispo ?'}, format='json')
        self.settings_row(reveal_daily_limit_account=2)
        self.reveal(user=self.other, offer=self.make_offer(title='Annonce de plus ici'))
        self.reveal(user=self.other, offer=self.make_offer(title='Encore une annonce'))
        self.reveal(user=self.other, offer=self.make_offer(title='Et une dernière ici'))
        self.disable('CALL')
        self.reveal(channel='CALL')
        self.set_contact_number(SELLER_CONTACT_2)
        dispatch_outbox_now()
        dispatch_outbox_now()
        dispatch_outbox_now()

    def test_number_is_in_no_trace(self):
        handler = _Capture()
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            self.run_full_flow()
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)
        self.assertTrue(handler.lines, 'témoin : aucun journal capturé')

        traces = {
            'AuditLog': [f'{a.action} {a.details} {a.target_type}' for a in AuditLog.objects.all()],
            'OutboxEvent': [json.dumps(e.payload) + e.event_type + e.aggregate_type for e in OutboxEvent.objects.all()],
            'OutboxDelivery.last_error': [d.last_error for d in OutboxDelivery.objects.all()],
            'Notification': [f'{n.title} {n.content} {n.link}' for n in Notification.objects.all()],
            'Message': [m.content for m in Message.objects.all()],
            'ContactEvent.message': [e.message for e in ContactEvent.objects.all()],
            'Report': [f'{r.description} {r.reason}' for r in Report.objects.all()],
            'Sanction': [s.reason for s in Sanction.objects.all()],
            'logs': handler.lines,
        }
        # Témoins : les traces existent bel et bien.
        self.assertTrue(any('contact.number_revealed' in t for t in traces['AuditLog']))
        self.assertTrue(traces['OutboxEvent'])
        self.assertTrue(any('demandé votre numéro' in t for t in traces['Notification']))
        found = []
        for name, texts in traces.items():
            for text in texts:
                for number in (SELLER_CONTACT, SELLER_CONTACT_2, SELLER_LOGIN):
                    for needle in needles(number):
                        if needle in text:
                            found.append((name, needle))
                    if number != SELLER_LOGIN and has_last4(text, number) and 'contact.consent_granted' not in text:
                        found.append((name, 'quatre derniers chiffres ' + number[-4:], text[:120]))
        self.assertEqual(found, [], 'fuite du numéro dans les traces (voir rapport)')

    def test_no_audit_carries_the_last_four_digits(self):
        """ADR 0005 §8/§11 (5) : aucun numéro, même masqué, dans l'audit ; `phone_last4` reste dans le consentement."""
        self.seller_ready()
        self.reveal()
        dispatch_outbox_now()
        self.assertTrue(AuditLog.objects.filter(action='contact.consent_granted').exists())
        carriers = {a.action for a in AuditLog.objects.all() if has_last4(a.details, SELLER_CONTACT)}
        self.assertEqual(carriers, set())

    def test_contact_verify_codes_do_not_linger_after_use(self):
        self.set_contact_number(SELLER_CONTACT)
        self.assertFalse(OtpCode.objects.filter(purpose='CONTACT_VERIFY', phone=SELLER_CONTACT).exists())

    def test_no_contact_number_in_any_contact_point_endpoint_for_other_users(self):
        self.seller_ready()
        self.reveal()
        for viewer in (self.other, self.moderator, self.admin):
            text = self.c(viewer).get(SETTINGS).content.decode()
            for needle in needles(SELLER_CONTACT):
                self.assertNotIn(needle, text)


class Scenario8bVisitorNameTests(RecetteContactBase):
    """Le nom libre du visiteur ne doit pas servir de canal pour transmettre un numéro ou un lien au vendeur."""

    def setUp(self):
        super().setUp()
        self.seller_ready()

    def test_reveal_opens_no_conversation(self):
        self.reveal()
        dispatch_outbox_now()
        dispatch_outbox_now()
        self.assertEqual(Conversation.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)

    def test_a_hostile_visitor_name_is_neutralised_in_the_list_and_in_the_notification(self):
        hostile = self.user('hostile@example.com', '0899990000 Kabongo', phone='+243970000077',
                            old=timezone.now() - timedelta(days=90))
        self.assertEqual(self.reveal(user=hostile).status_code, 201)
        dispatch_outbox_now()
        listed = self.c(self.seller).get(RECEIVED).json()['results'][0]['requester_display_name']
        notification = Notification.objects.get(user=self.seller)
        self.assertNotRegex(listed, r'\d')
        self.assertNotRegex(notification.content, r'\d{5,}')


# =========================================================================================
# Scénario 10 : cohérence des codes et des liens entre le serveur et le front
# =========================================================================================

class Scenario10FrontBackContractTests(RecetteContactBase):
    FRONT = Path(__file__).resolve().parents[3] / 'connect-grow' / 'src'
    # Regex du front (connect-grow/src/lib/contact-reveal.ts) : liens rendus seulement s'ils y correspondent.
    TEL_URL = re.compile(r'^tel:\+?\d{6,15}$')
    WHATSAPP_URL = re.compile(r'^https://wa\.me/\d{6,15}(\?text=[A-Za-z0-9%._~-]*)?$')
    REVEAL_CODES = ['channel_invalid', 'channel_not_allowed', 'own_offer', 'contact_restricted', 'offer_not_found',
                    'reveal_quota_account', 'reveal_quota_new_account', 'reveal_quota_ip', 'reveal_in_progress']
    SETTINGS_CODES = ['contact_phone_unverified', 'consent_version_mismatch', 'consent_text_required',
                      'login_phone_unverified', 'phone_invalid', 'otp_invalid', 'otp_expired', 'otp_attempts_exceeded',
                      'contact_phone_missing', 'channel_unknown']

    def front(self, *parts):
        path = self.FRONT.joinpath(*parts)
        if not path.exists():
            self.skipTest(f'front absent : {path}')
        return path.read_text(encoding='utf-8')

    def test_reveal_links_match_the_front_whitelist_for_awkward_titles(self):
        self.seller_ready()
        titles = ['Café (neuf) / 50% "promo" *urgent* l\'été', 'Téléphone — 😀 émoji', 'a' * 80, 'Prix: 10$ & plus ? #1',
                  "Chaise_en-bois.v2~ok"]
        for title in titles:
            offer = self.make_offer(title=title)
            call = self.reveal(offer=offer, channel='CALL').json()
            whatsapp = self.reveal(offer=offer, channel='WHATSAPP').json()
            self.assertRegex(call['tel_url'], self.TEL_URL)
            self.assertRegex(whatsapp['whatsapp_url'], self.WHATSAPP_URL, title)
            self.assertNotIn(SELLER_LOGIN, whatsapp['whatsapp_url'])

    def test_every_reveal_code_is_emitted_by_the_server_and_handled_by_the_front(self):
        reveal_ts = self.front('lib', 'contact-reveal.ts')
        server = (Path(__file__).resolve().parents[1] / 'marketplace' / 'services.py').read_text(encoding='utf-8')
        server += (Path(__file__).resolve().parents[1] / 'common' / 'throttles.py').read_text(encoding='utf-8')
        for code in self.REVEAL_CODES:
            self.assertIn(f"'{code}'", server, f'{code} jamais émis par le serveur')
            self.assertIn(f'"{code}"', reveal_ts, f'{code} non géré par le front')
        fr = self.front('i18n', 'locales', 'fr.ts')
        for code in ('own_offer', 'contact_restricted', 'channel_not_allowed', 'offer_not_found', 'reveal_quota_account',
                     'reveal_quota_new_account', 'reveal_quota_ip', 'reveal_in_progress'):
            self.assertIn(f'{code}:', fr, f'{code} sans texte français')

    def test_every_settings_code_is_emitted_by_the_server_and_known_to_the_front(self):
        settings_ts = self.front('lib', 'contact-settings.ts')
        server = (Path(__file__).resolve().parents[1] / 'identity' / 'services.py').read_text(encoding='utf-8')
        server += (Path(__file__).resolve().parents[1] / 'identity' / 'views.py').read_text(encoding='utf-8')
        for code in self.SETTINGS_CODES:
            self.assertIn(f"'{code}'", server, f'{code} jamais émis par le serveur')
            self.assertIn(f'"{code}"', settings_ts, f'{code} non géré par le front')

    def test_front_handles_the_http_statuses_and_codes_really_returned(self):
        """Statuts réels du serveur pour chaque code de l'ADR 5.4 (le front lit `code`, puis le statut)."""
        self.seller_ready()
        observed = {
            'channel_invalid': (400, self.reveal(channel='MESSAGE')),
            'own_offer': (403, self.reveal(user=self.seller)),
            'offer_not_found': (404, self.c(self.buyer).post(REVEAL, {'offer': str(uuid.uuid4()), 'channel': 'CALL'}, format='json')),
        }
        self.disable('CALL')
        observed['channel_not_allowed'] = (403, self.reveal(channel='CALL'))
        for code, (status, response) in observed.items():
            self.assert_error(response, status, code)
            detail = response.json()['detail']
            self.assertRegex(detail, r'[a-zéèàù]')  # texte français non vide
            self.assertNotRegex(detail, r'(?i)\b(not found|forbidden|throttled)\b')

    def test_retry_after_is_readable_by_the_browser_across_origins(self):
        from django.conf import settings
        self.assertIn('Retry-After', settings.CORS_EXPOSE_HEADERS)
        self.assertTrue(settings.CORS_ALLOWED_ORIGINS)
        self.assertNotIn('*', settings.CORS_ALLOWED_ORIGINS)

    def test_allowed_channels_is_present_on_list_and_detail_even_for_a_seller_without_contact_point(self):
        for url in (f'{POSTS}{self.offer.id}/', POSTS):
            response = self.c(None).get(url)
            body = response.json()
            row = body if isinstance(body, dict) and 'allowed_channels' in body else (body[0] if isinstance(body, list) else body['results'][0])
            self.assertEqual(row['allowed_channels'], ['MESSAGE'])
