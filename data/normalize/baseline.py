"""The S&P 500 baseline: what the index costs, so relative valuation has a zero.

Specified by `schema.contracts.factsheet.SP500Baseline`. The verdict is
"beats the S&P 500 or not", so without this the whole question has no reference
point and every multiple is an absolute number with nothing to be compared to.

THREE OF THE FOUR FIELDS ARE ASSUMPTIONS, AND SAY SO
    `forward_pe`, `earnings_yield` and `risk_free_rate` are forward-looking
    index-level figures. No free data provider serves them: Finnhub's free tier
    has /quote, /stock/profile2, /stock/peers and /company-news, none of which
    carries index forward earnings.

    So they are configured constants, typed `assumption` - which is exactly what
    the contract means by that word ("a chosen constant: discount rate, terminal
    growth, exit multiple"), and what makes them render in the report as a
    chosen input rather than as something we measured. Each carries the date it
    was last reviewed and a one-line rationale, so a stale number is visible
    rather than silently authoritative.

    The alternative - leaving them `unavailable` - is worse. The baseline is an
    input to a comparison that the run must make either way, and an unavailable
    baseline pushes the constant into an agent's head, where it is neither
    recorded nor reviewable. A wrong number we can see beats a wrong number we
    cannot.

WHAT IS ACTUALLY MEASURED
    `spy_price` and `spy_previous_close`, from Finnhub /quote for SPY, typed
    `fact` with a market source_id. They are the one part of this object that is
    observed rather than chosen.

WHY SPY AND NOT "THE S&P 500 LEVEL"
    SPY is an ETF that tracks the index at roughly a tenth of its level. The
    tempting move is to multiply by ten and call it the index; that is a
    fabricated number with a plausible magnitude, which is the worst kind. The
    price is reported as what it is - SPY's - and named accordingly.

NEVER UNFILLED
    Every field is populated on every path. A provider outage costs the two
    measured fields (they degrade to `unavailable` plus a gap); the assumptions
    do not depend on the network at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from data.normalize import snapshot as snapshot_rules
from schema.contracts.common import ISODate, ISOTimestamp, SourceRef, ValueObject
from schema.contracts.enums import Unit, ValueStatus, ValueType
from schema.contracts.factsheet import SP500Baseline

SPY = "SPY"
"""The tradeable proxy. `check_scope` never sees this ticker - the baseline is
fetched directly, not through the company path."""

ASSUMPTIONS_REVIEWED = "2026-09-20"
"""When a human last looked at the three constants below. Shown in the report
next to them, so an old baseline is visible rather than quietly authoritative."""

ASSUMPTIONS_VERSION = "2026.09"
"""Bumped whenever a constant changes. It is part of the source_id, so two runs
with different baselines cite different sources rather than the same one."""

FORWARD_PE = 22.0
"""S&P 500 forward P/E on next-twelve-month bottom-up consensus earnings.
Reviewed 2026-09-20. Above the ~16.5 twenty-year mean, as it has been for most
of the last decade; the index is more weighted to software and semis than that
mean reflects."""

EARNINGS_YIELD = 0.0455
"""The reciprocal of FORWARD_PE, as a fraction: 1 / 22.0 = 0.04545...

Stored as its own constant rather than computed from FORWARD_PE because P1 does
not do arithmetic on financial quantities - that is calc/'s job (ADR 0001).
`test_baseline_assumptions_are_mutually_consistent` fails if the two drift
apart, so the duplication cannot rot silently."""

RISK_FREE_RATE = 0.0425
"""10-year US Treasury constant-maturity yield, as a fraction. Reviewed
2026-09-20.

This is the one genuinely observable figure of the three - FRED's DGS10 series
serves it, and `SourceRef.kind` already allows `fred`. It is a constant here
because wiring a second provider was not worth doing before the baseline is
consumed. Moving it to FRED changes this module and nothing else."""

CONFIG_SOURCE_ID = f"src:config:sp500_baseline:{ASSUMPTIONS_VERSION}"
MARKET_SOURCE_PREFIX = "src:market"


@dataclass
class BaselineResult:
    """The baseline, plus what it could not measure and where it came from."""

    baseline: SP500Baseline
    gaps: list[str] = field(default_factory=list)
    sources: dict[str, SourceRef] = field(default_factory=dict)


def _assumption(value: float, unit: Unit) -> ValueObject:
    return ValueObject(
        value=value,
        unit=unit,
        type=ValueType.ASSUMPTION,
        status=ValueStatus.OK,
        source_id=CONFIG_SOURCE_ID,
    )


def _measured(value: float, source_id: str) -> ValueObject:
    return ValueObject(
        value=value,
        unit=Unit.USD_PER_SHARE,
        type=ValueType.FACT,
        status=ValueStatus.OK,
        source_id=source_id,
    )


def _unavailable(unit: Unit) -> ValueObject:
    return ValueObject(
        value=None, unit=unit, type=ValueType.FACT, status=ValueStatus.UNAVAILABLE
    )


def source_id_for(observed_at: ISOTimestamp) -> str:
    """src:market:SPY:<timestamp>, matching snapshot.py's convention."""
    stamp = observed_at.replace(":", "").replace("-", "")
    return f"{MARKET_SOURCE_PREFIX}:{SPY}:{stamp}"


def build(
    *,
    as_of: ISODate,
    quote,
    retrieved_at: ISOTimestamp,
) -> BaselineResult:
    """Assemble the baseline. `quote` is a SPY Quote, or None if the fetch failed."""
    sources: dict[str, SourceRef] = {
        CONFIG_SOURCE_ID: SourceRef(
            kind="config",
            url=None,
            accession=None,
            fetched_at=retrieved_at,
        )
    }
    gaps: list[str] = []

    extra: dict[str, ValueObject] = {}
    price = getattr(quote, "price", None)
    if price:
        observed_at = snapshot_rules.observed_timestamp(
            getattr(quote, "observed_at", None), as_of
        )
        market_source_id = source_id_for(observed_at)
        extra["spy_price"] = _measured(float(price), market_source_id)
        previous_close = getattr(quote, "previous_close", None)
        if previous_close:
            extra["spy_previous_close"] = _measured(float(previous_close), market_source_id)
        sources[market_source_id] = SourceRef(
            kind="market",
            url="https://finnhub.io/api/v1/quote?symbol=SPY",
            accession=None,
            fetched_at=observed_at,
        )
    else:
        extra["spy_price"] = _unavailable(Unit.USD_PER_SHARE)
        gaps.append(
            "SPY: no price available from the market data provider. The S&P 500 "
            "baseline still carries its forward P/E, earnings yield and risk-free "
            "rate, which are configured assumptions and do not depend on the quote."
        )

    baseline = SP500Baseline(
        forward_pe=_assumption(FORWARD_PE, Unit.MULTIPLE),
        earnings_yield=_assumption(EARNINGS_YIELD, Unit.FRACTION),
        risk_free_rate=_assumption(RISK_FREE_RATE, Unit.FRACTION),
        as_of=as_of,
        assumptions_reviewed=ASSUMPTIONS_REVIEWED,
        assumptions_version=ASSUMPTIONS_VERSION,
        **extra,
    )
    return BaselineResult(baseline=baseline, gaps=gaps, sources=sources)
