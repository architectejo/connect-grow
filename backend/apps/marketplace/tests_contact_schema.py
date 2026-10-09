"""Schéma posé par l'ADR 0005 (T1) côté marketplace : réglages de révélation, delivered_at, index, événements."""
import uuid

from django.contrib.admin.sites import site as admin_site
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from apps.platform_core import catalog
from apps.platform_core.checks import check_event_catalog

from .models import ContactEvent, MarketplaceSettings
from .tests import MarketplaceTestBase


class RevealSettingsTests(MarketplaceTestBase):
    def test_defaults_follow_the_adr(self):
        row = MarketplaceSettings.get_solo()
        self.assertEqual(
            (row.reveal_daily_limit_account, row.reveal_daily_limit_new_account, row.new_account_hours), (15, 3, 24),
        )

    def test_bounds_are_validated(self):
        for field, bad in (
            ('reveal_daily_limit_account', 0), ('reveal_daily_limit_account', 1001),
            ('reveal_daily_limit_new_account', 0), ('reveal_daily_limit_new_account', 1001),
            ('new_account_hours', 721),
        ):
            with self.subTest(field=field, value=bad):
                row = MarketplaceSettings.get_solo()
                setattr(row, field, bad)
                with self.assertRaises(ValidationError) as ctx:
                    row.full_clean()
                self.assertIn(field, ctx.exception.message_dict)
        row = MarketplaceSettings.get_solo()
        row.new_account_hours = 0
        row.full_clean()  # 0 autorisé : plus aucun compte n'est « neuf » par l'ancienneté

    def test_settings_are_editable_in_admin(self):
        self.assertIn('reveal_daily_limit_account', admin_site._registry[MarketplaceSettings].list_display)


class ContactEventSchemaTests(MarketplaceTestBase):
    def test_delivered_at_is_nullable_and_message_may_be_blank_for_calls(self):
        offer = self.make_offer()
        event = ContactEvent.objects.create(offer=offer, sender=self.buyer, channel='CALL')
        self.assertIsNone(event.delivered_at)
        self.assertEqual(event.message, '')

    def test_sender_channel_index_exists(self):
        names = {index.name for index in ContactEvent._meta.indexes}
        self.assertIn('contact_sender_channel_created', names)


class DeliveredAtBackfillTests(TransactionTestCase):
    """La migration marketplace 0005 remplit delivered_at des contacts existants."""

    migrate_from = [('marketplace', '0004_validateurs_prix_stock'), ('identity', '0003_emails_en_minuscules')]
    migrate_to = [('marketplace', '0005_contactevent_delivered_at_and_reveal_limits'), ('identity', '0003_emails_en_minuscules')]

    def tearDown(self):
        call_command('migrate', verbosity=0)

    def test_existing_contacts_get_created_at(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        User = old_apps.get_model('identity', 'User')
        Offer = old_apps.get_model('marketplace', 'Offer')
        Event = old_apps.get_model('marketplace', 'ContactEvent')
        seller = User.objects.create(email='s@example.com')
        buyer = User.objects.create(email='b@example.com')
        offer = Offer.objects.create(
            seller=seller, category_id=uuid.uuid4(), commune_id=uuid.uuid4(), title='Un joli canapé à vendre',
            description='Description suffisamment longue pour passer.', price=1, expires_at=timezone.now(),
        )
        event = Event.objects.create(offer=offer, sender=buyer, message='Bonjour', channel='MESSAGE')

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        migrated = new_apps.get_model('marketplace', 'ContactEvent').objects.get(pk=event.pk)
        self.assertIsNotNone(migrated.delivered_at)
        self.assertEqual(migrated.delivered_at, migrated.created_at)


class ContactEventsCatalogTests(MarketplaceTestBase):
    def test_new_event_types_are_registered_and_checks_are_green(self):
        for name in ('marketplace.contact_revealed', 'messaging.contact_message_delivered'):
            self.assertIn(name, catalog.EVENT_TYPES)
        self.assertEqual(catalog.EVENT_TYPES['marketplace.contact_revealed'].domain, 'marketplace')
        self.assertEqual(catalog.EVENT_TYPES['messaging.contact_message_delivered'].domain, 'messaging')
        self.assertEqual(check_event_catalog(None), [])
