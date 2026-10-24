"""Messagerie par contexte vendeur (ADR 0006, A8 et 9.8 ; T7 / L0-09f2) : conversations d'organisation, accès par
capacité (`message.reply`), réponse « en tant que » l'organisation, IDOR, anciennes conversations, requêtes constantes,
aucune donnée de membre exposée à l'acheteur."""
import json

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.catalog.models import Category, City, Commune
from apps.common.factories import make_test_image
from apps.identity.models import Membership, Organization, User
from apps.marketplace.models import Offer
from apps.moderation.models import Sanction
from apps.notifications.models import Notification

from . import services
from .models import Conversation, Message

CONVERSATIONS = '/api/interactions/conversations/'
MESSAGES = '/api/interactions/messages/'
SECRET_PHONE = '+243970000001'


class OrgMessagingBase(TestCase):
    def setUp(self):
        city = City.objects.create(name='Kinshasa')
        commune = Commune.objects.create(city=city, name='Gombe')
        category = Category.objects.create(name='Électronique', slug='electronique')
        self.org = Organization.objects.create(name='Atelier X', org_type='ENTREPRISE')
        self.other_org = Organization.objects.create(name='Atelier B', org_type='BOUTIQUE')
        self.team = {}
        for index, role in enumerate(('OWNER', 'ADMIN', 'EDITOR', 'ANALYST')):
            user = User.objects.create_user(
                email=f'{role.lower()}-secret@example.com', phone=f'+24397000000{index + 1}', password='x',
                full_name=f'Membre {role.title()}',
            )
            Membership.objects.create(organization=self.org, user=user, role=role)
            self.team[role] = user
        self.stranger = User.objects.create_user(email='stranger@example.com', password='x', full_name='Autre Owner')
        Membership.objects.create(organization=self.other_org, user=self.stranger, role='OWNER')
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')
        self.offer = Offer.objects.create(
            seller_context_type='ORGANIZATION', seller_context_id=self.org.pk,
            created_by=self.team['EDITOR'], category_id=category.id, commune_id=commune.id,
            title='Un joli canapé à vendre', description='Description suffisamment longue pour le CDC.',
            price=100, main_image=make_test_image(),
        )
        self.category, self.commune = category, commune
        services.open_conversation_with_message(
            offer_id=self.offer.id, sender_id=self.buyer.pk, content='Bonjour',
            seller_context=('ORGANIZATION', self.org.pk),
        )
        self.conversation = Conversation.objects.get()

    def client_for(self, user, org=None):
        client = APIClient()
        client.force_authenticate(user)
        if org is not None:
            client.defaults['HTTP_X_CONTEXT'] = f'ORGANIZATION:{org.pk}'
        return client

    def messages_of(self, user, conversation=None):
        response = self.client_for(user).get(MESSAGES, {'conversation': str((conversation or self.conversation).id)})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def write(self, user, content='Réponse', conversation=None):
        return self.client_for(user).post(
            MESSAGES, {'conversation': str((conversation or self.conversation).id), 'content': content},
        )


class ConversationModelTests(OrgMessagingBase):
    def test_an_organization_conversation_has_the_buyer_as_only_participant(self):
        self.assertEqual((self.conversation.seller_context_type, self.conversation.seller_context_id),
                         ('ORGANIZATION', self.org.pk))
        self.assertEqual(list(self.conversation.participants.all()), [self.buyer])

    def test_the_conversation_is_reused_for_the_same_buyer_and_offer_only(self):
        again = services.get_or_create_offer_conversation(
            offer_id=self.offer.id, user_ids=[self.buyer.pk], seller_context=('ORGANIZATION', self.org.pk),
        )
        self.assertEqual(again.pk, self.conversation.pk)
        other_buyer = User.objects.create_user(email='b2@example.com', password='x', full_name='B2')
        separate = services.get_or_create_offer_conversation(
            offer_id=self.offer.id, user_ids=[other_buyer.pk], seller_context=('ORGANIZATION', self.org.pk),
        )
        self.assertNotEqual(separate.pk, self.conversation.pk)

    def test_user_and_provider_contexts_keep_the_holder_as_participant(self):
        seller = User.objects.create_user(email='s@example.com', password='x', full_name='Vendeur')
        conversation = services.get_or_create_offer_conversation(
            offer_id=self.offer.id, user_ids=[self.buyer.pk, seller.pk], seller_context=('USER', seller.pk),
        )
        self.assertEqual((conversation.seller_context_type, conversation.seller_context_id), ('USER', seller.pk))
        self.assertEqual({u.pk for u in conversation.participants.all()}, {self.buyer.pk, seller.pk})


class InboxTests(OrgMessagingBase):
    def ids(self, response):
        return [item['id'] for item in response.json()]

    def test_owner_and_admin_see_the_conversation_in_the_organization_inbox(self):
        for role in ('OWNER', 'ADMIN'):
            response = self.client_for(self.team[role], self.org).get(CONVERSATIONS)
            self.assertEqual(response.status_code, 200, role)
            self.assertEqual(self.ids(response), [str(self.conversation.id)], role)

    def test_editor_and_analyst_are_refused_the_organization_inbox(self):
        for role in ('EDITOR', 'ANALYST'):
            response = self.client_for(self.team[role], self.org).get(CONVERSATIONS)
            self.assertEqual((response.status_code, response.json()['code']), (403, 'DENY_PERMISSION'), role)

    def test_a_member_of_another_organization_cannot_use_this_inbox(self):
        response = self.client_for(self.stranger, self.org).get(CONVERSATIONS)
        self.assertEqual((response.status_code, response.json()['code']), (403, 'DENY_RELATION'))
        own = self.client_for(self.stranger, self.other_org).get(CONVERSATIONS)
        self.assertEqual(own.json(), [])

    def test_the_personal_inbox_of_a_member_does_not_contain_the_organization_conversations(self):
        self.assertEqual(self.client_for(self.team['OWNER']).get(CONVERSATIONS).json(), [])

    def test_the_buyer_sees_the_organization_not_a_member(self):
        item = self.client_for(self.buyer).get(CONVERSATIONS).json()[0]
        self.assertEqual(item['seller_context'], {'type': 'ORGANIZATION', 'id': str(self.org.pk)})
        self.assertEqual(item['other_participant']['full_name'], 'Atelier X')
        self.assertEqual(item['other_participant']['id'], str(self.org.pk))

    def test_the_team_sees_the_buyer(self):
        item = self.client_for(self.team['OWNER'], self.org).get(CONVERSATIONS).json()[0]
        self.assertEqual(item['other_participant']['full_name'], 'Acheteur')

    def test_last_message_written_by_the_team_exposes_the_organization_not_the_member(self):
        self.write(self.team['ADMIN'], 'Bien reçu')
        for client in (self.client_for(self.buyer), self.client_for(self.team['OWNER'], self.org)):
            last = client.get(CONVERSATIONS).json()[0]['last_message']
            self.assertEqual((last['content'], last['sender_id']), ('Bien reçu', str(self.org.pk)))
            self.assertNotIn(str(self.team['ADMIN'].pk), json.dumps(last))

    def test_detail_is_by_object_and_ignores_the_header(self):
        url = f'{CONVERSATIONS}{self.conversation.id}/'
        self.assertEqual(self.client_for(self.team['ADMIN']).get(url).status_code, 200)
        self.assertEqual(self.client_for(self.buyer).get(url).status_code, 200)
        for user in (self.team['EDITOR'], self.team['ANALYST'], self.stranger):
            self.assertEqual(self.client_for(user).get(url).status_code, 404, user.email)
        # Un en-tête d'une autre organisation ne donne pas accès à celle-ci.
        self.assertEqual(self.client_for(self.stranger, self.other_org).get(url).status_code, 404)

    def test_each_buyer_only_sees_his_own_conversation(self):
        other_buyer = User.objects.create_user(email='b2@example.com', password='x', full_name='B2')
        services.open_conversation_with_message(
            offer_id=self.offer.id, sender_id=other_buyer.pk, content='Salut', seller_context=('ORGANIZATION', self.org.pk),
        )
        self.assertEqual(len(self.client_for(self.buyer).get(CONVERSATIONS).json()), 1)
        self.assertEqual(len(self.client_for(self.team['OWNER'], self.org).get(CONVERSATIONS).json()), 2)
        mine = self.client_for(other_buyer).get(CONVERSATIONS).json()
        self.assertEqual(len(mine), 1)
        self.assertNotEqual(mine[0]['id'], str(self.conversation.id))


class MessageAccessTests(OrgMessagingBase):
    def test_owner_and_admin_read_the_conversation(self):
        for role in ('OWNER', 'ADMIN'):
            self.assertEqual([m['content'] for m in self.messages_of(self.team[role])], ['Bonjour'], role)

    def test_editor_analyst_and_other_organizations_read_nothing_and_write_nothing(self):
        for user in (self.team['EDITOR'], self.team['ANALYST'], self.stranger):
            self.assertEqual(self.messages_of(user), [], user.email)
            response = self.write(user, 'Intrus')
            self.assertEqual(response.status_code, 400, user.email)
        self.assertEqual(Message.objects.count(), 1)

    def test_a_former_member_loses_access_at_once_but_the_history_stays(self):
        admin = self.team['ADMIN']
        self.assertEqual(self.write(admin, 'Avant la révocation').status_code, 201)
        Membership.objects.filter(organization=self.org, user=admin).update(status=Membership.STATUS_REVOKED)
        self.assertEqual(self.messages_of(admin), [])
        self.assertEqual(self.write(admin, 'Après').status_code, 400)
        self.assertEqual(self.client_for(admin).get(f'{CONVERSATIONS}{self.conversation.id}/').status_code, 404)
        self.assertEqual(self.client_for(admin, self.org).get(CONVERSATIONS).status_code, 403)
        self.assertEqual(Message.objects.count(), 2)  # l'historique est conservé
        self.assertEqual(len(self.messages_of(self.buyer)), 2)

    def test_a_restricted_account_loses_access_to_the_organization_conversation(self):
        owner = self.team['OWNER']
        self.assertEqual(len(self.messages_of(owner)), 1)
        Sanction.objects.create(
            user=owner, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.team['ADMIN'],
        )
        self.assertEqual(self.messages_of(owner), [])
        self.assertEqual(self.write(owner).status_code, 400)
        self.assertEqual(self.client_for(owner).get(f'{CONVERSATIONS}{self.conversation.id}/').status_code, 404)

    def test_a_suspended_organization_closes_the_team_access(self):
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertEqual(self.messages_of(self.team['OWNER']), [])
        self.assertEqual(self.write(self.team['OWNER']).status_code, 400)

    def test_the_service_rechecks_the_access_under_the_transaction(self):
        admin = self.team['ADMIN']
        Membership.objects.filter(organization=self.org, user=admin).update(status=Membership.STATUS_REVOKED)
        with self.assertRaises(services.ConversationAccessDenied):
            services.send_message(conversation=self.conversation, sender=admin, content='Trop tard')
        self.assertEqual(Message.objects.count(), 1)


class ReplyAsOrganizationTests(OrgMessagingBase):
    def test_the_team_replies_as_the_organization(self):
        admin = self.team['ADMIN']
        response = self.write(admin, 'Bonjour, oui il est disponible')
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual(data['sender_name'], 'Atelier X')
        self.assertEqual(data['sender'], str(self.org.pk))
        self.assertEqual(data['sender_context'], {'type': 'ORGANIZATION', 'id': str(self.org.pk)})
        self.assertTrue(data['is_me'])
        message = Message.objects.get(content='Bonjour, oui il est disponible')
        self.assertEqual((message.sender, message.sender_context_type, message.sender_context_id),
                         (admin, 'ORGANIZATION', self.org.pk))  # l'auteur reste tracé en interne
        self.assertNotIn(str(admin.pk), response.content.decode())

    def test_the_buyer_sees_no_member_identity_in_the_messages(self):
        self.write(self.team['ADMIN'], 'Réponse de l équipe')
        listed = self.messages_of(self.buyer)
        reply = next(m for m in listed if m['content'] == 'Réponse de l équipe')
        self.assertEqual((reply['sender_name'], reply['sender'], reply['is_me']), ('Atelier X', str(self.org.pk), False))
        blob = json.dumps(listed) + self.client_for(self.buyer).get(CONVERSATIONS).content.decode()
        for team_user in self.team.values():
            for secret in (str(team_user.pk), team_user.email, team_user.phone, team_user.full_name):
                self.assertNotIn(secret, blob)
        own = next(m for m in listed if m['content'] == 'Bonjour')
        self.assertTrue(own['is_me'])
        self.assertIsNone(own['sender_context'])

    def test_is_me_is_true_for_every_authorized_member_of_the_organization_side(self):
        self.write(self.team['ADMIN'], 'Réponse')
        reply = next(m for m in self.messages_of(self.team['OWNER']) if m['content'] == 'Réponse')
        self.assertTrue(reply['is_me'])
        initial = next(m for m in self.messages_of(self.team['OWNER']) if m['content'] == 'Bonjour')
        self.assertFalse(initial['is_me'])

    def test_the_buyer_is_notified_with_the_organization_name(self):
        self.write(self.team['ADMIN'], 'Réponse')
        notification = Notification.objects.get(user=self.buyer)
        self.assertEqual(notification.title, 'Nouveau message de Atelier X')
        self.assertNotIn('Admin', notification.title + notification.content)
        self.assertIsNone(notification.context_type)  # l'acheteur est dans son contexte personnel

    def test_the_team_is_notified_when_the_buyer_writes(self):
        response = self.write(self.buyer, 'Une question')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['sender_context'], None)
        notified = set(Notification.objects.values_list('user_id', flat=True))
        self.assertEqual(notified, {self.team['OWNER'].pk, self.team['ADMIN'].pk})
        for notification in Notification.objects.all():
            self.assertEqual((notification.context_type, notification.context_id), ('ORGANIZATION', self.org.pk))
            self.assertEqual(notification.title, 'Nouveau message de Acheteur')

    def test_a_message_cannot_be_forged_in_the_name_of_an_organization(self):
        response = self.client_for(self.buyer).post(MESSAGES, {
            'conversation': str(self.conversation.id), 'content': 'Faux', 'sender_context_type': 'ORGANIZATION',
            'sender_context_id': str(self.org.pk), 'sender': str(self.team['OWNER'].pk),
        })
        self.assertEqual(response.status_code, 201)
        message = Message.objects.get(content='Faux')
        self.assertEqual((message.sender, message.sender_context_type, message.sender_context_id),
                         (self.buyer, None, None))


class LegacyConversationTests(OrgMessagingBase):
    def setUp(self):
        super().setUp()
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.legacy = Conversation.objects.create(offer_id=self.offer.id)
        self.legacy.participants.add(self.buyer, self.seller)
        Message.objects.create(conversation=self.legacy, sender=self.buyer, content='Ancien message')

    def test_a_conversation_without_context_stays_accessible_by_participants_only(self):
        self.assertEqual(len(self.messages_of(self.seller, self.legacy)), 1)
        self.assertEqual(len(self.messages_of(self.buyer, self.legacy)), 1)
        for user in (*self.team.values(), self.stranger):
            self.assertEqual(self.messages_of(user, self.legacy), [], user.email)
            self.assertEqual(self.write(user, 'Intrus', self.legacy).status_code, 400)
        self.assertEqual(self.write(self.seller, 'Réponse', self.legacy).status_code, 201)
        self.assertIsNone(Message.objects.get(content='Réponse').sender_context_type)

    def test_the_legacy_conversation_is_not_in_the_organization_inbox(self):
        ids = [item['id'] for item in self.client_for(self.team['OWNER'], self.org).get(CONVERSATIONS).json()]
        self.assertEqual(ids, [str(self.conversation.id)])
        self.assertEqual(
            {item['id'] for item in self.client_for(self.seller).get(CONVERSATIONS).json()}, {str(self.legacy.id)},
        )

    def test_legacy_messages_expose_the_sender_as_before(self):
        item = self.messages_of(self.buyer, self.legacy)[0]
        self.assertEqual((item['sender'], item['sender_name'], item['sender_context']),
                         (str(self.buyer.pk), 'Acheteur', None))


class QueryCountTests(OrgMessagingBase):
    def count(self, client, url, params=None):
        client.get(url, params)  # amorce les caches de processus (réglages, types de contenu)
        with CaptureQueriesContext(connection) as captured:
            response = client.get(url, params)
        self.assertEqual(response.status_code, 200)
        return len(captured.captured_queries)

    def grow(self, count):
        for index in range(count):
            buyer = User.objects.create_user(email=f'bb{index}@example.com', password='x', full_name=f'B{index}')
            services.open_conversation_with_message(
                offer_id=self.offer.id, sender_id=buyer.pk, content='Salut', seller_context=('ORGANIZATION', self.org.pk),
            )

    def test_the_organization_inbox_costs_a_constant_number_of_queries(self):
        client = self.client_for(self.team['OWNER'], self.org)
        few = self.count(client, CONVERSATIONS)
        self.grow(6)
        self.assertEqual(self.count(client, CONVERSATIONS), few)

    def test_the_buyer_inbox_costs_a_constant_number_of_queries(self):
        client = self.client_for(self.buyer)
        few = self.count(client, CONVERSATIONS)
        other_offer = Offer.objects.create(
            seller_context_type='ORGANIZATION', seller_context_id=self.other_org.pk,
            created_by=self.stranger, category_id=self.category.id, commune_id=self.commune.id,
            title='Une autre offre', description='Description suffisamment longue pour le CDC.', price=10,
            main_image=make_test_image(),
        )
        for offer in (other_offer,):
            services.open_conversation_with_message(
                offer_id=offer.id, sender_id=self.buyer.pk, content='Hello', seller_context=('ORGANIZATION', self.other_org.pk),
            )
        self.assertEqual(self.count(client, CONVERSATIONS), few)

    def test_the_message_list_costs_a_constant_number_of_queries_with_team_replies(self):
        self.write(self.team['ADMIN'], 'Une réponse')
        client = self.client_for(self.team['OWNER'])
        params = {'conversation': str(self.conversation.id)}
        few = self.count(client, MESSAGES, params)
        for index in range(5):
            self.write(self.team['ADMIN'], f'Réponse {index}')
            self.write(self.buyer, f'Question {index}')
        self.assertEqual(self.count(client, MESSAGES, params), few)


class HardeningTests(OrgMessagingBase):
    def test_deleting_an_account_keeps_its_messages(self):
        admin = self.team['ADMIN']
        self.write(admin, 'Réponse de l équipe')
        admin.delete()
        message = Message.objects.get(content='Réponse de l équipe')
        self.assertIsNone(message.sender_id)
        listed = self.messages_of(self.buyer)
        reply = next(m for m in listed if m['content'] == 'Réponse de l équipe')
        self.assertEqual((reply['sender_name'], reply['sender']), ('Atelier X', str(self.org.pk)))

    def test_a_message_without_sender_and_context_shows_a_neutral_name(self):
        Message.objects.create(conversation=self.conversation, sender=None, content='Orphelin')
        listed = self.messages_of(self.team['OWNER'])
        orphan = next(m for m in listed if m['content'] == 'Orphelin')
        self.assertEqual((orphan['sender_name'], orphan['is_me']), ('Utilisateur supprimé', False))

    def test_the_buyer_cannot_write_to_a_suspended_or_archived_organization(self):
        for state, code in ((Organization.STATUS_SUSPENDED, 'DENY_SECURITY'), (Organization.STATUS_ARCHIVED, 'DENY_OBJECT_STATE')):
            with self.subTest(state=state):
                Organization.objects.filter(pk=self.org.pk).update(status=state)
                response = self.write(self.buyer, 'Allô ?')
                self.assertEqual((response.status_code, response.json()['code']), (403, code))
        self.assertEqual(Message.objects.count(), 1)

    def test_unknown_and_forbidden_conversations_give_the_same_answer(self):
        import uuid

        forbidden = self.client_for(self.stranger).post(
            MESSAGES, {'conversation': str(self.conversation.id), 'content': 'x'},
        )
        unknown = self.client_for(self.stranger).post(MESSAGES, {'conversation': str(uuid.uuid4()), 'content': 'x'})
        malformed = self.client_for(self.stranger).post(MESSAGES, {'conversation': 'pas-un-uuid', 'content': 'x'})
        self.assertEqual(forbidden.status_code, 400)
        self.assertEqual(forbidden.json(), unknown.json())
        self.assertEqual(forbidden.json(), malformed.json())
        self.assertEqual(forbidden.json(), {'conversation': ['Conversation introuvable.']})

    def test_the_team_sees_the_buyer_abbreviated_and_without_photo(self):
        User.objects.filter(pk=self.buyer.pk).update(full_name='Marie Kabongo')
        item = self.client_for(self.team['OWNER'], self.org).get(CONVERSATIONS).json()[0]
        self.assertEqual((item['other_participant']['full_name'], item['other_participant']['photo']), ('Marie K.', None))
        first = self.messages_of(self.team['OWNER'])[0]
        self.assertEqual(first['sender_name'], 'Marie K.')
        # L'acheteur, lui, voit son propre nom.
        self.assertEqual(self.messages_of(self.buyer)[0]['sender_name'], 'Marie Kabongo')
        self.assertNotIn('Kabongo', Notification.objects.filter(user=self.team['OWNER']).first().content
                         if Notification.objects.filter(user=self.team['OWNER']).exists() else '')
