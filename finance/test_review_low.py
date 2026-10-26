import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from finance.models import Category, MoneySource, Transaction


@override_settings(ALLOWED_HOSTS=["testserver"])
class LowConfidenceReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="r@example.test", email="r@example.test",
                                                         password="StrongPass123!")
        self.client.force_login(self.user)
        acc = MoneySource.objects.create(user=self.user, name="Main", type="bank")
        self.food = Category.objects.create(user=self.user, name="Maisto prekės")
        self.fun = Category.objects.create(user=self.user, name="Pramogos")
        self.rows = [
            Transaction.objects.create(
                user=self.user, money_source=acc, date=date(2026, 10, i + 1), merchant=f"Shop {i}",
                amount=Decimal("10"), in_out="out", category_fk=self.food, category=self.food.name,
                category_source="ai", ai_suggested_fk=self.food, ai_confidence=Decimal("0.5"), fingerprint=f"fp-{i}",
            )
            for i in range(3)
        ]

    def test_page_asks_for_an_explicit_pick_per_row(self):
        page = self.client.get(reverse("review_low_conf"))
        self.assertContains(page, 'class="row-pick"', count=3)
        self.assertContains(page, "Išsaugomos tik pažymėtos eilutės")

    def test_only_picked_rows_are_saved(self):
        picked = self.rows[0]
        self.client.post(reverse("review_low_apply"), {"changes_json": json.dumps({str(picked.id): str(self.fun.id)})})

        picked.refresh_from_db()
        self.assertEqual((picked.category_fk, picked.category_source, picked.ai_suggested_fk), (self.fun, "user", None))
        for other in self.rows[1:]:
            other.refresh_from_db()
            self.assertEqual((other.category_source, other.ai_suggested_fk), ("ai", self.food))
