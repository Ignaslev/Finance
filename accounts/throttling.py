from django.core.cache import cache


def client_ip(request):
    if request is None:
        return "unknown"
    return request.META.get("REMOTE_ADDR") or "unknown"


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
