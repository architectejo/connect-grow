"""API des organisations (L0-09g / T8) : création, liste publique, détail interne, modification (verrou de nom),
archivage, sortie, limites, inscription et `me/` sans type de compte. ADR 0006, sections 9.2, 9.5, 12 et 17.2."""
import json
import uuid
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.catalog.models import Category, City, Commune
from apps.common.contexts import CONTEXT_ORGANIZATION, DENY_OBJECT_STATE, DENY_PERMISSION, DENY_RELATION, DENY_SECURITY
from apps.common.factories import make_test_image
from apps.moderation.models import AuditLog, Sanction
from apps.platform_core.models import OutboxEvent

from . import capabilities, services
from .models import (
    IdentitySettings, KycDocument, Membership, Organization, OrganizationCategory,
    OrganizationDocumentRequirement, User,
)
from .tests_route_guard import collect_unguarded_write_routes

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'org-api-throttle'}}
ORGS = '/api/accounts/organizations/'
LIMITS = ORGS + 'limits/'
OWNER, ADMIN, EDITOR, ANALYST = capabilities.ROLE_OWNER, capabilities.ROLE_ADMIN, capabilities.ROLE_EDITOR, capabilities.ROLE_ANALYST

INTERNAL_KEYS = {
    'id', 'name', 'org_type', 'description', 'logo', 'nif', 'city_id', 'commune_id', 'category_ids', 'status',
    'created_at', 'my_role', 'capabilities', 'migrated_from_business', 'verification',
}
VERIFICATION_KEYS = {'required', 'verified_claims', 'summary'}
PUBLIC_KEYS = {
    'id', 'name', 'org_type', 'description', 'logo', 'city_id', 'commune_id', 'category_ids', 'verified_claims',
    'verification_summary', 'member_since',
}
SECRET_NAME = 'Sentinelle-Orga-API'
MEMBER_EMAIL = 'membre.secret@example.com'
MEMBER_PHONE = '+243999000222'
MEMBER_NAME = 'Prénom Secret-Membre'
NIF = 'NIF-SECRET-8421'


def make_user(label, **extra):
    extra.setdefault('phone_verified', True)
    extra.setdefault('full_name', f'Nom {label}')
    return User.objects.create_user(email=f'{label}@example.com', password='x', **extra)


def make_org(name='Atelier', org_type='ENTREPRISE', **extra):
    return Organization.objects.create(name=name, org_type=org_type, **extra)


def make_led_org(name='Atelier', org_type='ENTREPRISE', **extra):
    """Organisation listable publiquement : elle a un propriétaire actif non sanctionné (ADR 0006, A7)."""
    organization = make_org(name, org_type, **extra)
    owner = User.objects.create_user(email=f'owner-{uuid.uuid4().hex[:10]}@example.com', password='x', full_name='Propriétaire')
    Membership.objects.create(organization=organization, user=owner, role=OWNER, status=Membership.STATUS_ACTIVE)
    return organization


def join(org, user, role=OWNER, status=Membership.STATUS_ACTIVE):
    return Membership.objects.create(organization=org, user=user, role=role, status=status)


def truncated_images():
    """PNG et JPEG valides coupés en deux : l'en-tête est lisible, le décodage échoue."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    def encoded(fmt):
        buffer = io.BytesIO()
        Image.new('RGB', (300, 300), (10, 200, 30)).save(buffer, format=fmt)
        return buffer.getvalue()

    png, jpeg = encoded('PNG'), encoded('JPEG')
    return {
        'png': SimpleUploadedFile('l.png', png[:len(png) // 2], content_type='image/png'),
        'jpeg': SimpleUploadedFile('l.jpg', jpeg[:len(jpeg) // 2], content_type='image/jpeg'),
    }


def add_document(org, document_type, status=KycDocument.STATUS_VALIDE, reviewed_at=None):
    """Pièce de l'organisation (rattachée à l'organisation seule, sans profil d'entreprise historique)."""
    return KycDocument.objects.create(
        organization=org, document_type=document_type, status=status, reviewed_at=reviewed_at,
    )


class ApiBase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('proprio')
        self.client = self.login(self.user)

    @staticmethod
    def login(user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def assertDenied(self, response, code):
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()['code'], code)

    def create_via_api(self, **body):
        body.setdefault('name', 'Atelier X')
        body.setdefault('org_type', 'ENTREPRISE')
        return self.client.post(ORGS, body, format='json')


# --- Création ------------------------------------------------------------------------------------------------

class CreateTests(ApiBase):
    def test_nominal_creation_returns_the_internal_object_and_makes_the_creator_owner(self):
        city = City.objects.create(name='Kinshasa')
        commune = Commune.objects.create(city=city, name='Gombe')
        category = Category.objects.create(name='Mode', slug='mode')
        response = self.create_via_api(
            name='  Atelier   X ', description='Couture', nif=NIF, category_ids=[str(category.id)],
            city_id=str(city.id), commune_id=str(commune.id),
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(set(body), INTERNAL_KEYS)
        self.assertEqual(set(body['verification']), VERIFICATION_KEYS)
        self.assertEqual(
            (body['name'], body['my_role'], body['status'], body['nif'], body['logo'], body['migrated_from_business']),
            ('Atelier X', OWNER, 'ACTIVE', NIF, None, False),
        )
        self.assertEqual(body['category_ids'], [str(category.id)])
        self.assertEqual((body['city_id'], body['commune_id']), (str(city.id), str(commune.id)))
        self.assertEqual(body['capabilities'], capabilities.capabilities_for_role(OWNER))
        organization = Organization.objects.get(pk=body['id'])
        membership = Membership.objects.get(organization=organization)
        self.assertEqual((membership.user, membership.role, membership.status), (self.user, OWNER, 'ACTIVE'))
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_verification_block_lists_the_pieces_required_for_the_type(self):
        required = self.create_via_api(org_type='ONG').json()['verification']['required']
        self.assertEqual(
            [(r['document_type'], r['state']) for r in required],
            [(r.document_type, 'NONE') for r in OrganizationDocumentRequirement.objects.filter(org_type='ONG').order_by('position')],
        )
        self.assertTrue(all(r['label'] for r in required))
        self.assertIn('ARRETE_ONG', [r['document_type'] for r in required])

    def test_audit_event_and_no_personal_data_in_them(self):
        body = self.create_via_api(name=SECRET_NAME, nif=NIF).json()
        entry = AuditLog.objects.get(action='ORG_CREATED')
        self.assertEqual((entry.actor, entry.context_type, str(entry.context_id)), (self.user, CONTEXT_ORGANIZATION, body['id']))
        event = OutboxEvent.objects.get(event_type='identity.membership_changed')
        for text in (entry.details, json.dumps(event.payload)):
            for secret in (SECRET_NAME, NIF, self.user.email):
                self.assertNotIn(secret, text)

    def test_server_owned_fields_in_the_body_are_ignored(self):
        other_id = str(uuid.uuid4())
        body = self.create_via_api(id=other_id, status='SUSPENDED', my_role=ADMIN, legacy_business_profile_id=other_id).json()
        self.assertEqual((body['status'], body['my_role']), ('ACTIVE', OWNER))
        self.assertNotEqual(body['id'], other_id)
        self.assertFalse(Organization.objects.get(pk=body['id']).legacy_business_profile_id)

    def test_multipart_with_logo_and_several_categories(self):
        first, second = Category.objects.create(name='A', slug='a'), Category.objects.create(name='B', slug='b')
        response = self.client.post(ORGS, {
            'name': 'Avec logo', 'org_type': 'BOUTIQUE', 'category_ids': [str(first.id), str(second.id)],
            'logo': make_test_image(),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body['logo'].startswith('http') and '/organization_logos/' in body['logo'])
        self.assertEqual(set(body['category_ids']), {str(first.id), str(second.id)})

    def test_anonymous_is_refused(self):
        self.assertEqual(APIClient().post(ORGS, {'name': 'x'}, format='json').status_code, 401)

    def test_phone_must_be_verified(self):
        self.client = self.login(make_user('nonverif', phone_verified=False))
        response = self.create_via_api()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'phone_verification_required')
        self.assertEqual(Organization.objects.count(), 0)

    def test_organization_limit_is_a_setting(self):
        IdentitySettings.objects.update_or_create(pk=IdentitySettings.get_solo().pk, defaults={'max_organizations_per_account': 2})
        self.assertEqual(self.create_via_api(name='Une').status_code, 201)
        self.assertEqual(self.create_via_api(name='Deux').status_code, 201)
        refused = self.create_via_api(name='Trois')
        self.assertEqual((refused.status_code, refused.json()['code']), (409, 'organization_limit_reached'))
        self.assertEqual(Organization.objects.count(), 2)

    def test_restricted_or_inactive_account_is_refused(self):
        Sanction.objects.create(user=self.user, sanction_type='BANNISSEMENT', reason='x')
        self.assertDenied(self.create_via_api(), DENY_SECURITY)
        self.assertEqual(Organization.objects.count(), 0)

    def test_invalid_input_is_a_400_and_writes_nothing(self):
        city = City.objects.create(name='Kinshasa')
        other_city = City.objects.create(name='Lubumbashi')
        commune = Commune.objects.create(city=other_city, name='Kampemba')
        cases = {
            'name': {'name': 'a'},
            'name_long': {'name': 'a' * 256},
            'name_invisible': {'name': 'Atelier​X'},
            'org_type': {'org_type': 'AUTRE'},
            'description': {'description': 'x' * 2001},
            'nif': {'nif': 'x' * 51},
            'category_ids': {'category_ids': [str(uuid.uuid4())]},
            'city_id': {'city_id': str(uuid.uuid4())},
            'commune_id': {'city_id': str(city.id), 'commune_id': str(commune.id)},
        }
        for label, body in cases.items():
            with self.subTest(label):
                response = self.create_via_api(**body)
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.create_via_api(name='x', org_type=None).status_code, 400)
        self.assertEqual(self.client.post(ORGS, [1, 2], format='json').status_code, 400)
        empty = self.client.post(ORGS, {}, format='json')
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(set(empty.json()), {'name', 'org_type'})
        self.assertEqual(Organization.objects.count(), 0)

    def test_truncated_logo_is_a_400_on_creation_and_creates_nothing(self):
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(self.user)
        for label, upload in truncated_images().items():
            with self.subTest(label):
                response = client.post(
                    ORGS, {'name': 'Logo cassé', 'org_type': 'ENTREPRISE', 'logo': upload}, format='multipart',
                )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn('logo', response.json())
        self.assertEqual(Organization.objects.count(), 0)

    def test_names_mixing_scripts_are_refused(self):
        for name in ('Rawb\u0430nk', '\u03a1aypal Shop', '\u0410lfa'):  # a cyrillique ; rho grec ; A cyrillique
            with self.subTest(name=name):
                self.assertEqual(self.create_via_api(name=name).status_code, 400)
        cyrillic = '\u0411\u0430\u043d\u043a \u0421\u0442\u043e\u043b\u0438\u0446\u0430'
        self.assertEqual(self.create_via_api(name=cyrillic).status_code, 201)
        self.assertEqual(self.create_via_api(name='Café Élégance 24').status_code, 201)
        self.assertEqual(Organization.objects.count(), 2)

    def test_name_is_not_unique_but_normalized(self):
        self.assertEqual(self.create_via_api(name='Homonyme').status_code, 201)
        self.assertEqual(self.create_via_api(name='Homonyme').status_code, 201)

    def test_x_context_header_is_ignored(self):
        response = self.client.post(
            ORGS, {'name': 'Sans contexte', 'org_type': 'ENTREPRISE'}, format='json',
            HTTP_X_CONTEXT=f'ORGANIZATION:{uuid.uuid4()}',
        )
        self.assertEqual(response.status_code, 201)

    def test_too_many_categories_uses_the_adjustable_limit(self):
        categories = [Category.objects.create(name=f'C{i}', slug=f'c{i}') for i in range(6)]
        response = self.create_via_api(category_ids=[str(c.id) for c in categories])
        self.assertEqual(response.status_code, 400)
        self.assertIn('category_ids', response.json())
        ok = self.create_via_api(category_ids=[str(c.id) for c in categories[:5]])
        self.assertEqual(ok.status_code, 201)


@override_settings(CACHES=LOCMEM_CACHE)
class CreateThrottleTests(ApiBase):
    def test_rate_is_configured_and_limits_creations_only(self):
        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['org_create'], '5/day')
        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['org_write'], '30/hour')
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'org_create': '2/day'}):
            for _ in range(5):
                self.assertEqual(self.client.get(ORGS).status_code, 200)
            codes = [self.create_via_api(name=f'Orga {i}').status_code for i in range(3)]
        self.assertEqual(codes, [201, 201, 429])


# --- Détail interne ------------------------------------------------------------------------------------------

class InternalTests(ApiBase):
    def setUp(self):
        super().setUp()
        self.org = make_org(SECRET_NAME, nif=NIF)
        self.members = {role: make_user(role.lower()) for role in (OWNER, ADMIN, EDITOR, ANALYST)}
        for role, member in self.members.items():
            join(self.org, member, role)
        self.url = f'{ORGS}{self.org.pk}/internal/'

    def test_every_role_reads_with_its_own_role_and_capabilities(self):
        for role, member in self.members.items():
            with self.subTest(role=role):
                response = self.login(member).get(self.url)
                self.assertEqual(response.status_code, 200, response.content)
                body = response.json()
                self.assertEqual(set(body), INTERNAL_KEYS)
                self.assertEqual((body['my_role'], body['id']), (role, str(self.org.pk)))
                self.assertEqual(body['capabilities'], capabilities.capabilities_for_role(role))
                self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_nif_is_only_shown_to_roles_that_can_edit_the_identity(self):
        for role, member in self.members.items():
            with self.subTest(role=role):
                body = self.login(member).get(self.url).json()
                self.assertIn('nif', body)
                self.assertEqual(body['nif'], NIF if role in (OWNER, ADMIN) else None)

    def test_a_non_member_and_an_unknown_organization_get_the_same_refusal(self):
        stranger = self.login(make_user('etranger'))
        unknown = stranger.get(f'{ORGS}{uuid.uuid4()}/internal/')
        refused = stranger.get(self.url)
        self.assertDenied(refused, DENY_RELATION)
        self.assertEqual((unknown.status_code, unknown.json()), (refused.status_code, refused.json()))
        self.assertNotIn(SECRET_NAME, refused.content.decode())

    def test_staff_without_membership_gets_nothing(self):
        staff = make_user('staff', is_staff=True, is_superuser=True)
        self.assertDenied(self.login(staff).get(self.url), DENY_RELATION)

    def test_revoked_member_is_refused_immediately_with_the_same_token(self):
        client = self.login(self.members[EDITOR])
        self.assertEqual(client.get(self.url).status_code, 200)
        Membership.objects.filter(user=self.members[EDITOR]).update(status=Membership.STATUS_REVOKED)
        self.assertDenied(client.get(self.url), DENY_RELATION)

    def test_anonymous_is_refused(self):
        self.assertEqual(APIClient().get(self.url).status_code, 401)

    def test_suspended_and_archived_organizations(self):
        owner = self.login(self.members[OWNER])
        Organization.objects.filter(pk=self.org.pk).update(status='SUSPENDED')
        self.assertDenied(owner.get(self.url), DENY_SECURITY)
        Organization.objects.filter(pk=self.org.pk).update(status='ARCHIVED')
        self.assertDenied(owner.get(self.url), DENY_OBJECT_STATE)
        # non-membre d'abord, état ensuite : l'état n'est pas révélé à un tiers
        self.assertDenied(self.login(make_user('tiers')).get(self.url), DENY_RELATION)

    def test_x_context_header_is_ignored(self):
        client = self.login(self.members[ANALYST])
        other = make_org('Autre')
        join(other, self.members[ANALYST], OWNER)
        response = client.get(self.url, HTTP_X_CONTEXT=f'ORGANIZATION:{other.pk}')
        self.assertEqual((response.status_code, response.json()['my_role']), (200, ANALYST))
        bad = client.get(self.url, HTTP_X_CONTEXT='nimportequoi')
        self.assertEqual(bad.status_code, 200)

    def test_no_member_personal_data_is_returned(self):
        member = make_user('secretmember', phone=MEMBER_PHONE, full_name=MEMBER_NAME)
        member.email = MEMBER_EMAIL
        member.save()
        join(self.org, member, EDITOR)
        text = self.login(self.members[OWNER]).get(self.url).content.decode()
        for secret in (MEMBER_EMAIL, MEMBER_PHONE, MEMBER_NAME, 'Secret-Membre', self.members[OWNER].email):
            self.assertNotIn(secret, text)
        self.assertNotIn('members', json.loads(text))

    def test_migrated_flag_comes_from_the_legacy_link(self):
        Organization.objects.filter(pk=self.org.pk).update(legacy_business_profile_id=uuid.uuid4())
        self.assertTrue(self.login(self.members[OWNER]).get(self.url).json()['migrated_from_business'])

    def test_verification_states_claims_and_summary_are_derived_from_the_pieces(self):
        owner = self.login(self.members[OWNER])
        base = owner.get(self.url).json()['verification']
        self.assertEqual([r['state'] for r in base['required']], ['NONE', 'NONE', 'NONE'])
        self.assertEqual((base['verified_claims'], base['summary']), ([], {'complete': False, 'label': None}))

        from django.utils import timezone

        add_document(self.org, 'RCCM', KycDocument.STATUS_VALIDE, reviewed_at=timezone.now())
        add_document(self.org, 'ID_NATIONALE', KycDocument.STATUS_EN_ATTENTE)
        add_document(self.org, 'PIECE_GERANT', KycDocument.STATUS_REFUSE)
        add_document(self.org, 'ARRETE_ONG', KycDocument.STATUS_VALIDE, reviewed_at=timezone.now())  # non exigée
        partial = owner.get(self.url).json()['verification']
        self.assertEqual({r['document_type']: r['state'] for r in partial['required']},
                         {'RCCM': 'VALIDE', 'ID_NATIONALE': 'EN_ATTENTE', 'PIECE_GERANT': 'REFUSE'})
        self.assertEqual([c['code'] for c in partial['verified_claims']], ['RCCM_VERIFIED'])
        self.assertEqual(partial['verified_claims'][0]['label'], 'RCCM vérifié')
        self.assertTrue(partial['verified_claims'][0]['verified_at'])
        self.assertFalse(partial['summary']['complete'])

        KycDocument.objects.filter(organization=self.org, document_type__in=['ID_NATIONALE', 'PIECE_GERANT']).update(
            status=KycDocument.STATUS_VALIDE,
        )
        full = owner.get(self.url).json()['verification']
        self.assertEqual(full['summary'], {'complete': True, 'label': 'Organisation vérifiée'})
        self.assertEqual(
            [c['code'] for c in full['verified_claims']], ['RCCM_VERIFIED', 'NATIONAL_ID_VERIFIED', 'REPRESENTATIVE_VERIFIED'],
        )

    def test_summary_is_never_complete_when_the_requirement_list_is_empty(self):
        OrganizationDocumentRequirement.objects.filter(org_type='ENTREPRISE').delete()
        add_document(self.org, 'RCCM')
        verification = self.login(self.members[OWNER]).get(self.url).json()['verification']
        self.assertEqual((verification['required'], verification['verified_claims']), ([], []))
        self.assertEqual(verification['summary'], {'complete': False, 'label': None})


# --- Modification --------------------------------------------------------------------------------------------

class PatchTests(ApiBase):
    def setUp(self):
        super().setUp()
        self.org = make_org('Atelier', description='Avant')
        self.members = {role: make_user(role.lower()) for role in (OWNER, ADMIN, EDITOR, ANALYST)}
        for role, member in self.members.items():
            join(self.org, member, role)
        self.url = f'{ORGS}{self.org.pk}/'

    def patch(self, role=OWNER, **body):
        return self.login(self.members[role]).patch(self.url, body, format='json')

    def test_owner_and_admin_edit_the_identity(self):
        for role in (OWNER, ADMIN):
            with self.subTest(role=role):
                response = self.patch(role, name=f'Nom {role}', description=f'Texte {role}', nif=NIF)
                self.assertEqual(response.status_code, 200, response.content)
                body = response.json()
                self.assertEqual(set(body), INTERNAL_KEYS)
                self.assertEqual((body['name'], body['description'], body['my_role']), (f'Nom {role}', f'Texte {role}', role))
        self.org.refresh_from_db()
        self.assertEqual((self.org.name, self.org.nif), (f'Nom {ADMIN}', NIF))

    def test_editor_and_analyst_have_no_right_on_the_identity(self):
        for role in (EDITOR, ANALYST):
            with self.subTest(role=role):
                self.assertDenied(self.patch(role, name='Piraté', description='Piraté'), DENY_PERMISSION)
        self.org.refresh_from_db()
        self.assertEqual((self.org.name, self.org.description), ('Atelier', 'Avant'))
        self.assertFalse(AuditLog.objects.filter(action='ORG_UPDATED').exists())

    def test_non_member_unknown_revoked_anonymous(self):
        self.assertDenied(self.login(make_user('tiers')).patch(self.url, {'name': 'X2'}, format='json'), DENY_RELATION)
        self.assertDenied(self.login(make_user('tiers2')).patch(f'{ORGS}{uuid.uuid4()}/', {'name': 'X2'}, format='json'), DENY_RELATION)
        self.assertEqual(APIClient().patch(self.url, {'name': 'X2'}, format='json').status_code, 401)
        client = self.login(self.members[ADMIN])
        Membership.objects.filter(user=self.members[ADMIN]).update(status=Membership.STATUS_REVOKED)
        self.assertDenied(client.patch(self.url, {'name': 'Après révocation'}, format='json'), DENY_RELATION)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, 'Atelier')

    def test_suspended_archived_and_restricted(self):
        Organization.objects.filter(pk=self.org.pk).update(status='SUSPENDED')
        self.assertDenied(self.patch(name='Suspendue'), DENY_SECURITY)
        Organization.objects.filter(pk=self.org.pk).update(status='ARCHIVED')
        self.assertDenied(self.patch(name='Archivée'), DENY_OBJECT_STATE)
        Organization.objects.filter(pk=self.org.pk).update(status='ACTIVE')
        Sanction.objects.create(user=self.members[OWNER], sanction_type='BANNISSEMENT', reason='x')
        self.assertDenied(self.patch(name='Banni'), DENY_SECURITY)

    def test_org_type_is_immutable(self):
        for value in ('ONG', 'ENTREPRISE'):
            response = self.patch(org_type=value)
            self.assertEqual(response.status_code, 400)
            self.assertIn('org_type', response.json())
        self.org.refresh_from_db()
        self.assertEqual(self.org.org_type, 'ENTREPRISE')

    def test_server_owned_fields_are_ignored(self):
        response = self.patch(description='Ok', status='ARCHIVED', id=str(uuid.uuid4()), my_role=OWNER, verified_claims=['X'])
        self.assertEqual(response.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual((self.org.status, response.json()['id']), ('ACTIVE', str(self.org.pk)))

    def test_name_is_locked_once_a_piece_is_validated(self):
        add_document(self.org, 'RCCM', KycDocument.STATUS_VALIDE)
        refused = self.patch(name='Marque célèbre')
        self.assertEqual((refused.status_code, refused.json()['code']), (409, 'name_locked_by_verification'))
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, 'Atelier')
        # le même nom (même après normalisation) n'est pas un renommage ; le reste reste modifiable
        self.assertEqual(self.patch(name='  Atelier ', description='Nouvelle').status_code, 200)
        self.assertFalse(AuditLog.objects.filter(action='ORG_UPDATED', details__contains='fields=name').exists())

    def test_name_stays_editable_with_refused_pieces_only(self):
        add_document(self.org, 'ID_NATIONALE', KycDocument.STATUS_REFUSE)
        self.assertEqual(self.patch(name='Atelier 2', nif=NIF).status_code, 200)

    def test_name_is_also_locked_while_a_piece_is_pending(self):
        add_document(self.org, 'RCCM', KycDocument.STATUS_EN_ATTENTE)
        refused = self.patch(name='Autre marque')
        self.assertEqual((refused.status_code, refused.json()['code']), (409, 'name_locked_by_verification'))
        self.assertEqual(self.patch(nif=NIF, description='Ok').status_code, 200)  # le NIF reste libre sans pièce validée

    def test_nif_is_locked_once_a_piece_is_validated(self):
        self.assertEqual(self.patch(nif='AVANT-1').status_code, 200)
        add_document(self.org, 'RCCM', KycDocument.STATUS_VALIDE)
        refused = self.patch(nif=NIF)
        self.assertEqual((refused.status_code, refused.json()['code']), (409, 'nif_locked_by_verification'))
        self.assertEqual(self.patch(nif=' AVANT-1 ', description='Autre').status_code, 200)  # inchangé
        self.org.refresh_from_db()
        self.assertEqual(self.org.nif, 'AVANT-1')

    def test_removing_the_city_removes_the_commune(self):
        kin = City.objects.create(name='Kinshasa')
        gombe = Commune.objects.create(city=kin, name='Gombe')
        self.assertEqual(self.patch(city_id=str(kin.id), commune_id=str(gombe.id)).status_code, 200)
        cleared = self.patch(city_id=None).json()
        self.assertEqual((cleared['city_id'], cleared['commune_id']), (None, None))
        self.org.refresh_from_db()
        self.assertIsNone(self.org.commune_id)

    def test_truncated_logo_is_a_400_on_patch_and_leaves_no_file(self):
        import os

        from django.conf import settings as django_settings

        folder = os.path.join(django_settings.MEDIA_ROOT, 'organization_logos')
        before = set(os.listdir(folder)) if os.path.isdir(folder) else set()
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(self.members[OWNER])
        for label, upload in truncated_images().items():
            with self.subTest(label):
                response = client.patch(self.url, {'logo': upload}, format='multipart')
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn('logo', response.json())
        self.org.refresh_from_db()
        self.assertFalse(self.org.logo)
        self.assertEqual(set(os.listdir(folder)) if os.path.isdir(folder) else set(), before)

    def test_name_lock_covers_the_admin_too(self):
        add_document(self.org, 'RCCM', KycDocument.STATUS_VALIDE)
        self.assertEqual(self.patch(ADMIN, name='Autre').json()['code'], 'name_locked_by_verification')

    def test_invalid_values(self):
        for body in ({'name': ''}, {'name': 'a'}, {'name': None}, {'name': 'x‮y'}, {'description': 'x' * 2001},
                     {'description': ['a']}, {'nif': 'x' * 51}, {'category_ids': 'abc'}, {'category_ids': [str(uuid.uuid4())]},
                     {'city_id': str(uuid.uuid4())}, {'commune_id': str(uuid.uuid4())}, {'logo': 'texte'}):
            with self.subTest(body=body):
                self.assertEqual(self.patch(**body).status_code, 400)
        self.org.refresh_from_db()
        self.assertEqual((self.org.name, self.org.description), ('Atelier', 'Avant'))
        self.assertEqual(self.login(self.members[OWNER]).patch(self.url, [1], format='json').status_code, 400)

    def test_categories_are_replaced_and_limited(self):
        cats = [Category.objects.create(name=f'C{i}', slug=f'c{i}') for i in range(7)]
        self.assertEqual(self.patch(category_ids=[str(c.id) for c in cats[:2]]).json()['category_ids'].__len__(), 2)
        replaced = self.patch(category_ids=[str(cats[2].id), str(cats[2].id)]).json()
        self.assertEqual(replaced['category_ids'], [str(cats[2].id)])
        self.assertEqual(self.patch(category_ids=[]).json()['category_ids'], [])
        self.assertEqual(OrganizationCategory.objects.filter(organization=self.org).count(), 0)
        self.assertEqual(self.patch(category_ids=[str(c.id) for c in cats[:6]]).status_code, 400)
        IdentitySettings.objects.filter(pk=IdentitySettings.get_solo().pk).update(max_categories_per_context=7)
        self.assertEqual(self.patch(category_ids=[str(c.id) for c in cats]).status_code, 200)

    def test_location_is_validated_together(self):
        kin, lub = City.objects.create(name='Kinshasa'), City.objects.create(name='Lubumbashi')
        gombe = Commune.objects.create(city=kin, name='Gombe')
        kampemba = Commune.objects.create(city=lub, name='Kampemba')
        ok = self.patch(city_id=str(kin.id), commune_id=str(gombe.id))
        self.assertEqual((ok.status_code, ok.json()['commune_id']), (200, str(gombe.id)))
        self.assertEqual(self.patch(commune_id=str(kampemba.id)).status_code, 400)  # commune d'une autre ville
        self.assertEqual(self.patch(city_id=str(lub.id)).status_code, 400)  # la commune actuelle n'en fait pas partie
        cleared = self.patch(city_id=None, commune_id=None).json()
        self.assertEqual((cleared['city_id'], cleared['commune_id']), (None, None))

    def test_logo_is_replaced_removed_and_the_old_file_deleted_after_commit(self):
        first = self.login(self.members[OWNER]).patch(self.url, {'logo': make_test_image('a.jpg')}, format='multipart')
        self.assertEqual(first.status_code, 200, first.content)
        self.org.refresh_from_db()
        old_name = self.org.logo.name
        storage = self.org.logo.storage
        self.assertTrue(storage.exists(old_name))
        with self.captureOnCommitCallbacks(execute=True):
            second = self.login(self.members[OWNER]).patch(
                self.url, {'logo': make_test_image('b.jpg', color=(0, 255, 0))}, format='multipart',
            )
        self.assertEqual(second.status_code, 200)
        self.org.refresh_from_db()
        self.assertNotEqual(self.org.logo.name, old_name)
        self.assertFalse(storage.exists(old_name))
        new_name = self.org.logo.name
        with self.captureOnCommitCallbacks(execute=True):
            removed = self.patch(logo=None)
        self.assertEqual((removed.status_code, removed.json()['logo']), (200, None))
        self.assertFalse(storage.exists(new_name))
        self.org.refresh_from_db()
        self.assertFalse(self.org.logo)

    def test_audit_and_event_carry_field_names_only(self):
        self.patch(name=SECRET_NAME, nif=NIF, description='Une description secrète')
        entry = AuditLog.objects.get(action='ORG_UPDATED')
        self.assertEqual((entry.actor, entry.context_type, str(entry.context_id)), (self.members[OWNER], CONTEXT_ORGANIZATION, str(self.org.pk)))
        self.assertEqual(entry.details, f'organization={self.org.pk}; fields=name,description,nif')
        event = OutboxEvent.objects.get(event_type='identity.organization_updated')
        self.assertEqual(event.payload, {
            'organization_id': str(self.org.pk), 'fields': ['name', 'description', 'nif'],
            'actor_id': str(self.members[OWNER].pk),
        })
        for text in (entry.details, json.dumps(event.payload)):
            for secret in (SECRET_NAME, NIF, 'secrète'):
                self.assertNotIn(secret, text)

    def test_nothing_is_written_when_nothing_changes(self):
        self.assertEqual(self.patch(name='Atelier', description='Avant').status_code, 200)
        self.assertEqual(self.patch().status_code, 200)
        self.assertFalse(AuditLog.objects.filter(action='ORG_UPDATED').exists())
        self.assertFalse(OutboxEvent.objects.filter(event_type='identity.organization_updated').exists())

    def test_other_methods_are_not_allowed(self):
        client = self.login(self.members[OWNER])
        self.assertEqual(client.put(self.url, {'name': 'x'}, format='json').status_code, 405)
        self.assertEqual(client.delete(self.url).status_code, 405)

    def test_x_context_header_is_ignored(self):
        other = make_org('Autre')
        join(other, self.members[EDITOR], OWNER)  # propriétaire ailleurs, éditeur ici
        client = self.login(self.members[EDITOR])
        response = client.patch(self.url, {'name': 'Détournée'}, format='json', HTTP_X_CONTEXT=f'ORGANIZATION:{other.pk}')
        self.assertDenied(response, DENY_PERMISSION)


@override_settings(CACHES=LOCMEM_CACHE)
class WriteThrottleTests(ApiBase):
    def test_org_write_applies_to_patch_archive_and_leave_only(self):
        org = make_org('Throttle')
        join(org, self.user, OWNER)
        url = f'{ORGS}{org.pk}/'
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'org_write': '2/hour'}):
            for _ in range(4):
                self.assertEqual(self.client.get(url + 'internal/').status_code, 200)
            codes = [self.client.patch(url, {'description': str(i)}, format='json').status_code for i in range(3)]
        self.assertEqual(codes, [200, 200, 429])


# --- Archivage et sortie -------------------------------------------------------------------------------------

class ArchiveAndLeaveTests(ApiBase):
    def setUp(self):
        super().setUp()
        self.org = make_org('Atelier')
        self.members = {role: make_user(role.lower()) for role in (OWNER, ADMIN, EDITOR, ANALYST)}
        for role, member in self.members.items():
            join(self.org, member, role)
        self.base = f'{ORGS}{self.org.pk}/'

    def as_(self, role):
        return self.login(self.members[role])

    def test_owner_archives_and_the_event_is_published(self):
        response = self.as_(OWNER).post(self.base + 'archive/')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body['status'], body['my_role'], set(body)), ('ARCHIVED', OWNER, INTERNAL_KEYS))
        event = OutboxEvent.objects.get(event_type='identity.seller_context_status_changed')
        self.assertEqual((event.payload['reason'], event.payload['context_id']), ('archived', str(self.org.pk)))
        entry = AuditLog.objects.get(action='ORG_ARCHIVED')
        self.assertEqual((str(entry.context_id), entry.actor), (str(self.org.pk), self.members[OWNER]))

    def test_only_the_owner_archives(self):
        for role in (ADMIN, EDITOR, ANALYST):
            with self.subTest(role=role):
                self.assertDenied(self.as_(role).post(self.base + 'archive/'), DENY_PERMISSION)
        self.assertDenied(self.login(make_user('tiers')).post(self.base + 'archive/'), DENY_RELATION)
        self.assertEqual(APIClient().post(self.base + 'archive/').status_code, 401)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'ACTIVE')

    def test_archiving_twice_is_refused_and_it_is_irreversible_by_the_api(self):
        self.as_(OWNER).post(self.base + 'archive/')
        self.assertDenied(self.as_(OWNER).post(self.base + 'archive/'), DENY_OBJECT_STATE)
        self.assertDenied(self.as_(OWNER).patch(self.base, {'description': 'x'}, format='json'), DENY_OBJECT_STATE)

    def test_a_member_leaves_with_204_and_loses_the_context_at_once(self):
        client = self.as_(EDITOR)
        response = client.post(self.base + 'leave/')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')
        membership = Membership.objects.get(user=self.members[EDITOR])
        self.assertEqual((membership.status, membership.end_reason), ('REVOKED', 'left'))
        self.assertDenied(client.get(self.base + 'internal/'), DENY_RELATION)
        listed = client.get('/api/accounts/contexts/').json()['results']
        self.assertEqual([c['type'] for c in listed], ['USER'])
        event = OutboxEvent.objects.get(event_type='identity.membership_changed')
        self.assertEqual((event.payload['change'], event.payload['user_id']), ('revoked', str(self.members[EDITOR].pk)))

    def test_the_last_owner_cannot_leave_but_one_of_two_owners_can(self):
        for role in (ADMIN, EDITOR, ANALYST):
            Membership.objects.filter(user=self.members[role]).update(status='REVOKED')
        refused = self.as_(OWNER).post(self.base + 'leave/')
        self.assertEqual((refused.status_code, refused.json()['code']), (409, 'last_owner'))
        join(self.org, make_user('second'), OWNER)
        self.assertEqual(self.as_(OWNER).post(self.base + 'leave/').status_code, 204)

    def test_leaving_is_allowed_on_a_suspended_or_archived_organization(self):
        Organization.objects.filter(pk=self.org.pk).update(status='SUSPENDED')
        self.assertEqual(self.as_(EDITOR).post(self.base + 'leave/').status_code, 204)
        Organization.objects.filter(pk=self.org.pk).update(status='ARCHIVED')
        self.assertEqual(self.as_(ANALYST).post(self.base + 'leave/').status_code, 204)

    def test_leave_is_allowed_to_a_restricted_account(self):
        Sanction.objects.create(user=self.members[ANALYST], sanction_type='BANNISSEMENT', reason='x')
        self.assertEqual(self.as_(ANALYST).post(self.base + 'leave/').status_code, 204)

    def test_non_member_unknown_and_anonymous(self):
        self.assertDenied(self.login(make_user('tiers')).post(self.base + 'leave/'), DENY_RELATION)
        self.assertDenied(self.as_(OWNER).post(f'{ORGS}{uuid.uuid4()}/leave/'), DENY_RELATION)
        self.assertEqual(APIClient().post(self.base + 'leave/').status_code, 401)
        self.assertEqual(self.as_(OWNER).get(self.base + 'leave/').status_code, 405)


# --- Liste publique ------------------------------------------------------------------------------------------

class PublicListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def names(self, **params):
        response = self.client.get(ORGS, params)
        self.assertEqual(response.status_code, 200, response.content)
        return [o['name'] for o in response.json()['results']]

    def test_anonymous_gets_the_exact_public_keys_and_never_personal_data(self):
        member = make_user('secretmember', phone=MEMBER_PHONE, full_name=MEMBER_NAME)
        member.email = MEMBER_EMAIL
        member.save()
        city = City.objects.create(name='Kinshasa')
        org = make_led_org('Boutique A', description='Pagnes', nif=NIF, city_id=city.id, created_by=member)
        join(org, member, OWNER)
        add_document(org, 'RCCM')
        response = self.client.get(ORGS)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data['count'], data['next'], data['previous']), (1, None, None))
        item = data['results'][0]
        self.assertEqual(set(item), PUBLIC_KEYS)
        self.assertEqual(item['city_id'], str(city.id))
        self.assertEqual([c['code'] for c in item['verified_claims']], ['RCCM_VERIFIED'])
        self.assertEqual(set(item['verified_claims'][0]), {'code', 'label', 'verified_at'})
        self.assertEqual(set(item['verification_summary']), {'complete', 'label'})
        text = response.content.decode()
        for secret in (NIF, MEMBER_EMAIL, MEMBER_PHONE, MEMBER_NAME, 'Secret-Membre', 'kyc', 'status', 'members', 'is_verified'):
            self.assertNotIn(secret, text.replace('verification_summary', ''))
        self.assertNotIn('nif', item)

    def test_only_active_organizations_are_listed(self):
        make_led_org('Active')
        make_led_org('Suspendue', status='SUSPENDED')
        make_led_org('Archivée', status='ARCHIVED')
        self.assertEqual(self.names(), ['Active'])

    def test_order_is_by_name_ignoring_case_then_id_and_paginated(self):
        for name in ('banane', 'Zèbre', 'Abricot', 'cerise'):
            make_led_org(name)
        self.assertEqual(self.names(), ['Abricot', 'banane', 'cerise', 'Zèbre'])
        page = self.client.get(ORGS, {'page_size': 2}).json()
        self.assertEqual((page['count'], len(page['results']), bool(page['next'])), (4, 2, True))
        self.assertEqual(self.client.get(ORGS, {'page': 3, 'page_size': 2}).status_code, 404)

    def test_search_covers_name_and_description_only(self):
        make_led_org('Alpha', description='vente de pagnes')
        make_led_org('Beta', description='autre')
        member = make_user('pers', full_name='Personne Privée')
        join(Organization.objects.get(name='Beta'), member, OWNER)
        self.assertEqual(self.names(search='alpha'), ['Alpha'])
        self.assertEqual(self.names(search='PAGNES'), ['Alpha'])
        self.assertEqual(self.names(search='Privée'), [])
        self.assertEqual(self.names(search=member.email), [])

    def test_search_is_bounded(self):
        self.assertEqual(self.client.get(ORGS, {'search': 'a' * 100}).status_code, 200)
        response = self.client.get(ORGS, {'search': 'a' * 101})
        self.assertEqual(response.status_code, 400)
        self.assertIn('search', response.json())

    def test_org_type_filter(self):
        make_led_org('E1')
        make_led_org('O1', org_type='ONG')
        self.assertEqual(self.names(org_type='ONG'), ['O1'])
        self.assertEqual(self.client.get(ORGS, {'org_type': 'AUTRE'}).status_code, 400)

    def test_claim_and_fully_verified_filters(self):
        full, partial, none = make_led_org('Complete'), make_led_org('Partielle'), make_led_org('Aucune')
        for document_type in ('RCCM', 'ID_NATIONALE', 'PIECE_GERANT'):
            add_document(full, document_type)
        add_document(partial, 'RCCM')
        add_document(partial, 'ID_NATIONALE', KycDocument.STATUS_EN_ATTENTE)
        add_document(none, 'ARRETE_ONG')  # validée mais non exigée pour ENTREPRISE : ne compte pas
        self.assertEqual(self.names(claim='RCCM_VERIFIED'), ['Complete', 'Partielle'])
        self.assertEqual(self.names(claim='NATIONAL_ID_VERIFIED'), ['Complete'])
        self.assertEqual(self.names(claim='NGO_DECREE_VERIFIED'), [])
        self.assertEqual(self.names(fully_verified='true'), ['Complete'])
        self.assertEqual(self.names(fully_verified='FALSE'), ['Aucune', 'Partielle'])
        self.assertEqual(self.names(claim='RCCM_VERIFIED', fully_verified='false'), ['Partielle'])
        for params in ({'claim': 'INCONNU'}, {'fully_verified': 'oui'}, {'fully_verified': ''}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(ORGS, params).status_code, 400)

    def test_an_organization_without_requirements_is_never_fully_verified(self):
        OrganizationDocumentRequirement.objects.filter(org_type='BOUTIQUE').delete()
        make_led_org('Sans exigence', org_type='BOUTIQUE')
        self.assertEqual(self.names(fully_verified='true'), [])
        self.assertEqual(self.names(fully_verified='false'), ['Sans exigence'])

    def test_query_count_does_not_depend_on_the_number_of_organizations(self):
        for i in range(12):
            org = make_led_org(f'Org {i:02d}')
            add_document(org, 'RCCM')
        with self.assertNumQueries(6):
            self.assertEqual(self.client.get(ORGS, {'page_size': 12}).status_code, 200)

    def test_old_businesses_endpoint_is_gone(self):
        self.assertEqual(self.client.get('/api/accounts/businesses/').status_code, 404)


# --- Limites -------------------------------------------------------------------------------------------------

class LimitsTests(ApiBase):
    def test_limits_come_from_the_settings(self):
        response = self.client.get(LIMITS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'max_categories_per_context': 5, 'max_organizations_per_account': 10, 'name_min_length': 2,
            'name_max_length': 255, 'description_max_length': 2000,
        })
        IdentitySettings.objects.filter(pk=IdentitySettings.get_solo().pk).update(
            max_categories_per_context=8, max_organizations_per_account=3,
        )
        body = self.client.get(LIMITS).json()
        self.assertEqual((body['max_categories_per_context'], body['max_organizations_per_account']), (8, 3))

    def test_authentication_is_required_and_nothing_is_personal(self):
        self.assertEqual(APIClient().get(LIMITS).status_code, 401)
        self.assertEqual(self.client.post(LIMITS).status_code, 405)


# --- Inscription et profil sans type de compte --------------------------------------------------------------

class RegistrationAndMeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def register(self, **extra):
        body = {'email': 'nouveau@example.com', 'password': 'un-mot-de-passe-solide', 'full_name': 'Nouveau', **extra}
        return self.client.post('/api/accounts/register/', body, format='json')

    def test_register_never_exposes_nor_reads_the_account_type_or_business_profile(self):
        response = self.register(user_type='ENTREPRISE', business_profile={'business_name': 'Atelier', 'is_verified': True})
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertNotIn('user_type', body)
        self.assertNotIn('business_profile', body)
        self.assertEqual(Organization.objects.count(), 0)
        self.assertFalse(hasattr(User.objects.get(email='nouveau@example.com'), 'user_type'))

    def test_me_has_no_user_type_nor_business_profile_and_ignores_them_on_patch(self):
        user = make_user('moi')
        client = ApiBase.login(user)
        body = client.get('/api/accounts/me/').json()
        self.assertNotIn('user_type', body)
        self.assertNotIn('business_profile', body)
        response = client.patch('/api/accounts/me/', {
            'user_type': 'ENTREPRISE', 'business_profile': {'business_name': 'Pirate'}, 'full_name': 'Moi Renommé',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['full_name'], 'Moi Renommé')
        self.assertFalse(Organization.objects.exists())
        user.refresh_from_db()
        self.assertFalse(hasattr(user, 'user_type'))

    def test_me_contract_exposes_phone_verified_read_only(self):
        expected = {
            'id', 'email', 'photo', 'full_name', 'ville', 'ville_name', 'commune', 'commune_name', 'phone',
            'phone_verified', 'date_joined',
        }
        user = make_user('moi', phone_verified=False)
        client = ApiBase.login(user)
        body = client.get('/api/accounts/me/').json()
        self.assertEqual(set(body), expected)
        self.assertIs(body['phone_verified'], False)
        patched = client.patch('/api/accounts/me/', {'phone_verified': True}, format='json')
        self.assertEqual(patched.status_code, 200)
        self.assertIs(patched.json()['phone_verified'], False)
        user.refresh_from_db()
        self.assertFalse(user.phone_verified)
        user.phone_verified = True
        user.save()
        self.assertIs(client.get('/api/accounts/me/').json()['phone_verified'], True)

    def test_registration_by_phone_gives_a_verified_phone_that_allows_creating_an_organization(self):
        from .models import OtpCode

        phone = '+243812345600'
        _, code = OtpCode.issue(phone, OtpCode.PURPOSE_REGISTER)
        registered = self.client.post('/api/accounts/register/', {
            'phone': phone, 'otp_code': code, 'password': 'un-mot-de-passe-solide', 'full_name': 'Par Téléphone',
        }, format='json')
        self.assertEqual(registered.status_code, 201, registered.content)
        self.assertIs(registered.json()['phone_verified'], True)
        client = ApiBase.login(User.objects.get(phone=phone))
        self.assertEqual(client.post(ORGS, {'name': 'Ma boîte', 'org_type': 'ENTREPRISE'}, format='json').status_code, 201)


# --- Garde-fou de routes, données personnelles, règles -------------------------------------------------------

class GuardAndRulesTests(TestCase):
    def test_every_organization_write_route_is_declared_and_justified(self):
        from django.urls import get_resolver

        from .tests_route_guard import _walk, _view_class, _write_methods

        seen = {}
        for route, callback in _walk(get_resolver()):
            if route.startswith('api/accounts/organizations/') and '/kyc/' not in route and not route.endswith('/verification/'):
                view_class = _view_class(callback)
                seen[route] = (_write_methods(callback, view_class), getattr(view_class, 'acting_context_exempt', ''))
        self.assertEqual(
            {route for route, (methods, _) in seen.items() if methods},
            {
                'api/accounts/organizations/', 'api/accounts/organizations/<uuid:pk>/',
                'api/accounts/organizations/<uuid:pk>/archive/', 'api/accounts/organizations/<uuid:pk>/leave/',
            },
        )
        for route, (methods, reason) in seen.items():
            self.assertTrue(reason, route)
            self.assertIn('X-Context', reason, route)
        self.assertFalse([r for r in collect_unguarded_write_routes() if 'organizations' in r])

    def test_no_new_service_takes_a_plan_or_a_price(self):
        import inspect

        for function in (services.update_organization, services.create_organization, services.get_organization_for_member):
            names = set(inspect.signature(function).parameters)
            self.assertFalse(names & {'plan', 'price', 'entitlement', 'subscription'}, function.__name__)

    def test_a_plan_never_grants_a_role_or_a_claim(self):
        owner = make_user('payeur')
        org = make_org('Payante')
        join(org, owner, EDITOR)
        body = ApiBase.login(owner).get(f'{ORGS}{org.pk}/internal/').json()
        self.assertEqual(body['my_role'], EDITOR)
        self.assertNotIn('org.edit_profile', body['capabilities'])
        self.assertEqual(body['verification']['verified_claims'], [])

    def test_internal_organization_detail_only_leaks_the_nif_to_members(self):
        org = make_org('Avec NIF', nif=NIF)
        join(org, make_user('membre'), ANALYST)
        outsider = ApiBase.login(make_user('dehors'))
        for url in (f'{ORGS}{org.pk}/internal/', ORGS):
            self.assertNotIn(NIF, outsider.get(url).content.decode())


class FiltersMatchSharedDerivationTests(TestCase):
    """Les filtres SQL `claim` et `fully_verified` restent cohérents avec la dérivation unique de T4."""

    def test_filters_agree_with_get_verification_summaries(self):
        from . import verification

        orgs = []
        for i, types in enumerate([(), ('RCCM',), ('RCCM', 'ID_NATIONALE'), ('RCCM', 'ID_NATIONALE', 'PIECE_GERANT')]):
            org = make_led_org(f'Cohérence {i}')
            for document_type in types:
                add_document(org, document_type)
            orgs.append(org)
        summaries = verification.get_verification_summaries([o.pk for o in orgs])
        client = APIClient()
        for value in ('true', 'false'):
            names = {o['name'] for o in client.get(ORGS, {'fully_verified': value}).json()['results']}
            expected = {o.name for o in orgs if summaries[o.pk]['summary']['complete'] == (value == 'true')}
            self.assertEqual(names, expected)
        for code in {c['code'] for s in summaries.values() for c in s['verified_claims']}:
            names = {o['name'] for o in client.get(ORGS, {'claim': code}).json()['results']}
            expected = {o.name for o in orgs if code in {c['code'] for c in summaries[o.pk]['verified_claims']}}
            self.assertEqual(names, expected, code)


@override_settings(CACHES=LOCMEM_CACHE)
class ListThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_public_list_is_throttled_per_ip_and_defaults_apply(self):
        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['org_list'], '600/hour')
        client = APIClient()
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'org_list': '2/hour'}):
            codes = [client.get(ORGS, REMOTE_ADDR='10.7.7.7').status_code for _ in range(3)]
            other = client.get(ORGS, REMOTE_ADDR='10.7.7.8').status_code
        self.assertEqual((codes, other), ([200, 200, 429], 200))
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'anon': '1/hour'}):
            cache.clear()
            codes = [client.get(ORGS, REMOTE_ADDR='10.7.7.9').status_code for _ in range(2)]
        self.assertEqual(codes, [200, 429])
