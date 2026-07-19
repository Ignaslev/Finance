from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(name="Article", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("language", models.CharField(choices=[("lt", "Lithuanian"), ("en", "English")], default="lt", max_length=5)), ("title", models.CharField(max_length=160)), ("slug", models.SlugField(max_length=180, unique=True)), ("meta_title", models.CharField(blank=True, max_length=60)), ("meta_description", models.CharField(max_length=160)), ("excerpt", models.CharField(max_length=320)), ("body", models.TextField()), ("author_name", models.CharField(default="MoneyCompass komanda", max_length=120)), ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published")], default="draft", max_length=12)), ("published_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True))], options={"ordering": ("-published_at", "-created_at")})]
