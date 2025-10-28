from django.http import HttpResponse
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
import hashlib, pandas as pd
from io import StringIO
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from django.db import transaction as dbtx
import os, json, re
from openai import OpenAI
from datetime import datetime, date as _date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Case, When, DecimalField, F
from django.db.models.functions import TruncMonth
from django.shortcuts import render, redirect
from django.utils import timezone

from .models import Transaction, Category, BalanceSnapshot

import csv, io
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from .models import Transaction, Category
from .models import Transaction, Category, MoneySource
from django.db.models import Sum  # 👈 add this
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime
from collections import defaultdict

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect

from .models import Transaction, Category, BalanceSnapshot, MoneySource




AUTO_APPLY_THRESHOLD   = 0.80  # >= this → apply directly
AUTO_CHANGE_THRESHOLD  = 0.90  # when changing an existing AI/rule category
BATCH_SIZE             = 50

def env_check(request):
    ok = bool(os.getenv("OPENAI_API_KEY"))
    return HttpResponse("OPENAI_API_KEY loaded: " + ("YES" if ok else "NO"))

def home(request):
    return HttpResponse("It works")

DEFAULT_CATEGORIES = ["Cash","Dining","Fitness & Health","Groceries","Shopping","Crypto","Utilities","Other"]

def ensure_default_categories(user):
    from .models import Category
    if not Category.objects.filter(user=user).exists():
        Category.objects.bulk_create([Category(user=user, name=n) for n in DEFAULT_CATEGORIES])


def _fp(user_id, date, merchant, amount, currency, in_out, notes) -> str:
    """Stable hash to skip duplicates per user."""
    key = "|".join([
        str(user_id or ""),
        str(date or ""),
        (merchant or "").strip().lower(),
        f"{float(amount):.2f}" if amount not in (None, "") else "",
        (currency or "").strip().upper(),
        (in_out or "").strip().lower(),
        (notes or "").strip().lower(),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

@login_required
def tx_edit(request, pk):
    tx = get_object_or_404(Transaction, id=pk, user=request.user, is_deleted=False)
    categories = Category.objects.filter(user=request.user).order_by("name")

    if request.method == "POST":
        cat_id = request.POST.get("category_id")
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
def uncategorized(request):
    """
    List transactions missing a category (or explicitly 'Other'),
    excluding soft-deleted rows.
    """
    qs = (Transaction.objects
          .filter(user=request.user, is_deleted=False)
          .filter(
              Q(category_fk__isnull=True) |
              Q(category__isnull=True) |
              Q(category="") |
              Q(category="Other")
          )
          .order_by("-date", "-id"))

    per = request.GET.get("per")
    try:
        per = max(5, min(200, int(per)))
    except (TypeError, ValueError):
        per = 20

    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "uncategorized.html", {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
    })

def _read_df(fileobj):
    # Excel
    try:
        if fileobj.name.lower().endswith((".xlsx",".xls")):
            return pd.read_excel(fileobj)
    except Exception:
        pass
    # CSV (Lithuanian bank style)
    raw = fileobj.read()
    try:
        txt = raw.decode("utf-8-sig", errors="replace")
    except Exception:
        txt = raw.decode("utf-8", errors="replace")
    try:
        return pd.read_csv(StringIO(txt), engine="python", sep=";", quotechar='"', skiprows=1, on_bad_lines="skip")
    except Exception:
        try:
            return pd.read_csv(StringIO(txt), engine="python", sep=",", on_bad_lines="skip")
        except Exception:
            return None


def fingerprint(row, source_id: int):
    """Stable dedupe key per user+source: date|merchant|amount|currency|in_out|source"""
    return f"{row['date']}|{row['merchant']}|{row['amount']}|{row['currency']}|{row['in_out']}|{source_id}"



def parse_amount(raw):
    if raw is None:
        return Decimal("0")
    s = str(raw).strip().replace("€", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


def parse_in_out(debcred_value=None, trans_type=None):
    """
    Decide 'in' or 'out'. Preference:
    - DEBETAS/KREDITAS: 'D' -> out, 'C' -> in
    - TRANSAKCIJOS TIPAS: contains 'GAVIM' (in) or 'MOK' (out)
    Fallback to 'out'.
    """
    v = (debcred_value or "").strip().upper()
    if v == "D":
        return "out"
    if v == "C":
        return "in"
    t = (trans_type or "").upper()
    if "GAVIM" in t:
        return "in"
    if "MOK" in t:
        return "out"
    return "out"


def normalize_currency(s):
    s = (s or "").strip().upper()
    return "EUR" if s in ("", "€", "EURO", "EUR") else s


def parse_date(val):
    """Try common bank formats."""
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except Exception:
            continue
    return timezone.now().date()


def parse_date_filter(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def parse_decimal_filter(s):
    s = (s or "").strip().replace("€", "").replace(",", ".")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


@login_required
def upload(request):
    """
    Upload page with multi-account support + account-type filter + robust import + PRG:
      - Account filter (?src=<id>|all) and Account Type filter (?stype=bank|cash|savings)
      - Upload form lets you choose the target account (import_src)
      - CSV/XLSX import (delimiter sniff, preamble-skip)
      - Dedupe DB + within-file; diagnostics
      - After POST -> messages + redirect('upload')
      - Standard filters + pagination
    """
    # ---- Accounts for this user ----
    sources = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("name"))
    if not sources:
        primary_src = MoneySource.objects.create(user=request.user, name="Primary account", type="bank", is_active=True)
        sources = [primary_src]
    default_src = sources[0]

    # Read account filter for the table (GET)
    src_param = (request.GET.get("src") or "").strip()
    active_src = None
    if src_param and src_param != "all":
        try:
            active_src = MoneySource.objects.get(id=int(src_param), user=request.user, is_active=True)
        except MoneySource.DoesNotExist:
            active_src = None  # fallback to all

    # Read account TYPE filter (GET)
    stype = (request.GET.get("stype") or "").strip()  # "", "bank", "cash", "savings"
    valid_types = {t for t, _ in MoneySource.TYPE_CHOICES}
    if stype and stype not in valid_types:
        stype = ""  # guard against invalid values

    # -------------------- IMPORT (POST) --------------------
    if request.method == "POST" and request.FILES.get("file"):
        # Which account to import into? (form select)
        import_src_id = request.POST.get("import_src")
        try:
            import_src = MoneySource.objects.get(id=int(import_src_id), user=request.user, is_active=True)
        except Exception:
            import_src = default_src  # fallback

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

                # delimiter sniff
                sample = text[:8192]
                delimiter = None
                try:
                    dialect = csv.Sniffer().sniff(sample)
                    delimiter = dialect.delimiter
                except Exception:
                    pass
                if not delimiter:
                    counts = {sep: sample.count(sep) for sep in (";", ",", "\t")}
                    delimiter = max(counts, key=counts.get) if any(counts.values()) else ","

                # find header line (skip preamble/title)
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
                        "merchant": (merchant or "").strip()[:200],
                        "amount": amt,
                        "currency": cur or "EUR",
                        "in_out": in_out or "out",
                        "notes": (note or "").strip()[:500],
                    })
                    parsed_count += 1

            else:
                # XLSX
                try:
                    import pandas as pd
                except ImportError:
                    messages.error(request, "XLSX support requires pandas. Install with: pip install pandas openpyxl")
                    return redirect("upload")

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
                        "merchant": str(merchant or "").strip()[:200],
                        "amount": amt,
                        "currency": cur or "EUR",
                        "in_out": in_out or "out",
                        "notes": str(note or "").strip()[:500],
                    })
                    parsed_count += 1

            # ---- Dedupe: DB + within-file (account-aware fingerprint) ----
            fps = [fingerprint(r, import_src.id) for r in rows]

            existing_qs = Transaction.objects.filter(user=request.user, fingerprint__in=fps)
            existing_set = set(existing_qs.values_list("fingerprint", flat=True))
            blocked_deleted = existing_qs.filter(is_deleted=True).count()

            seen = set()
            duplicates_file = 0
            for fp in fps:
                if fp in seen:
                    duplicates_file += 1
                else:
                    seen.add(fp)

            seen_fps = set(existing_set)
            to_create = []
            for r in rows:
                fp = fingerprint(r, import_src.id)
                if fp in seen_fps:
                    continue
                seen_fps.add(fp)
                to_create.append(Transaction(
                    user=request.user,
                    money_source=import_src,
                    date=r["date"],
                    merchant=r["merchant"],
                    amount=r["amount"],
                    currency=r["currency"],
                    in_out=r["in_out"],
                    notes=r["notes"],
                    fingerprint=fp,
                    category_source="import",
                ))

            added = len(to_create)
            if added:
                Transaction.objects.bulk_create(to_create, batch_size=500, ignore_conflicts=True)

            # messages + redirect (PRG)
            if added == 0:
                messages.info(
                    request,
                    f"Imported into: {import_src.name}. Parsed {parsed_count}, skipped {skipped_count}. "
                    f"No new transactions. Duplicates in DB: {len(existing_set)} (blocked by deleted: {blocked_deleted}), "
                    f"duplicates in file: {duplicates_file}."
                )
            else:
                messages.success(
                    request,
                    f"Imported into: {import_src.name}. Parsed {parsed_count}, skipped {skipped_count}. "
                    f"Added {added} new transaction{'s' if added != 1 else ''}. "
                    f"(DB dups: {len(existing_set)}, file dups: {duplicates_file}, blocked by deleted: {blocked_deleted}.)"
                )

            # keep account/account-type filter on redirect
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

    # Apply account filter
    if active_src:
        qs = qs.filter(money_source=active_src)

    # Apply account TYPE filter
    if stype:
        qs = qs.filter(money_source__type=stype)

    # Other filters
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
                   .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category="") | Q(category="Other"))
                   .count())
    low_conf_count = Transaction.objects.filter(
        user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
    ).count()

    per = request.GET.get("per")
    try:
        per = max(5, min(200, int(per)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    categories = Category.objects.filter(user=request.user).order_by("name")

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
        "sources": sources,                         # for dropdowns
        "active_src": active_src,
        "src_param": src_param or "",
        "stype": stype,                             # current account-type filter
        "type_choices": MoneySource.TYPE_CHOICES,   # ('bank','cash','savings') with labels
        "default_account_name": default_src.name,
    }
    return render(request, "upload.html", ctx)



def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("upload")
    else:
        form = UserCreationForm()
    return render(request, "register.html", {"form": form})

@login_required
def uncategorized(request):
    qs = (Transaction.objects
          .filter(user=request.user, is_deleted=False)
          .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category="") | Q(category="Other"))
          .order_by("-date", "-id"))

    per = request.GET.get("per")
    try:
        per = max(5, min(200, int(per)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "uncategorized.html", {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
    })


@login_required
def category_list(request):
    # Seed defaults for the user (once)
    defaults = ["Cash", "Dining", "Fitness & Health", "Groceries", "Shopping", "Crypto", "Utilities", "Other"]
    if not Category.objects.filter(user=request.user).exists():
        Category.objects.bulk_create([Category(user=request.user, name=n) for n in defaults])

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
            # ensure uniqueness per user
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
        # find (or create) user's "Other" for reassignment
        other, _ = Category.objects.get_or_create(user=request.user, name="Other")
        with dbtx.atomic():
            Transaction.objects.filter(user=request.user, category_fk=cat).update(category_fk=other)
            cat.delete()
        return redirect("category_list")
    # simple confirm page inline in list; but if called directly:
    return redirect("category_list")

def _normalize_merchant(name: str) -> str:
    if not name: return ""
    s = name.upper()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[#,/ ]?X[- ]?\d+$", "", s)
    s = re.sub(r"\s+\d{3,}$", "", s)
    return s

def _pick_examples(user, limit=10):
    qs = (Transaction.objects
          .filter(user=user)
          .exclude(category_fk__isnull=True)
          .filter(category_source__in=["user","rule","ai"])
          .order_by("-date","-id")
          .select_related("category_fk"))[:500]
    ex, seen = [], set()
    for t in qs:
        m = _normalize_merchant(t.merchant)
        if m in seen:
            continue
        seen.add(m)
        ex.append({
            "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}"[:240],
            "amount": float(t.amount or 0),
            "in_out": t.in_out or "",
            "category": t.category_fk.name if t.category_fk else (t.category or "Other"),
        })
        if len(ex) >= limit:
            break
    return ex

def _call_openai_rows(user, rows, examples, cats):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)
    schema = {
        "type":"object",
        "properties":{
            "results":{
                "type":"array",
                "items":{
                    "type":"object",
                    "properties":{
                        "id":{"type":"integer"},
                        "category":{"type":"string","enum":cats},
                        "confidence":{"type":"number","minimum":0,"maximum":1},
                        "reason":{"type":"string"}
                    },
                    "required":["id","category","confidence"]
                }
            }
        },
        "required":["results"]
    }

    msg = (
        "You classify transactions into exactly one category from this list.\n"
        f"Categories: {', '.join(cats)}\n\n"
        "My labeled examples (treat these as ground truth):\n" +
        "\n".join([f"- text='{e['text']}', amount={e['amount']}, in_out={e['in_out']} => {e['category']}" for e in examples]) +
        "\n\nIf current_category_source=='user', output the SAME category (do not change it).\n"
        "Return strict JSON matching the schema."
    )

    rows_text = "\n".join([
        f"- id={r['id']}, text='{(r.get('text') or '')[:240]}', amount={r.get('amount',0)}, in_out='{r.get('in_out','')}', current_category='{r.get('current_category','')}', current_category_source='{r.get('current_source','')}'"
        for r in rows
    ])

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type":"json_schema","json_schema":{"name":"tx_categorizer","schema":schema}},
        messages=[
            {"role":"system","content":"JSON-only finance categorizer."},
            {"role":"user","content": msg + "\n\nRows:\n" + rows_text},
        ],
        temperature=0,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        txt = resp.choices[0].message.content
        start = txt.find("{"); end = txt.rfind("}")
        data = json.loads(txt[start:end+1]) if start>=0 and end>=0 else {"results":[]}

    out = {}
    for r in data.get("results", []):
        out[int(r.get("id"))] = {
            "category": r.get("category") or "Other",
            "confidence": float(r.get("confidence") or 0),
            "reason": r.get("reason") or ""
        }
    return out

@login_required
def ai_full_categorize(request):
    """
    Modes:
      - mode=uncat (default): only uncategorized / 'Other'
      - mode=ai:     only previously AI-labeled
      - mode=all:    everything EXCEPT user-labeled (we never override user)
    Behavior:
      - If row has no category: apply when confidence >= AUTO_APPLY_THRESHOLD, else park (ai_suggested_fk).
      - If row has AI/rule category and AI proposes a DIFFERENT one:
          * if confidence >= AUTO_CHANGE_THRESHOLD -> auto-change
          * elif confidence >= AUTO_APPLY_THRESHOLD -> park as change suggestion (ai_suggested_fk)
          * else ignore (keep current)
    """
    # ensure categories exist
    if not Category.objects.filter(user=request.user).exists():
        from .views import ensure_default_categories
        ensure_default_categories(request.user)

    key_present = bool(os.getenv("OPENAI_API_KEY"))
    if not key_present:
        return render(request, "ai_summary.html", {
            "key_present": False,
            "total_candidates": 0,
            "applied": 0,
            "parked": 0,
            "left_for_review": 0,
        })

    mode = request.GET.get("mode", "uncat")

    # ---------- Candidate pool (EXCLUDE deleted) ----------
    if mode == "uncat":
        qs = (Transaction.objects
              .filter(user=request.user, is_deleted=False)  # NEW
              .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category="") | Q(category="Other")))
    elif mode == "ai":
        qs = Transaction.objects.filter(user=request.user, is_deleted=False, category_source="ai")  # NEW
    elif mode == "all":
        qs = Transaction.objects.filter(user=request.user, is_deleted=False).exclude(category_source="user")  # NEW
    else:
        qs = Transaction.objects.none()

    qs = qs.order_by("date", "id")
    total_candidates = qs.count()
    if total_candidates == 0:
        return render(request, "ai_summary.html", {
            "key_present": True,
            "total_candidates": 0,
            "applied": 0,
            "parked": 0,
            "left_for_review": Transaction.objects.filter(
                user=request.user, is_deleted=False, ai_suggested_fk__isnull=False  # NEW
            ).count(),
        })

    cats_map = {c.name: c for c in Category.objects.filter(user=request.user)}
    applied = 0
    parked  = 0

    # Build payload once
    rows = []
    for t in qs.select_related("category_fk"):
        rows.append({
            "id": t.id,
            "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}",
            "amount": float(t.amount or 0),
            "in_out": t.in_out or "",
            "current_category": (t.category_fk.name if t.category_fk else (t.category or "")) or "",
            "current_source": t.category_source or "",
        })

    # Process in batches; refresh examples per batch so it learns as you go
    cats_list = sorted(cats_map.keys())
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        examples = _pick_examples(request.user, limit=10)

        try:
            results = _call_openai_rows(request.user, batch, examples, cats_list)
        except Exception as e:
            return render(request, "ai_error.html", {"error": str(e), "batch_index": i // BATCH_SIZE})

        for r in batch:
            t_id = r["id"]
            # Guard against operating on deleted rows (or others’ rows)
            try:
                t = Transaction.objects.get(pk=t_id, user=request.user, is_deleted=False)  # NEW
            except Transaction.DoesNotExist:
                continue

            res = results.get(t_id)
            if not res:
                continue

            suggested_name = res["category"]
            conf = float(res["confidence"] or 0)
            reason = (res.get("reason") or "")[:500]
            suggested_fk = cats_map.get(suggested_name)
            if not suggested_fk:
                continue

            # Never override user-labeled
            if t.category_source == "user":
                continue

            current_name = (t.category_fk.name if t.category_fk else (t.category or "")).strip()

            if not current_name or current_name == "" or current_name == "Other":
                # fresh assignment
                if conf >= AUTO_APPLY_THRESHOLD:
                    t.category_fk = suggested_fk
                    t.category = suggested_fk.name
                    t.category_source = "ai"
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.ai_suggested_fk = None
                    t.save(update_fields=["category_fk","category","category_source","ai_confidence","ai_reason","ai_suggested_fk"])
                    applied += 1
                else:
                    t.ai_suggested_fk = suggested_fk
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.save(update_fields=["ai_suggested_fk","ai_confidence","ai_reason"])
                    parked += 1
            else:
                # row already has AI/rule category; check for change
                if suggested_name == current_name:
                    # optional: refresh confidence/reason
                    if t.category_source == "ai":
                        t.ai_confidence = conf
                        t.ai_reason = reason
                        t.ai_suggested_fk = None
                        t.save(update_fields=["ai_confidence","ai_reason","ai_suggested_fk"])
                    continue

                # different suggestion
                if conf >= AUTO_CHANGE_THRESHOLD:
                    # very confident → auto-change
                    t.category_fk = suggested_fk
                    t.category = suggested_fk.name
                    t.category_source = "ai"
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.ai_suggested_fk = None
                    t.save(update_fields=["category_fk","category","category_source","ai_confidence","ai_reason","ai_suggested_fk"])
                    applied += 1
                elif conf >= AUTO_APPLY_THRESHOLD:
                    # moderate confidence → park as change suggestion
                    t.ai_suggested_fk = suggested_fk
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.save(update_fields=["ai_suggested_fk","ai_confidence","ai_reason"])
                    parked += 1
                else:
                    # low confidence → ignore (keep current)
                    pass

    left_for_review = Transaction.objects.filter(
        user=request.user, is_deleted=False, ai_suggested_fk__isnull=False  # NEW
    ).count()

    return render(request, "ai_summary.html", {
        "key_present": True,
        "total_candidates": total_candidates,
        "applied": applied,
        "parked": parked,
        "left_for_review": left_for_review,
    })

@login_required
def tx_delete(request, tx_id):
    """
    Soft-delete a transaction: hide from all lists/charts but keep in DB
    so re-uploads don’t recreate it (fingerprint dedupe still sees it).
    """
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
        # go back to where the user came from
        return redirect(request.POST.get("next") or "upload")
    # Disallow GET deletes
    messages.error(request, "Invalid request method.")
    return redirect("upload")


@login_required
def tx_restore(request, tx_id):
    """Restore a previously deleted transaction."""
    tx = get_object_or_404(Transaction, id=tx_id, user=request.user)
    if request.method == "POST":
        if tx.is_deleted:
            tx.is_deleted = False
            tx.deleted_at = None
            # keep deleted_note for audit or clear it, your call. I’ll keep it.
            tx.save(update_fields=["is_deleted", "deleted_at"])
            messages.success(request, "Transaction restored.")
        else:
            messages.info(request, "Transaction is not deleted.")
        return redirect(request.POST.get("next") or "deleted_list")
    messages.error(request, "Invalid request method.")
    return redirect("deleted_list")


@login_required
def deleted_list(request):
    """List of soft-deleted transactions with restore buttons."""
    qs = Transaction.objects.filter(user=request.user, is_deleted=True).order_by("-deleted_at", "-id")

    per = request.GET.get("per")
    try:
        per = max(5, min(200, int(per)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx = {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
    }
    return render(request, "deleted.html", ctx)

@login_required
def review_low_conf(request):
    qs = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        ai_suggested_fk__isnull=False,
    ).order_by("-id")

    per = request.GET.get("per")
    try:
        per = max(5, min(200, int(per)))
    except (TypeError, ValueError):
        per = 50
    paginator = Paginator(qs, per)
    page_obj = paginator.get_page(request.GET.get("page"))

    # categories to choose from
    categories = Category.objects.filter(user=request.user).order_by("name")

    return render(request, "review_low.html", {
        "page_obj": page_obj,
        "total": paginator.count,
        "per_value": per,
        "categories": categories,
    })


@login_required
def review_low_apply(request):
    if request.method != "POST":
        return redirect("review_low_conf")

    ids = request.POST.getlist("tx_id")
    cat_id = request.POST.get("category_id")
    if not ids or not cat_id:
        messages.error(request, "Select rows and a category.")
        return redirect("review_low_conf")

    try:
        cat = Category.objects.get(id=int(cat_id), user=request.user)
    except (Category.DoesNotExist, ValueError):
        messages.error(request, "Category not found.")
        return redirect("review_low_conf")

    applied = 0
    for sid in ids:
        try:
            tx = Transaction.objects.get(id=int(sid), user=request.user, is_deleted=False)
        except (Transaction.DoesNotExist, ValueError):
            continue
        tx.category_fk = cat
        tx.category = cat.name
        tx.category_source = "user"
        tx.ai_suggested_fk = None
        tx.ai_confidence = None
        tx.save(update_fields=["category_fk", "category", "category_source", "ai_suggested_fk", "ai_confidence"])
        applied += 1

    messages.success(request, f"Applied {applied} changes.")
    return redirect("review_low_conf")

@login_required
def review_ai_recent(request):
    qs = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        category_source="ai",
    ).order_by("-ai_updated_at", "-id")

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


def _month_key(val):
    """
    Normalize TruncMonth results across DBs to a date(YYYY-MM-01).
    - If val is datetime -> return val.date().replace(day=1)
    - If val is date     -> return val.replace(day=1)
    - Else               -> return None
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        d = val.date()
        return d.replace(day=1)
    if isinstance(val, date):
        return val.replace(day=1)
    return None


@login_required
def overview(request):
    """
    Overview page:
      - BalanceSnapshot add/update
      - Total manual balances (sum of MoneySource.current_balance)
      - Income vs Spending per month (Chart.js)
      - Net by month table
      - Spending per category per month (Chart.js, single-series toggle)
    """

    # ---------- 1) Handle BalanceSnapshot POST (modal) ----------
    if request.method == "POST" and request.POST.get("form") == "balance":
        raw_amount = (request.POST.get("amount") or "").strip().replace(",", ".")
        raw_ts     = (request.POST.get("timestamp") or "").strip()
        note       = (request.POST.get("note") or "").strip()

        try:
            amount = Decimal(raw_amount)
        except (InvalidOperation, TypeError):
            messages.error(request, "Enter a valid number for balance.")
            return redirect("overview")

        try:
            ts = datetime.strptime(raw_ts, "%Y-%m-%dT%H:%M")
            ts = timezone.make_aware(ts, timezone.get_current_timezone())
        except Exception:
            ts = timezone.now()

        latest = BalanceSnapshot.objects.filter(user=request.user).order_by("-timestamp").first()
        if latest:
            latest.amount = amount
            latest.timestamp = ts
            latest.note = note[:180]
            latest.save(update_fields=["amount", "timestamp", "note"])
            messages.success(request, "Balance snapshot updated.")
        else:
            BalanceSnapshot.objects.create(
                user=request.user,
                amount=amount,
                currency="EUR",
                timestamp=ts,
                note=note[:180],
            )
            messages.success(request, "Balance snapshot added.")

        return redirect("overview")

    # ---------- 2) Total manual balances across all accounts ----------
    total_accounts_balance = (
        MoneySource.objects
        .filter(user=request.user, is_active=True, current_balance__isnull=False)
        .aggregate(total=Sum("current_balance"))["total"]
    ) or 0

    # Active accounts for this user (show even if balance isn't set yet)
    accounts_with_balances = (
        MoneySource.objects
        .filter(user=request.user, is_active=True)
        .order_by("type", "name")
    )

    # ---------- 3) Income vs Spending per month ----------
    qs = (Transaction.objects
          .filter(user=request.user, is_deleted=False)
          .annotate(month=TruncMonth("date")))

    by_month = qs.values("month", "in_out").annotate(total=Sum("amount"))

    # Collect normalized months present
    months_set = set()
    for row in by_month:
        mk = _month_key(row["month"])
        if mk:
            months_set.add(mk)

    months = sorted(months_set)  # list of date(YYYY-MM-01)
    labels = [m.strftime("%Y-%m") for m in months]

    totals_in = {m: Decimal("0") for m in months}
    totals_out = {m: Decimal("0") for m in months}

    for row in by_month:
        mk = _month_key(row["month"])
        if not mk:
            continue
        amt = row["total"] or Decimal("0")
        if row["in_out"] == Transaction.IN:
            totals_in[mk] += amt
        else:
            totals_out[mk] += amt

    income_series   = [float(totals_in[m]) for m in months]
    spending_series = [float(totals_out[m]) for m in months]

    # ---------- 4) Net by month table ----------
    net_rows = [{"month": m.strftime("%Y-%m"), "net": float(totals_in[m] - totals_out[m])} for m in months]

    # ---------- 5) Spending per category per month (spending only) ----------
    qs_cat = (Transaction.objects
              .filter(user=request.user, is_deleted=False, in_out=Transaction.OUT, category_fk__isnull=False)
              .annotate(month=TruncMonth("date"))
              .values("month", "category_fk__name")
              .annotate(total=Sum("amount")))

    cat_months_set = set()
    cat_names_set = set()
    for row in qs_cat:
        mk = _month_key(row["month"])
        if mk:
            cat_months_set.add(mk)
        cname = row["category_fk__name"]
        if cname:
            cat_names_set.add(cname)

    cat_months = sorted(set(months) | cat_months_set)
    cat_labels = [m.strftime("%Y-%m") for m in cat_months]
    cat_names = sorted(cat_names_set)

    data_map = defaultdict(lambda: {m: Decimal("0") for m in cat_months})
    for row in qs_cat:
        mk = _month_key(row["month"])
        cname = row["category_fk__name"]
        if not mk or not cname:
            continue
        data_map[cname][mk] += (row["total"] or Decimal("0"))

    series_by_cat = {cname: [float(data_map[cname][m]) for m in cat_months] for cname in cat_names}

    # ---------- 6) Balance snapshot chart helpers (placeholder single point) ----------
    latest_snap = BalanceSnapshot.objects.filter(user=request.user).order_by("-timestamp").first()
    balance_labels_json = "[]"
    balance_values_json = "[]"
    if latest_snap:
        balance_labels_json = json.dumps([latest_snap.timestamp.strftime("%Y-%m-%d %H:%M")])
        balance_values_json = json.dumps([float(latest_snap.amount)])

    now_val = timezone.localtime().strftime("%Y-%m-%dT%H:%M")

    # ---------- 7) Context ----------
    ctx = {
        "latest_snap": latest_snap,
        "balance_labels_json": balance_labels_json,
        "balance_values_json": balance_values_json,
        "now_val": now_val,

        "labels_json": json.dumps(labels),
        "income_json": json.dumps(income_series),
        "spending_json": json.dumps(spending_series),

        "net_rows": net_rows,

        "cat_month_labels_json": json.dumps(cat_labels),
        "series_by_cat_json": json.dumps(series_by_cat),
        "cat_names": cat_names,

        "total_accounts_balance": float(total_accounts_balance),
    }

    return render(request, "overview.html", ctx)

@login_required
def profile(request):
    """
    Profile page:
      - Lists active accounts
      - Lets user add/update/delete accounts (if you already wired forms/buttons)
      - Always supplies total_accounts_balance for the template
    """
    # Handle simple POST actions (optional; keep your existing handlers if you have them)
    action = request.POST.get("action") if request.method == "POST" else None
    if action == "add_account":
        name = (request.POST.get("name") or "").strip() or "New account"
        atype = (request.POST.get("type") or "bank").strip()
        MoneySource.objects.get_or_create(user=request.user, name=name, defaults={"type": atype})
        messages.success(request, f"Account “{name}” added.")
        return redirect("profile")

    if action == "update_account":
        acc_id = request.POST.get("id")
        acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)
        acc.name = (request.POST.get("name") or acc.name).strip() or acc.name
        new_type = (request.POST.get("type") or acc.type).strip()
        if new_type in dict(MoneySource.TYPE_CHOICES):
            acc.type = new_type
        # Balance update (optional)
        bal = request.POST.get("current_balance")
        if bal not in (None, ""):
            try:
                from decimal import Decimal
                acc.current_balance = Decimal(str(bal).replace(",", "."))
            except Exception:
                messages.error(request, "Invalid balance value; not saved.")
        acc.save()
        messages.success(request, "Account updated.")
        return redirect("profile")

    if action == "delete_account":
        acc_id = request.POST.get("id")
        acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)
        acc.is_active = False  # soft delete
        acc.save(update_fields=["is_active"])
        messages.success(request, f"Account “{acc.name}” archived.")
        return redirect("profile")

    # ---- GET: build page ----
    accounts = MoneySource.objects.filter(user=request.user, is_active=True).order_by("type", "name")

    # Compute total_accounts_balance SAFELY (always defined)
    total_accounts_balance = (
        accounts.aggregate(total=Sum("current_balance"))["total"] or 0
    )

    ctx = {
        "accounts": accounts,
        "total_accounts_balance": float(total_accounts_balance),  # used by your template
        # add any other context keys your template expects...
    }
    return render(request, "profile.html", ctx)
