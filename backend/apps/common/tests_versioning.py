"""Versionnement de l'API sous `/api/v1/` et plafond de pagination (L0-11, ADR 0007)."""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from django.urls import get_resolver
from rest_framework.test import APIRequestFactory, APITestCase

from backend.api_limits import parse_page_limits
from apps.common.pagination import OptionalPagination, StandardPagination
from apps.notifications import services as notification_services
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
    URL = '/api/v1/interactions/notifications/'

    def setUp(self):
        self.user = User.objects.create_user(email='p@example.com', password='x', full_name='P')
        for n in range(5):
            notification_services.notify(user_id=self.user.pk, notification_type='SYSTEM', title=f'N{n}', content='c')
        self.client.force_authenticate(self.user)

    def test_page_size_paginates_with_links(self):
        first = self.client.get(self.URL + '?page_size=2').data
        self.assertEqual(first['count'], 5)
        self.assertEqual(len(first['results']), 2)
        self.assertIsNotNone(first['next'])
        self.assertIn('page_size=2', first['next'])
        self.assertIsNone(first['previous'])
        second = self.client.get(self.URL + '?page_size=2&page=2').data
        self.assertEqual(len(second['results']), 2)
        self.assertIsNotNone(second['previous'])
        last = self.client.get(self.URL + '?page_size=2&page=3').data
        self.assertEqual(len(last['results']), 1)
        self.assertIsNone(last['next'])

    @override_settings(API_MAX_PAGE_SIZE=2)
    def test_list_endpoint_is_capped(self):
        response = self.client.get(self.URL + '?page_size=1000')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 2)
        self.assertEqual(response.data['count'], 5)


class OptionalPaginationTests(SimpleTestCase):
    """Comportement de `OptionalPagination` sur une liste de 5 éléments (sans base de données)."""

    def paginate(self, query):
        from rest_framework.request import Request
        request = Request(APIRequestFactory().get('/x/' + query))
        paginator = OptionalPagination()
        page = paginator.paginate_queryset(list(range(5)), request)
        return paginator, page

    def test_bare_array_without_page_params(self):
        _, page = self.paginate('')
        self.assertIsNone(page)  # la vue renvoie alors le tableau nu

    def test_envelope_with_page_or_page_size(self):
        for query in ('?page=1', '?page_size=2'):
            paginator, page = self.paginate(query)
            self.assertIsNotNone(page, query)
            body = paginator.get_paginated_response(page).data
            self.assertEqual(set(body), {'count', 'next', 'previous', 'results'})
            self.assertEqual(body['count'], 5)

    @override_settings(API_MAX_PAGE_SIZE=2)
    def test_cap_applies(self):
        _, page = self.paginate('?page_size=50')
        self.assertEqual(page, [0, 1])


class PageLimitSettingsTests(SimpleTestCase):
    def test_valid_values(self):
        self.assertEqual(parse_page_limits('20', '100'), (20, 100))
        self.assertEqual(parse_page_limits(' 5 ', '5'), (5, 5))

    def test_invalid_values_fail_explicitly(self):
        for size, maximum in (('abc', '100'), ('0', '100'), ('-3', '100'), ('20', 'x'), ('20', '0'), ('20', '-1'),
                              ('', '100'), ('200', '100')):
            with self.assertRaises(ImproperlyConfigured, msg=(size, maximum)):
                parse_page_limits(size, maximum)
