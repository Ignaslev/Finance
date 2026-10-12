from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0043_transaction_internal_transfer"),
    ]

    operations = [
        migrations.AlterField(
            model_name="category",
            name="name",
            field=models.CharField(max_length=100),
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
                max_length=100,
                null=True,
            ),
        ),
    ]
