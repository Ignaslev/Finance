import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.utils import timezone

from finance.models import Category, MoneySource, Transaction, UserProfile
from finance.investments import current_investment_balance


@login_required
def tools(request):
    all_categories = list(Category.objects.filter(user=request.user).order_by("name"))
    base = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        is_internal_transfer=False,
        category_fk__isnull=False,
    )
    eligible_category_ids = {
        row["category_fk"]
        for row in (
            base.values("category_fk")
            .annotate(
                income_count=Count("id", filter=Q(in_out=Transaction.IN)),
                spending_count=Count("id", filter=Q(in_out=Transaction.OUT)),
            )
            .filter(income_count__gt=0, spending_count__gt=0)
        )
    }
    categories = [
        category for category in all_categories if category.id in eligible_category_ids
    ]

    requested_category = request.GET.get("category")
    selected_category = None
    if requested_category and str(requested_category).isdigit():
        selected_category = next(
            (category for category in categories if category.id == int(requested_category)),
            None,
        )
    if selected_category is None and categories:
        busiest_category = (
            base.filter(category_fk_id__in=eligible_category_ids)
            .values("category_fk")
            .annotate(transaction_count=Count("id"))
            .order_by("-transaction_count", "category_fk")
            .first()
        )
        busiest_id = busiest_category["category_fk"] if busiest_category else None
        selected_category = next(
            (category for category in categories if category.id == busiest_id),
            categories[0],
        )

    selected_summary = {
        "income": Decimal("0"),
        "spending": Decimal("0"),
        "balance": Decimal("0"),
        "transaction_count": 0,
    }
    month_labels = []
    month_income = []
    month_spending = []

    if selected_category is not None:
        selected_base = base.filter(category_fk=selected_category)
        totals = selected_base.aggregate(
            income=Sum("amount", filter=Q(in_out=Transaction.IN)),
            spending=Sum("amount", filter=Q(in_out=Transaction.OUT)),
            transaction_count=Count("id"),
        )
        income = totals["income"] or Decimal("0")
        spending = totals["spending"] or Decimal("0")
        selected_summary = {
            "income": income,
            "spending": spending,
            "balance": income - spending,
            "transaction_count": int(totals["transaction_count"] or 0),
        }
        monthly_rows = (
            selected_base
            .annotate(month=TruncMonth("date"))
            .values("month", "in_out")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )
        monthly = defaultdict(lambda: {
            Transaction.IN: Decimal("0"),
            Transaction.OUT: Decimal("0"),
        })
        for row in monthly_rows:
            if row["month"]:
                month = row["month"]
                if hasattr(month, "date"):
                    month = month.date()
                monthly[month.replace(day=1)][row["in_out"]] += row["total"] or Decimal("0")

        for month in sorted(monthly):
            income = monthly[month][Transaction.IN]
            spending = monthly[month][Transaction.OUT]
            month_labels.append(month.strftime("%Y-%m"))
            month_income.append(float(income))
            month_spending.append(float(spending))

    # Financial runway: selected assets divided by the last 90 days' monthly burn rate.
    profile, _created = UserProfile.objects.get_or_create(user=request.user)
    tax_factor = Decimal("0.85") if profile.exclude_investment_tax else Decimal("1.0")
    runway_sources = list(
        MoneySource.objects.filter(user=request.user, is_active=True)
        .prefetch_related("holdings__asset")
        .order_by("type", "name")
    )
    is_simulated = request.GET.get("runway_sim") == "1"
    if is_simulated:
        included_source_ids = {
            int(value) for value in request.GET.getlist("inc_src") if value.isdigit()
        }
        included_category_ids = {
            int(value) for value in request.GET.getlist("inc_cat") if value.isdigit()
        }
        include_uncategorized = request.GET.get("inc_uncat") == "1"
    else:
        included_source_ids = {source.id for source in runway_sources}
        included_category_ids = {category.id for category in all_categories}
        include_uncategorized = True

    total_net_worth = Decimal("0")
    for source in runway_sources:
        if source.id not in included_source_ids:
            continue
        if source.type == "investment":
            balance = current_investment_balance(source)
        else:
            balance = source.manual_balance if source.manual_balance is not None else Decimal("0")
        if profile.exclude_investment_tax and source.type == "investment" and balance > 0:
            balance *= tax_factor
        total_net_worth += balance

    today = timezone.localdate()
    spend_qs = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        is_internal_transfer=False,
        in_out=Transaction.OUT,
        date__gte=today - timedelta(days=90),
    )
    excluded_category_ids = {
        category.id for category in all_categories
    } - included_category_ids
    spend_qs = spend_qs.exclude(category_fk_id__in=excluded_category_ids)
    if not include_uncategorized:
        spend_qs = spend_qs.exclude(category_fk__isnull=True)

    recent_spend = spend_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    average_monthly_burn = recent_spend / Decimal("3.0")
    runway_months = (
        total_net_worth / average_monthly_burn
        if average_monthly_burn > 0
        else Decimal("999")
    )

    this_month_start = today.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    financial_base = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        is_internal_transfer=False,
        in_out=Transaction.OUT,
    )
    this_month_spend = (
        financial_base.filter(date__gte=this_month_start).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    last_month_spend = (
        financial_base.filter(
            date__gte=last_month_start,
            date__lte=last_month_end,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )

    return render(request, "tools.html", {
        "categories": categories,
        "selected_category": selected_category,
        "selected_summary": selected_summary,
        "chart_labels_json": json.dumps(month_labels),
        "chart_income_json": json.dumps(month_income),
        "chart_spending_json": json.dumps(month_spending),
        "runway_months": float(runway_months),
        "avg_monthly_burn": float(average_monthly_burn),
        "mom_diff": float(this_month_spend - last_month_spend),
        "all_sources_sim": runway_sources,
        "all_cats_sim": all_categories,
        "inc_src_ids": list(included_source_ids),
        "inc_cat_ids": list(included_category_ids),
        "inc_uncat": include_uncategorized,
        "is_simulated": is_simulated,
    })
