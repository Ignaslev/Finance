from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.utils import timezone
from datetime import timedelta
from zoneinfo import ZoneInfo

from finance.models import Transaction
from .models import User


def _lithuanian_datetime(value):
    if value is None:
        return None
    return timezone.localtime(value, ZoneInfo("Europe/Vilnius")).strftime("%Y-%m-%d %H:%M:%S")


class LastActivityFilter(admin.SimpleListFilter):
    title = "App activity"
    parameter_name = "app_activity"

    def lookups(self, request, model_admin):
        return (
            ("day", "Active in the last 24 hours"),
            ("week", "Active in the last 7 days"),
            ("month", "Active in the last 30 days"),
            ("older", "Last recorded activity over 30 days ago"),
            ("unrecorded", "No recorded activity yet"),
        )

    def queryset(self, request, queryset):
        windows = {"day": 1, "week": 7, "month": 30}
        if self.value() in windows:
            return queryset.filter(last_active_at__gte=timezone.now() - timedelta(days=windows[self.value()]))
        if self.value() == "older":
            return queryset.filter(last_active_at__lt=timezone.now() - timedelta(days=30))
        if self.value() == "unrecorded":
            return queryset.filter(last_active_at__isnull=True)
        return queryset


class TransactionDataFilter(admin.SimpleListFilter):
    title = "Current transaction data"
    parameter_name = "transaction_data"

    def lookups(self, request, model_admin):
        return (("yes", "Has transaction data"), ("no", "No transaction data"))

    def queryset(self, request, queryset):
        if self.value() in {"yes", "no"}:
            return queryset.filter(_has_transaction_data=self.value() == "yes")
        return queryset


class SuccessfulImportsFilter(admin.SimpleListFilter):
    title = "Successful imports"
    parameter_name = "successful_imports"

    def lookups(self, request, model_admin):
        return (("yes", "Has saved successful imports"), ("no", "No saved successful imports"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(_successful_import_count__gt=0)
        if self.value() == "no":
            return queryset.filter(_successful_import_count=0)
        return queryset


@admin.register(User)
class MoneyCompassUserAdmin(UserAdmin):
    list_display = (
        "email", "first_name", "is_active", "registered_display", "last_active_display",
        "last_login_display", "has_transaction_data", "successful_import_count", "last_import_display",
    )
    list_display_links = ("email",)
    ordering = ("-date_joined",)
    list_filter = UserAdmin.list_filter + (LastActivityFilter, TransactionDataFilter, SuccessfulImportsFilter)
    readonly_fields = UserAdmin.readonly_fields + (
        "last_active_display", "has_transaction_data", "successful_import_count",
        "undone_import_count", "last_import_display",
    )
    fieldsets = UserAdmin.fieldsets + (("App usage (read-only)", {
        "description": (
            "Times below and in the user list are Lithuanian local time. Activity records signed-in app "
            "requests at most once per minute, starting after deployment; a blank date means unknown, "
            "not necessarily never used. Transaction data excludes deleted records and may be entered "
            "manually. Imports count retained batches that added transactions, including later-undone "
            "imports; failed, empty, duplicate-only or deleted import history is not counted."
        ),
        "fields": (
            "last_active_display", "has_transaction_data", "successful_import_count",
            "undone_import_count", "last_import_display",
        ),
    }),)

    def get_queryset(self, request):
        successful_imports = Q(import_batches__added_count__gt=0)
        return super().get_queryset(request).annotate(
            _has_transaction_data=Exists(Transaction.objects.filter(user_id=OuterRef("pk"), is_deleted=False)),
            _successful_import_count=Count("import_batches", filter=successful_imports, distinct=True),
            _undone_import_count=Count(
                "import_batches",
                filter=successful_imports & Q(import_batches__undone_at__isnull=False),
                distinct=True,
            ),
            _last_import_at=Max("import_batches__created_at", filter=successful_imports),
        )

    @admin.display(description="Registered (LT time)", ordering="date_joined")
    def registered_display(self, obj):
        return _lithuanian_datetime(obj.date_joined)

    @admin.display(description="Last app activity (LT time)", ordering="last_active_at", empty_value="Not recorded yet")
    def last_active_display(self, obj):
        return _lithuanian_datetime(obj.last_active_at)

    @admin.display(description="Last login (LT time)", ordering="last_login")
    def last_login_display(self, obj):
        return _lithuanian_datetime(obj.last_login)

    @admin.display(boolean=True, description="Has transaction data", ordering="_has_transaction_data")
    def has_transaction_data(self, obj):
        return obj._has_transaction_data

    @admin.display(description="Successful imports (incl. undone)", ordering="_successful_import_count")
    def successful_import_count(self, obj):
        return obj._successful_import_count

    @admin.display(description="Undone successful imports", ordering="_undone_import_count")
    def undone_import_count(self, obj):
        return obj._undone_import_count

    @admin.display(description="Last successful import (LT time)", ordering="_last_import_at")
    def last_import_display(self, obj):
        return _lithuanian_datetime(obj._last_import_at)
