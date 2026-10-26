from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from finance.models import MoneySource, Transaction
from finance.utils import build_fingerprint_v2

# Swedbank exports have no time column: two coffees on the same day are byte-identical rows.
SWEDBANK_CSV = (
    '"Sąskaitos Nr.","","Data","Gavėjas","Paaiškinimai","Suma","Valiuta","D/K"\n'
    '"LT001","20","2026-10-01","","PIRKINYS 4769******1234 2026.10.01 CAFFEINE ROASTERS","4.20","EUR","D"\n'
    '"LT001","20","2026-10-01","","PIRKINYS 4769******1234 2026.10.01 CAFFEINE ROASTERS","4.20","EUR","D"\n'
    '"LT001","20","2026-10-02","","PIRKINYS 4769******1234 2026.10.02 MAXIMA X","12.00","EUR","D"\n'
)


@override_settings(ALLOWED_HOSTS=["testserver"])
class IdenticalRowsImportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dup@example.test", email="dup@example.test", password="StrongPass123!",
        )
        self.account = MoneySource.objects.create(user=self.user, name="Swedbank", type="bank")
        self.client.force_login(self.user)

    def _upload(self):
        csv_file = SimpleUploadedFile("swedbank.csv", SWEDBANK_CSV.encode("utf-8"), content_type="text/csv")
        self.client.post(reverse("upload"), {"file": csv_file, "bank": "auto", "import_src": self.account.pk})

    def _coffees(self):
        return Transaction.objects.filter(user=self.user, amount=Decimal("4.20"), date=date(2026, 10, 1)).count()

    def test_both_identical_purchases_are_kept(self):
        self._upload()

        self.assertEqual(self._coffees(), 2)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 3)

    def test_reimporting_the_same_file_adds_nothing(self):
        self._upload()
        self._upload()

        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 3)

    def test_reimport_restores_a_purchase_an_older_import_dropped(self):
        # Before the fix only the first coffee was stored, under the plain fingerprint.
        description = "PIRKINYS 4769******1234 2026.10.01 CAFFEINE ROASTERS"
        Transaction.objects.create(
            user=self.user, money_source=self.account, date=date(2026, 10, 1), merchant=description,
            amount=Decimal("4.20"), in_out="out", currency="EUR", notes=description,
            fingerprint=build_fingerprint_v2(
                date_iso="2026-10-01", time_str="", merchant=description, amount=Decimal("4.20"), currency="EUR",
                in_out="out", money_source_id=self.account.id, description=description,
            ),
        )

        self._upload()

        self.assertEqual(self._coffees(), 2)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 3)
