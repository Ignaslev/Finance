from django.test import SimpleTestCase

from moneycoach.seo import landing_seo_context


class SearchAppearanceTests(SimpleTestCase):
    def test_lithuanian_landing_page_has_a_descriptive_search_title(self):
        context = landing_seo_context("lt")

        self.assertEqual(
            context["seo_title"],
            "MoneyCompass – asmeninių finansų valdymo programa",
        )
        self.assertIn("banko išrašus", context["seo_description"])
        self.assertIn("Be banko prijungimo", context["seo_description"])
