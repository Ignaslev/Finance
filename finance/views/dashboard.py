from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from collections import defaultdict
from datetime import timedelta, datetime, date as _date, timezone as dt_timezone
from decimal import Decimal
from calendar import monthrange
import json, os, re
from finance.utils import _normalize_merchant
from django.contrib.admin.views.decorators import staff_member_required
from finance.models import MoneySource, Transaction, BalanceSnapshot, PortfolioSnapshot, Category, SavingsGoal, UserProfile


@staff_member_required
def env_check(request):
    ok = bool(os.getenv("OPENAI_API_KEY"))
    return HttpResponse("OPENAI_API_KEY loaded: " + ("YES" if ok else "NO"))

@staff_member_required
def home(request):
    return HttpResponse("It works")

CHAIN_CANONICALS = [
    ("Maxima", ["MAXIMA"]),
    ("IKI", ["IKI"]),
    ("Norfa", ["NORFA"]),
    ("Lidl", ["LIDL"]),
    ("Rimi", ["RIMI"]),
    ("Barbora", ["BARBORA"]),
    ("Aibė", ["AIBE", "AIBĖ"]),
    ("Moki Veži", ["MOKI VEZI", "MOKI VEŽI"]),
    ("Senukai", ["SENUKAI"]),
    ("Depo", ["DEPO"]),
    ("Circle K", ["CIRCLE K"]),
    ("Viada", ["VIADA"]),
    ("Neste", ["NESTE"]),
    ("Bolt", ["BOLT"]),
    ("Wolt", ["WOLT"]),
    ("McDonald's", ["MCDONALD", "MCDONALDS"]),
    ("Hesburger", ["HESBURGER"]),
    ("CanCan Pizza", ["CANCAN", "CAN CAN"]),
]


def _canonical_overview_merchant(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "—"

    upper_raw = raw.upper().strip()

    # 1) Strong chain-family recognition
    for display, patterns in CHAIN_CANONICALS:
        for p in patterns:
            if upper_raw.startswith(p):
                return display

    # 2) Generic normalization for uncommon merchants
    norm = _normalize_merchant(raw or "")
    norm = (norm or "").upper().strip()
    if not norm:
        return (raw[:80] or "—")

    # Remove common legal/entity noise
    norm = re.sub(r"\b(UAB|AB|MB|VSI|VŠĮ|IĮ|II|LTD|LIMITED|OOO|AS)\b", " ", norm)

    # Remove branch/store codes like X-925, X583, A-1234
    norm = re.sub(r"\b[A-Z]-?\d{2,}\b", " ", norm)

    # Remove long trailing numeric IDs
    norm = re.sub(r"\b\d{2,}\b", " ", norm)

    # Trim punctuation noise
    norm = re.sub(r"[,;/|]+", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()

    # Remove very generic trailing location/store suffix if present after the first word
    parts = norm.split()
    if len(parts) >= 2:
        # If merchant has a clean base and noisy branch tail, keep the first 1-2 tokens
        # for safer grouping instead of merging too aggressively.
        if len(parts[0]) >= 3 and len(parts[1]) >= 2:
            # conservative fallback stem for uncommon merchants
            stem = " ".join(parts[:2])
        else:
            stem = parts[0]
    else:
        stem = norm

    stem = re.sub(r"\s+", " ", stem).strip()
    if not stem:
        stem = norm or raw

    return stem.title()

@login_required
def overview(request):
    # Preference: exclude 15% tax from investment values (display only)
    prof, _created = UserProfile.objects.get_or_create(user=request.user)
    tax_on = bool(prof.exclude_investment_tax)
    tax_factor = Decimal("0.85") if tax_on else Decimal("1.0")

    # 1. ACCOUNTS & COMPOSITION
    accounts = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("type", "name"))

    comp_totals = defaultdict(Decimal)
    total_net_worth = Decimal("0")

    for acc in accounts:
        # 1. Determine Anchor
        if acc.manual_balance is not None:
            anchor_val = acc.manual_balance
            anchor_date = acc.balance_updated_at or datetime.min.replace(tzinfo=dt_timezone.utc)
        else:
            anchor_val = Decimal("0")
            anchor_date = datetime.min.replace(tzinfo=dt_timezone.utc)

        # 2. Calculate Live Balance
        if acc.type == 'investment':
            live_balance = anchor_val
        else:
            delta_qs = Transaction.objects.filter(
                user=request.user,
                money_source=acc,
                is_deleted=False,
                created_at__gt=anchor_date
            ).aggregate(
                inc=Sum('amount', filter=Q(in_out='in')),
                out=Sum('amount', filter=Q(in_out='out'))
            )
            plus = delta_qs['inc'] or Decimal("0")
            minus = delta_qs['out'] or Decimal("0")
            live_balance = anchor_val + plus - minus

        # Apply tax factor ONLY to investment balances, and only when positive
        if tax_on and acc.type == "investment" and live_balance > 0:
            live_balance = live_balance * tax_factor

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
    port_snaps = PortfolioSnapshot.objects.filter(user=request.user, timestamp__date__gte=start_date).order_by('timestamp')

    history_map = {}

    # Fill Cash History
    for b in bal_snaps:
        d = b.timestamp.date() if hasattr(b.timestamp, 'date') else b.timestamp
        if d not in history_map:
            history_map[d] = {'cash': 0, 'assets': 0}
        history_map[d]['cash'] = b.amount

    # Fill Asset History (apply tax factor here for graph + net worth history)
    for p in port_snaps:
        d = p.timestamp.date() if hasattr(p.timestamp, 'date') else p.timestamp
        if d not in history_map:
            history_map[d] = {'cash': 0, 'assets': 0}
        assets_val = p.total
        if tax_on and assets_val > 0:
            assets_val = assets_val * tax_factor
        history_map[d]['assets'] = assets_val

    # Fallback: if there are no asset snapshots at all in the window,
    # treat current investment balances as a flat assets line (already tax-adjusted in acc.effective_balance)
    if not port_snaps.exists():
        fallback_assets = sum(
            (acc.effective_balance or Decimal("0"))
            for acc in accounts
            if acc.type == 'investment'
        )

        if fallback_assets > 0 and history_map:
            for d in history_map:
                history_map[d]['assets'] = fallback_assets

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
                if history_map[d]['cash'] > 0:
                    last_cash = history_map[d]['cash']
                if history_map[d]['assets'] > 0:
                    last_assets = history_map[d]['assets']

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
            if hasattr(val, 'date'):
                val = val.date()
            months_set.add(val.replace(day=1))

    months = sorted(months_set)
    labels = [m.strftime("%Y-%m") for m in months]
    totals_in = {m: Decimal("0") for m in months}
    totals_out = {m: Decimal("0") for m in months}

    for row in by_month:
        if not row["month"]:
            continue
        val = row["month"]
        if hasattr(val, 'date'):
            val = val.date()
        mk = val.replace(day=1)
        amt = row["total"] or Decimal("0")
        if row["in_out"] == Transaction.IN:
            totals_in[mk] += amt
        else:
            totals_out[mk] += amt

    income_series = [float(totals_in[m]) for m in months]
    spending_series = [float(totals_out[m]) for m in months]
    net_rows = [{"month": m.strftime("%Y-%m"), "net": float(totals_in[m] - totals_out[m])} for m in months]

    # 4. CATEGORIES & (caps moved into category chart)
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
            if hasattr(val, 'date'):
                val = val.date()
            cat_months_set.add(val.replace(day=1))
        if row["category_fk__name"]:
            cat_names_set.add(row["category_fk__name"])

    cat_months = sorted(set(months) | cat_months_set)
    cat_labels = [m.strftime("%Y-%m") for m in cat_months]
    cat_names = sorted(cat_names_set)

    data_map = defaultdict(lambda: {m: Decimal("0") for m in cat_months})
    for row in qs_cat:
        if not row["month"]:
            continue
        val = row["month"]
        if hasattr(val, 'date'):
            val = val.date()
        mk = val.replace(day=1)
        cname = row["category_fk__name"]
        if mk and cname:
            data_map[cname][mk] += (row["total"] or Decimal("0"))

    series_by_cat = {cname: [float(data_map[cname][m]) for m in cat_months] for cname in cat_names}

    merchant_rows = (
        tx_base.filter(in_out=Transaction.OUT, category_fk__isnull=False)
        .select_related("category_fk")
        .only("date", "merchant", "amount", "category_fk__name")
        .order_by("date", "id")
    )

    breakdown_acc = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {
        "merchant": "",
        "total": Decimal("0"),
        "count": 0,
    })))

    for t in merchant_rows:
        if not t.date:
            continue

        month_key = t.date.replace(day=1).strftime("%Y-%m")
        cname = t.category_fk.name if t.category_fk else "Other"
        merchant_display = _canonical_overview_merchant(t.merchant or "")
        merchant_key = merchant_display.lower()

        bucket = breakdown_acc[cname][month_key][merchant_key]
        bucket["merchant"] = merchant_display
        bucket["total"] += (t.amount or Decimal("0"))
        bucket["count"] += 1

    breakdown_by_cat_month = {}
    for cname, per_month in breakdown_acc.items():
        breakdown_by_cat_month[cname] = {}

        for month_key, merchants in per_month.items():
            rows = []
            for _mkey, data in merchants.items():
                cnt = int(data["count"] or 0)
                total = data["total"] or Decimal("0")
                avg = (total / cnt) if cnt else Decimal("0")

                rows.append({
                    "merchant": data["merchant"][:80],
                    "total": float(total),
                    "count": cnt,
                    "avg": float(avg),
                })

            breakdown_by_cat_month[cname][month_key] = sorted(
                rows,
                key=lambda x: (-x["total"], x["merchant"])
            )[:12]


    for cname, per_month in breakdown_by_cat_month.items():
        for m in per_month:
            per_month[m] = sorted(per_month[m], key=lambda x: (-x["total"], x["merchant"]))[:12]

    # Cap map for category chart (keyed by category name to match existing frontend keys)
    cap_by_cat = {}
    for c in Category.objects.filter(user=request.user):
        cap = c.monthly_cap or Decimal("0")
        cap_by_cat[c.name] = float(cap) if cap > 0 else 0

    # Savings goals
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
        "month_bounds_json": "{}",  # unchanged
        "cap_by_cat_json": json.dumps(cap_by_cat),

        "goals": goals,

        "now_val": timezone.now(),
    }
    return render(request, "overview.html", ctx)

