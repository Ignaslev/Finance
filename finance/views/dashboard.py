from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from collections import defaultdict
from datetime import timedelta, datetime, date as _date
from decimal import Decimal
from calendar import monthrange
import json, os

from finance.models import MoneySource, Transaction, BalanceSnapshot, PortfolioSnapshot, Category, SavingsGoal
from finance.utils import _ledger_balance_by_source # You might need to move this to utils too

def env_check(request):
    ok = bool(os.getenv("OPENAI_API_KEY"))
    return HttpResponse("OPENAI_API_KEY loaded: " + ("YES" if ok else "NO"))

def home(request):
    return HttpResponse("It works")

@login_required
def overview(request):
    # 1. ACCOUNTS & COMPOSITION
    # We need to calculate "Live Balance":
    # Live = Manual_Anchor + (Income_Since_Anchor - Spending_Since_Anchor)

    accounts = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("type", "name"))

    comp_totals = defaultdict(Decimal)
    total_net_worth = Decimal("0")

    for acc in accounts:
        # 1. Determine Anchor
        if acc.manual_balance is not None:
            anchor_val = acc.manual_balance
            # If we have a timestamp for the manual set, use it. Else assume really old.
            anchor_date = acc.balance_updated_at or datetime.min.replace(tzinfo=timezone.utc)
        else:
            anchor_val = Decimal("0")
            anchor_date = datetime.min.replace(tzinfo=timezone.utc)

        # 2. Calculate Delta since Anchor (Only for Non-Investment accounts)
        # Investment accounts are auto-calculated by the asset engine, so we trust manual_balance.
        if acc.type == 'investment':
            live_balance = anchor_val
        else:
            # Sum transactions strictly AFTER the anchor update
            delta_qs = Transaction.objects.filter(
                user=request.user,
                money_source=acc,
                is_deleted=False,
                created_at__gt=anchor_date  # Use created_at for precision vs manual entry time
            ).aggregate(
                inc=Sum('amount', filter=Q(in_out='in')),
                out=Sum('amount', filter=Q(in_out='out'))
            )
            plus = delta_qs['inc'] or Decimal("0")
            minus = delta_qs['out'] or Decimal("0")
            live_balance = anchor_val + plus - minus

        acc.effective_balance = live_balance

        # 3. Add to Totals
        if live_balance > 0:
            comp_totals[acc.type] += live_balance
            total_net_worth += live_balance
        elif live_balance < 0:
            total_net_worth += live_balance

    # Composition Bar
    composition_bar = []
    if total_net_worth > 0:
        type_colors = {'bank': '#3182ce', 'savings': '#2b6cb0', 'cash': '#38a169', 'investment': '#805ad5'}
        type_labels = dict(MoneySource.TYPE_CHOICES)
        for k, val in comp_totals.items():
            pct = (val / total_net_worth) * 100
            composition_bar.append({
                'type': k,
                'label': type_labels.get(k, k.title()),
                'value': float(val),
                'pct': float(pct),
                'color': type_colors.get(k, '#cbd5e0')
            })
        composition_bar.sort(key=lambda x: x['value'], reverse=True)

    # 2. HISTORY GRAPH (Unified)
    days_to_graph = 90
    start_date = timezone.now().date() - timedelta(days=days_to_graph)

    bal_snaps = BalanceSnapshot.objects.filter(user=request.user, timestamp__date__gte=start_date).order_by('timestamp')
    port_snaps = PortfolioSnapshot.objects.filter(user=request.user, timestamp__date__gte=start_date).order_by(
        'timestamp')

    history_map = {}

    # Fill Cash History
    for b in bal_snaps:
        d = b.timestamp.date() if hasattr(b.timestamp, 'date') else b.timestamp
        if d not in history_map: history_map[d] = {'cash': 0, 'assets': 0}
        history_map[d]['cash'] = b.amount

    # Fill Asset History
    for p in port_snaps:
        d = p.timestamp.date() if hasattr(p.timestamp, 'date') else p.timestamp
        if d not in history_map: history_map[d] = {'cash': 0, 'assets': 0}
        history_map[d]['assets'] = p.total

    graph_dates = []
    graph_values = []

    if history_map:
        min_d = min(history_map.keys())
        max_d = timezone.now().date()
        delta = max_d - min_d
        last_cash = Decimal("0")
        last_assets = Decimal("0")

        for i in range(delta.days + 1):
            d = min_d + timedelta(days=i)
            if d in history_map:
                if history_map[d]['cash'] > 0: last_cash = history_map[d]['cash']
                if history_map[d]['assets'] > 0: last_assets = history_map[d]['assets']

            day_total = last_cash + last_assets
            if day_total > 0:
                graph_dates.append(d.strftime("%b %d"))
                graph_values.append(float(day_total))

    if not graph_values:
        graph_dates = ["Now"]
        graph_values = [float(total_net_worth)]

    # 3. INCOME VS SPENDING
    tx_base = Transaction.objects.filter(user=request.user, is_deleted=False)
    qs_month = tx_base.annotate(month=TruncMonth("date"))
    by_month = qs_month.values("month", "in_out").annotate(total=Sum("amount"))

    months_set = set()
    for row in by_month:
        if row["month"]:
            val = row["month"]
            if hasattr(val, 'date'): val = val.date()
            months_set.add(val.replace(day=1))

    months = sorted(months_set)
    labels = [m.strftime("%Y-%m") for m in months]
    totals_in = {m: Decimal("0") for m in months}
    totals_out = {m: Decimal("0") for m in months}

    for row in by_month:
        if not row["month"]: continue
        val = row["month"]
        if hasattr(val, 'date'): val = val.date()
        mk = val.replace(day=1)
        amt = row["total"] or Decimal("0")
        if row["in_out"] == Transaction.IN:
            totals_in[mk] += amt
        else:
            totals_out[mk] += amt

    income_series = [float(totals_in[m]) for m in months]
    spending_series = [float(totals_out[m]) for m in months]
    net_rows = [{"month": m.strftime("%Y-%m"), "net": float(totals_in[m] - totals_out[m])} for m in months]

    # 4. CATEGORIES & BUDGETS
    qs_cat = (
        tx_base.filter(in_out=Transaction.OUT, category_fk__isnull=False)
        .annotate(month=TruncMonth("date"))
        .values("month", "category_fk__name")
        .annotate(total=Sum("amount"))
    )
    cat_months_set, cat_names_set = set(), set()
    for row in qs_cat:
        if row["month"]:
            val = row["month"]
            if hasattr(val, 'date'): val = val.date()
            cat_months_set.add(val.replace(day=1))
        if row["category_fk__name"]: cat_names_set.add(row["category_fk__name"])

    cat_months = sorted(set(months) | cat_months_set)
    cat_labels = [m.strftime("%Y-%m") for m in cat_months]
    cat_names = sorted(cat_names_set)

    data_map = defaultdict(lambda: {m: Decimal("0") for m in cat_months})
    for row in qs_cat:
        if not row["month"]: continue
        val = row["month"]
        if hasattr(val, 'date'): val = val.date()
        mk = val.replace(day=1)
        cname = row["category_fk__name"]
        if mk and cname:
            data_map[cname][mk] += (row["total"] or Decimal("0"))

    series_by_cat = {cname: [float(data_map[cname][m]) for m in cat_months] for cname in cat_names}

    # Merchant Breakdown
    qs_merchant = (
        tx_base.filter(in_out=Transaction.OUT, category_fk__isnull=False)
        .annotate(month=TruncMonth("date"))
        .values("month", "category_fk__name", "merchant")
        .annotate(total=Sum("amount"), tx_count=Count("id"))
    )
    breakdown_by_cat_month = {}
    for row in qs_merchant:
        if not row["month"]: continue
        val = row["month"]
        if hasattr(val, 'date'): val = val.date()
        mk = val.replace(day=1)
        month_key = mk.strftime("%Y-%m")

        cname = row["category_fk__name"] or "Other"
        merchant = (row["merchant"] or "").strip() or "—"
        total = row["total"] or Decimal("0")
        cnt = int(row["tx_count"] or 0)
        avg = (total / cnt) if cnt else Decimal("0")

        breakdown_by_cat_month.setdefault(cname, {}).setdefault(month_key, []).append({
            "merchant": merchant[:80],
            "total": float(total),
            "count": cnt,
            "avg": float(avg),
        })
    for cname, per_month in breakdown_by_cat_month.items():
        for m in per_month:
            per_month[m] = sorted(per_month[m], key=lambda x: (-x["total"], x["merchant"]))[:12]

    # Budgets
    capped_qs = Category.objects.filter(user=request.user, monthly_cap__isnull=False).exclude(monthly_cap=0).order_by(
        "name")
    budget_has_caps = capped_qs.exists()
    months_for_budgets = sorted({_date(d.year, d.month, 1) for d in tx_base.values_list("date", flat=True)})
    if not months_for_budgets:
        today = timezone.localdate()
        months_for_budgets = [_date(today.year, today.month, 1)]

    budget_month_keys = [m.strftime("%Y-%m") for m in months_for_budgets]
    budget_all = {}

    for m in months_for_budgets:
        start = _date(m.year, m.month, 1)
        end = _date(m.year, m.month, monthrange(m.year, m.month)[1])
        spent_rows = (
            tx_base.filter(in_out=Transaction.OUT, date__gte=start, date__lte=end, category_fk__in=capped_qs)
            .values("category_fk").annotate(total=Sum("amount"))
        )
        spent_map = {r["category_fk"]: (r["total"] or Decimal("0")) for r in spent_rows}
        labels_b, spent_b, caps_b = [], [], []
        for c in capped_qs:
            labels_b.append(c.name)
            caps_b.append(float(c.monthly_cap))
            spent_b.append(float(spent_map.get(c.id, Decimal("0"))))
        key = start.strftime("%Y-%m")
        budget_all[key] = {"labels": labels_b, "spent": spent_b, "caps": caps_b}

    budget_selected_key = budget_month_keys[-1] if budget_month_keys else ""

    # Goals
    eff_map = {acc.id: acc.effective_balance for acc in accounts}
    goals = []
    for g in SavingsGoal.objects.filter(user=request.user, is_active=True).prefetch_related("accounts"):
        sel = [a for a in g.accounts.all() if a.is_active]
        current = sum((eff_map.get(a.id, Decimal("0")) for a in sel), Decimal("0"))
        target = g.target_amount or Decimal("0")
        pct = float((current / target * 100) if target > 0 else 0.0)
        goals.append({
            "id": g.id, "name": g.name, "target": float(target), "current": float(current),
            "pct": pct, "eta": None, "accounts": [{"name": a.name} for a in sel]
        })

    ctx = {
        "total_net_worth": float(total_net_worth),
        "composition_bar": composition_bar,
        "balance_labels_json": json.dumps(graph_dates),
        "balance_values_json": json.dumps(graph_values),

        "accounts_with_balances": accounts,
        "total_accounts_balance": float(total_net_worth),

        "labels_json": json.dumps(labels),
        "income_json": json.dumps(income_series),
        "spending_json": json.dumps(spending_series),
        "net_rows": net_rows,

        "cat_names": cat_names,
        "cat_month_labels_json": json.dumps(cat_labels),
        "series_by_cat_json": json.dumps(series_by_cat),
        "breakdown_by_cat_month_json": json.dumps(breakdown_by_cat_month),
        "month_bounds_json": "{}",

        "goals": goals,
        "budget_all_json": json.dumps(budget_all),
        "budget_month_keys": budget_month_keys,
        "budget_selected_key": budget_selected_key,
        "budget_has_caps": budget_has_caps,

        "now_val": timezone.now(),
    }
    return render(request, "overview.html", ctx)