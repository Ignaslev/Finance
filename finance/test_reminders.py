from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance import reminders
from finance.models import ImportBatch, MoneySource, Transaction, UserProfile

NOW = timezone.make_aware(datetime(2026, 11, 5, 10, 0))  # 5 November: October's statement is due


@override_settings(
    ALLOWED_HOSTS=["testserver"], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="MoneyCompass <labas@moneycompass.lt>", SITE_URL="https://moneycompass.lt",
)
class ReminderTests(TestCase):
    def _user(self, email, language="lt", joined_days_ago=60, with_data=True, active_days_ago=5):
        user = get_user_model().objects.create_user(username=email, email=email, password="StrongPass123!")
        user.date_joined = NOW - timedelta(days=joined_days_ago)
        user.last_active_at = NOW - timedelta(days=active_days_ago)
        user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.preferred_language = language
        profile.save()
        if with_data:
            acc = MoneySource.objects.create(user=user, name="Main", type="bank")
            Transaction.objects.create(user=user, money_source=acc, date=date(2026, 9, 30), merchant="Rimi",
                                       amount=Decimal("5"), in_out="out", fingerprint=f"fp-{email}")
        return user

    def test_monthly_goes_to_users_who_have_not_uploaded_this_month(self):
        self._user("due@example.test")
        uploaded = self._user("uploaded@example.test")
        batch = ImportBatch.objects.create(user=uploaded, money_source=MoneySource.objects.get(user=uploaded))
        ImportBatch.objects.filter(pk=batch.pk).update(created_at=NOW - timedelta(days=1))
        opted_out = self._user("optout@example.test")
        UserProfile.objects.filter(user=opted_out).update(reminder_emails=False)
        self._user("dormant@example.test", active_days_ago=400)
        self._user("nodata@example.test", with_data=False)

        emails = {p.user.email for p in reminders.monthly_due(NOW)}

        self.assertEqual(emails, {"due@example.test"})

    def test_monthly_waits_until_the_third(self):
        self._user("due@example.test")
        self.assertEqual(reminders.monthly_due(NOW.replace(day=2)), [])

    def test_nudge_only_for_recent_signups_without_data(self):
        self._user("fresh@example.test", joined_days_ago=3, with_data=False)
        self._user("brandnew@example.test", joined_days_ago=0, with_data=False)
        self._user("old@example.test", joined_days_ago=40, with_data=False)
        self._user("hasdata@example.test", joined_days_ago=3)

        self.assertEqual({p.user.email for p in reminders.nudge_due(NOW)}, {"fresh@example.test"})

    def test_email_language_and_sender(self):
        lt = UserProfile.objects.get(user=self._user("lt@example.test", language="lt"))
        en = UserProfile.objects.get(user=self._user("en@example.test", language="en"))

        reminders.send_reminder(lt, "monthly", now=NOW)
        reminders.send_reminder(en, "monthly", now=NOW)

        lt_mail, en_mail = mail.outbox
        self.assertEqual(lt_mail.subject, "Laikas įkelti spalio mėnesio išrašą")
        self.assertEqual(en_mail.subject, "Time to upload your October statement")
        self.assertEqual(lt_mail.from_email, "MoneyCompass <labas@moneycompass.lt>")
        self.assertIn("https://moneycompass.lt/overview/", lt_mail.body)
        self.assertIn("Atsisakyk čia: https://moneycompass.lt/reminders/unsubscribe/", lt_mail.body)
        self.assertTrue(lt_mail.extra_headers["List-Unsubscribe"].startswith("<https://moneycompass.lt/reminders/unsubscribe/"))

    def test_unsubscribe_link(self):
        user = self._user("bye@example.test", language="en")
        url = reverse("reminder_unsubscribe", args=[reminders.unsubscribe_token(user)])

        page = self.client.get(url)
        self.assertContains(page, "Stop reminder emails?")
        self.assertTrue(UserProfile.objects.get(user=user).reminder_emails)  # a GET (link preview) changes nothing

        self.client.post(url)  # also how mail clients do one-click unsubscribe
        self.assertFalse(UserProfile.objects.get(user=user).reminder_emails)
        self.assertEqual(self.client.get(reverse("reminder_unsubscribe", args=["tampered"])).status_code, 404)

    def test_command_sends_once_per_month(self):
        self._user("due@example.test")
        self._user("fresh@example.test", joined_days_ago=3, with_data=False)

        with patch("finance.reminders.timezone.now", return_value=NOW):
            dry = StringIO()
            call_command("moneycoach_send_reminders", "--dry-run", stdout=dry)
            self.assertIn("Dry run: 2 emails would be sent.", dry.getvalue())
            self.assertEqual(len(mail.outbox), 0)

            call_command("moneycoach_send_reminders", stdout=StringIO())
            call_command("moneycoach_send_reminders", stdout=StringIO())

        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["due@example.test", "fresh@example.test"])
