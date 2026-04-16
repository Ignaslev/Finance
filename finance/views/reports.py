from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from datetime import datetime, timedelta, date as _date
from decimal import Decimal
from calendar import monthrange
from collections import defaultdict
import json
import re

from finance.models import Transaction, Category, MoneySource, AdvisorReport, BalanceSnapshot, UserProfile, SubscriptionDecision
from finance.services import _advisor_build_payload, _advisor_call_model
# Move _reconcile_global to utils or keep here if private
from finance.utils import _reconcile_global, _normalize_merchant, looks_like_self_transfer
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

SUBSCRIPTIONS_CATEGORY_NAME = "Subscriptions"
SUBSCRIPTION_IGNORE_TERMS = (
    "atm", "bank", "bankas", "cash", "withdraw", "withdrawal",
    "brink", "brinks", "transfer", "paved", "mokej", "mokėj",
)

SUBSCRIPTION_CANONICAL_LABELS = {
    "spotify": "Spotify",
    "netflix": "Netflix",
    "hostinger": "Hostinger",
    "openai": "OpenAI",
    "claude": "Claude",
    "pildyk.lt": "pildyk.lt",
    "seb bankas": "SEB bankas",
    "disney plus": "Disney Plus",
    "crunchyroll": "Crunchyroll",
    "railway": "Railway",
    "google play apps": "Google Play Apps",
    "google one": "Google One",
}

SUBSCRIPTION_ALIAS_RULES = [
    (r"\bspotify\b", "spotify"),
    (r"\bnetflix\b", "netflix"),
    (r"\bhostinger\b", "hostinger"),
    (r"\bopenai\b|\bchatgpt\b", "openai"),
    (r"\bclaude\b", "claude"),
    (r"\bpildyk\b", "pildyk.lt"),
    (r"\bseb\b", "seb bankas"),
    (r"\bdisney\b", "disney plus"),
    (r"\bcrunchyroll\b", "crunchyroll"),
    (r"\brailway\b", "railway"),
    (r"\bgoogle one\b", "google one"),
    (r"\bgoogle play\b", "google play apps"),
]

def _canonical_subscription_merchant(raw_merchant: str) -> str:
    norm = _normalize_merchant(raw_merchant or "")
    if not norm:
        return ""

    for pattern, canonical in SUBSCRIPTION_ALIAS_RULES:
        if re.search(pattern, norm):
            return canonical

    # Strip random statement suffixes / ids that often split one real service
    norm = re.sub(r"\b[a-z]*\d+[a-z0-9]*\b", " ", norm)
    norm = re.sub(r"\b[a-z0-9]{8,}\b", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()

    return norm


def _subscription_display_name(canonical: str, fallback: str = "") -> str:
    return SUBSCRIPTION_CANONICAL_LABELS.get(canonical, fallback or canonical.title())

def _tx_is_subscription_category(tx) -> bool:
    return (
        (tx.category_fk and tx.category_fk.name == SUBSCRIPTIONS_CATEGORY_NAME)
        or (tx.category == SUBSCRIPTIONS_CATEGORY_NAME)
    )


def _subscription_month_key(d):
    return (d.year, d.month)


def _subscription_is_active(last_paid, today):
    this_month_start = today.replace(day=1)
    prev_month_end = this_month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    return last_paid >= prev_month_start


def _latest_nonempty_merchant(items):
    for tx in reversed(items):
        if (tx.merchant or "").strip():
            return tx.merchant.strip()
    return ""


def _build_subscription_row(normalized_merchant, items, display_name=""):
    items = sorted(items, key=lambda t: (t.date, t.id))
    months = sorted({_subscription_month_key(t.date) for t in items})
    latest_amount = items[-1].amount or Decimal("0")
    total_spent = sum((t.amount or Decimal("0")) for t in items)

    return {
        "normalized_merchant": normalized_merchant,
        "name": display_name or _latest_nonempty_merchant(items) or normalized_merchant,
        "monthly_cost": latest_amount,
        "months_subscribed": len(months),
        "first_paid": items[0].date,
        "last_paid": items[-1].date,
        "total_spent": total_spent,
        "tx_count": len(items),
    }


def _looks_like_non_subscription(user, normalized_merchant, raw_merchant):
    nm = (normalized_merchant or "").lower()
    raw = (raw_merchant or "").lower()

    if not nm:
        return True

    if any(term in nm for term in SUBSCRIPTION_IGNORE_TERMS):
        return True

    first_name = (user.first_name or "").strip()
    last_name = (user.last_name or "").strip()
    if first_name and last_name and looks_like_self_transfer(raw_merchant or "", first_name, last_name):
        return True

    return False


def _is_strong_subscription_candidate(user, normalized_merchant, items):
    if _looks_like_non_subscription(user, normalized_merchant, _latest_nonempty_merchant(items)):
        return False

    items = sorted(items, key=lambda t: (t.date, t.id))
    distinct_months = sorted({_subscription_month_key(t.date) for t in items})

    if len(distinct_months) < 2:
        return False

    if len(items) == 2:
        gap = (items[1].date - items[0].date).days
        return 20 <= gap <= 40

    gaps = [(curr.date - prev.date).days for prev, curr in zip(items, items[1:])]
    monthlyish = sum(1 for g in gaps if 20 <= g <= 40)
    ratio = (monthlyish / len(gaps)) if gaps else 0.0

    return ratio >= 0.5


def _build_tracked_subscriptions(user, base_qs, today):
    decisions = {
        d.normalized_merchant: d
        for d in SubscriptionDecision.objects.filter(
            user=user,
            decision=SubscriptionDecision.DECISION_TRACK,
        )
    }

    groups = defaultdict(list)

    txs = list(
        base_qs.filter(in_out=Transaction.OUT)
        .exclude(merchant__isnull=True)
        .exclude(merchant="")
        .select_related("category_fk")
        .order_by("date", "id")
    )

    for tx in txs:
        norm = _canonical_subscription_merchant(tx.merchant or "")
        if not norm:
            continue

        if _tx_is_subscription_category(tx) or norm in decisions:
            groups[norm].append(tx)

    active_rows = []
    past_rows = []

    for norm, items in groups.items():
        decision = decisions.get(norm)
        display_name = (
                (decision.display_name if decision and decision.display_name else "")
                or _subscription_display_name(norm, _latest_nonempty_merchant(items))
        )
        row = _build_subscription_row(norm, items, display_name=display_name)

        if _subscription_is_active(row["last_paid"], today):
            active_rows.append(row)
        else:
            past_rows.append(row)

    active_rows.sort(key=lambda r: (-r["monthly_cost"], r["name"].lower()))
    past_rows.sort(key=lambda r: (r["last_paid"], r["name"].lower()), reverse=True)

    summary = {
        "active_count": len(active_rows),
        "monthly_total": sum((r["monthly_cost"] for r in active_rows), Decimal("0")),
        "active_total_spent": sum((r["total_spent"] for r in active_rows), Decimal("0")),
        "past_total_spent": sum((r["total_spent"] for r in past_rows), Decimal("0")),
    }

    return active_rows, past_rows, summary


def _build_found_subscription_candidates(user, base_qs):
    track_set = set(
        SubscriptionDecision.objects.filter(
            user=user,
            decision=SubscriptionDecision.DECISION_TRACK,
        ).values_list("normalized_merchant", flat=True)
    )
    ignore_set = set(
        SubscriptionDecision.objects.filter(
            user=user,
            decision=SubscriptionDecision.DECISION_IGNORE,
        ).values_list("normalized_merchant", flat=True)
    )

    groups = defaultdict(list)

    txs = list(
        base_qs.filter(in_out=Transaction.OUT)
        .exclude(merchant__isnull=True)
        .exclude(merchant="")
        .select_related("category_fk")
        .order_by("date", "id")
    )

    for tx in txs:
        if _tx_is_subscription_category(tx):
            continue

        norm = _canonical_subscription_merchant(tx.merchant or "")
        if not norm:
            continue

        if norm in track_set or norm in ignore_set:
            continue

        groups[norm].append(tx)

    rows = []
    for norm, items in groups.items():
        if not _is_strong_subscription_candidate(user, norm, items):
            continue

        row = _build_subscription_row(
            norm,
            items,
            display_name=_subscription_display_name(norm, _latest_nonempty_merchant(items)),
        )
        rows.append(row)

    rows.sort(key=lambda r: (r["last_paid"], r["months_subscribed"], r["name"].lower()), reverse=True)
    return rows


@login_required
def statistics(request):
    user = request.user
    today = timezone.localtime().date()

    # Preference: exclude 15% tax from investment values (display only, not portfolio page)
    prof, _created = UserProfile.objects.get_or_create(user=user)
    tax_on = bool(prof.exclude_investment_tax)
    tax_factor = Decimal("0.85") if tax_on else Decimal("1.0")

    # ==========================================
    # 1. RUNWAY SIMULATOR (New Logic)
    # ==========================================
    # We need these for the simulator modal
    all_sources_sim = MoneySource.objects.filter(user=user, is_active=True).order_by('type', 'name')
    all_cats_sim = Category.objects.filter(user=user).order_by('name')

    is_simulated = request.GET.get('runway_sim') == '1'

    if is_simulated:
        inc_src_ids = {int(x) for x in request.GET.getlist('inc_src') if x.isdigit()}
        inc_cat_ids = {int(x) for x in request.GET.getlist('inc_cat') if x.isdigit()}
        inc_uncat = request.GET.get('inc_uncat') == '1'
    else:
        # Default: Include everything
        inc_src_ids = {s.id for s in all_sources_sim}
        inc_cat_ids = {c.id for c in all_cats_sim}
        inc_uncat = True

    # Calculate Net Worth (Filtered)
    total_net_worth = Decimal("0")
    for acc in all_sources_sim:
        if acc.id in inc_src_ids:
            bal = acc.manual_balance if acc.manual_balance is not None else Decimal("0")

            # Apply tax factor ONLY to investment values, and only when positive
            if tax_on and acc.type == "investment" and bal > 0:
                bal = bal * tax_factor

            total_net_worth += bal

    # Calculate Burn Rate (Filtered, Last 90 Days)
    start_90 = today - timedelta(days=90)
    spend_qs = Transaction.objects.filter(user=user, is_deleted=False, in_out=Transaction.OUT, date__gte=start_90)

    # Exclude unchecked categories
    spend_qs = spend_qs.exclude(category_fk__id__in=list(set(c.id for c in all_cats_sim) - inc_cat_ids))
    if not inc_uncat:
        spend_qs = spend_qs.exclude(category_fk__isnull=True)

    recent_spend = spend_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    avg_monthly_burn = recent_spend / Decimal("3.0")

    if avg_monthly_burn > 0:
        runway_months = total_net_worth / avg_monthly_burn
    else:
        runway_months = Decimal("999")

    # Month-over-Month Delta (Raw Reality Check)
    this_month_start = today.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    base = Transaction.objects.filter(user=user, is_deleted=False)

    mom_this = base.filter(in_out=Transaction.OUT, date__gte=this_month_start).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    mom_last = base.filter(in_out=Transaction.OUT, date__gte=last_month_start, date__lte=last_month_end).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    mom_diff = mom_this - mom_last

    # ==========================================
    # 2. EXISTING STATISTICS LOGIC (Restored 1:1)
    # ==========================================

    if not base.exists():
        return render(request, "statistics.html", {
            "empty_state": True,

            # Preference flag
            "exclude_investment_tax": tax_on,

            # Pass Runway vars even on empty state
            "runway_months": float(runway_months),
            "avg_monthly_burn": float(avg_monthly_burn),
            "mom_diff": float(mom_diff),
            "all_sources_sim": all_sources_sim,
            "all_cats_sim": all_cats_sim,
            "inc_src_ids": list(inc_src_ids),
            "inc_cat_ids": list(inc_cat_ids),
            "inc_uncat": inc_uncat,
            "is_simulated": is_simulated,
        })

    # Lifetime stats
    total_in = base.filter(in_out=Transaction.IN).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    total_out = base.filter(in_out=Transaction.OUT).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    lifetime_net = total_in - total_out
    total_tx = base.count()

    by_month = (
        base.annotate(m=TruncMonth("date"))
        .values("m", "in_out")
        .annotate(total=Sum("amount"))
    )

    def _mk(val):
        if isinstance(val, datetime):
            d = val.date()
            return _date(d.year, d.month, 1)
        if isinstance(val, _date):
            return _date(val.year, val.month, 1)
        return None

    month_map_in, month_map_out = {}, {}
    months_set = set()
    for r in by_month:
        mk = _mk(r["m"])
        if not mk:
            continue
        months_set.add(mk)
        if r["in_out"] == Transaction.IN:
            month_map_in[mk] = (month_map_in.get(mk, Decimal("0")) + (r["total"] or Decimal("0")))
        else:
            month_map_out[mk] = (month_map_out.get(mk, Decimal("0")) + (r["total"] or Decimal("0")))
    months_sorted = sorted(months_set)
    months_count = len(months_sorted) or 1
    avg_month_in = sum(month_map_in.get(m, Decimal("0")) for m in months_sorted) / months_count
    avg_month_out = sum(month_map_out.get(m, Decimal("0")) for m in months_sorted) / months_count

    month_nets = []
    for m in months_sorted:
        net = (month_map_in.get(m, Decimal("0")) - month_map_out.get(m, Decimal("0")))
        month_nets.append((m, net))
    best_month = max(month_nets, key=lambda x: x[1]) if month_nets else None
    worst_month = min(month_nets, key=lambda x: x[1]) if month_nets else None

    largest_tx = (
        base.filter(in_out=Transaction.OUT)
        .order_by("-amount")
        .values("id", "date", "merchant", "amount", "currency")
        .first()
    )
    distinct_merchants = base.exclude(merchant="").values("merchant").distinct().count()
    most_freq = (
        base.exclude(merchant="")
        .values("merchant")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")
        .first()
    )

    total_categorizable = base.count()
    categorized = base.filter(category_fk__isnull=False).count()
    coverage_pct = (categorized / total_categorizable * 100.0) if total_categorizable else 0.0

    active_subscriptions, past_subscriptions, subscriptions_summary = _build_tracked_subscriptions(user, base, today)
    found_subscription_candidates = _build_found_subscription_candidates(user, base)

    # Category share range picker (YOUR ORIGINAL LOGIC)
    all_months = sorted({_mk(x) for x in base.values_list("date", flat=True) if _mk(x) is not None})

    def key_from_date(d: _date) -> str:
        return d.strftime("%Y-%m")

    def month_start_from_key(k: str) -> _date:
        y, m = map(int, k.split("-"))
        return _date(y, m, 1)

    def month_end_from_key(k: str) -> _date:
        y, m = map(int, k.split("-"))
        return _date(y, m, monthrange(y, m)[1])

    this_month_key = key_from_date(_date(today.year, today.month, 1))
    months_keys = [key_from_date(m) for m in all_months]

    default_end_key = None
    for k in reversed(months_keys):
        if k != this_month_key:
            default_end_key = k
            break
    if not default_end_key and months_keys:
        default_end_key = months_keys[-1]
    default_start_key = default_end_key

    start_key = (request.GET.get("start_month") or default_start_key)
    end_key = (request.GET.get("end_month") or default_end_key)
    import re as _re
    def is_valid_key(k):
        return isinstance(k, str) and _re.match(r"^\d{4}-\d{2}$", k)

    if not is_valid_key(start_key):
        start_key = default_start_key
    if not is_valid_key(end_key):
        end_key = default_end_key

    start_date = month_start_from_key(start_key)
    end_date = month_end_from_key(end_key)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
        start_key, end_key = end_key, start_key
    months_in_range = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    if months_in_range < 1:
        months_in_range = 1

    all_categories = list(Category.objects.filter(user=user).order_by("name").values("id", "name"))
    selected_cat_ids = {int(x) for x in request.GET.getlist("cats") if str(x).isdigit()}
    include_uncat = request.GET.get("include_uncat") == "1"
    if not selected_cat_ids:
        selected_cat_ids = {c["id"] for c in all_categories}
    cat_q = Q(category_fk__in=selected_cat_ids)
    if include_uncat:
        cat_q = cat_q | Q(category_fk__isnull=True)

    per_cat = (
        base.filter(in_out=Transaction.OUT, date__gte=start_date, date__lte=end_date)
        .filter(cat_q)
        .values("category_fk", "category_fk__name", "category")
        .annotate(total=Sum("amount"), cnt=Count("id"))
        .order_by("-total")
    )

    share_total = sum((r["total"] or Decimal("0")) for r in per_cat) or Decimal("0")
    cat_labels = []
    cat_values = []
    for r in per_cat:
        name = r["category_fk__name"] or r.get("category") or "Uncategorized"
        cat_labels.append(name)
        cat_values.append(float((r["total"] or Decimal("0")) / share_total) if share_total else 0.0)

    caps_by_id = {c.id: (c.monthly_cap or Decimal("0")) for c in Category.objects.filter(user=user)}
    cat_summary_rows = []
    for r in per_cat:
        total = r["total"] or Decimal("0")
        cnt = int(r["cnt"] or 0)
        avg = (total / cnt) if cnt else Decimal("0")
        avg_month = (total / months_in_range) if months_in_range else Decimal("0")
        cat_id = r["category_fk"]
        cap_monthly = caps_by_id.get(cat_id, Decimal("0")) if cat_id else Decimal("0")
        has_cap = (cat_id is not None) and (caps_by_id.get(cat_id) is not None) and (cap_monthly > 0)
        cap_total = (cap_monthly * months_in_range) if has_cap else None
        delta = (cap_total - total) if has_cap else None
        cat_summary_rows.append({
            "cat_id": cat_id if cat_id is not None else "",
            "cat_name": r["category_fk__name"] or r.get("category") or "Uncategorized",
            "total": float(total),
            "count": cnt,
            "avg": float(avg),
            "avg_month": float(avg_month),
            "has_cap": has_cap,
            "cap_total": float(cap_total) if has_cap else None,
            "delta": float(delta) if has_cap else None,
        })

    last90_start = today - timedelta(days=89)
    wday_totals = [Decimal("0")] * 7
    qs_wday = base.filter(in_out=Transaction.OUT, date__gte=last90_start, date__lte=today).filter(cat_q).only("date", "amount")
    for t in qs_wday:
        wday_totals[t.date.weekday()] += (t.amount or Decimal("0"))
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_values = [float(x) for x in wday_totals]

    ctx = {
        # Preference flag
        "exclude_investment_tax": tax_on,

        # Runway Vars
        "runway_months": float(runway_months),
        "avg_monthly_burn": float(avg_monthly_burn),
        "mom_diff": float(mom_diff),
        "all_sources_sim": all_sources_sim,
        "all_cats_sim": all_cats_sim,
        "inc_src_ids": list(inc_src_ids),
        "inc_cat_ids": list(inc_cat_ids),
        "inc_uncat": inc_uncat,
        "is_simulated": is_simulated,

        # Standard Stats
        "total_in": float(total_in),
        "total_out": float(total_out),
        "lifetime_net": float(lifetime_net),
        "avg_month_in": float(avg_month_in),
        "avg_month_out": float(avg_month_out),
        "best_month": best_month[0].strftime("%Y-%m") if best_month else None,
        "best_month_net": float(best_month[1]) if best_month else None,
        "worst_month": worst_month[0].strftime("%Y-%m") if worst_month else None,
        "worst_month_net": float(worst_month[1]) if worst_month else None,
        "largest_tx": largest_tx,
        "total_tx": total_tx,
        "distinct_merchants": distinct_merchants,
        "most_freq_merchant": most_freq["merchant"] if most_freq else None,
        "most_freq_merchant_cnt": int(most_freq["cnt"]) if most_freq else None,
        "coverage_pct": round(coverage_pct, 1),

        "active_subscriptions": active_subscriptions,
        "past_subscriptions": past_subscriptions,
        "subscriptions_summary": subscriptions_summary,
        "found_subscriptions_count": len(found_subscription_candidates),

        "available_month_keys": months_keys,
        "start_key": start_key,
        "end_key": end_key,

        "cat_labels_json": json.dumps(cat_labels),
        "cat_values_json": json.dumps(cat_values),
        "share_note": f"Share of total spending from {start_key} to {end_key}.",

        "cat_summary_rows": cat_summary_rows,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),

        "weekday_labels_json": json.dumps(weekday_labels),
        "weekday_values_json": json.dumps(weekday_values),

        "last90_from": last90_start.strftime("%Y-%m-%d"),
        "last90_to": today.strftime("%Y-%m-%d"),

        "all_categories": all_categories,
        "selected_cat_ids": list(selected_cat_ids),
        "include_uncat": include_uncat,
    }
    return render(request, "statistics.html", ctx)


@login_required
def review_subscription_candidates(request):
    base = Transaction.objects.filter(user=request.user, is_deleted=False)
    rows = _build_found_subscription_candidates(request.user, base)

    try:
        per = max(5, min(200, int(request.GET.get("per") or 50)))
    except (TypeError, ValueError):
        per = 50

    paginator = Paginator(rows, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "review_subscriptions.html", {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
    })


@login_required
@require_POST
def review_subscription_candidates_apply(request):
    changes_raw = request.POST.get("decisions_json")
    if not changes_raw:
        messages.info(request, "No changes to apply.")
        return redirect("review_subscription_candidates")

    try:
        mapping = json.loads(changes_raw)
        if not isinstance(mapping, dict):
            mapping = {}
    except Exception:
        messages.error(request, "Invalid data format.")
        return redirect("review_subscription_candidates")

    if not mapping:
        messages.info(request, "No changes selected.")
        return redirect("review_subscription_candidates")

    applied = 0

    for norm, payload in mapping.items():
        if not isinstance(payload, dict):
            continue

        decision = (payload.get("decision") or "").strip()
        display_name = (payload.get("display_name") or "").strip()[:255]

        if decision not in {
            SubscriptionDecision.DECISION_TRACK,
            SubscriptionDecision.DECISION_IGNORE,
        }:
            continue

        SubscriptionDecision.objects.update_or_create(
            user=request.user,
            normalized_merchant=norm,
            defaults={
                "decision": decision,
                "display_name": display_name,
            },
        )
        applied += 1

    if applied:
        messages.success(request, f"Applied {applied} subscription decision(s).")
    else:
        messages.info(request, "Nothing changed.")

    return redirect("review_subscription_candidates")


@login_required
def reports(request):
    """
    Reports page:
    1. Master Month Picker (filtered by User Join Date).
    2. Monthly Report (for that month).
    3. Weekly Report (select a week WITHIN that month).
    """
    user = request.user
    # 1. Determine date range (From Join Date -> Today)
    join_date = user.date_joined.date()
    start_date = join_date.replace(day=1)  # Start from the 1st of their join month

    # Get all transaction dates to ensure we have data, but clip to join_date
    base = Transaction.objects.filter(user=user, is_deleted=False, date__gte=start_date)

    # Build list of available months
    # If no transactions yet, default to current month
    months = sorted({_date(d.year, d.month, 1) for d in base.values_list("date", flat=True)})
    if not months:
        today = timezone.localdate()
        months = [_date(today.year, today.month, 1)]

    month_keys = [m.strftime("%Y-%m") for m in months]

    # 2. Handle Selection (Default to latest available month)
    sel_m = request.GET.get("m")
    if sel_m not in month_keys:
        sel_m = month_keys[-1]

    try:
        y, m = map(int, sel_m.split("-"))
        m_start = _date(y, m, 1)
        m_end = _date(y, m, monthrange(y, m)[1])
    except Exception:
        # Fallback
        m_start = timezone.localdate().replace(day=1)
        m_end = _date(m_start.year, m_start.month, monthrange(m_start.year, m_start.month)[1])

    # 3. Fetch Monthly Report
    monthly_report = AdvisorReport.objects.filter(
        user=user, type=AdvisorReport.TYPE_MONTHLY,
        period_start=m_start, period_end=m_end
    ).first()

    # 4. Calculate Weeks for THIS selected month
    def _iter_weeks_in_month(year: int, month: int):
        # Standard ISO-like weeks (Mon-Sun) that overlap this month
        first = _date(year, month, 1)
        last = _date(year, month, monthrange(year, month)[1])

        # Start at the Monday of the first week
        curr = first - timedelta(days=first.weekday())

        while curr <= last:
            w_end = curr + timedelta(days=6)
            # We only care if the week overlaps the month somewhat,
            # but usually reports are strictly cut?
            # Let's use the strict "Monday of the week" as the key.
            # To be safe, clip the query range to the month or keep full week?
            # Usually full week is better for context.
            yield (curr, w_end)
            curr += timedelta(days=7)

    week_ranges = list(_iter_weeks_in_month(y, m))

    # Select specific week (default to first week of month, or none?)
    sel_w_start_str = request.GET.get("wstart")
    sel_w_start = None
    sel_w_end = None

    if sel_w_start_str:
        try:
            sel_w_start = datetime.strptime(sel_w_start_str, "%Y-%m-%d").date()
            sel_w_end = sel_w_start + timedelta(days=6)
        except Exception:
            pass

    # Default: If no week selected, don't auto-load one, or load the first one?
    # Let's auto-load the first week of that month to avoid empty state
    if not sel_w_start and week_ranges:
        sel_w_start, sel_w_end = week_ranges[0]

    weekly_report = None
    if sel_w_start:
        weekly_report = AdvisorReport.objects.filter(
            user=user, type=AdvisorReport.TYPE_WEEKLY,
            period_start=sel_w_start, period_end=sel_w_end
        ).first()

    # Persistent anomalies history
    anomaly_history = _reconcile_global(user)

    ctx = {
        "month_keys": month_keys,
        "sel_m": sel_m,
        "monthly_report": monthly_report,

        "week_ranges": [{"start": s.strftime("%Y-%m-%d"), "end": e.strftime("%Y-%m-%d")} for (s, e) in week_ranges],
        "sel_w_start": sel_w_start.strftime("%Y-%m-%d") if sel_w_start else "",
        "weekly_report": weekly_report,

        "anomaly_history": anomaly_history,
        "has_any_anomalies": any(s.get("is_anomaly") for s in anomaly_history),
    }
    return render(request, "reports.html", ctx)

@login_required
@require_http_methods(["POST"])
def reports_generate(request):
    """
    POST:
      - type = 'monthly' or 'weekly'
      - start = YYYY-MM-01 (monthly) or YYYY-MM-DD (weekly start)
    """
    rtype = (request.POST.get("type") or "").strip()
    start_str = (request.POST.get("start") or "").strip()

    if rtype not in (AdvisorReport.TYPE_MONTHLY, AdvisorReport.TYPE_WEEKLY):
        messages.error(request, "Invalid report type.")
        return redirect("reports")

    try:
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
    except Exception:
        messages.error(request, "Invalid start date.")
        return redirect("reports")

    if rtype == AdvisorReport.TYPE_MONTHLY:
        end = _date(start.year, start.month, monthrange(start.year, start.month)[1])
        qargs = f"?m={start.strftime('%Y-%m')}"
    else:
        end = min(start + timedelta(days=6), _date(start.year, start.month, monthrange(start.year, start.month)[1]))
        qargs = f"?wmonth={start.strftime('%Y-%m')}&wstart={start.strftime('%Y-%m-%d')}"

    report, created = AdvisorReport.objects.get_or_create(
        user=request.user, type=rtype, period_start=start, period_end=end,
        defaults={"payload": {}, "response": {}}
    )
    if not created and report.response:
        messages.info(request, "Report already exists.")
        return redirect("/reports/" + qargs)

    prev = (AdvisorReport.objects
            .filter(user=request.user, type=rtype)
            .exclude(id=report.id)
            .order_by("-created_at")
            .first())
    if prev and report.previous_id != prev.id:
        report.previous = prev
        report.save(update_fields=["previous"])

    payload = _advisor_build_payload(request.user, rtype, start, end)
    response = _advisor_call_model(payload)

    report.payload = payload
    report.response = response
    report.save(update_fields=["payload", "response"])

    messages.success(request, f"{rtype.title()} report generated for {start} – {end}.")
    return redirect("/reports/" + qargs)
