"""Rule 2: every api.py function returns contract-valid output in mock mode."""

import pytest
from helpers import load_fixture, validation_errors, value_objects

from audit import api as audit_api
from calc import api as calc_api
from data import api as data_api
from orchestrator import api as orch_api


def _ok(obj, schema):
    errs = validation_errors(obj, schema)
    assert not errs, "\n".join(errs)


# --------------------------------------------------------------------------
# P1 data layer
# --------------------------------------------------------------------------
def test_check_scope():
    assert data_api.check_scope("ACME") == {"in_scope": True, "reason": None}
    r = data_api.check_scope("BANKX")
    assert r["in_scope"] is False and r["reason"]
    assert data_api.check_scope("not a ticker")["in_scope"] is False


def test_build_factsheet():
    fs = data_api.build_factsheet("ACME")
    _ok(fs, "factsheet.json")
    with pytest.raises(ValueError):
        data_api.build_factsheet("BANKX")


def test_build_factsheet_as_of_is_point_in_time():
    fs = data_api.build_factsheet("ACME", as_of="2025-06-01")
    _ok(fs, "factsheet.json")
    assert fs["mode"] == "backtest" and fs["as_of"] == "2025-06-01"
    assert all(p["filed_date"] <= "2025-06-01" for p in fs["financials"])
    assert [p["period"] for p in fs["financials"]] == ["FY2024", "FY2023"]
    assert fs["filing_sections"] == [], "FY2025 sections were filed after the cutoff"
    with pytest.raises(ValueError):
        data_api.build_factsheet("ACME", as_of="2020-01-01")


def test_filing_sections_and_text():
    fs = data_api.build_factsheet("ACME")
    sections = fs["filing_sections"]
    assert sections and all("section_id" in s and "source_id" in s for s in sections)
    for s in sections:
        full = data_api.get_filing_section(s["section_id"])
        assert full["text"] and len(full["text"]) == s["char_count"]
        assert isinstance(data_api.get_section_text(s["source_id"]), str)
    with pytest.raises(KeyError):
        data_api.get_section_text("src:edgar:nope:missing")
    with pytest.raises(KeyError):
        data_api.get_filing_section("sec:nope:missing")


def test_get_filing_section_respects_as_of():
    section_id = data_api.build_factsheet("ACME")["filing_sections"][0]["section_id"]
    with pytest.raises(KeyError):
        data_api.get_filing_section(section_id, as_of="2025-06-01")


def test_search_filings():
    filings = data_api.search_filings("ACME")
    assert filings and all("accession" in f for f in filings)
    early = data_api.search_filings("ACME", as_of="2025-06-01")
    assert all(f["filed_at"] <= "2025-06-01" for f in early)
    assert len(early) < len(filings)
    assert all(f["form"] == "10-Q" for f in data_api.search_filings("ACME", forms=["10-Q"]))


def test_search_filing_full_text():
    hits = data_api.search_filing("ACME", "renewed at a rate")
    assert hits and hits[0]["item"] == "business"
    assert data_api.search_filing("ACME", "no such phrase anywhere") == []
    assert data_api.search_filing("ACME", "debt", items=["debt_note"])


def test_get_financial_facts():
    facts = data_api.get_financial_facts("ACME", ["revenue"])
    assert facts and all(f["metric"] == "revenue" for f in facts)
    ends = [f["period_end"] for f in facts]
    assert ends == sorted(ends, reverse=True), "facts must be newest first"


def test_get_financial_facts_excludes_restated_values_by_default():
    """A restated number must not reach an agent unless it is asked for."""
    default = data_api.get_financial_facts("ACME", ["op_cash_flow"])
    assert all(not f["superseded_by"] for f in default)
    with_old = data_api.get_financial_facts("ACME", ["op_cash_flow"], include_superseded=True)
    superseded = [f for f in with_old if f["superseded_by"]]
    assert len(superseded) == 1 and superseded[0]["value"] == 690_000_000


def test_get_financial_facts_respects_as_of():
    """Before the FY2025 10-K was filed, only the as-filed FY2024 value existed."""
    early = data_api.get_financial_facts(
        "ACME", ["op_cash_flow"], as_of="2025-06-01", include_superseded=True
    )
    assert all(f["filed_at"] <= "2025-06-01" for f in early)
    assert 700_000_000 not in [f["value"] for f in early], "restated value leaked into the past"


def test_resolve_fact():
    fact = data_api.resolve_fact("fact:ACME:revenue:FY2025")
    assert fact["value"] == 5_000_000_000
    with pytest.raises(KeyError):
        data_api.resolve_fact("fact:ACME:nope:FY2025")


def test_market_profile_and_peers():
    _ok(data_api.get_market_snapshot("ACME"), "market_snapshot.json")
    _ok(data_api.get_company_profile("ACME"), "company_profile.json")
    peers = data_api.get_peer_companies("ACME")
    assert len(peers) == 4 and all("ticker" in p for p in peers)
    assert len(data_api.get_peer_companies("ACME", limit=2)) == 2


def test_search_news():
    news = data_api.search_news("ACME")
    assert news and all("headline" in n for n in news)
    assert data_api.search_news("ACME", as_of="2026-08-28")[0]["date"] <= "2026-08-28"


# --------------------------------------------------------------------------
# P2 calc and audit
# --------------------------------------------------------------------------
def test_calc_api():
    fs = data_api.build_factsheet("ACME")
    metrics = calc_api.compute_metrics(fs)
    _ok(metrics, "metrics.json")
    assert calc_api.reverse_dcf(fs, metrics)["sensitivity_grid"]
    scen = load_fixture("scenarios.json")
    res = calc_api.evaluate_scenarios(scen, fs, metrics)
    _ok(res, "scenario_result.json")
    assert set(calc_api.derive_scores(res)) == {"short_term", "medium_term", "long_term"}
    assert calc_api.validate_consistency(res, load_fixture("verdict.json")["card"])["ok"] in (
        True,
        False,
    )


def test_calculate_valuation_is_the_mcp_entry_point():
    out = calc_api.calculate_valuation(
        {"ticker": "ACME", "methods": ["pe", "reverse_dcf"]}
    )
    assert out["reverse_dcf"]["sensitivity_grid"], "a DCF must never be a single point"


def test_evaluate_scenarios_rejects_bad_probabilities():
    scen = load_fixture("scenarios.json")
    scen["scenarios"]["base"]["probability"] = 0.9
    with pytest.raises(ValueError):
        calc_api.evaluate_scenarios(
            scen, data_api.build_factsheet("ACME"), load_fixture("metrics.json")
        )


def test_audit_api():
    fs = data_api.build_factsheet("ACME")
    state = load_fixture("research_state.json")
    report = audit_api.run_audit(state, fs, data_api.get_section_text)
    _ok(report, "audit.json")


# --------------------------------------------------------------------------
# P3 orchestrator
# --------------------------------------------------------------------------
def test_orchestrator_api():
    v = orch_api.run_analysis("ACME")
    _ok(v, "verdict.json")
    assert v["disclaimer"]
    with pytest.raises(ValueError):
        orch_api.run_analysis("BANKX")


def test_value_objects_present_in_api_outputs():
    fs = data_api.build_factsheet("ACME")
    assert len(value_objects(fs)) > 50
