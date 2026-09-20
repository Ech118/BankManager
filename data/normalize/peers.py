"""Choose comparable companies: same industry, nearest size, in scope.

Specified by docs/mcp-tools.md#get_peer_companies and docs/data-model.md.

Peer choice moves a relative valuation more than almost any other input, and
peer multiples are the weakest data the system carries (plan review, error E).
So the default list is DETERMINISTIC and every entry says why it was chosen.
The Valuation Agent may override it, but has to record a reason of its own.

THE PIPELINE
    1. The target's SIC, from its own SEC submissions.
    2. Everyone else filing 10-Ks under that SIC, from browse-edgar.
    3. Each candidate's revenue for the last closed fiscal year, from the XBRL
       frames API - ONE request for the whole industry, not one per company.
    4. Rank by size distance in LOG space, keep the closest that pass
       `check_scope`.
    5. Too few? Relax the size cutoff and take the next nearest.
    6. Still too few? Fall back to the market provider's own peer list.

WHY NOT "WIDEN TO THE TWO-DIGIT SIC PREFIX"
    Because browse-edgar does not support it. `SIC=35` returns ZERO rows - it is
    read as an unknown code, not as a wildcard over 3571, 3572 and the rest -
    so a widening step built on it would look correct, never fire, and quietly
    leave every short peer set short.

    Widening the SIZE tolerance achieves what the prefix was meant to: more
    candidates, drawn from the same industry rather than a neighbouring one, and
    labelled so the Valuation Agent can see the set was stretched. The
    alternative - enumerating the 4-digit codes under a prefix - needs a static
    copy of SEC's SIC taxonomy, which is one more thing to maintain and go
    stale.

WHY LOG DISTANCE AND NOT A PERCENTAGE BAND
    A fixed band ("within 50% of revenue") returns nothing for a company at the
    top or bottom of its industry - which is exactly where the interesting
    companies are. Log distance asks "how many times bigger or smaller", which
    is how an analyst actually thinks about comparability, and always returns
    the nearest candidates whether or not anything is close.

WHY THE MULTIPLES COME BACK UNAVAILABLE
    `Peer` carries pe, ev_ebitda, ev_revenue and fcf_yield. Every one of them is
    a RATIO, and P1 does not compute ratios - that is calc/ (ADR 0001). Filling
    them here would put valuation arithmetic in the data layer, where no
    sensitivity grid and no lineage would ever see it. They are returned
    `unavailable` with the market cap that calc/ needs to compute them.

POINT IN TIME
    The frames API has no `as_of`: it serves the current value for a period. The
    period this module asks for is the last fiscal year that CLOSED before
    `as_of`, so a backtest ranks peers on a year that had been reported by then.
    It does not reproduce the exact figures as first filed, and peer ranking is
    not sensitive at that resolution - a restatement moves a company's revenue a
    few percent, and ranking is by order of magnitude.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from data.ingest import edgar_client, market_client
from schema.contracts.common import ISODate, Ticker, ValueObject
from schema.contracts.enums import Unit, ValueStatus, ValueType
from schema.contracts.market import Peer

MIN_PEERS = 4
"""Below this the SIC is widened. Three comparables is not a peer set; it is
three companies, and a median over them is noise that reads as a number."""

DEFAULT_LIMIT = 6

MAX_LOG_DISTANCE = 1.3
"""About 20x. Past this a candidate is not a comparable, and including it to
reach a target count makes the peer median worse, not better.

Measured, not guessed. Ranking AAPL by SIC 3571 alone returns Dell at 3.7x and
then Omnicell at 351x, One Stop Systems at 12,918x and Socket Mobile at
27,600x - a $4B company and a $200M one in the same "peer set" as Apple. A
median over that is noise that reads as a number, which is worse than a short
list, because a short list is visible as a data-quality gap and a bad median is
not."""

MAX_CANDIDATES = 100
"""browse-edgar's page cap."""

CANDIDATE_PAGES = 4
"""Up to 400 candidates. Not a nicety: browse-edgar orders a SIC by neither size
nor relevance, and SIC 6021 puts Bank of America on page 1, Citigroup on page 2
and Wells Fargo on neither. One page misses the very companies a bank's peer set
exists to contain. Four pages is four cached requests a day per industry."""

WIDENED_LOG_DISTANCE = 2.0
"""100x, used only when the strict cutoff left fewer than MIN_PEERS. A 100x
spread is a bad peer set and is labelled as one, but it beats a median over two
companies, and the reason string says which happened."""

REVENUE_CONCEPTS: tuple[str, ...] = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "RevenuesNetOfInterestExpense",
)
"""Tried in this order, which is the head of the revenue chain in
concept_map.py. Merged rather than picked: most filers tag the first, older and
non-ASC-606 filers tag `Revenues`, and asking for only one loses half an
industry (docs/sec-pitfalls.md 4).

`RevenuesNetOfInterestExpense` is here for banks, which mostly tag nothing else
- its CY2025 frame holds 42 companies against tens of thousands. Without it a
bank's whole industry is missing a revenue, every candidate is dropped for
having none, and the SIC ranking silently returns nothing."""


def unavailable(unit: Unit) -> ValueObject:
    """A multiple P1 is not allowed to compute."""
    return ValueObject(value=None, unit=unit, type=ValueType.FACT, status=ValueStatus.UNAVAILABLE)


@dataclass
class PeerResult:
    peers: list[Peer] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


def frame_period(as_of: ISODate | None) -> str:
    """The last calendar year that had closed before `as_of`.

    Not the current year: a frame for a year still in progress is missing most
    of the industry, and ranking against a half-populated frame silently drops
    every company that has not filed yet.
    """
    year = int(as_of[:4]) if as_of else 2026
    return f"CY{year - 1}"


def industry_revenues(period: str) -> dict[str, float]:
    """cik -> revenue, merged across the revenue concepts.

    First concept that carries a value for a CIK wins, which is the same
    precedence the per-company chain uses. Two concepts for one company are not
    added together: they are alternative taggings of the same quantity, and
    summing them double-counts.
    """
    merged: dict[str, float] = {}
    for concept in REVENUE_CONCEPTS:
        for cik, value in edgar_client.fetch_frame(concept, period).items():
            if cik not in merged and value > 0:
                merged[cik] = value
    return merged


def size_distance(candidate_revenue: float, target_revenue: float) -> float:
    """How many orders of magnitude apart two companies are. Symmetric."""
    return abs(math.log10(candidate_revenue) - math.log10(target_revenue))


def _ticker_for(cik: str, cik_to_ticker: dict[str, str]) -> str | None:
    return cik_to_ticker.get(cik.zfill(10))


def primary_tickers(ticker_map: dict[str, str]) -> dict[str, str]:
    """cik -> the company's PRIMARY ticker, inverting SEC's ticker -> cik map.

    One CIK often has several tickers: common stock, preferred series, warrants.
    Inverting naively keeps whichever the iteration happened to end on, which is
    how a peer set ends up quoting `SMCIP` (a Super Micro preferred) and
    `BSQKZ` instead of the common stock everybody actually values. A market cap
    read against a thinly traded preferred listing is not the company's.

    SEC lists the primary listing first, so first-seen wins; length breaks a tie,
    because a suffixed ticker is the derivative instrument (SMCIP vs SMCI).
    """
    out: dict[str, str] = {}
    for tick, cik in ticker_map.items():
        padded = cik.zfill(10)
        current = out.get(padded)
        if current is None or len(tick) < len(current):
            out[padded] = tick
    return out


def rank_candidates(
    ciks: list[str],
    *,
    target_cik: str,
    target_revenue: float | None,
    revenues: dict[str, float],
    cik_to_ticker: dict[str, str],
) -> list[tuple[str, str, float, float]]:
    """(ticker, cik, revenue, distance), nearest in size first.

    A candidate missing from the frame is DROPPED, not ranked last: a January
    year end is absent from a calendar frame, and treating absent as zero would
    rank the biggest company in an industry as its smallest.
    """
    ranked: list[tuple[str, str, float, float]] = []
    for cik in ciks:
        padded = cik.zfill(10)
        if padded == target_cik.zfill(10):
            continue
        revenue = revenues.get(padded)
        if not revenue:
            continue
        ticker = _ticker_for(padded, cik_to_ticker)
        if not ticker:
            continue
        distance = size_distance(revenue, target_revenue) if target_revenue else 0.0
        ranked.append((ticker, padded, revenue, distance))
    # Ticker breaks ties so the list is stable across runs.
    ranked.sort(key=lambda row: (row[3], row[0]))
    return ranked


def _peer(
    ticker: str,
    *,
    sic: str | None,
    reason: str,
    market_cap: float | None,
    company_name: str | None = None,
) -> Peer:
    cap = (
        ValueObject(
            value=market_cap,
            unit=Unit.USD,
            type=ValueType.FACT,
            status=ValueStatus.OK,
            source_id=f"src:market:{ticker}:profile",
        )
        if market_cap
        else unavailable(Unit.USD)
    )
    return Peer(
        ticker=ticker,
        company_name=company_name,
        sic=sic,
        market_cap=cap,
        # Ratios are calc/'s, not P1's (ADR 0001).
        pe=unavailable(Unit.MULTIPLE),
        ev_ebitda=unavailable(Unit.MULTIPLE),
        ev_revenue=unavailable(Unit.MULTIPLE),
        fcf_yield=unavailable(Unit.FRACTION),
        selection_reason=reason,
    )


def _in_scope(ticker: str, as_of: ISODate | None) -> bool:
    from data.normalize import scope as scope_rules

    try:
        return bool(scope_rules.check_scope(ticker, as_of).in_scope)
    except Exception:
        # An unresolvable candidate is not a peer. It is also not an error:
        # browse-edgar lists registrants that no longer trade.
        return False


def select(
    ticker: Ticker,
    *,
    as_of: ISODate | None,
    sic: str | None,
    target_cik: str,
    target_revenue: float | None,
    limit: int = DEFAULT_LIMIT,
) -> PeerResult:
    """The deterministic default peer set for one company."""
    gaps: list[str] = []
    if not sic:
        gaps.append(
            f"{ticker}: SEC reports no SIC code, so peers cannot be selected by "
            "industry. Relative valuation has no comparable set."
        )
        return PeerResult([], gaps)

    period = frame_period(as_of)
    revenues = industry_revenues(period)
    if not revenues:
        gaps.append(
            f"{ticker}: the XBRL frames API returned no revenue data for {period}, "
            "so peers cannot be ranked by size."
        )

    cik_to_ticker = primary_tickers(edgar_client.fetch_ticker_map())

    candidates = edgar_client.fetch_sic_companies(
        sic, count=MAX_CANDIDATES, pages=CANDIDATE_PAGES
    )
    ranked = rank_candidates(
        candidates,
        target_cik=target_cik,
        target_revenue=target_revenue,
        revenues=revenues,
        cik_to_ticker=cik_to_ticker,
    )

    chosen: list[Peer] = []
    seen: set[str] = set()
    for cutoff, widened in ((MAX_LOG_DISTANCE, False), (WIDENED_LOG_DISTANCE, True)):
        if len(chosen) >= MIN_PEERS:
            break
        for peer_ticker, _cik, revenue, distance in ranked:
            if len(chosen) >= limit:
                break
            if target_revenue and distance > cutoff:
                # Ranked nearest-first, so everything after this is further.
                break
            if peer_ticker in seen or peer_ticker == ticker:
                continue
            if not _in_scope(peer_ticker, as_of):
                continue
            seen.add(peer_ticker)
            scale = (
                f"{10 ** distance:.1f}x apart on {period} revenue"
                if target_revenue
                else f"{period} revenue ${revenue:,.0f}"
            )
            reason = f"SIC {sic}; {scale}" + (
                "; size cutoff relaxed for lack of closer matches" if widened else ""
            )
            chosen.append(
                _peer(peer_ticker, sic=sic, reason=reason, market_cap=_market_cap(peer_ticker))
            )
        if not widened and len(chosen) < MIN_PEERS:
            gaps.append(
                f"{ticker}: only {len(chosen)} in-scope companies file under SIC {sic} "
                f"within {10 ** MAX_LOG_DISTANCE:.0f}x of its revenue, so the size "
                f"cutoff was relaxed to {10 ** WIDENED_LOG_DISTANCE:.0f}x. Peer "
                "multiples across that spread compare different businesses."
            )

    if len(chosen) < MIN_PEERS:
        chosen.extend(_provider_fallback(ticker, as_of, limit - len(chosen), seen))

    if len(chosen) < MIN_PEERS:
        gaps.append(
            f"{ticker}: only {len(chosen)} comparable companies of similar size could "
            f"be identified. A peer median over fewer than {MIN_PEERS} companies is "
            "noise that reads as a number; treat relative valuation as weak here."
        )
    return PeerResult(chosen[:limit], gaps)


def _provider_fallback(
    ticker: Ticker, as_of: ISODate | None, room: int, seen: set[str]
) -> list[Peer]:
    """Finnhub's own peer list, used only when SIC+frames came up short.

    Last because it is opaque: the provider does not say why two companies are
    comparable, so the selection_reason can only name the provider. A peer whose
    reason is "a vendor said so" is worth having when the alternative is three
    peers, and worth ranking below one whose reason is a SIC code and a revenue.
    """
    if room <= 0:
        return []
    try:
        candidates = market_client.get_client().peers(ticker)
    except Exception:
        return []

    out: list[Peer] = []
    for candidate in candidates:
        if len(out) >= room:
            break
        normalized = edgar_client.normalize_ticker(candidate)
        if normalized in seen or normalized == ticker:
            continue
        if not _in_scope(normalized, as_of):
            continue
        seen.add(normalized)
        out.append(
            _peer(
                normalized,
                sic=None,
                reason=(
                    "Market data provider's peer list; too few in-scope companies "
                    "share this SIC code to rank by size."
                ),
                market_cap=_market_cap(normalized),
            )
        )
    return out


def _market_cap(ticker: str) -> float | None:
    """The provider's own market cap: it covers every share class, which a
    cover-page share count does not (data/normalize/shares.py)."""
    try:
        profile = market_client.get_client().profile(ticker)
    except Exception:
        return None
    return getattr(profile, "market_cap", None)
