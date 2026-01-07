# finance/importers/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import csv
import io


@dataclass
class SniffResult:
    ok: bool
    score: int
    reason: str = ""
    detected_name: str = ""


class ImporterBase:
    key: str = "base"
    label: str = "Base"
    required_headers: set[str] = set()

    # ---------- decoding ----------
    def decode(self, raw: bytes) -> str:
        for enc in ("utf-8-sig", "utf-8", "cp1257", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("latin-1", errors="replace")

    # ---------- header extraction (for “simple” formats like Revolut) ----------
    def extract_first_header_row(self, text: str) -> tuple[set[str], str]:
        """
        Returns (headers_set, delimiter_used).
        Picks the first plausible CSV header line using delimiter guess.
        This is *not* used by SEB (SEB overrides sniff/parse).
        """
        text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = [ln for ln in text.split("\n") if ln.strip()][:50]
        if not lines:
            return set(), ","

        sample = "\n".join(lines[:10])
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
            delimiter = dialect.delimiter
        except Exception:
            # fallback: simple count
            counts = {sep: sample.count(sep) for sep in (",", ";", "\t")}
            delimiter = max(counts, key=counts.get) if any(counts.values()) else ","

        # take first non-empty line as header
        try:
            header_cells = next(csv.reader([lines[0]], delimiter=delimiter))
        except Exception:
            return set(), delimiter

        headers = {((c or "").strip().strip("\ufeff").strip()) for c in header_cells if (c or "").strip()}
        return headers, delimiter

    # ---------- sniff ----------
    def sniff(self, *, raw: bytes, filename: str = "") -> SniffResult:
        """
        Default sniff: decode + check first header row against required_headers (case-insensitive).
        Good for formats where the header is the first line (e.g., Revolut).
        """
        if not raw:
            return SniffResult(False, 0, "Empty file", self.label)

        text = self.decode(raw[:200_000])
        headers, _delim = self.extract_first_header_row(text)
        if not headers:
            return SniffResult(False, 0, "Could not extract headers", self.label)

        if not self.required_headers:
            return SniffResult(False, 0, "Importer has no required_headers", self.label)

        h = {x.lower() for x in headers}
        req = {x.lower() for x in self.required_headers}
        match = len(h & req)

        # threshold: require at least 4 matches, or all if fewer than 4 required
        need = min(4, len(req))
        ok = match >= need

        return SniffResult(ok, match, f"Matched {match}/{len(req)} required header(s)", self.label)

    # ---------- parse contract ----------
    def parse(self, *, text: str) -> list[dict]:
        """Return normalized rows: date,time,merchant,amount,currency,in_out,notes,description"""
        raise NotImplementedError

    # convenience
    def parse_raw(self, *, raw: bytes, filename: str = "") -> list[dict]:
        return self.parse(text=self.decode(raw))
