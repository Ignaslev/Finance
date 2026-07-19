from django.test import SimpleTestCase

from moneycoach.seo import SOCIAL_PROFILES, beta_landing_seo_context, landing_seo_context


class SearchAppearanceTests(SimpleTestCase):
    def test_lithuanian_landing_page_has_a_descriptive_search_title(self):
        context = landing_seo_context("lt")

        self.assertEqual(
            context["seo_title"],
            "MoneyCompass – asmeninių finansų valdymo programa",
        )
        self.assertIn("banko išrašus", context["seo_description"])
        self.assertIn("Be banko prijungimo", context["seo_description"])

    def test_beta_landing_has_indexable_search_metadata(self):
        context = beta_landing_seo_context()

        self.assertEqual(context["seo_canonical_url"], "https://moneycompass.lt/beta/")
        self.assertIn("asmeniniai finansai", context["seo_title"])
        self.assertIn("365 dienas", context["seo_description"])

    def test_facebook_structured_data_uses_the_public_username(self):
        self.assertIn("https://www.facebook.com/moneycompassapp", SOCIAL_PROFILES)
        self.assertNotIn("profile.php", " ".join(SOCIAL_PROFILES))
