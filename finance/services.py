# finance/services.py
import os, json, re
from decimal import Decimal
from datetime import date as _date
from collections import defaultdict
from calendar import monthrange
from django.db.models import Sum
from openai import OpenAI, BadRequestError
from django.utils import timezone
from django.conf import settings
from .models import Transaction, Category, SavingsGoal, MoneySource
from .investments import current_investment_balance
from .utils import _normalize_merchant, default_category_name

EXAMPLES_TOTAL_CAP = 60
EXAMPLES_PER_CATEGORY = 5
EXAMPLES_MIN_USER = 1
ADVISOR_MODEL = "gpt-4o" # or gpt-4o-mini
ADVISOR_TEMP = 0
EXAMPLE_LOOKBACK_MONTHS = 12

def _pick_examples(user, limit=EXAMPLES_TOTAL_CAP):
    from datetime import timedelta
    lookback_start = timezone.now().date() - timedelta(days=EXAMPLE_LOOKBACK_MONTHS * 30)
    qs = (
        Transaction.objects
        .filter(
            user=user,
            date__gte=lookback_start,
            category_fk__isnull=False,
            is_internal_transfer=False,
        )
        .filter(category_source__in=["user","rule","ai"])
        .select_related("category_fk")
        .order_by("-date","-id")
        .only("merchant","notes","user_note","amount","in_out","category_source","date","category_fk__name")
    )[:1500]

    def gist(t):
        base = f"{(t.notes or '')} {(t.user_note or '')}".strip()
        return (base[:80] if base else "")

    src_order = ["user", "rule", "ai"]
    pool = []
    for s in src_order:
        pool.extend([t for t in qs if t.category_source == s])

    per_cat_counts, seen_keys, examples = {}, set(), []
    for t in pool:
        cat = t.category_fk.name if t.category_fk else None
        if not cat: continue
        if per_cat_counts.get(cat, 0) >= EXAMPLES_PER_CATEGORY and len(examples) < limit // 2:
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
        per_cat_counts[cat] = per_cat_counts.get(cat, 0) + 1
        if len(examples) >= limit:
            break

    if len(examples) < limit:
        for t in pool:
            if len(examples) >= limit: break
            cat = t.category_fk.name if t.category_fk else None
            if not cat: continue
            mnorm = _normalize_merchant(t.merchant or "")
            key = (mnorm, gist(t))
            if key in seen_keys: continue
            examples.append({
                "text": f"{t.merchant} | {t.notes or ''} | {t.user_note or ''}"[:240],
                "amount": float(t.amount or 0),
                "in_out": t.in_out or "",
                "category": cat,
                "source": t.category_source,
            })
            seen_keys.add(key)

    return examples

# What each default category means, so the model does not have to guess from a bare name.
# Custom categories the user adds are sent by name only.
CATEGORY_GUIDE = {
    "Atlyginimas": "salary and wages from an employer (incoming). Not interest, refunds, tax returns or transfers from friends.",
    "Salary": "salary and wages from an employer (incoming). Not interest, refunds, tax returns or transfers from friends.",
    "Individuali veikla": "self-employment: client payments for freelance work, platform payouts (Upwork, Fiverr), and business taxes paid for it (VMI GPM, Sodra VSD/PSD as self-employed).",
    "Individual activity": "self-employment: client payments for freelance work, platform payouts (Upwork, Fiverr), and business taxes paid for it.",
    "Grynieji": "cash withdrawals and deposits at ATMs (bankomatas, ATM, grynųjų išėmimas).",
    "Cash": "cash withdrawals and deposits at ATMs.",
    "Kavinės ir restoranai": "cafes, restaurants, fast food, bars and food delivery (Wolt, Bolt Food).",
    "Dining": "cafes, restaurants, fast food, bars and food delivery (Wolt, Bolt Food).",
    "Sportas ir sveikata": "gyms and sport, pharmacies (Eurovaistinė, Camelia, Benu, Apotheka), doctors, clinics, dentists.",
    "Fitness & Health": "gyms and sport, pharmacies (Eurovaistinė, Camelia, Benu, Apotheka), doctors, clinics, dentists.",
    "Maisto prekės": "grocery stores and supermarkets (Maxima, Rimi, Lidl, Iki, Norfa).",
    "Groceries": "grocery stores and supermarkets (Maxima, Rimi, Lidl, Iki, Norfa).",
    "Pirkiniai": "shopping for goods: clothes, electronics, home and DIY (Senukai, IKEA), online shops (Pigu, AliExpress, Vinted), cosmetics, games bought once.",
    "Shopping": "shopping for goods: clothes, electronics, home and DIY, online shops, cosmetics, games bought once.",
    "Kripto": "buying or selling crypto (Binance, Coinbase, Kraken).",
    "Crypto": "buying or selling crypto (Binance, Coinbase, Kraken).",
    "Komunaliniai": "home bills: electricity, gas, water, heating, internet and phone plans (Ignitis, Elektrum, Telia, Bitė, Tele2).",
    "Utilities": "home bills: electricity, gas, water, heating, internet and phone plans.",
    "Prenumeratos": "recurring digital subscriptions (Spotify, Netflix, YouTube Premium, ChatGPT, Apple/Google services).",
    "Subscriptions": "recurring digital subscriptions (Spotify, Netflix, YouTube Premium, ChatGPT, Apple/Google services).",
    "Transportas": "fuel, taxis and ride hailing (Bolt rides), car sharing, public transport, trains, parking.",
    "Transportation": "fuel, taxis and ride hailing (Bolt rides), car sharing, public transport, trains, parking.",
    "Kita": "anything that fits nowhere else: transfers to or from people, rent paid to a person, bank fees, insurance, interest, tax refunds, top-ups between own accounts.",
    "Other": "anything that fits nowhere else: transfers to or from people, rent paid to a person, bank fees, insurance, interest, tax refunds, top-ups between own accounts.",
}

MERCHANT_HISTORY_LOOKBACK = 3000  # most recent categorized rows scanned for same-merchant history

_NOISE_PREFIX = re.compile(
    r"^(KORTELĖS OPERACIJA|KORTELES OPERACIJA|PIRKINYS|MOKĖJIMAS|MOKEJIMAS|CARD PAYMENT|POS|PAYPAL \*)[:\s]*"
)
_CARD_MASK = re.compile(r"\d{0,6}\*{2,}\d*")
_DATE = re.compile(r"\b\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\b|\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}\b|\b\d{1,2}:\d{2}(:\d{2})?\b")
_LEGAL = {"UAB", "AB", "MB", "IĮ", "II", "VŠĮ", "VSI", "LT", "LIETUVA", "LIETUVOS", "SIA", "AS", "OU", "LTD", "INC"}


_PERSONAL = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,4})?\b"), "[IBAN]"),
    (re.compile(r"(?:\+370|\b8)[ -]?6\d{2}[ -]?\d{5}\b"), "[phone]"),
    (re.compile(r"\b[3-6]\d{10}\b"), "[personal code]"),  # Lithuanian asmens kodas
    (re.compile(r"\b\d{12,}\b"), "[number]"),
]


def redact_personal(text):
    """Mask personal identifiers bank descriptions carry (personal codes, IBANs, emails, phones)
    before text is sent to the AI. Merchant and counterparty names stay: they decide the category."""
    for pattern, label in _PERSONAL:
        text = pattern.sub(label, text or "")
    return text


def _merchant_key(raw):
    """Matching key for the AI's memory of past categories.

    Strips what changes between rows of the same merchant in bank exports (card masks,
    dates, 'PIRKINYS' prefixes, terminal numbers, legal forms). Returns (full key, brand word).
    Deliberately separate from utils._normalize_merchant, which feeds import fingerprints.
    """
    s = (raw or "").upper()
    s = _NOISE_PREFIX.sub("", s.strip())
    s = _CARD_MASK.sub(" ", s)
    s = _DATE.sub(" ", s)
    s = re.sub(r"[^\wĄČĘĖĮŠŲŪŽ]+", " ", s)
    tokens = [t for t in s.split() if not t.isdigit() and t not in _LEGAL]
    if not tokens:
        return "", ""
    brand = next((t for t in tokens if len(t) >= 3), tokens[0])
    return " ".join(tokens[:4]), brand


def _merchant_history(user, rows, exclude_ids=()):
    """Past categories for the merchants in `rows`, user corrections first.

    Returns {row merchant: ("same" | "similar", [(category, source, count), ...])}.
    "same" = same merchant after cleaning; "similar" = only the brand word matches (a weaker hint).
    """
    wanted = {}
    for r in rows:
        merchant = r.get("merchant") or (r.get("text") or "").split(" | ")[0]
        full, brand = _merchant_key(merchant)
        if full:
            wanted[merchant] = (full, brand)
    if not wanted:
        return {}
    fulls = {full for full, _ in wanted.values()}
    brands = {brand for _, brand in wanted.values()}

    by_full = defaultdict(lambda: defaultdict(int))
    by_brand = defaultdict(lambda: defaultdict(int))
    qs = (
        Transaction.objects
        .filter(user=user, is_deleted=False, is_internal_transfer=False, category_fk__isnull=False)
        .filter(category_source__in=["user", "rule", "ai"])
        .exclude(id__in=list(exclude_ids))  # evaluation: never let a row see its own label
        .order_by("-date", "-id")
        .values_list("merchant", "category_fk__name", "category_source")[:MERCHANT_HISTORY_LOOKBACK]
    )
    for merchant, category, source in qs:
        full, brand = _merchant_key(merchant)
        if full in fulls:
            by_full[full][(category, source)] += 1
        if brand in brands:
            by_brand[brand][(category, source)] += 1

    source_rank = {"user": 0, "rule": 1, "ai": 2}

    def ranked(counts):
        return sorted(((cat, src, n) for (cat, src), n in counts.items()), key=lambda x: (source_rank[x[1]], -x[2]))[:3]

    out = {}
    for merchant, (full, brand) in wanted.items():
        if full in by_full:
            out[merchant] = ("same", ranked(by_full[full]))
        elif brand in by_brand:
            out[merchant] = ("similar", ranked(by_brand[brand]))
    return out


def _call_openai_rows(user, rows, examples, cats, exclude_ids=()):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)
    fallback_category = default_category_name("other", user)
    if fallback_category not in cats:
        fallback_category = "Other" if "Other" in cats else (cats[0] if cats else "Other")

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "integer"},
                        "category": {"type": "string", "enum": cats},
                        "confidence": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "category", "confidence", "reason"],
                },
            }
        },
        "required": ["results"],
    }

    category_lines = "\n".join(
        f"- {name}: {CATEGORY_GUIDE[name]}" if name in CATEGORY_GUIDE else f"- {name}: (the user's own category; use the name as the guide)"
        for name in cats
    )

    history = _merchant_history(user, rows, exclude_ids=exclude_ids)
    example_lines = [
        f"- {redact_personal(e['text'].split(' | ')[0])} ({e['in_out']}, {e['amount']:.2f}) => {e['category']}"
        + (" [set by the user]" if e.get("source") == "user" else "")
        for e in examples[:30]
    ]

    instructions = (
        "You sort personal bank transactions from Lithuanian banks (Swedbank, SEB, Luminor, Revolut) into the user's "
        "categories. Descriptions may be in Lithuanian or English and may contain card numbers, dates, terminal ids or "
        "'Kortelės operacija' / 'PIRKINYS' prefixes; ignore that noise and identify the merchant or counterparty.\n"
        "Rules:\n"
        "1) Pick exactly one category from the list. Never invent one.\n"
        "2) If the row lists 'user history' for this merchant, the user's own choice wins unless the amount or direction "
        "clearly makes it a different kind of transaction. 'similar merchant history' only shares the brand word "
        "(e.g. Bolt vs Bolt Food), so treat it as a hint, not a rule.\n"
        "3) Use the direction: 'in' is money received, 'out' is money spent. Salary is only employer wages; interest, "
        "refunds, tax returns and money from people are not salary.\n"
        f"4) When nothing fits, use '{fallback_category}'.\n"
        "5) confidence is your honest probability of being right: 0.9+ only for well-known merchants that clearly match "
        "a category description, 0.6-0.8 for a reasonable guess, below 0.6 when unsure. Wrong answers above 0.7 are "
        "applied automatically, so do not inflate it.\n"
        "6) reason: at most 10 words."
    )

    row_lines = []
    for r in rows:
        merchant = r.get("merchant") or (r.get("text") or "").split(" | ")[0]
        line = {
            "id": r["id"],
            "description": redact_personal((r.get("text") or merchant)[:240]),
            "direction": r.get("in_out", ""),
            "amount": round(float(r.get("amount") or 0), 2),
        }
        match = history.get(merchant)
        if match:
            kind, past = match
            label = "user history" if kind == "same" else "similar merchant history"
            line[label] = [f"{cat} ({'set by user' if src == 'user' else src}, {n}x)" for cat, src, n in past]
        row_lines.append(json.dumps(line, ensure_ascii=False))

    prompt = (
        f"Categories:\n{category_lines}\n\n"
        + ("Examples from this user's history:\n" + "\n".join(example_lines) + "\n\n" if example_lines else "")
        + "Transactions (one JSON object per line):\n" + "\n".join(row_lines)
    )

    request = {
        "model": getattr(settings, "OPENAI_CATEGORIZE_MODEL", "gpt-6.1-sol"),
        "response_format": {"type": "json_schema", "json_schema": {"name": "tx_categorizer", "strict": True, "schema": schema}},
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ],
    }
    effort = getattr(settings, "OPENAI_CATEGORIZE_REASONING_EFFORT", "")
    if effort:
        request["reasoning_effort"] = effort
    try:
        resp = client.chat.completions.create(**request)
    except BadRequestError as exc:
        # Non-reasoning models (e.g. if OPENAI_CATEGORIZE_MODEL is switched back to gpt-4o-mini)
        # reject reasoning_effort; retry once without it instead of failing the whole run.
        if "reasoning_effort" not in request or "reasoning" not in str(exc).lower():
            raise
        request.pop("reasoning_effort")
        resp = client.chat.completions.create(**request)

    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        txt = resp.choices[0].message.content or ""
        start = txt.find("{"); end = txt.rfind("}")
        data = json.loads(txt[start:end+1]) if start >= 0 and end >= 0 else {"results": []}

    out = {}
    for r in data.get("results", []):
        out[int(r.get("id"))] = {
            "category": r.get("category") or fallback_category,
            "confidence": max(0.0, min(1.0, float(r.get("confidence") or 0))),
            "reason": (r.get("reason") or "")[:500]
        }
    return out

def _sample_transactions_for_period(user, start, end):
    qs = list(
        Transaction.objects
        .filter(
            user=user,
            is_deleted=False,
            is_internal_transfer=False,
            date__gte=start,
            date__lte=end,
        )
        .select_related("category_fk")
        .order_by("-date", "-id")
    )

    def tx_row(t):
        category_name = ""
        if getattr(t, "category_fk", None):
            category_name = t.category_fk.name or ""
        else:
            category_name = getattr(t, "category", "") or ""

        note_parts = []
        if getattr(t, "notes", None):
            note_parts.append(t.notes)
        if getattr(t, "user_note", None):
            note_parts.append(t.user_note)

        return {
            "id": t.id,
            "date": t.date.isoformat() if t.date else None,
            "merchant": (t.merchant or "")[:120],
            "amount": float(t.amount or 0),
            "in_out": t.in_out or "",
            "category": category_name,
            "notes": " | ".join(note_parts)[:180],
        }

    # Basic sample the advisor can cite
    tx_sample = [tx_row(t) for t in qs[:12]]

    outs = [
        t for t in qs
        if t.in_out == Transaction.OUT and (t.merchant or "").strip()
    ]

    by_merchant = defaultdict(list)
    for t in outs:
        norm = _normalize_merchant(t.merchant or "")
        if norm:
            by_merchant[norm].append(t)

    recurrings = []
    leaks = []

    for norm, items in by_merchant.items():
        if len(items) < 2:
            continue

        items = sorted(items, key=lambda t: (t.date, t.id))
        amounts = [Decimal(t.amount or 0) for t in items]
        total = sum(amounts, Decimal("0"))
        avg = total / len(items) if items else Decimal("0")
        first_date = items[0].date
        last_date = items[-1].date
        span_days = (last_date - first_date).days if first_date and last_date else 0
        display_name = next((t.merchant for t in reversed(items) if t.merchant), norm)

        # Recurring-ish merchant activity
        if len(items) >= 2 and (span_days >= 14 or len(items) >= 3):
            recurrings.append({
                "merchant": display_name,
                "count": len(items),
                "total": float(total),
                "avg": float(avg),
                "first_date": first_date.isoformat() if first_date else None,
                "last_date": last_date.isoformat() if last_date else None,
            })

        # Small repeated outflows = possible leak
        if len(items) >= 3 and avg <= Decimal("25") and total >= Decimal("30"):
            leaks.append({
                "merchant": display_name,
                "count": len(items),
                "total": float(total),
                "avg": float(avg),
                "note": "Repeated small outgoing transactions in this period.",
            })

    recurrings.sort(key=lambda r: (-r["total"], -r["count"], r["merchant"].lower()))
    leaks.sort(key=lambda r: (-r["total"], -r["count"], r["merchant"].lower()))

    anomalies = []
    if outs:
        spend_amounts = [Decimal(t.amount or 0) for t in outs]
        avg_spend = sum(spend_amounts, Decimal("0")) / len(spend_amounts)
        threshold = max(Decimal("50"), avg_spend * Decimal("2"))

        large_spends = [
            t for t in outs
            if Decimal(t.amount or 0) >= threshold
        ]
        large_spends = sorted(
            large_spends,
            key=lambda t: (Decimal(t.amount or 0), t.date, t.id),
            reverse=True
        )[:5]

        for t in large_spends:
            anomalies.append({
                "merchant": t.merchant or "",
                "amount": float(t.amount or 0),
                "date": t.date.isoformat() if t.date else None,
                "reason": "Large outgoing transaction relative to this period average.",
            })

    return tx_sample, recurrings[:5], leaks[:5], anomalies[:5]

def _get_user_report_language(user) -> str:
    try:
        lang = (user.profile.preferred_language or "lt").lower()
    except Exception:
        lang = "lt"

    return "en" if lang == "en" else "lt"

def _advisor_build_payload(user, ptype: str, start: _date, end: _date):
    tx = Transaction.objects.filter(
        user=user,
        is_deleted=False,
        is_internal_transfer=False,
        date__gte=start,
        date__lte=end,
    )
    inc = tx.filter(in_out=Transaction.IN).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    out = tx.filter(in_out=Transaction.OUT).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    report_lang = _get_user_report_language(user)
    top_cat_qs = (tx.filter(in_out=Transaction.OUT, category_fk__isnull=False)
                    .values("category_fk__name")
                    .annotate(total=Sum("amount"))
                    .order_by("-total")[:10])
    top_cats = [{"category": r["category_fk__name"], "total": float(r["total"] or 0)} for r in top_cat_qs]

    top_merch_qs = (tx.filter(in_out=Transaction.OUT)
                      .exclude(merchant="")
                      .values("merchant")
                      .annotate(total=Sum("amount"))
                      .order_by("-total")[:10])
    top_merchants = [{"merchant": r["merchant"], "total": float(r["total"] or 0)} for r in top_merch_qs]

    wday_totals = [Decimal("0")] * 7
    for t in tx.filter(in_out=Transaction.OUT).only("date", "amount"):
        wday_totals[t.date.weekday()] += (t.amount or Decimal("0"))
    weekday_mix = [float(x) for x in wday_totals]

    # Budgets snapshot (scaled for weekly)
    budgets = []
    cats_with_caps = Category.objects.filter(user=user, monthly_cap__isnull=False).exclude(monthly_cap=0)
    if cats_with_caps.exists():
        cap_scale = 1.0 if ptype == "monthly" else ((end - start).days + 1) / monthrange(start.year, start.month)[1]
        spent_rows = (tx.filter(in_out=Transaction.OUT, category_fk__in=cats_with_caps)
                        .values("category_fk")
                        .annotate(total=Sum("amount")))
        spent_map = {r["category_fk"]: (r["total"] or Decimal("0")) for r in spent_rows}
        for c in cats_with_caps:
            cap_total = float((c.monthly_cap or Decimal("0")) * Decimal(cap_scale))
            spent = float(spent_map.get(c.id, Decimal("0")))
            delta = cap_total - spent
            status = "ok" if delta >= 0 else "over"
            budgets.append({"category": c.name, "cap": round(cap_total,2), "spent": round(spent,2),
                            "delta": round(delta,2), "status": status})

    # Goals snapshot
    tx_sums = (Transaction.objects.filter(user=user, is_deleted=False)
               .values("money_source_id", "in_out")
               .annotate(total=Sum("amount")))
    ledger_map = {}
    for r in tx_sums:
        ms = r["money_source_id"]; amt = r["total"] or Decimal("0")
        ledger_map[ms] = (ledger_map.get(ms, Decimal("0")) + (amt if r["in_out"] == Transaction.IN else -amt))
    eff_map = {}
    for acc in MoneySource.objects.filter(user=user).prefetch_related("holdings__asset"):
        if acc.type == "investment":
            eff_map[acc.id] = current_investment_balance(acc)
        else:
            eff_map[acc.id] = acc.manual_balance if acc.manual_balance is not None else ledger_map.get(acc.id, Decimal("0"))
    goals = []
    for g in SavingsGoal.objects.filter(user=user, is_active=True).prefetch_related("accounts"):
        sel = [a for a in g.accounts.all() if a.is_active]
        current = sum((eff_map.get(a.id, Decimal("0")) for a in sel), Decimal("0"))
        target = g.target_amount or Decimal("0")
        pct = float((current / target * 100) if target > 0 else 0.0)
        goals.append({"name": g.name, "progress_pct": round(pct,1), "eta": None})

    # NEW details for advice
    tx_sample, recurrings, leaks, anomalies = _sample_transactions_for_period(user, start, end)

    mom_delta = None
    if ptype == "monthly":
        prev_y, prev_m = (start.year, start.month-1) if start.month>1 else (start.year-1, 12)
        prev_s = _date(prev_y, prev_m, 1)
        prev_e = _date(prev_y, prev_m, monthrange(prev_y, prev_m)[1])
        prev_tx = Transaction.objects.filter(
            user=user,
            is_deleted=False,
            is_internal_transfer=False,
            date__gte=prev_s,
            date__lte=prev_e,
        )
        prev_inc = prev_tx.filter(in_out=Transaction.IN).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        prev_out = prev_tx.filter(in_out=Transaction.OUT).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        mom_delta = float((inc - out) - (prev_inc - prev_out))

    payload = {
        "user_context": {"currency": "EUR", "locale": report_lang.upper()},
        "period": {"type": ptype, "start": start.isoformat(), "end": end.isoformat()},
        "income_vs_spending": {
            "income_total": float(inc),
            "spending_total": float(out),
            "net": float(inc - out),
            "by_category_topN": top_cats,
            "by_merchant_topN": top_merchants,
            "weekday_mix": weekday_mix,
        },
        "budgets": budgets,
        "goals": goals,
        "balances": {"start_balance": None, "end_balance": None, "delta": float(inc - out)},
        "tx_sample": tx_sample,
        "recurrings": recurrings,
        "leaks": leaks,
        "anomalies": anomalies,
        "month_over_month_net_delta": mom_delta,
        "last_report_excerpt": None,
        "house_rules": [
            "Be practical and conservative.",
            "Use EUR amounts.",
            "Never change user categories.",
            "Cite specific merchants and amounts from tx_sample when giving advice."
        ]
    }
    return payload

def _advisor_call_model(payload: dict, model_name=None):
    api_key = os.getenv("OPENAI_API_KEY")
    model_name = model_name or ADVISOR_MODEL
    if not api_key:
        # key missing -> minimal stub
        return {
            "summary": "AI key missing. Stub report.",
            "key_metrics": {
                "income": payload["income_vs_spending"]["income_total"],
                "spending": payload["income_vs_spending"]["spending_total"],
                "net": payload["income_vs_spending"]["net"],
                "month_over_month_net_delta": payload.get("month_over_month_net_delta"),
                "risk_flags": []
            },
            "insights": [],
            "budgets": payload.get("budgets", []),
            "goals": payload.get("goals", []),
            "subscriptions": [],
            "forecast": {"next_month_notes": "", "targets": []},
            "action_items": [],
            "appendix": {
                "top_categories": payload["income_vs_spending"]["by_category_topN"],
                "top_merchants": payload["income_vs_spending"]["by_merchant_topN"]
            },
            "references": []
        }

    client = OpenAI(api_key=api_key)
    schema = {
        "type":"object",
        "properties":{
            "summary":{"type":"string"},
            "key_metrics":{
                "type":"object",
                "properties":{
                    "income":{"type":"number"},
                    "spending":{"type":"number"},
                    "net":{"type":"number"},
                    "month_over_month_net_delta":{"type":["number","null"]},
                    "risk_flags":{"type":"array","items":{"type":"string"}}
                },
                "required":["income","spending","net","month_over_month_net_delta","risk_flags"]
            },
            "insights":{
                "type":"array",
                "items":{"type":"object","properties":{
                    "title":{"type":"string"},
                    "detail":{"type":"string"},
                    "severity":{"type":"string","enum":["info","watch","alert"]},
                    "estimated_saving":{"type":["number","null"]}
                },"required":["title","detail","severity"]}
            },
            "budgets":{"type":"array","items":{"type":"object",
                "properties":{
                    "category":{"type":"string"},
                    "cap":{"type":"number"},
                    "spent":{"type":"number"},
                    "delta":{"type":"number"},
                    "status":{"type":"string","enum":["ok","over"]},
                    "note":{"type":["string","null"]}
                },
                "required":["category","cap","spent","delta","status"]
            }},
            "goals":{"type":"array","items":{"type":"object",
                "properties":{
                    "name":{"type":"string"},
                    "progress_pct":{"type":"number"},
                    "eta":{"type":["string","null"]},
                    "note":{"type":["string","null"]}
                },
                "required":["name","progress_pct","eta"]
            }},
            "subscriptions":{"type":"array","items":{"type":"object",
                "properties":{
                    "merchant":{"type":"string"},
                    "status_change":{"type":["string","null"]},
                    "action":{"type":["string","null"]}
                },
                "required":["merchant"]
            }},
            "forecast":{"type":"object","properties":{
                "next_month_notes":{"type":"string"},
                "targets":{"type":"array","items":{"type":"object",
                    "properties":{
                        "category":{"type":"string"},
                        "target_spend":{"type":"number"},
                        "rationale":{"type":"string"}
                    },
                    "required":["category","target_spend"]
                }}
            },"required":["next_month_notes","targets"]},
            "action_items":{"type":"array","items":{"type":"object",
                "properties":{
                    "title":{"type":"string"},
                    "why":{"type":"string"},
                    "steps":{"type":"array","items":{"type":"string"}},
                    "impact":{"type":"string","enum":["low","medium","high"]},
                    "estimated_saving":{"type":["number","null"]}
                },
                "required":["title","why","steps","impact"]
            }},
            "appendix":{"type":"object","properties":{
                "top_categories":{"type":"array","items":{"type":"object",
                    "properties":{"category":{"type":"string"},"total":{"type":"number"}},
                    "required":["category","total"]
                }},
                "top_merchants":{"type":"array","items":{"type":"object",
                    "properties":{"merchant":{"type":"string"},"total":{"type":"number"}},
                    "required":["merchant","total"]
                }}
            },"required":["top_categories","top_merchants"]},
            "references":{"type":"array","items":{"type":"object",
                "properties":{
                    "type":{"type":"string","enum":["tx","budget","recurring","leak","anomaly"]},
                    "ref":{"type":"string"},
                    "note":{"type":"string"}
                }}, "default":[]
            }
        },
        "required":["summary","key_metrics","insights","budgets","goals","subscriptions","forecast","action_items","appendix"]
    }

    locale = str(payload.get("user_context", {}).get("locale") or "LT").lower()
    report_language = "Lithuanian" if locale == "lt" else "English"

    system = (
        f"You are a personal finance and wealth advisor. Always write the report in {report_language}. "
        "Do not mix languages unless absolutely necessary for brand names or transaction labels. "
        "Analyze both cash flow and net worth / portfolio, comment on spending discipline, "
        "analyze portfolio performance and whether it cushioned spending, "
        "be concrete, quantify savings/gains, and ground claims in data. Use EUR.\n"
        "You are a personal finance & wealth advisor. "
        "Your goal is to analyze the user's holistic financial health: Cash Flow (Income/Spend) AND Net Worth (Portfolio). "
        "1. Comment on their spending discipline. "
        "2. Analyze their Portfolio performance (Crypto/Stocks). Did it grow? Did it cushion their spending? "
        "3. Be concrete, quantify savings/gains, and ground every claim in data. "
        "Use EUR."
    )

    resp = client.chat.completions.create(
        model=model_name,
        response_format={"type":"json_schema","json_schema":{"name":"advisor_report","schema":schema}},
        temperature=ADVISOR_TEMP,
        messages=[
            {"role":"system","content":system},
            {"role":"user","content":json.dumps(payload)},
        ],
    )

    txt = resp.choices[0].message.content
    try:
        return json.loads(txt)
    except Exception:
        start = txt.find("{"); end = txt.rfind("}")
        return json.loads(txt[start:end+1]) if start>=0 and end>=0 else {
            "summary":"(parse error)",
            "key_metrics":{"income":0,"spending":0,"net":0,"month_over_month_net_delta":None,"risk_flags":[]},
            "insights":[], "budgets":[], "goals":[], "subscriptions":[],
            "forecast":{"next_month_notes":"","targets":[]},
            "action_items":[], "appendix":{"top_categories":[],"top_merchants":[]}, "references":[]
        }
