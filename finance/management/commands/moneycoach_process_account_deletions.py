from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from finance.models import Transaction, UserProfile

class Command(BaseCommand):
    help = "Delete accounts scheduled for deletion (after 24h delay) and stale never-activated sign-ups."

    def handle(self, *args, **options):
        now = timezone.now()
        qs = (
            UserProfile.objects
            .select_related("user")
            .filter(
                account_delete_scheduled_for__isnull=False,
                account_delete_canceled_at__isnull=True,
                account_delete_scheduled_for__lte=now,
            )
        )

        deleted = 0
        for prof in qs:
            user = prof.user
            try:
                uid = user.id
                email = getattr(user, "email", "")
                user.delete()
                deleted += 1
                self.stdout.write(self.style.SUCCESS(f"Deleted user {uid} {email}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed deleting user {prof.user_id}: {e}"))

        self.stdout.write(f"Done. Deleted: {deleted}")

        removed = delete_unactivated_accounts(now)
        self.stdout.write(f"Removed never-activated sign-ups older than {UNACTIVATED_AFTER_DAYS} days: {removed}")


UNACTIVATED_AFTER_DAYS = 7


def delete_unactivated_accounts(now=None):
    """Delete sign-ups that never confirmed their email (mostly bots), so they don't pile up
    and the address can register properly later. Never touches anyone who has logged in,
    staff, or accounts with any transactions."""
    now = now or timezone.now()
    stale = (
        get_user_model().objects
        .filter(is_active=False, last_login__isnull=True, is_staff=False, is_superuser=False,
                date_joined__lte=now - timedelta(days=UNACTIVATED_AFTER_DAYS))
        .exclude(id__in=Transaction.objects.values("user_id"))
    )
    count = 0
    for user in stale:
        user.delete()
        count += 1
    return count