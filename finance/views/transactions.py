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
from datetime import datetime, timedelta
from datetime import date as date_cls
from django.utils import timezone
from django.core.mail import send_mail, mail_admins
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _, ngettext

from finance.models import (
    Transaction,
    Category,
    MoneySource,
    OnboardingState,
    AiRun,
    UserProfile,
    ImportBatch,
    PendingDataDeletion,
    RefundPairIgnore,
)

from finance.utils import (
    parse_date, parse_amount, parse_in_out, normalize_currency,
    build_fingerprint_v2, ensure_default_categories, parse_date_filter,
    parse_decimal_filter, category_names_for, default_money_source_name
)
from finance.subscriptions import access_context, require_paid_access
from django.db import transaction as db_transaction


def _safe_next_url(request, raw_url, fallback):
    if raw_url and url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return raw_url
    return fallback


DATE_INPUT_MIN = date_cls(2000, 1, 1)


def _date_in_user_range(value):
    return bool(value and DATE_INPUT_MIN <= value <= timezone.localdate())

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
            messages.success(request, _("Saved."))
        except Exception as e:
            messages.error(request, _("Error: %(error)s") % {"error": e})
        return redirect(_safe_next_url(request, request.GET.get("next"), "upload"))
    return render(request, "tx_edit.html", {"tx": tx, "categories": categories})

@login_required
@require_http_methods(["GET", "POST"])
def tx_add(request):
    sources = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("name"))
    if not sources:
        primary_src = MoneySource.objects.create(
            user=request.user,
            name=default_money_source_name(request.user),
            type="bank",
            is_active=True,
        )
        sources = [primary_src]
    categories = Category.objects.filter(user=request.user).order_by("name")
    if not categories.exists():
        ensure_default_categories(request.user)
        categories = Category.objects.filter(user=request.user).order_by("name")

    if request.method == "POST":
        blocked = require_paid_access(request)
        if blocked:
            return blocked

        date_str   = (request.POST.get("date") or "").strip()
        merchant   = (request.POST.get("merchant") or "").strip()[:255]
        amount_str = (request.POST.get("amount") or "").strip().replace(",", ".")
        currency   = (request.POST.get("currency") or "EUR").strip().upper()[:8] or "EUR"
        in_out     = (request.POST.get("in_out") or "out").strip()
        notes      = (request.POST.get("notes") or "").strip()[:2000]
        user_note  = (request.POST.get("user_note") or "").strip()[:2000]
        src_id     = request.POST.get("money_source") or ""
        cat_id     = request.POST.get("category") or ""
        next_url = _safe_next_url(request, request.POST.get("next"), "upload")

        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            messages.error(request, _("Choose a valid date from the calendar."))
            return redirect("tx_add")
        if not _date_in_user_range(d):
            messages.error(
                request,
                _("Choose a date between %(min)s and %(max)s.") % {
                    "min": DATE_INPUT_MIN.isoformat(),
                    "max": timezone.localdate().isoformat(),
                },
            )
            return redirect("tx_add")
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, TypeError):
            messages.error(request, _("Enter a valid amount (e.g., 12.34)."))
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
            messages.info(request, _("This transaction already exists (duplicate skipped)."))
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
        messages.success(request, _("Transaction added."))
        return redirect(next_url)

    ctx = {
        "today": timezone.localdate().strftime("%Y-%m-%d"),
        "date_min": DATE_INPUT_MIN.isoformat(),
        "sources": sources,
        "categories": categories,
        "next": _safe_next_url(
            request,
            request.GET.get("next") or request.META.get("HTTP_REFERER"),
            "/",
        ),
        "default_currency": "EUR",
    }
    return render(request, "tx_add.html", ctx)

@login_required
def tx_bulk_category_apply(request):
    if request.method != "POST":
        return redirect("upload")

    next_url = _safe_next_url(request, request.POST.get("next"), "/")
    changes_raw = request.POST.get("changes_json")
    if not changes_raw:
        messages.info(request, _("No changes to apply."))
        return redirect(next_url)

    try:
        mapping = json.loads(changes_raw)
        if not isinstance(mapping, dict):
            mapping = {}
    except Exception:
        mapping = {}
    if not mapping:
        messages.info(request, _("No changes to apply."))
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
        messages.success(
            request,
            ngettext(
                "Applied changes to %(count)s transaction.",
                "Applied changes to %(count)s transactions.",
                applied,
            ) % {"count": applied},
        )
    else:
        messages.info(request, _("Nothing changed."))

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

# views/upload.py (or wherever your upload view lives)

import csv
import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render

from django.conf import settings

from finance.importers import IMPORTERS
from finance.models import (
    MoneySource,
    Transaction,
    Category,
    AiRun,
    OnboardingState,
    UserProfile,
)
from finance.utils import (
    parse_date,
    parse_in_out,
    parse_amount,
    normalize_currency,
    parse_date_filter,
    parse_decimal_filter,
    build_fingerprint_v2,
    ensure_default_categories,
)


def _decode_upload_to_text(f) -> str:
    raw = f.read()
    try:
        text = raw.decode("utf-8-sig")  # handles UTF-8 with BOM too
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _guess_delimiter(header_line: str) -> str:
    # pick separator that yields the most columns
    seps = [";", ",", "\t"]
    best = ","
    best_cols = 0
    for sep in seps:
        cols = len([c for c in header_line.split(sep)])
        if cols > best_cols:
            best_cols = cols
            best = sep
    return best


def _extract_headers(text: str) -> set[str]:
    # first non-empty line is assumed header
    for line in text.split("\n"):
        if line.strip():
            delim = _guess_delimiter(line)
            return {h.strip() for h in line.split(delim) if h.strip()}
    return set()


def _pick_best_importer(headers: set[str]):
    best_imp = None
    best_res = None
    for imp in IMPORTERS.values():
        res = imp.sniff(headers)
        if best_res is None or res.score > best_res.score:
            best_res = res
            best_imp = imp
    return best_imp, best_res

@require_POST
@login_required
def undo_last_import(request):
    batch = (
        ImportBatch.objects
        .filter(user=request.user, undone_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if not batch:
        messages.warning(request, "No import found to undo.")
        return redirect("upload")

    with db_transaction.atomic():
        qs = Transaction.objects.filter(user=request.user, import_batch=batch)
        n = qs.count()

        # permanent delete (won't touch your deleted list)
        qs.delete()

        batch.undone_at = timezone.now()
        batch.save(update_fields=["undone_at"])

    messages.success(
        request,
        f"Undid last import: permanently deleted {n} transaction{'s' if n != 1 else ''}."
    )
    return redirect("upload")

def _get_tx_delete_request(user):
    return PendingDataDeletion.objects.filter(
        user=user,
        scope=PendingDataDeletion.SCOPE_TRANSACTIONS,
    ).first()

REFUND_AMOUNT_TOLERANCE = Decimal("0.00")
REFUND_MAX_DAYS = 10


def _build_refund_candidates(user, filtered_qs):
    qs = filtered_qs.filter(is_deleted=False)

    outs = list(
        qs.filter(in_out=Transaction.OUT)
        .select_related("money_source")
        .order_by("date", "id")
    )
    ins = list(
        qs.filter(in_out=Transaction.IN)
        .select_related("money_source")
        .order_by("date", "id")
    )

    if not outs or not ins:
        return []

    ignored_pairs = set(
        RefundPairIgnore.objects.filter(
            user=user,
            tx_out_id__in=[t.id for t in outs],
            tx_in_id__in=[t.id for t in ins],
        ).values_list("tx_out_id", "tx_in_id")
    )

    used_in_ids = set()
    pairs = []

    for tx_out in outs:
        best = None
        best_key = None

        for tx_in in ins:
            if tx_in.id in used_in_ids:
                continue

            if tx_out.currency != tx_in.currency:
                continue

            # Refund should be same day or later, within the configured 10-day window.
            days_apart = (tx_in.date - tx_out.date).days
            if days_apart < 0 or days_apart > REFUND_MAX_DAYS:
                continue

            amount_diff = abs((tx_out.amount or Decimal("0")) - (tx_in.amount or Decimal("0")))
            if amount_diff > REFUND_AMOUNT_TOLERANCE:
                continue

            pair_key = (tx_out.id, tx_in.id)
            if pair_key in ignored_pairs:
                continue

            sort_key = (amount_diff, days_apart, tx_in.id)
            if best is None or sort_key < best_key:
                best = tx_in
                best_key = sort_key

        if best is None:
            continue

        used_in_ids.add(best.id)

        pairs.append({
            "tx_out": tx_out,
            "tx_in": best,
            "amount_diff": best_key[0],
            "days_apart": best_key[1],
        })

    return pairs

@login_required
@require_http_methods(["GET", "POST"])
def data_delete_transactions(request):
    delete_req = _get_tx_delete_request(request.user)
    scheduled = bool(delete_req and delete_req.scheduled_for and not delete_req.canceled_at)
    scheduled_for = delete_req.scheduled_for if delete_req else None
    tx_count = Transaction.objects.filter(user=request.user).count()

    if request.method == "POST":
        if scheduled:
            messages.info(request, _("Transactions deletion is already scheduled."))
            return redirect("data_delete_transactions")

        if tx_count == 0:
            messages.info(request, _("You have no transactions to delete."))
            return redirect("upload")

        password = (request.POST.get("password") or "").strip()
        if not password or not request.user.check_password(password):
            messages.error(request, _("Incorrect password."))
            return render(request, "data_delete_confirm.html", {
                "scheduled": scheduled,
                "scheduled_for": scheduled_for,
                "tx_count": tx_count,
            })

        now = timezone.now()

        if delete_req is None:
            delete_req = PendingDataDeletion(
                user=request.user,
                scope=PendingDataDeletion.SCOPE_TRANSACTIONS,
            )

        delete_req.requested_at = now
        delete_req.scheduled_for = now + timedelta(hours=24)
        delete_req.canceled_at = None
        delete_req.save()

        try:
            when = delete_req.scheduled_for.strftime("%Y-%m-%d %H:%M")
            manage_url = request.build_absolute_uri(reverse("data_delete_transactions"))
            send_mail(
                subject="MoneyCompass – Transactions deletion scheduled",
                message=(
                    f"Your MoneyCompass transactions deletion has been scheduled.\n\n"
                    f"It will run after 24 hours: {when}.\n"
                    f"This deletes all uploaded and manually created transactions.\n"
                    f"It does not delete accounts, categories, balances, assets, or your profile.\n\n"
                    f"You can cancel it here:\n{manage_url}\n"
                ),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[request.user.email],
                fail_silently=True,
            )
        except Exception:
            pass

        try:
            mail_admins(
                "MoneyCompass – Transactions deletion scheduled",
                f"User: {request.user.email}\nScheduled for: {delete_req.scheduled_for.isoformat()}",
                fail_silently=True,
            )
        except Exception:
            pass

        messages.success(request, _("Transactions deletion scheduled. You can cancel it within 24 hours."))
        return redirect("upload")

    return render(request, "data_delete_confirm.html", {
        "scheduled": scheduled,
        "scheduled_for": scheduled_for,
        "tx_count": tx_count,
    })


@login_required
@require_POST
def cancel_data_delete_transactions(request):
    delete_req = _get_tx_delete_request(request.user)

    if not delete_req or not delete_req.scheduled_for or delete_req.canceled_at:
        messages.info(request, _("No scheduled transactions deletion found."))
        return redirect("upload")

    delete_req.canceled_at = timezone.now()
    delete_req.scheduled_for = None
    delete_req.save(update_fields=["canceled_at", "scheduled_for"])

    try:
        send_mail(
            subject="MoneyCompass – Transactions deletion canceled",
            message="Your MoneyCompass transactions deletion request has been canceled.",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[request.user.email],
            fail_silently=True,
        )
    except Exception:
        pass

    messages.success(request, _("Transactions deletion canceled."))
    return redirect("upload")

@login_required
def upload(request):
    sources = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("name"))
    if not sources:
        primary_src = MoneySource.objects.create(
            user=request.user,
            name=default_money_source_name(request.user),
            type="bank",
            is_active=True,
        )
        sources = [primary_src]

    # --- persisted default import source from UserProfile (DB), fallback to first active ---
    prof, _created = UserProfile.objects.get_or_create(user=request.user)
    default_src = None
    default_src_id = getattr(prof, "default_import_source_id", None)

    if default_src_id:
        default_src = next((s for s in sources if s.id == default_src_id), None)
        if default_src is None:
            try:
                default_src = MoneySource.objects.get(id=default_src_id, user=request.user, is_active=True)
            except MoneySource.DoesNotExist:
                default_src = None

    if default_src is None:
        default_src = sources[0]
    else:
        # Ensure default is the first option without changing template logic
        sources = [default_src] + [s for s in sources if s.id != default_src.id]

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

    # ---------------- importer helpers (RAW sniff + RAW parse) ----------------
    def _pick_best_importer(raw: bytes, filename: str):
        best_imp = None
        best_res = None
        best_score = -1

        for imp in IMPORTERS.values():
            try:
                res = imp.sniff(raw=raw, filename=filename)
            except Exception:
                continue
            if res.score > best_score:
                best_score = res.score
                best_imp = imp
                best_res = res

        return best_imp, best_res

    # -------------------- IMPORT (POST) --------------------
    if request.method == "POST" and request.FILES.get("file"):
        blocked = require_paid_access(request)
        if blocked:
            return blocked

        # --- quotas: block abusive importing ---
        MAX_IMPORTS_PER_DAY = getattr(settings, "MAX_IMPORTS_PER_DAY", 20)

        today = timezone.localdate()
        imports_today = ImportBatch.objects.filter(
            user=request.user,
            created_at__date=today,
        ).count()

        if imports_today >= MAX_IMPORTS_PER_DAY:
            messages.error(
                request,
                _("Daily import limit reached (%(limit)s). Try again tomorrow.") % {"limit": MAX_IMPORTS_PER_DAY},
            )
            return redirect("upload")

        import_src_id = request.POST.get("import_src")
        try:
            import_src = MoneySource.objects.get(id=int(import_src_id), user=request.user, is_active=True)
        except Exception:
            import_src = default_src

        f = request.FILES["file"]
        filename = (f.name or "")
        name_lower = filename.lower()
        bank = (request.POST.get("bank") or "auto").strip().lower()

        parsed_count = 0
        skipped_count = 0
        rows: list[dict] = []

        try:
            raw = f.read()

            MAX_UPLOAD_BYTES = getattr(settings, "MAX_UPLOAD_BYTES", 20 * 1024 * 1024)
            if len(raw) > MAX_UPLOAD_BYTES:
                messages.error(request, _("File is too large to import."))
                return redirect("upload")

            # ---- CSV import via bank importers ----
            if name_lower.endswith(".csv"):
                if bank == "auto":
                    importer, sniff = _pick_best_importer(raw, filename)
                    if not importer or not sniff or not sniff.ok:
                        messages.error(
                            request,
                            _("Could not detect CSV format. Please choose the bank and try again.")
                        )
                        return redirect("upload")
                else:
                    importer = IMPORTERS.get(bank)
                    if not importer:
                        messages.error(request, _("Unknown bank format selected."))
                        return redirect("upload")

                    sniff = importer.sniff(raw=raw, filename=filename)
                    if not sniff.ok:
                        sugg_imp, sugg = _pick_best_importer(raw, filename)
                        suggestion = (sugg_imp.label if sugg_imp else "")
                        if suggestion:
                            messages.error(
                                request,
                                _("This file does not look like %(bank)s. It looks like: %(suggestion)s. Please choose the correct bank and try again.")
                                % {"bank": importer.label, "suggestion": suggestion},
                            )
                        else:
                            messages.error(
                                request,
                                _("This file does not look like %(bank)s. Please choose the correct bank and try again.")
                                % {"bank": importer.label},
                            )
                        return redirect("upload")

                parsed = importer.parse_raw(raw=raw, filename=filename)

                # Defensive: allow either rows or (rows, meta)
                if isinstance(parsed, tuple):
                    rows = parsed[0] or []
                else:
                    rows = parsed or []

                parsed_count = len(rows)

            # ---- Excel import (keep your generic mapping) ----
            else:
                import pandas as pd

                df = pd.read_excel(io.BytesIO(raw))
                df.columns = [str(c).strip().lower() for c in df.columns]

                def pick_row(row, *aliases):
                    for a in aliases:
                        a = a.strip().lower()
                        if a in row and pd.notna(row[a]):
                            return row[a]
                    return None

                for row_idx, r in df.iterrows():
                    date_val   = pick_row(r, "data", "date", "operacijos data", "operation date", "transaction date")
                    merchant   = pick_row(
                        r,
                        "gavejas", "mokėtojas / gavėjas", "mokėtojo arba gavėjo pavadinimas",
                        "merchant", "description", "parduotuvė", "counterparty", "payee"
                    )
                    amount_raw = pick_row(r, "suma", "amount", "sum", "transaction amount", "suma sąskaitos valiuta")
                    currency   = pick_row(r, "valiuta", "currency", "sąskaitos valiuta")
                    debcred    = pick_row(r, "debetas/kreditas", "dr/cr", "dc", "d/k")
                    trans_type = pick_row(r, "transakcijos tipas", "transaction type", "tipas", "type")
                    note       = pick_row(r, "paskirtis", "note", "notes", "purpose", "details")
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

            # ---------------- NEW: create import batch (for Undo Last Upload) ----------------
            MAX_ROWS_PER_IMPORT = getattr(settings, "MAX_ROWS_PER_IMPORT", 20000)
            if len(rows) > MAX_ROWS_PER_IMPORT:
                messages.error(
                    request,
                    _("This file has %(count)s rows, which exceeds the per-import limit (%(limit)s).")
                    % {"count": len(rows), "limit": MAX_ROWS_PER_IMPORT},
                )
                return redirect("upload")

            # ---------------- DB-only dedupe using fingerprint v2 ----------------
            existing_fps = set(
                Transaction.objects.filter(user=request.user).values_list("fingerprint", flat=True)
            )

            db_dups = 0
            blocked_deleted = 0
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

                # 2) Signature-based safety dedupe
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

            with db_transaction.atomic():
                batch = ImportBatch.objects.create(
                    user=request.user,
                    money_source=import_src,
                    filename=filename,
                    bank_key=bank,
                )

                for pending_transaction in to_create:
                    pending_transaction.import_batch = batch

                added = 0
                if to_create:
                    Transaction.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)
                    created_fps = set(
                        Transaction.objects
                        .filter(user=request.user, fingerprint__in=[t.fingerprint for t in to_create])
                        .values_list("fingerprint", flat=True)
                    )
                    added = len(created_fps)

                # Keep "Undo last upload" meaningful: duplicate-only uploads should not create an empty batch.
                if added == 0 and not Transaction.objects.filter(import_batch=batch).exists():
                    batch.delete()
                else:
                    batch.added_count = added
                    batch.skipped_count = skipped_count
                    batch.dup_count = db_dups
                    batch.save(update_fields=["added_count", "skipped_count", "dup_count"])

            msg = _(
                "Imported into: %(account)s. Parsed %(parsed)s, skipped %(skipped)s. Added %(added)s new transactions. (DB duplicates: %(dups)s, blocked by deleted: %(blocked)s.)"
            ) % {
                "account": import_src.name,
                "parsed": parsed_count,
                "skipped": skipped_count,
                "added": added,
                "dups": db_dups,
                "blocked": blocked_deleted,
            }
            if added > 0:
                messages.success(request, msg, extra_tags="safe")
            else:
                messages.info(request, msg, extra_tags="safe")

            # ---- enqueue auto-categorize if eligible ----
            TEACH_AI_UNLOCK = getattr(settings, "TEACH_AI_UNLOCK", 20)
            try:
                state = request.user.onboarding_state
            except OnboardingState.DoesNotExist:
                state = None

            if state and state.categories_done:
                labeled = Transaction.objects.filter(user=request.user, category_source="user").count()
                has_uncat = Transaction.objects.filter(
                    user=request.user, is_deleted=False, category_fk__isnull=True
                ).exists()
                if labeled >= TEACH_AI_UNLOCK and has_uncat:
                    AiRun.objects.create(user=request.user, kind="autocategorize", mode="uncat", status="queued")

            # Redirect (preserve filters)
            qs_params = []
            if active_src:
                qs_params.append(f"src={active_src.id}")
            elif src_param == "all":
                qs_params.append("src=all")
            if stype:
                qs_params.append(f"stype={stype}")
            if qs_params:
                return redirect(f"/app/?{'&'.join(qs_params)}")
            return redirect("upload")

        except Exception as e:
            messages.error(request, _("Failed to import file: %(error)s") % {"error": e})
            return redirect("upload")

    # -------------------- LIST (GET) --------------------
    qs = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False)
        .select_related("category_fk", "money_source")
    )

    if active_src:
        qs = qs.filter(money_source=active_src)
    if stype:
        qs = qs.filter(money_source__type=stype)

    q = (request.GET.get("q") or "").strip()
    flow = (request.GET.get("flow") or "").strip()
    cat_id = (request.GET.get("cat") or "").strip()
    raw_from = request.GET.get("from") or ""
    raw_to = request.GET.get("to") or ""
    raw_amin = request.GET.get("amin") or ""
    raw_amax = request.GET.get("amax") or ""
    d_from = parse_date_filter(raw_from)
    d_to   = parse_date_filter(raw_to)
    a_min  = parse_decimal_filter(request.GET.get("amin"))
    a_max  = parse_decimal_filter(request.GET.get("amax"))
    filter_has_errors = False

    if raw_from and not _date_in_user_range(d_from):
        messages.error(request, _("Choose a valid From date from the calendar."))
        filter_has_errors = True
    if raw_to and not _date_in_user_range(d_to):
        messages.error(request, _("Choose a valid To date from the calendar."))
        filter_has_errors = True
    if d_from and d_to and d_from > d_to:
        messages.error(request, _("From date cannot be later than To date."))
        filter_has_errors = True
    if raw_amin and a_min is None:
        messages.error(request, _("Enter a valid minimum amount."))
        filter_has_errors = True
    if raw_amax and a_max is None:
        messages.error(request, _("Enter a valid maximum amount."))
        filter_has_errors = True
    if a_min is not None and a_min < 0:
        messages.error(request, _("Minimum amount cannot be negative."))
        filter_has_errors = True
    if a_max is not None and a_max < 0:
        messages.error(request, _("Maximum amount cannot be negative."))
        filter_has_errors = True
    if a_min is not None and a_max is not None and a_max < a_min:
        messages.error(request, _("Maximum amount cannot be lower than minimum amount."))
        filter_has_errors = True

    if filter_has_errors:
        qs = qs.none()

    if q:
        qs = qs.filter(Q(merchant__icontains=q) | Q(notes__icontains=q) | Q(user_note__icontains=q))
    if flow in ("in", "out"):
        qs = qs.filter(in_out=flow)
    if cat_id:
        try:
            qs = qs.filter(category_fk_id=int(cat_id))
        except ValueError:
            pass
    if d_from and not filter_has_errors:
        qs = qs.filter(date__gte=d_from)
    if d_to and not filter_has_errors:
        qs = qs.filter(date__lte=d_to)
    if a_min is not None and not filter_has_errors:
        qs = qs.filter(amount__gte=a_min)
    if a_max is not None and not filter_has_errors:
        qs = qs.filter(amount__lte=a_max)

    qs = qs.order_by("-date", "-id")

    uncat_count = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False)
        .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category=""))
        .count()
    )
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

    ensure_default_categories(request.user)
    income_exists = Category.objects.filter(
        user=request.user,
        name__in=category_names_for("income"),
    ).exists()
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

    bank_choices = [("auto", "Auto-detect")] + [(k, imp.label) for k, imp in IMPORTERS.items()]

    last_batch = (
        ImportBatch.objects
        .filter(user=request.user, undone_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    last_batch_count = (
        Transaction.objects.filter(user=request.user, import_batch=last_batch).count()
        if last_batch else 0
    )

    tx_delete_req = _get_tx_delete_request(request.user)
    tx_delete_scheduled = bool(
        tx_delete_req and tx_delete_req.scheduled_for and not tx_delete_req.canceled_at
    )
    all_tx_count = Transaction.objects.filter(user=request.user).count()
    refund_candidates = _build_refund_candidates(request.user, qs)

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
        "date_min": DATE_INPUT_MIN.isoformat(),
        "date_max": timezone.localdate().isoformat(),
        "categories": categories,
        "sources": sources,
        "active_src": active_src,
        "src_param": src_param or "",
        "stype": stype,
        "type_choices": MoneySource.TYPE_CHOICES,
        "default_account_name": default_src.name,
        "bank_choices": bank_choices,
        "last_batch": last_batch,
        "last_batch_count": last_batch_count,
        "tx_delete_scheduled": tx_delete_scheduled,
        "tx_delete_scheduled_for": (tx_delete_req.scheduled_for if tx_delete_req else None),
        "all_tx_count": all_tx_count,
        "refund_candidates": refund_candidates,
        "subscription_access": access_context(request.user),
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

@login_required
@require_POST
def refund_pair_delete(request):
    tx_out_id = request.POST.get("tx_out_id")
    tx_in_id = request.POST.get("tx_in_id")
    next_url = _safe_next_url(request, request.POST.get("next"), "upload")

    try:
        tx_out = Transaction.objects.get(
            id=int(tx_out_id),
            user=request.user,
            in_out=Transaction.OUT,
            is_deleted=False,
        )
        tx_in = Transaction.objects.get(
            id=int(tx_in_id),
            user=request.user,
            in_out=Transaction.IN,
            is_deleted=False,
        )
    except Exception:
        messages.error(request, _("Refund pair not found."))
        return redirect(next_url)

    now = timezone.now()

    with db_transaction.atomic():
        tx_out.is_deleted = True
        tx_out.deleted_at = now
        tx_out.deleted_note = "Deleted via refund pair"
        tx_out.save(update_fields=["is_deleted", "deleted_at", "deleted_note"])

        tx_in.is_deleted = True
        tx_in.deleted_at = now
        tx_in.deleted_note = "Deleted via refund pair"
        tx_in.save(update_fields=["is_deleted", "deleted_at", "deleted_note"])

    messages.success(request, _("Refund pair deleted. Both transactions were moved to Deleted."))
    return redirect(next_url)


@login_required
@require_POST
def refund_pair_ignore(request):
    tx_out_id = request.POST.get("tx_out_id")
    tx_in_id = request.POST.get("tx_in_id")
    next_url = _safe_next_url(request, request.POST.get("next"), "upload")

    try:
        tx_out = Transaction.objects.get(
            id=int(tx_out_id),
            user=request.user,
            in_out=Transaction.OUT,
            is_deleted=False,
        )
        tx_in = Transaction.objects.get(
            id=int(tx_in_id),
            user=request.user,
            in_out=Transaction.IN,
            is_deleted=False,
        )
    except Exception:
        messages.error(request, _("Refund pair not found."))
        return redirect(next_url)

    RefundPairIgnore.objects.get_or_create(
        user=request.user,
        tx_out=tx_out,
        tx_in=tx_in,
    )

    messages.success(request, _("Refund pair ignored."))
    return redirect(next_url)

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
            messages.success(request, _("Transaction deleted."))
        else:
            messages.info(request, _("Transaction was already deleted."))
        return redirect(_safe_next_url(request, request.POST.get("next"), "upload"))
    messages.error(request, _("Invalid request method."))
    return redirect("upload")

@login_required
def tx_restore(request, tx_id):
    tx = get_object_or_404(Transaction, id=tx_id, user=request.user)
    if request.method == "POST":
        if tx.is_deleted:
            tx.is_deleted = False
            tx.deleted_at = None
            tx.save(update_fields=["is_deleted", "deleted_at"])
            messages.success(request, _("Transaction restored."))
        else:
            messages.info(request, _("Transaction is not deleted."))
        return redirect(_safe_next_url(request, request.POST.get("next"), "deleted_list"))
    messages.error(request, _("Invalid request method."))
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

