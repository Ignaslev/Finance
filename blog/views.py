from django.shortcuts import get_object_or_404, render
from .models import Article
from .seo import article_index_seo_context, article_seo_context


def article_list(request):
    return render(request, "blog/article_list.html", {"articles": Article.objects.published().filter(language="lt"), **article_index_seo_context()})


def article_detail(request, slug):
    article = get_object_or_404(Article.objects.published(), slug=slug, language="lt")
    related_articles = Article.objects.published().filter(language="lt").exclude(pk=article.pk)[:3]
    return render(request, "blog/article_detail.html", {"article": article, "related_articles": related_articles, **article_seo_context(article)})
