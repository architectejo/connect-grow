"""Contexte actif (L0-09b / T2) : en-tête `X-Context`, révocation immédiate, non-fuite, en-têtes hostiles,
performance, `GET contexts/`, CORS et throttle. ADR 0006, sections 6, 9.1 et 12."""
import uuid
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.common.contexts import (
    CONTEXT_ORGANIZATION, CONTEXT_PROVIDER, CONTEXT_USER, DENY_CONTEXT, DENY_OBJECT_STATE, DENY_PERMISSION,
    DENY_RELATION, DENY_SECURITY, ContextDenied,
)

from apps.moderation.models import Sanction

from . import capabilities, services
from .models import Membership, Organization, ProviderProfile, User

OWNER, ADMIN, EDITOR, ANALYST = capabilities.ROLE_OWNER, capabilities.ROLE_ADMIN, capabilities.ROLE_EDITOR, capabilities.ROLE_ANALYST
CONTEXTS_URL = '/api/accounts/contexts/'
SECRET_ORG_NAME = 'Sentinelle-Secrete-Orga'


def make_user(label, **extra):
    extra.setdefault('phone_verified', True)
    return User.objects.create_user(email=f'{label}@example.com', password='x', full_name=f'Nom {label}', **extra)


def make_org(name='Atelier', org_type='ENTREPRISE', status=Organization.STATUS_ACTIVE, **extra):
    return Organization.objects.create(name=name, org_type=org_type, status=status, **extra)


def join(org, user, role=OWNER, status=Membership.STATUS_ACTIVE):
    return Membership.objects.create(organization=org, user=user, role=role, status=status)


def header(context_type, context_id):
    return f'{context_type}:{context_id}'


class WhoAmIView(services.ActingContextMixin, APIView):
    """Vue de test : branche la brique DRF sans toucher aux vues métier."""

    permission_classes = [services.capability_permission('offer.publish')]
    throttle_classes = []

    def get(self, request):
        ctx = self.acting_context
        again = self.acting_context  # mémorisation : pas de seconde résolution
        assert again is ctx
        return Response({'type': ctx.type, 'id': str(ctx.id), 'role': ctx.role})


class ResolutionTests(TestCase):
    def setUp(self):
        self.user = make_user('u')
        self.other = make_user('o')

    def test_absent_header_is_personal_context_with_account_guard_only(self):
        with self.assertNumQueries(2):  # garde du compte : is_active + sanctions
            ctx = services.resolve_acting_context(self.user, None)
        self.assertEqual((ctx.type, ctx.id, ctx.role), (CONTEXT_USER, self.user.pk, None))

    def test_user_header_forms(self):
        for raw in ('USER', header('USER', self.user.pk)):
            with self.subTest(raw=raw), self.assertNumQueries(2):
                self.assertEqual(services.resolve_acting_context(self.user, raw).type, CONTEXT_USER)
        with self.assertRaises(ContextDenied) as caught:
            services.resolve_acting_context(self.user, header('USER', self.other.pk))
        self.assertEqual(caught.exception.get_codes(), DENY_CONTEXT)

    def test_organization_member_gets_role(self):
        org = make_org()
        join(org, self.user, ADMIN)
        with self.assertNumQueries(3):  # garde du compte (2) + appartenance (1)
            ctx = services.resolve_acting_context(self.user, header('ORGANIZATION', org.pk))
        self.assertEqual((ctx.type, ctx.id, ctx.role), (CONTEXT_ORGANIZATION, org.pk, ADMIN))

    def test_provider_active_is_resolved_with_one_context_query(self):
        profile = ProviderProfile.objects.create(user=self.user, display_name='Moi prestataire')
        with self.assertNumQueries(3):
            ctx = services.resolve_acting_context(self.user, header('PROVIDER', profile.pk))
        self.assertEqual((ctx.type, ctx.id, ctx.role), (CONTEXT_PROVIDER, profile.pk, None))

    def test_provider_without_active_profile_is_refused(self):
        profile = ProviderProfile.objects.create(user=self.other, display_name='Autre')
        for raw in (header('PROVIDER', uuid.uuid4()), header('PROVIDER', profile.pk)):
            with self.subTest(raw=raw), self.assertRaises(ContextDenied) as caught:
                services.resolve_acting_context(self.user, raw)
            self.assertEqual(caught.exception.get_codes(), DENY_CONTEXT)

    def test_archived_provider_is_object_state(self):
        profile = ProviderProfile.objects.create(
            user=self.user, display_name='Archive', status=ProviderProfile.STATUS_ARCHIVED,
        )
        with self.assertRaises(ContextDenied) as caught:
            services.resolve_acting_context(self.user, header('PROVIDER', profile.pk))
        self.assertEqual(caught.exception.get_codes(), DENY_OBJECT_STATE)

    def test_suspended_and_archived_organizations(self):
        for org_status, code in ((Organization.STATUS_SUSPENDED, DENY_SECURITY), (Organization.STATUS_ARCHIVED, DENY_OBJECT_STATE)):
            org = make_org(status=org_status)
            join(org, self.user)
            with self.subTest(status=org_status), self.assertRaises(ContextDenied) as caught:
                services.resolve_acting_context(self.user, header('ORGANIZATION', org.pk))
            self.assertEqual(caught.exception.get_codes(), code)

    def test_staff_and_superuser_bypass_nothing(self):
        boss = make_user('boss', is_staff=True, is_superuser=True)
        org = make_org()
        join(org, self.user)
        with self.assertRaises(ContextDenied) as caught:
            services.resolve_acting_context(boss, header('ORGANIZATION', org.pk))
        self.assertEqual(caught.exception.get_codes(), DENY_RELATION)

    def test_authorize_uses_capability_matrix(self):
        org = make_org()
        join(org, self.user, ANALYST)
        ctx = services.resolve_acting_context(self.user, header('ORGANIZATION', org.pk))
        services.authorize(ctx, 'stats.view')
        with self.assertRaises(ContextDenied) as caught:
            services.authorize(ctx, 'offer.publish')
        self.assertEqual(caught.exception.get_codes(), DENY_PERMISSION)
        with self.assertRaises(capabilities.UnknownCapability):
            services.authorize(ctx, 'inconnue.capacite')

    def test_authorize_on_ignores_header_and_uses_real_role(self):
        org = make_org()
        join(org, self.user, EDITOR)
        self.assertTrue(services.can(self.user.pk, CONTEXT_ORGANIZATION, org.pk, 'offer.edit'))
        self.assertFalse(services.can(self.user.pk, CONTEXT_ORGANIZATION, org.pk, 'org.archive'))
        self.assertFalse(services.can(self.other.pk, CONTEXT_ORGANIZATION, org.pk, 'offer.edit'))
        self.assertFalse(services.can(self.user.pk, CONTEXT_ORGANIZATION, uuid.uuid4(), 'offer.edit'))
        self.assertFalse(services.can(self.user.pk, CONTEXT_ORGANIZATION, 'pas-un-uuid', 'offer.edit'))
        self.assertTrue(services.can(self.user.pk, CONTEXT_USER, self.user.pk, 'offer.publish'))
        self.assertFalse(services.can(self.user.pk, CONTEXT_USER, self.other.pk, 'offer.publish'))
        self.assertFalse(services.can(None, CONTEXT_USER, self.user.pk, 'offer.publish'))


class ActsForContextTests(TestCase):
    def setUp(self):
        self.user = make_user('a')
        self.other = make_user('b')

    def test_organization_members_of_any_role_act_for_it(self):
        org = make_org()
        for role in capabilities.ROLES:
            member = make_user(f'm-{role}')
            join(org, member, role)
            with self.subTest(role=role):
                self.assertTrue(services.acts_for_context(member.pk, CONTEXT_ORGANIZATION, org.pk))
        self.assertFalse(services.acts_for_context(self.other.pk, CONTEXT_ORGANIZATION, org.pk))

    def test_revoked_member_and_suspended_organization_do_not_act(self):
        org = make_org()
        membership = join(org, self.user, EDITOR)
        self.assertTrue(services.acts_for_context(self.user.pk, CONTEXT_ORGANIZATION, org.pk))
        Organization.objects.filter(pk=org.pk).update(status=Organization.STATUS_SUSPENDED)
        self.assertFalse(services.acts_for_context(self.user.pk, CONTEXT_ORGANIZATION, org.pk))
        Organization.objects.filter(pk=org.pk).update(status=Organization.STATUS_ARCHIVED)
        self.assertTrue(services.acts_for_context(self.user.pk, CONTEXT_ORGANIZATION, org.pk))
        Membership.objects.filter(pk=membership.pk).update(status=Membership.STATUS_REVOKED)
        self.assertFalse(services.acts_for_context(self.user.pk, CONTEXT_ORGANIZATION, org.pk))

    def test_provider_owner_acts_even_when_archived(self):
        profile = ProviderProfile.objects.create(user=self.user, display_name='P')
        self.assertTrue(services.acts_for_context(self.user.pk, CONTEXT_PROVIDER, profile.pk))
        self.assertFalse(services.acts_for_context(self.other.pk, CONTEXT_PROVIDER, profile.pk))
        ProviderProfile.objects.filter(pk=profile.pk).update(status=ProviderProfile.STATUS_ARCHIVED)
        self.assertTrue(services.acts_for_context(self.user.pk, CONTEXT_PROVIDER, profile.pk))

    def test_invalid_values_never_match(self):
        self.assertFalse(services.acts_for_context(self.user.pk, CONTEXT_ORGANIZATION, 'x'))
        self.assertFalse(services.acts_for_context(self.user.pk, 'AUTRE', self.user.pk))


class ViewIntegrationTests(TestCase):
    """Brique DRF derrière une vraie requête : codes, corps et non-fuite."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = make_user('member')
        self.org = make_org(name=SECRET_ORG_NAME)
        self.membership = join(self.org, self.user, EDITOR)

    def call(self, user=None, **extra):
        request = self.factory.get('/test/', **extra)
        force_authenticate(request, user=user if user is not None else self.user)
        return WhoAmIView.as_view()(request)

    def test_absent_header_is_personal(self):
        response = self.call()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['type'], CONTEXT_USER)

    def test_member_reaches_organization_context(self):
        response = self.call(HTTP_X_CONTEXT=header('ORGANIZATION', self.org.pk))
        self.assertEqual((response.status_code, response.data['role']), (200, EDITOR))

    def test_unauthenticated_is_refused_before_resolution(self):
        request = self.factory.get('/test/', HTTP_X_CONTEXT='n importe quoi')
        response = WhoAmIView.as_view()(request)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(response.data.get('code'), DENY_CODES_SET)

    def test_capability_refusal_is_deny_permission(self):
        self.membership.role = ANALYST
        self.membership.save()
        response = self.call(HTTP_X_CONTEXT=header('ORGANIZATION', self.org.pk))
        self.assertEqual((response.status_code, response.data['code']), (403, DENY_PERMISSION))

    def test_refusals_for_unknown_and_non_member_are_identical(self):
        stranger = make_user('stranger')
        unknown = self.call(user=stranger, HTTP_X_CONTEXT=header('ORGANIZATION', uuid.uuid4()))
        foreign = self.call(user=stranger, HTTP_X_CONTEXT=header('ORGANIZATION', self.org.pk))
        self.assertEqual(unknown.status_code, 403)
        self.assertEqual(unknown.status_code, foreign.status_code)
        self.assertEqual(dict(unknown.data), dict(foreign.data))
        self.assertEqual(foreign.data['code'], DENY_RELATION)
        self.assertNotIn(SECRET_ORG_NAME, str(foreign.data))
        self.assertNotIn(str(self.org.pk), str(foreign.data))

    def test_revoked_member_has_same_refusal_as_stranger(self):
        Membership.objects.filter(pk=self.membership.pk).update(status=Membership.STATUS_REVOKED)
        response = self.call(HTTP_X_CONTEXT=header('ORGANIZATION', self.org.pk))
        self.assertEqual((response.status_code, response.data['code']), (403, DENY_RELATION))

    def test_hostile_headers_are_refused_without_fallback(self):
        org_id = str(self.org.pk)
        hostile = [
            '',                                           # présent mais vide
            ' ',
            'ORGANIZATION',                               # sans identifiant
            'ORGANIZATION:',
            'ORGANIZATION:pas-un-uuid',
            'ORGANIZATION:' + org_id.upper(),             # casse de l'UUID
            'organization:' + org_id,                     # casse du type
            'Organization:' + org_id,
            'ADMIN:' + org_id,                            # type inconnu
            'STAFF:' + org_id,
            ' ORGANIZATION:' + org_id,                    # espace de tête
            'ORGANIZATION:' + org_id + ' ',               # espace de queue
            'ORGANIZATION:{' + org_id + '}',              # accolades
            'ORGANIZATION:' + org_id.replace('-', ''),    # sans tirets
            'ORGANIZATION:urn:uuid:' + org_id,
            'ORGANIZATION:' + org_id + ',ORGANIZATION:' + org_id,  # doublon fusionné par un proxy
            'ORGANIZATION:' + org_id + ':' + org_id,
            'USER:' + org_id + ',USER:' + org_id,
            'ORGANIZATION:' + org_id + "'; DROP TABLE x;--",
            'ORGANIZATION:' + org_id + '\\x00',
            'ORGANIZATION:%s%%00' % org_id,
            'ORGANIZATION:../' + org_id,
            'USER:',
            'user',
            'USER:pas-un-uuid',
            'PROVIDER:',
            'PROVIDER:' + 'a' * 5000,
            '*',
            'null',
        ]
        for raw in hostile:
            with self.subTest(raw=raw[:60]):
                response = self.call(HTTP_X_CONTEXT=raw)
                self.assertEqual(response.status_code, 403, raw[:60])
                self.assertEqual(response.data['code'], DENY_CONTEXT, raw[:60])
                self.assertNotIn(SECRET_ORG_NAME, str(response.data))

    def test_user_header_for_another_account_is_refused(self):
        response = self.call(HTTP_X_CONTEXT=header('USER', uuid.uuid4()))
        self.assertEqual((response.status_code, response.data['code']), (403, DENY_CONTEXT))


DENY_CODES_SET = {DENY_CONTEXT, DENY_RELATION, DENY_PERMISSION, DENY_SECURITY, DENY_OBJECT_STATE}


class ImmediateRevocationTests(TestCase):
    """Aucun cache de rôle : chaque requête relit la base (R11)."""

    def setUp(self):
        self.client = APIClient()
        self.user = make_user('rev')
        self.org = make_org()
        self.membership = join(self.org, self.user, ADMIN)
        self.client.force_authenticate(self.user)
        self.factory = APIRequestFactory()

    def call(self):
        request = self.factory.get('/test/', HTTP_X_CONTEXT=header('ORGANIZATION', self.org.pk))
        force_authenticate(request, user=self.user)
        return WhoAmIView.as_view()(request)

    def test_member_removed_between_two_requests(self):
        self.assertEqual(self.call().status_code, 200)
        Membership.objects.filter(pk=self.membership.pk).update(status=Membership.STATUS_REVOKED)
        response = self.call()
        self.assertEqual((response.status_code, response.data['code']), (403, DENY_RELATION))

    def test_role_downgraded_between_two_requests(self):
        self.assertEqual(self.call().data['role'], ADMIN)
        Membership.objects.filter(pk=self.membership.pk).update(role=ANALYST)
        response = self.call()
        self.assertEqual((response.status_code, response.data['code']), (403, DENY_PERMISSION))

    def test_organization_suspended_then_reactivated(self):
        self.assertEqual(self.call().status_code, 200)
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        response = self.call()
        self.assertEqual((response.status_code, response.data['code']), (403, DENY_SECURITY))
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ACTIVE)
        self.assertEqual(self.call().status_code, 200)

    def test_organization_archived(self):
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_ARCHIVED)
        response = self.call()
        self.assertEqual((response.status_code, response.data['code']), (403, DENY_OBJECT_STATE))

    def test_deactivated_account_is_refused_by_authentication_not_resolution(self):
        """Compte désactivé : le jeton valide ne passe plus (401), le contexte n'est jamais résolu."""
        from rest_framework_simplejwt.tokens import AccessToken

        client = APIClient()
        token = str(AccessToken.for_user(self.user))
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}', HTTP_X_CONTEXT=header('ORGANIZATION', self.org.pk))
        self.assertEqual(client.get(CONTEXTS_URL).status_code, 200)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        response = client.get(CONTEXTS_URL)
        self.assertEqual(response.status_code, 401)

    def test_contexts_list_reflects_revocation_immediately(self):
        names = [c['type'] for c in self.client.get(CONTEXTS_URL).json()['results']]
        self.assertIn(CONTEXT_ORGANIZATION, names)
        Membership.objects.filter(pk=self.membership.pk).update(status=Membership.STATUS_REVOKED)
        names = [c['type'] for c in self.client.get(CONTEXTS_URL).json()['results']]
        self.assertNotIn(CONTEXT_ORGANIZATION, names)


class QueryBudgetTests(TestCase):
    def test_resolution_cost_does_not_grow_with_memberships(self):
        user = make_user('perf')
        orgs = []
        for i in range(8):
            org = make_org(name=f'Org {i}')
            join(org, user, OWNER)
            orgs.append(org)
        for org in (orgs[0], orgs[-1]):
            with self.assertNumQueries(3):
                services.resolve_acting_context(user, header('ORGANIZATION', org.pk))

    def test_request_memoizes_resolution(self):
        user = make_user('memo')
        org = make_org()
        join(org, user, OWNER)
        request = APIRequestFactory().get('/t/', HTTP_X_CONTEXT=header('ORGANIZATION', org.pk))
        force_authenticate(request, user=user)
        # Une seule résolution (permission) puis lecture mémorisée dans la vue : 3 requêtes au total.
        with self.assertNumQueries(3):
            response = WhoAmIView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_contexts_list_has_constant_query_count(self):
        user = make_user('list')
        ProviderProfile.objects.create(user=user, display_name='P')
        client = APIClient()
        client.force_authenticate(user)
        for i in range(2):
            join(make_org(name=f'A{i}'), user)
        for i in range(2):
            join(make_org(name=f'S{i}', status=Organization.STATUS_SUSPENDED), user)
        with self.assertNumQueries(3):  # prestataire, organisations actives, organisations indisponibles
            client.get(CONTEXTS_URL)
        for i in range(6):
            join(make_org(name=f'B{i}'), user)
            join(make_org(name=f'T{i}', status=Organization.STATUS_ARCHIVED), user)
        with self.assertNumQueries(3):
            client.get(CONTEXTS_URL)


class ContextsEndpointTests(TestCase):
    EXPECTED_KEYS = {'type', 'id', 'name', 'role', 'org_type', 'photo', 'capabilities', 'migrated_from_business',
                     'status'}

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = make_user('ctxlist')
        self.client.force_authenticate(self.user)

    def get(self, **extra):
        return self.client.get(CONTEXTS_URL, **extra)

    def test_requires_authentication(self):
        self.assertEqual(APIClient().get(CONTEXTS_URL).status_code, 401)

    def test_only_get_is_allowed(self):
        self.assertEqual(self.client.post(CONTEXTS_URL, {}, format='json').status_code, 405)

    def test_personal_only(self):
        body = self.get().json()
        self.assertEqual((body['count'], body['next'], body['previous']), (1, None, None))
        item = body['results'][0]
        self.assertEqual(set(item), self.EXPECTED_KEYS)
        self.assertEqual(item['type'], CONTEXT_USER)
        self.assertEqual(item['id'], str(self.user.pk))
        self.assertEqual(item['name'], self.user.full_name)
        self.assertIsNone(item['role'])
        self.assertIsNone(item['org_type'])
        self.assertIs(item['migrated_from_business'], False)
        self.assertEqual(item['capabilities'], sorted(capabilities.PERSONAL_CAPABILITIES))
        self.assertFalse([c for c in item['capabilities'] if c.startswith('org.')])

    def test_order_filters_and_exhaustive_keys(self):
        profile = ProviderProfile.objects.create(user=self.user, display_name='Moi couture')
        zeta = make_org(name='Zeta', org_type='ONG')
        alpha = make_org(name='alpha', org_type='BOUTIQUE', legacy_business_profile_id=uuid.uuid4())
        beta = make_org(name='Beta')
        join(zeta, self.user, ANALYST)
        join(alpha, self.user, OWNER)
        join(beta, self.user, EDITOR)
        # Exclus : membership révoqué, organisation suspendue, organisation archivée, organisation étrangère.
        join(make_org(name='Revoquee'), self.user, status=Membership.STATUS_REVOKED)
        join(make_org(name='Suspendue', status=Organization.STATUS_SUSPENDED), self.user)
        join(make_org(name='Archivee', status=Organization.STATUS_ARCHIVED), self.user)
        make_org(name='Etrangere')
        results = self.get().json()['results']
        self.assertEqual([r['type'] for r in results], ['USER', 'PROVIDER', 'ORGANIZATION', 'ORGANIZATION', 'ORGANIZATION'])
        self.assertEqual([r['name'] for r in results[2:]], ['alpha', 'Beta', 'Zeta'])
        for item in results:
            self.assertEqual(set(item), self.EXPECTED_KEYS)
        provider = results[1]
        self.assertEqual(provider['id'], str(profile.pk))
        self.assertEqual(provider['capabilities'], sorted(capabilities.PERSONAL_CAPABILITIES))
        by_name = {r['name']: r for r in results[2:]}
        self.assertEqual(by_name['alpha']['role'], OWNER)
        self.assertEqual(by_name['alpha']['org_type'], 'BOUTIQUE')
        self.assertIs(by_name['alpha']['migrated_from_business'], True)
        self.assertIs(by_name['Beta']['migrated_from_business'], False)
        self.assertEqual(by_name['Zeta']['capabilities'], capabilities.capabilities_for_role(ANALYST))
        self.assertEqual(self.get().json()['count'], 5)

    def test_archived_provider_is_not_listed(self):
        ProviderProfile.objects.create(user=self.user, display_name='P', status=ProviderProfile.STATUS_ARCHIVED)
        self.assertEqual([r['type'] for r in self.get().json()['results']], ['USER'])

    def test_header_is_ignored_by_the_list(self):
        join(make_org(), self.user)
        response = self.get(HTTP_X_CONTEXT='nimporte quoi')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 2)

    def test_response_is_never_cached(self):
        self.assertEqual(self.get()['Cache-Control'], 'private, no-store')

    def test_no_private_data_of_other_members(self):
        org = make_org(name='Equipe', nif='NIF-SECRET-123')
        join(org, self.user, OWNER)
        join(org, make_user('colleague'), ADMIN)
        text = self.get().content.decode()
        self.assertNotIn('NIF-SECRET-123', text)
        self.assertNotIn('colleague', text)
        self.assertNotIn(self.user.email, text)

    def test_throttle_rate_is_configured(self):
        self.assertIn('contexts', settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'])


LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'contexts-throttle'}}


@override_settings(CACHES=LOCMEM_CACHE)
class ContextsThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_throttled_per_user(self):
        client = APIClient()
        client.force_authenticate(make_user('t1'))
        other = APIClient()
        other.force_authenticate(make_user('t2'))
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'contexts': '3/hour'}):
            statuses = [client.get(CONTEXTS_URL).status_code for _ in range(4)]
            other_status = other.get(CONTEXTS_URL).status_code
        self.assertEqual(statuses, [200, 200, 200, 429])
        self.assertEqual(other_status, 200)


class CorsSettingsTests(SimpleTestCase):
    def test_x_context_is_allowed_and_defaults_kept(self):
        from corsheaders.defaults import default_headers

        self.assertIn('x-context', settings.CORS_ALLOW_HEADERS)
        for name in default_headers:
            self.assertIn(name, settings.CORS_ALLOW_HEADERS)
        self.assertIn('authorization', settings.CORS_ALLOW_HEADERS)

    def test_preflight_accepts_x_context(self):
        from django.test import Client

        origin = settings.CORS_ALLOWED_ORIGINS[0]
        response = Client().options(
            CONTEXTS_URL, HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,x-context',
        )
        self.assertIn('x-context', response.headers.get('Access-Control-Allow-Headers', ''))


def sanction(user, kind):
    return Sanction.objects.create(user=user, sanction_type=kind, reason='test')


class RestrictedAccountTests(TestCase):
    """Compte sanctionné ou désactivé : refusé pour tout contexte (DENY_SECURITY), sauf `org.leave`."""

    KINDS = (Sanction.TYPE_SUSPENSION_TEMPORAIRE, Sanction.TYPE_BANNISSEMENT)

    def setUp(self):
        self.user = make_user('sanctionne')
        self.org = make_org()
        join(self.org, self.user, OWNER)
        self.profile = ProviderProfile.objects.create(user=self.user, display_name='P')

    def targets(self):
        return (
            (CONTEXT_USER, self.user.pk, None),
            (CONTEXT_PROVIDER, self.profile.pk, header('PROVIDER', self.profile.pk)),
            (CONTEXT_ORGANIZATION, self.org.pk, header('ORGANIZATION', self.org.pk)),
        )

    def test_resolution_is_refused_for_every_context(self):
        for kind in self.KINDS:
            sanction_row = sanction(self.user, kind)
            for context_type, context_id, raw in self.targets():
                with self.subTest(kind=kind, context=context_type), self.assertRaises(ContextDenied) as caught:
                    services.resolve_acting_context(self.user, raw)
                self.assertEqual(caught.exception.get_codes(), DENY_SECURITY)
            sanction_row.delete()

    def test_authorize_on_and_can_are_refused(self):
        sanction(self.user, Sanction.TYPE_BANNISSEMENT)
        for context_type, context_id, _ in self.targets():
            with self.subTest(context=context_type):
                with self.assertRaises(ContextDenied) as caught:
                    services.authorize_on(self.user, context_type, context_id, 'offer.edit')
                self.assertEqual(caught.exception.get_codes(), DENY_SECURITY)
                self.assertFalse(services.can(self.user.pk, context_type, context_id, 'offer.edit'))

    def test_leave_is_still_allowed(self):
        sanction(self.user, Sanction.TYPE_SUSPENSION_TEMPORAIRE)
        services.authorize_on(self.user, CONTEXT_ORGANIZATION, self.org.pk, 'org.leave')
        self.assertTrue(services.can(self.user.pk, CONTEXT_ORGANIZATION, self.org.pk, 'org.leave'))

    def test_warning_and_expired_or_lifted_sanctions_do_not_restrict(self):
        sanction(self.user, Sanction.TYPE_AVERTISSEMENT)
        Sanction.objects.create(
            user=self.user, sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='x',
            ends_at=timezone.now() - timedelta(days=1),
        )
        Sanction.objects.create(
            user=self.user, sanction_type=Sanction.TYPE_BANNISSEMENT, reason='x', is_active=False,
        )
        self.assertEqual(services.resolve_acting_context(self.user, header('ORGANIZATION', self.org.pk)).role, OWNER)

    def test_inactive_account_is_read_from_the_database(self):
        stale = User.objects.get(pk=self.user.pk)  # objet resté « actif » en mémoire
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertTrue(stale.is_active)
        with self.assertRaises(ContextDenied) as caught:
            services.resolve_acting_context(stale, None)
        self.assertEqual(caught.exception.get_codes(), DENY_SECURITY)
        self.assertFalse(services.can(self.user.pk, CONTEXT_USER, self.user.pk, 'offer.edit'))
        self.assertTrue(services.can(self.user.pk, CONTEXT_ORGANIZATION, self.org.pk, 'org.leave'))

    def test_view_and_permission_refuse_a_sanctioned_account(self):
        sanction(self.user, Sanction.TYPE_SUSPENSION_TEMPORAIRE)
        factory = APIRequestFactory()
        for raw in (None, header('ORGANIZATION', self.org.pk), header('PROVIDER', self.profile.pk)):
            extra = {'HTTP_X_CONTEXT': raw} if raw else {}
            request = factory.get('/test/', **extra)
            force_authenticate(request, user=self.user)
            response = WhoAmIView.as_view()(request)
            with self.subTest(raw=raw):
                self.assertEqual((response.status_code, response.data['code']), (403, DENY_SECURITY))


class ObjectView(services.ActingContextMixin, APIView):
    """Vue de test : création par en-tête, objet existant par propriétaire réel."""

    throttle_classes = []

    def get(self, request, target=None):
        self.authorize_capability('offer.edit')  # l'en-tête autorise (ou non) la création...
        self.authorize_object(CONTEXT_ORGANIZATION, target, 'offer.edit')  # ...l'objet décide pour lui-même
        return Response({'ok': True})


class ObjectAuthorizationTests(TestCase):
    """IDOR : sur un objet existant, l'en-tête ne décide jamais (ADR 0006, 6.4)."""

    def call(self, user, raw, target):
        request = APIRequestFactory().get('/t/', HTTP_X_CONTEXT=raw)
        force_authenticate(request, user=user)
        return ObjectView.as_view()(request, target=target)

    def test_header_of_org_a_cannot_act_on_object_of_org_b(self):
        user = make_user('double')
        org_a, org_b = make_org(name='A'), make_org(name='B')
        join(org_a, user, EDITOR)
        join(org_b, user, ANALYST)
        raw = header('ORGANIZATION', org_a.pk)
        refused = self.call(user, raw, org_b.pk)
        self.assertEqual((refused.status_code, refused.data['code']), (403, DENY_PERMISSION))
        self.assertEqual(self.call(user, raw, org_a.pk).status_code, 200)
        unknown = self.call(user, raw, uuid.uuid4())
        self.assertEqual((unknown.status_code, unknown.data['code']), (403, DENY_RELATION))

    def test_authorize_object_ignores_the_header_value(self):
        user = make_user('ignore')
        org = make_org()
        join(org, user, OWNER)
        request = APIRequestFactory().get('/t/', HTTP_X_CONTEXT='n importe quoi')
        force_authenticate(request, user=user)

        class ObjectOnlyView(services.ActingContextMixin, APIView):
            throttle_classes = []

            def get(self, request):
                self.authorize_object(CONTEXT_ORGANIZATION, org.pk, 'offer.edit')
                return Response({'ok': True})

        self.assertEqual(ObjectOnlyView.as_view()(request).status_code, 200)


class CacheHeadersTests(TestCase):
    def test_vary_and_no_store_for_context_dependent_responses(self):
        client = APIClient()
        client.force_authenticate(make_user('cache'))
        plain = client.get(CONTEXTS_URL)
        self.assertIn('X-Context', plain['Vary'])
        self.assertIn('Authorization', plain['Vary'])
        with_header = client.get('/api/accounts/me/', HTTP_X_CONTEXT='USER')
        self.assertIn('no-store', with_header['Cache-Control'])
        self.assertIn('X-Context', with_header['Vary'])
        without_header = client.get('/api/accounts/me/')
        self.assertNotIn('no-store', without_header.get('Cache-Control', ''))
