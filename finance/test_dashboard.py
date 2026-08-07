import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

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

    def _transaction(self, *, amount, in_out, category, fingerprint, transaction_date=None):
        return Transaction.objects.create(
            user=self.user,
            money_source=self.source,
            date=transaction_date or date(2026, 7, 15),
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
            transaction_date=timezone.localdate(),
        )

        response = self.client.get(reverse("overview"))

        self.assertContains(response, 'id="catSelect"')
        self.assertContains(response, 'id="catChartType"')
        self.assertContains(response, "Išlaidos pagal kategoriją šį mėnesį")
        self.assertContains(response, 'href="/statistics/#spending-by-category"')
        self.assertContains(response, 'id="monthCategoryChart"')
        self.assertNotContains(response, 'id="monthCategoryChartType"')
        self.assertContains(
            response,
            'id="monthly-category-spending" style="grid-column:1 / -1; order:3;"',
        )
        self.assertContains(response, 'id="monthCategoryYearButtons"')
        self.assertContains(response, 'id="monthCategoryMonthButtons"')
        self.assertContains(response, 'id="monthCategoryDetailSelect"')
        self.assertNotContains(response, 'id="catYearButtons"')
        self.assertNotContains(response, 'id="catMonthButtons"')
        self.assertNotContains(response, 'class="cat-btn"')

    def test_overview_current_month_chart_contains_all_spending_categories(self):
        transport = Category.objects.create(user=self.user, name="Transport")
        self._transaction(
            amount="20.00",
            in_out=Transaction.OUT,
            category=self.groceries_category,
            fingerprint="current-groceries",
            transaction_date=timezone.localdate(),
        )
        self._transaction(
            amount="15.00",
            in_out=Transaction.OUT,
            category=transport,
            fingerprint="current-transport",
            transaction_date=timezone.localdate(),
        )

        response = self.client.get(reverse("overview"))

        self.assertEqual(json.loads(response.context["cat_names_json"]), ["Groceries", "Transport"])
        self.assertEqual(json.loads(response.context["current_category_values_json"]), [20.0, 15.0])
        self.assertEqual(response.context["current_category_month"], timezone.localdate().strftime("%Y-%m"))

    def test_month_category_card_returns_top_ten_individual_transactions(self):
        transport = Category.objects.create(user=self.user, name="Transport")
        selected_date = date(2026, 5, 15)
        for index in range(12):
            transaction = self._transaction(
                amount=str(index + 1),
                in_out=Transaction.OUT,
                category=self.groceries_category,
                fingerprint=f"top-transaction-{index}",
                transaction_date=selected_date,
            )
            transaction.merchant = f"Merchant {index + 1}"
            transaction.save(update_fields=["merchant"])
        self._transaction(
            amount="25.00",
            in_out=Transaction.OUT,
            category=transport,
            fingerprint="month-transport",
            transaction_date=selected_date,
        )

        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.context["month_category_names_json"]), ["Groceries", "Transport"])
        self.assertIn("2026-05", json.loads(response.context["month_category_months_json"]))
        top_transactions = json.loads(response.context["month_category_top_transactions_json"])
        grocery_rows = top_transactions["Groceries"]["2026-05"]
        self.assertEqual(len(grocery_rows), 10)
        self.assertEqual([row["amount"] for row in grocery_rows], [12.0, 11.0, 10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0])
        self.assertEqual(grocery_rows[0]["merchant"], "Merchant 12")
        self.assertEqual(grocery_rows[0]["account"], "Main account")
