from django.contrib.auth.models import Group
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from apps.common.factories import owner_kwargs
from apps.identity.models import User
from apps.catalog.models import Category, City, Commune, ForbiddenItem
from apps.marketplace.models import Offer
from apps.marketplace.tests import make_test_image

from .models import AuditLog, Report, Sanction


class ModerationTestBase(APITestCase):
    def setUp(self):
        call_command('setup_roles', verbosity=0)
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')

        self.seller = User.objects.create_user(email='seller@example.com', password='x', full_name='Vendeur')
        self.reporter = User.objects.create_user(email='reporter@example.com', password='x', full_name='Rapporteur')
        self.moderator = User.objects.create_user(
            email='mod@example.com', password='x', full_name='Modo', is_staff=True,
        )
        self.moderator.groups.add(Group.objects.get(name='Modérateur'))
        self.admin = User.objects.create_user(
            email='admin@example.com', password='x', full_name='Admin', is_staff=True,
        )
        self.admin.groups.add(Group.objects.get(name='Administrateur'))

        self.post = Offer.objects.create(
            **owner_kwargs(self.seller), category_id=self.category.id, commune_id=self.commune.id,
            title='Un joli canapé à vendre', description='Description suffisamment longue pour le CDC.',
            price=100, main_image=make_test_image(),
        )


class ReportFlowTests(ModerationTestBase):
    def test_any_authenticated_user_can_report_a_post(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post('/api/moderation/reports/', {
            'target_type': 'POST', 'object_id': str(self.post.id), 'reason': 'ARNAQUE', 'description': 'Prix suspect.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], Report.STATUS_EN_ATTENTE)

    def test_report_a_user_by_uuid_and_reject_malformed_id(self):
        self.client.force_authenticate(self.reporter)
        ok = self.client.post('/api/moderation/reports/', {
            'target_type': 'USER', 'object_id': str(self.seller.id), 'reason': 'SPAM',
        })
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED, ok.data)
        self.assertEqual(Report.objects.get(pk=ok.data['id']).target_type, 'user')
        for bad in ('pas-un-uuid', '12'):
            response = self.client.post('/api/moderation/reports/', {
                'target_type': 'USER', 'object_id': bad, 'reason': 'SPAM',
            })
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)

    def test_report_object_id_is_normalized(self):
        self.client.force_authenticate(self.reporter)
        written_forms = (str(self.seller.id).upper(), self.seller.id.hex, f'  {self.seller.id}'.strip())
        for index, written in enumerate(written_forms):
            response = self.client.post('/api/moderation/reports/', {
                'target_type': 'USER', 'object_id': written, 'reason': 'SPAM',
            })
            # Toutes les écritures désignent le même compte : seul le premier signalement est accepté.
            self.assertEqual(response.status_code, 201 if index == 0 else 409, written)
        stored = set(Report.objects.values_list('target_id', flat=True))
        self.assertEqual(stored, {self.seller.id})

    def test_report_rejects_unknown_target(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post('/api/moderation/reports/', {
            'target_type': 'POST', 'object_id': 999999, 'reason': 'ARNAQUE',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_user_cannot_report(self):
        response = self.client.post('/api/moderation/reports/', {
            'target_type': 'POST', 'object_id': str(self.post.id), 'reason': 'ARNAQUE',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_staff_cannot_list_reports(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.get('/api/moderation/reports/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_moderator_can_claim_and_resolve(self):
        report = Report.objects.create(
            target_type='offer', target_id=self.post.id,
            reporter=self.reporter, reason=Report.REASON_ARNAQUE,
        )
        self.client.force_authenticate(self.moderator)

        claim_response = self.client.post(f'/api/moderation/reports/{report.id}/claim/')
        self.assertEqual(claim_response.status_code, status.HTTP_200_OK)
        report.refresh_from_db()
        self.assertEqual(report.status, Report.STATUS_EN_COURS)
        self.assertEqual(report.assigned_to, self.moderator)

        resolve_response = self.client.post(f'/api/moderation/reports/{report.id}/resolve/', {
            'notes': "Annonce vérifiée, pas d'anomalie.",
        })
        self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
        report.refresh_from_db()
        self.assertEqual(report.status, Report.STATUS_TRAITE)
        self.assertIsNotNone(report.resolved_at)

    def test_resolving_a_report_writes_an_audit_log(self):
        report = Report.objects.create(
            target_type='offer', target_id=self.post.id,
            reporter=self.reporter, reason=Report.REASON_ARNAQUE,
        )
        self.client.force_authenticate(self.moderator)
        self.client.post(f'/api/moderation/reports/{report.id}/resolve/', {'notes': 'ok'})
        self.assertTrue(AuditLog.objects.filter(action='REPORT_RESOLVED', actor=self.moderator).exists())


class SanctionRoleTests(ModerationTestBase):
    def test_moderator_can_issue_warning(self):
        self.client.force_authenticate(self.moderator)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_AVERTISSEMENT, 'reason': 'Description imprécise.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_moderator_cannot_ban(self):
        self.client.force_authenticate(self.moderator)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_BANNISSEMENT, 'reason': 'Fraude avérée.',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrator_can_ban(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_BANNISSEMENT, 'reason': 'Fraude avérée.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.seller.refresh_from_db()
        self.assertFalse(self.seller.is_active)

    def test_hiding_a_post_requires_related_post(self):
        self.client.force_authenticate(self.moderator)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_MASQUAGE_ANNONCE, 'reason': 'Produit interdit.',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_hiding_a_post_deactivates_it(self):
        self.client.force_authenticate(self.moderator)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': Sanction.TYPE_MASQUAGE_ANNONCE,
            'related_post': str(self.post.id), 'reason': 'Produit interdit.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_active)

    def test_lifting_a_ban_reactivates_the_user(self):
        self.client.force_authenticate(self.admin)
        sanction = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='x', issued_by=self.admin,
        )
        sanction.apply()
        self.seller.refresh_from_db()
        self.assertFalse(self.seller.is_active)

        response = self.client.post(f'/api/moderation/sanctions/{sanction.id}/lift/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.seller.refresh_from_db()
        self.assertTrue(self.seller.is_active)


class ForbiddenItemPermissionTests(ModerationTestBase):
    def test_anyone_can_list(self):
        ForbiddenItem.objects.create(keyword='arme à feu')
        response = self.client.get('/api/moderation/forbidden-items/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_only_admin_can_create(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.post('/api/moderation/forbidden-items/', {'keyword': 'contrefaçon'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/moderation/forbidden-items/', {'keyword': 'contrefaçon'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class DashboardTests(ModerationTestBase):
    def test_dashboard_requires_staff(self):
        self.client.force_authenticate(self.reporter)
        response = self.client.get('/api/moderation/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_returns_counts(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/moderation/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('pending_reports_count', response.data)


class LiftExpiredSanctionsCommandTests(ModerationTestBase):
    def test_only_expired_temporary_suspensions_are_lifted(self):
        from datetime import timedelta

        from django.core.management import call_command
        from django.utils import timezone

        expired = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='x',
            issued_by=self.admin, ends_at=timezone.now() - timedelta(days=1),
        )
        expired.apply()
        still_running = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='y',
            issued_by=self.admin, ends_at=timezone.now() + timedelta(days=5),
        )

        call_command('lift_expired_sanctions', verbosity=0)

        expired.refresh_from_db()
        still_running.refresh_from_db()
        self.assertFalse(expired.is_active)
        self.assertTrue(still_running.is_active)
        self.seller.refresh_from_db()
        # L0-21 (R0-03) : une autre suspension court toujours, le compte reste bloqué.
        self.assertFalse(self.seller.is_active)
        still_running.lift()
        self.seller.refresh_from_db()
        self.assertTrue(self.seller.is_active)  # plus aucune sanction bloquante -> compte réactivé
        self.assertTrue(AuditLog.objects.filter(action='SANCTION_AUTO_LIFTED').exists())


class OfferDecouplingTests(ModerationTestBase):
    """Les sanctions et signalements désignent l'offre par UUID (ADR 0002)."""

    def test_sanction_rejects_an_unknown_offer(self):
        import uuid

        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': 'MASQUAGE_ANNONCE',
            'related_post': str(uuid.uuid4()), 'reason': 'Produit interdit.',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('related_post', response.data)

    def test_hide_then_lift_restores_the_offer_and_notifies_the_seller(self):
        from apps.notifications.models import Notification

        self.client.force_authenticate(self.admin)
        created = self.client.post('/api/moderation/sanctions/', {
            'user': self.seller.id, 'sanction_type': 'MASQUAGE_ANNONCE',
            'related_post': str(self.post.id), 'reason': 'Produit interdit.',
        })
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(str(created.data['related_post']), str(self.post.id))
        self.assertTrue(Notification.objects.filter(user=self.seller, notification_type='SYSTEM').exists())

        self.client.post(f"/api/moderation/sanctions/{created.data['id']}/lift/")
        self.post.refresh_from_db()
        self.assertTrue(self.post.is_active)

    def test_reports_accept_reviews_and_messages_as_targets(self):
        from apps.messaging.models import Conversation, Message
        review = make_review(self.admin, self.seller)
        conversation = Conversation.objects.create()
        conversation.participants.add(self.admin, self.seller)
        message = Message.objects.create(conversation=conversation, sender=self.seller, content='Salut')
        self.client.force_authenticate(self.reporter)
        for target_type, target in (('REVIEW', review), ('MESSAGE', message), ('USER', self.seller)):
            response = self.client.post('/api/moderation/reports/', {
                'target_type': target_type, 'object_id': str(target.pk), 'reason': 'SPAM',
            })
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, (target_type, response.data))
            self.assertEqual(Report.objects.get(pk=response.data['id']).target_type, target_type.lower())

    def test_automatic_report_is_deduplicated(self):
        from . import services

        review = make_review(self.reporter, self.seller)
        first = services.file_automatic_report('review', review.pk, services.REASON_CROSSED_REVIEWS, 'x')
        self.assertIsNotNone(first)
        self.assertIsNone(services.file_automatic_report('review', review.pk, services.REASON_CROSSED_REVIEWS, 'x'))

    def test_dashboard_counts_active_offers(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get('/api/moderation/dashboard/').data['active_posts_count'], 1)


def make_review(author, seller, **extra):
    """Avis créé directement (la preuve de contact est un UUID, sans clé étrangère)."""
    import uuid
    from django.utils import timezone

    from apps.reviews.models import Review

    values = dict(
        user=author, offer_id=uuid.uuid4(), seller_context_type='USER', seller_context_id=seller.id,
        contact_event_id=uuid.uuid4(), contact_channel='MESSAGE', contact_recorded_at=timezone.now(),
        content='Avis assez long.', offer_rating=3, seller_rating=3,
    )
    values.update(extra)
    return Review.objects.create(**values)
