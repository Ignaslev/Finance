from django.utils import translation


class UserPreferredLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, "user", None) and request.user.is_authenticated:
            try:
                lang = (request.user.profile.preferred_language or "lt").lower()
            except Exception:
                lang = "lt"

            if lang not in {"lt", "en"}:
                lang = "lt"

            translation.activate(lang)
            request.LANGUAGE_CODE = lang

        response = self.get_response(request)
        return response