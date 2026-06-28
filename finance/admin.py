from django.contrib import admin
from django.utils import timezone
from datetime import timedelta

from .models import Transaction, Category, MoneySource, BalanceSnapshot, SavingsGoal, FeedbackTicket, UserProfile
from django.core.exceptions import PermissionDenied

@admin.register(FeedbackTicket)
class FeedbackTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "user", "kind", "page", "status")
    list_filter = ("kind", "page", "status", "created_at")
    search_fields = ("user__email", "message")
    ordering = ("-created_at",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "subscription_status",
        "plan_interval",
        "access_source",
        "access_until",
        "is_beta_tester",
        "manual_access_until",
        "stripe_customer_id",
    )
    list_filter = (
        "subscription_status",
        "plan_interval",
        "is_beta_tester",
        "stripe_cancel_at_period_end",
        "preferred_language",
    )
    search_fields = (
        "user__email",
        "user__username",
        "stripe_customer_id",
        "stripe_subscription_id",
    )
    readonly_fields = (
        "android_webhook_secret",
        "stripe_customer_id",
        "stripe_subscription_id",
        "stripe_price_id",
        "stripe_current_period_end",
        "stripe_cancel_at_period_end",
        "stripe_last_event_id",
        "subscription_updated_at",
        "access_source",
        "access_until",
    )
    fieldsets = (
        (None, {"fields": ("user", "preferred_language", "default_import_source")}),
        ("Access", {
            "fields": (
                "subscription_status",
                "plan_interval",
                "is_beta_tester",
                "beta_joined_at",
                "beta_access_until",
                "trial_started_at",
                "trial_ends_at",
                "manual_access_until",
                "manual_access_note",
                "access_source",
                "access_until",
            )
        }),
        ("Stripe", {
            "fields": (
                "stripe_customer_id",
                "stripe_subscription_id",
                "stripe_price_id",
                "stripe_current_period_end",
                "stripe_cancel_at_period_end",
                "stripe_last_event_id",
                "subscription_updated_at",
            )
        }),
        ("Preferences", {"fields": ("exclude_investment_tax", "android_webhook_secret")}),
        ("Deletion", {
            "fields": (
                "account_delete_requested_at",
                "account_delete_scheduled_for",
                "account_delete_canceled_at",
            )
        }),
    )
    actions = ("grant_30_days_manual_access", "grant_365_days_manual_access")

    @admin.action(description="Grant 30 days of manual access")
    def grant_30_days_manual_access(self, request, queryset):
        until = timezone.now() + timedelta(days=30)
        queryset.update(
            subscription_status=UserProfile.SUBSCRIPTION_MANUAL,
            manual_access_until=until,
            manual_access_note="Granted from Django admin",
            subscription_updated_at=timezone.now(),
        )

    @admin.action(description="Grant 365 days of manual access")
    def grant_365_days_manual_access(self, request, queryset):
        until = timezone.now() + timedelta(days=365)
        queryset.update(
            subscription_status=UserProfile.SUBSCRIPTION_MANUAL,
            manual_access_until=until,
            manual_access_note="Granted from Django admin",
            subscription_updated_at=timezone.now(),
        )
