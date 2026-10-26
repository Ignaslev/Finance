from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import time

from django.contrib.auth import get_user_model

from finance.models import Transaction, AiRun, PdfImportJob
from finance.ai_jobs import run_ai_for_user, _eligible_for_autocategorize

AI_AUTOCAT_COOLDOWN_MIN = getattr(settings, "AI_AUTOCAT_COOLDOWN_MIN", 10)

class Command(BaseCommand):
    help = "Auto-categorize users who have uncategorized transactions."

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

        # PDF statements: OpenAI drops background data after ~10 min, so a read still "reading"
        # after 30 min will never finish; and parsed rows nobody confirmed within a day are deleted.
        PdfImportJob.objects.filter(status=PdfImportJob.STATUS_READING, created_at__lt=now - timedelta(minutes=30))             .update(status=PdfImportJob.STATUS_FAILED, error="expired")
        PdfImportJob.objects.filter(result__isnull=False, updated_at__lt=now - timedelta(days=1)).update(result=None)

        # 1) FIRST consume any queued runs (e.g., created by upload hook)
        queued = (AiRun.objects
                  .filter(status="queued")
                  .select_related("user")
                  .order_by("started_at")[:50])  # small batch
        for run in queued:
            # skip if user has a running or very recent finished run
            recent = AiRun.objects.filter(user=run.user).exclude(pk=run.pk).order_by("-started_at").first()
            if recent and (recent.status == "running" or (recent.finished_at and recent.finished_at > cooldown_ago)):
                continue
            run_ai_for_user(run.user, kind="autocategorize", mode="uncat", run=run)
            processed += 1

        # 2) ALSO pro-actively run for eligible users (no queued record yet)
        user_ids = (Transaction.objects
                    # only rows the AI has not looked at yet, so parked low-confidence rows
                    # are not re-sent to OpenAI on every cycle
                    .filter(is_deleted=False, is_internal_transfer=False, category_fk__isnull=True,
                            ai_suggested_fk__isnull=True)
                    .exclude(category_source="user")
                    .values_list("user_id", flat=True).distinct())
        for user in get_user_model().objects.filter(id__in=user_ids):

            # cooldown / lock
            recent = AiRun.objects.filter(user=user).order_by("-started_at").first()
            if recent and (recent.status == "running" or (recent.finished_at and recent.finished_at > cooldown_ago)):
                continue

            # if they already have a queued run, let the queued pass above handle it
            if AiRun.objects.filter(user=user, status="queued").exists():
                continue

            if not _eligible_for_autocategorize(user):
                continue

            run_ai_for_user(user, kind="autocategorize", mode="uncat")
            processed += 1

        return processed
