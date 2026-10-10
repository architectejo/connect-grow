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
