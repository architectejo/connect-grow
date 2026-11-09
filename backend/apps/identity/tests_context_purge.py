"""Purge des contextes `USER` et `PROVIDER` à la suppression d'un compte ou d'un profil prestataire (L0-09 T9-3,
ADR 0006 section 20, règles 10 et 12) : événement `identity.seller_context_removed`, abonnés `marketplace`, `visibility`
et `reviews`, jamais d'`ORGANIZATION`."""
import datetime
import uuid
from unittest import mock

from django.contrib import admin
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.catalog.models import Category, City, Commune
from apps.common.factories import make_test_image, owner_kwargs
from apps.marketplace import services as marketplace_services
from apps.marketplace.models import ContactEvent, ExchangeProposal, Favorite, Offer, OfferImage
from apps.moderation.models import AuditLog
from apps.platform_core.models import OutboxDelivery, OutboxEvent
from apps.platform_core.registry import PermanentEventError
from apps.platform_core.testing import dispatch_outbox_now
from apps.reviews.models import Review
from apps.visibility.models import DailyVisibilityCounter, OfferUniqueView

from . import services
from .admin import UserAdmin
from .models import Membership, Organization, ProviderProfile, User

SECRET_EMAIL = 'vendeur-secret@example.com'
SECRET_NAME = 'Nom Secret Vendeur'


class PurgeBase(TestCase):
    def setUp(self):
        city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        self.seller = User.objects.create_user(email=SECRET_EMAIL, password='x', full_name=SECRET_NAME)
        self.buyer = User.objects.create_user(email='buyer@example.com', password='x', full_name='Acheteur')
        self.org = Organization.objects.create(name='Atelier X', org_type='ENTREPRISE')
        self.other_owner = User.objects.create_user(email='owner@example.com', password='x', full_name='Propriétaire')
        Membership.objects.create(organization=self.org, user=self.other_owner, role='OWNER')
        Membership.objects.create(organization=self.org, user=self.seller, role='EDITOR')

    def make_offer(self, **kwargs):
        defaults = dict(
            category_id=self.category.id, commune_id=self.commune.id, title='Un joli canapé à vendre',
            description='Description suffisamment longue pour passer la validation du CDC.', price=100,
            main_image=make_test_image(),
        )
        defaults.update(kwargs)
        return Offer.objects.create(**defaults)

    def populate(self, offer, context_type, context_id):
        """Tout ce qui s'accroche à une offre et à son contexte vendeur."""
        gallery = OfferImage.objects.create(offer=offer, image=make_test_image('extra.png', fmt='PNG'))
        Favorite.objects.create(user=self.buyer, offer=offer)
        ContactEvent.objects.create(offer=offer, sender=self.buyer, message='Bonjour')
        ExchangeProposal.objects.create(offer=offer, sender=self.buyer, message='Troc ?')
        DailyVisibilityCounter.objects.create(
            offer_id=offer.pk, date=datetime.date(2026, 1, 1), views=3,
            seller_context_type=context_type, seller_context_id=context_id,
        )
        OfferUniqueView.objects.create(offer_id=offer.pk, viewer_key='user:x', date=datetime.date(2026, 1, 1))
        Review.objects.create(
            user=self.buyer, offer_id=offer.pk, seller_context_type=context_type, seller_context_id=context_id,
            contact_event_id=uuid.uuid4(), contact_channel='MESSAGE', contact_recorded_at=timezone.now(),
            offer_rating=4, seller_rating=5, content='Très bon vendeur, je recommande vivement.',
        )
        return gallery

    def build_user_world(self):
        offer = self.make_offer(**owner_kwargs(self.seller))
        gallery = self.populate(offer, 'USER', self.seller.pk)
        return offer, gallery

    def files_of(self, offer, gallery):
        return [offer.main_image, gallery.image]

    def residue(self, context_type, context_id):
        """Nombre de lignes encore rattachées au contexte (tous domaines)."""
        offers = Offer.objects.filter(seller_context_type=context_type, seller_context_id=context_id)
        ids = list(offers.values_list('id', flat=True))
        return {
            'offers': len(ids),
            'images': OfferImage.objects.filter(offer_id__in=ids).count(),
            'favorites': Favorite.objects.filter(offer_id__in=ids).count(),
            'contacts': ContactEvent.objects.filter(offer_id__in=ids).count(),
            'exchanges': ExchangeProposal.objects.filter(offer_id__in=ids).count(),
            'counters': DailyVisibilityCounter.objects.filter(
                seller_context_type=context_type, seller_context_id=context_id).count()
            + DailyVisibilityCounter.objects.filter(offer_id__in=ids).count(),
            'views': OfferUniqueView.objects.filter(offer_id__in=ids).count(),
            'reviews': Review.objects.filter(seller_context_type=context_type, seller_context_id=context_id).count(),
        }

    def zero(self):
        return {key: 0 for key in ('offers', 'images', 'favorites', 'contacts', 'exchanges', 'counters', 'views', 'reviews')}


class AccountDeletionPurgeTests(PurgeBase):
    def test_deleting_an_account_leaves_no_residue_of_its_contexts(self):
        offer, gallery = self.build_user_world()
        provider = ProviderProfile.objects.create(user=self.seller, display_name='Marie couture')
        provider_offer = self.make_offer(**owner_kwargs(provider, 'PROVIDER', created_by=self.seller))
        provider_gallery = self.populate(provider_offer, 'PROVIDER', provider.pk)
        files = self.files_of(offer, gallery) + self.files_of(provider_offer, provider_gallery)
        storage = offer.main_image.storage
        names = [f.name for f in files]
        self.assertTrue(all(storage.exists(name) for name in names))
        seller_pk, provider_pk = self.seller.pk, provider.pk
        self.assertEqual(self.residue('USER', seller_pk)['offers'], 1)

        with self.captureOnCommitCallbacks(execute=True):
            self.seller.delete()

        self.assertEqual(self.residue('USER', seller_pk), self.zero())
        self.assertEqual(self.residue('PROVIDER', provider_pk), self.zero())
        self.assertFalse(any(storage.exists(name) for name in names))

    def test_organization_is_never_purged_when_a_member_account_is_deleted(self):
        org_offer = self.make_offer(**owner_kwargs(self.org, 'ORGANIZATION', created_by=self.seller))
        self.populate(org_offer, 'ORGANIZATION', self.org.pk)
        before = self.residue('ORGANIZATION', self.org.pk)
        self.assertEqual(before['offers'], 1)
        files = [org_offer.main_image.name]
        storage = org_offer.main_image.storage

        with self.captureOnCommitCallbacks(execute=True):
            self.seller.delete()

        self.assertEqual(self.residue('ORGANIZATION', self.org.pk), before)
        org_offer.refresh_from_db()
        self.assertIsNone(org_offer.created_by)
        self.assertTrue(org_offer.seller_is_public)
        self.assertTrue(Organization.objects.filter(pk=self.org.pk).exists())
        self.assertTrue(all(storage.exists(name) for name in files))

    def test_organization_never_purged_when_an_owner_account_is_deleted(self):
        org_offer = self.make_offer(**owner_kwargs(self.org, 'ORGANIZATION', created_by=self.other_owner))
        self.populate(org_offer, 'ORGANIZATION', self.org.pk)
        before = self.residue('ORGANIZATION', self.org.pk)
        Membership.objects.filter(user=self.seller).update(role='OWNER')  # deux propriétaires

        with self.captureOnCommitCallbacks(execute=True):
            self.other_owner.delete()

        self.assertEqual(self.residue('ORGANIZATION', self.org.pk), before)

    def test_other_accounts_keep_their_data(self):
        other_offer = self.make_offer(**owner_kwargs(self.buyer))
        self.populate(other_offer, 'USER', self.buyer.pk)
        before = self.residue('USER', self.buyer.pk)
        self.build_user_world()

        with self.captureOnCommitCallbacks(execute=True):
            self.seller.delete()

        self.assertEqual(self.residue('USER', self.buyer.pk), before)
        other_offer.refresh_from_db()
        self.assertTrue(other_offer.seller_is_public)

    def test_bulk_queryset_deletion_goes_through_the_same_purge(self):
        self.build_user_world()
        second = User.objects.create_user(email='second@example.com', password='x', full_name='Second')
        offer2 = self.make_offer(**owner_kwargs(second))
        self.populate(offer2, 'USER', second.pk)
        pks = [self.seller.pk, second.pk]

        with self.captureOnCommitCallbacks(execute=True):
            User.objects.filter(pk__in=pks).delete()

        for pk in pks:
            self.assertEqual(self.residue('USER', pk), self.zero())

    def test_offers_are_masked_even_when_the_purge_fails(self):
        offer, _ = self.build_user_world()
        with mock.patch.object(marketplace_services, 'purge_seller_context', side_effect=RuntimeError('boom')):
            self.seller.delete()
        offer.refresh_from_db()
        self.assertFalse(offer.seller_is_public)  # masqué aussitôt par le changement de statut
        delivery = OutboxDelivery.objects.get(handler='marketplace.purge_seller_context')
        self.assertEqual(delivery.status, OutboxDelivery.PENDING)
        self.assertEqual(delivery.attempts, 1)
        # Les autres abonnés ne sont pas affectés par l'échec de celui-ci.
        self.assertEqual(OutboxDelivery.objects.get(handler='reviews.purge_seller_context').status, OutboxDelivery.DONE)
        self.assertEqual(OutboxDelivery.objects.get(handler='visibility.purge_seller_context').status, OutboxDelivery.DONE)

    def test_failed_subscriber_is_retried_and_the_purge_completes(self):
        offer, gallery = self.build_user_world()
        seller_pk = self.seller.pk
        with mock.patch.object(marketplace_services, 'purge_seller_context', side_effect=RuntimeError('boom')):
            self.seller.delete()
        self.assertEqual(self.residue('USER', seller_pk)['offers'], 1)

        OutboxDelivery.objects.filter(status=OutboxDelivery.PENDING).update(next_attempt_at=timezone.now())
        with self.captureOnCommitCallbacks(execute=True):
            dispatch_outbox_now()

        self.assertEqual(self.residue('USER', seller_pk), self.zero())
        self.assertFalse(OutboxDelivery.objects.exclude(status=OutboxDelivery.DONE).exists())


class ProviderDeletionPurgeTests(PurgeBase):
    def test_deleting_a_provider_profile_purges_only_the_provider_context(self):
        offer, gallery = self.build_user_world()
        provider = ProviderProfile.objects.create(user=self.seller, display_name='Marie couture')
        provider_offer = self.make_offer(**owner_kwargs(provider, 'PROVIDER', created_by=self.seller))
        self.populate(provider_offer, 'PROVIDER', provider.pk)
        before_user = self.residue('USER', self.seller.pk)
        provider_pk = provider.pk

        with self.captureOnCommitCallbacks(execute=True):
            provider.delete()

        self.assertEqual(self.residue('PROVIDER', provider_pk), self.zero())
        self.assertEqual(self.residue('USER', self.seller.pk), before_user)
        self.assertTrue(User.objects.filter(pk=self.seller.pk).exists())

    def test_archiving_a_provider_hides_but_keeps_data(self):
        provider = ProviderProfile.objects.create(user=self.seller, display_name='Marie couture')
        provider_offer = self.make_offer(**owner_kwargs(provider, 'PROVIDER', created_by=self.seller))
        self.populate(provider_offer, 'PROVIDER', provider.pk)
        before = self.residue('PROVIDER', provider.pk)

        services.archive_provider(self.seller)
        dispatch_outbox_now()

        self.assertEqual(self.residue('PROVIDER', provider.pk), before)
        provider_offer.refresh_from_db()
        self.assertFalse(provider_offer.seller_is_public)
        self.assertFalse(OutboxEvent.objects.filter(event_type='identity.seller_context_removed').exists())


class EventContractTests(PurgeBase):
    def test_payload_carries_only_type_and_identifier(self):
        self.build_user_world()
        seller_pk = self.seller.pk
        self.seller.delete()
        event = OutboxEvent.objects.get(event_type='identity.seller_context_removed')
        self.assertEqual(event.version, 1)
        self.assertEqual(event.payload, {'context_type': 'USER', 'context_id': str(seller_pk)})
        blob = str(event.payload) + event.aggregate_type
        self.assertNotIn(SECRET_EMAIL, blob)
        self.assertNotIn(SECRET_NAME, blob)
        self.assertEqual(
            set(OutboxDelivery.objects.filter(event=event).values_list('handler', flat=True)),
            {'marketplace.purge_seller_context', 'visibility.purge_seller_context', 'reviews.purge_seller_context'},
        )

    def test_user_with_provider_announces_both_contexts(self):
        provider = ProviderProfile.objects.create(user=self.seller, display_name='Marie couture')
        seller_pk, provider_pk = self.seller.pk, provider.pk
        self.seller.delete()
        announced = set(
            (e.payload['context_type'], e.payload['context_id'])
            for e in OutboxEvent.objects.filter(event_type='identity.seller_context_removed')
        )
        self.assertEqual(announced, {('USER', str(seller_pk)), ('PROVIDER', str(provider_pk))})

    def test_organization_cannot_be_announced_nor_purged(self):
        with self.assertRaises(ValueError):
            services.announce_seller_context_removed('ORGANIZATION', self.org.pk)
        org_offer = self.make_offer(**owner_kwargs(self.org, 'ORGANIZATION', created_by=self.other_owner))
        for purge in (
            marketplace_services.purge_seller_context,
        ):
            with self.assertRaises(PermanentEventError):
                purge('ORGANIZATION', self.org.pk)
        from apps.reviews import services as reviews_services
        from apps.visibility import services as visibility_services
        for purge in (reviews_services.purge_seller_context, visibility_services.purge_seller_context):
            with self.assertRaises(PermanentEventError):
                purge('ORGANIZATION', self.org.pk)
        self.assertTrue(Offer.objects.filter(pk=org_offer.pk).exists())

    def test_replaying_and_unknown_contexts_do_nothing(self):
        from apps.reviews import services as reviews_services
        from apps.visibility import services as visibility_services
        offer, gallery = self.build_user_world()
        seller_pk = self.seller.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.seller.delete()
        self.assertEqual(self.residue('USER', seller_pk), self.zero())
        audits = AuditLog.objects.filter(action__startswith='SELLER_CONTEXT_PURGED').count()
        # Rejeu : la livraison est déjà traitée, et rappeler les services directement ne fait rien ni ne plante.
        dispatch_outbox_now()
        unknown = uuid.uuid4()
        for context_type in ('USER', 'PROVIDER'):
            for context_id in (seller_pk, unknown):
                self.assertEqual(marketplace_services.purge_seller_context(context_type, context_id)['offers'], 0)
                self.assertEqual(visibility_services.purge_seller_context(context_type, context_id), 0)
                self.assertEqual(reviews_services.purge_seller_context(context_type, context_id), 0)
        self.assertEqual(AuditLog.objects.filter(action__startswith='SELLER_CONTEXT_PURGED').count(), audits)

    def test_invalid_payload_is_a_permanent_error(self):
        with self.assertRaises(PermanentEventError):
            marketplace_services.purge_seller_context('USER', 'pas-un-uuid')

    def test_event_is_delivered_by_the_dispatcher_too(self):
        """Le cron livre l'événement si la diffusion immédiate n'a pas eu lieu (livraison remise en attente)."""
        offer, gallery = self.build_user_world()
        seller_pk = self.seller.pk
        self.seller.delete()
        OutboxDelivery.objects.filter(handler='marketplace.purge_seller_context').update(
            status=OutboxDelivery.PENDING, next_attempt_at=timezone.now(), processed_at=None,
        )
        dispatch_outbox_now()  # rejeu : aucune erreur
        self.assertEqual(self.residue('USER', seller_pk), self.zero())
        self.assertEqual(
            OutboxDelivery.objects.get(handler='marketplace.purge_seller_context').status, OutboxDelivery.DONE,
        )


class AuditTests(PurgeBase):
    def test_audit_carries_counts_and_no_personal_data(self):
        self.build_user_world()
        # Compteur dont l'offre n'existe plus (ceux des offres partent avec elles, côté marketplace) : c'est
        # `visibility` qui l'efface par contexte.
        DailyVisibilityCounter.objects.create(
            offer_id=uuid.uuid4(), date=datetime.date(2026, 1, 2), views=1,
            seller_context_type='USER', seller_context_id=self.seller.pk,
        )
        seller_pk = self.seller.pk
        self.seller.delete()
        entries = AuditLog.objects.filter(action__startswith='SELLER_CONTEXT_PURGED')
        self.assertEqual(
            set(entries.values_list('action', flat=True)),
            {'SELLER_CONTEXT_PURGED_MARKETPLACE', 'SELLER_CONTEXT_PURGED_VISIBILITY', 'SELLER_CONTEXT_PURGED_REVIEWS'},
        )
        for entry in entries:
            self.assertIsNone(entry.actor)
            self.assertEqual((entry.context_type, entry.context_id), ('USER', seller_pk))
            self.assertNotIn(SECRET_EMAIL, entry.details)
            self.assertNotIn(SECRET_NAME, entry.details)
            self.assertNotIn('example.com', entry.details)
        marketplace_entry = entries.get(action='SELLER_CONTEXT_PURGED_MARKETPLACE')
        self.assertEqual(
            marketplace_entry.details, 'offers=1; images=1; favorites=1; contacts=1; exchanges=1',
        )
        self.assertEqual(entries.get(action='SELLER_CONTEXT_PURGED_REVIEWS').details, 'reviews=1')
        self.assertEqual(entries.get(action='SELLER_CONTEXT_PURGED_VISIBILITY').details, 'counters=1')

    def test_account_without_data_writes_no_purge_audit(self):
        self.buyer.delete()
        self.assertFalse(AuditLog.objects.filter(action__startswith='SELLER_CONTEXT_PURGED').exists())


class AdminDeletionTests(PurgeBase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            email='root@example.com', password='x', full_name='Admin', is_staff=True, is_superuser=True,
        )
        self.model_admin = UserAdmin(User, admin.site)

    def request(self):
        request = RequestFactory().post('/')
        request.user = self.staff
        return request

    def test_admin_delete_model_purges_contexts(self):
        self.build_user_world()
        seller_pk = self.seller.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.model_admin.delete_model(self.request(), self.seller)
        self.assertEqual(self.residue('USER', seller_pk), self.zero())
        self.assertTrue(AuditLog.objects.filter(action='USER_ADMIN_DELETED', actor=self.staff).exists())
        self.assertTrue(AuditLog.objects.filter(action='SELLER_CONTEXT_PURGED_MARKETPLACE').exists())

    def test_admin_delete_queryset_purges_contexts(self):
        self.build_user_world()
        seller_pk = self.seller.pk
        with self.captureOnCommitCallbacks(execute=True):
            self.model_admin.delete_queryset(self.request(), User.objects.filter(pk=seller_pk))
        self.assertEqual(self.residue('USER', seller_pk), self.zero())

    def test_sole_owner_of_an_organization_is_refused_and_nothing_is_purged(self):
        Membership.objects.filter(user=self.other_owner).delete()
        Membership.objects.filter(user=self.seller).update(role='OWNER')
        offer = self.make_offer(**owner_kwargs(self.seller))
        self.populate(offer, 'USER', self.seller.pk)
        before = self.residue('USER', self.seller.pk)
        with self.assertRaises(services.OrganizationError):
            self.model_admin.delete_model(self.request(), self.seller)
        with mock.patch.object(self.model_admin, 'message_user'):
            self.model_admin.delete_queryset(self.request(), User.objects.filter(pk=self.seller.pk))
        self.assertTrue(User.objects.filter(pk=self.seller.pk).exists())
        self.assertEqual(self.residue('USER', self.seller.pk), before)
        self.assertFalse(OutboxEvent.objects.filter(event_type='identity.seller_context_removed').exists())
