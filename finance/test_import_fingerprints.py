import string
from decimal import Decimal

from django.test import SimpleTestCase

from finance.utils import build_fingerprint_v2


class ImportFingerprintTests(SimpleTestCase):
    def _fingerprint(self, **overrides):
        values = {
            "date_iso": "2026-07-31",
            "time_str": "13:42:05",
            "merchant": r"MAXIMA/X-646 MAXIMA\LIETUVNINKU G. 58\SILUTE\\LTULTU",
            "amount": Decimal("123.45"),
            "currency": "EUR",
            "in_out": "out",
            "money_source_id": 1,
            "description": r"MAXIMA/X-646 MAXIMA\LIETUVNINKU G. 58\SILUTE\\LTULTU",
        }
        values.update(overrides)
        return build_fingerprint_v2(**values)

    def test_long_swedbank_merchant_produces_database_safe_fingerprint(self):
        fingerprint = self._fingerprint()

        self.assertEqual(len(fingerprint), 64)
        self.assertTrue(set(fingerprint) <= set(string.hexdigits.lower()))

    def test_fingerprint_is_deterministic(self):
        self.assertEqual(self._fingerprint(), self._fingerprint())

    def test_material_transaction_change_changes_fingerprint(self):
        self.assertNotEqual(
            self._fingerprint(),
            self._fingerprint(amount=Decimal("123.46")),
        )
