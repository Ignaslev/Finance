from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from moneycoach.middleware import CanonicalHostRedirectMiddleware


@override_settings(SITE_URL="https://moneycompass.lt")
class CanonicalHostRedirectMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.middleware = CanonicalHostRedirectMiddleware(
            lambda _request: HttpResponse("OK")
        )
        self.factory = RequestFactory()

    def test_redirects_www_to_the_canonical_origin_and_preserves_path_and_query(self):
        response = self.middleware(
            self.factory.get("/en/privacy/?source=campaign", HTTP_HOST="www.moneycompass.lt")
        )

        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://moneycompass.lt/en/privacy/?source=campaign",
        )

    def test_leaves_the_canonical_host_unchanged(self):
        response = self.middleware(
            self.factory.get("/", HTTP_HOST="moneycompass.lt")
        )

        self.assertEqual(response.status_code, 200)
