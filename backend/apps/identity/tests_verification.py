"""Vérification des organisations (L0-09d / T4) : pièces KYB, décision du personnel, claims précis calculés à la
lecture, événement, non-fuite, admin. ADR 0006, sections 4.3, 5, 7, 8, 9.4 et 12."""
import inspect
import json
import os
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.moderation.models import AuditLog, Sanction
from apps.platform_core import catalog
from apps.platform_core.models import OutboxEvent

from . import services
from .models import KycDocument, Membership, Organization, OrganizationDocumentRequirement, User
from .tests_organizations import ADMIN, ANALYST, TeamTestBase, make_user

from .tests import PDF_BYTES, PNG_BYTES

PNG = PNG_BYTES
PDF = PDF_BYTES
RCCM, IDN, REP, ARRETE = 'RCCM', 'ID_NATIONALE', 'PIECE_GERANT', 'ARRETE_ONG'
EVENT = 'identity.organization_verification_changed'
DOC_KEYS = {'id', 'document_type', 'document_type_label', 'status', 'rejection_reason', 'uploaded_at', 'reviewed_at'}


def upload(content=PNG, name='piece.png'):
    return SimpleUploadedFile(name, content, content_type='application/octet-stream')


def reviewer(label='rev', perm=True):
    user = make_user(label, is_staff=True)
    if perm:
        user.user_permissions.add(Permission.objects.get(codename='review_kycdocument'))
    return User.objects.get(pk=user.pk)


class VerificationBase(TeamTestBase):
    def setUp(self):
        super().setUp()
        for org_type, types in {
            'ENTREPRISE': (RCCM, IDN, REP), 'ORGANISATEUR_EVENEMENTS': (RCCM, IDN, REP),
            'BOUTIQUE': (IDN, REP), 'ONG': (ARRETE, IDN, REP),
        }.items():
            for position, document_type in enumerate(types):
                OrganizationDocumentRequirement.objects.get_or_create(
                    org_type=org_type, document_type=document_type, defaults={'position': position},
                )
        self.client = APIClient()
        self.base = reverse('organization_kyc_documents', args=[self.org.pk])
        self.verification_url = reverse('organization_verification', args=[self.org.pk])

    def post_doc(self, user, document_type=RCCM, content=PNG, org=None):
        self.client.force_authenticate(user)
        url = reverse('organization_kyc_documents', args=[(org or self.org).pk])
        response = self.client.post(url, {'document_type': document_type, 'file': upload(content)}, format='multipart')
        if response.status_code == 201:
            self.addCleanup(self._remove_file, response.data['id'])
        return response

    def _remove_file(self, pk):
        doc = KycDocument.objects.filter(pk=pk).first()
        if doc is not None and doc.file:
            doc.file.delete(save=False)

    def make_doc(self, document_type=RCCM, status=KycDocument.STATUS_EN_ATTENTE, org=None, uploader=None):
        doc = KycDocument.objects.create(
            organization=org or self.org, uploaded_by=uploader or self.owner, document_type=document_type,
            file=upload(), status=status,
        )
        self.addCleanup(self._remove_file, doc.pk)
        return doc

    def decide(self, doc, who, decision='VALIDE', reason=''):
        return services.decide_kyc_document(doc.pk, who, decision, reason)

    def claims(self, org=None):
        org = org or self.org
        return services.get_verified_claims([org.pk])[org.pk]

    def events(self):
        return OutboxEvent.objects.filter(event_type=EVENT).order_by('created_at')


class SubmissionTests(VerificationBase):
    def test_owner_and_admin_deposit_a_private_pending_document_attached_to_the_organization(self):
        for who, document_type in ((self.owner, RCCM), (self.admin, IDN)):
            response = self.post_doc(who, document_type)
            self.assertEqual(response.status_code, 201, response.data)
            doc = KycDocument.objects.get(pk=response.data['id'])
            self.assertEqual((doc.organization_id, doc.uploaded_by_id), (self.org.pk, who.pk))
            self.assertEqual(doc.status, 'EN_ATTENTE')
            path = os.path.abspath(doc.file.path)
            self.assertTrue(path.startswith(os.path.abspath(str(settings.KYC_PRIVATE_ROOT))))
            self.assertFalse(path.startswith(os.path.abspath(str(settings.MEDIA_ROOT))))
            audit = AuditLog.objects.get(action='KYC_SUBMITTED', target_id=doc.pk)
            self.assertEqual((audit.context_type, audit.context_id, audit.actor_id), ('ORGANIZATION', self.org.pk, who.pk))

    def test_response_keys_are_exact_and_never_expose_the_file(self):
        response = self.post_doc(self.owner)
        self.assertEqual(set(response.data), DOC_KEYS)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        dump = json.dumps(response.data, default=str)
        for needle in ('private_media', 'download', '.png', 'file'):
            self.assertNotIn(needle, dump)

    def test_editor_analyst_outsider_and_anonymous_are_refused(self):
        for who, code in ((self.editor, 'DENY_PERMISSION'), (self.analyst, 'DENY_PERMISSION'),
                          (self.outsider, 'DENY_RELATION')):
            response = self.post_doc(who)
            self.assertEqual((response.status_code, response.data['code']), (403, code), who)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.base, {}).status_code, 401)
        self.assertEqual(KycDocument.objects.count(), 0)

    def test_the_header_context_does_not_grant_access_to_another_organization(self):
        other = services.create_organization(self.outsider, 'Autre', 'ENTREPRISE')
        self.client.force_authenticate(self.outsider)
        response = self.client.post(
            self.base, {'document_type': RCCM, 'file': upload()}, format='multipart',
            HTTP_X_CONTEXT=f'ORGANIZATION:{other.pk}',
        )
        self.assertEqual((response.status_code, response.data['code']), (403, 'DENY_RELATION'))

    def test_invalid_inputs(self):
        cases = [
            (dict(document_type=RCCM, content=b'texte brut'), 'file', 'invalid_file_type'),
            (dict(document_type=RCCM, content=b''), 'file', 'invalid_file_type'),
            (dict(document_type='INCONNU'), 'document_type', 'invalid_choice'),
            (dict(document_type=ARRETE), 'document_type', 'document_type_not_required'),
        ]
        for kwargs, field, code in cases:
            response = self.post_doc(self.owner, **kwargs)
            self.assertEqual(response.status_code, 400, kwargs)
            self.assertEqual(response.data[field][0].code, code, kwargs)
        self.client.force_authenticate(self.owner)
        missing = self.client.post(self.base, {'document_type': RCCM}, format='multipart')
        self.assertEqual((missing.status_code, missing.data['file'][0].code), (400, 'required'))
        self.assertEqual(KycDocument.objects.count(), 0)

    @override_settings(KYC_MAX_FILE_BYTES=100)
    def test_file_too_large(self):
        response = self.post_doc(self.owner, content=PNG + b'0' * 200)
        self.assertEqual((response.status_code, response.data['file'][0].code), (400, 'file_too_large'))

    def test_pdf_is_accepted_and_the_stored_name_is_generated(self):
        response = self.post_doc(self.owner, content=PDF)
        self.assertEqual(response.status_code, 201)
        doc = KycDocument.objects.get(pk=response.data['id'])
        self.assertTrue(doc.file.name.endswith('.pdf'))
        self.assertNotIn('piece', doc.file.name)

    def test_requirements_are_read_from_the_database_per_type(self):
        ong = services.create_organization(self.outsider, 'Mon ONG', 'ONG')
        self.assertEqual(self.post_doc(self.outsider, ARRETE, org=ong).status_code, 201)
        self.assertEqual(self.post_doc(self.outsider, RCCM, org=ong).status_code, 400)
        OrganizationDocumentRequirement.objects.create(org_type='ONG', document_type=RCCM, position=9)
        self.assertEqual(self.post_doc(self.outsider, RCCM, org=ong).status_code, 201)

    def test_pending_or_refused_document_is_replaced_and_its_file_removed(self):
        first = self.post_doc(self.owner)
        old_path = KycDocument.objects.get(pk=first.data['id']).file.path
        with self.captureOnCommitCallbacks(execute=True):
            second = self.post_doc(self.admin)
        self.assertEqual(second.status_code, 201)
        self.assertFalse(KycDocument.objects.filter(pk=first.data['id']).exists())
        self.assertFalse(os.path.exists(old_path))
        self.assertEqual(self.org.kyc_documents.filter(document_type=RCCM).count(), 1)
        self.assertTrue(AuditLog.objects.filter(action='KYC_REPLACED', target_id=first.data['id']).exists())
        self.decide(KycDocument.objects.get(pk=second.data['id']), reviewer(), 'REFUSE', 'Illisible')
        self.assertEqual(self.post_doc(self.owner).status_code, 201)
        self.assertEqual(self.org.kyc_documents.filter(document_type=RCCM).count(), 1)

    def test_validated_document_cannot_be_replaced(self):
        self.decide(self.make_doc(), reviewer())
        response = self.post_doc(self.owner)
        self.assertEqual((response.status_code, response.data['code']), (409, 'document_already_validated'))

    def test_suspended_and_archived_organizations_refuse_deposit(self):
        staff = self.staff_user()
        services.suspend_organization(staff, self.org.pk, 'moderation')
        self.assertEqual(self.post_doc(self.owner).data['code'], 'DENY_SECURITY')
        services.reactivate_organization(staff, self.org.pk)
        services.archive_organization(self.owner, self.org.pk)
        self.assertEqual(self.post_doc(self.owner).data['code'], 'DENY_OBJECT_STATE')

    def test_restricted_account_cannot_deposit(self):
        Sanction.objects.create(user=self.owner, sanction_type='SUSPENSION_TEMPORAIRE', reason='x')
        self.assertEqual(self.post_doc(self.owner).data['code'], 'DENY_SECURITY')

    def test_deposit_survives_the_departure_of_its_uploader(self):
        doc = self.make_doc(uploader=self.admin)
        services.leave_organization(self.admin, self.org.pk)
        doc.refresh_from_db()
        self.assertEqual(doc.organization_id, self.org.pk)
        self.decide(doc, reviewer())
        self.assertEqual([c['code'] for c in self.claims()], ['RCCM_VERIFIED'])


class ListAndDeleteTests(VerificationBase):
    def test_every_role_lists_own_organization_documents_paginated_without_urls(self):
        for document_type in (RCCM, IDN, REP):
            self.make_doc(document_type=document_type)
        other = services.create_organization(self.outsider, 'Autre', 'ENTREPRISE')
        self.make_doc(org=other, uploader=self.outsider)
        for who in (self.owner, self.admin, self.editor, self.analyst):
            self.client.force_authenticate(who)
            response = self.client.get(self.base)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['count'], 3)
            self.assertEqual(set(response.data['results'][0]), DOC_KEYS)
            self.assertNotIn('private_media', json.dumps(response.data, default=str))

    def test_non_member_and_unknown_organization_get_the_same_refusal(self):
        self.client.force_authenticate(self.outsider)
        a = self.client.get(self.base)
        b = self.client.get(reverse('organization_kyc_documents', args=[uuid.uuid4()]))
        self.assertEqual((a.status_code, a.data['code']), (403, 'DENY_RELATION'))
        self.assertEqual((b.status_code, b.data['code'], b.data['detail']), (403, 'DENY_RELATION', a.data['detail']))
        self.assertEqual(self.client.get(self.verification_url).status_code, 403)

    def test_former_member_loses_access(self):
        services.revoke_member(self.owner, self.org.pk, self.editor.pk)
        self.client.force_authenticate(self.editor)
        self.assertEqual(self.client.get(self.base).data['code'], 'DENY_RELATION')

    def test_delete_pending_removes_the_file_and_audits(self):
        doc = self.make_doc()
        path = doc.file.path
        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(reverse('organization_kyc_document_delete', args=[self.org.pk, doc.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(KycDocument.objects.filter(pk=doc.pk).exists())
        self.assertFalse(os.path.exists(path))
        audit = AuditLog.objects.get(action='KYC_DELETED', target_id=doc.pk)
        self.assertEqual((audit.context_type, audit.context_id), ('ORGANIZATION', self.org.pk))

    def test_delete_validated_is_a_conflict(self):
        doc = self.make_doc()
        self.decide(doc, reviewer())
        self.client.force_authenticate(self.owner)
        response = self.client.delete(reverse('organization_kyc_document_delete', args=[self.org.pk, doc.pk]))
        self.assertEqual((response.status_code, response.data['code']), (409, 'document_validated'))
        self.assertTrue(KycDocument.objects.filter(pk=doc.pk).exists())

    def test_delete_refused_for_editor_analyst_outsider_and_foreign_document(self):
        doc = self.make_doc()
        url = reverse('organization_kyc_document_delete', args=[self.org.pk, doc.pk])
        for who, code in ((self.editor, 'DENY_PERMISSION'), (self.analyst, 'DENY_PERMISSION'),
                          (self.outsider, 'DENY_RELATION')):
            self.client.force_authenticate(who)
            self.assertEqual(self.client.delete(url).data['code'], code)
        other = services.create_organization(self.outsider, 'Autre', 'ENTREPRISE')
        foreign = self.make_doc(org=other, uploader=self.outsider)
        self.client.force_authenticate(self.owner)
        response = self.client.delete(reverse('organization_kyc_document_delete', args=[self.org.pk, foreign.pk]))
        self.assertEqual((response.status_code, response.data['code']), (404, 'document_not_found'))
        self.assertTrue(KycDocument.objects.filter(pk=doc.pk).exists())
        self.assertTrue(KycDocument.objects.filter(pk=foreign.pk).exists())


class ClaimsTests(VerificationBase):
    def validate_all(self, org=None, types=(RCCM, IDN, REP), uploader=None):
        who = reviewer(f'rev{uuid.uuid4().hex[:6]}')
        for document_type in types:
            self.decide(self.make_doc(document_type, org=org, uploader=uploader), who)

    def summary(self, org=None):
        org = org or self.org
        return services.get_verification_summaries([org.pk])[org.pk]

    def test_no_document_means_no_claim_and_no_summary_label(self):
        self.assertEqual(self.summary(), {'verified_claims': [], 'summary': {'complete': False, 'label': None}})

    def test_partial_validation_gives_precise_claims_and_no_global_label(self):
        self.decide(self.make_doc(RCCM), reviewer())
        self.make_doc(IDN)  # en attente : aucun claim
        data = self.summary()
        self.assertEqual([(c['code'], c['label']) for c in data['verified_claims']], [('RCCM_VERIFIED', 'RCCM vérifié')])
        self.assertIsNotNone(data['verified_claims'][0]['verified_at'])
        self.assertEqual(data['summary'], {'complete': False, 'label': None})

    def test_complete_validation_gives_the_global_label_with_all_its_components(self):
        self.validate_all()
        data = self.summary()
        self.assertEqual(
            [c['label'] for c in data['verified_claims']],
            ["RCCM vérifié", "Identification nationale vérifiée", "Représentant vérifié"],
        )
        self.assertEqual(data['summary'], {'complete': True, 'label': 'Organisation vérifiée'})

    def test_requirements_are_configurable_and_empty_requirements_never_complete(self):
        OrganizationDocumentRequirement.objects.filter(org_type='ENTREPRISE', document_type__in=[IDN, REP]).delete()
        self.decide(self.make_doc(RCCM), reviewer())
        self.assertTrue(self.summary()['summary']['complete'])
        OrganizationDocumentRequirement.objects.filter(org_type='ENTREPRISE').delete()
        data = self.summary()
        self.assertFalse(data['summary']['complete'])
        self.assertEqual(data['verified_claims'], [])  # hors exigences courantes : non affiché

    def test_ong_needs_its_decree(self):
        ong = services.create_organization(self.outsider, 'Mon ONG', 'ONG')
        self.validate_all(ong, (IDN, REP), uploader=self.outsider)
        self.assertFalse(self.summary(ong)['summary']['complete'])
        self.decide(self.make_doc(ARRETE, org=ong, uploader=self.outsider), reviewer('rev2'))
        data = self.summary(ong)
        self.assertTrue(data['summary']['complete'])
        self.assertEqual(data['verified_claims'][0]['code'], 'NGO_DECREE_VERIFIED')

    def test_revocation_withdraws_the_claim_and_the_global_label(self):
        self.validate_all()
        doc = self.org.kyc_documents.get(document_type=RCCM)
        self.decide(doc, reviewer('revoker'), 'REFUSE', 'Document périmé')
        data = self.summary()
        self.assertEqual(len(data['verified_claims']), 2)
        self.assertFalse(data['summary']['complete'])
        self.assertTrue(AuditLog.objects.filter(action='KYC_REVOKED', target_id=doc.pk).exists())

    def test_batch_read_uses_three_queries_and_keeps_organizations_apart(self):
        other = services.create_organization(self.outsider, 'Autre', 'BOUTIQUE')
        self.validate_all(other, (IDN, REP), uploader=self.outsider)
        self.decide(self.make_doc(RCCM), reviewer('revb'))
        with self.assertNumQueries(3):
            result = services.get_verification_summaries([self.org.pk, other.pk])
        self.assertEqual(len(result[self.org.pk]['verified_claims']), 1)
        self.assertTrue(result[other.pk]['summary']['complete'])
        self.assertEqual(services.get_verification_summaries([]), {})
        unknown = uuid.uuid4()
        self.assertFalse(services.get_verification_summaries([unknown])[unknown]['summary']['complete'])

    def test_nothing_is_stored_and_no_commercial_input_exists(self):
        fields = {f.name for f in Organization._meta.get_fields()}
        self.assertFalse({f for f in fields if 'verif' in f or 'claim' in f})
        forbidden = {'plan', 'price', 'entitlement', 'subscription', 'tier'}
        for func in (services.get_verified_claims, services.get_verification_summaries, services.submit_kyb_document,
                     services.delete_kyb_document, services.decide_kyc_document, services.list_kyb_documents,
                     services.get_organization_verification):
            self.assertFalse(forbidden & set(inspect.signature(func).parameters), func.__name__)

    def test_team_changes_do_not_alter_claims(self):
        self.validate_all()
        before = self.claims()
        newcomer = make_user('newcomer')
        services.add_member(self.owner, self.org.pk, newcomer.pk, ADMIN)
        services.change_member_role(self.owner, self.org.pk, newcomer.pk, ANALYST)
        services.revoke_member(self.owner, self.org.pk, newcomer.pk)
        self.assertEqual(self.claims(), before)

    def test_verification_endpoint(self):
        self.decide(self.make_doc(RCCM), reviewer())
        self.make_doc(IDN, status='REFUSE')
        KycDocument.objects.filter(document_type=IDN).update(rejection_reason='Flou')
        for who in (self.owner, self.analyst):
            self.client.force_authenticate(who)
            response = self.client.get(self.verification_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.data), {'verified_claims', 'summary', 'requirements'})
            states = {r['document_type']: r['status'] for r in response.data['requirements']}
            self.assertEqual(states, {RCCM: 'VALIDE', IDN: 'REFUSE', REP: 'MANQUANTE'})
            self.assertEqual(response.data['requirements'][1]['rejection_reason'], 'Flou')
            self.assertEqual(response.data['summary'], {'complete': False, 'label': None})
            self.assertNotIn('private_media', json.dumps(response.data, default=str))
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.verification_url).status_code, 403)


class DecisionTests(VerificationBase):
    def test_decision_is_audited_with_context_and_publishes_the_event(self):
        who = reviewer()
        doc = self.make_doc()
        self.decide(doc, who)
        audit = AuditLog.objects.get(action='KYC_VALIDE', target_id=doc.pk)
        self.assertEqual((audit.context_type, audit.context_id, audit.actor_id), ('ORGANIZATION', self.org.pk, who.pk))
        self.assertEqual(self.events().get().payload, {
            'organization_id': str(self.org.pk), 'document_type': RCCM, 'decision': 'VALIDE',
        })
        self.decide(doc, who, 'REFUSE', 'Périmé')
        self.decide(self.make_doc(IDN), who, 'REFUSE', 'Illisible')
        self.assertEqual([e.payload['decision'] for e in self.events()], ['VALIDE', 'REVOKED', 'REFUSE'])

    def test_audit_details_and_event_carry_no_personal_data(self):
        self.decide(self.make_doc(), reviewer())
        blob = ' '.join(AuditLog.objects.values_list('details', flat=True))
        blob += json.dumps([e.payload for e in OutboxEvent.objects.all()])
        for needle in (self.owner.email, self.owner.full_name, self.org.name):
            self.assertNotIn(needle, blob)

    def test_invalid_or_repeated_decisions_change_nothing(self):
        who = reviewer()
        doc = self.make_doc()
        for args in (('PEUT_ETRE', ''), ('REFUSE', '')):
            with self.assertRaises(services.KycError) as caught:
                services.decide_kyc_document(doc.pk, who, *args)
            self.assertEqual(caught.exception.status_code, 400)
        self.decide(doc, who, 'REFUSE', 'Non')
        with self.assertRaises(services.KycError) as caught:
            self.decide(doc, who)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.events().count(), 1)

    def test_current_member_former_member_uploader_and_creator_cannot_decide(self):
        self.assertEqual(self.org.created_by_id, self.owner.pk)
        doc = self.make_doc(uploader=self.admin)
        services.revoke_member(self.owner, self.org.pk, self.editor.pk)  # ancien membre
        perm = Permission.objects.get(codename='review_kycdocument')
        for person in (self.owner, self.admin, self.editor, self.analyst):
            person.user_permissions.add(perm)
            with self.assertRaises(services.KycError) as caught:
                self.decide(doc, User.objects.get(pk=person.pk))
            self.assertEqual(caught.exception.status_code, 403, person)
        # Auteur du dépôt et créateur sans aucune ligne d'appartenance : refus par les deux autres règles.
        Membership.objects.filter(user__in=[self.admin, self.owner]).delete()
        for person in (self.admin, self.owner):
            with self.assertRaises(services.KycError) as caught:
                self.decide(doc, User.objects.get(pk=person.pk))
            self.assertEqual(caught.exception.status_code, 403, person)
        self.assertEqual(KycDocument.objects.get(pk=doc.pk).status, 'EN_ATTENTE')
        self.assertEqual(self.events().count(), 0)
        self.decide(doc, reviewer('stranger'))
        self.assertEqual(KycDocument.objects.get(pk=doc.pk).status, 'VALIDE')

    def test_former_member_cannot_decide_through_the_endpoint_and_gets_an_explicit_message(self):
        doc = self.make_doc()
        services.revoke_member(self.owner, self.org.pk, self.editor.pk)
        self.editor.is_staff = True
        self.editor.save()
        self.editor.user_permissions.add(Permission.objects.get(codename='review_kycdocument'))
        self.client.force_authenticate(User.objects.get(pk=self.editor.pk))
        response = self.client.post(reverse('kyc_decision', args=[doc.pk]), {'decision': 'VALIDE'})
        self.assertEqual(response.status_code, 403)
        self.assertIn('membre', response.data['error'])
        self.assertEqual(KycDocument.objects.get(pk=doc.pk).status, 'EN_ATTENTE')

    def test_members_without_the_permission_cannot_use_the_staff_endpoints(self):
        doc = self.make_doc()
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(reverse('kyc_decision', args=[doc.pk]), {'decision': 'VALIDE'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('kyc_download', args=[doc.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('kyc_review_queue')).status_code, 403)

    def test_review_queue_shows_the_organization_and_no_member_data(self):
        doc = self.make_doc()
        self.client.force_authenticate(reviewer())
        response = self.client.get(reverse('kyc_review_queue'))
        self.assertEqual(response.status_code, 200)
        item = next(i for i in response.data if str(i['id']) == str(doc.pk))
        self.assertEqual(item['organization'], {'id': str(self.org.pk), 'name': self.org.name, 'org_type': 'ENTREPRISE'})
        dump = json.dumps(response.data, default=str)
        for needle in (self.owner.email, self.owner.full_name, self.admin.email):
            self.assertNotIn(needle, dump)

    def test_decision_endpoint_and_download_by_a_reviewer_are_audited(self):
        doc = self.make_doc()
        who = reviewer()
        self.client.force_authenticate(who)
        response = self.client.post(reverse('kyc_decision', args=[doc.pk]), {'decision': 'VALIDE'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['organization']['id'], str(self.org.pk))
        download = self.client.get(reverse('kyc_download', args=[doc.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download['Cache-Control'], 'private, no-store')
        download.close()
        audit = AuditLog.objects.get(action='KYC_DOWNLOADED', target_id=doc.pk)
        self.assertEqual((audit.context_type, audit.context_id, audit.actor_id), ('ORGANIZATION', self.org.pk, who.pk))

    def test_required_documents_validated_by_reviewers_complete_the_summary_and_the_owner_cannot_decide(self):
        required = list(OrganizationDocumentRequirement.objects.filter(
            org_type=self.org.org_type,
        ).order_by('position').values_list('document_type', flat=True))
        docs = [self.make_doc(document_type) for document_type in required]
        for number, doc in enumerate(docs):
            self.decide(doc, reviewer(f'legacy{number}'))
        self.assertEqual(len(self.claims()), len(required))
        with self.assertRaises(services.KycError) as caught:
            self.decide(docs[0], self.owner, 'REFUSE', 'x')
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(self.events().count(), len(required))


class AdminTests(VerificationBase):
    def staff_with(self, *codenames, label='adm'):
        user = make_user(label, is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        return User.objects.get(pk=user.pk)

    def test_organization_documents_are_hidden_from_staff_without_the_review_permission(self):
        doc = self.make_doc()
        self.client = self.client_class()
        self.client.force_login(self.staff_with('view_kycdocument'))
        listing = self.client.get(reverse('admin:identity_kycdocument_changelist'))
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn(str(doc.pk).encode(), listing.content)
        self.assertNotIn(self.org.name.encode(), listing.content)
        detail = self.client.get(reverse('admin:identity_kycdocument_change', args=[doc.pk]))
        self.assertIn(detail.status_code, (302, 403, 404))
        self.assertFalse(AuditLog.objects.filter(action='KYC_ADMIN_VIEWED').exists())

    def test_reviewer_sees_the_document_without_file_or_member_contacts_and_each_view_is_audited(self):
        doc = self.make_doc(uploader=self.admin)
        staff = self.staff_with('view_kycdocument', 'review_kycdocument', label='adm2')
        self.client = self.client_class()
        self.client.force_login(staff)
        url = reverse('admin:identity_kycdocument_change', args=[doc.pk])
        for expected in (1, 2):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(AuditLog.objects.filter(action='KYC_ADMIN_VIEWED', target_id=doc.pk).count(), expected)
        for needle in (b'private_media', b'name="file"', self.admin.email.encode(), self.owner.email.encode()):
            self.assertNotIn(needle, response.content)
        audit = AuditLog.objects.filter(action='KYC_ADMIN_VIEWED').first()
        self.assertEqual((audit.context_type, audit.context_id, audit.actor_id), ('ORGANIZATION', self.org.pk, staff.pk))
        listing = self.client.get(reverse('admin:identity_kycdocument_changelist'))
        self.assertIn(self.org.name.encode(), listing.content)

    def test_admin_stays_read_only_for_organization_documents(self):
        doc = self.make_doc()
        staff = self.staff_with('view_kycdocument', 'review_kycdocument', 'change_kycdocument', 'delete_kycdocument',
                                label='adm3')
        self.client = self.client_class()
        self.client.force_login(staff)
        self.client.post(reverse('admin:identity_kycdocument_change', args=[doc.pk]), {'status': 'VALIDE'})
        self.client.post(reverse('admin:identity_kycdocument_delete', args=[doc.pk]), {'post': 'yes'})
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'EN_ATTENTE')
        self.assertEqual(self.claims(), [])


class EventCatalogTests(VerificationBase):
    def test_event_is_declared_with_an_emitter_and_no_pending_flag(self):
        spec = catalog.EVENT_TYPES[EVENT]
        self.assertFalse(spec.emitter_pending)
        # T6 : l'abonné `notifications.notify_kyb_decision` remplace le drapeau `no_subscriber`.
        self.assertFalse(spec.no_subscriber)
