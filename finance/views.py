from django.http import HttpResponse
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction as dbtx
from django.db.models import Q, Sum, Case, When, DecimalField, F
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
import csv, io, os, json, re, hashlib
import pandas as pd
from openai import OpenAI
from datetime import datetime, date as _date
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
import json

from .models import (
    Transaction,
    Category,
    BalanceSnapshot,
    MoneySource,
)

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

AUTO_APPLY_THRESHOLD   = 0.80  # >= this → apply directly
AUTO_CHANGE_THRESHOLD  = 0.90  # when changing an existing AI/rule category
BATCH_SIZE             = 50

# --- Tunables at the top of views.py (near your other constants) ---
EXAMPLE_LOOKBACK_MONTHS = 12       # only learn from the last N months of edits
EXAMPLES_TOTAL_CAP       = 48      # overall example cap per batch
EXAMPLES_PER_CATEGORY    = 4       # soft cap per category to ensure diversity
EXAMPLES_MIN_USER        = 1       # always prefer user-labeled where possible


DEFAULT_CATEGORIES = [
    "Cash","Dining","Fitness & Health","Groceries","Shopping","Crypto","Utilities","Other"
]

# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------

def env_check(request):
    ok = bool(os.getenv("OPENAI_API_KEY"))
    return HttpResponse("OPENAI_API_KEY loaded: " + ("YES" if ok else "NO"))

def home(request):
    return HttpResponse("It works")

def ensure_default_categories(user):
    if not Category.objects.filter(user=user).exists():
        Category.objects.bulk_create([Category(user=user, name=n) for n in DEFAULT_CATEGORIES])

def fingerprint(row, source_id: int) -> str:
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

def _normalize_merchant(name: str) -> str:
    if not name:
        return ""
    s = name.upper()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[#,/ ]?X[- ]?\d+$", "", s)
    s = re.sub(r"\s+\d{3,}$", "", s)
    return s

def _pick_examples(user, limit=EXAMPLES_TOTAL_CAP):
    """
    Returns up to `limit` high-quality, diverse examples:
      - Prefer user > rule > ai sources
      - Look back last EXAMPLE_LOOKBACK_MONTHS months
      - Dedupe by normalized merchant + short text gist
      - Try to balance across categories (soft cap per category)
    """
    from django.utils import timezone
    from datetime import timedelta

    lookback_start = timezone.now().date() - timedelta(days=EXAMPLE_LOOKBACK_MONTHS * 30)

    # Pull a reasonably large pool first
    qs = (
        Transaction.objects
        .filter(user=user, date__gte=lookback_start, category_fk__isnull=False)
        .filter(category_source__in=["user","rule","ai"])
        .select_related("category_fk")
        .order_by("-date","-id")
        .only("merchant","notes","user_note","amount","in_out","category_source","date","category_fk__name")
    )[:1500]

    # Helper: tiny gist to help dedupe near-duplicates
    def gist(t):
        base = f"{(t.notes or '')} {(t.user_note or '')}".strip()
        return (base[:80] if base else "")

    # Partition by source preference
    src_order = ["user", "rule", "ai"]
    pool = []
    for s in src_order:
        pool.extend([t for t in qs if t.category_source == s])

    # Soft per-category cap to maintain diversity
    per_cat_counts = {}
    seen_keys = set()   # dedupe by normalized merchant + gist bucket
    examples = []

    for t in pool:
        cat = t.category_fk.name if t.category_fk else None
        if not cat:
            continue

        # Soft cap per category
        if per_cat_counts.get(cat, 0) >= EXAMPLES_PER_CATEGORY and len(examples) < limit // 2:
            # Allow overflow later if we are under limit overall, but early pass enforces diversity
            continue

        # Deduplicate: merchant normalized + gist bucket
        mnorm = _normalize_merchant(t.merchant or "")
        key = (mnorm, gist(t))
        if key in seen_keys:
            continue

        examples.append({
            "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}"[:240],
            "amount": float(t.amount or 0),
            "in_out": t.in_out or "",
            "category": cat,
            "source": t.category_source,
        })
        seen_keys.add(key)
        per_cat_counts[cat] = per_cat_counts.get(cat, 0) + 1

        if len(examples) >= limit:
            break

    # If we didn't hit `limit` due to per-cat caps, do a second pass without the cap
    if len(examples) < limit:
        for t in pool:
            if len(examples) >= limit:
                break
            cat = t.category_fk.name if t.category_fk else None
            if not cat:
                continue
            mnorm = _normalize_merchant(t.merchant or "")
            key = (mnorm, gist(t))
            if key in seen_keys:
                continue
            examples.append({
                "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}"[:240],
                "amount": float(t.amount or 0),
                "in_out": t.in_out or "",
                "category": cat,
                "source": t.category_source,
            })
            seen_keys.add(key)

    return examples



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

    # Lightly annotate examples in the message so the model understands “don’t change user-labeled”
    user_locked = [e for e in examples if e.get("source") == "user"][:EXAMPLES_MIN_USER]
    example_lines = []
    if user_locked:
        # Show at least one explicit DO-NOT-CHANGE exemplar
        e = user_locked[0]
        example_lines.append(
            f"- (LOCKED) text='{e['text']}', amount={e['amount']}, in_out={e['in_out']} => {e['category']} (source=user)"
        )
    # Then the rest (mixed)
    for e in examples:
        example_lines.append(
            f"- text='{e['text']}', amount={e['amount']}, in_out={e['in_out']} => {e['category']} (source={e.get('source','')})"
        )

    msg = (
        "You are a strict finance transaction categorizer.\n"
        "Rules:\n"
        "1) Choose exactly ONE category from the provided list. Do NOT invent categories.\n"
        "2) If current_category_source == 'user', RETURN THE SAME category (do NOT change it).\n"
        "3) Use amount/in_out and text cues (merchant | notes | user_note). Prefer precision over guessing.\n"
        "4) If unsure, choose the most reasonable broad bucket from the list (e.g., 'Other').\n\n"
        f"Allowed categories: {', '.join(cats)}\n\n"
        "My labeled examples (treat these as ground truth; '(LOCKED)' rows demonstrate that user-labeled must not change):\n"
        + "\n".join(example_lines)
    )

    rows_text = "\n".join([
        f"- id={r['id']}, text='{(r.get('text') or '')[:240]}', amount={r.get('amount',0)}, in_out='{r.get('in_out','')}', current_category='{r.get('current_category','')}', current_category_source='{r.get('current_source','')}'"
        for r in rows
    ])

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type":"json_schema","json_schema":{"name":"tx_categorizer","schema":schema}},
        temperature=0,
        messages=[
            {"role":"system","content":"JSON-only finance categorizer. Reply with VALID JSON matching the schema, nothing else."},
            {"role":"user","content": msg + "\n\nRows:\n" + rows_text},
        ],
    )

    # Robust JSON parse
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
            "reason": (r.get("reason") or "")[:500]
        }
    return out



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
    if isinstance(val, _date):
        return val.replace(day=1)
    return None

def _ledger_balance_by_source(user):
    """
    Returns: dict { money_source_id: Decimal(net balance) } computed from transactions
    (income positive, spending negative), excluding soft-deleted.
    """
    qs = (
        Transaction.objects
        .filter(user=user, is_deleted=False)
        .values("money_source_id")
        .annotate(
            net=Sum(
                Case(
                    When(in_out=Transaction.IN, then=F("amount")),
                    When(in_out=Transaction.OUT, then=F("amount") * Decimal("-1")),
                    default=Decimal("0"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )
    )
    return {row["money_source_id"]: (row["net"] or Decimal("0")) for row in qs}

# ---------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------

@login_required
def tx_edit(request, pk):
    tx = get_object_or_404(Transaction, id=pk, user=request.user, is_deleted=False)
    categories = Category.objects.filter(user=request.user).order_by("name")

    if request.method == "POST":
        # form field name is "category_fk"
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
    """
    Add a transaction manually.

    Fields:
      - date (default today)
      - merchant
      - amount (decimal, required)
      - currency (default EUR)
      - in_out (in/out)
      - account (MoneySource)
      - category (Category)
      - notes (optional)
      - user_note (optional)

    Dedupe: uses same account-aware fingerprint as upload (includes money_source_id).
    """
    # Ensure user has at least one account & categories
    sources = list(MoneySource.objects.filter(user=request.user, is_active=True).order_by("name"))
    if not sources:
        primary_src = MoneySource.objects.create(user=request.user, name="Primary account", type="bank", is_active=True)
        sources = [primary_src]
    categories = Category.objects.filter(user=request.user).order_by("name")
    if not categories.exists():
        ensure_default_categories(request.user)
        categories = Category.objects.filter(user=request.user).order_by("name")

    if request.method == "POST":
        # Read fields
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

        # Validate/parse
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

        # Build the fingerprint (date|merchant|amount|currency|in_out|source_id)
        fp = f"{d.isoformat()}|{merchant}|{str(amount)}|{currency}|{in_out}|{src.id}"

        # Skip if duplicate for this user
        if Transaction.objects.filter(user=request.user, fingerprint=fp).exists():
            messages.info(request, "This transaction already exists (duplicate skipped).")
            return redirect(next_url)

        # Create
        tx = Transaction.objects.create(
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

    # GET
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
    """
    Apply many per-row category changes in one go.

    POST:
      - changes_json: JSON object { "<tx_id>": "<cat_id>", ... }
      - next: where to return (include your filters); we’ll add clear_local=1
    """
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

    # Validate all category ids first (per user) to avoid half-applies
    # Build {cat_id: Category}
    cat_ids = set()
    tx_ids = []
    for tx_id, cat_id in mapping.items():
        try:
            tx_ids.append(int(tx_id))
            cat_ids.add(int(cat_id))
        except Exception:
            continue

    cats = {c.id: c for c in Category.objects.filter(user=request.user, id__in=cat_ids)}
    applied = 0

    # Apply
    for tx_id, cat_id in mapping.items():
        try:
            tx_id = int(tx_id)
            cat_id = int(cat_id)
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

    # Ask client to clear its local draft
    sep = "&" if "?" in next_url else "?"
    return redirect(f"{next_url}{sep}clear_local=1")

@login_required
def uncategorized(request):
    """
    List transactions missing a category (or explicitly 'Other'),
    excluding soft-deleted rows.
    """
    qs = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False)
        .filter(
            Q(category_fk__isnull=True) |
            Q(category__isnull=True) |
            Q(category="") |
            Q(category="Other")
        )
        .order_by("-date", "-id")
    )

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

            # ---- Quick badges for next steps (computed AFTER insert) ----
            uncat_count = (Transaction.objects
                           .filter(user=request.user, is_deleted=False)
                           .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category="") | Q(category="Other"))
                           .count())
            low_conf_count = Transaction.objects.filter(
                user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
            ).count()

            # messages + redirect (PRG)
            link_uncat = f'<a href="/uncategorized/">Uncategorized ({uncat_count})</a>'
            link_low   = f'<a href="/review/low/">Low-confidence ({low_conf_count})</a>'

            if added == 0:
                messages.info(
                    request,
                    (
                        f'Imported into: {import_src.name}. Parsed {parsed_count}, skipped {skipped_count}. '
                        f'No new transactions. Duplicates in DB: {len(existing_set)} '
                        f'(blocked by deleted: {blocked_deleted}), duplicates in file: {duplicates_file}. '
                        f'Next: {link_uncat} · {link_low}'
                    ),
                    extra_tags="safe"
                )
            else:
                messages.success(
                    request,
                    (
                        f'Imported into: {import_src.name}. Parsed {parsed_count}, skipped {skipped_count}. '
                        f'Added {added} new transaction{"s" if added != 1 else ""}. '
                        f'(DB dups: {len(existing_set)}, file dups: {duplicates_file}, blocked by deleted: {blocked_deleted}.) '
                        f'Next: {link_uncat} · {link_low}'
                    ),
                    extra_tags="safe"
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

# ----------------------------- Categories CRUD -----------------------------

@login_required
def category_list(request):
    # Seed defaults once per user
    if not Category.objects.filter(user=request.user).exists():
        Category.objects.bulk_create([Category(user=request.user, name=n) for n in DEFAULT_CATEGORIES])

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
    # if called with GET, just go back to list
    return redirect("category_list")


@login_required
def ai_full_categorize(request):
    """
    Modes:
      - mode=uncat (default): only uncategorized / 'Other'
      - mode=ai:     only previously AI-labeled
      - mode=all:    everything EXCEPT user-labeled
    Behavior:
      - If row has no category: apply when confidence >= AUTO_APPLY_THRESHOLD, else park (ai_suggested_fk).
      - If row has AI/rule category and AI proposes a DIFFERENT one:
          * if confidence >= AUTO_CHANGE_THRESHOLD -> auto-change
          * elif confidence >= AUTO_APPLY_THRESHOLD -> park as change suggestion
          * else ignore
    Always excludes is_deleted=True.
    """
    # Seed defaults for the user (once)
    if not Category.objects.filter(user=request.user).exists():
        ensure_default_categories(request.user)

    if not os.getenv("OPENAI_API_KEY"):
        return render(request, "ai_summary.html", {
            "key_present": False, "total_candidates": 0, "applied": 0, "parked": 0,
            "left_for_review": 0,
        })

    mode = request.GET.get("mode", "uncat")
    try:
        hard_limit = int(request.GET.get("limit", "0"))
        hard_limit = max(0, min(2000, hard_limit))  # safety cap
    except ValueError:
        hard_limit = 0

    # ---------- Candidate pool (EXCLUDE deleted) ----------
    if mode == "uncat":
        base = (Transaction.objects
                .filter(user=request.user, is_deleted=False)
                .filter(Q(category_fk__isnull=True) | Q(category__isnull=True) | Q(category="") | Q(category="Other")))
    elif mode == "ai":
        base = Transaction.objects.filter(user=request.user, is_deleted=False, category_source="ai")
    elif mode == "all":
        base = Transaction.objects.filter(user=request.user, is_deleted=False).exclude(category_source="user")
    else:
        base = Transaction.objects.none()

    qs = base.order_by("date", "id").select_related("category_fk")
    if hard_limit:
        qs = qs[:hard_limit]

    total_candidates = qs.count()
    if total_candidates == 0:
        return render(request, "ai_summary.html", {
            "key_present": True, "total_candidates": 0, "applied": 0, "parked": 0,
            "left_for_review": Transaction.objects.filter(
                user=request.user, is_deleted=False, ai_suggested_fk__isnull=False
            ).count(),
        })

    cats_map = {c.name: c for c in Category.objects.filter(user=request.user)}
    cats_list = sorted(cats_map.keys())

    # Build request rows upfront
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

    # Process in batches, refreshing examples per batch (learn from new edits)
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

            # Never override user-labeled
            if t.category_source == "user":
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

            current_name = (t.category_fk.name if t.category_fk else (t.category or "")).strip() or ""

            if not current_name or current_name == "Other":
                if conf >= AUTO_APPLY_THRESHOLD:
                    t.category_fk = suggested_fk
                    t.category = suggested_fk.name
                    t.category_source = "ai"
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.ai_suggested_fk = None
                    t.save(update_fields=[
                        "category_fk","category","category_source","ai_confidence","ai_reason","ai_suggested_fk","updated_at"
                    ])
                    applied += 1
                else:
                    t.ai_suggested_fk = suggested_fk
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.save(update_fields=["ai_suggested_fk","ai_confidence","ai_reason","updated_at"])
                    parked += 1
                continue

            # Already has AI/rule category
            if suggested_name == current_name:
                # refresh confidence/reason if AI
                if t.category_source == "ai":
                    t.ai_confidence = conf
                    t.ai_reason = reason
                    t.ai_suggested_fk = None
                    t.save(update_fields=["ai_confidence","ai_reason","ai_suggested_fk","updated_at"])
                continue

            # Different suggestion
            if conf >= AUTO_CHANGE_THRESHOLD:
                t.category_fk = suggested_fk
                t.category = suggested_fk.name
                t.category_source = "ai"
                t.ai_confidence = conf
                t.ai_reason = reason
                t.ai_suggested_fk = None
                t.save(update_fields=[
                    "category_fk","category","category_source","ai_confidence","ai_reason","ai_suggested_fk","updated_at"
                ])
                applied += 1
            elif conf >= AUTO_APPLY_THRESHOLD:
                t.ai_suggested_fk = suggested_fk
                t.ai_confidence = conf
                t.ai_reason = reason
                t.save(update_fields=["ai_suggested_fk","ai_confidence","ai_reason","updated_at"])
                parked += 1
            else:
                # ignore
                pass

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
    cat_ids = request.POST.getlist("cat_id")  # one per row, same order as tx_id

    if not ids or not cat_ids or len(ids) != len(cat_ids):
        messages.error(request, "Select categories for the rows you want to change.")
        return redirect("review_low_conf")

    applied = 0
    for sid, scatid in zip(ids, cat_ids):
        try:
            tx = Transaction.objects.get(id=int(sid), user=request.user, is_deleted=False)
        except (Transaction.DoesNotExist, ValueError):
            continue
        try:
            cat = Category.objects.get(id=int(scatid), user=request.user)
        except (Category.DoesNotExist, ValueError):
            continue

        tx.category_fk = cat
        tx.category = cat.name
        tx.category_source = "user"
        tx.ai_suggested_fk = None
        tx.ai_confidence = None
        tx.save(update_fields=[
            "category_fk", "category", "category_source", "ai_suggested_fk", "ai_confidence"
        ])
        applied += 1

    messages.success(request, f"Applied {applied} changes.")
    return redirect("review_low_conf")


@login_required
def review_ai_recent(request):
    # Order by last mutation time you already track
    qs = Transaction.objects.filter(
        user=request.user,
        is_deleted=False,
        category_source="ai",
    ).order_by("-updated_at", "-id")

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
def overview(request):
    """
    Overview:
      - Same as before (totals, income vs spending, net, category chart)
      - Merchant breakdown per category+month
      - NEW: Month bounds mapping for quick "Review" links
    """
    # ----- BalanceSnapshot POST (unchanged) -----
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
                user=request.user, amount=amount, currency="EUR", timestamp=ts, note=note[:180]
            )
            messages.success(request, "Balance snapshot added.")
        return redirect("overview")

    # ----- Effective account balances -----
    accounts = list(MoneySource.objects.filter(user=request.user).order_by("type", "name"))

    tx_base = Transaction.objects.filter(user=request.user, is_deleted=False)

    tx_sums = (
        tx_base
        .values("money_source_id", "in_out")
        .annotate(total=Sum("amount"))
    )
    from collections import defaultdict
    ledger_map = defaultdict(lambda: Decimal("0"))
    for row in tx_sums:
        ms_id = row["money_source_id"]
        amt = row["total"] or Decimal("0")
        if row["in_out"] == Transaction.IN:
            ledger_map[ms_id] += amt
        else:
            ledger_map[ms_id] -= amt

    total_effective = Decimal("0")
    for acc in accounts:
        ledger_val = ledger_map.get(acc.id, Decimal("0"))
        effective = getattr(acc, "manual_balance", None)
        if effective is None:
            effective = ledger_val
        acc.effective_balance = effective
        total_effective += effective if acc.is_active else Decimal("0")

    # ----- Income vs Spending per month -----
    qs_month = tx_base.annotate(month=TruncMonth("date"))
    by_month = qs_month.values("month", "in_out").annotate(total=Sum("amount"))

    def _month_key(val):
        if val is None:
            return None
        if isinstance(val, datetime):
            d = val.date()
            return _date(d.year, d.month, 1)
        if isinstance(val, _date):
            return _date(val.year, val.month, 1)
        return None

    months_set = set()
    for row in by_month:
        mk = _month_key(row["month"])
        if mk: months_set.add(mk)
    months = sorted(months_set)
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
    net_rows = [{"month": m.strftime("%Y-%m"), "net": float(totals_in[m] - totals_out[m])} for m in months]

    # ----- Category chart (spending only; FK-only) -----
    qs_cat = (
        tx_base
        .filter(in_out=Transaction.OUT, category_fk__isnull=False)
        .annotate(month=TruncMonth("date"))
        .values("month", "category_fk__name")
        .annotate(total=Sum("amount"))
    )

    cat_months_set, cat_names_set = set(), set()
    for row in qs_cat:
        mk = _month_key(row["month"])
        if mk: cat_months_set.add(mk)
        cname = row["category_fk__name"]
        if cname: cat_names_set.add(cname)

    cat_months = sorted(set(months) | cat_months_set)
    cat_labels = [m.strftime("%Y-%m") for m in cat_months]
    cat_names = sorted(cat_names_set)

    from collections import defaultdict as _dd
    data_map = _dd(lambda: {m: Decimal("0") for m in cat_months})
    for row in qs_cat:
        mk = _month_key(row["month"]); cname = row["category_fk__name"]
        if mk and cname:
            data_map[cname][mk] += (row["total"] or Decimal("0"))
    series_by_cat = {cname: [float(data_map[cname][m]) for m in cat_months] for cname in cat_names}

    # ----- Merchant breakdown per category per month -----
    from django.db.models import Count
    qs_merchant = (
        tx_base
        .filter(in_out=Transaction.OUT, category_fk__isnull=False)
        .annotate(month=TruncMonth("date"))
        .values("month", "category_fk__name", "merchant")
        .annotate(total=Sum("amount"), tx_count=Count("id"))
    )

    breakdown_by_cat_month = {}
    for row in qs_merchant:
        mk = _month_key(row["month"])
        if not mk:
            continue
        month_key = mk.strftime("%Y-%m")
        cname = row["category_fk__name"] or "Other"
        merchant = (row["merchant"] or "").strip() or "—"
        total = row["total"] or Decimal("0")
        cnt = int(row["tx_count"] or 0)
        avg = (total / cnt) if cnt else Decimal("0")

        breakdown_by_cat_month.setdefault(cname, {}).setdefault(month_key, []).append({
            "merchant": merchant[:80],
            "total": float(total),
            "count": cnt,
            "avg": float(avg),
        })

    for cname, per_month in breakdown_by_cat_month.items():
        for m in per_month:
            per_month[m] = sorted(per_month[m], key=lambda x: (-x["total"], x["merchant"]))[:12]

    # ----- Balance timeline anchor -----
    latest_snap = BalanceSnapshot.objects.filter(user=request.user).order_by("-timestamp").first()
    if latest_snap:
        lt = timezone.localtime(latest_snap.timestamp)
        anchor_month = _date(lt.year, lt.month, 1)
        anchor_value = Decimal(latest_snap.amount)
    else:
        now = timezone.localtime().date()
        anchor_month = _date(now.year, now.month, 1)
        anchor_value = total_effective

    net_delta = {m: totals_in.get(m, Decimal("0")) - totals_out.get(m, Decimal("0")) for m in months}

    def _add_month(d: _date) -> _date:
        return _date(d.year + 1, 1, 1) if d.month == 12 else _date(d.year, d.month + 1, 1)

    all_months = set(months) | {anchor_month}
    if months:
        start = min(min(months), anchor_month); end = max(max(months), anchor_month)
    else:
        start = end = anchor_month

    seq, cur = [], start
    while cur <= end:
        seq.append(cur); cur = _add_month(cur)
    for m in seq:
        net_delta.setdefault(m, Decimal("0"))

    balances = {}
    idx = seq.index(anchor_month)
    for i in range(idx, len(seq)):
        m = seq[i]
        balances[m] = anchor_value if i == idx else balances[seq[i - 1]] + net_delta[m]
    for i in range(idx, 0, -1):
        curr = seq[i]; prev = seq[i - 1]
        balances[prev] = balances[curr] - net_delta[curr]

    balance_labels_json = json.dumps([m.strftime("%Y-%m") for m in seq])
    balance_values_json = json.dumps([float(balances[m]) for m in seq])
    now_val = timezone.localtime().strftime("%Y-%m-%dT%H:%M")

    # ----- NEW: Month bounds (YYYY-MM -> {start, end}) for quick filters -----
    from calendar import monthrange
    month_bounds = {}
    for m in cat_months:
        last_day = monthrange(m.year, m.month)[1]
        month_key = m.strftime("%Y-%m")
        month_bounds[month_key] = {
            "start": f"{m.year:04d}-{m.month:02d}-01",
            "end":   f"{m.year:04d}-{m.month:02d}-{last_day:02d}",
        }

    # ----- Context -----
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

        "breakdown_by_cat_month_json": json.dumps(breakdown_by_cat_month),
        "month_bounds_json": json.dumps(month_bounds),  # NEW
        "total_accounts_balance": float(total_effective),
        "accounts_with_balances": accounts,
    }
    return render(request, "overview.html", ctx)



@login_required
def profile(request):
    """
    Profile page:
      - Lists accounts
      - Handles: add, rename, toggle, setbalance, setdefault
      - Manual balances: MoneySource.manual_balance/manual_currency
      - Supplies type_choices, default_id, total_accounts_balance (effective)
    """
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "add":
            name = (request.POST.get("name") or "").strip() or "New account"
            atype = (request.POST.get("type") or "bank").strip()
            if atype not in dict(MoneySource.TYPE_CHOICES):
                atype = "bank"
            ms, created = MoneySource.objects.get_or_create(
                user=request.user, name=name, defaults={"type": atype, "is_active": True}
            )
            messages.success(request, f'Account “{name}” added.' if created else f'Account “{name}” already exists.')
            return redirect("profile")

        if action == "rename":
            acc_id = request.POST.get("id")
            new_name = (request.POST.get("name") or "").strip()
            acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)
            if new_name:
                exists = MoneySource.objects.filter(user=request.user, name=new_name).exclude(id=acc.id).exists()
                if exists:
                    messages.error(request, f'Another account named “{new_name}” already exists.')
                else:
                    acc.name = new_name
                    acc.save(update_fields=["name", "updated_at"])
                    messages.success(request, "Account renamed.")
            else:
                messages.error(request, "Name cannot be empty.")
            return redirect("profile")

        if action == "toggle":
            acc_id = request.POST.get("id")
            acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)
            acc.is_active = not acc.is_active
            acc.save(update_fields=["is_active", "updated_at"])
            messages.success(request, f'Account “{acc.name}” {"activated" if acc.is_active else "deactivated"}.')
            return redirect("profile")

        if action == "setbalance":
            # This now updates manual_balance/manual_currency
            acc_id = request.POST.get("id")
            amount_raw = (request.POST.get("amount") or "").strip().replace(",", ".")
            acc = get_object_or_404(MoneySource, id=acc_id, user=request.user)
            try:
                acc.manual_balance = Decimal(amount_raw) if amount_raw != "" else None
                # keep a timestamp using the existing field
                acc.balance_updated_at = timezone.now() if acc.manual_balance is not None else None
                # currency: stick to EUR for MVP; if you add a <select>, read it here
                acc.manual_currency = "EUR"
                acc.save(update_fields=["manual_balance", "manual_currency", "balance_updated_at", "updated_at"])
                messages.success(request, f'Manual balance saved for “{acc.name}”.')
            except (InvalidOperation, TypeError):
                messages.error(request, "Invalid balance value.")
            return redirect("profile")

        if action == "setdefault":
            acc_id = request.POST.get("id")
            try:
                acc = MoneySource.objects.get(id=int(acc_id), user=request.user, is_active=True)
                request.session["default_src_id"] = acc.id
                messages.success(request, f'“{acc.name}” set as default import account.')
            except (MoneySource.DoesNotExist, ValueError):
                messages.error(request, "Account not found or inactive.")
            return redirect("profile")

        messages.info(request, "No changes made.")
        return redirect("profile")

    # ----- GET -----
    accounts = MoneySource.objects.filter(user=request.user).order_by("type", "name")

    # Effective per-account balance: manual if present, else ledger (sum of tx)
    # Build ledger sums per account in a single query
    tx_sums = (
        Transaction.objects
        .filter(user=request.user, is_deleted=False)
        .values("money_source_id", "in_out")
        .annotate(total=Sum("amount"))
    )
    from collections import defaultdict
    ledger_map = defaultdict(lambda: Decimal("0"))
    for row in tx_sums:
        ms_id = row["money_source_id"]
        amt = row["total"] or Decimal("0")
        if row["in_out"] == Transaction.IN:
            ledger_map[ms_id] += amt
        else:
            ledger_map[ms_id] -= amt

    # Compute total effective balance across active accounts
    total_effective = Decimal("0")
    for acc in accounts:
        ledger_val = ledger_map.get(acc.id, Decimal("0"))
        effective = acc.manual_balance if acc.manual_balance is not None else ledger_val
        # attach for template usage
        acc.effective_balance = effective
        total_effective += effective if acc.is_active else Decimal("0")

    ctx = {
        "accounts": accounts,
        "total_accounts_balance": float(total_effective),
        "type_choices": MoneySource.TYPE_CHOICES,
        "default_id": request.session.get("default_src_id"),
    }
    return render(request, "profile.html", ctx)


@login_required
def statistics(request):
    """
    Statistics dashboard (no savings rate):
      - Lifetime stats (totals, averages, best/worst, largest purchase, merchant stats, coverage)
      - Category share (pie) with month/range picker (defaults to last *full* month)
      - Weekday mix (last 90 days)
      - Per-category totals, #tx, avg/tx, avg/month for the selected period
    """
    # Local imports to keep this a clean drop-in
    from calendar import monthrange
    from datetime import timedelta
    import re
    import json
    from decimal import Decimal
    from datetime import datetime, date as _date
    from django.db.models import Sum, Count
    from django.db.models.functions import TruncMonth
    from django.utils import timezone

    from .models import Transaction

    user = request.user
    today = timezone.localtime().date()
    base = Transaction.objects.filter(user=user, is_deleted=False)

    # ---------- Lifetime stats ----------
    total_in = base.filter(in_out=Transaction.IN).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    total_out = base.filter(in_out=Transaction.OUT).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    lifetime_net = total_in - total_out
    total_tx = base.count()

    # Monthly aggregates for averages + best/worst month (by net)
    by_month = (
        base.annotate(m=TruncMonth("date"))
            .values("m", "in_out")
            .annotate(total=Sum("amount"))
    )

    def _mk(val):
        if isinstance(val, datetime):
            d = val.date()
            return _date(d.year, d.month, 1)
        if isinstance(val, _date):
            return _date(val.year, val.month, 1)
        return None

    month_map_in, month_map_out = {}, {}
    months_set = set()
    for r in by_month:
        mk = _mk(r["m"])
        if not mk:
            continue
        months_set.add(mk)
        if r["in_out"] == Transaction.IN:
            month_map_in[mk] = (month_map_in.get(mk, Decimal("0")) + (r["total"] or Decimal("0")))
        else:
            month_map_out[mk] = (month_map_out.get(mk, Decimal("0")) + (r["total"] or Decimal("0")))

    months_sorted = sorted(months_set)
    months_count = len(months_sorted) or 1
    avg_month_in = sum(month_map_in.get(m, Decimal("0")) for m in months_sorted) / months_count
    avg_month_out = sum(month_map_out.get(m, Decimal("0")) for m in months_sorted) / months_count

    month_nets = []
    for m in months_sorted:
        net = (month_map_in.get(m, Decimal("0")) - month_map_out.get(m, Decimal("0")))
        month_nets.append((m, net))
    best_month = max(month_nets, key=lambda x: x[1]) if month_nets else None
    worst_month = min(month_nets, key=lambda x: x[1]) if month_nets else None

    largest_tx = (
        base.filter(in_out=Transaction.OUT)
            .order_by("-amount")
            .values("id", "date", "merchant", "amount", "currency")
            .first()
    )

    distinct_merchants = base.exclude(merchant="").values("merchant").distinct().count()
    most_freq = (
        base.exclude(merchant="")
            .values("merchant")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")
            .first()
    )

    total_categorizable = base.count()
    categorized = base.filter(category_fk__isnull=False).count()
    coverage_pct = (categorized / total_categorizable * 100.0) if total_categorizable else 0.0

    # ---------- Category share (pie) with month/range picker ----------
    all_months = sorted({_mk(x) for x in base.values_list("date", flat=True) if _mk(x) is not None})

    def key_from_date(d: _date) -> str:
        return d.strftime("%Y-%m")

    def month_start_from_key(k: str) -> _date:
        y, m = map(int, k.split("-"))
        return _date(y, m, 1)

    def month_end_from_key(k: str) -> _date:
        y, m = map(int, k.split("-"))
        return _date(y, m, monthrange(y, m)[1])

    this_month_key = key_from_date(_date(today.year, today.month, 1))
    months_keys = [key_from_date(m) for m in all_months]

    # default range = last full month
    default_end_key = None
    for k in reversed(months_keys):
        if k != this_month_key:
            default_end_key = k
            break
    if not default_end_key and months_keys:
        default_end_key = months_keys[-1]
    default_start_key = default_end_key

    start_key = (request.GET.get("start_month") or default_start_key)
    end_key = (request.GET.get("end_month") or default_end_key)

    def is_valid_key(k):
        return isinstance(k, str) and re.match(r"^\d{4}-\d{2}$", k)
    if not is_valid_key(start_key):
        start_key = default_start_key
    if not is_valid_key(end_key):
        end_key = default_end_key

    start_date = month_start_from_key(start_key)
    end_date = month_end_from_key(end_key)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
        start_key, end_key = end_key, start_key

    # Inclusive number of months in the selected range (for Avg/Month)
    months_in_range = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    if months_in_range < 1:
        months_in_range = 1

    # One query to get totals and counts per category in the selected period (spending only; FK-only)
    per_cat = (
        base.filter(
            in_out=Transaction.OUT,
            category_fk__isnull=False,
            date__gte=start_date,
            date__lte=end_date,
        )
        .values("category_fk", "category_fk__name")
        .annotate(total=Sum("amount"), cnt=Count("id"))
        .order_by("-total")
    )

    share_total = sum((r["total"] or Decimal("0")) for r in per_cat) or Decimal("0")
    cat_labels = [r["category_fk__name"] for r in per_cat]
    cat_values = [
        float((r["total"] or Decimal("0")) / share_total) if share_total else 0.0 for r in per_cat
    ]

    # Build rows for the summary table (includes Avg/Month)
    cat_summary_rows = []
    for r in per_cat:
        total = r["total"] or Decimal("0")
        cnt = int(r["cnt"] or 0)
        avg = (total / cnt) if cnt else Decimal("0")
        avg_month = (total / months_in_range) if months_in_range else Decimal("0")
        cat_summary_rows.append(
            {
                "cat_id": r["category_fk"],
                "cat_name": r["category_fk__name"],
                "total": float(total),
                "count": cnt,
                "avg": float(avg),
                "avg_month": float(avg_month),
            }
        )

    # ---------- Weekday mix (last 90 days, spending only) ----------
    last90_start = today - timedelta(days=89)
    wday_totals = [Decimal("0")] * 7  # Mon..Sun
    qs_wday = base.filter(in_out=Transaction.OUT, date__gte=last90_start, date__lte=today).only("date", "amount")
    for t in qs_wday:
        wday_totals[t.date.weekday()] += (t.amount or Decimal("0"))
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_values = [float(x) for x in wday_totals]

    ctx = {
        # Lifetime cards
        "total_in": float(total_in),
        "total_out": float(total_out),
        "lifetime_net": float(lifetime_net),
        "avg_month_in": float(avg_month_in),
        "avg_month_out": float(avg_month_out),
        "best_month": best_month[0].strftime("%Y-%m") if best_month else None,
        "best_month_net": float(best_month[1]) if best_month else None,
        "worst_month": worst_month[0].strftime("%Y-%m") if worst_month else None,
        "worst_month_net": float(worst_month[1]) if worst_month else None,
        "largest_tx": largest_tx,
        "total_tx": total_tx,
        "distinct_merchants": distinct_merchants,
        "most_freq_merchant": most_freq["merchant"] if most_freq else None,
        "most_freq_merchant_cnt": int(most_freq["cnt"]) if most_freq else None,
        "coverage_pct": round(coverage_pct, 1),

        # Month picker
        "available_month_keys": months_keys,
        "start_key": start_key,
        "end_key": end_key,

        # Category share pie
        "cat_labels_json": json.dumps(cat_labels),
        "cat_values_json": json.dumps(cat_values),
        "share_note": f"Share of total spending from {start_key} to {end_key}.",

        # Per-category summary (includes Avg/Month)
        "cat_summary_rows": cat_summary_rows,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),

        # Weekday mix
        "weekday_labels_json": json.dumps(weekday_labels),
        "weekday_values_json": json.dumps(weekday_values),

        # For other links
        "last90_from": last90_start.strftime("%Y-%m-%d"),
        "last90_to": today.strftime("%Y-%m-%d"),
    }
    return render(request, "statistics.html", ctx)
