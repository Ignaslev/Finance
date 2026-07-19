"""Privacy-conscious first-touch attribution for public acquisition links."""

from urllib.parse import urlsplit


UTM_FIELDS = {
    "utm_source": "acquisition_source",
    "utm_medium": "acquisition_medium",
    "utm_campaign": "acquisition_campaign",
    "utm_content": "acquisition_content",
    "utm_term": "acquisition_term",
}
SESSION_KEY = "moneycompass_first_touch"


def _clean(value, max_length=255):
    return " ".join((value or "").strip().split())[:max_length]


def capture_first_touch(request):
    """Store the first tagged visit only; never overwrite the original source."""
    if request.session.get(SESSION_KEY):
        return

    values = {
        profile_field: _clean(request.GET.get(query_key), 100)
        for query_key, profile_field in UTM_FIELDS.items()
    }
    if not any(values.values()):
        return

    values["acquisition_landing_page"] = _clean(request.path, 255)
    referrer = request.META.get("HTTP_REFERER", "")
    if referrer:
        parsed = urlsplit(referrer)
        values["acquisition_referrer"] = _clean(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}", 255
        )
    request.session[SESSION_KEY] = values


class AttributionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        capture_first_touch(request)
        return self.get_response(request)
