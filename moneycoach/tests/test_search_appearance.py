from django.test import SimpleTestCase

from moneycoach.seo import (
    SOCIAL_PROFILES,
    beta_landing_seo_context,
    finance_apps_comparison_seo_context,
    financial_app_seo_context,
    landing_seo_context,
    public_guide_seo_context,
)


class SearchAppearanceTests(SimpleTestCase):
    def test_shared_head_keeps_bing_verification_tag(self):
        response = self.client.get("/")

        self.assertContains(
            response,
            '<meta name="msvalidate.01" content="AEFFA2C5CC4EB8A6A13FF11F067AB6C8">',
            html=True,
        )

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

    def test_financial_app_page_targets_the_commercial_query(self):
        context = financial_app_seo_context()

        self.assertEqual(
            context["seo_canonical_url"],
            "https://moneycompass.lt/finansu-valdymo-programele/",
        )
        self.assertIn("Finansų valdymo programėlė", context["seo_title"])
        self.assertEqual(len(context["seo_faqs"]), 4)
        self.assertIn('"@type":"WebSite"', context["seo_schema"])
        self.assertIn('"@type":"SoftwareApplication"', context["seo_schema"])

    def test_public_guide_has_one_stable_lithuanian_canonical(self):
        context = public_guide_seo_context()

        self.assertEqual(
            context["seo_canonical_url"],
            "https://moneycompass.lt/gidas/",
        )
        self.assertIn("MoneyCompass gidas", context["seo_title"])

    def test_finance_apps_comparison_is_transparent_and_indexable(self):
        context = finance_apps_comparison_seo_context()

        self.assertEqual(
            context["seo_canonical_url"],
            "https://moneycompass.lt/geriausios-finansu-valdymo-programeles-lietuvoje/",
        )
        self.assertIn("Finansų valdymo programėlės", context["seo_title"])
        self.assertEqual(len(context["seo_faqs"]), 4)
        self.assertIn('"@type":"ItemList"', context["seo_schema"])
        self.assertIn(
            '"itemListOrder":"https://schema.org/ItemListUnordered"',
            context["seo_schema"],
        )
