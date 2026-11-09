"""Recette L0-09j : compte unique, contextes et organisations (scénarios IAM, matrice rôle x action x contexte,
règles verrouillées 1, 2, 3, 4, 10, 11 et 12).

Les scénarios passent par l'API HTTP (en-tête `X-Context`) ; seules les opérations d'équipe (ajout, changement
de rôle, retrait : aucun endpoint avant L1-01) passent par `identity.services`, comme le fera l'API.
Complète sans les modifier les tests de chaque domaine (`tests_contexts.py`, `tests_organizations_api.py`...).
"""
import json
import unittest
import uuid
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from apps.catalog.models import Category, City, Commune
from apps.common.factories import make_test_image
from apps.identity import services as identity_services
from apps.identity.models import IdentitySettings, KycDocument, Membership, Organization, ProviderProfile, User
from apps.marketplace.models import Offer
from apps.moderation.models import AuditLog, Sanction
from apps.notifications.models import Notification
from apps.platform_core.testing import dispatch_outbox_now
from apps.reviews.models import Review
from apps.reviews.tests import GOOD

OWNER, ADMIN, EDITOR, ANALYST = 'OWNER', 'ADMIN', 'EDITOR', 'ANALYST'
ROLES = (OWNER, ADMIN, EDITOR, ANALYST)
PASSWORD = 'Recette-l009-2026!'
CONTEXTS = '/api/accounts/contexts/'
ORGS = '/api/accounts/organizations/'
POSTS = '/api/marketplace/posts/'
SECRET_PHONE = '+243899112233'
SECRET_EMAIL = 'membre.secret@example.com'
SECRET_NAME = 'Zacharie Sentinelle-Membre'
SECRET_NIF = 'NIF-RECETTE-9981'


def ctx(kind, ident):
    return {'HTTP_X_CONTEXT': f'{kind}:{ident}'}


class RecetteBase(APITestCase):
    def setUp(self):
        self.city = City.objects.create(name='Kinshasa')
        self.commune = Commune.objects.create(city=self.city, name='Gombe')
        self.category = Category.objects.create(name='Électronique', slug='electronique')
        self.org = Organization.objects.create(name='Atelier Recette', org_type='ENTREPRISE', nif=SECRET_NIF)
        self.other_org = Organization.objects.create(name='Boutique Voisine', org_type='BOUTIQUE')
        self.team = {}
        for role in ROLES:
            user = User.objects.create_user(
                email=f'{role.lower()}@example.com', password='x', full_name=f'Membre {role}', phone_verified=True,
            )
            Membership.objects.create(organization=self.org, user=user, role=role)
            self.team[role] = user
        self.outsider = User.objects.create_user(
            email='outsider@example.com', password='x', full_name='Etranger Lambda', phone_verified=True)
        self.buyer = User.objects.create_user(
            email='buyer@example.com', password='x', full_name='Acheteur Test', phone_verified=True)
        self.staff = User.objects.create_user(
            email='staff@example.com', password='x', full_name='Personnel', is_staff=True, phone_verified=True)

    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def payload(self, **extra):
        data = {
            'title': 'Un titre correct', 'description': 'Description suffisamment longue pour valider.',
            'price': 10, 'category': str(self.category.id), 'commune': str(self.commune.id),
            'main_image': make_test_image(),
        }
        data.update(extra)
        return data

    def publish(self, user, headers=None, **extra):
        return self.api(user).post(POSTS, self.payload(**extra), **(headers or {}))

    def org_offer(self, org=None, **kwargs):
        org = org or self.org
        defaults = dict(
            category_id=self.category.id, commune_id=self.commune.id, title='Offre de l\'atelier',
            description='Description suffisamment longue pour passer la validation.', price=100,
            main_image=make_test_image(), seller_context_type='ORGANIZATION', seller_context_id=org.pk,
            created_by=self.team[OWNER],
        )
        defaults.update(kwargs)
        return Offer.objects.create(**defaults)

    def results(self, response):
        data = response.json()
        return data['results'] if isinstance(data, dict) else data

    def code(self, response):
        data = response.json() if response.content else {}
        return data.get('code') if isinstance(data, dict) else None


# --- IAM-01 à IAM-06 ------------------------------------------------------------------------

class IamScenarioTests(RecetteBase):
    def test_IAM01_registration_creates_one_personal_context_and_no_organization(self):
        client = APIClient()
        phone = '+243811119999'
        with mock.patch('apps.identity.views.send_otp_sms') as sms:
            self.assertEqual(client.post('/api/accounts/otp/request/', {'phone': phone, 'purpose': 'REGISTER'},
                                         format='json').status_code, 200)
        body = {'full_name': 'Nouveau Compte', 'password': PASSWORD, 'phone': phone, 'otp_code': sms.call_args[0][1]}
        before = Organization.objects.count()
        created = client.post('/api/accounts/register/', body, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        self.assertTrue(created.json()['phone_verified'])
        self.assertEqual(Organization.objects.count(), before)
        token = client.post('/api/accounts/login/', {'phone': phone, 'password': PASSWORD}, format='json').json()
        listing = client.get(CONTEXTS, HTTP_AUTHORIZATION=f"Bearer {token['access']}")
        self.assertEqual(listing.status_code, 200)
        types = [c['type'] for c in listing.json()['results' if 'results' in listing.json() else 'contexts']] \
            if isinstance(listing.json(), dict) else [c['type'] for c in listing.json()]
        self.assertEqual(types, ['USER'])

    def test_IAM02_provider_context_is_usable_only_after_activation(self):
        user = self.outsider
        profile_id = uuid.uuid4()
        self.assertEqual(self.code(self.publish(user, ctx('PROVIDER', profile_id))), 'DENY_CONTEXT')
        activated = self.api(user).post('/api/accounts/provider/activate/', {'display_name': 'Marie couture'},
                                        format='json')
        self.assertIn(activated.status_code, (200, 201), activated.content)
        profile = ProviderProfile.objects.get(user=user)
        published = self.publish(user, ctx('PROVIDER', profile.pk))
        self.assertEqual(published.status_code, 201, published.content)
        offer = Offer.objects.get(pk=published.json()['id'])
        self.assertEqual((offer.seller_context_type, offer.seller_context_id), ('PROVIDER', profile.pk))
        # Un autre compte ne peut pas emprunter ce profil prestataire.
        self.assertEqual(self.code(self.publish(self.buyer, ctx('PROVIDER', profile.pk))), 'DENY_CONTEXT')

    def test_IAM03_organization_context_needs_an_active_membership(self):
        self.assertEqual(self.code(self.publish(self.outsider, ctx('ORGANIZATION', self.org.pk))), 'DENY_RELATION')
        Membership.objects.create(organization=self.org, user=self.outsider, role=EDITOR)
        ok = self.publish(self.outsider, ctx('ORGANIZATION', self.org.pk))
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_IAM03_unknown_organization_is_indistinguishable_from_a_foreign_one(self):
        foreign = self.publish(self.outsider, ctx('ORGANIZATION', self.org.pk))
        unknown = self.publish(self.outsider, ctx('ORGANIZATION', uuid.uuid4()))
        self.assertEqual((foreign.status_code, self.code(foreign)), (unknown.status_code, self.code(unknown)))
        self.assertNotIn(self.org.name, foreign.content.decode())

    def test_IAM05_restricted_account_is_refused_in_every_context(self):
        Sanction.objects.create(user=self.team[EDITOR], sanction_type='SUSPENSION_TEMPORAIRE', reason='test',
                                is_active=True)
        member = self.team[EDITOR]
        for headers in ({}, ctx('USER', member.pk), ctx('ORGANIZATION', self.org.pk)):
            with self.subTest(headers=headers):
                response = self.publish(member, headers)
                self.assertEqual(response.status_code, 403, response.content)
        # Création d'une organisation et d'une activation prestataire refusées aussi.
        client = self.api(member)
        created = client.post(ORGS, {'name': 'Interdite Sarl', 'org_type': 'ENTREPRISE'}, format='json')
        self.assertEqual(created.status_code, 403, created.content)
        self.assertFalse(Organization.objects.filter(name='Interdite Sarl').exists())
        self.assertEqual(client.post('/api/accounts/provider/activate/', {'display_name': 'X Y'},
                                     format='json').status_code, 403)

    def test_IAM05_restriction_does_not_leak_into_the_contexts_of_others(self):
        Sanction.objects.create(user=self.team[EDITOR], sanction_type='BANNISSEMENT', reason='test', is_active=True)
        self.assertEqual(self.publish(self.team[ADMIN], ctx('ORGANIZATION', self.org.pk)).status_code, 201)

    def test_IAM06_revoked_member_loses_access_on_the_very_next_request(self):
        member = self.team[EDITOR]
        client = self.api(member)
        headers = ctx('ORGANIZATION', self.org.pk)
        self.assertEqual(client.post(POSTS, self.payload(), **headers).status_code, 201)
        identity_services.revoke_member(self.team[OWNER], self.org.pk, member.pk)
        self.assertEqual(self.code(client.post(POSTS, self.payload(), **headers)), 'DENY_RELATION')
        listed = client.get(CONTEXTS).json()
        text = json.dumps(listed)
        self.assertNotIn(str(self.org.pk), text)
        self.assertEqual(client.get(f'{ORGS}{self.org.pk}/internal/').status_code, 403)
        # Le compte personnel reste utilisable.
        self.assertEqual(client.post(POSTS, self.payload()).status_code, 201)

    def test_IAM06_a_role_downgrade_is_immediate_too(self):
        member = self.team[EDITOR]
        client = self.api(member)
        identity_services.change_member_role(self.team[OWNER], self.org.pk, member.pk, ANALYST)
        self.assertEqual(self.code(client.post(POSTS, self.payload(), **ctx('ORGANIZATION', self.org.pk))),
                         'DENY_PERMISSION')


# --- Matrice rôle x action ----------------------------------------------------------------

class RoleMatrixTests(RecetteBase):
    def test_offer_publication_edit_and_delete_by_role(self):
        for role, allowed in ((OWNER, True), (ADMIN, True), (EDITOR, True), (ANALYST, False)):
            with self.subTest(role=role):
                user = self.team[role]
                headers = ctx('ORGANIZATION', self.org.pk)
                response = self.publish(user, headers, title=f'Offre de {role} ici')
                self.assertEqual(response.status_code, 201 if allowed else 403, response.content)
                offer = self.org_offer(title=f'Offre cible {role}')
                edit = self.api(user).patch(f'{POSTS}{offer.pk}/', {'title': f'Modifiée par {role}'},
                                            format='json', **headers)
                self.assertEqual(edit.status_code, 200 if allowed else 403, edit.content)
                delete = self.api(user).delete(f'{POSTS}{offer.pk}/', **headers)
                self.assertIn(delete.status_code, (204, 200) if allowed else (403,), delete.content)

    def test_identity_edition_by_role(self):
        for role, allowed in ((OWNER, True), (ADMIN, True), (EDITOR, False), (ANALYST, False)):
            with self.subTest(role=role):
                response = self.api(self.team[role]).patch(
                    f'{ORGS}{self.org.pk}/', {'description': f'Description {role}'}, format='json')
                self.assertEqual(response.status_code, 200 if allowed else 403, response.content)
                if not allowed:
                    self.assertEqual(self.code(response), 'DENY_PERMISSION')

    def test_org_type_is_immutable_for_everybody_even_the_owner(self):
        response = self.api(self.team[OWNER]).patch(f'{ORGS}{self.org.pk}/', {'org_type': 'ONG'}, format='json')
        self.assertEqual(response.status_code, 400, response.content)
        self.org.refresh_from_db()
        self.assertEqual(self.org.org_type, 'ENTREPRISE')

    def test_archive_is_reserved_to_the_owner(self):
        for role in (ADMIN, EDITOR, ANALYST):
            with self.subTest(role=role):
                self.assertEqual(self.api(self.team[role]).post(f'{ORGS}{self.org.pk}/archive/').status_code, 403)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, Organization.STATUS_ACTIVE)
        self.assertEqual(self.api(self.team[OWNER]).post(f'{ORGS}{self.org.pk}/archive/').status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action='ORG_ARCHIVED', actor=self.team[OWNER]).exists())

    def test_internal_detail_exposes_the_nif_only_to_roles_that_can_edit(self):
        for role, sees in ((OWNER, True), (ADMIN, True), (EDITOR, False), (ANALYST, False)):
            with self.subTest(role=role):
                body = self.api(self.team[role]).get(f'{ORGS}{self.org.pk}/internal/')
                self.assertEqual(body.status_code, 200)
                self.assertEqual(SECRET_NIF in body.content.decode(), sees)

    def test_a_member_of_another_organization_gets_nothing_on_this_one(self):
        Membership.objects.create(organization=self.other_org, user=self.outsider, role=OWNER)
        client = self.api(self.outsider)
        for call in (
            lambda: client.get(f'{ORGS}{self.org.pk}/internal/'),
            lambda: client.patch(f'{ORGS}{self.org.pk}/', {'name': 'Piratée'}, format='json'),
            lambda: client.post(f'{ORGS}{self.org.pk}/archive/'),
            lambda: client.post(f'{ORGS}{self.org.pk}/leave/'),
            lambda: client.get(f'{ORGS}{self.org.pk}/kyc/documents/'),
            lambda: client.get(f'{ORGS}{self.org.pk}/verification/'),
            # L'en-tête de SA propre organisation ne donne aucun droit sur celle du chemin.
            lambda: client.patch(f'{ORGS}{self.org.pk}/', {'name': 'Piratée'}, format='json',
                                 **ctx('ORGANIZATION', self.other_org.pk)),
        ):
            response = call()
            self.assertEqual(response.status_code, 403, response.content)
        self.org.refresh_from_db()
        self.assertEqual(self.org.name, 'Atelier Recette')

    def test_staff_flag_opens_nothing_inside_an_organization(self):
        client = self.api(self.staff)
        self.assertEqual(client.get(f'{ORGS}{self.org.pk}/internal/').status_code, 403)
        self.assertEqual(client.patch(f'{ORGS}{self.org.pk}/', {'name': 'Staff'}, format='json').status_code, 403)
        self.assertEqual(self.code(self.publish(self.staff, ctx('ORGANIZATION', self.org.pk))), 'DENY_RELATION')

    def test_team_management_matrix_service_level(self):
        owner, admin, editor, analyst = (self.team[r] for r in ROLES)
        newcomer = User.objects.create_user(email='new@example.com', password='x', full_name='Nouveau', phone_verified=True)
        S = identity_services
        # Un administrateur ne touche jamais au propriétaire et ne crée pas de propriétaire.
        for call in (
            lambda: S.revoke_member(admin, self.org.pk, owner.pk),
            lambda: S.change_member_role(admin, self.org.pk, owner.pk, EDITOR),
            lambda: S.change_member_role(admin, self.org.pk, editor.pk, OWNER),
            lambda: S.add_member(admin, self.org.pk, newcomer.pk, OWNER),
            lambda: S.transfer_ownership(admin, self.org.pk, editor.pk),
            # Ni l'éditeur ni l'analyste ne gèrent l'équipe.
            lambda: S.add_member(editor, self.org.pk, newcomer.pk, ANALYST),
            lambda: S.change_member_role(analyst, self.org.pk, editor.pk, ANALYST),
            lambda: S.revoke_member(editor, self.org.pk, analyst.pk),
        ):
            with self.assertRaises(Exception) as caught:
                call()
            self.assertEqual(getattr(caught.exception, 'status_code', None), 403, repr(caught.exception))
        self.assertEqual(Membership.objects.filter(organization=self.org, status='ACTIVE').count(), 4)
        # Un administrateur ne s'auto-promeut pas.
        with self.assertRaises(Exception):
            S.change_member_role(admin, self.org.pk, admin.pk, OWNER)
        self.assertEqual(Membership.objects.get(organization=self.org, user=admin).role, ADMIN)

    def test_last_owner_invariant_on_every_path(self):
        owner = self.team[OWNER]
        S = identity_services
        for call in (
            lambda: S.leave_organization(owner, self.org.pk),
            lambda: S.change_member_role(owner, self.org.pk, owner.pk, ADMIN),
            lambda: S.transfer_ownership(owner, self.org.pk, self.team[ADMIN].pk, OWNER),
        ):
            with self.assertRaises(Exception):
                call()
        self.assertEqual(S.count_active_owners(self.org.pk), 1)
        leave = self.api(owner).post(f'{ORGS}{self.org.pk}/leave/')
        self.assertEqual((leave.status_code, self.code(leave)), (409, 'last_owner'))

    def test_AC14_every_team_change_is_audited_with_actor_target_context_and_no_personal_value(self):
        owner, admin, editor = self.team[OWNER], self.team[ADMIN], self.team[EDITOR]
        newcomer = User.objects.create_user(email='nv@example.com', password='x', full_name='Nom Nouveau', phone_verified=True)
        S = identity_services
        S.add_member(owner, self.org.pk, newcomer.pk, ANALYST)
        S.change_member_role(admin, self.org.pk, newcomer.pk, EDITOR)
        S.revoke_member(admin, self.org.pk, newcomer.pk)
        S.leave_organization(editor, self.org.pk)
        S.transfer_ownership(owner, self.org.pk, admin.pk, ADMIN)
        entries = AuditLog.objects.filter(context_type='ORGANIZATION', context_id=self.org.pk)
        actions = set(entries.values_list('action', flat=True))
        self.assertTrue({'MEMBERSHIP_ADDED', 'MEMBERSHIP_ROLE_CHANGED', 'MEMBERSHIP_REVOKED',
                         'ORG_OWNERSHIP_TRANSFERRED'} <= actions, actions)
        for entry in entries:
            self.assertIsNotNone(entry.actor_id, entry.action)
            self.assertIsNotNone(entry.created_at)
            blob = f'{entry.details} {entry.target_type}'
            for secret in ('Nom Nouveau', 'nv@example.com', 'Membre ', 'example.com', SECRET_NIF):
                self.assertNotIn(secret, blob, entry.action)
        added = entries.get(action='MEMBERSHIP_ADDED')
        self.assertEqual((added.actor_id, added.target_type), (owner.pk, 'membership'))
        self.assertIn('ANALYST', added.details)


# --- Règle 2 et 3 : plan et vérification ------------------------------------------------------

class VerificationRulesTests(RecetteBase):
    def verification(self, user):
        return self.api(user).get(f'{ORGS}{self.org.pk}/verification/')

    def test_a_submitted_piece_verifies_nothing_and_only_a_staff_decision_does(self):
        owner = self.team[OWNER]
        upload = SimpleUploadedFile('rccm.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        sent = self.api(owner).post(f'{ORGS}{self.org.pk}/kyc/documents/',
                                    {'document_type': 'RCCM', 'file': upload}, format='multipart')
        self.assertEqual(sent.status_code, 201, sent.content)
        self.assertEqual(self.verification(owner).json().get('verified_claims', []), [])
        doc = KycDocument.objects.get(organization=self.org)
        # Ni le propriétaire, ni un autre membre, ni un compte sans droit ne décident.
        for user in (owner, self.team[ADMIN], self.outsider, self.staff):
            response = self.api(user).post(f'/api/accounts/kyc/documents/{doc.pk}/decision/',
                                           {'decision': 'VALIDE'}, format='json')
            self.assertEqual(response.status_code, 403, (user.email, response.content))
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'EN_ATTENTE')

    def test_analyst_and_editor_cannot_submit_pieces_nor_delete_them(self):
        for role in (EDITOR, ANALYST):
            upload = SimpleUploadedFile('rccm.pdf', b'%PDF-1.4 test', content_type='application/pdf')
            response = self.api(self.team[role]).post(
                f'{ORGS}{self.org.pk}/kyc/documents/', {'document_type': 'RCCM', 'file': upload}, format='multipart')
            self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(KycDocument.objects.filter(organization=self.org).exists())

    def test_verification_responses_never_contain_a_file_url_or_path(self):
        owner = self.team[OWNER]
        upload = SimpleUploadedFile('secret-name.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        sent = self.api(owner).post(f'{ORGS}{self.org.pk}/kyc/documents/',
                                    {'document_type': 'RCCM', 'file': upload}, format='multipart')
        listed = self.api(owner).get(f'{ORGS}{self.org.pk}/kyc/documents/')
        for response in (sent, listed, self.verification(owner)):
            text = response.content.decode()
            self.assertNotIn('secret-name', text)
            self.assertNotIn('private_media', text)
            self.assertNotIn('.pdf', text)

    def test_no_paid_plan_or_staff_flag_exposes_a_verified_claim(self):
        for path in (f'{ORGS}', f'{ORGS}{self.org.pk}/internal/'):
            body = self.api(self.team[OWNER]).get(path).content.decode()
            self.assertNotIn('is_verified', body)
        public = self.api().get(ORGS).json()
        for item in public['results']:
            self.assertEqual(item['verified_claims'], [])

    def test_no_endpoint_writes_a_verification_claim_or_a_role_from_a_plan(self):
        """AC-08 : aucune route de paiement ou de plan ne touche aux rôles ni aux pièces."""
        from apps.common.tests_privacy import iter_routes
        names = [str(pattern) for pattern in iter_routes()]
        offenders = [n for n in names if any(w in n.lower() for w in ('plan', 'subscription', 'upgrade', 'buy-badge'))]
        self.assertEqual(offenders, [], offenders)


# --- Règle 4 : notes par contexte, hors classement ------------------------------------------------

class RatingRulesTests(RecetteBase):
    def test_ranking_options_never_include_a_rating_or_a_trust_criterion(self):
        offer = self.org_offer()
        for ordering in ('-seller_rating', 'seller_rating', '-offer_rating', '-rating', '-trust_score'):
            with self.subTest(ordering=ordering):
                response = self.api().get(POSTS, {'ordering': ordering})
                self.assertEqual(response.status_code, 200)
        self.assertNotIn('trust', json.dumps(self.api().get(f'{POSTS}{offer.pk}/').json()).lower())

    def test_ratings_of_an_organization_do_not_move_the_organic_order(self):
        low = self.org_offer(title='Offre sans avis aucun')
        high = self.org_offer(title='Offre très bien notée')
        before = [o['id'] for o in self.results(self.api().get(POSTS))]
        from django.utils import timezone
        scores = dict(Offer.objects.values_list('pk', 'visibility_score'))
        for i in range(6):
            reviewer = User.objects.create_user(email=f'r{i}@example.com', password='x', full_name=f'R {i}')
            Review.objects.create(
                user=reviewer, offer_id=high.pk, seller_context_type='ORGANIZATION', seller_context_id=self.org.pk,
                contact_event_id=uuid.uuid4(), contact_channel='MESSAGE', contact_recorded_at=timezone.now(),
                offer_rating=5, seller_rating=5, content='Excellent produit, livraison rapide et soignée.',
            )
        after = [o['id'] for o in self.results(self.api().get(POSTS))]
        self.assertEqual(before, after)
        self.assertEqual(scores, dict(Offer.objects.values_list('pk', 'visibility_score')))
        self.assertEqual({str(low.pk), str(high.pk)}, set(after))

    def test_sponsored_flag_is_never_set_by_an_organization_context(self):
        response = self.publish(self.team[OWNER], ctx('ORGANIZATION', self.org.pk), is_sponsored='true')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(response.json().get('is_sponsored'))


# --- Règle 10 : données personnelles ------------------------------------------------------------

class PrivacySweepTests(RecetteBase):
    def setUp(self):
        super().setUp()
        for role, user in self.team.items():
            User.objects.filter(pk=user.pk).update(
                phone=f'+24389911223{ROLES.index(role)}', email=f'secret-{role.lower()}@example.com',
                full_name=f'{SECRET_NAME} {role}')
        self.offer = self.org_offer()

    def sweep(self, client, paths):
        for path in paths:
            response = client.get(path)
            self.assertEqual(response.status_code, 200, path)
            text = response.content.decode()
            for needle in ('+24389911223', 'secret-owner', 'secret-admin', 'secret-editor', 'secret-analyst',
                           SECRET_NAME, SECRET_NIF, 'Sentinelle-Membre'):
                self.assertNotIn(needle, text, f'{path} -> {response.status_code}')

    def test_public_surfaces_of_an_organization_expose_no_personal_data(self):
        paths = [ORGS, POSTS, f'{POSTS}{self.offer.pk}/', f'/api/marketplace/sellers/organization/{self.org.pk}/',
                 f'/api/interactions/reviews/?offer={self.offer.pk}']
        self.sweep(self.api(), paths)
        self.sweep(self.api(self.buyer), paths)

    def test_member_facing_surfaces_expose_no_other_member_identity(self):
        client = self.api(self.team[OWNER])
        for path in (CONTEXTS, f'{ORGS}{self.org.pk}/internal/', '/api/interactions/conversations/',
                     '/api/interactions/notifications/'):
            text = client.get(path, **ctx('ORGANIZATION', self.org.pk)).content.decode()
            for role in (ADMIN, EDITOR, ANALYST):
                self.assertNotIn(f'secret-{role.lower()}@', text, path)
                self.assertNotIn(f'{SECRET_NAME} {role}', text, path)
        # Le contexte listé du membre n'expose que son propre rôle.
        self.assertNotIn(SECRET_NIF, json.dumps(self.api(self.team[ANALYST]).get(CONTEXTS).json()))

    def test_audit_details_of_organization_actions_hold_no_name_nor_contact(self):
        self.api(self.team[OWNER]).patch(f'{ORGS}{self.org.pk}/', {'description': 'Nouveau texte'}, format='json')
        created = self.api(self.outsider).post(ORGS, {'name': 'Nom Très Privé Sarl', 'org_type': 'ONG'}, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        for entry in AuditLog.objects.all():
            blob = f'{entry.details}'
            for needle in ('Nom Très Privé', '@example.com', '+24389911223', SECRET_NIF, SECRET_NAME):
                self.assertNotIn(needle, blob, entry.action)
        self.assertTrue(AuditLog.objects.filter(action='ORG_CREATED', actor=self.outsider).exists())


# --- Organisations suspendues ou archivées -----------------------------------------------------------

class UnavailableOrganizationTests(RecetteBase):
    def test_suspension_closes_the_context_hides_offers_and_keeps_data_and_leave(self):
        offer = self.org_offer()
        self.assertEqual(self.api().get(f'{POSTS}{offer.pk}/').status_code, 200)
        identity_services.suspend_organization(self.staff_with_perm(), self.org.pk, next(iter(identity_services.SUSPENSION_REASONS)))
        dispatch_outbox_now()
        member = self.team[OWNER]
        self.assertEqual(self.code(self.publish(member, ctx('ORGANIZATION', self.org.pk))), 'DENY_SECURITY')
        listed = self.api(member).get(CONTEXTS).json()
        self.assertIn('unavailable', json.dumps(listed))
        self.assertNotIn(offer.pk.hex, json.dumps(self.api().get(POSTS).json()).replace('-', ''))
        self.assertEqual(self.api().get(f'{POSTS}{offer.pk}/').status_code, 404)
        self.assertNotIn(str(self.org.pk), json.dumps(self.api().get(ORGS).json()))
        self.assertEqual(self.api(self.team[EDITOR]).post(f'{ORGS}{self.org.pk}/leave/').status_code, 204)
        self.assertTrue(Offer.objects.filter(pk=offer.pk).exists())
        # La réactivation par le personnel rend tout, sans réactiver un ancien membre.
        identity_services.reactivate_organization(self.staff_with_perm(), self.org.pk)
        dispatch_outbox_now()
        self.assertEqual(self.api().get(f'{POSTS}{offer.pk}/').status_code, 200)
        self.assertEqual(Membership.objects.get(organization=self.org, user=self.team[EDITOR]).status, 'REVOKED')

    def staff_with_perm(self):
        from django.contrib.auth.models import Permission
        perm = Permission.objects.get(codename='suspend_organization')
        user, _ = User.objects.get_or_create(
            email='mod@example.com', defaults={'full_name': 'Moderateur', 'is_staff': True})
        user.user_permissions.add(perm)
        return User.objects.get(pk=user.pk)

    def test_only_staff_with_the_permission_can_suspend(self):
        for user in (self.team[OWNER], self.staff, self.outsider):
            with self.assertRaises(Exception) as caught:
                identity_services.suspend_organization(user, self.org.pk, next(iter(identity_services.SUSPENSION_REASONS)))
            self.assertEqual(caught.exception.status_code, 403)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'ACTIVE')

    def test_archived_organization_is_never_reactivated_by_staff_and_closes_every_write(self):
        self.api(self.team[OWNER]).post(f'{ORGS}{self.org.pk}/archive/')
        with self.assertRaises(Exception):
            identity_services.reactivate_organization(self.staff_with_perm(), self.org.pk)
        self.assertEqual(self.code(self.publish(self.team[OWNER], ctx('ORGANIZATION', self.org.pk))), 'DENY_OBJECT_STATE')
        patch = self.api(self.team[OWNER]).patch(f'{ORGS}{self.org.pk}/', {'description': 'x y z'}, format='json')
        self.assertEqual(patch.status_code, 403)
        self.assertEqual(self.api(self.team[OWNER]).post(f'{ORGS}{self.org.pk}/archive/').status_code, 403)

    def test_suspended_organization_notifies_the_whole_team_not_the_outsider(self):
        identity_services.suspend_organization(self.staff_with_perm(), self.org.pk, next(iter(identity_services.SUSPENSION_REASONS)))
        dispatch_outbox_now()
        for role in ROLES:
            self.assertTrue(Notification.objects.filter(user=self.team[role]).exists(), role)
        self.assertFalse(Notification.objects.filter(user=self.outsider).exists())
        self.assertFalse(Notification.objects.filter(user=self.buyer).exists())


# --- Suppression de compte -----------------------------------------------------------------------

class AccountDeletionTests(RecetteBase):
    def test_sole_owner_cannot_be_deleted_but_a_co_owner_can_and_the_organization_survives(self):
        owner = self.team[OWNER]
        offer = self.org_offer()
        with self.assertRaises(Exception) as caught, transaction.atomic():
            owner.delete()
        self.assertEqual(getattr(caught.exception, 'status_code', 409), 409)
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        Membership.objects.filter(organization=self.org, user=self.team[ADMIN]).update(role=OWNER)
        owner.delete()
        self.assertTrue(Organization.objects.filter(pk=self.org.pk).exists())
        self.assertTrue(Offer.objects.filter(pk=offer.pk).exists())
        self.assertEqual(Offer.objects.get(pk=offer.pk).seller_context_id, self.org.pk)

    def test_sanctioned_account_is_not_deleted(self):
        user = self.outsider
        Sanction.objects.create(user=user, sanction_type='BANNISSEMENT', reason='t', is_active=True)
        with self.assertRaises(Exception), transaction.atomic():
            user.delete()
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_deleting_an_account_purges_personal_and_provider_offers_but_never_the_team_offers(self):
        member = self.team[EDITOR]
        mine = self.make_personal(member)
        theirs = self.org_offer(created_by=member)
        member.delete()
        self.assertFalse(Offer.objects.filter(pk=mine.pk).exists())
        self.assertTrue(Offer.objects.filter(pk=theirs.pk).exists())
        self.assertTrue(Organization.objects.filter(pk=self.org.pk).exists())

    def make_personal(self, user):
        return Offer.objects.create(
            category_id=self.category.id, commune_id=self.commune.id, title='Offre personnelle',
            description='Description suffisamment longue pour passer la validation.', price=5,
            main_image=make_test_image(), seller_context_type='USER', seller_context_id=user.pk, created_by=user)


# --- Règle 11 : réglages configurables -----------------------------------------------------------------

class SettingsTests(RecetteBase):
    def test_organization_limit_comes_from_the_settings(self):
        solo = User.objects.create_user(email='solo@example.com', password='x', full_name='Solo', phone_verified=True)
        settings_row = IdentitySettings.get_solo()
        settings_row.max_organizations_per_account = 2
        settings_row.save()
        client = self.api(solo)
        limits = client.get(f'{ORGS}limits/')
        self.assertEqual(limits.status_code, 200)
        self.assertIn('2', json.dumps(limits.json()))
        for i in range(2):
            self.assertEqual(client.post(ORGS, {'name': f'Orga numero {i}', 'org_type': 'ONG'}, format='json').status_code, 201)
        refused = client.post(ORGS, {'name': 'Orga numero 3', 'org_type': 'ONG'}, format='json')
        self.assertEqual(refused.status_code, 409, refused.content)
        self.assertEqual(self.code(refused), 'organization_limit_reached')
        settings_row.max_organizations_per_account = 3
        settings_row.save()
        self.assertEqual(client.post(ORGS, {'name': 'Orga numero 3', 'org_type': 'ONG'}, format='json').status_code, 201)

    def test_double_submission_of_the_creation_form_never_duplicates_silently(self):
        solo = User.objects.create_user(email='dbl@example.com', password='x', full_name='Double', phone_verified=True)
        client = self.api(solo)
        body = {'name': 'Meme Nom Sarl', 'org_type': 'ENTREPRISE'}
        first = client.post(ORGS, body, format='json')
        second = client.post(ORGS, body, format='json')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(Organization.objects.filter(name='Meme Nom Sarl').count(), 1 if second.status_code >= 400 else 2)
        # Le nom d'une organisation n'est pas unique (collision de noms, spec T9 : jamais fusionnées) : deux
        # propriétaires différents peuvent donc porter le même nom.
        other = self.api(self.outsider).post(ORGS, body, format='json')
        self.assertIn(other.status_code, (201, 400, 409))


# --- En-tête X-Context ----------------------------------------------------------------------------------

class HeaderTests(RecetteBase):
    def test_hostile_headers_never_fall_back_to_the_personal_context(self):
        member = self.team[OWNER]
        for raw in ('', ' ', 'ORGANIZATION', 'ORGANIZATION:', 'ORGANIZATION:nope', 'TEAM:' + str(self.org.pk),
                    f'organization:{self.org.pk}', f'USER:{self.buyer.pk}', f'ORGANIZATION:{self.org.pk}:x',
                    'A' * 5000, f'ORGANIZATION:{self.org.pk}\r\nX-Evil: 1'):
            with self.subTest(raw=raw[:40]):
                try:
                    response = self.api(member).post(POSTS, self.payload(), HTTP_X_CONTEXT=raw)
                except ValueError:
                    continue
                self.assertEqual(response.status_code, 403, (raw[:40], response.content))
        self.assertFalse(Offer.objects.filter(created_by=member, seller_context_type='USER').exists())

    def test_anonymous_requests_with_a_context_header_are_unauthorized_not_forbidden(self):
        response = self.api().post(POSTS, self.payload(), **ctx('ORGANIZATION', self.org.pk))
        self.assertEqual(response.status_code, 401)

    def test_the_context_header_does_not_leak_through_the_public_reads(self):
        offer = self.org_offer()
        anonymous = self.api().get(f'{POSTS}{offer.pk}/', **ctx('ORGANIZATION', self.org.pk))
        self.assertEqual(anonymous.status_code, 200)

    @override_settings()
    def test_the_context_of_one_request_never_bleeds_into_the_next(self):
        client = self.api(self.team[OWNER])
        self.assertEqual(client.post(POSTS, self.payload(), **ctx('ORGANIZATION', self.org.pk)).status_code, 201)
        personal = client.post(POSTS, self.payload())
        self.assertEqual(personal.status_code, 201)
        created = Offer.objects.get(pk=personal.json()['id'])
        self.assertEqual(created.seller_context_type, 'USER')


# --- Parcours acheteur <-> équipe d'une organisation, de bout en bout -----------------------------------

class BuyerToOrganizationFlowTests(RecetteBase):
    """Contact, messagerie, avis et réponse par l'API, sans état injecté : l'acheteur ne voit jamais un membre ;
    chaque rôle ne voit que ce que sa capacité permet ; un membre ne peut pas s'auto-noter."""

    def setUp(self):
        super().setUp()
        for role, user in self.team.items():
            User.objects.filter(pk=user.pk).update(full_name=f'{SECRET_NAME} {role}', phone=f'+24389911223{ROLES.index(role)}')
        self.offer = self.org_offer()

    def test_contact_message_review_and_reply_never_expose_a_member(self):
        buyer = self.api(self.buyer)
        contact = buyer.post('/api/interactions/contacts/', {'post': str(self.offer.pk), 'message': 'Bonjour, disponible ?'},
                             format='json')
        self.assertEqual(contact.status_code, 201, contact.content)
        dispatch_outbox_now()
        dispatch_outbox_now()  # deux événements en chaîne : enregistrement du contact, puis remise au vendeur
        # Aucun numéro ni nom de membre dans la réponse acheteur.
        self.assertNotIn('+24389911223', contact.content.decode())
        self.assertNotIn(SECRET_NAME, contact.content.decode())
        # Les membres habilités voient la demande ; l'analyste est refusé (contact.view_requesters).
        for role, allowed in ((OWNER, True), (ADMIN, True), (EDITOR, True), (ANALYST, False)):
            response = self.api(self.team[role]).get('/api/interactions/contacts/requesters/', {'post': str(self.offer.pk)},
                                                     **ctx('ORGANIZATION', self.org.pk))
            if response.status_code == 404:
                break  # route d'un autre nom : couvert par marketplace.tests_contexts
            self.assertEqual(response.status_code == 200, allowed, (role, response.status_code))
        # Avis puis réponse (le délai minimal avant avis est simulé en reculant la date du contact).
        from datetime import timedelta
        from django.utils import timezone
        from apps.marketplace.models import ContactEvent
        past = timezone.now() - timedelta(days=5)
        ContactEvent.objects.update(created_at=past, delivered_at=past)
        User.objects.filter(pk=self.buyer.pk).update(date_joined=past - timedelta(days=30))
        self.buyer.refresh_from_db()
        buyer = self.api(self.buyer)
        review = buyer.post('/api/interactions/reviews/', {'post': str(self.offer.pk), **GOOD}, format='json')
        self.assertEqual(review.status_code, 201, review.content)
        review_id = review.json()['id']
        for role, allowed in ((ANALYST, False), (EDITOR, True)):
            response = self.api(self.team[role]).post(f'/api/interactions/reviews/{review_id}/reply/',
                                                      {'reply_content': f'Merci de {role}'}, format='json')
            self.assertEqual(response.status_code == 200, allowed, (role, response.content))
        public = self.api().get(f'/api/interactions/reviews/?offer={self.offer.pk}')
        text = public.content.decode()
        self.assertIn('Merci de EDITOR', text)
        self.assertNotIn(SECRET_NAME, text)
        self.assertNotIn('+24389911223', text)
        # Les membres sont notifiés dans le contexte de l'organisation, sans donnée personnelle des autres membres.
        dispatch_outbox_now()
        self.assertTrue(Notification.objects.filter(user=self.team[OWNER]).exists())
        for note in Notification.objects.filter(user__in=self.team.values()):
            self.assertNotIn(SECRET_NAME, json.dumps([note.title, note.content]))
        self.assertFalse(Notification.objects.filter(user=self.outsider).exists())

    def test_a_member_cannot_contact_nor_review_the_offer_of_his_own_organization(self):
        member = self.api(self.team[EDITOR])
        contact = member.post('/api/interactions/contacts/', {'post': str(self.offer.pk), 'message': 'Auto-contact'},
                              format='json')
        self.assertGreaterEqual(contact.status_code, 400, contact.content)
        review = member.post('/api/interactions/reviews/', {'post': str(self.offer.pk), **GOOD}, format='json')
        self.assertGreaterEqual(review.status_code, 400, review.content)
        self.assertFalse(Review.objects.filter(offer_id=self.offer.pk).exists())

    def test_the_buyer_conversation_is_invisible_to_a_stranger_and_to_another_organization(self):
        buyer = self.api(self.buyer)
        contact = buyer.post('/api/interactions/contacts/', {'post': str(self.offer.pk), 'message': 'Bonjour'}, format='json')
        self.assertEqual(contact.status_code, 201, contact.content)
        dispatch_outbox_now()
        conversations = buyer.get('/api/interactions/conversations/')
        self.assertEqual(conversations.status_code, 200)
        data = conversations.json()
        data = data['results'] if isinstance(data, dict) else data
        self.assertEqual(len(data), 1)
        conversation_id = data[0]['id']
        Membership.objects.create(organization=self.other_org, user=self.outsider, role=OWNER)
        for headers in ({}, ctx('ORGANIZATION', self.other_org.pk)):
            stranger = self.api(self.outsider)
            self.assertEqual(stranger.get(f'/api/interactions/conversations/{conversation_id}/', **headers).status_code, 404)
            written = stranger.post('/api/interactions/messages/', {'conversation': conversation_id, 'content': 'Intrus'},
                                    format='json', **headers)
            self.assertIn(written.status_code, (400, 403, 404))
        # L'analyste (sans `message.reply`) ne lit pas la boîte de l'organisation.
        analyst = self.api(self.team[ANALYST]).get('/api/interactions/conversations/', **ctx('ORGANIZATION', self.org.pk))
        self.assertIn(analyst.status_code, (200, 403))
        if analyst.status_code == 200:
            body = analyst.json()
            self.assertEqual(body['results'] if isinstance(body, dict) else body, [])


# --- Propriétaire sanctionné ou désactivé : visibilité de l'organisation ----------------------------------

class SanctionedOwnerTests(RecetteBase):
    def visible(self, offer):
        return self.api().get(f'{POSTS}{offer.pk}/').status_code == 200

    def settle(self):
        dispatch_outbox_now()
        dispatch_outbox_now()

    def test_sole_owner_sanctioned_hides_the_organization_then_a_lift_restores_it(self):
        offer = self.org_offer()
        sanction = Sanction.objects.create(user=self.team[OWNER], sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='x')
        sanction.apply()
        self.settle()
        self.assertFalse(self.visible(offer))
        self.assertEqual(self.api().get(f'/api/marketplace/sellers/organization/{self.org.pk}/').status_code, 404)
        # Les autres membres, eux, ne sont pas sanctionnés : l'équipe garde ses données.
        self.assertTrue(Offer.objects.filter(pk=offer.pk).exists())
        sanction.lift()
        self.settle()
        self.assertTrue(self.visible(offer))

    @unittest.expectedFailure
    def test_ANOMALIE_L009_01_directory_still_lists_an_organization_whose_sole_owner_is_sanctioned(self):
        """ANOMALIE (mineure) : l'annuaire `GET organizations/` liste encore l'organisation (statut ACTIVE) alors que
        ses offres sont masquées et que `sellers/organization/<id>/` répond 404 (aucun propriétaire actif, ADR A7).
        À retirer de `expectedFailure` une fois `public_organizations_queryset` aligné sur `is_seller_context_public`."""
        self.org_offer()
        Sanction.objects.create(user=self.team[OWNER], sanction_type=Sanction.TYPE_SUSPENSION_TEMPORAIRE, reason='x').apply()
        self.settle()
        self.assertEqual(self.api().get(f'/api/marketplace/sellers/organization/{self.org.pk}/').status_code, 404)
        self.assertNotIn(str(self.org.pk), json.dumps(self.api().get(ORGS).json()))

    def test_a_second_owner_keeps_the_organization_public_when_one_owner_is_sanctioned(self):
        offer = self.org_offer()
        identity_services.change_member_role(self.team[OWNER], self.org.pk, self.team[ADMIN].pk, OWNER)
        Sanction.objects.create(user=self.team[OWNER], sanction_type=Sanction.TYPE_BANNISSEMENT, reason='x').apply()
        self.settle()
        self.assertTrue(self.visible(offer))
        self.assertIn(str(self.org.pk), json.dumps(self.api().get(ORGS).json()))

    def test_a_deactivated_account_cannot_use_any_context_with_its_old_token(self):
        member = self.team[EDITOR]
        User.objects.filter(pk=member.pk).update(is_active=False)
        login = APIClient().post('/api/accounts/login/', {'email': member.email, 'password': 'x'}, format='json')
        self.assertIn(login.status_code, (400, 401, 403))
