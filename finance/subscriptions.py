from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from finance.models import UserProfile


STRIPE_PRICE_BY_INTERVAL = {
    UserProfile.PLAN_MONTHLY: "STRIPE_PRICE_MONTHLY",
    UserProfile.PLAN_YEARLY: "STRIPE_PRICE_YEARLY",
}


def get_profile(user):
    profile, _created = UserProfile.objects.get_or_create(user=user)
    return profile


def grant_beta_access(profile, joined_at=None):
    joined_at = joined_at or timezone.now()
    profile.is_beta_tester = True
    profile.beta_joined_at = profile.beta_joined_at or joined_at
    profile.beta_access_until = profile.beta_access_until or joined_at + timedelta(
        days=getattr(settings, "BETA_FREE_DAYS", 365)
    )
    profile.subscription_status = UserProfile.SUBSCRIPTION_BETA
    profile.subscription_updated_at = timezone.now()
    profile.save(update_fields=[
        "is_beta_tester",
        "beta_joined_at",
        "beta_access_until",
        "subscription_status",
        "subscription_updated_at",
    ])
    return profile


def ensure_trial_access(profile):
    if profile.is_beta_tester or profile.trial_started_at or profile.trial_ends_at:
        return profile

    now = timezone.now()
    profile.trial_started_at = now
    profile.trial_ends_at = now + timedelta(days=getattr(settings, "TRIAL_FREE_DAYS", 14))
    profile.subscription_status = UserProfile.SUBSCRIPTION_TRIAL
    profile.subscription_updated_at = now
    profile.save(update_fields=[
        "trial_started_at",
        "trial_ends_at",
        "subscription_status",
        "subscription_updated_at",
    ])
    return profile


def stripe_locale_for_request(request):
    lang = (getattr(request, "LANGUAGE_CODE", "") or "").split("-")[0].lower()
    return "lt" if lang == "lt" else "en"


def price_id_for_interval(interval):
    setting_name = STRIPE_PRICE_BY_INTERVAL.get(interval)
    if not setting_name:
        return ""
    return getattr(settings, setting_name, "") or ""


def interval_for_price_id(price_id):
    for interval, setting_name in STRIPE_PRICE_BY_INTERVAL.items():
        if price_id and price_id == (getattr(settings, setting_name, "") or ""):
            return interval
    return ""


def stripe_is_configured():
    return bool(
        getattr(settings, "STRIPE_SECRET_KEY", "")
        and getattr(settings, "STRIPE_PRICE_MONTHLY", "")
        and getattr(settings, "STRIPE_PRICE_YEARLY", "")
    )


def access_context(user):
    billing_enabled = getattr(settings, "BILLING_ENABLED", False)
    if not user.is_authenticated:
        return {
            "profile": None,
            "has_access": False,
            "access_source": "",
            "access_until": None,
            "billing_enabled": billing_enabled,
            "stripe_configured": billing_enabled and stripe_is_configured(),
        }

    profile = get_profile(user)
    if getattr(settings, "FREE_ACCESS_MODE", True):
        return {
            "profile": profile,
            "has_access": True,
            "access_source": "free",
            "access_until": None,
            "billing_enabled": billing_enabled,
            "stripe_configured": billing_enabled and stripe_is_configured(),
            "monthly_price_id": getattr(settings, "STRIPE_PRICE_MONTHLY", ""),
            "yearly_price_id": getattr(settings, "STRIPE_PRICE_YEARLY", ""),
        }

    if not profile.is_beta_tester:
        ensure_trial_access(profile)

    return {
        "profile": profile,
        "has_access": profile.has_active_access(),
        "access_source": profile.access_source,
        "access_until": profile.access_until,
        "billing_enabled": billing_enabled,
        "stripe_configured": billing_enabled and stripe_is_configured(),
        "monthly_price_id": getattr(settings, "STRIPE_PRICE_MONTHLY", ""),
        "yearly_price_id": getattr(settings, "STRIPE_PRICE_YEARLY", ""),
    }


def blocked_feature_response(request, redirect_name="profile"):
    messages.error(
        request,
        _("Your free access has ended. Choose a monthly or yearly plan to continue using this feature."),
    )
    return redirect(redirect_name)


def require_paid_access(request, redirect_name="profile"):
    ctx = access_context(request.user)
    if ctx["has_access"]:
        return None
    return blocked_feature_response(request, redirect_name=redirect_name)


def billing_return_url(request):
    return request.build_absolute_uri(reverse("profile"))
