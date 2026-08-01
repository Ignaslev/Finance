from django.db import migrations, models


def mark_existing_subscriptions_as_notified(apps, schema_editor):
    UserProfile = apps.get_model("finance", "UserProfile")
    for profile in UserProfile.objects.exclude(stripe_subscription_id="").iterator(chunk_size=500):
        profile.stripe_owner_notified_subscription_id = profile.stripe_subscription_id
        profile.save(update_fields=["stripe_owner_notified_subscription_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0040_alter_subscriptiondecision_decision"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="stripe_owner_notified_subscription_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.RunPython(mark_existing_subscriptions_as_notified, migrations.RunPython.noop),
    ]
