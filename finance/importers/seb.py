# finance/importers/seb.py
from __future__ import annotations

import csv, io, re, unicodedata

from .base import ImporterBase, SniffResult
from finance.utils import parse_date, parse_amount, parse_in_out, normalize_currency


def _norm(s: str) -> str:
    s = (s or "").strip().strip("\ufeff").strip().strip('"').strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _find_header_idx(text: str, delimiter: str = ";") -> int | None:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")

    best_i = None
    best_score = -1

    for i, line in enumerate(lines[:100]):
        if line.count(delimiter) < 3:
            continue
        try:
            cells = next(csv.reader([line], delimiter=delimiter))
        except Exception:
            continue

        norm = " | ".join(_norm(c) for c in cells)
        score = 0
        if "debetas/kreditas" in norm:
            score += 6
        if "dok nr" in norm:
            score += 3
        if "data" in norm:
            score += 2
        if "suma" in norm:
            score += 2
        if "valiuta" in norm:
            score += 1

        if score > best_score:
            best_score = score
            best_i = i

    if best_score < 8:
        return None
    return best_i


class SEBImporter(ImporterBase):
    key = "seb"
    label = "SEB"

    def sniff(self, *, raw: bytes, filename: str = "") -> SniffResult:
        if not raw:
            return SniffResult(False, 0, "Empty file", self.label)

        text = self.decode(raw[:300_000])
        idx = _find_header_idx(text, delimiter=";")
        if idx is None:
            return SniffResult(False, 0, "SEB header not found", self.label)
        return SniffResult(True, 10, f"Found SEB header at line {idx}", self.label)

    def parse(self, *, text: str) -> list[dict]:
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")

        delimiter = ";"
        header_idx = _find_header_idx(text, delimiter=delimiter)
        if header_idx is None:
            raise ValueError("This file does not look like an SEB statement (header not found).")

        sliced_text = "\n".join(lines[header_idx:])
        reader = csv.DictReader(io.StringIO(sliced_text), delimiter=delimiter)

        def pick(d: dict, *aliases: str):
            keys = {_norm(k): k for k in d.keys()}
            for a in aliases:
                na = _norm(a)
                if na in keys:
                    return d.get(keys[na])
            return None

        rows: list[dict] = []

        for r in reader:
            rr = {(k or "").strip(): r.get(k) for k in r.keys()}

            date_val   = pick(rr, "DATA", "Date")
            merchant   = pick(rr, "MOKĖTOJAS / GAVĖJAS", "MOKĖTOJO ARBA GAVĖJO PAVADINIMAS", "GAVĖJAS", "MOKĖTOJAS")
            amount_raw = pick(rr, "SUMA", "SUMA SĄSKAITOS VALIUTA", "SUMA SASKAITOS VALIUTA")
            currency   = pick(rr, "VALIUTA", "SĄSKAITOS VALIUTA", "SASKAITOS VALIUTA")
            debcred    = pick(rr, "DEBETAS/KREDITAS", "D/K", "DR/CR")
            trans_type = pick(rr, "TRANSAKCIJOS TIPAS", "TRANSACTION TYPE", "TIPAS", "TYPE")
            note       = pick(rr, "PASKIRTIS", "MOKĖJIMO PASKIRTIS", "MOKEJIMO PASKIRTIS", "NOTE", "NOTES")
            time_val   = pick(rr, "LAIKAS", "TIME")

            dc = (debcred or "").strip().upper()
            # SEB sometimes uses K for credit; your parse_in_out expects C/D style
            if dc == "K":
                dc = "C"

            try:
                d = parse_date(date_val)
                in_out = parse_in_out(dc, trans_type)
                amt = parse_amount(amount_raw)
                cur = normalize_currency(currency)
            except Exception:
                continue

            if not d:
                continue

            rows.append({
                "date": d,
                "time": (str(time_val).strip() if time_val else ""),
                "merchant": (merchant or "").strip()[:200],
                "amount": amt,
                "currency": cur or "EUR",
                "in_out": in_out or "out",
                "notes": (note or "").strip()[:500],
                "description": (str(note or merchant or "").strip())[:500],
            })

        return rows
