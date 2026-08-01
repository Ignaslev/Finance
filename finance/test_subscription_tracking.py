from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance.models import Category, MoneySource, SubscriptionDecision, Transaction
from finance.views.reports import _build_tracked_subscriptions


@override_settings(ALLOWED_HOSTS=["testserver"])
class SubscriptionTrackingDecisionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="subscription-state@example.test",
            email="subscription-state@example.test",
            password="StrongPass123!",
        )
        self.source = MoneySource.objects.create(
            user=self.user,
            name="Main account",
            type="bank",
            is_active=True,
        )
        self.category = Category.objects.create(user=self.user, name="Subscriptions")
        Transaction.objects.create(
            user=self.user,
            money_source=self.source,
            date=timezone.localdate() - timedelta(days=2),
            merchant="Netflix",
            amount=Decimal("13.99"),
            currency="EUR",
            in_out=Transaction.OUT,
            category=self.category.name,
            category_fk=self.category,
            category_source="user",
            fingerprint="subscription-state-netflix",
        )
        self.client.force_login(self.user)

    def _groups(self):
        return _build_tracked_subscriptions(
            self.user,
            Transaction.objects.filter(user=self.user, is_deleted=False),
            timezone.localdate(),
        )

    def test_marking_active_subscription_ended_moves_it_to_past(self):
        active, past, _untracked, _summary = self._groups()
        self.assertEqual([row["name"] for row in active], ["Netflix"])
        self.assertEqual(past, [])
        statistics_response = self.client.get(reverse("statistics"))
        self.assertContains(statistics_response, reverse("subscription_mark_ended"))

        response = self.client.post(
            reverse("subscription_mark_ended"),
            {"normalized_merchant": "netflix", "display_name": "Netflix"},
        )

        self.assertRedirects(response, reverse("statistics"))
        decision = SubscriptionDecision.objects.get(user=self.user, normalized_merchant="netflix")
        self.assertEqual(decision.decision, SubscriptionDecision.DECISION_ENDED)

        active, past, _untracked, summary = self._groups()
        self.assertEqual(active, [])
        self.assertEqual([row["name"] for row in past], ["Netflix"])
        self.assertTrue(past[0]["manually_ended"])
        self.assertEqual(summary["active_count"], 0)
        statistics_response = self.client.get(reverse("statistics"))
        self.assertContains(statistics_response, reverse("subscription_mark_active"))

    def test_restore_returns_manually_ended_recent_subscription_to_active(self):
        SubscriptionDecision.objects.create(
            user=self.user,
            normalized_merchant="netflix",
            display_name="Netflix",
            decision=SubscriptionDecision.DECISION_ENDED,
        )

        response = self.client.post(
            reverse("subscription_mark_active"),
            {"normalized_merchant": "netflix", "display_name": "Netflix"},
        )

        self.assertRedirects(response, reverse("statistics"))
        decision = SubscriptionDecision.objects.get(user=self.user, normalized_merchant="netflix")
        self.assertEqual(decision.decision, SubscriptionDecision.DECISION_TRACK)
        active, past, _untracked, _summary = self._groups()
        self.assertEqual([row["name"] for row in active], ["Netflix"])
        self.assertEqual(past, [])

    def test_state_endpoints_reject_get_requests(self):
        self.assertEqual(self.client.get(reverse("subscription_mark_ended")).status_code, 405)
        self.assertEqual(self.client.get(reverse("subscription_mark_active")).status_code, 405)
