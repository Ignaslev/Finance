# finance/importers/revolut.py
from __future__ import annotations

import csv, io

from .base import ImporterBase
from finance.utils import parse_date, parse_amount, normalize_currency


class RevolutImporter(ImporterBase):
    key = "revolut"
    label = "Revolut"
    required_headers = {
        "Type", "Completed Date", "Started Date", "Description", "Amount", "Currency"
    }

    def parse(self, *, text: str) -> list[dict]:
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")

        # delimiter guess just for parsing (independent from sniff)
        sample = text[:8192]
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
            delimiter = dialect.delimiter
        except Exception:
            pass

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows: list[dict] = []

        for r in reader:
            date_val = (r.get("Completed Date") or r.get("Started Date") or "").strip()
            desc = (r.get("Description") or "").strip()
            currency = (r.get("Currency") or "EUR").strip()

            amt = parse_amount(r.get("Amount"))
            if amt < 0:
                in_out = "out"
                amt = abs(amt)
            elif amt > 0:
                in_out = "in"
            else:
                in_out = "out"

            d = parse_date(date_val)
            cur = normalize_currency(currency)

            rows.append({
                "date": d,
                "time": "",
                "merchant": desc[:200],
                "amount": amt,
                "currency": cur or "EUR",
                "in_out": in_out,
                "notes": "",
                "description": desc[:500],
            })

        return rows
