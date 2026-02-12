# finance/importers/swedbank.py
from __future__ import annotations

import csv
import io
import unicodedata
from typing import Any

from .base import ImporterBase, SniffResult
from finance.utils import parse_date, parse_amount, normalize_currency


def _decode_bytes(raw: bytes) -> str:
    # Swedbank LT exports can be UTF-8 with BOM or Windows Baltic (cp1257)
    for enc in ("utf-8-sig", "utf-8", "cp1257", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _norm_header(s: str) -> str:
    """
    Normalize header for matching:
    - strip quotes/whitespace
    - remove diacritics
    - lowercase
    """
    s = (s or "").strip().strip("\ufeff").strip().strip('"').strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


def _extract_headers_from_text(text: str) -> set[str]:
    """
    Reads the first meaningful CSV line and returns headers.
    Swedbank CSV is usually comma-delimited, quoted.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in text.split("\n")[:50]:
        if not line.strip():
            continue
        # Swedbank header line has many columns
        if line.count(",") < 5:
            continue
        try:
            cells = next(csv.reader([line], delimiter=",", quotechar='"'))
        except Exception:
            continue
        headers = {c.strip().strip('"') for c in cells if (c or "").strip()}
        if len(headers) >= 5:
            return headers
    return set()


class SwedbankImporter(ImporterBase):
    key = "swedbank"
    label = "Swedbank"

    # From your file: "Sąskaitos Nr.","","Data","Gavėjas","Paaiškinimai","Suma","Valiuta","D/K",...
    required_headers = {
        "Sąskaitos Nr.",
        "Data",
        "Gavėjas",
        "Paaiškinimai",
        "Suma",
        "Valiuta",
        "D/K",
    }

    def sniff(self, headers: set[str] | None = None, **kwargs: Any) -> SniffResult:
        """
        Supports BOTH styles:
          - sniff(headers=set(...))  <-- new pipeline
          - sniff(raw=b"...", filename="...")  <-- old calls
          - sniff(text="...") <-- just in case
        """
        # If someone passed raw/text via kwargs, convert → headers
        raw = kwargs.get("raw")
        text = kwargs.get("text")

        if headers is None and isinstance(text, str):
            headers = _extract_headers_from_text(text)

        if headers is None and isinstance(raw, (bytes, bytearray)):
            t = _decode_bytes(bytes(raw))
            headers = _extract_headers_from_text(t)

        headers = headers or set()

        # Diacritic-insensitive match
        want = {_norm_header(h) for h in self.required_headers}
        have = {_norm_header(h) for h in headers}

        match = len(want & have)

        # If it matches at least 4 of 7, it's very likely Swedbank
        ok = match >= 4
        score = match

        reason = f"Matched {match}/{len(want)} Swedbank headers"
        return SniffResult(ok=ok, score=score, reason=reason, detected_name=self.label)

    def parse(self, *, text: str) -> list[dict]:
        """
        Normalized output dict fields:
          date,time,merchant,amount,currency,in_out,notes,description
        """
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        reader = csv.DictReader(io.StringIO(text), delimiter=",", quotechar='"')

        rows: list[dict] = []

        for r in reader:
            # Swedbank headers (LT)
            date_val = (r.get("Data") or "").strip()
            merchant = (r.get("Gavėjas") or "").strip()
            explain = (r.get("Paaiškinimai") or "").strip()
            amount_raw = r.get("Suma")
            currency = (r.get("Valiuta") or "EUR").strip()
            dk = (r.get("D/K") or "").strip().upper()

            explain_l = explain.strip().lower()

            # Skip balance lines like: "Likutis pradžiai" / "Likutis pabaigai"
            if explain_l.startswith("likutis"):
                continue

            # Skip Swedbank turnover/summary lines: "Apyvarta"
            if explain_l == "apyvarta":
                continue

            # D/K: D = debit (out), K = credit (in)
            if dk == "D":
                in_out = "out"
            elif dk == "K":
                in_out = "in"
            else:
                # fallback: if missing, infer from sign (rare)
                amt_tmp = parse_amount(amount_raw)
                in_out = "out" if amt_tmp < 0 else "in"

            amt = parse_amount(amount_raw)
            if amt < 0:
                amt = abs(amt)

            d = parse_date(date_val)
            cur = normalize_currency(currency) or "EUR"

            rows.append({
                "date": d,
                "time": "",
                "merchant": merchant[:200] or (explain[:200] if explain else ""),
                "amount": amt,
                "currency": cur,
                "in_out": in_out,
                "notes": explain[:500],
                "description": explain[:500],
            })

        return rows
