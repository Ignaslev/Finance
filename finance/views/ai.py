from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _, ngettext
import os, json

from finance.models import Transaction, Category, AiRun, AiRunItem
from finance.utils import (
    category_names_for,
    default_category_name,
    ensure_default_categories,
    find_category_by_kind,
    _normalize_merchant,
    looks_like_self_transfer,
)
from finance.subscriptions import require_paid_access
from finance.services import _pick_examples, _call_openai_rows

BATCH_SIZE = 50
AUTO_CHANGE_THRESHOLD = 0.90


def _safe_next_url(request, raw_url, fallback):
    if raw_url and url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return raw_url
    return fallback

@login_required
@require_POST
def ai_dismiss_notification(request, run_id):
    run = get_object_or_404(AiRun, id=run_id, user=request.user)
    run.notified_at = timezone.now()
    run.save(update_fields=['notified_at'])
    return redirect(_safe_next_url(request, request.META.get('HTTP_REFERER'), 'upload'))

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
import os, json

from finance.models import Transaction, Category
from finance.utils import ensure_default_categories, looks_like_self_transfer
from finance.services import _pick_examples, _call_openai_rows

BATCH_SIZE = 50
AUTO_CHANGE_THRESHOLD = 0.90


@login_required
@require_POST
def ai_full_categorize(request):
    """
    Modes:
      - mode=uncat (default): only truly uncategorized (no FK/blank)
      - mode=ai:              only AI-labeled
      - mode=all:             everything EXCEPT user-labeled

    Rules:
      1) Self-transfer rule (merchant matches user's name) -> 'Internal transfer'
         - runs BEFORE Income rule
      2) Prefill IN rows with empty category -> 'Income' (category_source='rule')
      3) Never assign 'Income' to OUT rows
    """
    blocked = require_paid_access(request, redirect_name="upload")
    if blocked:
        return blocked

    # Seed defaults (now includes "Internal transfer" in your DEFAULT_CATEGORIES)
    ensure_default_categories(request.user)

    mode = request.GET.get("mode", "uncat")

    # ---------- Candidate pool (EXCLUDE deleted) ----------
    if mode == "uncat":
        base = (Transaction.objects
                .filter(user=request.user, is_deleted=False)
                .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
                .exclude(category_source="user"))
    elif mode == "ai":
        base = Transaction.objects.filter(user=request.user, is_deleted=False, category_source="ai")
    elif mode == "all":
        base = Transaction.objects.filter(user=request.user, is_deleted=False).exclude(category_source="user")
    else:
        base = Transaction.objects.none()

    # Build category map early for rule lookups
    cats_by_name = {c.name: c for c in Category.objects.filter(user=request.user)}

    # ---------- HARD RULE 1: Internal transfer if merchant matches user's own name ----------
    TRANSFER_NAME = default_category_name("internal_transfer", request.user)
    transfer_cat = find_category_by_kind(request.user, "internal_transfer")

    # Fallback for older users if category wasn't created for some reason
    if transfer_cat is None:
        transfer_cat = Category.objects.create(user=request.user, name=TRANSFER_NAME)
        cats_by_name[TRANSFER_NAME] = transfer_cat

    # Only apply if user has a meaningful name set (superuser often doesn't)
    u_first = (getattr(request.user, "first_name", "") or "").strip()
    u_last = (getattr(request.user, "last_name", "") or "").strip()

    if transfer_cat and u_first and u_last:
        # Only fill EMPTY categories; never override user labels
        transfer_qs = (
            Transaction.objects
            .filter(user=request.user, is_deleted=False)
            .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
            .exclude(category_source="user")
            .only("id", "merchant")
        )

        # Iterate because "looks_like_self_transfer" is Python-side logic
        for t in transfer_qs:
            if looks_like_self_transfer(t.merchant or "", u_first, u_last):
                Transaction.objects.filter(id=t.id).update(
                    category_fk=transfer_cat,
                    category=transfer_cat.name,
                    category_source="rule",
                    ai_suggested_fk=None,
                    ai_confidence=None,
                    ai_reason="",
                    updated_at=timezone.now(),
                )

    # ---------- HARD RULE 2: Income prefill for IN & empty (AFTER transfer rule) ----------
    INCOME_NAME = default_category_name("income", request.user)
    income_cat = find_category_by_kind(request.user, "income")

    if income_cat:
        prefill_income_qs = (
            Transaction.objects
            .filter(user=request.user, is_deleted=False, in_out=Transaction.IN)
            .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
            .exclude(category_source="user")
            .only("id")
        )
        for t in prefill_income_qs:
            Transaction.objects.filter(id=t.id).update(
                category_fk=income_cat,
                category=income_cat.name,
                category_source="rule",
                ai_suggested_fk=None,
                ai_confidence=None,
                ai_reason="",
                updated_at=timezone.now(),
            )

    # refresh base after rule prefills if we're working on uncategorized
    if mode == "uncat":
        base = (Transaction.objects
                .filter(user=request.user, is_deleted=False)
                .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
                .exclude(category_source="user"))

    qs = base.order_by("date", "id").select_related("category_fk")
    total_candidates = qs.count()

    # If no key, render simple card (existing behavior)
    if not os.getenv("OPENAI_API_KEY"):
        return render(request, "ai_summary.html", {
            "key_present": False,
            "total_candidates": total_candidates,
            "applied": 0,
            "parked": 0,
            "left_for_review": Transaction.objects.filter(
                user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
            ).count(),
        })

    if total_candidates == 0:
        return render(request, "ai_summary.html", {
            "key_present": True,
            "total_candidates": 0,
            "applied": 0,
            "parked": 0,
            "left_for_review": Transaction.objects.filter(
                user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
            ).count(),
        })

    # Stamp last-run timestamp if not already set (so Review AI can show only the latest)
    if "last_ai_run_started_at" not in request.session:
        request.session["last_ai_run_started_at"] = timezone.now().isoformat()

    cats_map = {c.name: c for c in Category.objects.filter(user=request.user)}
    cats_list = sorted(cats_map.keys())

    rows = [{
        "id": t.id,
        "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}",
        "amount": float(t.amount or 0),
        "in_out": t.in_out or "",
        "current_category": (t.category_fk.name if t.category_fk else (t.category or "")) or "",
        "current_source": t.category_source or "",
    } for t in qs]

    applied = 0
    parked = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        examples = _pick_examples(request.user, limit=12)

        try:
            results = _call_openai_rows(request.user, batch, examples, cats_list)
        except Exception as e:
            return render(request, "ai_error.html", {"error": str(e), "batch_index": i // BATCH_SIZE})

        for r in batch:
            t_id = r["id"]
            try:
                t = Transaction.objects.get(pk=t_id, user=request.user, is_deleted=False)
            except Transaction.DoesNotExist:
                continue

            if t.category_source == "user":
                continue  # never override user labels

            res = results.get(t_id)
            if not res:
                continue

            suggested_name = (res["category"] or "").strip() or "Other"
            conf = float(res.get("confidence") or 0.0)
            reason = (res.get("reason") or "")[:500]
            suggested_fk = cats_map.get(suggested_name)
            if not suggested_fk:
                continue

            # Guard: Never assign "Income" to OUT rows (rule safety)
            if t.in_out == Transaction.OUT and suggested_name in category_names_for("income"):
                continue

            current_name = (t.category_fk.name if t.category_fk else (t.category or "")).strip()

            # Determine if this is a "Fresh Assignment" or a "Change"
            is_new_assignment = (not current_name or current_name in category_names_for("other"))

            # Threshold: 0.70 for fresh assignments, 0.90 for overwrites
            apply_threshold = 0.70 if is_new_assignment else AUTO_CHANGE_THRESHOLD

            if is_new_assignment:
                if conf >= apply_threshold:
                    t.category_fk = suggested_fk
                    t.category = suggested_fk.name
                    t.category_source = "ai"
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.ai_suggested_fk = None
                    t.save(update_fields=[
                        "category_fk", "category", "category_source", "ai_confidence",
                        "ai_reason", "ai_suggested_fk", "updated_at"
                    ])
                    applied += 1
                else:
                    t.ai_suggested_fk = suggested_fk
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.save(update_fields=["ai_suggested_fk", "ai_confidence", "ai_reason", "updated_at"])
                    parked += 1
                continue

            if suggested_name == current_name:
                if t.category_source == "ai":
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.ai_suggested_fk = None
                    t.save(update_fields=["ai_confidence", "ai_reason", "ai_suggested_fk", "updated_at"])
                continue

            if conf >= apply_threshold:
                t.category_fk = suggested_fk
                t.category = suggested_fk.name
                t.category_source = "ai"
                t.ai_confidence = conf
                t.ai_reason = reason
                t.ai_suggested_fk = None
                t.save(update_fields=[
                    "category_fk", "category", "category_source", "ai_confidence",
                    "ai_reason", "ai_suggested_fk", "updated_at"
                ])
                applied += 1
            elif conf >= 0.70:
                t.ai_suggested_fk = suggested_fk
                t.ai_confidence = conf
                t.ai_reason = reason
                t.save(update_fields=["ai_suggested_fk", "ai_confidence", "ai_reason", "updated_at"])

    left_for_review = Transaction.objects.filter(
        user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
    ).count()

    return render(request, "ai_summary.html", {
        "key_present": True,
        "total_candidates": total_candidates,
        "applied": applied,
        "parked": parked,
        "left_for_review": left_for_review,
    })



@login_required
@require_POST
def ai_run_uncategorized(request):
    blocked = require_paid_access(request, redirect_name="upload")
    if blocked:
        return blocked

    base = Transaction.objects.filter(user=request.user, is_deleted=False)
    eligible_qs = (
        base
        .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
        .exclude(category_source="user")
    )
    n = eligible_qs.count()

    if n == 0:
        messages.info(request, _("No eligible uncategorized transactions to categorize."))
        return redirect("upload")
    request.session["last_ai_pre"] = {
        "kind": "uncategorized",
        "considered": n,
        "started_at": timezone.now().isoformat(),
    }

    request.session["last_ai_run_started_at"] = timezone.now().isoformat()

    request.GET = request.GET.copy()
    request.GET["mode"] = "uncat"
    return ai_full_categorize(request)

@login_required
@require_POST
def ai_recheck_all(request):
    """
    Re-evaluate categories:
      - scope=ai   -> only AI-labeled rows
      - scope=all  -> everything except user-labeled
      - default    -> ai
    Stamps a session timestamp so Review (AI) can show only rows from the latest run.
    """
    blocked = require_paid_access(request, redirect_name="upload")
    if blocked:
        return blocked

    from django.utils import timezone

    scope = (request.GET.get("scope") or "ai").lower()
    base = Transaction.objects.filter(user=request.user, is_deleted=False)

    if scope == "all":
        n = base.exclude(category_source="user").count()
        mode = "all"
        kind = "recheck_all"
        if n == 0:
            messages.info(request, _("No eligible transactions to recheck (excluding user-labeled)."))
            return redirect("upload")
    else:
        n = base.filter(category_source="ai").count()
        mode = "ai"
        kind = "recheck_ai"
        if n == 0:
            messages.info(request, _("No AI-labeled transactions to recheck."))
            return redirect("upload")

    # PRG card + last run timestamp
    request.session["last_ai_pre"] = {
        "kind": kind,
        "considered": n,
        "started_at": timezone.now().isoformat(),
    }
    request.session["last_ai_run_started_at"] = timezone.now().isoformat()

    request.GET = request.GET.copy()
    request.GET["mode"] = mode
    return ai_full_categorize(request)

@login_required
def review_low_conf(request):
    qs = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        ai_suggested_fk__isnull=False,
    ).order_by("-id")
    try:
        per = max(5, min(200, int(request.GET.get("per") or 50)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))
    categories = Category.objects.filter(user=request.user).order_by("name")
    return render(request, "review_low.html", {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
        "categories": categories,
    })

@login_required
@require_POST
def review_low_apply(request):
    # 1. Read the JSON payload
    changes_raw = request.POST.get("changes_json")
    if not changes_raw:
        messages.info(request, _("No changes to apply."))
        return redirect("review_low_conf")

    try:
        mapping = json.loads(changes_raw)
    except Exception:
        messages.error(request, _("Invalid data format."))
        return redirect("review_low_conf")

    if not mapping:
        messages.info(request, _("No changes selected."))
        return redirect("review_low_conf")

    # 2. Optimizing the DB fetch
    # Get all relevant transactions in one go
    tx_ids = [int(k) for k in mapping.keys() if str(k).isdigit()]
    transactions = Transaction.objects.filter(id__in=tx_ids, user=request.user, is_deleted=False)

    # Get all relevant categories
    cat_ids = {int(v) for v in mapping.values() if str(v).isdigit()}
    cats = {c.id: c for c in Category.objects.filter(user=request.user, id__in=cat_ids)}

    applied = 0

    # 3. Apply loop
    for tx in transactions:
        new_cat_id = mapping.get(str(tx.id))
        if not new_cat_id:
            continue

        try:
            cat = cats.get(int(new_cat_id))
        except (ValueError, TypeError):
            continue

        if cat:
            tx.category_fk = cat
            tx.category = cat.name
            tx.category_source = "user"
            # Clear AI fields since user made a decision
            tx.ai_suggested_fk = None
            tx.ai_confidence = None

            # We use update_fields for performance
            tx.save(update_fields=["category_fk", "category", "category_source", "ai_suggested_fk", "ai_confidence"])
            applied += 1

    messages.success(
        request,
        ngettext("Applied %(count)s change.", "Applied %(count)s changes.", applied) % {"count": applied},
    )
    return redirect("review_low_conf")

@login_required
def review_ai_recent(request):
    """
    Shows only AI-labeled rows from the latest AI run (based on session timestamp).
    Falls back to all AI rows if the timestamp is missing.
    """
    qs = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        category_source="ai",
    )

    ts = request.session.get("last_ai_run_started_at")
    if ts:
        try:
            from datetime import datetime
            from django.utils import timezone
            dt = datetime.fromisoformat(ts)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            qs = qs.filter(updated_at__gte=dt)
        except Exception:
            pass

    qs = qs.order_by("-updated_at", "-id")

    per = request.GET.get("per")
    try:
        per = max(5, min(200, int(per)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "review_ai.html", {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
    })

@login_required
@require_http_methods(["GET","POST"])
def teach_ai(request):
    """
    Teach AI: OUT flow only.
    GET: list one row per normalized merchant (OUT), ranked by frequency (up to 30).
    POST: apply one chosen category per merchant across all matching uncategorized OUT rows.
    """
    ensure_default_categories(request.user)

    MIN_USER_LABELS = 20
    BATCH_MERCHANTS = 20

    # Base pool: only truly uncategorized, non-deleted, and OUT flow only
    base = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False, in_out=Transaction.OUT)
        .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
    )

    if request.method == "POST":
        # Expect keys like: mk__out|<normalized_merchant> = <category_id>
        pairs = []
        for k, v in request.POST.items():
            if not k.startswith("mk__"):
                continue
            if v:
                pairs.append((k[len("mk__"):], v))

        if not pairs:
            messages.error(request, _("Select categories for at least one merchant."))
            return redirect("teach_ai")

        cat_ids = {int(cid) for _, cid in pairs if str(cid).isdigit()}
        cats = {c.id: c for c in Category.objects.filter(user=request.user, id__in=cat_ids)}

        applied = 0
        # Pre-fetch applicable OUT rows to speed normalization matching
        qs_apply = base.exclude(merchant="").only("id", "merchant", "in_out", "category_fk", "category", "category_source")
        for mk, cid in pairs:
            try:
                flow, norm = mk.split("|", 1)
            except ValueError:
                continue

            # Defensive: only OUT flow allowed here
            if flow != Transaction.OUT:
                continue

            cat = cats.get(int(cid))
            if not cat:
                continue

            batch_ids = []
            for t in qs_apply:
                if _normalize_merchant(t.merchant or "") == norm:
                    # Guard: never set Income on OUT
                    if cat.name in category_names_for("income"):
                        continue
                    batch_ids.append(t.id)

            if batch_ids:
                Transaction.objects.filter(id__in=batch_ids).update(
                    category_fk=cat,
                    category=cat.name,
                    category_source="user",
                    ai_suggested_fk=None,
                    ai_confidence=None,
                    updated_at=timezone.now(),
                )
                applied += len(batch_ids)

        if applied:
            messages.success(
                request,
                ngettext(
                    "Applied categories to %(count)s transaction.",
                    "Applied categories to %(count)s transactions.",
                    applied,
                ) % {"count": applied},
            )
        else:
            messages.info(request, _("Nothing to apply."))
        return redirect("upload")

    # ---------------- GET: build one row per normalized merchant (OUT only) ----------------
    from collections import defaultdict
    counts = defaultdict(int)
    samples = defaultdict(lambda: {"merchant": "", "flow": ""})

    for t in base.exclude(merchant="").only("merchant", "in_out"):
        norm = _normalize_merchant(t.merchant or "")
        key = (Transaction.OUT, norm)
        counts[key] += 1
        if not samples[key]["merchant"]:
            samples[key]["merchant"] = (t.merchant or "").strip()
            samples[key]["flow"] = Transaction.OUT

    ranked = sorted(samples.items(), key=lambda kv: (-counts[kv[0]], kv[0][1]))

    rows = []
    for (flow, norm), meta in ranked[:BATCH_MERCHANTS]:
        merchant_display = meta["merchant"] or norm
        form_key = f"mk__{flow}|{norm}"
        rows.append({
            "merchant_display": merchant_display,
            "flow": flow,  # always 'out' here
            "count": counts[(flow, norm)],
            "form_key": form_key,
        })

    categories = Category.objects.filter(user=request.user).order_by("name")
    return render(request, "teach_ai.html", {
        "rows": rows,
        "categories": categories,
        "target_labels": MIN_USER_LABELS,
        "total_unique_shown": len(rows),
    })

@login_required
def review_ai_runs(request):
    qs = (AiRun.objects
          .filter(user=request.user)
          .order_by("-started_at"))

    kind = (request.GET.get("kind") or "").strip()
    status = (request.GET.get("status") or "").strip()
    if kind in {"autocategorize", "recheck"}:
        qs = qs.filter(kind=kind)
    if status in {"queued", "running", "done", "failed"}:
        qs = qs.filter(status=status)

    try:
        per = max(5, min(200, int(request.GET.get("per") or 20)))
    except (TypeError, ValueError):
        per = 20

    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    STATUSES = ["queued", "running", "done", "failed"]  # ← add this
    ctx = {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
        "kind": kind,
        "status": status,
        "statuses": STATUSES,  # ← and pass it
    }
    return render(request, "review_ai.html", ctx)

@login_required
def review_ai_run_detail(request, run_id: int):
    """Show a single AI run and the items (what changed / parked)."""
    run = get_object_or_404(AiRun, id=run_id, user=request.user)
    items = (run.items
             .select_related("transaction", "old_category_fk", "new_category_fk")
             .all())

    action = (request.GET.get("action") or "").strip()
    if action in {"applied", "parked", "skipped"}:
        items = items.filter(action=action)

    try:
        per = max(5, min(200, int(request.GET.get("per") or 50)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(items.order_by("-id"), per)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx = {
        "run": run,
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
        "action": action,
    }
    return render(request, "review_ai_detail.html", ctx)
