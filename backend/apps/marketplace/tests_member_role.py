"""Rôle « Membre » et périmètre partiel côté marketplace (L1-01-B6, ADR 0010 D2, D3 ; relecture et audit de B6).

Un `MEMBER` n'a ni `offer.view_internal` ni `stats.view` : il ne voit aucune offre non publique de son organisation
(pause, corbeille, masquée par la modération : 404 comme un tiers), ne reçoit jamais le drapeau de modération, et
toutes les routes « internes » sous `X-Context` de l'organisation lui répondent 403 `DENY_PERMISSION`. Même chose
pour un membre dont l'appartenance est limitée à une ville (fermé par défaut)."""
import uuid
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status

from apps.identity.models import Membership, User

from . import services
from .models import Offer
from .tests_contexts import EDITOR, ContextBase, ctx_header

MEMBER = 'MEMBER'
NON_PUBLIC_STATES = {
    'pause': {'status': 'PAUSED', 'is_active': False},
    'corbeille': {'is_deleted': True},
    'masquée': {'is_hidden_by_moderation': True, 'is_active': False},
}


class MemberOfferVisibilityTests(ContextBase):
    def setUp(self):
        super().setUp()
        self.simple = User.objects.create_user(email='simple@example.com', password='x', full_name='Simple Membre')
        self.membership = self.join(self.simple, role=MEMBER)
        self.editor = User.objects.create_user(email='editeur@example.com', password='x', full_name='Edi Teur')
        self.join(self.editor, role=EDITOR)

    def retrieve(self, user, offer):
        self.client.force_authenticate(user)
        return self.client.get(reverse('offer-detail', args=[offer.id]))

    def test_member_gets_404_on_non_public_offers_of_its_organization(self):
        for label, fields in NON_PUBLIC_STATES.items():
            offer = self.org_offer(title=f'Offre interne {label}')
            Offer.objects.filter(pk=offer.pk).update(**fields)
            with self.subTest(state=label):
                self.assertEqual(self.retrieve(self.simple, offer).status_code, status.HTTP_404_NOT_FOUND)
                # Témoin : l'éditeur de la même organisation voit l'offre (et le drapeau de modération).
                response = self.retrieve(self.editor, offer)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertIn('is_hidden_by_moderation', response.data)

    def test_member_sees_a_public_offer_without_the_moderation_flag(self):
        offer = self.org_offer(title='Offre publique de l organisation')
        response = self.retrieve(self.simple, offer)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('is_hidden_by_moderation', response.data)

    def test_member_retrieve_costs_no_more_queries_than_an_editor(self):
        """Relecture B6 : la lecture « Membre » (pas d'`offer.view_internal`) n'ajoute aucune requête par rapport à
        celle de l'éditeur de la même organisation (même chemin d'autorisation, sans N+1)."""
        offer = self.org_offer(title='Offre publique comptée en requêtes')
        # Amorce pour les deux comptes (cache de permissions Django porté par l'objet compte, réglages).
        self.retrieve(self.editor, offer)
        self.retrieve(self.simple, offer)
        with CaptureQueriesContext(connection) as editor_queries:
            self.assertEqual(self.retrieve(self.editor, offer).status_code, status.HTTP_200_OK)
        with self.assertNumQueries(len(editor_queries)):
            self.assertEqual(self.retrieve(self.simple, offer).status_code, status.HTTP_200_OK)

    def test_member_view_of_its_own_organization_offer_is_not_counted(self):
        """Le compteur de vues reste sur l'appartenance : un Membre ne gonfle pas les statistiques."""
        offer = self.org_offer(title='Offre non comptée')
        with mock.patch.object(services, 'register_view') as register:
            self.assertEqual(self.retrieve(self.simple, offer).status_code, status.HTTP_200_OK)
            register.assert_not_called()
            self.retrieve(self.buyer, offer)  # témoin : un tiers est compté
            register.assert_called_once()

    def test_city_scoped_editor_is_treated_like_a_stranger_for_non_public_offers(self):
        Membership.objects.filter(organization=self.org, user=self.editor).update(
            scope_type='CITY', scope_id=uuid.uuid4(),
        )
        offer = self.org_offer(title='Offre en pause, périmètre partiel')
        Offer.objects.filter(pk=offer.pk).update(status='PAUSED', is_active=False)
        self.assertEqual(self.retrieve(self.editor, offer).status_code, status.HTTP_404_NOT_FOUND)


class MemberInternalRoutesTests(ContextBase):
    def setUp(self):
        super().setUp()
        self.simple = User.objects.create_user(email='simple2@example.com', password='x', full_name='Simple Deux')
        self.join(self.simple, role=MEMBER)
        self.client.force_authenticate(self.simple)
        self.header = ctx_header('ORGANIZATION', self.org.pk)

    def assertDenied(self, response):
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, getattr(response, 'data', None))
        self.assertEqual(response.data['code'], 'DENY_PERMISSION')

    def test_dashboard_my_offers_and_trash_are_refused(self):
        for url in (
            reverse('dashboard_stats'), reverse('offer-list') + '?my_posts=true', reverse('offer-trash'),
        ):
            with self.subTest(url=url):
                self.assertDenied(self.client.get(url, **self.header))

    def test_offer_stats_are_refused_on_public_and_non_public_offers(self):
        public = self.org_offer(title='Offre publique stats')
        paused = self.org_offer(title='Offre en pause stats')
        Offer.objects.filter(pk=paused.pk).update(status='PAUSED', is_active=False)
        for offer in (public, paused):
            with self.subTest(offer=offer.title):
                self.assertDenied(self.client.get(reverse('offer_stats', args=[offer.id])))

    def test_city_scoped_editor_is_refused_on_internal_routes(self):
        editor = User.objects.create_user(email='edi2@example.com', password='x', full_name='Edi Deux')
        self.join(editor, role=EDITOR)
        Membership.objects.filter(organization=self.org, user=editor).update(scope_type='CITY', scope_id=uuid.uuid4())
        self.client.force_authenticate(editor)
        for url in (reverse('dashboard_stats'), reverse('offer-trash')):
            with self.subTest(url=url):
                self.assertDenied(self.client.get(url, **self.header))
