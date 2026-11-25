"""Garde, volume, vues uniques et fichiers de la purge des contextes (L0-09 T9-3, corrections après relecture et audit)."""
import datetime
import uuid
from unittest import mock

from django.contrib import admin
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.test import RequestFactory
from django.utils import timezone

from apps.common.factories import owner_kwargs
from apps.messaging.models import Conversation, Message
from apps.marketplace import services as marketplace_services
from apps.marketplace.models import ContactEvent, ExchangeProposal, Favorite, Offer, OfferImage
from apps.moderation.models import AuditLog, Report, Sanction
from apps.platform_core.models import OutboxEvent
from apps.platform_core.registry import PermanentEventError
from apps.reviews.models import Review
from apps.visibility.models import DailyVisibilityCounter, OfferUniqueView

from . import services
from .admin import UserAdmin
from .models import Membership, Organization, ProviderProfile, User
from .tests_context_purge import PurgeBase


class DeletionGuardTests(PurgeBase):
    """Une suppression est refusée tant qu'il y a des preuves à garder : signalement grave ouvert ou sanction en cours."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            email='root@example.com', password='x', full_name='Admin', is_staff=True, is_superuser=True,
        )
        self.model_admin = UserAdmin(User, admin.site)
        self.offer, self.gallery = self.build_user_world()

    def request(self):
        request = RequestFactory().post('/')
        request.user = self.staff
        return request

    def report(self, target_type, target_id, reason='ARNAQUE', status='EN_ATTENTE'):
        return Report.objects.create(
            target_type=target_type, target_id=target_id, reporter=self.buyer, reason=reason, status=status,
        )

    def assert_refused(self, code):
        with self.assertRaises(services.OrganizationError) as caught:
            with transaction.atomic():  # le refus annule la suppression : point de reprise pour la suite du test
                self.seller.delete()
        self.assertEqual(caught.exception.detail.code, code)
        self.assertTrue(User.objects.filter(pk=self.seller.pk).exists())
        self.assertEqual(self.residue('USER', self.seller.pk)['offers'], 1)
        self.assertFalse(OutboxEvent.objects.filter(event_type='identity.seller_context_removed').exists())

    def test_grave_report_on_the_account_blocks_deletion_until_closed(self):
        report = self.report('user', self.seller.pk)
        self.assert_refused('open_grave_report')
        report.resolve('ok')
        seller_pk = self.seller.pk
        self.seller.delete()
        self.assertFalse(User.objects.filter(pk=seller_pk).exists())

    def test_grave_report_on_one_of_its_offers_blocks_deletion(self):
        report = self.report('offer', self.offer.pk, reason='CONTENU_INTERDIT', status='EN_COURS')
        self.assert_refused('open_grave_report')
        report.reject('non fondé')
        seller_pk = self.seller.pk
        self.seller.delete()
        self.assertEqual(self.residue('USER', seller_pk)['offers'], 0)

    def test_grave_report_on_a_received_review_blocks_deletion(self):
        review = Review.objects.get(seller_context_id=self.seller.pk)
        report = self.report('review', review.pk, reason='AVIS_CROISES')
        self.assert_refused('open_grave_report')
        report.resolve()
        self.seller.delete()
        self.assertFalse(Review.objects.filter(pk=review.pk).exists())

    def test_non_grave_report_does_not_block(self):
        self.report('offer', self.offer.pk, reason='SPAM')
        seller_pk = self.seller.pk
        self.seller.delete()
        self.assertEqual(self.residue('USER', seller_pk)['offers'], 0)

    def test_grave_report_on_a_provider_offer_blocks_account_and_provider_deletion(self):
        provider = ProviderProfile.objects.create(user=self.seller, display_name='Marie couture')
        provider_offer = self.make_offer(**owner_kwargs(provider, 'PROVIDER', created_by=self.seller))
        report = self.report('offer', provider_offer.pk)
        with self.assertRaises(services.OrganizationError) as caught:
            with transaction.atomic():
                provider.delete()
        self.assertEqual(caught.exception.detail.code, 'open_grave_report')
        self.assert_refused('open_grave_report')
        report.resolve()
        provider.delete()
        self.assertFalse(Offer.objects.filter(pk=provider_offer.pk).exists())

    def test_blocking_sanction_blocks_deletion_until_lifted(self):
        sanction = Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='x', issued_by=self.staff,
        )
        self.assert_refused('blocking_sanction')
        sanction.is_active = False
        sanction.save(update_fields=['is_active'])
        seller_pk = self.seller.pk
        self.seller.delete()
        self.assertFalse(User.objects.filter(pk=seller_pk).exists())

    def test_a_warning_does_not_block(self):
        Sanction.objects.create(
            user=self.seller, sanction_type=Sanction.TYPE_AVERTISSEMENT, reason='x', issued_by=self.staff,
        )
        self.seller.delete()

    def test_admin_refusal_is_audited_without_personal_data(self):
        self.report('user', self.seller.pk)
        with mock.patch.object(self.model_admin, 'message_user') as error:
            self.model_admin.delete_model(self.request(), self.seller)  # pas d'exception, pas de 500
        self.assertTrue(error.called)
        with mock.patch.object(self.model_admin, 'message_user') as message:
            self.model_admin.delete_queryset(self.request(), User.objects.filter(pk=self.seller.pk))
        self.assertTrue(message.called)
        entries = AuditLog.objects.filter(action='USER_ADMIN_DELETE_REFUSED')
        self.assertEqual(entries.count(), 2)
        for entry in entries:
            self.assertEqual(entry.actor, self.staff)
            self.assertEqual(entry.details, 'code=open_grave_report')
        self.assertFalse(AuditLog.objects.filter(action='USER_ADMIN_DELETED').exists())
        self.assertTrue(User.objects.filter(pk=self.seller.pk).exists())


class DefenseInDepthTests(PurgeBase):
    def test_purge_of_a_live_context_is_refused(self):
        offer, _ = self.build_user_world()
        provider = ProviderProfile.objects.create(user=self.seller, display_name='Marie')
        with self.assertRaises(PermanentEventError):
            marketplace_services.purge_seller_context('USER', self.seller.pk)
        with self.assertRaises(PermanentEventError):
            marketplace_services.purge_seller_context('PROVIDER', provider.pk)
        self.assertTrue(Offer.objects.filter(pk=offer.pk).exists())

    def test_unknown_context_is_still_a_noop(self):
        self.assertEqual(marketplace_services.purge_seller_context('USER', uuid.uuid4())['offers'], 0)


class VolumeTests(PurgeBase):
    def test_purge_of_more_than_a_thousand_offers_with_attachments(self):
        total = 1100
        Offer.objects.bulk_create([
            Offer(
                category_id=self.category.id, commune_id=self.commune.id, title=f'Offre numéro {i:05d}',
                description='Description suffisamment longue pour passer la validation du CDC.', price=1,
                main_image='offers/absent.webp', **owner_kwargs(self.seller),
            )
            for i in range(total)
        ])
        offer_ids = list(Offer.objects.filter(seller_context_id=self.seller.pk).values_list('id', flat=True))
        self.assertEqual(len(offer_ids), total)
        day = datetime.date(2026, 1, 1)
        Favorite.objects.bulk_create([Favorite(user=self.buyer, offer_id=i) for i in offer_ids])
        ContactEvent.objects.bulk_create([ContactEvent(offer_id=i, sender=self.buyer) for i in offer_ids])
        ExchangeProposal.objects.bulk_create(
            [ExchangeProposal(offer_id=i, sender=self.buyer, message='x') for i in offer_ids]
        )
        OfferImage.objects.bulk_create([OfferImage(offer_id=i, image='offers/gallery/absent.webp') for i in offer_ids])
        OfferUniqueView.objects.bulk_create([OfferUniqueView(offer_id=i, viewer_key='user:x', date=day) for i in offer_ids])
        DailyVisibilityCounter.objects.bulk_create([
            DailyVisibilityCounter(
                offer_id=i, date=day, seller_context_type='USER', seller_context_id=self.seller.pk,
            ) for i in offer_ids
        ])
        seller_pk = self.seller.pk
        self.seller.delete()
        self.assertEqual(self.residue('USER', seller_pk), self.zero())
        self.assertEqual(OfferImage.objects.count() + Favorite.objects.count() + ContactEvent.objects.count(), 0)
        self.assertEqual(
            AuditLog.objects.get(action='SELLER_CONTEXT_PURGED_MARKETPLACE').details,
            f'offers={total}; images={total}; favorites={total}; contacts={total}; exchanges={total}',
        )

    def test_delete_offers_works_by_batches(self):
        with mock.patch.object(marketplace_services, 'DELETE_BATCH_SIZE', 2):
            for i in range(5):
                self.make_offer(**owner_kwargs(self.seller), title=f'Offre numéro {i:05d}')
            self.assertEqual(marketplace_services.delete_offers(Offer.objects.filter(seller_context_id=self.seller.pk)), 5)
        self.assertFalse(Offer.objects.filter(seller_context_id=self.seller.pk).exists())


class OtherSellersViewsTests(PurgeBase):
    def test_unique_views_made_by_the_account_on_other_sellers_offers_are_purged(self):
        other_offer = self.make_offer(**owner_kwargs(self.buyer))
        day = datetime.date(2026, 1, 1)
        for key in (f'user:{self.seller.pk}', f'share:user:{self.seller.pk}', 'user:someone-else', 'anon:abc'):
            OfferUniqueView.objects.create(offer_id=other_offer.pk, viewer_key=key, date=day)
        seller_pk = self.seller.pk
        self.seller.delete()
        self.assertEqual(
            set(OfferUniqueView.objects.filter(offer_id=other_offer.pk).values_list('viewer_key', flat=True)),
            {'user:someone-else', 'anon:abc'},
        )
        entry = AuditLog.objects.get(action='SELLER_CONTEXT_PURGED_VISIBILITY')
        self.assertEqual(entry.details, 'counters=0; unique_views=2')
        self.assertEqual(entry.context_id, seller_pk)


class FileRemovalTests(PurgeBase):
    def test_trash_purge_removes_files(self):
        offer, gallery = self.build_user_world()
        storage = offer.main_image.storage
        names = [offer.main_image.name, gallery.image.name]
        Offer.objects.filter(pk=offer.pk).update(is_deleted=True, deleted_at=timezone.now() - datetime.timedelta(days=90))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(marketplace_services.purge_expired_trash(retention_days=30), 1)
        self.assertFalse(any(storage.exists(name) for name in names))

    def test_deleting_a_gallery_image_removes_its_file(self):
        offer, gallery = self.build_user_world()
        storage = gallery.image.storage
        name = gallery.image.name
        self.assertTrue(storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(marketplace_services.delete_offer_image(offer, actor=self.seller, image_id=gallery.pk))
        self.assertFalse(storage.exists(name))
        self.assertTrue(storage.exists(offer.main_image.name))

    def test_account_whose_offers_are_already_in_the_trash_is_purged(self):
        offer, gallery = self.build_user_world()
        Offer.objects.filter(pk=offer.pk).update(is_deleted=True, deleted_at=timezone.now())
        seller_pk = self.seller.pk
        storage = offer.main_image.storage
        name = offer.main_image.name
        with self.captureOnCommitCallbacks(execute=True):
            self.seller.delete()
        self.assertEqual(self.residue('USER', seller_pk), self.zero())
        self.assertFalse(storage.exists(name))


class AuthoredEvidenceTests(PurgeBase):
    """Avis écrits et messages envoyés par le compte (cascade de clé étrangère) : preuves à conserver."""

    def setUp(self):
        super().setUp()
        self.other_offer = self.make_offer(**owner_kwargs(self.buyer))

    def write_review(self):
        return Review.objects.create(
            user=self.seller, offer_id=self.other_offer.pk, seller_context_type='USER', seller_context_id=self.buyer.pk,
            contact_event_id=uuid.uuid4(), contact_channel='MESSAGE', contact_recorded_at=timezone.now(),
            offer_rating=1, seller_rating=1, content='Avis écrit par le compte supprimé, assez long.',
        )

    def test_grave_report_on_a_review_written_by_the_account_blocks_deletion(self):
        review = self.write_review()
        report = Report.objects.create(
            target_type='review', target_id=review.pk, reporter=self.buyer, reason='HARCELEMENT',
        )
        with self.assertRaises(services.OrganizationError) as caught:
            with transaction.atomic():
                self.seller.delete()
        self.assertEqual(caught.exception.detail.code, 'open_grave_report')
        report.resolve()
        self.seller.delete()

    def test_grave_report_on_a_message_sent_by_the_account_blocks_deletion(self):
        conversation = Conversation.objects.create()
        conversation.participants.add(self.seller, self.buyer)
        message = Message.objects.create(conversation=conversation, sender=self.seller, content='Propos signalés')
        report = Report.objects.create(
            target_type='message', target_id=message.pk, reporter=self.buyer, reason='HARCELEMENT',
        )
        with self.assertRaises(services.OrganizationError) as caught:
            with transaction.atomic():
                self.seller.delete()
        self.assertEqual(caught.exception.detail.code, 'open_grave_report')
        report.reject()
        self.seller.delete()


class SuspendedOrganizationTests(PurgeBase):
    def test_sole_owner_of_a_suspended_organization_cannot_be_deleted(self):
        Membership.objects.filter(user=self.other_owner).delete()
        Membership.objects.filter(user=self.seller).update(role='OWNER')
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        with self.assertRaises(services.OrganizationError) as caught:
            services.assert_account_removable(self.seller)
        self.assertEqual(caught.exception.detail.code, 'last_owner_account')

    def test_archived_organization_does_not_block(self):
        Membership.objects.filter(user=self.other_owner).delete()
        Membership.objects.filter(user=self.seller).update(role='OWNER')
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ARCHIVED)
        services.assert_account_removable(self.seller)

    def test_guard_query_count_does_not_depend_on_the_number_of_organizations(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                services.assert_account_removable(self.seller)
            return len(queries)

        Membership.objects.filter(user=self.seller).update(role='OWNER')
        before = count()
        for i in range(4):
            org = Organization.objects.create(name=f'Autre {i}', org_type='ENTREPRISE')
            Membership.objects.create(organization=org, user=self.seller, role='OWNER')
            Membership.objects.create(organization=org, user=self.buyer, role='OWNER')
        self.assertEqual(count(), before)

    def test_last_owner_message_of_a_suspended_organization_explains_the_way_out(self):
        Membership.objects.filter(user=self.other_owner).delete()
        Membership.objects.filter(user=self.seller).update(role='OWNER')
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        with self.assertRaises(services.OrganizationError) as caught:
            services.leave_organization(self.seller, self.org.pk)
        self.assertEqual(caught.exception.detail.code, 'last_owner')
        self.assertIn('suspendue', str(caught.exception.detail))
        self.assertIn('support', str(caught.exception.detail))
        # Organisation active : message général inchangé.
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ACTIVE)
        with self.assertRaises(services.OrganizationError) as general:
            services.leave_organization(self.seller, self.org.pk)
        self.assertEqual(str(general.exception.detail), "Une organisation doit garder au moins un administrateur principal.")


class IndexTests(PurgeBase):
    def test_viewer_key_is_indexed_with_an_explicit_length(self):
        self.assertIn('viewer_key', [f for index in OfferUniqueView._meta.indexes for f in index.fields])
        self.assertEqual(OfferUniqueView._meta.get_field('viewer_key').max_length, 64)
