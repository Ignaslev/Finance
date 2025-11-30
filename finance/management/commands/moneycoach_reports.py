from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta, date as _date

from finance.models import AdvisorReport
# FIXED IMPORT:
from finance.services import _advisor_build_payload, _advisor_call_model

User = get_user_model()


class Command(BaseCommand):
    help = "Generate scheduled Advisor Reports (Monthly on 1st, Weekly on Mon)."

    def handle(self, *args, **opts):
        today = timezone.localdate()
        processed = 0

        # 1. Monthly Report (1st of month)
        if today.day == 1:
            last_day_prev = today - timedelta(days=1)
            m_start = last_day_prev.replace(day=1)
            m_end = last_day_prev
            self.stdout.write(f"Generating MONTHLY reports for {m_start} to {m_end}...")
            processed += self._run_batch("monthly", m_start, m_end)

        # 2. Weekly Report (Monday)
        if today.weekday() == 0:
            w_end = today - timedelta(days=1)
            w_start = w_end - timedelta(days=6)
            self.stdout.write(f"Generating WEEKLY reports for {w_start} to {w_end}...")
            processed += self._run_batch("weekly", w_start, w_end)

        if processed == 0:
            self.stdout.write("No scheduled reports to generate today.")

    def _run_batch(self, rtype, start, end):
        count = 0
        # Only users who finished onboarding (check logic/model existence first)
        users = User.objects.all()

        for user in users:
            # Skip if onboarding not done (if model exists)
            if hasattr(user, 'onboarding_state') and not user.onboarding_state.categories_done:
                continue

            if AdvisorReport.objects.filter(user=user, type=rtype, period_start=start, period_end=end).exists():
                continue

            try:
                payload = _advisor_build_payload(user, rtype, start, end)
                response = _advisor_call_model(payload)
                AdvisorReport.objects.create(
                    user=user, type=rtype, period_start=start, period_end=end,
                    payload=payload, response=response
                )
                count += 1
                self.stdout.write(f"  + Generated {rtype} for {user.username}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ! Failed {rtype} for {user.username}: {e}"))
        return count