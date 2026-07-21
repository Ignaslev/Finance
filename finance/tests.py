from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from finance.models import OnboardingState, UserProfile
from finance.views.settings import profile_delete_account


User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountDeletionFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="account-deletion-test",
            email="account-deletion-test@example.com",
            password="A-strong-test-password-928!",
        )
        self.client.force_login(self.user)

    def test_valid_password_schedules_deletion_without_server_error(self):
        response = self.client.post(
            reverse("profile_delete_account"),
            {"password": "A-strong-test-password-928!"},
        )

        self.assertRedirects(response, reverse("profile"))
        profile = UserProfile.objects.get(user=self.user)
        self.assertIsNotNone(profile.account_delete_requested_at)
        self.assertIsNotNone(profile.account_delete_scheduled_for)

    def test_invalid_password_shows_validation_message_without_server_error(self):
        response = self.client.post(
            reverse("profile_delete_account"),
            {"password": "not-the-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Neteisingas slaptažodis.")
        profile = UserProfile.objects.get(user=self.user)
        self.assertIsNone(profile.account_delete_requested_at)
        self.assertIsNone(profile.account_delete_scheduled_for)

    def test_cancelling_scheduled_deletion_without_server_error(self):
        profile = UserProfile.objects.create(user=self.user)
        profile.account_delete_requested_at = profile.account_delete_scheduled_for = self.user.date_joined
        profile.save(update_fields=["account_delete_requested_at", "account_delete_scheduled_for"])

        response = self.client.post(reverse("profile_cancel_delete_account"))

        self.assertRedirects(response, reverse("profile"))
        profile.refresh_from_db()
        self.assertIsNone(profile.account_delete_scheduled_for)
        self.assertIsNotNone(profile.account_delete_canceled_at)

    def test_onboarding_confirmation_does_not_mask_translation_helper(self):
        response = self.client.post(reverse("onboarding_mark_done"), {"step": "ready"})

        self.assertRedirects(response, reverse("overview"))
        self.assertTrue(OnboardingState.objects.get(user=self.user).ready_dismissed)

    def test_deletion_password_is_marked_sensitive_for_error_reports(self):
        request = RequestFactory().post(
            reverse("profile_delete_account"),
            {"password": "not-the-password"},
        )
        request.user = self.user

        with patch("finance.views.settings.messages.error"), patch(
            "finance.views.settings.render", return_value=HttpResponse()
        ):
            profile_delete_account(request)

        self.assertEqual(request.sensitive_post_parameters, ("password",))
