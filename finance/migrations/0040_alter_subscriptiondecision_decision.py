from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0039_hash_transaction_fingerprints"),
    ]

    operations = [
        migrations.AlterField(
            model_name="subscriptiondecision",
            name="decision",
            field=models.CharField(
                choices=[
                    ("track", "Track"),
                    ("ignore", "Ignore"),
                    ("untrack", "Untrack"),
                    ("ended", "Ended"),
                ],
                max_length=16,
            ),
        ),
    ]
