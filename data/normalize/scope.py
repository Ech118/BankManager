"""check_scope: which companies this pipeline is honest about.

Specified by docs/sec-pitfalls.md "Sector scope" (plan review error H).

v1 covers non-financial operating companies with positive revenue. Banks,
insurers and REITs break the FCF and enterprise-value logic the whole valuation
rests on: a bank's "capex" is meaningless, and net debt is not a liability to be
subtracted but the raw material of the business. Producing a confident-looking
verdict for one is worse than refusing.

Rejection returns a human-readable reason, never a bare False.

TODO(roadmap Step 1, P1).
"""

from __future__ import annotations

from schema.contracts.common import ISODate, Scope, Ticker

EXCLUDED_SIC_RANGES: tuple[tuple[int, int, str], ...] = (
    (6000, 6499, "banks, brokers and insurers"),
    (6500, 6599, "real estate and REITs"),
    (6700, 6799, "holding and investment offices"),
)
"""SIC ranges whose accounting the FCF/EV model does not describe."""

TICKER_PATTERN = r"^[A-Z]{1,5}([.-][A-Z])?$"
"""Input allow-list. Also the first line of defence against injection (error F)."""


def check_scope(ticker: Ticker, as_of: ISODate | None = None) -> Scope:
    """Decide whether this pipeline can honestly analyse `ticker`.

    Checks, in order: ticker shape, SIC exclusion, and positive revenue in the
    latest reported year (a pre-revenue company has no meaningful multiple).
    """
    raise NotImplementedError("TODO(roadmap Step 1, P1)")


def sic_reason(sic: str) -> str | None:
    """Human-readable rejection reason for an excluded SIC code, else None."""
    raise NotImplementedError("TODO(roadmap Step 1, P1)")
