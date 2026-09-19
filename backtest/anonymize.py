"""Anonymizer for the point-in-time backtest (plan.txt error A, the "BIGGEST
FLAW": the LLM's training data runs past any 2020-2023 filing, so it may
already "know" what happened next. Strip company name/ticker/dates so a
backtest result can't be won by recognizing the company).

This is intentionally a regex-level anonymizer, not an NER model: it strips
the company name, the ticker, and absolute dates/years, replacing dates with
period markers RELATIVE to the filing's as_of date (plan.txt 14.A: "relative
periods only"). It cannot catch every product name a filing might mention -
that is a documented limitation, not a silent gap (see backtest/README.md).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Callable

ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTH_NAME_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+(\d{4})\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _relative_year_label(year: int, as_of_year: int) -> str:
    delta = year - as_of_year
    if delta == 0:
        return "[T]"
    sign = "+" if delta > 0 else ""
    return f"[T{sign}{delta}y]"


def build_redactor(company_name: str, ticker: str, as_of: str) -> Callable[[str], str]:
    """Return redact(text) -> text for one ticker/as_of, per plan.txt error A
    ("anonymize company name/dates in backtest prompts") and the
    orchestrator.api.run_analysis(redact=...) contract (plan.txt 15.8)."""
    as_of_year = int(as_of[:4]) if as_of and re.match(r"^\d{4}", as_of) else datetime.utcnow().year

    name_pattern = re.escape(company_name.strip()) if company_name else None
    # Also strip a bare "Acme Corporation" -> "Acme" style short form, and the
    # ticker as a standalone word (e.g. "$ACME" or "ACME shares").
    short_name = company_name.split(" (")[0].strip() if company_name else None

    def redact(text: str) -> str:
        if not text:
            return text
        out = text
        if name_pattern:
            out = re.sub(name_pattern, "[COMPANY]", out, flags=re.IGNORECASE)
        if short_name and short_name != company_name:
            out = re.sub(re.escape(short_name), "[COMPANY]", out, flags=re.IGNORECASE)
        if ticker:
            out = re.sub(rf"\b{re.escape(ticker)}\b", "[TICKER]", out)

        def _iso(m: re.Match) -> str:
            return _relative_year_label(int(m.group(1)), as_of_year)

        out = ISO_DATE_RE.sub(_iso, out)

        def _month_name(m: re.Match) -> str:
            return _relative_year_label(int(m.group(2)), as_of_year)

        out = MONTH_NAME_RE.sub(_month_name, out)

        def _year(m: re.Match) -> str:
            return _relative_year_label(int(m.group(0)), as_of_year)

        out = YEAR_RE.sub(_year, out)
        return out

    return redact
