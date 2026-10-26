import json
import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from finance import services
from finance.models import AiRun, Category, Transaction
from finance.utils import ensure_default_categories

REVOLUT_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-10-02 12:01:10,2026-10-03 09:12:00,Maxima,-23.45,0.00,EUR,COMPLETED,476.55\n"
    "CARD_PAYMENT,Current,2026-10-04 12:01:10,2026-10-05 09:12:00,Bolt,-7.80,0.00,EUR,COMPLETED,468.75\n"
)


def fake_categorizer(category_by_merchant, confidence=0.95):
    """Stand-in for services._call_openai_rows that answers from a lookup table."""
    def _call(user, rows, examples, cats):
        return {
            r["id"]: {"category": category_by_merchant.get(r["merchant"], cats[0]), "confidence": confidence, "reason": "test"}
            for r in rows
        }
    return _call


@override_settings(ALLOWED_HOSTS=["testserver"])
class AutoCategorizeWithoutLabelsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ai-user@example.test", email="ai-user@example.test", password="StrongPass123!",
        )
        ensure_default_categories(self.user, language="lt")
        self.client.force_login(self.user)

    def _tx(self, merchant, **kwargs):
        return Transaction.objects.create(
            user=self.user, date=kwargs.pop("day", date(2026, 10, 1)), merchant=merchant,
            amount=Decimal(kwargs.pop("amount", "10.00")), in_out=kwargs.pop("in_out", "out"),
            fingerprint=f"fp-{merchant}-{Transaction.objects.count()}", **kwargs,
        )

    def test_first_upload_queues_ai_without_any_hand_labels(self):
        upload = SimpleUploadedFile("revolut.csv", REVOLUT_CSV.encode("utf-8"), content_type="text/csv")

        self.client.post(reverse("upload"), {"file": upload, "bank": "auto"})

        self.assertEqual(Transaction.objects.filter(user=self.user, category_source="user").count(), 0)
        self.assertEqual(list(AiRun.objects.filter(user=self.user).values_list("status", flat=True)), ["queued"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_job_executes_the_queued_run_in_place_and_counts_applied_rows(self):
        self._tx("Maxima")
        self._tx("Bolt")
        AiRun.objects.create(user=self.user, kind="autocategorize", mode="uncat", status="queued")

        with patch("finance.views.ai._call_openai_rows",
                   fake_categorizer({"Maxima": "Maisto prekės", "Bolt": "Transportas"})):
            call_command("moneycoach_ai_autocategorize")

        runs = list(AiRun.objects.filter(user=self.user))
        self.assertEqual(len(runs), 1)  # the queued run itself was executed, not a duplicate
        self.assertEqual(runs[0].status, "done")
        self.assertEqual(runs[0].applied, 2)
        names = dict(Transaction.objects.filter(user=self.user).values_list("merchant", "category_fk__name"))
        self.assertEqual(names, {"Maxima": "Maisto prekės", "Bolt": "Transportas"})

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_parked_rows_are_not_resent_on_every_cycle(self):
        groceries = Category.objects.get(user=self.user, name="Maisto prekės")
        self._tx("Unclear shop", ai_suggested_fk=groceries, ai_confidence=0.4)

        with patch("finance.views.ai._call_openai_rows") as call:
            call_command("moneycoach_ai_autocategorize")

        call.assert_not_called()
        self.assertFalse(AiRun.objects.filter(user=self.user).exists())


class CategorizerPromptTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="prompt@example.test", email="prompt@example.test", password="StrongPass123!",
        )
        ensure_default_categories(self.user, language="lt")
        self.home = Category.objects.get(user=self.user, name="Komunaliniai")
        self.shopping = Category.objects.get(user=self.user, name="Pirkiniai")

    def test_merchant_history_puts_user_corrections_first(self):
        for i, (cat, src) in enumerate([(self.shopping, "ai"), (self.shopping, "ai"), (self.home, "user")]):
            Transaction.objects.create(
                user=self.user, date=date(2026, 9, 1 + i), merchant="SENUKAI", amount=Decimal("10"),
                in_out="out", category_fk=cat, category_source=src, fingerprint=f"hist-{i}",
            )

        history = services._merchant_history(self.user, [{"merchant": "Senukai"}])

        kind, past = history["Senukai"]
        self.assertEqual(kind, "same")
        self.assertEqual(past[0], ("Komunaliniai", "user", 1))
        self.assertEqual(past[1], ("Pirkiniai", "ai", 2))

    def test_bank_style_descriptions_match_across_dates_and_cards(self):
        Transaction.objects.create(
            user=self.user, date=date(2026, 9, 3), merchant="PIRKINYS 4769******1234 2026.09.03 MAXIMA X, VILNIUS",
            amount=Decimal("10"), in_out="out", category_fk=self.home, category_source="user", fingerprint="sw-1",
        )
        rows = [
            {"merchant": "PIRKINYS 4769******9876 2026.10.17 MAXIMA X, VILNIUS"},  # same store, new date and card
            {"merchant": "PIRKINYS 4769******1234 2026.10.18 MAXIMA XX, KAUNAS"},  # same brand, other store
        ]

        history = services._merchant_history(self.user, rows)

        self.assertEqual(history[rows[0]["merchant"]][0], "same")
        self.assertEqual(history[rows[1]["merchant"]][0], "similar")

    def test_merchant_key_keeps_bolt_rides_and_bolt_food_apart(self):
        self.assertNotEqual(services._merchant_key("BOLT.EU/O/2510111")[0], services._merchant_key("Bolt Food")[0])
        self.assertEqual(services._merchant_key("UAB Telia Lietuva")[0], "TELIA")

    @override_settings(OPENAI_CATEGORIZE_MODEL="gpt-test-model", OPENAI_CATEGORIZE_REASONING_EFFORT="low")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_request_uses_configured_model_guides_and_user_history(self):
        Transaction.objects.create(
            user=self.user, date=date(2026, 9, 1), merchant="Senukai", amount=Decimal("10"), in_out="out",
            category_fk=self.home, category_source="user", fingerprint="hist-user",
        )
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            content = json.dumps({"results": [{"id": 1, "category": "Komunaliniai", "confidence": 1.4, "reason": "x"}]})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
        cats = sorted(Category.objects.filter(user=self.user).values_list("name", flat=True))
        rows = [{"id": 1, "merchant": "Senukai", "text": "Senukai |  | ", "amount": 31.0, "in_out": "out"}]

        with patch("finance.services.OpenAI", return_value=fake_client):
            result = services._call_openai_rows(self.user, rows, [], cats)

        self.assertEqual(captured["model"], "gpt-test-model")
        self.assertEqual(captured["reasoning_effort"], "low")
        self.assertNotIn("temperature", captured)
        self.assertTrue(captured["response_format"]["json_schema"]["strict"])
        prompt = captured["messages"][1]["content"]
        self.assertIn("Sportas ir sveikata: gyms and sport, pharmacies", prompt)
        self.assertIn("Komunaliniai (set by user, 1x)", prompt)
        self.assertEqual(result[1]["category"], "Komunaliniai")
        self.assertEqual(result[1]["confidence"], 1.0)  # clamped
