from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponsePermanentRedirect


class CanonicalHostRedirectMiddleware:
    """Send www requests to the single public MoneyCompass origin."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.canonical_url = settings.SITE_URL
        self.canonical_host = (urlsplit(self.canonical_url).hostname or "").lower()

    def __call__(self, request):
        request_host = request.get_host().split(":", 1)[0].lower()
        if (
            self.canonical_host
            and request_host == f"www.{self.canonical_host}"
        ):
            return HttpResponsePermanentRedirect(
                f"{self.canonical_url}{request.get_full_path()}"
            )

        return self.get_response(request)
