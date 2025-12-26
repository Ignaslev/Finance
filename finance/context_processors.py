from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum
from django.conf import settings
from django.utils.translation import gettext as _

from .models import (
    Transaction,
    Category,
    BalanceSnapshot,
    OnboardingState,   # <- persistent progress
    AiRun,
)

# You can tweak this here if you like, or set it in settings and read from there.
MIN_USER_LABELS = getattr(settings, "MIN_USER_LABELS", 30)


def ensure_default_categories(user):
    """
    Seed default categories for a user (idempotent).
    Uses the single source of truth from settings.DEFAULT_CATEGORIES.
    """
    default_categories = getattr(settings, "DEFAULT_CATEGORIES", [])
    have = set(Category.objects.filter(user=user).values_list("name", flat=True))
    need = [Category(user=user, name=n) for n in default_categories if n not in have]
    if need:
        Category.objects.bulk_create(need)


def onboarding(request):
    """
    Provides a single, centralized `onboarding` dict for the global banner:
      { text, cta_text, cta_href, code }

    Steps (first matching wins):
      1) categories   – shown until user presses “I’m done”
      2) upload       – shown until any transactions exist
      3) balance      – shown until any BalanceSnapshot exists
      4) teach_ai     – shown until user labels reach MIN_USER_LABELS
      5) ready        – shows final message + “I’m done”, then never show again

    Persistent behavior:
      - Uses OnboardingState to persist across logins.
      - Session flags can still coexist, but the model is source of truth.
    """
    # Anonymous users: no banner
    if not request.user.is_authenticated:
        return {}

    # Make sure users at least have the defaults (safe to call repeatedly)
    ensure_default_categories(request.user)

    # Load persisted state (or create)
    state, _created = OnboardingState.objects.get_or_create(user=request.user)

    # If the user dismissed the final step, never show again
    if state.ready_dismissed:
        return {"onboarding": None, "onboarding_min_user_labels": MIN_USER_LABELS}

    # Heuristics for step gating
    has_tx = Transaction.objects.filter(user=request.user, is_deleted=False).exists()
    has_balance = BalanceSnapshot.objects.filter(user=request.user).exists()
    user_labels = Transaction.objects.filter(user=request.user, category_source="user").count()

    # --- 1) Categories (intentional gate until user clicks "I'm done")
    if not state.categories_done:
        return {
            "onboarding": {
                "text": _("Welcome! Let’s get you set up. First, check your categories, edit or add what you need."),
                "cta_text": _("Open Categories"),
                "cta_href": reverse("category_list"),
                "code": "categories",
            },
            "onboarding_min_user_labels": MIN_USER_LABELS,
        }

    # --- 2) Upload (until any transactions exist)
    if not has_tx:
        return {
            "onboarding": {
                "text": _("Next: Upload a CSV file from your bank of your transactions to begin."),
                "cta_text": _("Go to Upload"),
                "cta_href": reverse("upload"),
                "code": "upload",
            },
            "onboarding_min_user_labels": MIN_USER_LABELS,
        }

    # --- 3) Balance (until any snapshot exists)
    if not has_balance:
        return {
            "onboarding": {
                "text": _("Now set a manual balance snapshot so we have a reference point for balances."),
                "cta_text": _("Set a Balance"),
                "cta_href": reverse("profile"),
                "code": "balance",
            },
            "onboarding_min_user_labels": MIN_USER_LABELS,
        }

    # --- 4) Teach AI (until enough user labels exist)
    if user_labels < MIN_USER_LABELS:
        return {
            "onboarding": {
                "text": _(
                    "Almost there! Please label at least %(min)s transactions so AI can learn your habits. "
                    "You’ve labeled %(count)s so far."
                ) % {"min": MIN_USER_LABELS, "count": user_labels},
                "cta_text": _("Teach AI"),
                "cta_href": reverse("teach_ai"),
                "code": "teach_ai",
            },
            "onboarding_min_user_labels": MIN_USER_LABELS,
        }

    # --- 5) Ready (shows until dismissed)
    return {
        "onboarding": {
            "text": _("You're ready to auto-categorize. Keep an eye on AI results and correct anything — it will keep improving!"),
            "cta_text": None,
            "cta_href": None,
            "code": "ready",
        },
        "onboarding_min_user_labels": MIN_USER_LABELS,
    }


def ai_notifications(request):
    if not request.user.is_authenticated:
        return {}

    # Find the most recent DONE run that hasn't been notified yet
    run = AiRun.objects.filter(
        user=request.user,
        status='done',
        notified_at__isnull=True
    ).order_by('-finished_at').first()

    return {'ai_notification_run': run}
