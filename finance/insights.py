"""Plain-number spending overviews for the Reports page and the monthly email.

Computed straight from the user's transactions: no AI, no cost, same rules as the dashboard
(outgoing, not deleted, not internal transfers). Sample data is left out.
"""
from calendar import monthrange
from collections import defaultdict
from datetime import date as _date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from .models import Transaction
from .sample_data import real_transactions
from .services import _merchant_key

MONTHS_LT = ["sausis", "vasaris", "kovas", "balandis", "gegužė", "birželis", "liepa", "rugpjūtis",
             "rugsėjis", "spalis", "lapkritis", "gruodis"]
MONTHS_LT_GENITIVE = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio", "liepos",
                      "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]

MIN_BASE = Decimal("30")       # don't compare against (or call out) tiny amounts
MIN_CHANGE_PCT = 10            # category moves smaller than this aren't worth a sentence
MONTH_SLACK = 3                # days of slack when deciding if data covers a whole month
WEEK_SLACK = 1


def money(amount, lt):
    """Whole euros: '1 240 €' in Lithuanian, '€1,240' in English."""
    n = int(Decimal(amount or 0).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    sign = "−" if n < 0 else ""
    if lt:
        return f"{sign}{abs(n):,}".replace(",", "\u00a0") + "\u00a0€"
    return f"{sign}€{abs(n):,}"


def pct(value, lt):
    sign = "−" if value < 0 else ""
    return f"{sign}{abs(value)}\u00a0%" if lt else f"{sign}{abs(value)}%"


def month_bounds(day):
    start = day.replace(day=1)
    return start, _date(start.year, start.month, monthrange(start.year, start.month)[1])


def previous_month(day):
    return month_bounds(day.replace(day=1) - timedelta(days=1))


def month_name(day, lt, genitive=False):
    if lt:
        return (MONTHS_LT_GENITIVE if genitive else MONTHS_LT)[day.month - 1]
    return MONTHS_EN[day.month - 1]


def _rows(user, include_sample):
    qs = Transaction.objects.filter(user=user, is_deleted=False)
    return qs if include_sample else real_transactions(qs)


def base_qs(user, include_sample=False):
    return _rows(user, include_sample).filter(is_internal_transfer=False)


def covers(user, start, end, slack, include_sample=False):
    """True when the user's data reaches from the start to the end of the period (gaps in between aside)."""
    qs = _rows(user, include_sample)
    return (qs.filter(date__lte=start + timedelta(days=slack)).exists()
            and qs.filter(date__gte=end - timedelta(days=slack)).exists())


def last_complete_month(user, today, lookback=2):
    """(start, end) of the newest fully covered month among the last `lookback` finished months, or None."""
    start, end = previous_month(today)
    for _ in range(lookback):
        if covers(user, start, end, MONTH_SLACK):
            return start, end
        start, end = previous_month(start)
    return None


def _total(qs):
    return sum((a or Decimal("0") for a in qs.values_list("amount", flat=True)), Decimal("0"))


def _totals_by_category(qs, uncategorized):
    totals = defaultdict(Decimal)
    for name, amount in qs.values_list("category_fk__name", "amount"):
        totals[name or uncategorized] += amount or Decimal("0")
    return totals


def period_summary(user, start, end, prev_start, prev_end, *, lt, kind="month", include_sample=False):
    """Spending for start..end compared with prev_start..prev_end, plus up to three tips.

    The comparison is only made when the user's data covers both periods fully, so a half-uploaded
    month never reads as "you spent 80% less".
    """
    slack = MONTH_SLACK if kind == "month" else WEEK_SLACK
    qs = base_qs(user, include_sample)
    cur = qs.filter(date__gte=start, date__lte=end)
    out = cur.filter(in_out=Transaction.OUT)
    spent = _total(out)
    income = _total(cur.filter(in_out=Transaction.IN))

    complete = covers(user, start, end, slack, include_sample)
    comparable = complete and covers(user, prev_start, prev_end, slack, include_sample)
    prev_out = qs.filter(date__gte=prev_start, date__lte=prev_end, in_out=Transaction.OUT)
    prev_spent = _total(prev_out)
    change_pct = None
    if comparable and prev_spent >= MIN_BASE:
        change_pct = int(((spent - prev_spent) / prev_spent * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    uncategorized = "Be kategorijos" if lt else "Uncategorized"
    by_cat = _totals_by_category(out, uncategorized)
    prev_by_cat = _totals_by_category(prev_out, uncategorized) if comparable else {}
    categories = []
    for name, total in sorted(by_cat.items(), key=lambda kv: -kv[1])[:6]:
        prev = prev_by_cat.get(name)
        change = (total - prev) if prev is not None else None
        categories.append({
            "name": name,
            "total": total,
            "total_text": money(total, lt),
            "share": float(total / spent * 100) if spent else 0.0,
            "change": change,
            "change_text": (("+" if change > 0 else "") + money(change, lt)) if change else "",
        })

    biggest_move = None
    for name in set(by_cat) | set(prev_by_cat):
        if name == uncategorized or not comparable:
            continue
        now, before = by_cat.get(name, Decimal("0")), prev_by_cat.get(name, Decimal("0"))
        if now < MIN_BASE or before < MIN_BASE:
            continue
        change = now - before
        change_pct_cat = int((change / before * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if abs(change_pct_cat) < MIN_CHANGE_PCT:
            continue
        if biggest_move is None or abs(change) > abs(biggest_move["change"]):
            biggest_move = {"name": name, "change": change, "pct": change_pct_cat}

    summary = {
        "start": start, "end": end, "kind": kind,
        "spent": spent, "income": income, "net": income - spent,
        "prev_spent": prev_spent, "change_pct": change_pct,
        "complete": complete, "comparable": comparable,
        "categories": categories, "biggest_move": biggest_move,
        "spent_text": money(spent, lt), "income_text": money(income, lt), "net_text": money(income - spent, lt),
        "tx_count": out.count(),
        "data_until": cur.order_by("-date").values_list("date", flat=True).first(),
    }
    summary["change_text"] = _change_text(change_pct, kind, prev_start, lt)
    summary["tips"] = _tips(summary, out, by_cat.get(uncategorized, Decimal("0")), lt)
    return summary


def _change_text(change_pct, kind, prev_start, lt):
    """'12 % mažiau nei rugsėjo mėnesį' / '12% less than the week before', or '' with nothing to compare."""
    if not change_pct:
        return ""
    if lt:
        more = "daugiau" if change_pct > 0 else "mažiau"
        than = "nei ankstesnę savaitę" if kind == "week" else f"nei {month_name(prev_start, lt, genitive=True)} mėnesį"
    else:
        more = "more" if change_pct > 0 else "less"
        than = "than the week before" if kind == "week" else f"than in {month_name(prev_start, lt)}"
    return f"{pct(abs(change_pct), lt)} {more} {than}"


def _frequent_small_spend(out, min_count):
    """The merchant paid most often in small amounts, e.g. the daily coffee."""
    groups = defaultdict(lambda: {"count": 0, "total": Decimal("0"), "label": ""})
    for merchant, amount in out.values_list("merchant", "amount"):
        key = _merchant_key(merchant)[0]
        if not key:
            continue
        g = groups[key]
        g["count"] += 1
        g["total"] += amount or Decimal("0")
        label = (merchant or "").strip()
        if not g["label"] or len(label) < len(g["label"]):
            g["label"] = label
        g["key"] = key
    best = None
    for g in groups.values():
        if g["count"] >= min_count and g["total"] / g["count"] <= Decimal("15") and g["total"] >= Decimal("20"):
            if best is None or g["count"] > best["count"]:
                best = g
    if best and len(best["label"]) > 40:  # raw bank text with card masks etc.
        best["label"] = best["key"].title()
    return best


def _times_lt(n):
    if n % 10 == 0 or 11 <= n % 100 <= 19:
        return "kartų"
    return "kartas" if n % 10 == 1 else "kartai"


def _tips(s, out, uncategorized_total, lt):
    tips = []
    move = s["biggest_move"]
    if move:
        amount = money(abs(move["change"]), lt)
        if move["change"] > 0:
            tips.append(
                f"Daugiausia išaugo „{move['name']}“: +{amount} (+{pct(move['pct'], lt)}). Verta pažiūrėti, kas pasikeitė."
                if lt else
                f"Biggest increase: “{move['name']}” +{amount} (+{pct(move['pct'], lt)}). Worth a look at what changed."
            )
        else:
            tips.append(
                f"Gerai: „{move['name']}“ sumažėjo {amount} ({pct(move['pct'], lt)})."
                if lt else
                f"Nice: “{move['name']}” went down by {amount} ({pct(move['pct'], lt)})."
            )

    if s["kind"] == "month" and s["complete"] and s["income"] >= MIN_BASE:
        if s["net"] < 0:
            tips.append(
                f"Išleidai {money(-s['net'], lt)} daugiau, nei gavai."
                if lt else f"You spent {money(-s['net'], lt)} more than you received."
            )
        else:
            kept = int((s["net"] / s["income"] * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            tips.append(
                f"Liko {money(s['net'], lt)} – {pct(kept, lt)} gautų pinigų."
                if lt else f"You kept {money(s['net'], lt)} – {pct(kept, lt)} of the money that came in."
            )

    frequent = _frequent_small_spend(out, 6 if s["kind"] == "month" else 3)
    if frequent:
        tips.append(
            f"{frequent['label']}: {frequent['count']} {_times_lt(frequent['count'])}, iš viso {money(frequent['total'], lt)}. Smulkūs pirkiniai greitai susideda."
            if lt else
            f"{frequent['label']}: {frequent['count']} times, {money(frequent['total'], lt)} in total. Small buys add up."
        )

    if s["spent"] and uncategorized_total >= MIN_BASE and uncategorized_total / s["spent"] >= Decimal("0.1"):
        tips.append(
            f"{money(uncategorized_total, lt)} dar be kategorijos – priskirk jas, ir vaizdas bus tikslesnis."
            if lt else
            f"{money(uncategorized_total, lt)} is still uncategorized – categorize it for a clearer picture."
        )
    return tips[:3]


def monthly_summary(user, month_start, *, lt, include_sample=False):
    start, end = month_bounds(month_start)
    prev_start, prev_end = previous_month(start)
    return period_summary(user, start, end, prev_start, prev_end, lt=lt, kind="month", include_sample=include_sample)


def weekly_summary(user, week_start, *, lt, include_sample=False):
    end = week_start + timedelta(days=6)
    return period_summary(user, week_start, end, week_start - timedelta(days=7), week_start - timedelta(days=1),
                          lt=lt, kind="week", include_sample=include_sample)


def headline(s, lt):
    """'Spalio mėnesį išleidai 1 240 € – 12 % mažiau nei rugsėjo mėnesį.' (monthly summaries)"""
    if lt:
        text = f"{month_name(s['start'], lt, genitive=True).capitalize()} mėnesį išleidai {money(s['spent'], lt)}"
    else:
        text = f"You spent {money(s['spent'], lt)} in {month_name(s['start'], lt)}"
    if s["change_text"]:
        text += f" – {s['change_text']}"
    return text + "."
