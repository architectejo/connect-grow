"""Notifications par contexte (ADR 0006, T6 / L0-09f1) : `context` de l'API, abonnés d'équipe, de statut du vendeur
et de décision KYB, purge à la révocation, destinataires d'une organisation, non-fuite."""
import json

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.identity import services as identity_services
from apps.identity.models import Membership, Organization, ProviderProfile, User
from apps.identity.tests_organizations import ADMIN, ANALYST, EDITOR, OWNER, SENTINEL_EMAIL, SENTINEL_NAME, SENTINEL_PHONE
from apps.identity.tests_verification import RCCM, VerificationBase, reviewer
from apps.platform_core.catalog import EVENT_TYPES
from apps.platform_core.models import OutboxEvent
from apps.platform_core.registry import get_subscriber
from apps.platform_core.testing import dispatch_outbox_now

from . import services
from .models import Notification

URL = '/api/interactions/notifications/'


class NotificationContextBase(VerificationBase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()

    def deliver(self):
        dispatch_outbox_now()

    def settle(self):
        """Livre les événements de la mise en place (ajouts de membres) puis repart d'une base vide."""
        self.deliver()
        Notification.objects.all().delete()

    def of(self, user, **filters):
        return Notification.objects.filter(user=user, **filters)

    def listing(self, user, **headers):
        self.api.force_authenticate(user)
        return self.api.get(URL, **headers)


class ApiContextTests(NotificationContextBase):
    def test_personal_notification_has_a_null_context_and_the_other_keys_are_unchanged(self):
        services.notify(user_id=self.owner.pk, notification_type=services.SYSTEM, title='Perso', content='c')
        item = self.listing(self.owner).data[0]
        self.assertIsNone(item['context'])
        self.assertEqual(
            set(item), {'id', 'user', 'notification_type', 'title', 'content', 'link', 'is_read', 'created_at', 'context'},
        )

    def test_user_context_is_always_stored_as_null(self):
        services.notify(
            user_id=self.owner.pk, notification_type=services.SYSTEM, title='x', content='c',
            context=('USER', self.owner.pk),
        )
        notification = Notification.objects.get()
        self.assertEqual((notification.context_type, notification.context_id), (None, None))

    def test_organization_and_provider_contexts_carry_type_id_and_current_name(self):
        profile = ProviderProfile.objects.create(user=self.owner, display_name='Marie couture')
        services.notify(
            user_id=self.owner.pk, notification_type=services.SYSTEM, title='Org', content='c',
            context=('ORGANIZATION', self.org.pk),
        )
        services.notify(
            user_id=self.owner.pk, notification_type=services.SYSTEM, title='Prest', content='c',
            context=('PROVIDER', profile.pk),
        )
        by_title = {item['title']: item['context'] for item in self.listing(self.owner).data}
        self.assertEqual(by_title['Org'], {'type': 'ORGANIZATION', 'id': str(self.org.pk), 'name': 'Atelier Test'})
        self.assertEqual(by_title['Prest'], {'type': 'PROVIDER', 'id': str(profile.pk), 'name': 'Marie couture'})
        Organization.objects.filter(pk=self.org.pk).update(name='Nouveau nom')
        by_title = {item['title']: item['context'] for item in self.listing(self.owner).data}
        self.assertEqual(by_title['Org']['name'], 'Nouveau nom')  # nom actuel, pas un instantané

    def test_name_is_null_when_the_context_no_longer_exists(self):
        profile = ProviderProfile.objects.create(user=self.owner, display_name='Marie couture')
        services.notify(
            user_id=self.owner.pk, notification_type=services.SYSTEM, title='x', content='c',
            context=('PROVIDER', profile.pk),
        )
        ProviderProfile.objects.filter(pk=profile.pk).delete()
        context = self.listing(self.owner).data[0]['context']
        self.assertEqual((context['type'], context['name']), ('PROVIDER', None))

    def test_query_count_does_not_depend_on_the_number_of_contexts(self):
        def counted():
            self.listing(self.owner)  # échauffement
            with CaptureQueriesContext(connection) as captured:
                response = self.listing(self.owner)
            self.assertEqual(response.status_code, 200)
            return len(captured), len(response.data)

        def add(count):
            for index in range(count):
                org = Organization.objects.create(name=f'Org {index}-{Organization.objects.count()}', org_type='ONG')
                Membership.objects.create(organization=org, user=self.owner, role=OWNER)
                services.notify(
                    user_id=self.owner.pk, notification_type=services.SYSTEM, title='t', content='c',
                    context=('ORGANIZATION', org.pk),
                )

        add(2)
        few, count_few = counted()
        add(10)
        many, count_many = counted()
        self.assertEqual((count_few, count_many), (2, 12))
        self.assertEqual(few, many)

    def test_the_context_header_is_ignored(self):
        services.notify(user_id=self.owner.pk, notification_type=services.SYSTEM, title='x', content='c')
        response = self.listing(self.owner, HTTP_X_CONTEXT='n-importe-quoi')
        self.assertEqual((response.status_code, len(response.data)), (200, 1))

    def test_a_member_sees_the_notifications_of_a_suspended_organization(self):
        services.notify(
            user_id=self.owner.pk, notification_type=services.SYSTEM, title='x', content='c',
            context=('ORGANIZATION', self.org.pk),
        )
        Organization.objects.filter(pk=self.org.pk).update(status='SUSPENDED')
        self.assertEqual(len(self.listing(self.owner).data), 1)

    def test_a_notification_of_an_organization_left_is_hidden_even_if_not_purged(self):
        services.notify(
            user_id=self.editor.pk, notification_type=services.SYSTEM, title='Orga', content='c',
            context=('ORGANIZATION', self.org.pk),
        )
        services.notify(user_id=self.editor.pk, notification_type=services.SYSTEM, title='Perso', content='c')
        Membership.objects.filter(user=self.editor).update(status='REVOKED')  # sans événement : la purge n'a pas eu lieu
        self.assertEqual([item['title'] for item in self.listing(self.editor).data], ['Perso'])
        hidden = self.of(self.editor, title='Orga').get()
        self.api.post(f'{URL}mark_all_as_read/')
        hidden.refresh_from_db()
        self.assertFalse(hidden.is_read)  # hors de portée de l'ex-membre, aussi pour « tout marquer lu »
        self.assertEqual(self.api.patch(f'{URL}{hidden.pk}/', {'is_read': True}).status_code, 404)
        self.assertEqual(self.api.delete(f'{URL}{hidden.pk}/').status_code, 404)

    def test_notifications_of_another_user_are_unreachable(self):
        services.notify(
            user_id=self.owner.pk, notification_type=services.SYSTEM, title='x', content='c',
            context=('ORGANIZATION', self.org.pk),
        )
        self.assertEqual(self.listing(self.admin).data, [])


class SanctionTests(NotificationContextBase):
    def test_a_sanctioned_member_is_no_longer_a_recipient(self):
        from apps.moderation.models import Sanction

        Sanction.objects.create(user=self.admin, sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        recipients = identity_services.get_context_recipients('ORGANIZATION', self.org.pk, 'review.reply')
        self.assertEqual(set(recipients), {self.owner.pk, self.editor.pk})
        profile = ProviderProfile.objects.create(user=self.admin, display_name='P')
        self.assertEqual(identity_services.get_context_recipients('PROVIDER', profile.pk, 'review.reply'), [])
        self.assertEqual(identity_services.get_context_recipients('USER', self.admin.pk, 'review.reply'), [])

    def test_a_sanctioned_account_sees_only_its_personal_notifications(self):
        from apps.moderation.models import Sanction

        profile = ProviderProfile.objects.create(user=self.admin, display_name='P')
        for title, context in (
            ('Perso', None), ('Orga', ('ORGANIZATION', self.org.pk)), ('Prest', ('PROVIDER', profile.pk)),
        ):
            services.notify(
                user_id=self.admin.pk, notification_type=services.SYSTEM, title=title, content='c', context=context,
            )
        self.assertEqual({n['title'] for n in self.listing(self.admin).data}, {'Perso', 'Orga', 'Prest'})
        sanction = Sanction.objects.create(user=self.admin, sanction_type='BANNISSEMENT', reason='x')
        self.assertEqual([n['title'] for n in self.listing(self.admin).data], ['Perso'])
        Sanction.objects.filter(pk=sanction.pk).update(is_active=False)  # levée : tout réapparaît
        self.assertEqual(len(self.listing(self.admin).data), 3)


class MembershipNotificationTests(NotificationContextBase):
    def test_added_members_are_told_in_the_organization_context_and_the_creator_is_not(self):
        self.deliver()
        self.assertFalse(self.of(self.owner).exists())  # personne n'est notifié de sa propre action
        for user, label in ((self.admin, 'Administrateur'), (self.editor, 'Éditeur'), (self.analyst, 'Analyste')):
            notification = self.of(user).get()
            self.assertEqual((notification.context_type, notification.context_id), ('ORGANIZATION', self.org.pk))
            self.assertIn(label, notification.content)
            self.assertIn('Atelier Test', notification.content)

    def test_role_change_notifies_the_person_concerned(self):
        self.settle()
        identity_services.change_member_role(self.owner, self.org.pk, self.editor.pk, ADMIN)
        self.deliver()
        notification = self.of(self.editor).get()
        self.assertEqual(notification.title, 'Votre rôle a changé')
        self.assertIn('Administrateur', notification.content)
        self.assertEqual(notification.context_id, self.org.pk)
        self.assertFalse(self.of(self.owner).exists())

    def test_revocation_purges_the_organization_notifications_and_leaves_one_personal_notice(self):
        self.deliver()  # l'éditeur a reçu la notification d'ajout (contexte de l'organisation)
        services.notify(
            user_id=self.editor.pk, notification_type=services.COMMENT, title='Avis', content='c',
            context=('ORGANIZATION', self.org.pk),
        )
        other_org = Organization.objects.create(name='Autre', org_type='ONG')
        Membership.objects.create(organization=other_org, user=self.editor, role=EDITOR)
        services.notify(
            user_id=self.editor.pk, notification_type=services.COMMENT, title='Autre orga', content='c',
            context=('ORGANIZATION', other_org.pk),
        )
        services.notify(user_id=self.editor.pk, notification_type=services.SYSTEM, title='Perso', content='c')
        services.notify(user_id=self.admin.pk, notification_type=services.COMMENT, title='Admin', content='c',
                        context=('ORGANIZATION', self.org.pk))
        identity_services.revoke_member(self.owner, self.org.pk, self.editor.pk)
        self.deliver()
        self.assertFalse(self.of(self.editor, context_id=self.org.pk).exists())
        remaining = sorted(self.of(self.editor).values_list('title', flat=True))
        self.assertEqual(remaining, ['Autre orga', 'Perso', 'Vous ne faites plus partie d\'une organisation'])
        personal = self.of(self.editor, title='Vous ne faites plus partie d\'une organisation').get()
        self.assertEqual((personal.context_type, personal.context_id), (None, None))
        self.assertTrue(self.of(self.admin, title='Admin').exists())  # les autres membres gardent les leurs

    def test_demotion_to_analyst_purges_review_and_expiration_notices_but_keeps_the_rest(self):
        self.settle()
        for kind in (services.COMMENT, services.EXPIRATION, services.SYSTEM):
            services.notify(
                user_id=self.editor.pk, notification_type=kind, title=kind, content='c',
                context=('ORGANIZATION', self.org.pk),
            )
        services.notify(user_id=self.editor.pk, notification_type=services.COMMENT, title='Perso', content='c')
        identity_services.change_member_role(self.owner, self.org.pk, self.editor.pk, ANALYST)
        self.deliver()
        self.deliver()  # idempotent
        titles = set(self.of(self.editor).values_list('title', flat=True))
        self.assertEqual(titles, {'SYSTEM', 'Perso', 'Votre rôle a changé'})

    def test_promotion_or_a_role_keeping_the_capability_purges_nothing(self):
        self.settle()
        services.notify(
            user_id=self.editor.pk, notification_type=services.COMMENT, title='Avis', content='c',
            context=('ORGANIZATION', self.org.pk),
        )
        identity_services.change_member_role(self.owner, self.org.pk, self.editor.pk, ADMIN)
        self.deliver()
        self.assertTrue(self.of(self.editor, title='Avis').exists())

    def test_voluntary_leave_purges_without_notifying_the_leaver(self):
        self.deliver()
        self.assertTrue(self.of(self.editor, context_id=self.org.pk).exists())
        identity_services.leave_organization(self.editor, self.org.pk)
        self.deliver()
        self.assertFalse(self.of(self.editor).exists())

    def test_purge_is_idempotent_and_only_for_revocations(self):
        self.deliver()
        self.assertEqual(services.purge_context_notifications(self.editor.pk, 'ORGANIZATION', self.org.pk), 1)
        self.assertEqual(services.purge_context_notifications(self.editor.pk, 'ORGANIZATION', self.org.pk), 0)
        self.assertEqual(services.purge_context_notifications(self.editor.pk, 'USER', self.editor.pk), 0)

    def test_reactivation_of_a_member_is_announced_in_the_context(self):
        identity_services.revoke_member(self.owner, self.org.pk, self.editor.pk)
        self.deliver()
        Notification.objects.all().delete()
        services.notify(  # ligne périmée d'une ancienne appartenance
            user_id=self.editor.pk, notification_type=services.COMMENT, title='Vieux avis', content='c',
            context=('ORGANIZATION', self.org.pk),
        )
        Notification.objects.filter(title='Vieux avis').update(created_at='2020-01-01T00:00:00+00:00')
        identity_services.add_member(self.owner, self.org.pk, self.editor.pk, EDITOR)
        self.deliver()
        notification = self.of(self.editor).get()  # seule la notification de retour reste
        self.assertEqual(notification.context_id, self.org.pk)
        self.assertEqual(notification.title, 'Vous avez rejoint une organisation')

    def test_delivery_is_exactly_once(self):
        self.deliver()
        count = Notification.objects.count()
        self.deliver()
        self.assertEqual(Notification.objects.count(), count)


class StatusNotificationTests(NotificationContextBase):
    def setUp(self):
        super().setUp()
        self.settle()
        self.staff = self.staff_user()

    def test_suspension_and_reactivation_notify_owners_and_admins_only(self):
        identity_services.suspend_organization(self.staff, self.org.pk, 'moderation')
        self.deliver()
        self.assertEqual({n.user_id for n in Notification.objects.all()}, {self.owner.pk, self.admin.pk})
        for notification in Notification.objects.all():
            self.assertEqual((notification.context_type, notification.context_id), ('ORGANIZATION', self.org.pk))
            self.assertEqual(notification.title, 'Organisation suspendue')
            self.assertNotIn('moderation', notification.content)  # le motif n'est pas repris
        self.assertEqual(len(self.listing(self.owner).data), 1)  # visible malgré la suspension
        Notification.objects.all().delete()
        identity_services.reactivate_organization(self.staff, self.org.pk)
        self.deliver()
        self.assertEqual({n.title for n in Notification.objects.all()}, {'Organisation réactivée'})
        self.assertEqual(Notification.objects.count(), 2)

    def test_archiving_notifies_the_other_managers_not_the_actor(self):
        identity_services.archive_organization(self.owner, self.org.pk)
        self.deliver()
        self.assertEqual(self.of(self.admin).get().title, 'Organisation archivée')
        self.assertFalse(self.of(self.owner).exists())

    def test_no_active_owner_or_admin_means_nobody_is_notified_and_no_failure(self):
        User.objects.filter(pk__in=[self.owner.pk, self.admin.pk]).update(is_active=False)
        identity_services.suspend_organization(self.staff, self.org.pk, 'legal')
        self.deliver()
        self.assertFalse(Notification.objects.exists())
        event = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').latest('created_at')
        self.assertEqual(event.status, 'done')

    def test_other_contexts_and_reasons_produce_no_notification(self):
        profile = ProviderProfile.objects.create(user=self.owner, display_name='Marie couture')
        identity_services.archive_provider(self.owner)
        identity_services.set_account_active(self.analyst.pk, False)
        self.deliver()
        self.assertFalse(Notification.objects.exists())
        self.assertTrue(ProviderProfile.objects.filter(pk=profile.pk).exists())


class KybNotificationTests(NotificationContextBase):
    def setUp(self):
        super().setUp()
        self.settle()
        self.reviewer = reviewer()

    def test_validation_notifies_owners_and_admins_with_the_document_label(self):
        doc = self.make_doc(RCCM)
        self.decide(doc, self.reviewer, 'VALIDE')
        self.deliver()
        self.assertEqual({n.user_id for n in Notification.objects.all()}, {self.owner.pk, self.admin.pk})
        notification = self.of(self.owner).get()
        self.assertEqual(notification.title, 'Pièce de vérification validée')
        self.assertIn('RCCM', notification.content)
        self.assertEqual((notification.context_type, notification.context_id), ('ORGANIZATION', self.org.pk))
        self.assertFalse(self.of(self.editor).exists() or self.of(self.analyst).exists())

    def test_refusal_and_revocation_do_not_repeat_the_reason_or_name_the_reviewer(self):
        doc = self.make_doc(RCCM)
        self.decide(doc, self.reviewer, 'REFUSE', f'Illisible {SENTINEL_PHONE} {SENTINEL_EMAIL}')
        self.deliver()
        refused = self.of(self.owner).get()
        self.assertEqual(refused.title, 'Pièce de vérification refusée')
        doc2 = self.make_doc('ID_NATIONALE')
        self.decide(doc2, self.reviewer, 'VALIDE')
        self.decide(doc2, self.reviewer, 'REFUSE', 'Révoquée')
        self.deliver()
        titles = set(self.of(self.owner).values_list('title', flat=True))
        self.assertIn('Validation d\'une pièce révoquée', titles)
        blob = ' '.join(n.title + n.content for n in Notification.objects.all())
        for secret in (SENTINEL_PHONE, SENTINEL_EMAIL, 'Illisible', self.reviewer.full_name):
            self.assertNotIn(secret, blob)


class NonLeakTests(NotificationContextBase):
    def test_outbox_payloads_and_notifications_carry_no_personal_data(self):
        for index, user in enumerate((self.admin, self.editor)):
            user.full_name = f'{SENTINEL_NAME} {index}'
            user.email = f'{index}-{SENTINEL_EMAIL}'
            user.phone = f'{SENTINEL_PHONE[:-1]}{index}'
            user.save()
        staff = self.staff_user()
        identity_services.change_member_role(self.owner, self.org.pk, self.editor.pk, ANALYST)
        identity_services.revoke_member(self.owner, self.org.pk, self.analyst.pk)
        identity_services.suspend_organization(staff, self.org.pk, 'other')
        doc = self.make_doc(RCCM)
        self.decide(doc, reviewer(), 'VALIDE')
        self.deliver()
        types = (
            'identity.membership_changed', 'identity.seller_context_status_changed',
            'identity.organization_verification_changed',
        )
        for event in OutboxEvent.objects.filter(event_type__in=types):
            serialized = json.dumps(event.payload)
            for secret in (SENTINEL_NAME, SENTINEL_EMAIL, SENTINEL_PHONE[:-1], 'Nom admin', 'Nom editor'):
                self.assertNotIn(secret, serialized)
        for notification in Notification.objects.all():
            blob = notification.title + notification.content + str(notification.link)
            for secret in (SENTINEL_NAME, SENTINEL_EMAIL, SENTINEL_PHONE[:-1], '@'):
                self.assertNotIn(secret, blob)
        self.assertGreater(Notification.objects.count(), 0)


class CatalogTests(NotificationContextBase):
    def test_events_with_a_subscriber_are_no_longer_flagged_and_versions_are_enforced(self):
        for name in (
            'identity.membership_changed', 'identity.seller_context_status_changed',
            'identity.organization_verification_changed',
        ):
            self.assertFalse(EVENT_TYPES[name].no_subscriber, name)
        self.assertEqual(EVENT_TYPES['reviews.review_posted'].version, 3)
        self.assertEqual(EVENT_TYPES['marketplace.offer_expiring_soon'].version, 2)
        self.assertEqual(get_subscriber('notifications.notify_review_posted').versions, (3,))
        self.assertEqual(get_subscriber('notifications.notify_offer_expiration').versions, (2,))
        for name in (
            'notifications.notify_membership_change', 'notifications.purge_context_notifications',
            'notifications.notify_organization_status', 'notifications.notify_kyb_decision',
        ):
            self.assertIsNotNone(get_subscriber(name), name)
