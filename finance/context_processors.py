from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum
from django.conf import settings
from django.utils.translation import gettext as _

from .models import (
    Transaction,
    BalanceSnapshot,
    OnboardingState,   # <- persistent progress
    AiRun,
)
from .utils import ensure_default_categories

# You can tweak this here if you like, or set it in settings and read from there.
MIN_USER_LABELS = getattr(settings, "MIN_USER_LABELS", 30)


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
                "text": _("Now enter the current balance in your account so the app can perform calculations."),
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


from django.urls import reverse


def pending_delete_banner(request):
    if not request.user.is_authenticated:
        return {}

    # Account deletion takes priority over data deletion.
    try:
        profile = request.user.profile
    except Exception:
        profile = None

    if (
        profile
        and profile.account_delete_scheduled_for
        and not profile.account_delete_canceled_at
    ):
        return {
            "pending_delete_banner": {
                "kind": "account",
                "scheduled_for": profile.account_delete_scheduled_for,
                "manage_url": reverse("profile"),
                "cancel_url": reverse("profile_cancel_delete_account"),
            }
        }

    try:
        from finance.models import PendingDataDeletion

        tx_delete_req = (
            PendingDataDeletion.objects
            .filter(
                user=request.user,
                scope=PendingDataDeletion.SCOPE_TRANSACTIONS,
                scheduled_for__isnull=False,
                canceled_at__isnull=True,
            )
            .first()
        )
    except Exception:
        tx_delete_req = None

    if tx_delete_req:
        return {
            "pending_delete_banner": {
                "kind": "transactions",
                "scheduled_for": tx_delete_req.scheduled_for,
                "manage_url": reverse("data_delete_transactions"),
                "cancel_url": reverse("cancel_data_delete_transactions"),
            }
        }

    return {}


def subscription_access(request):
    if not request.user.is_authenticated:
        return {}

    from finance.subscriptions import access_context

    return {"subscription_access": access_context(request.user)}
