import json
import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from finance.models import Category, MoneySource, Transaction
from finance.utils import ensure_default_categories


@override_settings(ALLOWED_HOSTS=["testserver"])
class CategoryCashFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="cashflow@example.test",
            email="cashflow@example.test",
            password="StrongPass123!",
            first_name="Test",
            last_name="User",
        )
        self.source = MoneySource.objects.create(
            user=self.user,
            name="Main account",
            type="bank",
            is_active=True,
            manual_balance=Decimal("3000.00"),
        )
        self.activity = Category.objects.create(user=self.user, name="Individual activity")
        self.client.force_login(self.user)

    def _transaction(self, *, amount, in_out, merchant, fingerprint, is_transfer=False):
        return Transaction.objects.create(
            user=self.user,
            money_source=self.source,
            date=date(2026, 7, 15),
            merchant=merchant,
            amount=Decimal(amount),
            currency="EUR",
            in_out=in_out,
            category=self.activity.name,
            category_fk=self.activity,
            category_source="user",
            is_internal_transfer=is_transfer,
            fingerprint=fingerprint,
        )

    def test_tools_compares_both_directions_and_excludes_transfers(self):
        self._transaction(
            amount="1000.00",
            in_out=Transaction.IN,
            merchant="Customer payment",
            fingerprint="activity-income",
        )
        self._transaction(
            amount="400.00",
            in_out=Transaction.OUT,
            merchant="Materials",
            fingerprint="activity-cost",
        )
        self._transaction(
            amount="900.00",
            in_out=Transaction.IN,
            merchant="Own transfer",
            fingerprint="activity-transfer",
            is_transfer=True,
        )

        response = self.client.get(reverse("tools"), {"category": self.activity.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_summary"]["income"], Decimal("1000.00"))
        self.assertEqual(response.context["selected_summary"]["spending"], Decimal("400.00"))
        self.assertEqual(response.context["selected_summary"]["balance"], Decimal("600.00"))
        self.assertEqual(json.loads(response.context["chart_income_json"]), [1000.0])
        self.assertEqual(json.loads(response.context["chart_spending_json"]), [400.0])
        self.assertNotIn("chart_balance_json", response.context)
        self.assertNotContains(response, "type: 'line'")
        self.assertEqual(response.context["runway_months"], 22.5)
        self.assertNotContains(response, "Balance by category")
        self.assertNotContains(response, "Category transactions")
        self.assertNotContains(response, "Customer payment")
        self.assertNotContains(response, "Materials")
        self.assertNotContains(response, "Own transfer")
        self.assertContains(response, 'class="ph ph-magnifying-glass"')
        self.assertNotContains(response, 'class="ph ph-toolbox"')

    def test_runway_custom_view_is_scoped_to_the_users_own_choices(self):
        self._transaction(
            amount="300.00",
            in_out=Transaction.OUT,
            merchant="Operating cost",
            fingerprint="runway-cost",
        )
        other_user = get_user_model().objects.create_user(
            username="runway-other@example.test",
            email="runway-other@example.test",
            password="StrongPass123!",
        )
        other_source = MoneySource.objects.create(
            user=other_user,
            name="Other account",
            type="bank",
            manual_balance=Decimal("999999.00"),
        )

        response = self.client.get(reverse("tools"), {
            "category": self.activity.id,
            "runway_sim": "1",
            "inc_src": [self.source.id, other_source.id],
            "inc_cat": [self.activity.id],
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_simulated"])
        self.assertEqual(response.context["runway_months"], 30.0)
        self.assertNotContains(response, "Other account")

    def test_tools_does_not_accept_another_users_category(self):
        self._transaction(
            amount="200.00",
            in_out=Transaction.IN,
            merchant="Customer",
            fingerprint="own-category-income",
        )
        self._transaction(
            amount="80.00",
            in_out=Transaction.OUT,
            merchant="Supplies",
            fingerprint="own-category-spending",
        )
        other_user = get_user_model().objects.create_user(
            username="other@example.test",
            email="other@example.test",
            password="StrongPass123!",
        )
        other_category = Category.objects.create(user=other_user, name="Private business")

        response = self.client.get(reverse("tools"), {"category": other_category.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_category"], self.activity)
        self.assertNotContains(response, "Private business")

    def test_category_selector_only_includes_categories_with_both_directions(self):
        spending_only = Category.objects.create(user=self.user, name="Spending only")
        self._transaction(
            amount="500.00",
            in_out=Transaction.IN,
            merchant="Customer",
            fingerprint="eligible-income",
        )
        self._transaction(
            amount="120.00",
            in_out=Transaction.OUT,
            merchant="Materials",
            fingerprint="eligible-spending",
        )
        Transaction.objects.create(
            user=self.user,
            money_source=self.source,
            date=date(2026, 7, 15),
            merchant="Expense",
            amount=Decimal("25.00"),
            currency="EUR",
            in_out=Transaction.OUT,
            category=spending_only.name,
            category_fk=spending_only,
            category_source="user",
            fingerprint="spending-only",
        )

        response = self.client.get(reverse("tools"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["categories"]), [self.activity])
        self.assertContains(response, "Individual activity")
        self.assertNotContains(response, '<option value="{}"'.format(spending_only.id))

    def test_transaction_edit_can_mark_and_unmark_internal_transfer(self):
        transaction = self._transaction(
            amount="50.00",
            in_out=Transaction.OUT,
            merchant="Account move",
            fingerprint="editable-transfer",
        )

        response = self.client.post(
            reverse("tx_edit", args=[transaction.id]),
            {
                "category_fk": self.activity.id,
                "is_internal_transfer": "1",
                "user_note": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        transaction.refresh_from_db()
        self.assertTrue(transaction.is_internal_transfer)

        self.client.post(
            reverse("tx_edit", args=[transaction.id]),
            {"category_fk": self.activity.id, "user_note": ""},
        )
        transaction.refresh_from_db()
        self.assertFalse(transaction.is_internal_transfer)

    @patch("finance.views.ai.require_paid_access", return_value=None)
    def test_ai_does_not_force_incoming_transaction_into_one_category(self, _access):
        incoming = Transaction.objects.create(
            user=self.user,
            money_source=self.source,
            date=date(2026, 7, 20),
            merchant="New client",
            amount=Decimal("250.00"),
            currency="EUR",
            in_out=Transaction.IN,
            category_source="import",
            fingerprint="uncategorized-income",
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            response = self.client.post(reverse("ai_full_categorize"))

        self.assertEqual(response.status_code, 200)
        incoming.refresh_from_db()
        self.assertIsNone(incoming.category_fk)
        self.assertEqual(response.context["total_candidates"], 1)

    @patch("finance.views.ai.require_paid_access", return_value=None)
    def test_ai_marks_self_transfer_without_assigning_a_category(self, _access):
        transfer = Transaction.objects.create(
            user=self.user,
            money_source=self.source,
            date=date(2026, 7, 20),
            merchant="Test User",
            amount=Decimal("250.00"),
            currency="EUR",
            in_out=Transaction.IN,
            category_source="import",
            fingerprint="detected-self-transfer",
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            response = self.client.post(reverse("ai_full_categorize"))

        self.assertEqual(response.status_code, 200)
        transfer.refresh_from_db()
        self.assertTrue(transfer.is_internal_transfer)
        self.assertIsNone(transfer.category_fk)
        self.assertEqual(response.context["total_candidates"], 0)


class DefaultCategoryTests(TestCase):
    def test_new_english_user_gets_salary_and_activity_categories(self):
        user = get_user_model().objects.create_user(
            username="defaults-en@example.test",
            email="defaults-en@example.test",
            password="StrongPass123!",
        )
        ensure_default_categories(user, language="en")
        names = set(Category.objects.filter(user=user).values_list("name", flat=True))

        self.assertIn("Salary", names)
        self.assertIn("Individual activity", names)
        self.assertNotIn("Income", names)
        self.assertNotIn("Internal transfer", names)

    def test_new_lithuanian_user_gets_salary_and_activity_categories(self):
        user = get_user_model().objects.create_user(
            username="defaults-lt@example.test",
            email="defaults-lt@example.test",
            password="StrongPass123!",
        )
        ensure_default_categories(user, language="lt")
        names = set(Category.objects.filter(user=user).values_list("name", flat=True))

        self.assertIn("Atlyginimas", names)
        self.assertIn("Individuali veikla", names)
        self.assertNotIn("Pajamos", names)
        self.assertNotIn("Vidinis pavedimas", names)
