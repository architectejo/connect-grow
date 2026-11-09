"""Contraction du modèle « compte entreprise » (L0-09 T9-2, spec T9 §3.2 et §6).

Gardes des migrations `identity 0012/0013`, `marketplace 0011/0012` et `visibility 0007/0008` : elles échouent sur une
base non convertie (sans rien écrire, sans donnée personnelle dans le message) et passent sur une base convertie ;
retour arrière du SCHÉMA seulement ; contraintes NOT NULL définitives.
"""
import uuid

from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.common.factories import counter_owner_kwargs, make_test_image, owner_kwargs
from apps.identity.models import KycDocument, LegacyAccountMapping, Membership, Organization, User

from .tests_legacy_conversion import NEW, OLD, SECRET_EMAIL, SECRET_NIF, Builder, forward, migrate_to, state

LEAF = [
    ('identity', '0014_remove_user_user_type'), ('marketplace', '0012_offer_seller_context_required'),
    ('visibility', '0008_counter_seller_context_required'), ('reviews', '0006_convert_review_contexts'),
    ('moderation', '0005_audit_legacy_conversion'),
]
IDENTITY_0012 = ('identity', '0012_kycdocument_organization_required')
IDENTITY_0013 = ('identity', '0013_remove_business_profile')
MARKETPLACE_0011 = ('marketplace', '0011_remove_offer_seller')
VISIBILITY_0007 = ('visibility', '0007_remove_counter_seller')


def columns(table):
    with connection.cursor() as cursor:
        return {column.name for column in connection.introspection.get_table_description(cursor, table)}


def tables():
    return set(connection.introspection.table_names())


def applied():
    return MigrationExecutor(connection).loader.applied_migrations


def reset_database():
    """Revient à l'état NEW (les tables historiques existent), vide les données fabriquées (des profils non convertis
    feraient échouer les gardes, et `flush` ne connaît pas les tables retirées du code), puis migre à la dernière."""
    migrate_to(NEW)
    apps = state(NEW)
    for name in ('KycDocument', 'BusinessProfileCategory', 'BusinessProfile'):
        apps.get_model('identity', name).objects.all().delete()
    call_command('flush', verbosity=0, interactive=False)
    call_command('migrate', verbosity=0)


class ContractionBase(TransactionTestCase):
    """Chaque scénario reconstruit son monde (état NEW : conversion appliquée, contraction non appliquée)."""

    def setUp(self):
        cache.clear()
        migrate_to(NEW)
        self.apps = state(NEW)
        self.b = Builder(self.apps)

    def tearDown(self):
        reset_database()

    def assertRefused(self, target, *needles):
        with self.assertRaises(RuntimeError) as ctx:
            migrate_to([target])
        message = str(ctx.exception)
        self.assertIn('Contraction refusée', message)
        for needle in needles:
            self.assertIn(needle, message)
        for secret in (SECRET_EMAIL, SECRET_NIF, 'Atelier', '@'):
            self.assertNotIn(secret, message)  # comptages seulement, aucune donnée personnelle
        self.assertNotIn(target, applied())  # transaction annulée : rien n'est écrit
        return message


class GuardRefusesAnUnconvertedBaseTests(ContractionBase):
    def test_identity_refuses_a_profile_without_correspondence(self):
        profile = self.b.profile('Atelier')  # aucune ligne de correspondance : la conversion n'a pas eu lieu pour lui
        self.assertRefused(IDENTITY_0012, '1 profil(s) sans correspondance')
        self.assertIn('business_profile_id', columns('identity_kycdocument'))  # schéma intact
        self.assertEqual(self.b.Profile.objects.filter(pk=profile.pk).count(), 1)

    def test_identity_refuses_a_document_without_organization(self):
        self.b.Doc.objects.create(document_type='RCCM', file='x/orphelin.pdf')
        self.assertRefused(IDENTITY_0012, '1 pièce(s) sans organisation')

    def test_identity_deletion_of_the_models_has_its_own_guard(self):
        """`identity 0013` refait le contrôle : une base amenée à 0012 puis modifiée ne perd rien."""
        migrate_to([IDENTITY_0012])
        apps = state([IDENTITY_0012])
        user = apps.get_model('identity', 'User').objects.create(email='x@example.com', full_name='X')
        apps.get_model('identity', 'BusinessProfile').objects.create(user=user, business_name='Atelier')
        self.assertRefused(IDENTITY_0013, '1 profil(s) sans correspondance')
        self.assertIn('identity_businessprofile', tables())

    def test_marketplace_refuses_an_offer_still_personal_for_a_converted_account(self):
        owner = self.b.user()
        org = self.b.apps.get_model('identity', 'Organization').objects.create(name='Org', org_type='ENTREPRISE')
        self.b.apps.get_model('identity', 'LegacyAccountMapping').objects.create(user_id=owner.pk, organization_id=org.pk)
        self.b.offer(owner)  # contexte USER d'un compte présent dans la table de correspondance
        self.assertRefused(MARKETPLACE_0011, '1 offre(s) encore au contexte personnel')
        self.assertIn('seller_id', columns('marketplace_offer'))

    def test_marketplace_refuses_an_offer_without_context(self):
        owner = self.b.user()
        offer = self.b.offer(owner)
        self.b.Offer.objects.filter(pk=offer.pk).update(seller_context_type=None, seller_context_id=None)
        self.assertRefused(MARKETPLACE_0011, '1 offre(s) sans contexte vendeur')

    def test_visibility_refuses_a_counter_still_personal_for_a_converted_account(self):
        owner = self.b.user()
        org = self.b.apps.get_model('identity', 'Organization').objects.create(name='Org', org_type='ENTREPRISE')
        self.b.apps.get_model('identity', 'LegacyAccountMapping').objects.create(user_id=owner.pk, organization_id=org.pk)
        self.b.counter(self.b.offer(owner))
        self.assertRefused(VISIBILITY_0007, '1 compteur(s) encore au contexte personnel')
        self.assertIn('seller_id', columns('visibility_dailyvisibilitycounter'))

    def converted_without_mapping(self):
        """Organisation issue d'un profil (`legacy_business_profile_id`), table de correspondance vidée à la main."""
        owner = self.b.user()
        Org = self.b.apps.get_model('identity', 'Organization')
        org = Org.objects.create(name='Org', org_type='ENTREPRISE', legacy_business_profile_id=uuid.uuid4(), created_by=owner)
        self.b.apps.get_model('identity', 'Membership').objects.create(organization=org, user=owner, role='OWNER')
        self.assertEqual(self.b.apps.get_model('identity', 'LegacyAccountMapping').objects.count(), 0)
        return owner

    def test_marketplace_guard_does_not_depend_on_the_mapping_table(self):
        self.b.offer(self.converted_without_mapping())
        self.assertRefused(MARKETPLACE_0011, '1 offre(s) encore au contexte personnel')

    def test_visibility_guard_does_not_depend_on_the_mapping_table(self):
        self.b.counter(self.b.offer(self.converted_without_mapping()))
        # Les offres ne sont pas visées ici : la garde de `visibility` se refuse seule sur le compteur.
        self.assertRefused(VISIBILITY_0007, '1 compteur(s) encore au contexte personnel')

    def test_the_profiles_cannot_be_dropped_before_the_other_guards_ran(self):
        """`identity 0013` dépend des contractions de `marketplace` et `visibility` (les profils existent pendant leurs gardes)."""
        graph = MigrationExecutor(connection).loader.graph
        needed = {n for n in graph.forwards_plan(IDENTITY_0013)}
        for node in (MARKETPLACE_0011, ('marketplace', '0012_offer_seller_context_required'), VISIBILITY_0007,
                     ('visibility', '0008_counter_seller_context_required')):
            self.assertIn(node, needed)
        self.assertLess(graph.forwards_plan(IDENTITY_0013).index(MARKETPLACE_0011),
                        graph.forwards_plan(IDENTITY_0013).index(IDENTITY_0013))

    def test_the_not_null_steps_refuse_a_null_context(self):
        owner = self.b.user()
        migrate_to([MARKETPLACE_0011, VISIBILITY_0007])
        apps = state([MARKETPLACE_0011, VISIBILITY_0007])
        Offer, Counter = apps.get_model('marketplace', 'Offer'), apps.get_model('visibility', 'DailyVisibilityCounter')
        Offer.objects.create(
            created_by_id=owner.pk, category_id=uuid.uuid4(), commune_id=uuid.uuid4(), title='Sans contexte',
            description='d' * 30, price=1, expires_at=timezone.now(),
        )
        Counter.objects.create(offer_id=uuid.uuid4(), date=timezone.localdate())
        self.assertRefused(('marketplace', '0012_offer_seller_context_required'), '1 valeur(s) de contexte vendeur nulle(s)')
        self.assertRefused(('visibility', '0008_counter_seller_context_required'), '1 valeur(s) de contexte vendeur nulle(s)')


class ConvertedBaseTests(TransactionTestCase):
    """Une base réellement convertie passe les gardes sans perte ; le retour arrière ne rend que le schéma."""

    def setUp(self):
        cache.clear()
        migrate_to(OLD)
        b = self.b = Builder(state(OLD))
        profile = self.profile = b.complete_profile()
        offers = [b.offer(profile.user, 'Offre A'), b.offer(profile.user, 'Offre B')]
        [b.counter(o) for o in offers]
        [b.review(o) for o in offers]
        b.offer(b.user('PARTICULIER'), 'Offre perso')
        b.profile('Banni', user=b.user(is_active=False))
        forward()

    def tearDown(self):
        reset_database()

    def snapshot(self):
        apps = state(NEW)
        Offer, Counter, Review = (apps.get_model(a, m) for a, m in (
            ('marketplace', 'Offer'), ('visibility', 'DailyVisibilityCounter'), ('reviews', 'Review')))
        return {
            'organizations': sorted(Organization.objects.values_list('pk', 'name', 'status', 'legacy_business_profile_id')),
            'memberships': Membership.objects.count(), 'mappings': LegacyAccountMapping.objects.count(),
            'documents': sorted(KycDocument.objects.values_list('pk', 'organization_id', 'status', 'file')),
            'offers': sorted(Offer.objects.values_list('pk', 'seller_context_type', 'seller_context_id', 'created_by_id')),
            'counters': sorted(Counter.objects.values_list('pk', 'seller_context_type', 'seller_context_id', 'views')),
            'reviews': sorted(Review.objects.values_list('pk', 'seller_context_type', 'seller_context_id')),
            'accounts': User.objects.count(),
        }

    def test_contraction_loses_nothing_and_removes_the_legacy_columns_and_tables(self):
        before = self.snapshot()
        self.assertEqual(len(before['organizations']), 2)
        self.assertIn('identity_businessprofile', tables())
        self.assertIn('user_type', columns('identity_user'))

        migrate_to(LEAF)
        self.assertEqual(self.snapshot(), before)  # aucune donnée perdue ni déplacée
        for target in (IDENTITY_0012, IDENTITY_0013, MARKETPLACE_0011, VISIBILITY_0007, *LEAF):
            self.assertIn(target, applied())
        self.assertNotIn('identity_businessprofile', tables())
        self.assertNotIn('identity_businessprofilecategory', tables())
        self.assertNotIn('business_profile_id', columns('identity_kycdocument'))
        self.assertNotIn('user_type', columns('identity_user'))
        self.assertNotIn('seller_id', columns('marketplace_offer'))
        self.assertNotIn('seller_id', columns('visibility_dailyvisibilitycounter'))
        with connection.cursor() as cursor:
            descriptions = {
                table: {c.name: c.null_ok for c in connection.introspection.get_table_description(cursor, table)}
                for table in ('identity_kycdocument', 'marketplace_offer', 'visibility_dailyvisibilitycounter')
            }
        self.assertFalse(descriptions['identity_kycdocument']['organization_id'])
        self.assertFalse(descriptions['marketplace_offer']['seller_context_id'])
        self.assertFalse(descriptions['marketplace_offer']['seller_context_type'])
        self.assertFalse(descriptions['visibility_dailyvisibilitycounter']['seller_context_id'])
        self.assertFalse(descriptions['visibility_dailyvisibilitycounter']['seller_context_type'])

    def test_reverse_restores_the_schema_only_never_the_data_and_replays_forward(self):
        migrate_to(LEAF)
        before = self.snapshot()

        migrate_to(NEW)
        self.assertIn('identity_businessprofile', tables())
        self.assertIn('identity_businessprofilecategory', tables())
        self.assertIn('business_profile_id', columns('identity_kycdocument'))
        self.assertIn('user_type', columns('identity_user'))
        self.assertIn('seller_id', columns('marketplace_offer'))
        self.assertIn('seller_id', columns('visibility_dailyvisibilitycounter'))
        apps = state(NEW)
        self.assertEqual(apps.get_model('identity', 'BusinessProfile').objects.count(), 0)  # tables vides
        self.assertEqual(apps.get_model('identity', 'BusinessProfileCategory').objects.count(), 0)
        self.assertFalse(apps.get_model('identity', 'KycDocument').objects.filter(business_profile__isnull=False).exists())
        self.assertFalse(apps.get_model('marketplace', 'Offer').objects.filter(seller__isnull=False).exists())
        self.assertEqual(self.snapshot(), before)  # organisations, offres, pièces : intactes dans les deux sens

        migrate_to(LEAF)  # les gardes repassent : la base reste convertie
        self.assertEqual(self.snapshot(), before)


class DatabaseConstraintTests(TestCase):
    """Après la contraction, un propriétaire est obligatoire en base."""

    def offer_kwargs(self, **extra):
        return dict(
            category_id=uuid.uuid4(), commune_id=uuid.uuid4(), title='Un joli canapé à vendre',
            description='Description suffisamment longue pour passer la validation.', price=1,
            main_image=make_test_image(), **extra,
        )

    def test_an_offer_without_owner_context_is_refused_by_the_database(self):
        from apps.marketplace.models import Offer

        with self.assertRaises(IntegrityError), transaction.atomic():
            Offer.objects.create(**self.offer_kwargs())

    def test_an_offer_with_an_owner_context_is_created(self):
        from apps.marketplace.models import Offer

        user = User.objects.create_user(email='o@example.com', password='x', full_name='O')
        offer = Offer.objects.create(**self.offer_kwargs(**owner_kwargs(user)))
        self.assertEqual((offer.seller_context_type, offer.seller_context_id, offer.created_by_id), ('USER', user.pk, user.pk))

    def test_a_counter_without_owner_context_is_refused_by_the_database(self):
        from apps.visibility.models import DailyVisibilityCounter

        with self.assertRaises(IntegrityError), transaction.atomic():
            DailyVisibilityCounter.objects.create(offer_id=uuid.uuid4(), date=timezone.localdate())
        user = User.objects.create_user(email='c@example.com', password='x', full_name='C')
        counter = DailyVisibilityCounter.objects.create(
            offer_id=uuid.uuid4(), date=timezone.localdate(), **counter_owner_kwargs(user),
        )
        self.assertEqual((counter.seller_context_type, counter.seller_context_id), ('USER', user.pk))

    def test_a_document_without_organization_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            KycDocument.objects.create(document_type='RCCM', file='x/y.pdf')

    def test_models_carry_no_legacy_field(self):
        from apps.marketplace.models import Offer
        from apps.visibility.models import DailyVisibilityCounter

        for model, name in ((Offer, 'seller'), (DailyVisibilityCounter, 'seller'), (KycDocument, 'business_profile'),
                            (User, 'user_type')):
            self.assertNotIn(name, {f.name for f in model._meta.get_fields()}, f'{model.__name__}.{name}')
        self.assertFalse(hasattr(User, 'offers') or hasattr(User, 'visibility_counters'))
