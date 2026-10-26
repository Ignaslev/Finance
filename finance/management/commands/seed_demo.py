"""Seed a local demo database for UI work.

Creates two local-only test accounts:
  - new@moneycompass.test  : empty account, shows the first-run screen
  - demo@moneycompass.test : about three months of realistic Lithuanian transactions

Both use the password in DEMO_PASSWORD. Refuses to run unless DEBUG is on, so it
cannot touch a production database. See DESIGN.md "Local preview".
"""
import hashlib
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from finance.models import (
    BalanceSnapshot, Category, ImportBatch, MoneySource, OnboardingState, Transaction, UserProfile,
)
from finance.utils import ensure_default_categories

DEMO_PASSWORD = "Kompasas-demo-2026"  # local demo database only

RECURRING = [
    # (day of month, merchant, amount, flow, category names to try, account key)
    (10, "UAB Telia Lietuva", "17.99", "out", ("Utilities", "Komunaliniai"), "bank"),
    (12, "Ignitis", "64.20", "out", ("Utilities", "Komunaliniai"), "bank"),
    (5, "Spotify AB", "7.99", "out", ("Subscriptions", "Prenumeratos"), "card"),
    (14, "Netflix.com", "11.99", "out", ("Subscriptions", "Prenumeratos"), "card"),
    (3, "Gym+ Lietuva", "34.00", "out", ("Fitness & Health", "Sportas ir sveikata"), "bank"),
    (25, "UAB Darbdavys LT atlyginimas", "2140.00", "in", ("Salary", "Atlyginimas"), "bank"),
]
RANDOM_SPEND = [
    # (merchant, (min, max), category names to try, times per month)
    ("MAXIMA LT, UAB", (6, 48), ("Groceries", "Maisto prekės"), 14),
    ("Rimi Lietuva", (9, 62), ("Groceries", "Maisto prekės"), 6),
    ("LIDL LIETUVA", (11, 55), ("Groceries", "Maisto prekės"), 5),
    ("Bolt Food", (12, 27), ("Dining", "Kavinės ir restoranai"), 4),
    ("Caffeine Roasters", (3.2, 6.8), ("Dining", "Kavinės ir restoranai"), 6),
    ("Bolt", (4, 14), ("Transportation", "Transportas"), 6),
    ("Circle K", (38, 72), ("Transportation", "Transportas"), 3),
    ("Senukai", (12, 140), ("Shopping", "Pirkiniai"), 2),
    ("Pigu.lt", (15, 95), ("Shopping", "Pirkiniai"), 2),
    ("Eurovaistinė", (4, 26), ("Fitness & Health", "Sportas ir sveikata"), 2),
]
UNCATEGORIZED = [("PAYPAL *STEAMGAMES", "23.49"), ("Mokėjimas: R. Kazlauskienė", "40.00"), ("VINTED", "18.50")]


class Command(BaseCommand):
    help = "Create local demo accounts with realistic data (DEBUG only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DJANGO_DEBUG=1 against a local database.")

        random.seed(42)
        new_user = self._user("naujas", "new@moneycompass.test")
        Transaction.objects.filter(user=new_user).delete()
        ImportBatch.objects.filter(user=new_user).delete()
        BalanceSnapshot.objects.filter(user=new_user).delete()
        OnboardingState.objects.update_or_create(
            user=new_user,
            defaults={"categories_done": False, "ready_dismissed": False, "intro_acknowledged_at": None},
        )
        ensure_default_categories(new_user)

        demo = self._user("demo", "demo@moneycompass.test")
        ensure_default_categories(demo)
        Transaction.objects.filter(user=demo).delete()
        OnboardingState.objects.update_or_create(
            user=demo,
            defaults={
                "categories_done": True, "upload_done": True, "balance_done": True, "teach_ai_done": True,
                "ready_dismissed": True, "intro_acknowledged_at": timezone.now(),
            },
        )
        accounts = {
            "bank": MoneySource.objects.get_or_create(user=demo, name="Swedbank", defaults={"type": "bank"})[0],
            "card": MoneySource.objects.get_or_create(user=demo, name="Revolut", defaults={"type": "bank"})[0],
        }
        categories = {c.name: c for c in Category.objects.filter(user=demo)}

        rows = self._transactions(demo, accounts, categories)
        Transaction.objects.bulk_create(rows)

        # Balances are "as of now", after the seeded rows, so the overview shows these exact amounts.
        anchor = timezone.now() + timedelta(seconds=5)
        for key, amount in (("bank", "1843.27"), ("card", "312.60")):
            MoneySource.objects.filter(pk=accounts[key].pk).update(
                manual_balance=Decimal(amount), current_balance=Decimal(amount), balance_updated_at=anchor,
            )
        BalanceSnapshot.objects.filter(user=demo).delete()
        BalanceSnapshot.objects.create(user=demo, amount=Decimal("2155.87"), timestamp=timezone.now())

        self.stdout.write(self.style.SUCCESS(
            f"Demo ready: {len(rows)} transactions for demo@moneycompass.test; "
            f"new@moneycompass.test is empty. Password: see DEMO_PASSWORD in this command."
        ))

    def _user(self, username, email):
        user, _created = get_user_model().objects.get_or_create(username=username, defaults={"email": email})
        user.email = email
        user.is_active = True
        if not user.check_password(DEMO_PASSWORD):
            user.set_password(DEMO_PASSWORD)  # only when needed, so open sessions survive a reseed
        user.save()
        UserProfile.objects.get_or_create(user=user)
        return user

    def _transactions(self, user, accounts, categories):
        def category(names):
            return next((categories[n] for n in names if n in categories), None)

        rows = []

        def add(day, merchant, amount, flow, cat, account):
            amount = Decimal(str(amount)).quantize(Decimal("0.01"))
            fingerprint = hashlib.sha256(f"demo|{day}|{merchant}|{amount}|{flow}|{len(rows)}".encode()).hexdigest()
            rows.append(Transaction(
                user=user, date=day, merchant=merchant, amount=amount, in_out=flow, currency="EUR",
                category_fk=cat, category=cat.name if cat else None,
                category_source=random.choice(["ai", "ai", "ai", "user"]) if cat else "unknown",
                money_source=account, fingerprint=fingerprint,
            ))

        today = timezone.localdate()
        month = (today.replace(day=1) - timedelta(days=75)).replace(day=1)
        while month <= today:
            for day, merchant, amount, flow, names, key in RECURRING:
                d = month.replace(day=day)
                if d <= today:
                    add(d, merchant, amount, flow, category(names), accounts[key])
            for merchant, (low, high), names, per_month in RANDOM_SPEND:
                for _ in range(per_month):
                    d = month + timedelta(days=random.randint(0, 27))
                    if d <= today:
                        add(d, merchant, round(random.uniform(low, high), 2), "out", category(names),
                            random.choice(list(accounts.values())))
            month = (month + timedelta(days=32)).replace(day=1)

        for merchant, amount in UNCATEGORIZED:
            add(today - timedelta(days=random.randint(1, 9)), merchant, amount, "out", None, accounts["card"])
        return rows
