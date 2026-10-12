from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse

from accounts.middleware import UserActivityMiddleware
from accounts.models import User


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class UserActivityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="activity-test", email="activity@example.test")
        self.factory = RequestFactory()
        self.middleware = UserActivityMiddleware(lambda request: HttpResponse())
        self.now = datetime(2026, 10, 12, 8, 0, tzinfo=datetime_timezone.utc)

    def _request(self, path="/overview/", method="get", user=None):
        request = getattr(self.factory, method)(path)
        request.user = user if user is not None else self.user
        request.resolver_match = resolve(path)
        return request

    def _record(self, request, when=None):
        match = request.resolver_match
        with patch("accounts.middleware.timezone.now", return_value=when or self.now):
            return self.middleware.process_view(request, match.func, match.args, match.kwargs)

    def test_first_authenticated_app_request_records_activity_without_changing_login(self):
        before_login = self.user.last_login
        with self.assertNumQueries(1):
            self.assertIsNone(self._record(self._request()))
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_active_at, self.now)
        self.assertEqual(self.user.last_login, before_login)

    def test_requests_in_the_same_minute_do_not_write_again(self):
        self._record(self._request())
        with self.assertNumQueries(0):
            self._record(self._request(), self.now + timedelta(seconds=59))
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_active_at, self.now)
        self._record(self._request(), self.now + timedelta(minutes=1))
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_active_at, self.now + timedelta(minutes=1))

    def test_return_visit_while_signed_in_updates_activity_not_last_login(self):
        self.client.force_login(self.user)
        self.user.refresh_from_db()
        last_login = self.user.last_login
        for when in (self.now, self.now + timedelta(days=1)):
            with patch("accounts.middleware.timezone.now", return_value=when):
                response = self.client.get(reverse("teach_ai"))
            self.assertEqual(response.status_code, 200)
            self.user.refresh_from_db()
            self.assertEqual(self.user.last_active_at, when)
            self.assertEqual(self.user.last_login, last_login)

    def test_anonymous_visits_do_not_write(self):
        with self.assertNumQueries(0):
            self._record(self._request(user=AnonymousUser()))
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_active_at)

    def test_admin_marketing_login_and_static_requests_do_not_count(self):
        for path in ("/admin/", "/", "/accounts/login/", "/robots.txt"):
            with self.subTest(path=path), self.assertNumQueries(0):
                self._record(self._request(path))
        from django.views.static import serve

        request = self.factory.get("/static/example.css")
        request.user = self.user
        with self.assertNumQueries(0):
            self.middleware.process_view(request, serve, (), {})
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_active_at)

    def test_head_requests_and_webhooks_do_not_count(self):
        for request in (self._request(method="head"), self._request("/stripe/webhook/", method="post")):
            with self.assertNumQueries(0):
                self._record(request)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_active_at)

    def test_background_status_polling_does_not_count(self):
        request = self._request()
        request.resolver_match.url_name = "ai_run_status"
        with self.assertNumQueries(0):
            self._record(request)

    def test_post_actions_record_activity_before_the_view_runs(self):
        self._record(self._request("/tx/bulk-apply/", method="post"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_active_at, self.now)

    def test_stale_concurrent_request_does_not_overwrite_a_newer_timestamp(self):
        later = self.now + timedelta(minutes=2)
        User.objects.filter(pk=self.user.pk).update(last_active_at=later)
        self._record(self._request())
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_active_at, later)

    def test_clock_moving_backwards_does_not_overwrite_activity(self):
        self._record(self._request())
        with self.assertNumQueries(0):
            self._record(self._request(), self.now - timedelta(minutes=2))

    def test_tracking_failure_does_not_block_the_app(self):
        with patch("accounts.middleware.User.objects.filter", side_effect=DatabaseError("test failure")), patch(
            "accounts.middleware.logger.warning"
        ) as warning:
            self.assertIsNone(self._record(self._request()))
        warning.assert_called_once()

    def test_middleware_runs_after_authentication(self):
        from django.conf import settings

        self.assertGreater(
            settings.MIDDLEWARE.index("accounts.middleware.UserActivityMiddleware"),
            settings.MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware"),
        )
