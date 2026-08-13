import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance.models import Category, MoneySource, Transaction


@override_settings(ALLOWED_HOSTS=["testserver"])
class StatisticsDisclosureTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="statistics-ui@example.test",
            email="statistics-ui@example.test",
            password="StrongPass123!",
        )
        source = MoneySource.objects.create(
            user=self.user,
            name="Main account",
            type="bank",
            is_active=True,
        )
        income = Category.objects.create(user=self.user, name="Individual activity")
        subscriptions = Category.objects.create(user=self.user, name="Subscriptions")

        Transaction.objects.create(
            user=self.user,
            money_source=source,
            date=timezone.localdate() - timedelta(days=3),
            merchant="Employer",
            amount=Decimal("1500.00"),
            currency="EUR",
            in_out=Transaction.IN,
            category=income.name,
            category_fk=income,
            category_source="user",
            fingerprint="statistics-income",
        )
        Transaction.objects.create(
            user=self.user,
            money_source=source,
            date=timezone.localdate() - timedelta(days=2),
            merchant="Streaming service",
            amount=Decimal("12.99"),
            currency="EUR",
            in_out=Transaction.OUT,
            category=subscriptions.name,
            category_fk=subscriptions,
            category_source="user",
            fingerprint="statistics-subscription",
        )
        Transaction.objects.create(
            user=self.user,
            money_source=source,
            date=timezone.localdate() - timedelta(days=1),
            merchant="Own account transfer",
            amount=Decimal("900.00"),
            currency="EUR",
            in_out=Transaction.IN,
            category=income.name,
            category_fk=income,
            category_source="user",
            is_internal_transfer=True,
            fingerprint="statistics-transfer",
        )
        self.client.force_login(self.user)

    def test_statistics_tables_are_collapsed_and_weekday_chart_is_not_rendered(self):
        response = self.client.get(reverse("statistics"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertGreaterEqual(html.count('<details class="statistics-disclosure"'), 3)
        self.assertIn('<details class="statistics-disclosure statistics-disclosure-nested">', html)
        self.assertNotIn('<details class="statistics-disclosure" open', html)
        self.assertNotIn('id="weekdayChart"', html)
        self.assertNotIn("const wdLabels", html)
        self.assertNotIn("Financial Runway", html)
        self.assertNotIn('id="runwayModal"', html)
        self.assertNotIn("runway_months", response.context)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", html)
        self.assertIn('id="spending-by-category"', html)
        self.assertIn('id="historyCatSelect"', html)
        self.assertIn('id="historyCatChartType"', html)
        self.assertIn('id="historyCatYearButtons"', html)
        self.assertIn('id="historyCatMonthButtons"', html)
        self.assertIn('id="monthly-spending-by-category"', html)
        self.assertIn('id="monthlyHistoryYearButtons"', html)
        self.assertIn('id="monthlyHistoryMonthButtons"', html)
        self.assertIn('id="monthlyHistoryChart"', html)
        self.assertIn('id="monthlyHistoryCategorySelect"', html)
        self.assertNotIn('id="monthlyHistoryChartType"', html)
        self.assertLess(
            html.index('id="monthly-spending-by-category"'),
            html.index('id="spending-by-category"'),
        )

        month_key = timezone.localdate().strftime("%Y-%m")
        top_transactions = json.loads(
            response.context["spending_top_transactions_by_cat_month_json"]
        )
        self.assertEqual(
            top_transactions["Subscriptions"][month_key][0]["merchant"],
            "Streaming service",
        )
        self.assertEqual(response.context["total_in"], 1500.0)
        self.assertEqual(response.context["found_income_sources_count"], 1)
        self.assertEqual(response.context["income_sources_summary"]["total_income"], Decimal("0"))
