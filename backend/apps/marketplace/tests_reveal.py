"""Révélation du numéro de contact et liste « qui a demandé » (ADR 0005, L0-10a-c/d, tâche T3)."""
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from apps.identity import services as identity_services
from apps.identity.models import CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint, User
from apps.moderation import services as moderation_services
from apps.moderation.models import AuditLog, Report, Sanction
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now

from . import services
from .models import ContactEvent, MarketplaceSettings, Offer
from .tests import MarketplaceTestBase

REVEAL_URL = '/api/interactions/contacts/reveal/'
RECEIVED_URL = '/api/interactions/contacts/reveals/received/'
CONTACTS_URL = '/api/interactions/contacts/'
SELLER_NUMBER = '+243891111111'
LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'reveal-throttle-tests'}}


class RevealTestBase(MarketplaceTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()  # les throttles par IP partagent le cache de tout le processus de test
        old = timezone.now() - timedelta(days=30)
        for user in (self.seller, self.buyer):
            User.objects.filter(pk=user.pk).update(phone_verified=True, date_joined=old)
            user.refresh_from_db()
        self.seller.full_name = 'Jean Mukendi'
        self.seller.save(update_fields=['full_name'])
        self.buyer.full_name = 'Marie Kabongo'
        self.buyer.save(update_fields=['full_name'])
        ContactPoint.objects.create(user=self.seller, phone=SELLER_NUMBER, is_verified=True)
        self.grant(self.seller, 'CALL')
        self.grant(self.seller, 'WHATSAPP')
        self.offer = self.make_offer()
        self.client.force_authenticate(self.buyer)

    @staticmethod
    def grant(user, channel):
        ContactConsent.objects.update_or_create(
            user=user, channel=channel,
            defaults={
                'is_granted': True, 'text_version': CONTACT_CONSENT_TEXT_VERSION, 'granted_at': timezone.now(),
                'phone_last4': SELLER_NUMBER[-4:],  # preuve d'accord exigée par get_contact_endpoint (L0-24)
            },
        )

    def reveal(self, offer=None, channel='CALL', **extra):
        offer = offer or self.offer
        return self.client.post(REVEAL_URL, {'offer': str(offer.id), 'channel': channel}, format='json', **extra)

    def set_limits(self, **values):
        MarketplaceSettings.objects.filter(pk=MarketplaceSettings.get_solo().pk).update(**values)

    def more_offers(self, count):
        return [self.make_offer(title=f'Annonce numéro {i}') for i in range(count)]


class RevealNominalTests(RevealTestBase):
    def test_call_reveal_returns_the_number_once_with_no_store(self):
        response = self.reveal()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(
            set(body), {'contact_event_id', 'channel', 'created', 'phone', 'tel_url', 'whatsapp_url'},
        )
        self.assertEqual(
            (body['channel'], body['created'], body['phone'], body['tel_url'], body['whatsapp_url']),
            ('CALL', True, SELLER_NUMBER, f'tel:{SELLER_NUMBER}', None),
        )
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Pragma'], 'no-cache')

    def test_whatsapp_reveal_builds_the_link_with_the_public_title_only(self):
        offer = self.make_offer(title='Chaussures & sacs à vendre')
        response = self.reveal(offer, 'WHATSAPP')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIsNone(body['tel_url'])
        self.assertEqual(
            body['whatsapp_url'], 'https://wa.me/243891111111?text=Chaussures%20%26%20sacs%20%C3%A0%20vendre',
        )

    def test_one_contact_event_one_audit_one_outbox_event_and_no_number_in_them(self):
        response = self.reveal()
        event = ContactEvent.objects.get()
        self.assertEqual((event.channel, event.sender, event.offer, event.message), ('CALL', self.buyer, self.offer, ''))
        self.assertEqual(event.delivered_at, event.created_at)
        self.assertTrue(event.is_counted)
        self.assertEqual(response.json()['contact_event_id'], str(event.pk))
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.contacts_count, 1)

        audit = AuditLog.objects.get(action='contact.number_revealed')
        self.assertEqual((audit.actor, audit.target_type, audit.target_id), (self.buyer, 'offer', self.offer.id))
        outbox = OutboxEvent.objects.get(event_type='marketplace.contact_revealed')
        self.assertEqual(outbox.payload, {
            'contact_event_id': str(event.pk), 'offer_id': str(self.offer.id), 'offer_title': self.offer.title,
            'seller_id': str(self.seller.pk), 'sender_id': str(self.buyer.pk), 'channel': 'CALL',
        })
        for text in (audit.details, str(outbox.payload)):
            self.assertNotIn('891111111', text)
            self.assertNotIn('+243', text)
        self.assertEqual(OutboxEvent.objects.filter(event_type='marketplace.contact_recorded').count(), 0)

    def test_the_seller_is_notified_with_the_display_name_and_no_number(self):
        self.reveal()
        dispatch_outbox_now()
        notification = Notification.objects.get(user=self.seller)
        self.assertEqual(notification.content, f'Marie K. a demandé votre numéro pour {self.offer.title}')
        self.assertNotIn('891111111', notification.title + notification.content + notification.link)
        self.assertEqual(Notification.objects.exclude(user=self.seller).count(), 0)

    def test_a_reveal_after_a_message_is_a_second_contact_that_is_not_counted_twice(self):
        services.create_contact_event(offer=self.offer, sender=self.buyer, message='Bonjour')
        self.assertEqual(self.reveal().status_code, 201)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.contacts_count, 1)  # un seul contact compté par fenêtre et par expéditeur
        self.assertEqual(ContactEvent.objects.filter(is_counted=True).count(), 1)

    def test_a_message_after_a_reveal_is_allowed_because_duplicates_are_judged_per_channel(self):
        self.reveal()
        response = self.client.post(CONTACTS_URL, {'post': str(self.offer.id), 'message': 'Bonjour'}, format='json')
        self.assertEqual(response.status_code, 201)


class RevealIdempotenceTests(RevealTestBase):
    def test_second_reveal_returns_the_same_contact_without_new_event_or_quota(self):
        self.set_limits(reveal_daily_limit_account=1, reveal_daily_limit_new_account=1)
        first = self.reveal()
        second = self.reveal()
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(second.json()['created'], False)
        self.assertEqual(second.json()['contact_event_id'], first.json()['contact_event_id'])
        self.assertEqual(second.json()['phone'], SELLER_NUMBER)
        self.assertIn('no-store', second['Cache-Control'])
        self.assertEqual(ContactEvent.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type='marketplace.contact_revealed').count(), 1)
        # Le numéro qui sort est tracé à chaque fois.
        self.assertEqual(AuditLog.objects.filter(action='contact.number_revealed').count(), 2)
        # Le plafond (1) est atteint, mais le renvoi ne le consomme pas et n'est pas refusé.
        other = self.more_offers(1)[0]
        self.assertEqual(self.reveal(other).status_code, 429)

    def test_each_channel_is_its_own_contact(self):
        self.assertEqual(self.reveal(channel='CALL').status_code, 201)
        self.assertEqual(self.reveal(channel='WHATSAPP').status_code, 201)
        self.assertEqual(ContactEvent.objects.count(), 2)

    def test_after_the_window_a_new_contact_is_created(self):
        self.reveal()
        ContactEvent.objects.update(created_at=timezone.now() - timedelta(hours=25))
        self.assertEqual(self.reveal().status_code, 201)
        self.assertEqual(ContactEvent.objects.count(), 2)

    def test_revoked_consent_refuses_even_a_duplicate(self):
        self.assertEqual(self.reveal().status_code, 201)
        identity_services.set_channel_consent(self.seller, 'CALL', enabled=False)
        response = self.reveal()
        self.assertEqual((response.status_code, response.json()['code']), (403, 'channel_not_allowed'))
        self.assertNotIn('891111111', response.content.decode())
        self.assertEqual(ContactEvent.objects.count(), 1)
        # L'autre canal, toujours consenti, reste utilisable.
        self.assertEqual(self.reveal(channel='WHATSAPP').status_code, 201)

    def test_revocation_between_the_consent_check_and_the_write_cannot_return_a_number_without_a_trace(self):
        """Le numéro n'est renvoyé qu'après le commit du contact : si l'écriture échoue, la réponse ne le contient pas."""
        with mock.patch.object(services, 'publish_event', side_effect=RuntimeError('panne')):
            with self.assertRaises(RuntimeError):
                self.reveal()
        self.assertEqual((ContactEvent.objects.count(), AuditLog.objects.filter(action='contact.number_revealed').count()), (0, 0))


class RevealRefusalTests(RevealTestBase):
    def code_of(self, response):
        return response.status_code, response.json().get('code')

    def test_invalid_channel(self):
        for channel in ('MESSAGE', 'SMS', 'call'):
            self.assertEqual(self.code_of(self.reveal(channel=channel)), (400, 'channel_invalid'), channel)
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_missing_fields_are_field_errors(self):
        response = self.client.post(REVEAL_URL, {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {'offer', 'channel'})

    def test_anonymous_gets_401_and_nothing_is_recorded(self):
        self.client.force_authenticate(None)
        response = self.reveal()
        self.assertEqual((response.status_code, response.json()['code']), (401, 'not_authenticated'))
        self.assertEqual((ContactEvent.objects.count(), AuditLog.objects.count()), (0, 0))

    def test_unavailable_offers_all_answer_the_same_404(self):
        import uuid
        trashed = self.make_offer(title='En corbeille', is_deleted=True)
        paused = self.make_offer(title='En pause', status=Offer.STATUS_PAUSED, is_active=False)
        hidden = self.make_offer(title='Masquée', is_hidden_by_moderation=True, is_active=False)
        expired = self.make_offer(title='Expirée', status=Offer.STATUS_EXPIRED, is_active=False)
        bodies = []
        for offer_id in (uuid.uuid4(), 'pas-un-uuid', trashed.id, paused.id, hidden.id, expired.id):
            response = self.client.post(REVEAL_URL, {'offer': str(offer_id), 'channel': 'CALL'}, format='json')
            self.assertEqual(self.code_of(response), (404, 'offer_not_found'), offer_id)
            bodies.append(response.json())
        self.assertEqual(len({str(b) for b in bodies}), 1)
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_offer_of_a_deactivated_seller_is_a_404(self):
        identity_services.set_account_active(self.seller.pk, False)
        dispatch_outbox_now()  # l'abonné recalcule `seller_is_public` (ADR 0006, A7)
        self.assertEqual(self.code_of(self.reveal()), (404, 'offer_not_found'))

    def test_own_offer(self):
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.code_of(self.reveal()), (403, 'own_offer'))
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_restricted_visitor(self):
        Sanction.objects.create(user=self.buyer, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='Test')
        self.assertEqual(self.code_of(self.reveal()), (403, 'contact_restricted'))
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_is_user_restricted_follows_blocking_active_sanctions_only(self):
        buyer = self.buyer.pk
        self.assertFalse(moderation_services.is_user_restricted(buyer))
        Sanction.objects.create(user=self.buyer, sanction_type=Sanction.TYPE_AVERTISSEMENT, reason='Test')
        Sanction.objects.create(
            user=self.buyer, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='Échue',
            ends_at=timezone.now() - timedelta(days=1),
        )
        Sanction.objects.create(
            user=self.buyer, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Levée', is_active=False,
        )
        self.assertFalse(moderation_services.is_user_restricted(buyer))
        Sanction.objects.create(
            user=self.buyer, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='En cours',
            ends_at=timezone.now() + timedelta(days=1),
        )
        self.assertTrue(moderation_services.is_user_restricted(buyer))

    def test_no_consent_or_unverified_number(self):
        ContactConsent.objects.filter(user=self.seller, channel='WHATSAPP').update(is_granted=False)
        self.assertEqual(self.code_of(self.reveal(channel='WHATSAPP')), (403, 'channel_not_allowed'))
        ContactPoint.objects.filter(user=self.seller).update(is_verified=False)
        self.assertEqual(self.code_of(self.reveal(channel='CALL')), (403, 'channel_not_allowed'))
        self.assertEqual(ContactEvent.objects.count(), 0)
        refused = AuditLog.objects.filter(action='contact.reveal_refused')
        self.assertEqual(refused.count(), 1)  # même visiteur, même offre, même jour : une seule trace
        for entry in refused.all():
            self.assertNotIn('891111111', entry.details)
        other = self.more_offers(1)[0]
        self.assertEqual(self.code_of(self.reveal(other, 'CALL')), (403, 'channel_not_allowed'))
        self.assertEqual(refused.all().count(), 2)  # autre offre : nouvelle trace
        AuditLog.objects.update(created_at=timezone.now() - timedelta(days=2))
        self.reveal()
        self.assertEqual(refused.all().count(), 3)  # autre jour : nouvelle trace

    def test_seller_without_any_consent_row(self):
        ContactConsent.objects.all().delete()
        self.assertEqual(self.code_of(self.reveal()), (403, 'channel_not_allowed'))


class RevealQuotaTests(RevealTestBase):
    def test_account_quota_is_a_429_with_retry_after_and_a_settings_driven_limit(self):
        self.set_limits(reveal_daily_limit_account=2)
        offers = self.more_offers(3)
        self.assertEqual(self.reveal(offers[0]).status_code, 201)
        self.assertEqual(self.reveal(offers[1]).status_code, 201)
        refused = self.reveal(offers[2])
        self.assertEqual((refused.status_code, refused.json()['code']), (429, 'reveal_quota_account'))
        self.assertIn('message', refused.json()['detail'])
        self.assertTrue(0 < int(refused['Retry-After']) <= 24 * 3600)
        self.assertEqual(ContactEvent.objects.count(), 2)
        self.assertNotIn('891111111', refused.content.decode())
        # Une modification dans le back-office joue tout de suite.
        self.set_limits(reveal_daily_limit_account=3)
        self.assertEqual(self.reveal(offers[2]).status_code, 201)

    def test_retry_after_is_the_time_before_the_oldest_reveal_leaves_the_window(self):
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(1)
        self.reveal()
        ContactEvent.objects.update(created_at=timezone.now() - timedelta(hours=23))
        refused = self.reveal(offers[0])
        self.assertEqual(refused.status_code, 429)
        self.assertAlmostEqual(int(refused['Retry-After']), 3600, delta=5)

    def test_reveals_older_than_24_hours_do_not_count(self):
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(1)
        self.reveal()
        ContactEvent.objects.update(created_at=timezone.now() - timedelta(hours=25))
        self.assertEqual(self.reveal(offers[0]).status_code, 201)

    def test_messages_do_not_use_the_reveal_quota(self):
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(2)
        services.create_contact_event(offer=offers[0], sender=self.buyer, message='Bonjour')
        self.assertEqual(self.reveal(offers[1]).status_code, 201)

    def test_new_account_has_the_lower_limit(self):
        User.objects.filter(pk=self.buyer.pk).update(date_joined=timezone.now() - timedelta(hours=2))
        self.buyer.refresh_from_db()
        offers = self.more_offers(4)
        for offer in offers[:3]:
            self.assertEqual(self.reveal(offer).status_code, 201)
        refused = self.reveal(offers[3])
        self.assertEqual((refused.status_code, refused.json()['code']), (429, 'reveal_quota_new_account'))
        self.assertIn('Retry-After', refused)

    def test_new_account_hours_come_from_the_settings(self):
        User.objects.filter(pk=self.buyer.pk).update(date_joined=timezone.now() - timedelta(hours=2))
        self.buyer.refresh_from_db()
        self.set_limits(new_account_hours=1, reveal_daily_limit_new_account=1, reveal_daily_limit_account=2)
        offers = self.more_offers(2)
        self.assertEqual(self.reveal(offers[0]).status_code, 201)
        self.assertEqual(self.reveal(offers[1]).status_code, 201)  # plus « neuf » au bout d'une heure

    def test_an_unverified_phone_counts_as_a_new_account(self):
        User.objects.filter(pk=self.buyer.pk).update(phone_verified=False)
        self.buyer.refresh_from_db()
        self.set_limits(reveal_daily_limit_new_account=1)
        offers = self.more_offers(1)
        self.assertEqual(self.reveal().status_code, 201)
        self.assertEqual(self.reveal(offers[0]).json()['code'], 'reveal_quota_new_account')

    def test_quota_refusals_are_audited_without_number(self):
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(1)
        self.reveal()
        self.reveal(offers[0])
        exceeded = AuditLog.objects.get(action='contact.reveal_quota_exceeded')  # une seule entrée par refus
        self.assertEqual((exceeded.actor, exceeded.target_type, exceeded.target_id), (self.buyer, 'user', self.buyer.pk))
        self.assertIn(str(offers[0].id), exceeded.details)
        self.assertNotIn('891111111', exceeded.details)
        self.assertFalse(AuditLog.objects.filter(action='contact.reveal_refused').exists())

    def test_quota_is_checked_before_consent_so_a_refusal_does_not_leak_who_consented(self):
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(1)
        self.reveal()
        ContactConsent.objects.filter(user=self.seller).update(is_granted=False)
        self.assertEqual(self.reveal(offers[0]).json()['code'], 'reveal_quota_account')

    def test_concurrent_request_that_passed_the_pre_check_is_refused_and_rolled_back(self):
        """Verrou après insertion : même si le contrôle préalable est contourné (rafale), le
        recomptage dans la transaction refuse et annule le contact (comme `reserve_daily_slot`)."""
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(1)
        self.reveal()
        with mock.patch.object(services, '_enforce_reveal_quota'):
            refused = self.reveal(offers[0])
        self.assertEqual((refused.status_code, refused.json()['code']), (429, 'reveal_quota_account'))
        self.assertIn('Retry-After', refused)
        self.assertEqual(ContactEvent.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type='marketplace.contact_revealed').count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='contact.number_revealed').count(), 1)
        offers[0].refresh_from_db()
        self.assertEqual(offers[0].contacts_count, 0)

    def test_failed_reveals_do_not_consume_the_quota(self):
        self.set_limits(reveal_daily_limit_account=1)
        ContactConsent.objects.filter(user=self.seller).update(is_granted=False)
        for _ in range(3):
            self.assertEqual(self.reveal().status_code, 403)
        ContactConsent.objects.filter(user=self.seller).update(is_granted=True)
        self.assertEqual(self.reveal().status_code, 201)

    def overrun_on_day(self, offer, days_ago):
        """Un dépassement de plafond, daté de `days_ago` jours (la dernière entrée d'audit est reculée)."""
        self.assertEqual(self.reveal(offer).status_code, 429)
        AuditLog.objects.filter(action='contact.reveal_quota_exceeded').order_by('-created_at').first()
        entry = AuditLog.objects.filter(action='contact.reveal_quota_exceeded').order_by('-created_at').first()
        AuditLog.objects.filter(pk=entry.pk).update(created_at=timezone.now() - timedelta(days=days_ago))

    def test_overruns_on_three_distinct_days_file_an_automatic_report(self):
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(1)
        self.reveal()
        self.overrun_on_day(offers[0], 2)
        self.overrun_on_day(offers[0], 1)
        self.assertEqual(Report.objects.count(), 0)
        self.assertEqual(self.reveal(offers[0]).status_code, 429)  # troisième jour (aujourd'hui)
        report = Report.objects.get()
        self.assertEqual((report.target_type, report.target_id, report.reporter), ('user', self.buyer.pk, None))
        self.assertEqual(report.reason, Report.REASON_SPAM)
        self.assertNotIn('891111111', report.description)
        self.reveal(offers[0])  # signalement encore ouvert : pas de doublon
        self.assertEqual(Report.objects.count(), 1)

    def test_a_burst_on_a_single_day_is_not_an_abuse(self):
        """Faux positif écarté : de nombreux refus le même jour (double-clics) ne font qu'un jour."""
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(1)
        self.reveal()
        for _ in range(6):
            self.assertEqual(self.reveal(offers[0]).status_code, 429)
        self.assertEqual(Report.objects.count(), 0)
        self.assertEqual(AuditLog.objects.filter(action='contact.reveal_quota_exceeded').count(), 6)

    def test_after_the_report_is_closed_new_overruns_file_a_new_one(self):
        self.set_limits(reveal_daily_limit_account=1, reveal_abuse_threshold=1)
        offers = self.more_offers(1)
        self.reveal()
        self.reveal(offers[0])
        report = Report.objects.get()
        report.resolve('Traité')
        self.reveal(offers[0])
        self.assertEqual(Report.objects.filter(target_type='user').count(), 2)
        self.assertEqual(Report.objects.filter(status__in=Report.OPEN_STATUSES).count(), 1)

    def test_automatic_report_only_open_leaves_reviews_behaviour_unchanged(self):
        target = self.buyer.pk
        first = moderation_services.file_automatic_report('user', target, Report.REASON_SPAM, 'x', only_open=True)
        self.assertIsNotNone(first)
        self.assertIsNone(moderation_services.file_automatic_report('user', target, Report.REASON_SPAM, 'x', only_open=True))
        first.reject('ok')
        # Sans only_open (avis croisés) : un signalement clos bloque toujours le suivant.
        self.assertIsNone(moderation_services.file_automatic_report('user', target, Report.REASON_SPAM, 'x'))
        self.assertIsNotNone(moderation_services.file_automatic_report('user', target, Report.REASON_SPAM, 'x', only_open=True))

    def test_overruns_older_than_the_window_do_not_count_towards_a_report(self):
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(1)
        self.reveal()
        self.overrun_on_day(offers[0], 9)
        self.overrun_on_day(offers[0], 8)
        self.assertEqual(self.reveal(offers[0]).status_code, 429)
        self.assertEqual(Report.objects.count(), 0)

    def test_retry_after_after_insertion_ignores_the_contact_being_cancelled(self):
        self.set_limits(reveal_daily_limit_account=1)
        offers = self.more_offers(1)
        self.reveal()
        ContactEvent.objects.update(created_at=timezone.now() - timedelta(hours=23))
        with mock.patch.object(services, '_enforce_reveal_quota'):
            refused = self.reveal(offers[0])
        self.assertEqual(refused.status_code, 429)
        self.assertAlmostEqual(int(refused['Retry-After']), 3600, delta=5)  # et non ~86400


class RevealConcurrencyTests(RevealTestBase):
    def test_the_visitor_is_locked_before_the_duplicate_and_quota_are_read(self):
        calls = []
        real_find = services._find_recent_reveal
        with mock.patch.object(services, '_lock_visitor', side_effect=lambda user: calls.append(('lock', user.pk))), \
                mock.patch.object(services, '_find_recent_reveal', side_effect=lambda *a, **k: (calls.append('find'), real_find(*a, **k))[1]):
            self.assertEqual(self.reveal().status_code, 201)
        self.assertEqual(calls, ['find', ('lock', self.buyer.pk), 'find'])  # le dernier `find` suit le verrou

    def test_lock_helper_is_harmless_in_a_transaction(self):
        from django.db import transaction
        with transaction.atomic():
            services._lock_visitor(self.buyer)

    def test_sqlite_locked_error_without_a_duplicate_is_a_clean_409(self):
        from django.db import OperationalError
        with mock.patch.object(services, '_lock_visitor', side_effect=OperationalError('database is locked')):
            response = self.reveal()
        self.assertEqual((response.status_code, response.json()['code']), (409, 'reveal_in_progress'))
        self.assertTrue(int(response['Retry-After']) >= 1)
        self.assertEqual(ContactEvent.objects.count(), 0)
        self.assertNotIn('891111111', response.content.decode())

    def test_sqlite_locked_error_with_a_duplicate_replays_the_contact(self):
        from django.db import OperationalError
        first = self.reveal()
        with mock.patch.object(services, '_lock_visitor', side_effect=OperationalError('database is locked')):
            response = self.reveal()
        self.assertEqual((response.status_code, response.json()['created']), (200, False))
        self.assertEqual(response.json()['contact_event_id'], first.json()['contact_event_id'])
        self.assertEqual(ContactEvent.objects.count(), 1)

    def test_other_operational_errors_are_not_swallowed(self):
        from django.db import OperationalError
        with mock.patch.object(services, '_lock_visitor', side_effect=OperationalError('disk I/O error')):
            with self.assertRaises(OperationalError):
                self.reveal()

    def test_a_duplicate_that_appears_after_insertion_cancels_the_newest(self):
        earlier = ContactEvent.objects.create(
            offer=self.offer, sender=self.buyer, channel='CALL', is_counted=True,
        )
        # Les deux relectures « avant insertion » ratent le doublon (course) ; le filet le retrouve.
        with mock.patch.object(services, '_find_recent_reveal', side_effect=[None, None]):
            response = self.reveal()
        self.assertEqual((response.status_code, response.json()['created']), (200, False))
        self.assertEqual(response.json()['contact_event_id'], str(earlier.pk))
        self.assertEqual(ContactEvent.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type='marketplace.contact_revealed').count(), 0)


class ReadOnlyChannelAndLooseOfferTests(RevealTestBase):
    def test_contact_list_exposes_the_channel_read_only(self):
        self.reveal(channel='WHATSAPP')
        rows = self.client.get(CONTACTS_URL).json()
        rows = rows['results'] if isinstance(rows, dict) else rows
        self.assertEqual([r['channel'] for r in rows], ['WHATSAPP'])
        self.assertNotIn('891111111', str(rows))
        created = self.client.post(
            CONTACTS_URL, {'post': str(self.offer.id), 'message': 'Bonjour', 'channel': 'CALL'}, format='json',
        )
        self.assertEqual((created.status_code, created.json()['channel']), (201, 'MESSAGE'))

    def test_a_very_long_offer_identifier_is_still_the_uniform_404(self):
        response = self.client.post(REVEAL_URL, {'offer': 'x' * 500, 'channel': 'CALL'}, format='json')
        self.assertEqual((response.status_code, response.json()['code']), (404, 'offer_not_found'))


@override_settings(CACHES=LOCMEM_CACHE)
class RevealIpThrottleTests(RevealTestBase):
    """Les tests utilisent un cache factice : les throttles exigent un cache mémoire."""

    def test_ip_throttle_is_a_429_with_its_own_code_and_retry_after(self):
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'contact_reveal_ip': '2/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            self.assertEqual(self.reveal().status_code, 201)
            self.assertEqual(self.reveal(channel='WHATSAPP').status_code, 201)
            refused = self.reveal()
            # Un autre compte, derrière la même IP, partage la limite.
            self.client.force_authenticate(self.seller)
            other = self.reveal()
        for response in (refused, other):
            self.assertEqual((response.status_code, response.json()['code']), (429, 'reveal_quota_ip'))
            self.assertTrue(int(response['Retry-After']) > 0)
        self.assertNotIn('891111111', refused.content.decode())

    def test_ip_throttle_uses_the_forwarded_address_when_a_proxy_is_trusted(self):
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'contact_reveal_ip': '1/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates), \
                mock.patch('rest_framework.settings.api_settings.NUM_PROXIES', 1):
            first = self.reveal(HTTP_X_FORWARDED_FOR='203.0.113.7')
            same_ip = self.reveal(HTTP_X_FORWARDED_FOR='203.0.113.7')
            other_ip = self.reveal(HTTP_X_FORWARDED_FOR='203.0.113.8')
        self.assertEqual((first.status_code, same_ip.status_code, other_ip.status_code), (201, 429, 200))

    def test_ipv6_addresses_of_the_same_64_prefix_share_the_limit(self):
        from apps.common.throttles import normalize_ip
        self.assertEqual(normalize_ip('2001:db8:1:2:aaaa:bbbb:cccc:dddd'), '2001:db8:1:2::/64')
        self.assertEqual(normalize_ip('2001:db8:1:2:1::1'), normalize_ip('2001:db8:1:2:ffff::2'))
        self.assertNotEqual(normalize_ip('2001:db8:1:3::1'), normalize_ip('2001:db8:1:2::1'))
        self.assertEqual(normalize_ip('203.0.113.7'), '203.0.113.7')
        self.assertEqual(normalize_ip('pas-une-ip'), 'pas-une-ip')
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'contact_reveal_ip': '1/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates), \
                mock.patch('rest_framework.settings.api_settings.NUM_PROXIES', 1):
            first = self.reveal(HTTP_X_FORWARDED_FOR='2001:db8:1:2::1')
            same_prefix = self.reveal(HTTP_X_FORWARDED_FOR='2001:db8:1:2:dead:beef:0:9')
            other_prefix = self.reveal(HTTP_X_FORWARDED_FOR='2001:db8:1:3::1')
        self.assertEqual((first.status_code, same_prefix.status_code, other_prefix.status_code), (201, 429, 200))

    def test_no_ip_is_written_to_the_database(self):
        self.reveal(HTTP_X_FORWARDED_FOR='203.0.113.7', REMOTE_ADDR='198.51.100.9')
        rows = list(AuditLog.objects.values_list('details', flat=True)) + [str(e.payload) for e in OutboxEvent.objects.all()]
        for text in rows:
            self.assertNotIn('203.0.113', text)
            self.assertNotIn('198.51.100', text)


class ReceivedRevealsTests(RevealTestBase):
    def test_the_seller_sees_who_asked_without_number_or_identifier(self):
        self.reveal()
        self.reveal(channel='WHATSAPP')
        self.client.force_authenticate(self.seller)
        response = self.client.get(RECEIVED_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        body = response.json()
        self.assertEqual((body['count'], body['next'], body['previous']), (2, None, None))
        first = body['results'][0]
        self.assertEqual(set(first), {'id', 'channel', 'created_at', 'requester_display_name', 'offer'})
        self.assertEqual(first['requester_display_name'], 'Marie K.')
        self.assertEqual(first['offer'], {'id': str(self.offer.id), 'title': self.offer.title})
        self.assertEqual([r['channel'] for r in body['results']], ['WHATSAPP', 'CALL'])
        text = response.content.decode()
        for forbidden in (str(self.buyer.pk), self.buyer.email, '891111111', 'Kabongo', SELLER_NUMBER):
            self.assertNotIn(forbidden, text)

    def test_channel_filter_and_invalid_channel(self):
        self.reveal()
        self.reveal(channel='WHATSAPP')
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.get(RECEIVED_URL, {'channel': 'CALL'}).json()['count'], 1)
        invalid = self.client.get(RECEIVED_URL, {'channel': 'MESSAGE'})
        self.assertEqual((invalid.status_code, invalid.json()['code']), (400, 'channel_invalid'))

    def test_messages_are_not_listed_and_other_sellers_see_nothing(self):
        services.create_contact_event(offer=self.offer, sender=self.buyer, message='Bonjour')
        self.client.force_authenticate(self.seller)
        self.assertEqual(self.client.get(RECEIVED_URL).json()['count'], 0)
        self.client.force_authenticate(self.buyer)
        self.reveal()
        self.assertEqual(self.client.get(RECEIVED_URL).json()['count'], 0)  # le visiteur ne voit pas les siennes ici

    def test_anonymous_is_refused(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(RECEIVED_URL).status_code, 401)

    def test_pagination(self):
        for offer in self.more_offers(3):
            self.reveal(offer)
        self.client.force_authenticate(self.seller)
        page = self.client.get(RECEIVED_URL, {'page_size': 2}).json()
        self.assertEqual((page['count'], len(page['results'])), (3, 2))
        self.assertIsNotNone(page['next'])

    def test_number_of_queries_does_not_grow_with_the_page(self):
        for offer in self.more_offers(2):
            self.reveal(offer)
        self.client.force_authenticate(self.seller)
        with CaptureQueriesContext(connection) as small:
            self.client.get(RECEIVED_URL)
        self.client.force_authenticate(self.buyer)
        for offer in self.more_offers(5):
            self.reveal(offer)
        self.client.force_authenticate(self.seller)
        with CaptureQueriesContext(connection) as large:
            self.client.get(RECEIVED_URL)
        self.assertEqual(len(small), len(large))


class MessageChannelTests(RevealTestBase):
    def test_message_is_refused_when_the_seller_disabled_it(self):
        identity_services.set_channel_consent(self.seller, 'MESSAGE', enabled=False)
        response = self.client.post(CONTACTS_URL, {'post': str(self.offer.id), 'message': 'Bonjour'}, format='json')
        self.assertEqual((response.status_code, response.json()['code']), (403, 'channel_not_allowed'))
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_message_duplicate_keeps_a_400_and_carries_a_code(self):
        payload = {'post': str(self.offer.id), 'message': 'Bonjour'}
        self.assertEqual(self.client.post(CONTACTS_URL, payload, format='json').status_code, 201)
        response = self.client.post(CONTACTS_URL, payload, format='json')
        self.assertEqual((response.status_code, response.json()['code']), (400, 'contact_duplicate'))
        self.assertIn('déjà contacté', response.json()['detail'])


class AbuseSettingsTests(RevealTestBase):
    def test_defaults_bounds_and_admin_columns(self):
        from django.contrib.admin.sites import site as admin_site
        from django.core.exceptions import ValidationError

        row = MarketplaceSettings.get_solo()
        self.assertEqual((row.reveal_abuse_threshold, row.reveal_abuse_window_days), (3, 7))
        for field, value in (('reveal_abuse_threshold', 0), ('reveal_abuse_threshold', 101),
                             ('reveal_abuse_window_days', 0), ('reveal_abuse_window_days', 91)):
            setattr(row, field, value)
            with self.assertRaises(ValidationError):
                row.full_clean()
            row.refresh_from_db()
        columns = admin_site._registry[MarketplaceSettings].list_display
        self.assertIn('reveal_abuse_threshold', columns)
        self.assertIn('reveal_abuse_window_days', columns)

    def test_threshold_comes_from_the_settings(self):
        self.set_limits(reveal_daily_limit_account=1, reveal_abuse_threshold=1)
        offers = self.more_offers(1)
        self.reveal()
        self.reveal(offers[0])
        self.assertEqual(Report.objects.filter(target_type='user').count(), 1)
