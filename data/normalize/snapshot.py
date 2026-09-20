"""Build a MarketSnapshot: price, shares and the EV bridge at ONE instant.

Specified by docs/data-model.md "Market data" and docs/sec-pitfalls.md 8.

WHY ONE TIMESTAMP FOR THE WHOLE BUNDLE
    Mixing a live price with last quarter's share count corrupts market cap and
    therefore every multiple built on it. The contract puts `as_of` on the
    snapshot rather than on each field precisely so the two cannot drift, and
    this module never assembles a snapshot from parts observed at different
    moments without saying so.

WHAT DEGRADES, AND HOW
    Nothing here raises because a provider is down. Each field becomes an
    `unavailable` ValueObject with a data_quality gap naming what is missing:

      price unavailable        -> market cap and enterprise value follow
      shares unresolvable      -> market cap and enterprise value follow
      cash or debt unavailable -> enterprise value follows

    A partial snapshot is useful (a bank still has a price); a snapshot with an
    invented number in it is not.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from data.normalize import shares as shares_rules
from schema.contracts.common import ISODate, ISOTimestamp, Ticker, ValueObject
from schema.contracts.enums import Unit, ValueStatus, ValueType
from schema.contracts.facts import FinancialFact
from schema.contracts.market import MarketSnapshot

MARKET_SOURCE_PREFIX = "src:market"


def unavailable(unit: Unit, *, derived_from: list[str] | None = None) -> ValueObject:
    """Missing data, the only way the contract allows it to be expressed."""
    return ValueObject(
        value=None,
        unit=unit,
        type=ValueType.FACT,
        status=ValueStatus.UNAVAILABLE,
        derived_from=derived_from or [],
    )


def ok(
    value: float,
    unit: Unit,
    *,
    source_id: str | None = None,
    derived_from: list[str] | None = None,
) -> ValueObject:
    return ValueObject(
        value=value,
        unit=unit,
        type=ValueType.FACT,
        status=ValueStatus.OK,
        source_id=source_id,
        derived_from=derived_from or [],
    )


def source_id_for(ticker: Ticker, observed_at: ISOTimestamp) -> str:
    """src:market:<TICKER>:<timestamp>, matching the SourceId pattern."""
    return f"{MARKET_SOURCE_PREFIX}:{ticker}:{observed_at.replace(':', '').replace('-', '')}"


def _timestamp(epoch_seconds: int | None) -> ISOTimestamp:
    moment = (
        dt.datetime.fromtimestamp(epoch_seconds, dt.UTC)
        if epoch_seconds
        else dt.datetime.now(dt.UTC)
    )
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _cap_as_of(as_of: ISODate | None, observed_at: ISOTimestamp) -> ISOTimestamp:
    """Never claim an observation from after the run's cutoff (ADR 0003).

    A quote is always "now", so for a backtest the honest timestamp is the end
    of the as_of day, not whenever the provider answered.
    """
    if as_of and observed_at[:10] > as_of:
        return f"{as_of}T23:59:59Z"
    return observed_at


@dataclass
class SnapshotResult:
    snapshot: MarketSnapshot
    gaps: list[str] = field(default_factory=list)


def build(
    ticker: Ticker,
    *,
    as_of: ISODate | None,
    quote,
    profile,
    companyfacts: dict,
    facts: list[FinancialFact],
    retrieved_at: ISOTimestamp,
) -> SnapshotResult:
    """Assemble the snapshot from a quote, a provider profile and the facts."""
    gaps: list[str] = []

    observed_at = _cap_as_of(as_of, _timestamp(getattr(quote, "observed_at", None)))
    source_id = source_id_for(ticker, observed_at)
    price_value = getattr(quote, "price", None)

    if price_value:
        price = ok(float(price_value), Unit.USD_PER_SHARE, source_id=source_id)
    else:
        price = unavailable(Unit.USD_PER_SHARE)
        gaps.append(
            f"{ticker}: no price available from the market data provider. Market "
            "cap, enterprise value and every multiple built on them are unavailable."
        )

    # -- shares ------------------------------------------------------------
    latest_diluted = _latest_fact(facts, "shares_diluted")
    options = shares_rules.candidates(
        companyfacts,
        as_of=as_of,
        diluted=latest_diluted.value if latest_diluted else None,
        diluted_source=_fact_source(latest_diluted),
        provider_shares=getattr(profile, "shares_outstanding", None),
        provider_market_cap=getattr(profile, "market_cap", None),
        price=price_value,
    )
    resolution = shares_rules.resolve(
        price_value, shares_rules.public_float(companyfacts, as_of), options
    )
    share_gap = resolution.gap(ticker)
    if share_gap:
        gaps.append(share_gap)

    if resolution.ok:
        chosen = resolution.candidate
        shares = ok(
            chosen.value,
            Unit.SHARES,
            source_id=source_id if chosen.accession is None else None,
            derived_from=[chosen.concept] if chosen.accession else [],
        )
        shares = shares.model_copy(
            update={
                "xbrl_concept": chosen.concept,
                "accession": chosen.accession,
                "source_url": chosen.source_url,
                "note": chosen.note,
            }
        )
    else:
        shares = unavailable(Unit.SHARES)

    # -- market cap --------------------------------------------------------
    if price.value is not None and shares.value is not None:
        market_cap = ok(
            price.value * shares.value,
            Unit.USD,
            derived_from=["market.price", "market.shares_outstanding"],
        )
    else:
        market_cap = unavailable(
            Unit.USD, derived_from=["market.price", "market.shares_outstanding"]
        )

    # -- the EV bridge, from the truth layer -------------------------------
    cash = _from_fact(facts, "cash", gaps, ticker)
    total_debt = _from_fact(facts, "total_debt", gaps, ticker)

    if market_cap.value is not None and cash.value is not None and total_debt.value is not None:
        enterprise_value = ok(
            market_cap.value + total_debt.value - cash.value,
            Unit.USD,
            derived_from=["market.market_cap", "market.total_debt", "market.cash"],
        )
    else:
        enterprise_value = unavailable(
            Unit.USD, derived_from=["market.market_cap", "market.total_debt", "market.cash"]
        )

    snapshot = MarketSnapshot(
        ticker=ticker,
        as_of=observed_at,
        retrieved_at=retrieved_at,
        source_id=source_id,
        price=price,
        shares_outstanding=shares,
        market_cap=market_cap,
        total_debt=total_debt,
        cash=cash,
        enterprise_value=enterprise_value,
        currency=getattr(quote, "currency", None) or "USD",
    )
    return SnapshotResult(snapshot, gaps)


def _latest_fact(facts: list[FinancialFact], metric: str) -> FinancialFact | None:
    """Newest CURRENT fact for a metric. Prefers a split-adjusted variant."""
    adjusted = [
        f for f in facts if f.metric == f"{metric}_split_adjusted" and f.is_current
    ]
    plain = [f for f in facts if f.metric == metric and f.is_current]
    pool = plain or adjusted
    if not pool:
        return None
    return max(pool, key=lambda f: f.period_end)


def _fact_source(fact: FinancialFact | None) -> dict | None:
    if fact is None:
        return None
    return {
        "accession": fact.accession_number,
        "filed_at": fact.filed_at,
        "source_url": fact.source_url,
    }


def _from_fact(
    facts: list[FinancialFact], metric: str, gaps: list[str], ticker: Ticker
) -> ValueObject:
    """A balance-sheet input to the EV bridge, cited back to its fact."""
    fact = _latest_fact(facts, metric)
    if fact is None or fact.value is None:
        gaps.append(
            f"{ticker}: {metric} is not reported in the latest filing, so "
            "enterprise value cannot be computed."
        )
        return unavailable(Unit.USD)
    value = ok(fact.value, Unit.USD, derived_from=[fact.fact_id])
    return value.model_copy(
        update={"fiscal_period": fact.fiscal_period, "source_url": fact.source_url}
    )
