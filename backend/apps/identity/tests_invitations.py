"""Invitations d'équipe par lien (L1-01-B2b, ADR 0008 §3 à §7, §11 ; contrat d'API L1-01 §2) : création, liste,
révocation, aperçu, acceptation, refus, balayage de l'inviteur, concurrence logique, neutralité des réponses,
absence de jeton ou d'étiquette dans l'audit, l'outbox, les notifications, les journaux et les clés de cache."""
import ast
import hashlib
import inspect
import json
import logging
import os
import re
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import SimpleRateThrottle

from apps.common.contexts import DENY_OBJECT_STATE, DENY_PERMISSION, DENY_RELATION, DENY_SECURITY
from apps.moderation.models import AuditLog, Sanction
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now

from . import capabilities, invitations, services, tests_team as team
from .models import IdentitySettings, Membership, Organization, OrganizationInvitation
from .tests_invitations_base import SENTINEL_LABEL, make_invitation
from .tests_route_guard import collect_unguarded_write_routes

OWNER, ADMIN, EDITOR, ANALYST = team.OWNER, team.ADMIN, team.EDITOR, team.ANALYST
ORGS = team.ORGS
BASE = '/api/v1/accounts/organization-invitations/'
INVITEE_NAME = 'Zephyrine Invitee-Sentinelle'
INVITER_NAME = 'Balthazar Inviteur-Sentinelle'
TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')
INVITATION_KEYS = {
    'invitation_id', 'role', 'status', 'label', 'created_at', 'expires_at', 'created_by_display_name', 'is_mine',
    # Invitations v2 (contrat §7.4)
    'scope', 'requires_confirmation', 'accepted_at', 'confirmation_expires_at', 'accepted_by_display_name',
    'accepted_by_phone_hint', 'can_confirm',
}
CREATED_KEYS = {
    'invitation_id', 'role', 'status', 'label', 'created_at', 'expires_at', 'link_token', 'scope',
    'requires_confirmation',
}
ORG_SCOPE = {'type': 'ORGANIZATION', 'id': None}
INVALID = {'detail': "Cette invitation n'est pas valide.", 'code': 'invitation_invalid'}


def url_invitations(org):
    return f'{ORGS}{org.pk}/invitations/'


def url_invitation(org, invitation_id):
    return f'{ORGS}{org.pk}/invitations/{invitation_id}/'


def set_settings(**values):
    IdentitySettings.objects.update_or_create(pk=IdentitySettings.get_solo().pk, defaults=values)


class InvBase(team.TeamBase):
    def setUp(self):
        super().setUp()
        self.invitee = team.make_user('invitee', full_name=INVITEE_NAME)
        self.invitee_client = team.login(self.invitee)

    # --- Aides -----------------------------------------------------------------------------------------------------
    def create(self, role=OWNER, invite_role=EDITOR, label='', org=None):
        return self.as_role(role).post(
            url_invitations(org or self.org), {'role': invite_role, 'label': label}, format='json',
        )

    def make(self, role=OWNER, invite_role=EDITOR, label='', org=None):
        """Crée une invitation par l'API : `(ligne, jeton)`."""
        response = self.create(role, invite_role, label, org)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        return OrganizationInvitation.objects.get(pk=body['invitation_id']), body['link_token']

    def call(self, action, token, client=None):
        return (client or self.invitee_client).post(f'{BASE}{action}/', {'token': token}, format='json')

    def accept(self, token, client=None):
        return self.call('accept', token, client)

    def decline(self, token, client=None):
        return self.call('decline', token, client)

    def preview(self, token, client=None):
        return self.call('preview', token, client)

    def fresh(self, invitation):
        return OrganizationInvitation.objects.get(pk=invitation.pk)

    def deliver(self):
        dispatch_outbox_now()

    def audit(self, action, **filters):
        return AuditLog.objects.filter(action=action, **filters)

    def fresh_org(self, name='Autre organisation'):
        org = Organization.objects.create(name=name, org_type='ENTREPRISE')
        owner, owner_membership = self.add('o-owner', OWNER, org=org)
        return org, owner, owner_membership


# --- Création ---------------------------------------------------------------------------------------------------

class CreateInvitationTests(InvBase):
    def test_owner_creates_an_invitation_with_exact_keys_and_a_single_use_token(self):
        response = self.create(label='  Jean, comptable  ')
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(set(body), CREATED_KEYS)
        self.assertRegex(body['link_token'], TOKEN_RE)
        self.assertEqual((body['role'], body['status'], body['label']), (EDITOR, 'PENDING', 'Jean, comptable'))
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        invitation = OrganizationInvitation.objects.get(pk=body['invitation_id'])
        self.assertEqual(invitation.token_hash, hashlib.sha256(body['link_token'].encode()).hexdigest())
        self.assertEqual(invitation.created_by, self.owner)
        stored = ' '.join(str(v) for v in OrganizationInvitation.objects.values().get(pk=invitation.pk).values())
        self.assertNotIn(body['link_token'], stored)

    def test_the_token_is_never_returned_again(self):
        invitation, token = self.make()
        listing = self.as_role(OWNER).get(url_invitations(self.org))
        self.assertNotIn(token, listing.content.decode())
        self.assertNotIn(invitation.token_hash, listing.content.decode())
        self.assertNotIn('link_token', listing.content.decode())

    def test_admin_may_invite_and_expiry_follows_the_setting(self):
        set_settings(invitation_ttl_days=3)
        before = timezone.now()
        invitation, _ = self.make(role=ADMIN, invite_role=ANALYST)
        self.assertEqual(invitation.role, ANALYST)
        self.assertAlmostEqual(
            (invitation.expires_at - before).total_seconds(), 3 * 86400, delta=60,
        )

    def test_owner_role_is_refused_but_admin_and_member_are_invitable(self):
        """Invitations v2 (ADR 0010 D4) : inversion du test qui refusait ADMIN (et MEMBER, B6) ; OWNER jamais."""
        self.assertDenied(self.create(invite_role=OWNER), 'invitation_role_not_allowed', 400)
        self.assertFalse(OrganizationInvitation.objects.exists())
        for role, confirmation in ((ADMIN, True), ('MEMBER', False), (EDITOR, False), (ANALYST, False)):
            with self.subTest(role=role):
                response = self.create(invite_role=role)
                self.assertEqual(response.status_code, 201, response.content)
                body = response.json()
                self.assertEqual(
                    (body['role'], body['requires_confirmation'], body['scope']), (role, confirmation, ORG_SCOPE),
                )

    def test_invalid_role_and_label(self):
        client = self.as_role(OWNER)
        for body in ({}, {'role': 'DIRECTEUR'}, {'role': 7}, {'role': None}):
            with self.subTest(body=body):
                response = client.post(url_invitations(self.org), body, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('role', response.json())
        for label in ('x' * 61, 12, ['a'], 'a\x00b'):
            with self.subTest(label=label):
                response = client.post(url_invitations(self.org), {'role': EDITOR, 'label': label}, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('label', response.json())
        ok = client.post(url_invitations(self.org), {'role': EDITOR, 'label': 'x' * 60}, format='json')
        self.assertEqual(ok.status_code, 201)

    def test_label_is_optional(self):
        response = self.as_role(OWNER).post(url_invitations(self.org), {'role': ANALYST}, format='json')
        self.assertEqual((response.status_code, response.json()['label']), (201, ''))

    def test_permissions_by_role_and_state(self):
        for role in (EDITOR, ANALYST):
            self.assertDenied(self.create(role), DENY_PERMISSION)
        stranger = team.login(team.make_user('stranger'))
        response = stranger.post(url_invitations(self.org), {'role': EDITOR}, format='json')
        self.assertDenied(response, DENY_RELATION)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertDenied(self.create(), DENY_SECURITY)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ARCHIVED)
        self.assertDenied(self.create(), DENY_OBJECT_STATE)
        self.assertFalse(OrganizationInvitation.objects.exists())

    def test_restricted_account_is_refused(self):
        Sanction.objects.create(
            user=self.owner, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.users[ADMIN],
        ).apply()
        self.assertDenied(self.create(), DENY_SECURITY)

    def test_unknown_organization_answers_like_a_non_member(self):
        import uuid
        response = self.as_role(OWNER).post(
            f'{ORGS}{uuid.uuid4()}/invitations/', {'role': EDITOR}, format='json',
        )
        self.assertDenied(response, DENY_RELATION)

    def test_anonymous_is_refused(self):
        response = APIClient().post(url_invitations(self.org), {'role': EDITOR}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_pending_cap_is_enforced_per_organization_and_ignores_lapsed_rows(self):
        set_settings(max_pending_invitations=2)
        make_invitation(self.org, 'lapsed', expires_at=timezone.now() - timedelta(hours=1))
        self.make()
        self.make()
        self.assertDenied(self.create(), 'invitation_limit_reached', 409)
        other, _, _ = self.fresh_org()
        response = self.as_role(OWNER).post(url_invitations(other), {'role': EDITOR}, format='json')
        self.assertDenied(response, DENY_RELATION)  # autre organisation : pas membre ; le plafond est par organisation
        # Une révocation libère une place.
        invitation = OrganizationInvitation.objects.filter(status='PENDING', expires_at__gt=timezone.now()).first()
        self.assertEqual(self.as_role(OWNER).delete(url_invitation(self.org, invitation.pk)).status_code, 204)
        self.assertEqual(self.create().status_code, 201)

    def test_audit_and_event_carry_no_token_label_or_name(self):
        invitation, token = self.make(label=SENTINEL_LABEL)
        entry = self.audit('INVITATION_CREATED').get()
        self.assertEqual(entry.actor, self.owner)
        self.assertEqual(entry.target_id, invitation.pk)
        self.assertEqual(
            entry.details,
            f'organization={self.org.pk}; role={EDITOR}; ttl_days=7; scope_type=ORGANIZATION; scope_id=-',
        )
        event = OutboxEvent.objects.get(event_type='identity.organization_invitation_changed')
        self.assertEqual(event.payload, {
            'organization_id': str(self.org.pk), 'invitation_id': str(invitation.pk), 'change': 'created',
            'role': EDITOR, 'actor_id': str(self.owner.pk), 'inviter_id': str(self.owner.pk),
        })
        self.assertNotIn(token, json.dumps(event.payload) + entry.details)
        self.deliver()
        self.assertFalse(Notification.objects.exists())  # rien n'est notifié à la création

    def test_creation_throttles(self):
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'invitation_create': '2/hour', 'invitation_create_org': '3/day'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            self.assertEqual(self.create(OWNER).status_code, 201)
            self.assertEqual(self.create(OWNER).status_code, 201)
            self.assertEqual(self.create(OWNER).status_code, 429)  # par compte (non compté pour l'organisation)
            self.assertEqual(self.create(ADMIN).status_code, 201)  # autre compte, organisation à 3/3
            self.assertEqual(self.create(ADMIN).status_code, 429)  # par organisation
        self.assertEqual(OrganizationInvitation.objects.count(), 3)

    def test_a_non_member_never_consumes_the_organization_quota(self):
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'invitation_create': '1000/hour', 'invitation_create_org': '3/day'}
        stranger = team.login(team.make_user('stranger-q'))
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            for _ in range(60):
                response = stranger.post(url_invitations(self.org), {'role': EDITOR}, format='json')
                self.assertDenied(response, DENY_RELATION)
            for _ in range(2):  # un rôle sans capacité ne consomme rien non plus
                self.assertDenied(self.create(EDITOR), DENY_PERMISSION)
            for _ in range(3):
                self.assertEqual(self.create(OWNER).status_code, 201)
            self.assertEqual(self.create(OWNER).status_code, 429)

    def test_label_charset(self):
        client = self.as_role(OWNER)
        for bad in ('a\u200eb', 'a\u200fb', 'a\ufeffb', 'a\u202eb', 'a\u2066b', 'a\u2069b', 'a\u2028b', 'a\nb'):
            with self.subTest(label=bad):
                response = client.post(url_invitations(self.org), {'role': EDITOR, 'label': bad}, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('label', response.json())
        family = '\U0001f468\u200d\U0001f469\u200d\U0001f467'  # emoji composé : ZWJ permis
        response = client.post(url_invitations(self.org), {'role': EDITOR, 'label': family + '\u200c'}, format='json')
        self.assertEqual(response.status_code, 201, response.content)

    def test_x_context_header_is_ignored(self):
        client = self.as_role(OWNER)
        response = client.post(
            url_invitations(self.org), {'role': EDITOR}, format='json', HTTP_X_CONTEXT='PROVIDER:whatever',
        )
        self.assertEqual(response.status_code, 201)


# --- Liste ------------------------------------------------------------------------------------------------------

class ListInvitationsTests(InvBase):
    def get(self, role=OWNER, org=None, **params):
        return self.as_role(role).get(url_invitations(org or self.org), params)

    def test_default_is_pending_with_exact_keys_and_envelope(self):
        mine, _ = self.make(label='Jean')
        theirs, _ = self.make(role=ADMIN, invite_role=ANALYST)
        make_invitation(self.org, 'old', status='REVOKED', closed_at=timezone.now())
        response = self.get()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {'count', 'next', 'previous', 'results'})
        self.assertEqual(body['count'], 2)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        for row in body['results']:
            self.assertEqual(set(row), INVITATION_KEYS)
        by_id = {r['invitation_id']: r for r in body['results']}
        self.assertTrue(by_id[str(mine.pk)]['is_mine'])
        self.assertFalse(by_id[str(theirs.pk)]['is_mine'])
        self.assertEqual(by_id[str(mine.pk)]['label'], 'Jean')
        self.assertEqual(
            by_id[str(mine.pk)]['created_by_display_name'], services.public_display_name(self.owner.full_name),
        )

    def test_status_filter_and_effective_expiry(self):
        past = timezone.now() - timedelta(hours=1)
        lapsed = make_invitation(self.org, 'lapsed', expires_at=past, label=SENTINEL_LABEL)
        make_invitation(self.org, 'live')
        make_invitation(self.org, 'rev', status='REVOKED', closed_at=past)
        make_invitation(self.org, 'acc', status='ACCEPTED', closed_at=past)
        make_invitation(self.org, 'dec', status='DECLINED', closed_at=past)
        make_invitation(self.org, 'exp', status='EXPIRED', closed_at=past)
        counts = {s: self.get(status=s).json()['count'] for s in ('PENDING', 'ACCEPTED', 'DECLINED', 'REVOKED', 'EXPIRED')}
        self.assertEqual(counts, {'PENDING': 1, 'ACCEPTED': 1, 'DECLINED': 1, 'REVOKED': 1, 'EXPIRED': 2})
        expired = {r['invitation_id']: r for r in self.get(status='EXPIRED').json()['results']}
        row = expired[str(lapsed.pk)]
        self.assertEqual((row['status'], row['label']), ('EXPIRED', ''))  # présentée échue, étiquette masquée
        response = self.get(status='NOPE')
        self.assertEqual(response.status_code, 400)
        self.assertIn('status', response.json())

    def test_pagination_and_newest_first(self):
        for index in range(3):
            make_invitation(self.org, f't{index}')
        body = self.get(page_size=2).json()
        self.assertEqual((body['count'], len(body['results'])), (3, 2))
        self.assertIsNotNone(body['next'])
        dates = [r['created_at'] for r in body['results']]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_permissions(self):
        for role in (EDITOR, ANALYST):
            self.assertDenied(self.get(role), DENY_PERMISSION)
        self.assertEqual(self.get(ADMIN).status_code, 200)
        stranger = team.login(team.make_user('stranger-l'))
        self.assertDenied(stranger.get(url_invitations(self.org)), DENY_RELATION)

    def test_idor_other_organization_invitations_are_not_visible(self):
        other, other_owner, _ = self.fresh_org()
        make_invitation(other, 'foreign', created_by=other_owner)
        make_invitation(self.org, 'own', created_by=self.owner)
        self.assertEqual(self.get().json()['count'], 1)
        self.assertDenied(self.get(org=other), DENY_RELATION)

    def test_query_count_does_not_depend_on_the_page_size(self):
        make_invitation(self.org, 'one', created_by=self.owner)
        with CaptureQueriesContext(connection) as small:
            self.get()
        for index in range(6):
            make_invitation(self.org, f'more{index}', created_by=self.users[ADMIN])
        with CaptureQueriesContext(connection) as large:
            self.get()
        self.assertEqual(len(small), len(large))

    def test_post_is_not_a_list_and_members_post_stays_absent(self):
        response = self.as_role(OWNER).post(f'{ORGS}{self.org.pk}/members/', {'identifier': 'x'}, format='json')
        self.assertEqual(response.status_code, 405)


# --- Révocation -------------------------------------------------------------------------------------------------

class RevokeInvitationTests(InvBase):
    def test_revocation_closes_the_invitation_and_kills_the_link(self):
        invitation, token = self.make(label=SENTINEL_LABEL)
        response = self.as_role(OWNER).delete(url_invitation(self.org, invitation.pk))
        self.assertEqual(response.status_code, 204)
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.label, row.closed_by), ('REVOKED', '', self.owner))
        self.assertIsNotNone(row.closed_at)
        self.assertEqual(self.accept(token).json(), INVALID)
        self.assertEqual(self.preview(token).json(), INVALID)
        entry = self.audit('INVITATION_REVOKED').get()
        self.assertEqual(entry.details, f'organization={self.org.pk}; role={EDITOR}; reason=manual')
        self.assertTrue(OutboxEvent.objects.filter(payload__change='revoked').exists())

    def test_any_authorized_member_may_revoke_any_invitation(self):
        invitation, _ = self.make(role=OWNER)
        self.assertEqual(self.as_role(ADMIN).delete(url_invitation(self.org, invitation.pk)).status_code, 204)

    def test_not_pending_gives_409_and_unknown_or_foreign_gives_404(self):
        import uuid
        invitation, _ = self.make()
        client = self.as_role(OWNER)
        self.assertEqual(client.delete(url_invitation(self.org, invitation.pk)).status_code, 204)
        self.assertDenied(client.delete(url_invitation(self.org, invitation.pk)), 'invitation_not_pending', 409)
        self.assertDenied(client.delete(url_invitation(self.org, uuid.uuid4())), 'invitation_not_found', 404)
        other, other_owner, _ = self.fresh_org()
        foreign = make_invitation(other, 'foreign', created_by=other_owner)
        response = client.delete(url_invitation(self.org, foreign.pk))
        self.assertDenied(response, 'invitation_not_found', 404)
        self.assertEqual(self.fresh(foreign).status, 'PENDING')
        lapsed = make_invitation(self.org, 'lapsed', expires_at=timezone.now() - timedelta(minutes=1))
        self.assertDenied(client.delete(url_invitation(self.org, lapsed.pk)), 'invitation_not_pending', 409)

    def test_permissions(self):
        invitation, _ = self.make()
        for role in (EDITOR, ANALYST):
            self.assertDenied(self.as_role(role).delete(url_invitation(self.org, invitation.pk)), DENY_PERMISSION)
        stranger = team.login(team.make_user('stranger-r'))
        self.assertDenied(stranger.delete(url_invitation(self.org, invitation.pk)), DENY_RELATION)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')

    def test_revocation_uses_the_org_write_throttle(self):
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'org_write': '1/hour'}
        first, _ = self.make()
        second, _ = self.make()
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            client = self.as_role(OWNER)
            self.assertEqual(client.delete(url_invitation(self.org, first.pk)).status_code, 204)
            self.assertEqual(client.delete(url_invitation(self.org, second.pk)).status_code, 429)
        self.assertEqual(self.fresh(second).status, 'PENDING')


# --- Aperçu -----------------------------------------------------------------------------------------------------

class PreviewTests(InvBase):
    def test_preview_has_exact_keys_and_no_side_effect(self):
        invitation, token = self.make(label=SENTINEL_LABEL)
        audits, events = AuditLog.objects.count(), OutboxEvent.objects.count()
        response = self.preview(token)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(set(body), {
            'organization_name', 'org_type', 'role', 'expires_at', 'invited_by_display_name', 'scope', 'capabilities',
            'requires_confirmation',
        })
        self.assertEqual((body['scope'], body['requires_confirmation']), (ORG_SCOPE, False))
        self.assertEqual(body['capabilities'], capabilities.capabilities_for_role(EDITOR))
        self.assertEqual((body['organization_name'], body['org_type'], body['role']), (self.org.name, 'ENTREPRISE', EDITOR))
        self.assertEqual(body['invited_by_display_name'], services.public_display_name(self.owner.full_name))
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual((AuditLog.objects.count(), OutboxEvent.objects.count()), (audits, events))
        self.assertEqual(self.fresh(invitation).status, 'PENDING')
        self.assertFalse(Membership.objects.filter(user=self.invitee).exists())

    def test_requires_a_connected_account_and_a_token_field(self):
        _, token = self.make()
        self.assertEqual(APIClient().post(f'{BASE}preview/', {'token': token}, format='json').status_code, 401)
        for body in ({}, {'token': None}):
            response = self.invitee_client.post(f'{BASE}preview/', body, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('token', response.json())

    def test_token_is_never_accepted_in_the_url_or_the_query_string(self):
        _, token = self.make()
        self.assertEqual(self.invitee_client.get(f'{BASE}preview/?token={token}').status_code, 405)
        self.assertEqual(self.invitee_client.get(f'{BASE}{token}/').status_code, 404)

    def test_preview_ignores_the_target_state(self):
        _, token = self.make()
        Membership.objects.create(organization=self.fresh_org()[0], user=self.invitee, role=OWNER)
        set_settings(max_organizations_per_account=1)
        self.assertEqual(self.preview(token).status_code, 200)  # plafond atteint : propre à la cible, non contrôlé ici


# --- Neutralité des réponses --------------------------------------------------------------------------------------

class UniformResponseTests(InvBase):
    """Aucune différence observable (statut, corps) entre toutes les formes d'invalidité (contrat §2.7)."""

    def scenarios(self):
        """`{nom: jeton}` : chaque scénario sur sa propre organisation."""
        out = {'unknown': 'A' * 43, 'malformed': 'bad token!', 'too_long': 'a' * 129, 'empty': ''}

        def org_with_invite(name):
            org, owner, owner_membership = self.fresh_org(name)
            invitation, token = services.create_invitation(owner, org.pk, EDITOR)
            return org, owner, owner_membership, invitation, token

        org, owner, _, invitation, token = org_with_invite('expired')
        OrganizationInvitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        out['expired'] = token
        org, owner, _, invitation, token = org_with_invite('revoked')
        services.revoke_invitation(owner, org.pk, invitation.pk)
        out['revoked'] = token
        org, owner, _, invitation, token = org_with_invite('accepted')
        other = team.make_user('someone-else')
        services.accept_invitation(other, token)
        out['accepted'] = token
        org, owner, _, invitation, token = org_with_invite('declined')
        services.decline_invitation(other, token)
        out['declined'] = token
        org, owner, _, invitation, token = org_with_invite('suspended')
        Organization.objects.filter(pk=org.pk).update(status=Organization.STATUS_SUSPENDED)
        out['org_suspended'] = token
        org, owner, _, invitation, token = org_with_invite('archived')
        Organization.objects.filter(pk=org.pk).update(status=Organization.STATUS_ARCHIVED)
        out['org_archived'] = token
        org, owner, owner_membership, invitation, token = org_with_invite('inviter-gone')
        Membership.objects.filter(pk=owner_membership.pk).update(status=Membership.STATUS_REVOKED)
        out['inviter_removed'] = token
        org, owner, owner_membership, invitation, token = org_with_invite('inviter-demoted')
        Membership.objects.filter(pk=owner_membership.pk).update(role=EDITOR)
        out['inviter_demoted'] = token
        return out

    def test_accept_and_preview_answer_identically_for_every_invalid_case(self):
        scenarios = self.scenarios()
        for action in ('accept', 'preview'):
            for name, token in scenarios.items():
                with self.subTest(action=action, scenario=name):
                    cache.clear()
                    response = self.call(action, token)
                    self.assertEqual(response.status_code, 404, response.content)
                    self.assertEqual(response.json(), INVALID)
        self.assertFalse(Membership.objects.filter(user=self.invitee).exists())

    def test_decline_answers_identically_for_dead_invitations(self):
        scenarios = self.scenarios()
        for name in (
            'unknown', 'malformed', 'too_long', 'empty', 'expired', 'revoked', 'accepted', 'declined', 'org_suspended',
            'org_archived',
        ):
            with self.subTest(scenario=name):
                cache.clear()
                audits, events = AuditLog.objects.count(), OutboxEvent.objects.count()
                response = self.decline(scenarios[name])
                self.assertEqual((response.status_code, response.json()), (404, INVALID))
                self.assertEqual((AuditLog.objects.count(), OutboxEvent.objects.count()), (audits, events))

    def test_only_identified_refusals_are_journaled_and_an_unknown_token_never_is(self):
        scenarios = self.scenarios()
        for name in ('unknown', 'malformed'):
            cache.clear()
            self.accept(scenarios[name])
        self.assertFalse(self.audit('INVITATION_REFUSED').exists())
        expected = {
            'expired': 'expired', 'revoked': 'revoked', 'accepted': 'used', 'declined': 'used',
            'org_suspended': 'org_inactive', 'org_archived': 'org_inactive', 'inviter_removed': 'authority_lost',
            'inviter_demoted': 'authority_lost',
        }
        for name, reason in expected.items():
            cache.clear()
            before = self.audit('INVITATION_REFUSED').count()
            self.accept(scenarios[name])
            entries = self.audit('INVITATION_REFUSED').order_by('-created_at')
            self.assertEqual(entries.count(), before + 1, name)
            self.assertTrue(entries.first().details.endswith(f'reason={reason}'), (name, entries.first().details))
            self.assertEqual(entries.first().actor, self.invitee)

    def test_only_malformed_or_unknown_tokens_slow_the_account_down(self):
        scenarios = self.scenarios()
        for name in ('unknown', 'malformed'):
            with self.subTest(scenario=name):
                cache.clear()
                statuses = [self.accept(scenarios[name]).status_code for _ in range(7)]
                self.assertEqual(statuses, [404] * 5 + [429] * 2)
        # Invitation connue mais morte : détenir un vrai jeton n'est pas une devinette, aucun verrouillage.
        for name in ('expired', 'revoked', 'accepted', 'declined', 'org_suspended', 'org_archived', 'inviter_removed'):
            with self.subTest(scenario=name):
                cache.clear()
                for action in ('accept', 'preview'):
                    statuses = [self.call(action, scenarios[name]).status_code for _ in range(7)]
                    self.assertEqual(statuses, [404] * 7)

    def test_a_successful_preview_does_not_reset_the_failure_counter(self):
        scenarios = self.scenarios()
        _, token = self.make()
        for _ in range(4):
            self.assertEqual(self.accept(scenarios['unknown']).status_code, 404)
        self.assertEqual(self.preview(token).status_code, 200)
        self.assertEqual(self.accept(scenarios['unknown']).status_code, 404)  # 5e échec
        self.assertEqual(self.accept(scenarios['unknown']).status_code, 429)

    def test_a_trailing_newline_is_not_a_well_formed_token(self):
        _, token = self.make()
        self.assertIsNone(invitations.TOKEN_PATTERN.fullmatch(token + '\n'))
        self.assertIsNotNone(invitations.TOKEN_PATTERN.fullmatch(token))
        for action in ('accept', 'preview', 'decline'):
            self.assertEqual(self.call(action, token + '\n').json(), INVALID)

    def test_a_row_with_a_role_outside_invitable_roles_is_never_accepted(self):
        # Depuis B7 tout rôle délégable sauf OWNER (interdit en base) est invitable : on retire ANALYST de la liste.
        token = 'Zz' * 20
        row = make_invitation(self.org, token, role=ANALYST, created_by=self.owner)
        with mock.patch.object(invitations, 'INVITABLE_ROLES', (ADMIN, EDITOR, 'MEMBER')):
            self.assertEqual(self.preview(token).json(), INVALID)
            self.assertEqual(self.accept(token).json(), INVALID)
        self.assertEqual(self.fresh(row).status, 'PENDING')
        self.assertFalse(Membership.objects.filter(user=self.invitee).exists())
        self.assertTrue(self.audit('INVITATION_REFUSED').get().details.endswith('reason=role_not_invitable'))

    def test_rate_limited_account_is_refused_even_with_a_valid_token(self):
        scenarios = self.scenarios()
        _, token = self.make()
        for _ in range(5):
            self.accept(scenarios['unknown'])
        self.assertEqual(self.accept(token).status_code, 429)
        self.assertEqual(self.preview(token).status_code, 429)
        self.assertEqual(self.fresh(OrganizationInvitation.objects.get(organization=self.org)).status, 'PENDING')


# --- Acceptation ------------------------------------------------------------------------------------------------

class AcceptInvitationTests(InvBase):
    def test_acceptance_creates_the_membership_and_closes_the_invitation(self):
        invitation, token = self.make(label=SENTINEL_LABEL)
        response = self.accept(token)
        self.assertEqual(response.status_code, 200, response.content)
        membership = Membership.objects.get(organization=self.org, user=self.invitee)
        self.assertEqual(response.json(), {
            'status': 'ACTIVE', 'organization_id': str(self.org.pk), 'organization_name': self.org.name,
            'role': EDITOR, 'membership_id': str(membership.pk),
        })
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual((membership.status, membership.role, membership.added_by), ('ACTIVE', EDITOR, self.owner))
        self.assertIsNotNone(membership.joined_at)
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.label, row.closed_by), ('ACCEPTED', '', self.invitee))
        self.assertIsNotNone(row.closed_at)
        contexts = self.invitee_client.get('/api/v1/accounts/contexts/').json()
        self.assertIn(str(self.org.pk), json.dumps(contexts))

    def test_audit_trail_acts_in_the_name_of_the_target_without_personal_data(self):
        invitation, token = self.make(label=SENTINEL_LABEL)
        self.accept(token)
        accepted = self.audit('INVITATION_ACCEPTED').get()
        self.assertEqual(accepted.actor, self.invitee)
        self.assertEqual(
            accepted.details, f'organization={self.org.pk}; role={EDITOR}; invited_by={self.owner.pk}',
        )
        added = self.audit('MEMBERSHIP_ADDED').get()
        self.assertEqual(added.actor, self.invitee)
        self.assertIn('via=invitation', added.details)
        self.assertIn(f'invited_by={self.owner.pk}', added.details)
        self.assertEqual((accepted.context_type, accepted.context_id), ('ORGANIZATION', self.org.pk))

    def test_events_and_notifications(self):
        invitation, token = self.make(label=SENTINEL_LABEL)
        self.accept(token)
        changed = OutboxEvent.objects.get(event_type='identity.membership_changed')
        self.assertEqual(changed.payload['via'], 'invitation')
        self.assertEqual(changed.payload['actor_id'], str(self.owner.pk))  # l'inviteur, pas la cible
        self.assertEqual((changed.payload['change'], changed.payload['new_role']), ('added', EDITOR))
        outcome = OutboxEvent.objects.get(event_type='identity.organization_invitation_changed', payload__change='accepted')
        self.assertEqual(outcome.payload, {
            'organization_id': str(self.org.pk), 'invitation_id': str(invitation.pk), 'change': 'accepted',
            'role': EDITOR, 'actor_id': str(self.invitee.pk), 'inviter_id': str(self.owner.pk),
        })
        self.deliver()
        team_link = f'/organizations/{self.org.pk}/team'
        welcome = Notification.objects.get(user=self.invitee)
        self.assertEqual(welcome.link, team_link)
        inviter_note = Notification.objects.get(user=self.owner)
        self.assertEqual(inviter_note.title, 'Invitation acceptée')
        self.assertEqual(inviter_note.link, team_link)
        self.assertEqual(
            inviter_note.content,
            f"Une invitation à rejoindre « {self.org.name} » avec le rôle Éditeur a été acceptée.",
        )
        self.assertEqual(Notification.objects.count(), 2)  # ni l'administrateur ni personne d'autre
        for note in Notification.objects.all():
            blob = note.title + note.content + note.link
            for secret in (INVITEE_NAME, 'Sentinelle', SENTINEL_LABEL, token, self.invitee.email):
                self.assertNotIn(secret, blob)

    def test_inviter_is_not_notified_if_he_no_longer_manages_members(self):
        _, token = self.make(role=ADMIN)
        self.accept(token)
        Membership.objects.filter(organization=self.org, user=self.users[ADMIN]).update(role=EDITOR)
        self.deliver()
        self.assertFalse(Notification.objects.filter(user=self.users[ADMIN]).exists())

    def test_second_use_of_the_same_token_is_refused(self):
        _, token = self.make()
        self.assertEqual(self.accept(token).status_code, 200)
        other = team.login(team.make_user('second'))
        self.assertEqual((self.accept(token, other).status_code, self.accept(token, other).json()), (404, INVALID))
        self.assertEqual(Membership.objects.filter(organization=self.org, role=EDITOR).count(), 2)

    def test_two_concurrent_acceptances_one_wins(self):
        _, token = self.make()
        rival = team.make_user('rival')
        original, state = invitations._find_invitation, {'done': False}

        def racing(user, value):
            found = original(user, value)
            if not state['done']:
                state['done'] = True
                invitations.accept_invitation(rival, value)  # l'autre requête passe d'abord
            return found

        with mock.patch.object(invitations, '_find_invitation', racing):
            response = self.accept(token)
        self.assertEqual((response.status_code, response.json()), (404, INVALID))
        self.assertTrue(Membership.objects.filter(organization=self.org, user=rival).exists())
        self.assertFalse(Membership.objects.filter(organization=self.org, user=self.invitee).exists())

    def test_revocation_racing_an_acceptance_one_wins(self):
        invitation, token = self.make()
        original = invitations._find_invitation

        def racing(user, value):
            found = original(user, value)
            invitations.revoke_invitation(self.owner, self.org.pk, found.pk)  # la révocation passe d'abord
            return found

        with mock.patch.object(invitations, '_find_invitation', racing):
            response = self.accept(token)
        self.assertEqual((response.status_code, response.json()), (404, INVALID))
        self.assertEqual(self.fresh(invitation).status, 'REVOKED')
        self.assertFalse(Membership.objects.filter(user=self.invitee).exists())

    def test_acceptance_then_revocation_gives_409(self):
        invitation, token = self.make()
        self.assertEqual(self.accept(token).status_code, 200)
        response = self.as_role(OWNER).delete(url_invitation(self.org, invitation.pk))
        self.assertDenied(response, 'invitation_not_pending', 409)
        self.assertEqual(self.fresh(invitation).status, 'ACCEPTED')

    def test_organization_limit_at_acceptance_leaves_the_invitation_pending(self):
        invitation, token = self.make()
        set_settings(max_organizations_per_account=1)
        elsewhere = self.fresh_org('Ailleurs')[0]
        Membership.objects.create(organization=elsewhere, user=self.invitee, role=ANALYST)
        response = self.accept(token)
        self.assertDenied(response, 'organization_limit_reached', 409)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')
        self.assertEqual(self.fresh(invitation).closed_at, None)
        self.assertFalse(Membership.objects.filter(organization=self.org, user=self.invitee).exists())
        self.assertFalse(self.audit('INVITATION_ACCEPTED').exists())
        refusal = self.audit('INVITATION_REFUSED').get()
        self.assertTrue(refusal.details.endswith('reason=limit'))
        self.assertFalse(OutboxEvent.objects.filter(payload__change='accepted').exists())
        Membership.objects.filter(organization=elsewhere, user=self.invitee).update(status='REVOKED')
        self.assertEqual(self.accept(token).status_code, 200)

    def test_target_errors_do_not_count_as_invalid_token_failures(self):
        _, token = self.make()
        set_settings(max_organizations_per_account=1)
        Membership.objects.create(organization=self.fresh_org('Ailleurs')[0], user=self.invitee, role=ANALYST)
        for _ in range(7):
            self.assertEqual(self.accept(token).status_code, 409)

    def test_already_member_never_changes_the_role_and_leaves_the_invitation_pending(self):
        invitation, token = self.make(invite_role=EDITOR)
        membership = Membership.objects.create(organization=self.org, user=self.invitee, role=ANALYST)
        response = self.accept(token)
        self.assertDenied(response, 'already_member', 409)
        membership.refresh_from_db()
        self.assertEqual((membership.role, membership.status), (ANALYST, 'ACTIVE'))
        self.assertEqual(self.fresh(invitation).status, 'PENDING')
        self.assertTrue(self.audit('INVITATION_REFUSED').get().details.endswith('reason=already_member'))

    def test_inviter_accepting_his_own_link_is_a_plain_already_member(self):
        invitation, token = self.make()
        response = self.accept(token, self.as_role(OWNER))
        self.assertDenied(response, 'already_member', 409)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')

    def test_unverified_phone_and_restriction_leave_the_invitation_pending(self):
        invitation, token = self.make()
        User = type(self.invitee)
        User.objects.filter(pk=self.invitee.pk).update(phone_verified=False)
        client = team.login(User.objects.get(pk=self.invitee.pk))
        self.assertDenied(self.accept(token, client), 'phone_verification_required', 403)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')
        # Ordre de l'ADR : la restriction (DENY_SECURITY) passe avant le téléphone.
        Sanction.objects.create(
            user=self.invitee, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.owner,
        ).apply()
        self.assertDenied(self.accept(token, client), DENY_SECURITY)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')
        reasons = sorted(e.details.rsplit('reason=', 1)[1] for e in self.audit('INVITATION_REFUSED'))
        self.assertEqual(reasons, ['account_restricted', 'phone_unverified'])

    def test_phone_check_precedes_the_organization_limit(self):
        _, token = self.make()
        set_settings(max_organizations_per_account=1)
        Membership.objects.create(organization=self.fresh_org('Ailleurs')[0], user=self.invitee, role=ANALYST)
        type(self.invitee).objects.filter(pk=self.invitee.pk).update(phone_verified=False)
        client = team.login(type(self.invitee).objects.get(pk=self.invitee.pk))
        self.assertDenied(self.accept(token, client), 'phone_verification_required', 403)

    def test_a_former_member_is_reactivated_on_the_same_row_with_the_invited_role(self):
        old = Membership.objects.create(
            organization=self.org, user=self.invitee, role=OWNER, status=Membership.STATUS_REVOKED, end_reason='removed',
        )
        _, token = self.make(invite_role=ANALYST)
        self.assertEqual(self.accept(token).status_code, 200)
        old.refresh_from_db()
        self.assertEqual((old.status, old.role, old.end_reason, old.added_by), ('ACTIVE', ANALYST, '', self.owner))
        self.assertEqual(Membership.objects.filter(organization=self.org, user=self.invitee).count(), 1)
        self.assertEqual(OutboxEvent.objects.get(event_type='identity.membership_changed').payload['change'], 'reactivated')

    def test_suspended_organization_keeps_the_invitation_pending_but_unusable(self):
        invitation, token = self.make()
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertEqual(self.accept(token).json(), INVALID)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ACTIVE)
        self.assertEqual(self.accept(token).status_code, 200)

    def test_lapsed_but_unswept_invitation_is_unusable(self):
        invitation, token = self.make()
        OrganizationInvitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.accept(token).json(), INVALID)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')
        self.assertFalse(Membership.objects.filter(user=self.invitee).exists())

    def test_authority_is_rechecked_at_acceptance_even_without_a_sweep(self):
        for how in ('removed', 'demoted', 'inactive', 'restricted'):
            with self.subTest(how=how):
                cache.clear()
                org, owner, owner_membership = self.fresh_org(f'Org {how}')
                invitation, token = services.create_invitation(owner, org.pk, EDITOR)
                if how == 'removed':
                    Membership.objects.filter(pk=owner_membership.pk).update(status='REVOKED')
                elif how == 'demoted':
                    Membership.objects.filter(pk=owner_membership.pk).update(role=ANALYST)
                elif how == 'inactive':
                    type(owner).objects.filter(pk=owner.pk).update(is_active=False)
                else:
                    Sanction.objects.create(
                        user=owner, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='T', issued_by=self.owner,
                    ).apply()
                self.assertEqual(self.accept(token).json(), INVALID)
                self.assertEqual(self.fresh(invitation).status, 'PENDING')

    def test_acceptance_throttles_are_per_ip_and_per_account(self):
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'invitation_redeem_user': '2/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            self.assertEqual(self.preview('A' * 43).status_code, 404)
            self.assertEqual(self.preview('A' * 43).status_code, 404)
            self.assertEqual(self.preview('A' * 43).status_code, 429)
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'invitation_redeem': '1/hour'}
        cache.clear()
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            self.assertEqual(self.preview('A' * 43).status_code, 404)
            self.assertEqual(self.preview('A' * 43, team.login(team.make_user('other-ip'))).status_code, 429)

    def test_get_on_redeem_routes_is_not_allowed(self):
        for action in ('preview', 'accept', 'decline'):
            self.assertEqual(self.invitee_client.get(f'{BASE}{action}/').status_code, 405)

    def test_anonymous_cannot_accept_or_decline(self):
        _, token = self.make()
        for action in ('accept', 'decline'):
            response = APIClient().post(f'{BASE}{action}/', {'token': token}, format='json')
            self.assertEqual(response.status_code, 401)

    def test_missing_token_field_is_a_400(self):
        for action in ('accept', 'decline'):
            response = self.invitee_client.post(f'{BASE}{action}/', {}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('token', response.json())


# --- Refus ------------------------------------------------------------------------------------------------------

class DeclineInvitationTests(InvBase):
    def test_decline_closes_the_invitation_and_notifies_the_inviter_without_a_name(self):
        invitation, token = self.make(label=SENTINEL_LABEL)
        response = self.decline(token)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.label, row.closed_by), ('DECLINED', '', self.invitee))
        self.assertFalse(Membership.objects.filter(user=self.invitee).exists())
        entry = self.audit('INVITATION_DECLINED').get()
        self.assertEqual((entry.actor, entry.details), (self.invitee, f'organization={self.org.pk}; role={EDITOR}'))
        self.deliver()
        note = Notification.objects.get()
        self.assertEqual((note.user, note.title), (self.owner, 'Invitation refusée'))
        self.assertEqual(
            note.content, f"Une invitation à rejoindre « {self.org.name} » avec le rôle Éditeur a été refusée.",
        )
        self.assertEqual(self.accept(token).json(), INVALID)

    def test_decline_never_checks_cap_phone_or_membership(self):
        invitation, token = self.make()
        set_settings(max_organizations_per_account=1)
        Membership.objects.create(organization=self.fresh_org('Ailleurs')[0], user=self.invitee, role=ANALYST)
        Membership.objects.create(organization=self.org, user=self.invitee, role=ANALYST)
        type(self.invitee).objects.filter(pk=self.invitee.pk).update(phone_verified=False)
        client = team.login(type(self.invitee).objects.get(pk=self.invitee.pk))
        self.assertEqual(self.decline(token, client).status_code, 204)

    def test_decline_after_revocation_or_use_is_the_uniform_404(self):
        invitation, token = self.make()
        self.as_role(OWNER).delete(url_invitation(self.org, invitation.pk))
        self.assertEqual((self.decline(token).status_code, self.decline(token).json()), (404, INVALID))
        other, other_token = self.make()
        self.accept(other_token)
        self.assertEqual(self.decline(other_token, team.login(team.make_user('x2'))).json(), INVALID)

    def test_decline_racing_an_acceptance_one_wins(self):
        invitation, token = self.make()
        original = invitations._find_invitation

        winner, state = team.make_user('winner'), {'done': False}

        def racing(user, value):
            found = original(user, value)
            if not state['done']:
                state['done'] = True
                invitations.accept_invitation(winner, value)
            return found

        with mock.patch.object(invitations, '_find_invitation', racing):
            response = self.decline(token)
        self.assertEqual((response.status_code, response.json()), (404, INVALID))
        self.assertEqual(self.fresh(invitation).status, 'ACCEPTED')

    def test_expiry_by_the_command_emits_no_event_and_notifies_nobody(self):
        invitation, _ = self.make()
        OrganizationInvitation.objects.filter(pk=invitation.pk).update(expires_at=timezone.now() - timedelta(hours=1))
        before = OutboxEvent.objects.count()
        from .management.commands.expire_invitations import expire_invitations
        self.assertEqual(expire_invitations(), 1)
        self.assertEqual(OutboxEvent.objects.count(), before)


# --- Balayage de l'inviteur -------------------------------------------------------------------------------------

class InviterSweepTests(InvBase):
    def pending_of(self, user):
        return OrganizationInvitation.objects.filter(created_by=user, status='PENDING').count()

    def test_removing_the_inviter_revokes_his_pending_invitations_only(self):
        mine, _ = self.make(role=ADMIN, label=SENTINEL_LABEL)
        kept, _ = self.make(role=OWNER)
        response = self.as_role(OWNER).delete(team.url_member(self.org, self.memberships[ADMIN]))
        self.assertEqual(response.status_code, 204)
        row = self.fresh(mine)
        self.assertEqual((row.status, row.label, row.closed_by), ('REVOKED', '', self.owner))
        self.assertEqual(self.fresh(kept).status, 'PENDING')
        entry = self.audit('INVITATION_REVOKED').get()
        self.assertEqual(entry.actor, self.owner)
        self.assertEqual(entry.details, f'organization={self.org.pk}; role={EDITOR}; reason=authority_lost')

    def test_leaving_revokes_the_pending_invitations(self):
        self.make(role=ADMIN)
        self.make(role=ADMIN, invite_role=ANALYST)
        response = self.as_role(ADMIN).post(f'{ORGS}{self.org.pk}/leave/')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.pending_of(self.users[ADMIN]), 0)
        self.assertEqual(self.audit('INVITATION_REVOKED').count(), 2)

    def test_demotion_below_the_manage_members_level_revokes_them(self):
        invitation, token = self.make(role=ADMIN)
        response = self.as_role(OWNER).patch(
            team.url_member(self.org, self.memberships[ADMIN]), {'role': EDITOR}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.fresh(invitation).status, 'REVOKED')
        self.assertEqual(self.accept(token).json(), INVALID)

    def test_a_role_change_that_keeps_the_authority_keeps_the_invitations(self):
        invitation, _ = self.make(role=OWNER)
        body = {'membership_id': str(self.memberships[ADMIN].pk), 'confirm': True, 'password': team.PASSWORD}
        response = self.as_role(OWNER).post(team.url_transfer(self.org), body, format='json')  # l'ancien propriétaire devient ADMIN
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')

    def test_transfer_to_a_lower_role_revokes_the_former_owner_invitations(self):
        invitation, _ = self.make(role=OWNER)
        body = {
            'membership_id': str(self.memberships[ADMIN].pk), 'confirm': True, 'password': team.PASSWORD,
            'my_new_role': EDITOR,
        }
        self.assertEqual(self.as_role(OWNER).post(team.url_transfer(self.org), body, format='json').status_code, 200)
        self.assertEqual(self.fresh(invitation).status, 'REVOKED')

    def test_removing_a_member_without_invitations_costs_no_audit(self):
        self.as_role(OWNER).delete(team.url_member(self.org, self.memberships[ANALYST]))
        self.assertFalse(self.audit('INVITATION_REVOKED').exists())

    def test_removed_person_invitations_cannot_be_used_even_if_the_sweep_is_bypassed(self):
        invitation, token = self.make(role=ADMIN)
        OrganizationInvitation.objects.filter(pk=invitation.pk).update()  # ligne intacte, PENDING
        Membership.objects.filter(pk=self.memberships[ADMIN].pk).update(status='REVOKED')
        self.assertEqual(self.accept(token).json(), INVALID)


# --- Données personnelles, journaux, caches, garde de routes ------------------------------------------------------

class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage() + ' ' + str(record.args))


class InvitationPrivacyTests(InvBase):
    def test_token_label_and_names_appear_nowhere_but_the_creation_response(self):
        handler = _Capture()
        root = logging.getLogger()
        root.addHandler(handler)
        previous_level = root.level
        root.setLevel(logging.DEBUG)
        try:
            inviter = self.users[ADMIN]
            type(inviter).objects.filter(pk=inviter.pk).update(full_name=INVITER_NAME)
            invitation, token = self.make(role=ADMIN, label=SENTINEL_LABEL)
            second, second_token = self.make(role=ADMIN, label=SENTINEL_LABEL + '2')
            third, third_token = self.make(role=ADMIN, label=SENTINEL_LABEL + '3')
            self.preview(token)
            self.accept(token)
            self.decline(second_token)
            self.as_role(OWNER).delete(url_invitation(self.org, third.pk))
            self.accept(third_token)  # refus journalisé
            self.deliver()
        finally:
            root.removeHandler(handler)
            root.setLevel(previous_level)
        blobs = [a.details + ' ' + str(a.target_id) for a in AuditLog.objects.all()]
        blobs += [json.dumps(e.payload) for e in OutboxEvent.objects.all()]
        blobs += [f'{n.title} {n.content} {n.link}' for n in Notification.objects.all()]
        blobs += handler.lines
        blobs += [str(k) for k in cache._cache.keys()]
        text = '\n'.join(blobs)
        for secret in (
            token, second_token, third_token, SENTINEL_LABEL, INVITEE_NAME, INVITER_NAME, 'Sentinelle',
            self.invitee.email, hashlib.sha256(token.encode()).hexdigest(),
        ):
            self.assertNotIn(secret, text)

    def test_real_jwt_requests_are_never_cacheable(self):
        access = str(RefreshToken.for_user(self.owner).access_token)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        created = client.post(url_invitations(self.org), {'role': EDITOR}, format='json')
        self.assertEqual(created.status_code, 201)
        token = created.json()['link_token']
        for response in (created, client.get(url_invitations(self.org))):
            control = response['Cache-Control']
            self.assertIn('no-store', control)
            self.assertIn('private', control)
        invitee_access = str(RefreshToken.for_user(self.invitee).access_token)
        invitee = APIClient()
        invitee.credentials(HTTP_AUTHORIZATION=f'Bearer {invitee_access}')
        for action in ('preview', 'accept'):
            response = invitee.post(f'{BASE}{action}/', {'token': token}, format='json')
            self.assertEqual(response.status_code, 200, response.content)
            self.assertIn('no-store', response['Cache-Control'])

    def test_services_and_responses_never_carry_a_plan_price_or_entitlement(self):
        forbidden = ('plan', 'price', 'prix', 'entitlement', 'subscription', 'paid', 'tier')
        for function in (
            invitations.create_invitation, invitations.list_invitations, invitations.revoke_invitation,
            invitations.preview_invitation, invitations.accept_invitation, invitations.decline_invitation,
        ):
            for name in inspect.signature(function).parameters:
                self.assertFalse(any(word in name.lower() for word in forbidden), (function.__name__, name))
        invitation, token = self.make()
        texts = [
            json.dumps(self.as_role(OWNER).get(url_invitations(self.org)).json()),
            json.dumps(self.preview(token).json()), json.dumps(self.accept(token).json()),
        ]
        for text in texts:
            self.assertFalse(any(word in text.lower() for word in forbidden), text)

    def test_invitation_gives_no_capability_before_acceptance(self):
        _, token = self.make()
        response = self.invitee_client.get(f'{ORGS}{self.org.pk}/members/')
        self.assertDenied(response, DENY_RELATION)
        self.preview(token)
        self.assertDenied(self.invitee_client.get(f'{ORGS}{self.org.pk}/members/'), DENY_RELATION)
        self.accept(token)
        self.assertEqual(self.invitee_client.get(f'{ORGS}{self.org.pk}/members/').status_code, 200)


class InvitationRouteGuardTests(TestCase):
    def test_every_invitation_write_route_declares_the_exemption(self):
        self.assertEqual([r for r in collect_unguarded_write_routes() if 'invitation' in r], [])
        from . import views_invitations as v
        for view in (
            v.OrganizationInvitationsView, v.OrganizationInvitationDetailView, v.InvitationPreviewView,
            v.InvitationAcceptView, v.InvitationDeclineView, v.OrganizationInvitationConfirmView,
            v.OrganizationInvitationRejectView, v.MyAwaitingInvitationsView, v.InvitationWithdrawView,
        ):
            self.assertTrue(view.acting_context_exempt, view)

    def test_no_route_carries_a_token_in_its_path(self):
        from django.urls import get_resolver
        routes = []

        def walk(resolver, prefix=''):
            for entry in resolver.url_patterns:
                if hasattr(entry, 'url_patterns'):
                    walk(entry, prefix + str(entry.pattern))
                else:
                    routes.append(prefix + str(entry.pattern))

        walk(get_resolver())
        invitation_routes = [r for r in routes if r.startswith('api/v1/') and 'invitation' in r]
        self.assertEqual(len(invitation_routes), 9, invitation_routes)  # + confirm, reject, awaiting, withdraw (B7)
        self.assertFalse([r for r in invitation_routes if 'token' in r])

    def test_no_view_imports_add_member(self):
        apps_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for domain in sorted(os.listdir(apps_dir)):
            folder = os.path.join(apps_dir, domain)
            if not os.path.isdir(folder):
                continue
            for name in sorted(os.listdir(folder)):
                if not (name.startswith('views') and name.endswith('.py')) and name != 'urls.py':
                    continue
                with open(os.path.join(folder, name), encoding='utf-8') as handle:
                    tree = ast.parse(handle.read())
                for node in ast.walk(tree):
                    names = set()
                    if isinstance(node, ast.ImportFrom):
                        names = {alias.name for alias in node.names}
                    elif isinstance(node, ast.Attribute):
                        names = {node.attr}
                    elif isinstance(node, ast.Name):
                        names = {node.id}
                    if 'add_member' in names:
                        offenders.append(f'{domain}/{name}')
        self.assertEqual(offenders, [])

    def test_routes_are_documented_in_the_openapi_schema(self):
        from drf_spectacular.generators import SchemaGenerator
        paths = SchemaGenerator().get_schema(request=None, public=True)['paths']
        found = {p: sorted(m for m in ops if m in ('get', 'post', 'patch', 'delete')) for p, ops in paths.items() if 'invitation' in p}
        self.assertEqual(len(found), 9, found)
        self.assertEqual(
            sorted(found.values()), [['delete'], ['get'], ['get', 'post']] + [['post']] * 6,
        )
