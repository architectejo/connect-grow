"""Durcissement de T4 (relecture et audit) : contenu des fichiers, minimisation, nettoyage disque, conflit
d'intérêts au téléchargement, lecture sur organisation inactive, purge planifiée."""
import io
import os
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction
from django.db.models.fields.files import FieldFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.moderation.models import AuditLog

from . import services
from .kyc_files import validate_kyc_file
from .models import IdentitySettings, KycDocument, Organization, OrganizationDocumentRequirement, User
from .tests import JPEG_BYTES, PDF_BYTES, PNG_BYTES
from .tests_verification import IDN, RCCM, REP, VerificationBase, reviewer, upload


class HardeningTests(VerificationBase):
    def test_images_are_reencoded_without_exif_or_gps(self):
        exif = Image.Exif()
        exif[0x010E] = 'SENTINELLE-GPS-ZZ'
        buffer = io.BytesIO()
        Image.new('RGB', (16, 16), (200, 10, 10)).save(buffer, format='JPEG', exif=exif)
        self.assertIn(b'SENTINELLE-GPS-ZZ', buffer.getvalue())
        response = self.post_doc(self.owner, content=buffer.getvalue())
        self.assertEqual(response.status_code, 201, response.data)
        doc = KycDocument.objects.get(pk=response.data['id'])
        with doc.file.open('rb') as handle:
            stored = handle.read()
        self.assertNotIn(b'SENTINELLE-GPS-ZZ', stored)
        self.assertTrue(stored.startswith(b'\xff\xd8\xff'))
        self.assertTrue(doc.file.name.endswith('.jpg'))
        self.assertEqual(Image.open(io.BytesIO(stored)).size, (16, 16))

    def test_png_keeps_its_format_and_pdf_is_stored_unchanged(self):
        png = KycDocument.objects.get(pk=self.post_doc(self.owner, RCCM, PNG_BYTES).data['id'])
        self.assertTrue(png.file.name.endswith('.png'))
        pdf = KycDocument.objects.get(pk=self.post_doc(self.owner, IDN, PDF_BYTES).data['id'])
        with pdf.file.open('rb') as handle:
            self.assertEqual(handle.read(), PDF_BYTES)

    def test_corrupted_images_are_refused(self):
        for content in (PNG_BYTES[:40], b'\x89PNG\r\n\x1a\n' + b'\x00' * 64, JPEG_BYTES[:30],
                        b'\xff\xd8\xff\xe0' + b'\x00' * 64):
            response = self.post_doc(self.owner, content=content)
            self.assertEqual((response.status_code, response.data['file'][0].code), (400, 'invalid_file_type'))
        self.assertEqual(KycDocument.objects.count(), 0)

    @override_settings(PROFILE_IMAGE_MAX_PIXELS=10)
    def test_oversized_pixel_count_is_refused(self):
        response = self.post_doc(self.owner)
        self.assertEqual((response.status_code, response.data['file'][0].code), (400, 'image_too_large'))

    def test_pdf_with_active_content_is_refused_including_escaped_names(self):
        for marker in (b'/JavaScript', b'/JS (alert(1))', b'/Launch', b'/EmbeddedFile', b'/OpenAction', b'/J#61vaScript'):
            response = self.post_doc(self.owner, content=b'%PDF-1.4\n1 0 obj << ' + marker + b' >> endobj\n')
            self.assertEqual(response.status_code, 400, marker)
            self.assertEqual(response.data['file'][0].code, 'pdf_active_content', marker)
        harmless = b'%PDF-1.4\n1 0 obj << /Type /Catalog /JSON 1 >> endobj\n'
        self.assertEqual(self.post_doc(self.owner, content=harmless).status_code, 201)

    def test_legacy_upload_also_gets_the_content_checks(self):
        with self.assertRaises(ValidationError):
            validate_kyc_file(upload(b'%PDF-1.4 /OpenAction'))

    def test_file_is_removed_with_its_row_even_by_cascade(self):
        doc = self.make_doc()
        path = doc.file.path
        with self.captureOnCommitCallbacks(execute=True):
            Organization.objects.filter(pk=self.org.pk).delete()
        self.assertFalse(os.path.exists(path))

    def test_row_rollback_keeps_the_file(self):
        doc = self.make_doc()
        path = doc.file.path
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    doc.delete()
                    raise RuntimeError('retour arrière')
            except RuntimeError:
                pass
        self.assertTrue(os.path.exists(path))

    def test_disk_failure_on_cleanup_never_raises(self):
        doc = self.make_doc()
        with mock.patch.object(FieldFile, 'delete', side_effect=OSError('disque')):
            with self.assertLogs('apps.identity.models', level='ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    doc.delete()
        self.assertFalse(KycDocument.objects.filter(pk=doc.pk).exists())

    def test_error_after_the_file_is_written_removes_the_file(self):
        root = str(settings.KYC_PRIVATE_ROOT)
        before = set(os.listdir(root)) if os.path.isdir(root) else set()
        with mock.patch('apps.identity.verification.record_audit', side_effect=RuntimeError('audit en panne')):
            with self.assertRaises(RuntimeError):
                services.submit_kyb_document(self.owner, self.org.pk, RCCM, upload())
        after = set(os.listdir(root)) if os.path.isdir(root) else set()
        self.assertEqual(after, before)
        self.assertEqual(KycDocument.objects.count(), 0)

    def test_download_conflict_rule_denies_and_audits(self):
        doc = self.make_doc(uploader=self.admin)
        services.revoke_member(self.owner, self.org.pk, self.editor.pk)
        perm = Permission.objects.get(codename='review_kycdocument')
        for person in (self.owner, self.admin, self.editor):
            person.is_staff = True
            person.save()
            person.user_permissions.add(perm)
            self.client.force_authenticate(User.objects.get(pk=person.pk))
            response = self.client.get(reverse('kyc_download', args=[doc.pk]))
            self.assertEqual(response.status_code, 403, person)
            self.assertTrue(
                AuditLog.objects.filter(action='KYC_DOWNLOAD_DENIED', actor=person, target_id=doc.pk).exists()
            )
        self.assertFalse(AuditLog.objects.filter(action='KYC_DOWNLOADED').exists())
        self.client.force_authenticate(reviewer('outsider-rev'))
        ok = self.client.get(reverse('kyc_download', args=[doc.pk]))
        self.assertEqual(ok.status_code, 200)
        ok.close()

    def test_reads_stay_allowed_on_suspended_and_archived_organizations_but_writes_are_refused(self):
        self.make_doc()
        staff = self.staff_user()
        services.suspend_organization(staff, self.org.pk, 'moderation')
        self.client.force_authenticate(self.owner)
        for url in (self.base, self.verification_url):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.post_doc(self.owner, IDN).status_code, 403)
        services.reactivate_organization(staff, self.org.pk)
        services.archive_organization(self.owner, self.org.pk)
        self.client.force_authenticate(self.owner)
        for url in (self.base, self.verification_url):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.post_doc(self.owner, IDN).status_code, 403)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.base).status_code, 403)

    def test_reason_is_bounded_to_500_characters(self):
        doc = self.make_doc()
        with self.assertRaises(services.KycError) as caught:
            self.decide(doc, reviewer(), 'REFUSE', 'x' * 501)
        self.assertEqual(caught.exception.status_code, 400)
        self.decide(doc, reviewer('r2'), 'REFUSE', 'x' * 500)

    def test_document_without_profile_nor_organization_is_a_conflict(self):
        orphan = KycDocument.objects.create(document_type=RCCM, file=upload())
        self.addCleanup(self._remove_file, orphan.pk)
        with self.assertRaises(services.KycError) as caught:
            self.decide(orphan, reviewer())
        self.assertEqual(caught.exception.status_code, 409)

    def test_only_currently_required_types_give_claims(self):
        self.decide(self.make_doc(RCCM), reviewer())
        self.assertEqual(len(self.claims()), 1)
        OrganizationDocumentRequirement.objects.filter(org_type='ENTREPRISE', document_type=RCCM).delete()
        self.assertEqual(self.claims(), [])


class PurgeCommandTests(VerificationBase):
    def run_purge(self, *args):
        call_command('purge_kyb_files', *args, verbosity=0)

    def decided_doc(self, days_ago, status='VALIDE', document_type=RCCM):
        doc = self.make_doc(document_type)
        KycDocument.objects.filter(pk=doc.pk).update(
            status=status, reviewed_at=timezone.now() - timedelta(days=days_ago),
        )
        return KycDocument.objects.get(pk=doc.pk)

    def test_default_is_unlimited_and_purges_nothing(self):
        doc = self.decided_doc(4000)
        self.run_purge()
        self.assertTrue(os.path.exists(doc.file.path))

    def test_purge_removes_only_old_decided_files_keeps_rows_claims_and_audits_each(self):
        IdentitySettings.get_solo()
        IdentitySettings.objects.update(kyb_file_retention_days=30)
        old = self.decided_doc(60, 'VALIDE', RCCM)
        recent = self.decided_doc(5, 'REFUSE', IDN)
        pending = self.make_doc(REP)
        old_path = old.file.path
        self.run_purge('--dry-run')
        self.assertTrue(os.path.exists(old_path))
        self.run_purge()
        self.assertFalse(os.path.exists(old_path))
        old.refresh_from_db()
        self.assertEqual((old.file.name, old.status), ('', 'VALIDE'))
        self.assertTrue(os.path.exists(recent.file.path))
        self.assertTrue(os.path.exists(pending.file.path))
        self.assertEqual([c['code'] for c in self.claims()], ['RCCM_VERIFIED'])
        audit = AuditLog.objects.get(action='KYC_FILE_PURGED')
        self.assertEqual((audit.target_id, audit.context_id), (old.pk, self.org.pk))
        self.run_purge()
        self.assertEqual(AuditLog.objects.filter(action='KYC_FILE_PURGED').count(), 1)
        self.client.force_authenticate(reviewer())
        self.assertEqual(self.client.get(reverse('kyc_download', args=[old.pk])).status_code, 404)
