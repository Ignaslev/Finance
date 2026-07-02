from django.core.cache import cache
from django.conf import settings
import ipaddress


def _ip_matches(value, trusted):
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False

    for item in trusted:
        try:
            if "/" in item:
                if ip in ipaddress.ip_network(item, strict=False):
                    return True
            elif ip == ipaddress.ip_address(item):
                return True
        except ValueError:
            continue
    return False


def client_ip(request):
    if request is None:
        return "unknown"

    remote_addr = (request.META.get("REMOTE_ADDR") or "").strip()
    trusted_proxies = getattr(settings, "TRUSTED_PROXY_IPS", [])
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")

    if remote_addr and forwarded_for and _ip_matches(remote_addr, trusted_proxies):
        for part in forwarded_for.split(","):
            candidate = part.strip()
            if candidate and _ip_matches(candidate, [candidate]):
                return candidate

    return remote_addr or "unknown"


def throttle_key(scope, identifier):
    value = str(identifier or "unknown").strip().lower()
    return f"throttle:{scope}:{value}"


def is_limited(scope, identifier, *, limit, window_seconds):
    key = throttle_key(scope, identifier)
    return int(cache.get(key, 0) or 0) >= limit


def record_attempt(scope, identifier, *, window_seconds):
    key = throttle_key(scope, identifier)
    cache.add(key, 0, timeout=window_seconds)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        return 1


def clear_attempts(scope, identifier):
    cache.delete(throttle_key(scope, identifier))
