"""Rule 4: value-object, source, quote, probability and arithmetic rules. FROZEN (Step 0)."""
import re

import pytest
from data import api as data_api
from helpers import (MOCK_DIR, evidence_items, load_fixture, norm, value_objects, walk, FIXTURE_SCHEMAS)

FS = load_fixture("factsheet.json")
SOURCES = set(FS["sources"])
ALLOWED_EXTERNAL_PREFIXES = ("src:llm:", "src:config:")


def _all_fixtures():
    return {name: load_fixture(name) for name in FIXTURE_SCHEMAS}


@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_fraction_values_look_like_fractions_not_percents(name):
    for path, vo in value_objects(load_fixture(name)):
        if vo["unit"] == "fraction" and vo["value"] is not None:
            assert abs(vo["value"]) <= 10, f"{name}:{path} = {vo['value']} looks like a percent, use fractions (0.25 = 25%)"


@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_numeric_leaves_are_value_objects(name):
    """No bare floats for financial figures. Allowed bare numbers are listed by key."""
    allowed_keys = {
        "probability", "value", "horizon_years", "char_count", "discount_rate", "terminal_growth",
        "requested_shift", "applied_shift", "cap", "1y", "3y", "5y", "short_term", "medium_term",
        "long_term", "p_beat_sp500_5y", "base_rate",
    }
    def scan(node, path, inside_value):
        if isinstance(node, dict):
            vo = {"value", "unit", "type", "status"} <= set(node)
            for k, x in node.items():
                scan(x, f"{path}.{k}", inside_value or vo)
        elif isinstance(node, list):
            for i, x in enumerate(node):
                scan(x, f"{path}[{i}]", inside_value)
        elif isinstance(node, (int, float)) and not isinstance(node, bool) and not inside_value:
            key = re.split(r"[.\[]", path)[-1] if "[" not in path.split(".")[-1] else path.split(".")[-1].split("[")[0]
            assert key in allowed_keys, f"{name}:{path} is a bare number; wrap it in a value object"
    scan(load_fixture(name), name, False)


def test_factsheet_source_ids_resolve():
    for path, vo in value_objects(FS):
        if vo["source_id"]:
            assert vo["source_id"] in SOURCES, f"{path}: {vo['source_id']} not in factsheet.sources"
    for sec in FS["filing_sections"]:
        assert sec["source_id"] in SOURCES
    for n in FS["news"]:
        assert n["source_id"] in SOURCES


@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_other_artifacts_source_ids_resolve(name):
    obj = load_fixture(name)
    for path, vo in value_objects(obj):
        sid = vo["source_id"]
        if sid:
            assert sid in SOURCES or sid.startswith(ALLOWED_EXTERNAL_PREFIXES), f"{name}:{path}: unknown {sid}"
    for path, ev in evidence_items(obj):
        assert ev["source_id"] in SOURCES, f"{name}:{path}: evidence cites unknown {ev['source_id']}"


@pytest.mark.parametrize("name", sorted(FIXTURE_SCHEMAS))
def test_every_evidence_quote_is_verbatim_in_its_source(name):
    for path, ev in evidence_items(load_fixture(name)):
        text = norm(data_api.get_section_text(ev["source_id"]))
        assert norm(ev["quote"]) in text, f"{name}:{path}: quote not found in {ev['source_id']}: {ev['quote']!r}"


def test_scenario_probabilities_sum_to_one():
    for fname in ("scenarios.json", "scenario_result.json"):
        s = load_fixture(fname)["scenarios"]
        assert abs(sum(x["probability"] for x in s.values()) - 1.0) < 1e-6, fname


def test_prior_shift_respects_cap():
    p = load_fixture("scenario_result.json")["prior"]
    assert abs(p["applied_shift"]) <= p["cap"] + 1e-12
    assert abs(p["applied_shift"]) <= abs(p["requested_shift"]) + 1e-12


def test_verdict_has_disclaimer_and_matches_calc():
    v = load_fixture("verdict.json")
    assert len(v["disclaimer"].strip()) >= 20
    sr = load_fixture("scenario_result.json")
    assert v["card"]["scores"] == sr["scores"]
    assert v["card"]["p_beat_sp500_5y"] == sr["p_beat_sp500"]["5y"]


def test_financial_periods_are_newest_first_and_identities_hold():
    fin = FS["financials"]
    ends = [p["period_end"] for p in fin]
    assert ends == sorted(ends, reverse=True)
    for p in fin:
        val = lambda k: p[k]["value"]  # noqa: E731
        assert val("gross_profit") == pytest.approx(val("revenue") - val("cost_of_revenue"))
        assert val("pretax_income") == pytest.approx(val("operating_income") - val("interest_expense"))
    m = FS["market"]
    q2 = fin[0]
    assert m["enterprise_value"]["value"] == pytest.approx(
        m["market_cap"]["value"] + q2["total_debt"]["value"] - q2["cash"]["value"])
    assert m["market_cap"]["value"] == pytest.approx(m["price"]["value"] * m["shares_outstanding"]["value"])


def test_metrics_match_factsheet():
    m = load_fixture("metrics.json")
    fy = next(p for p in FS["financials"] if p["period"] == m["latest_annual_period"])
    fcf = fy["op_cash_flow"]["value"] - fy["capex"]["value"]
    assert m["cash_flow"]["fcf"]["value"] == pytest.approx(fcf)
    assert m["margins"]["FY2025"]["gross"]["value"] == pytest.approx(
        fy["gross_profit"]["value"] / fy["revenue"]["value"])
    assert m["cash_flow"]["fcf_yield"]["value"] == pytest.approx(fcf / FS["market"]["market_cap"]["value"])


def test_derived_values_declare_their_inputs():
    for name in ("metrics.json", "scenario_result.json"):
        for path, vo in value_objects(load_fixture(name)):
            if vo["status"] == "ok" and vo["type"] == "fact":
                assert vo.get("derived_from") or vo["source_id"], f"{name}:{path}"
            if vo["type"] == "assumption":
                assert vo["source_id"] or vo.get("derived_from"), f"{name}:{path}"


def test_ticker_and_dates_are_consistent_across_fixtures():
    for name in FIXTURE_SCHEMAS:
        obj = load_fixture(name)
        if "ticker" in obj:
            assert obj["ticker"] == FS["ticker"], name
