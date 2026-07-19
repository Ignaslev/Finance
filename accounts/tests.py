from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from finance.models import UserProfile


User = get_user_model()


@override_settings(
    BETA_ACCESS_CODE="Noriutestuoti",
    BETA_USER_LIMIT=100,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class RegistrationAttributionTests(TestCase):
    def test_beta_page_prefills_code_and_exposes_seo_copy(self):
        response = self.client.get(reverse("beta_landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pagaliau aišku, kur dingsta tavo pinigai")
        self.assertContains(response, "beta_code=Noriutestuoti")
        self.assertContains(response, "Tik analitika")
        self.assertContains(response, 'rel="canonical" href="https://moneycompass.lt/beta/"')

    def test_first_touch_utm_is_saved_on_successful_registration(self):
        self.client.get(
            "/beta/",
            {
                "utm_source": "instagram",
                "utm_medium": "organic_social",
                "utm_campaign": "beta_launch",
                "utm_content": "profile_bio",
            },
            HTTP_REFERER="https://www.instagram.com/moneycompassapp/",
        )

        response = self.client.post(
            reverse("register"),
            {
                "first_name": "Test",
                "last_name": "User",
                "email": "attribution@example.com",
                "preferred_language": "lt",
                "beta_access_code": "Noriutestuoti",
                "password1": "A-strong-test-password-928!",
                "password2": "A-strong-test-password-928!",
                "lang": "lt",
            },
        )

        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user__email="attribution@example.com")
        self.assertEqual(profile.acquisition_source, "instagram")
        self.assertEqual(profile.acquisition_medium, "organic_social")
        self.assertEqual(profile.acquisition_campaign, "beta_launch")
        self.assertEqual(profile.acquisition_content, "profile_bio")
        self.assertEqual(profile.acquisition_landing_page, "/beta/")
        self.assertEqual(profile.acquisition_referrer, "https://www.instagram.com/moneycompassapp/")

    @override_settings(META_PIXEL_ID="123456789")
    def test_meta_pixel_is_present_but_loaded_only_after_marketing_consent(self):
        response = self.client.get(reverse("beta_landing"))

        self.assertContains(response, "connect.facebook.net/en_US/fbevents.js")
        self.assertContains(response, "moneyCompassLoadMetaPixel")
        self.assertContains(response, "moneycompass_analytics_consent=marketing")
        self.assertNotContains(response, "<noscript>")
