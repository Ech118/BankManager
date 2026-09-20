"""calculate_valuation: multiples, peers, both DCFs, and what gets skipped.

The rule under test throughout: **a method whose inputs are unavailable is
skipped with its reason recorded**, never guessed and never silently dropped.
"""

from __future__ import annotations

import pytest

from calc import config
from calc.api import calculate_valuation, compute_metrics, reverse_dcf
from calc.tests.support import load_real
from calc.valuation.dcf import growth_input, growth_schedule, present_value_fading
from calc.valuation.historical import NO_PRICE_HISTORY, historical_block, historical_median
from calc.valuation.peers import peer_multiple
from calc.valuation.reverse_dcf import present_value, solve_implied_growth
from schema.contracts.facts import FinancialFact
from schema.contracts.metrics import Metrics
from schema.contracts.tools import CalculateValuationResponse


def value_of(response: dict, *path: str):
    node = response["metrics"]["valuation"]
    for key in path:
        node = node[key]
    return node


# --------------------------------------------------------------------------
# The response contract
# --------------------------------------------------------------------------
def test_acme_response_is_contract_valid():
    out = calculate_valuation({"ticker": "ACME", "methods": ["all"]})
    CalculateValuationResponse.model_validate(out)
    Metrics.model_validate(out["metrics"])
    assert out["as_of"] == "2026-09-19"
    assert out["reverse_dcf"]["sensitivity_grid"], "a DCF is never a single point"


def test_a_real_ticker_needs_a_factsheet():
    """calc/ is pure: it cannot turn a ticker into data, and says so."""
    with pytest.raises(ValueError, match="no factsheet supplied"):
        calculate_valuation({"ticker": "AAPL", "methods": ["pe"]})


def test_factsheet_in_the_request_is_used(real_factsheet):
    out = calculate_valuation(
        {"ticker": real_factsheet["ticker"], "methods": ["all"], "factsheet": real_factsheet}
    )
    CalculateValuationResponse.model_validate(out)
    for fact in out["metrics"]["derived_facts"]:
        FinancialFact.model_validate(fact)


# --------------------------------------------------------------------------
# Multiples
# --------------------------------------------------------------------------
def test_acme_multiples(acme, pinned_metrics):
    out = calculate_valuation({"ticker": "ACME", "methods": ["multiples"], "factsheet": acme})
    assert value_of(out, "pe", "value") == pytest.approx(pinned_metrics["valuation"]["pe"]["value"])
    assert value_of(out, "ev_ebitda", "value") == pytest.approx(19.9)
    assert value_of(out, "p_fcf", "value") == pytest.approx(19_750_000_000 / 600_000_000)
    assert value_of(out, "p_s", "value") == pytest.approx(19_750_000_000 / 5_000_000_000)
    assert value_of(out, "p_b", "value") == pytest.approx(19_750_000_000 / 3_150_000_000)


def test_enterprise_value_is_cap_plus_debt_less_cash(acme):
    """EV = market cap + debt - cash, whether P1 published it or calc/ rebuilt it."""
    del acme["market"]["enterprise_value"]
    metrics = compute_metrics(acme)
    rebuilt = next(f for f in metrics["derived_facts"] if f["metric"] == "enterprise_value")
    assert rebuilt["value"] == 19_750_000_000 + 1_150_000_000 - 1_000_000_000
    assert rebuilt["derivation"]["formula"] == "market_cap + total_debt - cash"
    assert metrics["valuation"]["ev_ebitda"]["value"] == pytest.approx(19.9)


def test_multiples_say_which_period_they_divide(real_factsheet):
    """A reader comparing with a finance site must be able to see the difference."""
    out = calculate_valuation(
        {"ticker": real_factsheet["ticker"], "methods": ["pe"], "factsheet": real_factsheet}
    )
    basis = value_of(out, "basis")
    assert basis["earnings_period"] == out["metrics"]["latest_annual_period"]
    assert "TRAILING TWELVE MONTH" in basis["note"]


def test_aapl_pe_is_price_over_latest_full_year_eps():
    """45x on FY2025 EPS, not the ~36x TTM figure a data provider quotes."""
    aapl = load_real("AAPL")
    out = calculate_valuation({"ticker": "AAPL", "methods": ["pe"], "factsheet": aapl})
    assert value_of(out, "pe", "value") == pytest.approx(336.13 / 7.46, rel=1e-6)


def test_bank_gets_p_b_and_no_ev_multiples():
    """The check that matters for a financial: P/B in, EV/EBITDA out."""
    out = calculate_valuation({"ticker": "JPM", "methods": ["all"], "factsheet": load_real("JPM")})
    assert value_of(out, "primary_multiple") == "p_b"
    assert value_of(out, "p_b", "value") == pytest.approx(2.5645433614)
    for method in ("ev_ebitda", "ev_revenue", "p_fcf", "dcf", "reverse_dcf"):
        assert method in value_of(out, "methods_skipped"), method
    assert value_of(out, "ev_ebitda", "not_applicable") is True
    assert "p_b" in value_of(out, "methods_used")


# --------------------------------------------------------------------------
# Peers
# --------------------------------------------------------------------------
def test_acme_peer_median_and_premium(acme):
    out = calculate_valuation({"ticker": "ACME", "methods": ["peer_median"], "factsheet": acme})
    table = value_of(out, "peer_table")
    assert [row["ticker"] for row in table["peers"]] == ["PRAA", "PRBB", "PRCC", "PRDD"]
    assert table["median"]["pe"]["value"] == pytest.approx(26.5)
    assert table["median"]["pe"]["usable_peers"] == 4
    premium = value_of(out, "vs_peers", "pe_premium")
    assert premium["value"] == pytest.approx(33.7837837838 / 26.5 - 1)
    assert "peer_median" in value_of(out, "methods_used")


def test_peer_multiple_is_computed_from_raw_fields_when_present():
    """When P1 sends the peer's own filing figures, calc/ prefers them to a ratio."""
    peer = {
        "ticker": "PEER",
        "market_cap": {"value": 1000.0, "unit": "usd", "type": "fact", "status": "ok"},
        "pe": {"value": None, "unit": "multiple", "type": "fact", "status": "unavailable"},
        "net_income": {"value": 50.0, "unit": "usd", "type": "fact", "status": "ok"},
        "revenue": {"value": 500.0, "unit": "usd", "type": "fact", "status": "ok"},
    }
    assert peer_multiple(peer, "pe") == (20.0, "computed")
    assert peer_multiple(peer, "p_s") == (2.0, "computed")
    assert peer_multiple(peer, "ev_ebitda") == (None, "none")


def test_real_peers_have_no_multiples_and_say_so(real_factsheet):
    out = calculate_valuation(
        {
            "ticker": real_factsheet["ticker"],
            "methods": ["peer_median"],
            "factsheet": real_factsheet,
        }
    )
    median = value_of(out, "peer_table", "median")["pe"]
    assert median["value"] is None
    assert median["usable_peers"] == 0 and median["peer_count"] > 0
    assert "no peer carries this multiple" in median["unavailable_reason"]
    assert "peer_median" in value_of(out, "methods_skipped")


def test_median_not_mean(acme):
    """One mispriced comparable must not be able to move the comparison much.

    ACME's peers trade at 22, 25, 28 and 30x. Mis-tag the first as 1000x: the mean
    goes to 271x and the median to 29x, still inside the peer range. That is the
    whole reason for the choice.
    """
    acme["peers"][0]["pe"]["value"] = 1000.0
    out = calculate_valuation({"ticker": "ACME", "methods": ["peer_median"], "factsheet": acme})
    median = value_of(out, "peer_table", "median")["pe"]["value"]
    assert median == pytest.approx(29.0)
    assert 22 <= median <= 30, "the median stays inside the sane peer range"


# --------------------------------------------------------------------------
# Reverse DCF
# --------------------------------------------------------------------------
def test_reverse_dcf_solves_the_pinned_acme_value(acme, pinned_metrics):
    block = reverse_dcf(acme, {})
    want = pinned_metrics["reverse_dcf"]
    assert block["implied_fcf_cagr"]["value"] == pytest.approx(
        want["implied_fcf_cagr"]["value"], rel=1e-9
    )
    assert len(block["sensitivity_grid"]) == 9
    for got, expected in zip(block["sensitivity_grid"], want["sensitivity_grid"], strict=True):
        assert got["discount_rate"] == expected["discount_rate"]
        assert got["terminal_growth"] == expected["terminal_growth"]
        assert got["implied_fcf_cagr"]["value"] == pytest.approx(
            expected["implied_fcf_cagr"]["value"], rel=1e-9
        )


def test_the_solver_round_trips():
    """The growth it solves for must reprice the stream to the value it started from."""
    ev, fcf = 19_900_000_000.0, 600_000_000.0
    g = solve_implied_growth(ev, fcf, 0.09, 0.03, 10)
    assert present_value(fcf, g, 0.09, 0.03, 10) == pytest.approx(ev, rel=1e-6)


def test_the_solver_refuses_an_ill_posed_problem():
    assert solve_implied_growth(1e9, -5.0, 0.09, 0.03, 10) is None, "negative FCF"
    assert solve_implied_growth(1e9, 1e8, 0.03, 0.03, 10) is None, "r == terminal growth diverges"
    assert solve_implied_growth(None, 1e8, 0.09, 0.03, 10) is None, "no price to solve against"


def test_assumption_overrides_reach_the_grid(acme):
    block = reverse_dcf(acme, {}, {"discount_rate": 0.12, "terminal_growth": 0.02})
    assert block["assumptions"]["discount_rate"]["value"] == 0.12
    assert block["assumptions"]["discount_rate"]["type"] == "assumption"
    assert block["implied_fcf_cagr"]["value"] > 0.16, "a higher discount rate implies more growth"


# --------------------------------------------------------------------------
# Forward DCF
# --------------------------------------------------------------------------
def test_dcf_growth_is_the_revenue_cagr_bounded_both_ways(acme):
    """Revenue, not FCF: the KO deposit makes its FCF CAGR -17% and revenue +5.5%."""
    from calc.facts import Ledger

    metrics = compute_metrics(acme)
    assert growth_input(Ledger(acme), metrics)["basis"] == "trailing_revenue_cagr"

    metrics["cagr"]["revenue"]["value"] = 0.85
    clamped = growth_input(Ledger(acme), metrics)
    assert clamped["value"] == 0.15 and clamped["was_clamped"] is True
    assert clamped["requested"] == 0.85 and "clamped" in clamped["note"]

    metrics["cagr"]["revenue"]["value"] = -0.17
    floored = growth_input(Ledger(acme), metrics)
    assert floored["value"] == 0.03 and floored["was_floored"] is True
    assert floored["requested"] == -0.17, "the trailing figure stays visible"
    assert floored["floor"] == 0.03


def test_growth_fades_to_the_terminal_rate(acme):
    """Year 1 at the assumed rate, year 10 at 3%, interpolating."""
    schedule = growth_schedule(0.15, 0.03, 10)
    assert schedule[0] == pytest.approx(0.15)
    assert schedule[-1] == pytest.approx(0.03)
    assert schedule == sorted(schedule, reverse=True), "monotonically decelerating"
    steps = [b - a for a, b in zip(schedule, schedule[1:], strict=False)]
    assert all(step == pytest.approx(steps[0]) for step in steps), "linear"

    out = calculate_valuation({"ticker": "ACME", "methods": ["dcf"], "factsheet": acme})
    published = value_of(out, "dcf", "assumptions", "growth_schedule")
    assert published[0] == pytest.approx(value_of(out, "dcf", "assumptions", "fcf_growth")["value"])
    assert published[-1] == pytest.approx(0.03)


def test_fading_is_worth_less_than_a_flat_decade():
    """The fade is not cosmetic: it is the difference between two valuations."""
    flat = present_value(600e6, 0.15, 0.09, 0.03, 10)
    faded = present_value_fading(600e6, 0.15, 0.09, 0.03, 10)
    assert faded < flat
    assert faded == pytest.approx(present_value_fading(600e6, 0.15, 0.09, 0.03, 10))


def test_fcf_base_is_a_three_year_average(acme):
    """ACME's FY2023-25 FCF is 400M, 480M, 600M: the base is 493.3M, not 600M."""
    out = calculate_valuation({"ticker": "ACME", "methods": ["dcf"], "factsheet": acme})
    base = value_of(out, "dcf", "fcf_base")
    assert base["value"] == pytest.approx((600e6 + 480e6 + 400e6) / 3)
    assert base["years_used"] == ["FY2025", "FY2024", "FY2023"]
    assert base["basis"] == "3-year average"
    assert base["latest_year"] == 600e6
    assert base["latest_vs_average"] == pytest.approx(600e6 / ((600 + 480 + 400) / 3 * 1e6) - 1)


def test_ko_base_smooths_the_irs_deposit():
    """The one-off cut FY2025 FCF 20% below the three-year average."""
    out = calculate_valuation({"ticker": "KO", "methods": ["dcf"], "factsheet": load_real("KO")})
    base = value_of(out, "dcf", "fcf_base")
    assert base["value"] == pytest.approx((5296e6 + 4741e6 + 9747e6) / 3)
    assert base["latest_vs_average"] < -0.15, "the latest year is well below the average"
    # And the growth input is revenue-based, so the deposit no longer sets it either.
    growth = value_of(out, "dcf", "assumptions", "fcf_growth")
    assert growth["basis"] == "trailing_revenue_cagr"
    assert growth["was_floored"] is False and growth["value"] > 0.03


def test_the_reverse_dcf_publishes_the_smoothed_base_too():
    """A depressed base overstates the growth the price implies; show both."""
    metrics = compute_metrics(load_real("KO"))
    headline = metrics["reverse_dcf"]["implied_fcf_cagr"]["value"]
    smoothed = metrics["reverse_dcf"]["implied_fcf_cagr_smoothed_base"]["value"]
    assert smoothed < headline, "a bigger base needs less growth to justify the price"
    assert (
        "instead of the latest year"
        in (metrics["reverse_dcf"]["implied_fcf_cagr_smoothed_base"]["note"])
    )


def test_nvda_growth_is_clamped():
    nvda = calculate_valuation(
        {"ticker": "NVDA", "methods": ["dcf"], "factsheet": load_real("NVDA")}
    )
    growth = value_of(nvda, "dcf", "assumptions", "fcf_growth")
    assert growth["was_clamped"] is True and growth["value"] == 0.15
    assert growth["requested"] > 0.5, "NVDA's trailing revenue CAGR really is that high"


def test_rates_are_recorded_as_nominal(acme):
    out = calculate_valuation({"ticker": "ACME", "methods": ["dcf"], "factsheet": acme})
    assumptions = value_of(out, "dcf", "assumptions")
    assert assumptions["rates_are_nominal"] is True
    assert assumptions["discount_rate"]["value"] == config.DISCOUNT_RATE
    assert assumptions["discount_rate"]["type"] == "assumption"
    assert assumptions["terminal_growth"]["value"] == config.TERMINAL_GROWTH


def test_dcf_value_is_equity_after_net_debt(acme):
    out = calculate_valuation({"ticker": "ACME", "methods": ["dcf"], "factsheet": acme})
    dcf = value_of(out, "dcf")
    assert dcf["value_per_share"]["value"] > 0
    assert dcf["value_per_share"]["type"] == "estimate"
    assert len(dcf["sensitivity_grid"]) == 9
    assert dcf["upside_to_price"]["value"] == pytest.approx(
        dcf["value_per_share"]["value"] / 50.0 - 1
    )


def test_dcf_refuses_a_negative_equity_value(acme):
    """Worth less than its net debt is not a negative share price."""
    for period in acme["financials"]:
        period["total_debt"] = {
            "value": 500_000_000_000.0,
            "unit": "usd",
            "type": "fact",
            "status": "ok",
        }
    out = calculate_valuation({"ticker": "ACME", "methods": ["dcf"], "factsheet": acme})
    dcf = value_of(out, "dcf")
    assert dcf["value_per_share"]["value"] is None
    assert "less than net debt" in dcf["value_per_share"]["unavailable_reason"]
    assert "dcf" in value_of(out, "methods_skipped")


# --------------------------------------------------------------------------
# Historical
# --------------------------------------------------------------------------
def test_historical_is_unavailable_with_the_documented_reason(acme):
    out = calculate_valuation({"ticker": "ACME", "methods": ["historical"], "factsheet": acme})
    historical = value_of(out, "historical")
    assert historical["available"] is False
    assert historical["reason"] == NO_PRICE_HISTORY
    assert historical["pe"]["median"]["status"] == "unavailable"
    assert value_of(out, "methods_skipped")["historical"] == NO_PRICE_HISTORY


def test_historical_works_the_day_a_series_arrives():
    """The functions are complete; only the caller that feeds them is missing."""
    series = [
        {"value": 20.0, "unit": "multiple", "type": "fact", "status": "ok", "source_id": "src:x:1"},
        {"value": 24.0, "unit": "multiple", "type": "fact", "status": "ok", "source_id": "src:x:2"},
        {"value": 22.0, "unit": "multiple", "type": "fact", "status": "ok", "source_id": "src:x:3"},
    ]
    assert historical_median(series)["value"] == 22.0
    own = {"pe": {"value": 33.0, "unit": "multiple", "type": "fact", "status": "ok"}}
    block = historical_block(own, {"pe": series})
    assert block["available"] is True
    assert block["pe"]["premium_to_median"]["value"] == pytest.approx(0.5)


# --------------------------------------------------------------------------
# Skipping
# --------------------------------------------------------------------------
def test_unknown_method_is_recorded_not_raised(acme):
    out = calculate_valuation({"ticker": "ACME", "methods": ["pe", "astrology"], "factsheet": acme})
    assert value_of(out, "methods_skipped")["astrology"].startswith("unknown method")
    assert value_of(out, "methods_used") == ["pe"]


def test_every_skip_has_a_reason(real_factsheet):
    out = calculate_valuation(
        {"ticker": real_factsheet["ticker"], "methods": ["all"], "factsheet": real_factsheet}
    )
    for method, why in value_of(out, "methods_skipped").items():
        assert why and len(why) > 10, f"{method} was skipped without a reason"
    assert all(note for note in out["notes"])
