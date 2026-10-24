"""Contact d'une offre d'organisation par un acheteur (ADR 0006, T7 / L0-09f2) : message routé vers l'équipe habilitée,
révélation du numéro DE L'ORGANISATION (jamais celui d'un membre), quotas conservés, événements en version 2, aucune
fuite de données de membre dans l'audit, l'outbox, les notifications ni les conversations."""
import json
from datetime import timedelta

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.identity.models import (
    CONTACT_CONSENT_TEXT_VERSION, ContactConsent, ContactPoint, IdentitySettings, Membership, Organization, User,
)
from apps.messaging.models import Conversation, Message
from apps.moderation.models import AuditLog
from apps.notifications.models import Notification
from apps.platform_core import registry
from apps.platform_core.models import OutboxEvent
from apps.platform_core.testing import dispatch_outbox_now

from .models import ContactEvent, MarketplaceSettings
from .tests_contexts import ContextBase

ORG_NUMBER = '+243891111111'
MEMBER_NUMBERS = {'OWNER': '+243970000001', 'ADMIN': '+243970000002', 'EDITOR': '+243970000003', 'ANALYST': '+243970000004'}
MEMBER_CONTACT_NUMBER = '+243893333333'


class OrgContactBase(ContextBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.team = {}
        for role in ('OWNER', 'ADMIN', 'EDITOR', 'ANALYST'):
            user = User.objects.create_user(
                email=f'{role.lower()}-secret@example.com', phone=MEMBER_NUMBERS[role], password='x',
                full_name=f'Membre {role.title()}', phone_verified=True,
            )
            self.join(user, role=role)
            self.team[role] = user
        old = timezone.now() - timedelta(days=30)
        User.objects.filter(pk=self.buyer.pk).update(phone_verified=True, date_joined=old)
        self.buyer.refresh_from_db()
        self.offer = self.org_offer(creator=self.team['EDITOR'])
        self.client.force_authenticate(self.buyer)

    def contact(self, offer=None, message='Bonjour, je suis intéressé'):
        return self.client.post(reverse('contact-list'), {'post': str((offer or self.offer).id), 'message': message})

    def get_offer(self, offer):
        """Fiche publique (anonyme), puis retour à l'acheteur."""
        self.client.force_authenticate(None)
        data = self.client.get(reverse('offer-detail', args=[offer.id])).data
        self.client.force_authenticate(self.buyer)
        return data

    def reveal(self, channel='CALL', offer=None):
        return self.client.post(
            reverse('contact-reveal'), {'offer': str((offer or self.offer).id), 'channel': channel}, format='json',
        )

    def open_phone_channels(self, channels=('CALL', 'WHATSAPP')):
        IdentitySettings.objects.update_or_create(
            pk=IdentitySettings.SINGLETON_ID, defaults={'org_phone_channels_enabled': True},
        )
        ContactPoint.objects.update_or_create(
            organization=self.org, defaults={'phone': ORG_NUMBER, 'is_verified': True, 'verified_at': timezone.now()},
        )
        for channel in channels:
            ContactConsent.objects.update_or_create(
                organization=self.org, channel=channel,
                defaults={
                    'is_granted': True, 'text_version': CONTACT_CONSENT_TEXT_VERSION, 'granted_at': timezone.now(),
                    'phone_last4': ORG_NUMBER[-4:], 'granted_by': self.team['OWNER'],
                },
            )

    def give_members_personal_contact(self):
        """Chaque membre a un numéro de contact personnel vérifié avec CALL et WHATSAPP consentis : rien de cela ne
        doit jamais sortir au titre d'une offre de l'organisation."""
        for user in self.team.values():
            ContactPoint.objects.create(user=user, phone=MEMBER_CONTACT_NUMBER, is_verified=True)
            for channel in ('CALL', 'WHATSAPP'):
                ContactConsent.objects.create(
                    user=user, channel=channel, is_granted=True, text_version=CONTACT_CONSENT_TEXT_VERSION,
                    granted_at=timezone.now(), phone_last4=MEMBER_CONTACT_NUMBER[-4:],
                )

    def secrets(self):
        values = [MEMBER_CONTACT_NUMBER, MEMBER_CONTACT_NUMBER[4:], *MEMBER_NUMBERS.values()]
        values += [f'{role.lower()}-secret@example.com' for role in self.team]
        return values

    def stored_texts(self):
        return [
            *(f'{a.action} {a.details}' for a in AuditLog.objects.all()),
            *(json.dumps(e.payload) for e in OutboxEvent.objects.all()),
            *(f'{n.title} {n.content} {n.link}' for n in Notification.objects.all()),
            *(m.content for m in Message.objects.all()),
        ]

    def assert_no_secret(self, *extra):
        for text in [*self.stored_texts(), *extra]:
            for secret in self.secrets():
                self.assertNotIn(secret, text)


class ContactRoutingTests(OrgContactBase):
    def test_the_offer_exposes_message_as_its_only_channel_even_with_member_numbers(self):
        self.give_members_personal_contact()
        self.client.force_authenticate(None)
        data = self.get_offer(self.offer)
        self.assertEqual(data['allowed_channels'], ['MESSAGE'])
        self.assertNotIn(MEMBER_CONTACT_NUMBER, json.dumps(data, default=str))

    def test_a_buyer_contacts_an_organization_offer_and_the_team_receives_it(self):
        response = self.contact()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        dispatch_outbox_now()
        dispatch_outbox_now()  # la preuve de remise est posée par un second événement
        conversation = Conversation.objects.get()
        self.assertEqual((conversation.seller_context_type, conversation.seller_context_id), ('ORGANIZATION', self.org.pk))
        self.assertEqual(list(conversation.participants.all()), [self.buyer])  # aucun membre copié
        message = Message.objects.get()
        self.assertEqual((message.sender, message.content, message.sender_context_type), (
            self.buyer, 'Bonjour, je suis intéressé', None,
        ))
        notified = set(Notification.objects.values_list('user_id', flat=True))
        self.assertEqual(notified, {self.team['OWNER'].pk, self.team['ADMIN'].pk})  # message.reply : propriétaire, admin
        for notification in Notification.objects.all():
            self.assertEqual((notification.context_type, notification.context_id), ('ORGANIZATION', self.org.pk))
            self.assertEqual(notification.notification_type, 'CONTACT')
        # La preuve de remise (ADR 0005, C10) est conservée.
        self.assertIsNotNone(ContactEvent.objects.get().delivered_at)

    def test_delivery_proof_and_conversation_are_not_duplicated_by_a_replay(self):
        self.contact()
        dispatch_outbox_now()
        dispatch_outbox_now()
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)

    def test_recipients_are_resolved_at_delivery_not_at_publication(self):
        self.assertEqual(self.contact().status_code, status.HTTP_201_CREATED)
        Membership.objects.filter(user=self.team['ADMIN'], organization=self.org).update(
            status=Membership.STATUS_REVOKED,
        )
        dispatch_outbox_now()
        self.assertEqual(set(Notification.objects.values_list('user_id', flat=True)), {self.team['OWNER'].pk})

    def test_events_are_version_2_without_account_or_personal_data(self):
        self.give_members_personal_contact()
        self.contact()
        event = OutboxEvent.objects.get(event_type='marketplace.contact_recorded')
        self.assertEqual(event.version, 2)
        self.assertNotIn('seller_id', event.payload)
        self.assertEqual(event.payload['seller_context_type'], 'ORGANIZATION')
        self.assertEqual(event.payload['seller_context_id'], str(self.org.pk))
        blob = json.dumps(event.payload)
        for user in self.team.values():
            self.assertNotIn(str(user.pk), blob)
        dispatch_outbox_now()
        self.assert_no_secret()

    def test_subscribers_accept_versions_1_and_2_only(self):
        for name in ('messaging.open_contact_conversation', 'messaging.open_exchange_conversation',
                     'notifications.notify_contact', 'notifications.notify_contact_revealed',
                     'notifications.notify_exchange'):
            self.assertEqual(registry.get_subscriber(name).versions, (1, 2), name)  # v1 encore en file : lue en USER

    def test_no_secret_in_audit_outbox_notifications_or_conversation_after_a_contact(self):
        self.give_members_personal_contact()
        self.contact()
        dispatch_outbox_now()
        self.assert_no_secret()
        self.assertTrue(Notification.objects.exists())  # témoin positif : des notifications ont bien été créées

    def test_an_exchange_proposal_goes_to_the_team_too(self):
        self.enable_exchange()
        response = self.client.post(reverse('exchange-list'), {'post': str(self.offer.id), 'message': 'Troc ?'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        dispatch_outbox_now()
        self.assertEqual(
            set(Notification.objects.filter(notification_type='EXCHANGE').values_list('user_id', flat=True)),
            {self.team['OWNER'].pk, self.team['ADMIN'].pk},
        )
        self.assertEqual(Message.objects.get().content, "[PROPOSITION D'ÉCHANGE] Troc ?")

    def test_the_team_member_cannot_contact_his_own_organization(self):
        self.client.force_authenticate(self.team['EDITOR'])
        response = self.contact()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_a_former_member_may_contact_the_organization_like_anyone(self):
        former = User.objects.create_user(email='former@example.com', password='x', full_name='Ancien')
        Membership.objects.create(organization=self.org, user=former, role='EDITOR', status=Membership.STATUS_REVOKED)
        self.client.force_authenticate(former)
        self.assertEqual(self.contact().status_code, status.HTTP_201_CREATED)

    def test_without_any_recipient_the_dedicated_refusal_remains(self):
        Membership.objects.filter(organization=self.org, role__in=('OWNER', 'ADMIN')).update(
            status=Membership.STATUS_REVOKED,
        )
        for response in (self.contact(), self.reveal('CALL')):
            self.assertEqual((response.status_code, response.data['code']), (403, 'seller_contact_unavailable'))
        self.assertEqual(ContactEvent.objects.count(), 0)
        self.client.force_authenticate(None)
        self.assertEqual(self.get_offer(self.offer)['allowed_channels'], [])


class RevealTests(OrgContactBase):
    def test_closed_switch_refuses_the_reveal_and_never_falls_back_to_a_member_number(self):
        self.give_members_personal_contact()
        self.open_phone_channels()
        IdentitySettings.objects.filter(pk=IdentitySettings.SINGLETON_ID).update(org_phone_channels_enabled=False)
        for channel in ('CALL', 'WHATSAPP'):
            response = self.reveal(channel=channel)
            self.assertEqual((response.status_code, response.data['code']), (403, 'channel_not_allowed'))
            self.assertNotIn(ORG_NUMBER, json.dumps(response.data))
            self.assertNotIn(MEMBER_CONTACT_NUMBER, json.dumps(response.data))
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_a_member_number_is_never_revealed_without_the_organization_own_consent(self):
        self.give_members_personal_contact()
        IdentitySettings.objects.update_or_create(
            pk=IdentitySettings.SINGLETON_ID, defaults={'org_phone_channels_enabled': True},
        )
        self.client.force_authenticate(None)
        self.assertEqual(self.get_offer(self.offer)['allowed_channels'], ['MESSAGE'])
        self.client.force_authenticate(self.buyer)
        response = self.reveal('CALL')
        self.assertEqual((response.status_code, response.data['code']), (403, 'channel_not_allowed'))
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_open_switch_and_consent_reveal_the_organization_number_only(self):
        self.give_members_personal_contact()
        self.open_phone_channels()
        self.client.force_authenticate(None)
        self.assertEqual(self.get_offer(self.offer)['allowed_channels'], ['MESSAGE', 'CALL', 'WHATSAPP'])
        self.client.force_authenticate(self.buyer)
        response = self.reveal('CALL')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['phone'], ORG_NUMBER)
        self.assertEqual(response['Cache-Control'], 'no-store')
        # Un renvoi dans la fenêtre : même contact, aucun nouveau plafond consommé.
        again = self.reveal('CALL')
        self.assertEqual((again.status_code, again.data['created']), (200, False))
        dispatch_outbox_now()
        for text in self.stored_texts():
            self.assertNotIn(ORG_NUMBER, text)
            self.assertNotIn(ORG_NUMBER[4:], text)
        self.assert_no_secret()
        audit = AuditLog.objects.filter(action='contact.number_revealed')
        self.assertEqual(audit.count(), 2)
        self.assertTrue(all(f'ORGANIZATION:{self.org.pk}' in entry.details for entry in audit))

    def test_the_requesters_are_notified_by_capability_and_the_analyst_is_not(self):
        self.open_phone_channels()
        self.reveal('CALL')
        dispatch_outbox_now()
        notified = set(Notification.objects.filter(title='Votre numéro a été demandé').values_list('user_id', flat=True))
        self.assertEqual(notified, {self.team[r].pk for r in ('OWNER', 'ADMIN', 'EDITOR')})
        for notification in Notification.objects.all():
            self.assertNotIn(ORG_NUMBER, notification.content)
            self.assertEqual(notification.context_id, self.org.pk)

    def test_revocation_of_the_consent_closes_the_reveal(self):
        self.open_phone_channels()
        ContactConsent.objects.filter(organization=self.org, channel='CALL').update(is_granted=False)
        response = self.reveal('CALL')
        self.assertEqual((response.status_code, response.data['code']), (403, 'channel_not_allowed'))
        self.assertEqual(self.reveal('WHATSAPP').status_code, 201)

    def test_reveal_quotas_still_apply_to_the_buyer_account(self):
        self.open_phone_channels()
        MarketplaceSettings.objects.filter(pk=MarketplaceSettings.get_solo().pk).update(reveal_daily_limit_account=1)
        other = self.org_offer(creator=self.team['EDITOR'], title='Une seconde offre de l organisation')
        self.assertEqual(self.reveal('CALL', self.offer).status_code, 201)
        response = self.reveal('CALL', other)
        self.assertEqual((response.status_code, response.data['code']), (429, 'reveal_quota_account'))
        self.assertIn('Retry-After', response)
        self.assertEqual(ContactEvent.objects.count(), 1)
        self.assertTrue(AuditLog.objects.filter(action='contact.reveal_quota_exceeded').exists())

    def test_the_refusal_is_audited_once_per_day_without_number(self):
        self.give_members_personal_contact()
        self.reveal('CALL')
        self.reveal('CALL')
        refused = AuditLog.objects.filter(action='contact.reveal_refused')
        self.assertEqual(refused.count(), 1)
        self.assert_no_secret()

    def test_a_member_cannot_reveal_the_number_of_his_own_organization(self):
        self.open_phone_channels()
        self.client.force_authenticate(self.team['ANALYST'])
        response = self.reveal('CALL')
        self.assertEqual((response.status_code, response.data['code']), (403, 'own_offer'))

    def test_a_suspended_organization_offer_is_not_revealable(self):
        self.open_phone_channels()
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        type(self.offer).objects.filter(pk=self.offer.pk).update(seller_is_public=False)
        self.assertEqual(self.reveal('CALL').status_code, 404)


class SuspendedOrganizationAndEventTests(OrgContactBase):
    def test_buyer_writes_to_a_suspended_or_archived_organization_are_refused(self):
        self.enable_exchange()
        for state, code in ((Organization.STATUS_SUSPENDED, 'DENY_SECURITY'), (Organization.STATUS_ARCHIVED, 'DENY_OBJECT_STATE')):
            with self.subTest(state=state):
                Organization.objects.filter(pk=self.org.pk).update(status=state)  # le drapeau de l'offre reste vrai
                contact = self.contact()
                self.assertEqual((contact.status_code, contact.data['code']), (403, code))
                exchange = self.client.post(reverse('exchange-list'), {'post': str(self.offer.id), 'message': 'Troc ?'})
                self.assertEqual((exchange.status_code, exchange.data['code']), (403, code))
                reveal = self.reveal('CALL')
                self.assertEqual((reveal.status_code, reveal.data['code']), (403, code))
        self.assertEqual(ContactEvent.objects.count(), 0)

    def test_the_team_sees_the_buyer_under_an_abbreviated_name(self):
        User.objects.filter(pk=self.buyer.pk).update(full_name='Marie Kabongo')
        self.contact()
        dispatch_outbox_now()
        notification = Notification.objects.filter(user=self.team['OWNER']).get()
        self.assertIn('Marie K.', notification.content)
        self.assertNotIn('Kabongo', notification.content)

    def test_version_1_events_still_in_the_queue_are_read_as_a_user_context(self):
        from apps.notifications import events as notification_events
        from apps.platform_core.registry import EventData, PermanentEventError
        import uuid

        payload = {
            'offer_id': str(self.offer.id), 'offer_title': 'Un titre', 'seller_id': str(self.team['EDITOR'].pk),
            'sender_id': str(self.buyer.pk),
        }
        event = EventData(uuid.uuid4(), 'marketplace.contact_recorded', 1, payload, timezone.now())
        notification_events.notify_contact(event)
        self.assertEqual(Notification.objects.get().user_id, self.team['EDITOR'].pk)
        bad = EventData(
            uuid.uuid4(), 'marketplace.contact_recorded', 2,
            {**payload, 'seller_context_type': 'NOPE', 'seller_context_id': str(self.org.pk)}, timezone.now(),
        )
        with self.assertRaises(PermanentEventError):
            notification_events.notify_contact(bad)
