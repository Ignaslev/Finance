"""Read PDF bank statements with OpenAI in background mode and turn them into import rows.

Flow: upload -> start_pdf_read() creates a background response -> the status page polls
refresh_job() until the rows are stored on the PdfImportJob -> build_preview() shows totals,
the balance check and likely duplicates -> the confirm view feeds `fresh_rows` to the shared
import helper.
"""
import base64
import json
import os
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from openai import BadRequestError, NotFoundError, OpenAI

from .models import PdfImportJob, Transaction

CENT = Decimal("0.01")
MAX_OUTPUT_TOKENS = 64000  # enough for roughly a year of rows

STATEMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["bank", "opening_balance", "closing_balance", "currency", "rows"],
    "properties": {
        "bank": {"type": ["string", "null"], "description": "the bank's name, e.g. Swedbank, SEB, Luminor"},
        "opening_balance": {"type": ["number", "null"]},
        "closing_balance": {"type": ["number", "null"]},
        "currency": {"type": "string"},
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["date", "merchant", "description", "amount", "direction", "currency"],
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "merchant": {"type": "string", "description": "shop or counterparty name only"},
                    "description": {"type": "string", "description": "the full line as printed"},
                    "amount": {"type": "number", "description": "positive amount"},
                    "direction": {"type": "string", "enum": ["in", "out"]},
                    "currency": {"type": "string"},
                },
            },
        },
    },
}

INSTRUCTIONS = (
    "You read personal bank account statements (Lithuanian and other banks; Lithuanian or English). "
    "Return every transaction row exactly as printed, in order, across all pages. Skip summary lines such as "
    "opening/closing balance ('Likutis pradžiai/pabaigai'), turnover ('Apyvarta') and page totals.\n"
    "- date: the booking/operation date as YYYY-MM-DD.\n"
    "- merchant: only the shop or counterparty name, without card numbers, dates, 'PIRKINYS', "
    "'Kortelės operacija' or terminal ids (e.g. 'MAXIMA X, VILNIUS'). Rows without a counterparty (bank fees, "
    "cash withdrawals, interest) get a short label such as 'Banko mokestis' or 'Grynieji pinigai' - never the "
    "row number, reference numbers or amount.\n"
    "- description: the full row text as printed.\n"
    "- amount: positive number; direction 'out' for money leaving the account (debit, minus sign, D), "
    "'in' for money received (credit, K, C).\n"
    "- currency: the row's currency (usually EUR).\n"
    "Also return the bank's name and the statement's opening and closing balance for this account if "
    "printed, otherwise null. "
    "Never invent rows or balances."
)


def _client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _model():
    return getattr(settings, "OPENAI_PDF_MODEL", "gpt-6.1-sol")


def start_pdf_read(raw: bytes, filename: str) -> tuple[str, str]:
    """Start a background read of the PDF. Returns (response_id, model)."""
    model = _model()
    request = {
        "model": model,
        "background": True,
        "store": False,  # OpenAI keeps background data only ~10 minutes for polling
        "instructions": INSTRUCTIONS,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_file", "filename": filename or "statement.pdf",
                 "file_data": "data:application/pdf;base64," + base64.b64encode(raw).decode()},
                {"type": "input_text", "text": "Extract the statement."},
            ],
        }],
        "text": {"format": {"type": "json_schema", "name": "bank_statement", "strict": True, "schema": STATEMENT_SCHEMA}},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
    }
    effort = getattr(settings, "OPENAI_PDF_REASONING_EFFORT", "low")
    if effort:
        request["reasoning"] = {"effort": effort}
    client = _client()
    try:
        response = client.responses.create(**request)
    except BadRequestError as exc:
        # Non-reasoning models reject the reasoning option; retry once without it.
        if "reasoning" not in request or "reasoning" not in str(exc).lower():
            raise
        request.pop("reasoning")
        response = client.responses.create(**request)
    return response.id, model


def refresh_job(job: PdfImportJob) -> PdfImportJob:
    """Check the background read once. Safe to call repeatedly (two tabs, fast polling)."""
    if job.status != PdfImportJob.STATUS_READING:
        return job
    try:
        response = _client().responses.retrieve(job.response_id)
    except NotFoundError:
        # Background data is gone (~10 min). Another poll may have just stored the result.
        job.refresh_from_db()
        if job.status == PdfImportJob.STATUS_READING:
            _fail(job, "expired")
        return job

    status = getattr(response, "status", "")
    if status in ("queued", "in_progress"):
        return job
    if status == "completed":
        try:
            data = json.loads(response.output_text or "")
        except (TypeError, ValueError):
            _fail(job, "unreadable_output")
            return job
        # Only the first poll that sees "completed" stores the rows.
        PdfImportJob.objects.filter(pk=job.pk, status=PdfImportJob.STATUS_READING).update(
            status=PdfImportJob.STATUS_READY, result=data,
        )
        job.refresh_from_db()
        return job
    _fail(job, status or "failed")
    return job


def cancel_job(job: PdfImportJob) -> None:
    if job.status == PdfImportJob.STATUS_READING and job.response_id:
        try:
            _client().responses.cancel(job.response_id)
        except Exception:
            pass  # already finished or expired; nothing to stop
    job.status = PdfImportJob.STATUS_CANCELLED
    job.result = None  # drop the statement data as soon as the user cancels
    job.save(update_fields=["status", "result", "updated_at"])


def _fail(job, reason):
    PdfImportJob.objects.filter(pk=job.pk, status=PdfImportJob.STATUS_READING).update(
        status=PdfImportJob.STATUS_FAILED, error=reason[:500],
    )
    job.refresh_from_db()


def _money(value):
    try:
        return Decimal(str(value)).quantize(CENT)
    except (InvalidOperation, TypeError, ValueError):
        return None


# A printed statement line, e.g. "2 2026-08-01 MP banko mokestis 2026080100497342 -0.41 TT".
_RAW_LINE_START = re.compile(r"^\d{1,4}\s+\d{4}-\d{2}-\d{2}\s")
_LABEL_NOISE = [
    re.compile(r"^\d{1,4}\s+\d{4}-\d{2}-\d{2}\s+"),          # row number + date
    re.compile(r"\b\d{4,6}\*{4,}\d{4}\b"),                    # card mask 516793******3619
    re.compile(r"\b\d{2}\.\d{2}\.\d{2,4}\b|\b\d{1,2}:\d{2}\b"),  # 06.08.26 19:52
    re.compile(r"-?\d+[.,]\d{2}\s*(?:EUR|USD|GBP)?"),         # amounts
    re.compile(r"\(\d+\)|\b\d{10,}\b"),                       # (511732), reference numbers
    re.compile(r"\s+[A-Z]{1,2}$"),                            # trailing type code (TT, M, K)
]


def _short_label(text: str) -> str:
    """Readable merchant for rows the model gave no counterparty for (fees, cash withdrawals)."""
    label = text or ""
    for pattern in _LABEL_NOISE:
        label = pattern.sub(" ", label)
    label = re.sub(r"\s{2,}", " ", label).strip(" ,;-")
    return label[:60].strip()


def statement_bank(job: PdfImportJob) -> str:
    return str((job.result or {}).get("bank") or "").strip()[:60]


def parsed_rows(job: PdfImportJob) -> tuple[list[dict], int]:
    """Strictly parse stored rows. Returns (rows, unreadable_count). Never guesses a date."""
    data = job.result or {}
    default_currency = (str(data.get("currency") or "EUR").strip().upper() or "EUR")[:8]
    rows, unreadable = [], 0
    seen = Counter()
    for r in data.get("rows") or []:
        try:
            day = datetime.strptime(str(r.get("date", "")).strip(), "%Y-%m-%d").date()
        except ValueError:
            unreadable += 1
            continue
        amount = _money(r.get("amount"))
        direction = r.get("direction")
        if amount is None or amount <= 0 or direction not in ("in", "out"):
            unreadable += 1
            continue
        description = str(r.get("description") or "").strip()
        merchant = str(r.get("merchant") or "").strip()
        if not merchant or merchant == description or _RAW_LINE_START.match(merchant):
            merchant = _short_label(merchant or description) or description
        # Identical rows (two coffees, same day) would share one import fingerprint and the second
        # would be dropped; number repeats within this file. Deterministic, so re-imports still dedupe.
        seen[(day, amount, direction, description)] += 1
        repeat = seen[(day, amount, direction, description)]
        rows.append({
            "date": day,
            "time": f"#{repeat}" if repeat > 1 else "",
            "merchant": merchant[:200],
            "amount": amount,
            "currency": (str(r.get("currency") or "").strip().upper() or default_currency)[:8],
            "in_out": direction,
            "notes": description[:500],
            "description": description[:500],
        })
    return rows, unreadable


def _split_duplicates(job: PdfImportJob, rows: list[dict], money_source=None) -> tuple[list[dict], int]:
    """Skip rows already stored for the target account, counting identical rows.

    A PDF and a CSV of the same month describe rows differently, so match on date, amount,
    currency and direction. Two identical coffees on one day are both real: only as many PDF rows
    are skipped as the account already has. money_source=False means a new, empty account.
    """
    if money_source is False:
        return list(rows), 0
    stored = (
        Transaction.objects
        .filter(user=job.user, money_source=money_source or job.money_source, is_deleted=False)
        .values_list("date", "amount", "currency", "in_out")
    )
    existing = Counter((d, _money(a), (c or "EUR"), io) for d, a, c, io in stored)
    fresh, duplicates = [], 0
    for r in rows:
        key = (r["date"], r["amount"], r["currency"], r["in_out"])
        if existing[key] > 0:
            existing[key] -= 1
            duplicates += 1
        else:
            fresh.append(r)
    return fresh, duplicates


def build_preview(job: PdfImportJob, money_source=None) -> dict:
    """money_source: the account to import into (default the job's; False = a new account)."""
    rows, unreadable = parsed_rows(job)
    fresh, duplicates = _split_duplicates(job, rows, money_source)
    data = job.result or {}
    total_in = sum((r["amount"] for r in rows if r["in_out"] == "in"), Decimal("0"))
    total_out = sum((r["amount"] for r in rows if r["in_out"] == "out"), Decimal("0"))
    opening = _money(data.get("opening_balance"))
    closing = _money(data.get("closing_balance"))
    if opening is None or closing is None:
        balance_check, difference = "missing", None
    else:
        difference = (opening + total_in - total_out - closing).quantize(CENT)
        balance_check = "ok" if difference == 0 else "mismatch"
    dates = [r["date"] for r in rows]
    return {
        "rows": rows,
        "fresh_rows": fresh,
        "row_count": len(rows),
        "new_count": len(fresh),
        "duplicate_count": duplicates,
        "unreadable_count": unreadable,
        "total_in": total_in,
        "total_out": total_out,
        "opening": opening,
        "closing": closing,
        "balance_check": balance_check,
        "difference": difference,
        "period_start": min(dates) if dates else None,
        "period_end": max(dates) if dates else None,
        "currency": data.get("currency") or "EUR",
    }
