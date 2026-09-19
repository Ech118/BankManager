"""Unit tests for calc.consistency (plan.txt 15.14 P2 step 5)."""
import copy
import json
from pathlib import Path

from calc import api as calc_api

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "mock"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_acme_fixture_is_self_consistent():
    sr = load_fixture("scenario_result.json")
    card = load_fixture("verdict.json")["card"]
    result = calc_api.validate_consistency(sr, card)
    assert result["ok"] is True
    assert result["issues"] == []


def test_strong_buy_with_negative_excess_is_an_error():
    sr = load_fixture("scenario_result.json")
    card = copy.deepcopy(load_fixture("verdict.json")["card"])
    card["verdict"] = "strong_buy"
    result = calc_api.validate_consistency(sr, card)
    assert result["ok"] is False
    assert any("strong_buy" in issue for issue in result["issues"])


def test_mismatched_scores_are_flagged():
    sr = load_fixture("scenario_result.json")
    card = copy.deepcopy(load_fixture("verdict.json")["card"])
    card["scores"] = {"short_term": 9, "medium_term": 9, "long_term": 9}
    result = calc_api.validate_consistency(sr, card)
    assert result["ok"] is False
    assert any("scores" in issue for issue in result["issues"])


def test_mismatched_p_beat_sp500_is_flagged():
    sr = load_fixture("scenario_result.json")
    card = copy.deepcopy(load_fixture("verdict.json")["card"])
    card["p_beat_sp500_5y"] = 0.99
    result = calc_api.validate_consistency(sr, card)
    assert result["ok"] is False
    assert any("p_beat_sp500" in issue for issue in result["issues"])


def test_sell_with_strongly_positive_excess_is_flagged():
    sr = copy.deepcopy(load_fixture("scenario_result.json"))
    for h in sr["excess_vs_sp500"]:
        sr["excess_vs_sp500"][h]["value"] = 0.10
    card = copy.deepcopy(load_fixture("verdict.json")["card"])
    card["verdict"] = "sell"
    result = calc_api.validate_consistency(sr, card)
    assert result["ok"] is False
    assert any("sell" in issue for issue in result["issues"])
