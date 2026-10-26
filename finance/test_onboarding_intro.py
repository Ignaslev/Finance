from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance.models import OnboardingState, Transaction

REVOLUT_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-10-02 12:01:10,2026-10-03 09:12:00,Maxima,-23.45,0.00,EUR,COMPLETED,476.55\n"
    "TOPUP,Current,2026-10-06 10:00:00,2026-10-06 10:00:01,Top-Up,300.00,0.00,EUR,COMPLETED,776.55\n"
)


@override_settings(ALLOWED_HOSTS=["testserver"])
class OnboardingIntroTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="onboarding-intro@example.test",
            email="onboarding-intro@example.test",
            password="StrongPass123!",
        )
        self.client.force_login(self.user)

    def test_new_user_sees_upload_first_without_setup_popup(self):
        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="onboarding-intro-backdrop"')
        self.assertContains(response, 'id="firstrun-upload"')
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertEqual(response.context["onboarding"]["code"], "upload")
        self.assertEqual(response.context["onboarding"]["step_number"], 1)
        self.assertEqual(response.context["onboarding"]["step_total"], 2)
        # The first-run screen is the step, so the setup banner is hidden on the overview...
        self.assertNotContains(response, 'class="onboarding-banner"')
        self.assertNotContains(response, 'id="netWorthChart"')
        # ...but other pages still point the user back to it.
        other = self.client.get(reverse("statistics"))
        self.assertContains(other, 'class="onboarding-banner"')

    def test_intro_acknowledgement_still_works_without_completing_a_task(self):
        response = self.client.post(
            reverse("onboarding_intro_acknowledge"),
            {"next": reverse("overview")},
        )

        self.assertRedirects(response, reverse("overview"))
        state = OnboardingState.objects.get(user=self.user)
        self.assertIsNotNone(state.intro_acknowledged_at)
        self.assertFalse(state.upload_done)
        self.assertFalse(state.ready_dismissed)

    def test_intro_acknowledgement_requires_post(self):
        response = self.client.get(reverse("onboarding_intro_acknowledge"))

        self.assertEqual(response.status_code, 405)

    def test_first_upload_returns_to_overview_and_unlocks_auto_categorization(self):
        upload = SimpleUploadedFile("revolut.csv", REVOLUT_CSV.encode("utf-8"), content_type="text/csv")

        response = self.client.post(
            reverse("upload"),
            {"file": upload, "bank": "auto", "next": reverse("overview")},
        )

        self.assertRedirects(response, reverse("overview"))
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)
        self.assertTrue(OnboardingState.objects.get(user=self.user).categories_done)

        overview = self.client.get(reverse("overview"))
        self.assertNotContains(overview, 'id="firstrun-upload"')
        self.assertEqual(overview.context["onboarding"]["code"], "balance")

    def test_unrecognised_file_returns_to_first_run_with_a_clear_message(self):
        junk = SimpleUploadedFile("luminor.csv", b"Kazkas;Kita\n1;2\n", content_type="text/csv")

        response = self.client.post(
            reverse("upload"),
            {"file": junk, "bank": "auto", "next": reverse("overview")},
            follow=True,
        )

        self.assertEqual(response.redirect_chain[-1][0], reverse("overview"))
        self.assertContains(response, 'id="firstrun-upload"')
        self.assertContains(response, "Swedbank, SEB")
        self.assertFalse(Transaction.objects.filter(user=self.user).exists())

    def test_upload_ignores_offsite_next_url(self):
        upload = SimpleUploadedFile("revolut.csv", REVOLUT_CSV.encode("utf-8"), content_type="text/csv")

        response = self.client.post(
            reverse("upload"),
            {"file": upload, "bank": "auto", "next": "https://evil.example/"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(response["Location"].startswith("https://evil.example"))

    def test_existing_user_with_transactions_gets_categories_unblocked(self):
        OnboardingState.objects.create(user=self.user, intro_acknowledged_at=timezone.now())
        Transaction.objects.create(
            user=self.user, date=date(2026, 10, 1), merchant="Rimi", amount=Decimal("12.00"),
            in_out="out", fingerprint="legacy-user-tx",
        )

        self.client.get(reverse("overview"))

        self.assertTrue(OnboardingState.objects.get(user=self.user).categories_done)
