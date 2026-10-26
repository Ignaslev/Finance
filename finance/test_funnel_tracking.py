import os
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance.funnel import ai_correction_rate, signup_funnel
from finance.models import AiRun, AiRunItem, Category, MoneySource, Transaction, UploadAttempt
from finance.utils import ensure_default_categories

REVOLUT_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-10-02 12:01:10,2026-10-03 09:12:00,Maxima,-23.45,0.00,EUR,COMPLETED,476.55\n"
)
CONSENT = {"moneycompass_analytics_consent": "accepted"}


@override_settings(ALLOWED_HOSTS=["testserver"])
class UploadTrackingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="t@example.test", email="t@example.test", password="StrongPass123!")
        self.client.force_login(self.user)

    def _post(self, name, content, **extra):
        f = SimpleUploadedFile(name, content, content_type="text/csv")
        return self.client.post(reverse("upload"), {"file": f, "bank": "auto", **extra})

    def test_successful_first_upload_is_tracked_and_queues_ga_events(self):
        self._post("revolut.csv", REVOLUT_CSV.encode(), next=reverse("overview"))

        attempt = UploadAttempt.objects.get(user=self.user)
        self.assertEqual((attempt.outcome, attempt.file_type, attempt.bank, attempt.source, attempt.rows_added),
                         ("imported", "csv", "revolut", "first_run", 1))
        names = [e["name"] for e in self.client.session["ga_pending_events"]]
        self.assertEqual(names, ["first_statement_imported", "statement_imported"])

    def test_unrecognised_file_is_tracked_as_a_failure(self):
        self._post("luminor.csv", b"A;B\n1;2\n")

        attempt = UploadAttempt.objects.get(user=self.user)
        self.assertEqual((attempt.outcome, attempt.source), ("unrecognised", "upload_page"))
        self.assertEqual(self.client.session["ga_pending_events"][0]["params"]["reason"], "unrecognised")

    def test_ga_events_are_sent_only_with_analytics_consent(self):
        self._post("revolut.csv", REVOLUT_CSV.encode())

        without = self.client.get(reverse("overview"))
        self.assertNotContains(without, "mc-ga-upload-events")
        self.assertIn("ga_pending_events", self.client.session)  # still waiting

        self.client.cookies.load(CONSENT)
        with_consent = self.client.get(reverse("overview"))
        self.assertContains(with_consent, 'id="mc-ga-upload-events"')
        self.assertContains(with_consent, "statement_imported")
        self.assertNotIn("ga_pending_events", self.client.session)  # sent once


@override_settings(ALLOWED_HOSTS=["testserver"])
class FunnelPageTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(username="s@example.test", email="s@example.test", password="StrongPass123!", is_staff=True)
        self.admin = User.objects.create_superuser(username="root@example.test", email="root@example.test", password="StrongPass123!")
        self.u1 = User.objects.create_user(username="a@example.test", email="a@example.test", password="StrongPass123!")
        self.u2 = User.objects.create_user(username="b@example.test", email="b@example.test", password="StrongPass123!", is_active=False)
        self.u1.last_login = timezone.now()
        self.u1.last_active_at = timezone.now() + timedelta(days=2)
        self.u1.save()
        acc = MoneySource.objects.create(user=self.u1, name="Main", type="bank")
        Transaction.objects.create(user=self.u1, money_source=acc, date=date(2026, 10, 1), merchant="Rimi",
                                   amount=Decimal("5"), in_out="out", fingerprint="f1")
        UploadAttempt.objects.create(user=self.u1, outcome="imported", file_type="csv", rows_added=1)

    def test_funnel_counts_each_step(self):
        steps = {s["key"]: s["count"] for s in signup_funnel(timezone.now() - timedelta(days=30))}

        self.assertEqual(steps["registered"], 4)
        self.assertEqual(steps["activated"], 3)
        self.assertEqual(steps["logged_in"], 1)
        self.assertEqual(steps["tried_upload"], 1)
        self.assertEqual(steps["has_data"], 1)
        self.assertEqual(steps["returned"], 1)

    def test_page_and_menu_link_are_admin_only(self):
        self.assertEqual(self.client.get(reverse("staff_funnel")).status_code, 302)  # logged out -> login

        for user in (self.u1, self.staff):  # regular user and staff without admin rights
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("staff_funnel")).status_code, 404)
            self.assertNotContains(self.client.get(reverse("overview")), reverse("staff_funnel"))

        self.client.force_login(self.admin)
        response = self.client.get(reverse("staff_funnel"), {"days": 7})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bandė įkelti išrašą")
        self.assertContains(self.client.get(reverse("overview")), reverse("staff_funnel"))

    def test_ai_correction_rate(self):
        ensure_default_categories(self.u1, language="lt")
        food = Category.objects.get(user=self.u1, name="Maisto prekės")
        shop = Category.objects.get(user=self.u1, name="Pirkiniai")
        run = AiRun.objects.create(user=self.u1, kind="autocategorize", status="done")
        acc = MoneySource.objects.get(user=self.u1)
        kept = Transaction.objects.create(user=self.u1, money_source=acc, date=date(2026, 10, 2), merchant="Maxima",
                                          amount=Decimal("9"), in_out="out", category_fk=food, category_source="ai", fingerprint="k")
        fixed = Transaction.objects.create(user=self.u1, money_source=acc, date=date(2026, 10, 3), merchant="Drogas",
                                           amount=Decimal("9"), in_out="out", category_fk=shop, category_source="user", fingerprint="x")
        AiRunItem.objects.create(run=run, transaction=kept, new_category_fk=food, action="applied")
        AiRunItem.objects.create(run=run, transaction=fixed, new_category_fk=food, action="applied")

        rate = ai_correction_rate(timezone.now() - timedelta(days=1))

        self.assertEqual((rate["applied"], rate["corrected"], rate["correction_rate"]), (2, 1, 50.0))
        self.assertEqual(rate["top_corrections"][0]["transaction__category_fk__name"], "Pirkiniai")


@override_settings(ALLOWED_HOSTS=["testserver"], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailUploadLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="m@example.test", email="m@example.test", password="StrongPass123!")
        self.client.force_login(self.user)

    def test_sends_one_link_per_twelve_hours(self):
        self.client.post(reverse("email_upload_link"))
        self.client.post(reverse("email_upload_link"))

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["m@example.test"])
        self.assertIn("/overview/", mail.outbox[0].body)

    def test_first_run_screen_offers_the_link(self):
        self.assertContains(self.client.get(reverse("overview")), reverse("email_upload_link"))

    def test_requires_post(self):
        self.assertEqual(self.client.get(reverse("email_upload_link")).status_code, 405)


@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
class AiEvalCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="e@example.test", email="e@example.test", password="StrongPass123!")
        ensure_default_categories(self.user, language="lt")
        food = Category.objects.get(user=self.user, name="Maisto prekės")
        self.txs = [
            Transaction.objects.create(user=self.user, date=timezone.localdate(), merchant=m, amount=Decimal("5"),
                                       in_out="out", category_fk=food, category_source="user", fingerprint=f"e{i}")
            for i, m in enumerate(["Rimi", "Maxima"])
        ]

    def test_dry_run_does_not_call_the_api(self):
        out = StringIO()
        with patch("finance.management.commands.moneycoach_ai_eval._call_openai_rows") as call:
            call_command("moneycoach_ai_eval", stdout=out)
        call.assert_not_called()
        self.assertIn("Dry run", out.getvalue())

    def test_scores_answers_and_hides_each_rows_own_label(self):
        def fake(user, rows, examples, cats, exclude_ids=()):
            fake.excluded = set(exclude_ids)
            return {r["id"]: {"category": "Maisto prekės" if r["merchant"] == "Rimi" else "Kita"} for r in rows}

        out = StringIO()
        with patch("finance.management.commands.moneycoach_ai_eval._call_openai_rows", side_effect=fake):
            call_command("moneycoach_ai_eval", "--yes", stdout=out)

        self.assertIn("Accuracy: 1/2 = 50.0%", out.getvalue())
        self.assertIn("Maisto prekės -> Kita: 1", out.getvalue())
        self.assertEqual(fake.excluded, {t.id for t in self.txs})
