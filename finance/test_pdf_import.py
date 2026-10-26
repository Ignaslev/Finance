import json
import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openai import NotFoundError

from finance import pdf_import
from finance.models import AiRun, MoneySource, PdfImportJob, Transaction

STATEMENT = {
    "opening_balance": 100.00,
    "closing_balance": 1135.80,
    "currency": "EUR",
    "rows": [
        {"date": "2026-10-01", "merchant": "CAFFEINE ROASTERS", "description": "PIRKINYS 4769******1234 CAFFEINE ROASTERS", "amount": 4.20, "direction": "out", "currency": "EUR"},
        {"date": "2026-10-01", "merchant": "CAFFEINE ROASTERS", "description": "PIRKINYS 4769******1234 CAFFEINE ROASTERS", "amount": 4.20, "direction": "out", "currency": "EUR"},
        {"date": "2026-10-03", "merchant": "MAXIMA X, VILNIUS", "description": "PIRKINYS MAXIMA X, VILNIUS", "amount": 95.80, "direction": "out", "currency": "EUR"},
        {"date": "2026-10-25", "merchant": "UAB DARBDAVYS", "description": "Atlyginimas", "amount": 1140.00, "direction": "in", "currency": "EUR"},
    ],
}


def fake_client(status="completed", payload=STATEMENT):
    client = MagicMock()
    client.responses.retrieve.return_value = SimpleNamespace(status=status, output_text=json.dumps(payload))
    return client


@override_settings(ALLOWED_HOSTS=["testserver"], PDF_READS_PER_DAY=10)
@patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
class PdfImportFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="pdf@example.test", email="pdf@example.test", password="StrongPass123!")
        self.account = MoneySource.objects.create(user=self.user, name="Luminor", type="bank")
        self.client.force_login(self.user)

    def _job(self, **kwargs):
        defaults = dict(user=self.user, money_source=self.account, filename="luminor.pdf",
                        response_id="resp_1", next_url=reverse("overview"))
        defaults.update(kwargs)
        return PdfImportJob.objects.create(**defaults)

    def _upload_pdf(self):
        pdf = SimpleUploadedFile("luminor.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        return self.client.post(reverse("upload"), {"file": pdf, "import_src": self.account.pk, "next": reverse("overview")})

    @patch("finance.views.pdf_import.start_pdf_read", return_value=("resp_9", "gpt-test"))
    def test_pdf_upload_starts_a_background_read_and_shows_the_wait_page(self, start):
        response = self._upload_pdf()

        job = PdfImportJob.objects.get(user=self.user)
        self.assertRedirects(response, reverse("pdf_import_status", args=[job.pk]), fetch_redirect_response=False)
        self.assertEqual((job.response_id, job.model_name, job.status), ("resp_9", "gpt-test", "reading"))
        self.assertEqual(job.money_source, self.account)
        self.assertFalse(Transaction.objects.filter(user=self.user).exists())  # nothing imported before preview

    @override_settings(PDF_READS_PER_DAY=1)
    @patch("finance.views.pdf_import.start_pdf_read", return_value=("resp_9", "gpt-test"))
    def test_daily_pdf_limit(self, start):
        self._upload_pdf()
        response = self._upload_pdf()

        self.assertEqual(PdfImportJob.objects.filter(user=self.user).count(), 1)
        self.assertEqual(start.call_count, 1)
        self.assertRedirects(response, reverse("overview"), fetch_redirect_response=False)

    def test_other_users_job_is_not_found(self):
        stranger = get_user_model().objects.create_user(username="x@example.test", email="x@example.test", password="StrongPass123!")
        other_account = MoneySource.objects.create(user=stranger, name="Other", type="bank")
        job = PdfImportJob.objects.create(user=stranger, money_source=other_account, response_id="resp_x")

        self.assertEqual(self.client.get(reverse("pdf_import_status", args=[job.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("pdf_import_preview", args=[job.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("pdf_import_preview", args=[job.pk]), {"action": "import"}).status_code, 404)

    def test_poll_stores_rows_once_even_when_polled_twice(self):
        job = self._job()
        client = fake_client()
        with patch("finance.pdf_import._client", return_value=client):
            first = self.client.get(reverse("pdf_import_status", args=[job.pk]), {"format": "json"}).json()
            second = self.client.get(reverse("pdf_import_status", args=[job.pk]), {"format": "json"}).json()

        self.assertEqual(first["status"], "ready")
        self.assertEqual(second["status"], "ready")
        self.assertEqual(client.responses.retrieve.call_count, 1)
        job.refresh_from_db()
        self.assertEqual(len(job.result["rows"]), 4)

    def test_still_reading_and_incomplete_and_expired(self):
        job = self._job()
        with patch("finance.pdf_import._client", return_value=fake_client(status="in_progress")):
            self.assertEqual(pdf_import.refresh_job(job).status, "reading")
        with patch("finance.pdf_import._client", return_value=fake_client(status="incomplete")):
            job = pdf_import.refresh_job(job)
        self.assertEqual((job.status, job.error), ("failed", "incomplete"))

        expired = self._job(response_id="resp_gone")
        gone = MagicMock()
        gone.responses.retrieve.side_effect = NotFoundError(
            "gone", response=httpx.Response(404, request=httpx.Request("GET", "https://api.openai.com")), body=None)
        with patch("finance.pdf_import._client", return_value=gone):
            expired = pdf_import.refresh_job(expired)
        self.assertEqual((expired.status, expired.error), ("failed", "expired"))

    def test_preview_checks_balances_and_counts_identical_rows(self):
        # One of the two identical coffees is already stored: only the second one is new.
        Transaction.objects.create(user=self.user, money_source=self.account, date=date(2026, 10, 1), merchant="Caffeine",
                                   amount=Decimal("4.20"), in_out="out", fingerprint="existing-coffee")
        job = self._job(status="ready", result=STATEMENT)

        preview = pdf_import.build_preview(job)

        self.assertEqual(preview["balance_check"], "ok")
        self.assertEqual((preview["row_count"], preview["new_count"], preview["duplicate_count"]), (4, 3, 1))
        response = self.client.get(reverse("pdf_import_preview", args=[job.pk]))
        self.assertContains(response, "pdf-check ok")

    def test_preview_warns_when_balances_do_not_match(self):
        short = dict(STATEMENT, rows=STATEMENT["rows"][1:])  # one row missing, balances unchanged
        job = self._job(status="ready", result=short)

        preview = pdf_import.build_preview(job)

        self.assertEqual(preview["balance_check"], "mismatch")
        self.assertEqual(preview["difference"], Decimal("4.20"))
        self.assertContains(self.client.get(reverse("pdf_import_preview", args=[job.pk])), "pdf-check mismatch")

    def test_bad_dates_are_unreadable_not_today(self):
        bad = dict(STATEMENT, rows=[dict(STATEMENT["rows"][0], date="03.10.2026")] + STATEMENT["rows"][2:])
        job = self._job(status="ready", result=bad)

        rows, unreadable = pdf_import.parsed_rows(job)

        self.assertEqual(unreadable, 1)
        self.assertEqual(len(rows), 2)

    def test_confirm_imports_rows_queues_ai_and_drops_statement_data(self):
        job = self._job(status="ready", result=STATEMENT)

        response = self.client.post(reverse("pdf_import_preview", args=[job.pk]), {"action": "import"})

        self.assertRedirects(response, reverse("overview"), fetch_redirect_response=False)
        txs = Transaction.objects.filter(user=self.user, money_source=self.account)
        self.assertEqual(txs.count(), 4)  # both identical coffees are real purchases
        self.assertEqual(set(txs.values_list("merchant", flat=True)), {"CAFFEINE ROASTERS", "MAXIMA X, VILNIUS", "UAB DARBDAVYS"})
        self.assertTrue(AiRun.objects.filter(user=self.user, status="queued").exists())
        job.refresh_from_db()
        self.assertEqual(job.status, "imported")
        self.assertIsNone(job.result)

        # Confirming the same job again does nothing.
        self.client.post(reverse("pdf_import_preview", args=[job.pk]), {"action": "import"})
        self.assertEqual(txs.count(), 4)

    def test_cancel_while_reading_stops_the_remote_read(self):
        job = self._job()
        client = fake_client(status="in_progress")
        with patch("finance.pdf_import._client", return_value=client):
            self.client.post(reverse("pdf_import_preview", args=[job.pk]), {"action": "cancel"})

        client.responses.cancel.assert_called_once_with("resp_1")
        job.refresh_from_db()
        self.assertEqual(job.status, "cancelled")
        self.assertIsNone(job.result)
