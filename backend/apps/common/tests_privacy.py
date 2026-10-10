"""Test de non-fuite exhaustif (L0-10a-a, règle 10) : aucun téléphone ni e-mail d'un utilisateur
ne sort dans une réponse destinée à un anonyme, à un tiers ou à un membre du personnel.

Il parcourt toutes les routes GET (hors admin et suffixes de format), puis les réponses
d'écriture usuelles et la recherche plein texte. Des témoins positifs et des seuils de
couverture garantissent que le parcours atteint vraiment des données (un test qui ne voit
rien passerait à tort)."""
import json
import re

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from rest_framework.test import APITestCase

from apps.catalog.models import Category, City, Commune
from apps.common.factories import make_test_image
from apps.identity.models import BusinessProfile, ContactConsent, ContactPoint, KycDocument, User, CONTACT_CONSENT_TEXT_VERSION
from apps.marketplace.models import ContactEvent, ExchangeProposal, Favorite, Offer
from apps.messaging.models import Conversation, Message
from apps.moderation.models import Report, Sanction
from apps.reviews.models import Review, ReviewSettings

# Seul l'espace personnel d'un utilisateur renvoie ses propres coordonnées. `phone_verified`
# est interdit partout ailleurs : il révèle qu'un numéro existe sur le compte.
# Les réglages de contact (ADR 0005, 5.1) renvoient le seul numéro du titulaire, masqué.
OWN_DATA_ROUTES = ('api/accounts/me/', 'api/accounts/contact-settings/')
CONTACT_SETTINGS_ROUTES = (
    'api/accounts/contact-settings/', 'api/accounts/contact-settings/phone/',
    'api/accounts/contact-settings/phone/verify/', 'api/accounts/contact-settings/channels/<str:channel>/',
)
# Routes de l'ADR 0005 (5.4 et 5.5) : seule la première renvoie un numéro de contact.
REVEAL_ROUTES = ('api/interactions/contacts/reveal/', 'api/interactions/contacts/reveals/received/')
LEAKY_KEY_RE = re.compile(r'phone|email|whatsapp|mobile|tel', re.IGNORECASE)
PARAM_RE = re.compile(r'<(?:\w+:)?\w+>')
REGEX_PARAM_RE = re.compile(r'\(\?P<(\w+)>[^)]*\)')


def normalize(route):
    """Route DRF (regex du routeur ou chemin) -> chemin avec des marques <param>."""
    route = REGEX_PARAM_RE.sub(lambda match: '<' + match.group(1) + '>', route)
    return route.replace('^', '').replace('$', '').replace(chr(92) + '.', '.').replace('?', '')


def iter_routes(resolver=None, prefix=''):
    resolver = resolver or get_resolver()
    for entry in resolver.url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from iter_routes(entry, route)
        elif isinstance(entry, URLPattern) and not route.startswith(('admin/', '^admin')):
            path = normalize(route)
            if '<format>' in path:  # doublons « .json » du routeur DRF
                continue
            yield path


def keys_of(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from keys_of(item)
    elif isinstance(value, list):
        for item in value:
            yield from keys_of(item)


class NoPersonalContactLeakTests(APITestCase):
    PEOPLE = {
        'seller': ('+243970000001', 'seller-secret@example.com'),
        'buyer': ('+243970000002', 'buyer-secret@example.com'),
        'third': ('+243970000003', 'third-secret@example.com'),
        'moderator': ('+243970000004', 'moderator-secret@example.com'),
        'admin': ('+243970000005', 'admin-secret@example.com'),
    }
    # Numéros de contact (distincts des numéros de connexion), vérifiés et consentis (ADR 0005).
    CONTACT_NUMBERS = {'seller': '+243891111111', 'buyer': '+243892222222'}

    def setUp(self):
        call_command('setup_roles', verbosity=0)
        city = City.objects.create(name='Kinshasa')
        commune = Commune.objects.create(city=city, name='Gombe')
        category = Category.objects.create(name='Électronique', slug='electronique')
        self.users = {}
        for name, (phone, email) in self.PEOPLE.items():
            user = User.objects.create_user(
                email=email, phone=phone, password='x', full_name=name.capitalize(), phone_verified=True,
                is_staff=name in ('moderator', 'admin'),
            )
            if name == 'moderator':
                user.groups.add(Group.objects.get(name='Modérateur'))
            if name == 'admin':
                user.groups.add(Group.objects.get(name='Administrateur'))
            self.users[name] = user
        for name, number in self.CONTACT_NUMBERS.items():
            ContactPoint.objects.create(user=self.users[name], phone=number, is_verified=True)
            for channel in ('CALL', 'WHATSAPP'):
                ContactConsent.objects.create(
                    user=self.users[name], channel=channel, is_granted=True,
                    text_version=CONTACT_CONSENT_TEXT_VERSION, phone_last4=number[-4:],
                )
        seller, buyer = self.users['seller'], self.users['buyer']
        seller.user_type = 'ENTREPRISE'
        seller.save()
        profile = BusinessProfile.objects.create(user=seller, business_name='Boutique', bio='Bio', is_verified=True)
        KycDocument.objects.create(business_profile=profile, document_type=KycDocument.DOC_RCCM)
        self.offer = Offer.objects.create(
            seller=seller, category_id=category.id, commune_id=commune.id, title='Un joli canapé à vendre',
            description='Description suffisamment longue pour le CDC.', price=100, main_image=make_test_image(),
        )
        Favorite.objects.create(user=buyer, offer=self.offer)
        contact = ContactEvent.objects.create(offer=self.offer, sender=buyer, message='Bonjour')
        ExchangeProposal.objects.create(offer=self.offer, sender=buyer, message='Echange ?')
        self.review = Review.objects.create(
            offer_id=self.offer.id, user=buyer, seller_context_type='USER', seller_context_id=seller.id,
            contact_event_id=contact.id, contact_channel=contact.channel, contact_recorded_at=contact.created_at,
            content='Avis suffisamment long pour être valide.', offer_rating=4, seller_rating=5,
        )
        self.conversation = Conversation.objects.create(offer_id=self.offer.id)
        self.conversation.participants.add(seller, buyer)
        Message.objects.create(conversation=self.conversation, sender=buyer, content='Salut')
        Message.objects.create(conversation=self.conversation, sender=seller, content='Bonjour à vous')
        report = Report.objects.create(
            target_type='offer', target_id=self.offer.id, reporter=buyer, reason=Report.REASON_SPAM,
        )
        sanction = Sanction.objects.create(
            user=seller, sanction_type=Sanction.TYPE_AVERTISSEMENT, reason='Test', issued_by=self.users['admin'],
        )
        self.pool = [
            *(str(u.id) for u in self.users.values()), str(self.offer.id), str(self.review.id),
            str(self.conversation.id), str(report.id), str(sanction.id), str(category.id), str(city.id),
            str(commune.id), *(str(m.id) for m in Message.objects.all()),
            *(str(d.id) for d in KycDocument.objects.all()),
        ]

    # --- utilitaires -------------------------------------------------------------------

    def expand(self, route):
        """Une route à paramètres est appelée avec chaque identifiant connu."""
        if not PARAM_RE.search(route):
            return [route]
        return [PARAM_RE.sub(identifier, route) for identifier in self.pool]

    def client_for(self, viewer):
        client = self.client_class()
        if viewer:
            client.force_authenticate(self.users[viewer])
        return client

    def forbidden_values(self, viewer):
        values = [value for name, pair in self.PEOPLE.items() if name != viewer for value in pair]
        for name, number in self.CONTACT_NUMBERS.items():
            if name != viewer:
                # Numéro de contact d'un autre compte : complet, sans indicatif, et sous forme masquée.
                values += [number, number[4:], f'+243 {number[4:6]} *** ** {number[-2:]}']
        for name, (phone, _) in self.PEOPLE.items():
            if name != viewer:
                values.append(f'+243 {phone[4:6]} *** ** {phone[-2:]}')
        return values

    def assert_clean(self, response, url, viewer):
        body = response.content.decode('utf-8', errors='ignore')
        label = viewer or 'anonyme'
        for value in self.forbidden_values(viewer):
            self.assertNotIn(value, body, f'{label} voit {value} sur {url}')
        if url.lstrip('/').startswith(OWN_DATA_ROUTES):
            return
        try:
            payload = json.loads(body)
        except ValueError:
            return
        leaked = {k for k in keys_of(payload) if LEAKY_KEY_RE.search(k)}
        self.assertFalse(leaked, f'clé {leaked} dans la réponse de {url} ({label})')

    def crawl(self, viewer):
        client = self.client_for(viewer)
        ok_responses = 0
        for route in iter_routes():
            for path in self.expand(route):
                url = '/' + path
                response = client.get(url, {'page_size': 100})
                if response.status_code >= 500:
                    self.fail(f'{url} : {response.status_code}')
                ok_responses += response.status_code == 200
                self.assert_clean(response, url, viewer)
        return ok_responses

    # --- parcours des routes GET -------------------------------------------------------

    def test_no_phone_or_email_for_anonymous(self):
        self.assertGreaterEqual(self.crawl(None), 8)

    def test_no_phone_or_email_for_an_unrelated_user(self):
        self.assertGreaterEqual(self.crawl('third'), 12)

    def test_no_phone_or_email_for_the_counterparty(self):
        self.assertGreaterEqual(self.crawl('buyer'), 15)

    def test_the_seller_does_not_get_other_people_data(self):
        self.assertGreaterEqual(self.crawl('seller'), 15)

    def test_a_moderator_does_not_get_contact_data_through_the_api(self):
        # Le modérateur voit la file KYC, les signalements et les sanctions.
        self.assertGreaterEqual(self.crawl('moderator'), 18)

    def test_an_administrator_does_not_get_contact_data_through_the_api(self):
        self.assertGreaterEqual(self.crawl('admin'), 18)

    # --- témoins positifs : le parcours atteint bien des données ----------------------

    def test_positive_witnesses_return_the_seller_name(self):
        """Si une de ces routes cessait de renvoyer le vendeur, les tests de non-fuite
        deviendraient vides sans que rien n'échoue : on l'exige explicitement."""
        witnesses = [
            (None, reverse('offer-detail', args=[self.offer.id]), 'Seller'),
            (None, reverse('offer-list'), 'Seller'),
            (None, reverse('business_list'), 'Boutique'),
            (None, reverse('review-list'), 'Buyer'),
            ('buyer', reverse('conversation-list'), 'Seller'),
            ('buyer', reverse('message-list') + f'?conversation={self.conversation.id}', 'Seller'),
            ('buyer', reverse('favorite-list'), 'Seller'),
            ('moderator', reverse('kyc_review_queue'), 'RCCM'),
        ]
        for viewer, url, expected in witnesses:
            response = self.client_for(viewer).get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertIn(expected, response.content.decode(), f'témoin vide : {url}')

    # --- réponses d'écriture -----------------------------------------------------------

    def test_write_responses_do_not_leak_either(self):
        # Le contact de « third » (premier cas) ouvre son droit d'avis (deuxième cas), sans délai ici.
        ReviewSettings.objects.filter(pk=ReviewSettings.get_solo().pk).update(
            delay_after_contact_hours=0, min_account_age_hours=0,  # update() contourne le minimum de 1 h (tests seulement)
        )
        cases = [
            ('third', 'contact-list', {'post': str(self.offer.id), 'message': 'Bonjour, toujours disponible ?'}),
            ('third', 'review-list', {
                'post': str(self.offer.id), 'offer_rating': 5, 'seller_rating': 5,
                'content': 'Un avis tout à fait correct et assez long.',
            }),
            ('buyer', 'message-list', {'conversation': str(self.conversation.id), 'content': 'Merci'}),
            ('third', 'report-list', {
                'target_type': 'POST', 'object_id': str(self.offer.id), 'reason': 'SPAM', 'description': 'Doute',
            }),
        ]
        for viewer, name, payload in cases:
            response = self.client_for(viewer).post(reverse(name), payload, format='json')
            self.assertLess(response.status_code, 500, name)
            self.assertIn(response.status_code, (200, 201), f'{name} : {response.content[:200]}')
            self.assert_clean(response, reverse(name), viewer)
        favorite = self.client_for('third').post(reverse('offer-favorite', args=[self.offer.id]))
        self.assertEqual(favorite.status_code, 200)
        self.assert_clean(favorite, 'favorite', 'third')

    # --- recherche plein texte ---------------------------------------------------------

    def test_search_by_phone_or_email_finds_nothing(self):
        seller_phone, seller_email = self.PEOPLE['seller']
        for term in (seller_phone, seller_email, '970000001', 'seller-secret'):
            for name in ('offer-list', 'business_list'):
                for viewer in (None, 'third'):
                    response = self.client_for(viewer).get(reverse(name), {'search': term})
                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    results = payload['results'] if isinstance(payload, dict) else payload
                    self.assertEqual(results, [], f'{name} trouve le vendeur par « {term} »')

    # --- une seule route renvoie un numéro de contact ----------------------------------

    def test_only_the_adr_routes_look_like_phone_reveal_routes(self):
        """Hors les routes de réglages du titulaire (numéro masqué), les seules routes qui parlent de
        révélation sont celles de l'ADR 0005 (5.4 et 5.5) : pas de route par lot, par numéro ni par utilisateur."""
        routes = [r for r in iter_routes() if re.search(r'phone|reveal|bulk|batch|numero', r)]
        self.assertEqual(sorted(set(routes) - set(CONTACT_SETTINGS_ROUTES)), sorted(REVEAL_ROUTES))

    def post_everywhere(self, viewer):
        """POST sur chaque route de l'API avec un corps riche (offre, canal, conversation...) : renvoie
        {chemin: réponse}. L'inventaire prouve qu'aucune route, sauf la révélation, ne produit le numéro."""
        client = self.client_for(viewer)
        body = {
            'offer': str(self.offer.id), 'post': str(self.offer.id), 'channel': 'CALL',
            'conversation': str(self.conversation.id), 'message': 'Bonjour', 'content': 'Bonjour',
        }
        responses = {}
        for route in iter_routes():
            for path in self.expand(route):
                response = client.post('/' + path, body, format='json')
                self.assertLess(response.status_code, 500, f'{path} : {response.status_code}')
                responses.setdefault(route, []).append((path, response))
        return responses

    def test_inventory_no_route_but_reveal_returns_the_contact_number(self):
        seller_number = self.CONTACT_NUMBERS['seller']
        revealing = []
        for route, items in self.post_everywhere('buyer').items():
            for path, response in items:
                body = response.content.decode('utf-8', errors='ignore')
                if seller_number in body or seller_number[4:] in body:
                    revealing.append((route, response.status_code))
        self.assertEqual(sorted(set(revealing)), [('api/interactions/contacts/reveal/', 201)])

    def test_inventory_other_viewers_never_get_the_seller_number_from_any_route(self):
        for viewer in ('third', 'moderator'):
            for route, items in self.post_everywhere(viewer).items():
                if route == 'api/interactions/contacts/reveal/':
                    continue  # un compte quelconque obtient le numéro consenti, comme le visiteur
                for path, response in items:
                    self.assert_clean(response, '/' + path, viewer)

    def test_reveal_is_the_only_response_with_the_number_and_it_is_not_cacheable(self):
        response = self.client_for('buyer').post(
            '/api/interactions/contacts/reveal/', {'offer': str(self.offer.id), 'channel': 'WHATSAPP'}, format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn(self.CONTACT_NUMBERS['seller'], response.content.decode())
        # Anonyme : refusé, sans numéro.
        refused = self.client_for(None).post(
            '/api/interactions/contacts/reveal/', {'offer': str(self.offer.id), 'channel': 'CALL'}, format='json',
        )
        self.assertEqual(refused.status_code, 401)
        self.assertNotIn('891111111', refused.content.decode())

    def reveal_as_buyer(self):
        response = self.client_for('buyer').post(
            '/api/interactions/contacts/reveal/', {'offer': str(self.offer.id), 'channel': 'CALL'}, format='json',
        )
        self.assertIn(response.status_code, (200, 201))

    def test_after_a_reveal_the_number_is_nowhere_else_in_the_api(self):
        self.reveal_as_buyer()
        for viewer in (None, 'buyer', 'third', 'moderator', 'admin'):
            self.crawl(viewer)

    def test_the_seller_never_sees_the_visitor_number_or_identifier(self):
        self.reveal_as_buyer()
        self.crawl('seller')
        response = self.client_for('seller').get('/api/interactions/contacts/reveals/received/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        text = response.content.decode()
        self.assertIn('Buyer', text)  # le nom d'affichage, seule identité montrée
        for forbidden in (str(self.users['buyer'].id), self.PEOPLE['buyer'][1], self.PEOPLE['buyer'][0],
                          self.CONTACT_NUMBERS['buyer'], self.CONTACT_NUMBERS['seller']):
            self.assertNotIn(forbidden, text)
        for key in keys_of(response.json()):
            self.assertFalse(LEAKY_KEY_RE.search(key), key)

    def test_the_received_list_is_empty_for_moderators_and_administrators(self):
        self.reveal_as_buyer()
        for viewer in ('moderator', 'admin', 'third', 'buyer'):
            response = self.client_for(viewer).get('/api/interactions/contacts/reveals/received/')
            self.assertEqual(response.json()['count'], 0, viewer)

    def test_the_number_is_in_no_event_audit_notification_or_stored_message(self):
        from apps.moderation.models import AuditLog
        from apps.notifications.models import Notification
        from apps.platform_core.models import OutboxEvent
        from apps.platform_core.testing import dispatch_outbox_now

        self.reveal_as_buyer()
        self.reveal_as_buyer()  # renvoi idempotent : un second audit
        dispatch_outbox_now()
        stored = [
            *(f'{a.action} {a.details}' for a in AuditLog.objects.all()),
            *(str(e.payload) for e in OutboxEvent.objects.all()),
            *(f'{n.title} {n.content} {n.link}' for n in Notification.objects.all()),
            *(m.content for m in Message.objects.all()),
            *(c.message for c in ContactEvent.objects.all()),
            *(r.description for r in Report.objects.all()),
        ]
        # Témoins : l'audit, l'événement et la notification existent bel et bien.
        self.assertEqual(sum('contact.number_revealed' in text for text in stored), 2)
        self.assertTrue(OutboxEvent.objects.filter(event_type='marketplace.contact_revealed').exists())
        self.assertTrue(any('demandé votre numéro' in text for text in stored))
        number = self.CONTACT_NUMBERS['seller']
        for text in stored:
            for value in (number, number[4:], f'+243 {number[4:6]} *** ** {number[-2:]}'):
                self.assertNotIn(value, text)
        self.assertFalse(Notification.objects.filter(content__contains='demandé votre numéro').exclude(
            user=self.users['seller']).exists())

    # --- réglages de contact (ADR 0005, T2) --------------------------------------------

    def test_contact_settings_routes_are_exactly_the_four_of_the_adr_and_take_no_user_id(self):
        routes = [r for r in iter_routes() if r.startswith('api/accounts/contact-settings')]
        self.assertEqual(sorted(routes), sorted(CONTACT_SETTINGS_ROUTES))

    def test_contact_settings_show_only_the_owner_masked_numbers(self):
        for viewer in ('seller', 'buyer', 'moderator', 'admin'):
            response = self.client_for(viewer).get('/api/accounts/contact-settings/')
            self.assertEqual(response.status_code, 200)
            self.assert_clean(response, '/api/accounts/contact-settings/', viewer)
            text = response.content.decode()
            # Jamais de numéro complet, même celui du titulaire.
            for number in (*self.CONTACT_NUMBERS.values(), self.PEOPLE[viewer][0]):
                self.assertNotIn(number, text)
                self.assertNotIn(number[4:], text)
            for masked in re.findall(r'\+243 [0-9*]{2} \*{3} \*{2} [0-9]{2}', text):
                self.assertEqual(len(re.findall(r'[0-9]', masked[4:])), 4)  # hors indicatif : 4 chiffres au plus
            self.assertEqual(response['Cache-Control'], 'no-store')
        seller_body = self.client_for('seller').get('/api/accounts/contact-settings/').json()
        self.assertEqual(seller_body['phone']['masked'], '+243 89 *** ** 11')
        self.assertEqual(seller_body['login_phone_masked'], '+243 97 *** ** 01')

    def test_offers_expose_channels_but_not_the_contact_number(self):
        for url in (reverse('offer-detail', args=[self.offer.id]), reverse('offer-list')):
            response = self.client_for(None).get(url)
            self.assertEqual(response.status_code, 200)
            text = response.content.decode()
            self.assertIn('"allowed_channels":["MESSAGE","CALL","WHATSAPP"]', text.replace(' ', ''))
            self.assertNotIn('891111111', text)
            self.assertNotIn('1111', text.replace(str(self.offer.id), ''))

    def test_writes_on_contact_settings_do_not_leak_other_numbers(self):
        client = self.client_for('buyer')
        for response in (
            client.put('/api/accounts/contact-settings/phone/', {'phone': '+243893333333'}, format='json'),
            client.put('/api/accounts/contact-settings/channels/CALL/', {'enabled': False}, format='json'),
        ):
            self.assertEqual(response.status_code, 200)
            self.assert_clean(response, '/api/accounts/contact-settings/ (écriture)', 'buyer')
            self.assertNotIn('893333333', response.content.decode())
