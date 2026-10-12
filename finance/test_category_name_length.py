import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext

from finance.models import Category, Transaction
from finance.views.ai import _normalize_merchant


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    SECURE_SSL_REDIRECT=False,
    FREE_ACCESS_MODE=True,
    BILLING_ENABLED=False,
    LANGUAGE_CODE="en",
)
class CategoryNameLengthTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="category-length@example.test",
            email="category-length@example.test",
            password="StrongPass123!",
        )
        self.client.force_login(self.user)

    def _name(self, length):
        return "Category " + "\u0105" * (length - len("Category "))

    def _transaction(self, *, user=None, merchant="Test shop", fingerprint):
        return Transaction.objects.create(
            user=user or self.user,
            date=date(2026, 10, 12),
            merchant=merchant,
            amount=Decimal("10.00"),
            currency="EUR",
            in_out=Transaction.OUT,
            fingerprint=fingerprint,
        )

    def _assert_length_error(self, response):
        self.assertEqual(response.status_code, 302)
        with translation.override(response.wsgi_request.LANGUAGE_CODE):
            expected_message = gettext("Category name can be at most %(count)s characters.") % {"count": 100}
        self.assertIn(
            expected_message,
            [str(message) for message in get_messages(response.wsgi_request)],
        )

    def test_model_and_migration_limits_match(self):
        state = MigrationLoader(None).project_state()
        for model_name, field_name in (("Category", "name"), ("Transaction", "category")):
            with self.subTest(model=model_name):
                model = {"Category": Category, "Transaction": Transaction}[model_name]
                field = model._meta.get_field(field_name)
                self.assertEqual(field.max_length, 100)
                migrated_model = state.apps.get_model("finance", model_name)
                self.assertEqual(migrated_model._meta.get_field(field_name).max_length, 100)
                field.run_validators(self._name(100))
                with self.assertRaises(ValidationError):
                    field.run_validators(self._name(101))

    def test_category_creation_accepts_boundary_lengths(self):
        for length in (33, 40, 100):
            with self.subTest(length=length):
                name = self._name(length)
                response = self.client.post(reverse("category_list"), {"name": name})
                self.assertEqual(response.status_code, 302)
                self.assertTrue(Category.objects.filter(user=self.user, name=name).exists())

    def test_profile_category_creation_accepts_boundary_lengths(self):
        for length in (33, 40, 100):
            with self.subTest(length=length):
                name = self._name(length)
                response = self.client.post(reverse("profile"), {"action": "cat_add", "name": name})
                self.assertEqual(response.status_code, 302)
                self.assertTrue(Category.objects.filter(user=self.user, name=name).exists())

    def test_category_edit_accepts_boundary_lengths(self):
        category = Category.objects.create(user=self.user, name="Original")
        for length in (33, 40, 100):
            with self.subTest(length=length):
                name = self._name(length)
                response = self.client.post(reverse("category_edit", args=[category.pk]), {"name": name})
                self.assertEqual(response.status_code, 302)
                category.refresh_from_db()
                self.assertEqual(category.name, name)

    def test_category_creation_rejects_101_characters_without_saving(self):
        name = self._name(101)
        response = self.client.post(reverse("category_list"), {"name": name})
        self._assert_length_error(response)
        self.assertFalse(Category.objects.filter(user=self.user, name=name).exists())

    def test_profile_category_creation_rejects_101_characters_without_saving(self):
        name = self._name(101)
        response = self.client.post(reverse("profile"), {"action": "cat_add", "name": name})
        self._assert_length_error(response)
        self.assertFalse(Category.objects.filter(user=self.user, name=name).exists())

    def test_category_edit_rejects_101_characters_and_preserves_original(self):
        category = Category.objects.create(user=self.user, name="Original", color="#123456")
        response = self.client.post(
            reverse("category_edit", args=[category.pk]),
            {"name": self._name(101), "color": "#654321"},
        )
        self._assert_length_error(response)
        category.refresh_from_db()
        self.assertEqual(category.name, "Original")
        self.assertEqual(category.color, "#123456")

    def test_category_forms_render_the_model_limit(self):
        category = Category.objects.create(user=self.user, name=self._name(100))
        for url in (reverse("category_list"), reverse("category_edit", args=[category.pk]), reverse("profile")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["category_name_max"], 100)
                self.assertRegex(response.content.decode(), r'name="name"\s+(?:value="[^"]*"\s+)?required\s+maxlength="100"')
                self.assertNotContains(response, 'maxlength="40"')
                self.assertContains(response, category.name)

    def test_bulk_category_save_preserves_long_names(self):
        for length in (33, 40, 100):
            with self.subTest(length=length):
                category = Category.objects.create(user=self.user, name=self._name(length))
                tx = self._transaction(fingerprint=f"bulk-long-{length}")
                response = self.client.post(
                    reverse("tx_bulk_category_apply"),
                    {"changes_json": json.dumps({str(tx.pk): str(category.pk)}), "next": "/app/"},
                )
                self.assertEqual(response.status_code, 302)
                tx.refresh_from_db()
                self.assertEqual(tx.category, category.name)
                self.assertEqual(tx.category_fk_id, category.pk)
                self.assertEqual(tx.category_source, "user")

    def test_teach_ai_preserves_long_names_for_all_matching_transactions(self):
        for length in (33, 40, 100):
            with self.subTest(length=length):
                category = Category.objects.create(user=self.user, name=self._name(length))
                merchant = f"Test shop {length}"
                transactions = [
                    self._transaction(merchant=merchant, fingerprint=f"teach-long-{length}-{i}")
                    for i in range(2)
                ]
                response = self.client.post(
                    reverse("teach_ai"),
                    {f"mk__out|{_normalize_merchant(merchant)}": str(category.pk)},
                )
                self.assertEqual(response.status_code, 302)
                for tx in transactions:
                    tx.refresh_from_db()
                    self.assertEqual(tx.category, category.name)
                    self.assertEqual(tx.category_fk_id, category.pk)
                    self.assertEqual(tx.category_source, "user")

    def test_long_category_assignment_remains_scoped_to_its_owner(self):
        other_user = get_user_model().objects.create_user(username="other-category-user")
        category = Category.objects.create(user=self.user, name=self._name(100))
        other_category = Category.objects.create(user=other_user, name=self._name(100))
        own_tx = self._transaction(fingerprint="own-long-category")
        other_tx = self._transaction(user=other_user, fingerprint="other-long-category")
        self.client.post(reverse("tx_bulk_category_apply"), {
            "changes_json": json.dumps({str(own_tx.pk): str(other_category.pk), str(other_tx.pk): str(category.pk)}),
        })
        self.client.post(reverse("teach_ai"), {
            f"mk__out|{_normalize_merchant(own_tx.merchant)}": str(other_category.pk),
        })
        own_tx.refresh_from_db()
        other_tx.refresh_from_db()
        self.assertIsNone(own_tx.category_fk_id)
        self.assertIsNone(other_tx.category_fk_id)
        self.client.post(reverse("teach_ai"), {
            f"mk__out|{_normalize_merchant(own_tx.merchant)}": str(category.pk),
        })
        other_tx.refresh_from_db()
        self.assertIsNone(other_tx.category_fk_id)

    def test_single_transaction_edit_preserves_long_names(self):
        tx = self._transaction(fingerprint="edit-long-category")
        for length in (33, 40, 100):
            with self.subTest(length=length):
                category = Category.objects.create(user=self.user, name=self._name(length))
                response = self.client.post(
                    reverse("tx_edit", args=[tx.pk]),
                    {"category_fk": str(category.pk)},
                )
                self.assertEqual(response.status_code, 302)
                tx.refresh_from_db()
                self.assertEqual(tx.category, category.name)
                self.assertEqual(tx.category_fk_id, category.pk)

    def test_bulk_save_can_mix_short_and_long_names_without_truncation(self):
        short_category = Category.objects.create(user=self.user, name="Short")
        long_category = Category.objects.create(user=self.user, name=self._name(100))
        short_tx = self._transaction(fingerprint="mixed-short-category")
        long_tx = self._transaction(fingerprint="mixed-long-category")
        response = self.client.post(reverse("tx_bulk_category_apply"), {
            "changes_json": json.dumps({str(short_tx.pk): str(short_category.pk), str(long_tx.pk): str(long_category.pk)}),
        })
        self.assertEqual(response.status_code, 302)
        short_tx.refresh_from_db()
        long_tx.refresh_from_db()
        self.assertEqual(short_tx.category, "Short")
        self.assertEqual(long_tx.category, long_category.name)
