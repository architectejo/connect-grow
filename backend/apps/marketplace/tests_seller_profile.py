"""Profil public d'un vendeur par contexte (ADR 0006, 9.7), statistiques par contexte, colonnes de contexte de la
messagerie et des notifications (T5b / L0-09e)."""
import importlib
import json
import re
import uuid
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.identity.models import KycDocument, Organization, ProviderProfile, User
from apps.moderation.models import Sanction
from apps.platform_core.testing import dispatch_outbox_now
from apps.reviews.models import Review
from apps.visibility.models import DailyVisibilityCounter

from .models import Offer
from .tests_contexts import ANALYST, EDITOR, OWNER, ContextBase, _kyb_file, ctx_header

PROFILE_KEYS = {
    'context_type', 'context_id', 'display_name', 'photo', 'description', 'org_type', 'verified_claims',
    'verification_summary', 'member_since', 'seller_rating', 'active_offers_count',
}
SENTINEL_NAME_PART = 'Zorglub'
SENTINEL_PHONE = '+243899887766'
SENTINEL_EMAIL = 'sentinelle-privee@example.com'
SENTINEL_NIF = 'NIF-SENTINELLE-777'


def profile_url(kind, context_id):
    return reverse('seller_profile', args=[kind, context_id])


class ProfileBase(ContextBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient()
        User.objects.filter(pk=self.seller.pk).update(
            full_name=f'Marie {SENTINEL_NAME_PART} Kabongo', phone=SENTINEL_PHONE, email=SENTINEL_EMAIL,
        )
        self.seller.refresh_from_db()
        self.profile = self.provider()
        ProviderProfile.objects.filter(pk=self.profile.pk).update(display_name='Marie couture')
        Organization.objects.filter(pk=self.org.pk).update(
            nif=SENTINEL_NIF, description='Atelier de menuiserie à Kinshasa.',
        )
        self.join(self.member, role=OWNER)

    def provider_offer(self, **kwargs):
        return self.make_offer(
            seller=None, seller_context_type='PROVIDER', seller_context_id=self.profile.pk,
            created_by=self.seller, **kwargs,
        )

    def review(self, context_type, context_id, rating=5):
        author = User.objects.create_user(
            email=f'a{uuid.uuid4().hex[:8]}@example.com', password='x', full_name='Auteur Test',
        )
        return Review.objects.create(
            offer_id=uuid.uuid4(), user=author, seller_context_type=context_type, seller_context_id=context_id,
            contact_event_id=uuid.uuid4(), contact_channel='MESSAGE', contact_recorded_at=timezone.now(),
            offer_rating=rating, seller_rating=rating, content='Avis suffisamment long pour être valide.',
        )

    def get(self, kind, context_id, **extra):
        return self.client.get(profile_url(kind, context_id), **extra)


class PublicProfileTests(ProfileBase):
    def test_personal_profile_is_minimal(self):
        self.make_offer()
        response = self.get('user', self.seller.pk)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), PROFILE_KEYS)
        self.assertEqual(data['context_type'], 'USER')
        self.assertEqual(data['context_id'], str(self.seller.pk))
        self.assertEqual(data['display_name'], f'Marie K.')
        self.assertIsNone(data['description'])
        self.assertIsNone(data['org_type'])
        self.assertEqual((data['verified_claims'], data['verification_summary']), ([], {'complete': False, 'label': None}))
        self.assertEqual(data['active_offers_count'], 1)
        self.assertEqual(data['seller_rating'], {'average': None, 'count': 0})
        self.assertTrue(data['member_since'])

    def test_provider_profile(self):
        self.provider_offer()
        data = self.get('provider', self.profile.pk).json()
        self.assertEqual(set(data), PROFILE_KEYS)
        self.assertEqual(
            (data['context_type'], data['display_name'], data['description'], data['org_type']),
            ('PROVIDER', 'Marie couture', 'Couture sur mesure', None),
        )
        self.assertEqual(data['active_offers_count'], 1)

    def test_organization_profile_with_precise_claims(self):
        self.org_offer(creator=self.member)
        KycDocument.objects.create(
            organization=self.org, uploaded_by=self.member, document_type='RCCM', file=_kyb_file(),
            status=KycDocument.STATUS_VALIDE, reviewed_at=timezone.now(),
        )
        KycDocument.objects.create(
            organization=self.org, uploaded_by=self.member, document_type='ID_NATIONALE', file=_kyb_file(),
            status=KycDocument.STATUS_EN_ATTENTE,
        )
        data = self.get('organization', self.org.pk).json()
        self.assertEqual(set(data), PROFILE_KEYS)
        self.assertEqual(
            (data['context_type'], data['display_name'], data['org_type'], data['description']),
            ('ORGANIZATION', 'Atelier X', 'ENTREPRISE', 'Atelier de menuiserie à Kinshasa.'),
        )
        # Règle 3 : seule la pièce validée donne un claim, et jamais un « vérifié » global.
        self.assertEqual([claim['code'] for claim in data['verified_claims']], ['RCCM_VERIFIED'])
        self.assertEqual(data['verification_summary'], {'complete': False, 'label': None})
        self.assertEqual(data['active_offers_count'], 1)

    def test_complete_verification_shows_the_summary_with_its_claims(self):
        for document_type in ('RCCM', 'ID_NATIONALE', 'PIECE_GERANT'):
            KycDocument.objects.create(
                organization=self.org, uploaded_by=self.member, document_type=document_type, file=_kyb_file(),
                status=KycDocument.STATUS_VALIDE, reviewed_at=timezone.now(),
            )
        data = self.get('organization', self.org.pk).json()
        self.assertTrue(data['verification_summary']['complete'])
        self.assertEqual(len(data['verified_claims']), 3)

    def test_counts_only_public_active_offers_of_the_context(self):
        self.org_offer(creator=self.member)
        self.org_offer(creator=self.member, is_active=False)
        self.org_offer(creator=self.member, is_deleted=True)
        self.org_offer(self.other_org, creator=self.member)
        self.make_offer(seller=self.member)
        self.assertEqual(self.get('organization', self.org.pk).json()['active_offers_count'], 1)

    def test_ratings_are_per_context_and_never_universal(self):
        # Même personne : une note comme particulier, une autre comme prestataire, une autre pour son organisation.
        for _ in range(3):
            self.review('USER', self.seller.pk, rating=5)
            self.review('PROVIDER', self.profile.pk, rating=2)
        self.review('ORGANIZATION', self.org.pk, rating=4)
        user = self.get('user', self.seller.pk).json()['seller_rating']
        provider = self.get('provider', self.profile.pk).json()['seller_rating']
        org = self.get('organization', self.org.pk).json()['seller_rating']
        self.assertEqual((user['average'], user['count']), (5.0, 3))
        self.assertEqual((provider['average'], provider['count']), (2.0, 3))
        # Sous le seuil d'affichage : la moyenne reste masquée, le nombre est exact.
        self.assertEqual((org['average'], org['count']), (None, 1))
        for kind, key in (('user', self.seller.pk), ('provider', self.profile.pk), ('organization', self.org.pk)):
            self.assertNotIn('trust_score', self.get(kind, key).json())

    def test_hidden_reviews_are_not_counted(self):
        for _ in range(3):
            self.review('USER', self.seller.pk, rating=5)
        Review.objects.filter(seller_context_type='USER').update(is_hidden=True)
        self.assertEqual(self.get('user', self.seller.pk).json()['seller_rating'], {'average': None, 'count': 0})

    def test_reading_a_profile_never_touches_the_organic_ranking(self):
        offer = self.make_offer()
        before = offer.visibility_score
        for _ in range(5):
            self.review('USER', self.seller.pk, rating=5)
        self.get('user', self.seller.pk)
        offer.refresh_from_db()
        self.assertEqual(offer.visibility_score, before)


class UniformNotFoundTests(ProfileBase):
    def test_every_unavailable_context_gives_the_same_404(self):
        archived = Organization.objects.create(name='Vieille orga', org_type='ONG', status=Organization.STATUS_ARCHIVED)
        suspended = Organization.objects.create(
            name='Orga suspendue', org_type='ONG', status=Organization.STATUS_SUSPENDED,
        )
        other = User.objects.create_user(email='prov@example.com', password='x', full_name='Autre Prestataire')
        archived_provider = ProviderProfile.objects.create(
            user=other, display_name='Ancien profil', status=ProviderProfile.STATUS_ARCHIVED,
        )
        inactive = User.objects.create_user(email='off@example.com', password='x', full_name='Compte Inactif')
        User.objects.filter(pk=inactive.pk).update(is_active=False)
        banned = User.objects.create_user(email='banned@example.com', password='x', full_name='Compte Banni')
        Sanction.objects.create(user=banned, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='x')
        candidates = [
            ('organization', uuid.uuid4()), ('provider', uuid.uuid4()), ('user', uuid.uuid4()),
            ('organization', archived.pk), ('organization', suspended.pk), ('provider', archived_provider.pk),
            ('user', inactive.pk), ('user', banned.pk),
            ('organization', 'pas-un-uuid'), ('user', '00000'),
            # Mauvais type pour un identifiant existant : pas d'oracle non plus.
            ('provider', self.org.pk), ('organization', self.seller.pk), ('user', self.org.pk),
            ('USER', self.seller.pk), ('team', self.seller.pk),
        ]
        bodies = set()
        for kind, context_id in candidates:
            with self.subTest(kind=kind, context_id=context_id):
                response = self.client.get(f'/api/marketplace/sellers/{kind}/{context_id}/')
                self.assertEqual(response.status_code, 404)
                bodies.add(response.content)
        self.assertEqual(len(bodies), 1)

    def test_the_404_does_not_depend_on_what_exists(self):
        absent = self.client.get(profile_url('organization', uuid.uuid4())).content
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertEqual(self.get('organization', self.org.pk).content, absent)

    def test_the_profile_comes_back_when_the_seller_is_public_again(self):
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertEqual(self.get('organization', self.org.pk).status_code, 404)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ACTIVE)
        self.assertEqual(self.get('organization', self.org.pk).status_code, 200)

    def test_only_get_is_allowed(self):
        self.client.force_authenticate(self.seller)
        for method in ('post', 'put', 'patch', 'delete'):
            response = getattr(self.client, method)(profile_url('user', self.seller.pk), {})
            self.assertEqual(response.status_code, 405, method)


class NoLeakTests(ProfileBase):
    def test_no_private_data_in_any_profile(self):
        # Valeurs sentinelles : nom complet, téléphone, e-mail, NIF, nom et numéro d'un membre.
        User.objects.filter(pk=self.member.pk).update(full_name='Membre Secretissime', phone='+243855500011')
        self.provider_offer()
        self.org_offer(creator=self.member)
        for kind, key in (('user', self.seller.pk), ('provider', self.profile.pk), ('organization', self.org.pk)):
            with self.subTest(kind=kind):
                text = json.dumps(self.get(kind, key).json(), ensure_ascii=False)
                for secret in (
                    SENTINEL_NAME_PART, 'Kabongo', SENTINEL_PHONE, SENTINEL_EMAIL, SENTINEL_NIF, 'Secretissime',
                    '+243855500011', 'member@example.com',
                ):
                    self.assertNotIn(secret, text, secret)
                self.assertIsNone(re.search(r'\+?\d{9,}', text), text)
                self.assertNotIn('@', text)
                for forbidden in (
                    'nif', 'members', 'phone', 'email', 'address', 'user_type', 'business_profile', 'is_verified',
                ):
                    self.assertNotIn(f'"{forbidden}"', text)

    def test_the_header_context_and_the_token_change_nothing(self):
        anonymous = self.get('organization', self.org.pk).json()
        self.client.force_authenticate(self.member)
        with_header = self.get('organization', self.org.pk, **ctx_header('ORGANIZATION', self.org.pk)).json()
        other_context = self.get('organization', self.org.pk, **ctx_header('ORGANIZATION', self.other_org.pk))
        self.assertEqual(anonymous, with_header)
        self.assertEqual(other_context.status_code, 200)  # l'en-tête est ignoré, pas validé

    def test_offer_list_exposes_no_user_type_nor_business_profile(self):
        self.org_offer(creator=self.member)
        self.make_offer()
        text = json.dumps(self.client.get(reverse('offer-list')).json())
        for forbidden in ('user_type', 'business_profile', 'full_name', 'date_joined'):
            self.assertNotIn(forbidden, text)


LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'seller-profile'}}


@override_settings(CACHES=LOCMEM_CACHE)
class CachingAndThrottleTests(ProfileBase):
    def test_short_public_cache_without_context_header(self):
        response = self.get('organization', self.org.pk)
        self.assertEqual(response['Cache-Control'], 'public, max-age=60')
        self.assertIn('X-Context', response['Vary'])

    def test_no_public_cache_with_a_context_header_or_a_token(self):
        with_header = self.get('organization', self.org.pk, **ctx_header('ORGANIZATION', self.org.pk))
        self.assertIn('no-store', with_header['Cache-Control'])
        self.assertNotIn('public', with_header['Cache-Control'])
        with_token = self.get('organization', self.org.pk, HTTP_AUTHORIZATION='Bearer inutile')
        self.assertNotIn('public', with_token['Cache-Control'])

    def test_a_404_is_never_publicly_cached(self):
        response = self.get('organization', uuid.uuid4())
        self.assertNotIn('public', response.get('Cache-Control', ''))

    def test_rate_limit_by_ip_applies_to_connected_users_too(self):
        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['seller_profile'], '600/hour')
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'seller_profile': '2/hour'}):
            cache.clear()
            codes = [self.get('user', self.seller.pk, REMOTE_ADDR='10.7.7.7').status_code for _ in range(3)]
            self.client.force_authenticate(self.member)
            codes.append(self.get('user', self.seller.pk, REMOTE_ADDR='10.7.7.7').status_code)
            other = self.get('user', self.seller.pk, REMOTE_ADDR='10.7.7.8').status_code
            cache.clear()
        self.assertEqual((codes, other), ([200, 200, 429, 429], 200))


class ConstantQueriesTests(ProfileBase):
    def count(self, kind, key):
        with CaptureQueriesContext(connection) as captured:
            response = self.get(kind, key)
        self.assertEqual(response.status_code, 200)
        return len(captured)

    def grow(self, size):
        for _ in range(size):
            self.org_offer(creator=self.member)
            self.make_offer()
            self.provider_offer()
            self.review('USER', self.seller.pk)
            self.review('PROVIDER', self.profile.pk)
            self.review('ORGANIZATION', self.org.pk)

    def test_the_number_of_queries_does_not_depend_on_data_volume(self):
        targets = (('user', self.seller.pk), ('provider', self.profile.pk), ('organization', self.org.pk))
        for kind, key in targets:
            self.count(kind, key)  # échauffement (réglages)
        small = {kind: self.count(kind, key) for kind, key in targets}
        self.grow(8)
        cache.clear()
        large = {kind: self.count(kind, key) for kind, key in targets}
        self.assertEqual(small, large)
        self.assertTrue(all(value <= 12 for value in large.values()), large)


class SellerOffersListTests(ProfileBase):
    def rows(self, **params):
        data = self.client.get(reverse('offer-list'), params).json()
        return data['results'] if isinstance(data, dict) else data

    def test_public_offers_of_a_seller_use_the_existing_filter(self):
        mine = self.org_offer(creator=self.member, title='Offre publique de l organisation')
        self.org_offer(creator=self.member, title='Offre en pause', is_active=False)
        self.org_offer(self.other_org, creator=self.member, title='Offre d une autre organisation')
        self.make_offer(title='Offre personnelle du vendeur')
        rows = self.rows(seller=str(self.org.pk), seller_type='ORGANIZATION')
        self.assertEqual([row['id'] for row in rows], [str(mine.pk)])

    def test_a_context_identifier_does_not_match_another_type(self):
        self.org_offer(creator=self.member)
        self.assertEqual(self.rows(seller=str(self.org.pk), seller_type='USER'), [])

    def test_offers_of_a_non_public_seller_are_not_listed(self):
        self.org_offer(creator=self.member)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        Offer.objects.filter(seller_context_id=self.org.pk).update(seller_is_public=False)
        dispatch_outbox_now()
        self.assertEqual(self.rows(seller=str(self.org.pk), seller_type='ORGANIZATION'), [])


class DashboardByContextTests(ProfileBase):
    def setUp(self):
        super().setUp()
        for _ in range(2):
            self.review('USER', self.member.pk, rating=3)
        for rating in (5, 4, 4):
            self.review('ORGANIZATION', self.org.pk, rating=rating)
        self.org_offer(creator=self.member)
        self.make_offer(seller=self.member)

    def dashboard(self, user, headers=None):
        self.client.force_authenticate(user)
        return self.client.get(reverse('dashboard_stats'), **(headers or {}))

    def test_rating_and_counters_follow_the_active_context(self):
        personal = self.dashboard(self.member).json()['summary']
        in_org = self.dashboard(self.member, ctx_header('ORGANIZATION', self.org.pk)).json()['summary']
        self.assertEqual((personal['avg_rating'], personal['review_count'], personal['active_posts']), (3.0, 2, 1))
        self.assertEqual((in_org['avg_rating'], in_org['review_count'], in_org['active_posts']), (4.3, 3, 1))

    def test_every_role_of_the_organization_can_read_it_analyst_included(self):
        for role in ('ADMIN', EDITOR, ANALYST):
            member = User.objects.create_user(email=f'{role.lower()}@example.com', password='x', full_name='Role Test')
            self.join(member, role=role)
            with self.subTest(role=role):
                response = self.dashboard(member, ctx_header('ORGANIZATION', self.org.pk))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['summary']['review_count'], 3)

    def test_a_non_member_and_an_anonymous_visitor_are_refused(self):
        stranger = User.objects.create_user(email='stranger@example.com', password='x', full_name='Etranger Test')
        response = self.dashboard(stranger, ctx_header('ORGANIZATION', self.org.pk))
        self.assertEqual((response.status_code, response.json()['code']), (403, 'DENY_RELATION'))
        self.assertEqual(self.dashboard(None).status_code, 401)

    def test_provider_context_dashboard(self):
        for _ in range(2):
            self.review('PROVIDER', self.profile.pk, rating=2)
        self.client.force_authenticate(self.seller)
        response = self.client.get(reverse('dashboard_stats'), **ctx_header('PROVIDER', self.profile.pk))
        summary = response.json()['summary']
        self.assertEqual((summary['avg_rating'], summary['review_count']), (2.0, 2))

    def test_counters_of_another_context_are_not_mixed_in(self):
        DailyVisibilityCounter.objects.create(
            offer_id=uuid.uuid4(), seller_context_type='ORGANIZATION', seller_context_id=self.org.pk,
            date=timezone.localdate(), views=9,
        )
        self.assertEqual(self.dashboard(self.member).json()['summary']['total_views'], 0)
        in_org = self.dashboard(self.member, ctx_header('ORGANIZATION', self.org.pk)).json()['summary']
        self.assertEqual(in_org['total_views'], 9)


class ContextColumnsMigrationTests(TransactionTestCase):
    """Colonnes de contexte de `messaging` (0002) et `notifications` (0002), puis remplissage séparé (0003)."""

    def tearDown(self):
        call_command('migrate', verbosity=0)

    def targets(self, executor, messaging, notifications):
        leaf = lambda app: executor.loader.graph.leaf_nodes(app)[0]  # noqa: E731
        return [(messaging[0], messaging[1]), (notifications[0], notifications[1]), leaf('identity')]

    def test_schema_is_additive_nullable_and_indexed(self):
        executor = MigrationExecutor(connection)
        new = self.targets(
            executor, ('messaging', '0002_conversation_message_contexts'),
            ('notifications', '0002_notification_context'),
        )
        executor.migrate(new)
        apps_ = executor.loader.project_state(new).apps
        conversation = apps_.get_model('messaging', 'Conversation')
        message = apps_.get_model('messaging', 'Message')
        notification = apps_.get_model('notifications', 'Notification')
        for model, names in (
            (conversation, ('seller_context_type', 'seller_context_id')),
            (message, ('sender_context_type', 'sender_context_id')),
            (notification, ('context_type', 'context_id')),
        ):
            for name in names:
                self.assertTrue(model._meta.get_field(name).null, name)
            self.assertEqual(model._meta.get_field(names[0]).max_length, 20)
        indexes = {index.name for model in (conversation, notification) for index in model._meta.indexes}
        self.assertTrue({'conv_seller_ctx', 'notif_user_ctx'} <= indexes)

    def test_backfill_is_correct_idempotent_and_reversible(self):
        before = MigrationExecutor(connection)
        old = self.targets(before, ('messaging', '0001_initial'), ('notifications', '0001_initial'))
        before.migrate(old)
        old_apps = before.loader.project_state(old).apps
        HUser = old_apps.get_model('identity', 'User')
        HConversation = old_apps.get_model('messaging', 'Conversation')
        HMessage = old_apps.get_model('messaging', 'Message')
        HNotification = old_apps.get_model('notifications', 'Notification')
        alice = HUser.objects.create(email='alice@example.com')
        bob = HUser.objects.create(email='bob@example.com')
        conversation = HConversation.objects.create()
        conversation.participants.add(alice, bob)
        for sender in (alice, bob, alice):
            HMessage.objects.create(conversation=conversation, sender=sender, content='Bonjour')
        for owner in (alice, bob):
            HNotification.objects.create(user=owner, notification_type='SYSTEM', title='t', content='c')

        after = MigrationExecutor(connection)
        new = self.targets(
            after, ('messaging', '0003_fill_message_sender_context'),
            ('notifications', '0003_fill_notification_context'),
        )
        after.migrate(new)
        new_apps = after.loader.project_state(new).apps
        NMessage = new_apps.get_model('messaging', 'Message')
        NNotification = new_apps.get_model('notifications', 'Notification')
        NConversation = new_apps.get_model('messaging', 'Conversation')

        expected_messages = sorted((s.pk, 'USER', s.pk) for s in (alice, alice, bob))
        expected_notifications = sorted((s.pk, 'USER', s.pk) for s in (alice, bob))
        self.assertEqual(
            sorted((m.sender_id, m.sender_context_type, m.sender_context_id) for m in NMessage.objects.all()),
            expected_messages,
        )
        self.assertEqual(
            sorted((n.user_id, n.context_type, n.context_id) for n in NNotification.objects.all()),
            expected_notifications,
        )
        # Les conversations existantes restent sans contexte vendeur (ADR 0006, 10.3).
        conv = NConversation.objects.get()
        self.assertEqual((conv.seller_context_type, conv.seller_context_id), (None, None))
        self.assertEqual(conv.participants.count(), 2)

        # Idempotence : rejouer ne réécrase pas un contexte déjà posé et ne crée rien.
        marker = uuid.uuid4()
        NMessage.objects.filter(sender_id=bob.pk).update(sender_context_type='ORGANIZATION', sender_context_id=marker)
        NNotification.objects.filter(user_id=bob.pk).update(context_type='ORGANIZATION', context_id=marker)
        importlib.import_module(
            'apps.messaging.migrations.0003_fill_message_sender_context',
        ).fill_sender_contexts(new_apps, None)
        importlib.import_module(
            'apps.notifications.migrations.0003_fill_notification_context',
        ).fill_contexts(new_apps, None)
        self.assertEqual((NMessage.objects.count(), NNotification.objects.count()), (3, 2))
        self.assertEqual(NMessage.objects.filter(sender_context_id=marker).count(), 1)
        self.assertEqual(NNotification.objects.filter(context_id=marker).count(), 1)
        self.assertEqual(NMessage.objects.filter(sender_context_type='USER').count(), 2)

        # Retour arrière : colonnes retirées, données conservées.
        back = MigrationExecutor(connection)
        back.migrate(old)
        back_apps = back.loader.project_state(old).apps
        self.assertEqual(back_apps.get_model('messaging', 'Message').objects.count(), 3)
        self.assertEqual(back_apps.get_model('notifications', 'Notification').objects.count(), 2)
        self.assertNotIn(
            'context_id', {f.name for f in back_apps.get_model('notifications', 'Notification')._meta.get_fields()},
        )
        self.assertNotIn(
            'sender_context_id', {f.name for f in back_apps.get_model('messaging', 'Message')._meta.get_fields()},
        )
