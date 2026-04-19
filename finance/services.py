# finance/services.py
import os, json
from decimal import Decimal
from datetime import date as _date
from collections import defaultdict
from calendar import monthrange
from django.db.models import Sum
from openai import OpenAI
from django.utils import timezone
from .models import Transaction, Category, SavingsGoal, MoneySource
from .utils import _normalize_merchant

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
        .filter(user=user, date__gte=lookback_start, category_fk__isnull=False)
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

    user_locked = [e for e in examples if e.get("source") == "user"][:EXAMPLES_MIN_USER]
    example_lines = []
    if user_locked:
        e = user_locked[0]
        example_lines.append(
            f"- (LOCKED) text='{e['text']}', amount={e['amount']}, in_out={e['in_out']} => {e['category']} (source=user)"
        )
    for e in examples:
        example_lines.append(
            f"- text='{e['text']}', amount={e['amount']}, in_out={e['in_out']} => {e['category']} (source={e.get('source','')})"
        )

    msg = (
        "You are a strict finance transaction categorizer.\n"
        "Rules:\n"
        "1) Choose exactly ONE category from the provided list. Do NOT invent categories.\n"
        "2) If current_category_source == 'user', RETURN THE SAME category (do NOT change it).\n"
        "3) Use amount/in_out and text cues (merchant | notes | user_note). Prefer precision.\n"
        "4) If unsure, pick a broad bucket (e.g., 'Other').\n\n"
        f"Allowed categories: {', '.join(cats)}\n\n"
        "Ground-truth examples (respect '(LOCKED)'):\n" + "\n".join(example_lines)
    )

    rows_text = "\n".join([
        f"- id={r['id']}, text='{(r.get('text') or '')[:240]}', amount={r.get('amount',0)}, "
        f"in_out='{r.get('in_out','')}', current_category='{r.get('current_category','')}', "
        f"current_category_source='{r.get('current_source','')}'"
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

def _get_user_report_language(user) -> str:
    try:
        lang = (user.profile.preferred_language or "lt").lower()
    except Exception:
        lang = "lt"

    return "en" if lang == "en" else "lt"

def _advisor_build_payload(user, ptype: str, start: _date, end: _date):
    tx = Transaction.objects.filter(user=user, is_deleted=False, date__gte=start, date__lte=end)
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
    for acc in MoneySource.objects.filter(user=user):
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
        prev_s, prev_e = _date(prev_y, 1, 1).replace(month=prev_m), _date(prev_y, monthrange(prev_y, prev_m)[1], 1).replace(month=prev_m)
        prev_e = _date(prev_y, prev_m, monthrange(prev_y, prev_m)[1])
        prev_tx = Transaction.objects.filter(user=user, is_deleted=False, date__gte=prev_s, date__lte=prev_e)
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