"""Socle des invitations d'organisation (L1-01-B2a, ADR 0008 §4, §6, §8.3, §10) : modèle, contraintes, migrations,
réglages, commande `expire_invitations`, catalogue d'événements, throttles. Les services et les vues (B2b) sont
testés dans `tests_invitations.py`."""
import hashlib
import io
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.checks import run_checks
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from apps.moderation.models import AuditLog
from apps.platform_core import catalog, registry
from apps.platform_core.models import OutboxEvent

from . import throttles
from .models import INVITABLE_ROLES, IdentitySettings, Organization, OrganizationInvitation
from .tests_admin import make_admin_user

User = get_user_model()
SENTINEL_LABEL = 'Etiquette-Sentinelle-Marie'


def make_invitation(organization, token='tok', role='EDITOR', status=OrganizationInvitation.STATUS_PENDING, **extra):
    extra.setdefault('expires_at', timezone.now() + timedelta(days=7))
    return OrganizationInvitation.objects.create(
        organization=organization, role=role, status=status,
        token_hash=hashlib.sha256(token.encode()).hexdigest(), **extra,
    )


class InvitationModelTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Org', org_type='ENTREPRISE')

    def test_defaults_and_uuid_key(self):
        invitation = make_invitation(self.organization, label='Jean, comptable')
        self.assertEqual(invitation.status, 'PENDING')
        self.assertEqual(len(str(invitation.pk)), 36)
        self.assertIsNone(invitation.closed_at)
        self.assertIsNone(invitation.closed_by)

    def test_invitable_roles_are_editor_and_analyst_only(self):
        self.assertEqual(INVITABLE_ROLES, ('EDITOR', 'ANALYST'))

    def test_owner_role_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_invitation(self.organization, token='o', role='OWNER')

    def test_admin_role_is_not_refused_by_the_database(self):
        # Interdit en service (INVITABLE_ROLES), pas en base : l'assouplir ne demande aucune migration.
        make_invitation(self.organization, token='a', role='ADMIN')

    def test_token_hash_is_unique(self):
        make_invitation(self.organization, token='same')
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_invitation(self.organization, token='same')

    def test_no_conditional_unique_constraint_and_named_indexes(self):
        meta = OrganizationInvitation._meta
        # Contraintes inconditionnelles seulement ; `orginv_scope_consistent` : périmètre (ADR 0010 §4.3, L1-01-B6).
        self.assertEqual([c.name for c in meta.constraints], ['orginv_role_not_owner', 'orginv_scope_consistent'])
        self.assertEqual(
            sorted(i.name for i in meta.indexes), ['orginv_created_by', 'orginv_org_status', 'orginv_status_expires'],
        )
        # Plusieurs invitations en attente pour un même rôle : aucune unicité par cible.
        make_invitation(self.organization, token='1')
        make_invitation(self.organization, token='2')

    def test_explicit_lengths(self):
        meta = OrganizationInvitation._meta
        self.assertEqual(meta.get_field('token_hash').max_length, 64)
        self.assertEqual(meta.get_field('label').max_length, 60)
        self.assertEqual(meta.get_field('status').max_length, 10)
        self.assertEqual(meta.get_field('role').max_length, 20)

    def test_deleting_the_organization_deletes_its_invitations(self):
        make_invitation(self.organization)
        self.organization.delete()
        self.assertEqual(OrganizationInvitation.objects.count(), 0)

    def test_deleting_a_user_keeps_the_invitation_with_null_author(self):
        user = User.objects.create_user(email='a@example.com', password='x')
        invitation = make_invitation(self.organization, created_by=user, closed_by=user)
        user.delete()
        invitation.refresh_from_db()
        self.assertIsNone(invitation.created_by)
        self.assertIsNone(invitation.closed_by)


class InvitationSettingsTests(TestCase):
    def admin_data(self, row, **extra):
        data = {
            'max_organizations_per_account': row.max_organizations_per_account,
            'max_categories_per_context': row.max_categories_per_context,
            'kyb_file_retention_days': row.kyb_file_retention_days,
            'invitation_ttl_days': 7, 'max_pending_invitations': 20, 'invitation_history_days': 30,
        }
        data.update(extra)
        return data

    def test_defaults(self):
        row = IdentitySettings.get_solo()
        self.assertEqual((row.invitation_ttl_days, row.max_pending_invitations, row.invitation_history_days), (7, 20, 30))

    def test_bounds(self):
        cases = {
            'invitation_ttl_days': (1, 30), 'max_pending_invitations': (1, 200), 'invitation_history_days': (1, 365),
        }
        for field, (low, high) in cases.items():
            for value, valid in ((low - 1, False), (low, True), (high, True), (high + 1, False)):
                row = IdentitySettings.get_solo()
                setattr(row, field, value)
                if valid:
                    row.full_clean()
                else:
                    with self.assertRaises(ValidationError, msg=f'{field}={value}'):
                        row.full_clean()

    def test_admin_change_is_journaled(self):
        staff = make_admin_user('inv-adm@example.com', perms=['view_identitysettings', 'change_identitysettings'])
        row = IdentitySettings.get_solo()
        self.client.force_login(staff)
        url = reverse('admin:identity_identitysettings_change', args=[row.pk])
        response = self.client.post(url, self.admin_data(row, invitation_ttl_days=14))
        self.assertEqual(response.status_code, 302)
        entry = AuditLog.objects.get(action='SETTINGS_CHANGED', actor=staff)
        self.assertIn('invitation_ttl_days', entry.details)
        self.assertNotIn('max_pending_invitations', entry.details)

    def test_out_of_bounds_value_is_refused_by_the_admin(self):
        staff = make_admin_user('inv-adm2@example.com', perms=['view_identitysettings', 'change_identitysettings'])
        row = IdentitySettings.get_solo()
        self.client.force_login(staff)
        url = reverse('admin:identity_identitysettings_change', args=[row.pk])
        response = self.client.post(url, self.admin_data(row, invitation_ttl_days=31))
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.invitation_ttl_days, 7)


class InvitationAdminTests(TestCase):
    def test_admin_is_read_only_and_hides_token_hash_and_label(self):
        organization = Organization.objects.create(name='Org', org_type='ENTREPRISE')
        invitation = make_invitation(organization, label=SENTINEL_LABEL)
        staff = make_admin_user(
            'inv-adm3@example.com', perms=['view_organizationinvitation', 'change_organizationinvitation'],
        )
        self.client.force_login(staff)
        response = self.client.get(reverse('admin:identity_organizationinvitation_change', args=[invitation.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, SENTINEL_LABEL)
        self.assertNotContains(response, invitation.token_hash)
        listing = self.client.get(reverse('admin:identity_organizationinvitation_changelist'))
        self.assertNotContains(listing, SENTINEL_LABEL)
        self.assertEqual(self.client.get(reverse('admin:identity_organizationinvitation_add')).status_code, 403)

    def test_change_and_delete_posts_are_refused_and_change_nothing(self):
        organization = Organization.objects.create(name='Org', org_type='ENTREPRISE')
        invitation = make_invitation(organization, label=SENTINEL_LABEL)
        staff = make_admin_user(
            'inv-adm4@example.com',
            perms=['view_organizationinvitation', 'change_organizationinvitation', 'delete_organizationinvitation'],
        )
        self.client.force_login(staff)
        change_url = reverse('admin:identity_organizationinvitation_change', args=[invitation.pk])
        response = self.client.post(change_url, {'role': 'ANALYST', 'status': 'REVOKED'})
        self.assertIn(response.status_code, (302, 403))
        delete_url = reverse('admin:identity_organizationinvitation_delete', args=[invitation.pk])
        self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)
        invitation.refresh_from_db()
        self.assertEqual((invitation.role, invitation.status, invitation.label), ('EDITOR', 'PENDING', SENTINEL_LABEL))
        # Action de masse « supprimer » : refusée aussi.
        self.client.post(
            reverse('admin:identity_organizationinvitation_changelist'),
            {'action': 'delete_selected', '_selected_action': [str(invitation.pk)], 'post': 'yes'},
        )
        self.assertTrue(OrganizationInvitation.objects.filter(pk=invitation.pk).exists())


class ExpireInvitationsCommandTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='Org', org_type='ENTREPRISE')

    def run_command(self):
        call_command('expire_invitations', verbosity=0, stdout=io.StringIO())

    def test_expires_due_pending_invitations_and_clears_the_label(self):
        now = timezone.now()
        due = make_invitation(self.organization, 'due', label=SENTINEL_LABEL, expires_at=now - timedelta(minutes=1))
        alive = make_invitation(self.organization, 'alive', label='garde', expires_at=now + timedelta(days=1))
        self.run_command()
        due.refresh_from_db()
        alive.refresh_from_db()
        self.assertEqual(due.status, 'EXPIRED')
        self.assertEqual(due.label, '')
        self.assertIsNotNone(due.closed_at)
        self.assertIsNone(due.closed_by)
        self.assertEqual((alive.status, alive.label), ('PENDING', 'garde'))

    def test_expiry_bumps_updated_at(self):
        due = make_invitation(self.organization, 'due', expires_at=timezone.now() - timedelta(minutes=1))
        before = due.updated_at
        self.run_command()
        due.refresh_from_db()
        self.assertGreater(due.updated_at, before)

    def test_other_closed_statuses_are_left_untouched_before_retention(self):
        past = timezone.now() - timedelta(days=1)
        rows = [
            make_invitation(self.organization, status=s, token=s, expires_at=past, closed_at=past)
            for s in ('ACCEPTED', 'DECLINED', 'REVOKED')
        ]
        self.run_command()
        for row in rows:
            row.refresh_from_db()
        self.assertEqual([r.status for r in rows], ['ACCEPTED', 'DECLINED', 'REVOKED'])

    def test_purges_closed_rows_older_than_the_history_setting(self):
        IdentitySettings.objects.update_or_create(pk=IdentitySettings.get_solo().pk, defaults={'invitation_history_days': 10})
        now = timezone.now()
        old = make_invitation(self.organization, 'old', status='REVOKED', closed_at=now - timedelta(days=11))
        recent = make_invitation(self.organization, 'recent', status='REVOKED', closed_at=now - timedelta(days=9))
        pending = make_invitation(self.organization, 'pend', expires_at=now + timedelta(days=1))
        OrganizationInvitation.objects.filter(pk=pending.pk).update(created_at=now - timedelta(days=400))
        self.run_command()
        remaining = set(OrganizationInvitation.objects.values_list('pk', flat=True))
        self.assertEqual(remaining, {recent.pk, pending.pk})
        self.assertNotIn(old.pk, remaining)

    def test_a_freshly_expired_row_is_not_purged_in_the_same_run(self):
        make_invitation(self.organization, 'due', expires_at=timezone.now() - timedelta(days=200))
        self.run_command()
        self.assertEqual(OrganizationInvitation.objects.filter(status='EXPIRED').count(), 1)

    def test_purge_handles_more_than_one_batch(self):
        old = timezone.now() - timedelta(days=400)
        OrganizationInvitation.objects.bulk_create([
            OrganizationInvitation(
                organization=self.organization, role='EDITOR', status='DECLINED', closed_at=old,
                token_hash=hashlib.sha256(str(n).encode()).hexdigest(), expires_at=old,
            ) for n in range(520)
        ])
        self.run_command()
        self.assertEqual(OrganizationInvitation.objects.count(), 0)

    def test_one_audit_trace_per_run_without_personal_data_and_none_when_nothing_expired(self):
        self.run_command()
        self.assertFalse(AuditLog.objects.filter(action='INVITATION_EXPIRED').exists())
        past = timezone.now() - timedelta(hours=1)
        make_invitation(self.organization, 'a', label=SENTINEL_LABEL, expires_at=past)
        make_invitation(self.organization, 'b', expires_at=past)
        self.run_command()
        entry = AuditLog.objects.get(action='INVITATION_EXPIRED')
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.details, 'count=2')

    def test_is_idempotent_and_emits_no_event(self):
        make_invitation(self.organization, 'a', expires_at=timezone.now() - timedelta(hours=1))
        self.run_command()
        self.run_command()
        self.assertEqual(AuditLog.objects.filter(action='INVITATION_EXPIRED').count(), 1)
        self.assertEqual(OutboxEvent.objects.count(), 0)


class InvitationEventCatalogTests(TestCase):
    def test_type_is_declared_in_v1_without_provisional_flags(self):
        spec = catalog.EVENT_TYPES['identity.organization_invitation_changed']
        self.assertEqual((spec.version, spec.domain), (1, 'identity'))
        # B2b : l'émetteur (services d'invitation) et l'abonné existent, les drapeaux provisoires sont retirés.
        self.assertFalse(spec.emitter_pending)
        self.assertFalse(spec.no_subscriber)
        self.assertTrue(registry.subscribers_for('identity.organization_invitation_changed'))

    def test_django_checks_stay_green(self):
        self.assertEqual([e for e in run_checks() if e.id.startswith('platform_core.')], [])


class InvitationThrottleTests(TestCase):
    def test_rates_are_declared(self):
        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        self.assertEqual(rates['invitation_create'], '20/hour')
        self.assertEqual(rates['invitation_create_org'], '50/day')
        self.assertEqual(rates['invitation_redeem'], '60/hour')
        self.assertEqual(rates['invitation_redeem_user'], '30/hour')

    def test_scopes(self):
        self.assertEqual(throttles.InvitationCreateThrottle.scope, 'invitation_create')
        self.assertEqual(throttles.InvitationCreateOrgThrottle.scope, 'invitation_create_org')
        self.assertEqual(throttles.InvitationRedeemIpThrottle.scope, 'invitation_redeem')
        self.assertEqual(throttles.InvitationRedeemUserThrottle.scope, 'invitation_redeem_user')

    def test_org_throttle_is_keyed_on_the_path_organization_and_only_counts_writes(self):
        throttle = throttles.InvitationCreateOrgThrottle()
        request = RequestFactory().post('/x/')
        view = type('V', (), {'kwargs': {'pk': 'ABC-1'}})()
        self.assertIn('abc-1', throttle.get_cache_key(request, view))
        self.assertIsNone(throttle.get_cache_key(request, type('V', (), {'kwargs': {}})()))
        self.assertTrue(throttle.allow_request(RequestFactory().get('/x/'), view))

    def test_user_throttle_ignores_anonymous_requests(self):
        request = RequestFactory().post('/x/')
        request.user = AnonymousUser()
        self.assertIsNone(throttles.InvitationRedeemUserThrottle().get_cache_key(request, None))

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'inv-throttle'}})
    def test_ip_throttle_blocks_after_the_rate(self):
        cache.clear()
        request = RequestFactory().post('/x/', REMOTE_ADDR='10.0.0.9')
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', {'invitation_redeem': '2/hour'}):
            allowed = [throttles.InvitationRedeemIpThrottle().allow_request(request, None) for _ in range(3)]
        self.assertEqual(allowed, [True, True, False])
        cache.clear()


class InvitationMigrationTests(TransactionTestCase):
    """Avant/arrière sur la base de test (le jeu complet de migrations y est déjà appliqué)."""

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([target])

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_0016_then_0015_are_reversible_and_forward_again(self):
        self.assertIn('identity_organizationinvitation', connection.introspection.table_names())
        self.migrate(('identity', '0015_organizationinvitation'))
        with connection.cursor() as cursor:
            columns = [c.name for c in connection.introspection.get_table_description(cursor, 'identity_identitysettings')]
        self.assertNotIn('invitation_ttl_days', columns)
        self.migrate(('identity', '0014_remove_user_user_type'))
        self.assertNotIn('identity_organizationinvitation', connection.introspection.table_names())
        self.migrate(('identity', '0016_identitysettings_invitations'))
        self.assertIn('identity_organizationinvitation', connection.introspection.table_names())
        self.assertEqual(IdentitySettings.get_solo().invitation_ttl_days, 7)
