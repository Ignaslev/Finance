from django.conf import settings


def analytics(_request):
    pending_event = _request.session.pop("google_analytics_pending_event", None)
    return {
        "google_analytics_measurement_id": settings.GOOGLE_ANALYTICS_MEASUREMENT_ID,
        "meta_pixel_id": settings.META_PIXEL_ID,
        "google_analytics_pending_event": pending_event if pending_event == "sign_up" else None,
    }
