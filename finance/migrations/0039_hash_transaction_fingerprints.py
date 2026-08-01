import hashlib

from django.db import migrations


def hash_existing_fingerprints(apps, schema_editor):
    Transaction = apps.get_model("finance", "Transaction")

    pending_updates = []
    transactions = Transaction.objects.all().only("id", "fingerprint")
    for transaction in transactions.iterator(chunk_size=1000):
        old_fingerprint = transaction.fingerprint or ""
        transaction.fingerprint = hashlib.sha256(old_fingerprint.encode("utf-8")).hexdigest()
        pending_updates.append(transaction)

        if len(pending_updates) == 1000:
            Transaction.objects.bulk_update(pending_updates, ["fingerprint"], batch_size=1000)
            pending_updates.clear()

    if pending_updates:
        Transaction.objects.bulk_update(pending_updates, ["fingerprint"], batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0038_userprofile_acquisition"),
    ]

    operations = [
        migrations.RunPython(hash_existing_fingerprints, migrations.RunPython.noop),
    ]
