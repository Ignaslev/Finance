# finance/utils.py
import re
import hashlib
import os
from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from .models import Category, Transaction, BalanceAnomaly, BalanceSnapshot, PortfolioSnapshot
from django.db.models import Sum, Case, When, F, DecimalField


def _normalize_text_basic(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _normalize_merchant(name: str) -> str:
    if not name: return ""
    s = name.upper()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[#,/ ]?X[- ]?\d+$", "", s)
    s = re.sub(r"\s+\d{3,}$", "", s)
    return s

def build_fingerprint_v2(*, date_iso: str, time_str: str | None, merchant: str,
                         amount, currency: str, in_out: str, money_source_id: int,
                         description: str | None) -> str:
    try:
        norm_merchant = _normalize_merchant(merchant or "")
    except NameError:
        norm_merchant = _normalize_text_basic(merchant or "").upper()

    norm_desc = _normalize_text_basic(description or "")
    desc_prefix = norm_desc[:80]
    desc8 = hashlib.sha1(desc_prefix.encode("utf-8")).hexdigest()[:8] if desc_prefix else ""
    tpart = (time_str or "").strip()
    return f"{date_iso}|{tpart}|{norm_merchant}|{amount}|{currency}|{in_out}|{money_source_id}|{desc8}"

def parse_amount(raw):
    if raw is None: return Decimal("0")
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
    if not s: return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def parse_decimal_filter(s):
    s = (s or "").strip().replace("€", "").replace(",", ".")
    if not s: return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None

def ensure_default_categories(user):
    have = set(Category.objects.filter(user=user).values_list("name", flat=True))
    need = [Category(user=user, name=n) for n in settings.DEFAULT_CATEGORIES if n not in have]
    if need:
        Category.objects.bulk_create(need)

ANOMALY_EPSILON = Decimal("0.50")

def _ledger_delta_between(user, d1, d2):
    from django.db.models import Sum
    inc = (Transaction.objects
           .filter(user=user, is_deleted=False, in_out=Transaction.IN, date__gte=d1, date__lte=d2)
           .aggregate(s=Sum("amount"))["s"] or Decimal("0"))
    out = (Transaction.objects
           .filter(user=user, is_deleted=False, in_out=Transaction.OUT, date__gte=d1, date__lte=d2)
           .aggregate(s=Sum("amount"))["s"] or Decimal("0"))
    return inc - out

def _maybe_log_balance_anomaly(user, prev_snap, new_snap, note="Detected after snapshot update"):
    if not prev_snap: return
    d1 = timezone.localtime(prev_snap.timestamp).date()
    d2 = timezone.localtime(new_snap.timestamp).date()
    if d2 < d1: d1, d2 = d2, d1

    expected = _ledger_delta_between(user, d1, d2)
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

def _reconcile_global(user):
    """
    Build anomaly segments between consecutive BalanceSnapshots.
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

        calc_end = Decimal(a.amount) + net_tx
        snap_delta = Decimal(b.amount) - Decimal(a.amount)
        diff = Decimal(b.amount) - calc_end
        is_anom = abs(diff) > Decimal("0.01")

        segs.append({
            "spotted_at": b.timestamp,
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
        })
    segs.sort(key=lambda s: s["spotted_at"], reverse=True)
    return segs