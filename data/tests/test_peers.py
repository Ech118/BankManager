"""Peer selection, replayed against recorded SEC and provider responses.

Nothing here touches the network: `python -m data.record.peers` captured the
candidate lists, the revenue frame and the provider answers once, and these
tests rank exactly what production would.

Each company is here because it breaks a different plausible implementation:

  NVDA   400 candidates in SIC 3674; the good peers are spread across pages.
  AAPL   SIC 3571 holds Dell and then a $200M company - an unfiltered ranking
         puts Socket Mobile in Apple's peer set.
  KO     PEP is on page 2 of SIC 2080. One page loses the obvious peer.
  JPM    banks tag RevenuesNetOfInterestExpense and nothing else; without it
         the whole industry has no revenue and the ranking returns empty.
  MSFT   one CIK, several tickers: the preferred listing must not win.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from data.normalize import peers as peer_rules
from data.record.peers import load

TICKERS = ["NVDA", "AAPL", "KO", "JPM", "MSFT"]


@dataclass
class FakeProfile:
    market_cap: float | None


class FakeMarketClient:
    """Replays the recorded provider answers."""

    def __init__(self, fixture: dict):
        self._peers = fixture["provider_peers"]
        self._caps = fixture["market_caps"]

    def peers(self, ticker):
        return list(self._peers)

    def profile(self, ticker):
        return FakeProfile(self._caps.get(ticker))

    def quote(self, ticker):
        return None

    def news(self, ticker, start, end):
        return []


@pytest.fixture
def replay(monkeypatch):
    """Point peer selection at a recorded fixture. Returns a select() callable."""

    def go(ticker, *, out_of_scope=(), limit=6):
        fixture = load(ticker)
        monkeypatch.setattr(
            peer_rules.edgar_client,
            "fetch_sic_companies",
            lambda sic, count=100, pages=1: list(fixture["candidates"]),
        )
        monkeypatch.setattr(
            peer_rules,
            "industry_revenues",
            lambda period, sic=None: dict(fixture["revenues"]),
        )
        monkeypatch.setattr(
            peer_rules,
            "industry_net_income",
            lambda period: dict(fixture.get("net_incomes") or {}),
        )
        monkeypatch.setattr(
            peer_rules, "primary_tickers", lambda _map: dict(fixture["tickers"])
        )
        monkeypatch.setattr(peer_rules.edgar_client, "fetch_ticker_map", dict)
        monkeypatch.setattr(
            peer_rules.market_client, "get_client", lambda: FakeMarketClient(fixture)
        )
        excluded = {t.upper() for t in out_of_scope}
        monkeypatch.setattr(
            peer_rules, "_in_scope", lambda tick, as_of: tick.upper() not in excluded
        )
        return fixture, peer_rules.select(
            ticker,
            as_of=fixture["as_of"],
            sic=fixture["sic"],
            target_cik=fixture["target_cik"],
            target_revenue=fixture["target_revenue"],
            limit=limit,
        )

    return go


# --------------------------------------------------------------------------
# the peers are actually the peers
# --------------------------------------------------------------------------
def test_nvda_gets_semiconductor_companies(replay):
    _, result = replay("NVDA")
    chosen = {p.ticker for p in result.peers}
    assert {"AVGO", "AMD"} <= chosen
    assert len(result.peers) >= peer_rules.MIN_PEERS


def test_ko_finds_pepsi_which_is_not_on_the_first_page(replay):
    """browse-edgar orders SIC 2080 by neither size nor relevance. A one-page
    fetch returns Keurig and Constellation but not the obvious comparable."""
    _, result = replay("KO")
    assert "PEP" in {p.ticker for p in result.peers}


def test_jpm_ranks_banks_by_sic_not_by_the_provider(replay):
    """Banks tag RevenuesNetOfInterestExpense and nothing else. Without that
    concept every candidate is dropped for having no revenue."""
    _, result = replay("JPM")
    by_ticker = {p.ticker: p for p in result.peers}
    assert {"BAC", "C"} <= set(by_ticker)
    assert "SIC 6021" in by_ticker["BAC"].selection_reason


def test_no_peer_is_absurdly_far_from_the_target(replay):
    """Apple's SIC holds a $200M company. A peer median including it is noise
    that reads as a number."""
    for ticker in TICKERS:
        _, result = replay(ticker)
        for peer in result.peers:
            reason = peer.selection_reason or ""
            if "x apart" not in reason:
                continue
            multiple = float(reason.split("x apart")[0].split(";")[-1].strip())
            assert multiple <= 10**peer_rules.WIDENED_LOG_DISTANCE, (
                f"{ticker}: {peer.ticker} is {multiple}x apart"
            )


def test_a_preferred_listing_never_replaces_the_common_stock(replay):
    """One CIK, several tickers. Inverting SEC's map naively keeps whichever
    the iteration ended on - SMCIP rather than SMCI - and a market cap read off
    a thinly traded preferred is not the company's."""
    for ticker in TICKERS:
        _, result = replay(ticker)
        for peer in result.peers:
            assert not (len(peer.ticker) == 5 and peer.ticker.endswith(("P", "Z", "W"))), (
                f"{ticker}: {peer.ticker} looks like a preferred or warrant listing"
            )


# --------------------------------------------------------------------------
# what P1 is not allowed to do
# --------------------------------------------------------------------------
def test_the_multiples_come_back_unavailable(replay):
    """pe, ev_ebitda, ev_revenue and fcf_yield are RATIOS. P1 does not compute
    ratios (ADR 0001) - filling them here would hide valuation arithmetic in
    the data layer, where no sensitivity grid would ever see it."""
    _, result = replay("NVDA")
    for peer in result.peers:
        for field in ("pe", "ev_ebitda", "ev_revenue", "fcf_yield"):
            assert getattr(peer, field).status.value == "unavailable", field
            assert getattr(peer, field).value is None, field


def test_the_market_cap_calc_needs_is_filled(replay):
    _, result = replay("NVDA")
    assert any(p.market_cap.status.value == "ok" for p in result.peers)


def test_every_peer_says_why_it_was_chosen(replay):
    """Peer choice moves a valuation more than almost any other input, so the
    Valuation Agent has to be able to argue with it."""
    for ticker in TICKERS:
        _, result = replay(ticker)
        for peer in result.peers:
            assert peer.selection_reason, f"{ticker}: {peer.ticker} has no reason"


# --------------------------------------------------------------------------
# scope, limits and degradation
# --------------------------------------------------------------------------
def test_an_out_of_scope_candidate_is_skipped(replay):
    _, baseline = replay("NVDA")
    first = baseline.peers[0].ticker
    _, result = replay("NVDA", out_of_scope=[first])
    assert first not in {p.ticker for p in result.peers}


def test_the_target_is_never_its_own_peer(replay):
    for ticker in TICKERS:
        _, result = replay(ticker)
        assert ticker not in {p.ticker for p in result.peers}


def test_no_duplicate_peers(replay):
    for ticker in TICKERS:
        _, result = replay(ticker)
        chosen = [p.ticker for p in result.peers]
        assert len(chosen) == len(set(chosen))


def test_limit_is_respected(replay):
    _, result = replay("NVDA", limit=3)
    assert len(result.peers) <= 3


def test_a_short_peer_set_raises_a_data_quality_gap(replay):
    """Fewer peers than MIN_PEERS is a valid answer, but it must be visible:
    a median over two companies is noise that reads as a number."""
    _, result = replay("AAPL", out_of_scope=["DELL", "SMCI", "HPQ", "HPE", "NTAP", "WDC",
                                             "SNDK", "STX", "PSTG", "P", "IONQ", "XRX"])
    if len(result.peers) < peer_rules.MIN_PEERS:
        assert result.gaps
        assert any("comparable companies" in g for g in result.gaps)


def test_no_sic_is_a_gap_not_an_exception():
    result = peer_rules.select(
        "ACME", as_of="2026-09-19", sic=None, target_cik="0000000001",
        target_revenue=1e9, limit=6,
    )
    assert result.peers == []
    assert result.gaps and "SIC" in result.gaps[0]


def test_selection_is_deterministic(replay):
    """Two runs must agree, or a report is not reproducible."""
    _, first = replay("NVDA")
    _, second = replay("NVDA")
    assert [p.ticker for p in first.peers] == [p.ticker for p in second.peers]


# --------------------------------------------------------------------------
# the ranking arithmetic
# --------------------------------------------------------------------------
def test_size_distance_is_symmetric_and_in_orders_of_magnitude():
    assert peer_rules.size_distance(1e9, 1e10) == pytest.approx(1.0)
    assert peer_rules.size_distance(1e10, 1e9) == pytest.approx(1.0)
    assert peer_rules.size_distance(5e9, 5e9) == pytest.approx(0.0)


def test_a_candidate_missing_from_the_frame_is_dropped_not_ranked_last():
    """A January year end is absent from a calendar frame. Treating absent as
    zero ranks the biggest company in an industry as its smallest."""
    ranked = peer_rules.rank_candidates(
        ["0000000002", "0000000003"],
        target_cik="0000000001",
        target_revenue=1e10,
        revenues={"0000000002": 9e9},
        cik_to_ticker={"0000000002": "AAA", "0000000003": "BBB"},
    )
    assert [row[0] for row in ranked] == ["AAA"]


def test_frame_period_is_the_year_before_the_run():
    """A frame for a year still in progress is missing most of the industry."""
    assert peer_rules.frame_period("2026-09-19") == "CY2025"
    assert peer_rules.frame_period("2024-01-02") == "CY2023"


def test_revenue_concepts_are_merged_not_summed(monkeypatch):
    """Two concepts for one company are alternative taggings of the same
    quantity. Adding them double-counts."""
    frames = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"0000000001": 100.0},
        "Revenues": {"0000000001": 90.0, "0000000002": 50.0},
    }
    monkeypatch.setattr(
        peer_rules.edgar_client,
        "fetch_frame",
        lambda concept, period, **kw: frames.get(concept, {}),
    )
    merged = peer_rules.industry_revenues("CY2025")
    assert merged == {"0000000001": 100.0, "0000000002": 50.0}


def test_primary_tickers_prefers_the_shortest_spelling():
    assert peer_rules.primary_tickers({"SMCIP": "1", "SMCI": "1"}) == {"0000000001": "SMCI"}


# --------------------------------------------------------------------------
# the raw figures calc/ needs to compute a peer median
# --------------------------------------------------------------------------
def test_peers_carry_revenue_and_net_income(replay):
    """Without these calc/ skips peer_median entirely, reporting "no peer
    carries this multiple, and the raw fields to compute it are not on the
    peers either"."""
    for ticker in TICKERS:
        _, result = replay(ticker)
        filled = [p for p in result.peers if p.revenue.status.value == "ok"]
        assert filled, f"{ticker}: no peer carries a revenue"
        for peer in filled:
            assert peer.revenue.value is not None
            assert peer.revenue.unit.value == "usd"


def test_peer_figures_come_from_the_frames_not_a_per_peer_fetch(replay):
    """One frame request covers the whole industry. A companyfacts fetch per
    peer is six requests for six peers and grows with the peer count."""
    for ticker in TICKERS:
        fixture, result = replay(ticker)
        for peer in result.peers:
            if peer.revenue.status.value == "ok":
                assert peer.revenue.source_id == f"src:edgar_frames:{fixture['frame_period']}"


def test_a_peer_missing_from_the_frames_is_unavailable_not_zero(replay):
    """Zero revenue would rank a company as tiny and make a P/S infinite."""
    for ticker in TICKERS:
        _, result = replay(ticker)
        for peer in result.peers:
            for field in ("revenue", "net_income"):
                value = getattr(peer, field)
                if value.status.value == "unavailable":
                    assert value.value is None, f"{ticker} {peer.ticker} {field}"


def test_a_loss_making_peer_keeps_its_negative_net_income():
    """Dropping losers would quietly bias a peer median upward."""
    assert peer_rules._reported(-1.5e9, "CY2025").value == -1.5e9
    assert peer_rules._reported(-1.5e9, "CY2025").status.value == "ok"


def test_only_none_counts_as_missing():
    assert peer_rules._reported(0.0, "CY2025").status.value == "ok"
    assert peer_rules._reported(None, "CY2025").status.value == "unavailable"


def test_a_bank_reads_revenue_net_of_interest_expense_first():
    """A bank tagging RevenueFromContractWithCustomer is reporting FEE income.
    Taking it first gives Capital One $8.1B against a real $53.4B, which ranks
    it as a small company and hands calc/ a P/S five times too high."""
    order = peer_rules.revenue_concept_order("6021")
    assert order[0] == "RevenuesNetOfInterestExpense"

    ordinary = peer_rules.revenue_concept_order("3674")
    assert ordinary == peer_rules.REVENUE_CONCEPTS
    assert set(order) == set(ordinary), "reordered, never shortened"


def test_no_sic_keeps_the_ordinary_order():
    assert peer_rules.revenue_concept_order(None) == peer_rules.REVENUE_CONCEPTS


def test_net_income_prefers_the_figure_a_pe_divides(monkeypatch):
    """NetIncomeLoss is attributable to the parent; ProfitLoss includes
    non-controlling interests."""
    frames = {
        "NetIncomeLoss": {"0000000001": 100.0},
        "ProfitLoss": {"0000000001": 130.0, "0000000002": 50.0},
    }
    monkeypatch.setattr(
        peer_rules.edgar_client,
        "fetch_frame",
        lambda concept, period, **kw: frames.get(concept, {}),
    )
    merged = peer_rules.industry_net_income("CY2025")
    assert merged == {"0000000001": 100.0, "0000000002": 50.0}
