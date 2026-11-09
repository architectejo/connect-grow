"""Documentation OpenAPI de l'API sous `/api/v1/` (L0-11b, ADR 0007)."""
import json
import re

from django.test import TestCase
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema  # noqa: F401  (utilisé par la commande --validate)
from rest_framework.test import APITestCase


class OpenApiSchemaTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = SchemaGenerator().get_schema(request=None, public=True)

    def test_schema_endpoint_is_served_and_is_openapi3(self):
        response = self.client.get('/api/v1/schema/', HTTP_ACCEPT='application/vnd.oai.openapi+json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['openapi'].startswith('3.'))
        self.assertEqual(data['info']['title'], 'Connecte+ API')
        self.assertEqual(data['info']['version'], '1.0.0')

    def test_schema_endpoint_is_public(self):
        self.assertEqual(self.client.get('/api/v1/schema/').status_code, 200)

    def test_schema_validates(self):
        validate_schema(self.schema)

    def test_only_v1_paths_and_no_old_prefix(self):
        paths = list(self.schema['paths'])
        self.assertGreater(len(paths), 50)
        self.assertTrue(all(p.startswith('/api/v1/') for p in paths))
        self.assertFalse([p for p in paths if p.startswith('/api/') and not p.startswith('/api/v1/')])
        self.assertFalse([p for p in paths if '/schema/' in p or '/docs/' in p or p.startswith('/admin')])

    def test_bearer_and_context_header_documented(self):
        scheme = self.schema['components']['securitySchemes']['jwtAuth']
        self.assertEqual((scheme['type'], scheme['scheme'], scheme['bearerFormat']), ('http', 'bearer', 'JWT'))
        param = self.schema['components']['parameters']['ActiveContext']
        self.assertEqual((param['name'], param['in'], param['required']), ('X-Context', 'header', False))
        ref = {'$ref': '#/components/parameters/ActiveContext'}
        for path, item in self.schema['paths'].items():
            for method, op in item.items():
                if method in ('get', 'post', 'put', 'patch', 'delete'):
                    self.assertIn(ref, op['parameters'], f'{method} {path}')

    def test_no_personal_data_in_schema(self):
        text = json.dumps(self.schema)
        for marker in ('@gmail', '@yahoo'):
            self.assertNotIn(marker, text)
        self.assertIsNone(re.search(r'\+243\d{6}', text))  # un motif de validation n'est pas un numéro


class DocsInterfaceTests(TestCase):
    def test_docs_ui_not_served_outside_debug(self):
        # Les tests tournent avec DEBUG=False : l'interface (assets externes) n'est pas routée.
        self.assertEqual(self.client.get('/api/v1/docs/').status_code, 404)
