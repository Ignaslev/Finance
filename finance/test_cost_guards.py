import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from finance.models import AiRun, Category, MoneySource, PdfImportJob, Transaction, UploadAttempt, UserProfile
from finance.utils import ensure_default_categories


@override_settings(ALLOWED_HOSTS=["testserver"])
@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
class CostGuardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="c@example.test", email="c@example.test", password="StrongPass123!")
        ensure_default_categories(self.user, language="lt")
        self.account = MoneySource.objects.create(user=self.user, name="Main", type="bank")
        self.client.force_login(self.user)

    def _pdf(self, content=b"%PDF-1.4 same statement"):
        return self.client.post(reverse("upload"), {
            "file": SimpleUploadedFile("year.pdf", content, content_type="application/pdf"),
            "import_src": self.account.pk, "next": reverse("overview"),
        })

    @patch("finance.views.pdf_import.start_pdf_read", return_value=("resp_1", "gpt-test"))
    def test_same_pdf_is_never_read_twice(self, start):
        self._pdf()
        PdfImportJob.objects.update(status=PdfImportJob.STATUS_IMPORTED)

        response = self._pdf()

        self.assertEqual(start.call_count, 1)
        self.assertRedirects(response, reverse("overview"), fetch_redirect_response=False)
        self.assertEqual(UploadAttempt.objects.filter(outcome="nothing_new").count(), 1)

    @patch("finance.views.pdf_import.start_pdf_read", return_value=("resp_1", "gpt-test"))
    def test_same_pdf_while_still_reading_returns_to_that_job(self, start):
        self._pdf()
        job = PdfImportJob.objects.get()

        response = self._pdf()

        self.assertEqual(start.call_count, 1)
        self.assertRedirects(response, reverse("pdf_import_status", args=[job.pk]), fetch_redirect_response=False)

    @patch("finance.views.pdf_import.start_pdf_read", return_value=("resp_2", "gpt-test"))
    def test_a_different_pdf_is_read(self, start):
        self._pdf(b"%PDF-1.4 statement A")
        PdfImportJob.objects.update(status=PdfImportJob.STATUS_IMPORTED)
        self._pdf(b"%PDF-1.4 statement B")
        self.assertEqual(start.call_count, 2)

    def test_automatic_runs_skip_rows_the_ai_already_looked_at(self):
        food = Category.objects.get(user=self.user, name="Maisto prekės")
        Transaction.objects.create(user=self.user, money_source=self.account, date=date(2026, 10, 1), merchant="New shop",
                                   amount=Decimal("5"), in_out="out", fingerprint="new")
        Transaction.objects.create(user=self.user, money_source=self.account, date=date(2026, 10, 2), merchant="Unclear",
                                   amount=Decimal("5"), in_out="out", fingerprint="parked", ai_suggested_fk=food)
        AiRun.objects.create(user=self.user, kind="autocategorize", mode="new", status="queued")
        sent = []

        def fake(user, rows, examples, cats, exclude_ids=()):
            sent.extend(r["merchant"] for r in rows)
            return {}

        with patch("finance.views.ai._call_openai_rows", side_effect=fake):
            call_command("moneycoach_ai_autocategorize")

        self.assertEqual(sent, ["New shop"])

    def test_big_manual_run_goes_to_the_background(self):
        Transaction.objects.bulk_create([
            Transaction(user=self.user, money_source=self.account, date=date(2026, 10, 1), merchant=f"Shop {i}",
                        amount=Decimal("1"), in_out="out", fingerprint=f"big-{i}")
            for i in range(81)
        ])
        with patch("finance.views.ai._call_openai_rows") as call:
            response = self.client.post(reverse("ai_run_uncategorized"))

        call.assert_not_called()
        self.assertRedirects(response, reverse("upload"), fetch_redirect_response=False)
        self.assertTrue(AiRun.objects.filter(user=self.user, status="queued", mode="uncat").exists())

    def test_reminders_can_be_switched_back_on_in_profile(self):
        UserProfile.objects.update_or_create(user=self.user, defaults={"reminder_emails": False})

        self.client.post(reverse("profile"), {"action": "pref_tax", "reminder_emails": "1"})

        self.assertTrue(UserProfile.objects.get(user=self.user).reminder_emails)
        self.assertContains(self.client.get(reverse("profile")), 'name="reminder_emails"')
