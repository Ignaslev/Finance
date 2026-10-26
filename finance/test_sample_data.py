from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from finance.funnel import signup_funnel
from finance.models import MoneySource, Transaction
from finance.sample_data import has_sample_data

REVOLUT_CSV = (
    "Type,Product,Started Date,Completed Date,Description,Amount,Fee,Currency,State,Balance\n"
    "CARD_PAYMENT,Current,2026-10-02 12:01:10,2026-10-03 09:12:00,Maxima,-23.45,0.00,EUR,COMPLETED,476.55\n"
)


@override_settings(ALLOWED_HOSTS=["testserver"])
class SampleDataTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="s@example.test", email="s@example.test", password="StrongPass123!")
        self.client.force_login(self.user)

    def test_first_run_offers_sample_data(self):
        self.assertContains(self.client.get(reverse("overview")), reverse("sample_data_add"))

    def test_add_shows_dashboard_with_clear_remove_button(self):
        self.client.post(reverse("sample_data_add"))

        self.assertTrue(has_sample_data(self.user))
        self.assertGreater(Transaction.objects.filter(user=self.user).count(), 50)
        self.assertTrue(Transaction.objects.filter(user=self.user, category_fk__isnull=False).exists())
        page = self.client.get(reverse("overview"))
        self.assertNotContains(page, 'id="firstrun-upload"')
        self.assertContains(page, "Dabar matai pavyzdinius duomenis")
        self.assertContains(page, reverse("sample_data_remove"))

    def test_remove_returns_to_a_clean_first_run(self):
        self.client.post(reverse("sample_data_add"))
        self.client.post(reverse("sample_data_remove"))

        self.assertFalse(has_sample_data(self.user))
        self.assertFalse(Transaction.objects.filter(user=self.user).exists())
        self.assertFalse(MoneySource.objects.filter(user=self.user, name="Pavyzdinė sąskaita").exists())
        self.assertContains(self.client.get(reverse("overview")), 'id="firstrun-upload"')

    def test_first_real_upload_replaces_the_sample(self):
        self.client.post(reverse("sample_data_add"))

        self.client.post(reverse("upload"), {
            "file": SimpleUploadedFile("revolut.csv", REVOLUT_CSV.encode(), content_type="text/csv"), "bank": "auto",
        })

        self.assertFalse(has_sample_data(self.user))
        txs = Transaction.objects.filter(user=self.user)
        self.assertEqual(txs.count(), 1)
        self.assertNotEqual(txs.get().money_source.name, "Pavyzdinė sąskaita")

    def test_sample_account_is_not_an_upload_target(self):
        self.client.post(reverse("sample_data_add"))
        self.assertNotContains(self.client.get(reverse("upload")), "Pavyzdinė sąskaita</option>")

    def test_sample_is_not_offered_when_real_data_exists(self):
        self.client.post(reverse("upload"), {
            "file": SimpleUploadedFile("revolut.csv", REVOLUT_CSV.encode(), content_type="text/csv"), "bank": "auto",
        })
        self.client.post(reverse("sample_data_add"))
        self.assertFalse(has_sample_data(self.user))

    def test_funnel_does_not_count_sample_as_data(self):
        self.client.post(reverse("sample_data_add"))
        steps = {s["key"]: s["count"] for s in signup_funnel(timezone.now() - timedelta(days=1))}
        self.assertEqual(steps["has_data"], 0)
