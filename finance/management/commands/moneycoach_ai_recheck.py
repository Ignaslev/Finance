from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings

from finance.models import OnboardingState, AiRun
from finance.ai_jobs import run_ai_for_user

class Command(BaseCommand):
    help = "Recheck categories for all eligible users (daily)."

    def handle(self, *args, **opts):
        processed = 0
        for st in OnboardingState.objects.filter(categories_done=True).select_related("user"):
            user = st.user
            # You can add your own eligibility constraints; for now, recheck everyone who finished categories
            run_ai_for_user(user, kind="recheck", mode="all")  # 'all' excludes user-labeled per your engine
            processed += 1
        self.stdout.write(self.style.SUCCESS(f"Rechecked: {processed} user(s)."))
