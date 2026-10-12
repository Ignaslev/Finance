from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_create_throttle_cache_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="last_active_at",
            field=models.DateTimeField(blank=True, db_index=True, editable=False, null=True),
        ),
    ]
