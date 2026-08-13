from django.db import migrations, models
from django.db.models import Q


LEGACY_TRANSFER_NAMES = ("Internal transfer", "Vidinis pavedimas")


def mark_legacy_internal_transfers(apps, schema_editor):
    Transaction = apps.get_model("finance", "Transaction")
    Transaction.objects.filter(
        Q(category_fk__name__in=LEGACY_TRANSFER_NAMES)
        | Q(category__in=LEGACY_TRANSFER_NAMES)
    ).update(is_internal_transfer=True)


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0042_onboardingstate_intro_acknowledged_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="is_internal_transfer",
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(
                fields=["user", "is_deleted", "is_internal_transfer", "date"],
                name="finance_tx_financial_date_idx",
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("Salary", "Salary"),
                    ("Individual activity", "Individual activity"),
                    ("Cash", "Cash"),
                    ("Dining", "Dining"),
                    ("Fitness & Health", "Fitness & Health"),
                    ("Groceries", "Groceries"),
                    ("Shopping", "Shopping"),
                    ("Crypto", "Crypto"),
                    ("Utilities", "Utilities"),
                    ("Other", "Other"),
                    ("Subscriptions", "Subscriptions"),
                    ("Transportation", "Transportation"),
                ],
                max_length=32,
                null=True,
            ),
        ),
        migrations.RunPython(mark_legacy_internal_transfers, migrations.RunPython.noop),
    ]
