"""Every user sees and changes only their own data.

Crawls every URL in the app as a second user (and as an anonymous visitor), pointing every id at
the first user's records, with GET and with POSTs full of the first user's ids. Fails if anything
of the first user's shows up in a response or changes. New views are covered automatically.
"""
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver

from finance.models import (
    AiRun, AiRunItem, Asset, AssetHolding, Category, ImportBatch, MoneySource, PdfImportJob, SavingsGoal,
    Transaction,
)

SECRET = "ALICESECRET"
# Public pages, auth pages and machine endpoints that are meant to answer anonymous visitors.
PUBLIC_EXACT = {"/", "/en/", "/beta/", "/favicon.ico", "/robots.txt", "/sitemap.xml", "/register/", "/login/",
                "/logout/", "/privacy/", "/en/privacy/", "/terms/", "/en/terms/", "/contact/", "/en/contact/",
                "/finansu-valdymo-programele/", "/gidas/", "/guide/", "/stripe/webhook/"}
PUBLIC_PREFIXES = ("/geriausios-finansu-valdymo-programeles", "/straipsniai/", "/i18n/", "/accounts/",
                   "/reminders/unsubscribe/")


def _routes():
    def walk(patterns, prefix=""):
        for p in patterns:
            if isinstance(p, URLResolver):
                yield from walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                yield prefix + str(p.pattern)
    for route in walk(get_resolver().url_patterns):
        if route.startswith(("admin/", "^static")) or route.endswith(".txt"):
            continue
        yield route


@override_settings(ALLOWED_HOSTS=["testserver"], OPENAI_API_KEY="", STRIPE_SECRET_KEY="")
class CrossUserIsolationTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.alice = users.create_user(username="alice@example.test", email="alice@example.test",
                                       password="Alice-pass-123!", first_name=SECRET)
        self.bob = users.create_user(username="bob@example.test", email="bob@example.test", password="Bob-pass-123!")
        a = self.alice
        self.acc = MoneySource.objects.create(user=a, name=f"{SECRET} account", type="bank", manual_balance=Decimal("4321.09"))
        self.cat = Category.objects.create(user=a, name=f"{SECRET} category", monthly_cap=Decimal("99"))
        batch = ImportBatch.objects.create(user=a, money_source=self.acc, filename=f"{SECRET}.csv", bank_key="seb")
        self.txs = [
            Transaction.objects.create(
                user=a, money_source=self.acc, import_batch=batch, date=date(2026, 10, d), merchant=f"{SECRET} shop {d}",
                amount=Decimal("777.77"), in_out=flow, category_fk=self.cat, category=self.cat.name,
                category_source="ai", ai_suggested_fk=self.cat, ai_confidence=Decimal("0.5"),
                notes=f"{SECRET} note", fingerprint=f"alice-{d}",
            )
            for d, flow in ((1, "out"), (2, "in"), (3, "out"))
        ]
        self.deleted_tx = Transaction.objects.create(
            user=a, money_source=self.acc, date=date(2026, 10, 4), merchant=f"{SECRET} deleted", amount=Decimal("5"),
            in_out="out", is_deleted=True, fingerprint="alice-deleted",
        )
        self.goal = SavingsGoal.objects.create(user=a, name=f"{SECRET} goal", target_amount=Decimal("1000"))
        self.goal.accounts.add(self.acc)
        self.run = AiRun.objects.create(user=a, kind=AiRun.KIND_CHOICES[0][0])
        AiRunItem.objects.create(run=self.run, transaction=self.txs[0], action="applied", new_category_fk=self.cat)
        self.job = PdfImportJob.objects.create(user=a, money_source=self.acc, filename=f"{SECRET}.pdf")
        asset = Asset.objects.create(symbol="ZZZ", lookup_key="zzz-test", name="Test asset",
                                     asset_type=Asset.TYPE_CHOICES[0][0])
        self.holding = AssetHolding.objects.create(user=a, asset=asset, money_source=self.acc, quantity=Decimal("3"))
        self.alice_ids = sorted({o.pk for o in (*self.txs, self.deleted_tx, self.cat, self.acc, self.goal, self.run,
                                                self.job, self.holding)})
        self.snapshot = self._alice_state()

    def _alice_state(self):
        return (
            list(Transaction.objects.filter(user=self.alice).order_by("id").values_list(
                "id", "merchant", "amount", "category_fk", "category_source", "is_deleted", "is_internal_transfer",
                "notes", "money_source")),
            list(Category.objects.filter(user=self.alice).values_list("id", "name", "monthly_cap", "color")),
            list(MoneySource.objects.filter(user=self.alice).values_list("id", "name", "is_active", "manual_balance")),
            list(SavingsGoal.objects.filter(user=self.alice).values_list("id", "name", "target_amount", "is_active")),
            list(AssetHolding.objects.filter(user=self.alice).values_list("id", "quantity")),
            list(ImportBatch.objects.filter(user=self.alice).values_list("id", "undone_at")),
            list(PdfImportJob.objects.filter(user=self.alice).values_list("id", "status")),
            get_user_model().objects.filter(pk=self.alice.pk).values_list("email", "is_active", "password").get(),
        )

    def _urls(self):
        for route in _routes():
            if "<" not in route:
                yield "/" + route
                continue
            for pk in self.alice_ids:
                url = route
                for conv in ("<int:pk>", "<int:tx_id>", "<int:job_id>", "<int:run_id>"):
                    url = url.replace(conv, str(pk))
                url = url.replace("<str:interval>", "month").replace("<str:token>", "x").replace("<slug:slug>", "x")
                url = url.replace("<uidb64>", "x").replace("<token>", "x")
                yield "/" + url

    def _attack_payload(self):
        cat, acc = self.cat.pk, self.acc.pk
        return {
            "id": self.txs[0].pk, "tx_out_id": self.txs[0].pk, "tx_in_id": self.txs[1].pk, "cat_id": cat,
            "category_fk": cat, "category": cat, "money_source": acc, "import_src": acc, "goal_id": self.goal.pk,
            "goal_accounts": acc, "amount": "1", "name": "hacked", "display_name": "hacked", "notes": "hacked",
            "note": "hacked", "merchant": "hacked", "date": "2026-10-01", "in_out": "out", "color": "#000000",
            "action": "delete", "changes_json": json.dumps({str(t.pk): str(cat) for t in self.txs}),
            "decisions_json": json.dumps({str(t.pk): "track" for t in self.txs}),
            "normalized_merchant": f"{SECRET} shop 1", "type": "monthly", "start": "2026-10-01",
        }

    def _check(self, response, label):
        body = response.content.decode("utf-8", "ignore")
        self.assertNotIn(SECRET, body, f"{label} showed another user's data")
        self.assertNotIn("777,77", body, f"{label} showed another user's amount")
        self.assertNotIn("777.77", body, f"{label} showed another user's amount")

    def test_another_user_can_neither_see_nor_change_my_data(self):
        self.client.force_login(self.bob)
        errors = []
        for url in self._urls():
            for method in ("get", "post"):
                try:
                    if method == "get":
                        response = self.client.get(url)
                    else:
                        response = self.client.post(url, self._attack_payload())
                except Exception as exc:  # a crash is not a leak, but it should be looked at
                    errors.append(f"{method.upper()} {url}: {type(exc).__name__}: {exc}")
                    continue
                self._check(response, f"{method.upper()} {url}")
                self.client.force_login(self.bob)  # some POSTs (logout, delete account) end the session
        self.assertEqual(self._alice_state(), self.snapshot, "another user's request changed my data")
        self.assertEqual(errors, [], "\n".join(errors))

    def test_crawl_reaches_real_pages(self):
        """Control: the owner does see their data on these pages, so the checks above are not vacuous."""
        self.client.force_login(self.alice)
        showing = [url for url in self._urls() if "<" not in url and self.client.get(url).status_code == 200
                   and SECRET in self.client.get(url).content.decode("utf-8", "ignore")]
        self.assertGreaterEqual(len(showing), 5, showing)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get("/overview/").status_code, 200)

    def test_admin_cannot_take_over_an_account(self):
        admin = get_user_model().objects.create_superuser(username="root@example.test", email="root@example.test",
                                                          password="Root-pass-123!")
        self.client.force_login(admin)
        password_page = f"/admin/accounts/user/{self.alice.pk}/password/"
        self.assertEqual(self.client.get(password_page).status_code, 403)
        self.client.post(password_page, {"password1": "Taken-over-123!", "password2": "Taken-over-123!"})
        self.client.post(f"/admin/accounts/user/{self.alice.pk}/change/", {"email": "root@example.test"})
        self.assertEqual(self._alice_state(), self.snapshot)
        self.assertEqual(self.client.get(f"/admin/accounts/user/{admin.pk}/password/").status_code, 200)

    def test_admin_pages_show_no_financial_data(self):
        admin = get_user_model().objects.create_superuser(username="root@example.test", email="root@example.test",
                                                          password="Root-pass-123!")
        self.client.force_login(admin)
        from finance.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.alice)
        UserProfile.objects.filter(pk=profile.pk).update(default_import_source=self.acc)  # used to fill a dropdown
        profile_id = profile.pk
        for url in ("/admin/", "/admin/accounts/user/", f"/admin/accounts/user/{self.alice.pk}/change/",
                    "/admin/finance/userprofile/", f"/admin/finance/userprofile/{profile_id}/change/",
                    "/staff/funnel/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            body = response.content.decode("utf-8", "ignore")
            self.assertNotIn(f"{SECRET} account", body, url)
            self.assertNotIn(f"{SECRET} shop", body, url)
            self.assertNotIn("777", body.replace("7777", ""), url)

    def test_personal_identifiers_are_masked_before_the_ai(self):
        from finance.services import redact_personal
        text = redact_personal("Jonas | LT40 7300 0102 0142 6820, gav. ident. kodas 39608283137, +37061234567, j@x.lt")
        for leaked in ("7300", "39608283137", "61234567", "j@x.lt"):
            self.assertNotIn(leaked, text)
        self.assertIn("Jonas", text)

    def test_rate_limit_ip_cannot_be_spoofed(self):
        from django.test import RequestFactory
        from accounts.throttling import client_ip
        request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9")
        with self.settings(TRUSTED_PROXY_IPS=["10.0.0.0/8"]):
            self.assertEqual(client_ip(request), "203.0.113.9")

    def test_anonymous_visitors_get_no_app_pages(self):
        for url in self._urls():
            if url in PUBLIC_EXACT or url.startswith(PUBLIC_PREFIXES):
                continue
            for method in ("get", "post"):
                response = getattr(self.client, method)(url)
                self.assertIn(response.status_code, (301, 302, 403, 404, 405),
                              f"anonymous {method.upper()} {url} answered {response.status_code}")
                if response.status_code in (301, 302):
                    self.assertIn("login", response.url, f"anonymous {method.upper()} {url} -> {response.url}")
                self._check(response, f"anonymous {method.upper()} {url}")
        self.assertEqual(self._alice_state(), self.snapshot)
