from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from finance.funnel import ai_correction_rate, funnel_by_source, signup_funnel, upload_outcomes, window_start

WINDOWS = (7, 30, 90)


@login_required
def staff_funnel(request):
    # Admin only (superuser). Everyone else gets a plain 404, so the page's existence isn't revealed.
    if not request.user.is_superuser:
        raise Http404
    try:
        days = int(request.GET.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    if days not in WINDOWS:
        days = 30
    since = window_start(days)
    return render(request, "staff_funnel.html", {
        "days": days,
        "windows": WINDOWS,
        "funnel": signup_funnel(since),
        "by_source": funnel_by_source(since),
        "uploads": upload_outcomes(since),
        "ai": ai_correction_rate(since),
    })
