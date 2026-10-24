"""Lectures par lot des contextes (ADR 0006, T6) : droits (`get_capable_contexts` == `can`), destinataires d'une
organisation quel que soit son état, noms, libellés, requêtes constantes."""
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.moderation.models import Sanction

from . import capabilities, services
from .models import Membership, Organization, ProviderProfile, User
from .tests_organizations import EDITOR, OWNER, TeamTestBase


class CapableContextsTests(TeamTestBase):
    def test_batch_equals_can_for_every_capability_user_and_context(self):
        other = Organization.objects.create(name='Autre', org_type='ONG', status='SUSPENDED')
        Membership.objects.create(organization=other, user=self.owner, role=OWNER)
        profile = ProviderProfile.objects.create(user=self.editor, display_name='Prestataire')
        archived = ProviderProfile.objects.create(user=self.outsider, display_name='Archivé', status='ARCHIVED')
        contexts = [
            ('ORGANIZATION', self.org.pk), ('ORGANIZATION', other.pk), ('PROVIDER', profile.pk),
            ('PROVIDER', archived.pk), ('USER', self.owner.pk), ('USER', self.outsider.pk),
        ]
        for capability in capabilities.CAPABILITIES:
            for user in (self.owner, self.admin, self.editor, self.analyst, self.outsider):
                batch = services.get_capable_contexts(user.pk, capability)
                for context_type, context_id in contexts:
                    with self.subTest(capability=capability, user=user.email, context=context_type):
                        self.assertEqual(
                            (context_type, context_id) in batch,
                            services.can(user.pk, context_type, context_id, capability),
                        )

    def test_revoked_deactivated_and_sanctioned_accounts_have_no_context_right(self):
        Membership.objects.filter(user=self.editor).update(status='REVOKED')
        self.assertNotIn(('ORGANIZATION', self.org.pk), services.get_capable_contexts(self.editor.pk, 'review.reply'))
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        self.assertEqual(services.get_capable_contexts(self.admin.pk, 'review.reply'), set())
        Sanction.objects.create(user=self.owner, sanction_type='BANNISSEMENT', reason='x')
        self.assertEqual(services.get_capable_contexts(self.owner.pk, 'review.reply'), set())

    def test_analyst_lacks_review_reply_and_unknown_capability_is_a_programming_error(self):
        self.assertEqual(
            ('ORGANIZATION', self.org.pk) in services.get_capable_contexts(self.analyst.pk, 'review.reply'), False,
        )
        with self.assertRaises(capabilities.UnknownCapability):
            services.get_capable_contexts(self.owner.pk, 'review.inconnue')
        self.assertEqual(services.get_capable_contexts('pas-un-uuid', 'review.reply'), set())

    def test_query_count_is_constant(self):
        for index in range(8):
            org = Organization.objects.create(name=f'O{index}', org_type='ONG')
            Membership.objects.create(organization=org, user=self.editor, role=EDITOR)
        with CaptureQueriesContext(connection) as many:
            services.get_capable_contexts(self.editor.pk, 'review.reply')
        with CaptureQueriesContext(connection) as few:
            services.get_capable_contexts(self.outsider.pk, 'review.reply')
        self.assertLessEqual(len(many), 4)
        self.assertEqual(len(many), len(few))


class RecipientsTests(TeamTestBase):
    def test_managers_of_an_organization_in_any_status(self):
        for org_status in ('ACTIVE', 'SUSPENDED', 'ARCHIVED'):
            Organization.objects.filter(pk=self.org.pk).update(status=org_status)
            with self.subTest(status=org_status):
                self.assertEqual(
                    set(services.get_organization_recipients(self.org.pk, 'org.manage_members')),
                    {self.owner.pk, self.admin.pk},
                )
        self.assertEqual(
            set(services.get_organization_recipients(self.org.pk, 'org.verification_submit')),
            {self.owner.pk, self.admin.pk},
        )

    def test_revoked_and_deactivated_members_are_excluded_and_empty_is_an_empty_list(self):
        Membership.objects.filter(user=self.admin).update(status='REVOKED')
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assertEqual(services.get_organization_recipients(self.org.pk, 'org.manage_members'), [])
        self.assertEqual(services.get_organization_recipients('pas-un-uuid', 'org.manage_members'), [])

    def test_active_organization_ids_ignore_status_and_revoked_memberships(self):
        Organization.objects.filter(pk=self.org.pk).update(status='SUSPENDED')
        self.assertEqual(services.get_active_organization_ids(self.editor.pk), {self.org.pk})
        Membership.objects.filter(user=self.editor).update(status='REVOKED')
        self.assertEqual(services.get_active_organization_ids(self.editor.pk), set())
        self.assertEqual(services.get_active_organization_ids(self.outsider.pk), set())


class NamesAndLabelsTests(TeamTestBase):
    def test_context_names_by_lot_without_personal_names(self):
        profile = ProviderProfile.objects.create(user=self.outsider, display_name='Marie couture')
        names = services.get_context_names([
            ('ORGANIZATION', self.org.pk), ('PROVIDER', profile.pk), ('USER', self.owner.pk), ('ORGANIZATION', 'x'),
        ])
        self.assertEqual(names, {('ORGANIZATION', self.org.pk): 'Atelier Test', ('PROVIDER', profile.pk): 'Marie couture'})
        with CaptureQueriesContext(connection) as captured:
            services.get_context_names([('ORGANIZATION', self.org.pk), ('PROVIDER', profile.pk)])
        self.assertEqual(len(captured), 2)

    def test_labels_are_french_and_fall_back_to_the_code(self):
        self.assertEqual(services.get_role_label('EDITOR'), 'Éditeur')
        self.assertEqual(services.get_role_label('INCONNU'), 'INCONNU')
        self.assertEqual(services.get_document_type_label('RCCM'), 'RCCM')
        self.assertEqual(services.get_document_type_label('ARRETE_ONG'), "Arrêté d'enregistrement de l'ONG")
        self.assertEqual(services.get_role_label(None), '')
