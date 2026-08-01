from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from finance.models import UserProfile
from finance.owner_notifications import notify_paid_subscription
from finance.subscriptions import (
    billing_return_url,
    interval_for_price_id,
    price_id_for_interval,
    stripe_is_configured,
    stripe_locale_for_request,
)


def _stripe():
    import stripe

    stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    return stripe


def _obj_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _timestamp_to_datetime(value):
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)


def _profile_from_customer_or_subscription(customer_id="", subscription_id=""):
    qs = UserProfile.objects.all()
    if subscription_id:
        profile = qs.filter(stripe_subscription_id=subscription_id).first()
        if profile:
            return profile
    if customer_id:
        profile = qs.filter(stripe_customer_id=customer_id).first()
        if profile:
            return profile
    return None


def _subscription_status_for_stripe(status):
    if status == "active":
        return UserProfile.SUBSCRIPTION_ACTIVE
    if status == "trialing":
        return UserProfile.SUBSCRIPTION_TRIALING
    if status in {"past_due", "unpaid", "incomplete", "incomplete_expired"}:
        return UserProfile.SUBSCRIPTION_PAST_DUE
    if status == "canceled":
        return UserProfile.SUBSCRIPTION_CANCELED
    return UserProfile.SUBSCRIPTION_EXPIRED


def _price_is_allowed(price_id):
    return bool(price_id and interval_for_price_id(price_id))


def _subscription_id_from_invoice(invoice):
    subscription_id = _obj_get(invoice, "subscription", "")
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id.get("id", "")
    if subscription_id:
        return subscription_id

    parent = _obj_get(invoice, "parent", {}) or {}
    subscription_details = _obj_get(parent, "subscription_details", {}) or {}
    subscription_id = _obj_get(subscription_details, "subscription", "")
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id.get("id", "")
    return subscription_id or ""


def _sync_subscription(subscription, event_id=""):
    subscription_id = _obj_get(subscription, "id", "")
    customer_id = _obj_get(subscription, "customer", "")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id", "")

    profile = _profile_from_customer_or_subscription(customer_id, subscription_id)
    metadata = _obj_get(subscription, "metadata", {}) or {}
    user_id = metadata.get("user_id") if isinstance(metadata, dict) else None
    if not profile and user_id:
        profile = UserProfile.objects.filter(user_id=user_id).first()
    if not profile:
        return None

    if event_id and profile.stripe_last_event_id == event_id:
        return profile

    items = _obj_get(_obj_get(subscription, "items", {}), "data", []) or []
    first_item = items[0] if items else {}
    price = _obj_get(first_item, "price", {}) or {}
    price_id = _obj_get(price, "id", "")
    plan_interval = interval_for_price_id(price_id)

    status = _obj_get(subscription, "status", "")
    profile.subscription_status = (
        _subscription_status_for_stripe(status)
        if _price_is_allowed(price_id)
        else UserProfile.SUBSCRIPTION_EXPIRED
    )
    profile.plan_interval = plan_interval
    profile.stripe_customer_id = customer_id or profile.stripe_customer_id
    profile.stripe_subscription_id = subscription_id or profile.stripe_subscription_id
    profile.stripe_price_id = price_id or profile.stripe_price_id
    profile.stripe_current_period_end = _timestamp_to_datetime(_obj_get(subscription, "current_period_end"))
    profile.stripe_cancel_at_period_end = bool(_obj_get(subscription, "cancel_at_period_end", False))
    profile.stripe_last_event_id = event_id or profile.stripe_last_event_id
    profile.subscription_updated_at = timezone.now()
    profile.save(update_fields=[
        "subscription_status",
        "plan_interval",
        "stripe_customer_id",
        "stripe_subscription_id",
        "stripe_price_id",
        "stripe_current_period_end",
        "stripe_cancel_at_period_end",
        "stripe_last_event_id",
        "subscription_updated_at",
    ])

    if (
        profile.subscription_status == UserProfile.SUBSCRIPTION_ACTIVE
        and subscription_id
    ):
        claimed = (
            UserProfile.objects.filter(pk=profile.pk)
            .exclude(stripe_owner_notified_subscription_id=subscription_id)
            .update(stripe_owner_notified_subscription_id=subscription_id)
        )
        if claimed:
            profile.stripe_owner_notified_subscription_id = subscription_id
            notify_paid_subscription(profile)

    return profile


def sync_checkout_session_for_user(user, session_id):
    if not session_id or not str(session_id).startswith("cs_"):
        return False, _("Missing Stripe checkout session.")
    if not getattr(settings, "STRIPE_SECRET_KEY", ""):
        return False, _("Payments are not configured yet. Please try again later.")

    stripe = _stripe()
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    except Exception:
        return False, _("Could not confirm the Stripe payment yet. Please try again later.")

    metadata = _obj_get(session, "metadata", {}) or {}
    session_user_id = str(_obj_get(session, "client_reference_id", "") or metadata.get("user_id", ""))
    if session_user_id != str(user.id):
        return False, _("This Stripe checkout session does not belong to your account.")

    if _obj_get(session, "status", "") != "complete":
        return False, _("Stripe checkout is not complete yet.")

    if _obj_get(session, "mode", "") != "subscription":
        return False, _("This Stripe checkout session is not a subscription.")

    subscription = _obj_get(session, "subscription", None)
    if not subscription:
        return False, _("No Stripe subscription was found for this payment.")

    items = _obj_get(_obj_get(subscription, "items", {}), "data", []) or []
    first_item = items[0] if items else {}
    price_id = _obj_get(_obj_get(first_item, "price", {}) or {}, "id", "")
    if not _price_is_allowed(price_id):
        return False, _("This Stripe subscription does not match a MoneyCompass plan.")

    profile, _created = UserProfile.objects.get_or_create(user=user)
    customer_id = _obj_get(session, "customer", "")
    subscription_id = _obj_get(subscription, "id", "")
    subscription_customer_id = _obj_get(subscription, "customer", "")
    if isinstance(subscription_customer_id, dict):
        subscription_customer_id = subscription_customer_id.get("id", "")
    if customer_id and subscription_customer_id and customer_id != subscription_customer_id:
        return False, _("This Stripe checkout session does not belong to your account.")
    if profile.stripe_customer_id and customer_id and profile.stripe_customer_id != customer_id:
        return False, _("This Stripe checkout session does not belong to your account.")

    profile.stripe_customer_id = customer_id or profile.stripe_customer_id
    profile.stripe_subscription_id = subscription_id or profile.stripe_subscription_id
    profile.subscription_updated_at = timezone.now()
    profile.save(update_fields=[
        "stripe_customer_id",
        "stripe_subscription_id",
        "subscription_updated_at",
    ])

    synced_profile = _sync_subscription(subscription)
    if synced_profile and synced_profile.has_active_access():
        return True, _("Subscription activated.")

    return False, _("Stripe payment was found, but the subscription is not active yet.")


@login_required
@require_POST
def checkout(request, interval):
    if interval not in {UserProfile.PLAN_MONTHLY, UserProfile.PLAN_YEARLY}:
        messages.error(request, _("Unknown plan selected."))
        return redirect("profile")

    price_id = price_id_for_interval(interval)
    if not stripe_is_configured() or not price_id:
        messages.error(request, _("Payments are not configured yet. Please try again later."))
        return redirect("profile")

    stripe = _stripe()
    profile, _created = UserProfile.objects.get_or_create(user=request.user)

    if profile.stripe_subscription_id and profile.has_active_access():
        messages.info(request, _("You already have an active subscription. Use Manage billing to make changes."))
        return redirect("profile")

    if profile.has_active_access() and profile.access_source in {"beta", "manual", "admin"}:
        messages.info(request, _("No payment is needed right now."))
        return redirect("profile")

    try:
        if not profile.stripe_customer_id:
            customer = stripe.Customer.create(
                email=request.user.email,
                name=request.user.get_full_name() or request.user.email,
                metadata={"user_id": str(request.user.id)},
            )
            profile.stripe_customer_id = customer.id
            profile.save(update_fields=["stripe_customer_id"])

        return_url = billing_return_url(request)
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=profile.stripe_customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{return_url}?billing=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{return_url}?billing=cancelled",
            client_reference_id=str(request.user.id),
            allow_promotion_codes=True,
            locale=stripe_locale_for_request(request),
            metadata={
                "user_id": str(request.user.id),
                "interval": interval,
            },
            subscription_data={
                "metadata": {
                    "user_id": str(request.user.id),
                    "interval": interval,
                },
            },
        )
    except Exception:
        messages.error(request, _("Could not open Stripe Checkout. Please try again later."))
        return redirect("profile")

    return redirect(session.url)


@login_required
@require_http_methods(["GET", "POST"])
def portal(request):
    if not getattr(settings, "STRIPE_SECRET_KEY", ""):
        messages.error(request, _("Payments are not configured yet. Please try again later."))
        return redirect("profile")

    profile, _created = UserProfile.objects.get_or_create(user=request.user)
    if not profile.stripe_customer_id or not profile.stripe_subscription_id:
        messages.info(request, _("No paid subscription found yet. Choose a plan first."))
        return redirect("profile")

    stripe = _stripe()
    try:
        session = stripe.billing_portal.Session.create(
            customer=profile.stripe_customer_id,
            return_url=billing_return_url(request),
            locale=stripe_locale_for_request(request),
        )
    except Exception:
        messages.error(request, _("Could not open the billing portal. Please try again later."))
        return redirect("profile")

    return redirect(session.url)


@csrf_exempt
def webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    stripe = _stripe()

    try:
        if not webhook_secret:
            return HttpResponse(status=400)
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception:
        return HttpResponse(status=400)

    event_id = _obj_get(event, "id", "")
    event_type = _obj_get(event, "type", "")
    data_object = _obj_get(_obj_get(event, "data", {}), "object", {})

    try:
        if event_type == "checkout.session.completed":
            customer_id = _obj_get(data_object, "customer", "")
            subscription_id = _obj_get(data_object, "subscription", "")
            user_id = _obj_get(data_object, "client_reference_id", "") or (_obj_get(data_object, "metadata", {}) or {}).get("user_id")
            profile = _profile_from_customer_or_subscription(customer_id, subscription_id)
            if not profile and user_id:
                profile = UserProfile.objects.filter(user_id=user_id).first()
            if profile:
                profile.stripe_customer_id = customer_id or profile.stripe_customer_id
                profile.stripe_subscription_id = subscription_id or profile.stripe_subscription_id
                profile.subscription_updated_at = timezone.now()
                update_fields = [
                    "stripe_customer_id",
                    "stripe_subscription_id",
                    "subscription_updated_at",
                ]
                if not subscription_id:
                    profile.stripe_last_event_id = event_id or profile.stripe_last_event_id
                    update_fields.append("stripe_last_event_id")
                profile.save(update_fields=update_fields)
            if subscription_id:
                subscription = stripe.Subscription.retrieve(subscription_id)
                _sync_subscription(subscription, event_id=event_id)

        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            subscription_id = _obj_get(data_object, "id", "")
            if not subscription_id:
                return HttpResponse(status=400)
            current_subscription = stripe.Subscription.retrieve(subscription_id)
            _sync_subscription(current_subscription, event_id=event_id)

        elif event_type == "invoice.payment_failed":
            subscription_id = _subscription_id_from_invoice(data_object)
            if subscription_id:
                current_subscription = stripe.Subscription.retrieve(subscription_id)
                _sync_subscription(current_subscription, event_id=event_id)

    except Exception:
        return HttpResponse(status=500)

    return HttpResponse(status=200)
