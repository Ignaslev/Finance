from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0013_savingsgoal"),  # adjust to your latest
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="goal_fk",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="transactions",
                to="finance.savingsgoal",
            ),
        ),
    ]
