"""Libellé « Administrateur principal » du rôle `OWNER` (L1-01-B5, ADR 0010 §2.1 K1 ; contrat d'API L1-01 §7.1).

Le code technique `OWNER` et les codes d'erreur (`last_owner`, `last_effective_owner`, `owner_must_be_demoted`,
`last_owner_account`) ne changent pas ; seuls les textes exposés changent. Le mot « propriétaire » ne doit plus
apparaître dans aucun texte exposé à l'utilisateur par `identity` ni `notifications` : messages d'erreur et de
validation, libellés de rôle, notifications, administration Django, descriptions OpenAPI."""
import ast
import json
import re
from pathlib import Path

from django.test import TestCase
from drf_spectacular.generators import SchemaGenerator

from apps.notifications.models import Notification
from apps.platform_core.testing import dispatch_outbox_now

from . import capabilities, services
from .models import Membership, Organization, OrganizationInvitation, User

PRIMARY_ADMIN = 'Administrateur principal'
FORBIDDEN = re.compile(r'propri[ée]taire', re.IGNORECASE)
APPS_DIR = Path(__file__).resolve().parent.parent
SCANNED_APPS = ('identity', 'notifications')


def make_user(label):
    return User.objects.create_user(
        email=f'{label}@example.com', password='x', full_name=f'Nom {label}', phone_verified=True,
    )


def _docstring_nodes(tree):
    """Nœuds de docstring (module, classes, fonctions) : texte de développeur, hors périmètre du balayage des
    littéraux (les docstrings des vues exposées par OpenAPI sont vérifiées par le schéma)."""
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            value = getattr(first, 'value', None)
            if isinstance(first, ast.Expr) and isinstance(value, ast.Constant) and isinstance(value.value, str):
                nodes.add(id(value))
    return nodes


def _exposed_literals():
    """Littéraux de chaîne (hors docstrings, y compris les morceaux de f-strings) des modules de production."""
    for app in SCANNED_APPS:
        for path in sorted((APPS_DIR / app).rglob('*.py')):
            parts = path.relative_to(APPS_DIR / app).parts
            if parts[0] in ('migrations', '__pycache__') or path.name.startswith('tests') or path.name == 'testing.py':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            docstrings = _docstring_nodes(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                    yield f'{app}/{"/".join(parts)}:{node.lineno}', node.value


class RoleLabelTests(TestCase):
    def test_owner_code_is_unchanged_and_labelled_primary_administrator(self):
        self.assertEqual(capabilities.ROLE_OWNER, 'OWNER')
        self.assertEqual(dict(capabilities.ROLE_CHOICES)['OWNER'], PRIMARY_ADMIN)
        self.assertEqual(services.get_role_label('OWNER'), PRIMARY_ADMIN)
        self.assertEqual(services.get_role_label('ADMIN'), 'Administrateur')

    def test_model_choices_and_display_use_the_new_label(self):
        for model in (Membership, OrganizationInvitation):
            self.assertEqual(dict(model._meta.get_field('role').choices)['OWNER'], PRIMARY_ADMIN)
        org = Organization.objects.create(name='Atelier Libellés', org_type='ENTREPRISE')
        membership = Membership.objects.create(organization=org, user=make_user('libelle'), role='OWNER')
        self.assertEqual(membership.get_role_display(), PRIMARY_ADMIN)


class ExposedTextTests(TestCase):
    def test_no_exposed_literal_mentions_proprietaire(self):
        offenders = [f'{where}: {text!r}' for where, text in _exposed_literals() if FORBIDDEN.search(text)]
        self.assertEqual(offenders, [])

    def test_openapi_descriptions_of_identity_and_notifications_do_not_mention_proprietaire(self):
        paths = SchemaGenerator().get_schema(request=None, public=True)['paths']
        scanned = {
            path: item for path, item in paths.items()
            if path.startswith('/api/v1/accounts/') or 'notifications' in path
        }
        self.assertTrue(any('organizations' in path for path in scanned))
        offenders = [
            path for path, item in scanned.items() if FORBIDDEN.search(json.dumps(item, ensure_ascii=False))
        ]
        self.assertEqual(offenders, [])


class ErrorMessageTests(TestCase):
    """Les codes d'erreur ne changent pas ; leur `detail` emploie « administrateur principal »."""

    def setUp(self):
        self.org = Organization.objects.create(name='Atelier Messages', org_type='ENTREPRISE')
        self.owner = make_user('seul-admin-principal')
        self.owner_membership = Membership.objects.create(organization=self.org, user=self.owner, role='OWNER')

    def assertMessage(self, exc, code):
        self.assertEqual(exc.detail.code, code)
        self.assertIn('administrateur principal', str(exc.detail))
        self.assertIsNone(FORBIDDEN.search(str(exc.detail)))

    def test_last_owner_on_leave(self):
        with self.assertRaises(services.OrganizationError) as ctx:
            services.leave_organization(self.owner, self.org.pk)
        self.assertMessage(ctx.exception, 'last_owner')

    def test_last_owner_on_suspended_organization(self):
        Organization.objects.filter(pk=self.org.pk).update(status=Organization.STATUS_SUSPENDED)
        with self.assertRaises(services.OrganizationError) as ctx:
            services.leave_organization(self.owner, self.org.pk)
        self.assertMessage(ctx.exception, 'last_owner')

    def test_owner_must_be_demoted(self):
        other = make_user('second-admin-principal')
        membership = Membership.objects.create(organization=self.org, user=other, role='OWNER')
        with self.assertRaises(services.OrganizationError) as ctx:
            services.remove_member(self.owner, self.org.pk, membership.pk)
        self.assertMessage(ctx.exception, 'owner_must_be_demoted')

    def test_last_owner_account(self):
        with self.assertRaises(services.OrganizationError) as ctx:
            services.assert_account_removable(self.owner)
        self.assertMessage(ctx.exception, 'last_owner_account')


class NotificationLabelTests(TestCase):
    def test_promotion_notification_names_the_role_primary_administrator(self):
        org = Organization.objects.create(name='Atelier Notifications', org_type='ENTREPRISE')
        owner, editor = make_user('notif-owner'), make_user('notif-editor')
        Membership.objects.create(organization=org, user=owner, role='OWNER')
        Membership.objects.create(organization=org, user=editor, role='EDITOR')
        services.change_member_role(owner, org.pk, editor.pk, 'OWNER')
        dispatch_outbox_now()
        notification = Notification.objects.get(user=editor, title='Votre rôle a changé')
        self.assertIn(PRIMARY_ADMIN, notification.content)
        self.assertIsNone(FORBIDDEN.search(notification.content))
