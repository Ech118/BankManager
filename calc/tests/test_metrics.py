"""Unit tests for calc.metrics, hand-checked against ACME and against one real
filing (plan.txt 15.14 P2: "Unit tests hand-checked against ACME and against
at least one real filing").

The ACME expected values are the same hand-verified numbers pinned by the
asserts at the bottom of scripts/gen_mock_fixtures.py (FROZEN, coordinator-
owned) - we recompute them independently here via calc.api instead of trusting
the fixture file, so a bug that breaks both the generator and calc/ the same
way would still be caught by the arithmetic in this file.
"""
import json
from pathlib import Path

import pytest
from helpers import validation_errors

from calc import api as calc_api

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(scope="module")
def acme_factsheet():
    return load_fixture("factsheet.json")


@pytest.fixture(scope="module")
def acme_metrics(acme_factsheet):
    return calc_api.compute_metrics(acme_factsheet)


def test_compute_metrics_output_validates_against_schema(acme_metrics):
    errs = validation_errors(acme_metrics, "metrics.json")
    assert not errs, "\n".join(errs)


def test_margins_match_hand_checked_acme_values(acme_metrics):
    assert acme_metrics["margins"]["FY2025"]["gross"]["value"] == pytest.approx(0.4, abs=1e-4)
    assert acme_metrics["margins"]["FY2025"]["operating"]["value"] == pytest.approx(0.16, abs=1e-4)
    assert acme_metrics["margins"]["FY2025"]["net"]["value"] == pytest.approx(0.1184, abs=1e-4)
    assert acme_metrics["margins"]["FY2025"]["fcf"]["value"] == pytest.approx(0.12, abs=1e-4)


def test_growth_matches_hand_checked_acme_values(acme_metrics):
    assert acme_metrics["growth"]["FY2025"]["revenue_yoy"]["value"] == pytest.approx(0.1111, abs=1e-3)
    assert acme_metrics["growth"]["FY2025"]["eps_yoy"]["value"] == pytest.approx(0.2437, abs=1e-3)
    assert acme_metrics["growth"]["FY2025"]["fcf_yoy"]["value"] == pytest.approx(0.25, abs=1e-4)
    # No FY2022 in the fixture -> FY2023 has no prior comparable period.
    assert "FY2023" not in acme_metrics["growth"]


def test_cash_flow_matches_hand_checked_acme_values(acme_metrics):
    cf = acme_metrics["cash_flow"]
    assert cf["fcf"]["value"] == 600_000_000
    assert cf["ebitda"]["value"] == 1_000_000_000
    assert cf["fcf_yield"]["value"] == pytest.approx(0.0304, abs=1e-4)
    assert cf["fcf_conversion"]["value"] == pytest.approx(600_000_000 / 592_000_000, abs=1e-6)
    assert cf["capex_intensity"]["value"] == pytest.approx(0.05, abs=1e-6)


def test_balance_sheet_matches_hand_checked_acme_values(acme_metrics):
    bs = acme_metrics["balance_sheet"]
    assert bs["net_debt"]["value"] == 150_000_000
    assert bs["interest_coverage"]["value"] == pytest.approx(13.333, abs=1e-3)
    assert bs["current_ratio"]["value"] == pytest.approx(2_500_000_000 / 1_350_000_000, abs=1e-6)
    assert bs["net_debt_to_ebitda"]["value"] == pytest.approx(0.15, abs=1e-6)


def test_valuation_matches_hand_checked_acme_values(acme_metrics):
    val = acme_metrics["valuation"]
    assert val["pe"]["value"] == pytest.approx(33.78, abs=1e-2)
    assert val["ev_ebitda"]["value"] == pytest.approx(19.9, abs=1e-2)
    assert val["vs_peers"]["pe_premium"]["value"] == pytest.approx(0.2749, abs=1e-3)


def test_reverse_dcf_matches_hand_checked_acme_value(acme_metrics):
    assert acme_metrics["reverse_dcf"]["implied_fcf_cagr"]["value"] == pytest.approx(0.116, abs=2e-3)
    assert len(acme_metrics["reverse_dcf"]["sensitivity_grid"]) == 9


def test_quality_flags_catch_dso_rise_and_buyback_on_acme(acme_metrics):
    flags = {f["flag"]: f for f in acme_metrics["quality_flags"]}
    assert "dso_rising" in flags
    assert flags["dso_rising"]["severity"] == "low"
    assert "buyback_flatters_eps" in flags
    assert flags["buyback_flatters_eps"]["severity"] == "low"


def test_missing_data_is_unavailable_never_zero(acme_factsheet):
    """error E: a failed/missing input must degrade to unavailable, never 0."""
    import copy
    fs = copy.deepcopy(acme_factsheet)
    fs["financials"][1]["revenue"] = {"value": None, "unit": "usd", "type": "fact",
                                       "status": "unavailable", "source_id": None}
    metrics = calc_api.compute_metrics(fs)
    gross = metrics["margins"]["FY2025"]["gross"]
    assert gross["value"] is None
    assert gross["status"] == "unavailable"


# ---------------------------------------------------------------------------
# One real filing: Apple Inc. FY2023 10-K (fiscal year ended 2023-09-30).
# Figures below are the company's own reported GAAP numbers as commonly
# cited from that filing (in whole USD). Only revenue/cost/operating
# income/net income/op cash flow/capex are asserted with precision, since
# those are the figures we are confident about; balance-sheet fields are
# filled with approximate figures for schema completeness only and are
# checked loosely (order of magnitude / sign), not to exact cents.
# ---------------------------------------------------------------------------
APPLE_FY2023 = dict(
    revenue=383_285_000_000,
    cost_of_revenue=214_137_000_000,
    operating_income=114_301_000_000,
    net_income=96_995_000_000,
    eps_diluted=6.13,
    shares_diluted=15_744_231_000,
    depreciation_amortization=11_519_000_000,
    op_cash_flow=110_543_000_000,
    capex=10_959_000_000,
    sbc=10_833_000_000,
    interest_expense=3_933_000_000,
    cash=29_965_000_000,
    total_debt=111_088_000_000,
    total_assets=352_583_000_000,
    total_equity=62_146_000_000,
    current_assets=143_566_000_000,
    current_liabilities=145_308_000_000,
    receivables=60_985_000_000,
    inventory=6_331_000_000,
)


def _apple_factsheet():
    src = "src:edgar:0000320193-23-000106:xbrl"

    def v(val, unit="usd"):
        return {"value": val, "unit": unit, "type": "fact", "status": "ok", "source_id": src}

    p = APPLE_FY2023
    gross_profit = p["revenue"] - p["cost_of_revenue"]
    pretax_income = p["operating_income"] - p["interest_expense"]
    return {
        "schema_version": "1.0.0",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "as_of": "2023-11-03",
        "built_at": "2023-11-03T12:00:00Z",
        "mode": "mock",
        "scope": {"in_scope": True, "reason": None},
        "data_quality": {"overall": "ok", "gaps": []},
        "market": {
            "price": v(178.64, "usd_per_share"),
            "market_cap": v(178.64 * p["shares_diluted"]),
            "shares_outstanding": v(p["shares_diluted"], "shares"),
            "enterprise_value": v(178.64 * p["shares_diluted"] + p["total_debt"] - p["cash"]),
        },
        "financials": [{
            "period": "FY2023",
            "period_end": "2023-09-30",
            "form": "10-K",
            "filed_date": "2023-11-03",
            "accession": "0000320193-23-000106",
            "revenue": v(p["revenue"]),
            "cost_of_revenue": v(p["cost_of_revenue"]),
            "gross_profit": v(gross_profit),
            "operating_income": v(p["operating_income"]),
            "pretax_income": v(pretax_income),
            "net_income": v(p["net_income"]),
            "eps_diluted": v(p["eps_diluted"], "usd_per_share"),
            "shares_diluted": v(p["shares_diluted"], "shares"),
            "depreciation_amortization": v(p["depreciation_amortization"]),
            "op_cash_flow": v(p["op_cash_flow"]),
            "capex": v(p["capex"]),
            "sbc": v(p["sbc"]),
            "cash": v(p["cash"]),
            "total_debt": v(p["total_debt"]),
            "interest_expense": v(p["interest_expense"]),
            "total_assets": v(p["total_assets"]),
            "total_equity": v(p["total_equity"]),
            "current_assets": v(p["current_assets"]),
            "current_liabilities": v(p["current_liabilities"]),
            "receivables": v(p["receivables"]),
            "inventory": v(p["inventory"]),
        }],
        "peers": [],
        "sp500_baseline": {
            "forward_pe": v(22.0, "multiple"),
            "earnings_yield": v(1 / 22.0, "fraction"),
            "risk_free_rate": v(0.045, "fraction"),
            "as_of": "2023-11-02",
        },
        "filing_sections": [],
        "news": [],
        "sources": {src: {"kind": "edgar_xbrl", "url": None, "accession": "0000320193-23-000106",
                           "fetched_at": "2023-11-03T12:00:00Z"}},
    }


@pytest.fixture(scope="module")
def apple_metrics():
    return calc_api.compute_metrics(_apple_factsheet())


def test_apple_fy2023_margins_match_public_10k_figures(apple_metrics):
    """Hand-checked against Apple's reported FY2023 GAAP figures."""
    m = apple_metrics["margins"]["FY2023"]
    assert m["gross"]["value"] == pytest.approx(0.4413, abs=1e-3)
    assert m["operating"]["value"] == pytest.approx(0.2982, abs=1e-3)
    assert m["net"]["value"] == pytest.approx(0.2531, abs=1e-3)


def test_apple_fy2023_fcf_matches_public_10k_figures(apple_metrics):
    fcf = apple_metrics["cash_flow"]["fcf"]["value"]
    assert fcf == pytest.approx(99_584_000_000, abs=1)
    assert apple_metrics["cash_flow"]["ebitda"]["value"] == pytest.approx(
        APPLE_FY2023["operating_income"] + APPLE_FY2023["depreciation_amortization"])


def test_apple_fy2023_output_validates_against_schema(apple_metrics):
    errs = validation_errors(apple_metrics, "metrics.json")
    assert not errs, "\n".join(errs)


def test_apple_fy2023_balance_sheet_sanity(apple_metrics):
    """Loose sanity checks only - these inputs are approximate, unlike the
    precisely-sourced income-statement/cash-flow figures above."""
    bs = apple_metrics["balance_sheet"]
    assert bs["current_ratio"]["value"] > 0
    assert bs["interest_coverage"]["value"] > 1
