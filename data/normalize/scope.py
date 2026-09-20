"""check_scope: which companies this pipeline is honest about.

Specified by docs/sec-pitfalls.md "Sector scope" (plan review error H).

v1 covers non-financial operating companies with positive revenue. Banks,
insurers and REITs break the FCF and enterprise-value logic the whole valuation
rests on: a bank's "capex" is meaningless, and net debt is not a liability to be
subtracted but the raw material of the business. Producing a confident-looking
verdict for one is worse than refusing.

Rejection returns a human-readable reason, never a bare False.

THREE OUTCOMES, NOT TWO
    supported    a US operating company filing 10-Ks under us-gaap.
    partial      the data loads but some of it is missing or does not mean what
                 the model assumes. The run proceeds with the reason attached as
                 a data_quality gap, so the report can say what it cannot see.
    unsupported  nothing honest can be produced. in_scope is False.

    `Scope` itself carries `in_scope` and `reason`; `level` and `gaps` ride in
    its extra fields, so no contract change is needed to express the middle
    case.

WHAT THE REAL FILERS SHOWED
    JPM   SIC 6021. No OperatingIncomeLoss, no capex tag at all, and operating
          cash flow of -147.8B in FY2025. Every margin the model wants is absent
          rather than wrong, which is the good failure.
    O     SIC 6798 (REIT). No operating income, no gross profit; its debt is
          tagged NotesPayable, not LongTermDebt.
    TSM   Files 20-F. Its companyfacts has dei, ifrs-full and srt - no us-gaap
          node exists, so a us-gaap concept map returns NOTHING, not less.
    XOM   Resolves to a 2026 holding company with zero 10-Ks; the history is
          under a different CIK (data/ingest/ticker_overrides.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from data.normalize import concept_map, to_facts
from data.normalize.concept_map import US_GAAP
from schema.contracts.common import ISODate, Scope, Ticker

EXCLUDED_SIC_RANGES: tuple[tuple[int, int, str], ...] = (
    (6000, 6499, "banks, brokers and insurers"),
    (6500, 6599, "real estate and REITs"),
    (6700, 6799, "holding and investment offices"),
)
"""SIC ranges whose accounting the FCF/EV model does not describe."""

FOREIGN_ANNUAL_FORMS: frozenset[str] = frozenset({"20-F", "40-F"})
"""Annual reports of a foreign private issuer. Usually IFRS, never a 10-K."""

TICKER_PATTERN = r"^[A-Z]{1,5}([.-][A-Z])?$"
"""Input allow-list. Also the first line of defence against injection (error F)."""

MIN_ANNUAL_FILINGS = 2
"""Fewer than two annual periods means no year-over-year anything."""

_TICKER_RE = re.compile(TICKER_PATTERN)


class ScopeLevel(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass
class ScopeResult:
    """A scope decision with its reason and any data-quality consequences."""

    level: ScopeLevel
    reason: str | None = None
    gaps: list[str] = field(default_factory=list)

    @property
    def in_scope(self) -> bool:
        return self.level is not ScopeLevel.UNSUPPORTED

    def to_scope(self) -> Scope:
        """The contract model, with the extra detail in its extra fields."""
        return Scope(
            in_scope=self.in_scope,
            reason=self.reason,
            level=self.level.value,
            gaps=list(self.gaps),
        )

    def to_dict(self) -> dict:
        return self.to_scope().model_dump(mode="json")


def sic_reason(sic: str | None) -> str | None:
    """Human-readable rejection reason for an excluded SIC code, else None."""
    if not sic:
        return None
    try:
        code = int(str(sic).strip())
    except ValueError:
        return None
    for low, high, label in EXCLUDED_SIC_RANGES:
        if low <= code <= high:
            return (
                f"SIC {code} ({label}): free cash flow and enterprise value do not "
                "describe this balance sheet, so valuation output is partial."
            )
    return None


def annual_period_count(companyfacts: dict, as_of: ISODate | None = None) -> int:
    """Distinct annual 10-K fiscal periods visible at `as_of`.

    Counted from companyfacts, never from `filings.recent`: that array is a
    ~1000-filing window, and JPM's holds one single 10-K across 26,190 rows.
    """
    entries: list[dict] = []
    for metric in to_facts.ANCHOR_METRICS:
        for concept in concept_map.candidates(metric, US_GAAP):
            entries.extend(to_facts.annual_entries(companyfacts, concept, US_GAAP, as_of))
    return len({e["end"] for e in entries})


def classify(
    ticker: Ticker,
    submissions: dict | None,
    companyfacts: dict | None,
    as_of: ISODate | None = None,
) -> ScopeResult:
    """Decide what this pipeline can honestly say about `ticker`.

    Pure: takes the payloads rather than fetching them, so every branch is
    testable against recorded SEC responses.
    """
    if not _TICKER_RE.match(ticker or ""):
        return ScopeResult(ScopeLevel.UNSUPPORTED, f"Invalid ticker format: {ticker!r}")

    if not submissions and not companyfacts:
        return ScopeResult(
            ScopeLevel.UNSUPPORTED,
            f"{ticker} is not in SEC's company_tickers.json. It may be a non-US "
            "listing, an ADR, or delisted.",
        )

    submissions = submissions or {}
    companyfacts = companyfacts or {}
    gaps: list[str] = []

    taxonomies = set((companyfacts.get("facts") or {}).keys())
    forms = set((submissions.get("filings", {}).get("recent", {}) or {}).get("form") or [])
    foreign_forms = sorted(forms & FOREIGN_ANNUAL_FORMS)

    if foreign_forms or (taxonomies and US_GAAP not in taxonomies):
        detail = (
            f"files {', '.join(foreign_forms)}"
            if foreign_forms
            else f"reports under {', '.join(sorted(taxonomies)) or 'no known taxonomy'}"
        )
        reason = (
            f"{ticker} is a foreign private issuer ({detail}). Only us-gaap concepts "
            "are mapped, so financial data is unavailable rather than reduced."
        )
        return ScopeResult(ScopeLevel.PARTIAL, reason, [reason])

    periods = annual_period_count(companyfacts, as_of)
    if periods < MIN_ANNUAL_FILINGS:
        return ScopeResult(
            ScopeLevel.UNSUPPORTED,
            f"{ticker} has {periods} annual 10-K period(s) of XBRL data"
            f"{f' on or before {as_of}' if as_of else ''}, fewer than the "
            f"{MIN_ANNUAL_FILINGS} needed for any year-over-year comparison. "
            "A recent IPO, a newly registered holding company, or a filer that "
            "reports under another CIK.",
        )

    sector = sic_reason(submissions.get("sic"))
    if sector:
        description = submissions.get("sicDescription") or ""
        reason = f"{ticker}: {sector}" + (f" [{description}]" if description else "")
        gaps.append(reason)
        return ScopeResult(ScopeLevel.PARTIAL, reason, gaps)

    return ScopeResult(ScopeLevel.SUPPORTED, None, gaps)


def check_scope(ticker: Ticker, as_of: ISODate | None = None) -> Scope:
    """Live scope check: resolve the ticker, fetch what it needs, classify.

    Raises nothing for an unknown ticker - "not an SEC filer" is a real answer.
    """
    from data.ingest import companyfacts as companyfacts_api
    from data.ingest import edgar_client

    if not _TICKER_RE.match(ticker or ""):
        return ScopeResult(ScopeLevel.UNSUPPORTED, f"Invalid ticker format: {ticker!r}").to_scope()

    try:
        cik = edgar_client.lookup_cik(ticker)
    except KeyError:
        return classify(ticker, None, None, as_of).to_scope()

    submissions = edgar_client.fetch_submissions(cik)
    facts = companyfacts_api.fetch_companyfacts(cik)
    return classify(ticker, submissions, facts, as_of).to_scope()
