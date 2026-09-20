"""Two things that only work once P1 sends more data, tested now so they work then.

1. **TTM flow multiples.** When a `<metric>_ttm` fact is on the factsheet, P/E,
   P/S, P/FCF and EV/EBITDA use it and `valuation.basis` says so; when it is not,
   they fall back to the latest full year and say that instead. AAPL's real
   recording has no TTM fact, so the fallback is what ships today - and with a
   TTM EPS of $9.38 the P/E is 35.8x, which is the figure a finance site quotes.

2. **Peer medians from raw peer fields.** The recordings' peers carry a market cap
   and nothing else, so every peer median is unavailable. Given revenue and net
   income, calc/ computes each peer's P/E and P/S itself, takes the median, and
   reports this company's premium to it.

Both are exercised on a copy of a real factsheet with the extra fields added, so
the day P1 publishes them nothing here changes.
"""

from __future__ import annotations

import copy

import pytest

from calc.api import calculate_valuation, compute_metrics
from calc.tests.support import load_real
from schema.contracts.facts import FinancialFact
from schema.contracts.metrics import Metrics

TTM = {
    "eps_diluted": (9.38, "usd_per_share"),
    "revenue": (440_000_000_000.0, "usd"),
    "op_cash_flow": (120_000_000_000.0, "usd"),
    "capex": (14_000_000_000.0, "usd"),
    "operating_income": (140_000_000_000.0, "usd"),
    "depreciation_amortization": (12_000_000_000.0, "usd"),
}


def _vo(value: float, unit: str = "usd", fact_id: str | None = None) -> dict:
    out = {
        "value": value,
        "unit": unit,
        "type": "fact",
        "status": "ok",
        "source_id": "src:edgar_xbrl:0000320193-26-000020",
    }
    if fact_id:
        out["derived_from"] = [fact_id]
    return out


@pytest.fixture
def aapl_with_ttm() -> dict:
    factsheet = copy.deepcopy(load_real("AAPL"))
    factsheet["ttm"] = {
        field: _vo(value, unit, f"fact:AAPL:{field}_ttm:TTM-2026Q3")
        for field, (value, unit) in TTM.items()
    }
    return factsheet


def value_of(response: dict, *path: str):
    node = response["metrics"]["valuation"]
    for key in path:
        node = node[key]
    return node


# --------------------------------------------------------------------------
# TTM
# --------------------------------------------------------------------------
def test_without_ttm_facts_multiples_use_the_latest_full_year():
    out = calculate_valuation(
        {"ticker": "AAPL", "methods": ["multiples"], "factsheet": load_real("AAPL")}
    )
    basis = value_of(out, "basis")
    assert basis["earnings_basis"] == "latest_full_year"
    assert basis["ttm_multiples"] == []
    assert basis["earnings_period"] == "FY2025"
    assert value_of(out, "pe", "value") == pytest.approx(336.13 / 7.46)
    assert value_of(out, "pe", "basis") == "latest_full_year"


def test_with_ttm_facts_the_flow_multiples_switch(aapl_with_ttm):
    out = calculate_valuation(
        {"ticker": "AAPL", "methods": ["multiples"], "factsheet": aapl_with_ttm}
    )
    basis = value_of(out, "basis")
    assert basis["earnings_basis"] == "ttm"
    assert set(basis["ttm_multiples"]) == {"pe", "p_s", "p_fcf", "ev_ebitda", "ev_revenue"}
    assert basis["earnings_period"] == "TTM"
    assert basis["latest_annual_period"] == "FY2025"
    assert "TRAILING TWELVE MONTH" in basis["note"]

    # 336.13 / 9.38 = 35.8x, which is what a data provider quotes for AAPL.
    assert value_of(out, "pe", "value") == pytest.approx(336.13 / 9.38)
    assert value_of(out, "pe", "basis") == "ttm"
    assert value_of(out, "p_s", "value") == pytest.approx(
        aapl_with_ttm["market"]["market_cap"]["value"] / 440e9
    )
    assert value_of(out, "p_fcf", "value") == pytest.approx(
        aapl_with_ttm["market"]["market_cap"]["value"] / (120e9 - 14e9)
    )
    assert value_of(out, "ev_ebitda", "value") == pytest.approx(
        aapl_with_ttm["market"]["enterprise_value"]["value"] / (140e9 + 12e9)
    )


def test_the_balance_sheet_multiple_does_not_move(aapl_with_ttm):
    """P/B divides equity, which is an instant, not a flow. TTM is irrelevant to it."""
    plain = calculate_valuation(
        {"ticker": "AAPL", "methods": ["p_b"], "factsheet": load_real("AAPL")}
    )
    trailing = calculate_valuation(
        {"ticker": "AAPL", "methods": ["p_b"], "factsheet": aapl_with_ttm}
    )
    assert value_of(plain, "p_b", "value") == value_of(trailing, "p_b", "value")
    assert value_of(trailing, "p_b", "basis") == "latest_balance_sheet"


def test_a_partial_ttm_block_does_not_mix_periods(aapl_with_ttm):
    """A TTM numerator over a full-year denominator is the error the rule prevents."""
    del aapl_with_ttm["ttm"]["capex"]
    out = calculate_valuation(
        {"ticker": "AAPL", "methods": ["multiples"], "factsheet": aapl_with_ttm}
    )
    assert value_of(out, "p_fcf", "basis") == "latest_full_year", "no TTM capex, no TTM FCF"
    assert value_of(out, "pe", "basis") == "ttm", "EPS is unaffected"


def test_ttm_lineage_resolves(aapl_with_ttm):
    out = calculate_valuation({"ticker": "AAPL", "methods": ["all"], "factsheet": aapl_with_ttm})
    metrics = out["metrics"]
    Metrics.model_validate(metrics)
    published = {fact["fact_id"] for fact in metrics["derived_facts"] + metrics["input_facts"]}
    # A TTM value P1 published already carries its own fact_id, so calc/ cites that
    # id rather than minting a twin: the verifier resolves it from the factsheet.
    on_factsheet = {
        fid for vo in aapl_with_ttm["ttm"].values() for fid in vo.get("derived_from", [])
    }
    for fact in metrics["derived_facts"] + metrics["input_facts"]:
        FinancialFact.model_validate(fact)
    pe = next(fact for fact in metrics["derived_facts"] if fact["metric"] == "pe")
    assert "fact:AAPL:eps_diluted_ttm:TTM-2026Q3" in pe["derivation"]["input_fact_ids"]
    assert set(pe["derivation"]["input_fact_ids"]) <= published | on_factsheet
    assert pe["fiscal_period"] == "FY2025", "fiscal_period stays a legal period label"


def test_a_ttm_fact_on_a_period_is_also_found():
    """The other shape P1 might choose: `<metric>_ttm` beside the reported fields."""
    factsheet = copy.deepcopy(load_real("AAPL"))
    factsheet["financials"][0]["eps_diluted_ttm"] = _vo(
        9.38, "usd_per_share", "fact:AAPL:eps_diluted_ttm:FY2025"
    )
    out = calculate_valuation({"ticker": "AAPL", "methods": ["pe"], "factsheet": factsheet})
    assert value_of(out, "pe", "value") == pytest.approx(336.13 / 9.38)
    assert value_of(out, "pe", "basis") == "ttm"


# --------------------------------------------------------------------------
# Peers
# --------------------------------------------------------------------------
PEER_FINANCIALS = {
    "DELL": (105_000_000_000.0, 5_000_000_000.0),
    "SMCI": (22_000_000_000.0, 1_100_000_000.0),
    "SNDK": (9_000_000_000.0, 600_000_000.0),
    "WDC": (16_000_000_000.0, 1_600_000_000.0),
    "HPE": (30_000_000_000.0, 2_500_000_000.0),
    "NTAP": (6_600_000_000.0, 1_200_000_000.0),
}


@pytest.fixture
def aapl_with_peer_financials() -> dict:
    factsheet = copy.deepcopy(load_real("AAPL"))
    for peer in factsheet["peers"]:
        revenue, net_income = PEER_FINANCIALS[peer["ticker"]]
        peer["revenue"] = _vo(revenue)
        peer["net_income"] = _vo(net_income)
    return factsheet


def test_peer_pe_and_ps_medians_are_computed_from_raw_fields(aapl_with_peer_financials):
    out = calculate_valuation(
        {
            "ticker": "AAPL",
            "methods": ["peer_median"],
            "factsheet": aapl_with_peer_financials,
        }
    )
    table = value_of(out, "peer_table")
    assert all(row["multiples"]["pe"]["basis"] == "computed" for row in table["peers"])
    assert table["median"]["pe"]["usable_peers"] == 6
    expected = sorted(
        peer["market_cap"]["value"] / PEER_FINANCIALS[peer["ticker"]][1]
        for peer in aapl_with_peer_financials["peers"]
    )
    assert table["median"]["pe"]["value"] == pytest.approx((expected[2] + expected[3]) / 2)
    assert table["median"]["p_s"]["usable_peers"] == 6
    assert "peer_median" in value_of(out, "methods_used")


def test_the_premium_to_the_peer_median_is_reported(aapl_with_peer_financials):
    out = calculate_valuation(
        {
            "ticker": "AAPL",
            "methods": ["peer_median"],
            "factsheet": aapl_with_peer_financials,
        }
    )
    median = value_of(out, "peer_table", "median")["pe"]["value"]
    premium = value_of(out, "vs_peers", "pe_premium")
    assert premium["value"] == pytest.approx(value_of(out, "pe", "value") / median - 1)
    # Sign follows the comparison, whichever way it falls for this peer set.
    assert (premium["value"] > 0) == (value_of(out, "pe", "value") > median)
    ps_premium = value_of(out, "vs_peers", "p_s_premium")
    assert ps_premium["value"] == pytest.approx(
        value_of(out, "p_s", "value") / value_of(out, "peer_table", "median")["p_s"]["value"] - 1
    )


def test_a_peer_premium_carries_its_sample_size(aapl_with_peer_financials):
    """A premium to two peers must not read like a premium to six."""
    for peer in aapl_with_peer_financials["peers"][2:]:
        del peer["net_income"]
    out = calculate_valuation(
        {
            "ticker": "AAPL",
            "methods": ["peer_median"],
            "factsheet": aapl_with_peer_financials,
        }
    )
    assert value_of(out, "peer_table", "median")["pe"]["usable_peers"] == 2
    assert value_of(out, "peer_table", "median")["pe"]["peer_count"] == 6
    fact = next(f for f in out["metrics"]["derived_facts"] if f["metric"] == "pe_premium_vs_peers")
    assert fact["derivation"]["usable_peers"] == 2
    assert fact["derivation"]["peer_median"] is not None


def test_one_usable_peer_is_not_a_median(aapl_with_peer_financials):
    for peer in aapl_with_peer_financials["peers"][1:]:
        del peer["net_income"]
    out = calculate_valuation(
        {
            "ticker": "AAPL",
            "methods": ["peer_median"],
            "factsheet": aapl_with_peer_financials,
        }
    )
    median = value_of(out, "peer_table", "median")["pe"]
    assert median["value"] is None and median["usable_peers"] == 1
    assert "below the minimum" in median["unavailable_reason"]
    assert value_of(out, "vs_peers", "pe_premium")["value"] is None


def test_a_published_peer_multiple_wins_over_a_computed_one(aapl_with_peer_financials):
    """P1's own figure is used as-is; calc/ only computes what is missing."""
    aapl_with_peer_financials["peers"][0]["pe"] = _vo(11.0, "multiple")
    out = calculate_valuation(
        {
            "ticker": "AAPL",
            "methods": ["peer_median"],
            "factsheet": aapl_with_peer_financials,
        }
    )
    first = value_of(out, "peer_table", "peers")[0]["multiples"]["pe"]
    assert first["value"] == 11.0 and first["basis"] == "published"


def test_bank_peers_get_p_b():
    """For a financial the comparison that means something is book value."""
    factsheet = copy.deepcopy(load_real("JPM"))
    for peer, equity in zip(factsheet["peers"], [300e9, 200e9, 60e9, 8e9], strict=True):
        peer["total_equity"] = _vo(equity)
    out = calculate_valuation({"ticker": "JPM", "methods": ["peer_median"], "factsheet": factsheet})
    median = value_of(out, "peer_table", "median")["p_b"]
    assert median["usable_peers"] == 4
    assert value_of(out, "vs_peers", "p_b_premium")["value"] is not None
    assert compute_metrics(factsheet)["valuation"]["primary_multiple"] == "p_b"
