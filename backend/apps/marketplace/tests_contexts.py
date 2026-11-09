"""Offres et compteurs rattachés à un contexte vendeur (ADR 0006, T5a / L0-09e) : création, modification et listes
selon le contexte actif (`X-Context`), autorisation par objet, visibilité publique dénormalisée (`seller_is_public`),
objet `seller`, absence de fuite, migrations de données."""
import importlib
import json
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.identity import services as identity_services
from apps.identity.models import (
    CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint, KycDocument, Membership, Organization, ProviderProfile,
    User,
)
from apps.moderation.models import AuditLog, Sanction
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now
from apps.visibility.models import DailyVisibilityCounter

from . import services
from apps.common.factories import make_test_image

from .models import ContactEvent, Offer
from .tests import MarketplaceTestBase

OWNER, ADMIN, EDITOR, ANALYST = 'OWNER', 'ADMIN', 'EDITOR', 'ANALYST'
SENTINEL_PHONE = '+243811234567'
SENTINEL_EMAIL = 'secret-sentinelle@example.com'


def ctx_header(context_type, context_id):
    return {'HTTP_X_CONTEXT': f'{context_type}:{context_id}'}


class ContextBase(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        self.member = User.objects.create_user(email='member@example.com', password='x', full_name='Membre Test')
        self.org = Organization.objects.create(name='Atelier X', org_type='ENTREPRISE')
        self.other_org = Organization.objects.create(name='Atelier B', org_type='BOUTIQUE')

    def join(self, user, org=None, role=OWNER):
        return Membership.objects.create(organization=org or self.org, user=user, role=role)

    def provider(self, user=None, name='Marie couture'):
        return ProviderProfile.objects.create(user=user or self.seller, display_name=name, bio='Couture sur mesure')

    def create(self, user, headers=None, **overrides):
        self.client.force_authenticate(user)
        return self.client.post(reverse('offer-list'), self.offer_payload(**overrides), **(headers or {}))

    def org_offer(self, org=None, creator=None, **kwargs):
        org = org or self.org
        return self.make_offer(
            seller_context_type='ORGANIZATION', seller_context_id=org.pk,
            created_by=creator or self.member, **kwargs,
        )

    def error_code(self, response):
        return response.data.get('code')


class CreationByContextTests(ContextBase):
    def test_personal_context_without_header(self):
        response = self.create(self.seller)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        offer = Offer.objects.get(pk=response.data['id'])
        self.assertEqual((offer.seller_context_type, offer.seller_context_id), ('USER', self.seller.pk))
        self.assertEqual(offer.created_by, self.seller)
        self.assertTrue(offer.seller_is_public)
        self.assertEqual(response.data['seller']['context_type'], 'USER')

    def test_explicit_personal_header(self):
        response = self.create(self.seller, ctx_header('USER', self.seller.pk))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_provider_context(self):
        profile = self.provider()
        response = self.create(self.seller, ctx_header('PROVIDER', profile.pk))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        offer = Offer.objects.get(pk=response.data['id'])
        self.assertEqual((offer.seller_context_type, offer.seller_context_id), ('PROVIDER', profile.pk))
        self.assertEqual(offer.created_by, self.seller)
        self.assertEqual(response.data['seller']['context_type'], 'PROVIDER')
        self.assertEqual(response.data['seller']['display_name'], 'Marie couture')
        self.assertEqual(response.data['seller_name'], 'Marie couture')

    def test_archived_provider_cannot_publish(self):
        profile = self.provider()
        identity_services.archive_provider(self.seller)
        response = self.create(self.seller, ctx_header('PROVIDER', profile.pk))
        self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_OBJECT_STATE'))
        self.assertEqual(Offer.objects.count(), 0)

    def test_someone_elses_provider_profile_is_refused(self):
        profile = self.provider(self.buyer)
        response = self.create(self.seller, ctx_header('PROVIDER', profile.pk))
        self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_CONTEXT'))
        self.assertEqual(Offer.objects.count(), 0)

    def test_organization_roles_that_can_publish(self):
        for role in (OWNER, ADMIN, EDITOR):
            with self.subTest(role=role):
                user = User.objects.create_user(email=f'{role.lower()}@example.com', password='x', full_name=role)
                self.join(user, role=role)
                response = self.create(user, ctx_header('ORGANIZATION', self.org.pk), title=f'Offre publiée par {role}')
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                offer = Offer.objects.get(pk=response.data['id'])
                self.assertEqual((offer.seller_context_type, offer.seller_context_id), ('ORGANIZATION', self.org.pk))
                self.assertEqual(offer.created_by, user)
                self.assertTrue(offer.seller_is_public)
                seller = response.data['seller']
                self.assertEqual((seller['context_type'], seller['display_name'], seller['org_type']),
                                 ('ORGANIZATION', 'Atelier X', 'ENTREPRISE'))

    def test_analyst_cannot_publish(self):
        self.join(self.member, role=ANALYST)
        response = self.create(self.member, ctx_header('ORGANIZATION', self.org.pk))
        self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_PERMISSION'))
        self.assertEqual(Offer.objects.count(), 0)

    def test_non_member_and_unknown_organization_get_the_same_refusal(self):
        for target in (self.org.pk, uuid.uuid4()):
            with self.subTest(target=target):
                response = self.create(self.member, ctx_header('ORGANIZATION', target))
                self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_RELATION'))
        self.assertEqual(Offer.objects.count(), 0)

    def test_malformed_header_never_falls_back_to_the_personal_context(self):
        for raw in ('', 'ORGANIZATION', 'ORGANIZATION:nope', 'TEAM:' + str(self.org.pk), f'USER:{self.buyer.pk}'):
            with self.subTest(raw=raw):
                response = self.create(self.seller, {'HTTP_X_CONTEXT': raw})
                self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_CONTEXT'))
        self.assertEqual(Offer.objects.count(), 0)

    def test_revoked_member_publishes_nothing_not_even_a_personal_offer(self):
        membership = self.join(self.member, role=EDITOR)
        membership.status = Membership.STATUS_REVOKED
        membership.save()
        response = self.create(self.member, ctx_header('ORGANIZATION', self.org.pk))
        self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_RELATION'))
        self.assertEqual(Offer.objects.count(), 0)

    def test_suspended_and_archived_organizations_refuse(self):
        self.join(self.member, role=OWNER)
        for org_status, code in ((Organization.STATUS_SUSPENDED, 'DENY_SECURITY'),
                                 (Organization.STATUS_ARCHIVED, 'DENY_OBJECT_STATE')):
            with self.subTest(status=org_status):
                Organization.objects.filter(pk=self.org.pk).update(status=org_status)
                response = self.create(self.member, ctx_header('ORGANIZATION', self.org.pk))
                self.assertEqual((response.status_code, self.error_code(response)), (403, code))
        self.assertEqual(Offer.objects.count(), 0)

    def test_restricted_account_cannot_publish_in_any_context(self):
        self.join(self.member, role=OWNER)
        Sanction.objects.create(user=self.member, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='Test')
        for headers in (None, ctx_header('ORGANIZATION', self.org.pk)):
            response = self.create(self.member, headers)
            self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_SECURITY'))
        self.assertEqual(Offer.objects.count(), 0)

    def test_the_body_cannot_choose_the_seller(self):
        self.join(self.member, role=OWNER)
        for field, value in (
            ('seller', str(self.buyer.pk)), ('seller_context_type', 'ORGANIZATION'),
            ('seller_context_id', str(self.org.pk)), ('created_by', str(self.buyer.pk)),
            ('seller_is_public', 'false'),
        ):
            with self.subTest(field=field):
                response = self.create(self.seller, **{field: value})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('seller_context_id', response.data)
                self.assertEqual(response.data['seller_context_id'][0].code, 'seller_not_settable')
        self.assertEqual(Offer.objects.count(), 0)

    def test_refusal_precedes_validation(self):
        # Un analyste qui envoie un corps invalide reçoit le refus d'autorisation, pas des erreurs de champ.
        self.join(self.member, role=ANALYST)
        self.client.force_authenticate(self.member)
        response = self.client.post(reverse('offer-list'), {}, **ctx_header('ORGANIZATION', self.org.pk))
        self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_PERMISSION'))

    def test_publication_is_audited_with_its_context(self):
        self.join(self.member, role=EDITOR)
        response = self.create(self.member, ctx_header('ORGANIZATION', self.org.pk))
        entry = AuditLog.objects.get(action='OFFER_CREATED')
        self.assertEqual(str(entry.target_id), response.data['id'])
        self.assertEqual((entry.context_type, entry.context_id, entry.actor), ('ORGANIZATION', self.org.pk, self.member))

    def test_two_requests_with_two_contexts_are_each_handled_under_their_own(self):
        self.join(self.member, role=OWNER)
        first = self.create(self.member, ctx_header('ORGANIZATION', self.org.pk), title='Offre de l organisation')
        second = self.create(self.member, None, title='Offre personnelle du membre')
        offers = {o.title: o for o in Offer.objects.all()}
        self.assertEqual(offers['Offre de l organisation'].seller_context_id, self.org.pk)
        self.assertEqual(offers['Offre personnelle du membre'].seller_context_id, self.member.pk)
        self.assertEqual((first.status_code, second.status_code), (201, 201))


class ObjectAuthorizationTests(ContextBase):
    """Une action sur une offre existante dépend du contexte PROPRIÉTAIRE de l'offre, jamais de l'en-tête."""

    def patch(self, user, offer, headers=None, **body):
        self.client.force_authenticate(user)
        return self.client.patch(reverse('offer-detail', args=[offer.id]), body, **(headers or {}))

    def test_editor_of_a_and_analyst_of_b_cannot_use_a_header_to_edit_b(self):
        self.join(self.member, self.org, EDITOR)
        self.join(self.member, self.other_org, ANALYST)
        offer_b = self.org_offer(self.other_org, creator=self.buyer)
        offer_a = self.org_offer(self.org, creator=self.buyer)

        # En-tête de A (éditeur) sur l'offre de B (analyste) : refus, d'après le rôle réel dans B.
        response = self.patch(self.member, offer_b, ctx_header('ORGANIZATION', self.org.pk), price=1)
        self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_PERMISSION'))
        # Sans en-tête, ou avec l'en-tête de B : même résultat.
        for headers in (None, ctx_header('ORGANIZATION', self.other_org.pk)):
            response = self.patch(self.member, offer_b, headers, price=1)
            self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_PERMISSION'))
        offer_b.refresh_from_db()
        self.assertEqual(offer_b.price, 100)
        # L'offre de A reste modifiable quel que soit l'en-tête (ignoré) : l'éditeur de A y est autorisé.
        for headers in (None, ctx_header('ORGANIZATION', self.other_org.pk)):
            response = self.patch(self.member, offer_a, headers, price=55)
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_roles_on_lifecycle_actions(self):
        offer = self.org_offer(creator=self.buyer)
        analyst = User.objects.create_user(email='an@example.com', password='x', full_name='An')
        editor = User.objects.create_user(email='ed@example.com', password='x', full_name='Ed')
        self.join(analyst, role=ANALYST)
        self.join(editor, role=EDITOR)
        self.client.force_authenticate(analyst)
        for name in ('pause', 'renew', 'mark-sold', 'soft-delete'):
            response = self.client.post(reverse(f'offer-{name}', args=[offer.id]))
            self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_PERMISSION'), name)
        self.assertEqual(self.client.delete(reverse('offer-hard-delete', args=[offer.id])).status_code, 403)
        self.client.force_authenticate(editor)
        self.assertEqual(self.client.post(reverse('offer-pause', args=[offer.id])).status_code, 200)
        self.assertEqual(self.client.post(reverse('offer-unpause', args=[offer.id])).status_code, 200)
        self.assertEqual(self.client.post(reverse('offer-soft-delete', args=[offer.id])).status_code, 200)
        self.assertEqual(self.client.post(reverse('offer-restore', args=[offer.id])).status_code, 200)
        self.assertEqual(self.client.delete(reverse('offer-hard-delete', args=[offer.id])).status_code, 200)
        self.assertFalse(Offer.objects.filter(pk=offer.pk).exists())
        entry = AuditLog.objects.get(action='OFFER_DELETED')
        self.assertEqual((entry.context_type, entry.context_id), ('ORGANIZATION', self.org.pk))

    def test_revoked_author_loses_access_but_the_offer_stays_with_the_organization(self):
        author, colleague = self.member, User.objects.create_user(email='col@example.com', password='x', full_name='C')
        membership = self.join(author, role=EDITOR)
        self.join(colleague, role=EDITOR)
        self.join(User.objects.create_user(email='own@example.com', password='x', full_name='P'), role=OWNER)  # M3
        response = self.create(author, ctx_header('ORGANIZATION', self.org.pk))
        offer = Offer.objects.get(pk=response.data['id'])
        membership.status = Membership.STATUS_REVOKED
        membership.save()

        denied = self.patch(author, offer, price=1)
        self.assertEqual((denied.status_code, self.error_code(denied)), (403, 'DENY_RELATION'))
        allowed = self.patch(colleague, offer, price=77)
        self.assertEqual(allowed.status_code, status.HTTP_200_OK, allowed.data)
        offer.refresh_from_db()
        self.assertEqual((offer.price, offer.seller_context_id, offer.created_by), (77, self.org.pk, author))

    def test_suspended_organization_blocks_its_members(self):
        offer = self.org_offer(creator=self.member)
        self.join(self.member, role=OWNER)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        response = self.patch(self.member, offer, price=1)
        self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_SECURITY'))

    def test_personal_offer_is_never_editable_by_an_organization_member(self):
        self.join(self.member, role=OWNER)
        offer = self.make_offer()
        response = self.patch(self.member, offer, ctx_header('ORGANIZATION', self.org.pk), price=1)
        self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_RELATION'))

    def test_body_cannot_move_an_offer_to_another_context(self):
        offer = self.make_offer()
        response = self.patch(self.seller, offer, seller_context_id=str(self.org.pk))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        offer.refresh_from_db()
        self.assertEqual(offer.seller_context_id, self.seller.pk)

    def test_the_service_ignores_protected_fields(self):
        offer = self.make_offer()
        services.update_offer(offer, actor=self.seller, changes={
            'price': 9, 'seller_context_id': self.org.pk, 'seller_context_type': 'ORGANIZATION', 'seller_is_public': False,
        })
        offer.refresh_from_db()
        self.assertEqual((offer.price, offer.seller_context_type, offer.seller_context_id, offer.seller_is_public),
                         (9, 'USER', self.seller.pk, True))

    def test_the_service_authorizes_again_inside_the_write(self):
        # Une révocation survenue après le contrôle de la vue est prise en compte par le service.
        offer = self.org_offer(creator=self.member)
        membership = self.join(self.member, role=EDITOR)
        membership.status = Membership.STATUS_REVOKED
        membership.save()
        from apps.common.contexts import ContextDenied

        with self.assertRaises(ContextDenied):
            services.pause_offer(offer, actor=self.member)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.STATUS_ACTIVE)

    def test_statistics_of_an_offer_follow_the_owner_context(self):
        offer = self.org_offer(creator=self.buyer)
        DailyVisibilityCounter.objects.create(
            offer_id=offer.id, seller_context_type='ORGANIZATION', seller_context_id=self.org.pk,
            date=timezone.localdate(), views=5,
        )
        url = reverse('offer_stats', args=[offer.id])
        analyst = User.objects.create_user(email='an@example.com', password='x', full_name='An')
        self.join(analyst, role=ANALYST)
        self.client.force_authenticate(analyst)
        self.assertEqual(self.client.get(url).data['history'][0]['views'], 5)  # stats.view : tous les rôles
        self.client.force_authenticate(self.buyer)
        denied = self.client.get(url)
        self.assertEqual((denied.status_code, denied.data['code']), (403, 'DENY_RELATION'))


class ListsByContextTests(ContextBase):
    def setUp(self):
        super().setUp()
        self.join(self.member, role=EDITOR)
        self.personal = self.make_offer(owner=self.member, title='Offre personnelle du membre')
        self.org_active = self.org_offer(title='Offre active de l organisation')
        self.org_trashed = self.org_offer(title='Offre en corbeille de l orga', is_deleted=True)
        self.personal_trashed = self.make_offer(owner=self.member, title='Corbeille personnelle', is_deleted=True)
        self.other_org_offer = self.org_offer(self.other_org, title='Offre d une autre organisation')
        self.client.force_authenticate(self.member)

    def titles(self, response):
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        return {row['title'] for row in rows}

    def test_my_posts_is_scoped_to_the_active_context(self):
        url = reverse('offer-list')
        self.assertEqual(self.titles(self.client.get(url, {'my_posts': 'true'})), {'Offre personnelle du membre'})
        in_org = self.client.get(url, {'my_posts': 'true'}, **ctx_header('ORGANIZATION', self.org.pk))
        self.assertEqual(self.titles(in_org), {'Offre active de l organisation'})

    def test_trash_is_scoped_to_the_active_context(self):
        url = reverse('offer-trash')
        self.assertEqual(self.titles(self.client.get(url)), {'Corbeille personnelle'})
        in_org = self.client.get(url, **ctx_header('ORGANIZATION', self.org.pk))
        self.assertEqual(self.titles(in_org), {'Offre en corbeille de l orga'})

    def test_internal_lists_refuse_a_context_of_which_the_user_is_not_a_member(self):
        for url, params in ((reverse('offer-list'), {'my_posts': 'true'}), (reverse('offer-trash'), {})):
            response = self.client.get(url, params, **ctx_header('ORGANIZATION', self.other_org.pk))
            self.assertEqual((response.status_code, self.error_code(response)), (403, 'DENY_RELATION'))

    def test_an_analyst_can_view_the_internal_lists(self):
        analyst = User.objects.create_user(email='an@example.com', password='x', full_name='An')
        self.join(analyst, role=ANALYST)
        self.client.force_authenticate(analyst)
        response = self.client.get(reverse('offer-list'), {'my_posts': 'true'}, **ctx_header('ORGANIZATION', self.org.pk))
        self.assertEqual(self.titles(response), {'Offre active de l organisation'})

    def test_filter_by_seller_context_identifier(self):
        self.client.force_authenticate(None)
        url = reverse('offer-list')
        self.assertEqual(self.titles(self.client.get(url, {'seller': str(self.org.pk)})), {'Offre active de l organisation'})
        self.assertEqual(
            self.titles(self.client.get(url, {'seller': str(self.org.pk), 'seller_type': 'ORGANIZATION'})),
            {'Offre active de l organisation'},
        )
        self.assertEqual(self.titles(self.client.get(url, {'seller': str(self.org.pk), 'seller_type': 'USER'})), set())
        self.assertEqual(self.titles(self.client.get(url, {'seller': str(self.org.pk), 'seller_type': 'NOPE'})), set())
        self.assertEqual(self.titles(self.client.get(url, {'seller': str(uuid.uuid4())})), set())
        self.assertEqual(
            self.titles(self.client.get(url, {'seller': str(self.member.pk), 'seller_type': 'USER'})),
            {'Offre personnelle du membre'},
        )

    def test_dashboard_is_scoped_to_the_active_context(self):
        for context_type, context_id, views in (('USER', self.member.pk, 3), ('ORGANIZATION', self.org.pk, 8)):
            DailyVisibilityCounter.objects.create(
                offer_id=uuid.uuid4(), seller_context_type=context_type, seller_context_id=context_id,
                date=timezone.localdate(), views=views,
            )
        url = reverse('dashboard_stats')
        personal = self.client.get(url).data['summary']
        in_org = self.client.get(url, **ctx_header('ORGANIZATION', self.org.pk)).data['summary']
        self.assertEqual((personal['total_views'], personal['active_posts']), (3, 1))
        self.assertEqual((in_org['total_views'], in_org['active_posts']), (8, 1))
        denied = self.client.get(url, **ctx_header('ORGANIZATION', self.other_org.pk))
        self.assertEqual((denied.status_code, self.error_code(denied)), (403, 'DENY_RELATION'))

    def test_contact_requesters_need_the_capability_of_the_active_context(self):
        url = reverse('contact-reveals-received')
        analyst = User.objects.create_user(email='an@example.com', password='x', full_name='An')
        self.join(analyst, role=ANALYST)
        self.client.force_authenticate(analyst)
        denied = self.client.get(url, **ctx_header('ORGANIZATION', self.org.pk))
        self.assertEqual((denied.status_code, self.error_code(denied)), (403, 'DENY_PERMISSION'))
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(url, **ctx_header('ORGANIZATION', self.org.pk)).status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 200)


class SellerVisibilityTests(ContextBase):
    """`seller_is_public` : calculé à la création, propagé par l'événement, réconcilié par la commande."""

    def public_ids(self):
        self.client.force_authenticate(None)
        rows = self.client.get(reverse('offer-list')).data
        rows = rows['results'] if isinstance(rows, dict) else rows
        return {row['id'] for row in rows}

    def test_default_public_for_an_active_seller(self):
        offer = self.make_offer()
        self.assertTrue(offer.seller_is_public)
        self.assertIn(str(offer.id), self.public_ids())

    def test_event_hides_and_restores_offers_when_the_account_is_deactivated(self):
        offer = self.make_offer()
        self.assertTrue(identity_services.set_account_active(self.seller.pk, False))
        dispatch_outbox_now()
        offer.refresh_from_db()
        self.assertFalse(offer.seller_is_public)
        self.assertNotIn(str(offer.id), self.public_ids())
        self.assertEqual(
            self.client.get(reverse('offer-detail', args=[offer.id])).status_code, status.HTTP_404_NOT_FOUND,
        )
        identity_services.set_account_active(self.seller.pk, True)
        dispatch_outbox_now()
        offer.refresh_from_db()
        self.assertTrue(offer.seller_is_public)
        self.assertIn(str(offer.id), self.public_ids())

    def test_set_account_active_is_idempotent_and_publishes_one_event_per_context(self):
        self.provider()
        before = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count()
        identity_services.set_account_active(self.seller.pk, False)
        identity_services.set_account_active(self.seller.pk, False)  # inchangé : aucun événement
        events = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed')
        self.assertEqual(events.count() - before, 2)  # contexte personnel + profil prestataire
        self.assertEqual({e.payload['context_type'] for e in events}, {'USER', 'PROVIDER'})
        self.assertEqual({e.payload['reason'] for e in events}, {'account_deactivated'})

    def test_sanction_hides_the_personal_and_provider_offers_but_not_those_of_an_organization(self):
        profile = self.provider()
        self.join(self.seller, role=OWNER)
        self.join(self.member, role=OWNER)  # un second propriétaire actif : l'organisation reste publique (T9-1, M3)
        personal = self.make_offer(title='Offre personnelle du vendeur')
        provider_offer = self.make_offer(
            seller_context_type='PROVIDER', seller_context_id=profile.pk, created_by=self.seller,
            title='Offre du prestataire',
        )
        org_offer = self.org_offer(creator=self.seller, title='Offre de l organisation du vendeur')
        sanction = Sanction.objects.create(user=self.seller, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='x')
        sanction.apply()
        dispatch_outbox_now()
        for offer, expected in ((personal, False), (provider_offer, False), (org_offer, True)):
            offer.refresh_from_db()
            self.assertEqual(offer.seller_is_public, expected, offer.title)
        sanction.lift()
        dispatch_outbox_now()
        personal.refresh_from_db()
        self.assertTrue(personal.seller_is_public)

    def test_archiving_an_organization_hides_its_offers(self):
        self.join(self.member, role=OWNER)
        offer = self.org_offer(creator=self.member)
        identity_services.archive_organization(self.member, self.org.pk)
        dispatch_outbox_now()
        offer.refresh_from_db()
        self.assertFalse(offer.seller_is_public)
        self.assertNotIn(str(offer.id), self.public_ids())

    def test_archiving_a_provider_hides_its_offers(self):
        profile = self.provider()
        offer = self.make_offer(
            seller_context_type='PROVIDER', seller_context_id=profile.pk, created_by=self.seller,
        )
        identity_services.archive_provider(self.seller)
        dispatch_outbox_now()
        offer.refresh_from_db()
        self.assertFalse(offer.seller_is_public)

    def test_the_event_handler_is_idempotent_and_rejects_a_bad_payload(self):
        from apps.platform_core.registry import PermanentEventError

        offer = self.org_offer(creator=self.member)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        payload = {'context_type': 'ORGANIZATION', 'context_id': str(self.org.pk)}
        self.assertEqual(services.apply_seller_status_event(payload), 1)
        self.assertEqual(services.apply_seller_status_event(payload), 0)  # rejeu : rien à faire
        offer.refresh_from_db()
        self.assertFalse(offer.seller_is_public)
        for bad in ({}, {'context_type': 'NOPE', 'context_id': str(self.org.pk)},
                    {'context_type': 'USER', 'context_id': 'x'}):
            with self.assertRaises(PermanentEventError):
                services.apply_seller_status_event(bad)

    def test_reconciliation_command_repairs_a_missed_event(self):
        profile = self.provider()
        self.join(self.member, role=OWNER)
        self.join(self.member, self.other_org, role=OWNER)
        suspended = self.org_offer(creator=self.member, title='Offre d une organisation suspendue')
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)  # sans événement
        user_offer = self.make_offer(title='Offre d un compte désactivé')
        User.objects.filter(pk=self.seller.pk).update(is_active=False)
        wrongly_hidden = self.org_offer(self.other_org, creator=self.member, seller_is_public=False, title='Cachée à tort')
        provider_offer = self.make_offer(
            seller_context_type='PROVIDER', seller_context_id=profile.pk, created_by=self.seller,
            title='Offre du prestataire désactivé',
        )

        call_command('sync_seller_visibility', verbosity=0)
        flags = {o.title: Offer.objects.get(pk=o.pk).seller_is_public
                 for o in (suspended, user_offer, wrongly_hidden, provider_offer)}
        self.assertEqual(flags, {
            'Offre d une organisation suspendue': False, 'Offre d un compte désactivé': False,
            'Cachée à tort': True, 'Offre du prestataire désactivé': False,
        })
        self.assertEqual(services.sync_all_seller_visibility(), 0)  # idempotent

    def test_a_sanctioned_but_still_active_account_is_not_public(self):
        offer = self.make_offer()
        Sanction.objects.create(user=self.seller, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='x')
        self.assertFalse(identity_services.is_seller_context_public('USER', self.seller.pk))
        call_command('sync_seller_visibility', verbosity=0)
        offer.refresh_from_db()
        self.assertFalse(offer.seller_is_public)

    def test_unknown_or_malformed_contexts_are_not_public(self):
        self.assertFalse(identity_services.is_seller_context_public('ORGANIZATION', uuid.uuid4()))
        self.assertFalse(identity_services.is_seller_context_public('PROVIDER', 'x'))
        self.assertFalse(identity_services.is_seller_context_public('NOPE', uuid.uuid4()))

    def test_an_offer_created_for_a_restricted_context_is_never_published_public(self):
        # La création refuse déjà un compte restreint ; le calcul d'origine reste la source de vérité.
        self.join(self.member, role=OWNER)
        self.assertTrue(identity_services.is_seller_context_public('ORGANIZATION', self.org.pk))
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertFalse(identity_services.is_seller_context_public('ORGANIZATION', self.org.pk))


def _kyb_file():
    return SimpleUploadedFile('piece.pdf', b'%PDF-1.4 test', content_type='application/pdf')


class SellerObjectTests(ContextBase):
    SELLER_KEYS = {
        'context_type', 'context_id', 'display_name', 'photo', 'org_type', 'verified_claims',
        'verification_summary', 'member_since',
    }

    def get_offer(self, offer):
        self.client.force_authenticate(None)
        return self.client.get(reverse('offer-detail', args=[offer.id])).data

    def test_exact_keys_for_every_type_of_seller(self):
        profile = self.provider()
        offers = {
            'USER': self.make_offer(),
            'PROVIDER': self.make_offer(seller_context_type='PROVIDER', seller_context_id=profile.pk,
                                        created_by=self.seller),
            'ORGANIZATION': self.org_offer(),
        }
        for context_type, offer in offers.items():
            with self.subTest(context_type=context_type):
                seller = self.get_offer(offer)['seller']
                self.assertEqual(set(seller), self.SELLER_KEYS)
                self.assertEqual(seller['context_type'], context_type)

    def test_offer_json_keys_are_exact_for_an_organization_offer(self):
        data = self.get_offer(self.org_offer())
        self.assertEqual(set(data), {
            'id', 'seller', 'seller_name', 'category', 'category_name', 'commune', 'commune_name', 'post_type',
            'title', 'description', 'price', 'currency', 'condition', 'stock', 'is_price_negotiable',
            'main_image', 'images', 'views_count', 'likes_count', 'shares_count', 'created_at', 'status', 'expires_at',
            'visibility_score', 'visibility_rank', 'offer_rating', 'seller_rating', 'is_favorited', 'favorites_count',
            'is_trending', 'is_sponsored', 'allowed_channels',
        })
        for hidden in ('created_by', 'seller_is_public', 'seller_context_type', 'seller_context_id'):
            self.assertNotIn(hidden, data)

    def test_no_phone_or_email_anywhere_in_offers_lists_and_search(self):
        self.member.phone = SENTINEL_PHONE
        self.member.email = SENTINEL_EMAIL
        self.member.save()
        self.seller.phone = '+243822222222'
        self.seller.save()
        point = ContactPoint.objects.create(user=self.seller, phone='+243822222222', is_verified=True)
        ContactConsent.objects.create(
            user=self.seller, channel='CALL', is_granted=True, text_version=CONTACT_CONSENT_TEXT_VERSION,
            granted_at=timezone.now(), phone_last4=point.phone[-4:],
        )
        profile = self.provider()
        self.join(self.member, role=OWNER)
        self.org_offer(creator=self.member, title='Offre publiée par le membre')
        self.make_offer(seller_context_type='PROVIDER', seller_context_id=profile.pk,
                        created_by=self.seller, title='Offre du prestataire Marie')
        self.make_offer(title='Offre personnelle du vendeur')
        self.client.force_authenticate(None)
        for params in ({}, {'search': 'Offre'}, {'seller': str(self.org.pk)}, {'ordering': 'price'}):
            blob = json.dumps(self.client.get(reverse('offer-list'), params).data, default=str)
            for secret in (SENTINEL_PHONE, SENTINEL_EMAIL, '+243822222222', 'seller@example.com', 'member@example.com'):
                self.assertNotIn(secret, blob, params)
        for offer in Offer.objects.all():
            blob = json.dumps(self.get_offer(offer), default=str)
            for secret in (SENTINEL_PHONE, SENTINEL_EMAIL, '+243822222222', 'seller@example.com'):
                self.assertNotIn(secret, blob)

    def test_organization_offer_never_exposes_a_member_number_as_a_channel(self):
        self.member.phone = SENTINEL_PHONE
        self.member.phone_verified = True
        self.member.save()
        point = ContactPoint.objects.create(user=self.member, phone=SENTINEL_PHONE, is_verified=True)
        for channel in ('CALL', 'WHATSAPP', 'MESSAGE'):
            ContactConsent.objects.create(
                user=self.member, channel=channel, is_granted=True, text_version=CONTACT_CONSENT_TEXT_VERSION,
                granted_at=timezone.now(), phone_last4=point.phone[-4:],
            )
        self.join(self.member, role=OWNER)
        offer = self.org_offer(creator=self.member)
        # T7 : une organisation offre MESSAGE (routé vers l'équipe), jamais le numéro d'un membre.
        self.assertEqual(self.get_offer(offer)['allowed_channels'], ['MESSAGE'])
        self.client.force_authenticate(self.buyer)
        for channel in ('CALL', 'WHATSAPP'):
            response = self.client.post(reverse('contact-reveal'), {'offer': str(offer.id), 'channel': channel})
            self.assertEqual((response.status_code, response.data['code']), (403, 'channel_not_allowed'))
            self.assertNotIn(SENTINEL_PHONE, json.dumps(response.data, default=str))
            self.assertEqual(response.data['detail'], "Ce vendeur n'accepte pas ce moyen de contact.")
        self.assertEqual(ContactEvent.objects.count(), 0)
        contact = self.client.post(reverse('contact-list'), {'post': str(offer.id), 'message': 'Bonjour'})
        self.assertEqual(contact.status_code, status.HTTP_201_CREATED, contact.data)
        self.assertEqual(ContactEvent.objects.count(), 1)

    def test_a_member_cannot_contact_or_review_the_offer_of_his_own_organization(self):
        self.join(self.member, role=EDITOR)
        offer = self.org_offer(creator=self.buyer)
        self.client.force_authenticate(self.member)
        response = self.client.post(reverse('contact-reveal'), {'offer': str(offer.id), 'channel': 'CALL'})
        self.assertEqual((response.status_code, response.data['code']), (403, 'own_offer'))
        with self.assertRaises(services.MarketplaceError):
            services.create_exchange_proposal(offer=offer, sender=self.member, message='x') \
                if services.is_exchange_enabled() else services._check_can_contact(offer, self.member)

    def test_provider_contact_goes_through_the_account_of_its_owner(self):
        profile = self.provider()
        offer = self.make_offer(seller_context_type='PROVIDER', seller_context_id=profile.pk,
                                created_by=self.seller)
        self.assertEqual(self.get_offer(offer)['allowed_channels'], ['MESSAGE'])
        self.client.force_authenticate(self.buyer)
        response = self.client.post(reverse('contact-list'), {'post': str(offer.id), 'message': 'Bonjour'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        dispatch_outbox_now()
        from apps.notifications.models import Notification

        self.assertTrue(Notification.objects.filter(user=self.seller).exists())

    def test_verified_claims_come_from_validated_pieces_only(self):
        owner = self.member
        self.join(owner, role=OWNER)
        offer = self.org_offer(creator=owner)
        KycDocument.objects.create(
            organization=self.org, uploaded_by=owner, document_type='RCCM', file=_kyb_file(),
            status=KycDocument.STATUS_VALIDE, reviewed_at=timezone.now(),
        )
        KycDocument.objects.create(
            organization=self.org, uploaded_by=owner, document_type='ID_NATIONALE', file=_kyb_file(),
            status=KycDocument.STATUS_EN_ATTENTE,
        )
        seller = self.get_offer(offer)['seller']
        self.assertEqual([claim['code'] for claim in seller['verified_claims']], ['RCCM_VERIFIED'])
        self.assertEqual(seller['verification_summary'], {'complete': False, 'label': None})

    def test_a_paid_status_or_a_role_changes_nothing_about_verification(self):
        # Règle 3 : seul l'état des pièces compte ; aucun paramètre de plan n'existe dans l'objet vendeur.
        seller = self.get_offer(self.org_offer())['seller']
        self.assertEqual((seller['verified_claims'], seller['verification_summary']['complete']), ([], False))

    def test_a_page_of_offers_has_a_constant_number_of_queries(self):
        profile = self.provider()

        def build(count):
            for index in range(count):
                self.org_offer(title=f'Offre d organisation numéro {index}')
                self.make_offer(seller_context_type='PROVIDER', seller_context_id=profile.pk,
                                created_by=self.seller, title=f'Offre de prestataire numéro {index}')
                self.make_offer(title=f'Offre personnelle numéro {index}')

        def count_queries():
            self.client.force_authenticate(self.member)
            with self.assertNumQueries(0) if False else CaptureQueries() as captured:
                response = self.client.get(reverse('offer-list'))
            self.assertEqual(response.status_code, 200)
            return len(captured)

        from django.db import connection as conn
        from django.test.utils import CaptureQueriesContext as CaptureQueries

        class _Capture(CaptureQueries):
            def __init__(self):
                super().__init__(conn)

        CaptureQueries = _Capture  # noqa: F811
        self.join(self.member, role=OWNER)
        build(1)
        count_queries()  # échauffement : réglages mis en cache en base à la première lecture
        small = count_queries()
        build(6)
        large = count_queries()
        self.assertEqual(small, large)


make_image = make_test_image


class NoExistenceOracleTests(ContextBase):
    """Un étranger au contexte reçoit 404 quand l'offre n'est pas publique, 403 DENY_RELATION sinon ;
    un membre au rôle insuffisant reçoit toujours DENY_PERMISSION."""

    def test_stranger_gets_404_on_every_non_public_state_and_403_on_a_public_offer(self):
        states = {
            'pause': {'status': 'PAUSED', 'is_active': False},
            'masquée': {'is_hidden_by_moderation': True, 'is_active': False},
            'corbeille': {'is_deleted': True}, 'vendeur non public': {'seller_is_public': False},
        }
        self.client.force_authenticate(self.buyer)
        for label, fields in states.items():
            offer = self.make_offer(title=f'Offre dans l état {label}')
            Offer.objects.filter(pk=offer.pk).update(**fields)
            with self.subTest(state=label):
                for response in (
                    self.client.patch(reverse('offer-detail', args=[offer.id]), {'price': 1}),
                    self.client.post(reverse('offer-pause', args=[offer.id])),
                    self.client.get(reverse('offer_stats', args=[offer.id])),
                    self.client.post(reverse('offer-images', args=[offer.id]), {}, format='multipart'),
                ):
                    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        public = self.make_offer(title='Offre publique du vendeur')
        for response in (
            self.client.patch(reverse('offer-detail', args=[public.id]), {'price': 1}),
            self.client.get(reverse('offer_stats', args=[public.id])),
        ):
            self.assertEqual((response.status_code, response.data['code']), (403, 'DENY_RELATION'))

    def test_insufficient_role_stays_403_even_on_a_non_public_offer(self):
        analyst = User.objects.create_user(email='an@example.com', password='x', full_name='An')
        self.join(analyst, role=ANALYST)
        offer = self.org_offer(creator=self.buyer, is_deleted=True)
        self.client.force_authenticate(analyst)
        response = self.client.post(reverse('offer-restore', args=[offer.id]))
        self.assertEqual((response.status_code, response.data['code']), (403, 'DENY_PERMISSION'))


class AuditTrailTests(ContextBase):
    def test_every_write_is_audited_with_its_context_and_no_personal_value(self):
        self.join(self.member, role=EDITOR)
        self.client.force_authenticate(self.member)
        offer = self.org_offer(creator=self.member, title='Titre sentinelle confidentiel')
        url = reverse('offer-detail', args=[offer.id])
        self.client.patch(url, {'price': 4242, 'title': 'Nouveau titre sentinelle'})
        for name in ('pause', 'unpause', 'renew', 'mark-sold', 'soft-delete', 'restore'):
            self.assertEqual(self.client.post(reverse(f'offer-{name}', args=[offer.id])).status_code, 200, name)
        images = self.client.post(
            reverse('offer-images', args=[offer.id]), {'image': make_image()}, format='multipart',
        )
        self.assertEqual(images.status_code, 201, images.data)
        removed = self.client.delete(f"{reverse('offer-images', args=[offer.id])}?image_id={images.data[0]['id']}")
        self.assertEqual(removed.status_code, 204)
        actions = set(AuditLog.objects.filter(action__startswith='OFFER_').values_list('action', flat=True))
        self.assertEqual(actions, {
            'OFFER_UPDATED', 'OFFER_PAUSED', 'OFFER_RESUMED', 'OFFER_RENEWED', 'OFFER_SOLD', 'OFFER_TRASHED',
            'OFFER_RESTORED', 'OFFER_IMAGES_ADDED', 'OFFER_IMAGE_DELETED',
        })
        for entry in AuditLog.objects.filter(action__startswith='OFFER_'):
            self.assertEqual((entry.context_type, entry.context_id, entry.actor), ('ORGANIZATION', self.org.pk, self.member))
            self.assertNotIn('sentinelle', entry.details)
            self.assertNotIn('4242', entry.details)
        self.assertEqual(AuditLog.objects.get(action='OFFER_UPDATED').details, 'fields=price,title')

    def test_images_are_reauthorized_in_the_service(self):
        from apps.common.contexts import ContextDenied

        offer = self.org_offer(creator=self.member)
        membership = self.join(self.member, role=EDITOR)
        membership.status = Membership.STATUS_REVOKED
        membership.save()
        with self.assertRaises(ContextDenied):
            services.add_offer_images(offer, actor=self.member, files=[make_image()])
        self.assertEqual(offer.images.count(), 0)

    def test_gallery_limits_and_errors_come_from_the_service(self):
        offer = self.make_offer()
        with self.assertRaises(services.MarketplaceError):
            services.add_offer_images(offer, actor=self.seller, files=[])
        with self.assertRaises(services.MarketplaceError):
            services.add_offer_images(offer, actor=self.seller, files=[make_image() for _ in range(8)])
        self.assertFalse(services.delete_offer_image(offer, actor=self.seller, image_id=uuid.uuid4()))

    def test_admin_deletion_is_audited_with_context(self):
        from django.contrib.admin.sites import site

        admin = site._registry[Offer]
        offer = self.org_offer(creator=self.member)

        class _Req:
            user = self.buyer

        admin.delete_model(_Req(), offer)
        entry = AuditLog.objects.get(action='OFFER_DELETED')
        self.assertEqual((entry.context_type, entry.context_id), ('ORGANIZATION', self.org.pk))

    def test_an_offer_carries_only_its_owner_context_and_its_author(self):
        # Contraction (T9-2) : plus de rattachement direct au compte (`seller`), seul le contexte propriétaire fait foi.
        response = self.create(self.seller)
        offer = Offer.objects.get(pk=response.data['id'])
        self.assertEqual((offer.seller_context_type, offer.seller_context_id, offer.created_by_id),
                         ('USER', self.seller.pk, self.seller.pk))
        self.assertFalse(hasattr(offer, 'seller'))
        profile = self.provider()
        response = self.create(self.seller, ctx_header('PROVIDER', profile.pk), title='Offre du prestataire')
        offer = Offer.objects.get(pk=response.data['id'])
        self.assertEqual((offer.seller_context_type, offer.seller_context_id, offer.created_by_id),
                         ('PROVIDER', profile.pk, self.seller.pk))


class SynchronousVisibilityTests(ContextBase):
    """Aucune fenêtre d'incohérence : la visibilité suit dans la même requête, sans diffusion de l'outbox
    (OUTBOX_INLINE_DISPATCH désactivé dans les tests, aucun `dispatch_outbox_now` ici)."""

    def test_account_deactivation_is_immediate(self):
        offer = self.make_offer()
        identity_services.set_account_active(self.seller.pk, False)
        offer.refresh_from_db()
        self.assertFalse(offer.seller_is_public)
        identity_services.set_account_active(self.seller.pk, True)
        offer.refresh_from_db()
        self.assertTrue(offer.seller_is_public)

    def test_organization_archive_and_provider_archive_are_immediate(self):
        self.join(self.member, role=OWNER)
        org_offer = self.org_offer(creator=self.member)
        identity_services.archive_organization(self.member, self.org.pk)
        org_offer.refresh_from_db()
        self.assertFalse(org_offer.seller_is_public)
        profile = self.provider()
        provider_offer = self.make_offer(
            seller_context_type='PROVIDER', seller_context_id=profile.pk, created_by=self.seller,
        )
        identity_services.archive_provider(self.seller)
        provider_offer.refresh_from_db()
        self.assertFalse(provider_offer.seller_is_public)

    def test_sanction_is_immediate(self):
        offer = self.make_offer()
        sanction = Sanction.objects.create(user=self.seller, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='x')
        sanction.apply()
        offer.refresh_from_db()
        self.assertFalse(offer.seller_is_public)

    def test_direct_is_active_change_in_the_admin_goes_through_the_single_point(self):
        from django.contrib.admin.sites import site

        offer = self.make_offer()
        admin = site._registry[User]

        class _Form:
            changed_data = ['is_active']

        class _Req:
            user = self.buyer

        self.seller.is_active = False
        admin.save_model(_Req(), self.seller, _Form(), True)
        offer.refresh_from_db()
        self.assertFalse(offer.seller_is_public)


class RequestContextsMemoTests(ContextBase):
    def test_retrieve_reads_the_user_contexts_once(self):
        from django.db import connection as conn
        from django.test.utils import CaptureQueriesContext

        self.join(self.member, role=OWNER)
        offer = self.org_offer(creator=self.member)
        self.client.force_authenticate(self.member)
        self.client.get(reverse('offer-detail', args=[offer.id]))  # échauffement
        with CaptureQueriesContext(conn) as captured:
            response = self.client.get(reverse('offer-detail', args=[offer.id]))
        self.assertEqual(response.status_code, 200)
        role_queries = [q for q in captured if 'identity_membership' in q['sql'] or 'identity_providerprofile' in q['sql']]
        self.assertLessEqual(len(role_queries), 3)


class ExpirationRecipientsTests(ContextBase):
    """Expiration v2 : un événement par offre ; les destinataires (`offer.edit`) sont résolus à la livraison."""

    def soon(self, offer):
        Offer.objects.filter(pk=offer.pk).update(expires_at=timezone.now() + timezone.timedelta(hours=2))

    def test_organization_without_active_editor_notifies_nobody(self):
        offer = self.org_offer(creator=self.member)
        analyst = User.objects.create_user(email='an@example.com', password='x', full_name='An')
        self.join(analyst, role=ANALYST)  # l'analyste n'a pas `offer.edit`
        self.soon(offer)
        services.expire_offers()
        events = OutboxEvent.objects.filter(event_type='marketplace.offer_expiring_soon')
        self.assertEqual(events.count(), 1)
        dispatch_outbox_now()
        self.assertEqual(Notification.objects.count(), 0)  # aucun destinataire éligible : rien n'est envoyé
        self.assertEqual(events.get().status, 'done')  # et l'événement est traité sans erreur, sans rejeu

    def test_organization_with_two_editors_notifies_each(self):
        offer = self.org_offer(creator=self.member)
        editors = []
        for label, role in (('o', OWNER), ('e', EDITOR), ('a', ANALYST)):
            user = User.objects.create_user(email=f'{label}@example.com', password='x', full_name=label)
            self.join(user, role=role)
            editors.append(user)
        self.soon(offer)
        services.expire_offers()
        self.assertEqual(OutboxEvent.objects.filter(event_type='marketplace.offer_expiring_soon').count(), 1)
        dispatch_outbox_now()
        notified = Notification.objects.all()
        self.assertEqual({n.user_id for n in notified}, {editors[0].pk, editors[1].pk})  # pas l'analyste
        self.assertEqual({(n.context_type, n.context_id) for n in notified}, {('ORGANIZATION', self.org.pk)})
        self.assertTrue(all(n.notification_type == 'EXPIRATION' for n in notified))
        self.assertNotIn('@', ''.join(n.content + n.title for n in notified))


class AuditAndAdminTests(ContextBase):
    def test_admin_does_not_let_the_owner_be_edited(self):
        from django.contrib.admin.sites import site

        from .models import Offer as OfferModel

        admin = site._registry[OfferModel]
        for field in ('seller_context_type', 'seller_context_id', 'created_by', 'seller_is_public'):
            self.assertIn(field, admin.readonly_fields)


class OfferContextMigrationTests(TransactionTestCase):
    """Migrations 0008 (schéma) puis 0009 (remplissage) de `marketplace`, 0004 puis 0005 de `visibility`."""

    def targets(self, executor, marketplace, visibility):
        leaf = lambda app: executor.loader.graph.leaf_nodes(app)[0]  # noqa: E731
        return [(marketplace[0], marketplace[1]), (visibility[0], visibility[1]),
                ('identity', '0012_kycdocument_organization_required'), leaf('catalog')]

    def tearDown(self):
        call_command('migrate', verbosity=0)

    def test_backfill_is_correct_idempotent_and_reversible(self):
        before = MigrationExecutor(connection)
        old = self.targets(before, ('marketplace', '0007_exchange_enabled_setting'), ('visibility', '0003_bornes_reglages'))
        before.migrate(old)
        old_apps = before.loader.project_state(old).apps
        HUser = old_apps.get_model('identity', 'User')
        HOffer = old_apps.get_model('marketplace', 'Offer')
        HCounter = old_apps.get_model('visibility', 'DailyVisibilityCounter')
        City, Commune, Category = (old_apps.get_model('catalog', name) for name in ('City', 'Commune', 'Category'))
        city = City.objects.create(name='Kinshasa', name_key='kinshasa', slug='kinshasa')
        commune = Commune.objects.create(city=city, name='Gombe', name_key='gombe')
        category = Category.objects.create(name='Électronique', name_key='electronique', slug='electronique')
        active = HUser.objects.create(email='a@example.com')
        banned = HUser.objects.create(email='b@example.com', is_active=False)

        def offer(owner, title):
            return HOffer.objects.create(
                seller=owner, category_id=category.id, commune_id=commune.id, title=title,
                description='Description suffisamment longue pour passer.', price=1, expires_at=timezone.now(),
            )

        offers = {name: offer(owner, name) for name, owner in (('active-1', active), ('active-2', active), ('banned', banned))}
        for entry in offers.values():
            HCounter.objects.create(offer_id=entry.id, seller=entry.seller, date=timezone.localdate(), views=2)

        after = MigrationExecutor(connection)
        new = self.targets(after, ('marketplace', '0009_fill_offer_seller_context'), ('visibility', '0005_fill_counter_seller_context'))
        after.migrate(new)
        new_apps = after.loader.project_state(new).apps
        NOffer = new_apps.get_model('marketplace', 'Offer')
        NCounter = new_apps.get_model('visibility', 'DailyVisibilityCounter')

        def snapshot():
            return {
                o.title: (o.seller_context_type, o.seller_context_id, o.created_by_id, o.seller_is_public)
                for o in NOffer.objects.all()
            }

        expected = {
            'active-1': ('USER', active.pk, active.pk, True), 'active-2': ('USER', active.pk, active.pk, True),
            'banned': ('USER', banned.pk, banned.pk, False),
        }
        self.assertEqual(snapshot(), expected)
        for counter in NCounter.objects.all():
            self.assertEqual((counter.seller_context_type, counter.seller_context_id), ('USER', counter.seller_id))
        self.assertEqual(NCounter.objects.count(), 3)

        # Idempotence : rejouer les deux remplissages ne change rien, et ne réécrase pas un contexte déjà posé.
        marker = uuid.uuid4()
        NOffer.objects.filter(title='active-1').update(seller_context_type='ORGANIZATION', seller_context_id=marker)
        for module, app_label in (
            ('apps.marketplace.migrations.0009_fill_offer_seller_context', None),
            ('apps.visibility.migrations.0005_fill_counter_seller_context', None),
        ):
            importlib.import_module(module).fill_contexts(new_apps, None)
        replayed = snapshot()
        self.assertEqual(replayed['active-1'][:2], ('ORGANIZATION', marker))
        self.assertEqual({k: v for k, v in replayed.items() if k != 'active-1'},
                         {k: v for k, v in expected.items() if k != 'active-1'})

        # Retour arrière : colonnes retirées, offres et compteurs conservés.
        back = MigrationExecutor(connection)
        back.migrate(old)
        back_apps = back.loader.project_state(old).apps
        self.assertEqual(back_apps.get_model('marketplace', 'Offer').objects.count(), 3)
        self.assertNotIn('seller_context_id', {f.name for f in back_apps.get_model('marketplace', 'Offer')._meta.get_fields()})
        self.assertEqual(back_apps.get_model('visibility', 'DailyVisibilityCounter').objects.count(), 3)
