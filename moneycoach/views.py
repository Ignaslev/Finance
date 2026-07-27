from django.conf import settings
from django.shortcuts import redirect, render
from django.utils import translation

from finance.guide_content import GUIDE_CONTENT

from .seo import (
    beta_landing_seo_context,
    finance_apps_comparison_seo_context,
    financial_app_seo_context,
    landing_seo_context,
    public_guide_seo_context,
    public_page_seo_context,
)


def landing(request, language="lt"):
    if request.user.is_authenticated:
        return redirect("/overview/")

    landing_language = language or request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME) or "lt"
    if landing_language not in {"lt", "en"}:
        landing_language = "lt"

    context = {"landing_language": landing_language, **landing_seo_context(landing_language)}
    response = render(request, "landing.html", context)
    response["Content-Language"] = landing_language
    return response


def beta_landing(request):
    if request.user.is_authenticated:
        return redirect("/overview/")

    context = {
        "landing_language": "lt",
        "register_url": "/accounts/register/?lang=lt&beta_code=Noriutestuoti",
        **beta_landing_seo_context(),
    }
    with translation.override("lt"):
        response = render(request, "beta_landing.html", context)
    response["Content-Language"] = "lt"
    return response


def financial_app(request):
    with translation.override("lt"):
        response = render(request, "financial_app.html", financial_app_seo_context())
    response["Content-Language"] = "lt"
    return response


def finance_apps_comparison(request):
    with translation.override("lt"):
        response = render(
            request,
            "finance_apps_comparison.html",
            finance_apps_comparison_seo_context(),
        )
    response["Content-Language"] = "lt"
    return response


def public_guide(request):
    context = {
        "sections": GUIDE_CONTENT["lt"],
        **public_guide_seo_context(),
    }
    with translation.override("lt"):
        response = render(request, "public_guide.html", context)
    response["Content-Language"] = "lt"
    return response


def _public_page_response(request, page, language):
    language = "en" if language == "en" else "lt"
    template = f"{page}_{language}.html"
    with translation.override(language):
        response = render(request, template, public_page_seo_context(page, language))
    response["Content-Language"] = language
    return response


def privacy(request, language="lt"):
    return _public_page_response(request, "privacy", language)


def terms(request, language="lt"):
    return _public_page_response(request, "terms", language)


def contact(request, language="lt"):
    return _public_page_response(request, "contact", language)
