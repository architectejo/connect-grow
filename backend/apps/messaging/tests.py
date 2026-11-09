import uuid

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Category, City, Commune
from apps.common.factories import make_test_image, owner_kwargs
from apps.identity.models import User
from apps.marketplace.models import Offer
from apps.notifications.models import Notification

from . import services
from .models import Conversation, Message


class MessagingTestBase(APITestCase):
    def setUp(self):
        city = City.objects.create(name='Kinshasa')
        commune = Commune.objects.create(city=city, name='Gombe')
        category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')
        self.other = User.objects.create_user(email='other@example.com', password='x', full_name='Tiers')
        self.offer = Offer.objects.create(
            **owner_kwargs(self.seller), category_id=category.id, commune_id=commune.id,
            title='Un joli canapé à vendre', description='Description suffisamment longue pour le CDC.',
            price=100, main_image=make_test_image(),
        )
        self.conversation = services.get_or_create_offer_conversation(
            offer_id=self.offer.id, user_ids=[self.buyer.id, self.seller.id],
        )


class ServiceTests(MessagingTestBase):
    def test_conversation_is_reused_for_the_same_pair_and_offer(self):
        again = services.get_or_create_offer_conversation(
            offer_id=self.offer.id, user_ids=[self.seller.id, self.buyer.id],
        )
        self.assertEqual(again.id, self.conversation.id)

    def test_other_buyer_or_other_offer_gets_another_conversation(self):
        other_buyer = services.get_or_create_offer_conversation(
            offer_id=self.offer.id, user_ids=[self.other.id, self.seller.id],
        )
        other_offer = services.get_or_create_offer_conversation(
            offer_id=uuid.uuid4(), user_ids=[self.buyer.id, self.seller.id],
        )
        self.assertEqual(len({self.conversation.id, other_buyer.id, other_offer.id}), 3)

    def test_send_message_notifies_the_other_participant_and_bumps_the_conversation(self):
        before = Conversation.objects.get(pk=self.conversation.pk).updated_at
        message = services.send_message(conversation=self.conversation, sender=self.buyer, content='Bonjour !')
        self.assertGreater(Conversation.objects.get(pk=self.conversation.pk).updated_at, before)
        notification = Notification.objects.get(user=self.seller)
        self.assertEqual((notification.notification_type, notification.content), ('MESSAGE', 'Bonjour !'))
        self.assertEqual(message.conversation, self.conversation)
        self.assertFalse(Notification.objects.filter(user=self.buyer).exists())


class ConversationApiTests(MessagingTestBase):
    url = '/api/v1/interactions/conversations/'

    def test_lists_only_own_conversations_with_expected_keys(self):
        services.send_message(conversation=self.conversation, sender=self.buyer, content='Bonjour !', notify=False)
        self.client.force_authenticate(self.seller)
        data = self.client.get(self.url).data
        self.assertEqual(len(data), 1)
        item = data[0]
        self.assertEqual(
            set(item), {
                'id', 'post', 'post_title', 'post_image', 'other_participant', 'last_message', 'seller_context',
                'updated_at',
            },
        )
        self.assertIsNone(item['seller_context'])
        self.assertEqual(item['post'], str(self.offer.id))
        self.assertEqual(item['post_title'], self.offer.title)
        self.assertTrue(item['post_image'].endswith('.webp'))
        self.assertEqual(item['other_participant']['id'], self.buyer.id)
        self.assertEqual(item['last_message']['content'], 'Bonjour !')

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).data, [])
        self.assertEqual(self.client.get(f'{self.url}{self.conversation.id}/').status_code, status.HTTP_404_NOT_FOUND)

    def test_conversation_survives_the_purge_of_its_offer(self):
        self.offer.delete()
        self.client.force_authenticate(self.buyer)
        item = self.client.get(self.url).data[0]
        self.assertIsNone(item['post'])
        self.assertIsNone(item['post_title'])
        self.assertIsNone(item['last_message'])

    def test_list_query_count_does_not_grow_with_conversations(self):
        self.client.force_authenticate(self.seller)
        services.send_message(conversation=self.conversation, sender=self.buyer, content='Bonjour !')
        self.client.get(self.url)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)
        for i in range(5):
            buyer = User.objects.create_user(email=f'b{i}@example.com', password='x', full_name=f'B{i}')
            conversation = services.get_or_create_offer_conversation(
                offer_id=self.offer.id, user_ids=[buyer.id, self.seller.id],
            )
            services.send_message(conversation=conversation, sender=buyer, content='Salut', notify=False)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)
        self.assertEqual(len(few.captured_queries), len(many.captured_queries))

    def test_anonymous_is_refused(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)


class MessageApiTests(MessagingTestBase):
    url = '/api/v1/interactions/messages/'

    def test_participant_sends_and_other_is_notified(self):
        self.client.force_authenticate(self.buyer)
        response = self.client.post(self.url, {'conversation': str(self.conversation.id), 'content': 'Bonjour'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data['is_me'])
        self.assertEqual(response.data['sender_name'], 'Acheteur')
        self.assertEqual(Message.objects.get().sender, self.buyer)
        self.assertEqual(Notification.objects.get(user=self.seller).title, 'Nouveau message de Acheteur')

    def test_outsider_cannot_write_in_a_conversation(self):
        self.client.force_authenticate(self.other)
        response = self.client.post(self.url, {'conversation': str(self.conversation.id), 'content': 'Intrus'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Message.objects.exists())

    def test_content_is_required_and_bounded(self):
        self.client.force_authenticate(self.buyer)
        for content in ('', 'x' * 2001):
            response = self.client.post(self.url, {'conversation': str(self.conversation.id), 'content': content})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_is_limited_to_own_conversations_and_filterable(self):
        message = services.send_message(
            conversation=self.conversation, sender=self.buyer, content='Bonjour', notify=False,
        )
        self.client.force_authenticate(self.seller)
        listed = self.client.get(self.url, {'conversation': str(self.conversation.id)}).data
        self.assertEqual([m['id'] for m in listed], [str(message.id)])
        self.assertEqual(self.client.get(self.url, {'conversation': 'pas-un-uuid'}).data, [])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).data, [])

    def test_messages_cannot_be_edited_or_deleted(self):
        message = services.send_message(
            conversation=self.conversation, sender=self.buyer, content='Bonjour', notify=False,
        )
        self.client.force_authenticate(self.seller)
        url = f'{self.url}{message.id}/'
        self.assertEqual(self.client.patch(url, {'content': 'Réécrit'}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        message.refresh_from_db()
        self.assertEqual(message.content, 'Bonjour')

    def test_anonymous_is_refused(self):
        self.assertEqual(self.client.post(self.url, {}).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_conversation_has_no_foreign_key_to_another_domain(self):
        for model in (Conversation, Message):
            for field in model._meta.get_fields():
                if field.is_relation and field.concrete:
                    self.assertIn(field.related_model._meta.app_label, ('messaging', 'identity'), field.name)
