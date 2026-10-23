import uuid

from django.test import TestCase

from apps.identity.models import User

from .models import Transaction


class TransactionStructureTests(TestCase):
    """Module gelé (L0-13) : seul l'alignement structurel est vérifié (ADR 0002)."""

    def test_transaction_has_a_uuid_key_and_references_the_offer_by_uuid(self):
        buyer = User.objects.create_user(email='b@example.com', password='x', full_name='Acheteur')
        seller = User.objects.create_user(email='s@example.com', password='x', full_name='Vendeur')
        offer_id = uuid.uuid4()
        transaction = Transaction.objects.create(buyer=buyer, seller=seller, offer_id=offer_id, amount=10)
        self.assertIsInstance(transaction.id, uuid.UUID)
        self.assertEqual(Transaction.objects.get(pk=transaction.pk).offer_id, offer_id)
        self.assertEqual(transaction.status, 'PENDING')

    def test_no_route_is_exposed(self):
        from apps.payments.urls import urlpatterns

        self.assertEqual(urlpatterns, [])


class FrozenModuleTests(TestCase):
    """L0-13 : le module est inerte (aucune route, aucun webhook, aucune commande, aucun admin)."""

    def test_every_payments_path_is_a_404_without_side_effect(self):
        for method in ('get', 'post', 'put', 'patch', 'delete'):
            for path in ('/api/payments/', '/api/payments/transactions/', '/api/payments/webhook/',
                         '/api/payments/webhooks/laxpaie/', '/api/payments/callback/'):
                response = getattr(self.client, method)(path, data={}, content_type='application/json') \
                    if method != 'get' else self.client.get(path)
                self.assertEqual(response.status_code, 404, f'{method} {path}')
        self.assertEqual(Transaction.objects.count(), 0)

    def test_no_payments_management_command_and_no_admin_registration(self):
        from django.contrib import admin
        from django.core.management import get_commands

        self.assertEqual([n for n, app in get_commands().items() if app == 'apps.payments'], [])
        self.assertNotIn(Transaction, admin.site._registry)
