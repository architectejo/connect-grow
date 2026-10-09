"""Test de non-fuite exhaustif (L0-10a-a, règle 10) : aucun téléphone ni e-mail d'un utilisateur
ne sort dans une réponse GET destinée à un anonyme ou à un tiers, sur toutes les routes."""
import json
import re

from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APITestCase

from apps.catalog.models import Category, City, Commune
from apps.common.factories import make_test_image
from apps.identity.models import BusinessProfile, User
from apps.marketplace.models import ContactEvent, ExchangeProposal, Favorite, Offer
from apps.messaging.models import Conversation, Message
from apps.moderation.models import Report, Sanction
from apps.reviews.models import Deal, Review

# Seul l'espace personnel d'un utilisateur renvoie ses propres coordonnées.
OWN_DATA_ROUTES = ('api/accounts/me/',)
PARAM_RE = re.compile(r'<(?:\w+:)?\w+>')
REGEX_PARAM_RE = re.compile(r'\(\?P<(\w+)>[^)]*\)')


def iter_routes(resolver=None, prefix=''):
    resolver = resolver or get_resolver()
    for entry in resolver.url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from iter_routes(entry, route)
        elif isinstance(entry, URLPattern) and not route.startswith(('admin/', '^admin')):
            yield route


def normalize(route):
    """Route DRF (regex du routeur ou chemin) -> chemin avec des marques <param>."""
    route = REGEX_PARAM_RE.sub(lambda match: '<' + match.group(1) + '>', route)
    return route.replace('^', '').replace('$', '').replace(chr(92) + '.', '.').replace('?', '')


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
        'staff': ('+243970000004', 'staff-secret@example.com'),
    }

    def setUp(self):
        city = City.objects.create(name='Kinshasa')
        commune = Commune.objects.create(city=city, name='Gombe')
        category = Category.objects.create(name='Électronique', slug='electronique')
        self.users = {}
        for name, (phone, email) in self.PEOPLE.items():
            self.users[name] = User.objects.create_user(
                email=email, phone=phone, password='x', full_name=name.capitalize(), phone_verified=True,
                is_staff=(name == 'staff'),
            )
        seller, buyer = self.users['seller'], self.users['buyer']
        BusinessProfile.objects.create(user=seller, business_name='Boutique', bio='Bio', is_verified=True)
        offer = Offer.objects.create(
            seller=seller, category_id=category.id, commune_id=commune.id, title='Un joli canapé à vendre',
            description='Description suffisamment longue pour le CDC.', price=100, main_image=make_test_image(),
        )
        Favorite.objects.create(user=buyer, offer=offer)
        ContactEvent.objects.create(offer=offer, sender=buyer, message='Bonjour')
        ExchangeProposal.objects.create(offer=offer, sender=buyer, message='Echange ?')
        deal = Deal.objects.create(offer_id=offer.id, initiator=buyer, counterparty=seller)
        deal.confirm()
        review = Review.objects.create(
            deal=deal, offer_id=offer.id, user=buyer, reviewed_user=seller,
            content='Avis suffisamment long pour être valide.', rating=4,
        )
        conversation = Conversation.objects.create(offer_id=offer.id)
        conversation.participants.add(seller, buyer)
        message = Message.objects.create(conversation=conversation, sender=buyer, content='Salut')
        report = Report.objects.create(
            target_type='offer', target_id=offer.id, reporter=buyer, reason=Report.REASON_SPAM,
        )
        sanction = Sanction.objects.create(
            user=seller, sanction_type=Sanction.TYPE_AVERTISSEMENT, reason='Test', issued_by=self.users['staff'],
        )
        self.pool = [
            *(str(u.id) for u in self.users.values()), str(offer.id), str(review.id), str(deal.id),
            str(conversation.id), str(message.id), str(report.id), str(sanction.id),
            str(category.id), str(city.id), str(commune.id),
        ]

    def expand(self, route):
        """Une route à paramètres est appelée avec chaque identifiant connu."""
        if not PARAM_RE.search(route):
            return [route]
        return [PARAM_RE.sub(identifier, route) for identifier in self.pool]

    def forbidden_values(self, viewer):
        return [value for name, pair in self.PEOPLE.items() if name != viewer for value in pair]

    def crawl(self, viewer):
        client = self.client_class()
        if viewer:
            client.force_authenticate(self.users[viewer])
        visited = 0
        for route in iter_routes():
            route = normalize(route)
            for path in self.expand(route):
                url = '/' + path
                response = client.get(url, {'page_size': 100})
                visited += 1
                if response.status_code >= 500:
                    self.fail(f'{url} : {response.status_code}')
                body = response.content.decode('utf-8', errors='ignore')
                for value in self.forbidden_values(viewer):
                    self.assertNotIn(value, body, f'{viewer or "anonyme"} voit {value} sur {url}')
                if path.startswith(OWN_DATA_ROUTES):
                    continue
                try:
                    payload = json.loads(body)
                except ValueError:
                    continue
                leaked = {k for k in keys_of(payload) if k in ('phone', 'email', 'phone_verified')}
                self.assertFalse(leaked, f'clé {leaked} dans la réponse de {url} ({viewer or "anonyme"})')
        return visited

    def test_no_phone_or_email_for_anonymous(self):
        self.assertGreater(self.crawl(None), 20)

    def test_no_phone_or_email_for_an_unrelated_user(self):
        self.assertGreater(self.crawl('third'), 20)

    def test_no_phone_or_email_for_the_counterparty(self):
        self.assertGreater(self.crawl('buyer'), 20)

    def test_the_seller_does_not_get_other_people_data(self):
        self.assertGreater(self.crawl('seller'), 20)

    def test_a_moderator_does_not_get_users_contact_data_through_the_api(self):
        self.assertGreater(self.crawl('staff'), 20)

    def test_no_route_returns_several_contact_details_at_once(self):
        """Aucune route de numéro, de révélation ou de lot d'offres : seule la prise de contact
        existante (ContactEvent, sans numéro) porte « contact » dans son chemin."""
        routes = [normalize(r) for r in iter_routes() if re.search(r'phone|reveal|bulk|batch|numero', r)]
        self.assertEqual(routes, [])
