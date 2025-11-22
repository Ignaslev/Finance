from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import time

from finance.models import OnboardingState, Transaction, AiRun
from finance.ai_jobs import run_ai_for_user, _eligible_for_autocategorize

TEACH_AI_UNLOCK = getattr(settings, "TEACH_AI_UNLOCK", 20)
AI_AUTOCAT_COOLDOWN_MIN = getattr(settings, "AI_AUTOCAT_COOLDOWN_MIN", 10)

class Command(BaseCommand):
    help = "Auto-categorize users who finished onboarding and have uncategorized transactions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep running in a loop (dev).",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Seconds to sleep between loops (when --loop). Default 60.",
        )

    def handle(self, *args, **opts):
        loop = opts.get("loop")
        interval = max(5, int(opts.get("interval") or 60))

        while True:
            processed = self._run_once()
            self.stdout.write(self.style.SUCCESS(f"Processed: {processed} user(s)."))

            if not loop:
                break
            time.sleep(interval)

    def _run_once(self) -> int:
        now = timezone.now()
        cooldown_ago = now - timedelta(minutes=AI_AUTOCAT_COOLDOWN_MIN)
        processed = 0

        # 1) FIRST consume any queued runs (e.g., created by upload hook)
        queued = (AiRun.objects
                  .filter(status="queued")
                  .select_related("user")
                  .order_by("started_at")[:50])  # small batch
        for run in queued:
            # skip if user has a running or very recent finished run
            recent = AiRun.objects.filter(user=run.user).order_by("-started_at").first()
            if recent and (recent.status == "running" or (recent.finished_at and recent.finished_at > cooldown_ago)):
                continue
            run_ai_for_user(run.user, kind="autocategorize", mode="uncat")
            processed += 1

        # 2) ALSO pro-actively run for eligible users (no queued record yet)
        states = OnboardingState.objects.filter(categories_done=True).select_related("user")
        for st in states:
            user = st.user

            # cooldown / lock
            recent = AiRun.objects.filter(user=user).order_by("-started_at").first()
            if recent and (recent.status == "running" or (recent.finished_at and recent.finished_at > cooldown_ago)):
                continue

            # if they already have a queued run, let the queued pass above handle it
            if AiRun.objects.filter(user=user, status="queued").exists():
                continue

            if not _eligible_for_autocategorize(user, TEACH_AI_UNLOCK):
                continue

            run_ai_for_user(user, kind="autocategorize", mode="uncat")
            processed += 1

        return processed
