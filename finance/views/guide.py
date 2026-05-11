from django.shortcuts import render
from django.utils.translation import get_language

from finance.guide_content import GUIDE_CONTENT


def guide(request):
    lang = (get_language() or "lt").split("-")[0]
    if lang not in GUIDE_CONTENT:
        lang = "lt"

    sections = GUIDE_CONTENT[lang]
    active_id = request.GET.get("section") or sections[0]["id"]

    active_section = next(
        (section for section in sections if section["id"] == active_id),
        sections[0],
    )

    return render(
        request,
        "guide.html",
        {
            "sections": sections,
            "active_section": active_section,
        },
    )