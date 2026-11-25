"""Invitations v2 (L1-01-B7 ; ADR 0010 D4, §5.1, §6.2, §7, §8, §9, §11, §12 ; contrat d'API L1-01 §7.4).

Invitation `ADMIN` en deux temps : l'acceptation (202) ne crée AUCUNE appartenance ; seule la confirmation par
l'émetteur habilité ou un administrateur principal effectif, avec ressaisie du mot de passe, ouvre l'accès. Machine
d'états, concurrence logique (confirmation contre retrait, rejet, seconde confirmation, révocation de l'émetteur,
plafond, échéance), neutralité des réponses, IDOR, indice de téléphone (sentinelles), notifications, audit,
commande d'expiration, migration réversible avec garde."""
import json
import logging
import uuid
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.common.contexts import (
    CONTEXT_ORGANIZATION, DENY_OBJECT_STATE, DENY_PERMISSION, DENY_RELATION, DENY_SECURITY, ContextDenied,
)
from apps.moderation.models import AuditLog, Sanction
from apps.notifications.models import Notification
from apps.platform_core.models import OutboxEvent

from . import capabilities, invitations, services, tests_team as team
from .capabilities import Scope
from .management.commands.expire_invitations import expire_invitations, purge_closed_invitations
from .models import IdentitySettings, Membership, Organization, OrganizationInvitation, User
from .tests_invitations import BASE, INVALID, INVITATION_KEYS, ORG_SCOPE, InvBase, _Capture, set_settings
from .tests_invitations_base import SENTINEL_LABEL, make_invitation

OWNER, ADMIN, EDITOR, ANALYST, MEMBER = team.OWNER, team.ADMIN, team.EDITOR, team.ANALYST, 'MEMBER'
ORGS = team.ORGS
INVITEE_PHONE = '+243812345647'
HINT = '••47'
ACCEPTED_202_KEYS = {
    'status', 'invitation_id', 'organization_name', 'role', 'confirmation_expires_at', 'confirmation_code',
}
CODE_RE = r'^[0-9]{6}$'
AWAITING_ITEM_KEYS = {
    'invitation_id', 'organization_name', 'org_type', 'role', 'scope', 'accepted_at', 'confirmation_expires_at',
    'status',
}
UNAVAILABLE = {
    'detail': "Ce compte ne peut pas être ajouté ou modifié dans l'organisation.", 'code': 'user_unavailable',
}
CONFIRM_BODY = {'confirm': True, 'password': team.PASSWORD}


def url_confirm(org, invitation_id):
    return f'{ORGS}{org.pk}/invitations/{invitation_id}/confirm/'


def url_reject(org, invitation_id):
    return f'{ORGS}{org.pk}/invitations/{invitation_id}/reject/'


def url_withdraw(invitation_id):
    return f'{BASE}{invitation_id}/withdraw/'


def set_deadline(invitation, delta):
    """Échéance de confirmation à `maintenant + delta` (négatif : échue)."""
    OrganizationInvitation.objects.filter(pk=invitation.pk).update(confirmation_expires_at=timezone.now() + delta)


class V2Base(InvBase):
    def setUp(self):
        super().setUp()
        self.codes = {}  # code de rattachement par invitation (montré à la seule personne qui a accepté)
        User.objects.filter(pk=self.invitee.pk).update(phone=INVITEE_PHONE)
        self.invitee = User.objects.get(pk=self.invitee.pk)
        self.invitee_client = team.login(self.invitee)

    def awaiting(self, inviter_role=OWNER, org=None, client=None):
        """Invitation ADMIN créée par `inviter_role` puis acceptée par l'invité : ligne `AWAITING_CONFIRMATION`."""
        invitation, token = self.make(role=inviter_role, invite_role=ADMIN, org=org, label=SENTINEL_LABEL)
        response = self.accept(token, client)
        self.assertEqual(response.status_code, 202, response.content)
        self.codes[invitation.pk] = response.json()['confirmation_code']
        return self.fresh(invitation), token

    def accept_service(self, user, token):
        """Acceptation par le service (attente) : retient le code pour les confirmations suivantes."""
        result = services.accept_invitation(user, token)
        if result.confirmation_code:
            self.codes[result.invitation.pk] = result.confirmation_code
        return result

    def code_of(self, invitation):
        return self.codes[invitation.pk]

    def confirm(self, role, invitation, password=team.PASSWORD, confirm=True, org=None, code='auto'):
        body = {'confirm': confirm}
        if password is not None:
            body['password'] = password
        if code == 'auto':
            code = self.codes.get(invitation.pk)
        if code is not None:
            body['code'] = code
        return self.as_role(role).post(url_confirm(org or self.org, invitation.pk), body, format='json')

    def confirm_body(self, invitation):
        return {**CONFIRM_BODY, 'code': self.codes.get(invitation.pk, '000000')}

    def reject(self, role, invitation, org=None):
        return self.as_role(role).post(url_reject(org or self.org, invitation.pk))

    def withdraw(self, invitation, client=None):
        return (client or self.invitee_client).post(url_withdraw(invitation.pk))

    def is_member(self, user=None):
        return Membership.objects.filter(
            organization=self.org, user=user or self.invitee, status=Membership.STATUS_ACTIVE,
        ).exists()


# --- Création et aperçu ------------------------------------------------------------------------------------------

class CreateAndPreviewV2Tests(V2Base):
    def test_owner_and_admin_may_invite_an_administrator_and_a_member(self):
        for inviter in (OWNER, ADMIN):
            for role in (ADMIN, MEMBER):
                with self.subTest(inviter=inviter, role=role):
                    response = self.create(inviter, role)
                    self.assertEqual(response.status_code, 201, response.content)
                    self.assertEqual(response.json()['requires_confirmation'], role == ADMIN)

    def test_owner_is_never_invitable_and_lower_roles_cannot_invite(self):
        self.assertDenied(self.create(OWNER, OWNER), 'invitation_role_not_allowed', 400)
        self.assertDenied(self.create(ADMIN, OWNER), 'invitation_role_not_allowed', 400)
        for role in (EDITOR, ANALYST):
            self.assertDenied(self.create(role, ADMIN), DENY_PERMISSION)
        self.assertFalse(OrganizationInvitation.objects.exists())

    def test_scope_input_accepts_the_organization_only(self):
        client = self.as_role(OWNER)
        ok = client.post(f'{ORGS}{self.org.pk}/invitations/', {'role': ADMIN, 'scope': ORG_SCOPE}, format='json')
        self.assertEqual((ok.status_code, ok.json()['scope']), (201, ORG_SCOPE))
        for scope in (
            {'type': 'CITY', 'id': str(uuid.uuid4())}, {'type': 'UNIT', 'id': str(uuid.uuid4())},
            {'type': 'ORGANIZATION', 'id': str(uuid.uuid4())}, {'type': 'ORGANIZATION'},
            {'type': 'ORGANIZATION', 'id': None, 'extra': 1}, 'ORGANIZATION', [],
        ):
            with self.subTest(scope=scope):
                response = client.post(f'{ORGS}{self.org.pk}/invitations/', {'role': EDITOR, 'scope': scope},
                                       format='json')
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {'scope': ["Ce périmètre n'est pas encore disponible."]})
        self.assertEqual(OrganizationInvitation.objects.count(), 1)

    def test_a_branch_administrator_cannot_delegate_an_organization_wide_administrator(self):
        """Q23 : le périmètre de l'émetteur borne ce qu'il délègue (`can_delegate`, périmètre fictif)."""
        city = Scope.of('CITY', uuid.uuid4())
        self.assertFalse(capabilities.can_delegate(ADMIN, city, ADMIN, capabilities.ORGANIZATION_SCOPE))
        self.assertTrue(capabilities.can_delegate(ADMIN, city, ADMIN, city))
        self.assertTrue(capabilities.can_delegate(ADMIN, capabilities.ORGANIZATION_SCOPE, ADMIN, city))

    def test_preview_announces_scope_accesses_and_the_confirmation(self):
        _, token = self.make(invite_role=ADMIN)
        response = self.preview(token)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['role'], ADMIN)
        self.assertEqual(body['scope'], ORG_SCOPE)
        self.assertTrue(body['requires_confirmation'])
        self.assertEqual(body['capabilities'], sorted(body['capabilities']))
        self.assertEqual(body['capabilities'], capabilities.capabilities_for_role(ADMIN))
        self.assertNotIn('org.archive', body['capabilities'])  # réservé à l'administrateur principal
        _, member_token = self.make(invite_role=MEMBER)
        member = self.preview(member_token).json()
        self.assertEqual(member['capabilities'], ['org.leave', 'org.view_internal'])
        self.assertFalse(member['requires_confirmation'])


# --- Acceptation en deux temps -----------------------------------------------------------------------------------

class AwaitingAcceptanceTests(V2Base):
    def test_acceptance_of_an_administrator_invitation_answers_202_and_creates_no_membership(self):
        set_settings(admin_invitation_confirmation_hours=10)
        invitation, token = self.make(invite_role=ADMIN, label=SENTINEL_LABEL)
        before = timezone.now()
        response = self.accept(token)
        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertEqual(set(body), ACCEPTED_202_KEYS)
        self.assertEqual(
            (body['status'], body['invitation_id'], body['role']), ('AWAITING_CONFIRMATION', str(invitation.pk), ADMIN),
        )
        self.assertEqual(body['organization_name'], self.org.name)
        self.assertNotIn('organization_id', body)
        self.assertNotIn('membership_id', body)
        self.assertRegex(body['confirmation_code'], CODE_RE)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        row = self.fresh(invitation)
        self.assertEqual(
            (row.status, row.label, row.accepted_by, row.closed_at), ('AWAITING_CONFIRMATION', '', self.invitee, None),
        )
        self.assertAlmostEqual((row.confirmation_expires_at - before).total_seconds(), 10 * 3600, delta=60)
        self.assertFalse(Membership.objects.filter(organization=self.org, user=self.invitee).exists())
        self.assertNotIn(str(self.org.pk), json.dumps(self.invitee_client.get('/api/v1/accounts/contexts/').json()))

    def test_awaiting_acceptance_is_audited_and_published_without_personal_data(self):
        invitation, token = self.awaiting()
        entry = AuditLog.objects.get(action='INVITATION_ACCEPTED_AWAITING_CONFIRMATION')
        self.assertEqual(entry.actor, self.invitee)
        self.assertEqual(entry.details, f'organization={self.org.pk}; role={ADMIN}; invited_by={self.owner.pk}')
        self.assertFalse(AuditLog.objects.filter(action__in=('INVITATION_ACCEPTED', 'MEMBERSHIP_ADDED')).exists())
        event = OutboxEvent.objects.get(payload__change='awaiting_confirmation')
        self.assertEqual(event.payload, {
            'organization_id': str(self.org.pk), 'invitation_id': str(invitation.pk), 'change': 'awaiting_confirmation',
            'role': ADMIN, 'actor_id': str(self.invitee.pk), 'inviter_id': str(self.owner.pk),
            'accepted_by_id': str(self.invitee.pk),
        })
        self.assertFalse(OutboxEvent.objects.filter(event_type='identity.membership_changed').exists())

    def test_no_right_is_open_before_confirmation(self):
        self.awaiting()
        self.assertDenied(self.invitee_client.get(f'{ORGS}{self.org.pk}/members/'), DENY_RELATION)
        self.assertDenied(self.invitee_client.get(f'{ORGS}{self.org.pk}/internal/'), DENY_RELATION)
        with self.assertRaises(ContextDenied) as ctx:
            services.resolve_acting_context(self.invitee, f'ORGANIZATION:{self.org.pk}')
        self.assertEqual(ctx.exception.detail.code, DENY_RELATION)
        for capability in ('org.view_internal', 'org.manage_members', 'offer.publish', 'org.leave'):
            self.assertFalse(services.can(self.invitee.pk, CONTEXT_ORGANIZATION, self.org.pk, capability), capability)
        self.assertNotIn((CONTEXT_ORGANIZATION, self.org.pk), services.get_user_context_roles(self.invitee.pk))
        self.assertNotIn(self.invitee.pk, services.get_organization_recipients(self.org.pk, 'org.leave'))

    def test_the_link_is_spent_once_awaiting(self):
        invitation, token = self.awaiting()
        other = team.login(team.make_user('other-awaiting'))
        for action in ('accept', 'preview', 'decline'):
            self.assertEqual(self.call(action, token, other).json(), INVALID)
            self.assertEqual(self.call(action, token).json(), INVALID)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')

    def test_an_awaiting_invitation_cannot_be_revoked_it_is_rejected(self):
        invitation, _ = self.awaiting()
        response = self.as_role(OWNER).delete(f'{ORGS}{self.org.pk}/invitations/{invitation.pk}/')
        self.assertDenied(response, 'invitation_not_pending', 409)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')

    def test_one_awaiting_request_per_person_and_organization(self):
        first, _ = self.awaiting()
        second, second_token = self.make(invite_role=ADMIN)
        editor_invitation, editor_token = self.make(invite_role=EDITOR)
        for row, token in ((second, second_token), (editor_invitation, editor_token)):
            with self.subTest(role=row.role):
                self.assertDenied(self.accept(token), 'already_awaiting_confirmation', 409)
                self.assertEqual(self.fresh(row).status, 'PENDING')
        reasons = [e.details.rsplit('reason=', 1)[1] for e in AuditLog.objects.filter(action='INVITATION_REFUSED')]
        self.assertEqual(reasons, ['already_awaiting', 'already_awaiting'])
        # Ailleurs : aucune restriction (une attente par organisation).
        other, other_owner, _ = self.fresh_org()
        _, other_token = services.create_invitation(other_owner, other.pk, ADMIN)
        self.assertEqual(self.accept(other_token).status_code, 202)
        # La première échue : une nouvelle attente est possible.
        set_deadline(first, -timedelta(minutes=1))
        self.assertEqual(self.accept(second_token).status_code, 202)

    def test_already_member_and_target_checks_still_apply(self):
        invitation, token = self.make(invite_role=ADMIN)
        Membership.objects.create(organization=self.org, user=self.invitee, role=ANALYST)
        self.assertDenied(self.accept(token), 'already_member', 409)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')
        Membership.objects.filter(organization=self.org, user=self.invitee).delete()
        User.objects.filter(pk=self.invitee.pk).update(phone_verified=False)
        client = team.login(User.objects.get(pk=self.invitee.pk))
        self.assertDenied(self.accept(token, client), 'phone_verification_required', 403)
        self.assertEqual(self.fresh(invitation).status, 'PENDING')

    def test_target_limit_is_checked_at_acceptance(self):
        invitation, token = self.make(invite_role=ADMIN)
        set_settings(max_organizations_per_account=1)
        Membership.objects.create(organization=self.fresh_org('Ailleurs')[0], user=self.invitee, role=ANALYST)
        self.assertDenied(self.accept(token), 'organization_limit_reached', 409)  # `account_review_required` : B8
        self.assertEqual(self.fresh(invitation).status, 'PENDING')

    def test_two_concurrent_acceptances_of_the_same_admin_link_one_wins(self):
        _, token = self.make(invite_role=ADMIN)
        rival = team.make_user('rival-admin')
        original, state = invitations._find_invitation, {'done': False}

        def racing(user, value):
            found = original(user, value)
            if not state['done']:
                state['done'] = True
                invitations.accept_invitation(rival, value)
            return found

        with mock.patch.object(invitations, '_find_invitation', racing):
            response = self.accept(token)
        self.assertEqual((response.status_code, response.json()), (404, INVALID))
        row = OrganizationInvitation.objects.get(organization=self.org, role=ADMIN)
        self.assertEqual((row.status, row.accepted_by_id), ('AWAITING_CONFIRMATION', rival.pk))


# --- Liste (contrat §7.4, §7.4.2) --------------------------------------------------------------------------------

class AwaitingListTests(V2Base):
    def listing(self, role=OWNER, **params):
        return self.as_role(role).get(f'{ORGS}{self.org.pk}/invitations/', params)

    def test_awaiting_filter_shows_name_and_phone_hint_only_to_who_can_confirm(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        self.assertEqual(self.listing().json()['count'], 0)  # défaut PENDING : l'attente n'y est pas
        second_admin, _ = self.add('admin-bis', ADMIN)
        cases = {
            OWNER: True, ADMIN: True,  # administrateur principal ; émetteur
            'second_admin': False,  # autre administrateur : ni nom, ni indice
        }
        for who, expected in cases.items():
            with self.subTest(who=who):
                client = team.login(second_admin) if who == 'second_admin' else self.as_role(who)
                body = client.get(f'{ORGS}{self.org.pk}/invitations/', {'status': 'AWAITING_CONFIRMATION'}).json()
                self.assertEqual(body['count'], 1)
                row = body['results'][0]
                self.assertEqual(set(row), INVITATION_KEYS)
                self.assertEqual(
                    (row['status'], row['can_confirm'], row['requires_confirmation']),
                    ('AWAITING_CONFIRMATION', expected, True),
                )
                self.assertEqual(row['label'], '')
                self.assertIsNotNone(row['accepted_at'])
                self.assertIsNotNone(row['confirmation_expires_at'])
                if expected:
                    self.assertEqual(
                        row['accepted_by_display_name'], services.public_display_name(self.invitee.full_name),
                    )
                    self.assertEqual(row['accepted_by_phone_hint'], HINT)
                else:
                    self.assertEqual((row['accepted_by_display_name'], row['accepted_by_phone_hint']), (None, None))
        for role in (EDITOR, ANALYST):
            self.assertDenied(self.listing(role, status='AWAITING_CONFIRMATION'), DENY_PERMISSION)

    def test_an_expired_wait_is_listed_as_expired_without_identity(self):
        invitation, _ = self.awaiting()
        set_deadline(invitation, -timedelta(seconds=1))
        self.assertEqual(self.listing(status='AWAITING_CONFIRMATION').json()['count'], 0)
        row = self.listing(status='EXPIRED').json()['results'][0]
        self.assertEqual((row['status'], row['can_confirm']), ('EXPIRED', False))
        self.assertEqual((row['accepted_by_display_name'], row['accepted_by_phone_hint']), (None, None))

    def test_rejected_filter_and_other_values(self):
        invitation, _ = self.awaiting()
        self.assertEqual(self.reject(OWNER, invitation).status_code, 204)
        row = self.listing(status='REJECTED').json()['results'][0]
        self.assertEqual((row['status'], row['accepted_by_phone_hint'], row['can_confirm']), ('REJECTED', None, False))
        self.assertEqual(self.listing(status='rejected').status_code, 400)

    def test_query_count_does_not_depend_on_the_page_size(self):
        self.awaiting()
        with CaptureQueriesContext(connection) as small:
            self.listing(status='AWAITING_CONFIRMATION')
        for index in range(4):
            guest = team.make_user(f'guest-{index}')
            make_invitation(
                self.org, f'aw{index}', role=ADMIN, status='AWAITING_CONFIRMATION', created_by=self.owner,
                accepted_by=guest, accepted_at=timezone.now(),
                confirmation_expires_at=timezone.now() + timedelta(hours=5),
            )
        with CaptureQueriesContext(connection) as large:
            body = self.listing(status='AWAITING_CONFIRMATION').json()
        self.assertEqual(body['count'], 5)
        self.assertEqual(len(small), len(large))


# --- Confirmation ------------------------------------------------------------------------------------------------

class ConfirmTests(V2Base):
    def test_the_inviter_confirms_and_the_person_becomes_administrator(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        inviter = self.users[ADMIN]
        response = self.confirm(ADMIN, invitation)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(set(body), team.MEMBER_KEYS)
        membership = Membership.objects.get(organization=self.org, user=self.invitee)
        self.assertEqual(body['membership_id'], str(membership.pk))
        self.assertEqual(
            (body['role'], body['scope'], body['is_self'], body['is_last_effective_owner']),
            (ADMIN, ORG_SCOPE, False, False),
        )
        self.assertEqual(body['display_name'], services.public_display_name(self.invitee.full_name))
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual((membership.status, membership.role, membership.added_by), ('ACTIVE', ADMIN, inviter))
        row = self.fresh(invitation)
        self.assertEqual(
            (row.status, row.confirmed_by, row.closed_by, row.accepted_by),
            ('ACCEPTED', inviter, inviter, self.invitee),
        )
        self.assertIsNotNone(row.closed_at)
        # Audit (règle 12) : confirmateur, fondement, ressaisie ; UUID et codes seulement.
        confirmed = AuditLog.objects.get(action='INVITATION_CONFIRMED')
        self.assertEqual(confirmed.actor, inviter)
        self.assertEqual(confirmed.details, (
            f'organization={self.org.pk}; role={ADMIN}; accepted_by={self.invitee.pk}; invited_by={inviter.pk}; '
            'confirmer_basis=inviter; reauth=true'
        ))
        added = AuditLog.objects.get(action='MEMBERSHIP_ADDED')
        self.assertEqual(added.actor, inviter)
        self.assertIn('via=invitation', added.details)
        # Événements : `confirmed` et `membership_changed` (acteur = émetteur, via invitation).
        event = OutboxEvent.objects.get(payload__change='confirmed')
        self.assertEqual(event.payload['accepted_by_id'], str(self.invitee.pk))
        self.assertEqual(event.payload['actor_id'], str(inviter.pk))
        changed = OutboxEvent.objects.get(event_type='identity.membership_changed')
        self.assertEqual(
            (changed.payload['actor_id'], changed.payload['via'], changed.payload['new_role']),
            (str(inviter.pk), 'invitation', ADMIN),
        )
        # L'accès est ouvert à la requête suivante.
        self.assertEqual(self.invitee_client.get(f'{ORGS}{self.org.pk}/members/').status_code, 200)
        self.assertIn(str(self.org.pk), json.dumps(self.invitee_client.get('/api/v1/accounts/contexts/').json()))

    def test_a_primary_admin_confirms_even_after_the_inviter_left(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        self.assertEqual(self.as_role(ADMIN).post(f'{ORGS}{self.org.pk}/leave/').status_code, 204)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')  # le balayage ne touche que PENDING
        response = self.confirm(OWNER, invitation)
        self.assertEqual(response.status_code, 200, response.content)
        details = AuditLog.objects.get(action='INVITATION_CONFIRMED').details
        self.assertTrue(details.endswith('confirmer_basis=primary_admin; reauth=true'))
        membership = Membership.objects.get(organization=self.org, user=self.invitee)
        self.assertEqual(membership.added_by, self.users[ADMIN])  # l'émetteur reste l'origine

    def test_who_may_not_confirm(self):
        invitation, _ = self.awaiting(inviter_role=OWNER)
        self.assertDenied(self.confirm(ADMIN, invitation), DENY_PERMISSION)  # ni émetteur, ni administrateur principal
        for role in (EDITOR, ANALYST):
            self.assertDenied(self.confirm(role, invitation), DENY_PERMISSION)
        stranger = team.login(team.make_user('stranger-c'))
        body = self.confirm_body(invitation)
        response = stranger.post(url_confirm(self.org, invitation.pk), body, format='json')
        self.assertDenied(response, DENY_RELATION)
        # La personne qui a accepté n'est pas membre : elle ne peut pas se confirmer elle-même, même avec son code.
        response = self.invitee_client.post(url_confirm(self.org, invitation.pk), body, format='json')
        self.assertDenied(response, DENY_RELATION)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')
        self.assertFalse(self.is_member())
        self.assertFalse(AuditLog.objects.filter(action='ORG_SENSITIVE_REAUTH_FAILED').exists())

    def test_inviter_who_lost_the_authority_is_refused_but_a_primary_admin_still_can(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        Membership.objects.filter(pk=self.memberships[ADMIN].pk).update(role=EDITOR)
        self.assertDenied(self.confirm(ADMIN, invitation), DENY_PERMISSION)
        # Simple rétrogradation : l'attente reste, un administrateur principal confirme.
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')
        self.assertEqual(self.confirm(OWNER, invitation).status_code, 200)

    def test_idor_and_unknown_invitations_are_404(self):
        other, other_owner, _ = self.fresh_org()
        foreign, foreign_token = services.create_invitation(other_owner, other.pk, ADMIN)
        self.accept_service(self.invitee, foreign_token)
        for target in (foreign.pk, uuid.uuid4()):
            with self.subTest(target=target):
                body = {**CONFIRM_BODY, 'code': self.codes[foreign.pk]}
                response = self.as_role(OWNER).post(url_confirm(self.org, target), body, format='json')
                self.assertDenied(response, 'invitation_not_found', 404)
                self.assertDenied(self.as_role(OWNER).post(url_reject(self.org, target)), 'invitation_not_found', 404)
        self.assertEqual(self.fresh(foreign).status, 'AWAITING_CONFIRMATION')

    def test_password_is_required_and_failures_are_limited_and_journaled(self):
        invitation, _ = self.awaiting()
        self.assertDenied(self.confirm(OWNER, invitation, confirm=False), 'confirmation_required', 400)
        self.assertDenied(self.confirm(OWNER, invitation, password=None), 'password_required', 400)
        for _ in range(5):
            self.assertDenied(self.confirm(OWNER, invitation, password='mauvais'), 'reauthentication_failed', 403)
        self.assertEqual(self.confirm(OWNER, invitation).status_code, 429)  # limiteur atomique `org_reauth`
        entries = AuditLog.objects.filter(action='ORG_SENSITIVE_REAUTH_FAILED')
        self.assertEqual(entries.count(), 5)
        self.assertEqual(entries.first().details, f'organization={self.org.pk}; action=confirm_admin_invitation')
        self.assertNotIn('mauvais', ' '.join(e.details for e in AuditLog.objects.all()))
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')
        self.assertFalse(self.is_member())

    def test_only_an_awaiting_invitation_can_be_confirmed(self):
        pending, _ = self.make(invite_role=ADMIN)
        self.assertDenied(self.confirm(OWNER, pending), 'invitation_not_awaiting_confirmation', 409)
        invitation, _ = self.awaiting()
        set_deadline(invitation, -timedelta(seconds=1))
        self.assertDenied(self.confirm(OWNER, invitation), 'invitation_not_awaiting_confirmation', 409)
        self.assertDenied(self.reject(OWNER, invitation), 'invitation_not_awaiting_confirmation', 409)
        self.assertFalse(self.is_member())
        self.assertFalse(AuditLog.objects.filter(action='ORG_SENSITIVE_REAUTH_FAILED').exists())

    def test_the_person_is_rechecked_and_the_refusal_is_neutral(self):
        bodies = []
        for how in ('inactive', 'restricted', 'phone', 'limit', 'deleted'):
            with self.subTest(how=how):
                cache.clear()
                OrganizationInvitation.objects.all().delete()
                Membership.objects.filter(user=self.invitee).delete()
                User.objects.filter(pk=self.invitee.pk).update(is_active=True, phone_verified=True)
                Sanction.objects.all().delete()
                set_settings(max_organizations_per_account=10)
                invitation, _ = self.awaiting()
                if how == 'inactive':
                    User.objects.filter(pk=self.invitee.pk).update(is_active=False)
                elif how == 'restricted':
                    Sanction.objects.create(
                        user=self.invitee, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='T', issued_by=self.owner,
                    ).apply()
                elif how == 'phone':
                    User.objects.filter(pk=self.invitee.pk).update(phone_verified=False)
                elif how == 'limit':
                    set_settings(max_organizations_per_account=1)
                    elsewhere = self.fresh_org(f'Ailleurs {how}')[0]
                    Membership.objects.create(organization=elsewhere, user=self.invitee, role=ANALYST)
                else:
                    OrganizationInvitation.objects.filter(pk=invitation.pk).update(accepted_by=None)
                response = self.confirm(OWNER, invitation)
                self.assertEqual(response.status_code, 400, response.content)
                bodies.append(response.json())
                self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')
                self.assertFalse(self.is_member())
        self.assertEqual(bodies, [UNAVAILABLE] * 5)

    def test_already_member_at_confirmation(self):
        invitation, _ = self.awaiting()
        Membership.objects.create(organization=self.org, user=self.invitee, role=ANALYST)
        self.assertDenied(self.confirm(OWNER, invitation), 'already_member', 409)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')
        self.assertEqual(Membership.objects.get(organization=self.org, user=self.invitee).role, ANALYST)

    def test_a_former_member_is_reactivated_on_the_same_row(self):
        old = Membership.objects.create(
            organization=self.org, user=self.invitee, role=ANALYST, status=Membership.STATUS_REVOKED, end_reason='left',
        )
        invitation, _ = self.awaiting()
        self.assertEqual(self.confirm(OWNER, invitation).status_code, 200)
        old.refresh_from_db()
        self.assertEqual((old.status, old.role), ('ACTIVE', ADMIN))
        changed = OutboxEvent.objects.get(event_type='identity.membership_changed')
        self.assertEqual(changed.payload['change'], 'reactivated')

    def test_organization_state_is_checked(self):
        invitation, _ = self.awaiting()
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertDenied(self.confirm(OWNER, invitation), DENY_SECURITY)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ARCHIVED)
        self.assertDenied(self.confirm(OWNER, invitation), DENY_OBJECT_STATE)
        self.assertFalse(self.is_member())

    def test_confirmation_uses_the_sensitive_throttle(self):
        invitation, _ = self.awaiting()
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'org_sensitive': '1/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            self.assertDenied(self.confirm(OWNER, invitation, password='mauvais'), 'reauthentication_failed', 403)
            self.assertEqual(self.confirm(OWNER, invitation).status_code, 429)
        self.assertFalse(self.is_member())

    def test_anonymous_and_get_are_refused(self):
        invitation, _ = self.awaiting()
        self.assertEqual(APIClient().post(url_confirm(self.org, invitation.pk), {}, format='json').status_code, 401)
        self.assertEqual(self.as_role(OWNER).get(url_confirm(self.org, invitation.pk)).status_code, 405)


# --- Concurrence logique (ADR 0010 §11) ------------------------------------------------------------------------

class ConfirmConcurrencyTests(V2Base):
    """La ressaisie se fait AVANT le verrou : on intercale l'action concurrente juste après elle."""

    def race(self, action):
        original, state = invitations._require_reauthentication, {'done': False}

        def racing(*args, **kwargs):
            original(*args, **kwargs)
            if not state['done']:  # l'action concurrente peut elle-même ressaisir (seconde confirmation)
                state['done'] = True
                action()

        return mock.patch.object(invitations, '_require_reauthentication', racing)

    def test_confirmation_against_withdrawal(self):
        invitation, _ = self.awaiting()
        with self.race(lambda: services.withdraw_awaiting_invitation(self.invitee, invitation.pk)):
            response = self.confirm(OWNER, invitation)
        self.assertDenied(response, 'invitation_not_awaiting_confirmation', 409)
        self.assertEqual(self.fresh(invitation).status, 'DECLINED')
        self.assertFalse(self.is_member())
        self.assertFalse(AuditLog.objects.filter(action='INVITATION_CONFIRMED').exists())

    def test_two_confirmations_one_wins(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        def rival():
            services.confirm_invitation(
                self.owner, self.org.pk, invitation.pk, True, team.PASSWORD, code=self.code_of(invitation),
            )

        with self.race(rival):
            response = self.confirm(ADMIN, invitation)
        self.assertDenied(response, 'invitation_not_awaiting_confirmation', 409)
        self.assertEqual(Membership.objects.filter(organization=self.org, user=self.invitee).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='INVITATION_CONFIRMED').count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='MEMBERSHIP_ADDED').count(), 1)
        self.assertEqual(self.fresh(invitation).confirmed_by, self.owner)

    def test_confirmation_against_rejection(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        with self.race(lambda: services.reject_invitation(self.owner, self.org.pk, invitation.pk)):
            response = self.confirm(ADMIN, invitation)
        self.assertDenied(response, 'invitation_not_awaiting_confirmation', 409)
        self.assertEqual(self.fresh(invitation).status, 'REJECTED')
        self.assertFalse(self.is_member())

    def test_confirmation_against_removal_or_demotion_of_the_inviter(self):
        for how in ('removed', 'demoted'):
            with self.subTest(how=how):
                cache.clear()
                OrganizationInvitation.objects.all().delete()
                inviter, membership = self.add(f'inviter-{how}', ADMIN)
                invitation, token = services.create_invitation(inviter, self.org.pk, ADMIN)
                guest = team.make_user(f'guest-{how}')
                self.accept_service(guest, token)

                def action():
                    if how == 'removed':
                        services.remove_member(self.owner, self.org.pk, membership.pk)
                    else:
                        services.change_role(self.owner, self.org.pk, membership.pk, EDITOR)

                with self.race(action):
                    response = team.login(inviter).post(
                        url_confirm(self.org, invitation.pk), self.confirm_body(invitation), format='json',
                    )
                self.assertDenied(response, DENY_RELATION if how == 'removed' else DENY_PERMISSION)
                self.assertFalse(Membership.objects.filter(organization=self.org, user=guest).exists())
                if how == 'removed':
                    # Émetteur retiré : son attente est rejetée dans la même transaction (décision S3).
                    self.assertEqual(self.fresh(invitation).status, 'REJECTED')
                    self.assertDenied(self.confirm(OWNER, invitation), 'invitation_not_awaiting_confirmation', 409)
                else:
                    # Simple rétrogradation : un administrateur principal peut toujours confirmer.
                    self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')
                    self.assertEqual(self.confirm(OWNER, invitation).status_code, 200)

    def test_confirmation_against_the_person_reaching_the_limit_elsewhere(self):
        invitation, _ = self.awaiting()
        set_settings(max_organizations_per_account=1)
        elsewhere = self.fresh_org('Ailleurs course')[0]
        with self.race(lambda: Membership.objects.create(organization=elsewhere, user=self.invitee, role=ANALYST)):
            response = self.confirm(OWNER, invitation)
        self.assertEqual((response.status_code, response.json()), (400, UNAVAILABLE))
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')

    def test_confirmation_against_expiry(self):
        invitation, _ = self.awaiting()
        with self.race(lambda: OrganizationInvitation.objects.filter(pk=invitation.pk).update(
            confirmation_expires_at=timezone.now() - timedelta(seconds=1),
        )):
            response = self.confirm(OWNER, invitation)
        self.assertDenied(response, 'invitation_not_awaiting_confirmation', 409)
        self.assertFalse(self.is_member())

    def test_confirmation_against_suspension(self):
        invitation, _ = self.awaiting()
        def suspend():
            Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)

        with self.race(suspend):
            response = self.confirm(OWNER, invitation)
        self.assertDenied(response, DENY_SECURITY)
        self.assertFalse(self.is_member())


# --- Rejet --------------------------------------------------------------------------------------------------------

class RejectTests(V2Base):
    def test_rejection_closes_the_request_and_notifies_the_person_without_the_confirmer_name(self):
        type(self.owner).objects.filter(pk=self.owner.pk).update(full_name='Confirmateur Sentinelle')
        invitation, _ = self.awaiting()
        response = self.reject(OWNER, invitation)
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.confirmed_by, row.closed_by), ('REJECTED', self.owner, self.owner))
        entry = AuditLog.objects.get(action='INVITATION_REJECTED')
        self.assertEqual(entry.actor, self.owner)
        self.assertEqual(entry.details, f'organization={self.org.pk}; role={ADMIN}; accepted_by={self.invitee.pk}')
        event = OutboxEvent.objects.get(payload__change='rejected')
        self.assertEqual(event.payload['accepted_by_id'], str(self.invitee.pk))
        Notification.objects.all().delete()
        self.deliver()
        note = Notification.objects.get(user=self.invitee)
        self.assertEqual((note.title, note.context_type, note.link), ('Demande non confirmée', None, '/profiles'))
        self.assertEqual(note.content, f"Votre demande pour rejoindre « {self.org.name} » n'a pas été confirmée.")
        self.assertNotIn('Sentinelle', note.title + note.content)
        self.assertFalse(self.is_member())
        self.assertDenied(self.confirm(OWNER, invitation), 'invitation_not_awaiting_confirmation', 409)
        self.assertDenied(self.withdraw(invitation), 'invitation_not_awaiting_confirmation', 409)

    def test_who_may_reject(self):
        invitation, _ = self.awaiting(inviter_role=OWNER)
        for role in (ADMIN, EDITOR, ANALYST):
            self.assertDenied(self.reject(role, invitation), DENY_PERMISSION)
        stranger = team.login(team.make_user('stranger-r2'))
        self.assertDenied(stranger.post(url_reject(self.org, invitation.pk)), DENY_RELATION)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')
        mine, _ = self.make(role=ADMIN, invite_role=ADMIN)
        # L'émetteur ADMIN peut rejeter sa propre invitation en attente.
        guest = team.make_user('guest-r2')
        _, token = services.create_invitation(self.users[ADMIN], self.org.pk, ADMIN)
        self.accept_service(guest, token)
        own = OrganizationInvitation.objects.get(accepted_by=guest)
        self.assertEqual(self.reject(ADMIN, own).status_code, 204)
        self.assertEqual(self.fresh(mine).status, 'PENDING')

    def test_rejection_uses_the_org_write_throttle(self):
        first, _ = self.awaiting()
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'org_write': '1/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            self.assertEqual(self.reject(OWNER, first).status_code, 204)
            self.assertEqual(self.reject(OWNER, first).status_code, 429)


# --- Côté personne qui a accepté (contrat §7.4.7) ----------------------------------------------------------------

class MyAwaitingTests(V2Base):
    def mine(self, client=None, **params):
        return (client or self.invitee_client).get(f'{BASE}awaiting/', params)

    def test_list_has_exact_keys_and_only_my_requests(self):
        invitation, _ = self.awaiting()
        other_person = team.make_user('other-person')
        other_org, other_owner, _ = self.fresh_org('Org B')
        _, token = services.create_invitation(other_owner, other_org.pk, ADMIN)
        self.accept_service(other_person, token)
        response = self.mine()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        body = response.json()
        self.assertEqual(set(body), {'count', 'next', 'previous', 'results'})
        self.assertEqual(body['count'], 1)
        row = body['results'][0]
        self.assertEqual(set(row), AWAITING_ITEM_KEYS)
        self.assertEqual(
            (row['invitation_id'], row['organization_name'], row['org_type'], row['role'], row['scope'], row['status']),
            (str(invitation.pk), self.org.name, 'ENTREPRISE', ADMIN, ORG_SCOPE, 'AWAITING_CONFIRMATION'),
        )
        for secret in (
            'label', 'phone', 'hint', SENTINEL_LABEL, INVITEE_PHONE, 'created_by', 'inviter', 'code',
            self.code_of(invitation),
        ):
            self.assertNotIn(secret, json.dumps(body))
        self.assertEqual(APIClient().get(f'{BASE}awaiting/').status_code, 401)

    def test_recently_expired_requests_are_listed_for_information_then_disappear(self):
        invitation, _ = self.awaiting()
        set_deadline(invitation, -timedelta(days=1))
        self.assertEqual(self.mine().json()['results'][0]['status'], 'EXPIRED')
        expire_invitations()
        self.assertEqual(self.mine().json()['results'][0]['status'], 'EXPIRED')
        set_deadline(invitation, -timedelta(days=8))
        self.assertEqual(self.mine().json()['count'], 0)

    def test_confirmed_rejected_and_withdrawn_requests_leave_the_list(self):
        invitation, _ = self.awaiting()
        self.assertEqual(self.confirm(OWNER, invitation).status_code, 200)
        self.assertEqual(self.mine().json()['count'], 0)

    def test_withdrawal(self):
        invitation, _ = self.awaiting()
        response = self.invitee_client.post(url_withdraw(invitation.pk))
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.closed_by), ('DECLINED', self.invitee))
        entry = AuditLog.objects.get(action='INVITATION_WITHDRAWN')
        self.assertEqual((entry.actor, entry.details), (self.invitee, f'organization={self.org.pk}; role={ADMIN}'))
        event = OutboxEvent.objects.get(payload__change='declined')
        self.assertEqual(event.payload['actor_id'], str(self.invitee.pk))
        self.assertEqual(self.mine().json()['count'], 0)
        self.assertDenied(self.withdraw(invitation), 'invitation_not_awaiting_confirmation', 409)
        self.assertDenied(self.confirm(OWNER, invitation), 'invitation_not_awaiting_confirmation', 409)

    def test_withdrawal_of_someone_else_request_answers_like_an_unknown_one(self):
        invitation, _ = self.awaiting()
        intruder = team.login(team.make_user('intruder'))
        foreign = intruder.post(url_withdraw(invitation.pk))
        unknown = intruder.post(url_withdraw(uuid.uuid4()))
        self.assertEqual((foreign.status_code, foreign.json()), (unknown.status_code, unknown.json()))
        self.assertDenied(foreign, 'invitation_not_found', 404)
        # Même l'émetteur ou un administrateur principal ne retire pas à la place de la personne.
        self.assertDenied(self.as_role(OWNER).post(url_withdraw(invitation.pk)), 'invitation_not_found', 404)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')

    def test_withdrawal_is_allowed_on_a_suspended_organization_but_not_once_expired(self):
        invitation, _ = self.awaiting()
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertEqual(self.invitee_client.post(url_withdraw(invitation.pk)).status_code, 204)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ACTIVE)
        _, token = self.make(invite_role=ADMIN)
        self.assertEqual(self.accept(token).status_code, 202)
        late = OrganizationInvitation.objects.get(status='AWAITING_CONFIRMATION')
        set_deadline(late, -timedelta(seconds=1))
        self.assertDenied(self.withdraw(late), 'invitation_not_awaiting_confirmation', 409)


# --- Commande d'expiration ----------------------------------------------------------------------------------------

class AwaitingExpiryCommandTests(V2Base):
    def test_overdue_waits_expire_and_live_ones_stay(self):
        overdue, _ = self.awaiting()
        set_deadline(overdue, -timedelta(minutes=1))
        other, other_owner, _ = self.fresh_org()
        _, token = services.create_invitation(other_owner, other.pk, ADMIN)
        self.accept_service(self.invitee, token)
        live = OrganizationInvitation.objects.get(organization=other)
        # Le lien d'origine est échu mais la confirmation ne l'est pas : l'attente reste.
        OrganizationInvitation.objects.filter(pk=live.pk).update(expires_at=timezone.now() - timedelta(days=1))
        events = OutboxEvent.objects.count()
        self.assertEqual(expire_invitations(), 1)
        self.assertEqual(self.fresh(overdue).status, 'EXPIRED')
        self.assertIsNotNone(self.fresh(overdue).closed_at)
        self.assertEqual(self.fresh(live).status, 'AWAITING_CONFIRMATION')
        self.assertEqual(AuditLog.objects.get(action='INVITATION_EXPIRED').details, 'count=1; awaiting=1')
        self.assertEqual(OutboxEvent.objects.count(), events)  # aucun événement à l'expiration
        self.assertFalse(Membership.objects.filter(user=self.invitee).exists())
        self.assertEqual(expire_invitations(), 0)  # idempotente

    def test_the_purge_never_deletes_an_open_wait(self):
        invitation, _ = self.awaiting()
        old = timezone.now() - timedelta(days=400)
        OrganizationInvitation.objects.filter(pk=invitation.pk).update(created_at=old, accepted_at=old)
        purge_closed_invitations()
        self.assertTrue(OrganizationInvitation.objects.filter(pk=invitation.pk).exists())

    def test_the_confirmation_delay_setting_has_bounds(self):
        row = IdentitySettings.get_solo()
        self.assertEqual(row.admin_invitation_confirmation_hours, 72)
        for value, valid in ((0, False), (1, True), (336, True), (337, False)):
            row.admin_invitation_confirmation_hours = value
            if valid:
                row.full_clean()
            else:
                with self.assertRaises(ValidationError, msg=value):
                    row.full_clean()


# --- Notifications et données personnelles -----------------------------------------------------------------------

class NotificationAndPrivacyTests(V2Base):
    def test_awaiting_notifies_the_inviter_and_every_effective_primary_admin_only(self):
        second_owner, _ = self.add('owner-2', OWNER)
        restricted_owner, _ = self.add('owner-3', OWNER)
        Sanction.objects.create(
            user=restricted_owner, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='T', issued_by=self.owner,
        ).apply()
        self.deliver()
        Notification.objects.all().delete()
        self.awaiting(inviter_role=ADMIN)
        self.deliver()
        recipients = set(Notification.objects.values_list('user_id', flat=True))
        self.assertEqual(recipients, {self.users[ADMIN].pk, self.owner.pk, second_owner.pk})
        note = Notification.objects.filter(user=self.owner).get()
        self.assertEqual(note.title, 'Confirmation requise')
        self.assertEqual(note.content, (
            f"Une invitation comme Administrateur pour « {self.org.name} » a été acceptée. Confirmez l'identité de "
            "la personne avant de lui ouvrir l'accès."
        ))
        self.assertEqual(note.link, f'/organizations/{self.org.pk}/team')
        self.assertEqual((note.context_type, note.context_id), (CONTEXT_ORGANIZATION, self.org.pk))

    def test_an_inviter_who_lost_the_authority_is_not_asked_to_confirm(self):
        self.awaiting(inviter_role=ADMIN)
        Membership.objects.filter(pk=self.memberships[ADMIN].pk).update(role=EDITOR)
        Notification.objects.all().delete()
        self.deliver()
        self.assertEqual(set(Notification.objects.values_list('user_id', flat=True)), {self.owner.pk})

    def test_confirmed_notifies_the_person_and_the_other_confirmers(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        self.deliver()
        Notification.objects.all().delete()
        self.assertEqual(self.confirm(OWNER, invitation).status_code, 200)
        self.deliver()
        # UNE seule notification pour la personne (décision du chef de projet) : pas de « Vous avez rejoint… ».
        person = Notification.objects.get(user=self.invitee)
        self.assertEqual(person.title, 'Accès confirmé')
        self.assertEqual(person.content, f"Votre accès à « {self.org.name} » est confirmé.")
        changed = OutboxEvent.objects.get(event_type='identity.membership_changed')
        self.assertIs(changed.payload['confirmed'], True)
        inviter = Notification.objects.filter(user=self.users[ADMIN]).get()
        self.assertEqual(
            inviter.content, f"Une invitation comme Administrateur pour « {self.org.name} » a été confirmée.",
        )
        self.assertFalse(Notification.objects.filter(user=self.owner).exists())  # l'auteur de la confirmation

    def test_hint_name_phone_label_and_token_never_leak_outside_the_listing(self):
        handler = _Capture()
        root = logging.getLogger()
        root.addHandler(handler)
        previous_level = root.level
        root.setLevel(logging.DEBUG)
        try:
            invitation, token = self.awaiting(inviter_role=ADMIN)
            listing = self.as_role(ADMIN).get(f'{ORGS}{self.org.pk}/invitations/', {'status': 'AWAITING_CONFIRMATION'})
            self.assertIn(HINT, listing.content.decode())  # seule réponse qui le porte
            self.confirm(OWNER, invitation, password='mauvais')
            self.confirm(OWNER, invitation)
            second, second_token = self.make(invite_role=ADMIN)
            other = team.make_user('other-sentinel', phone='+243899990011', full_name='Autre Sentinelle')
            self.accept_service(other, second_token)
            self.confirm(OWNER, second, code='999999' if self.code_of(second) != '999999' else '888888')
            services.reject_invitation(self.owner, self.org.pk, second.pk)
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
            HINT, '••', INVITEE_PHONE, '345647', '+243899990011', team.SECRET_NAME, self.invitee.full_name,
            'Autre Sentinelle', SENTINEL_LABEL, token, second_token, self.invitee.email, self.code_of(invitation),
            self.code_of(second),
        ):
            self.assertNotIn(secret, text)

    def test_new_services_never_carry_a_plan_price_or_entitlement(self):
        import inspect
        forbidden = ('plan', 'price', 'prix', 'entitlement', 'subscription', 'paid', 'tier')
        for function in (
            invitations.confirm_invitation, invitations.reject_invitation, invitations.list_my_awaiting_invitations,
            invitations.withdraw_awaiting_invitation, invitations.get_invitation_confirmer_ids,
            invitations.create_invitation, invitations.regenerate_confirmation_code,
        ):
            for name in inspect.signature(function).parameters:
                self.assertFalse(any(word in name.lower() for word in forbidden), (function.__name__, name))


# --- Code de rattachement (décision S3, ADR 0010 QG-2) ----------------------------------------------------------

class ConfirmationCodeTests(V2Base):
    def wrong_code(self, invitation):
        right = self.code_of(invitation)
        return '000000' if right != '000000' else '111111'

    def test_the_code_is_shown_once_to_the_person_and_only_its_hmac_is_stored(self):
        invitation, _ = self.awaiting()
        code = self.code_of(invitation)
        self.assertRegex(code, CODE_RE)
        row = self.fresh(invitation)
        self.assertEqual(len(row.confirmation_code_hash), 64)
        self.assertNotEqual(row.confirmation_code_hash, code)
        stored = ' '.join(str(v) for v in OrganizationInvitation.objects.values().get(pk=invitation.pk).values())
        self.assertNotIn(code, stored.replace(row.confirmation_code_hash, ''))
        # Ni la liste de l'équipe ni « mes demandes » ne le renvoient.
        listing = self.as_role(OWNER).get(f'{ORGS}{self.org.pk}/invitations/', {'status': 'AWAITING_CONFIRMATION'})
        mine = self.invitee_client.get(f'{BASE}awaiting/')
        for response in (listing, mine):
            self.assertNotIn(code, response.content.decode())
            self.assertNotIn('confirmation_code', response.content.decode())

    def test_the_code_is_required_before_the_password_is_checked(self):
        invitation, _ = self.awaiting()
        for code in (None, '', '   '):
            with self.subTest(code=code):
                body = {'confirm': True, 'password': 'mauvais'}
                if code is not None:
                    body['code'] = code
                response = self.as_role(OWNER).post(url_confirm(self.org, invitation.pk), body, format='json')
                self.assertDenied(response, 'confirmation_code_required', 400)
        self.assertFalse(AuditLog.objects.filter(action='ORG_SENSITIVE_REAUTH_FAILED').exists())
        self.assertEqual(self.fresh(invitation).confirmation_code_failures, 0)

    def test_a_wrong_code_is_refused_counted_and_journaled_without_the_code(self):
        invitation, _ = self.awaiting()
        wrong = self.wrong_code(invitation)
        response = self.confirm(OWNER, invitation, code=wrong)
        self.assertEqual(
            response.json(), {'detail': "Le code de confirmation est incorrect.", 'code': 'confirmation_code_invalid'},
        )
        self.assertEqual(response.status_code, 400)
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.confirmation_code_failures), ('AWAITING_CONFIRMATION', 1))
        entry = AuditLog.objects.get(action='INVITATION_CONFIRMATION_CODE_FAILED')
        self.assertEqual(entry.actor, self.owner)
        self.assertEqual(entry.details, f'organization={self.org.pk}; role={ADMIN}; failures=1')
        self.assertFalse(self.is_member())
        self.assertEqual(self.confirm(OWNER, invitation).status_code, 200)  # le bon code reste valable

    def test_a_wrong_password_does_not_consume_a_code_attempt(self):
        invitation, _ = self.awaiting()
        self.assertDenied(self.confirm(OWNER, invitation, password='mauvais'), 'reauthentication_failed', 403)
        self.assertEqual(self.fresh(invitation).confirmation_code_failures, 0)

    def test_five_wrong_codes_reject_the_request_and_notify_the_person_neutrally(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        wrong = self.wrong_code(invitation)
        self.deliver()
        Notification.objects.all().delete()
        statuses = []
        for attempt in range(5):
            role = ADMIN if attempt % 2 else OWNER  # le compteur est porté par l'invitation, pas par le confirmateur
            statuses.append((self.confirm(role, invitation, code=wrong).json()['code']))
        self.assertEqual(statuses, ['confirmation_code_invalid'] * 4 + ['confirmation_code_exhausted'])
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.confirmation_code_failures, row.confirmation_code_hash), ('REJECTED', 5, ''))
        rejected = AuditLog.objects.get(action='INVITATION_REJECTED')
        self.assertTrue(rejected.details.endswith('reason=code_failed'))
        # Le bon code arrive trop tard.
        self.assertDenied(self.confirm(OWNER, invitation), 'invitation_not_awaiting_confirmation', 409)
        self.assertFalse(self.is_member())
        self.deliver()
        note = Notification.objects.get(user=self.invitee)
        self.assertEqual(note.content, f"Votre demande pour rejoindre « {self.org.name} » n'a pas été confirmée.")

    def test_comparison_is_constant_time(self):
        invitation, _ = self.awaiting()
        with mock.patch.object(invitations, 'constant_time_compare', wraps=invitations.constant_time_compare) as spy:
            self.assertEqual(self.confirm(OWNER, invitation).status_code, 200)
        spy.assert_called()

    def test_regeneration_invalidates_the_previous_code_and_keeps_the_counter(self):
        invitation, _ = self.awaiting()
        old = self.code_of(invitation)
        self.confirm(OWNER, invitation, code=self.wrong_code(invitation))
        response = self.invitee_client.post(f'{BASE}{invitation.pk}/confirmation-code/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        body = response.json()
        self.assertEqual(set(body), {'invitation_id', 'confirmation_code', 'confirmation_expires_at'})
        self.assertRegex(body['confirmation_code'], CODE_RE)
        new = body['confirmation_code']
        self.assertEqual(self.fresh(invitation).confirmation_code_failures, 1)
        entry = AuditLog.objects.get(action='INVITATION_CONFIRMATION_CODE_REGENERATED')
        self.assertEqual((entry.actor, entry.details), (self.invitee, f'organization={self.org.pk}; role={ADMIN}'))
        if new != old:
            self.assertDenied(self.confirm(OWNER, invitation, code=old), 'confirmation_code_invalid', 400)
        self.assertEqual(self.confirm(OWNER, invitation, code=new).status_code, 200)

    def test_regeneration_is_reserved_to_the_person_and_to_an_open_wait(self):
        invitation, _ = self.awaiting()
        intruder = team.login(team.make_user('intruder-code'))
        foreign = intruder.post(f'{BASE}{invitation.pk}/confirmation-code/')
        unknown = intruder.post(f'{BASE}{uuid.uuid4()}/confirmation-code/')
        self.assertEqual((foreign.status_code, foreign.json()), (unknown.status_code, unknown.json()))
        self.assertDenied(foreign, 'invitation_not_found', 404)
        response = self.as_role(OWNER).post(f'{BASE}{invitation.pk}/confirmation-code/')
        self.assertDenied(response, 'invitation_not_found', 404)
        set_deadline(invitation, -timedelta(seconds=1))
        response = self.invitee_client.post(f'{BASE}{invitation.pk}/confirmation-code/')
        self.assertDenied(response, 'invitation_not_awaiting_confirmation', 409)
        self.assertEqual(APIClient().post(f'{BASE}{invitation.pk}/confirmation-code/').status_code, 401)
        self.assertEqual(self.invitee_client.get(f'{BASE}{invitation.pk}/confirmation-code/').status_code, 405)

    def test_regeneration_uses_the_org_write_throttle(self):
        invitation, _ = self.awaiting()
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'org_write': '1/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            self.assertEqual(self.invitee_client.post(f'{BASE}{invitation.pk}/confirmation-code/').status_code, 200)
            self.assertEqual(self.invitee_client.post(f'{BASE}{invitation.pk}/confirmation-code/').status_code, 429)

    def test_the_code_and_password_are_masked_from_error_reports(self):
        from rest_framework.test import APIRequestFactory, force_authenticate

        from . import views_invitations as v
        invitation, _ = self.awaiting()
        request = APIRequestFactory().post('/x/', self.confirm_body(invitation), format='json')
        force_authenticate(request, user=self.owner)
        v.OrganizationInvitationConfirmView.as_view()(request, pk=self.org.pk, invitation_id=invitation.pk)
        self.assertEqual(set(request.sensitive_post_parameters), {'password', 'code'})

    def test_closing_the_wait_erases_the_code_hash(self):
        cases = ('confirmed', 'rejected', 'withdrawn', 'expired')
        for how in cases:
            with self.subTest(how=how):
                OrganizationInvitation.objects.all().delete()
                Membership.objects.filter(organization=self.org, user=self.invitee).delete()
                invitation, _ = self.awaiting()
                if how == 'confirmed':
                    self.assertEqual(self.confirm(OWNER, invitation).status_code, 200)
                elif how == 'rejected':
                    self.assertEqual(self.reject(OWNER, invitation).status_code, 204)
                elif how == 'withdrawn':
                    self.assertEqual(self.withdraw(invitation).status_code, 204)
                else:
                    set_deadline(invitation, -timedelta(seconds=1))
                    expire_invitations()
                self.assertEqual(self.fresh(invitation).confirmation_code_hash, '')


# --- Autorité de l'émetteur (décision S3) -------------------------------------------------------------------------

class InviterAuthorityTests(V2Base):
    def awaiting_rows(self, role=OWNER):
        response = self.as_role(role).get(f'{ORGS}{self.org.pk}/invitations/', {'status': 'AWAITING_CONFIRMATION'})
        return {row['invitation_id']: row for row in response.json()['results']}

    def test_the_list_flags_an_inviter_who_lost_the_authority(self):
        mine, _ = self.awaiting(inviter_role=ADMIN)
        pending, _ = self.make(role=ADMIN, invite_role=EDITOR)
        self.assertTrue(self.awaiting_rows()[str(mine.pk)]['inviter_has_authority'])
        pending_rows = self.as_role(OWNER).get(f'{ORGS}{self.org.pk}/invitations/').json()['results']
        self.assertTrue(pending_rows[0]['inviter_has_authority'])
        Membership.objects.filter(pk=self.memberships[ADMIN].pk).update(role=EDITOR)  # rétrogradation : l'attente reste
        row = self.awaiting_rows()[str(mine.pk)]
        self.assertEqual((row['inviter_has_authority'], row['can_confirm']), (False, True))
        orphan = make_invitation(
            self.org, 'orphan', role=ADMIN, status='AWAITING_CONFIRMATION', created_by=None,
            accepted_by=team.make_user('orphan-guest'), accepted_at=timezone.now(),
            confirmation_expires_at=timezone.now() + timedelta(hours=3),
        )
        self.assertFalse(self.awaiting_rows()[str(orphan.pk)]['inviter_has_authority'])

    def test_removing_the_inviter_rejects_his_waits(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        other_inviter_wait, other_token = self.make(role=OWNER, invite_role=ADMIN)
        guest = team.make_user('guest-other')
        self.accept_service(guest, other_token)
        self.deliver()
        Notification.objects.all().delete()
        response = self.as_role(OWNER).delete(team.url_member(self.org, self.memberships[ADMIN]))
        self.assertEqual(response.status_code, 204)
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.closed_by, row.confirmation_code_hash), ('REJECTED', self.owner, ''))
        self.assertEqual(self.fresh(other_inviter_wait).status, 'AWAITING_CONFIRMATION')
        entry = AuditLog.objects.get(action='INVITATION_REJECTED')
        self.assertEqual(entry.details, (
            f'organization={self.org.pk}; role={ADMIN}; accepted_by={self.invitee.pk}; reason=authority_lost'
        ))
        event = OutboxEvent.objects.filter(payload__change='rejected').get()
        self.assertEqual(event.payload['accepted_by_id'], str(self.invitee.pk))
        self.deliver()
        self.assertEqual(
            Notification.objects.get(user=self.invitee).content,
            f"Votre demande pour rejoindre « {self.org.name} » n'a pas été confirmée.",
        )

    def test_leaving_keeps_the_waits_for_a_primary_admin(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        self.assertEqual(self.as_role(ADMIN).post(f'{ORGS}{self.org.pk}/leave/').status_code, 204)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')

    def test_a_sanctioned_or_deactivated_inviter_has_his_waits_rejected_everywhere(self):
        for how in ('sanction', 'deactivation'):
            with self.subTest(how=how):
                inviter, _ = self.add(f'inviter-{how}', ADMIN)
                other, other_owner, _ = self.fresh_org(f'Autre {how}')
                Membership.objects.create(organization=other, user=inviter, role=ADMIN)
                waits = []
                for org in (self.org, other):
                    _, token = services.create_invitation(inviter, org.pk, ADMIN)
                    waits.append(self.accept_service(team.make_user(f'g-{how}-{org.pk.hex[:6]}'), token).invitation)
                if how == 'sanction':
                    Sanction.objects.create(
                        user=inviter, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='T', issued_by=self.owner,
                    ).apply()
                else:
                    services.set_account_active(inviter.pk, False, actor=self.owner)
                for wait in waits:
                    self.assertEqual(self.fresh(wait).status, 'REJECTED')
                    confirmer = self.as_role(OWNER) if wait.organization_id == self.org.pk else team.login(other_owner)
                    url = url_confirm(wait.organization, wait.pk)
                    response = confirmer.post(url, self.confirm_body(wait), format='json')
                    self.assertDenied(response, 'invitation_not_awaiting_confirmation', 409)
                reasons = AuditLog.objects.filter(action='INVITATION_REJECTED', target_id__in=[w.pk for w in waits])
                self.assertEqual(reasons.count(), 2)
                self.assertTrue(all(e.details.endswith('reason=authority_lost') for e in reasons))

    def test_reactivation_does_not_reject_anything(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        services.set_account_active(self.users[ADMIN].pk, True)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')

    def test_the_authority_flag_costs_a_constant_number_of_queries(self):
        self.awaiting(inviter_role=ADMIN)
        with CaptureQueriesContext(connection) as small:
            self.awaiting_rows()
        for index in range(4):
            inviter, _ = self.add(f'inv-q{index}', ADMIN)
            make_invitation(
                self.org, f'awq{index}', role=ADMIN, status='AWAITING_CONFIRMATION', created_by=inviter,
                accepted_by=team.make_user(f'gq{index}'), accepted_at=timezone.now(),
                confirmation_expires_at=timezone.now() + timedelta(hours=5),
            )
        with CaptureQueriesContext(connection) as large:
            self.assertEqual(len(self.awaiting_rows()), 5)
        self.assertEqual(len(small), len(large))


# --- Plafond d'invitations ouvertes (décision S3) ------------------------------------------------------------------

class OpenInvitationCapTests(V2Base):
    def test_waits_for_confirmation_count_in_the_cap_until_they_lapse(self):
        set_settings(max_pending_invitations=2)
        invitation, _ = self.awaiting()
        self.make(invite_role=EDITOR)
        self.assertDenied(self.create(OWNER, EDITOR), 'invitation_limit_reached', 409)
        set_deadline(invitation, -timedelta(seconds=1))
        self.assertEqual(self.create(OWNER, EDITOR).status_code, 201)


# --- Relecture de B7 (aller-retour 3) ------------------------------------------------------------------------------

class ReviewRoundThreeTests(V2Base):
    def test_deactivation_in_the_django_admin_rejects_the_waits_of_the_account(self):
        from .tests_admin import make_admin_user

        invitation, _ = self.awaiting(inviter_role=ADMIN)
        inviter = self.users[ADMIN]
        staff = make_admin_user('staff-b7@example.com', perms=['view_user', 'change_user'])
        self.client.force_login(staff)
        response = self.client.post(reverse('admin:identity_user_change', args=[inviter.pk]), {
            'full_name': inviter.full_name, 'email': inviter.email,  # `is_active` absent : case décochée
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.get(pk=inviter.pk).is_active)
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.closed_by), ('REJECTED', staff))
        entry = AuditLog.objects.get(action='INVITATION_REJECTED')
        self.assertEqual(entry.actor, staff)
        self.assertTrue(entry.details.endswith('reason=authority_lost'))

    def test_an_inviter_demoted_then_removed_has_his_waits_rejected(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        membership = self.memberships[ADMIN]
        services.change_role(self.owner, self.org.pk, membership.pk, EDITOR)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')  # rétrogradation : l'attente reste
        self.assertEqual(self.as_role(OWNER).delete(team.url_member(self.org, membership)).status_code, 204)
        self.assertEqual(self.fresh(invitation).status, 'REJECTED')
        self.assertTrue(AuditLog.objects.get(action='INVITATION_REJECTED').details.endswith('reason=authority_lost'))

    def test_an_already_lapsed_wait_is_left_to_the_cron(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        set_deadline(invitation, -timedelta(seconds=1))
        response = self.as_role(OWNER).delete(team.url_member(self.org, self.memberships[ADMIN]))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.fresh(invitation).status, 'AWAITING_CONFIRMATION')
        self.assertFalse(AuditLog.objects.filter(action='INVITATION_REJECTED').exists())
        call_command('expire_invitations', verbosity=0)
        self.assertEqual(self.fresh(invitation).status, 'EXPIRED')

    def test_the_cron_rejects_waits_of_inactive_or_restricted_inviters(self):
        live_inactive, _ = self.awaiting(inviter_role=ADMIN)
        restricted_inviter, _ = self.add('restricted-inviter', ADMIN)
        _, token = services.create_invitation(restricted_inviter, self.org.pk, ADMIN)
        live_restricted = self.accept_service(team.make_user('guest-restricted'), token).invitation
        _, token = services.create_invitation(self.owner, self.org.pk, ADMIN)
        healthy = self.accept_service(team.make_user('guest-healthy'), token).invitation
        # Contournement du chemin direct : écriture en base et sanction sans `apply()`.
        User.objects.filter(pk=self.users[ADMIN].pk).update(is_active=False)
        Sanction.objects.create(
            user=restricted_inviter, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='T', issued_by=self.owner,
        )
        self.deliver()
        Notification.objects.all().delete()
        call_command('expire_invitations', verbosity=0)
        self.assertEqual(self.fresh(live_inactive).status, 'REJECTED')
        self.assertEqual(self.fresh(live_restricted).status, 'REJECTED')
        self.assertEqual(self.fresh(healthy).status, 'AWAITING_CONFIRMATION')
        entries = AuditLog.objects.filter(action='INVITATION_REJECTED')
        self.assertEqual(entries.count(), 2)
        self.assertTrue(all(e.actor is None and e.details.endswith('reason=authority_lost') for e in entries))
        self.deliver()
        self.assertEqual(Notification.objects.filter(title='Demande non confirmée').count(), 2)
        call_command('expire_invitations', verbosity=0)  # idempotent
        self.assertEqual(AuditLog.objects.filter(action='INVITATION_REJECTED').count(), 2)

    def test_the_cron_lets_a_lapsed_wait_expire_rather_than_reject_it(self):
        invitation, _ = self.awaiting(inviter_role=ADMIN)
        set_deadline(invitation, -timedelta(seconds=1))
        User.objects.filter(pk=self.users[ADMIN].pk).update(is_active=False)
        call_command('expire_invitations', verbosity=0)
        self.assertEqual(self.fresh(invitation).status, 'EXPIRED')
        self.assertFalse(AuditLog.objects.filter(action='INVITATION_REJECTED').exists())

    def test_a_malformed_code_is_an_invalid_attempt(self):
        invitation, _ = self.awaiting()
        malformed = ['1234567', 'abcdef', 123456]
        bodies = []
        for code in malformed:
            with self.subTest(code=code):
                response = self.confirm(OWNER, invitation, code=code)
                self.assertEqual(response.status_code, 400, response.content)
                bodies.append(response.json())
        wrong = self.confirm(OWNER, invitation, code='000000' if self.code_of(invitation) != '000000' else '111111')
        self.assertEqual(bodies, [wrong.json()] * len(malformed))  # même réponse qu'un code faux
        self.assertEqual(wrong.json()['code'], 'confirmation_code_invalid')
        row = self.fresh(invitation)
        self.assertEqual((row.status, row.confirmation_code_failures), ('AWAITING_CONFIRMATION', 4))
        self.assertDenied(self.confirm(OWNER, invitation, code='12345'), 'confirmation_code_exhausted', 409)
        self.assertEqual(self.fresh(invitation).status, 'REJECTED')  # 5e essai mal formé : épuisé aussi

    def test_surrounding_spaces_make_a_code_malformed(self):
        invitation, _ = self.awaiting()
        code = self.code_of(invitation)
        self.assertDenied(self.confirm(OWNER, invitation, code=f' {code} '), 'confirmation_code_invalid', 400)
        self.assertEqual(self.fresh(invitation).confirmation_code_failures, 1)
        self.assertEqual(self.confirm(OWNER, invitation, code=code).status_code, 200)


# --- Fonctions pures ----------------------------------------------------------------------------------------------

class PureTests(SimpleTestCase):
    def test_phone_hint(self):
        user = User(phone='+243812345647', phone_verified=True)
        self.assertEqual(invitations.phone_hint(user), '••47')
        self.assertIsNone(invitations.phone_hint(User(phone='+243812345647', phone_verified=False)))
        self.assertIsNone(invitations.phone_hint(User(phone=None, phone_verified=True)))
        self.assertIsNone(invitations.phone_hint(User(phone='+7', phone_verified=True)))
        self.assertIsNone(invitations.phone_hint(None))

    def test_confirmer_basis_follows_delegation_and_scope(self):
        actor_id, other_id = uuid.uuid4(), uuid.uuid4()
        org_scope, city = capabilities.ORGANIZATION_SCOPE, Scope.of('CITY', uuid.uuid4())
        row = OrganizationInvitation(role=ADMIN, created_by_id=actor_id, scope_type='ORGANIZATION', scope_id=None)
        basis = invitations._confirmer_basis
        self.assertEqual(basis(actor_id, ADMIN, org_scope, row), 'inviter')
        self.assertEqual(basis(actor_id, OWNER, org_scope, row), 'inviter')
        self.assertEqual(basis(other_id, OWNER, org_scope, row), 'primary_admin')
        self.assertIsNone(basis(other_id, ADMIN, org_scope, row))
        self.assertIsNone(basis(actor_id, EDITOR, org_scope, row))
        self.assertIsNone(basis(actor_id, ADMIN, city, row))  # un émetteur de branche ne confirme pas un global
        self.assertIsNone(basis(other_id, OWNER, city, row))  # impossible en base ; refusé quand même

    def test_effective_status(self):
        now = timezone.now()
        row = OrganizationInvitation(status='AWAITING_CONFIRMATION', expires_at=now - timedelta(days=1))
        row.confirmation_expires_at = now + timedelta(hours=1)
        self.assertEqual(invitations.effective_status(row, now), 'AWAITING_CONFIRMATION')
        row.confirmation_expires_at = now
        self.assertEqual(invitations.effective_status(row, now), 'EXPIRED')
        row.confirmation_expires_at = None
        self.assertEqual(invitations.effective_status(row, now), 'EXPIRED')


# --- Migration 0019 : réversible, avec garde -----------------------------------------------------------------------

class InvitationConfirmationMigrationTests(TransactionTestCase):
    """Migrations 0019 et 0020 : aller, retour, garde."""

    serialized_rollback = True

    def _fixture_setup(self):
        # Même précaution que `tests_member_scope.MigrationRollbackGuardTests` (vidage sans `post_migrate`).
        call_command('flush', verbosity=0, interactive=False, inhibit_post_migrate=True)
        super()._fixture_setup()

    def tearDown(self):
        call_command('migrate', verbosity=0)

    def migrate(self, target):
        MigrationExecutor(connection).migrate([target])

    def columns(self, table):
        with connection.cursor() as cursor:
            return [c.name for c in connection.introspection.get_table_description(cursor, table)]

    def test_0020_then_0019_are_reversible_with_a_guard_on_the_new_statuses(self):
        org = Organization.objects.create(name='Atelier Migration 0019', org_type='ENTREPRISE')
        # 0020 (code de rattachement) : garde tant qu'une attente est ouverte (elle deviendrait confirmable sans code).
        wait = make_invitation(
            org, 'mig-0020', role=ADMIN, status='AWAITING_CONFIRMATION',
            confirmation_expires_at=timezone.now() + timedelta(hours=1),
        )
        with self.assertRaises(RuntimeError) as ctx:
            self.migrate(('identity', '0019_invitation_confirmation'))
        self.assertIn('identity.0020', str(ctx.exception))
        self.assertIn('confirmation_code_hash', self.columns('identity_organizationinvitation'))
        wait.delete()
        self.migrate(('identity', '0019_invitation_confirmation'))
        columns = self.columns('identity_organizationinvitation')
        self.assertNotIn('confirmation_code_hash', columns)
        self.assertNotIn('confirmation_code_failures', columns)
        # 0019 : garde de données, lignes écrites par le modèle HISTORIQUE de 0019.
        state = MigrationExecutor(connection).loader.project_state(('identity', '0019_invitation_confirmation'))
        historical = state.apps.get_model('identity', 'OrganizationInvitation')
        for status_value in ('AWAITING_CONFIRMATION', 'REJECTED'):
            with self.subTest(status=status_value):
                row = historical.objects.create(
                    organization_id=org.pk, role=ADMIN, status=status_value,
                    token_hash=status_value.lower().ljust(64, 'x'),
                    expires_at=timezone.now() + timedelta(days=1),
                )
                with self.assertRaises(RuntimeError) as ctx:
                    self.migrate(('identity', '0018_membership_scope_member_role'))
                self.assertIn('identity.0019', str(ctx.exception))
                self.assertIn('accepted_by_id', self.columns('identity_organizationinvitation'))
                row.delete()
        self.migrate(('identity', '0018_membership_scope_member_role'))
        self.assertNotIn('accepted_by_id', self.columns('identity_organizationinvitation'))
        self.assertNotIn('admin_invitation_confirmation_hours', self.columns('identity_identitysettings'))
        self.migrate(('identity', '0020_invitation_confirmation_code'))
        columns = self.columns('identity_organizationinvitation')
        self.assertIn('confirmation_expires_at', columns)
        self.assertIn('confirmation_code_hash', columns)
