from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("blog", "0003_expand_seo_article_cluster")]
    operations = [
        migrations.AlterField(
            model_name="article",
            name="body",
            field=models.TextField(help_text="Use ## headings, - lists and **bold** text."),
        )
    ]
