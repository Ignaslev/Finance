"""Send due reminder emails. Run once a day (e.g. 10:00):

    python manage.py moneycoach_send_reminders --dry-run   # list who would get what
    python manage.py moneycoach_send_reminders             # send

Monthly reminder: from the 3rd of the month, to users with data who haven't uploaded since the 1st.
First-upload nudge: once, 2-14 days after sign-up, to activated users with no transactions yet.
"""
from django.core.mail import get_connection
from django.core.management.base import BaseCommand

from finance.reminders import monthly_due, nudge_due, send_reminder


class Command(BaseCommand):
    help = "Send monthly upload reminders and first-upload nudges (in each user's language)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only list recipients.")
        parser.add_argument("--limit", type=int, default=300, help="Max emails per run.")

    def handle(self, *args, **opts):
        due = [(p, "nudge") for p in nudge_due()] + [(p, "monthly") for p in monthly_due()]
        due = due[: max(0, opts["limit"])]
        if opts["dry_run"]:
            for profile, kind in due:
                self.stdout.write(f"{kind:8} {profile.preferred_language} {profile.user.email}")
            self.stdout.write(f"Dry run: {len(due)} emails would be sent.")
            return

        sent = failed = 0
        connection = get_connection()
        for profile, kind in due:
            try:
                send_reminder(profile, kind, connection=connection)
                sent += 1
            except Exception as exc:  # one bad address must not stop the rest
                failed += 1
                self.stderr.write(f"Failed {profile.user.email}: {type(exc).__name__}: {exc}")
        self.stdout.write(self.style.SUCCESS(f"Reminders sent: {sent}, failed: {failed}."))
