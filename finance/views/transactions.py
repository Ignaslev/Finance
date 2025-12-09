from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
import io, csv, json
from decimal import Decimal, InvalidOperation
from datetime import datetime

from finance.models import Transaction, Category, MoneySource, OnboardingState, AiRun
from finance.utils import (
    parse_date, parse_amount, parse_in_out, normalize_currency,
    build_fingerprint_v2, ensure_default_categories, parse_date_filter,
    parse_decimal_filter
)


@login_required
def tx_edit(request, pk):
    tx = get_object_or_404(Transaction, id=pk, user=request.user, is_deleted=False)
    categories = Category.objects.filter(user=request.user).order_by("name")
    if request.method == "POST":
        cat_id = request.POST.get("category_fk")
        user_note = (request.POST.get("user_note") or "").strip()[:500]
        try:
            if cat_id:
                cat = Category.objects.get(id=int(cat_id), user=request.user)
                tx.category_fk = cat
                tx.category = cat.name
                tx.category_source = "user"
            tx.user_note = user_note
            tx.save(update_fields=["category_fk", "category", "category_source", "user_note"])
            messages.success(request, "Saved.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
        return redirect(request.GET.get("next") or "upload")
    return render(request, "tx_edit.html", {"tx": tx, "categories": categories})

@login_required
@require_http_methods(["GET", "POST"])
def tx_add(request):
    sources = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("name"))
    if not sources:
        primary_src = MoneySource.objects.create(user=request.user, name="Primary account", type="bank", is_active=True)
        sources = [primary_src]
    categories = Category.objects.filter(user=request.user).order_by("name")
    if not categories.exists():
        ensure_default_categories(request.user)
        categories = Category.objects.filter(user=request.user).order_by("name")

    if request.method == "POST":
        date_str   = (request.POST.get("date") or "").strip()
        merchant   = (request.POST.get("merchant") or "").strip()[:255]
        amount_str = (request.POST.get("amount") or "").strip().replace(",", ".")
        currency   = (request.POST.get("currency") or "EUR").strip().upper()[:8] or "EUR"
        in_out     = (request.POST.get("in_out") or "out").strip()
        notes      = (request.POST.get("notes") or "").strip()[:2000]
        user_note  = (request.POST.get("user_note") or "").strip()[:2000]
        src_id     = request.POST.get("money_source") or ""
        cat_id     = request.POST.get("category") or ""
        next_url   = request.POST.get("next") or "upload"

        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            d = timezone.localdate()
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, TypeError):
            messages.error(request, "Enter a valid amount (e.g., 12.34).")
            return redirect("tx_add")
        try:
            src = MoneySource.objects.get(id=int(src_id), user=request.user, is_active=True)
        except Exception:
            src = sources[0]

        cat = None
        if cat_id:
            try:
                cat = Category.objects.get(id=int(cat_id), user=request.user)
            except Category.DoesNotExist:
                cat = None

        fp = f"{d.isoformat()}|{merchant}|{str(amount)}|{currency}|{in_out}|{src.id}"

        if Transaction.objects.filter(user=request.user, fingerprint=fp).exists():
            messages.info(request, "This transaction already exists (duplicate skipped).")
            return redirect(next_url)

        Transaction.objects.create(
            user=request.user,
            money_source=src,
            date=d,
            merchant=merchant,
            amount=amount,
            currency=currency,
            in_out=in_out,
            notes=notes,
            user_note=user_note,
            fingerprint=fp,
            category_source="user" if cat else "unknown",
            category_fk=cat,
            category=(cat.name if cat else None),
        )
        messages.success(request, "Transaction added.")
        return redirect(next_url)

    ctx = {
        "today": timezone.localdate().strftime("%Y-%m-%d"),
        "sources": sources,
        "categories": categories,
        "next": request.GET.get("next") or request.META.get("HTTP_REFERER") or "/",
        "default_currency": "EUR",
    }
    return render(request, "tx_add.html", ctx)

@login_required
def tx_bulk_category_apply(request):
    if request.method != "POST":
        return redirect("upload")

    next_url = request.POST.get("next") or "/"
    changes_raw = request.POST.get("changes_json")
    if not changes_raw:
        messages.info(request, "No changes to apply.")
        return redirect(next_url)

    try:
        mapping = json.loads(changes_raw)
        if not isinstance(mapping, dict):
            mapping = {}
    except Exception:
        mapping = {}
    if not mapping:
        messages.info(request, "No changes to apply.")
        return redirect(next_url)

    cat_ids, tx_ids = set(), []
    for tx_id, cat_id in mapping.items():
        try:
            tx_ids.append(int(tx_id))
            cat_ids.add(int(cat_id))
        except Exception:
            continue
    cats = {c.id: c for c in Category.objects.filter(user=request.user, id__in=cat_ids)}

    applied = 0
    for tx_id, cat_id in mapping.items():
        try:
            tx_id = int(tx_id); cat_id = int(cat_id)
        except Exception:
            continue
        cat = cats.get(cat_id)
        if not cat:
            continue
        try:
            tx = Transaction.objects.get(id=tx_id, user=request.user, is_deleted=False)
        except Transaction.DoesNotExist:
            continue
        tx.category_fk = cat
        tx.category = cat.name
        tx.category_source = "user"
        tx.ai_suggested_fk = None
        tx.ai_confidence = None
        tx.save(update_fields=["category_fk", "category", "category_source", "ai_suggested_fk", "ai_confidence"])
        applied += 1

    if applied:
        messages.success(request, f"Applied changes to {applied} transaction(s).")
    else:
        messages.info(request, "Nothing changed.")

    sep = "&" if "?" in next_url else "?"
    return redirect(f"{next_url}{sep}clear_local=1")

@login_required
def uncategorized(request):
    qs = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False)
        .filter(
            Q(category_fk__isnull=True) |
            Q(category__isnull=True) |
            Q(category="")
        )
        .order_by("-date", "-id")
    )
    try:
        per = max(5, min(200, int(request.GET.get("per") or 20)))
    except (TypeError, ValueError):
        per = 20
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "uncategorized.html", {"page_obj": page_obj, "total": paginator.count, "per_value": per})

@login_required
def upload(request):
    sources = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("name"))
    if not sources:
        primary_src = MoneySource.objects.create(user=request.user, name="Primary account", type="bank", is_active=True)
        sources = [primary_src]
    default_src = sources[0]

    src_param = (request.GET.get("src") or "").strip()
    active_src = None
    if src_param and src_param != "all":
        try:
            active_src = MoneySource.objects.get(id=int(src_param), user=request.user, is_active=True)
        except MoneySource.DoesNotExist:
            active_src = None

    stype = (request.GET.get("stype") or "").strip()
    valid_types = {t for t, _ in MoneySource.TYPE_CHOICES}
    if stype and stype not in valid_types:
        stype = ""

    # -------------------- IMPORT (POST) --------------------
    if request.method == "POST" and request.FILES.get("file"):
        import_src_id = request.POST.get("import_src")
        try:
            import_src = MoneySource.objects.get(id=int(import_src_id), user=request.user, is_active=True)
        except Exception:
            import_src = default_src

        f = request.FILES["file"]
        name = (f.name or "").lower()

        parsed_count = 0
        skipped_count = 0
        rows = []

        try:
            if name.endswith(".csv"):
                raw = f.read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                text = text.replace("\r\n", "\n").replace("\r", "\n")
                lines = text.split("\n")

                sample = text[:8192]
                delimiter = None
                try:
                    dialect = csv.Sniffer().sniff(sample)
                    delimiter = dialect.delimiter
                except Exception:
                    pass
                if not delimiter:
                    counts = {sep: sample.count(sep) for sep in (";", ",", "\t")}
                    delimiter = max(counts, key=counts.get) if any(counts.values()) else ","  # <- fixed

                header_idx = 0
                for i, line in enumerate(lines[:20]):
                    if line.count(delimiter) >= 3:
                        header_idx = i
                        break
                sliced_text = "\n".join(lines[header_idx:])
                reader = csv.DictReader(io.StringIO(sliced_text), delimiter=delimiter)

                def pick(d, *aliases):
                    for a in aliases:
                        a = a.strip().lower()
                        for k in d.keys():
                            if (k or "").strip().lower() == a:
                                return d[k]
                    return None

                for r in reader:
                    rr = {(k or "").strip(): r[k] for k in r.keys()}

                    date_val   = pick(rr, "data", "date", "operacijos data", "operation date", "transaction date")
                    merchant   = pick(rr, "gavejas", "mokėtojas / gavėjas", "mokėtojo arba gavėjo pavadinimas",
                                      "merchant", "description", "parduotuvė", "counterparty", "payee")
                    amount_raw = pick(rr, "suma", "amount", "sum", "transaction amount", "suma sąskaitos valiuta")
                    currency   = pick(rr, "valiuta", "currency", "sąskaitos valiuta")
                    debcred    = pick(rr, "debetas/kreditas", "dr/cr", "dc", "d/k")
                    trans_type = pick(rr, "transakcijos tipas", "transaction type", "tipas", "type")
                    note       = pick(rr, "paskirtis", "note", "notes", "purpose", "details")
                    # Optional:
                    time_val   = pick(rr, "time", "operation time", "transaction time", "laikas")
                    descr_val  = pick(rr, "description", "details", "purpose", "mokėjimo paskirtis", "mokėjimo paskirtis (description)")

                    try:
                        d = parse_date(date_val)
                        in_out = parse_in_out(debcred, trans_type)
                        amt = parse_amount(amount_raw)
                        cur = normalize_currency(currency)
                    except Exception:
                        skipped_count += 1
                        continue
                    if not d or amt is None:
                        skipped_count += 1
                        continue

                    rows.append({
                        "date": d,
                        "time": (str(time_val).strip() if time_val else ""),
                        "merchant": (merchant or "").strip()[:200],
                        "amount": amt,
                        "currency": cur or "EUR",
                        "in_out": in_out or "out",
                        "notes": (note or "").strip()[:500],
                        "description": (str(descr_val or note or merchant or "").strip())[:500],
                    })
                    parsed_count += 1

            else:
                import pandas as pd
                df = pd.read_excel(f)
                df.columns = [str(c).strip().lower() for c in df.columns]

                def pick_row(row, *aliases):
                    for a in aliases:
                        a = a.strip().lower()
                        if a in row and pd.notna(row[a]):
                            return row[a]
                    return None

                for _, r in df.iterrows():
                    date_val   = pick_row(r, "data", "date", "operacijos data", "operation date", "transaction date")
                    merchant   = pick_row(r, "gavejas", "mokėtojas / gavėjas", "mokėtojo arba gavėjo pavadinimas",
                                          "merchant", "description", "parduotuvė", "counterparty", "payee")
                    amount_raw = pick_row(r, "suma", "amount", "sum", "transaction amount", "suma sąskaitos valiuta")
                    currency   = pick_row(r, "valiuta", "currency", "sąskaitos valiuta")
                    debcred    = pick_row(r, "debetas/kreditas", "dr/cr", "dc", "d/k")
                    trans_type = pick_row(r, "transakcijos tipas", "transaction type", "tipas", "type")
                    note       = pick_row(r, "paskirtis", "note", "notes", "purpose", "details")
                    # Optional:
                    time_val   = pick_row(r, "time", "operation time", "transaction time", "laikas")
                    descr_val  = pick_row(r, "description", "details", "purpose", "mokėjimo paskirtis", "mokėjimo paskirtis (description)")

                    try:
                        d = parse_date(date_val)
                        in_out = parse_in_out(debcred, trans_type)
                        amt = parse_amount(str(amount_raw) if amount_raw is not None else None)
                        cur = normalize_currency(currency)
                    except Exception:
                        skipped_count += 1
                        continue
                    if not d or amt is None:
                        skipped_count += 1
                        continue

                    rows.append({
                        "date": d,
                        "time": (str(time_val).strip() if time_val is not None else ""),
                        "merchant": str(merchant or "").strip()[:200],
                        "amount": amt,
                        "currency": cur or "EUR",
                        "in_out": in_out or "out",
                        "notes": str(note or "").strip()[:500],
                        "description": (str(descr_val or note or merchant or "").strip())[:500],
                    })
                    parsed_count += 1

            # ---------------- DB-only dedupe using fingerprint v2 ----------------
            existing_fps = set(
                Transaction.objects
                .filter(user=request.user)
                .values_list("fingerprint", flat=True)
            )

            db_dups = 0
            blocked_deleted = 0  # keep if you later want to count deleted-blocks
            to_create = []

            for r in rows:
                try:
                    date_iso = r["date"].strftime("%Y-%m-%d")
                except Exception:
                    skipped_count += 1
                    continue

                fp = build_fingerprint_v2(
                    date_iso=date_iso,
                    time_str=(r.get("time") or "").strip(),
                    merchant=r.get("merchant") or "",
                    amount=r.get("amount"),
                    currency=(r.get("currency") or "EUR").strip() or "EUR",
                    in_out=r.get("in_out"),
                    money_source_id=import_src.id,
                    description=r.get("description") or r.get("notes") or r.get("merchant") or "",
                )

                # 1) Fingerprint-based dedupe
                if fp in existing_fps:
                    db_dups += 1
                    continue

                # 2) Extra safety: signature-based dedupe
                merchant_norm = (r.get("merchant") or "").strip()
                cur_norm = (r.get("currency") or "EUR").strip() or "EUR"

                sig_exists = Transaction.objects.filter(
                    user=request.user,
                    money_source=import_src,
                    date=r["date"],
                    amount=r["amount"],
                    currency=cur_norm,
                    in_out=r.get("in_out"),
                    merchant__iexact=merchant_norm,
                    is_deleted=False,
                ).exists()

                if sig_exists:
                    db_dups += 1
                    continue

                to_create.append(Transaction(
                    user=request.user,
                    money_source=import_src,
                    date=r["date"],
                    merchant=merchant_norm,
                    amount=r["amount"],
                    currency=cur_norm,
                    in_out=r.get("in_out"),
                    notes=r.get("notes") or "",
                    user_note="",
                    category_fk=None,
                    category=None,
                    category_source="import",
                    fingerprint=fp,
                ))

            added = 0
            if to_create:
                Transaction.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)
                created_fps = set(
                    Transaction.objects
                    .filter(user=request.user, fingerprint__in=[t.fingerprint for t in to_create])
                    .values_list("fingerprint", flat=True)
                )
                added = len(created_fps)

            msg = (
                f'Imported into: {import_src.name}. Parsed {parsed_count}, skipped {skipped_count}. '
                f'Added {added} new transaction{"s" if added != 1 else ""}. '
                f'(DB dups: {db_dups}, blocked by deleted: {blocked_deleted}.) '
            )
            if added > 0:
                messages.success(request, msg, extra_tags="safe")
            else:
                messages.info(request, msg, extra_tags="safe")

            # ---- enqueue auto-categorize if eligible (single place) ----
            from django.conf import settings as dj_settings
            from finance.models import AiRun, OnboardingState as OBState

            TEACH_AI_UNLOCK = getattr(dj_settings, "TEACH_AI_UNLOCK", 20)
            try:
                state = request.user.onboarding_state
            except OBState.DoesNotExist:
                state = None

            if state and state.categories_done:
                labeled = Transaction.objects.filter(user=request.user, category_source="user").count()
                has_uncat = Transaction.objects.filter(
                    user=request.user, is_deleted=False, category_fk__isnull=True
                ).exists()
                if labeled >= TEACH_AI_UNLOCK and has_uncat:
                    AiRun.objects.create(user=request.user, kind="autocategorize", mode="uncat", status="queued")

            # Redirect
            qs_params = []
            if active_src:
                qs_params.append(f"src={active_src.id}")
            elif src_param == "all":
                qs_params.append("src=all")
            if stype:
                qs_params.append(f"stype={stype}")
            if qs_params:
                return redirect(f"/?{'&'.join(qs_params)}")
            return redirect("upload")

        except Exception as e:
            messages.error(request, f"Failed to import file: {e}")
            return redirect("upload")

    # -------------------- LIST (GET) --------------------
    qs = (Transaction.objects
          .filter(user=request.user, is_deleted=False)
          .select_related("category_fk", "money_source"))

    if active_src:
        qs = qs.filter(money_source=active_src)
    if stype:
        qs = qs.filter(money_source__type=stype)

    q = (request.GET.get("q") or "").strip()
    flow = (request.GET.get("flow") or "").strip()
    cat_id = (request.GET.get("cat") or "").strip()
    d_from = parse_date_filter(request.GET.get("from"))
    d_to   = parse_date_filter(request.GET.get("to"))
    a_min  = parse_decimal_filter(request.GET.get("amin"))
    a_max  = parse_decimal_filter(request.GET.get("amax"))

    if q:
        qs = qs.filter(Q(merchant__icontains=q) | Q(notes__icontains=q) | Q(user_note__icontains=q))
    if flow in ("in", "out"):
        qs = qs.filter(in_out=flow)
    if cat_id:
        try:
            qs = qs.filter(category_fk_id=int(cat_id))
        except ValueError:
            pass
    if d_from:
        qs = qs.filter(date__gte=d_from)
    if d_to:
        qs = qs.filter(date__lte=d_to)
    if a_min is not None:
        qs = qs.filter(amount__gte=a_min)
    if a_max is not None:
        qs = qs.filter(amount__lte=a_max)

    qs = qs.order_by("-date", "-id")

    uncat_count = (Transaction.objects
                   .filter(user=request.user, is_deleted=False)
                   .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
                   .count())
    low_conf_count = Transaction.objects.filter(
        user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
    ).count()

    try:
        per = max(5, min(200, int(request.GET.get("per") or 50)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    categories = Category.objects.filter(user=request.user).order_by("name")

    # Onboarding sidebar state (model-backed)
    ensure_default_categories(request.user)
    income_exists = Category.objects.filter(user=request.user, name="Income").exists()
    try:
        state = request.user.onboarding_state
        cats_done = bool(state and state.categories_done and income_exists)
    except OnboardingState.DoesNotExist:
        cats_done = False

    MIN_USER_LABELS = getattr(settings, "MIN_USER_LABELS", 30)
    has_any_tx = Transaction.objects.filter(user=request.user, is_deleted=False).exists()
    user_labels_count = Transaction.objects.filter(
        user=request.user, is_deleted=False, category_source="user"
    ).count()
    ai_locked = (has_any_tx and user_labels_count < MIN_USER_LABELS)

    ctx = {
        "page_obj": page_obj,
        "total": paginator.count,
        "uncat_count": uncat_count,
        "low_conf_count": low_conf_count,
        "per_options": [20, 50, 100, 200],
        "per_value": per,
        "q": q,
        "flow": flow,
        "cat": cat_id,
        "from": request.GET.get("from") or "",
        "to": request.GET.get("to") or "",
        "amin": request.GET.get("amin") or "",
        "amax": request.GET.get("amax") or "",
        "categories": categories,
        "sources": sources,
        "active_src": active_src,
        "src_param": src_param or "",
        "stype": stype,
        "type_choices": MoneySource.TYPE_CHOICES,
        "default_account_name": default_src.name,
        "onboarding_state": {
            "categories_done": cats_done,
            "has_income": income_exists,
            "has_any_tx": has_any_tx,
            "user_labels_count": user_labels_count,
            "min_needed": MIN_USER_LABELS,
            "ai_locked": ai_locked,
        },
    }

    last_ai_pre = request.session.pop("last_ai_pre", None)
    if last_ai_pre:
        ctx["last_ai_pre"] = last_ai_pre

    return render(request, "upload.html", ctx)

# ----------------------------- Soft delete -----------------------------

@login_required
def tx_delete(request, tx_id):
    tx = get_object_or_404(Transaction, id=tx_id, user=request.user)
    if request.method == "POST":
        note = (request.POST.get("note") or "").strip()[:200]
        if not tx.is_deleted:
            tx.is_deleted = True
            tx.deleted_at = timezone.now()
            tx.deleted_note = note
            tx.save(update_fields=["is_deleted", "deleted_at", "deleted_note"])
            messages.success(request, "Transaction deleted.")
        else:
            messages.info(request, "Transaction was already deleted.")
        return redirect(request.POST.get("next") or "upload")
    messages.error(request, "Invalid request method.")
    return redirect("upload")

@login_required
def tx_restore(request, tx_id):
    tx = get_object_or_404(Transaction, id=tx_id, user=request.user)
    if request.method == "POST":
        if tx.is_deleted:
            tx.is_deleted = False
            tx.deleted_at = None
            tx.save(update_fields=["is_deleted", "deleted_at"])
            messages.success(request, "Transaction restored.")
        else:
            messages.info(request, "Transaction is not deleted.")
        return redirect(request.POST.get("next") or "deleted_list")
    messages.error(request, "Invalid request method.")
    return redirect("deleted_list")

@login_required
def deleted_list(request):
    qs = Transaction.objects.filter(user=request.user, is_deleted=True).order_by("-deleted_at", "-id")
    try:
        per = max(5, min(200, int(request.GET.get("per") or 50)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "deleted.html", {"page_obj": page_obj, "total": paginator.count, "per_value": per})

