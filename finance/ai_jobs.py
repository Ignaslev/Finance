from __future__ import annotations
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone
from django.db import transaction

from .models import Transaction, Category, AiRun, AiRunItem, OnboardingState
from .views import ai_full_categorize  # re-use your existing engine/view
from django.contrib.sessions.backends.db import SessionStore

User = get_user_model()

def _fake_request_for_user(user):
    rf = RequestFactory()
    req = rf.get("/ai/full/")
    req.user = user
    # minimal session so ai_full_categorize can stamp timestamps
    store = SessionStore()
    store.create()
    req.session = store
    return req

def _eligible_for_autocategorize(user, min_labels: int) -> bool:
    try:
        state = user.onboarding_state
    except OnboardingState.DoesNotExist:
        return False
    if not state.categories_done:
        return False
    labeled = Transaction.objects.filter(user=user, category_source="user").count()
    if labeled < min_labels:
        return False
    has_uncat = Transaction.objects.filter(
        user=user, is_deleted=False
    ).filter(
        category_fk__isnull=True
    ).exists()
    return has_uncat

def run_ai_for_user(user, *, kind: str, mode: str = "uncat") -> AiRun:
    """
    kind: 'autocategorize' or 'recheck'
    mode: 'uncat'|'ai'|'all' for your ai_full_categorize view
    Returns the AiRun with items populated.
    """
    run = AiRun.objects.create(user=user, kind=kind, mode=mode, status="running", locked_at=timezone.now())
    started = timezone.now()

    # capture pre-state to diff later
    before = Transaction.objects.filter(user=user).values_list("id", "category_fk", "category_source")

    # call your existing categorize view with a fake request
    try:
        req = _fake_request_for_user(user)
        req.GET = req.GET.copy()
        req.GET["mode"] = mode  # 'uncat' default; 'all' for recheck
        ai_full_categorize(req)  # side-effect applies/parks according to thresholds
        status = "done"
        error_text = ""
    except Exception as e:
        status = "failed"
        error_text = f"{type(e).__name__}: {e}"

    finished = timezone.now()

    # compute diff
    after = Transaction.objects.filter(user=user).values_list("id", "category_fk", "category_source", "ai_suggested_fk", "ai_confidence", "ai_reason")

    before_map = {tid: (cat, src) for (tid, cat, src) in before}
    applied = parked = skipped = considered = 0

    items = []
    for tid, cat_fk, src, sug_fk, conf, reason in after:
        old_cat, old_src = before_map.get(tid, (None, None))
        if src == "user":
            continue  # user labels are out of scope for AI actions
        # Count considered if AI touched fields or if category set from empty/ai/rule/import
        touched = (sug_fk is not None) or (old_cat != cat_fk) or (old_src != src)
        if touched:
            considered += 1

        if old_cat != cat_fk and src in ("ai", "rule", "import"):
            # category changed by AI engine (applied)
            items.append(("applied", tid, old_cat, cat_fk, conf, reason or ""))
            applied += 1
        elif sug_fk:
            # suggestion parked for review
            items.append(("parked", tid, old_cat, sug_fk, conf, reason or ""))
            parked += 1

    # Create items + finalize run
    with transaction.atomic():
        for action, tid, old_fk, new_fk, conf, reason in items:
            AiRunItem.objects.create(
                run=run,
                transaction_id=tid,
                old_category_fk_id=old_fk,
                new_category_fk_id=new_fk,
                confidence=conf,
                reason=reason,
                action=action,
            )
        run.considered = considered
        run.applied = applied
        run.parked = parked
        run.skipped = skipped
        run.status = status
        run.finished_at = finished
        run.log_text = error_text
        run.save(update_fields=["considered", "applied", "parked", "skipped", "status", "finished_at", "log_text"])

    return run
