import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from finance.models import Category, MoneySource, Transaction


@override_settings(ALLOWED_HOSTS=["testserver"])
class OverviewAnalyticsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="overview-test@example.test",
            email="overview-test@example.test",
            password="StrongPass123!",
        )
        self.source = MoneySource.objects.create(
            user=self.user,
            name="Main account",
            type="bank",
            is_active=True,
        )
        self.income_category = Category.objects.create(user=self.user, name="Income")
        self.groceries_category = Category.objects.create(user=self.user, name="Groceries")
        self.transfer_category = Category.objects.create(user=self.user, name="Internal transfer")
        self.client.force_login(self.user)

    def _transaction(self, *, amount, in_out, category, fingerprint):
        return Transaction.objects.create(
            user=self.user,
            money_source=self.source,
            date=date(2026, 7, 15),
            merchant="Test merchant",
            amount=Decimal(amount),
            currency="EUR",
            in_out=in_out,
            category=category.name,
            category_fk=category,
            category_source="user",
            fingerprint=fingerprint,
        )

    def _monthly_transaction(self, *, year, month, amount, fingerprint):
        return Transaction.objects.create(
            user=self.user,
            money_source=self.source,
            date=date(year, month, 15),
            merchant="Monthly test",
            amount=Decimal(amount),
            currency="EUR",
            in_out=Transaction.IN,
            category=self.income_category.name,
            category_fk=self.income_category,
            category_source="user",
            fingerprint=fingerprint,
        )

    def test_internal_transfers_are_excluded_from_overview_analytics(self):
        self._transaction(
            amount="1000.00",
            in_out=Transaction.IN,
            category=self.income_category,
            fingerprint="income",
        )
        self._transaction(
            amount="200.00",
            in_out=Transaction.OUT,
            category=self.groceries_category,
            fingerprint="groceries",
        )
        self._transaction(
            amount="500.00",
            in_out=Transaction.OUT,
            category=self.transfer_category,
            fingerprint="transfer-out",
        )
        self._transaction(
            amount="500.00",
            in_out=Transaction.IN,
            category=self.transfer_category,
            fingerprint="transfer-in",
        )

        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.context["income_json"]), [1000.0])
        self.assertEqual(json.loads(response.context["spending_json"]), [200.0])
        self.assertEqual(response.context["net_rows"], [{"month": "2026-07", "net": 800.0}])
        self.assertNotIn("Internal transfer", response.context["cat_names"])

    def test_lithuanian_legacy_category_value_is_also_excluded(self):
        transfer = Transaction.objects.create(
            user=self.user,
            money_source=self.source,
            date=date(2026, 7, 15),
            merchant="Transfer",
            amount=Decimal("250.00"),
            currency="EUR",
            in_out=Transaction.OUT,
            category="Vidinis pavedimas",
            category_fk=None,
            category_source="user",
            fingerprint="legacy-lt-transfer",
        )

        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.context["income_json"]), [])
        self.assertEqual(json.loads(response.context["spending_json"]), [])
        transfer.refresh_from_db()
        self.assertFalse(transfer.is_deleted)

    def test_net_by_month_is_newest_first_and_paginated_by_eight(self):
        for month in range(1, 11):
            self._monthly_transaction(
                year=2026,
                month=month,
                amount=str(month),
                fingerprint=f"month-{month}",
            )

        first_page = self.client.get(reverse("overview"))
        second_page = self.client.get(reverse("overview"), {"net_page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.context["net_page"].paginator.per_page, 8)
        self.assertEqual(
            [row["month"] for row in first_page.context["net_page"]],
            ["2026-10", "2026-09", "2026-08", "2026-07", "2026-06", "2026-05", "2026-04", "2026-03"],
        )
        self.assertEqual(
            [row["month"] for row in second_page.context["net_page"]],
            ["2026-02", "2026-01"],
        )

    def test_category_and_month_filters_render_as_dropdowns(self):
        self._transaction(
            amount="20.00",
            in_out=Transaction.OUT,
            category=self.groceries_category,
            fingerprint="category-dropdown",
        )

        response = self.client.get(reverse("overview"))

        self.assertContains(response, 'id="catSelect"')
        self.assertContains(response, 'id="catYearButtons"')
        self.assertContains(response, 'id="catMonthButtons"')
        self.assertNotContains(response, 'id="catMonthSelect"')
        self.assertNotContains(response, 'class="cat-btn"')
