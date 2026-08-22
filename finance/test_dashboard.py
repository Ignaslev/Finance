import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance.models import (
    Asset,
    AssetHolding,
    BalanceSnapshot,
    Category,
    MoneySource,
    PortfolioSnapshot,
    Transaction,
)


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

    def _transaction(
        self,
        *,
        amount,
        in_out,
        category,
        fingerprint,
        transaction_date=None,
        is_internal_transfer=False,
    ):
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
            is_internal_transfer=is_internal_transfer,
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
            is_internal_transfer=True,
        )
        self._transaction(
            amount="500.00",
            in_out=Transaction.IN,
            category=self.transfer_category,
            fingerprint="transfer-in",
            is_internal_transfer=True,
        )

        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.context["income_json"]), [1000.0])
        self.assertEqual(json.loads(response.context["spending_json"]), [200.0])
        self.assertEqual(response.context["net_rows"], [{"month": "2026-07", "net": 800.0}])
        self.assertNotIn("Internal transfer", response.context["cat_names"])

    def test_category_name_alone_does_not_control_transfer_behavior(self):
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
        self.assertEqual(json.loads(response.context["income_json"]), [0.0])
        self.assertEqual(json.loads(response.context["spending_json"]), [250.0])
        transfer.refresh_from_db()
        self.assertFalse(transfer.is_deleted)

    def test_internal_transfer_still_changes_its_account_balance(self):
        self._transaction(
            amount="125.00",
            in_out=Transaction.OUT,
            category=self.transfer_category,
            fingerprint="balance-transfer-out",
            is_internal_transfer=True,
        )

        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)
        account = response.context["accounts_with_balances"][0]
        self.assertEqual(account.effective_balance, Decimal("-125.00"))
        self.assertEqual(json.loads(response.context["income_json"]), [])
        self.assertEqual(json.loads(response.context["spending_json"]), [])

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
        self.assertContains(response, 'class="card dashboard-month-category-card"')
        self.assertContains(response, 'id="monthly-category-spending"')
        self.assertNotContains(response, 'id="monthly-category-spending" style=')
        self.assertContains(response, 'href="/statistics/#monthly-spending-by-category"')
        self.assertNotContains(response, 'id="monthCategoryYearButtons"')
        self.assertNotContains(response, 'id="monthCategoryMonthButtons"')
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
        selected_date = timezone.localdate()
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
        top_transactions = json.loads(response.context["month_category_top_transactions_json"])
        grocery_rows = top_transactions["Groceries"][selected_date.strftime("%Y-%m")]
        self.assertEqual(len(grocery_rows), 10)
        self.assertEqual([row["amount"] for row in grocery_rows], [12.0, 11.0, 10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0])
        self.assertEqual(grocery_rows[0]["merchant"], "Merchant 12")
        self.assertEqual(grocery_rows[0]["account"], "Main account")

    def test_dashboard_uses_live_holdings_for_renamed_investment_source(self):
        self.source.manual_balance = Decimal("50.00")
        self.source.balance_updated_at = timezone.now()
        self.source.save(update_fields=["manual_balance", "balance_updated_at"])
        investment = MoneySource.objects.create(
            user=self.user,
            name="My renamed portfolio",
            type="investment",
            is_active=True,
            manual_balance=Decimal("100.00"),
        )
        asset = Asset.objects.create(
            symbol="BTC",
            lookup_key="dashboard-live-btc",
            name="Bitcoin",
            asset_type="crypto",
            current_price_eur=Decimal("150.00"),
        )
        holding = AssetHolding.objects.create(
            user=self.user,
            asset=asset,
            money_source=investment,
            quantity=Decimal("2.00"),
        )
        BalanceSnapshot.objects.create(
            user=self.user,
            amount=Decimal("50.00"),
            timestamp=timezone.now(),
        )
        PortfolioSnapshot.objects.create(
            user=self.user,
            crypto_total=Decimal("100.00"),
        )

        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_net_worth"], 350.0)
        investment_row = next(
            row for row in response.context["accounts_with_balances"]
            if row.id == investment.id
        )
        self.assertEqual(investment_row.effective_balance, Decimal("300.0000000000000000"))
        self.assertEqual(json.loads(response.context["balance_values_json"])[-1], 350.0)

        holding.quantity = Decimal("3.00")
        holding.save(update_fields=["quantity"])
        edit_response = self.client.post(
            reverse("asset_edit", args=[holding.id]),
            {"quantity": "3"},
        )
        self.assertEqual(edit_response.status_code, 302)
        investment.refresh_from_db()
        self.assertEqual(investment.manual_balance, Decimal("450.00"))

        delete_response = self.client.post(
            reverse("asset_edit", args=[holding.id]),
            {"delete": "1"},
        )
        self.assertEqual(delete_response.status_code, 302)
        investment.refresh_from_db()
        self.assertEqual(investment.manual_balance, Decimal("0.00"))
