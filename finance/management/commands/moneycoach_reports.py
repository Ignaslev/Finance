from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta, date as _date
from calendar import monthrange

from finance.models import AdvisorReport, OnboardingState
# Import the generator helpers from views (make sure they are accessible)
# If you encounter import errors, you might need to move those helpers to a separate utils.py
# For now, assuming they are in views.py:
from finance.views import _advisor_build_payload, _advisor_call_model

User = get_user_model()


class Command(BaseCommand):
    help = "Generate scheduled Advisor Reports (Monthly on 1st, Weekly on Mon)."

    def handle(self, *args, **opts):
        today = timezone.localdate()
        processed = 0

        # 1. Monthly Report Check (Run on 1st day of month for the PREVIOUS month)
        if today.day == 1:
            # Calculate previous month
            last_day_prev = today - timedelta(days=1)
            m_start = last_day_prev.replace(day=1)
            m_end = last_day_prev

            self.stdout.write(f"Generating MONTHLY reports for {m_start} to {m_end}...")
            processed += self._run_batch("monthly", m_start, m_end)

        # 2. Weekly Report Check (Run on Monday for the PREVIOUS week)
        if today.weekday() == 0:  # 0 = Monday
            # Previous week: last Monday to last Sunday
            # today is Monday. yesterday (Sun) is end.
            w_end = today - timedelta(days=1)
            w_start = w_end - timedelta(days=6)

            self.stdout.write(f"Generating WEEKLY reports for {w_start} to {w_end}...")
            processed += self._run_batch("weekly", w_start, w_end)

        if processed == 0:
            self.stdout.write("No scheduled reports to generate today.")

    def _run_batch(self, rtype, start, end):
        count = 0
        # Only generate for users who have finished onboarding
        users = User.objects.filter(onboarding_state__categories_done=True)

        for user in users:
            # Check if already exists
            if AdvisorReport.objects.filter(user=user, type=rtype, period_start=start, period_end=end).exists():
                continue

            try:
                # Build payload
                payload = _advisor_build_payload(user, rtype, start, end)

                # Call AI
                response = _advisor_call_model(payload)

                # Save
                AdvisorReport.objects.create(
                    user=user,
                    type=rtype,
                    period_start=start,
                    period_end=end,
                    payload=payload,
                    response=response
                )
                count += 1
                self.stdout.write(f"  + Generated {rtype} for {user.username}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ! Failed {rtype} for {user.username}: {e}"))

        return count