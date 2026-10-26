"""Measure categorisation accuracy against categories users set themselves.

Samples transactions whose category was set by the user, hides the answer, asks the current
model + prompt, and compares. The row being tested is excluded from the AI's merchant history, so it
cannot see its own label. Calls the OpenAI API (costs money): runs only with --yes.

    python manage.py moneycoach_ai_eval --limit 200            # shows what it would do
    python manage.py moneycoach_ai_eval --limit 200 --yes      # runs it
    python manage.py moneycoach_ai_eval --model gpt-5.6-luna --yes
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings
from django.utils import timezone

from finance.models import Category, Transaction
from finance.services import _call_openai_rows

BATCH = 50


class Command(BaseCommand):
    help = "Check AI categorisation accuracy against users' own categories (uses the OpenAI API with --yes)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=150, help="How many labelled transactions to test.")
        parser.add_argument("--days", type=int, default=180, help="Only transactions from the last N days.")
        parser.add_argument("--user-id", type=int, help="Only this user's transactions.")
        parser.add_argument("--model", help="Override OPENAI_CATEGORIZE_MODEL for this run.")
        parser.add_argument("--yes", action="store_true", help="Actually call the API.")

    def handle(self, *args, **opts):
        since = timezone.localdate() - timedelta(days=opts["days"])
        qs = (
            Transaction.objects
            .filter(category_source="user", is_deleted=False, is_internal_transfer=False,
                    category_fk__isnull=False, date__gte=since)
            .select_related("category_fk", "user")
        )
        if opts.get("user_id"):
            qs = qs.filter(user_id=opts["user_id"])
        sample = list(qs.order_by("?")[: max(1, opts["limit"])])
        if not sample:
            raise CommandError("No user-labelled transactions found for these filters.")

        by_user = defaultdict(list)
        for t in sample:
            by_user[t.user_id].append(t)
        calls = sum((len(rows) + BATCH - 1) // BATCH for rows in by_user.values())
        self.stdout.write(f"{len(sample)} labelled transactions from {len(by_user)} users, {calls} API calls.")
        if not opts["yes"]:
            self.stdout.write("Dry run. Add --yes to call the API.")
            return

        settings_override = {"OPENAI_CATEGORIZE_MODEL": opts["model"]} if opts.get("model") else {}
        correct, confusions, per_user = 0, Counter(), {}
        with override_settings(**settings_override):
            for user_id, txs in by_user.items():
                cats = sorted(Category.objects.filter(user_id=user_id).values_list("name", flat=True))
                user = txs[0].user
                hits = 0
                for i in range(0, len(txs), BATCH):
                    batch = txs[i:i + BATCH]
                    rows = [{
                        "id": t.id, "merchant": t.merchant or "",
                        "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}",
                        "amount": float(t.amount or 0), "in_out": t.in_out or "",
                    } for t in batch]
                    results = _call_openai_rows(user, rows, [], cats, exclude_ids=[t.id for t in batch])
                    for t in batch:
                        got = (results.get(t.id) or {}).get("category")
                        if got == t.category_fk.name:
                            hits += 1
                        else:
                            confusions[(t.category_fk.name, got or "(none)")] += 1
                correct += hits
                per_user[user_id] = (hits, len(txs))

        total = len(sample)
        self.stdout.write(self.style.SUCCESS(f"Accuracy: {correct}/{total} = {correct / total:.1%}"))
        worst = sorted(per_user.items(), key=lambda kv: kv[1][0] / kv[1][1])[:5]
        self.stdout.write("Lowest per user (user id: correct/total): " + ", ".join(f"{u}: {h}/{n}" for u, (h, n) in worst))
        if confusions:
            self.stdout.write("Most common mistakes (user's category -> AI's answer):")
            for (want, got), n in confusions.most_common(10):
                self.stdout.write(f"  {want} -> {got}: {n}")
