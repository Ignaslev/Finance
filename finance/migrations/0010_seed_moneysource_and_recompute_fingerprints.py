from django.db import migrations, models
from django.db.models import F
from django.db import migrations

def forwards(apps, schema_editor):
    User = apps.get_model("auth", "User")
    MoneySource = apps.get_model("finance", "MoneySource")
    Transaction = apps.get_model("finance", "Transaction")

    # 1) Create "Primary account" per user
    for u in User.objects.all():
        ms, _ = MoneySource.objects.get_or_create(
            user=u, name="Primary account",
            defaults={"type": "bank", "is_active": True}
        )
        # 2) Attach existing transactions that have no source
        Transaction.objects.filter(user=u, money_source__isnull=True).update(money_source=ms)

    # 3) Recompute fingerprint to include money_source_id, with collision handling
    from collections import defaultdict
    used = defaultdict(set)  # user_id -> set of fingerprints already used

    # iterate in stable order to make "first seen" become the canonical fp
    qs = Transaction.objects.all().order_by("user_id", "date", "id").only(
        "id", "user_id", "date", "merchant", "amount", "currency", "in_out", "money_source_id"
    )

    for t in qs.iterator():
        src_id = t.money_source_id or 0
        date_str = t.date.isoformat() if hasattr(t.date, "isoformat") else str(t.date)
        merchant = (t.merchant or "").strip()
        amount = str(t.amount)  # decimal -> string
        currency = (t.currency or "").strip().upper()
        flow = (t.in_out or "").strip()

        base_fp = f"{date_str}|{merchant}|{amount}|{currency}|{flow}|{src_id}"
        fp = base_fp

        # collision handling: if same fp already used for this user, suffix this one
        if fp in used[t.user_id]:
            fp = f"{base_fp}|dup|{t.id}"

        # record and update
        used[t.user_id].add(fp)
        Transaction.objects.filter(pk=t.id).update(fingerprint=fp)

def backwards(apps, schema_editor):
    # Revert to old scheme without source id (best-effort)
    Transaction = apps.get_model("finance", "Transaction")
    qs = Transaction.objects.all().only("id", "date", "merchant", "amount", "currency", "in_out")
    for t in qs.iterator():
        date_str = t.date.isoformat() if hasattr(t.date, "isoformat") else str(t.date)
        merchant = (t.merchant or "").strip()
        amount = str(t.amount)
        currency = (t.currency or "").strip().upper()
        flow = (t.in_out or "").strip()
        fp = f"{date_str}|{merchant}|{amount}|{currency}|{flow}"
        Transaction.objects.filter(pk=t.id).update(fingerprint=fp)

class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0009_moneysource_transaction_money_source_and_more"),  # keep whatever Django generated just before this
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
