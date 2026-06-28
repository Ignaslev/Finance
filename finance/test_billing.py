from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance.models import Category, UserProfile
from finance.views import billing


MONTHLY = "price_test_monthly"
YEARLY = "price_test_yearly"


def subscription(
    *,
    subscription_id="sub_test",
    customer_id="cus_test",
    price_id=MONTHLY,
    status="active",
    user_id=None,
    period_end=None,
):
    return {
        "id": subscription_id,
        "customer": customer_id,
        "status": status,
        "metadata": {"user_id": str(user_id)} if user_id else {},
        "items": {"data": [{"price": {"id": price_id}}]},
        "current_period_end": int(
            (period_end or (timezone.now() + timedelta(days=30))).timestamp()
        ),
        "cancel_at_period_end": False,
    }


@override_settings(
    STRIPE_SECRET_KEY="sk_test_fake",
    STRIPE_PUBLISHABLE_KEY="pk_test_fake",
    STRIPE_WEBHOOK_SECRET="whsec_fake",
    STRIPE_PRICE_MONTHLY=MONTHLY,
    STRIPE_PRICE_YEARLY=YEARLY,
    ALLOWED_HOSTS=["testserver"],
)
class PaymentSecurityTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username="payer@example.test",
            email="payer@example.test",
            password="StrongPass123!",
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            subscription_status=UserProfile.SUBSCRIPTION_EXPIRED,
            trial_started_at=timezone.now() - timedelta(days=15),
            trial_ends_at=timezone.now() - timedelta(days=1),
            stripe_customer_id="cus_test",
            stripe_subscription_id="sub_test",
        )

    def _stripe(self, event=None):
        fake = SimpleNamespace()
        fake.Webhook = SimpleNamespace(
            construct_event=Mock(return_value=event)
        )
        fake.Subscription = SimpleNamespace(retrieve=Mock())
        if event and event.get("type", "").startswith("customer.subscription."):
            fake.Subscription.retrieve.return_value = event["data"]["object"]
        fake.Customer = SimpleNamespace(create=Mock())
        fake.checkout = SimpleNamespace(
            Session=SimpleNamespace(create=Mock(), retrieve=Mock())
        )
        fake.billing_portal = SimpleNamespace(
            Session=SimpleNamespace(create=Mock())
        )
        return fake

    def _event(self, event_type, data, event_id="evt_test"):
        return {
            "id": event_id,
            "type": event_type,
            "created": int(timezone.now().timestamp()),
            "data": {"object": data},
        }

    def test_webhook_rejects_missing_or_invalid_signature(self):
        fake = self._stripe()
        fake.Webhook.construct_event.side_effect = ValueError("bad signature")
        with patch("finance.views.billing._stripe", return_value=fake):
            response = self.client.post(
                reverse("stripe_webhook"),
                data=b"{}",
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)

    def test_allowed_active_subscription_grants_access(self):
        event = self._event(
            "customer.subscription.updated",
            subscription(user_id=self.user.id),
        )
        with patch("finance.views.billing._stripe", return_value=self._stripe(event)):
            response = self.client.post(
                reverse("stripe_webhook"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="signed",
            )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.subscription_status, UserProfile.SUBSCRIPTION_ACTIVE)
        self.assertEqual(self.profile.plan_interval, UserProfile.PLAN_MONTHLY)
        self.assertTrue(self.profile.has_active_access())

    def test_unknown_price_cannot_grant_access(self):
        event = self._event(
            "customer.subscription.updated",
            subscription(price_id="price_attacker", user_id=self.user.id),
        )
        with patch("finance.views.billing._stripe", return_value=self._stripe(event)):
            response = self.client.post(
                reverse("stripe_webhook"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="signed",
            )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.subscription_status, UserProfile.SUBSCRIPTION_EXPIRED)
        self.assertFalse(self.profile.has_active_access())

    def test_failed_invoice_and_deleted_subscription_revoke_access(self):
        self.profile.subscription_status = UserProfile.SUBSCRIPTION_ACTIVE
        self.profile.stripe_current_period_end = timezone.now() + timedelta(days=30)
        self.profile.save()
        failed = self._event(
            "invoice.payment_failed",
            {"customer": "cus_test", "subscription": "sub_test"},
            "evt_failed",
        )
        failed_stripe = self._stripe(failed)
        failed_stripe.Subscription.retrieve.return_value = subscription(
            status="past_due", user_id=self.user.id
        )
        with patch("finance.views.billing._stripe", return_value=failed_stripe):
            response = self.client.post(
                reverse("stripe_webhook"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="signed",
            )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.subscription_status, UserProfile.SUBSCRIPTION_PAST_DUE)
        self.assertFalse(self.profile.has_active_access())

        deleted = self._event(
            "customer.subscription.deleted",
            subscription(status="canceled", user_id=self.user.id),
            "evt_deleted",
        )
        with patch("finance.views.billing._stripe", return_value=self._stripe(deleted)):
            response = self.client.post(
                reverse("stripe_webhook"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="signed",
            )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.subscription_status, UserProfile.SUBSCRIPTION_CANCELED)
        self.assertFalse(self.profile.has_active_access())

    def test_subscription_event_reconciles_current_stripe_state(self):
        stale_canceled = self._event(
            "customer.subscription.updated",
            subscription(status="canceled", user_id=self.user.id),
            "evt_stale",
        )
        current_active = subscription(status="active", user_id=self.user.id)
        fake = self._stripe(stale_canceled)
        fake.Subscription.retrieve.return_value = current_active
        with patch("finance.views.billing._stripe", return_value=fake):
            response = self.client.post(
                reverse("stripe_webhook"),
                data=b"{}",
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="signed",
            )
        self.assertEqual(response.status_code, 200)
        fake.Subscription.retrieve.assert_called_once_with("sub_test")
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.subscription_status, UserProfile.SUBSCRIPTION_ACTIVE)
        self.assertTrue(self.profile.has_active_access())

    def test_checkout_requires_login_and_post(self):
        url = reverse("billing_checkout", args=[UserProfile.PLAN_MONTHLY])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_checkout_uses_bound_customer_plan_and_metadata(self):
        self.client.force_login(self.user)
        fake = self._stripe()
        fake.checkout.Session.create.return_value = SimpleNamespace(
            url="https://checkout.stripe.test/session"
        )
        with patch("finance.views.billing._stripe", return_value=fake):
            response = self.client.post(
                reverse("billing_checkout", args=[UserProfile.PLAN_MONTHLY])
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.stripe.test/session")
        kwargs = fake.checkout.Session.create.call_args.kwargs
        self.assertEqual(kwargs["customer"], "cus_test")
        self.assertEqual(kwargs["line_items"], [{"price": MONTHLY, "quantity": 1}])
        self.assertEqual(kwargs["client_reference_id"], str(self.user.id))
        self.assertEqual(kwargs["metadata"]["user_id"], str(self.user.id))
        self.assertEqual(kwargs["subscription_data"]["metadata"]["user_id"], str(self.user.id))

    def test_active_user_cannot_start_duplicate_checkout(self):
        self.profile.subscription_status = UserProfile.SUBSCRIPTION_ACTIVE
        self.profile.stripe_current_period_end = timezone.now() + timedelta(days=30)
        self.profile.save()
        self.client.force_login(self.user)
        fake = self._stripe()
        with patch("finance.views.billing._stripe", return_value=fake):
            response = self.client.post(
                reverse("billing_checkout", args=[UserProfile.PLAN_MONTHLY])
            )
        self.assertEqual(response.status_code, 302)
        fake.checkout.Session.create.assert_not_called()

    def test_portal_requires_bound_paid_subscription(self):
        self.client.force_login(self.user)
        self.profile.stripe_subscription_id = ""
        self.profile.save(update_fields=["stripe_subscription_id"])
        fake = self._stripe()
        with patch("finance.views.billing._stripe", return_value=fake):
            response = self.client.get(reverse("billing_portal"))
        self.assertEqual(response.status_code, 302)
        fake.billing_portal.Session.create.assert_not_called()

    def test_checkout_return_rejects_another_users_session(self):
        other = self.User.objects.create_user(
            username="other@example.test",
            email="other@example.test",
            password="StrongPass123!",
        )
        other_profile = UserProfile.objects.create(user=other)
        fake = self._stripe()
        fake.checkout.Session.retrieve.return_value = {
            "id": "cs_test_other",
            "status": "complete",
            "mode": "subscription",
            "client_reference_id": str(other.id),
            "metadata": {"user_id": str(other.id)},
            "customer": "cus_other",
            "subscription": subscription(
                subscription_id="sub_other",
                customer_id="cus_other",
                user_id=other.id,
            ),
        }
        with patch("finance.views.billing._stripe", return_value=fake):
            ok, _message = billing.sync_checkout_session_for_user(
                self.user, "cs_test_other"
            )
        self.assertFalse(ok)
        other_profile.refresh_from_db()
        self.assertFalse(other_profile.stripe_subscription_id)

    def test_expired_user_is_blocked_from_paid_mutations(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("category_list"), {"name": "Blocked"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Category.objects.filter(user=self.user, name="Blocked").exists()
        )

        response = self.client.post(
            reverse("tx_add"),
            {
                "date": "2026-06-28",
                "merchant": "Blocked",
                "amount": "10.00",
                "currency": "EUR",
                "in_out": "out",
            },
        )
        self.assertEqual(response.status_code, 302)

        upload = SimpleUploadedFile("bank.csv", b"date,amount\n2026-01-01,1\n")
        response = self.client.post(reverse("upload"), {"file": upload})
        self.assertEqual(response.status_code, 302)

        response = self.client.post(reverse("ai_full_categorize"))
        self.assertEqual(response.status_code, 302)

    def test_beta_manual_trial_and_staff_access_rules(self):
        now = timezone.now()
        self.profile.is_beta_tester = True
        self.profile.beta_access_until = now + timedelta(days=365)
        self.profile.subscription_status = UserProfile.SUBSCRIPTION_BETA
        self.profile.save()
        self.assertTrue(self.profile.has_active_access(now))

        self.profile.beta_access_until = now - timedelta(seconds=1)
        self.profile.is_beta_tester = False
        self.profile.subscription_status = UserProfile.SUBSCRIPTION_TRIAL
        self.profile.trial_ends_at = now + timedelta(days=14)
        self.profile.save()
        self.assertTrue(self.profile.has_active_access(now))

        self.profile.trial_ends_at = now - timedelta(seconds=1)
        self.profile.manual_access_until = now + timedelta(days=30)
        self.profile.save()
        self.assertTrue(self.profile.has_active_access(now))

        self.profile.manual_access_until = now - timedelta(seconds=1)
        self.profile.save()
        self.assertFalse(self.profile.has_active_access(now))

        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.assertTrue(self.profile.has_active_access(now))
