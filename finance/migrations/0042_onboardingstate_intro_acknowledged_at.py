from django.db import migrations, models
from django.utils import timezone


def acknowledge_intro_for_existing_states(apps, schema_editor):
    OnboardingState = apps.get_model("finance", "OnboardingState")
    OnboardingState.objects.filter(intro_acknowledged_at__isnull=True).update(
        intro_acknowledged_at=timezone.now()
    )


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0041_userprofile_stripe_owner_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="onboardingstate",
            name="intro_acknowledged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(
            acknowledge_intro_for_existing_states,
            migrations.RunPython.noop,
        ),
    ]
