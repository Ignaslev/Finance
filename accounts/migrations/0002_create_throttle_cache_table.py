from django.core.management import call_command
from django.db import migrations


def create_throttle_cache_table(apps, schema_editor):
    # DatabaseCache tables are not created by Django's normal model migrations.
    # Create this one during deployment before authentication receives traffic.
    call_command(
        "createcachetable",
        "moneycompass_cache",
        database=schema_editor.connection.alias,
        verbosity=0,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_throttle_cache_table, migrations.RunPython.noop),
    ]
