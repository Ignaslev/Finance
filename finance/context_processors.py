from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from django.db.models import Sum
from django.conf import settings
from django.utils.translation import gettext as _, get_language

from .models import (
    Transaction,
    BalanceSnapshot,
    OnboardingState,   # <- persistent progress
    AiRun,
)
from .utils import ensure_default_categories



def onboarding(request):
    """
    Provides a single, centralized `onboarding` dict for the global banner:
      { text, cta_text, cta_href, code }

    Steps (first matching wins):
      1) upload       – shown until any transactions exist (the overview shows
                        a full first-run screen instead of this banner)
      2) balance      – shown until any BalanceSnapshot exists
      3) ready        – shows final message + “I’m done”, then never show again
                        (no hand-labelling step: the AI categorizes from the first upload)

    Reviewing categories is optional and no longer blocks anything: once a user
    has transactions, `categories_done` is switched on so auto-categorization works.

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

    from .sample_data import has_sample_data
    shared_context = {"has_sample_data": has_sample_data(request.user)}

    # If the user dismissed the final step, never show again
    if state.ready_dismissed:
        return {**shared_context, "onboarding": None}

    # Heuristics for step gating
    has_tx = Transaction.objects.filter(user=request.user, is_deleted=False).exists()
    has_balance = BalanceSnapshot.objects.filter(user=request.user).exists()
    is_lt = (get_language() or "").startswith("lt")

    if has_tx and not state.categories_done:
        state.categories_done = True
        state.save(update_fields=["categories_done", "updated_at"])

    # --- 1) Upload (until any transactions exist)
    if not has_tx:
        return {
            "onboarding": {
                "text": (
                    "Įkelk banko išrašą ir pamatyk, kur dingsta pinigai."
                    if is_lt else "Upload a bank statement to see where your money goes."
                ),
                "cta_text": "Įkelti išrašą" if is_lt else "Upload statement",
                "cta_href": reverse("overview"),
                "code": "upload",
                "step_number": 1,
                "step_total": 2,
            },
            **shared_context,
        }

    # --- 2) Balance (until any snapshot exists)
    if not has_balance:
        return {
            "onboarding": {
                "text": (
                    "Įvesk šiandienos sąskaitos likutį, kad sumos sutaptų su banku."
                    if is_lt else "Enter today's account balance so totals match your bank."
                ),
                "cta_text": _("Set a Balance"),
                "cta_href": reverse("profile"),
                "code": "balance",
                "step_number": 2,
                "step_total": 2,
            },
            **shared_context,
        }

    # --- 3) Ready (shows until dismissed). The AI categorizes on its own; corrections teach it.
    return {
        "onboarding": {
            "text": (
                "Viskas paruošta. Operacijas suskirstome automatiškai; jei kas neteisinga, pataisyk ir AI įsimins."
                if is_lt else
                "You're all set. We categorize transactions automatically; fix anything that's wrong and the AI will remember."
            ),
            "cta_text": None,
            "cta_href": None,
            "code": "ready",
            "step_number": 2,
            "step_total": 2,
        },
        **shared_context,
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
