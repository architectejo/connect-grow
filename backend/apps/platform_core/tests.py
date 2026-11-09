import ast
import importlib
import io
import os
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.common.tests import ALL_DOMAINS, APPS_DIR
from apps.moderation.models import AuditLog

from . import catalog, registry, services
from .catalog import EventType
from .models import OutboxDelivery, OutboxEvent
from .registry import PermanentEventError
from .testing import dispatch_outbox_now

User = get_user_model()
TYPE = 'platform_core.test_happened'
OTHER_TYPE = 'platform_core.test_other'


class OutboxTestMixin:
    """Enregistre des types et des abonnés de test, retirés en fin de test."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(catalog.EVENT_TYPES, {
            TYPE: EventType(TYPE), OTHER_TYPE: EventType(OTHER_TYPE, no_subscriber=True),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []
        self._names = []

    def subscribe(self, name, func=None, event_type=TYPE, **kwargs):
        def default(event):
            self.calls.append((name, event.payload))
        registry.subscribe(event_type, name=name, **kwargs)(func or default)
        self._names.append(name)
        self.addCleanup(registry.unregister, name)

    def publish(self, payload=None, event_type=TYPE):
        with transaction.atomic():
            return services.publish_event(
                event_type, aggregate_type='test', aggregate_id=uuid.uuid4(), payload=payload or {'n': 1},
            )


class PublishTests(OutboxTestMixin, TestCase):
    def test_event_and_one_delivery_per_subscriber_are_written(self):
        self.subscribe('platform_core.a')
        self.subscribe('platform_core.b')
        event_id = self.publish()
        event = OutboxEvent.objects.get(pk=event_id)
        self.assertEqual((event.status, event.version, event.payload), ('pending', 1, {'n': 1}))
        self.assertEqual(
            sorted(event.deliveries.values_list('handler', flat=True)), ['platform_core.a', 'platform_core.b'],
        )
        self.assertEqual(self.calls, [])  # publier n'appelle aucun abonné

    def test_event_without_subscriber_is_recorded_as_done(self):
        event = OutboxEvent.objects.get(pk=self.publish(event_type=OTHER_TYPE))
        self.assertEqual(event.status, 'done')
        self.assertIsNotNone(event.completed_at)
        self.assertFalse(event.deliveries.exists())

    def test_rollback_of_the_emitter_leaves_no_event_nor_delivery(self):
        self.subscribe('platform_core.a')
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                services.publish_event(TYPE, aggregate_type='t', aggregate_id=None, payload={})
                raise RuntimeError('échec après publication')
        self.assertEqual((OutboxEvent.objects.count(), OutboxDelivery.objects.count()), (0, 0))

    def test_invalid_publications_are_refused(self):
        def publish(event_type=TYPE, payload=None, **kwargs):
            with transaction.atomic():
                services.publish_event(event_type, aggregate_type='t', aggregate_id=None,
                                       payload={} if payload is None else payload, **kwargs)
        with self.assertRaises(services.OutboxError):
            publish(event_type='platform_core.inconnu')
        with self.assertRaises(services.OutboxError):
            publish(version=2)
        with self.assertRaises(services.OutboxError):
            publish(payload={'id': uuid.uuid4()})  # UUID non converti en chaîne
        with self.assertRaises(services.OutboxError):
            publish(payload={'texte': 'x' * 20000})
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_catalog_check_reports_unknown_and_unsubscribed_types(self):
        from .checks import check_event_catalog

        self.assertEqual([e.id for e in check_event_catalog(None)], ['platform_core.E002'])  # TYPE sans abonné
        self.subscribe('platform_core.a')
        self.assertEqual(check_event_catalog(None), [])
        self.subscribe('platform_core.ghost', event_type='platform_core.absent')
        self.assertEqual([e.id for e in check_event_catalog(None)], ['platform_core.E001'])

    def test_duplicate_subscriber_name_stops_startup(self):
        self.subscribe('platform_core.a')
        with self.assertRaises(RuntimeError):
            registry.subscribe(TYPE, name='platform_core.a')(lambda event: None)


class PublishOutsideTransactionTests(OutboxTestMixin, TransactionTestCase):
    def test_publication_outside_atomic_is_refused(self):
        with self.assertRaises(services.OutboxError):
            services.publish_event(TYPE, aggregate_type='t', aggregate_id=None, payload={})
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_inline_dispatch_runs_after_commit_only(self):
        self.subscribe('platform_core.a')
        with override_settings(OUTBOX_INLINE_DISPATCH=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    services.publish_event(TYPE, aggregate_type='t', aggregate_id=None, payload={'n': 1})
                    raise RuntimeError('annulé')
            self.assertEqual(self.calls, [])
            self.publish()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(OutboxEvent.objects.get().status, 'done')


class DispatchTests(OutboxTestMixin, TestCase):
    def delivery(self, handler='platform_core.a'):
        return OutboxDelivery.objects.get(handler=handler)

    def test_success_marks_delivery_and_event_done(self):
        self.subscribe('platform_core.a')
        self.publish()
        self.assertEqual(dispatch_outbox_now(), {'done': 1, 'failed': 0, 'skipped': 0})
        delivery = self.delivery()
        self.assertEqual((delivery.status, delivery.attempts), ('done', 1))
        self.assertIsNotNone(delivery.processed_at)
        event = OutboxEvent.objects.get()
        self.assertEqual(event.status, 'done')
        self.assertIsNotNone(event.completed_at)

    def test_replaying_dispatch_does_not_run_a_handler_twice(self):
        self.subscribe('platform_core.a')
        self.publish()
        dispatch_outbox_now()
        dispatch_outbox_now()
        self.assertEqual(len(self.calls), 1)

    def test_failure_is_retried_with_exponential_backoff_then_succeeds(self):
        state = {'fail': True}

        def flaky(event):
            if state['fail']:
                raise ValueError('secret=jean@example.com')
            self.calls.append(('ok', event.payload))
        self.subscribe('platform_core.a', flaky)
        self.publish()
        start = timezone.now()
        with mock.patch('apps.platform_core.services.timezone') as clock:
            clock.now.return_value = start
            dispatch_outbox_now()
            delivery = self.delivery()
            self.assertEqual((delivery.status, delivery.attempts), ('pending', 1))
            self.assertEqual(delivery.next_attempt_at, start + timedelta(seconds=30))
            self.assertNotIn('jean@example.com', delivery.last_error)  # aucune donnée personnelle
            self.assertIn('ValueError', delivery.last_error)
            self.assertEqual(OutboxEvent.objects.get().status, 'pending')

            dispatch_outbox_now()  # pas encore échue : rien ne se passe
            self.assertEqual(self.delivery().attempts, 1)

            clock.now.return_value = start + timedelta(seconds=31)
            dispatch_outbox_now()
            delivery = self.delivery()
            self.assertEqual(delivery.attempts, 2)
            self.assertEqual(delivery.next_attempt_at, start + timedelta(seconds=31 + 60))

            state['fail'] = False
            clock.now.return_value = start + timedelta(seconds=200)
            dispatch_outbox_now()
        self.assertEqual(self.delivery().status, 'done')
        self.assertEqual(self.calls, [('ok', {'n': 1})])

    def test_backoff_is_capped(self):
        with override_settings(OUTBOX_BACKOFF_MAX_SECONDS=3600):
            self.assertEqual(services._backoff(20), timedelta(hours=1))

    def test_delivery_becomes_dead_after_the_maximum_attempts(self):
        def boom(event):
            raise ValueError('x')
        self.subscribe('platform_core.a', boom)
        self.publish()
        with override_settings(OUTBOX_MAX_ATTEMPTS=3):
            for _ in range(3):
                OutboxDelivery.objects.update(next_attempt_at=timezone.now())
                dispatch_outbox_now()
        delivery = self.delivery()
        self.assertEqual((delivery.status, delivery.attempts), ('dead', 3))
        self.assertEqual(OutboxEvent.objects.get().status, 'dead')
        OutboxDelivery.objects.update(next_attempt_at=timezone.now())
        self.assertEqual(dispatch_outbox_now()['done'], 0)  # un échec définitif n'est plus rejoué

    def test_permanent_error_is_dead_at_once(self):
        def refuse(event):
            raise PermanentEventError('charge invalide')
        self.subscribe('platform_core.a', refuse)
        self.publish()
        dispatch_outbox_now()
        delivery = self.delivery()
        self.assertEqual((delivery.status, delivery.attempts), ('dead', 1))
        self.assertIn('charge invalide', delivery.last_error)

    def test_unknown_handler_and_unsupported_version_are_dead(self):
        self.subscribe('platform_core.a', versions=(2,))
        self.subscribe('platform_core.gone')
        self.publish()
        registry.unregister('platform_core.gone')
        dispatch_outbox_now()
        self.assertEqual(self.delivery().status, 'dead')
        self.assertIn('version 1', self.delivery().last_error)
        self.assertEqual(self.delivery('platform_core.gone').status, 'dead')
        self.assertIn('handler inconnu', self.delivery('platform_core.gone').last_error)

    def test_stale_processing_delivery_is_taken_over(self):
        self.subscribe('platform_core.a')
        self.publish()
        stale = timezone.now() - timedelta(minutes=6)
        OutboxDelivery.objects.update(status='processing', locked_at=stale, locked_by='mort', attempts=1)
        dispatch_outbox_now()
        delivery = self.delivery()
        self.assertEqual((delivery.status, delivery.attempts), ('done', 2))
        self.assertEqual(len(self.calls), 1)

    def test_recent_processing_delivery_is_left_alone(self):
        self.subscribe('platform_core.a')
        self.publish()
        OutboxDelivery.objects.update(status='processing', locked_at=timezone.now(), locked_by='vivant')
        dispatch_outbox_now()
        self.assertEqual(self.calls, [])

    def test_second_concurrent_claim_is_refused(self):
        self.subscribe('platform_core.a')
        self.publish()
        delivery = self.delivery()
        now = timezone.now()
        first = services._claim(delivery.pk, 'pending', '', now)
        second = services._claim(delivery.pk, 'pending', '', now)
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(self.delivery().attempts, 1)

    def test_delivery_retried_in_the_meantime_is_not_claimed_from_a_stale_read(self):
        self.subscribe('platform_core.a')
        self.publish()
        delivery = self.delivery()
        OutboxDelivery.objects.update(next_attempt_at=timezone.now() + timedelta(minutes=5))
        self.assertIsNone(services._claim(delivery.pk, 'pending', '', timezone.now()))

    def test_lost_lock_cancels_the_handler_writes(self):
        def thief(event):
            OutboxEvent.objects.create(event_type='effet', aggregate_type='x', payload={})
            OutboxDelivery.objects.update(locked_by='autre')  # une autre exécution a repris le verrou
        self.subscribe('platform_core.a', thief)
        self.publish()
        dispatch_outbox_now()
        self.assertFalse(OutboxEvent.objects.filter(event_type='effet').exists())
        delivery = self.delivery()
        self.assertEqual(delivery.status, 'pending')  # jamais marquée « traitée » sans le verrou
        self.assertIn('verrou perdu', delivery.last_error)

    def test_failing_subscriber_neither_blocks_nor_replays_the_other(self):
        state = {'fail': True}

        def flaky(event):
            if state['fail']:
                raise ValueError('x')
        self.subscribe('platform_core.a')
        self.subscribe('platform_core.b', flaky)
        self.publish()
        dispatch_outbox_now()
        self.assertEqual((self.delivery().status, self.delivery('platform_core.b').status), ('done', 'pending'))
        self.assertEqual(OutboxEvent.objects.get().status, 'pending')
        state['fail'] = False
        OutboxDelivery.objects.update(next_attempt_at=timezone.now())
        dispatch_outbox_now()
        self.assertEqual(len(self.calls), 1)  # a n'a pas été rejoué
        self.assertEqual(OutboxEvent.objects.get().status, 'done')

    def test_events_are_delivered_in_creation_order(self):
        self.subscribe('platform_core.a')
        for n in range(3):
            self.publish({'n': n})
        dispatch_outbox_now()
        self.assertEqual([payload['n'] for _, payload in self.calls], [0, 1, 2])

    def test_limit_bounds_one_run(self):
        self.subscribe('platform_core.a')
        for n in range(3):
            self.publish({'n': n})
        self.assertEqual(services.dispatch_due(limit=2)['done'], 2)
        self.assertEqual(services.dispatch_due(limit=2)['done'], 1)


class CommandsAndAdminTests(OutboxTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(email='root@example.com', password='Motdepasse-Solide-1')
        self.subscribe('platform_core.a', lambda event: (_ for _ in ()).throw(PermanentEventError('non')))
        self.publish()
        dispatch_outbox_now()
        self.delivery = OutboxDelivery.objects.get()

    def test_stats_exit_code_signals_dead_deliveries(self):
        out = io.StringIO()
        with self.assertRaises(CommandError):
            call_command('dispatch_outbox', '--stats', stdout=out)
        self.assertIn('En échec définitif : 1', out.getvalue())
        OutboxDelivery.objects.update(status='done')
        call_command('dispatch_outbox', '--stats', stdout=out)  # pas d'erreur

    def test_command_dispatches_due_deliveries(self):
        self.subscribe('platform_core.b')
        self.publish()
        out = io.StringIO()
        call_command('dispatch_outbox', stdout=out)
        self.assertIn('1 livraison(s) traitée(s)', out.getvalue())

    def test_requeue_command_is_audited(self):
        call_command('dispatch_outbox', '--requeue', 'dead', stdout=io.StringIO())
        self.delivery.refresh_from_db()
        self.assertEqual((self.delivery.status, self.delivery.attempts, self.delivery.last_error), ('pending', 0, ''))
        entry = AuditLog.objects.get(action='OUTBOX_REQUEUED')
        self.assertEqual(entry.target_id, self.delivery.pk)
        self.assertNotIn('"n"', entry.details)  # la charge utile n'est pas journalisée
        with self.assertRaises(CommandError):
            call_command('dispatch_outbox', '--requeue', 'pas-un-uuid')

    def test_requeue_does_not_touch_a_processed_delivery(self):
        OutboxDelivery.objects.update(status='done')
        call_command('dispatch_outbox', '--requeue', str(self.delivery.pk), stdout=io.StringIO())
        self.assertEqual(OutboxDelivery.objects.get().status, 'done')
        self.assertFalse(AuditLog.objects.filter(action='OUTBOX_REQUEUED').exists())

    def test_admin_requeue_action_is_audited_and_restricted(self):
        from django.urls import reverse

        self.client.force_login(self.admin)
        url = reverse('admin:platform_core_outboxdelivery_changelist')
        response = self.client.post(url, {'action': 'requeue_selected', '_selected_action': [str(self.delivery.pk)]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OutboxDelivery.objects.get().status, 'pending')
        self.assertEqual(AuditLog.objects.get(action='OUTBOX_REQUEUED').actor, self.admin)

        staff = User.objects.create_user(email='staff@example.com', password='Motdepasse-Solide-1', is_staff=True)
        OutboxDelivery.objects.update(status='dead')
        self.client.force_login(staff)
        self.client.post(url, {'action': 'requeue_selected', '_selected_action': [str(self.delivery.pk)]})
        self.assertEqual(OutboxDelivery.objects.get().status, 'dead')

    def test_admin_is_read_only_and_hides_the_payload(self):
        from django.urls import reverse

        self.client.force_login(self.admin)
        url = reverse('admin:platform_core_outboxevent_change', args=[self.delivery.event_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="payload"')
        self.assertEqual(self.client.post(url, {'event_type': 'x'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:platform_core_outboxevent_add')).status_code, 403)


class CorrectionsTests(OutboxTestMixin, TestCase):
    """Corrections d'audit (aller-retour 1) : journaux, atomicité, statistiques, relance."""

    def test_logs_never_carry_the_exception_message_nor_a_traceback(self):
        def boom(event):
            raise ValueError('secret=jean@example.com')
        self.subscribe('platform_core.a', boom)
        self.publish()
        with self.assertLogs('apps.platform_core', level='DEBUG') as captured:
            dispatch_outbox_now()
        self.assertTrue(captured.records)
        for record in captured.records:
            self.assertIsNone(record.exc_info)
        text = ' '.join(captured.output) + ' '.join(r.getMessage() for r in captured.records)
        self.assertNotIn('secret', text)
        self.assertNotIn('jean@example.com', text)
        self.assertIn('ValueError', text)

    def test_inline_dispatch_failure_log_has_no_message_either(self):
        with mock.patch.object(services, '_run', side_effect=ValueError('secret')):
            with self.assertLogs('apps.platform_core', level='ERROR') as captured:
                services.dispatch_for_event(uuid.uuid4())
        self.assertNotIn('secret', ' '.join(captured.output))
        self.assertIsNone(captured.records[0].exc_info)

    def test_stats_use_a_grouped_query(self):
        self.subscribe('platform_core.a')
        self.publish()
        dispatch_outbox_now()
        with self.assertNumQueries(2):
            stats = services.get_stats()
        self.assertEqual(stats['counts'], {'pending': 0, 'processing': 0, 'done': 1, 'dead': 0})

    def test_event_status_follows_its_deliveries_with_conditional_updates(self):
        self.subscribe('platform_core.a')
        self.subscribe('platform_core.b')
        event_id = self.publish()
        OutboxDelivery.objects.filter(handler='platform_core.a').update(status='done')
        OutboxEvent.objects.filter(pk=event_id).update(status='done')  # état périmé : b est encore en attente
        with self.assertNumQueries(3):
            services._refresh_event_status(event_id)
        self.assertEqual(OutboxEvent.objects.get().status, 'pending')
        OutboxDelivery.objects.update(status='done')
        services._refresh_event_status(event_id)
        event = OutboxEvent.objects.get()
        self.assertEqual(event.status, 'done')
        self.assertIsNotNone(event.completed_at)
        OutboxDelivery.objects.filter(handler='platform_core.b').update(status='dead')
        services._refresh_event_status(event_id)
        self.assertEqual(OutboxEvent.objects.get().status, 'dead')
        OutboxDelivery.objects.filter(handler='platform_core.b').update(status='processing')
        services._refresh_event_status(event_id)
        self.assertEqual(OutboxEvent.objects.get().status, 'pending')

    def test_admin_requeue_touches_dead_deliveries_only(self):
        from django.urls import reverse

        self.subscribe('platform_core.a')
        self.subscribe('platform_core.b')
        self.publish()
        OutboxDelivery.objects.filter(handler='platform_core.a').update(status='dead', attempts=8)
        OutboxDelivery.objects.filter(handler='platform_core.b').update(status='pending', attempts=3)
        admin_user = User.objects.create_superuser(email='root@example.com', password='Motdepasse-Solide-1')
        self.client.force_login(admin_user)
        self.client.post(reverse('admin:platform_core_outboxdelivery_changelist'), {
            'action': 'requeue_selected',
            '_selected_action': [str(pk) for pk in OutboxDelivery.objects.values_list('pk', flat=True)],
        })
        self.assertEqual(OutboxDelivery.objects.get(handler='platform_core.a').attempts, 0)
        self.assertEqual(OutboxDelivery.objects.get(handler='platform_core.b').attempts, 3)  # intacte
        self.assertEqual(AuditLog.objects.filter(action='OUTBOX_REQUEUED').count(), 1)

    def test_command_requeue_is_audited_with_no_actor(self):
        self.subscribe('platform_core.a')
        self.publish()
        OutboxDelivery.objects.update(status='dead')
        call_command('dispatch_outbox', '--requeue', 'dead', stdout=io.StringIO())
        entry = AuditLog.objects.get(action='OUTBOX_REQUEUED')
        self.assertIsNone(entry.actor)
        self.assertIn('ligne de commande', entry.details)

    def test_requeue_and_its_audit_entry_succeed_or_fail_together(self):
        from .operations import requeue_and_audit

        self.subscribe('platform_core.a')
        self.publish()
        OutboxDelivery.objects.update(status='dead', attempts=8)
        with mock.patch('apps.platform_core.operations.record_audit', side_effect=RuntimeError('journal indisponible')):
            with self.assertRaises(RuntimeError):
                requeue_and_audit(None, OutboxDelivery.objects.all())
        delivery = OutboxDelivery.objects.get()
        self.assertEqual((delivery.status, delivery.attempts), ('dead', 8))

    def test_dead_events_are_kept_30_days_by_default(self):
        from django.conf import settings

        self.assertEqual(settings.OUTBOX_DEAD_RETENTION_DAYS, 30)
        self.assertEqual(settings.OUTBOX_RETENTION_DAYS, 7)

    def test_notification_handlers_reject_an_invalid_payload_definitively(self):
        from apps.notifications.models import Notification

        for event_type in ('marketplace.contact_recorded', 'marketplace.exchange_proposed',
                           'marketplace.offer_expiring_soon', 'reviews.review_posted', 'reviews.review_replied'):
            self.publish({'seulement': 'du bruit'}, event_type=event_type)
        self.publish({'seller_id': 'pas-un-uuid', 'sender_id': 'x', 'offer_title': 't'},
                     event_type='marketplace.contact_recorded')
        dispatch_outbox_now()
        notifications = OutboxDelivery.objects.filter(handler__startswith='notifications.')
        self.assertEqual(notifications.count(), 6)
        self.assertEqual(set(notifications.values_list('status', flat=True)), {'dead'})
        self.assertTrue(all('charge utile invalide' in d.last_error for d in notifications))
        self.assertTrue(all(d.attempts == 1 for d in notifications))
        self.assertFalse(Notification.objects.exists())


class PurgeTests(OutboxTestMixin, TestCase):
    def make(self, status, age_days):
        event = OutboxEvent.objects.create(
            event_type=TYPE, aggregate_type='t', status=status, payload={},
            completed_at=timezone.now() - timedelta(days=age_days),
        )
        OutboxDelivery.objects.create(event=event, handler='platform_core.a', status=status,
                                      next_attempt_at=timezone.now())
        return event

    def test_purge_respects_the_retention_per_status(self):
        old_done, recent_done = self.make('done', 8), self.make('done', 6)
        old_dead, recent_dead = self.make('dead', 31), self.make('dead', 29)
        pending = OutboxEvent.objects.create(event_type=TYPE, aggregate_type='t', payload={})
        out = io.StringIO()
        call_command('purge_outbox', stdout=out)
        remaining = set(OutboxEvent.objects.values_list('pk', flat=True))
        self.assertEqual(remaining, {recent_done.pk, recent_dead.pk, pending.pk})
        self.assertFalse(OutboxDelivery.objects.filter(event_id__in=[old_done.pk, old_dead.pk]).exists())
        self.assertIn('1 événement(s) traité(s) et 1 en échec', out.getvalue())

    def test_retention_is_a_setting(self):
        self.make('done', 2)
        with override_settings(OUTBOX_RETENTION_DAYS=1):
            self.assertEqual(services.purge()['done'], 1)


class BoundaryTests(SimpleTestCase):
    """ADR 0003, §4 : frontières de la plateforme d'événements."""

    @staticmethod
    def sources(label, only=None):
        base = os.path.join(APPS_DIR, label)
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ('migrations', '__pycache__')]
            for name in files:
                if name.endswith('.py') and not name.startswith('tests') and (only is None or name in only):
                    path = os.path.join(root, name)
                    with open(path, encoding='utf-8') as handle:
                        yield os.path.relpath(path, APPS_DIR).replace(os.sep, '/'), ast.parse(handle.read())

    @staticmethod
    def imported_modules(tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield alias.name
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                yield node.module
                for alias in node.names:
                    yield f'{node.module}.{alias.name}'

    def test_platform_core_only_reaches_other_domains_through_the_audit_service(self):
        offenders = []
        for path, tree in self.sources('platform_core'):
            for module in self.imported_modules(tree):
                parts = module.split('.')
                if len(parts) >= 2 and parts[0] == 'apps' and parts[1] in ALL_DOMAINS - {'platform_core'}:
                    if (parts[1], path) != ('moderation', 'platform_core/operations.py') or parts[2:3] != ['services']:
                        offenders.append(f'{path}: {module}')
        self.assertEqual(offenders, [])

    def test_events_modules_import_only_services_and_the_registry(self):
        offenders = []
        for label in sorted(ALL_DOMAINS):
            for path, tree in self.sources(label, only={'events.py'}):
                for module in self.imported_modules(tree):
                    parts = module.split('.')
                    if parts[0] != 'apps':
                        continue
                    allowed = (
                        parts[1:3] == ['platform_core', 'registry']
                        or parts[2:3] == ['services'] or parts[1:2] == ['common']
                        or module in {f'apps.{d}' for d in ALL_DOMAINS}  # « from apps.x import services »
                    )
                    if not allowed or parts[2:3] in (['models'], ['views']):
                        offenders.append(f'{path}: {module}')
        self.assertEqual(offenders, [])

    def published_types(self):
        """{type: [domaine émetteur]} d'après les appels publish_event à type littéral."""
        found = {}
        for label in sorted(ALL_DOMAINS):
            for path, tree in self.sources(label):
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call) and getattr(node.func, 'id', getattr(node.func, 'attr', None)) == 'publish_event'
                            and node.args and isinstance(node.args[0], ast.Constant)):
                        found.setdefault(node.args[0].value, []).append((label, path))
        found.pop('platform_core.test_happened', None)
        return found

    def test_every_catalog_type_has_an_emitter_of_its_own_domain_and_a_subscriber(self):
        published = self.published_types()
        for name, spec in catalog.EVENT_TYPES.items():
            emitters = published.get(name, [])
            if spec.emitter_pending:
                # Drapeau provisoire : il doit disparaître dès que l'émetteur existe.
                self.assertFalse(emitters, f'{name} : un émetteur existe, retirer le drapeau emitter_pending')
                continue
            self.assertTrue(emitters, f'{name} : aucun émetteur')
            self.assertEqual({label for label, _ in emitters}, {spec.domain}, name)
            if spec.no_subscriber:
                self.assertFalse(
                    registry.subscribers_for(name), f'{name} : un abonné existe, retirer le drapeau no_subscriber',
                )
            else:
                self.assertTrue(registry.subscribers_for(name), f'{name} : aucun abonné')
        self.assertEqual(set(published) - set(catalog.EVENT_TYPES), set(), 'type publié absent du catalogue')

    def test_subscribers_are_named_after_their_domain_and_listen_to_known_types(self):
        for subscriber in registry.all_subscribers():
            if subscriber.name.startswith('platform_core.'):
                continue
            self.assertIn(subscriber.event_type, catalog.EVENT_TYPES, subscriber.name)
            domain = subscriber.name.split('.', 1)[0]
            self.assertIn(domain, ALL_DOMAINS, subscriber.name)
            self.assertTrue(subscriber.func.__module__.startswith(f'apps.{domain}.'), subscriber.name)

    def test_the_app_label_does_not_shadow_the_standard_platform_module(self):
        module = importlib.import_module('platform')
        self.assertNotIn(os.path.normcase(APPS_DIR), os.path.normcase(os.path.dirname(module.__file__)))
        self.assertTrue(os.path.isdir(os.path.join(APPS_DIR, 'platform_core')))
        self.assertFalse(os.path.exists(os.path.join(APPS_DIR, 'platform')))
