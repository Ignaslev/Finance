"""Public SEO metadata and crawl-discovery endpoints for MoneyCompass."""

import json
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.utils.safestring import mark_safe


SOCIAL_PROFILES = [
    "https://www.instagram.com/moneycompassapp/",
    "https://www.facebook.com/profile.php?id=61591596006519",
    "https://www.tiktok.com/@moneycompassapp",
]


def _site_url():
    return settings.SITE_URL.rstrip("/")


def _absolute_url(path):
    return f"{_site_url()}{path}"


def _json_ld(data):
    """Safely serialize a JSON-LD object for a script element."""
    return mark_safe(json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))


def public_seo_context(*, language, canonical_path, alternate_lt_path, alternate_en_path, title, description):
    """Return server-rendered metadata used by each public, indexable page."""
    canonical_url = _absolute_url(canonical_path)
    alternate_lt_url = _absolute_url(alternate_lt_path)
    alternate_en_url = _absolute_url(alternate_en_path)
    image_url = _absolute_url(f"/static/img/landing-dashboard-{language}.png")

    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{_site_url()}/#organization",
                "name": "MoneyCompass",
                "url": _site_url(),
                "email": "support@moneycompass.lt",
                "sameAs": SOCIAL_PROFILES,
            },
            {
                "@type": "SoftwareApplication",
                "@id": f"{_site_url()}/#software",
                "name": "MoneyCompass",
                "applicationCategory": "FinanceApplication",
                "operatingSystem": "Web",
                "url": _site_url(),
                "description": description,
                "publisher": {"@id": f"{_site_url()}/#organization"},
                "featureList": [
                    "Manual CSV and Excel statement import",
                    "Expense categorization and spending analysis",
                    "Personal dashboard and net-worth tracking",
                    "Portfolio and financial-goal tracking",
                ],
            },
            {
                "@type": "WebPage",
                "@id": f"{canonical_url}#webpage",
                "url": canonical_url,
                "name": title,
                "description": description,
                "inLanguage": language,
                "isPartOf": {"@id": f"{_site_url()}/#software"},
            },
        ],
    }

    return {
        "seo_title": title,
        "seo_description": description,
        "seo_canonical_url": canonical_url,
        "seo_alternate_lt_url": alternate_lt_url,
        "seo_alternate_en_url": alternate_en_url,
        "seo_image_url": image_url,
        "seo_locale": "lt_LT" if language == "lt" else "en_US",
        "seo_schema": _json_ld(schema),
    }


def landing_seo_context(language):
    if language == "en":
        return public_seo_context(
            language="en",
            canonical_path="/en/",
            alternate_lt_path="/",
            alternate_en_path="/en/",
            title="MoneyCompass | Private personal finance tracking",
            description=(
                "Track spending, net worth, investments and goals in one private personal finance app. "
                "Import CSV or Excel statements manually - no bank connection required."
            ),
        )

    return public_seo_context(
        language="lt",
        canonical_path="/",
        alternate_lt_path="/",
        alternate_en_path="/en/",
        title="MoneyCompass – asmeninių finansų valdymo programa",
        description=(
            "Privati asmeninių finansų programa: importuokite banko išrašus, stebėkite išlaidas, "
            "turtą, investicijas ir tikslus. Be banko prijungimo."
        ),
    )


def public_page_seo_context(page, language):
    pages = {
        "privacy": {
            "lt": ("/privacy/", "Privatumo politika | MoneyCompass", "MoneyCompass privatumo politika."),
            "en": ("/en/privacy/", "Privacy policy | MoneyCompass", "MoneyCompass privacy policy."),
        },
        "terms": {
            "lt": ("/terms/", "Naudojimosi salygos | MoneyCompass", "MoneyCompass naudojimosi salygos."),
            "en": ("/en/terms/", "Terms of service | MoneyCompass", "MoneyCompass terms of service."),
        },
        "contact": {
            "lt": ("/contact/", "Kontaktai | MoneyCompass", "Susisiekite su MoneyCompass komanda."),
            "en": ("/en/contact/", "Contact | MoneyCompass", "Contact the MoneyCompass team."),
        },
    }
    canonical_path, title, description = pages[page][language]
    return public_seo_context(
        language=language,
        canonical_path=canonical_path,
        alternate_lt_path=pages[page]["lt"][0],
        alternate_en_path=pages[page]["en"][0],
        title=title,
        description=description,
    )


def robots_txt(_request):
    return HttpResponse(
        "\n".join(
            [
                "User-agent: *",
                "Allow: /",
                "Disallow: /admin/",
                "Disallow: /app/",
                "Disallow: /overview/",
                "Disallow: /upload/",
                "Disallow: /statistics/",
                "Disallow: /reports/",
                "Disallow: /assets/",
                "Disallow: /profile/",
                "Disallow: /billing/",
                "Disallow: /stripe/",
                "Disallow: /api/",
                "",
                f"Sitemap: {_absolute_url('/sitemap.xml')}",
                "",
            ]
        ),
        content_type="text/plain; charset=utf-8",
    )


def sitemap_xml(_request):
    # Only stable, public canonical URLs belong here. Private app pages and
    # cookie-dependent guide pages are intentionally excluded.
    paths = [
        "/",
        "/en/",
        "/privacy/",
        "/en/privacy/",
        "/terms/",
        "/en/terms/",
        "/contact/",
        "/en/contact/",
    ]
    entries = "".join(f"<url><loc>{escape(_absolute_url(path))}</loc></url>" for path in paths)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'
    return HttpResponse(xml, content_type="application/xml; charset=utf-8")
