"""Conversion des comptes entreprise en organisations (L0-09 T9-1, spec T9 §2 et §6).

Tests par `MigrationExecutor` : état historique avant `identity 0011`, jeu de données fabriqué, migration en avant
puis retour arrière. Couvre le mapping champ par champ, l'équivalence de la vérification dérivée, l'idempotence, les
cas limites, le retour arrière, la base vierge, la non-fuite de données personnelles et la commande de pré-vol.
"""
import importlib
import io
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity import legacy_conversion as rules
from apps.identity import services as identity_services
from apps.identity.models import (
    ContactConsent, ContactPoint, KycDocument, LegacyAccountMapping, Membership, Organization,
    OrganizationCategory,
)
from apps.identity.verification import get_verification_summaries

OLD = [
    ('identity', '0010_identitysettings_kyb_file_retention_days'), ('marketplace', '0009_fill_offer_seller_context'),
    ('visibility', '0005_fill_counter_seller_context'), ('reviews', '0005_provider_context_choice'),
    ('moderation', '0004_auditlog_context'),
]
NEW = [
    ('identity', '0011_convert_business_profiles'), ('marketplace', '0010_convert_offer_contexts'),
    ('visibility', '0006_convert_counter_contexts'), ('reviews', '0006_convert_review_contexts'),
    ('moderation', '0005_audit_legacy_conversion'),
]
_STATE_CACHE = {}
SECRET_NIF = 'NIF-SENTINELLE-777'
SECRET_EMAIL = 'proprietaire.secret@example.com'
SECRET_PHONE = '+243899887766'
SECRET_FULL_NAME = 'Prenom Secret-Proprietaire'
SECRET_BIO_MARK = 'bio-sentinelle'


class ConversionBase(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.catalog_leaf = lambda executor: executor.loader.graph.leaf_nodes('catalog')[0]  # noqa: E731
        self.go(OLD)
        self.old_apps = self.state(OLD)
        self.build_world()

    def tearDown(self):
        call_command('migrate', verbosity=0)

    # -- migrations ---------------------------------------------------------------------------------------
    def go(self, targets):
        executor = MigrationExecutor(connection)
        full = list(targets) + [self.catalog_leaf(executor)]
        executor.migrate(full)

    def state(self, targets):
        # Le rendu des modèles historiques est coûteux et sans état : un seul par jeu de cibles pour tout le module.
        key = tuple(targets)
        if key not in _STATE_CACHE:
            executor = MigrationExecutor(connection)
            _STATE_CACHE[key] = executor.loader.project_state(list(targets) + [self.catalog_leaf(executor)]).apps
        return _STATE_CACHE[key]

    def forward(self):
        self.go(NEW)
        self.new_apps = self.state(NEW)

    # -- jeu de données historique ------------------------------------------------------------------------
    def build_world(self):
        a = self.old_apps
        self.HUser = a.get_model('identity', 'User')
        self.HProfile = a.get_model('identity', 'BusinessProfile')
        self.HProfileCat = a.get_model('identity', 'BusinessProfileCategory')
        self.HDoc = a.get_model('identity', 'KycDocument')
        self.HOffer = a.get_model('marketplace', 'Offer')
        self.HCounter = a.get_model('visibility', 'DailyVisibilityCounter')
        self.HReview = a.get_model('reviews', 'Review')
        Req = a.get_model('identity', 'OrganizationDocumentRequirement')
        for position, doc_type in enumerate(('RCCM', 'ID_NATIONALE', 'PIECE_GERANT')):
            Req.objects.get_or_create(org_type='ENTREPRISE', document_type=doc_type, defaults={'position': position})
        City, Commune, Category = (a.get_model('catalog', n) for n in ('City', 'Commune', 'Category'))
        self.city = City.objects.create(name='Kinshasa', name_key='kinshasa', slug='kinshasa')
        self.commune = Commune.objects.create(city=self.city, name='Gombe', name_key='gombe')
        self.category = Category.objects.create(name='Electronique', name_key='electronique', slug='electronique')
        self.reviewer = self.HUser.objects.create(email='reviewer@example.com', full_name='Relecteur', is_staff=True)
        self.created_at = timezone.now() - timedelta(days=400)
        self.seq = 0

    def user(self, user_type='ENTREPRISE', **kwargs):
        self.seq += 1
        kwargs.setdefault('email', f'u{self.seq}@example.com')
        kwargs.setdefault('full_name', f'Compte {self.seq}')
        return self.HUser.objects.create(user_type=user_type, **kwargs)

    def profile(self, name='Atelier', user=None, categories=1, **kwargs):
        user = user or self.user(city_id=self.city.id, commune_id=self.commune.id)
        profile = self.HProfile.objects.create(user=user, business_name=name, **kwargs)
        self.HProfile.objects.filter(pk=profile.pk).update(created_at=self.created_at)
        for _ in range(categories):
            self.HProfileCat.objects.create(business_profile=profile, category_id=uuid.uuid4())
        profile.refresh_from_db()
        return profile

    def doc(self, profile, doc_type, status='VALIDE', **kwargs):
        if status != 'EN_ATTENTE':
            kwargs.setdefault('reviewed_by', self.reviewer)
            kwargs.setdefault('reviewed_at', timezone.now() - timedelta(days=3))
        return self.HDoc.objects.create(
            business_profile=profile, document_type=doc_type, status=status,
            file=f'profile-{profile.pk}/{doc_type}.pdf', **kwargs,
        )

    def offer(self, owner, title='Offre', public=True):
        return self.HOffer.objects.create(
            seller=owner, seller_context_type='USER', seller_context_id=owner.pk, created_by=owner,
            seller_is_public=public, category_id=self.category.id, commune_id=self.commune.id, title=title,
            description='Description suffisamment longue pour passer.', price=1,
            expires_at=timezone.now() + timedelta(days=30),
        )

    def counter(self, offer, views=3):
        return self.HCounter.objects.create(
            offer_id=offer.id, seller=offer.seller, seller_context_type='USER', seller_context_id=offer.seller_id,
            date=timezone.localdate(), views=views, shares=1, contacts=2,
        )

    def review(self, offer, rating=5):
        author = self.user('PARTICULIER')
        return self.HReview.objects.create(
            user=author, offer_id=offer.id, seller_context_type='USER', seller_context_id=offer.seller_id,
            contact_event_id=uuid.uuid4(), contact_channel='MESSAGE', contact_recorded_at=timezone.now(),
            offer_rating=rating, seller_rating=rating, content='Avis suffisamment long pour être valide.',
        )

    def complete_profile(self):
        """Profil complet : bio, logo, NIF, ville, 3 catégories, 3 pièces validées, `is_verified` vrai."""
        owner = self.user(
            email=SECRET_EMAIL, phone=SECRET_PHONE, full_name=SECRET_FULL_NAME, city_id=self.city.id,
            commune_id=self.commune.id,
        )
        profile = self.profile(
            'Atelier Zorglub', user=owner, categories=3, bio=f'Menuiserie {SECRET_BIO_MARK}.',
            logo='business_logos/zorglub.png', nif=SECRET_NIF, is_verified=True,
        )
        for doc_type in ('RCCM', 'ID_NATIONALE', 'PIECE_GERANT'):
            self.doc(profile, doc_type)
        return profile

    def org_of(self, profile):
        return Organization.objects.get(legacy_business_profile_id=profile.pk)


class MappingTests(ConversionBase):
    def test_complete_profile_is_converted_field_by_field(self):
        profile = self.complete_profile()
        owner = profile.user
        owner_id = owner.pk
        categories = set(self.HProfileCat.objects.filter(business_profile=profile).values_list('category_id', flat=True))
        docs_before = {
            d.pk: (d.document_type, d.status, d.rejection_reason, d.reviewed_by_id, d.reviewed_at, d.file.name)
            for d in self.HDoc.objects.filter(business_profile=profile)
        }
        self.forward()

        org = self.org_of(profile)
        self.assertEqual(
            (org.name, org.org_type, org.description, org.logo.name, org.nif, org.city_id, org.commune_id, org.status,
             org.suspension_reason, org.created_by_id, org.legacy_business_profile_id),
            ('Atelier Zorglub', 'ENTREPRISE', f'Menuiserie {SECRET_BIO_MARK}.', 'business_logos/zorglub.png', SECRET_NIF,
             self.city.id, self.commune.id, 'ACTIVE', '', owner_id, profile.pk),
        )
        self.assertEqual(org.created_at, profile.created_at)
        self.assertEqual(set(OrganizationCategory.objects.filter(organization=org).values_list('category_id', flat=True)),
                         categories)
        members = list(Membership.objects.filter(organization=org))
        self.assertEqual(len(members), 1)
        member = members[0]
        self.assertEqual((member.user_id, member.role, member.status, member.added_by_id, member.ended_at),
                         (owner_id, 'OWNER', 'ACTIVE', None, None))
        self.assertEqual(member.joined_at, profile.created_at)
        mapping = LegacyAccountMapping.objects.get()
        self.assertEqual((mapping.user_id, mapping.organization_id), (owner_id, org.pk))
        # Pièces : rattachées, auteur du dépôt posé, tout le reste inchangé (fichier compris).
        docs = KycDocument.objects.filter(organization=org)
        self.assertEqual(docs.count(), 3)
        for doc in docs:
            self.assertEqual(doc.uploaded_by_id, owner_id)
            self.assertEqual(doc.business_profile_id, profile.pk)  # l'ancien lien reste jusqu'à la contraction
            self.assertEqual(
                (doc.document_type, doc.status, doc.rejection_reason, doc.reviewed_by_id, doc.reviewed_at, doc.file.name),
                docs_before[doc.pk],
            )
        self.assertEqual(self.new_apps.get_model('identity', 'BusinessProfile').objects.count(), 1)  # rien supprimé

    def test_conversion_criterion_is_the_profile_not_user_type(self):
        converted_particulier = self.profile('Chez un particulier', user=self.user('PARTICULIER'))
        enterprise_without_profile = self.user('ENTREPRISE')
        plain = self.user('PARTICULIER')
        self.forward()
        self.assertTrue(Organization.objects.filter(legacy_business_profile_id=converted_particulier.pk).exists())
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(Membership.objects.exclude(user_id=converted_particulier.user_id).count(), 0)
        self.assertFalse(LegacyAccountMapping.objects.filter(user_id__in=[enterprise_without_profile.pk, plain.pk]).exists())

    def test_profile_without_offer_is_converted_active(self):
        profile = self.profile('Sans offre')
        self.forward()
        self.assertEqual(self.org_of(profile).status, 'ACTIVE')

    def test_inactive_owner_gives_a_suspended_organization_with_private_offers(self):
        banned = self.profile('Banni', user=self.user(is_active=False))
        offer = self.offer(banned.user)
        self.forward()
        org = self.org_of(banned)
        self.assertEqual((org.status, org.suspension_reason), ('SUSPENDED', 'other'))
        moved = self.new_apps.get_model('marketplace', 'Offer').objects.get(pk=offer.pk)
        self.assertEqual((moved.seller_context_type, moved.seller_context_id, moved.seller_is_public),
                         ('ORGANIZATION', org.pk, False))

    def test_names_are_cleaned_never_rejected_and_never_merged(self):
        control = self.profile('  Atelier​ \t Control\x00e  ')
        empty = self.profile('​ ‎ ')
        short = self.profile('A')
        long_name = self.profile('N' * 300)
        twin_1 = self.profile('Café Zorglub')
        twin_2 = self.profile('cafe  zorglub')
        mixed = self.profile('Bаnque')  # a cyrillique
        self.forward()
        self.assertEqual(self.org_of(control).name, 'Atelier Controle')
        for profile in (empty, short):
            self.assertEqual(self.org_of(profile).name, f'Organisation {str(profile.pk)[:8]}')
        self.assertEqual(len(self.org_of(long_name).name), 255)
        self.assertNotEqual(self.org_of(twin_1).pk, self.org_of(twin_2).pk)
        self.assertEqual(self.org_of(twin_1).name, 'Café Zorglub')
        self.assertEqual(self.org_of(twin_2).name, 'cafe zorglub')
        self.assertEqual(self.org_of(mixed).name, 'Bаnque')
        self.assertEqual(Organization.objects.count(), 7)

    def test_long_description_is_truncated_and_all_categories_are_kept(self):
        profile = self.profile('Gros profil', categories=7, bio='x' * 2500)
        self.forward()
        org = self.org_of(profile)
        self.assertEqual(len(org.description), 2000)
        self.assertEqual(org.category_links.count(), 7)
        self.assertEqual(self.HProfile.objects.get(pk=profile.pk).bio, 'x' * 2500)  # l'original reste

    def test_missing_logo_gives_no_logo(self):
        profile = self.profile('Sans logo')
        self.forward()
        self.assertFalse(self.org_of(profile).logo)


class VerificationTests(ConversionBase):
    def test_derived_verification_matches_the_old_flag(self):
        full = self.complete_profile()
        two = self.profile('Deux pieces', is_verified=False)
        for doc_type in ('RCCM', 'ID_NATIONALE'):
            self.doc(two, doc_type)
        refused = self.profile('Refusee', is_verified=False)
        self.doc(refused, 'RCCM', status='REFUSE', rejection_reason='Illisible')
        self.doc(refused, 'ID_NATIONALE', status='EN_ATTENTE')
        manual = self.profile('Drapeau manuel', is_verified=True)  # aucune pièce : règle 3, jamais recopié
        self.forward()
        summaries = get_verification_summaries([self.org_of(p).pk for p in (full, two, refused, manual)])
        complete = {p.business_name: summaries[self.org_of(p).pk]['summary']['complete'] for p in (full, two, refused, manual)}
        self.assertEqual(complete, {'Atelier Zorglub': True, 'Deux pieces': False, 'Refusee': False, 'Drapeau manuel': False})
        self.assertEqual({p.business_name: p.is_verified for p in (full, two, refused, manual)},
                         {'Atelier Zorglub': True, 'Deux pieces': False, 'Refusee': False, 'Drapeau manuel': True})
        self.assertEqual([c['code'] for c in summaries[self.org_of(full).pk]['verified_claims']],
                         ['RCCM_VERIFIED', 'NATIONAL_ID_VERIFIED', 'REPRESENTATIVE_VERIFIED'])
        self.assertEqual(len(summaries[self.org_of(two).pk]['verified_claims']), 2)
        self.assertEqual(summaries[self.org_of(refused).pk]['verified_claims'], [])
        self.assertEqual(summaries[self.org_of(manual).pk]['verified_claims'], [])
        refused_doc = KycDocument.objects.get(organization=self.org_of(refused), document_type='RCCM')
        self.assertEqual((refused_doc.status, refused_doc.rejection_reason), ('REFUSE', 'Illisible'))

    def test_document_already_on_an_organization_is_left_alone(self):
        profile = self.profile('Incoherent')
        other = self.new_org_before(profile)
        mixed = self.doc(profile, 'RCCM')
        self.HDoc.objects.filter(pk=mixed.pk).update(organization=other)
        self.forward()
        self.assertEqual(KycDocument.objects.get(pk=mixed.pk).organization_id, other.pk)

    def new_org_before(self, profile):
        return self.old_apps.get_model('identity', 'Organization').objects.create(name='Preexistante', org_type='ONG')

    def test_converted_owner_cannot_decide_their_own_pieces(self):
        staff_owner = self.profile('Chez le personnel', user=self.user(is_staff=True))
        revoked_owner = self.profile('Ancien proprietaire')
        self.doc(staff_owner, 'RCCM', status='EN_ATTENTE')
        self.doc(revoked_owner, 'RCCM', status='EN_ATTENTE')
        self.forward()
        User = get_user_model()
        staff = User.objects.get(pk=staff_owner.user_id)
        for profile, reviewer in ((staff_owner, staff), (revoked_owner, User.objects.get(pk=revoked_owner.user_id))):
            doc = KycDocument.objects.get(organization=self.org_of(profile))
            with self.assertRaises(identity_services.KycError) as ctx:
                identity_services.decide_kyc_document(doc.pk, reviewer, 'VALIDE')
            self.assertEqual(ctx.exception.status_code, 403)
        Membership.objects.filter(organization=self.org_of(revoked_owner)).update(status='REVOKED')
        doc = KycDocument.objects.get(organization=self.org_of(revoked_owner))
        with self.assertRaises(identity_services.KycError):
            identity_services.decide_kyc_document(doc.pk, User.objects.get(pk=revoked_owner.user_id), 'VALIDE')


class RelatedDataTests(ConversionBase):
    def seed(self):
        self.business = self.complete_profile()
        self.biz_offers = [self.offer(self.business.user, 'Offre A'), self.offer(self.business.user, 'Offre B')]
        self.biz_counters = [self.counter(o) for o in self.biz_offers]
        self.biz_reviews = [self.review(o) for o in self.biz_offers]
        self.person = self.user('PARTICULIER')
        self.person_offer = self.offer(self.person, 'Offre perso')
        self.person_counter = self.counter(self.person_offer)
        self.person_review = self.review(self.person_offer)
        self.noprofile = self.user('ENTREPRISE')
        self.noprofile_offer = self.offer(self.noprofile, 'Sans profil')

    def test_offers_counters_and_reviews_follow_the_organization(self):
        self.seed()
        self.forward()
        org = self.org_of(self.business)
        Offer = self.new_apps.get_model('marketplace', 'Offer')
        Counter = self.new_apps.get_model('visibility', 'DailyVisibilityCounter')
        Review = self.new_apps.get_model('reviews', 'Review')
        for offer in self.biz_offers:
            row = Offer.objects.get(pk=offer.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id, row.created_by_id, row.seller_is_public),
                             ('ORGANIZATION', org.pk, self.business.user_id, True))
            self.assertEqual(row.seller_id, self.business.user_id)  # FK inchangée jusqu'à la contraction
        for counter in self.biz_counters:
            row = Counter.objects.get(pk=counter.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id, row.views, row.shares, row.contacts),
                             ('ORGANIZATION', org.pk, 3, 1, 2))
        for review in self.biz_reviews:
            row = Review.objects.get(pk=review.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id, row.counts_for_seller),
                             ('ORGANIZATION', org.pk, True))
        # Comptes sans profil : rien ne bouge.
        for row in (self.person_offer, self.noprofile_offer):
            current = Offer.objects.get(pk=row.pk)
            self.assertEqual((current.seller_context_type, current.seller_context_id), ('USER', row.seller_id))
        self.assertEqual(Counter.objects.get(pk=self.person_counter.pk).seller_context_type, 'USER')
        self.assertEqual(Review.objects.get(pk=self.person_review.pk).seller_context_type, 'USER')

    def test_second_run_of_the_functions_changes_nothing(self):
        self.seed()
        self.forward()

        def snapshot():
            return (
                Organization.objects.count(), Membership.objects.count(), LegacyAccountMapping.objects.count(),
                OrganizationCategory.objects.count(),
                list(self.new_apps.get_model('moderation', 'AuditLog').objects.order_by('pk').values_list('pk', flat=True)),
                sorted(self.new_apps.get_model('marketplace', 'Offer').objects.values_list('pk', 'seller_context_id')),
            )

        before = snapshot()
        schema_editor = None
        importlib.import_module('apps.identity.migrations.0011_convert_business_profiles').convert_profiles(
            self.new_apps, schema_editor)
        importlib.import_module('apps.marketplace.migrations.0010_convert_offer_contexts').to_organizations(
            self.new_apps, schema_editor)
        importlib.import_module('apps.visibility.migrations.0006_convert_counter_contexts').to_organizations(
            self.new_apps, schema_editor)
        importlib.import_module('apps.reviews.migrations.0006_convert_review_contexts').to_organizations(
            self.new_apps, schema_editor)
        importlib.import_module('apps.moderation.migrations.0005_audit_legacy_conversion').audit(self.new_apps, schema_editor)
        self.assertEqual(snapshot(), before)

    def test_rollback_then_forward_again_duplicates_nothing_and_deletes_nothing(self):
        self.seed()
        self.forward()
        counts = (Organization.objects.count(), Membership.objects.count(), LegacyAccountMapping.objects.count())

        self.go(OLD)
        old = self.state(OLD)
        Offer = old.get_model('marketplace', 'Offer')
        Counter = old.get_model('visibility', 'DailyVisibilityCounter')
        Review = old.get_model('reviews', 'Review')
        self.assertEqual((Offer.objects.count(), Counter.objects.count(), Review.objects.count()), (4, 3, 3))
        for offer in self.biz_offers:
            row = Offer.objects.get(pk=offer.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id, row.seller_is_public),
                             ('USER', self.business.user_id, True))
        for counter in self.biz_counters:
            self.assertEqual(Counter.objects.get(pk=counter.pk).seller_context_type, 'USER')
        for review in self.biz_reviews:
            row = Review.objects.get(pk=review.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id), ('USER', self.business.user_id))
        # Création des organisations en `noop` au retour arrière : rien n'est supprimé.
        self.assertEqual(
            (Organization.objects.count(), Membership.objects.count(), LegacyAccountMapping.objects.count()), counts)
        self.assertEqual(old.get_model('identity', 'BusinessProfile').objects.count(), 1)

        self.forward()
        self.assertEqual(
            (Organization.objects.count(), Membership.objects.count(), LegacyAccountMapping.objects.count()), counts)
        self.assertEqual(self.new_apps.get_model('moderation', 'AuditLog').objects.filter(action='ORG_CONVERTED').count(), 1)
        self.assertEqual(
            self.new_apps.get_model('marketplace', 'Offer').objects.filter(seller_context_type='ORGANIZATION').count(), 2)

    def test_rollback_restores_the_visibility_of_the_account(self):
        banned = self.profile('Banni', user=self.user(is_active=False))
        offer = self.offer(banned.user, public=False)
        self.forward()
        self.go(OLD)
        row = self.state(OLD).get_model('marketplace', 'Offer').objects.get(pk=offer.pk)
        self.assertEqual((row.seller_context_type, row.seller_is_public), ('USER', False))

    def test_lost_mapping_is_recovered_without_duplicating_the_organization(self):
        profile = self.profile('Reprise')
        self.forward()
        org_id = self.org_of(profile).pk
        LegacyAccountMapping.objects.all().delete()
        Membership.objects.all().delete()
        importlib.import_module('apps.identity.migrations.0011_convert_business_profiles').convert_profiles(
            self.new_apps, None)
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(LegacyAccountMapping.objects.get().organization_id, org_id)
        self.assertEqual(Membership.objects.filter(organization_id=org_id, role='OWNER').count(), 1)

    def test_audit_log_has_one_line_per_conversion_and_only_identifiers(self):
        self.seed()
        banned = self.profile('Banni', user=self.user(is_active=False))
        self.forward()
        AuditLog = self.new_apps.get_model('moderation', 'AuditLog')
        lines = list(AuditLog.objects.filter(action='ORG_CONVERTED'))
        self.assertEqual(len(lines), LegacyAccountMapping.objects.count())
        self.assertEqual(len(lines), 2)
        by_org = {line.target_id: line for line in lines}
        for mapping in LegacyAccountMapping.objects.all():
            line = by_org[mapping.organization_id]
            org = Organization.objects.get(pk=mapping.organization_id)
            self.assertEqual((line.actor_id, line.target_type, line.context_type, line.context_id),
                             (None, 'organization', 'ORGANIZATION', org.pk))
            self.assertEqual(line.details, f'legacy_business_profile={org.legacy_business_profile_id}; status={org.status}')
        self.assertIn('status=SUSPENDED', by_org[self.org_of(banned).pk].details)
        blob = ' '.join(f'{line.details} {line.target_type} {line.action}' for line in lines)
        for secret in (SECRET_NIF, SECRET_EMAIL, SECRET_PHONE, SECRET_FULL_NAME, 'Zorglub', SECRET_BIO_MARK):
            self.assertNotIn(secret, blob)


class SafetyTests(ConversionBase):
    def test_no_contact_data_is_copied_and_only_the_owner_gets_a_role(self):
        profile = self.complete_profile()
        staff = self.user('PARTICULIER', is_staff=True, is_superuser=True)
        owner = profile.user
        ContactPoint = self.old_apps.get_model('identity', 'ContactPoint')
        Consent = self.old_apps.get_model('identity', 'ContactConsent')
        ContactPoint.objects.create(user=owner, phone=SECRET_PHONE, is_verified=True)
        for channel in ('CALL', 'WHATSAPP'):
            Consent.objects.create(user=owner, channel=channel, is_granted=True, granted_at=timezone.now(),
                                   text_version='2026-10-v1', phone_last4=SECRET_PHONE[-4:])
        offer = self.offer(owner)
        self.forward()
        org = self.org_of(profile)
        self.assertFalse(ContactPoint.objects.filter(organization__isnull=False).exists())
        self.assertFalse(ContactConsent.objects.filter(organization__isnull=False).exists())
        self.assertEqual(ContactConsent.objects.filter(user_id=owner.pk).count(), 2)  # le personnel reste au propriétaire
        self.assertEqual(list(Membership.objects.values_list('user_id', 'organization_id')), [(owner.pk, org.pk)])
        self.assertFalse(Membership.objects.filter(user_id=staff.pk).exists())

        client = APIClient()
        detail = client.get(f'/api/marketplace/posts/{offer.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['allowed_channels'], ['MESSAGE'])
        self.assertEqual(detail.json()['seller']['context_type'], 'ORGANIZATION')
        self.assertEqual(detail.json()['seller']['context_id'], str(org.pk))
        listing = client.get('/api/accounts/organizations/')
        self.assertEqual(listing.status_code, 200)
        item = listing.json()['results'][0]
        self.assertEqual(set(item), {
            'id', 'name', 'org_type', 'description', 'logo', 'city_id', 'commune_id', 'category_ids',
            'verified_claims', 'verification_summary', 'member_since',
        })
        profile_page = client.get(f'/api/marketplace/sellers/organization/{org.pk}/')
        self.assertEqual(profile_page.status_code, 200)
        for response in (detail, listing, profile_page):
            text = response.content.decode()
            for secret in (SECRET_NIF, SECRET_EMAIL, SECRET_PHONE, SECRET_FULL_NAME, str(owner.pk)):
                self.assertNotIn(secret, text)

    def test_converted_organization_is_listed_in_the_contexts_of_its_owner(self):
        profile = self.complete_profile()
        self.forward()
        User = get_user_model()
        client = APIClient()
        client.force_authenticate(User.objects.get(pk=profile.user_id))
        results = client.get('/api/accounts/contexts/').json()['results']
        organizations = [r for r in results if r['type'] == 'ORGANIZATION']
        self.assertEqual(len(organizations), 1)
        self.assertTrue(organizations[0]['migrated_from_business'])
        self.assertEqual(organizations[0]['role'], 'OWNER')

    def test_empty_database_conversion_is_a_noop(self):
        self.forward()
        self.assertEqual(
            (Organization.objects.count(), Membership.objects.count(), LegacyAccountMapping.objects.count()), (0, 0, 0))
        self.assertEqual(self.new_apps.get_model('moderation', 'AuditLog').objects.filter(action='ORG_CONVERTED').count(), 0)


class RulesTests(ConversionBase):
    def test_clean_name(self):
        self.assertEqual(rules.clean_name('  A​B \n  C\x00 '), 'AB C')
        self.assertEqual(rules.clean_name(None), '')
        self.assertEqual(len(rules.clean_name('x' * 400)), 255)
        self.assertEqual(rules.name_key('Café  ZORGLUB'), rules.name_key('cafe zorglub'))
        self.assertTrue(rules.mixes_scripts('Bаnque'))
        self.assertFalse(rules.mixes_scripts('Banque'))


class PreflightCommandTests(ConversionBase):
    def run_command(self):
        out = io.StringIO()
        call_command('check_legacy_conversion', stdout=out)
        return out.getvalue()

    def snapshot(self):
        from apps.identity.models import BusinessProfile, User
        return (
            list(BusinessProfile.objects.order_by('pk').values()), list(KycDocument.objects.order_by('pk').values()),
            list(User.objects.order_by('pk').values_list('pk', 'is_active', 'user_type')),
            Organization.objects.count(), LegacyAccountMapping.objects.count(), Membership.objects.count(),
        )

    def test_report_has_only_identifiers_and_counts_and_changes_nothing(self):
        full = self.complete_profile()
        banned = self.profile('Banni', user=self.user(is_active=False))
        twin_1 = self.profile('Doublon Zorglub', nif='NIF-DOUBLE')
        twin_2 = self.profile('DOUBLON zorglub', nif='NIF-DOUBLE')
        empty = self.profile('​')
        manual = self.profile('Drapeau', is_verified=True)
        self.doc(manual, 'RCCM')
        orphan_user = self.user('ENTREPRISE')
        before = self.snapshot()
        output = self.run_command()
        self.assertEqual(self.snapshot(), before)

        self.assertIn('profils: 6', output)
        self.assertIn('profils à convertir: 6', output)
        self.assertIn(f'{twin_1.pk}~{twin_2.pk}' if str(twin_1.pk) < str(twin_2.pk) else f'{twin_2.pk}~{twin_1.pk}',
                      output.replace(' ', ''))
        for expected in (str(banned.pk), str(empty.pk), str(manual.pk), str(orphan_user.pk), str(twin_1.pk)):
            self.assertIn(expected, output)
        self.assertIn('propriétaires désactivés (organisation SUSPENDED): 1', output)
        self.assertIn('noms vides ou trop courts après nettoyage (nom neutre): 1', output)
        self.assertIn('profils partageant un NIF non vide: 2', output)
        self.assertIn('pièces dont le fichier est absent du stockage privé: 4', output)
        self.assertIn('is_verified diffère du calcul dérivé des pièces (le drapeau n\'est pas recopié): 1', output)
        for secret in (SECRET_NIF, 'NIF-DOUBLE', SECRET_EMAIL, SECRET_PHONE, SECRET_FULL_NAME, 'Zorglub', 'Banni',
                       'Drapeau', 'Doublon', 'u1@example.com', SECRET_BIO_MARK):
            self.assertNotIn(secret, output)
        self.assertNotIn('@', output)

    def test_after_conversion_nothing_is_left_to_convert(self):
        self.complete_profile()
        self.forward()
        output = self.run_command()
        self.assertIn('profils à convertir: 0', output)
        self.assertIn('profils déjà convertis (correspondance): 1', output)

    def test_missing_table_gives_exit_code_1(self):
        with mock.patch('django.db.backends.base.introspection.BaseDatabaseIntrospection.table_names', return_value=[]):
            with self.assertRaises(SystemExit) as ctx:
                call_command('check_legacy_conversion', stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(ctx.exception.code, 1)
