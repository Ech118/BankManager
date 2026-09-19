"""Rule 2: every api.py function returns schema-valid output in mock mode. FROZEN (Step 0)."""
import pytest
from helpers import load_fixture, validation_errors, value_objects

from audit import api as audit_api
from calc import api as calc_api
from data import api as data_api
from orchestrator import api as orch_api


def _ok(obj, schema):
    errs = validation_errors(obj, schema)
    assert not errs, "\n".join(errs)


def test_data_api():
    assert data_api.check_scope("ACME") == {"in_scope": True, "reason": None}
    r = data_api.check_scope("BANKX")
    assert r["in_scope"] is False and r["reason"]
    assert data_api.check_scope("not a ticker")["in_scope"] is False
    fs = data_api.build_factsheet("ACME")
    _ok(fs, "factsheet.json")
    with pytest.raises(ValueError):
        data_api.build_factsheet("BANKX")
    secs = data_api.list_sections("ACME")
    assert secs and all("source_id" in s for s in secs)
    for s in secs:
        assert isinstance(data_api.get_section_text(s["source_id"]), str)
    with pytest.raises(KeyError):
        data_api.get_section_text("src:edgar:nope:missing")
    xs = data_api.get_xbrl("ACME", "revenue", 3)
    assert len(xs) == 3 and all(x["period"] for x in xs)
    assert [x["period"] for x in xs] == ["Q2-2026", "FY2025", "FY2024"]


def test_data_api_as_of_is_point_in_time():
    fs = data_api.build_factsheet("ACME", as_of="2025-06-01")
    _ok(fs, "factsheet.json")
    assert fs["mode"] == "backtest" and fs["as_of"] == "2025-06-01"
    assert all(p["filed_date"] <= "2025-06-01" for p in fs["financials"])
    assert [p["period"] for p in fs["financials"]] == ["FY2024", "FY2023"]
    with pytest.raises(ValueError):
        data_api.build_factsheet("ACME", as_of="2020-01-01")


def test_calc_api():
    fs = data_api.build_factsheet("ACME")
    metrics = calc_api.compute_metrics(fs)
    _ok(metrics, "metrics.json")
    assert calc_api.reverse_dcf(fs, metrics)["sensitivity_grid"]
    scen = load_fixture("scenarios.json")
    res = calc_api.evaluate_scenarios(scen, fs, metrics)
    _ok(res, "scenario_result.json")
    assert set(calc_api.derive_scores(res)) == {"short_term", "medium_term", "long_term"}
    assert calc_api.validate_consistency(res, load_fixture("verdict.json")["card"])["ok"] in (True, False)


def test_evaluate_scenarios_rejects_bad_probabilities():
    scen = load_fixture("scenarios.json")
    scen["scenarios"]["base"]["probability"] = 0.9
    with pytest.raises(ValueError):
        calc_api.evaluate_scenarios(scen, data_api.build_factsheet("ACME"), load_fixture("metrics.json"))


def test_audit_api():
    fs = data_api.build_factsheet("ACME")
    v = load_fixture("verdict.json")
    report = audit_api.run_audit(fs, load_fixture("metrics.json"), list(v["agent_outputs"].values()), v,
                                 data_api.get_section_text)
    _ok(report, "audit.json")


def test_orchestrator_api():
    v = orch_api.run_analysis("ACME")
    _ok(v, "verdict.json")
    assert v["disclaimer"]
    with pytest.raises(ValueError):
        orch_api.run_analysis("BANKX")


def test_value_objects_present_in_api_outputs():
    fs = data_api.build_factsheet("ACME")
    assert len(value_objects(fs)) > 50
