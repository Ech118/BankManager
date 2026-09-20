"""Tickers whose company_tickers.json CIK is not where the history lives.

SEC's ticker map points at the CURRENT registrant. After a holding-company
reorganisation the ticker moves to a newly-formed CIK that has filed almost
nothing, while every 10-K remains under the predecessor. Resolving the ticker
normally then yields a company with no annual history, and the scope check
correctly - but uselessly - calls it unsupported.

Found by `python -m data.record.cik_history`, which resolves the largest US
companies and reports any whose CIK holds fewer than two annual 10-Ks. Add a
row here, with the evidence, rather than special-casing a ticker anywhere else.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CikOverride:
    """Where a ticker's filing history actually lives."""

    cik: str
    reason: str
    mapped_cik: str | None = None


CIK_OVERRIDES: dict[str, CikOverride] = {
    "XOM": CikOverride(
        cik="0000034088",
        mapped_cik="0002115436",
        reason=(
            "company_tickers.json maps XOM to ExxonMobil Holdings Corp (CIK 2115436), "
            "a holding company first registered in 2026 with no 10-K and 76KB of XBRL. "
            "Exxon Mobil Corp (CIK 34088) holds the filing history."
        ),
    ),
}
"""ticker -> the CIK that holds the filings. Checked before the SEC map."""


def override_for(ticker: str) -> CikOverride | None:
    """The override for `ticker`, or None when the SEC map is right."""
    return CIK_OVERRIDES.get((ticker or "").strip().upper().replace(".", "-"))
