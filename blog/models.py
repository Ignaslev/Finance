from django.db import models
from django.urls import reverse
from django.utils import timezone

from .markdown import render_markdown


class ArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Article.Status.PUBLISHED, published_at__lte=timezone.now())


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    language = models.CharField(max_length=5, default="lt", choices=(("lt", "Lithuanian"), ("en", "English")))
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    meta_title = models.CharField(max_length=60, blank=True)
    meta_description = models.CharField(max_length=160)
    excerpt = models.CharField(max_length=320)
    body = models.TextField(help_text="Use ## headings, - lists and **bold** text.")
    author_name = models.CharField(max_length=120, default="MoneyCompass komanda")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ("-published_at", "-created_at")

    def __str__(self): return self.title
    def get_absolute_url(self): return reverse("article_detail", kwargs={"slug": self.slug})
    @property
    def seo_title(self): return self.meta_title or self.title
    @property
    def rendered_body(self): return render_markdown(self.body)
