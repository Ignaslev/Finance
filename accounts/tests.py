from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from unittest.mock import patch

from finance.models import UserProfile


User = get_user_model()


@override_settings(
    PUBLIC_REGISTRATION_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ADMINS=[("Owner", "owner@example.test")],
)
class RegistrationAttributionTests(TestCase):
    def _registration_data(self, email):
        return {
            "first_name": "Test",
            "last_name": "User",
            "email": email,
            "preferred_language": "lt",
            "password1": "A-strong-test-password-928!",
            "password2": "A-strong-test-password-928!",
            "lang": "lt",
        }

    def test_legacy_beta_page_permanently_redirects_to_landing(self):
        response = self.client.get(reverse("beta_landing"))

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, reverse("landing"))

    def test_registration_requires_no_access_code_or_trial(self):
        response = self.client.get(reverse("register") + "?lang=en")

        self.assertNotContains(response, "Beta code")
        registration_response = self.client.post(
            reverse("register"),
            self._registration_data("public-registration@example.com"),
        )
        self.assertEqual(registration_response.status_code, 302)
        profile = UserProfile.objects.get(user__email="public-registration@example.com")
        self.assertFalse(profile.is_beta_tester)
        self.assertIsNone(profile.trial_started_at)
        self.assertIsNone(profile.trial_ends_at)

    def test_first_touch_utm_is_saved_on_successful_registration(self):
        self.client.get(
            "/",
            {
                "utm_source": "instagram",
                "utm_medium": "organic_social",
                "utm_campaign": "public_launch",
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
                "password1": "A-strong-test-password-928!",
                "password2": "A-strong-test-password-928!",
                "lang": "lt",
            },
        )

        self.assertEqual(response.status_code, 302)
        profile = UserProfile.objects.get(user__email="attribution@example.com")
        self.assertEqual(profile.acquisition_source, "instagram")
        self.assertEqual(profile.acquisition_medium, "organic_social")
        self.assertEqual(profile.acquisition_campaign, "public_launch")
        self.assertEqual(profile.acquisition_content, "profile_bio")
        self.assertEqual(profile.acquisition_landing_page, "/")
        self.assertEqual(profile.acquisition_referrer, "https://www.instagram.com/moneycompassapp/")

    def test_registration_and_first_activation_send_owner_alerts(self):
        response = self.client.post(
            reverse("register"),
            self._registration_data("owner-alert@example.com"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(any("MoneyCompass: new registration" in message.subject for message in mail.outbox))

        user = User.objects.get(email="owner-alert@example.com")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        activation_url = reverse("accounts_activate", kwargs={"uidb64": uid, "token": token})

        activation_response = self.client.get(activation_url)

        self.assertEqual(activation_response.status_code, 302)
        self.assertEqual(len(mail.outbox), 3)
        self.assertTrue(any("MoneyCompass: account activated" in message.subject for message in mail.outbox))

        self.client.get(activation_url)
        self.assertEqual(len(mail.outbox), 3)

    def test_owner_alert_failure_does_not_break_registration(self):
        with patch("finance.owner_notifications.mail_admins", side_effect=RuntimeError("smtp unavailable")):
            response = self.client.post(
                reverse("register"),
                self._registration_data("owner-alert-failure@example.com"),
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email="owner-alert-failure@example.com").exists())

    def test_registration_events_wait_for_the_required_consent(self):
        response = self.client.post(
            reverse("register"),
            {
                "first_name": "Consent",
                "last_name": "Pending",
                "email": "consent-pending@example.com",
                "preferred_language": "lt",
                "password1": "A-strong-test-password-928!",
                "password2": "A-strong-test-password-928!",
                "lang": "lt",
            },
        )

        self.assertEqual(response.status_code, 302)
        pending_response = self.client.get(response.url)
        self.assertContains(pending_response, "moneyCompassHasPendingConsentEvent")
        self.assertNotContains(pending_response, 'window.fbq("track", "CompleteRegistration"')
        self.assertEqual(self.client.session["google_analytics_pending_event"], "sign_up")
        self.assertEqual(
            self.client.session["meta_analytics_pending_event"],
            "CompleteRegistration",
        )

    @override_settings(META_PIXEL_ID="123456789")
    def test_marketing_consent_emits_and_clears_registration_events(self):
        self.client.cookies["moneycompass_analytics_consent"] = "marketing"
        response = self.client.post(
            reverse("register"),
            {
                "first_name": "Consent",
                "last_name": "Granted",
                "email": "consent-granted@example.com",
                "preferred_language": "lt",
                "password1": "A-strong-test-password-928!",
                "password2": "A-strong-test-password-928!",
                "lang": "lt",
            },
        )

        self.assertEqual(response.status_code, 302)
        event_response = self.client.get(response.url)
        self.assertContains(event_response, 'window.gtag("event", "sign_up"')
        self.assertContains(event_response, 'window.fbq("track", "CompleteRegistration"')
        self.assertNotIn("google_analytics_pending_event", self.client.session)
        self.assertNotIn("meta_analytics_pending_event", self.client.session)

    @override_settings(META_PIXEL_ID="123456789")
    def test_meta_pixel_is_present_but_loaded_only_after_marketing_consent(self):
        response = self.client.get(reverse("landing"))

        self.assertContains(response, "connect.facebook.net/en_US/fbevents.js")
        self.assertContains(response, "moneyCompassLoadMetaPixel")
        self.assertContains(response, "moneycompass_analytics_consent=marketing")
        self.assertNotContains(response, "<noscript>")
