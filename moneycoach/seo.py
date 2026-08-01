"""Public SEO metadata and crawl-discovery endpoints for MoneyCompass."""

import json
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.utils.safestring import mark_safe


SOCIAL_PROFILES = [
    "https://www.instagram.com/moneycompassapp/",
    "https://www.facebook.com/moneycompassapp",
    "https://www.tiktok.com/@moneycompassapp",
]

BRAND_LOGO_PATH = "/static/img/favicon.svg"


def organization_schema():
    """The single public MoneyCompass entity shared by public pages and articles."""
    return {
        "@type": "Organization",
        "@id": f"{_site_url()}/#organization",
        "name": "MoneyCompass",
        "alternateName": "MoneyCompass Lietuva",
        "url": _site_url(),
        "description": (
            "MoneyCompass Lietuva yra lietuviška, naršyklėje veikianti asmeninių finansų "
            "valdymo programėlė išlaidoms, turtui ir finansiniams tikslams stebėti."
        ),
        "email": "support@moneycompass.lt",
        "areaServed": {"@type": "Country", "name": "Lithuania"},
        "logo": {
            "@type": "ImageObject",
            "url": _absolute_url(BRAND_LOGO_PATH),
            "width": 192,
            "height": 192,
        },
        "sameAs": SOCIAL_PROFILES,
    }


def website_schema():
    """The canonical website entity used to connect every public page."""
    return {
        "@type": "WebSite",
        "@id": f"{_site_url()}/#website",
        "url": _site_url(),
        "name": "MoneyCompass",
        "alternateName": "MoneyCompass Lietuva",
        "inLanguage": ["lt", "en"],
        "publisher": {"@id": f"{_site_url()}/#organization"},
    }


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
            organization_schema(),
            website_schema(),
            {
                "@type": "SoftwareApplication",
                "@id": f"{_site_url()}/#software",
                "name": "MoneyCompass",
                "alternateName": "MoneyCompass Lietuva",
                "applicationCategory": "FinanceApplication",
                "applicationSubCategory": "Personal finance management",
                "operatingSystem": "Web",
                "browserRequirements": "Modern web browser",
                "url": _site_url(),
                "description": description,
                "inLanguage": ["lt", "en"],
                "publisher": {"@id": f"{_site_url()}/#organization"},
                "isPartOf": {"@id": f"{_site_url()}/#website"},
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
                "isPartOf": {"@id": f"{_site_url()}/#website"},
                "about": {"@id": f"{_site_url()}/#software"},
                "publisher": {"@id": f"{_site_url()}/#organization"},
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


def financial_app_seo_context():
    path = "/finansu-valdymo-programele/"
    url = _absolute_url(path)
    title = "Finansų valdymo programėlė | MoneyCompass"
    description = (
        "Lietuviška, naršyklėje veikianti finansų valdymo programėlė išlaidoms, biudžetui, "
        "turtui ir tikslams. Importuokite CSV ar Excel išrašą – be banko prijungimo."
    )
    faqs = [
        {
            "question": "Ar MoneyCompass jungiasi prie banko sąskaitos?",
            "answer": (
                "Ne. Banko išrašą CSV arba Excel formatu eksportuojate patys ir rankiniu būdu "
                "įkeliate į MoneyCompass. Programa neprašo banko prisijungimo duomenų."
            ),
        },
        {
            "question": "Ar MoneyCompass yra mobilioji programėlė ar interneto aplikacija?",
            "answer": (
                "MoneyCompass yra naršyklėje veikianti finansų valdymo programėlė, kitaip – "
                "interneto aplikacija. Ją galima naudoti telefono ir kompiuterio naršyklėje, "
                "tačiau šiuo metu nėra atskiros iOS ar Android programėlės."
            ),
        },
        {
            "question": "Ką galima stebėti su MoneyCompass?",
            "answer": (
                "Galite stebėti pajamas, išlaidas ir jų kategorijas, sąskaitų vaizdą, turtą, "
                "investicijas ir pasirinktų finansinių tikslų progresą."
            ),
        },
        {
            "question": "Ar MoneyCompass teikia finansines konsultacijas?",
            "answer": (
                "Ne. MoneyCompass padeda sutvarkyti ir parodyti jūsų pateiktus duomenis, bet "
                "neteikia individualių investavimo ar kitų finansinių rekomendacijų."
            ),
        },
    ]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            organization_schema(),
            website_schema(),
            {
                "@type": "SoftwareApplication",
                "@id": f"{_site_url()}/#software",
                "name": "MoneyCompass",
                "alternateName": "MoneyCompass Lietuva",
                "applicationCategory": "FinanceApplication",
                "applicationSubCategory": "Personal finance management",
                "operatingSystem": "Web",
                "browserRequirements": "Modern web browser",
                "url": url,
                "description": description,
                "inLanguage": "lt",
                "publisher": {"@id": f"{_site_url()}/#organization"},
                "featureList": [
                    "Rankinis CSV ir Excel banko išrašų importas",
                    "Išlaidų kategorijos ir analizė",
                    "Asmeninio biudžeto peržiūra",
                    "Turto, investicijų ir finansinių tikslų stebėjimas",
                ],
            },
            {
                "@type": "WebPage",
                "@id": f"{url}#webpage",
                "url": url,
                "name": title,
                "description": description,
                "inLanguage": "lt",
                "isPartOf": {"@id": f"{_site_url()}/#website"},
                "about": {"@id": f"{_site_url()}/#software"},
                "publisher": {"@id": f"{_site_url()}/#organization"},
            },
            {
                "@type": "FAQPage",
                "@id": f"{url}#faq",
                "url": f"{url}#duk",
                "inLanguage": "lt",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["question"],
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": item["answer"],
                        },
                    }
                    for item in faqs
                ],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "MoneyCompass",
                        "item": _site_url(),
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "Finansų valdymo programėlė",
                        "item": url,
                    },
                ],
            },
        ],
    }
    return {
        "seo_title": title,
        "seo_description": description,
        "seo_canonical_url": url,
        "seo_alternate_lt_url": url,
        "seo_alternate_en_url": url,
        "seo_image_url": _absolute_url("/static/img/landing-dashboard-lt.png"),
        "seo_locale": "lt_LT",
        "seo_schema": _json_ld(schema),
        "seo_faqs": faqs,
    }


def public_guide_seo_context():
    path = "/gidas/"
    url = _absolute_url(path)
    title = "MoneyCompass gidas: finansų programėlės naudojimas"
    description = (
        "Išsamus lietuviškas MoneyCompass gidas: banko išrašo importas, išlaidų kategorijos, "
        "biudžetas, statistika, turtas, investicijos ir finansiniai tikslai."
    )
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            organization_schema(),
            website_schema(),
            {
                "@type": "WebPage",
                "@id": f"{url}#webpage",
                "url": url,
                "name": title,
                "description": description,
                "inLanguage": "lt",
                "isPartOf": {"@id": f"{_site_url()}/#website"},
                "about": {"@id": f"{_site_url()}/#software"},
                "publisher": {"@id": f"{_site_url()}/#organization"},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "MoneyCompass",
                        "item": _site_url(),
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "Gidas",
                        "item": url,
                    },
                ],
            },
        ],
    }
    return {
        "seo_title": title,
        "seo_description": description,
        "seo_canonical_url": url,
        "seo_alternate_lt_url": url,
        "seo_alternate_en_url": url,
        "seo_image_url": _absolute_url("/static/img/landing-dashboard-lt.png"),
        "seo_locale": "lt_LT",
        "seo_schema": _json_ld(schema),
    }

def finance_apps_comparison_seo_context():
    path = "/geriausios-finansu-valdymo-programeles-lietuvoje/"
    url = _absolute_url(path)
    title = "Finansų valdymo programėlės Lietuvoje: palyginimas"
    description = (
        "Palyginkite finansų valdymo programėles Lietuvoje pagal duomenų įvedimą, "
        "banko ryšį, kalbą, biudžetą ir tinkamiausią naudojimo būdą."
    )
    faqs = [
        {
            "question": "Kuri finansų valdymo programėlė yra geriausia?",
            "answer": (
                "Vienos geriausios programėlės visiems nėra. Pasirinkimas priklauso nuo to, "
                "ar norite automatinio banko ryšio, rankinio operacijų įvedimo, CSV ar Excel "
                "importo, lietuviškos sąsajos ir turto bei tikslų stebėjimo."
            ),
        },
        {
            "question": "Ar galima sekti išlaidas neprijungiant banko sąskaitos?",
            "answer": (
                "Taip. Galite operacijas įvesti rankiniu būdu, tvarkyti jas skaičiuoklėje "
                "arba importuoti patys atsisiųstą banko išrašą. MoneyCompass naudoja pastarąjį "
                "būdą ir neprašo banko prisijungimo duomenų."
            ),
        },
        {
            "question": "Kuo interneto programa skiriasi nuo mobiliosios programėlės?",
            "answer": (
                "Interneto programa veikia naršyklėje ir jos nereikia diegti iš programėlių "
                "parduotuvės. Mobilioji programėlė diegiama telefone ir gali turėti įrenginiui "
                "būdingų funkcijų. Prieš pasirinkdami patikrinkite, kokiuose įrenginiuose "
                "veikia jums reikalingos funkcijos."
            ),
        },
        {
            "question": "Ar finansų programėlė gali pakeisti finansų konsultantą?",
            "answer": (
                "Ne. Finansų programėlė gali padėti surinkti, suskirstyti ir parodyti jūsų "
                "duomenis, tačiau ji nepakeičia individualios profesionalo konsultacijos ir "
                "neturėtų priimti finansinių sprendimų už jus."
            ),
        },
    ]
    products = [
        ("MoneyCompass", f"{_site_url()}/#software"),
        (
            "Mano Piniginė: Išlaidų sekimas",
            "https://play.google.com/store/apps/details?id=lt.algimka.manopiniginelt",
        ),
        ("Ekonomikas.lt", "https://ekonomikas.lt/"),
        (
            "Wallet by BudgetBakers",
            "https://budgetbakers.com/en/products/wallet/features/",
        ),
        ("Spendee", "https://www.spendee.com/pricing"),
        ("Skaičiuoklė", None),
    ]
    schema = {
        "@context": "https://schema.org",
        "@graph": [
            organization_schema(),
            website_schema(),
            {
                "@type": "Article",
                "@id": f"{url}#article",
                "url": url,
                "mainEntityOfPage": {"@id": f"{url}#webpage"},
                "headline": "Finansų valdymo programėlės Lietuvoje: kaip pasirinkti?",
                "description": description,
                "datePublished": "2026-07-27",
                "dateModified": "2026-07-27",
                "inLanguage": "lt",
                "author": {"@id": f"{_site_url()}/#organization"},
                "publisher": {"@id": f"{_site_url()}/#organization"},
                "image": _absolute_url("/static/img/guide/lt/statistics-summary.png"),
                "isPartOf": {"@id": f"{_site_url()}/#website"},
            },
            {
                "@type": "WebPage",
                "@id": f"{url}#webpage",
                "url": url,
                "name": title,
                "description": description,
                "inLanguage": "lt",
                "isPartOf": {"@id": f"{_site_url()}/#website"},
                "about": {"@id": f"{url}#list"},
                "publisher": {"@id": f"{_site_url()}/#organization"},
            },
            {
                "@type": "ItemList",
                "@id": f"{url}#list",
                "name": "Asmeninių finansų valdymo priemonių palyginimas",
                "itemListOrder": "https://schema.org/ItemListUnordered",
                "numberOfItems": len(products),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": position,
                        "item": {
                            "@type": "SoftwareApplication" if name != "Skaičiuoklė" else "Thing",
                            "name": name,
                            **({"url": product_url} if product_url else {}),
                        },
                    }
                    for position, (name, product_url) in enumerate(products, start=1)
                ],
            },
            {
                "@type": "FAQPage",
                "@id": f"{url}#faq",
                "url": f"{url}#duk",
                "inLanguage": "lt",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["question"],
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": item["answer"],
                        },
                    }
                    for item in faqs
                ],
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "MoneyCompass",
                        "item": _site_url(),
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "Finansų valdymo programėlių palyginimas",
                        "item": url,
                    },
                ],
            },
        ],
    }
    return {
        "seo_title": title,
        "seo_description": description,
        "seo_canonical_url": url,
        "seo_alternate_lt_url": url,
        "seo_alternate_en_url": url,
        "seo_image_url": _absolute_url("/static/img/guide/lt/statistics-summary.png"),
        "seo_locale": "lt_LT",
        "seo_schema": _json_ld(schema),
        "seo_faqs": faqs,
        "comparison_last_reviewed": "2026-07-27",
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
        title="MoneyCompass – asmeninių finansų valdymo programėlė",
        description=(
            "Lietuviška naršyklėje veikianti finansų valdymo programėlė: importuokite CSV ar "
            "Excel banko išrašus, stebėkite išlaidas, turtą ir tikslus. Be banko prijungimo."
        ),
    )


def beta_landing_seo_context():
    return public_seo_context(
        language="lt",
        canonical_path="/beta/",
        alternate_lt_path="/beta/",
        alternate_en_path="/beta/",
        title="MoneyCompass beta | Finansų valdymo programėlė",
        description=(
            "Išbandykite naršyklėje veikiančią MoneyCompass finansų valdymo programėlę 365 dienas "
            "nemokamai. Importuokite CSV ar Excel išrašą – be banko prijungimo."
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


def public_sitemap_paths():
    """Return every stable public canonical path used by sitemap and IndexNow."""
    paths = [
        "/",
        "/en/",
        "/beta/",
        "/privacy/",
        "/en/privacy/",
        "/terms/",
        "/en/terms/",
        "/contact/",
        "/en/contact/",
        "/finansu-valdymo-programele/",
        "/geriausios-finansu-valdymo-programeles-lietuvoje/",
        "/gidas/",
        "/straipsniai/",
    ]
    try:
        from blog.models import Article
        paths.extend(article.get_absolute_url() for article in Article.objects.published().filter(language="lt"))
    except Exception:
        pass
    return list(dict.fromkeys(paths))


def sitemap_xml(_request):
    # Only stable, public canonical URLs belong here. Private app pages and
    # authenticated guide pages are intentionally excluded.
    paths = public_sitemap_paths()
    entries = "".join(f"<url><loc>{escape(_absolute_url(path))}</loc></url>" for path in paths)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'
    return HttpResponse(xml, content_type="application/xml; charset=utf-8")
