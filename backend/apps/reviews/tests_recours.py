"""Corrections d'intégration (aller-retour 1) : recours de l'auteur d'un avis signalé « contact fictif »,
verrou limité aux motifs graves, délai de traitement, séries de signalements, admin des signalements,
ancienneté de compte, lots de recalcul et limite de la liste des annonces."""
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle

from apps.identity.models import User
from apps.marketplace import services as marketplace_services
from apps.marketplace.models import ContactEvent, Offer
from apps.moderation.admin import ReportAdmin, ReportAdminForm
from apps.moderation.models import AuditLog, ModerationSettings, Report
from apps.notifications.models import Notification

from . import services
from .models import Review
from .tests_eligibility import LOCMEM, REPORTS_URL, REVIEWS_URL, EligibilityBase


class RecoursBase(EligibilityBase):
    def setUp(self):
        super().setUp()
        call_command('setup_roles', verbosity=0)
        self.review = self.make_review()
        self.moderator = User.objects.create_user(
            email='mod@example.com', password='x', full_name='Modo', is_staff=True,
        )
        self.moderator.groups.add(Group.objects.get(name='Modérateur'))

    def file_report(self, review=None, user=None, reason='CONTACT_FICTIF'):
        self.client.force_authenticate(user or self.seller)
        return self.client.post(REPORTS_URL, {
            'target_type': 'REVIEW', 'object_id': str((review or self.review).id), 'reason': reason,
            'description': "Cette personne ne m'a jamais contacté.",
        }, format='json')

    def decide(self, action, report=None):
        report = report or Report.objects.get(reason='CONTACT_FICTIF')
        self.client.force_authenticate(self.moderator)
        return self.client.post(f'{REPORTS_URL}{report.id}/{action}/', {'notes': 'Vérifié.'}, format='json')

    def respond(self, user, text='Je lui ai bien écrit hier, voici le contexte.', report=None):
        report = report or Report.objects.get(reason='CONTACT_FICTIF')
        self.client.force_authenticate(user)
        return self.client.post(f'{REPORTS_URL}{report.id}/author-response/', {'author_response': text}, format='json')


class AuthorNotificationTests(RecoursBase):
    def notifications(self):
        return list(Notification.objects.filter(user=self.buyer).order_by('created_at'))

    def test_author_is_told_when_the_report_is_filed_without_the_seller_identity(self):
        self.file_report()
        (note,) = self.notifications()
        self.assertEqual(note.title, "Votre avis est contesté")
        self.assertIn("Le vendeur conteste", note.content)
        for secret in ('Vendeur', 'seller@example.com', str(self.seller.pk)):
            self.assertNotIn(secret, note.title + note.content + note.link)
        self.assertFalse(Notification.objects.filter(user=self.seller).exists())

    def test_other_reasons_do_not_notify(self):
        self.file_report(reason='SPAM')
        self.assertEqual(self.notifications(), [])

    def test_upheld_and_rejected_decisions_are_notified(self):
        self.file_report()
        self.decide('resolve')
        self.assertEqual([n.title for n in self.notifications()], ["Votre avis est contesté", "Votre avis a été masqué"])
        other_review = self.make_review(user=self.other)
        self.file_report(review=other_review)
        self.decide('reject', Report.objects.get(target_id=other_review.id))
        self.assertEqual(
            [n.title for n in Notification.objects.filter(user=self.other).order_by('created_at')],
            ["Votre avis est contesté", "Votre avis est maintenu"],
        )
        self.assertIn("reste publié", Notification.objects.filter(user=self.other).latest('created_at').content)


class AuthorResponseTests(RecoursBase):
    def test_author_answers_once_and_the_moderator_sees_it(self):
        self.file_report()
        response = self.respond(self.buyer)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(response.json()['author_responded_at'])
        self.assertNotIn('author_response', response.json())
        entry = AuditLog.objects.get(action='REPORT_AUTHOR_RESPONDED')
        self.assertEqual((entry.actor, entry.target_type), (self.buyer, 'report'))
        self.client.force_authenticate(self.moderator)
        row = self.client.get(REPORTS_URL).data[0]
        self.assertEqual(row['author_response'], 'Je lui ai bien écrit hier, voici le contexte.')
        self.assertIsNotNone(row['author_responded_at'])
        again = self.respond(self.buyer, text='Une seconde réponse.')
        self.assertEqual((again.status_code, again.data['code']), (409, 'already_responded'))
        self.assertEqual(Report.objects.get().author_response, 'Je lui ai bien écrit hier, voici le contexte.')

    def test_only_the_author_can_answer(self):
        self.file_report()
        for user in (self.seller, self.other, self.moderator):
            self.assertEqual(self.respond(user).status_code, 404, user.email)
        self.client.force_authenticate(None)
        anonymous = self.client.post(f'{REPORTS_URL}{Report.objects.get().id}/author-response/', {}, format='json')
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(Report.objects.get().author_response, '')

    def test_other_reasons_have_no_recourse(self):
        self.file_report(reason='SPAM', user=self.other)
        self.assertEqual(self.respond(self.buyer, report=Report.objects.get()).status_code, 404)

    def test_answer_is_validated_and_refused_on_a_closed_report(self):
        self.file_report()
        for text in ('', '   ', 'x' * 1001):
            response = self.respond(self.buyer, text=text)
            self.assertEqual(response.status_code, 400, len(text))
            self.assertIn('author_response', response.data)
        self.assertEqual(self.respond(self.buyer, text='x' * 1000).status_code, 200)
        Report.objects.update(author_response='', author_responded_at=None)
        self.decide('reject')
        closed = self.respond(self.buyer)
        self.assertEqual((closed.status_code, closed.data['code']), (409, 'report_closed'))

    def test_non_text_body_is_a_field_error(self):
        self.file_report()
        self.client.force_authenticate(self.buyer)
        response = self.client.post(
            f'{REPORTS_URL}{Report.objects.get().id}/author-response/', {'author_response': 12}, format='json',
        )
        self.assertEqual(response.status_code, 400)


class LockAndDelayTests(RecoursBase):
    def test_overdue_fictitious_reports_are_counted_on_the_dashboard(self):
        self.file_report()
        self.client.force_authenticate(self.moderator)
        dashboard = '/api/v1/moderation/dashboard/'
        self.assertEqual(self.client.get(dashboard).data['overdue_contact_fictif_count'], 0)
        Report.objects.update(created_at=timezone.now() - timedelta(hours=73))
        self.assertEqual(self.client.get(dashboard).data['overdue_contact_fictif_count'], 1)
        ModerationSettings.objects.filter(pk=ModerationSettings.get_solo().pk).update(report_processing_target_hours=100)
        self.assertEqual(self.client.get(dashboard).data['overdue_contact_fictif_count'], 0)
        ModerationSettings.objects.filter(pk=ModerationSettings.get_solo().pk).update(report_processing_target_hours=72)
        self.decide('reject')  # un signalement clos n'est plus en retard
        self.assertEqual(self.client.get(dashboard).data['overdue_contact_fictif_count'], 0)

    def test_settings_are_bounded(self):
        from django.core.exceptions import ValidationError
        for field, bad in (
            ('report_processing_target_hours', 0), ('report_processing_target_hours', 721),
            ('fictitious_contact_daily_limit', 0), ('fictitious_contact_daily_limit', 201),
        ):
            with self.assertRaises(ValidationError, msg=field):
                ModerationSettings(**{field: bad}).full_clean()
        ModerationSettings().full_clean()

    def test_contact_rejected_follows_the_real_state(self):
        self.file_report()
        self.decide('resolve')
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.eligibility().data['reason'], 'contact_rejected')
        # La modération réaffiche l'avis : la décision est défaite, plus rien n'est « rejeté ».
        services.set_review_hidden(Review.objects.get(pk=self.review.pk), False, self.moderator)
        self.assertEqual(self.eligibility().data['reason'], 'already_reviewed')
        refused = self.client.post(REVIEWS_URL, {'post': str(self.offer.id), 'offer_rating': 4, 'seller_rating': 4,
                                                 'content': 'Un nouvel avis assez long.'}, format='json')
        self.assertEqual((refused.status_code, refused.data['code']), (409, 'already_reviewed'))


class ReportSeriesTests(RecoursBase):
    def test_a_rejected_report_cannot_be_filed_again(self):
        self.file_report()
        self.decide('reject')
        again = self.file_report()
        self.assertEqual((again.status_code, again.data['code']), (409, 'report_already_rejected'))
        self.assertEqual(Report.objects.filter(reason='CONTACT_FICTIF').count(), 1)

    def test_the_rejection_is_audited_with_the_review(self):
        self.file_report()
        self.decide('reject')
        entry = AuditLog.objects.get(action='CONTACT_FICTIF_REJECTED')
        self.assertEqual((entry.target_type, entry.target_id, entry.actor), ('review', self.review.id, self.moderator))

    def test_daily_limit_per_seller_comes_from_the_settings(self):
        ModerationSettings.objects.filter(pk=ModerationSettings.get_solo().pk).update(fictitious_contact_daily_limit=2)
        reviews = [self.review] + [
            self.make_review(user=User.objects.create_user(email=f'x{i}@example.com', password='x', full_name=f'X {i}'))
            for i in range(2)
        ]
        statuses = [self.file_report(review=r).status_code for r in reviews]
        self.assertEqual(statuses, [201, 201, 429])
        refused = self.file_report(review=reviews[2])
        self.assertEqual(refused.data['code'], 'report_daily_limit')
        self.assertTrue(0 < int(refused['Retry-After']) <= 24 * 3600)  # R0-06 : délai jusqu'à minuit
        # Un autre motif n'est pas concerné, et la veille ne compte pas.
        self.assertEqual(self.file_report(review=reviews[2], reason='SPAM', user=self.other).status_code, 201)
        Report.objects.update(created_at=timezone.now() - timedelta(days=1))
        self.assertEqual(self.file_report(review=reviews[2]).status_code, 201)


class ReportAdminTests(RecoursBase):
    def setUp(self):
        super().setUp()
        self.file_report()
        self.report = Report.objects.get()
        self.admin = ReportAdmin(Report, admin_site)
        self.request = RequestFactory().post('/admin/')
        self.request.user = self.moderator

    def form(self, report, status_value):
        return ReportAdminForm(
            data={'status': status_value, 'assigned_to': '', 'decision_notes': 'Vérifié.'}, instance=report,
        )

    def test_the_report_itself_is_read_only_and_cannot_be_added(self):
        readonly = set(self.admin.get_readonly_fields(self.request, self.report))
        self.assertTrue({'reason', 'target_type', 'target_id', 'reporter'} <= readonly)
        self.assertFalse(self.admin.has_add_permission(self.request))
        self.assertEqual(set(ReportAdminForm.base_fields), {'status', 'assigned_to', 'decision_notes'})

    def test_a_closed_report_cannot_be_reopened(self):
        self.report.resolve(notes='fait')
        form = self.form(Report.objects.get(), Report.STATUS_EN_ATTENTE)
        self.assertFalse(form.is_valid())
        self.assertIn('status', form.errors)
        self.assertFalse(self.form(Report.objects.get(), Report.STATUS_REJETE).is_valid())

    def test_saving_a_resolution_applies_the_same_consequences_as_the_api(self):
        form = self.form(Report.objects.get(), Report.STATUS_TRAITE)
        self.assertTrue(form.is_valid(), form.errors)
        self.admin.save_model(self.request, form.instance, form, True)
        report = Report.objects.get()
        self.assertEqual((report.status, report.decision_notes), (Report.STATUS_TRAITE, 'Vérifié.'))
        self.assertIsNotNone(report.resolved_at)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_hidden)
        self.assertTrue(AuditLog.objects.filter(action='REPORT_STATUS_CHANGED').exists())
        self.assertTrue(Notification.objects.filter(user=self.buyer, title="Votre avis a été masqué").exists())

    def test_saving_a_rejection_keeps_the_review_and_audits_it(self):
        form = self.form(Report.objects.get(), Report.STATUS_REJETE)
        self.assertTrue(form.is_valid(), form.errors)
        self.admin.save_model(self.request, form.instance, form, True)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_hidden)
        self.assertTrue(AuditLog.objects.filter(action='CONTACT_FICTIF_REJECTED').exists())

    def test_a_report_closed_meanwhile_is_not_overwritten(self):
        stale = Report.objects.get()
        form = self.form(stale, Report.STATUS_TRAITE)
        self.assertTrue(form.is_valid())
        Report.objects.get().reject(notes='déjà rejeté')
        with mock.patch.object(self.admin, 'message_user') as message:
            self.admin.save_model(self.request, form.instance, form, True)
        message.assert_called_once()
        self.assertEqual(Report.objects.get().status, Report.STATUS_REJETE)
        self.assertEqual(Report.objects.get().decision_notes, 'déjà rejeté')
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_hidden)


class AccountAgeTests(EligibilityBase):
    def make_new_account(self, hours_old):
        User.objects.filter(pk=self.buyer.pk).update(date_joined=timezone.now() - timedelta(hours=hours_old))
        self.buyer.refresh_from_db()

    def test_new_account_cannot_review_until_the_end_of_the_wait(self):
        self.set_settings(min_account_age_hours=24, delay_after_contact_hours=1)
        contact = self.make_contact()
        self.age_contact(contact, hours=10)
        self.make_new_account(hours_old=6)
        self.client.force_authenticate(self.buyer)
        response = self.eligibility()
        self.assertEqual((response.data['reason'], response.data['can_review']), ('account_too_new', False))
        self.assertEqual(response.json()['available_at'], (self.buyer.date_joined + timedelta(hours=24)).isoformat().replace('+00:00', 'Z'))
        refused = self.post_review()
        self.assertEqual((refused.status_code, refused.data['code']), (403, 'account_too_new'))
        self.assertTrue(refused.data['detail'].startswith("Votre compte est trop récent"))
        self.assertFalse(Review.objects.exists())

    def test_the_later_deadline_wins(self):
        self.set_settings(min_account_age_hours=24, delay_after_contact_hours=48)
        self.make_contact()
        self.make_new_account(hours_old=1)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.eligibility().data['reason'], 'too_early')

    def test_old_enough_account_can_review_and_zero_disables_the_rule(self):
        self.set_settings(min_account_age_hours=24, delay_after_contact_hours=1)
        self.age_contact(self.make_contact(), hours=10)
        self.make_new_account(hours_old=25)
        self.client.force_authenticate(self.buyer)
        self.assertTrue(self.eligibility().data['can_review'])
        self.make_new_account(hours_old=0)
        self.set_settings(min_account_age_hours=0)
        self.assertTrue(self.eligibility().data['can_review'])

    def test_no_contact_is_still_reported_first(self):
        self.set_settings(min_account_age_hours=24)
        self.make_new_account(hours_old=0)
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.eligibility().data['reason'], 'no_contact')

    def test_uncounted_contacts_are_no_proof(self):
        contact = self.make_contact()
        self.assertIsNotNone(marketplace_services.get_review_contact(self.offer.id, self.buyer.pk))
        ContactEvent.objects.filter(pk=contact.pk).update(is_counted=False)
        self.assertIsNone(marketplace_services.get_review_contact(self.offer.id, self.buyer.pk))
        self.client.force_authenticate(self.buyer)
        self.assertEqual(self.eligibility().data['reason'], 'no_contact')


class BatchAndThrottleTests(EligibilityBase):
    def test_refresh_all_scores_works_by_batches(self):
        offers = [self.make_offer(self.seller, f'Annonce numéro {i} à recalculer') for i in range(5)]
        Offer.objects.update(visibility_score=0, contacts_count=7)
        with mock.patch.object(marketplace_services, 'REFRESH_BATCH_SIZE', 2):
            count = marketplace_services.refresh_all_scores()
        self.assertEqual(count, 6)  # 5 + l'offre du jeu d'essai
        self.assertEqual(Offer.objects.filter(contacts_count=0).count(), 6)  # recomptés à la source
        self.assertTrue(all(Offer.objects.get(pk=o.pk).visibility_score > 0 for o in offers))

    @override_settings(CACHES=LOCMEM)
    def test_offer_list_is_throttled_but_not_the_detail(self):
        cache.clear()
        with mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {'offer_list': '2/hour'}):
            self.assertEqual(self.client.get('/api/v1/marketplace/posts/').status_code, 200)
            self.assertEqual(self.client.get('/api/v1/marketplace/posts/').status_code, 200)
            third = self.client.get('/api/v1/marketplace/posts/')
            self.assertEqual((third.status_code, third.data['code']), (status.HTTP_429_TOO_MANY_REQUESTS, 'throttled'))
            self.assertEqual(self.client.get(f'/api/v1/marketplace/posts/{self.offer.id}/').status_code, 200)
