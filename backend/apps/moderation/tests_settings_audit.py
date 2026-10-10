"""B3 (L0-20) : toute modification d'un réglage du back-office est journalisée, ancienne et nouvelle valeur."""
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.test import RequestFactory, TestCase

from apps.identity.models import User
from apps.marketplace.models import MarketplaceSettings
from apps.moderation.models import AuditLog, ModerationSettings
from apps.reviews.models import ReviewSettings
from apps.visibility.models import RankingSettings, VisibilitySettings

CASES = [
    (ModerationSettings, 'report_processing_target_hours', 99),
    (ReviewSettings, 'min_account_age_hours', 7),
    (ReviewSettings, 'delay_after_contact_hours', 5),
    (RankingSettings, 'weight_views', 3),
    (MarketplaceSettings, 'expiration_days', 45),
    (VisibilitySettings, 'unique_view_retention_days', 15),
]


class SettingsAuditTests(TestCase):
    def test_each_settings_change_is_audited_with_old_and_new_value(self):
        admin = User.objects.create_user(email='a@example.com', password='x', full_name='A', is_staff=True)
        request = RequestFactory().post('/admin/')
        request.user = admin
        for model, field, value in CASES:
            with self.subTest(model=model.__name__, field=field):
                row = model.get_solo()
                old = getattr(row, field)
                setattr(row, field, value)
                form = mock.Mock(changed_data=[field], initial={field: old})
                admin_site._registry[model].save_model(request, row, form, True)
                entry = AuditLog.objects.filter(action='SETTINGS_CHANGED', target_id=row.pk).latest('created_at')
                self.assertEqual(entry.actor, admin)
                self.assertIn(f'{field} : {old!r} -> {value!r}', entry.details)
                self.assertEqual(getattr(model.get_solo(), field), value)
