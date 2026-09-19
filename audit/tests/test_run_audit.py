"""Unit tests for audit.api.run_audit (plan.txt 15.14 P2 step 6.

"Done when: ... audit catches an injected fake number and a fabricated
quote" - the two tests below are exactly that.
"""
import copy
import json
from pathlib import Path

from audit import api as audit_api
from data import api as data_api

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


def _run(verdict, analyses=None, factsheet=None, metrics=None):
    factsheet = factsheet or load_fixture("factsheet.json")
    metrics = metrics or load_fixture("metrics.json")
    analyses = analyses if analyses is not None else list(verdict["agent_outputs"].values())
    return audit_api.run_audit(factsheet, metrics, analyses, verdict, data_api.get_section_text)


def test_acme_verdict_passes_audit():
    verdict = load_fixture("verdict.json")
    report = _run(verdict)
    assert report["passed"] is True
    assert not [i for i in report["issues"] if i["severity"] == "error"]


def test_catches_an_injected_fake_number():
    verdict = copy.deepcopy(load_fixture("verdict.json"))
    verdict["card"]["expected_5y_return"] = {
        "value": 0.99, "unit": "fraction", "type": "fact",
        "status": "ok", "source_id": "src:made:up:number",
    }
    report = _run(verdict)
    assert report["passed"] is False
    assert any("src:made:up:number" in i["message"] for i in report["issues"])


def test_catches_a_value_with_no_source_and_no_derivation():
    verdict = copy.deepcopy(load_fixture("verdict.json"))
    verdict["card"]["market_cap"] = {
        "value": 123.0, "unit": "usd", "type": "fact", "status": "ok", "source_id": None,
    }
    report = _run(verdict)
    assert report["passed"] is False
    assert any("neither a resolvable source_id nor derived_from" in i["message"] for i in report["issues"])


def test_catches_a_fabricated_quote():
    verdict = copy.deepcopy(load_fixture("verdict.json"))
    analyses = copy.deepcopy(list(verdict["agent_outputs"].values()))
    analyses[0]["findings"][0]["evidence"][0]["quote"] = "This sentence was never in any filing."
    report = _run(verdict, analyses=analyses)
    assert report["passed"] is False
    assert any("quote not found verbatim" in i["message"] for i in report["issues"])


def test_catches_evidence_citing_an_unknown_source():
    verdict = copy.deepcopy(load_fixture("verdict.json"))
    analyses = copy.deepcopy(list(verdict["agent_outputs"].values()))
    analyses[0]["findings"][0]["evidence"][0]["source_id"] = "src:edgar:nope:missing"
    report = _run(verdict, analyses=analyses)
    assert report["passed"] is False
    assert any("unknown source_id" in i["message"] for i in report["issues"])


def test_catches_a_missing_disclaimer():
    verdict = copy.deepcopy(load_fixture("verdict.json"))
    verdict["disclaimer"] = ""
    report = _run(verdict)
    assert report["passed"] is False
    assert any(i["path"] == "disclaimer" for i in report["issues"])


def test_catches_an_inconsistent_verdict():
    verdict = copy.deepcopy(load_fixture("verdict.json"))
    verdict["card"]["verdict"] = "strong_buy"  # ACME's expected return is below the S&P assumption
    report = _run(verdict)
    assert report["passed"] is False
    assert any(i["path"] == "consistency" for i in report["issues"])


def test_allowed_external_source_prefixes_do_not_trip_the_trace_check():
    """src:llm: and src:config: are documented exceptions (plan.txt 15.6)."""
    verdict = copy.deepcopy(load_fixture("verdict.json"))
    verdict["card"]["primary_catalyst"] = verdict["card"]["primary_catalyst"]
    verdict["scenario_result"]["sp500_expected_return"] = {
        "value": 0.07, "unit": "fraction", "type": "assumption",
        "status": "ok", "source_id": "src:config:calc_assumptions",
    }
    report = _run(verdict)
    assert not [i for i in report["issues"]
                if i["severity"] == "error" and "calc_assumptions" in i["message"]]
