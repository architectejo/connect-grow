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
from apps.identity.models import BusinessProfile, KycDocument, User
from apps.marketplace.models import ContactEvent, ExchangeProposal, Favorite, Offer
from apps.messaging.models import Conversation, Message
from apps.moderation.models import Report, Sanction
from apps.reviews.models import Deal, Review

# Seul l'espace personnel d'un utilisateur renvoie ses propres coordonnées. `phone_verified`
# est interdit partout ailleurs : il révèle qu'un numéro existe sur le compte.
OWN_DATA_ROUTES = ('api/accounts/me/',)
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
        ContactEvent.objects.create(offer=self.offer, sender=buyer, message='Bonjour')
        ExchangeProposal.objects.create(offer=self.offer, sender=buyer, message='Echange ?')
        deal = Deal.objects.create(offer_id=self.offer.id, initiator=buyer, counterparty=seller)
        deal.confirm()
        self.review = Review.objects.create(
            deal=deal, offer_id=self.offer.id, user=buyer, reviewed_user=seller,
            content='Avis suffisamment long pour être valide.', rating=4,
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
            *(str(u.id) for u in self.users.values()), str(self.offer.id), str(self.review.id), str(deal.id),
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
        return [value for name, pair in self.PEOPLE.items() if name != viewer for value in pair]

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
        third_deal = Deal.objects.create(
            offer_id=self.offer.id, initiator=self.users['third'], counterparty=self.users['seller'],
        )
        third_deal.confirm()
        cases = [
            ('third', 'contact-list', {'post': str(self.offer.id), 'message': 'Bonjour, toujours disponible ?'}),
            ('third', 'review-list', {
                'deal': str(third_deal.id), 'rating': 5, 'content': 'Un avis tout à fait correct et assez long.',
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

    # --- pas de route de révélation ---------------------------------------------------

    def test_no_phone_reveal_route(self):
        """Aucune route ne s'appelle numéro, téléphone, révélation ou lot (la révélation
        encadrée par consentement viendra avec L0-10a-c)."""
        routes = [r for r in iter_routes() if re.search(r'phone|reveal|bulk|batch|numero', r)]
        self.assertEqual(routes, [])
