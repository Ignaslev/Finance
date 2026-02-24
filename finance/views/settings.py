from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.utils import timezone
from django.db.models import Sum
from django.db import transaction as dbtx
from decimal import Decimal, InvalidOperation
from datetime import date as _date
from calendar import monthrange
from collections import defaultdict

from finance.models import Category, MoneySource, Transaction, SavingsGoal, BalanceSnapshot, OnboardingState, UserProfile
from finance.utils import ensure_default_categories, _ledger_balance_by_source, _maybe_log_balance_anomaly
from django.conf import settings

# Paste: register, category_list, category_edit, category_delete, profile, onboarding_mark_done


def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()

            # === AUTO-POPULATE START ===
            # 1. Create Default Categories (Income, Groceries, etc.)
            ensure_default_categories(user)

            # 2. Create Default Accounts so the Dashboard isn't empty
            MoneySource.objects.create(user=user, name="Main Account", type="bank", is_active=True)
            MoneySource.objects.create(user=user, name="Cash Wallet", type="cash", is_active=True)
            MoneySource.objects.create(user=user, name="Savings", type="savings", is_active=True)
            # === AUTO-POPULATE END ===

            login(request, user)
            messages.success(request, "Welcome! We've set up your default accounts and categories.")
            return redirect("overview")  # Redirect to Dashboard instead of Upload
    else:
        form = UserCreationForm()
    return render(request, "register.html", {"form": form})

@login_required
def category_list(request):
    if not Category.objects.filter(user=request.user).exists():
        Category.objects.bulk_create([Category(user=request.user, name=n) for n in settings.DEFAULT_CATEGORIES])

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        color = (request.POST.get("color") or "").strip()
        if name:
            Category.objects.get_or_create(user=request.user, name=name, defaults={"color": color})
        return redirect("category_list")

    cats = Category.objects.filter(user=request.user).order_by("name")
    return render(request, "categories.html", {"categories": cats})

@login_required
def category_edit(request, pk):
    cat = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        color = (request.POST.get("color") or "").strip()
        if name:
            exists = Category.objects.filter(user=request.user, name=name).exclude(pk=cat.pk).exists()
            if not exists:
                cat.name = name
            cat.color = color
            cat.save()
        return redirect("category_list")
    return render(request, "category_edit.html", {"cat": cat})

@login_required
def category_delete(request, pk):
    cat = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == "POST":
        other, _ = Category.objects.get_or_create(user=request.user, name="Other")
        with dbtx.atomic():
            Transaction.objects.filter(user=request.user, category_fk=cat).update(category_fk=other)
            cat.delete()
        return redirect("category_list")
    return redirect("category_list")

@login_required
def profile(request):
    from django.utils.translation import gettext as _

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        # ----------------------------
        # Categories (inside Profile)
        # ----------------------------
        if action == "cat_add":
            # --- QUOTA: max categories per user ---
            MAX_CATEGORIES_PER_USER = getattr(settings, "MAX_CATEGORIES_PER_USER", 200)
            if Category.objects.filter(user=request.user).count() >= MAX_CATEGORIES_PER_USER:
                messages.error(request, _(f"You can have at most {MAX_CATEGORIES_PER_USER} categories."))
                return redirect("profile")

            name = (request.POST.get("name") or "").strip()
            if not name:
                messages.error(request, _("Name cannot be empty."))
                return redirect("profile")

            # Prevent duplicates
            created = False
            obj, created = Category.objects.get_or_create(user=request.user, name=name)
            if created:
                messages.success(request, _("Category added."))
            else:
                messages.info(request, _("Category already exists."))
            return redirect("profile")

        if action == "cat_delete":
            cat_id = request.POST.get("cat_id")
            cat = get_object_or_404(Category, id=cat_id, user=request.user)

            if cat.name == "Other":
                messages.error(request, _("“Other” cannot be deleted."))
                return redirect("profile")

            other, _o = Category.objects.get_or_create(user=request.user, name="Other")
            with dbtx.atomic():
                Transaction.objects.filter(user=request.user, category_fk=cat).update(category_fk=other)
                cat.delete()

            messages.success(request, _("Category deleted."))
            return redirect("profile")

        # Preferences
        if action == "pref_tax":
            prof, _created = UserProfile.objects.get_or_create(user=request.user)
            prof.exclude_investment_tax = bool(request.POST.get("exclude_investment_tax"))
            prof.save(update_fields=["exclude_investment_tax"])
            messages.success(request, _("Preferences saved."))
            return redirect("profile")

        # Accounts
        if action == "add":
            # --- QUOTA: max money sources per user ---
            MAX_MONEY_SOURCES_PER_USER = getattr(settings, "MAX_MONEY_SOURCES_PER_USER", 25)
            if MoneySource.objects.filter(user=request.user).count() >= MAX_MONEY_SOURCES_PER_USER:
                messages.error(request, _(f"You can have at most {MAX_MONEY_SOURCES_PER_USER} accounts."))
                return redirect("profile")

            name = (request.POST.get("name") or "").strip()
            typ  = (request.POST.get("type") or "").strip()
            if not name or typ not in dict(MoneySource.TYPE_CHOICES):
                messages.error(request, _("Provide a valid name and type."))
                return redirect("profile")
            if MoneySource.objects.filter(user=request.user, name=name).exists():
                messages.error(request, _("Account with this name already exists."))
                return redirect("profile")
            MoneySource.objects.create(user=request.user, name=name, type=typ, is_active=True)
            messages.success(request, _("Account added."))
            return redirect("profile")

        if action == "rename":
            acc_id = request.POST.get("id")
            new_name = (request.POST.get("name") or "").strip()
            acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)
            if new_name:
                exists = MoneySource.objects.filter(user=request.user, name=new_name).exclude(id=acc.id).exists()
                if exists:
                    messages.error(request, _('Another account named “%(name)s” already exists.') % {"name": new_name})
                else:
                    acc.name = new_name
                    acc.save(update_fields=["name", "updated_at"])
                    messages.success(request, _("Account renamed."))
            else:
                messages.error(request, _("Name cannot be empty."))
            return redirect("profile")

        if action == "toggle":
            acc_id = request.POST.get("id")
            acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)
            acc.is_active = not acc.is_active
            acc.save(update_fields=["is_active", "updated_at"])
            messages.success(request, (_("Activated") if acc.is_active else _("Deactivated")) + f' “{acc.name}”.')
            return redirect("profile")

        if action == "setdefault":
            acc_id = request.POST.get("id")
            try:
                acc = MoneySource.objects.get(id=int(acc_id), user=request.user, is_active=True)

                prof, _created = UserProfile.objects.get_or_create(user=request.user)
                prof.default_import_source = acc
                prof.save(update_fields=["default_import_source"])

                # Keep session too (optional/backward-compat), but DB is the real persistence now
                request.session["default_src_id"] = acc.id

                messages.success(request, f'“{acc.name}” set as default import account.')
            except (MoneySource.DoesNotExist, ValueError):
                messages.error(request, "Account not found or inactive.")
            return redirect("profile")

        if action == "setbalance":
            acc_id = request.POST.get("id")
            raw = (request.POST.get("amount") or "").strip().replace(",", ".")
            acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)

            if raw == "":
                acc.manual_balance = None
                acc.balance_updated_at = timezone.now()
                acc.save(update_fields=["manual_balance", "balance_updated_at"])
                messages.success(request, _("Manual balance cleared."))
                return redirect("profile")

            try:
                val = Decimal(raw)
                acc.manual_balance = val
                acc.balance_updated_at = timezone.now()
                acc.save(update_fields=["manual_balance", "balance_updated_at"])

                ledger_map = _ledger_balance_by_source(request.user)
                total_effective = Decimal("0")
                for a in MoneySource.objects.filter(user=request.user, is_active=True):
                    if a.type == "investment":
                        continue
                    eff = a.manual_balance if a.manual_balance is not None else ledger_map.get(a.id, Decimal("0"))
                    total_effective += (eff or Decimal("0"))

                prev_snap = (BalanceSnapshot.objects
                             .filter(user=request.user)
                             .order_by("-timestamp")
                             .first())

                new_snap = BalanceSnapshot.objects.create(
                    user=request.user,
                    amount=total_effective,
                    currency="EUR",
                    timestamp=timezone.now(),
                    note=f"Snapshot after setting manual balance for {acc.name}",
                )

                discrepancy = _maybe_log_balance_anomaly(
                    request.user, prev_snap, new_snap,
                    note="After setbalance on Profile"
                )

                if prev_snap is None:
                    messages.success(request, _("Manual balance saved and an initial snapshot was recorded."))
                else:
                    if discrepancy:
                        sign = "+" if discrepancy >= 0 else "−"
                        messages.warning(
                            request,
                            _("Manual balance saved. Anomaly recorded: snapshot vs. transactions differ by %(diff)s EUR.") %
                            {"diff": f"{sign}{abs(discrepancy):.2f}"}
                        )
                    else:
                        messages.success(request, _("Manual balance saved and a global snapshot was recorded."))
            except (InvalidOperation, TypeError):
                messages.error(request, _("Enter a valid number."))
            return redirect("profile")

        # Category caps
        if action == "setcap":
            cat_id = request.POST.get("id")
            raw = (request.POST.get("amount") or "").strip().replace(",", ".")
            cat = get_object_or_404(Category, id=cat_id, user=request.user)
            if raw == "":
                cat.monthly_cap = None
                cat.save(update_fields=["monthly_cap"])
                messages.success(request, _('Removed cap for “%(name)s”.') % {"name": cat.name})
            else:
                try:
                    val = Decimal(raw)
                    if val < 0:
                        raise InvalidOperation
                    cat.monthly_cap = val
                    cat.save(update_fields=["monthly_cap"])
                    messages.success(request, _('Saved cap for “%(name)s”.') % {"name": cat.name})
                except (InvalidOperation, TypeError):
                    messages.error(request, _("Enter a valid non-negative number."))
            return redirect("profile")

        # Savings goals
        if action == "goal_add":
            # --- QUOTA: max goals per user ---
            MAX_GOALS_PER_USER = getattr(settings, "MAX_GOALS_PER_USER", 50)
            if SavingsGoal.objects.filter(user=request.user).count() >= MAX_GOALS_PER_USER:
                messages.error(request, _(f"You can have at most {MAX_GOALS_PER_USER} goals."))
                return redirect("profile")

            name = (request.POST.get("goal_name") or "").strip()
            target_raw = (request.POST.get("goal_target") or "").strip().replace(",", ".")
            try:
                target = Decimal(target_raw)
            except Exception:
                target = Decimal("0")
            g = SavingsGoal.objects.create(user=request.user, name=name, target_amount=target, is_active=True)
            for aid in request.POST.getlist("goal_accounts"):
                try:
                    a = MoneySource.objects.get(id=int(aid), user=request.user)
                    g.accounts.add(a)
                except MoneySource.DoesNotExist:
                    pass
            messages.success(request, _("Goal created."))
            return redirect("profile")

        if action == "goal_toggle":
            gid = request.POST.get("goal_id")
            g = get_object_or_404(SavingsGoal, id=gid, user=request.user)
            g.is_active = not g.is_active
            g.save(update_fields=["is_active", "updated_at"])
            messages.success(request, (_("Activated") if g.is_active else _("Paused")) + f' “{g.name}”.')
            return redirect("profile")

        if action == "goal_delete":
            gid = request.POST.get("goal_id")
            g = get_object_or_404(SavingsGoal, id=gid, user=request.user)
            g.delete()
            messages.success(request, _("Goal deleted."))
            return redirect("profile")

    # ---------- GET ----------
    prof, _created = UserProfile.objects.get_or_create(user=request.user)

    accounts = MoneySource.objects.filter(user=request.user).order_by("type", "name")

    tx_sums = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False)
        .values("money_source_id", "in_out")
        .annotate(total=Sum("amount"))
    )
    ledger_map = defaultdict(lambda: Decimal("0"))
    for row in tx_sums:
        ms_id = row["money_source_id"]
        amt = row["total"] or Decimal("0")
        if row["in_out"] == Transaction.IN:
            ledger_map[ms_id] += amt
        else:
            ledger_map[ms_id] -= amt

    total_effective = Decimal("0")
    acc_by_id = {}
    for acc in accounts:
        ledger_val = ledger_map.get(acc.id, Decimal("0"))
        effective = acc.manual_balance if acc.manual_balance is not None else ledger_val
        acc.effective_balance = effective
        acc_by_id[acc.id] = acc
        total_effective += effective if acc.is_active else Decimal("0")

    # Suggested caps (avg of last 3 full months)
    today = timezone.localdate()
    def month_start(y, m): return _date(y, m, 1)
    def month_end(y, m):   return _date(y, m, monthrange(y, m)[1])

    prev_year = today.year if today.month > 1 else today.year - 1
    prev_month = today.month - 1 if today.month > 1 else 12

    m3 = []
    y, m = prev_year, prev_month
    for _ in range(3):
        m3.append((y, m))
        if m == 1: y, m = y - 1, 12
        else: m -= 1
    m3 = list(reversed(m3))

    start_3 = month_start(m3[0][0], m3[0][1])
    end_3   = month_end(m3[-1][0], m3[-1][1])

    spend_3 = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False, in_out=Transaction.OUT, date__gte=start_3, date__lte=end_3)
        .values("category_fk")
        .annotate(total=Sum("amount"))
    )
    spend_map = {r["category_fk"]: (r["total"] or Decimal("0")) for r in spend_3}

    cats = Category.objects.filter(user=request.user).order_by("name")
    caps_rows = []
    for c in cats:
        tot = spend_map.get(c.id, Decimal("0"))
        suggested = (tot / Decimal("3")) if tot is not None else Decimal("0")
        caps_rows.append({
            "id": c.id, "name": c.name, "color": c.color, "cap": c.monthly_cap, "suggested": suggested,
        })

    goals_qs = (
        SavingsGoal.objects
        .filter(user=request.user)
        .prefetch_related("accounts")
        .order_by("created_at", "id")
    )
    goals = []
    for g in goals_qs:
        sel_accs = [acc_by_id[a.id] for a in g.accounts.all() if a.id in acc_by_id]
        current = sum((a.effective_balance or Decimal("0") for a in sel_accs), Decimal("0"))
        target  = g.target_amount or Decimal("0")
        pct = float((current / target * 100) if target > 0 else 0.0)
        pct = 0.0 if pct != pct else max(0.0, min(pct, 200.0))
        goals.append({
            "obj": g, "accounts": sel_accs, "current": float(current), "target": float(target),
            "progress_pct": round(pct, 1), "eta_months": None,
        })

    ctx = {
        "exclude_investment_tax": prof.exclude_investment_tax,

        "accounts": accounts,
        "total_accounts_balance": float(total_effective),
        "type_choices": MoneySource.TYPE_CHOICES,
        "default_id": prof.default_import_source_id,
        "caps_rows": caps_rows,
        "caps_window_note": f"Based on average spending across {m3[0][0]:04d}-{m3[0][1]:02d} to {m3[-1][0]:04d}-{m3[-1][1]:02d}.",
        "goals": goals,

        # Categories for the Profile categories card
        "categories": cats,
    }
    return render(request, "profile.html", ctx)

@login_required
@require_POST
def onboarding_mark_done(request):
    step = (request.POST.get("step") or "").strip()

    state, _ = OnboardingState.objects.get_or_create(user=request.user)

    updated_fields = []

    if step == "categories":
        state.categories_done = True
        updated_fields.append("categories_done")
    elif step == "ready":
        state.ready_dismissed = True
        updated_fields.append("ready_dismissed")
    else:
        # Unknown step – just bounce back without changing anything
        return redirect(request.META.get("HTTP_REFERER") or "overview")

    updated_fields.append("updated_at")
    state.save(update_fields=updated_fields)

    from django.utils.translation import gettext as _
    messages.success(request, _("Thanks! We've saved your onboarding progress."))

    return redirect(request.META.get("HTTP_REFERER") or "overview")

