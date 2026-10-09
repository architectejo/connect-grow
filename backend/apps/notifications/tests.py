from rest_framework import status
from rest_framework.test import APITestCase

from apps.identity.models import User

from . import services
from .models import Notification


class NotificationTests(APITestCase):
    url = '/api/interactions/notifications/'

    def setUp(self):
        self.user = User.objects.create_user(email='a@example.com', password='x', full_name='A')
        self.other = User.objects.create_user(email='b@example.com', password='x', full_name='B')
        self.mine = services.notify(
            user_id=self.user.id, notification_type=services.SYSTEM, title='Bienvenue', content='Contenu', link='/x',
        )
        services.notify(user_id=self.other.id, notification_type=services.SYSTEM, title='Autre', content='Contenu')

    def test_list_only_own_notifications_with_expected_keys(self):
        self.client.force_authenticate(self.user)
        data = self.client.get(self.url).data
        self.assertEqual([n['id'] for n in data], [str(self.mine.id)])
        self.assertEqual(
            set(data[0]), {'id', 'user', 'notification_type', 'title', 'content', 'link', 'is_read', 'created_at'},
        )

    def test_service_truncates_long_titles_and_links(self):
        notification = services.notify(
            user_id=self.user.id, notification_type=services.CONTACT, title='T' * 400, content='c', link='/' + 'l' * 400,
        )
        self.assertEqual((len(notification.title), len(notification.link)), (255, 255))

    def test_mark_one_as_read_and_nothing_else_is_editable(self):
        self.client.force_authenticate(self.user)
        response = self.client.patch(f'{self.url}{self.mine.id}/', {'is_read': True, 'title': 'Piraté', 'content': 'X'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.mine.refresh_from_db()
        self.assertTrue(self.mine.is_read)
        self.assertEqual(self.mine.title, 'Bienvenue')

    def test_cannot_touch_someone_elses_notification(self):
        theirs = Notification.objects.get(user=self.other)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.patch(f'{self.url}{theirs.id}/', {'is_read': True}).status_code, 404)
        self.assertEqual(self.client.delete(f'{self.url}{theirs.id}/').status_code, 404)

    def test_mark_all_as_read_affects_only_own_notifications(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(f'{self.url}mark_all_as_read/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Notification.objects.filter(user=self.user, is_read=False).count(), 0)
        self.assertEqual(Notification.objects.filter(user=self.other, is_read=False).count(), 1)

    def test_clients_cannot_create_notifications(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(self.url, {'notification_type': 'SYSTEM', 'title': 'Faux', 'content': 'X'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_anonymous_is_refused(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_optional_pagination(self):
        self.client.force_authenticate(self.user)
        for i in range(3):
            services.notify(user_id=self.user.id, notification_type=services.SYSTEM, title=f'N{i}', content='c')
        self.assertEqual(self.client.get(self.url, {'page_size': 2}).data['count'], 4)
