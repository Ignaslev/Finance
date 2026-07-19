from django.conf import settings
from django.shortcuts import redirect, render
from django.utils import translation

from .seo import landing_seo_context, public_page_seo_context


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
