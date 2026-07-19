from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0037_subscription_access"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="acquisition_source",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="acquisition_medium",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="acquisition_campaign",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="acquisition_content",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="acquisition_term",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="acquisition_landing_page",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="acquisition_referrer",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
