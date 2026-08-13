import re
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from finance.models import Category, Transaction
from finance.utils import _normalize_merchant


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


def canonical_spending_merchant(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "—"

    upper_raw = raw.upper().strip()
    for display, patterns in CHAIN_CANONICALS:
        if any(upper_raw.startswith(pattern) for pattern in patterns):
            return display

    norm = (_normalize_merchant(raw) or "").upper().strip()
    if not norm:
        return raw[:80] or "—"

    norm = re.sub(r"\b(UAB|AB|MB|VSI|VŠĮ|IĮ|II|LTD|LIMITED|OOO|AS)\b", " ", norm)
    norm = re.sub(r"\b[A-Z]-?\d{2,}\b", " ", norm)
    norm = re.sub(r"\b\d{2,}\b", " ", norm)
    norm = re.sub(r"[,;/|]+", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()

    parts = norm.split()
    if len(parts) >= 2:
        stem = " ".join(parts[:2]) if len(parts[0]) >= 3 and len(parts[1]) >= 2 else parts[0]
    else:
        stem = norm

    return (stem or norm or raw).title()


def build_spending_category_analytics(user, base_qs=None):
    base = base_qs if base_qs is not None else Transaction.objects.filter(user=user, is_deleted=False)
    base = base.filter(is_internal_transfer=False)

    monthly_totals = (
        base.filter(in_out=Transaction.OUT, category_fk__isnull=False)
        .annotate(month=TruncMonth("date"))
        .values("month", "category_fk__name")
        .annotate(total=Sum("amount"))
    )

    month_set = set()
    for month in base.annotate(month=TruncMonth("date")).values_list("month", flat=True).distinct():
        if hasattr(month, "date"):
            month = month.date()
        if month:
            month_set.add(month.replace(day=1))

    category_set = set()
    normalized_rows = []
    for row in monthly_totals:
        month = row["month"]
        if hasattr(month, "date"):
            month = month.date()
        if not month or not row["category_fk__name"]:
            continue
        month = month.replace(day=1)
        month_set.add(month)
        category_set.add(row["category_fk__name"])
        normalized_rows.append((month, row["category_fk__name"], row["total"] or Decimal("0")))

    months = sorted(month_set)
    category_names = sorted(category_set)
    data_map = defaultdict(lambda: {month: Decimal("0") for month in months})
    for month, category_name, total in normalized_rows:
        data_map[category_name][month] += total

    series_by_category = {
        category_name: [float(data_map[category_name][month]) for month in months]
        for category_name in category_names
    }

    merchant_rows = (
        base.filter(in_out=Transaction.OUT, category_fk__isnull=False)
        .select_related("category_fk", "money_source")
        .only(
            "date",
            "merchant",
            "amount",
            "currency",
            "category_fk__name",
            "money_source__name",
        )
        .order_by("date", "id")
    )
    breakdown_acc = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {
        "merchant": "",
        "total": Decimal("0"),
        "count": 0,
    })))
    transaction_acc = defaultdict(lambda: defaultdict(list))

    for transaction in merchant_rows:
        if not transaction.date:
            continue
        month_key = transaction.date.replace(day=1).strftime("%Y-%m")
        category_name = transaction.category_fk.name
        merchant = canonical_spending_merchant(transaction.merchant or "")
        bucket = breakdown_acc[category_name][month_key][merchant.lower()]
        bucket["merchant"] = merchant
        bucket["total"] += transaction.amount or Decimal("0")
        bucket["count"] += 1
        transaction_acc[category_name][month_key].append({
            "id": transaction.id,
            "date": transaction.date.strftime("%Y-%m-%d"),
            "merchant": (transaction.merchant or "-")[:120],
            "account": transaction.money_source.name if transaction.money_source else "",
            "amount": float(transaction.amount or Decimal("0")),
            "currency": transaction.currency or "EUR",
        })

    breakdown = {}
    for category_name, per_month in breakdown_acc.items():
        breakdown[category_name] = {}
        for month_key, merchants in per_month.items():
            rows = []
            for data in merchants.values():
                count = int(data["count"] or 0)
                total = data["total"] or Decimal("0")
                rows.append({
                    "merchant": data["merchant"][:80],
                    "total": float(total),
                    "count": count,
                    "avg": float(total / count) if count else 0.0,
                })
            breakdown[category_name][month_key] = sorted(
                rows,
                key=lambda item: (-item["total"], item["merchant"]),
            )[:12]

    top_transactions = {}
    for category_name, per_month in transaction_acc.items():
        top_transactions[category_name] = {}
        for month_key, rows in per_month.items():
            top_transactions[category_name][month_key] = sorted(
                rows,
                key=lambda item: (-item["amount"], item["date"], item["id"]),
            )[:10]

    caps = {}
    for category in Category.objects.filter(user=user):
        cap = category.monthly_cap or Decimal("0")
        caps[category.name] = float(cap) if cap > 0 else 0

    current_month = timezone.localdate().replace(day=1)
    current_month_key = current_month.strftime("%Y-%m")
    current_category_names = [
        category_name
        for category_name in category_names
        if data_map[category_name].get(current_month, Decimal("0")) > 0
    ]

    return {
        "category_names": category_names,
        "month_labels": [month.strftime("%Y-%m") for month in months],
        "series_by_category": series_by_category,
        "breakdown": breakdown,
        "top_transactions": top_transactions,
        "caps": caps,
        "current_month_key": current_month_key,
        "current_category_names": current_category_names,
        "current_category_values": [
            float(data_map[category_name].get(current_month, Decimal("0")))
            for category_name in current_category_names
        ],
    }
