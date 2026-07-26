from django.conf import settings


def analytics(_request):
    consent = _request.COOKIES.get("moneycompass_analytics_consent", "")
    google_pending = _request.session.get("google_analytics_pending_event")
    meta_pending = _request.session.get("meta_analytics_pending_event")

    google_event = None
    if google_pending == "sign_up" and consent in {"accepted", "analytics", "marketing"}:
        google_event = _request.session.pop("google_analytics_pending_event")

    meta_event = None
    if meta_pending == "CompleteRegistration" and consent == "marketing":
        meta_event = _request.session.pop("meta_analytics_pending_event")

    return {
        "google_analytics_measurement_id": settings.GOOGLE_ANALYTICS_MEASUREMENT_ID,
        "meta_pixel_id": settings.META_PIXEL_ID,
        "google_analytics_pending_event": google_event,
        "meta_analytics_pending_event": meta_event,
        "analytics_event_waiting": bool(
            google_pending == "sign_up" or meta_pending == "CompleteRegistration"
        ),
    }
