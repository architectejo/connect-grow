"""Prestataire individuel (L0-09c / T3) : activation, mise à jour, archivage, catégories, permissions,
audit, événement, non-fuite et contexte actif. ADR 0006, sections 5, 7, 8, 9.3 et 17 (Q-F5)."""
import json
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.test import APIClient

from apps.catalog.models import Category
from apps.common.contexts import (
    CONTEXT_PROVIDER, DENY_CONTEXT, DENY_OBJECT_STATE, DENY_SECURITY, ContextDenied,
)
from apps.moderation.models import AuditLog, Sanction
from apps.platform_core.models import OutboxEvent

from . import capabilities, services
from .models import IdentitySettings, ProviderProfile, ProviderProfileCategory, User

LOCMEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'provider-throttle'}}
URL = '/api/accounts/provider/'
ACTIVATE = URL + 'activate/'
ARCHIVE = URL + 'archive/'
CONTEXTS = '/api/accounts/contexts/'
EXPECTED_KEYS = {'id', 'display_name', 'bio', 'category_ids', 'status', 'created_at'}
SECRET_PHONE = '+243999000111'
SECRET_EMAIL = 'secret.prestataire@example.com'
SECRET_FULL_NAME = 'Marie Kabongo Mutombo'


def make_user(label, **extra):
    extra.setdefault('phone_verified', True)
    extra.setdefault('full_name', f'Nom {label}')
    return User.objects.create_user(email=f'{label}@example.com', password='x', **extra)


def make_category(name):
    return Category.objects.create(name=name)


class ProviderBase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('prest')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def activate(self, **body):
        return self.client.post(ACTIVATE, body, format='json')


class ActivationTests(ProviderBase):
    def test_creates_profile_without_new_user(self):
        users = User.objects.count()
        response = self.activate(display_name='  Marie   Coiffure ', bio='Coiffeuse à domicile')
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(set(body), EXPECTED_KEYS)
        self.assertEqual((body['display_name'], body['status']), ('Marie Coiffure', 'ACTIVE'))
        self.assertEqual(User.objects.count(), users)
        profile = ProviderProfile.objects.get(user=self.user)
        self.assertNotEqual(profile.pk, self.user.pk)
        self.assertEqual(body['id'], str(profile.pk))
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_default_name_is_public_form_not_full_name(self):
        user = make_user('mk', full_name=SECRET_FULL_NAME)
        client = APIClient()
        client.force_authenticate(user)
        body = client.post(ACTIVATE, {}, format='json').json()
        self.assertEqual(body['display_name'], 'Marie M.')
        self.assertNotIn('Kabongo', json.dumps(body))

    def test_too_short_default_name_falls_back(self):
        for label, full_name in (('court', 'X'), ('vide', '')):
            with self.subTest(full_name=full_name):
                user = make_user(label, full_name=full_name)
                client = APIClient()
                client.force_authenticate(user)
                self.assertEqual(client.post(ACTIVATE, {}, format='json').json()['display_name'], 'Utilisateur')

    def test_account_state_rechecked_after_lock(self):
        calls = []
        from . import providers

        original = providers._ensure_account_allowed
        with mock.patch.object(providers, '_ensure_account_allowed', side_effect=lambda u: (calls.append(1), original(u))[1]):
            self.activate(display_name='Nom valide')
            before = len(calls)
            self.client.patch(URL, {'bio': 'x'}, format='json')
        self.assertGreaterEqual(before, 2)
        self.assertGreaterEqual(len(calls) - before, 2)

    def test_name_is_nfkc_normalized(self):
        body = self.activate(display_name='ＡＢＣ Service').json()
        self.assertEqual(body['display_name'], 'ABC Service')

    def test_activation_is_idempotent(self):
        first = self.activate(display_name='Premier').json()
        again = self.activate(display_name='Autre nom')
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()['id'], first['id'])
        self.assertEqual(again.json()['display_name'], 'Premier')
        self.assertEqual(ProviderProfile.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='PROVIDER_ACTIVATED').count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count(), 1)

    def test_free_plan_is_enough_and_phone_not_required(self):
        user = make_user('nophone', phone_verified=False)
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.post(ACTIVATE, {'display_name': 'Sans tel'}, format='json').status_code, 201)

    def test_requires_authentication(self):
        anonymous = APIClient()
        for method, url in (('get', URL), ('post', ACTIVATE), ('patch', URL), ('post', ARCHIVE)):
            with self.subTest(url=url, method=method):
                self.assertEqual(getattr(anonymous, method)(url, {}, format='json').status_code, 401)

    def test_inactive_account_refused(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.user.refresh_from_db()
        response = self.activate(display_name='Nom valide')
        self.assertEqual((response.status_code, response.json()['code']), (403, DENY_SECURITY))
        self.assertEqual(ProviderProfile.objects.count(), 0)

    def test_sanctioned_account_refused_and_nothing_written(self):
        Sanction.objects.create(user=self.user, sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        response = self.activate(display_name='Nom valide')
        self.assertEqual((response.status_code, response.json()['code']), (403, DENY_SECURITY))
        self.assertEqual(ProviderProfile.objects.count(), 0)
        self.assertEqual(AuditLog.objects.filter(action='PROVIDER_ACTIVATED').count(), 0)
        self.assertEqual(OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').count(), 0)

    def test_invalid_names(self):
        for value in ('A', ' ', 'x' * 256, 'Nom‮Inversé', 'Nom\x00nul', 'Zéro​Largeur', 12, None, ['a']):
            with self.subTest(value=value):
                response = self.activate(display_name=value)
                self.assertEqual(response.status_code, 400)
                self.assertIn('display_name', response.json())
        self.assertEqual(ProviderProfile.objects.count(), 0)

    def test_name_boundaries_accepted(self):
        self.assertEqual(self.activate(display_name='Ab').status_code, 201)

    def test_bio_validation(self):
        self.assertEqual(self.activate(display_name='Nom valide', bio='x' * 2001).status_code, 400)
        self.assertEqual(self.activate(display_name='Nom valide', bio=['a']).status_code, 400)
        self.assertEqual(ProviderProfile.objects.count(), 0)
        self.assertEqual(self.activate(display_name='Nom valide', bio='x' * 2000).status_code, 201)

    def test_audit_and_event(self):
        profile_id = self.activate(display_name='Nom valide').json()['id']
        entry = AuditLog.objects.get(action='PROVIDER_ACTIVATED')
        self.assertEqual((entry.actor, entry.target_type, str(entry.target_id)), (self.user, 'providerprofile', profile_id))
        self.assertEqual((entry.context_type, str(entry.context_id)), (CONTEXT_PROVIDER, profile_id))
        event = OutboxEvent.objects.get(event_type='identity.seller_context_status_changed')
        self.assertEqual(event.payload, {
            'context_type': CONTEXT_PROVIDER, 'context_id': profile_id, 'reason': 'activated',
            'actor_id': str(self.user.pk),
        })

    def test_reactivates_archived_profile_with_new_values(self):
        first = self.activate(display_name='Ancien').json()
        self.client.post(ARCHIVE)
        response = self.activate(display_name='Nouveau')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body['id'], body['display_name'], body['status']), (first['id'], 'Nouveau', 'ACTIVE'))
        self.assertIsNone(ProviderProfile.objects.get(user=self.user).archived_at)
        self.assertEqual(AuditLog.objects.filter(action='PROVIDER_ACTIVATED').count(), 2)

    def test_restricted_account_cannot_reactivate(self):
        self.activate(display_name='Nom valide')
        self.client.post(ARCHIVE)
        Sanction.objects.create(user=self.user, sanction_type='BANNISSEMENT', reason='x')
        response = self.activate()
        self.assertEqual((response.status_code, response.json()['code']), (403, DENY_SECURITY))
        self.assertEqual(ProviderProfile.objects.get(user=self.user).status, ProviderProfile.STATUS_ARCHIVED)

    def test_unknown_and_read_only_keys_are_ignored(self):
        other = make_user('autre')
        body = self.activate(display_name='Nom valide', status='ARCHIVED', user=str(other.pk), id='x').json()
        self.assertEqual(body['status'], 'ACTIVE')
        self.assertEqual(ProviderProfile.objects.get().user, self.user)

    def test_non_object_body_rejected(self):
        response = self.client.post(ACTIVATE, ['a'], format='json')
        self.assertEqual(response.status_code, 400)


class ReadTests(ProviderBase):
    def test_404_without_profile(self):
        response = self.client.get(URL)
        self.assertEqual((response.status_code, response.json()['code']), (404, 'provider_not_found'))

    def test_get_returns_own_profile_even_archived(self):
        self.activate(display_name='Mon profil')
        self.client.post(ARCHIVE)
        body = self.client.get(URL).json()
        self.assertEqual((body['display_name'], body['status']), ('Mon profil', 'ARCHIVED'))

    def test_other_account_does_not_see_it(self):
        self.activate(display_name='Privé')
        other = make_user('autre')
        client = APIClient()
        client.force_authenticate(other)
        self.assertEqual(client.get(URL).status_code, 404)
        self.assertEqual(client.patch(URL, {'display_name': 'Pirate'}, format='json').status_code, 404)
        self.assertEqual(client.post(ARCHIVE).status_code, 404)
        self.assertEqual(ProviderProfile.objects.get().display_name, 'Privé')

    def test_response_leaks_no_personal_data(self):
        user = make_user('fuite', full_name=SECRET_FULL_NAME, phone=SECRET_PHONE, email=SECRET_EMAIL) \
            if False else User.objects.create_user(
                email=SECRET_EMAIL, password='x', full_name=SECRET_FULL_NAME, phone=SECRET_PHONE, phone_verified=True,
            )
        client = APIClient()
        client.force_authenticate(user)
        raw = client.post(ACTIVATE, {'bio': 'Présentation'}, format='json').content.decode()
        raw += client.get(URL).content.decode()
        for secret in (SECRET_PHONE, SECRET_EMAIL, 'Kabongo', 'secret.prestataire'):
            self.assertNotIn(secret, raw)
        audit = ' '.join(AuditLog.objects.values_list('details', flat=True))
        events = json.dumps(list(OutboxEvent.objects.values_list('payload', flat=True)))
        for secret in (SECRET_PHONE, SECRET_EMAIL, 'Kabongo', 'Présentation'):
            self.assertNotIn(secret, audit + events)


class UpdateTests(ProviderBase):
    def setUp(self):
        super().setUp()
        self.activate(display_name='Initial', bio='Bio')

    def patch(self, **body):
        return self.client.patch(URL, body, format='json')

    def test_partial_update(self):
        response = self.patch(display_name='  Nouveau  nom ')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body['display_name'], body['bio']), ('Nouveau nom', 'Bio'))
        response = self.patch(bio='')
        self.assertEqual(response.json()['bio'], '')
        self.assertEqual(self.patch().status_code, 200)

    def test_update_audited_without_values(self):
        self.patch(display_name='Valeur-Sensible-Zz', bio='Bio-Sensible-Zz')
        entry = AuditLog.objects.get(action='PROVIDER_UPDATED')
        self.assertEqual(entry.context_type, CONTEXT_PROVIDER)
        self.assertIn('fields=display_name,bio', entry.details)
        self.assertNotIn('Sensible', entry.details)
        self.assertEqual(self.patch().status_code, 200)
        self.assertEqual(AuditLog.objects.filter(action='PROVIDER_UPDATED').count(), 1)

    def test_invalid_values(self):
        for body in ({'display_name': 'A'}, {'display_name': ''}, {'display_name': None}, {'bio': 'x' * 2001},
                     {'display_name': 'a‮b'}):
            with self.subTest(body=body):
                self.assertEqual(self.patch(**body).status_code, 400)
        self.assertEqual(ProviderProfile.objects.get().display_name, 'Initial')

    def test_status_cannot_be_patched(self):
        self.assertEqual(self.patch(status='ARCHIVED').json()['status'], 'ACTIVE')

    def test_archived_profile_refused(self):
        self.client.post(ARCHIVE)
        response = self.patch(display_name='Nouveau')
        self.assertEqual((response.status_code, response.json()['code']), (403, DENY_OBJECT_STATE))
        self.assertEqual(ProviderProfile.objects.get().display_name, 'Initial')

    def test_restricted_account_refused(self):
        Sanction.objects.create(user=self.user, sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        response = self.patch(display_name='Nouveau')
        self.assertEqual((response.status_code, response.json()['code']), (403, DENY_SECURITY))

    def test_no_profile_is_404(self):
        client = APIClient()
        client.force_authenticate(make_user('vide'))
        self.assertEqual(client.patch(URL, {'display_name': 'Xx'}, format='json').status_code, 404)


class CategoryTests(ProviderBase):
    def setUp(self):
        super().setUp()
        self.cats = [make_category(f'Catégorie {i}') for i in range(7)]

    def ids(self, n):
        return [str(c.pk) for c in self.cats[:n]]

    def test_optional_and_empty_allowed(self):
        self.assertEqual(self.activate(display_name='Sans cat').json()['category_ids'], [])
        self.assertEqual(self.client.patch(URL, {'category_ids': []}, format='json').status_code, 200)

    def test_set_replace_and_dedupe(self):
        body = self.activate(display_name='Avec cat', category_ids=self.ids(2) + self.ids(1)).json()
        self.assertEqual(sorted(body['category_ids']), sorted(self.ids(2)))
        body = self.client.patch(URL, {'category_ids': self.ids(3)[1:]}, format='json').json()
        self.assertEqual(sorted(body['category_ids']), sorted(self.ids(3)[1:]))
        self.assertEqual(ProviderProfileCategory.objects.count(), 2)
        self.assertEqual(self.client.get(URL).json()['category_ids'], body['category_ids'])

    def test_maximum_is_five_by_default_and_adjustable(self):
        self.assertEqual(IdentitySettings.get_solo().max_categories_per_context, 5)
        self.assertEqual(self.activate(display_name='Cinq', category_ids=self.ids(5)).status_code, 201)
        response = self.client.patch(URL, {'category_ids': self.ids(6)}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['category_ids'][0].code, 'too_many_categories')
        self.assertEqual(ProviderProfileCategory.objects.count(), 5)
        settings_row = IdentitySettings.get_solo()
        settings_row.max_categories_per_context = 6
        settings_row.save()
        self.assertEqual(self.client.patch(URL, {'category_ids': self.ids(6)}, format='json').status_code, 200)

    def test_too_many_on_activation_creates_nothing(self):
        response = self.activate(display_name='Trop', category_ids=self.ids(6))
        self.assertEqual((response.status_code, response.data['category_ids'][0].code), (400, 'too_many_categories'))
        self.assertEqual(ProviderProfile.objects.count(), 0)

    def test_unknown_and_malformed(self):
        import uuid

        for value in ([str(uuid.uuid4())], ['pas-un-uuid'], 'texte', [1], self.ids(1) + [str(uuid.uuid4())]):
            with self.subTest(value=value):
                response = self.activate(display_name='Inconnue', category_ids=value)
                self.assertEqual((response.status_code, response.data['category_ids'][0].code), (400, 'unknown_category'))
        self.assertEqual(ProviderProfile.objects.count(), 0)


class ArchiveTests(ProviderBase):
    def setUp(self):
        super().setUp()
        self.profile_id = self.activate(display_name='A archiver', bio='Conservée').json()['id']

    def test_archive_keeps_data_and_is_audited(self):
        response = self.client.post(ARCHIVE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ARCHIVED')
        profile = ProviderProfile.objects.get()
        self.assertIsNotNone(profile.archived_at)
        self.assertEqual(profile.bio, 'Conservée')
        entry = AuditLog.objects.get(action='PROVIDER_ARCHIVED')
        self.assertEqual((entry.context_type, str(entry.context_id)), (CONTEXT_PROVIDER, self.profile_id))
        event = OutboxEvent.objects.filter(event_type='identity.seller_context_status_changed').latest('created_at')
        self.assertEqual((event.payload['reason'], event.payload['context_id']), ('archived', self.profile_id))

    def test_archive_is_idempotent(self):
        self.client.post(ARCHIVE)
        self.assertEqual(self.client.post(ARCHIVE).status_code, 200)
        self.assertEqual(AuditLog.objects.filter(action='PROVIDER_ARCHIVED').count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(payload__reason='archived').count(), 1)

    def test_restricted_account_can_still_archive(self):
        Sanction.objects.create(user=self.user, sanction_type='BANNISSEMENT', reason='x')
        self.assertEqual(self.client.post(ARCHIVE).status_code, 200)

    def test_archive_without_profile_is_404(self):
        client = APIClient()
        client.force_authenticate(make_user('vide'))
        self.assertEqual(client.post(ARCHIVE).status_code, 404)

    def test_status_event_has_the_marketplace_subscriber(self):
        # T5a : l'abonné `marketplace.sync_seller_visibility` remplace le drapeau `no_subscriber`.
        from apps.platform_core.catalog import EVENT_TYPES
        from apps.platform_core.registry import subscribers_for

        self.assertFalse(EVENT_TYPES['identity.seller_context_status_changed'].no_subscriber)
        self.assertIn(
            'marketplace.sync_seller_visibility',
            [s.name for s in subscribers_for('identity.seller_context_status_changed')],
        )


class ContextIntegrationTests(ProviderBase):
    def test_contexts_lists_provider_after_activation(self):
        self.assertEqual([c['type'] for c in self.client.get(CONTEXTS).json()['results']], ['USER'])
        profile_id = self.activate(display_name='Visible').json()['id']
        results = self.client.get(CONTEXTS).json()['results']
        provider = next(c for c in results if c['type'] == 'PROVIDER')
        self.assertEqual((provider['id'], provider['name']), (profile_id, 'Visible'))
        self.assertNotEqual(provider['id'], str(self.user.pk))
        self.assertEqual(set(provider['capabilities']), set(capabilities.capabilities_for_context('PROVIDER')))
        self.assertFalse(any(c.startswith('org.') for c in provider['capabilities']))
        self.assertTrue(services.acts_for_context(self.user.pk, 'PROVIDER', profile_id))
        self.assertFalse(services.acts_for_context(make_user('autre').pk, 'PROVIDER', profile_id))

    def test_archived_provider_leaves_contexts(self):
        self.activate(display_name='Visible')
        self.client.post(ARCHIVE)
        self.assertEqual([c['type'] for c in self.client.get(CONTEXTS).json()['results']], ['USER'])

    def test_x_context_provider_resolution(self):
        profile_id = self.activate(display_name='Visible').json()['id']
        ctx = services.resolve_acting_context(self.user, f'PROVIDER:{profile_id}')
        self.assertEqual((ctx.type, str(ctx.id)), ('PROVIDER', profile_id))
        other = make_user('autre')
        with self.assertRaises(ContextDenied) as denied:
            services.resolve_acting_context(other, f'PROVIDER:{profile_id}')
        self.assertEqual(denied.exception.get_codes(), DENY_CONTEXT)
        self.client.post(ARCHIVE)
        with self.assertRaises(ContextDenied) as denied:
            services.resolve_acting_context(self.user, f'PROVIDER:{profile_id}')
        self.assertEqual(denied.exception.get_codes(), DENY_OBJECT_STATE)

    def test_routes_ignore_x_context_header(self):
        self.activate(display_name='Visible')
        response = self.client.get(URL, HTTP_X_CONTEXT='ORGANIZATION:00000000-0000-0000-0000-000000000000')
        self.assertEqual(response.status_code, 200)


@override_settings(CACHES=LOCMEM_CACHE)
class ThrottleAndAdminTests(ProviderBase):
    def test_rate_is_configured_and_applies_to_writes_only(self):
        self.assertIn('provider_write', settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'])
        self.activate(display_name='Premier')
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'provider_write': '2/hour'}):
            for _ in range(5):
                self.assertEqual(self.client.get(URL).status_code, 200)
            codes = [self.client.patch(URL, {'bio': str(i)}, format='json').status_code for i in range(3)]
        self.assertEqual(codes, [200, 429, 429])

    def test_admin_is_read_only(self):
        from django.contrib import admin

        model_admin = admin.site._registry[ProviderProfile]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None))
        self.assertIn('user', model_admin.exclude)
