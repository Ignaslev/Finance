"""Verify MoneyCompass public SEO pages after migrations."""

import json
import os
import sys
from html.parser import HTMLParser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moneycoach.settings")

import django

django.setup()

from blog.models import Article
from django.test import Client


EXPECTED_ARTICLES = {
    "asmeninis-biudzetas",
    "asmeniniu-finansu-valdymas",
    "banko-israso-analize",
    "biudzeto-planavimo-metodai",
    "islaidu-sekimas",
    "menesio-finansu-perziura",
}

EXPECTED_SITEMAP_PATHS = {
    "/finansu-valdymo-programele/",
    "/geriausios-finansu-valdymo-programeles-lietuvoje/",
    "/gidas/",
    "/straipsniai/banko-israso-analize/",
    "/straipsniai/biudzeto-planavimo-metodai/",
    "/straipsniai/menesio-finansu-perziura/",
}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self.h1_count = 0
        self.description = ""
        self.canonical = ""
        self.json_ld = []
        self._in_json_ld = False
        self._json_ld_parts = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.h1_count += 1
        elif tag == "meta" and values.get("name") == "description":
            self.description = values.get("content", "")
        elif tag == "link" and "canonical" in values.get("rel", "").split():
            self.canonical = values.get("href", "")
        elif tag == "script" and values.get("type") == "application/ld+json":
            self._in_json_ld = True
            self._json_ld_parts = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_json_ld:
            payload = "".join(self._json_ld_parts).strip()
            if payload:
                self.json_ld.append(json.loads(payload))
            self._in_json_ld = False
            self._json_ld_parts = []

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_json_ld:
            self._json_ld_parts.append(data)


def fail(message):
    print(f"FAIL: {message}")
    return False


def main():
    ok = True
    client = Client(HTTP_HOST="moneycompass.lt")
    article_slugs = set(
        Article.objects.published().filter(language="lt").values_list("slug", flat=True)
    )

    missing_articles = EXPECTED_ARTICLES - article_slugs
    if missing_articles:
        ok = fail(f"missing published articles: {sorted(missing_articles)}")

    urls = [
        "/finansu-valdymo-programele/",
        "/geriausios-finansu-valdymo-programeles-lietuvoje/",
        "/gidas/",
        "/straipsniai/",
        *[f"/straipsniai/{slug}/" for slug in sorted(EXPECTED_ARTICLES)],
    ]

    for url in urls:
        response = client.get(url)
        if response.status_code != 200:
            ok = fail(f"{url} returned HTTP {response.status_code}")
            continue

        parser = PageParser()
        parser.feed(response.content.decode("utf-8"))

        if not parser.title.strip():
            ok = fail(f"{url} has no title")
        if len(parser.title.strip()) > 65:
            ok = fail(f"{url} title is too long ({len(parser.title.strip())})")
        if not parser.description:
            ok = fail(f"{url} has no meta description")
        if len(parser.description) > 165:
            ok = fail(f"{url} meta description is too long ({len(parser.description)})")
        if parser.h1_count != 1:
            ok = fail(f"{url} has {parser.h1_count} H1 elements")
        if not parser.canonical.startswith("https://moneycompass.lt/"):
            ok = fail(f"{url} has invalid canonical {parser.canonical!r}")
        if not parser.json_ld:
            ok = fail(f"{url} has no valid JSON-LD")

        print(
            "OK:",
            url,
            f"title={len(parser.title.strip())}",
            f"description={len(parser.description)}",
            f"h1={parser.h1_count}",
            f"jsonld={len(parser.json_ld)}",
        )

    sitemap = client.get("/sitemap.xml")
    sitemap_text = sitemap.content.decode("utf-8")
    if sitemap.status_code != 200:
        ok = fail(f"sitemap returned HTTP {sitemap.status_code}")
    for path in EXPECTED_SITEMAP_PATHS:
        if f"https://moneycompass.lt{path}" not in sitemap_text:
            ok = fail(f"sitemap is missing {path}")

    if ok:
        print(
            f"SEO verification passed: {len(urls)} pages, "
            f"{len(article_slugs)} published Lithuanian articles."
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
