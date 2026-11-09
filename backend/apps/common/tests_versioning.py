"""Versionnement de l'API sous `/api/v1/` et plafond de pagination (L0-11, ADR 0007)."""
from django.test import SimpleTestCase, override_settings
from django.urls import get_resolver
from rest_framework.test import APIRequestFactory, APITestCase

from apps.common.pagination import StandardPagination
from apps.identity.models import User


class ApiPrefixTests(APITestCase):
    def test_public_route_is_served_under_v1(self):
        self.assertEqual(self.client.get('/api/v1/marketplace/cities/').status_code, 200)

    def test_old_prefix_is_not_served(self):
        for path in ('/api/marketplace/cities/', '/api/accounts/login/', '/api/config/features/',
                     '/api/interactions/notifications/', '/api/moderation/reports/'):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_every_api_route_is_under_v1(self):
        roots = {str(p.pattern) for p in get_resolver().url_patterns}
        self.assertEqual({r for r in roots if r.startswith('api')} - {r for r in roots if r.startswith('api/v1/')}, set())

    def test_api_headers_apply_under_v1(self):
        response = self.client.get('/api/v1/marketplace/cities/')
        self.assertIn('Authorization', response.headers.get('Vary', ''))


class PaginationCapTests(SimpleTestCase):
    def page_size(self, query):
        request = APIRequestFactory().get('/x/' + query)
        from rest_framework.request import Request
        return StandardPagination().get_page_size(Request(request))

    def test_default_and_cap_from_settings(self):
        self.assertEqual(self.page_size(''), 20)
        self.assertEqual(self.page_size('?page_size=1000'), 100)
        self.assertEqual(self.page_size('?page_size=7'), 7)

    def test_invalid_values_fall_back_to_default(self):
        for value in ('0', '-5', 'abc', '', '1.5'):
            self.assertEqual(self.page_size('?page_size=' + value), 20, value)

    @override_settings(API_PAGE_SIZE=5, API_MAX_PAGE_SIZE=10)
    def test_settings_are_honoured(self):
        self.assertEqual(self.page_size(''), 5)
        self.assertEqual(self.page_size('?page_size=50'), 10)


class PaginationEndToEndTests(APITestCase):
    @override_settings(API_MAX_PAGE_SIZE=2)
    def test_list_endpoint_is_capped(self):
        user = User.objects.create_user(email='p@example.com', password='x', full_name='P')
        self.client.force_authenticate(user)
        response = self.client.get('/api/v1/interactions/notifications/?page_size=1000')
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertLessEqual(len(response.data['results']), 2)
