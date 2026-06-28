from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def seed_access_windows(apps, schema_editor):
    UserProfile = apps.get_model("finance", "UserProfile")
    now = timezone.now()

    for profile in UserProfile.objects.all():
        update_fields = []

        if profile.is_beta_tester:
            joined_at = profile.beta_joined_at or now
            if not profile.beta_joined_at:
                profile.beta_joined_at = joined_at
                update_fields.append("beta_joined_at")
            if not profile.beta_access_until:
                profile.beta_access_until = joined_at + timedelta(days=365)
                update_fields.append("beta_access_until")
            profile.subscription_status = "beta"
            update_fields.append("subscription_status")
        else:
            if not profile.trial_started_at:
                profile.trial_started_at = now
                update_fields.append("trial_started_at")
            if not profile.trial_ends_at:
                profile.trial_ends_at = now + timedelta(days=14)
                update_fields.append("trial_ends_at")
            if not profile.subscription_status:
                profile.subscription_status = "trial"
                update_fields.append("subscription_status")

        if update_fields:
            profile.save(update_fields=sorted(set(update_fields)))


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0036_userprofile_beta_joined_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="beta_access_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="manual_access_note",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="manual_access_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="plan_interval",
            field=models.CharField(blank=True, choices=[("monthly", "Monthly"), ("yearly", "Yearly")], default="", max_length=10),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="stripe_cancel_at_period_end",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="stripe_current_period_end",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="stripe_customer_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="stripe_last_event_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="stripe_price_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="stripe_subscription_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="subscription_status",
            field=models.CharField(choices=[("trial", "Trial"), ("beta", "Beta access"), ("active", "Active"), ("trialing", "Trialing"), ("past_due", "Past due"), ("canceled", "Canceled"), ("expired", "Expired"), ("manual", "Manual access")], db_index=True, default="trial", max_length=20),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="subscription_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="trial_ends_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="trial_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(seed_access_windows, migrations.RunPython.noop),
    ]
