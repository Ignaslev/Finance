from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from moneycoach.indexnow import key_location
from moneycoach.seo import public_sitemap_paths


class IndexNowTests(SimpleTestCase):
    def test_verification_key_is_available_only_at_exact_root_path(self):
        response = self.client.get(
            reverse("indexnow_key", kwargs={"key": settings.INDEXNOW_KEY})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(response.content.decode().strip(), settings.INDEXNOW_KEY)
        self.assertEqual(
            key_location(),
            f"https://moneycompass.lt/{settings.INDEXNOW_KEY}.txt",
        )

    def test_unknown_text_key_returns_404(self):
        response = self.client.get(
            reverse("indexnow_key", kwargs={"key": "not-the-key"})
        )

        self.assertEqual(response.status_code, 404)

    def test_comparison_page_is_part_of_indexnow_and_sitemap_url_set(self):
        self.assertIn(
            "/geriausios-finansu-valdymo-programeles-lietuvoje/",
            public_sitemap_paths(),
        )
