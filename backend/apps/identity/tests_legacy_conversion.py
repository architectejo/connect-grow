"""Conversion des comptes entreprise en organisations (L0-09 T9-1, spec T9 §2 et §6).

Tests par `MigrationExecutor` : état historique avant `identity 0011`, jeu de données fabriqué, migration en avant
puis retour arrière.

Indépendance du schéma courant (L1-01-B8) : les données converties sont lues par les seuls modèles HISTORIQUES de
l'état `NEW` (`hist`, `self.new_apps`) ; le code courant (services, API) ne s'exécute jamais sur la base figée à
`identity 0011`. Son comportement sur des organisations converties est vérifié dans
`ConvertedWorldOnCurrentSchemaTests`, après conversion PUIS application de toutes les migrations suivantes (le chemin réel de la production), sans aucun
contournement de colonnes. Une nouvelle colonne d'un modèle courant ne casse donc plus ces tests.

Coût maîtrisé : les scénarios en lecture seule partagent UN monde (migration et jeu de données construits une fois
par classe, `_fixture_teardown` neutralisé) ; seuls les scénarios qui modifient l'état (retour arrière, rejeu,
garde, base vierge, volume) reconstruisent le leur.
"""
import importlib
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity import legacy_conversion as rules
from apps.identity import models as current_models
from apps.identity import services as identity_services
from apps.identity.verification import get_verification_summaries
from apps.moderation.services import get_restricted_user_ids

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
MIGRATION = 'apps.identity.migrations.0011_convert_business_profiles'


def migrate_to(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(list(targets) + [executor.loader.graph.leaf_nodes('catalog')[0]])


def state(targets):
    """Modèles historiques (rendu coûteux, sans état : un par jeu de cibles pour tout le module)."""
    key = tuple(targets)
    if key not in _STATE_CACHE:
        executor = MigrationExecutor(connection)
        _STATE_CACHE[key] = executor.loader.project_state(
            list(targets) + [executor.loader.graph.leaf_nodes('catalog')[0]]).apps
    return _STATE_CACHE[key]


class Builder:
    """Fabrique des données à l'ancien schéma, avec les modèles historiques."""

    def __init__(self, apps):
        self.apps = apps
        g = apps.get_model
        self.User, self.Profile, self.ProfileCat, self.Doc = (
            g('identity', n) for n in ('User', 'BusinessProfile', 'BusinessProfileCategory', 'KycDocument'))
        self.Offer, self.Counter, self.Review = (
            g('marketplace', 'Offer'), g('visibility', 'DailyVisibilityCounter'), g('reviews', 'Review'))
        self.Sanction = g('moderation', 'Sanction')
        Req = g('identity', 'OrganizationDocumentRequirement')
        for position, doc_type in enumerate(('RCCM', 'ID_NATIONALE', 'PIECE_GERANT')):
            Req.objects.get_or_create(org_type='ENTREPRISE', document_type=doc_type, defaults={'position': position})
        City, Commune, Category = (g('catalog', n) for n in ('City', 'Commune', 'Category'))
        self.city = City.objects.create(name='Kinshasa', name_key='kinshasa', slug='kinshasa')
        self.commune = Commune.objects.create(city=self.city, name='Gombe', name_key='gombe')
        self.category = Category.objects.create(name='Electronique', name_key='electronique', slug='electronique')
        self.reviewer = self.User.objects.create(email='reviewer@example.com', full_name='Relecteur', is_staff=True)
        self.created_at = timezone.now() - timedelta(days=400)
        self.seq = 0

    def user(self, user_type='ENTREPRISE', **kwargs):
        self.seq += 1
        kwargs.setdefault('email', f'u{self.seq}@example.com')
        kwargs.setdefault('full_name', f'Compte {self.seq}')
        return self.User.objects.create(user_type=user_type, **kwargs)

    def profile(self, name='Atelier', user=None, categories=1, **kwargs):
        user = user or self.user(city_id=self.city.id, commune_id=self.commune.id)
        profile = self.Profile.objects.create(user=user, business_name=name, **kwargs)
        self.Profile.objects.filter(pk=profile.pk).update(created_at=self.created_at)
        for _ in range(categories):
            self.ProfileCat.objects.create(business_profile=profile, category_id=uuid.uuid4())
        profile.refresh_from_db()
        return profile

    def doc(self, profile, doc_type, status='VALIDE', **kwargs):
        if status != 'EN_ATTENTE':
            kwargs.setdefault('reviewed_by', self.reviewer)
            kwargs.setdefault('reviewed_at', timezone.now() - timedelta(days=3))
        return self.Doc.objects.create(
            business_profile=profile, document_type=doc_type, status=status,
            file=f'profile-{profile.pk}/{doc_type}.pdf', **kwargs,
        )

    def sanction(self, user, kind='BANNISSEMENT', is_active=True, ends_at=None):
        return self.Sanction.objects.create(
            user=user, sanction_type=kind, reason='Test', is_active=is_active, ends_at=ends_at)

    def offer(self, owner, title='Offre', public=True):
        return self.Offer.objects.create(
            seller=owner, seller_context_type='USER', seller_context_id=owner.pk, created_by=owner,
            seller_is_public=public, category_id=self.category.id, commune_id=self.commune.id, title=title,
            description='Description suffisamment longue pour passer.', price=1,
            expires_at=timezone.now() + timedelta(days=30),
        )

    def counter(self, offer, views=3):
        return self.Counter.objects.create(
            offer_id=offer.id, seller=offer.seller, seller_context_type='USER', seller_context_id=offer.seller_id,
            date=timezone.localdate(), views=views, shares=1, contacts=2,
        )

    def review(self, offer, rating=5):
        author = self.user('PARTICULIER')
        return self.Review.objects.create(
            user=author, offer_id=offer.id, seller_context_type='USER', seller_context_id=offer.seller_id,
            contact_event_id=uuid.uuid4(), contact_channel='MESSAGE', contact_recorded_at=timezone.now(),
            offer_rating=rating, seller_rating=rating, content='Avis suffisamment long pour être valide.',
        )

    def complete_profile(self):
        """Profil complet : bio, logo, NIF, ville du compte, 3 catégories, 3 pièces validées, `is_verified` vrai."""
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

    def contact_data(self, user):
        """Numéro vérifié et consentements Appel / WhatsApp du compte (jamais copiés sur l'organisation)."""
        ContactPoint, Consent = (self.apps.get_model('identity', n) for n in ('ContactPoint', 'ContactConsent'))
        ContactPoint.objects.create(user=user, phone=SECRET_PHONE, is_verified=True)
        for channel in ('CALL', 'WHATSAPP'):
            Consent.objects.create(user=user, channel=channel, is_granted=True, granted_at=timezone.now(),
                                   text_version='2026-10-v1', phone_last4=SECRET_PHONE[-4:])

    def verification_profiles(self):
        """(deux pièces validées, une refusée, drapeau manuel sans pièce) : règle 3."""
        two = self.profile('Deux pieces', is_verified=False)
        for doc_type in ('RCCM', 'ID_NATIONALE'):
            self.doc(two, doc_type)
        refused = self.profile('Refusee', is_verified=False)
        self.doc(refused, 'RCCM', status='REFUSE', rejection_reason='Illisible')
        self.doc(refused, 'ID_NATIONALE', status='EN_ATTENTE')
        return two, refused, self.profile('Drapeau manuel', is_verified=True)

    def sanctioned_profiles(self):
        """Un profil par cas de sanction (M1), clé -> profil."""
        now = timezone.now()
        scenarios = {
            'ban': ('BANNISSEMENT', True, None),
            'timed': ('SUSPENSION_TEMPORAIRE', True, now + timedelta(days=5)),
            'expired': ('SUSPENSION_TEMPORAIRE', True, now - timedelta(days=5)),
            'lifted': ('BANNISSEMENT', False, None),
            'warning': ('AVERTISSEMENT', True, None),
        }
        profiles = {}
        for key, (kind, active, ends) in scenarios.items():
            profiles[key] = self.profile(f'Sanction {key}')
            self.sanction(profiles[key].user, kind, active, ends)
        return profiles

    def conflict_profiles(self):
        """(propriétaire membre du personnel, futur ancien propriétaire), chacun avec une pièce en attente."""
        staff_owner = self.profile('Chez le personnel', user=self.user(is_staff=True))
        revoked_owner = self.profile('Ancien proprietaire')
        for p in (staff_owner, revoked_owner):
            self.doc(p, 'RCCM', status='EN_ATTENTE')
        return staff_owner, revoked_owner


def hist(name, app='identity'):
    """Modèle HISTORIQUE à l'état converti (`NEW`, identity 0011). Les assertions sur les données converties ne lisent
    jamais un modèle courant : ses colonnes ajoutées depuis (périmètre, revue de création…) n'existent pas à ce schéma,
    et chaque nouvelle colonne casserait ces tests sans rapport avec la conversion. Le comportement du code courant sur
    des données converties est vérifié à part, au dernier schéma (`ConvertedWorldOnCurrentSchemaTests`)."""
    return state(NEW).get_model(app, name)


def org_of(profile):
    return hist('Organization').objects.get(legacy_business_profile_id=profile.pk)


class SharedStateTestCase(TransactionTestCase):
    """Un monde construit et migré une fois pour la classe ; les tests le lisent sans le modifier."""

    @classmethod
    def build(cls, b):
        raise NotImplementedError

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        migrate_to(OLD)
        cls.b = Builder(state(OLD))
        cls.build(cls.b)

    def setUp(self):
        cache.clear()

    def _fixture_teardown(self):  # pas de vidage entre les tests : le monde est partagé
        pass

    @classmethod
    def tearDownClass(cls):
        try:
            call_command('migrate', verbosity=0)
            call_command('flush', verbosity=0, interactive=False)
        finally:
            super().tearDownClass()


def forward():
    migrate_to(NEW)
    return state(NEW)


class ConvertedWorldTests(SharedStateTestCase):
    @classmethod
    def build(cls, b):
        w = cls.w = type('World', (), {})()
        w.full = b.complete_profile()
        w.docs_before = {
            d.pk: (d.document_type, d.status, d.rejection_reason, d.reviewed_by_id, d.reviewed_at, d.file.name)
            for d in b.Doc.objects.filter(business_profile=w.full)
        }
        w.categories = set(b.ProfileCat.objects.filter(business_profile=w.full).values_list('category_id', flat=True))
        w.owner_id = w.full.user_id
        w.biz_offers = [b.offer(w.full.user, 'Offre A'), b.offer(w.full.user, 'Offre B')]
        w.biz_counters = [b.counter(o) for o in w.biz_offers]
        w.biz_reviews = [b.review(o) for o in w.biz_offers]
        b.contact_data(w.full.user)
        w.public_offer = w.biz_offers[0]
        w.two, w.refused, w.manual = b.verification_profiles()  # règle 3
        # Critère de conversion
        w.particulier = b.profile('Chez un particulier', user=b.user('PARTICULIER'))
        w.no_profile = b.user('ENTREPRISE')
        w.no_profile_offer = b.offer(w.no_profile, 'Sans profil')
        w.person = b.user('PARTICULIER')
        w.person_offer = b.offer(w.person, 'Offre perso')
        w.person_counter, w.person_review = b.counter(w.person_offer), b.review(w.person_offer)
        w.staff_plain = b.user('PARTICULIER', is_staff=True, is_superuser=True)
        w.no_offer = b.profile('Sans offre')
        # Propriétaires désactivés ou sanctionnés (M1)
        w.inactive = b.profile('Desactive', user=b.user(is_active=False))
        w.inactive_offer = b.offer(w.inactive.user, public=False)
        w.sanctioned = b.sanctioned_profiles()
        w.sanction_offers = {key: b.offer(p.user, f'offre {key}', public=True) for key, p in w.sanctioned.items()}
        w.pre_private = b.profile('Deja prive')
        w.pre_private_offer = b.offer(w.pre_private.user, public=False)
        # Noms et tailles
        w.control = b.profile('  Atelier​ \t Control\x00e  ')
        w.empty, w.short = b.profile('​ ‎ '), b.profile('A')
        w.long_name = b.profile('N' * 300)
        w.twin_1, w.twin_2 = b.profile('Café Zorglub'), b.profile('cafe  zorglub')
        w.mixed = b.profile('Bаnque')
        w.big = b.profile('Gros profil', categories=7, bio='x' * 2500)
        w.staff_owner, w.revoked_owner = b.conflict_profiles()  # pièces et conflit d'intérêts
        w.other_org = b.apps.get_model('identity', 'Organization').objects.create(name='Preexistante', org_type='ONG')
        w.mixed_doc = b.doc(b.profile('Incoherent'), 'RCCM')
        b.Doc.objects.filter(pk=w.mixed_doc.pk).update(organization=w.other_org)
        w.profile_count = b.Profile.objects.count()
        cls.new_apps = forward()

    # -- mapping -----------------------------------------------------------------------------------------
    def test_complete_profile_is_converted_field_by_field(self):
        w = self.w
        org = org_of(w.full)
        # Ville et commune : celles du compte (donnée personnelle) ne sont PAS reprises (le profil n'en avait pas).
        self.assertEqual(
            (org.name, org.org_type, org.description, org.logo.name, org.nif, org.city_id, org.commune_id, org.status,
             org.suspension_reason, org.created_by_id, org.legacy_business_profile_id),
            ('Atelier Zorglub', 'ENTREPRISE', f'Menuiserie {SECRET_BIO_MARK}.', 'business_logos/zorglub.png', SECRET_NIF,
             None, None, 'ACTIVE', '', w.owner_id, w.full.pk),
        )
        self.assertEqual(org.created_at, w.full.created_at)
        self.assertEqual(
            set(hist('OrganizationCategory').objects.filter(organization=org).values_list('category_id', flat=True)),
            w.categories)
        members = list(hist('Membership').objects.filter(organization=org).values_list(
            'user_id', 'role', 'status', 'added_by_id', 'ended_at', 'joined_at',
        ))
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0][:5], (w.owner_id, 'OWNER', 'ACTIVE', None, None))
        self.assertEqual(members[0][5], w.full.created_at)
        mapping = hist('LegacyAccountMapping').objects.get(user_id=w.owner_id)
        self.assertEqual(mapping.organization_id, org.pk)
        docs = hist('KycDocument').objects.filter(organization=org)
        self.assertEqual(docs.count(), 3)
        for doc in docs:
            self.assertEqual(doc.uploaded_by_id, w.owner_id)
            historical = self.new_apps.get_model('identity', 'KycDocument').objects.get(pk=doc.pk)
            self.assertEqual(historical.business_profile_id, w.full.pk)  # l'ancien lien reste jusqu'à la contraction
            self.assertEqual(
                (doc.document_type, doc.status, doc.rejection_reason, doc.reviewed_by_id, doc.reviewed_at, doc.file.name),
                w.docs_before[doc.pk])
        self.assertEqual(self.new_apps.get_model('identity', 'BusinessProfile').objects.count(), w.profile_count)

    def test_account_address_is_never_copied(self):
        self.assertFalse(hist('Organization').objects.filter(legacy_business_profile_id__isnull=False)
                         .exclude(city_id=None, commune_id=None).exists())

    def test_conversion_criterion_is_the_profile_not_user_type(self):
        w = self.w
        self.assertTrue(hist('Organization').objects.filter(legacy_business_profile_id=w.particulier.pk).exists())
        self.assertEqual(
            hist('Organization').objects.filter(legacy_business_profile_id__isnull=False).count(), w.profile_count)
        self.assertFalse(
            hist('LegacyAccountMapping').objects.filter(user_id__in=[w.no_profile.pk, w.person.pk]).exists())

    def test_only_the_profile_owner_gets_a_role(self):
        w = self.w
        self.assertEqual(hist('Membership').objects.count(), w.profile_count)
        self.assertEqual(
            set(hist('Membership').objects.values_list('role', 'status', 'added_by')), {('OWNER', 'ACTIVE', None)})
        self.assertFalse(hist('Membership').objects.filter(user_id=w.staff_plain.pk).exists())
        # Le personnel propriétaire d'un ancien profil reçoit son appartenance de propriétaire, rien de plus.
        self.assertEqual(hist('Membership').objects.filter(user_id=w.staff_owner.user_id).count(), 1)

    def test_profile_without_offer_is_converted_active(self):
        self.assertEqual(org_of(self.w.no_offer).status, 'ACTIVE')

    def test_names_are_cleaned_never_rejected_and_never_merged(self):
        w = self.w
        self.assertEqual(org_of(w.control).name, 'Atelier Controle')
        for profile in (w.empty, w.short):
            self.assertEqual(org_of(profile).name, f'Organisation {str(profile.pk)[:8]}')
        self.assertEqual(len(org_of(w.long_name).name), 255)
        self.assertNotEqual(org_of(w.twin_1).pk, org_of(w.twin_2).pk)
        self.assertEqual((org_of(w.twin_1).name, org_of(w.twin_2).name), ('Café Zorglub', 'cafe zorglub'))
        self.assertEqual(org_of(w.mixed).name, 'Bаnque')

    def test_long_description_is_truncated_and_all_categories_are_kept(self):
        org = org_of(self.w.big)
        self.assertEqual(len(org.description), 2000)
        self.assertEqual(org.category_links.count(), 7)
        self.assertEqual(self.b.Profile.objects.get(pk=self.w.big.pk).bio, 'x' * 2500)

    def test_missing_logo_gives_no_logo(self):
        self.assertFalse(org_of(self.w.no_offer).logo)

    def test_document_already_on_an_organization_is_left_alone(self):
        self.assertEqual(hist('KycDocument').objects.get(pk=self.w.mixed_doc.pk).organization_id, self.w.other_org.pk)

    # -- suspension (M1) ---------------------------------------------------------------------------------
    def test_initial_status_follows_the_state_of_the_owner(self):
        w = self.w
        expected = {
            'ban': 'SUSPENDED', 'timed': 'SUSPENDED', 'expired': 'ACTIVE', 'lifted': 'ACTIVE', 'warning': 'ACTIVE',
        }
        for key, status in expected.items():
            org = org_of(w.sanctioned[key])
            self.assertEqual(org.status, status, key)
            self.assertEqual(org.suspension_reason, 'other' if status == 'SUSPENDED' else '', key)
        inactive = org_of(w.inactive)
        self.assertEqual((inactive.status, inactive.suspension_reason), ('SUSPENDED', 'other'))

    def test_offers_of_suspended_organizations_are_not_public(self):
        w = self.w
        Offer = self.new_apps.get_model('marketplace', 'Offer')
        public = {key: Offer.objects.get(pk=o.pk).seller_is_public for key, o in w.sanction_offers.items()}
        self.assertEqual(public, {'ban': False, 'timed': False, 'expired': True, 'lifted': True, 'warning': True})
        row = Offer.objects.get(pk=w.inactive_offer.pk)
        self.assertEqual((row.seller_context_type, row.seller_context_id, row.seller_is_public),
                         ('ORGANIZATION', org_of(w.inactive).pk, False))

    def test_an_already_private_offer_is_never_made_public(self):
        row = self.new_apps.get_model('marketplace', 'Offer').objects.get(pk=self.w.pre_private_offer.pk)
        self.assertEqual((row.seller_context_type, row.seller_is_public), ('ORGANIZATION', False))

    def test_audit_status_follows_the_suspension(self):
        w = self.w
        AuditLog = self.new_apps.get_model('moderation', 'AuditLog')
        status = lambda p: AuditLog.objects.get(action='ORG_CONVERTED', target_id=org_of(p).pk).details  # noqa: E731
        self.assertTrue(status(w.sanctioned['ban']).endswith('status=SUSPENDED'))
        self.assertTrue(status(w.sanctioned['expired']).endswith('status=ACTIVE'))

    # -- offres, compteurs, avis -------------------------------------------------------------------------
    def test_offers_counters_and_reviews_follow_the_organization(self):
        w = self.w
        org = org_of(w.full)
        Offer, Counter, Review = (self.new_apps.get_model(a, m) for a, m in (
            ('marketplace', 'Offer'), ('visibility', 'DailyVisibilityCounter'), ('reviews', 'Review')))
        for offer in w.biz_offers:
            row = Offer.objects.get(pk=offer.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id, row.created_by_id, row.seller_is_public),
                             ('ORGANIZATION', org.pk, w.owner_id, True))
            self.assertEqual(row.seller_id, w.owner_id)  # FK inchangée jusqu'à la contraction
        for counter in w.biz_counters:
            row = Counter.objects.get(pk=counter.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id, row.views, row.shares, row.contacts),
                             ('ORGANIZATION', org.pk, 3, 1, 2))
        for review in w.biz_reviews:
            row = Review.objects.get(pk=review.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id, row.counts_for_seller),
                             ('ORGANIZATION', org.pk, True))
        for row in (w.person_offer, w.no_profile_offer):
            current = Offer.objects.get(pk=row.pk)
            self.assertEqual((current.seller_context_type, current.seller_context_id), ('USER', row.seller_id))
        self.assertEqual(Counter.objects.get(pk=w.person_counter.pk).seller_context_type, 'USER')
        self.assertEqual(Review.objects.get(pk=w.person_review.pk).seller_context_type, 'USER')

    def test_audit_log_has_one_line_per_conversion_and_only_identifiers(self):
        w = self.w
        AuditLog = self.new_apps.get_model('moderation', 'AuditLog')
        lines = list(AuditLog.objects.filter(action='ORG_CONVERTED'))
        self.assertEqual(len(lines), hist('LegacyAccountMapping').objects.count())
        self.assertEqual(len(lines), w.profile_count)
        by_org = {line.target_id: line for line in lines}
        for mapping in hist('LegacyAccountMapping').objects.all():
            line = by_org[mapping.organization_id]
            org = hist('Organization').objects.get(pk=mapping.organization_id)
            self.assertEqual((line.actor_id, line.target_type, line.context_type, line.context_id),
                             (None, 'organization', 'ORGANIZATION', org.pk))
            self.assertEqual(line.details, f'legacy_business_profile={org.legacy_business_profile_id}; status={org.status}')
        self.assertIn('status=SUSPENDED', by_org[org_of(w.inactive).pk].details)
        blob = ' '.join(f'{line.details} {line.target_type} {line.action}' for line in lines)
        for secret in (SECRET_NIF, SECRET_EMAIL, SECRET_PHONE, SECRET_FULL_NAME, 'Zorglub', SECRET_BIO_MARK):
            self.assertNotIn(secret, blob)


class ConvertedWorldOnCurrentSchemaTests(SharedStateTestCase):
    """Code COURANT sur des organisations converties : monde construit à l'ancien schéma, converti (`NEW`), puis porté
    au dernier schéma par toutes les migrations suivantes, comme en production. Aucune lecture de colonne n'est
    neutralisée : une régression du code courant sur une organisation convertie fait échouer ces tests."""

    @classmethod
    def build(cls, b):
        w = cls.w = type('World', (), {})()
        w.full = b.complete_profile()
        w.owner_id = w.full.user_id
        w.public_offer = b.offer(w.full.user, 'Offre A')
        b.contact_data(w.full.user)
        w.two, w.refused, w.manual = b.verification_profiles()
        w.sanctioned = b.sanctioned_profiles()
        w.staff_owner, w.revoked_owner = b.conflict_profiles()
        forward()
        call_command('migrate', verbosity=0)  # identity 0012 et suivantes : dernier schéma

    @staticmethod
    def current_org_of(profile):
        """Organisation convertie, lue par le modèle COURANT (dernier schéma)."""
        return current_models.Organization.objects.get(legacy_business_profile_id=profile.pk)

    def test_converted_organizations_take_the_defaults_of_later_columns(self):
        """Les colonnes ajoutées après la conversion prennent leur valeur par défaut : une organisation convertie reste
        publique (aucune revue de création rétroactive, ADR 0010 §10) et ses appartenances couvrent l'organisation."""
        org = self.current_org_of(self.w.full)
        self.assertEqual(org.creation_review_status, current_models.Organization.CREATION_REVIEW_NONE)
        self.assertEqual(
            set(current_models.Membership.objects.filter(organization=org).values_list('scope_type', 'scope_id')),
            {('ORGANIZATION', None)},
        )
        self.assertTrue(identity_services.is_seller_context_public('ORGANIZATION', org.pk))

    def test_blocking_rule_agrees_with_moderation(self):
        now = timezone.now()
        cases = [
            ('BANNISSEMENT', True, None, True), ('SUSPENSION_TEMPORAIRE', True, now + timedelta(days=1), True),
            ('SUSPENSION_TEMPORAIRE', True, now - timedelta(days=1), False), ('BANNISSEMENT', False, None, False),
            ('AVERTISSEMENT', True, None, False), ('MASQUAGE_ANNONCE', True, None, False),
        ]
        for kind, active, ends, expected in cases:
            self.assertIs(rules.is_blocking(kind, active, ends, now), expected, (kind, active, ends))
        self.assertTrue(rules.owner_is_suspended(False, False))
        self.assertTrue(rules.owner_is_suspended(True, True))
        self.assertFalse(rules.owner_is_suspended(True, False))
        # La commande de pré-vol utilise `get_restricted_user_ids` : même résultat que `is_blocking`.
        owners = {key: p.user_id for key, p in self.w.sanctioned.items()}
        self.assertEqual({key for key, uid in owners.items() if uid in get_restricted_user_ids(owners.values())},
                         {'ban', 'timed'})

    def test_derived_verification_matches_the_old_flag(self):
        w = self.w
        profiles = (w.full, w.two, w.refused, w.manual)
        summaries = get_verification_summaries([self.current_org_of(p).pk for p in profiles])
        complete = {p.business_name: summaries[self.current_org_of(p).pk]['summary']['complete'] for p in profiles}
        self.assertEqual(complete, {'Atelier Zorglub': True, 'Deux pieces': False, 'Refusee': False,
                                    'Drapeau manuel': False})
        self.assertEqual({p.business_name: p.is_verified for p in profiles},
                         {'Atelier Zorglub': True, 'Deux pieces': False, 'Refusee': False, 'Drapeau manuel': True})
        self.assertEqual([c['code'] for c in summaries[self.current_org_of(w.full).pk]['verified_claims']],
                         ['RCCM_VERIFIED', 'NATIONAL_ID_VERIFIED', 'REPRESENTATIVE_VERIFIED'])
        self.assertEqual(len(summaries[self.current_org_of(w.two).pk]['verified_claims']), 2)
        self.assertEqual(summaries[self.current_org_of(w.refused).pk]['verified_claims'], [])
        self.assertEqual(summaries[self.current_org_of(w.manual).pk]['verified_claims'], [])
        refused = current_models.KycDocument.objects.get(organization=self.current_org_of(w.refused), document_type='RCCM')
        self.assertEqual((refused.status, refused.rejection_reason), ('REFUSE', 'Illisible'))

    def test_converted_owner_cannot_decide_their_own_pieces(self):
        User = get_user_model()
        for profile in (self.w.staff_owner, self.w.revoked_owner):
            doc = current_models.KycDocument.objects.get(organization=self.current_org_of(profile))
            with self.assertRaises(identity_services.KycError) as ctx:
                identity_services.decide_kyc_document(doc.pk, User.objects.get(pk=profile.user_id), 'VALIDE')
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertEqual(current_models.KycDocument.objects.get(pk=doc.pk).status, 'EN_ATTENTE')

    def test_a_revoked_owner_still_cannot_decide_nor_download(self):
        User = get_user_model()
        profile = self.w.revoked_owner
        Membership = current_models.Membership
        membership = Membership.objects.filter(organization=self.current_org_of(profile))
        membership.update(status=Membership.STATUS_REVOKED)
        try:
            doc = current_models.KycDocument.objects.get(organization=self.current_org_of(profile))
            reviewer = User.objects.get(pk=profile.user_id)
            with self.assertRaises(identity_services.KycError) as ctx:
                identity_services.decide_kyc_document(doc.pk, reviewer, 'VALIDE')
            self.assertEqual(ctx.exception.status_code, 403)
            with self.assertRaises(identity_services.KycError) as ctx:
                identity_services.get_document_for_download(doc.pk, reviewer)
            self.assertEqual(ctx.exception.status_code, 403)
            # Plus aucune route ne donne accès aux pièces à un ancien propriétaire (anciennes routes retirées : 404).
            client = APIClient()
            client.force_authenticate(reviewer)
            self.assertEqual(client.get('/api/v1/accounts/kyc/documents/').status_code, 404)
            self.assertEqual(client.post('/api/v1/accounts/kyc/documents/', {}, format='json').status_code, 404)
            self.assertEqual(client.delete(f'/api/v1/accounts/kyc/documents/{doc.pk}/').status_code, 404)
            # La route d'organisation refuse aussi un ancien membre (code d'autorisation courant, sans contournement).
            organization_id = self.current_org_of(profile).pk
            refused = client.get(f'/api/v1/accounts/organizations/{organization_id}/kyc/documents/')
            self.assertEqual(refused.status_code, 403)
        finally:
            membership.update(status=Membership.STATUS_ACTIVE)

    @staticmethod
    def read_public_api(client, w, org):
        return (
            client.get(f'/api/v1/marketplace/posts/{w.public_offer.pk}/'),
            client.get('/api/v1/accounts/organizations/'),
            client.get(f'/api/v1/marketplace/sellers/organization/{org.pk}/'),
        )

    def test_no_contact_data_is_copied_and_the_public_api_leaks_nothing(self):
        w = self.w
        org = self.current_org_of(w.full)
        self.assertFalse(current_models.ContactPoint.objects.filter(organization__isnull=False).exists())
        self.assertFalse(current_models.ContactConsent.objects.filter(organization__isnull=False).exists())
        self.assertEqual(current_models.ContactConsent.objects.filter(user_id=w.owner_id).count(), 2)
        detail, listing, page = self.read_public_api(APIClient(), w, org)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['allowed_channels'], ['MESSAGE'])
        self.assertEqual(detail.json()['seller']['context_type'], 'ORGANIZATION')
        self.assertEqual(detail.json()['seller']['context_id'], str(org.pk))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(set(listing.json()['results'][0]), {
            'id', 'name', 'org_type', 'description', 'logo', 'city_id', 'commune_id', 'category_ids',
            'verified_claims', 'verification_summary', 'member_since',
        })
        self.assertEqual(page.status_code, 200)
        for response in (detail, listing, page):
            text = response.content.decode()
            for secret in (SECRET_NIF, SECRET_EMAIL, SECRET_PHONE, SECRET_FULL_NAME, str(w.owner_id)):
                self.assertNotIn(secret, text)

    def test_converted_organization_is_listed_in_the_contexts_of_its_owner(self):
        client = APIClient()
        client.force_authenticate(get_user_model().objects.get(pk=self.w.owner_id))
        response = client.get('/api/v1/accounts/contexts/')
        organizations = [r for r in response.json()['results'] if r['type'] == 'ORGANIZATION']
        self.assertEqual(len(organizations), 1)
        self.assertTrue(organizations[0]['migrated_from_business'])
        self.assertEqual(organizations[0]['role'], 'OWNER')


class RulesTests(SimpleTestCase):
    def test_clean_name(self):
        self.assertEqual(rules.clean_name('  A​B \n  C\x00 '), 'AB C')
        self.assertEqual(rules.clean_name(None), '')
        self.assertEqual(len(rules.clean_name('x' * 400)), 255)
        self.assertEqual(len(rules.clean_name_full('x' * 400)), 400)
        self.assertEqual(rules.name_key('Café  ZORGLUB'), rules.name_key('cafe zorglub'))
        self.assertTrue(rules.mixes_scripts('Bаnque'))
        self.assertFalse(rules.mixes_scripts('Banque'))


class RollbackAndReplayTests(TransactionTestCase):
    """Scénarios qui modifient l'état : chacun reconstruit son monde à l'ancien schéma."""

    def setUp(self):
        cache.clear()
        migrate_to(OLD)
        self.b = Builder(state(OLD))

    def tearDown(self):
        # Les profils historiques ne sont plus un modèle courant : le `flush` de Django ne les vide pas (clés
        # étrangères vers les comptes). On les vide ici, à l'état historique.
        migrate_to(NEW)
        state(NEW).get_model('identity', 'BusinessProfile').objects.all().delete()

    @classmethod
    def tearDownClass(cls):
        try:
            call_command('migrate', verbosity=0)
        finally:
            super().tearDownClass()

    def seed(self):
        b = self.b
        self.business = b.complete_profile()
        self.offers = [b.offer(self.business.user, 'Offre A'), b.offer(self.business.user, 'Offre B')]
        self.counters = [b.counter(o) for o in self.offers]
        self.reviews = [b.review(o) for o in self.offers]
        self.person = b.user('PARTICULIER')
        b.offer(self.person, 'Offre perso')
        self.banned = b.profile('Banni', user=b.user(is_active=False))
        self.banned_offer = b.offer(self.banned.user, public=False)
        self.private_offer = b.offer(b.profile('Prive').user, 'Deja prive', public=False)

    def counts(self):
        return tuple(
            hist(name).objects.count()
            for name in ('Organization', 'Membership', 'LegacyAccountMapping', 'OrganizationCategory')
        )

    def test_rollback_restores_the_contexts_and_deletes_nothing_then_forward_again_duplicates_nothing(self):
        self.seed()
        new = forward()
        counts = self.counts()
        audits = new.get_model('moderation', 'AuditLog').objects.filter(action='ORG_CONVERTED').count()

        migrate_to(OLD)
        old = state(OLD)
        Offer, Counter, Review = (old.get_model(a, m) for a, m in (
            ('marketplace', 'Offer'), ('visibility', 'DailyVisibilityCounter'), ('reviews', 'Review')))
        self.assertEqual((Offer.objects.count(), Counter.objects.count(), Review.objects.count()), (5, 2, 2))
        for offer in self.offers:
            row = Offer.objects.get(pk=offer.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id, row.seller_is_public),
                             ('USER', self.business.user_id, True))
        for counter in self.counters:
            self.assertEqual(Counter.objects.get(pk=counter.pk).seller_context_type, 'USER')
        for review in self.reviews:
            row = Review.objects.get(pk=review.pk)
            self.assertEqual((row.seller_context_type, row.seller_context_id), ('USER', self.business.user_id))
        # Compte désactivé : offres non publiques ; offre déjà privée : jamais rendue publique.
        self.assertEqual((Offer.objects.get(pk=self.banned_offer.pk).seller_context_type,
                          Offer.objects.get(pk=self.banned_offer.pk).seller_is_public), ('USER', False))
        self.assertFalse(Offer.objects.get(pk=self.private_offer.pk).seller_is_public)
        # Création des organisations en `noop` au retour arrière : rien n'est supprimé.
        self.assertEqual(self.counts(), counts)
        self.assertEqual(old.get_model('identity', 'BusinessProfile').objects.count(), 3)

        new = forward()
        self.assertEqual(self.counts(), counts)
        self.assertEqual(new.get_model('moderation', 'AuditLog').objects.filter(action='ORG_CONVERTED').count(), audits)
        self.assertEqual(new.get_model('marketplace', 'Offer').objects.filter(
            seller_context_type='ORGANIZATION').count(), 4)

    def test_second_run_of_every_function_changes_nothing(self):
        self.seed()
        new = forward()

        def snapshot():
            return (
                self.counts(),
                sorted(new.get_model('moderation', 'AuditLog').objects.values_list('pk', flat=True)),
                sorted(new.get_model('marketplace', 'Offer').objects.values_list('pk', 'seller_context_id', 'seller_is_public')),
            )

        before = snapshot()
        for module, name in (
            (MIGRATION, 'convert_profiles'),
            ('apps.marketplace.migrations.0010_convert_offer_contexts', 'to_organizations'),
            ('apps.visibility.migrations.0006_convert_counter_contexts', 'to_organizations'),
            ('apps.reviews.migrations.0006_convert_review_contexts', 'to_organizations'),
            ('apps.moderation.migrations.0005_audit_legacy_conversion', 'audit'),
        ):
            getattr(importlib.import_module(module), name)(new, None)
        self.assertEqual(snapshot(), before)

    def test_lost_mapping_is_recovered_without_duplicating_the_organization(self):
        profile = self.b.profile('Reprise')
        new = forward()
        org_id = org_of(profile).pk
        hist('LegacyAccountMapping').objects.all().delete()
        hist('Membership').objects.all().delete()
        importlib.import_module(MIGRATION).convert_profiles(new, None)
        self.assertEqual(hist('Organization').objects.count(), 1)
        self.assertEqual(hist('LegacyAccountMapping').objects.get().organization_id, org_id)
        self.assertEqual(hist('Membership').objects.filter(organization_id=org_id, role='OWNER').count(), 1)

    def test_incomplete_conversion_aborts_with_a_clear_error(self):
        self.b.profile('Reprise')
        new = forward()
        hist('LegacyAccountMapping').objects.all().delete()
        hist('Membership').objects.all().delete()
        # Modèle historique : à ce schéma, la table des invitations (identity 0015) n'existe pas encore.
        new.get_model('identity', 'Organization').objects.all().delete()
        Mapping = new.get_model('identity', 'LegacyAccountMapping')
        with mock.patch.object(Mapping.objects, 'create', return_value=None):  # la correspondance n'est pas écrite
            with self.assertRaises(RuntimeError) as ctx:
                importlib.import_module(MIGRATION).convert_profiles(new, None)
        self.assertIn('Conversion incomplète', str(ctx.exception))

    def test_empty_database_conversion_is_a_noop(self):
        new = forward()
        self.assertEqual(self.counts(), (0, 0, 0, 0))
        self.assertEqual(new.get_model('moderation', 'AuditLog').objects.filter(action='ORG_CONVERTED').count(), 0)

    def test_query_count_is_linear_in_the_number_of_profiles(self):
        """Volume : 200 profils convertis par la migration en un nombre de requêtes borné par profil (pas
        quadratique). Les migrations de contexte par ligne de correspondance restent un N+1 assumé avant la production."""
        b = self.b
        for i in range(200):
            profile = b.profile(f'Boutique {i}', categories=2)
            b.doc(profile, 'RCCM')
        with CaptureQueriesContext(connection) as queries:
            forward()
        self.assertEqual(hist('Organization').objects.count(), 200)
        self.assertEqual(hist('Membership').objects.count(), 200)
        self.assertLess(len(queries), 200 * 15)
