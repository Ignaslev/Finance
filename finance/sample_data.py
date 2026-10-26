"""Sample data so new users can see the app before fetching a statement.

Everything sample lives in its own account and an ImportBatch with bank_key="sample", so it can be
removed in one go and is left out of the funnel, reminders and AI runs.
"""
import hashlib
import random
from datetime import timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from .models import Category, ImportBatch, MoneySource, Transaction
from .utils import ensure_default_categories, preferred_language_for_user

SAMPLE_BANK_KEY = "sample"

# (day of month, merchant, amount, flow, category kind)
RECURRING = [
    (25, "UAB Darbdavys atlyginimas", "1850.00", "in", "salary"),
    (3, "Gym+ Lietuva", "34.00", "out", "health"),
    (5, "Spotify", "7.99", "out", "subscriptions"),
    (10, "Telia Lietuva", "17.99", "out", "utilities"),
    (12, "Ignitis", "58.40", "out", "utilities"),
]
# (merchant, (min, max), category kind, times per month)
RANDOM = [
    ("MAXIMA LT, UAB", (6, 45), "groceries", 12),
    ("Rimi Lietuva", (9, 55), "groceries", 5),
    ("LIDL LIETUVA", (11, 50), "groceries", 4),
    ("Wolt", (12, 26), "dining", 3),
    ("Caffeine Roasters", (3.2, 6.8), "dining", 5),
    ("Bolt", (4, 13), "transport", 5),
    ("Circle K", (40, 70), "transport", 2),
    ("Senukai", (15, 120), "shopping", 1),
    ("Pigu.lt", (15, 80), "shopping", 1),
    ("Eurovaistinė", (5, 22), "health", 1),
]
CATEGORY_NAMES = {  # LT and EN default category names per kind
    "salary": ("Atlyginimas", "Salary"),
    "health": ("Sportas ir sveikata", "Fitness & Health"),
    "subscriptions": ("Prenumeratos", "Subscriptions"),
    "utilities": ("Komunaliniai", "Utilities"),
    "groceries": ("Maisto prekės", "Groceries"),
    "dining": ("Kavinės ir restoranai", "Dining"),
    "transport": ("Transportas", "Transportation"),
    "shopping": ("Pirkiniai", "Shopping"),
}


def sample_source_ids(user):
    return set(
        MoneySource.objects.filter(user=user, import_batches__bank_key=SAMPLE_BANK_KEY).values_list("id", flat=True)
    )


def has_sample_data(user):
    return ImportBatch.objects.filter(user=user, bank_key=SAMPLE_BANK_KEY).exists()


def real_transactions(qs):
    """Filter a Transaction queryset down to real (non-sample) rows."""
    return qs.exclude(import_batch__bank_key=SAMPLE_BANK_KEY)


@db_transaction.atomic
def add_sample_data(user):
    if has_sample_data(user):
        return 0
    ensure_default_categories(user)
    lt = preferred_language_for_user(user) != "en"
    categories = {c.name: c for c in Category.objects.filter(user=user)}

    def category(kind):
        lt_name, en_name = CATEGORY_NAMES[kind]
        return categories.get(lt_name) or categories.get(en_name)

    source = MoneySource.objects.create(
        user=user, name="Pavyzdinė sąskaita" if lt else "Sample account", type="bank",
        manual_balance=Decimal("2148.35"), current_balance=Decimal("2148.35"),
    )
    batch = ImportBatch.objects.create(user=user, money_source=source, filename="sample", bank_key=SAMPLE_BANK_KEY)

    rng = random.Random(user.pk)
    today = timezone.localdate()
    month = (today.replace(day=1) - timedelta(days=62)).replace(day=1)
    rows = []

    def add(day, merchant, amount, flow, kind):
        amount = Decimal(str(amount)).quantize(Decimal("0.01"))
        cat = category(kind)
        rows.append(Transaction(
            user=user, money_source=source, import_batch=batch, date=day, merchant=merchant, amount=amount,
            in_out=flow, currency="EUR", category_fk=cat, category=cat.name if cat else None,
            category_source="ai" if cat else "unknown",
            fingerprint=hashlib.sha256(f"sample|{user.pk}|{len(rows)}".encode()).hexdigest(),
        ))

    while month <= today:
        for day, merchant, amount, flow, kind in RECURRING:
            d = month.replace(day=day)
            if d <= today:
                add(d, merchant, amount, flow, kind)
        for merchant, (low, high), kind, per_month in RANDOM:
            for _ in range(per_month):
                d = month + timedelta(days=rng.randint(0, 27))
                if d <= today:
                    add(d, merchant, round(rng.uniform(low, high), 2), "out", kind)
        month = (month + timedelta(days=32)).replace(day=1)

    Transaction.objects.bulk_create(rows)
    # Balance is "as of now", after the sample rows, so the overview shows it exactly.
    MoneySource.objects.filter(pk=source.pk).update(balance_updated_at=timezone.now() + timedelta(seconds=5))
    batch.added_count = len(rows)
    batch.save(update_fields=["added_count"])
    return len(rows)


@db_transaction.atomic
def remove_sample_data(user):
    source_ids = sample_source_ids(user)
    Transaction.objects.filter(user=user, import_batch__bank_key=SAMPLE_BANK_KEY).delete()
    ImportBatch.objects.filter(user=user, bank_key=SAMPLE_BANK_KEY).delete()
    MoneySource.objects.filter(user=user, id__in=source_ids).delete()
    return bool(source_ids)
