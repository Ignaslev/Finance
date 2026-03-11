from django.shortcuts import render, redirect
from django.utils.translation import get_language

def landing(request):
    if request.user.is_authenticated:
        return redirect("/overview/")
    return render(request, "landing.html")

def privacy(request):
    lang = get_language() or "lt"
    tpl = "privacy_lt.html" if lang.startswith("lt") else "privacy_en.html"
    return render(request, tpl)

def terms(request):
    lang = get_language() or "lt"
    tpl = "terms_lt.html" if lang.startswith("lt") else "terms_en.html"
    return render(request, tpl)

def contact(request):
    lang = get_language() or "lt"
    tpl = "contact_lt.html" if lang.startswith("lt") else "contact_en.html"
    return render(request, tpl)