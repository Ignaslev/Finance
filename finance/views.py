# views.py — cleaned & consolidated

from django.http import HttpResponse
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction as dbtx
from django.db.models import Q, Sum, Case, When, DecimalField, F, Count
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.utils.timezone import localdate
from django.utils import timezone as _tz

import csv, io, os, json, re, hashlib
from datetime import datetime, date as _date, timedelta
from decimal import Decimal, InvalidOperation
from calendar import monthrange
from collections import defaultdict

from openai import OpenAI

from .models import (
    Transaction,
    Category,
    BalanceSnapshot,
    MoneySource,
    SavingsGoal,
    AdvisorReport,
    BalanceAnomaly,
    AiRun,          # <-- add this
    AiRunItem,
)
from django.conf import settings

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

AUTO_APPLY_THRESHOLD   = 0.80  # >= this → apply directly
AUTO_CHANGE_THRESHOLD  = 0.90  # when changing an existing AI/rule category
BATCH_SIZE             = 50

EXAMPLE_LOOKBACK_MONTHS = 12
EXAMPLES_TOTAL_CAP       = 60
EXAMPLES_PER_CATEGORY    = 5
EXAMPLES_MIN_USER        = 1

# Advisor / Reports
ADVISOR_MODEL = "gpt-4.1"
ADVISOR_TEMP  = 0
TX_SAMPLE_MAX = 350
TX_TOP_N      = 40
REC_MIN_COUNT = 3
REC_AMOUNT_JITTER = Decimal("0.08")
LEAK_MAX_AMOUNT = Decimal("7.00")
MIN_USER_LABELS = 20         # gate to unlock auto-categorization
CURATED_LABEL_TARGET = 20    # how many rows to show on “Teach AI”


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------

# --- Normalizers (re-use your existing _normalize_merchant if you have it) ---
def _normalize_text_basic(s: str) -> str:
    """
    Simple, stable normalization for description hashing:
    - lowercase
    - collapse whitespace
    - strip leading/trailing spaces
    """
    s = (s or "").lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def build_fingerprint_v2(*, date_iso: str, time_str: str | None, merchant: str,
                         amount, currency: str, in_out: str, money_source_id: int,
                         description: str | None) -> str:
    """
    New fingerprint (DB-only dedupe):
      date | time | NORMALIZED_MERCHANT | amount | currency | in_out | money_source_id | desc8
    - time is optional ('' if not present)
    - desc8 is an 8-hex digest of the first 80 normalized description characters
    """
    # Use your existing normalization if present
    try:
        norm_merchant = _normalize_merchant(merchant or "")
    except NameError:
        norm_merchant = _normalize_text_basic(merchant or "").upper()

    # Normalize & hash a short prefix of the description for stability
    norm_desc = _normalize_text_basic(description or "")
    desc_prefix = norm_desc[:80]
    desc8 = hashlib.sha1(desc_prefix.encode("utf-8")).hexdigest()[:8] if desc_prefix else ""

    tpart = (time_str or "").strip()
    # Keep amount/currency/in_out/money_source_id identical to current semantics
    return f"{date_iso}|{tpart}|{norm_merchant}|{amount}|{currency}|{in_out}|{money_source_id}|{desc8}"

def env_check(request):
    ok = bool(os.getenv("OPENAI_API_KEY"))
    return HttpResponse("OPENAI_API_KEY loaded: " + ("YES" if ok else "NO"))

def home(request):
    return HttpResponse("It works")

def ensure_default_categories(user):
    have = set(Category.objects.filter(user=user).values_list("name", flat=True))
    need = [Category(user=user, name=n) for n in settings.DEFAULT_CATEGORIES if n not in have]
    if need:
        Category.objects.bulk_create(need)


def parse_amount(raw):
    if raw is None:
        return Decimal("0")
    s = str(raw).strip().replace("€", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")

def parse_in_out(debcred_value=None, trans_type=None):
    v = (debcred_value or "").strip().upper()
    if v == "D": return "out"
    if v == "C": return "in"
    t = (trans_type or "").upper()
    if "GAVIM" in t: return "in"
    if "MOK" in t: return "out"
    return "out"

def normalize_currency(s):
    s = (s or "").strip().upper()
    return "EUR" if s in ("", "€", "EURO", "EUR") else s

def parse_date(val):
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except Exception:
            continue
    return timezone.now().date()

def parse_date_filter(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def parse_decimal_filter(s):
    s = (s or "").strip().replace("€", "").replace(",", ".")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None

def _normalize_merchant(name: str) -> str:
    if not name:
        return ""
    s = name.upper()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[#,/ ]?X[- ]?\d+$", "", s)
    s = re.sub(r"\s+\d{3,}$", "", s)
    return s

def _month_key(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        d = val.date()
        return d.replace(day=1)
    if isinstance(val, _date):
        return val.replace(day=1)
    return None

def _ledger_balance_by_source(user):
    qs = (
        Transaction.objects
        .filter(user=user, is_deleted=False)
        .values("money_source_id")
        .annotate(
            net=Sum(
                Case(
                    When(in_out=Transaction.IN, then=F("amount")),
                    When(in_out=Transaction.OUT, then=F("amount") * Decimal("-1")),
                    default=Decimal("0"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )
    )
    return {row["money_source_id"]: (row["net"] or Decimal("0")) for row in qs}

ANOMALY_EPSILON = Decimal("0.50")  # ignore < 50 cents noise; tweak as you like

def _ledger_delta_between(user, d1, d2):
    """
    Returns Decimal(income - spending) between dates [d1, d2] inclusive.
    d1, d2 are date objects (not datetimes).
    """
    from django.db.models import Sum
    inc = (Transaction.objects
           .filter(user=user, is_deleted=False, in_out=Transaction.IN, date__gte=d1, date__lte=d2)
           .aggregate(s=Sum("amount"))["s"] or Decimal("0"))
    out = (Transaction.objects
           .filter(user=user, is_deleted=False, in_out=Transaction.OUT, date__gte=d1, date__lte=d2)
           .aggregate(s=Sum("amount"))["s"] or Decimal("0"))
    return inc - out


def _maybe_log_balance_anomaly(user, prev_snap, new_snap, note="Detected after snapshot update"):
    """
    Compare account ledger delta vs. snapshot delta and log BalanceAnomaly if off.
    prev_snap, new_snap are BalanceSnapshot instances (prev may be None).
    """
    if not prev_snap:
        return  # nothing to compare

    # Use DATE window (your transactions are date-based)
    d1 = timezone.localtime(prev_snap.timestamp).date()
    d2 = timezone.localtime(new_snap.timestamp).date()
    if d2 < d1:
        d1, d2 = d2, d1

    expected = _ledger_delta_between(user, d1, d2)                 # what tx say should have happened
    actual   = (new_snap.amount or Decimal("0")) - (prev_snap.amount or Decimal("0"))
    discrepancy = actual - expected

    if discrepancy.copy_abs() >= ANOMALY_EPSILON:
        BalanceAnomaly.objects.create(
            user=user,
            snapshot_prev=prev_snap,
            snapshot_curr=new_snap,
            prev_amount=prev_snap.amount,
            curr_amount=new_snap.amount,
            tx_delta_between=expected,
            expected_curr=(prev_snap.amount or Decimal("0")) + expected,
            diff=discrepancy,
            note=note,
        )
        return discrepancy
    return None


# --- durable onboarding (session fallback if model not present) ---
try:
    from .models import OnboardingState  # optional model; if you don't have it yet, we fallback to session
except Exception:
    OnboardingState = None

def ensure_onboarding_state(user):
    if OnboardingState:
        OnboardingState.objects.get_or_create(user=user)

def onboarding_get_categories_done(request):
    if OnboardingState:
        obj = OnboardingState.objects.filter(user=request.user).first()
        return bool(obj and obj.categories_done)
    return bool(request.session.get("onboarding_categories_done"))

def onboarding_mark_categories_done(request):
    if OnboardingState:
        ensure_onboarding_state(request.user)
        obj = OnboardingState.objects.get(user=request.user)
        obj.categories_done = True
        obj.save(update_fields=["categories_done","updated_at"])
    else:
        request.session["onboarding_categories_done"] = True

def get_or_create_income_category(user):
    cat, _ = Category.objects.get_or_create(user=user, name="Income")
    return cat

# ---------------------------------------------------------------------
# AI categorization helpers
# ---------------------------------------------------------------------

def _pick_examples(user, limit=EXAMPLES_TOTAL_CAP):
    from datetime import timedelta
    lookback_start = timezone.now().date() - timedelta(days=EXAMPLE_LOOKBACK_MONTHS * 30)
    qs = (
        Transaction.objects
        .filter(user=user, date__gte=lookback_start, category_fk__isnull=False)
        .filter(category_source__in=["user","rule","ai"])
        .select_related("category_fk")
        .order_by("-date","-id")
        .only("merchant","notes","user_note","amount","in_out","category_source","date","category_fk__name")
    )[:1500]

    def gist(t):
        base = f"{(t.notes or '')} {(t.user_note or '')}".strip()
        return (base[:80] if base else "")

    src_order = ["user", "rule", "ai"]
    pool = []
    for s in src_order:
        pool.extend([t for t in qs if t.category_source == s])

    per_cat_counts, seen_keys, examples = {}, set(), []
    for t in pool:
        cat = t.category_fk.name if t.category_fk else None
        if not cat: continue
        if per_cat_counts.get(cat, 0) >= EXAMPLES_PER_CATEGORY and len(examples) < limit // 2:
            continue
        mnorm = _normalize_merchant(t.merchant or "")
        key = (mnorm, gist(t))
        if key in seen_keys:
            continue
        examples.append({
            "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}"[:240],
            "amount": float(t.amount or 0),
            "in_out": t.in_out or "",
            "category": cat,
            "source": t.category_source,
        })
        seen_keys.add(key)
        per_cat_counts[cat] = per_cat_counts.get(cat, 0) + 1
        if len(examples) >= limit:
            break

    if len(examples) < limit:
        for t in pool:
            if len(examples) >= limit: break
            cat = t.category_fk.name if t.category_fk else None
            if not cat: continue
            mnorm = _normalize_merchant(t.merchant or "")
            key = (mnorm, gist(t))
            if key in seen_keys: continue
            examples.append({
                "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}"[:240],
                "amount": float(t.amount or 0),
                "in_out": t.in_out or "",
                "category": cat,
                "source": t.category_source,
            })
            seen_keys.add(key)

    return examples

def _call_openai_rows(user, rows, examples, cats):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)

    schema = {
        "type":"object",
        "properties":{
            "results":{
                "type":"array",
                "items":{
                    "type":"object",
                    "properties":{
                        "id":{"type":"integer"},
                        "category":{"type":"string","enum":cats},
                        "confidence":{"type":"number","minimum":0,"maximum":1},
                        "reason":{"type":"string"}
                    },
                    "required":["id","category","confidence"]
                }
            }
        },
        "required":["results"]
    }

    user_locked = [e for e in examples if e.get("source") == "user"][:EXAMPLES_MIN_USER]
    example_lines = []
    if user_locked:
        e = user_locked[0]
        example_lines.append(
            f"- (LOCKED) text='{e['text']}', amount={e['amount']}, in_out={e['in_out']} => {e['category']} (source=user)"
        )
    for e in examples:
        example_lines.append(
            f"- text='{e['text']}', amount={e['amount']}, in_out={e['in_out']} => {e['category']} (source={e.get('source','')})"
        )

    msg = (
        "You are a strict finance transaction categorizer.\n"
        "Rules:\n"
        "1) Choose exactly ONE category from the provided list. Do NOT invent categories.\n"
        "2) If current_category_source == 'user', RETURN THE SAME category (do NOT change it).\n"
        "3) Use amount/in_out and text cues (merchant | notes | user_note). Prefer precision.\n"
        "4) If unsure, pick a broad bucket (e.g., 'Other').\n\n"
        f"Allowed categories: {', '.join(cats)}\n\n"
        "Ground-truth examples (respect '(LOCKED)'):\n" + "\n".join(example_lines)
    )

    rows_text = "\n".join([
        f"- id={r['id']}, text='{(r.get('text') or '')[:240]}', amount={r.get('amount',0)}, "
        f"in_out='{r.get('in_out','')}', current_category='{r.get('current_category','')}', "
        f"current_category_source='{r.get('current_source','')}'"
        for r in rows
    ])

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type":"json_schema","json_schema":{"name":"tx_categorizer","schema":schema}},
        temperature=0,
        messages=[
            {"role":"system","content":"JSON-only finance categorizer. Reply with VALID JSON matching the schema, nothing else."},
            {"role":"user","content": msg + "\n\nRows:\n" + rows_text},
        ],
    )

    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        txt = resp.choices[0].message.content
        start = txt.find("{"); end = txt.rfind("}")
        data = json.loads(txt[start:end+1]) if start>=0 and end>=0 else {"results":[]}

    out = {}
    for r in data.get("results", []):
        out[int(r.get("id"))] = {
            "category": r.get("category") or "Other",
            "confidence": float(r.get("confidence") or 0),
            "reason": (r.get("reason") or "")[:500]
        }
    return out

@login_required
@require_POST
def ai_dismiss_notification(request, run_id):
    run = get_object_or_404(AiRun, id=run_id, user=request.user)
    run.notified_at = timezone.now()
    run.save(update_fields=['notified_at'])
    return redirect(request.META.get('HTTP_REFERER') or 'upload')

# ---------------------------------------------------------------------
# Advisor payload helpers (richer + sampling)
# ---------------------------------------------------------------------

def _tx_row_dict(t):
    return {
        "id": t.id,
        "date": t.date.isoformat(),
        "merchant": (t.merchant or "").strip(),
        "amount": float(t.amount or 0),
        "in_out": t.in_out,
        "category": (t.category_fk.name if t.category_fk else (t.category or "")) or None,
        "note": (t.notes or "")[:120]
    }

def _group_by(items, key):
    d = defaultdict(list)
    for it in items:
        d[key(it)].append(it)
    return d

def _detect_recurring(tx_qs):
    txs = list(tx_qs.filter(in_out=Transaction.OUT).only("merchant","amount","date"))
    by_m = _group_by(txs, lambda x: (x.merchant or "").strip().upper())
    out = []
    for mkey, arr in by_m.items():
        if len(arr) < REC_MIN_COUNT:
            continue
        amts = sorted([t.amount or Decimal("0") for t in arr])
        median = amts[len(amts)//2]
        low = median * (Decimal("1.0") - REC_AMOUNT_JITTER)
        high = median * (Decimal("1.0") + REC_AMOUNT_JITTER)
        close = [t for t in arr if (t.amount or Decimal("0")) >= low and (t.amount or Decimal("0")) <= high]
        if len(close) >= REC_MIN_COUNT:
            last = max(t.date for t in close)
            out.append({
                "merchant": (arr[0].merchant or "").strip(),
                "median": float(median),
                "count": len(close),
                "last_date": last.isoformat(),
                "est_monthly": float(median)
            })
    out.sort(key=lambda x: -x["est_monthly"])
    return out

def _compute_leaks(tx_qs):
    small = list(tx_qs.filter(in_out=Transaction.OUT, amount__lte=LEAK_MAX_AMOUNT)
                       .exclude(merchant="")
                       .only("merchant","amount"))
    by_m = _group_by(small, lambda x: (x.merchant or "").strip())
    leaks = []
    for m, arr in by_m.items():
        total = sum((t.amount or Decimal("0") for t in arr), Decimal("0"))
        leaks.append({"merchant": m, "count": len(arr), "total": float(total)})
    leaks.sort(key=lambda x: (-x["total"], -x["count"]))
    return leaks[:10]

def _compute_anomalies_top(tx_qs, top_n=8):
    big = list(tx_qs.filter(in_out=Transaction.OUT).order_by("-amount")[:top_n])
    return [{"merchant": (t.merchant or "").strip(), "amount": float(t.amount or 0), "date": t.date.isoformat(),
             "category": (t.category_fk.name if t.category_fk else (t.category or "")) or None} for t in big]

def _sample_transactions_for_period(user, start, end):
    qs = Transaction.objects.filter(user=user, is_deleted=False, date__gte=start, date__lte=end)
    outs = list(qs.filter(in_out=Transaction.OUT).order_by("-amount").select_related("category_fk"))
    ins  = list(qs.filter(in_out=Transaction.IN).order_by("-amount"))

    take = []
    take.extend(outs[:TX_TOP_N])

    rec = _detect_recurring(qs)
    rec_names = {r["merchant"].strip().upper() for r in rec}
    if rec_names:
        take.extend([t for t in outs if (t.merchant or "").strip().upper() in rec_names])

    remaining = [t for t in outs if t not in take]
    by_cat = _group_by(remaining, lambda x: (x.category_fk.name if x.category_fk else (x.category or "Uncategorized")))
    left = max(0, TX_SAMPLE_MAX - len(take))
    cat_quota = max(4, left // max(1, len(by_cat)))
    for _, arr in by_cat.items():
        arr_sorted = sorted(arr, key=lambda t: (-t.amount, t.date))
        take.extend(arr_sorted[:cat_quota])

    take.extend(ins[:20])
    take.extend(sorted(ins, key=lambda t: t.date, reverse=True)[:10])

    seen_ids, final = set(), []
    for t in take:
        if t.id in seen_ids: continue
        seen_ids.add(t.id)
        final.append(t)
        if len(final) >= TX_SAMPLE_MAX: break

    tx_sample = [_tx_row_dict(t) for t in final]
    leaks = _compute_leaks(qs)
    anomalies = _compute_anomalies_top(qs)
    return tx_sample, rec, leaks, anomalies

def _advisor_build_payload(user, ptype: str, start: _date, end: _date):
    tx = Transaction.objects.filter(user=user, is_deleted=False, date__gte=start, date__lte=end)
    inc = tx.filter(in_out=Transaction.IN).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    out = tx.filter(in_out=Transaction.OUT).aggregate(s=Sum("amount"))["s"] or Decimal("0")

    top_cat_qs = (tx.filter(in_out=Transaction.OUT, category_fk__isnull=False)
                    .values("category_fk__name")
                    .annotate(total=Sum("amount"))
                    .order_by("-total")[:10])
    top_cats = [{"category": r["category_fk__name"], "total": float(r["total"] or 0)} for r in top_cat_qs]

    top_merch_qs = (tx.filter(in_out=Transaction.OUT)
                      .exclude(merchant="")
                      .values("merchant")
                      .annotate(total=Sum("amount"))
                      .order_by("-total")[:10])
    top_merchants = [{"merchant": r["merchant"], "total": float(r["total"] or 0)} for r in top_merch_qs]

    wday_totals = [Decimal("0")] * 7
    for t in tx.filter(in_out=Transaction.OUT).only("date", "amount"):
        wday_totals[t.date.weekday()] += (t.amount or Decimal("0"))
    weekday_mix = [float(x) for x in wday_totals]

    # Budgets snapshot (scaled for weekly)
    budgets = []
    cats_with_caps = Category.objects.filter(user=user, monthly_cap__isnull=False).exclude(monthly_cap=0)
    if cats_with_caps.exists():
        cap_scale = 1.0 if ptype == "monthly" else ((end - start).days + 1) / monthrange(start.year, start.month)[1]
        spent_rows = (tx.filter(in_out=Transaction.OUT, category_fk__in=cats_with_caps)
                        .values("category_fk")
                        .annotate(total=Sum("amount")))
        spent_map = {r["category_fk"]: (r["total"] or Decimal("0")) for r in spent_rows}
        for c in cats_with_caps:
            cap_total = float((c.monthly_cap or Decimal("0")) * Decimal(cap_scale))
            spent = float(spent_map.get(c.id, Decimal("0")))
            delta = cap_total - spent
            status = "ok" if delta >= 0 else "over"
            budgets.append({"category": c.name, "cap": round(cap_total,2), "spent": round(spent,2),
                            "delta": round(delta,2), "status": status})

    # Goals snapshot
    tx_sums = (Transaction.objects.filter(user=user, is_deleted=False)
               .values("money_source_id", "in_out")
               .annotate(total=Sum("amount")))
    ledger_map = {}
    for r in tx_sums:
        ms = r["money_source_id"]; amt = r["total"] or Decimal("0")
        ledger_map[ms] = (ledger_map.get(ms, Decimal("0")) + (amt if r["in_out"] == Transaction.IN else -amt))
    eff_map = {}
    for acc in MoneySource.objects.filter(user=user):
        eff_map[acc.id] = acc.manual_balance if acc.manual_balance is not None else ledger_map.get(acc.id, Decimal("0"))
    goals = []
    for g in SavingsGoal.objects.filter(user=user, is_active=True).prefetch_related("accounts"):
        sel = [a for a in g.accounts.all() if a.is_active]
        current = sum((eff_map.get(a.id, Decimal("0")) for a in sel), Decimal("0"))
        target = g.target_amount or Decimal("0")
        pct = float((current / target * 100) if target > 0 else 0.0)
        goals.append({"name": g.name, "progress_pct": round(pct,1), "eta": None})

    # NEW details for advice
    tx_sample, recurrings, leaks, anomalies = _sample_transactions_for_period(user, start, end)

    mom_delta = None
    if ptype == "monthly":
        prev_y, prev_m = (start.year, start.month-1) if start.month>1 else (start.year-1, 12)
        prev_s, prev_e = _date(prev_y, 1, 1).replace(month=prev_m), _date(prev_y, monthrange(prev_y, prev_m)[1], 1).replace(month=prev_m)
        prev_e = _date(prev_y, prev_m, monthrange(prev_y, prev_m)[1])
        prev_tx = Transaction.objects.filter(user=user, is_deleted=False, date__gte=prev_s, date__lte=prev_e)
        prev_inc = prev_tx.filter(in_out=Transaction.IN).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        prev_out = prev_tx.filter(in_out=Transaction.OUT).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        mom_delta = float((inc - out) - (prev_inc - prev_out))

    payload = {
        "user_context": {"currency": "EUR", "locale": "LT"},
        "period": {"type": ptype, "start": start.isoformat(), "end": end.isoformat()},
        "income_vs_spending": {
            "income_total": float(inc),
            "spending_total": float(out),
            "net": float(inc - out),
            "by_category_topN": top_cats,
            "by_merchant_topN": top_merchants,
            "weekday_mix": weekday_mix,
        },
        "budgets": budgets,
        "goals": goals,
        "balances": {"start_balance": None, "end_balance": None, "delta": float(inc - out)},
        "tx_sample": tx_sample,
        "recurrings": recurrings,
        "leaks": leaks,
        "anomalies": anomalies,
        "month_over_month_net_delta": mom_delta,
        "last_report_excerpt": None,
        "house_rules": [
            "Be practical and conservative.",
            "Use EUR amounts.",
            "Never change user categories.",
            "Cite specific merchants and amounts from tx_sample when giving advice."
        ]
    }
    return payload

def _advisor_call_model(payload: dict, model_name=None):
    api_key = os.getenv("OPENAI_API_KEY")
    model_name = model_name or ADVISOR_MODEL
    if not api_key:
        # key missing -> minimal stub
        return {
            "summary": "AI key missing. Stub report.",
            "key_metrics": {
                "income": payload["income_vs_spending"]["income_total"],
                "spending": payload["income_vs_spending"]["spending_total"],
                "net": payload["income_vs_spending"]["net"],
                "month_over_month_net_delta": payload.get("month_over_month_net_delta"),
                "risk_flags": []
            },
            "insights": [],
            "budgets": payload.get("budgets", []),
            "goals": payload.get("goals", []),
            "subscriptions": [],
            "forecast": {"next_month_notes": "", "targets": []},
            "action_items": [],
            "appendix": {
                "top_categories": payload["income_vs_spending"]["by_category_topN"],
                "top_merchants": payload["income_vs_spending"]["by_merchant_topN"]
            },
            "references": []
        }

    client = OpenAI(api_key=api_key)
    schema = {
        "type":"object",
        "properties":{
            "summary":{"type":"string"},
            "key_metrics":{
                "type":"object",
                "properties":{
                    "income":{"type":"number"},
                    "spending":{"type":"number"},
                    "net":{"type":"number"},
                    "month_over_month_net_delta":{"type":["number","null"]},
                    "risk_flags":{"type":"array","items":{"type":"string"}}
                },
                "required":["income","spending","net","month_over_month_net_delta","risk_flags"]
            },
            "insights":{
                "type":"array",
                "items":{"type":"object","properties":{
                    "title":{"type":"string"},
                    "detail":{"type":"string"},
                    "severity":{"type":"string","enum":["info","watch","alert"]},
                    "estimated_saving":{"type":["number","null"]}
                },"required":["title","detail","severity"]}
            },
            "budgets":{"type":"array","items":{"type":"object",
                "properties":{
                    "category":{"type":"string"},
                    "cap":{"type":"number"},
                    "spent":{"type":"number"},
                    "delta":{"type":"number"},
                    "status":{"type":"string","enum":["ok","over"]},
                    "note":{"type":["string","null"]}
                },
                "required":["category","cap","spent","delta","status"]
            }},
            "goals":{"type":"array","items":{"type":"object",
                "properties":{
                    "name":{"type":"string"},
                    "progress_pct":{"type":"number"},
                    "eta":{"type":["string","null"]},
                    "note":{"type":["string","null"]}
                },
                "required":["name","progress_pct","eta"]
            }},
            "subscriptions":{"type":"array","items":{"type":"object",
                "properties":{
                    "merchant":{"type":"string"},
                    "status_change":{"type":["string","null"]},
                    "action":{"type":["string","null"]}
                },
                "required":["merchant"]
            }},
            "forecast":{"type":"object","properties":{
                "next_month_notes":{"type":"string"},
                "targets":{"type":"array","items":{"type":"object",
                    "properties":{
                        "category":{"type":"string"},
                        "target_spend":{"type":"number"},
                        "rationale":{"type":"string"}
                    },
                    "required":["category","target_spend"]
                }}
            },"required":["next_month_notes","targets"]},
            "action_items":{"type":"array","items":{"type":"object",
                "properties":{
                    "title":{"type":"string"},
                    "why":{"type":"string"},
                    "steps":{"type":"array","items":{"type":"string"}},
                    "impact":{"type":"string","enum":["low","medium","high"]},
                    "estimated_saving":{"type":["number","null"]}
                },
                "required":["title","why","steps","impact"]
            }},
            "appendix":{"type":"object","properties":{
                "top_categories":{"type":"array","items":{"type":"object",
                    "properties":{"category":{"type":"string"},"total":{"type":"number"}},
                    "required":["category","total"]
                }},
                "top_merchants":{"type":"array","items":{"type":"object",
                    "properties":{"merchant":{"type":"string"},"total":{"type":"number"}},
                    "required":["merchant","total"]
                }}
            },"required":["top_categories","top_merchants"]},
            "references":{"type":"array","items":{"type":"object",
                "properties":{
                    "type":{"type":"string","enum":["tx","budget","recurring","leak","anomaly"]},
                    "ref":{"type":"string"},
                    "note":{"type":"string"}
                }}, "default":[]
            }
        },
        "required":["summary","key_metrics","insights","budgets","goals","subscriptions","forecast","action_items","appendix"]
    }

    system = (
        "You are a personal-finance advisor. Be concrete, quantify savings, and ground every claim in the provided data. "
        "Use EUR, cite merchants/amounts from tx_sample, prefer categories with status='over' for action items."
    )

    resp = client.chat.completions.create(
        model=model_name,
        response_format={"type":"json_schema","json_schema":{"name":"advisor_report","schema":schema}},
        temperature=ADVISOR_TEMP,
        messages=[
            {"role":"system","content":system},
            {"role":"user","content":json.dumps(payload)},
        ],
    )

    txt = resp.choices[0].message.content
    try:
        return json.loads(txt)
    except Exception:
        start = txt.find("{"); end = txt.rfind("}")
        return json.loads(txt[start:end+1]) if start>=0 and end>=0 else {
            "summary":"(parse error)",
            "key_metrics":{"income":0,"spending":0,"net":0,"month_over_month_net_delta":None,"risk_flags":[]},
            "insights":[], "budgets":[], "goals":[], "subscriptions":[],
            "forecast":{"next_month_notes":"","targets":[]},
            "action_items":[], "appendix":{"top_categories":[],"top_merchants":[]}, "references":[]
        }

# ---------------------------------------------------------------------
# Balance anomaly reconciliation (history)
# ---------------------------------------------------------------------

def _reconcile_global(user):
    """
    Build anomaly segments between consecutive BalanceSnapshots.
    Each row compares what the app *calculated* the ending balance should be
    versus what the user declared in the newer snapshot.
    """
    snaps = list(BalanceSnapshot.objects.filter(user=user).order_by("timestamp", "id"))
    if len(snaps) < 2:
        return []

    segs = []
    for a, b in zip(snaps, snaps[1:]):
        start_ts, end_ts = a.timestamp, b.timestamp

        # Transactions inside the snapshot interval (inclusive on dates)
        tx_qs = Transaction.objects.filter(
            user=user, is_deleted=False,
            date__gte=start_ts.date(), date__lte=end_ts.date()
        )

        inc = tx_qs.filter(in_out=Transaction.IN).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        out = tx_qs.filter(in_out=Transaction.OUT).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        net_tx = inc - out

        # What the app thinks the ending balance should be
        calc_end = Decimal(a.amount) + net_tx

        snap_delta = Decimal(b.amount) - Decimal(a.amount)
        diff = Decimal(b.amount) - calc_end
        is_anom = abs(diff) > Decimal("0.01")

        # Extra useful context
        tx_count   = tx_qs.count()
        in_count   = tx_qs.filter(in_out=Transaction.IN).count()
        out_count  = tx_qs.filter(in_out=Transaction.OUT).count()
        largest_out = (tx_qs.filter(in_out=Transaction.OUT)
                              .order_by("-amount")
                              .values("merchant", "amount", "date")
                              .first())
        # Longest gap (days) with no transactions within the interval
        dates = sorted(set(tx_qs.values_list("date", flat=True)))
        gap_days = 0
        if dates:
            prev = dates[0]
            for d in dates[1:]:
                gap_days = max(gap_days, (d - prev).days - 1)
                prev = d

        segs.append({
            # Primary fields for your table
            "spotted_at": b.timestamp,  # newer snapshot time
            "snapshot1_date": a.timestamp,
            "snapshot1_amount": float(a.amount),
            "snapshot2_date": b.timestamp,
            "snapshot2_amount": float(b.amount),

            "tx_income": float(inc),
            "tx_spending": float(out),
            "tx_net": float(net_tx),

            "app_calculated_end": float(calc_end),
            "snapshot_delta": float(snap_delta),
            "diff": float(diff),

            "is_anomaly": is_anom,
            "note": (b.note or ""),

            # Helpful extras
            "tx_count": tx_count,
            "in_count": in_count,
            "out_count": out_count,
            "largest_out": {
                "merchant": (largest_out or {}).get("merchant"),
                "amount": float((largest_out or {}).get("amount") or 0),
                "date": (largest_out or {}).get("date").isoformat() if largest_out else None,
            },
            "longest_quiet_gap_days": gap_days,
        })
    # Most recent first in the UI feels nicer
    segs.sort(key=lambda s: s["spotted_at"], reverse=True)
    return segs


# ---------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------

@login_required
def tx_edit(request, pk):
    tx = get_object_or_404(Transaction, id=pk, user=request.user, is_deleted=False)
    categories = Category.objects.filter(user=request.user).order_by("name")
    if request.method == "POST":
        cat_id = request.POST.get("category_fk")
        user_note = (request.POST.get("user_note") or "").strip()[:500]
        try:
            if cat_id:
                cat = Category.objects.get(id=int(cat_id), user=request.user)
                tx.category_fk = cat
                tx.category = cat.name
                tx.category_source = "user"
            tx.user_note = user_note
            tx.save(update_fields=["category_fk", "category", "category_source", "user_note"])
            messages.success(request, "Saved.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
        return redirect(request.GET.get("next") or "upload")
    return render(request, "tx_edit.html", {"tx": tx, "categories": categories})

@login_required
@require_http_methods(["GET", "POST"])
def tx_add(request):
    sources = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("name"))
    if not sources:
        primary_src = MoneySource.objects.create(user=request.user, name="Primary account", type="bank", is_active=True)
        sources = [primary_src]
    categories = Category.objects.filter(user=request.user).order_by("name")
    if not categories.exists():
        ensure_default_categories(request.user)
        categories = Category.objects.filter(user=request.user).order_by("name")

    if request.method == "POST":
        date_str   = (request.POST.get("date") or "").strip()
        merchant   = (request.POST.get("merchant") or "").strip()[:255]
        amount_str = (request.POST.get("amount") or "").strip().replace(",", ".")
        currency   = (request.POST.get("currency") or "EUR").strip().upper()[:8] or "EUR"
        in_out     = (request.POST.get("in_out") or "out").strip()
        notes      = (request.POST.get("notes") or "").strip()[:2000]
        user_note  = (request.POST.get("user_note") or "").strip()[:2000]
        src_id     = request.POST.get("money_source") or ""
        cat_id     = request.POST.get("category") or ""
        next_url   = request.POST.get("next") or "upload"

        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            d = timezone.localdate()
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, TypeError):
            messages.error(request, "Enter a valid amount (e.g., 12.34).")
            return redirect("tx_add")
        try:
            src = MoneySource.objects.get(id=int(src_id), user=request.user, is_active=True)
        except Exception:
            src = sources[0]

        cat = None
        if cat_id:
            try:
                cat = Category.objects.get(id=int(cat_id), user=request.user)
            except Category.DoesNotExist:
                cat = None

        fp = f"{d.isoformat()}|{merchant}|{str(amount)}|{currency}|{in_out}|{src.id}"

        if Transaction.objects.filter(user=request.user, fingerprint=fp).exists():
            messages.info(request, "This transaction already exists (duplicate skipped).")
            return redirect(next_url)

        Transaction.objects.create(
            user=request.user,
            money_source=src,
            date=d,
            merchant=merchant,
            amount=amount,
            currency=currency,
            in_out=in_out,
            notes=notes,
            user_note=user_note,
            fingerprint=fp,
            category_source="user" if cat else "unknown",
            category_fk=cat,
            category=(cat.name if cat else None),
        )
        messages.success(request, "Transaction added.")
        return redirect(next_url)

    ctx = {
        "today": timezone.localdate().strftime("%Y-%m-%d"),
        "sources": sources,
        "categories": categories,
        "next": request.GET.get("next") or request.META.get("HTTP_REFERER") or "/",
        "default_currency": "EUR",
    }
    return render(request, "tx_add.html", ctx)

@login_required
def tx_bulk_category_apply(request):
    if request.method != "POST":
        return redirect("upload")

    next_url = request.POST.get("next") or "/"
    changes_raw = request.POST.get("changes_json")
    if not changes_raw:
        messages.info(request, "No changes to apply.")
        return redirect(next_url)

    try:
        mapping = json.loads(changes_raw)
        if not isinstance(mapping, dict):
            mapping = {}
    except Exception:
        mapping = {}
    if not mapping:
        messages.info(request, "No changes to apply.")
        return redirect(next_url)

    cat_ids, tx_ids = set(), []
    for tx_id, cat_id in mapping.items():
        try:
            tx_ids.append(int(tx_id))
            cat_ids.add(int(cat_id))
        except Exception:
            continue
    cats = {c.id: c for c in Category.objects.filter(user=request.user, id__in=cat_ids)}

    applied = 0
    for tx_id, cat_id in mapping.items():
        try:
            tx_id = int(tx_id); cat_id = int(cat_id)
        except Exception:
            continue
        cat = cats.get(cat_id)
        if not cat:
            continue
        try:
            tx = Transaction.objects.get(id=tx_id, user=request.user, is_deleted=False)
        except Transaction.DoesNotExist:
            continue
        tx.category_fk = cat
        tx.category = cat.name
        tx.category_source = "user"
        tx.ai_suggested_fk = None
        tx.ai_confidence = None
        tx.save(update_fields=["category_fk", "category", "category_source", "ai_suggested_fk", "ai_confidence"])
        applied += 1

    if applied:
        messages.success(request, f"Applied changes to {applied} transaction(s).")
    else:
        messages.info(request, "Nothing changed.")

    sep = "&" if "?" in next_url else "?"
    return redirect(f"{next_url}{sep}clear_local=1")

@login_required
def uncategorized(request):
    qs = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False)
        .filter(
            Q(category_fk__isnull=True) |
            Q(category__isnull=True) |
            Q(category="")
        )
        .order_by("-date", "-id")
    )
    try:
        per = max(5, min(200, int(request.GET.get("per") or 20)))
    except (TypeError, ValueError):
        per = 20
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "uncategorized.html", {"page_obj": page_obj, "total": paginator.count, "per_value": per})

@login_required
def upload(request):
    sources = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("name"))
    if not sources:
        primary_src = MoneySource.objects.create(user=request.user, name="Primary account", type="bank", is_active=True)
        sources = [primary_src]
    default_src = sources[0]

    src_param = (request.GET.get("src") or "").strip()
    active_src = None
    if src_param and src_param != "all":
        try:
            active_src = MoneySource.objects.get(id=int(src_param), user=request.user, is_active=True)
        except MoneySource.DoesNotExist:
            active_src = None

    stype = (request.GET.get("stype") or "").strip()
    valid_types = {t for t, _ in MoneySource.TYPE_CHOICES}
    if stype and stype not in valid_types:
        stype = ""

    # -------------------- IMPORT (POST) --------------------
    if request.method == "POST" and request.FILES.get("file"):
        import_src_id = request.POST.get("import_src")
        try:
            import_src = MoneySource.objects.get(id=int(import_src_id), user=request.user, is_active=True)
        except Exception:
            import_src = default_src

        f = request.FILES["file"]
        name = (f.name or "").lower()

        parsed_count = 0
        skipped_count = 0
        rows = []

        try:
            if name.endswith(".csv"):
                raw = f.read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                text = text.replace("\r\n", "\n").replace("\r", "\n")
                lines = text.split("\n")

                sample = text[:8192]
                delimiter = None
                try:
                    dialect = csv.Sniffer().sniff(sample)
                    delimiter = dialect.delimiter
                except Exception:
                    pass
                if not delimiter:
                    counts = {sep: sample.count(sep) for sep in (";", ",", "\t")}
                    delimiter = max(counts, key=counts.get) if any(counts.values()) else ","  # <- fixed

                header_idx = 0
                for i, line in enumerate(lines[:20]):
                    if line.count(delimiter) >= 3:
                        header_idx = i
                        break
                sliced_text = "\n".join(lines[header_idx:])
                reader = csv.DictReader(io.StringIO(sliced_text), delimiter=delimiter)

                def pick(d, *aliases):
                    for a in aliases:
                        a = a.strip().lower()
                        for k in d.keys():
                            if (k or "").strip().lower() == a:
                                return d[k]
                    return None

                for r in reader:
                    rr = {(k or "").strip(): r[k] for k in r.keys()}

                    date_val   = pick(rr, "data", "date", "operacijos data", "operation date", "transaction date")
                    merchant   = pick(rr, "gavejas", "mokėtojas / gavėjas", "mokėtojo arba gavėjo pavadinimas",
                                      "merchant", "description", "parduotuvė", "counterparty", "payee")
                    amount_raw = pick(rr, "suma", "amount", "sum", "transaction amount", "suma sąskaitos valiuta")
                    currency   = pick(rr, "valiuta", "currency", "sąskaitos valiuta")
                    debcred    = pick(rr, "debetas/kreditas", "dr/cr", "dc", "d/k")
                    trans_type = pick(rr, "transakcijos tipas", "transaction type", "tipas", "type")
                    note       = pick(rr, "paskirtis", "note", "notes", "purpose", "details")
                    # Optional:
                    time_val   = pick(rr, "time", "operation time", "transaction time", "laikas")
                    descr_val  = pick(rr, "description", "details", "purpose", "mokėjimo paskirtis", "mokėjimo paskirtis (description)")

                    try:
                        d = parse_date(date_val)
                        in_out = parse_in_out(debcred, trans_type)
                        amt = parse_amount(amount_raw)
                        cur = normalize_currency(currency)
                    except Exception:
                        skipped_count += 1
                        continue
                    if not d or amt is None:
                        skipped_count += 1
                        continue

                    rows.append({
                        "date": d,
                        "time": (str(time_val).strip() if time_val else ""),
                        "merchant": (merchant or "").strip()[:200],
                        "amount": amt,
                        "currency": cur or "EUR",
                        "in_out": in_out or "out",
                        "notes": (note or "").strip()[:500],
                        "description": (str(descr_val or note or merchant or "").strip())[:500],
                    })
                    parsed_count += 1

            else:
                import pandas as pd
                df = pd.read_excel(f)
                df.columns = [str(c).strip().lower() for c in df.columns]

                def pick_row(row, *aliases):
                    for a in aliases:
                        a = a.strip().lower()
                        if a in row and pd.notna(row[a]):
                            return row[a]
                    return None

                for _, r in df.iterrows():
                    date_val   = pick_row(r, "data", "date", "operacijos data", "operation date", "transaction date")
                    merchant   = pick_row(r, "gavejas", "mokėtojas / gavėjas", "mokėtojo arba gavėjo pavadinimas",
                                          "merchant", "description", "parduotuvė", "counterparty", "payee")
                    amount_raw = pick_row(r, "suma", "amount", "sum", "transaction amount", "suma sąskaitos valiuta")
                    currency   = pick_row(r, "valiuta", "currency", "sąskaitos valiuta")
                    debcred    = pick_row(r, "debetas/kreditas", "dr/cr", "dc", "d/k")
                    trans_type = pick_row(r, "transakcijos tipas", "transaction type", "tipas", "type")
                    note       = pick_row(r, "paskirtis", "note", "notes", "purpose", "details")
                    # Optional:
                    time_val   = pick_row(r, "time", "operation time", "transaction time", "laikas")
                    descr_val  = pick_row(r, "description", "details", "purpose", "mokėjimo paskirtis", "mokėjimo paskirtis (description)")

                    try:
                        d = parse_date(date_val)
                        in_out = parse_in_out(debcred, trans_type)
                        amt = parse_amount(str(amount_raw) if amount_raw is not None else None)
                        cur = normalize_currency(currency)
                    except Exception:
                        skipped_count += 1
                        continue
                    if not d or amt is None:
                        skipped_count += 1
                        continue

                    rows.append({
                        "date": d,
                        "time": (str(time_val).strip() if time_val is not None else ""),
                        "merchant": str(merchant or "").strip()[:200],
                        "amount": amt,
                        "currency": cur or "EUR",
                        "in_out": in_out or "out",
                        "notes": str(note or "").strip()[:500],
                        "description": (str(descr_val or note or merchant or "").strip())[:500],
                    })
                    parsed_count += 1

            # ---------------- DB-only dedupe using fingerprint v2 ----------------
            existing_fps = set(
                Transaction.objects
                .filter(user=request.user)
                .values_list("fingerprint", flat=True)
            )

            db_dups = 0
            blocked_deleted = 0  # keep if you later want to count deleted-blocks
            to_create = []

            for r in rows:
                try:
                    date_iso = r["date"].strftime("%Y-%m-%d")
                except Exception:
                    skipped_count += 1
                    continue

                fp = build_fingerprint_v2(
                    date_iso=date_iso,
                    time_str=(r.get("time") or "").strip(),
                    merchant=r.get("merchant") or "",
                    amount=r.get("amount"),
                    currency=(r.get("currency") or "EUR").strip() or "EUR",
                    in_out=r.get("in_out"),
                    money_source_id=import_src.id,
                    description=r.get("description") or r.get("notes") or r.get("merchant") or "",
                )

                if fp in existing_fps:
                    db_dups += 1
                    continue

                to_create.append(Transaction(
                    user=request.user,
                    money_source=import_src,
                    date=r["date"],
                    merchant=r.get("merchant") or "",
                    amount=r.get("amount"),
                    currency=(r.get("currency") or "EUR").strip() or "EUR",
                    in_out=r.get("in_out"),
                    notes=r.get("notes") or "",
                    user_note="",
                    category_fk=None,
                    category=None,
                    category_source="import",
                    fingerprint=fp,
                ))

            added = 0
            if to_create:
                Transaction.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)
                created_fps = set(
                    Transaction.objects
                    .filter(user=request.user, fingerprint__in=[t.fingerprint for t in to_create])
                    .values_list("fingerprint", flat=True)
                )
                added = len(created_fps)

            msg = (
                f'Imported into: {import_src.name}. Parsed {parsed_count}, skipped {skipped_count}. '
                f'Added {added} new transaction{"s" if added != 1 else ""}. '
                f'(DB dups: {db_dups}, blocked by deleted: {blocked_deleted}.) '
            )
            if added > 0:
                messages.success(request, msg, extra_tags="safe")
            else:
                messages.info(request, msg, extra_tags="safe")

            # ---- enqueue auto-categorize if eligible (single place) ----
            from django.conf import settings as dj_settings
            from finance.models import AiRun, OnboardingState as OBState

            TEACH_AI_UNLOCK = getattr(dj_settings, "TEACH_AI_UNLOCK", 20)
            try:
                state = request.user.onboarding_state
            except OBState.DoesNotExist:
                state = None

            if state and state.categories_done:
                labeled = Transaction.objects.filter(user=request.user, category_source="user").count()
                has_uncat = Transaction.objects.filter(
                    user=request.user, is_deleted=False, category_fk__isnull=True
                ).exists()
                if labeled >= TEACH_AI_UNLOCK and has_uncat:
                    AiRun.objects.create(user=request.user, kind="autocategorize", mode="uncat", status="queued")

            # Redirect
            qs_params = []
            if active_src:
                qs_params.append(f"src={active_src.id}")
            elif src_param == "all":
                qs_params.append("src=all")
            if stype:
                qs_params.append(f"stype={stype}")
            if qs_params:
                return redirect(f"/?{'&'.join(qs_params)}")
            return redirect("upload")

        except Exception as e:
            messages.error(request, f"Failed to import file: {e}")
            return redirect("upload")

    # -------------------- LIST (GET) --------------------
    qs = (Transaction.objects
          .filter(user=request.user, is_deleted=False)
          .select_related("category_fk", "money_source"))

    if active_src:
        qs = qs.filter(money_source=active_src)
    if stype:
        qs = qs.filter(money_source__type=stype)

    q = (request.GET.get("q") or "").strip()
    flow = (request.GET.get("flow") or "").strip()
    cat_id = (request.GET.get("cat") or "").strip()
    d_from = parse_date_filter(request.GET.get("from"))
    d_to   = parse_date_filter(request.GET.get("to"))
    a_min  = parse_decimal_filter(request.GET.get("amin"))
    a_max  = parse_decimal_filter(request.GET.get("amax"))

    if q:
        qs = qs.filter(Q(merchant__icontains=q) | Q(notes__icontains=q) | Q(user_note__icontains=q))
    if flow in ("in", "out"):
        qs = qs.filter(in_out=flow)
    if cat_id:
        try:
            qs = qs.filter(category_fk_id=int(cat_id))
        except ValueError:
            pass
    if d_from:
        qs = qs.filter(date__gte=d_from)
    if d_to:
        qs = qs.filter(date__lte=d_to)
    if a_min is not None:
        qs = qs.filter(amount__gte=a_min)
    if a_max is not None:
        qs = qs.filter(amount__lte=a_max)

    qs = qs.order_by("-date", "-id")

    uncat_count = (Transaction.objects
                   .filter(user=request.user, is_deleted=False)
                   .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
                   .count())
    low_conf_count = Transaction.objects.filter(
        user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
    ).count()

    try:
        per = max(5, min(200, int(request.GET.get("per") or 50)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    categories = Category.objects.filter(user=request.user).order_by("name")

    # Onboarding sidebar state (model-backed)
    ensure_default_categories(request.user)
    income_exists = Category.objects.filter(user=request.user, name="Income").exists()
    try:
        state = request.user.onboarding_state
        cats_done = bool(state and state.categories_done and income_exists)
    except OnboardingState.DoesNotExist:
        cats_done = False

    MIN_USER_LABELS = getattr(settings, "MIN_USER_LABELS", 30)
    has_any_tx = Transaction.objects.filter(user=request.user, is_deleted=False).exists()
    user_labels_count = Transaction.objects.filter(
        user=request.user, is_deleted=False, category_source="user"
    ).count()
    ai_locked = (has_any_tx and user_labels_count < MIN_USER_LABELS)

    ctx = {
        "page_obj": page_obj,
        "total": paginator.count,
        "uncat_count": uncat_count,
        "low_conf_count": low_conf_count,
        "per_options": [20, 50, 100, 200],
        "per_value": per,
        "q": q,
        "flow": flow,
        "cat": cat_id,
        "from": request.GET.get("from") or "",
        "to": request.GET.get("to") or "",
        "amin": request.GET.get("amin") or "",
        "amax": request.GET.get("amax") or "",
        "categories": categories,
        "sources": sources,
        "active_src": active_src,
        "src_param": src_param or "",
        "stype": stype,
        "type_choices": MoneySource.TYPE_CHOICES,
        "default_account_name": default_src.name,
        "onboarding_state": {
            "categories_done": cats_done,
            "has_income": income_exists,
            "has_any_tx": has_any_tx,
            "user_labels_count": user_labels_count,
            "min_needed": MIN_USER_LABELS,
            "ai_locked": ai_locked,
        },
    }

    last_ai_pre = request.session.pop("last_ai_pre", None)
    if last_ai_pre:
        ctx["last_ai_pre"] = last_ai_pre

    return render(request, "upload.html", ctx)



def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("upload")
    else:
        form = UserCreationForm()
    return render(request, "register.html", {"form": form})

# ----------------------------- Categories CRUD -----------------------------

@login_required
def category_list(request):
    if not Category.objects.filter(user=request.user).exists():
        Category.objects.bulk_create([Category(user=request.user, name=n) for n in DEFAULT_CATEGORIES])

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        color = (request.POST.get("color") or "").strip()
        if name:
            Category.objects.get_or_create(user=request.user, name=name, defaults={"color": color})
        return redirect("category_list")

    cats = Category.objects.filter(user=request.user).order_by("name")
    return render(request, "categories.html", {"categories": cats})

@login_required
def category_edit(request, pk):
    cat = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        color = (request.POST.get("color") or "").strip()
        if name:
            exists = Category.objects.filter(user=request.user, name=name).exclude(pk=cat.pk).exists()
            if not exists:
                cat.name = name
            cat.color = color
            cat.save()
        return redirect("category_list")
    return render(request, "category_edit.html", {"cat": cat})

@login_required
def category_delete(request, pk):
    cat = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == "POST":
        other, _ = Category.objects.get_or_create(user=request.user, name="Other")
        with dbtx.atomic():
            Transaction.objects.filter(user=request.user, category_fk=cat).update(category_fk=other)
            cat.delete()
        return redirect("category_list")
    return redirect("category_list")

# ----------------------------- AI categorize -----------------------------

@login_required
def ai_full_categorize(request):
    """
    Modes:
      - mode=uncat (default): only truly uncategorized (no FK/blank)
      - mode=ai:              only AI-labeled
      - mode=all:             everything EXCEPT user-labeled
    Rules added:
      - Prefill all IN rows with empty category -> 'Income' (category_source='rule')
      - Never assign 'Income' to OUT rows
    Also respects batching & thresholds.
    """
    # Seed defaults
    ensure_default_categories(request.user)

    # If no key, render simple card (existing behavior)
    if not os.getenv("OPENAI_API_KEY"):
        return render(request, "ai_summary.html", {
            "key_present": False, "total_candidates": 0, "applied": 0, "parked": 0,
            "left_for_review": 0,
        })

    mode = request.GET.get("mode", "uncat")

    # ---------- Candidate pool (EXCLUDE deleted) ----------
    if mode == "uncat":
        base = (Transaction.objects
                .filter(user=request.user, is_deleted=False)
                .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
                .exclude(category_source="user"))
    elif mode == "ai":
        base = Transaction.objects.filter(user=request.user, is_deleted=False, category_source="ai")
    elif mode == "all":
        base = Transaction.objects.filter(user=request.user, is_deleted=False).exclude(category_source="user")
    else:
        base = Transaction.objects.none()

    # ---------- HARD RULES: Income prefill for IN & empty ----------
    INCOME_NAME = "Income"
    cats_by_name = {c.name: c for c in Category.objects.filter(user=request.user)}
    income_cat = cats_by_name.get(INCOME_NAME)

    if income_cat:
        prefill_qs = (
            Transaction.objects
            .filter(user=request.user, is_deleted=False, in_out=Transaction.IN)
            .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
        )
        for t in prefill_qs.only("id"):
            t.category_fk = income_cat
            t.category = income_cat.name
            t.category_source = "rule"
            t.ai_suggested_fk = None
            t.ai_confidence = None
            t.save(update_fields=[
                "category_fk","category","category_source","ai_suggested_fk","ai_confidence","updated_at"
            ])

    # refresh after prefill if we're working on uncategorized
    if mode == "uncat":
        base = (Transaction.objects
                .filter(user=request.user, is_deleted=False)
                .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
                .exclude(category_source="user"))

    qs = base.order_by("date", "id").select_related("category_fk")
    total_candidates = qs.count()
    if total_candidates == 0:
        return render(request, "ai_summary.html", {
            "key_present": True, "total_candidates": 0, "applied": 0, "parked": 0,
            "left_for_review": Transaction.objects.filter(
                user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
            ).count(),
        })

    # Stamp last-run timestamp if not already set (so Review AI can show only the latest)
    if "last_ai_run_started_at" not in request.session:
        from django.utils import timezone
        request.session["last_ai_run_started_at"] = timezone.now().isoformat()

    cats_map = {c.name: c for c in Category.objects.filter(user=request.user)}
    cats_list = sorted(cats_map.keys())

    rows = [{
        "id": t.id,
        "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}",
        "amount": float(t.amount or 0),
        "in_out": t.in_out or "",
        "current_category": (t.category_fk.name if t.category_fk else (t.category or "")) or "",
        "current_source": t.category_source or "",
    } for t in qs]

    applied = 0
    parked = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        examples = _pick_examples(request.user, limit=12)
        try:
            results = _call_openai_rows(request.user, batch, examples, cats_list)
        except Exception as e:
            return render(request, "ai_error.html", {"error": str(e), "batch_index": i // BATCH_SIZE})

        for r in batch:
            t_id = r["id"]
            try:
                t = Transaction.objects.get(pk=t_id, user=request.user, is_deleted=False)
            except Transaction.DoesNotExist:
                continue

            if t.category_source == "user":
                continue  # never override user labels

            res = results.get(t_id)
            if not res:
                continue

            suggested_name = (res["category"] or "").strip() or "Other"
            conf = float(res.get("confidence") or 0.0)
            reason = (res.get("reason") or "")[:500]
            suggested_fk = cats_map.get(suggested_name)

            if not suggested_fk:
                continue

            # Guard: Never assign "Income" to OUT rows (rule safety)
            if t.in_out == Transaction.OUT and suggested_name == "Income":
                continue

            current_name = (t.category_fk.name if t.category_fk else (t.category or "")).strip()

            # === LOGIC CHANGE STARTS HERE ===
            # 1. Determine if this is a "Fresh Assignment" or a "Change"
            is_new_assignment = (not current_name or current_name == "Other")

            # 2. Set threshold: 0.70 for fresh assignments, 0.90 (AUTO_CHANGE_THRESHOLD) for overwrites
            apply_threshold = 0.70 if is_new_assignment else AUTO_CHANGE_THRESHOLD

            # 3. Apply logic
            if is_new_assignment:
                # CASE A: It's currently empty/Other.
                if conf >= apply_threshold:
                    # High confidence -> Apply immediately
                    t.category_fk = suggested_fk
                    t.category = suggested_fk.name
                    t.category_source = "ai"
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.ai_suggested_fk = None
                    t.save(update_fields=[
                        "category_fk", "category", "category_source", "ai_confidence",
                        "ai_reason", "ai_suggested_fk", "updated_at"
                    ])
                    applied += 1
                else:
                    # Low confidence -> Park for review
                    t.ai_suggested_fk = suggested_fk
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.save(update_fields=["ai_suggested_fk", "ai_confidence", "ai_reason", "updated_at"])
                    parked += 1
                continue

            # CASE B: It already has a category (from Import or older AI run)
            if suggested_name == current_name:
                # AI agrees with current category. Just update confidence.
                if t.category_source == "ai":
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.ai_suggested_fk = None
                    t.save(update_fields=["ai_confidence", "ai_reason", "ai_suggested_fk", "updated_at"])
                continue

            # CASE C: AI disagrees with current category.
            # Only change if confidence is very high (>= 0.90).
            if conf >= apply_threshold:
                t.category_fk = suggested_fk
                t.category = suggested_fk.name
                t.category_source = "ai"
                t.ai_confidence = conf
                t.ai_reason = reason
                t.ai_suggested_fk = None
                t.save(update_fields=[
                    "category_fk", "category", "category_source", "ai_confidence",
                    "ai_reason", "ai_suggested_fk", "updated_at"
                ])
                applied += 1
            elif conf >= 0.70:  # Optional: if medium confidence, park it as a suggestion
                t.ai_suggested_fk = suggested_fk
                t.ai_confidence = conf
                t.ai_reason = reason
                t.save(update_fields=["ai_suggested_fk", "ai_confidence", "ai_reason", "updated_at"])
                parked += 1
            else:
                # Too low to mention
                pass

    left_for_review = Transaction.objects.filter(
        user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
    ).count()

    return render(request, "ai_summary.html", {
        "key_present": True,
        "total_candidates": total_candidates,
        "applied": applied,
        "parked": parked,
        "left_for_review": left_for_review,
    })



@login_required
def ai_run_uncategorized(request):
    base = Transaction.objects.filter(user=request.user, is_deleted=False)
    eligible_qs = (
        base
        .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
        .exclude(category_source="user")
    )
    n = eligible_qs.count()

    if n == 0:
        messages.info(request, "No eligible uncategorized transactions to categorize.")
        return redirect("upload")
    request.session["last_ai_pre"] = {
        "kind": "uncategorized",
        "considered": n,
        "started_at": timezone.now().isoformat(),
    }

    request.session["last_ai_run_started_at"] = timezone.now().isoformat()

    return redirect("/ai/full/?mode=uncat")

@login_required
def ai_recheck_all(request):
    """
    Re-evaluate categories:
      - scope=ai   -> only AI-labeled rows
      - scope=all  -> everything except user-labeled
      - default    -> ai
    Stamps a session timestamp so Review (AI) can show only rows from the latest run.
    """
    from django.utils import timezone

    scope = (request.GET.get("scope") or "ai").lower()
    base = Transaction.objects.filter(user=request.user, is_deleted=False)

    if scope == "all":
        n = base.exclude(category_source="user").count()
        mode = "all"
        kind = "recheck_all"
        if n == 0:
            messages.info(request, "No eligible transactions to recheck (excluding user-labeled).")
            return redirect("upload")
    else:
        n = base.filter(category_source="ai").count()
        mode = "ai"
        kind = "recheck_ai"
        if n == 0:
            messages.info(request, "No AI-labeled transactions to recheck.")
            return redirect("upload")

    # PRG card + last run timestamp
    request.session["last_ai_pre"] = {
        "kind": kind,
        "considered": n,
        "started_at": timezone.now().isoformat(),
    }
    request.session["last_ai_run_started_at"] = timezone.now().isoformat()

    return redirect(f"/ai/full/?mode={mode}")


# ----------------------------- Soft delete -----------------------------

@login_required
def tx_delete(request, tx_id):
    tx = get_object_or_404(Transaction, id=tx_id, user=request.user)
    if request.method == "POST":
        note = (request.POST.get("note") or "").strip()[:200]
        if not tx.is_deleted:
            tx.is_deleted = True
            tx.deleted_at = timezone.now()
            tx.deleted_note = note
            tx.save(update_fields=["is_deleted", "deleted_at", "deleted_note"])
            messages.success(request, "Transaction deleted.")
        else:
            messages.info(request, "Transaction was already deleted.")
        return redirect(request.POST.get("next") or "upload")
    messages.error(request, "Invalid request method.")
    return redirect("upload")

@login_required
def tx_restore(request, tx_id):
    tx = get_object_or_404(Transaction, id=tx_id, user=request.user)
    if request.method == "POST":
        if tx.is_deleted:
            tx.is_deleted = False
            tx.deleted_at = None
            tx.save(update_fields=["is_deleted", "deleted_at"])
            messages.success(request, "Transaction restored.")
        else:
            messages.info(request, "Transaction is not deleted.")
        return redirect(request.POST.get("next") or "deleted_list")
    messages.error(request, "Invalid request method.")
    return redirect("deleted_list")

@login_required
def deleted_list(request):
    qs = Transaction.objects.filter(user=request.user, is_deleted=True).order_by("-deleted_at", "-id")
    try:
        per = max(5, min(200, int(request.GET.get("per") or 50)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "deleted.html", {"page_obj": page_obj, "total": paginator.count, "per_value": per})

# ----------------------------- Review pages -----------------------------

@login_required
def review_low_conf(request):
    qs = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        ai_suggested_fk__isnull=False,
    ).order_by("-id")
    try:
        per = max(5, min(200, int(request.GET.get("per") or 50)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))
    categories = Category.objects.filter(user=request.user).order_by("name")
    return render(request, "review_low.html", {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
        "categories": categories,
    })

@login_required
@require_POST
def review_low_apply(request):
    # 1. Read the JSON payload
    changes_raw = request.POST.get("changes_json")
    if not changes_raw:
        messages.info(request, "No changes to apply.")
        return redirect("review_low_conf")

    try:
        mapping = json.loads(changes_raw)
    except Exception:
        messages.error(request, "Invalid data format.")
        return redirect("review_low_conf")

    if not mapping:
        messages.info(request, "No changes selected.")
        return redirect("review_low_conf")

    # 2. Optimizing the DB fetch
    # Get all relevant transactions in one go
    tx_ids = [int(k) for k in mapping.keys() if str(k).isdigit()]
    transactions = Transaction.objects.filter(id__in=tx_ids, user=request.user, is_deleted=False)

    # Get all relevant categories
    cat_ids = {int(v) for v in mapping.values() if str(v).isdigit()}
    cats = {c.id: c for c in Category.objects.filter(user=request.user, id__in=cat_ids)}

    applied = 0

    # 3. Apply loop
    for tx in transactions:
        new_cat_id = mapping.get(str(tx.id))
        if not new_cat_id:
            continue

        try:
            cat = cats.get(int(new_cat_id))
        except (ValueError, TypeError):
            continue

        if cat:
            tx.category_fk = cat
            tx.category = cat.name
            tx.category_source = "user"
            # Clear AI fields since user made a decision
            tx.ai_suggested_fk = None
            tx.ai_confidence = None

            # We use update_fields for performance
            tx.save(update_fields=["category_fk", "category", "category_source", "ai_suggested_fk", "ai_confidence"])
            applied += 1

    messages.success(request, f"Applied {applied} changes.")
    return redirect("review_low_conf")


@login_required
def review_ai_recent(request):
    """
    Shows only AI-labeled rows from the latest AI run (based on session timestamp).
    Falls back to all AI rows if the timestamp is missing.
    """
    qs = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        category_source="ai",
    )

    ts = request.session.get("last_ai_run_started_at")
    if ts:
        try:
            from datetime import datetime
            from django.utils import timezone
            dt = datetime.fromisoformat(ts)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            qs = qs.filter(updated_at__gte=dt)
        except Exception:
            pass

    qs = qs.order_by("-updated_at", "-id")

    per = request.GET.get("per")
    try:
        per = max(5, min(200, int(per)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "review_ai.html", {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
    })


# ----------------------------- Overview -----------------------------

@login_required
def overview(request):
    """
    Overview:
      - Balance snapshot anchor + reconstructed monthly balances
      - Per-account effective balances (manual if set, else ledger)
      - Savings goals (progress from selected accounts' effective balances)
      - Income vs Spending by month + Net by month table
      - Spending per category by month + merchant breakdown per category+month
      - Budgets vs Spent (category caps)
    """
    # ===== BalanceSnapshot POST (UPDATED with anomaly logging) =====
    if request.method == "POST" and request.POST.get("form") == "balance":
        raw_amount = (request.POST.get("amount") or "").strip().replace(",", ".")
        raw_ts     = (request.POST.get("timestamp") or "").strip()
        note       = (request.POST.get("note") or "").strip()

        try:
            amount = Decimal(raw_amount)
        except (InvalidOperation, TypeError):
            messages.error(request, "Enter a valid number for balance.")
            return redirect("overview")

        try:
            ts = datetime.strptime(raw_ts, "%Y-%m-%dT%H:%M")
            ts = timezone.make_aware(ts, timezone.get_current_timezone())
        except Exception:
            ts = timezone.now()

        # Create or update the "latest" snapshot behavior as you had:
        latest = BalanceSnapshot.objects.filter(user=request.user).order_by("-timestamp").first()

        # We will save a new snapshot row (recommended for history),
        # but if you prefer "update latest", you can adjust.
        # Here we *add* a new snapshot:
        new_snap = BalanceSnapshot.objects.create(
            user=request.user,
            amount=amount,
            currency="EUR",
            timestamp=ts,
            note=note[:180]
        )

        # Find the immediate previous snapshot *before* this new one to compare
        prev_snap = (BalanceSnapshot.objects
                     .filter(user=request.user, timestamp__lt=new_snap.timestamp)
                     .order_by("-timestamp")
                     .first())

        # Compare ledger vs snapshots and log anomaly if off
        discrepancy = _maybe_log_balance_anomaly(
            request.user, prev_snap, new_snap,
            note="Discrepancy detected after new snapshot was added"
        )

        if discrepancy is None:
            messages.success(request, "Balance snapshot added.")
        else:
            sign = "+" if discrepancy >= 0 else "−"
            messages.warning(
                request,
                f"Anomaly detected: snapshot delta vs. transactions differ by {sign}{abs(discrepancy):.2f} EUR. "
                "We recorded it and will use your snapshot as the new anchor."
            )

        return redirect("overview")

    # ===== Effective account balances (unchanged) =====
    accounts = list(MoneySource.objects.filter(user=request.user).order_by("type", "name"))
    tx_base  = Transaction.objects.filter(user=request.user, is_deleted=False)

    tx_sums = (
        tx_base.values("money_source_id", "in_out").annotate(total=Sum("amount"))
    )
    from collections import defaultdict
    ledger_map = defaultdict(lambda: Decimal("0"))
    for row in tx_sums:
        ms_id = row["money_source_id"]
        amt = row["total"] or Decimal("0")
        if row["in_out"] == Transaction.IN:
            ledger_map[ms_id] += amt
        else:
            ledger_map[ms_id] -= amt

    total_effective = Decimal("0")
    effective_map = {}
    for acc in accounts:
        ledger_val = ledger_map.get(acc.id, Decimal("0"))
        effective = getattr(acc, "manual_balance", None)
        if effective is None:
            effective = ledger_val
        acc.effective_balance = effective
        effective_map[acc.id] = effective
        total_effective += effective if acc.is_active else Decimal("0")

    # ===== Savings goals (unchanged) =====
    try:
        goals_raw = (
            SavingsGoal.objects
            .filter(user=request.user, is_active=True)
            .prefetch_related("accounts")
            .order_by("created_at", "id")
        )
    except Exception:
        goals_raw = []

    goals = []
    for g in goals_raw:
        accs = [a for a in g.accounts.all() if a.is_active]
        current = sum((effective_map.get(a.id, Decimal("0")) for a in accs), Decimal("0"))
        target  = g.target_amount or Decimal("0")
        pct = float((current / target * 100) if target > 0 else 0.0)
        pct = 0.0 if pct != pct else max(0.0, min(pct, 200.0))
        goals.append({
            "id": g.id,
            "name": g.name,
            "target": float(target),
            "current": float(current),
            "pct": pct,
            "eta": g.eta_date.strftime("%Y-%m-%d") if getattr(g, "eta_date", None) else None,
            "accounts": [{"id": a.id, "name": a.name} for a in accs],
        })

    # ===== Income vs Spending by month + Net table (unchanged) =====
    qs_month = tx_base.annotate(month=TruncMonth("date"))
    by_month = qs_month.values("month", "in_out").annotate(total=Sum("amount"))

    def _month_key(val):
        if val is None:
            return None
        if isinstance(val, datetime):
            d = val.date()
            return _date(d.year, d.month, 1)
        if isinstance(val, _date):
            return _date(val.year, val.month, 1)
        return None

    months_set = set()
    for row in by_month:
        mk = _month_key(row["month"])
        if mk: months_set.add(mk)
    months = sorted(months_set)
    labels = [m.strftime("%Y-%m") for m in months]

    totals_in = {m: Decimal("0") for m in months}
    totals_out = {m: Decimal("0") for m in months}
    for row in by_month:
        mk = _month_key(row["month"])
        if not mk:
            continue
        amt = row["total"] or Decimal("0")
        if row["in_out"] == Transaction.IN:
            totals_in[mk] += amt
        else:
            totals_out[mk] += amt

    income_series   = [float(totals_in[m]) for m in months]
    spending_series = [float(totals_out[m]) for m in months]
    net_rows = [{"month": m.strftime("%Y-%m"), "net": float(totals_in[m] - totals_out[m])} for m in months]

    # ===== Category chart + breakdown (unchanged) =====
    qs_cat = (
        tx_base.filter(in_out=Transaction.OUT, category_fk__isnull=False)
               .annotate(month=TruncMonth("date"))
               .values("month", "category_fk__name")
               .annotate(total=Sum("amount"))
    )

    cat_months_set, cat_names_set = set(), set()
    for row in qs_cat:
        mk = _month_key(row["month"])
        if mk: cat_months_set.add(mk)
        cname = row["category_fk__name"]
        if cname: cat_names_set.add(cname)

    cat_months = sorted(set(months) | cat_months_set)
    cat_labels = [m.strftime("%Y-%m") for m in cat_months]
    cat_names  = sorted(cat_names_set)

    from collections import defaultdict as _dd
    data_map = _dd(lambda: {m: Decimal("0") for m in cat_months})
    for row in qs_cat:
        mk = _month_key(row["month"]); cname = row["category_fk__name"]
        if mk and cname:
            data_map[cname][mk] += (row["total"] or Decimal("0"))
    series_by_cat = {cname: [float(data_map[cname][m]) for m in cat_months] for cname in cat_names}

    # Merchant breakdown per category per month (unchanged)
    from django.db.models import Count
    qs_merchant = (
        tx_base.filter(in_out=Transaction.OUT, category_fk__isnull=False)
               .annotate(month=TruncMonth("date"))
               .values("month", "category_fk__name", "merchant")
               .annotate(total=Sum("amount"), tx_count=Count("id"))
    )

    breakdown_by_cat_month = {}
    for row in qs_merchant:
        mk = _month_key(row["month"])
        if not mk:
            continue
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

    # ===== Balance timeline anchor (unchanged) =====
    latest_snap = BalanceSnapshot.objects.filter(user=request.user).order_by("-timestamp").first()
    if latest_snap:
        lt = timezone.localtime(latest_snap.timestamp)
        anchor_month = _date(lt.year, lt.month, 1)
        anchor_value = Decimal(latest_snap.amount)
    else:
        now = timezone.localtime().date()
        anchor_month = _date(now.year, now.month, 1)
        anchor_value = total_effective

    net_delta = {m: (totals_in.get(m, Decimal("0")) - totals_out.get(m, Decimal("0"))) for m in months}

    def _add_month(d: _date) -> _date:
        return _date(d.year + 1, 1, 1) if d.month == 12 else _date(d.year, d.month + 1, 1)

    all_months = set(months) | {anchor_month}
    if months:
        start = min(min(months), anchor_month); end = max(max(months), anchor_month)
    else:
        start = end = anchor_month

    seq, cur = [], start
    while cur <= end:
        seq.append(cur); cur = _add_month(cur)
    for m in seq:
        net_delta.setdefault(m, Decimal("0"))

    balances = {}
    idx = seq.index(anchor_month)
    for i in range(idx, len(seq)):
        m = seq[i]
        balances[m] = anchor_value if i == idx else balances[seq[i - 1]] + net_delta[m]
    for i in range(idx, 0, -1):
        curr = seq[i]; prev = seq[i - 1]
        balances[prev] = balances[curr] - net_delta[curr]

    balance_labels_json = json.dumps([m.strftime("%Y-%m") for m in seq])
    balance_values_json = json.dumps([float(balances[m]) for m in seq])
    now_val = timezone.localtime().strftime("%Y-%m-%dT%H:%M")

    # ===== Budgets (unchanged) =====
    capped_qs = (
        Category.objects
        .filter(user=request.user, monthly_cap__isnull=False)
        .exclude(monthly_cap=0)
        .order_by("name")
    )
    budget_has_caps = capped_qs.exists()

    months_for_budgets = sorted({_date(d.year, d.month, 1) for d in tx_base.values_list("date", flat=True)})
    if not months_for_budgets:
        today = timezone.localdate()
        months_for_budgets = [_date(today.year, today.month, 1)]

    budget_month_keys = [m.strftime("%Y-%m") for m in months_for_budgets]

    budget_all = {}
    for m in months_for_budgets:
        start = _date(m.year, m.month, 1)
        end   = _date(m.year, m.month, monthrange(m.year, m.month)[1])

        spent_rows = (
            tx_base.filter(
                in_out=Transaction.OUT,
                date__gte=start, date__lte=end,
                category_fk__in=capped_qs
            )
            .values("category_fk")
            .annotate(total=Sum("amount"))
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

    # ===== Context =====
    ctx = {
        # balances
        "latest_snap": latest_snap,
        "balance_labels_json": balance_labels_json,
        "balance_values_json": balance_values_json,
        "now_val": now_val,

        # income/spend + net
        "labels_json": json.dumps(labels),
        "income_json": json.dumps(income_series),
        "spending_json": json.dumps(spending_series),
        "net_rows": net_rows,

        # category series + breakdown
        "cat_month_labels_json": json.dumps(cat_labels),
        "series_by_cat_json": json.dumps(series_by_cat),
        "cat_names": cat_names,
        "breakdown_by_cat_month_json": json.dumps(breakdown_by_cat_month),

        # accounts card
        "total_accounts_balance": float(total_effective),
        "accounts_with_balances": accounts,

        # savings goals
        "goals": goals,

        # budgets (caps)
        "budget_all_json": json.dumps(budget_all),
        "budget_month_keys": budget_month_keys,
        "budget_selected_key": budget_selected_key,
        "budget_has_caps": budget_has_caps,
    }
    return render(request, "overview.html", ctx)


# ----------------------------- Profile (manual balance + snapshot) -----------------------------

# ----------------------------- Profile (manual balance + snapshot) -----------------------------

@login_required
def profile(request):
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        # Accounts
        if action == "add":
            name = (request.POST.get("name") or "").strip()
            typ  = (request.POST.get("type") or "").strip()
            if not name or typ not in dict(MoneySource.TYPE_CHOICES):
                messages.error(request, "Provide a valid name and type.")
                return redirect("profile")
            if MoneySource.objects.filter(user=request.user, name=name).exists():
                messages.error(request, "Account with this name already exists.")
                return redirect("profile")
            MoneySource.objects.create(user=request.user, name=name, type=typ, is_active=True)
            messages.success(request, "Account added.")
            return redirect("profile")

        if action == "rename":
            acc_id = request.POST.get("id")
            new_name = (request.POST.get("name") or "").strip()
            acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)
            if new_name:
                exists = MoneySource.objects.filter(user=request.user, name=new_name).exclude(id=acc.id).exists()
                if exists:
                    messages.error(request, f'Another account named “{new_name}” already exists.')
                else:
                    acc.name = new_name
                    acc.save(update_fields=["name", "updated_at"])
                    messages.success(request, "Account renamed.")
            else:
                messages.error(request, "Name cannot be empty.")
            return redirect("profile")

        if action == "toggle":
            acc_id = request.POST.get("id")
            acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)
            acc.is_active = not acc.is_active
            acc.save(update_fields=["is_active", "updated_at"])
            messages.success(request, ("Activated" if acc.is_active else "Deactivated") + f' “{acc.name}”.')
            return redirect("profile")

        if action == "setdefault":
            acc_id = request.POST.get("id")
            try:
                acc = MoneySource.objects.get(id=int(acc_id), user=request.user, is_active=True)
                request.session["default_src_id"] = acc.id
                messages.success(request, f'“{acc.name}” set as default import account.')
            except (MoneySource.DoesNotExist, ValueError):
                messages.error(request, "Account not found or inactive.")
            return redirect("profile")

        if action == "setbalance":
            acc_id = request.POST.get("id")
            raw = (request.POST.get("amount") or "").strip().replace(",", ".")
            acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)

            if raw == "":
                # Clear manual balance (no snapshot here, same as your current logic)
                acc.manual_balance = None
                acc.balance_updated_at = timezone.now()
                acc.save(update_fields=["manual_balance", "balance_updated_at"])
                messages.success(request, "Manual balance cleared.")
                return redirect("profile")

            # Save manual balance and record a global snapshot for anomaly tracking
            try:
                val = Decimal(raw)
                acc.manual_balance = val
                acc.balance_updated_at = timezone.now()
                acc.save(update_fields=["manual_balance", "balance_updated_at"])

                # Compute total effective (post-change), as you already do
                ledger_map = _ledger_balance_by_source(request.user)  # existing helper
                total_effective = Decimal("0")
                for a in MoneySource.objects.filter(user=request.user, is_active=True):
                    eff = a.manual_balance if a.manual_balance is not None else ledger_map.get(a.id, Decimal("0"))
                    total_effective += (eff or Decimal("0"))

                # Grab the previous snapshot BEFORE creating a new one
                prev_snap = (BalanceSnapshot.objects
                             .filter(user=request.user)
                             .order_by("-timestamp")
                             .first())

                new_snap = BalanceSnapshot.objects.create(
                    user=request.user,
                    amount=total_effective,
                    currency="EUR",
                    timestamp=timezone.now(),
                    note=f"Snapshot after setting manual balance for {acc.name}",
                )

                # Compare vs ledger delta and log anomaly if needed
                # (helper is already in your codebase; we’re reusing it)
                discrepancy = _maybe_log_balance_anomaly(
                    request.user, prev_snap, new_snap,
                    note="After setbalance on Profile"
                )

                if prev_snap is None:
                    # First-ever snapshot for this user
                    messages.success(request, "Manual balance saved and an initial snapshot was recorded.")
                else:
                    if discrepancy:
                        sign = "+" if discrepancy >= 0 else "−"
                        messages.warning(
                            request,
                            f"Manual balance saved. Anomaly recorded: snapshot vs. transactions differ by "
                            f"{sign}{abs(discrepancy):.2f} EUR."
                        )
                    else:
                        messages.success(request, "Manual balance saved and a global snapshot was recorded.")
            except (InvalidOperation, TypeError):
                messages.error(request, "Enter a valid number.")
            return redirect("profile")

        # Category caps
        if action == "setcap":
            cat_id = request.POST.get("id")
            raw = (request.POST.get("amount") or "").strip().replace(",", ".")
            cat = get_object_or_404(Category, id=cat_id, user=request.user)
            if raw == "":
                cat.monthly_cap = None
                cat.save(update_fields=["monthly_cap"])
                messages.success(request, f'Removed cap for “{cat.name}”.')
            else:
                try:
                    val = Decimal(raw)
                    if val < 0:
                        raise InvalidOperation
                    cat.monthly_cap = val
                    cat.save(update_fields=["monthly_cap"])
                    messages.success(request, f'Saved cap for “{cat.name}”.')
                except (InvalidOperation, TypeError):
                    messages.error(request, "Enter a valid non-negative number.")
            return redirect("profile")

        # Savings goals
        if action == "goal_add":
            name = (request.POST.get("goal_name") or "").strip()
            target_raw = (request.POST.get("goal_target") or "").strip().replace(",", ".")
            try:
                target = Decimal(target_raw)
            except Exception:
                target = Decimal("0")
            g = SavingsGoal.objects.create(user=request.user, name=name, target_amount=target, is_active=True)
            for aid in request.POST.getlist("goal_accounts"):
                try:
                    a = MoneySource.objects.get(id=int(aid), user=request.user)
                    g.accounts.add(a)
                except MoneySource.DoesNotExist:
                    pass
            messages.success(request, "Goal created.")
            return redirect("profile")

        if action == "goal_toggle":
            gid = request.POST.get("goal_id")
            g = get_object_or_404(SavingsGoal, id=gid, user=request.user)
            g.is_active = not g.is_active
            g.save(update_fields=["is_active", "updated_at"])
            messages.success(request, ("Activated" if g.is_active else "Paused") + f' “{g.name}”.')
            return redirect("profile")

        if action == "goal_delete":
            gid = request.POST.get("goal_id")
            g = get_object_or_404(SavingsGoal, id=gid, user=request.user)
            g.delete()
            messages.success(request, "Goal deleted.")
            return redirect("profile")

    # ---------- GET ----------
    accounts = MoneySource.objects.filter(user=request.user).order_by("type", "name")

    tx_sums = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False)
        .values("money_source_id", "in_out")
        .annotate(total=Sum("amount"))
    )
    ledger_map = defaultdict(lambda: Decimal("0"))
    for row in tx_sums:
        ms_id = row["money_source_id"]
        amt = row["total"] or Decimal("0")
        if row["in_out"] == Transaction.IN:
            ledger_map[ms_id] += amt
        else:
            ledger_map[ms_id] -= amt

    total_effective = Decimal("0")
    acc_by_id = {}
    for acc in accounts:
        ledger_val = ledger_map.get(acc.id, Decimal("0"))
        effective = acc.manual_balance if acc.manual_balance is not None else ledger_val
        acc.effective_balance = effective
        acc_by_id[acc.id] = acc
        total_effective += effective if acc.is_active else Decimal("0")

    # Suggested caps (avg of last 3 full months)
    today = timezone.localdate()
    def month_start(y, m): return _date(y, m, 1)
    def month_end(y, m):   return _date(y, m, monthrange(y, m)[1])

    prev_year = today.year if today.month > 1 else today.year - 1
    prev_month = today.month - 1 if today.month > 1 else 12

    m3 = []
    y, m = prev_year, prev_month
    for _ in range(3):
        m3.append((y, m))
        if m == 1: y, m = y - 1, 12
        else: m -= 1
    m3 = list(reversed(m3))

    start_3 = month_start(m3[0][0], m3[0][1])
    end_3   = month_end(m3[-1][0], m3[-1][1])

    spend_3 = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False, in_out=Transaction.OUT, date__gte=start_3, date__lte=end_3)
        .values("category_fk")
        .annotate(total=Sum("amount"))
    )
    spend_map = {r["category_fk"]: (r["total"] or Decimal("0")) for r in spend_3}

    cats = Category.objects.filter(user=request.user).order_by("name")
    caps_rows = []
    for c in cats:
        tot = spend_map.get(c.id, Decimal("0"))
        suggested = (tot / Decimal("3")) if tot is not None else Decimal("0")
        caps_rows.append({
            "id": c.id, "name": c.name, "color": c.color, "cap": c.monthly_cap, "suggested": suggested,
        })

    # Goals (active + paused)
    goals_qs = (
        SavingsGoal.objects
        .filter(user=request.user)
        .prefetch_related("accounts")
        .order_by("created_at", "id")
    )
    goals = []
    for g in goals_qs:
        sel_accs = [acc_by_id[a.id] for a in g.accounts.all() if a.id in acc_by_id]
        current = sum((a.effective_balance or Decimal("0") for a in sel_accs), Decimal("0"))
        target  = g.target_amount or Decimal("0")
        pct = float((current / target * 100) if target > 0 else 0.0)
        pct = 0.0 if pct != pct else max(0.0, min(pct, 200.0))
        goals.append({
            "obj": g, "accounts": sel_accs, "current": float(current), "target": float(target),
            "progress_pct": round(pct, 1), "eta_months": None,
        })

    ctx = {
        "accounts": accounts,
        "total_accounts_balance": float(total_effective),
        "type_choices": MoneySource.TYPE_CHOICES,
        "default_id": request.session.get("default_src_id"),
        "caps_rows": caps_rows,
        "caps_window_note": f"Based on average spending across {m3[0][0]:04d}-{m3[0][1]:02d} to {m3[-1][0]:04d}-{m3[-1][1]:02d}.",
        "goals": goals,
    }
    return render(request, "profile.html", ctx)


# ----------------------------- Statistics -----------------------------

@login_required
def statistics(request):
    user = request.user
    today = timezone.localtime().date()
    base = Transaction.objects.filter(user=user, is_deleted=False)

    if not base.exists():
        return render(request, "statistics.html", {
            "empty_state": True,
            # lifetime cards
            "total_in": 0.0, "total_out": 0.0, "lifetime_net": 0.0,
            "avg_month_in": 0.0, "avg_month_out": 0.0,
            "best_month": None, "best_month_net": None,
            "worst_month": None, "worst_month_net": None,
            "largest_tx": None, "total_tx": 0,
            "distinct_merchants": 0, "most_freq_merchant": None, "most_freq_merchant_cnt": None,
            "coverage_pct": 0.0,
            # pickers & charts
            "available_month_keys": [], "start_key": None, "end_key": None,
            "cat_labels_json": "[]", "cat_values_json": "[]", "share_note": "",
            "cat_summary_rows": [], "start_date": None, "end_date": None,
            "weekday_labels_json": '["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]',
            "weekday_values_json": "[0,0,0,0,0,0,0]",
            "last90_from": None, "last90_to": None,
            "all_categories": [], "selected_cat_ids": [], "include_uncat": False,
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
        if isinstance(val, datetime): d = val.date(); return _date(d.year, d.month, 1)
        if isinstance(val, _date): return _date(val.year, val.month, 1)
        return None
    month_map_in, month_map_out = {}, {}
    months_set = set()
    for r in by_month:
        mk = _mk(r["m"])
        if not mk: continue
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

    # Category share range picker (defaults to last full month)
    all_months = sorted({_mk(x) for x in base.values_list("date", flat=True) if _mk(x) is not None})
    def key_from_date(d: _date) -> str: return d.strftime("%Y-%m")
    def month_start_from_key(k: str) -> _date: y, m = map(int, k.split("-")); return _date(y, m, 1)
    def month_end_from_key(k: str) -> _date: y, m = map(int, k.split("-")); return _date(y, m, monthrange(y, m)[1])
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
    def is_valid_key(k): return isinstance(k, str) and _re.match(r"^\d{4}-\d{2}$", k)
    if not is_valid_key(start_key): start_key = default_start_key
    if not is_valid_key(end_key): end_key = default_end_key

    start_date = month_start_from_key(start_key)
    end_date = month_end_from_key(end_key)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
        start_key, end_key = end_key, start_key
    months_in_range = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    if months_in_range < 1: months_in_range = 1

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

# ----------------------------- Reports (+ anomalies history) -----------------------------

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

@login_required
@require_http_methods(["GET","POST"])
def teach_ai(request):
    """
    Teach AI: OUT flow only.
    GET: list one row per normalized merchant (OUT), ranked by frequency (up to 30).
    POST: apply one chosen category per merchant across all matching uncategorized OUT rows.
    """
    ensure_default_categories(request.user)

    MIN_USER_LABELS = 20
    BATCH_MERCHANTS = 20

    # Base pool: only truly uncategorized, non-deleted, and OUT flow only
    base = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False, in_out=Transaction.OUT)
        .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
    )

    if request.method == "POST":
        # Expect keys like: mk__out|<normalized_merchant> = <category_id>
        pairs = []
        for k, v in request.POST.items():
            if not k.startswith("mk__"):
                continue
            if v:
                pairs.append((k[len("mk__"):], v))

        if not pairs:
            messages.error(request, "Select categories for at least one merchant.")
            return redirect("teach_ai")

        cat_ids = {int(cid) for _, cid in pairs if str(cid).isdigit()}
        cats = {c.id: c for c in Category.objects.filter(user=request.user, id__in=cat_ids)}

        applied = 0
        # Pre-fetch applicable OUT rows to speed normalization matching
        qs_apply = base.exclude(merchant="").only("id", "merchant", "in_out", "category_fk", "category", "category_source")
        for mk, cid in pairs:
            try:
                flow, norm = mk.split("|", 1)
            except ValueError:
                continue

            # Defensive: only OUT flow allowed here
            if flow != Transaction.OUT:
                continue

            cat = cats.get(int(cid))
            if not cat:
                continue

            batch_ids = []
            for t in qs_apply:
                if _normalize_merchant(t.merchant or "") == norm:
                    # Guard: never set Income on OUT
                    if cat.name == "Income":
                        continue
                    batch_ids.append(t.id)

            if batch_ids:
                Transaction.objects.filter(id__in=batch_ids).update(
                    category_fk=cat,
                    category=cat.name,
                    category_source="user",
                    ai_suggested_fk=None,
                    ai_confidence=None,
                    updated_at=timezone.now(),
                )
                applied += len(batch_ids)

        if applied:
            messages.success(request, f"Applied categories to {applied} transaction(s).")
        else:
            messages.info(request, "Nothing to apply.")
        return redirect("upload")

    # ---------------- GET: build one row per normalized merchant (OUT only) ----------------
    from collections import defaultdict
    counts = defaultdict(int)
    samples = defaultdict(lambda: {"merchant": "", "flow": ""})

    for t in base.exclude(merchant="").only("merchant", "in_out"):
        norm = _normalize_merchant(t.merchant or "")
        key = (Transaction.OUT, norm)
        counts[key] += 1
        if not samples[key]["merchant"]:
            samples[key]["merchant"] = (t.merchant or "").strip()
            samples[key]["flow"] = Transaction.OUT

    ranked = sorted(samples.items(), key=lambda kv: (-counts[kv[0]], kv[0][1]))

    rows = []
    for (flow, norm), meta in ranked[:BATCH_MERCHANTS]:
        merchant_display = meta["merchant"] or norm
        form_key = f"mk__{flow}|{norm}"
        rows.append({
            "merchant_display": merchant_display,
            "flow": flow,  # always 'out' here
            "count": counts[(flow, norm)],
            "form_key": form_key,
        })

    categories = Category.objects.filter(user=request.user).order_by("name")
    return render(request, "teach_ai.html", {
        "rows": rows,
        "categories": categories,
        "target_labels": MIN_USER_LABELS,
        "total_unique_shown": len(rows),
    })




@login_required
@require_POST
def onboarding_mark_done(request):
    step = (request.POST.get("step") or "").strip()
    state, _ = OnboardingState.objects.get_or_create(user=request.user)

    if step == "categories":
        state.categories_done = True
        # also keep session if you want:
        request.session["onboarding_categories_done"] = True

    elif step == "ready":
        state.ready_dismissed = True
        request.session["onboarding_ready_dismissed"] = True

    # (If later you add explicit buttons for "upload", "balance", "teach_ai", mark them here.)

    state.save(update_fields=["categories_done", "ready_dismissed", "updated_at"])
    messages.success(request, "Thanks! We’ve saved your onboarding progress.")
    return redirect(request.META.get("HTTP_REFERER") or "upload")


from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

@login_required
def review_ai_runs(request):
    qs = (AiRun.objects
          .filter(user=request.user)
          .order_by("-started_at"))

    kind = (request.GET.get("kind") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if kind in {"autocategorize", "recheck"}:
        qs = qs.filter(kind=kind)
    if status in {"queued", "running", "done", "failed"}:
        qs = qs.filter(status=status)

    try:
        per = max(5, min(200, int(request.GET.get("per") or 20)))
    except (TypeError, ValueError):
        per = 20

    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    STATUSES = ["queued", "running", "done", "failed"]  # ← add this
    ctx = {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
        "kind": kind,
        "status": status,
        "statuses": STATUSES,  # ← and pass it
    }
    return render(request, "review_ai.html", ctx)



@login_required
def review_ai_run_detail(request, run_id: int):
    """Show a single AI run and the items (what changed / parked)."""
    run = get_object_or_404(AiRun, id=run_id, user=request.user)
    items = (run.items
             .select_related("transaction", "old_category_fk", "new_category_fk")
             .all())

    action = (request.GET.get("action") or "").strip()
    if action in {"applied", "parked", "skipped"}:
        items = items.filter(action=action)

    try:
        per = max(5, min(200, int(request.GET.get("per") or 50)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(items.order_by("-id"), per)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx = {
        "run": run,
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
        "action": action,
    }
    return render(request, "review_ai_detail.html", ctx)
