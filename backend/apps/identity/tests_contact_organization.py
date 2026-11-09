"""Contact par contexte vendeur : réglages d'une organisation, canaux ouverts, numéro remis (ADR 0006, T7 / L0-09f2).

Le numéro et le consentement d'une organisation appartiennent à l'organisation, pas à un membre (règle 10) ; ils sont
gérés par un propriétaire ou un administrateur (`contact.manage_channels`), sous l'interrupteur
`IdentitySettings.org_phone_channels_enabled` (fermé par défaut, Q-CLI5)."""
import json
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.moderation.models import AuditLog, Sanction

from . import services
from .models import (
    CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint, IdentitySettings, Membership, Organization,
    ProviderProfile, User,
)

BASE = '/api/v1/accounts/contact-settings/'
VERSION = CONTACT_CONSENT_TEXT_VERSION
ORG_NUMBER = '+243891111111'
NEW_ORG_NUMBER = '+243892222222'
MEMBER_LOGIN = '+243970000001'
MEMBER_CONTACT = '+243893333333'


def header(org):
    return {'HTTP_X_CONTEXT': f'ORGANIZATION:{org.pk}'}


def open_switch(value=True):
    IdentitySettings.objects.update_or_create(
        pk=IdentitySettings.SINGLETON_ID, defaults={'org_phone_channels_enabled': value},
    )


class OrgContactBase(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(name='Atelier X', org_type='ENTREPRISE')
        self.people = {}
        for index, role in enumerate(('OWNER', 'ADMIN', 'EDITOR', 'ANALYST')):
            user = User.objects.create_user(
                email=f'{role.lower()}@example.com', phone=f'+24397000000{index + 1}', password='x',
                full_name=f'Membre {role.title()}', phone_verified=True,
            )
            Membership.objects.create(organization=self.org, user=user, role=role)
            self.people[role] = user
        self.outsider = User.objects.create_user(email='out@example.com', password='x', full_name='Étranger')
        sms = mock.patch('apps.identity.sms.send_otp_sms')
        self.sms = sms.start()
        self.addCleanup(sms.stop)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def put_phone(self, user, **body):
        return self.client_for(user).put(BASE + 'phone/', body, format='json', **header(self.org))

    def verify(self, user, code):
        return self.client_for(user).post(BASE + 'phone/verify/', {'code': code}, format='json', **header(self.org))

    def channel(self, user, channel, **body):
        return self.client_for(user).put(f'{BASE}channels/{channel}/', body, format='json', **header(self.org))

    def get(self, user):
        return self.client_for(user).get(BASE, **header(self.org))

    def verified_org_phone(self, user=None, phone=ORG_NUMBER):
        user = user or self.people['OWNER']
        self.assertEqual(self.put_phone(user, phone=phone).status_code, 200)
        self.assertEqual(self.verify(user, self.sms.call_args[0][1]).status_code, 200)

    def db_consent(self, channel='CALL', phone=ORG_NUMBER, **extra):
        ContactPoint.objects.update_or_create(
            organization=self.org, defaults={'phone': phone, 'is_verified': True, 'verified_at': timezone.now()},
        )
        values = dict(
            is_granted=True, text_version=VERSION, granted_at=timezone.now(), phone_last4=phone[-4:],
            granted_by=self.people['OWNER'],
        )
        values.update(extra)
        return ContactConsent.objects.update_or_create(organization=self.org, channel=channel, defaults=values)[0]

    def assert_code(self, response, status, code):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json().get('code'), code, response.content)


class RolesTests(OrgContactBase):
    def test_owner_and_admin_manage_the_organization_contact(self):
        open_switch()
        for role in ('OWNER', 'ADMIN'):
            with self.subTest(role=role):
                user = self.people[role]
                self.assertEqual(self.get(user).status_code, 200)
                self.verified_org_phone(user, ORG_NUMBER if role == 'OWNER' else NEW_ORG_NUMBER)
                response = self.channel(user, 'CALL', enabled=True, text_version=VERSION)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertTrue(response.json()['channels']['CALL']['enabled'])

    def test_editor_and_analyst_cannot_read_or_change_the_organization_contact(self):
        open_switch()
        for role in ('EDITOR', 'ANALYST'):
            with self.subTest(role=role):
                user = self.people[role]
                self.assert_code(self.get(user), 403, 'DENY_PERMISSION')
                self.assert_code(self.put_phone(user, phone=ORG_NUMBER), 403, 'DENY_PERMISSION')
                self.assert_code(self.verify(user, '123456'), 403, 'DENY_PERMISSION')
                self.assert_code(self.channel(user, 'CALL', enabled=True, text_version=VERSION), 403, 'DENY_PERMISSION')
        self.assertFalse(ContactPoint.objects.filter(organization=self.org).exists())
        self.assertFalse(ContactConsent.objects.filter(organization=self.org).exists())
        self.sms.assert_not_called()

    def test_a_non_member_gets_the_same_refusal_for_any_organization(self):
        self.assert_code(self.get(self.outsider), 403, 'DENY_RELATION')
        self.assert_code(self.put_phone(self.outsider, phone=ORG_NUMBER), 403, 'DENY_RELATION')
        self.assertFalse(ContactPoint.objects.filter(organization=self.org).exists())

    def test_a_revoked_member_loses_access_with_the_same_token(self):
        user = self.people['ADMIN']
        self.assertEqual(self.get(user).status_code, 200)
        Membership.objects.filter(organization=self.org, user=user).update(status=Membership.STATUS_REVOKED)
        self.assert_code(self.get(user), 403, 'DENY_RELATION')
        self.assert_code(self.put_phone(user, phone=ORG_NUMBER), 403, 'DENY_RELATION')
        self.assertFalse(ContactPoint.objects.exists())

    def test_a_restricted_account_cannot_change_the_contact(self):
        user = self.people['OWNER']
        Sanction.objects.create(
            user=user, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.people['ADMIN'],
            is_active=True,
        )
        self.assert_code(self.get(user), 403, 'DENY_SECURITY')
        self.assert_code(self.put_phone(user, phone=ORG_NUMBER), 403, 'DENY_SECURITY')

    def test_a_suspended_organization_is_refused(self):
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assert_code(self.get(self.people['OWNER']), 403, 'DENY_SECURITY')

    def test_settings_are_isolated_between_contexts_of_one_account(self):
        owner = self.people['OWNER']
        ContactPoint.objects.create(user=owner, phone=MEMBER_CONTACT, is_verified=True)
        self.verified_org_phone(owner)
        personal = self.client_for(owner).get(BASE).json()
        organization = self.get(owner).json()
        self.assertEqual(personal['phone']['masked'], '+243 89 *** ** 33')
        self.assertEqual(organization['phone']['masked'], '+243 89 *** ** 11')
        self.assertEqual(personal['context'], {'type': 'USER', 'id': str(owner.pk)})
        self.assertEqual(organization['context'], {'type': 'ORGANIZATION', 'id': str(self.org.pk)})
        # Chacun garde son propre point de contact : ni fusion, ni écrasement.
        self.assertEqual(ContactPoint.objects.get(user=owner).phone, MEMBER_CONTACT)
        self.assertEqual(ContactPoint.objects.get(organization=self.org).phone, ORG_NUMBER)


class AvailableChannelsTests(OrgContactBase):
    def test_closed_switch_offers_message_only_for_an_organization(self):
        body = self.get(self.people['OWNER']).json()
        self.assertEqual(body['available_channels'], ['MESSAGE'])
        self.assertEqual(body['context'], {'type': 'ORGANIZATION', 'id': str(self.org.pk)})

    def test_open_switch_offers_the_three_channels(self):
        open_switch()
        self.assertEqual(self.get(self.people['OWNER']).json()['available_channels'], ['MESSAGE', 'CALL', 'WHATSAPP'])

    def test_user_and_provider_contexts_always_offer_the_three_channels(self):
        owner = self.people['OWNER']
        profile = ProviderProfile.objects.create(user=owner, display_name='Marie couture')
        client = self.client_for(owner)
        personal = client.get(BASE).json()
        provider = client.get(BASE, HTTP_X_CONTEXT=f'PROVIDER:{profile.pk}').json()
        for body in (personal, provider):
            self.assertEqual(body['available_channels'], ['MESSAGE', 'CALL', 'WHATSAPP'])
        self.assertEqual(provider['context'], {'type': 'PROVIDER', 'id': str(profile.pk)})

    def test_every_response_carries_context_and_channels(self):
        open_switch()
        owner = self.people['OWNER']
        self.sms.reset_mock()
        responses = [
            self.get(owner), self.put_phone(owner, phone=ORG_NUMBER),
            self.channel(owner, 'CALL', enabled=False),
        ]
        for response in responses:
            body = response.json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(body['context']['type'], 'ORGANIZATION')
            self.assertEqual(body['available_channels'], ['MESSAGE', 'CALL', 'WHATSAPP'])

    def test_a_channel_outside_the_available_ones_is_refused_with_its_code(self):
        self.verified_org_phone()
        response = self.channel(self.people['OWNER'], 'WHATSAPP', enabled=True, text_version=VERSION)
        self.assert_code(response, 400, 'channel_not_available')
        self.assertIn('channel', response.json())
        self.assertFalse(ContactConsent.objects.filter(organization=self.org, is_granted=True, channel='WHATSAPP').exists())

    def test_a_stale_consent_can_still_be_withdrawn_when_the_switch_closes(self):
        open_switch()
        self.db_consent('CALL')
        open_switch(False)
        response = self.channel(self.people['OWNER'], 'CALL', enabled=False)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContactConsent.objects.get(organization=self.org, channel='CALL').is_granted)

    def test_message_cannot_be_switched_off_for_an_organization(self):
        self.assert_code(self.channel(self.people['OWNER'], 'MESSAGE', enabled=False), 400, 'message_channel_required')
        self.assertEqual(self.channel(self.people['OWNER'], 'MESSAGE', enabled=True).status_code, 200)
        self.assertTrue(self.get(self.people['OWNER']).json()['channels']['MESSAGE']['enabled'])


class ConsentTests(OrgContactBase):
    def test_consent_keeps_who_granted_it_and_audits_with_the_context(self):
        open_switch()
        admin = self.people['ADMIN']
        self.verified_org_phone(admin)
        self.assertEqual(self.channel(admin, 'CALL', enabled=True, text_version=VERSION).status_code, 200)
        consent = ContactConsent.objects.get(organization=self.org, channel='CALL')
        self.assertEqual((consent.granted_by_id, consent.text_version, consent.phone_last4), (admin.pk, VERSION, '1111'))
        self.assertIsNone(consent.user_id)
        entry = AuditLog.objects.get(action='CONTACT_CHANNEL_CHANGED')
        self.assertEqual((entry.actor_id, entry.context_type, entry.context_id), (admin.pk, 'ORGANIZATION', self.org.pk))
        self.assertEqual((entry.target_type, entry.target_id), ('organization', self.org.pk))
        for forbidden in (ORG_NUMBER, ORG_NUMBER[4:], 'Membre Admin', 'admin@example.com'):
            self.assertNotIn(forbidden, entry.details)

    def test_consent_requires_a_verified_number_and_the_current_text(self):
        open_switch()
        owner = self.people['OWNER']
        self.assert_code(self.channel(owner, 'CALL', enabled=True, text_version=VERSION), 409, 'contact_phone_unverified')
        self.put_phone(owner, phone=ORG_NUMBER)  # non vérifié
        self.assert_code(self.channel(owner, 'CALL', enabled=True, text_version=VERSION), 409, 'contact_phone_unverified')
        self.verify(owner, self.sms.call_args[0][1])
        self.assert_code(self.channel(owner, 'CALL', enabled=True), 400, 'consent_text_required')
        self.assert_code(self.channel(owner, 'CALL', enabled=True, text_version='old'), 400, 'consent_version_mismatch')
        self.assertFalse(ContactConsent.objects.filter(organization=self.org, is_granted=True).exists())

    def test_changing_the_number_revokes_the_consents_automatically(self):
        open_switch()
        owner = self.people['OWNER']
        self.verified_org_phone(owner)
        for channel in ('CALL', 'WHATSAPP'):
            self.assertEqual(self.channel(owner, channel, enabled=True, text_version=VERSION).status_code, 200)
        key = ('ORGANIZATION', self.org.pk)
        self.assertEqual(services.get_context_allowed_channels([key])[key], ['MESSAGE', 'CALL', 'WHATSAPP'])
        response = self.put_phone(owner, phone=NEW_ORG_NUMBER)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body['channels']['CALL']['enabled'])
        self.assertFalse(body['channels']['WHATSAPP']['enabled'])
        self.assertFalse(body['phone']['is_verified'])
        for consent in ContactConsent.objects.filter(organization=self.org, channel__in=('CALL', 'WHATSAPP')):
            self.assertEqual((consent.is_granted, consent.revoked_reason), (False, 'phone_changed'))
        self.assertEqual(services.get_context_allowed_channels([key])[key], ['MESSAGE'])
        actions = list(AuditLog.objects.filter(context_id=self.org.pk).values_list('action', flat=True))
        self.assertIn('CONTACT_PHONE_CHANGED', actions)
        self.assertEqual(actions.count('CONTACT_CHANNEL_CHANGED'), 2 + 2)  # deux accords donnés, deux retirés

    def test_the_same_number_keeps_the_consents(self):
        open_switch()
        owner = self.people['OWNER']
        self.verified_org_phone(owner)
        self.channel(owner, 'CALL', enabled=True, text_version=VERSION)
        self.put_phone(owner, phone=ORG_NUMBER)
        self.assertTrue(ContactConsent.objects.get(organization=self.org, channel='CALL').is_granted)

    def test_the_login_phone_of_a_member_never_becomes_the_organization_number(self):
        owner = self.people['OWNER']
        self.assert_code(self.put_phone(owner, use_login_phone=True), 400, 'login_phone_not_allowed')
        self.assertFalse(ContactPoint.objects.exists())
        body = self.get(owner).json()
        self.assertIsNone(body['login_phone_masked'])
        self.assertFalse(body['can_use_login_phone'])
        self.assertNotIn(owner.phone[4:], json.dumps(body))

    def test_a_member_number_does_not_change_the_organization_channels(self):
        open_switch()
        owner = self.people['OWNER']
        ContactPoint.objects.create(user=owner, phone=MEMBER_CONTACT, is_verified=True)
        for channel in ('CALL', 'WHATSAPP'):
            ContactConsent.objects.create(
                user=owner, channel=channel, is_granted=True, text_version=VERSION, phone_last4=MEMBER_CONTACT[-4:],
            )
        key = ('ORGANIZATION', self.org.pk)
        self.assertEqual(services.get_context_allowed_channels([key])[key], ['MESSAGE'])
        with self.assertRaises(services.ChannelNotConsented):
            services.get_context_contact_endpoint(*key, 'CALL')
        # Le membre change son numéro personnel : rien ne bouge pour l'organisation.
        self.db_consent('CALL')
        self.client_for(owner).put(BASE + 'phone/', {'phone': '+243894444444'}, format='json')
        self.assertEqual(services.get_context_allowed_channels([key])[key], ['MESSAGE', 'CALL'])
        self.assertEqual(services.get_context_contact_endpoint(*key, 'CALL').phone_e164, ORG_NUMBER)


class AllowedChannelsTests(OrgContactBase):
    key = None

    def setUp(self):
        super().setUp()
        self.key = ('ORGANIZATION', self.org.pk)

    def channels(self):
        return services.get_context_allowed_channels([self.key])[self.key]

    def test_default_is_message_to_the_team(self):
        self.assertEqual(self.channels(), ['MESSAGE'])

    def test_closed_switch_hides_a_valid_consent(self):
        self.db_consent('CALL')
        self.db_consent('WHATSAPP')
        self.assertEqual(self.channels(), ['MESSAGE'])
        with self.assertRaises(services.ChannelNotConsented):
            services.get_context_contact_endpoint(*self.key, 'CALL')

    def test_open_switch_and_valid_consent_open_the_number_channels(self):
        open_switch()
        self.db_consent('CALL')
        self.assertEqual(self.channels(), ['MESSAGE', 'CALL'])
        self.db_consent('WHATSAPP')
        self.assertEqual(self.channels(), ['MESSAGE', 'CALL', 'WHATSAPP'])
        self.assertEqual(services.get_context_contact_endpoint(*self.key, 'WHATSAPP').phone_e164, ORG_NUMBER)

    def test_open_switch_without_consent_or_with_an_invalid_one(self):
        open_switch()
        self.assertEqual(self.channels(), ['MESSAGE'])
        self.db_consent('CALL', text_version='ancienne-version')
        self.assertEqual(self.channels(), ['MESSAGE'])
        self.db_consent('CALL', phone_last4='9999')
        self.assertEqual(self.channels(), ['MESSAGE'])
        self.db_consent('CALL')
        ContactPoint.objects.filter(organization=self.org).update(is_verified=False)
        self.assertEqual(self.channels(), ['MESSAGE'])
        with self.assertRaises(services.ChannelNotConsented):
            services.get_context_contact_endpoint(*self.key, 'CALL')

    def test_a_revoked_consent_closes_the_channel(self):
        open_switch()
        self.db_consent('CALL', is_granted=False)
        self.assertEqual(self.channels(), ['MESSAGE'])

    def test_no_channel_without_a_recipient_or_for_an_inactive_organization(self):
        Membership.objects.filter(organization=self.org, role__in=('OWNER', 'ADMIN')).update(
            status=Membership.STATUS_REVOKED,
        )
        self.assertEqual(self.channels(), [])  # reste un éditeur et un analyste : ils ne répondent pas
        Membership.objects.filter(organization=self.org, role='OWNER').update(status=Membership.STATUS_ACTIVE)
        self.assertEqual(self.channels(), ['MESSAGE'])
        User.objects.filter(pk=self.people['OWNER'].pk).update(is_active=False)
        self.assertEqual(self.channels(), [])
        User.objects.filter(pk=self.people['OWNER'].pk).update(is_active=True)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertEqual(self.channels(), [])

    def test_the_result_has_an_entry_for_every_requested_context_and_costs_constant_queries(self):
        open_switch()
        self.db_consent('CALL')

        def build(count):
            keys = []
            for index in range(count):
                org = Organization.objects.create(name=f'Org {index}', org_type='BOUTIQUE')
                user = User.objects.create_user(email=f'o{index}-{count}@example.com', password='x', full_name='O')
                Membership.objects.create(organization=org, user=user, role='OWNER')
                keys.append(('ORGANIZATION', org.pk))
            return keys

        few = build(1) + [self.key]
        with CaptureQueriesContext(connection) as small:
            result = services.get_context_allowed_channels(few)
        self.assertEqual(set(result), set(few))
        many = few + build(6)
        with CaptureQueriesContext(connection) as large:
            services.get_context_allowed_channels(many)
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))

    def test_unknown_or_malformed_context_has_no_channel(self):
        result = services.get_context_allowed_channels([('ORGANIZATION', 'pas-un-uuid')])
        self.assertEqual(list(result.values()), [[]])


class RestrictedAccountAndSwitchTests(OrgContactBase):
    def sanction(self, user):
        Sanction.objects.create(
            user=user, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='Test', issued_by=self.people['ADMIN'],
        )

    def test_a_restricted_personal_account_can_still_withdraw_a_channel_but_not_enable_one(self):
        user = self.people['EDITOR']
        ContactPoint.objects.create(user=user, phone=ORG_NUMBER, is_verified=True)
        ContactConsent.objects.create(
            user=user, channel='CALL', is_granted=True, text_version=VERSION, phone_last4=ORG_NUMBER[-4:],
        )
        self.sanction(user)
        client = self.client_for(user)
        response = client.put(f'{BASE}channels/CALL/', {'enabled': False}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(ContactConsent.objects.get(user=user, channel='CALL').is_granted)
        self.assert_code(
            client.put(f'{BASE}channels/CALL/', {'enabled': True, 'text_version': VERSION}, format='json'),
            403, 'DENY_SECURITY',
        )
        self.assert_code(client.get(BASE), 403, 'DENY_SECURITY')

    def test_a_restricted_provider_context_can_withdraw_a_channel(self):
        user = self.people['EDITOR']
        profile = ProviderProfile.objects.create(user=user, display_name='Marie couture')
        ContactPoint.objects.create(user=user, phone=ORG_NUMBER, is_verified=True)
        ContactConsent.objects.create(
            user=user, channel='WHATSAPP', is_granted=True, text_version=VERSION, phone_last4=ORG_NUMBER[-4:],
        )
        self.sanction(user)
        response = self.client_for(user).put(
            f'{BASE}channels/WHATSAPP/', {'enabled': False}, format='json', HTTP_X_CONTEXT=f'PROVIDER:{profile.pk}',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(ContactConsent.objects.get(user=user, channel='WHATSAPP').is_granted)

    def test_a_restricted_organization_owner_can_withdraw_but_not_enable(self):
        open_switch()
        self.db_consent('CALL')
        owner = self.people['OWNER']
        self.sanction(owner)
        self.assertEqual(self.channel(owner, 'CALL', enabled=False).status_code, 200)
        self.assertFalse(ContactConsent.objects.get(organization=self.org, channel='CALL').is_granted)
        self.assert_code(self.channel(owner, 'CALL', enabled=True, text_version=VERSION), 403, 'DENY_SECURITY')

    def test_closing_the_switch_revokes_the_organization_phone_consents_with_audit(self):
        open_switch()
        self.db_consent('CALL')
        self.db_consent('WHATSAPP')
        key = ('ORGANIZATION', self.org.pk)
        self.assertEqual(services.get_context_allowed_channels([key])[key], ['MESSAGE', 'CALL', 'WHATSAPP'])
        open_switch(False)
        for consent in ContactConsent.objects.filter(organization=self.org):
            self.assertEqual((consent.is_granted, consent.revoked_reason), (False, 'moderation'))
        open_switch(True)  # la réouverture ne réactive rien
        self.assertEqual(services.get_context_allowed_channels([key])[key], ['MESSAGE'])
        entries = AuditLog.objects.filter(action='CONTACT_CHANNEL_CHANGED', context_id=self.org.pk)
        self.assertEqual(entries.count(), 2)
        for entry in entries:
            self.assertNotIn(ORG_NUMBER, entry.details)

    def test_saving_settings_with_the_switch_still_open_revokes_nothing(self):
        open_switch()
        self.db_consent('CALL')
        open_switch(True)
        self.assertTrue(ContactConsent.objects.get(organization=self.org, channel='CALL').is_granted)
