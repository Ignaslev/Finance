from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance import insights, reminders
from finance.management.commands.moneycoach_reports import Command as ReportsCommand
from finance.models import Category, MoneySource, Transaction, UserProfile
from finance.sample_data import add_sample_data

NBSP = " "
NOV_5 = timezone.make_aware(datetime(2026, 11, 5, 10, 0))  # October is only half uploaded by then


@override_settings(ALLOWED_HOSTS=["testserver"], SITE_URL="https://moneycompass.lt")
class InsightsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="i@example.test", email="i@example.test",
                                                         password="StrongPass123!")
        self.user.date_joined = timezone.make_aware(datetime(2026, 1, 1))
        self.user.save()
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.preferred_language = "lt"
        self.profile.save()
        self.acc = MoneySource.objects.create(user=self.user, name="Main", type="bank")
        self.groceries = Category.objects.create(user=self.user, name="Maisto prekės")
        self.dining = Category.objects.create(user=self.user, name="Kavinės")
        # August and September are fully uploaded, October only up to the 14th.
        self._tx(date(2026, 8, 1), "300", self.groceries)
        self._tx(date(2026, 8, 15), "2000", flow="in", merchant="Darbdavys")
        self._tx(date(2026, 8, 31), "100", self.dining)
        self._tx(date(2026, 9, 1), "240", self.groceries)
        self._tx(date(2026, 9, 15), "2000", flow="in", merchant="Darbdavys")
        self._tx(date(2026, 9, 30), "160", self.dining)
        for day in range(5, 12):
            self._tx(date(2026, 9, day), "4", self.dining, merchant="CAFFEINE ROASTERS")
        self._tx(date(2026, 10, 2), "50", self.groceries)
        self._tx(date(2026, 10, 14), "20", self.dining)

    def _tx(self, day, amount, category=None, flow="out", merchant="Rimi"):
        n = Transaction.objects.filter(user=self.user).count()
        return Transaction.objects.create(
            user=self.user, money_source=self.acc, date=day, merchant=merchant, amount=Decimal(amount),
            in_out=flow, category_fk=category, category=category.name if category else None, fingerprint=f"fp-{n}",
        )

    def test_money_formats_per_language(self):
        self.assertEqual(insights.money(Decimal("1240.4"), True), f"1{NBSP}240{NBSP}€")
        self.assertEqual(insights.money(Decimal("1240.5"), False), "€1,241")

    def test_last_complete_month_skips_a_half_uploaded_month(self):
        self.assertEqual(insights.last_complete_month(self.user, NOV_5.date()), (date(2026, 9, 1), date(2026, 9, 30)))

    def test_monthly_summary_compares_with_previous_month_and_gives_tips(self):
        s = insights.monthly_summary(self.user, date(2026, 9, 1), lt=True)

        self.assertEqual(s["spent"], Decimal("428"))
        self.assertEqual(s["change_pct"], 7)
        self.assertEqual(s["biggest_move"]["name"], "Kavinės")
        self.assertEqual(s["biggest_move"]["change"], Decimal("88"))
        self.assertEqual(insights.headline(s, True),
                         f"Rugsėjo mėnesį išleidai 428{NBSP}€ – 7{NBSP}% daugiau nei rugpjūčio mėnesį.")
        self.assertEqual(len(s["tips"]), 3)
        self.assertTrue(any("CAFFEINE ROASTERS: 7 kartai" in t for t in s["tips"]))
        self.assertTrue(any(t.startswith("Liko 1") for t in s["tips"]))

    def test_partial_month_is_never_compared(self):
        s = insights.monthly_summary(self.user, date(2026, 10, 1), lt=True)

        self.assertFalse(s["complete"])
        self.assertIsNone(s["change_pct"])
        self.assertIsNone(s["biggest_move"])
        self.assertEqual(insights.headline(s, True), f"Spalio mėnesį išleidai 70{NBSP}€.")

    def test_reminder_with_half_uploaded_month_recaps_the_last_full_one(self):
        subject, text, _ = reminders.build_email(self.profile, "monthly", NOV_5)

        self.assertEqual(subject, "Laikas įkelti spalio mėnesio išrašą")
        self.assertIn(f"Rugsėjo mėnesį išleidai 428{NBSP}€ – 7{NBSP}% daugiau nei rugpjūčio mėnesį.", text)
        self.assertIn(f"Labiausiai pasikeitė „Kavinės“: +88{NBSP}€ (+88{NBSP}%).", text)
        self.assertIn("https://moneycompass.lt/reports/?m=2026-09", text)
        self.assertIn("Spalio mėnuo baigėsi", text)

    def test_reminder_when_last_month_is_uploaded_is_the_overview_itself(self):
        subject, text, _ = reminders.build_email(self.profile, "monthly", NOV_5.replace(month=10))

        self.assertEqual(subject, f"Rugsėjo mėnesį išleidai 428{NBSP}€ – 7{NBSP}% daugiau nei rugpjūčio mėnesį")
        self.assertIn("Visą apžvalgą ir patarimus rasi čia:", text)
        self.assertNotIn("išrašą (PDF arba CSV)", text)

    def test_reminder_in_english(self):
        self.profile.preferred_language = "en"
        self.profile.save()
        subject, text, _ = reminders.build_email(self.profile, "monthly", NOV_5)

        self.assertEqual(subject, "Time to upload your October statement")
        self.assertIn("You spent €428 in September – 7% more than in August.", text)

    def test_reminder_without_a_full_month_is_the_plain_one(self):
        Transaction.objects.filter(user=self.user, date__lt=date(2026, 10, 1)).delete()
        _, text, _ = reminders.build_email(self.profile, "monthly", NOV_5)

        self.assertNotIn("išleidai", text)
        self.assertIn("Spalio mėnuo baigėsi", text)

    def test_sample_data_never_reaches_the_email(self):
        Transaction.objects.filter(user=self.user).delete()
        add_sample_data(self.user)
        self.assertIsNone(reminders._recap(self.profile, timezone.localtime(), True))

    def test_reports_page_shows_overview_and_tips_to_everyone(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("reports") + "?m=2026-09")

        self.assertContains(page, "Rugsėjo mėnesį išleidai")
        self.assertContains(page, "CAFFEINE ROASTERS: 7 kartai")
        self.assertContains(page, 'id="week-overview"')

    def test_reports_page_shows_sample_data(self):
        Transaction.objects.filter(user=self.user).delete()
        add_sample_data(self.user)
        self.client.force_login(self.user)
        page = self.client.get(reverse("reports"))

        self.assertContains(page, "mėnesį išleidai")

    def test_ai_reports_cron_skips_periods_without_data(self):
        self.user.is_staff = True
        self.user.save()
        with patch("finance.management.commands.moneycoach_reports._advisor_call_model", return_value={}) as call:
            ReportsCommand()._run_batch("weekly", date(2026, 7, 6), date(2026, 7, 12))
        call.assert_not_called()

    def test_ai_reports_are_staff_only(self):
        with patch("finance.management.commands.moneycoach_reports._advisor_call_model", return_value={}) as call:
            ReportsCommand()._run_batch("monthly", date(2026, 9, 1), date(2026, 9, 30))
        call.assert_not_called()

        self.user.is_staff = True
        self.user.save()
        with patch("finance.management.commands.moneycoach_reports._advisor_call_model", return_value={}) as call:
            ReportsCommand()._run_batch("monthly", date(2026, 9, 1), date(2026, 9, 30))
        call.assert_called_once()

    def test_non_staff_cannot_trigger_a_paid_report(self):
        self.client.force_login(self.user)
        with patch("finance.views.reports._advisor_call_model", return_value={}) as call:
            self.client.post(reverse("reports_generate"), {"type": "monthly", "start": "2026-09-01"})
        call.assert_not_called()
