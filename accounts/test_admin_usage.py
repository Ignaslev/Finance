from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.admin import LastActivityFilter, SuccessfulImportsFilter, TransactionDataFilter
from accounts.models import User
from finance.models import ImportBatch, MoneySource, Transaction


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class AdminUsageTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(username="usage-admin", email="usage-admin@example.test")
        self.user = User.objects.create_user(username="usage-user", email="usage-user@example.test", first_name="Usage")
        self.empty_user = User.objects.create_user(username="empty-user", email="empty@example.test")
        self.source = MoneySource.objects.create(user=self.user, name="Private account")
        self.first_import = datetime(2026, 10, 10, 8, 0, tzinfo=datetime_timezone.utc)
        self.latest_import = datetime(2026, 10, 11, 9, 0, tzinfo=datetime_timezone.utc)
        self.now = datetime(2026, 10, 12, 8, 0, tzinfo=datetime_timezone.utc)
        self._batch(added_count=4, created_at=self.first_import)
        self._batch(added_count=1, created_at=self.latest_import, undone_at=self.now)
        self._batch(added_count=0, created_at=self.now)
        self.tx = Transaction.objects.create(
            user=self.user, money_source=self.source, date=date(2026, 10, 10),
            merchant="PRIVATE TRANSACTION CONTENT", amount=Decimal("123.45"),
            currency="EUR", in_out="out", fingerprint="admin-usage-transaction",
        )
        self.client.force_login(self.staff)
        self.model_admin = admin.site._registry[User]
        self.request = RequestFactory().get(reverse("admin:accounts_user_changelist"))
        self.request.user = self.staff

    def _batch(self, *, added_count, created_at, undone_at=None):
        batch = ImportBatch.objects.create(
            user=self.user, money_source=self.source, added_count=added_count,
            filename="PRIVATE BANK FILENAME.csv", undone_at=undone_at,
        )
        ImportBatch.objects.filter(pk=batch.pk).update(created_at=created_at)
        return batch

    def _queryset(self):
        return self.model_admin.get_queryset(self.request)

    def _filtered_ids(self, filter_class, value):
        filter_instance = filter_class(
            self.request, {filter_class.parameter_name: [value]}, User, self.model_admin,
        )
        return set(filter_instance.queryset(self.request, self._queryset()).values_list("pk", flat=True))

    def test_usage_counts_saved_successful_batches_including_undone_not_empty(self):
        user = self._queryset().get(pk=self.user.pk)
        self.assertTrue(self.model_admin.has_transaction_data(user))
        self.assertEqual(self.model_admin.successful_import_count(user), 2)
        self.assertEqual(self.model_admin.undone_import_count(user), 1)
        self.assertEqual(user._last_import_at, self.latest_import)
        self.assertEqual(self.model_admin.last_import_display(user), "2026-10-11 12:00:00")

    def test_empty_account_has_zero_imports_no_data_and_unknown_activity(self):
        user = self._queryset().get(pk=self.empty_user.pk)
        self.assertFalse(self.model_admin.has_transaction_data(user))
        self.assertEqual(self.model_admin.successful_import_count(user), 0)
        self.assertIsNone(user._last_import_at)
        self.assertIsNone(self.model_admin.last_active_display(user))

    def test_manual_transactions_are_distinguished_from_import_history(self):
        Transaction.objects.create(
            user=self.empty_user, date=date(2026, 10, 10), merchant="Manually entered",
            amount=Decimal("5.00"), currency="EUR", in_out="out", fingerprint="manual-admin-usage",
        )
        user = self._queryset().get(pk=self.empty_user.pk)
        self.assertTrue(self.model_admin.has_transaction_data(user))
        self.assertEqual(self.model_admin.successful_import_count(user), 0)

    def test_deleted_transactions_are_not_reported_as_current_data(self):
        self.tx.is_deleted = True
        self.tx.save(update_fields=["is_deleted"])
        self.assertFalse(self.model_admin.has_transaction_data(self._queryset().get(pk=self.user.pk)))

    def test_multiple_transactions_do_not_multiply_import_counts(self):
        Transaction.objects.create(
            user=self.user, date=date(2026, 10, 10), merchant="Second row",
            amount=Decimal("5.00"), currency="EUR", in_out="out", fingerprint="second-admin-usage",
        )
        self.assertEqual(self.model_admin.successful_import_count(self._queryset().get(pk=self.user.pk)), 2)

    def test_usage_values_are_fetched_without_per_user_queries(self):
        with self.assertNumQueries(1):
            users = list(self._queryset())
            for user in users:
                self.model_admin.has_transaction_data(user)
                self.model_admin.successful_import_count(user)
                self.model_admin.undone_import_count(user)
                self.model_admin.last_import_display(user)

    def test_activity_filters_separate_unknown_from_known_inactivity(self):
        User.objects.filter(pk=self.user.pk).update(last_active_at=self.now - timedelta(hours=2))
        User.objects.filter(pk=self.staff.pk).update(last_active_at=self.now - timedelta(days=40))
        with patch("accounts.admin.timezone.now", return_value=self.now):
            for window in ("day", "week", "month"):
                self.assertEqual(self._filtered_ids(LastActivityFilter, window), {self.user.pk})
            self.assertEqual(self._filtered_ids(LastActivityFilter, "older"), {self.staff.pk})
            self.assertEqual(self._filtered_ids(LastActivityFilter, "unrecorded"), {self.empty_user.pk})

    def test_data_and_import_filters_match_the_displayed_values(self):
        for filter_class in (TransactionDataFilter, SuccessfulImportsFilter):
            with self.subTest(filter=filter_class):
                self.assertEqual(self._filtered_ids(filter_class, "yes"), {self.user.pk})
                self.assertEqual(self._filtered_ids(filter_class, "no"), {self.empty_user.pk, self.staff.pk})

    def test_activity_and_login_display_use_lithuanian_time_with_dst(self):
        self.user.last_active_at = self.now
        self.user.last_login = self.now
        self.assertEqual(self.model_admin.last_active_display(self.user), "2026-10-12 11:00:00")
        self.assertEqual(self.model_admin.last_login_display(self.user), "2026-10-12 11:00:00")
        self.user.last_active_at = datetime(2026, 12, 12, 8, 0, tzinfo=datetime_timezone.utc)
        self.assertEqual(self.model_admin.last_active_display(self.user), "2026-12-12 10:00:00")

    def test_admin_list_and_detail_show_usage_but_not_financial_contents(self):
        User.objects.filter(pk=self.user.pk).update(last_active_at=self.now)
        for url in (
            reverse("admin:accounts_user_changelist"),
            reverse("admin:accounts_user_change", args=[self.user.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Last app activity (LT time)")
                self.assertContains(response, "Successful imports (incl. undone)")
                self.assertContains(response, "2026-10-12 11:00:00")
                self.assertNotContains(response, "PRIVATE TRANSACTION CONTENT")
                self.assertNotContains(response, "PRIVATE BANK FILENAME.csv")
                self.assertNotContains(response, "Private account")
        self.staff.refresh_from_db()
        self.assertIsNone(self.staff.last_active_at)

    def test_admin_filters_and_sorting_work_on_the_real_list(self):
        response = self.client.get(reverse("admin:accounts_user_changelist"), {
            "transaction_data": "yes", "successful_imports": "yes", "o": "-7",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["cl"].queryset.values_list("pk", flat=True)), [self.user.pk])

    def test_non_staff_cannot_read_usage_overview(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:accounts_user_changelist"))
        self.assertEqual(response.status_code, 302)
        self.assertNotContains(response, "Successful imports", status_code=302)

    def test_tracking_field_is_not_editable_in_admin(self):
        self.assertFalse(User._meta.get_field("last_active_at").editable)
        form = self.model_admin.get_form(self.request, self.user)
        self.assertNotIn("last_active_at", form.base_fields)
