from django.core.management.base import BaseCommand
from django.utils import timezone
from finance.models import UserProfile

class Command(BaseCommand):
    help = "Delete accounts scheduled for deletion (after 24h delay)."

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