from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance.models import OnboardingState


@override_settings(ALLOWED_HOSTS=["testserver"])
class OnboardingIntroTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="onboarding-intro@example.test",
            email="onboarding-intro@example.test",
            password="StrongPass123!",
        )
        self.client.force_login(self.user)

    def test_new_user_sees_intro_and_first_banner_step(self):
        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="onboarding-intro-backdrop"')
        self.assertContains(response, 'class="onboarding-progress"')
        self.assertEqual(response.context["onboarding"]["step_number"], 1)
        self.assertEqual(response.context["onboarding"]["step_total"], 4)
        self.assertTrue(response.context["show_onboarding_intro"])
        self.assertIsNone(
            OnboardingState.objects.get(user=self.user).intro_acknowledged_at
        )

    def test_acknowledgement_hides_intro_without_completing_a_task(self):
        self.client.get(reverse("overview"))

        response = self.client.post(
            reverse("onboarding_intro_acknowledge"),
            {"next": reverse("overview")},
        )

        self.assertRedirects(response, reverse("overview"))
        state = OnboardingState.objects.get(user=self.user)
        self.assertIsNotNone(state.intro_acknowledged_at)
        self.assertFalse(state.categories_done)
        self.assertFalse(state.upload_done)
        self.assertFalse(state.balance_done)
        self.assertFalse(state.teach_ai_done)
        self.assertFalse(state.ready_dismissed)

        response = self.client.get(reverse("overview"))
        self.assertNotContains(response, 'class="onboarding-intro-backdrop"')
        self.assertFalse(response.context["show_onboarding_intro"])

    def test_intro_acknowledgement_requires_post(self):
        response = self.client.get(reverse("onboarding_intro_acknowledge"))

        self.assertEqual(response.status_code, 405)

    def test_existing_acknowledged_user_does_not_see_intro(self):
        OnboardingState.objects.create(
            user=self.user,
            intro_acknowledged_at=timezone.now(),
        )

        response = self.client.get(reverse("overview"))

        self.assertNotContains(response, 'class="onboarding-intro-backdrop"')
        self.assertFalse(response.context["show_onboarding_intro"])
