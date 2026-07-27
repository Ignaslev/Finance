"""IndexNow verification and submission helpers."""

import json
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.http import Http404, HttpResponse


INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def key_location():
    return f"{settings.SITE_URL.rstrip('/')}/{settings.INDEXNOW_KEY}.txt"


def indexnow_key_txt(_request, key):
    """Expose the public verification key only at its exact root path."""
    if key != settings.INDEXNOW_KEY:
        raise Http404
    return HttpResponse(
        f"{settings.INDEXNOW_KEY}\n",
        content_type="text/plain; charset=utf-8",
    )


def submit_urls(urls, *, timeout=15):
    """Submit canonical same-host URLs to IndexNow and return the HTTP status."""
    site_url = settings.SITE_URL.rstrip("/")
    host = urlparse(site_url).netloc
    normalized = []
    for url in urls:
        absolute_url = url if url.startswith(("http://", "https://")) else f"{site_url}{url}"
        if urlparse(absolute_url).netloc != host:
            raise ValueError(f"IndexNow URL must use the canonical host: {absolute_url}")
        if absolute_url not in normalized:
            normalized.append(absolute_url)

    if not normalized:
        raise ValueError("At least one URL is required for IndexNow submission.")

    payload = json.dumps(
        {
            "host": host,
            "key": settings.INDEXNOW_KEY,
            "keyLocation": key_location(),
            "urlList": normalized,
        }
    ).encode("utf-8")
    request = Request(
        INDEXNOW_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return response.status, normalized
